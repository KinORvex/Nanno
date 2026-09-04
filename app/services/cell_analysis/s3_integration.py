"""
Integração do pipeline de visão computacional com o armazenamento em S3.

Fluxo típico (chamado por uma task de background/worker, ver README):
1. baixa a imagem original do S3 usando a `s3_key` salva em `MicroalgaeImage`;
2. roda o pipeline de análise (`pipeline.analyze_nannochloropsis_image`);
3. envia a imagem anotada de volta ao S3 sob uma nova key;
4. retorna um dicionário pronto para atualizar o registro no banco
   (compatível com `schemas.MicroalgaeImageMetricsUpdate` + a key da imagem anotada).
"""
import io
import logging
from typing import Optional

from app.services.cell_analysis.config import CellDetectionParams
from app.services.cell_analysis.exceptions import CellAnalysisError
from app.services.cell_analysis.pipeline import analyze_nannochloropsis_image
from app.services.exceptions import StorageServiceError
from app.services.s3_service import S3Service, s3_service

logger = logging.getLogger(__name__)


def _derive_annotated_key(source_key: str) -> str:
    """'project_id/abc123-imagem.png' -> 'project_id/abc123-imagem_annotated.png'"""
    if "." in source_key:
        base, ext = source_key.rsplit(".", 1)
        return f"{base}_annotated.png"
    return f"{source_key}_annotated.png"


def analyze_image_from_s3(
    source_key: str,
    params: Optional[CellDetectionParams] = None,
    sample_volume_context: Optional[dict] = None,
    annotated_key: Optional[str] = None,
    storage: S3Service = s3_service,
) -> dict:
    """
    Baixa uma imagem do S3, executa a análise completa e reenvia a versão
    anotada. Não toca no banco de dados — o chamador (endpoint/worker) decide
    como persistir o resultado.

    Returns:
        dict com todas as chaves de `AnalysisResult.to_dict()`, mais:
        - `source_s3_key`
        - `annotated_s3_key`
        - `annotated_s3_bucket`

    Raises:
        StorageServiceError: falha ao baixar/enviar do/para o S3.
        CellAnalysisError: falha no processamento da imagem em si.
    """
    annotated_key = annotated_key or _derive_annotated_key(source_key)

    buffer = io.BytesIO()
    try:
        storage.download_fileobj(key=source_key, file_obj=buffer)
    except StorageServiceError:
        logger.exception("Falha ao baixar imagem do S3 (key=%s) para análise", source_key)
        raise

    image_bytes = buffer.getvalue()

    try:
        result = analyze_nannochloropsis_image(
            image_bytes=image_bytes,
            params=params,
            sample_volume_context=sample_volume_context,
        )
    except CellAnalysisError:
        logger.exception("Falha ao analisar imagem baixada do S3 (key=%s)", source_key)
        raise

    try:
        upload_result = storage.upload_fileobj(
            file_obj=io.BytesIO(result.annotated_image_bytes),
            key=annotated_key,
            content_type="image/png",
            size_bytes=len(result.annotated_image_bytes),
        )
    except StorageServiceError:
        logger.exception("Falha ao enviar imagem anotada para o S3 (key=%s)", annotated_key)
        raise

    payload = result.to_dict(include_individual_measurements=True)
    payload.update(
        {
            "source_s3_key": source_key,
            "annotated_s3_key": upload_result.key,
            "annotated_s3_bucket": upload_result.bucket,
        }
    )
    return payload
