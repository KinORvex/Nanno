"""
Fixtures compartilhadas de teste.

⚠️ Requer uma instância PostgreSQL de teste acessível (via TEST_DATABASE_URI).
NUNCA aponte isso para o banco de produção — Base.metadata.create_all e
drop_all são executados contra essa URL.

Isolamento entre testes: cada teste roda dentro de uma transação com
SAVEPOINT (join_transaction_mode="create_savepoint", recurso do SQLAlchemy
2.0), que é revertida ao final — mesmo que o código da aplicação chame
`db.commit()` internamente (como os endpoints fazem), o rollback externo
desfaz tudo, então os testes não precisam limpar dados manualmente.
"""
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.crud.project import create_project
from app.main import app
from app.models.user import User
from app.schemas.project import ProjectCreate

TEST_DATABASE_URI = os.environ.get(
    "TEST_DATABASE_URI",
    "postgresql+psycopg://nanno_user:nice@localhost:5432/nanno_analysis_test",
)


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(TEST_DATABASE_URI)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    def _get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session) -> User:
    user = User(
        email=f"pytest+{uuid.uuid4().hex[:8]}@example.com",
        full_name="Pytest User",
        hashed_password=hash_password("senha-teste-123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def other_user(db_session) -> User:
    user = User(
        email=f"other+{uuid.uuid4().hex[:8]}@example.com",
        full_name="Other User",
        hashed_password=hash_password("outra-senha-123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user) -> dict:
    token = create_access_token(str(test_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_auth_headers(other_user) -> dict:
    token = create_access_token(str(other_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_project(db_session, test_user):
    return create_project(db_session, owner_id=test_user.id, project_in=ProjectCreate(name="Projeto de teste"))
