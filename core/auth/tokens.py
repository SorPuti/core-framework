"""
Implementações de backends de token.

Backends disponíveis:
- JWTBackend: JSON Web Tokens (padrão)

Uso:
    from core.auth import get_token_backend, create_access_token
    
    # Funções de conveniência
    token = create_access_token(user_id=123)
    payload = decode_token(token)
    
    # Ou via backend diretamente
    backend = get_token_backend()
    token = backend.create_token({"sub": "123"})
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from core.auth.base import (
    TokenBackend,
    TokenError,
    register_token_backend,
    get_auth_config,
)
from core.datetime import timezone

# Logger for token operations
logger = logging.getLogger("core.auth.tokens")


class JWTBackend(TokenBackend):
    """
    Backend de tokens usando JWT (JSON Web Tokens).
    
    Requer: pyjwt (já incluído nas dependências do framework)
    
    Exemplo:
        backend = JWTBackend(secret_key="your-secret")
        
        # Criar token
        token = backend.create_token(
            {"sub": "user_123", "role": "admin"},
            token_type="access",
        )
        
        # Decodificar
        payload = backend.decode_token(token)
        print(payload["sub"])  # "user_123"
    """
    
    def __init__(
        self,
        secret_key: str | None = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7,
    ) -> None:
        self._secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days
    
    @property
    def secret_key(self) -> str:
        """Obtém secret key da config se não definida."""
        if self._secret_key:
            return self._secret_key
        return get_auth_config().secret_key
    
    def create_token(
        self,
        payload: dict[str, Any],
        token_type: str = "access",
        expires_delta: timedelta | None = None,
    ) -> str:
        """
        Cria um token JWT.
        
        Args:
            payload: Dados a incluir no token
            token_type: "access" ou "refresh"
            expires_delta: Tempo de expiração customizado
            
        Returns:
            Token JWT codificado
        """
        import jwt
        
        # Define expiração
        if expires_delta is None:
            if token_type == "refresh":
                expires_delta = timedelta(days=self.refresh_token_expire_days)
            else:
                expires_delta = timedelta(minutes=self.access_token_expire_minutes)
        
        expire = timezone.add(timezone.now(), seconds=int(expires_delta.total_seconds()))
        
        # Monta payload completo
        to_encode = payload.copy()
        to_encode.update({
            "exp": expire,
            "iat": timezone.now(),
            "type": token_type,
        })
        
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
    
    def decode_token(self, token: str) -> dict[str, Any]:
        """
        Decodifica um token JWT.
        
        Args:
            token: Token JWT
            
        Returns:
            Payload do token
            
        Raises:
            TokenError: Se token inválido ou expirado
        """
        import jwt
        
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            logger.debug(f"Token decoded: sub={payload.get('sub')}, type={payload.get('type')}")
            return payload
        except jwt.ExpiredSignatureError:
            logger.debug("Token decode failed: token expired")
            raise TokenError("Token expired")
        except jwt.InvalidTokenError as e:
            logger.debug(f"Token decode failed: {e}")
            raise TokenError(f"Invalid token: {e}")
    
    def verify_token(
        self,
        token: str,
        token_type: str = "access",
    ) -> dict[str, Any] | None:
        """
        Verifica e decodifica um token.
        
        Args:
            token: Token JWT
            token_type: Tipo esperado
            
        Returns:
            Payload se válido, None caso contrário
        """
        try:
            payload = self.decode_token(token)
            
            actual_type = payload.get("type")
            if actual_type != token_type:
                logger.debug(
                    f"Token type mismatch: expected '{token_type}', got '{actual_type}'"
                )
                return None
            
            logger.debug(f"Token verified successfully: sub={payload.get('sub')}")
            return payload
        except TokenError as e:
            logger.debug(f"Token verification failed: {e}")
            return None
    
    def refresh_token(self, refresh_token: str) -> tuple[str, str] | None:
        """
        Gera novos tokens a partir de um refresh token.
        
        Args:
            refresh_token: Token de refresh
            
        Returns:
            Tupla (access_token, new_refresh_token) ou None
        """
        payload = self.verify_token(refresh_token, token_type="refresh")
        
        if payload is None:
            return None
        
        # Remove claims de tempo do payload original
        new_payload = {k: v for k, v in payload.items() if k not in ("exp", "iat", "type")}
        
        # Gera novos tokens
        access = self.create_token(new_payload, token_type="access")
        refresh = self.create_token(new_payload, token_type="refresh")
        
        return access, refresh


# =============================================================================
# Funções de Conveniência
# =============================================================================

def create_access_token(
    user_id: int | str,
    secret_key: str | None = None,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Cria um token de acesso JWT.
    
    Args:
        user_id: ID do usuário
        secret_key: Chave secreta (usa config se None)
        expires_delta: Tempo de expiração
        extra_claims: Claims adicionais
        
    Returns:
        Token JWT
        
    Exemplo:
        token = create_access_token(
            user_id=user.id,
            extra_claims={"role": "admin"},
        )
    """
    from core.auth.base import get_token_backend
    
    payload = {"sub": str(user_id)}
    if extra_claims:
        payload.update(extra_claims)
    
    backend = get_token_backend()
    
    # Se secret_key fornecida, cria backend temporário
    if secret_key:
        backend = JWTBackend(secret_key=secret_key)
    
    return backend.create_token(payload, token_type="access", expires_delta=expires_delta)


def create_refresh_token(
    user_id: int | str,
    secret_key: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Cria um token de refresh JWT.
    
    Args:
        user_id: ID do usuário
        secret_key: Chave secreta (usa config se None)
        expires_delta: Tempo de expiração
        
    Returns:
        Token JWT
    """
    from core.auth.base import get_token_backend
    
    payload = {"sub": str(user_id)}
    
    backend = get_token_backend()
    
    if secret_key:
        backend = JWTBackend(secret_key=secret_key)
    
    return backend.create_token(payload, token_type="refresh", expires_delta=expires_delta)


def decode_token(token: str, secret_key: str | None = None) -> dict[str, Any]:
    """
    Decodifica um token JWT.
    
    Args:
        token: Token JWT
        secret_key: Chave secreta (usa config se None)
        
    Returns:
        Payload do token
        
    Raises:
        TokenError: Se token inválido
    """
    from core.auth.base import get_token_backend
    
    backend = get_token_backend()
    
    if secret_key:
        backend = JWTBackend(secret_key=secret_key)
    
    return backend.decode_token(token)


def verify_token(
    token: str,
    secret_key: str | None = None,
    token_type: str = "access",
) -> dict[str, Any] | None:
    """
    Verifica e decodifica um token JWT.
    
    Args:
        token: Token JWT
        secret_key: Chave secreta (usa config se None)
        token_type: Tipo esperado
        
    Returns:
        Payload se válido, None caso contrário
    """
    from core.auth.base import get_token_backend
    
    backend = get_token_backend()
    
    if secret_key:
        backend = JWTBackend(secret_key=secret_key)
    
    return backend.verify_token(token, token_type)


# =============================================================================
# Registro do backend padrão
# =============================================================================

def _register_default_token_backends() -> None:
    """Registra os backends de token padrão."""
    register_token_backend("jwt", JWTBackend())


# Registra ao importar
_register_default_token_backends()
