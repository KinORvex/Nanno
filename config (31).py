"""
Configurações centrais da aplicação.

Todas as variáveis sensíveis são carregadas do ambiente (.env) usando
pydantic-settings, o que garante validação de tipos e falha rápida
caso alguma variável obrigatória esteja ausente em produção.
"""
from functools import lru_cache
from typing import List, Optional

from pydantic import AnyHttpUrl, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Aplicação ---
    PROJECT_NAME: str = "Nannochloropsis Image Analysis API"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"  # development | staging | production
    DEBUG: bool = False
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []

    # --- Banco de dados (PostgreSQL) ---
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DATABASE_URI: Optional[PostgresDsn] = None
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    @field_validator("DATABASE_URI", mode="before")
    @classmethod
    def assemble_db_uri(cls, v: Optional[str], info) -> str:
        if isinstance(v, str) and v:
            return v
        values = info.data
        return (
            f"postgresql+psycopg://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}"
            f"@{values['POSTGRES_SERVER']}:{values['POSTGRES_PORT']}/{values['POSTGRES_DB']}"
        )

    # --- Segurança / JWT ---
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 dias

    # --- AWS S3 ---
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str
    S3_ENDPOINT_URL: Optional[str] = None  # útil para MinIO / testes locais
    S3_PRESIGNED_URL_EXPIRATION: int = 3600  # segundos
    S3_USE_SSL: bool = True

    # --- Upload ---
    MAX_UPLOAD_SIZE_MB: int = 25
    ALLOWED_IMAGE_CONTENT_TYPES: List[str] = [
        "image/png",
        "image/jpeg",
        "image/tiff",
    ]


@lru_cache
def get_settings() -> Settings:
    """Cacheia a instância de Settings (evita reparsing do .env)."""
    return Settings()


settings = get_settings()
