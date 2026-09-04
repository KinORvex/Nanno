"""
Endpoint principal de análise: recebe a imagem via multipart/form-data,
envia o original para o S3, executa o pipeline de visão computacional
(OpenCV + scikit-image), persiste os resultados no PostgreSQL e devolve a
contagem de células + distribuição de tamanhos.
"""
import io
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.image import MicroalgaeImage, ProcessingStatus
from app.models.project import AnalysisProject
from app.models.user import User
from app.schemas.analyze import AnalyzeImageResponse, AreaDistributionStats, SizeDistributionStats
from app.services.cell_analysis import (
    CellAnalysisError,
    CellDetectionParams,
    InvalidImageError,
    analyze_nannochloropsis_image,
)
from app.services.exceptions import InvalidFileError, StorageServiceError
from app.services.s3_service import s3_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyze", tags=["analyze"])


def _get_owned_project(db: Session, project_id: uuid.UUID, user: User) -> AnalysisProject:
    project = db.get(AnalysisProject, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado.")
    return project


@router.post(
    "",
    response_model=AnalyzeImageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Envia uma imagem de microscopia e retorna contagem/tamanho das células detectadas",
)
async def analyze_image(
    project_id: uuid.UUID = Form(..., description="ID do AnalysisProject ao qual a imagem pertence."),
    file: UploadFile = File(..., description="Imagem de microscopia (PNG/JPEG/TIFF)."),
    microns_per_pixel: float = Form(
        0.1, gt=0, description="Calibração óptica: micrômetros representados por cada pixel."
    ),
    chamber_depth_um: Optional[float] = Form(
        None, gt=0, description="Opcional: profundidade da câmara de contagem, para estimar densidade celular."
    ),
    dilution_factor: float = Form(1.0, gt=0, description="Fator de diluição da amostra, se houver."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalyzeImageResponse:
    project = _get_owned_project(db, project_id, current_user)

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Arquivo de imagem vazio.")

    original_key = s3_service.build_object_key(project_id=project.id, filename=file.filename or "image")

    # --- 1. Upload do original para o S3 ---
    try:
        upload_result = await run_in_threadpool(
            s3_service.upload_fileobj,
            file_obj=io.BytesIO(raw_bytes),
            key=original_key,
            content_type=file.content_type,
            size_bytes=len(raw_bytes),
        )
    except InvalidFileError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except StorageServiceError as exc:
        logger.exception("Falha ao enviar imagem original para o S3")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Falha ao enviar imagem: {exc}") from exc

    # --- 2. Registro inicial no banco (permite auditar falhas de processamento) ---
    image = MicroalgaeImage(
        project_id=project.id,
        original_filename=file.filename or "image",
        s3_bucket=upload_result.bucket,
        s3_key=upload_result.key,
        content_type=upload_result.content_type,
        file_size_bytes=upload_result.size_bytes,
        processing_status=ProcessingStatus.PROCESSING,
    )
    db.add(image)
    db.commit()
    db.refresh(image)

    # --- 3. Pipeline de visão computacional (CPU-bound -> threadpool) ---
    params = CellDetectionParams(microns_per_pixel=microns_per_pixel)
    sample_volume_context = (
        {"chamber_depth_um": chamber_depth_um, "dilution_factor": dilution_factor}
        if chamber_depth_um
        else None
    )

    try:
        result = await run_in_threadpool(
            analyze_nannochloropsis_image,
            image_bytes=raw_bytes,
            params=params,
            sample_volume_context=sample_volume_context,
        )
    except (InvalidImageError, CellAnalysisError) as exc:
        image.processing_status = ProcessingStatus.FAILED
        image.processing_error = str(exc)[:2000]
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Falha ao processar imagem: {exc}") from exc

    # --- 4. Upload da imagem anotada ---
    annotated_key = original_key.rsplit(".", 1)[0] + "_annotated.png" if "." in original_key else original_key + "_annotated.png"
    try:
        annotated_upload = await run_in_threadpool(
            s3_service.upload_fileobj,
            file_obj=io.BytesIO(result.annotated_image_bytes),
            key=annotated_key,
            content_type="image/png",
            size_bytes=len(result.annotated_image_bytes),
        )
        annotated_url = await run_in_threadpool(
            s3_service.generate_presigned_download_url, key=annotated_upload.key
        )
    except StorageServiceError as exc:
        # A análise em si teve sucesso — não descartamos os resultados por
        # uma falha no upload da imagem anotada, apenas registramos o erro.
        logger.exception("Falha ao enviar/assinar imagem anotada (análise já concluída, key=%s)", annotated_key)
        image.processing_status = ProcessingStatus.FAILED
        image.processing_error = f"Análise concluída, mas falhou o upload da imagem anotada: {exc}"
        db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    # --- 5. Persiste os resultados ---
    diameter_stats = result.summary.get("diameter_um", {})
    area_stats = result.summary.get("area_um2", {})

    image.processing_status = ProcessingStatus.COMPLETED
    image.processing_error = None
    image.cell_count = result.cell_count
    image.avg_cell_diameter_um = diameter_stats.get("mean")
    image.std_cell_diameter_um = diameter_stats.get("std")
    image.cell_density_cells_per_ml = result.summary.get("cell_density_cells_per_ml")
    image.confidence_score = result.summary.get("avg_confidence_score")
    image.extra_metrics = {
        "diameter_um": diameter_stats,
        "area_um2": area_stats,
        "diameters_um": [m.equivalent_diameter_um for m in result.measurements],
        "annotated_s3_key": annotated_upload.key,
        "processing_time_ms": result.processing_time_ms,
    }
    db.commit()
    db.refresh(image)

    return AnalyzeImageResponse(
        image_id=image.id,
        project_id=project.id,
        cell_count=result.cell_count,
        diameter_um=SizeDistributionStats(**diameter_stats),
        area_um2=AreaDistributionStats(**area_stats),
        avg_confidence_score=result.summary.get("avg_confidence_score"),
        cell_density_cells_per_ml=result.summary.get("cell_density_cells_per_ml"),
        diameters_um=[m.equivalent_diameter_um for m in result.measurements],
        processing_time_ms=result.processing_time_ms,
        microns_per_pixel=microns_per_pixel,
        original_s3_key=upload_result.key,
        annotated_s3_key=annotated_upload.key,
        annotated_image_download_url=annotated_url,
    )
