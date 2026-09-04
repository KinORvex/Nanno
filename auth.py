"""
Endpoints de autenticação. São as ÚNICAS rotas públicas da API — todas as
demais exigem um Bearer token válido (ver `app/api/deps.py::get_current_user`).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token, decode_token, verify_password
from app.crud.user import create_user, get_user_by_email
from app.models.user import User
from app.schemas.user import RefreshTokenRequest, Token, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma nova conta de usuário",
)
def register(user_in: UserCreate, db: Session = Depends(get_db)) -> User:
    if get_user_by_email(db, user_in.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Este e-mail já está cadastrado.")

    try:
        return create_user(db, user_in)
    except IntegrityError as exc:
        # Proteção contra corrida (duas requisições de registro concorrentes
        # com o mesmo e-mail passando pela checagem acima ao mesmo tempo).
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Este e-mail já está cadastrado.") from exc


@router.post(
    "/login",
    response_model=Token,
    summary="Autentica e retorna access/refresh tokens JWT",
)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    # OAuth2PasswordRequestForm usa "username" como nome do campo por
    # convenção do padrão OAuth2 — aqui ele carrega o e-mail do usuário.
    user = get_user_by_email(db, form_data.username)

    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Usuário inativo.")

    return Token(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post(
    "/refresh",
    response_model=Token,
    summary="Troca um refresh token válido por um novo par access/refresh",
)
def refresh_token(payload: RefreshTokenRequest, db: Session = Depends(get_db)) -> Token:
    invalid_token_exc = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token inválido ou expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        decoded = decode_token(payload.refresh_token)
    except JWTError as exc:
        raise invalid_token_exc from exc

    if decoded.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token fornecido não é um refresh token.")

    subject = decoded.get("sub")
    if subject is None:
        raise invalid_token_exc

    try:
        user = db.get(User, uuid.UUID(subject))
    except ValueError as exc:
        raise invalid_token_exc from exc

    if user is None or not user.is_active:
        raise invalid_token_exc

    return Token(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.get(
    "/me",
    response_model=UserRead,
    summary="Retorna os dados do usuário autenticado (usado pelo frontend para validar o token)",
)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
