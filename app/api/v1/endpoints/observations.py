"""
Endpoints de Observation: registro de timepoints de uma Culture, e upload
de imagens associadas a uma observação.

IMPORTANTE: o upload de imagem AQUI reaproveita exatamente a mesma função
de pipeline (`analyze_nannochloropsis_image`) e o mesmo `s3_service` do
endpoint `/analyze` já existente — nenhuma lógica de visão computacional é
duplicada ou reescrita. O endpoint `/analyze` original permanece 100%
intocado neste arquivo; esta é uma rota adicional para o fluxo de
experimentos controlados, não uma substituição.
"""
import io
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud.culture import get_culture
from app.crud.observation import create_observation, get_observation, list_observations
from app.models.culture import Culture
from app.models.image import MicroalgaeImage, ProcessingStatus
from app.models.image_analysis import ImageAnalysis
from app.models.observation import Observation
from app.models.user import User
from app.schemas.image_analysis import ImageAnalysisRead
from app.schemas.observation import ObservationCreate, ObservationRead
from app.services.cell_analysis import (
    CellAnalysisError,
    CellDetectionParams,
    InvalidImageError,
    analyze_nannochloropsis_image,
)
from app.services.exceptions import InvalidFileError, StorageServiceError
from app.services.s3_service import s3_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cultures/{culture_id}/observations", tags=["observations"])
image_router = APIRouter(prefix="/observations/{observation_id}", tags=["observations"])


def _get_owned_culture(db: Session, culture_id: uuid.UUID, user: User) -> Culture:
    culture = get_culture(db, culture_id)
    if culture is None or culture.experiment.project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cultura não encontrada.")
    return culture


def _get_owned_observation(db: Session, observation_id: uuid.UUID, user: User) -> Observation:
    observation = get_observation(db, observation_id)
    if observation is None or observation.culture.experiment.project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Observação não encontrada.")
    return observation


@router.post(
    "", response_model=ObservationRead, status_code=status.HTTP_201_CREATED,
    summary="Registra uma nova observação (timepoint) de uma cultura",
)
def create_new_observation(
    culture_id: uuid.UUID,
    observation_in: ObservationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Observation:
    culture = _get_owned_culture(db, culture_id, current_user)
    return create_observation(db, culture=culture, observation_in=observation_in)


@router.get("", response_model=List[ObservationRead], summary="Lista as observações de uma cultura")
def list_culture_observations(
    culture_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Observation]:
    culture = _get_owned_culture(db, culture_id, current_user)
    return list_observations(db, culture_id=culture.id)


@image_router.post(
    "/images",
    response_model=ImageAnalysisRead,
    status_code=status.HTTP_201_CREATED,
    summary="Envia uma imagem para uma observação (reaproveita o pipeline de visão computacional existente)",
)
async def upload_observation_image(
    observation_id: uuid.UUID,
    file: UploadFile = File(..., description="Imagem de microscopia (PNG/JPEG/TIFF)."),
    microns_per_pixel: float = Form(0.1, gt=0),
    chamber_depth_um: Optional[float] = Form(None, gt=0),
    dilution_factor: float = Form(1.0, gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImageAnalysis:
    observation = _get_owned_observation(db, observation_id, current_user)
    project_id = observation.culture.experiment.project_id

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Arquivo de imagem vazio.")

    original_key = s3_service.build_object_key(project_id=project_id, filename=file.filename or "image")

    # --- 1. Upload do original (mesmo s3_service do endpoint /analyze) ---
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
        logger.exception("Falha ao enviar imagem da observação para o S3")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Falha ao enviar imagem: {exc}") from exc

    # --- 2. Registro da imagem (MicroalgaeImage, já com observation_id) ---
    image = MicroalgaeImage(
        project_id=project_id,
        observation_id=observation.id,
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

    # --- 3. Registro da análise versionada (ImageAnalysis) ---
    analysis = ImageAnalysis(
        image_id=image.id,
        observation_id=observation.id,
        status=ProcessingStatus.PROCESSING,
        algorithm_name="nannochloropsis_watershed",
        algorithm_version="v1",
        parameters={"microns_per_pixel": microns_per_pixel},
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    # --- 4. Pipeline de CV — MESMA função usada por /analyze, não duplicada ---
    params = CellDetectionParams(microns_per_pixel=microns_per_pixel)
    sample_volume_context = (
        {"chamber_depth_um": chamber_depth_um, "dilution_factor": dilution_factor} if chamber_depth_um else None
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
        analysis.status = ProcessingStatus.FAILED
        analysis.processing_error = str(exc)[:2000]
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Falha ao processar imagem: {exc}") from exc

    # --- 5. Persiste métricas (formato "v1" documentado em models/image_analysis.py) ---
    diameter_stats = result.summary.get("diameter_um", {})
    area_stats = result.summary.get("area_um2", {})
    diameter_mean = diameter_stats.get("mean")
    diameter_std = diameter_stats.get("std")
    diameter_cv = (
        (diameter_std / diameter_mean) if diameter_mean and diameter_std is not None and diameter_mean > 0 else None
    )

    metrics = {
        "cell_count": result.cell_count,
        "diameter_mean_um": diameter_mean,
        "diameter_median_um": diameter_stats.get("median"),
        "diameter_std_um": diameter_std,
        "diameter_cv": diameter_cv,
        "diameter_p25_um": diameter_stats.get("p25"),
        "diameter_p75_um": diameter_stats.get("p75"),
        "area_mean_um2": area_stats.get("mean"),
        "avg_confidence_score": result.summary.get("avg_confidence_score"),
        "cell_density_cells_per_ml": result.summary.get("cell_density_cells_per_ml"),
    }

    image.processing_status = ProcessingStatus.COMPLETED
    image.processing_error = None
    image.cell_count = result.cell_count
    image.avg_cell_diameter_um = diameter_mean
    image.std_cell_diameter_um = diameter_std
    image.cell_density_cells_per_ml = result.summary.get("cell_density_cells_per_ml")
    image.confidence_score = result.summary.get("avg_confidence_score")
    image.extra_metrics = {
        "diameter_um": diameter_stats,
        "area_um2": area_stats,
        "diameters_um": [m.equivalent_diameter_um for m in result.measurements],
        "processing_time_ms": result.processing_time_ms,
    }

    analysis.status = ProcessingStatus.COMPLETED
    analysis.processing_error = None
    analysis.metrics = metrics

    db.commit()
    db.refresh(analysis)

    return analysis


@image_router.get(
    "/analyses", response_model=List[ImageAnalysisRead],
    summary="Lista as análises de imagem de uma observação",
)
def list_observation_analyses(
    observation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ImageAnalysis]:
    observation = _get_owned_observation(db, observation_id, current_user)
    return sorted(observation.analyses, key=lambda a: a.created_at, reverse=True)
