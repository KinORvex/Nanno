"""Handlers globais de exceção. Garantem que erros de infraestrutura (S3, DB)
nunca vazem stack traces para o cliente e sempre retornem um JSON padronizado."""
import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.services.exceptions import (
    InvalidFileError,
    StorageObjectNotFoundError,
    StorageServiceError,
)

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(InvalidFileError)
    async def invalid_file_handler(request: Request, exc: InvalidFileError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(exc)})

    @app.exception_handler(StorageObjectNotFoundError)
    async def storage_not_found_handler(
        request: Request, exc: StorageObjectNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    @app.exception_handler(StorageServiceError)
    async def storage_service_error_handler(request: Request, exc: StorageServiceError) -> JSONResponse:
        logger.error("Erro de storage não tratado: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "Falha ao comunicar com o serviço de armazenamento."},
        )

    @app.exception_handler(SQLAlchemyError)
    async def db_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("Erro de banco de dados não tratado")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Erro interno ao acessar o banco de dados."},
        )
