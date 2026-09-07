"""Ponto de entrada da aplicação FastAPI."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

OPENAPI_TAGS = [
    {"name": "auth", "description": "Registro, login e renovação de token JWT. Únicas rotas públicas da API."},
    {"name": "projects", "description": "CRUD de projetos/sessões de análise (AnalysisProject)."},
    {"name": "analyze", "description": "Upload de imagem de microscopia + pipeline de visão computacional (OpenCV/scikit-image) + persistência dos resultados."},
    {"name": "trends", "description": "Leitura/cálculo das estimativas de tendência populacional geradas pelo modelo PyTorch."},
    {"name": "forecast", "description": "Cálculo explícito de uma nova previsão de tendência (variante de escrita de 'trends')."},
    {"name": "images", "description": "Upload/download avulso de imagens no S3, sem disparar o pipeline de análise."},
    {"name": "health", "description": "Verificação de disponibilidade do serviço."},
]

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    openapi_tags=OPENAPI_TAGS,
)

if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "environment": settings.ENVIRONMENT}
