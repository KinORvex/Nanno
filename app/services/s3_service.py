"""
Serviço utilitário para gerenciar upload e download de imagens no Amazon S3.

Design:
- boto3 é uma biblioteca síncrona; para não bloquear o event loop do FastAPI,
  os endpoints devem chamar estes métodos via `starlette.concurrency.run_in_threadpool`
  (exemplo no final deste arquivo e em api/v1/endpoints/images.py).
- Todas as exceções do boto3/botocore são capturadas e traduzidas para exceções
  de domínio (app.services.exceptions), para que o restante da aplicação nunca
  precise importar botocore diretamente.
- O client é criado uma única vez (singleton) e reutilizado — criar um client
  por requisição é um anti-padrão de performance.
"""
from __future__ import annotations

import logging
import mimetypes
import uuid
from dataclasses import dataclass
from typing import BinaryIO, Optional

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
    ParamValidationError,
)

from app.core.config import settings
from app.services.exceptions import (
    InvalidFileError,
    StorageConfigurationError,
    StorageDeleteError,
    StorageDownloadError,
    StorageObjectNotFoundError,
    StorageUploadError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadResult:
    """Resultado de um upload bem-sucedido, pronto para persistir no model MicroalgaeImage."""

    bucket: str
    key: str
    content_type: str
    size_bytes: int
    etag: Optional[str] = None


class S3Service:
    """Encapsula toda a interação com o Amazon S3 para o domínio de imagens.

    O client boto3 é criado de forma lazy (na primeira chamada que efetivamente
    precisa dele, via a property `_client`), e não no `__init__`. Isso permite
    que o singleton `s3_service` seja importado/instanciado em qualquer
    ambiente (dev sem S3/MinIO rodando, testes, coleta do pytest) sem exigir
    que o serviço externo esteja disponível — o erro de configuração/conexão
    só é levantado quando alguma rota realmente tenta usar o S3.
    """

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        region_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ) -> None:
        self.bucket_name = bucket_name or settings.S3_BUCKET_NAME
        if not self.bucket_name:
            raise StorageConfigurationError("S3_BUCKET_NAME não configurado.")

        self._region_name = region_name or settings.AWS_REGION
        # String vazia ("" no .env quando S3_ENDPOINT_URL não é definido) não é
        # um endpoint válido para o boto3 — precisa virar None para que o SDK
        # use o endpoint padrão da AWS em vez de tentar conectar em "".
        self._endpoint_url = (endpoint_url or settings.S3_ENDPOINT_URL) or None
        self.__client = None

    @property
    def _client(self):
        if self.__client is None:
            try:
                self.__client = boto3.client(
                    "s3",
                    region_name=self._region_name,
                    endpoint_url=self._endpoint_url,
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    # SigV4 + addressing path-style funcionam tanto com AWS real
                    # quanto com MinIO/localstack em desenvolvimento.
                    config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
                    use_ssl=settings.S3_USE_SSL,
                )
            except (BotoCoreError, ValueError) as exc:
                logger.exception("Falha ao inicializar client S3")
                raise StorageConfigurationError(f"Não foi possível inicializar o client S3: {exc}") from exc
        return self.__client

    # ------------------------------------------------------------------ #
    # Helpers internos
    # ------------------------------------------------------------------ #

    @staticmethod
    def build_object_key(project_id: uuid.UUID, filename: str) -> str:
        """
        Gera uma key determinística e organizada por projeto, evitando colisões
        de nome e permitindo listagens eficientes por prefixo (project_id/).
        Exemplo: '3f1c.../a92e1c4e-image_01.png'
        """
        safe_name = filename.replace(" ", "_")
        unique_prefix = uuid.uuid4().hex[:12]
        return f"{project_id}/{unique_prefix}-{safe_name}"

    def _validate_file(self, content_type: str, size_bytes: int) -> None:
        if content_type not in settings.ALLOWED_IMAGE_CONTENT_TYPES:
            raise InvalidFileError(
                f"Tipo de arquivo '{content_type}' não permitido. "
                f"Tipos aceitos: {', '.join(settings.ALLOWED_IMAGE_CONTENT_TYPES)}"
            )
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if size_bytes > max_bytes:
            raise InvalidFileError(
                f"Arquivo de {size_bytes / (1024 * 1024):.2f}MB excede o limite "
                f"de {settings.MAX_UPLOAD_SIZE_MB}MB."
            )

    # ------------------------------------------------------------------ #
    # Upload
    # ------------------------------------------------------------------ #

    def upload_fileobj(
        self,
        file_obj: BinaryIO,
        key: str,
        content_type: Optional[str] = None,
        size_bytes: Optional[int] = None,
    ) -> UploadResult:
        """
        Envia um objeto (stream de arquivo) para o S3.

        `file_obj` deve ser um objeto binário posicionado no início (seek(0)).
        Em FastAPI, `UploadFile.file` satisfaz essa interface.
        """
        resolved_content_type = content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"

        if size_bytes is not None:
            self._validate_file(resolved_content_type, size_bytes)

        try:
            file_obj.seek(0)
            self._client.upload_fileobj(
                Fileobj=file_obj,
                Bucket=self.bucket_name,
                Key=key,
                ExtraArgs={
                    "ContentType": resolved_content_type,
                    "ServerSideEncryption": "AES256",
                },
            )
            head = self._client.head_object(Bucket=self.bucket_name, Key=key)
        except NoCredentialsError as exc:
            logger.exception("Credenciais AWS ausentes ao fazer upload da key=%s", key)
            raise StorageConfigurationError("Credenciais AWS não configuradas.") from exc
        except EndpointConnectionError as exc:
            logger.exception("Falha de conexão com o S3 ao fazer upload da key=%s", key)
            raise StorageUploadError(f"Não foi possível conectar ao S3: {exc}") from exc
        except (ClientError, ParamValidationError) as exc:
            logger.exception("Erro do S3 ao fazer upload da key=%s", key)
            raise StorageUploadError(f"Falha no upload para o S3 (key={key}): {exc}") from exc
        except BotoCoreError as exc:
            logger.exception("Erro inesperado do boto3 ao fazer upload da key=%s", key)
            raise StorageUploadError(f"Erro inesperado no upload: {exc}") from exc

        return UploadResult(
            bucket=self.bucket_name,
            key=key,
            content_type=resolved_content_type,
            size_bytes=head.get("ContentLength", size_bytes or 0),
            etag=head.get("ETag"),
        )

    # ------------------------------------------------------------------ #
    # Download
    # ------------------------------------------------------------------ #

    def download_fileobj(self, key: str, file_obj: BinaryIO) -> None:
        """Baixa o objeto do S3 e escreve seu conteúdo em `file_obj` (ex.: BytesIO)."""
        try:
            self._client.download_fileobj(Bucket=self.bucket_name, Key=key, Fileobj=file_obj)
            file_obj.seek(0)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey"}:
                raise StorageObjectNotFoundError(f"Objeto não encontrado: {key}") from exc
            logger.exception("Erro do S3 ao baixar key=%s", key)
            raise StorageDownloadError(f"Falha no download do S3 (key={key}): {exc}") from exc
        except EndpointConnectionError as exc:
            logger.exception("Falha de conexão com o S3 ao baixar key=%s", key)
            raise StorageDownloadError(f"Não foi possível conectar ao S3: {exc}") from exc
        except BotoCoreError as exc:
            logger.exception("Erro inesperado do boto3 ao baixar key=%s", key)
            raise StorageDownloadError(f"Erro inesperado no download: {exc}") from exc

    def generate_presigned_upload_url(
        self, key: str, content_type: str, expires_in: Optional[int] = None
    ) -> str:
        """Gera uma URL pré-assinada para o cliente fazer upload direto (sem passar pela API)."""
        try:
            return self._client.generate_presigned_url(
                ClientMethod="put_object",
                Params={"Bucket": self.bucket_name, "Key": key, "ContentType": content_type},
                ExpiresIn=expires_in or settings.S3_PRESIGNED_URL_EXPIRATION,
            )
        except (ClientError, BotoCoreError) as exc:
            logger.exception("Erro ao gerar presigned URL de upload para key=%s", key)
            raise StorageUploadError(f"Falha ao gerar URL de upload: {exc}") from exc

    def generate_presigned_download_url(self, key: str, expires_in: Optional[int] = None) -> str:
        """Gera uma URL pré-assinada temporária para leitura/download do objeto."""
        if not self.object_exists(key):
            raise StorageObjectNotFoundError(f"Objeto não encontrado: {key}")
        try:
            return self._client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_in or settings.S3_PRESIGNED_URL_EXPIRATION,
            )
        except (ClientError, BotoCoreError) as exc:
            logger.exception("Erro ao gerar presigned URL de download para key=%s", key)
            raise StorageDownloadError(f"Falha ao gerar URL de download: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Utilitários
    # ------------------------------------------------------------------ #

    def object_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey"}:
                return False
            logger.exception("Erro ao verificar existência da key=%s", key)
            raise StorageDownloadError(f"Falha ao verificar objeto (key={key}): {exc}") from exc

    def delete_object(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket_name, Key=key)
        except (ClientError, BotoCoreError) as exc:
            logger.exception("Erro ao deletar key=%s", key)
            raise StorageDeleteError(f"Falha ao deletar objeto (key={key}): {exc}") from exc


# Singleton reutilizado pela aplicação inteira (evita recriar o client boto3
# a cada requisição). Importar diretamente: `from app.services.s3_service import s3_service`.
s3_service = S3Service()
