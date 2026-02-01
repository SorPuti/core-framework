"""
Autenticação JWT para a aplicação de exemplo.

Demonstra:
- Login com JWT
- Registro de usuário
- Configuração de autenticação no framework
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import APIRouter, HTTPException, status, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db, configure_auth
from core.permissions import AllowAny

from example.models import User
from example.schemas import (
    LoginInput,
    TokenOutput,
    RegisterInput,
    UserOutput,
)


# Configurações JWT (em produção, use variáveis de ambiente)
JWT_SECRET = "your-secret-key-change-in-production"
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


# Router de autenticação
auth_router = APIRouter(prefix="/auth", tags=["auth"])


def create_access_token(user_id: int) -> str:
    """Cria um token JWT."""
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decodifica um token JWT."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


async def load_user(user_id: str) -> User | None:
    """Carrega usuário por ID."""
    from core.models import get_session
    
    session = await get_session()
    try:
        user = await User.objects.using(session).get_or_none(id=int(user_id))
        return user
    finally:
        await session.close()


def setup_auth() -> None:
    """Configura autenticação no framework."""
    configure_auth(
        user_loader=load_user,
        token_decoder=decode_token,
    )


@auth_router.post("/login", response_model=TokenOutput)
async def login(
    data: LoginInput,
    db: AsyncSession = Depends(get_db),
) -> TokenOutput:
    """
    Autentica usuário e retorna token JWT.
    
    - **email**: Email do usuário
    - **password**: Senha do usuário
    """
    # Busca usuário por email
    user = await User.objects.using(db).get_or_none(email=data.email.lower())
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    # Verifica senha
    if not user.verify_password(data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    # Verifica se usuário está ativo
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
        )
    
    # Gera token
    access_token = create_access_token(user.id)
    
    return TokenOutput(
        access_token=access_token,
        token_type="bearer",
        expires_in=JWT_EXPIRATION_HOURS * 3600,
    )


@auth_router.post("/register", response_model=UserOutput, status_code=201)
async def register(
    data: RegisterInput,
    db: AsyncSession = Depends(get_db),
) -> UserOutput:
    """
    Registra um novo usuário.
    
    - **email**: Email único do usuário
    - **name**: Nome do usuário
    - **password**: Senha (mínimo 8 caracteres, 1 maiúscula, 1 número)
    """
    # Verifica se email já existe
    existing = await User.objects.using(db).get_or_none(email=data.email.lower())
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    
    # Cria usuário
    user = User(
        email=data.email.lower(),
        name=data.name,
        password_hash=User.hash_password(data.password),
    )
    await user.save(db)
    
    return UserOutput.model_validate(user)


@auth_router.post("/refresh", response_model=TokenOutput)
async def refresh_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenOutput:
    """
    Renova o token JWT.
    
    Requer autenticação via Bearer token.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    
    # Gera novo token
    access_token = create_access_token(user.id)
    
    return TokenOutput(
        access_token=access_token,
        token_type="bearer",
        expires_in=JWT_EXPIRATION_HOURS * 3600,
    )
