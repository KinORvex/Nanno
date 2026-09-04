"""
Endpoints de imagens: upload para o S3 + persistência de metadados,
e geração de URL de download.

boto3 é síncrono — por isso as chamadas ao S3Service são delegadas a um
threadpool (`run_in_threadpool`) para não bloquear o event loop do FastAPI.
"""
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.image import MicroalgaeImage, ProcessingStatus
from app.models.project import AnalysisProject
from app.models.user import User
from app.schemas.image import MicroalgaeImageDownloadURL, MicroalgaeImageRead
from app.services.exceptions import InvalidFileError, StorageObjectNotFoundError, StorageServiceError
from app.services.s3_service import s3_service

router = APIRouter(prefix="/images", tags=["images"])


def _get_owned_project(db: Session, project_id: uuid.UUID, user: User) -> AnalysisProject:
    project = db.get(AnalysisProject, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado.")
    return project


@router.post(
    "/projects/{project_id}/upload",
    response_model=MicroalgaeImageRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_image(
    project_id: uuid.UUID,
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MicroalgaeImage:
    project = _get_owned_project(db, project_id, current_user)

    raw_bytes = await file.read()
    key = s3_service.build_object_key(project_id=project.id, filename=file.filename or "image")

    try:
        upload_result = await run_in_threadpool(
            s3_service.upload_fileobj,
            file_obj=io.BytesIO(raw_bytes),
            key=key,
            content_type=file.content_type,
            size_bytes=len(raw_bytes),
        )
    except InvalidFileError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except StorageServiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Falha ao enviar imagem: {exc}") from exc

    image = MicroalgaeImage(
        project_id=project.id,
        original_filename=file.filename or "image",
        s3_bucket=upload_result.bucket,
        s3_key=upload_result.key,
        content_type=upload_result.content_type,
        file_size_bytes=upload_result.size_bytes,
        processing_status=ProcessingStatus.PENDING,
    )
    db.add(image)
    db.commit()
    db.refresh(image)

    # Em produção: disparar aqui uma task assíncrona (Celery/RQ) que baixa a
    # imagem do S3, roda o pipeline de contagem/tamanho de células e faz o
    # PATCH das métricas (ver schemas.MicroalgaeImageMetricsUpdate).
    return image


@router.get("/{image_id}/download-url", response_model=MicroalgaeImageDownloadURL)
async def get_download_url(
    image_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MicroalgaeImageDownloadURL:
    image = db.get(MicroalgaeImage, image_id)
    if image is None or image.project.owner_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Imagem não encontrada.")

    try:
        url = await run_in_threadpool(s3_service.generate_presigned_download_url, key=image.s3_key)
    except StorageObjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StorageServiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Falha ao gerar URL: {exc}") from exc

    from app.core.config import settings

    return MicroalgaeImageDownloadURL(url=url, expires_in=settings.S3_PRESIGNED_URL_EXPIRATION)


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(
    image_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    image = db.get(MicroalgaeImage, image_id)
    if image is None or image.project.owner_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Imagem não encontrada.")

    try:
        await run_in_threadpool(s3_service.delete_object, key=image.s3_key)
    except StorageServiceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Falha ao remover do S3: {exc}") from exc

    db.delete(image)
    db.commit()
