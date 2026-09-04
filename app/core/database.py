"""
Configuração de conexão com o PostgreSQL usando SQLAlchemy 2.0 (estilo async-ready).

Expõe:
- `engine`: engine síncrona do SQLAlchemy
- `SessionLocal`: fábrica de sessões
- `Base`: classe declarativa base para os models
- `get_db`: dependency do FastAPI para injeção de sessão por request
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    str(settings.DATABASE_URI),
    pool_pre_ping=True,          # evita conexões mortas em produção
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


class Base(DeclarativeBase):
    """Classe base declarativa para todos os models ORM."""
    pass


def get_db() -> Generator[Session, None, None]:
    """
    Dependency do FastAPI: fornece uma sessão por requisição e garante
    o fechamento correto mesmo em caso de exceção.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session_scope() -> Generator[Session, None, None]:
    """
    Context manager para uso fora do ciclo de request do FastAPI
    (ex.: scripts, workers, tasks assíncronas/Celery).
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
