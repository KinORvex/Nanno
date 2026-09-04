"""Exceções específicas do domínio de armazenamento (S3), desacopladas do
boto3/botocore para que a camada de API não precise conhecer detalhes da AWS."""


class StorageServiceError(Exception):
    """Erro base — não deve ser instanciada diretamente."""


class StorageUploadError(StorageServiceError):
    """Falha ao enviar um arquivo para o storage."""


class StorageDownloadError(StorageServiceError):
    """Falha ao baixar/ler um arquivo do storage."""


class StorageObjectNotFoundError(StorageServiceError):
    """O objeto solicitado não existe no bucket."""


class StorageDeleteError(StorageServiceError):
    """Falha ao remover um arquivo do storage."""


class StorageConfigurationError(StorageServiceError):
    """Credenciais ausentes/inválidas ou bucket mal configurado."""


class InvalidFileError(StorageServiceError):
    """Arquivo rejeitado antes mesmo de tentar o upload (tipo/tamanho inválido)."""
