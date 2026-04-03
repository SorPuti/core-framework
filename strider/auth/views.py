"""
ViewSets de autenticação prontos para uso.

Endpoints fornecidos:
- POST /auth/register - Registro de usuário
- POST /auth/login - Login
- POST /auth/refresh - Renovar token
- GET /auth/me - Usuário atual
- POST /auth/change-password - Alterar senha

Exemplo:
    from strider.auth.views import AuthViewSet
    from myapp.models import User
    
    class MyAuthViewSet(AuthViewSet):
        user_model = User
    
    router.register_viewset("/auth", MyAuthViewSet, basename="auth")

Cookies / resposta HTTP: ver ``AuthViewSet.finalize_token_response`` e métodos
``perform_user_registration``, ``authenticate_login_user``, ``resolve_user_for_refresh``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, TYPE_CHECKING, ClassVar
from uuid import UUID

from fastapi import Request, HTTPException
from pydantic import create_model
from starlette.responses import Response

from strider.views import ViewSet, action
from strider.permissions import AllowAny, IsAuthenticated
from strider.auth.tokens import create_access_token, create_refresh_token, verify_token
from strider.auth.schemas import (
    AUTH_USER_API_RESPONSE_BLOCKLIST,
    BaseRegisterInput,
    BaseLoginInput,
    RefreshTokenInput,
    ChangePasswordInput,
    TokenResponse,
    BaseUserOutput,
    MessageResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AuthViewSet(ViewSet):
    """
    ViewSet de autenticação pronto para uso.
    
    Atributos configuráveis:
        user_model: Classe do modelo User (obrigatório)
        register_schema: Schema Pydantic do body de ``POST /auth/register`` (prioridade máxima)
        input_schema: Atalho estilo ``ModelViewSet``: se definires **só** isto (sem mudar
            ``register_schema`` de ``BaseRegisterInput``), o registo e o OpenAPI usam este
            schema. Não precisas de ``output_schema`` — login/register continuam com
            ``TokenResponse``.
        login_schema: Schema de login customizado  
        user_output_schema: Schema de output do usuário
        extra_register_fields: Campos extras no schema dinâmico de registo
        register_block_privilege_extras: Se True (default), ``is_superuser``/``is_staff``
            só vão para ``create_user`` se estiverem declarados no schema de registo
        user_response_secret_keys: Nomes extra a nunca expor no JSON de ``/auth/me``
            (unido a ``AUTH_USER_API_RESPONSE_BLOCKLIST``: ``password``,
            ``password_hash``, ``hashed_password``).
        access_token_expire_minutes: Expiração do access token (default: 30)
        refresh_token_expire_days: Expiração do refresh token (default: 7)
    
    Customização (cookies, corpo da resposta, headers):
        - ``finalize_token_response(request, payload)``: ponto único após
          ``register`` / ``login`` / ``refresh``; por padrão devolve o ``dict``.
          Sobrescreva para devolver ``JSONResponse`` (ou outro ``Response``) e
          chamar ``set_cookie``, omitir tokens do JSON, etc.
        - ``perform_user_registration(db, data)``: cria o utilizador (sem
          ``commit``); útil para estender registo antes do commit.
        - ``authenticate_login_user(db, data)``: valida credenciais e devolve
          o utilizador (sem ``commit``).
        - ``resolve_user_for_refresh(db, data)``: valida refresh token e
          carrega o utilizador.

        Exemplo com cookies (refresh só no cookie, corpo igual ao default)::

            from fastapi.responses import JSONResponse
            from strider.auth.views import AuthViewSet

            class CookieAuthViewSet(AuthViewSet):
                user_model = User

                async def finalize_token_response(self, request, payload):
                    response = JSONResponse(content=payload)
                    response.set_cookie(
                        key="refresh_token",
                        value=payload["refresh_token"],
                        httponly=True,
                        secure=True,
                        samesite="lax",
                        max_age=self.refresh_token_expire_days * 86400,
                        path="/",
                    )
                    return response

        Exemplo com ``super().login()`` para lógica antes/depois::

            async def login(self, request, db, data=None, **kwargs):
                # pré-login opcional
                result = await super().login(request, db, data, **kwargs)
                # se super() devolver dict, ainda pode embrulhar aqui
                return result

    Exemplo:
        from strider.auth.views import AuthViewSet
        
        class MyAuthViewSet(AuthViewSet):
            user_model = User
            extra_register_fields = ["name", "phone"]
        
        router.register_viewset("/auth", MyAuthViewSet)
    
    Endpoints:
        POST /auth/register
        POST /auth/login
        POST /auth/refresh
        GET /auth/me
        POST /auth/change-password
    """
    
    # Configuration - override in subclass or use get_user_model()
    user_model: type | None = None
    register_schema: type = BaseRegisterInput
    login_schema: type = BaseLoginInput
    user_output_schema: type = BaseUserOutput
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # Bug #5 Fix: Extra fields to accept on registration
    extra_register_fields: list[str] = []

    #: Chaves removidas do dict de ``/auth/me`` além de ``AUTH_USER_API_RESPONSE_BLOCKLIST``.
    user_response_secret_keys: ClassVar[frozenset[str]] = frozenset()

    #: Impede escalação de privilégio via JSON extra não documentado no schema.
    register_block_privilege_extras: ClassVar[bool] = True
    
    # ViewSet config
    tags: list[str] = ["auth"]
    
    # Previne que CRUD routes sejam criadas mesmo se user_model/model for definido
    # AuthViewSet usa apenas @action endpoints, nunca CRUD
    _exclude_crud: bool = True
    
    # Explicitly disable CRUD endpoints that don't make sense for auth
    # These would cause 500 errors if called
    async def list(self, *args, **kwargs):
        """List is not available on auth endpoint."""
        raise HTTPException(
            status_code=405,
            detail="Method not allowed. Use /auth/me to get current user."
        )
    
    async def retrieve(self, *args, **kwargs):
        """Retrieve is not available on auth endpoint."""
        raise HTTPException(
            status_code=405,
            detail="Method not allowed. Use /auth/me to get current user."
        )
    
    async def create(self, *args, **kwargs):
        """Use /auth/register instead."""
        raise HTTPException(
            status_code=405,
            detail="Method not allowed. Use /auth/register to create users."
        )
    
    async def update(self, *args, **kwargs):
        """Update is not available on auth endpoint."""
        raise HTTPException(
            status_code=405,
            detail="Method not allowed."
        )
    
    async def destroy(self, *args, **kwargs):
        """Destroy is not available on auth endpoint."""
        raise HTTPException(
            status_code=405,
            detail="Method not allowed."
        )
    
    # Cache for dynamic schema
    _dynamic_register_schema: type | None = None
    
    def _get_user_model(self):
        """
        Get user model from class attribute or global config.
        
        Priority:
        1. self.user_model (if set on subclass)
        2. get_user_model() (from configure_auth or settings)
        """
        if self.user_model is not None:
            return self.user_model
        
        # Try to get from global config
        from strider.auth.models import get_user_model
        return get_user_model()

    def _effective_user_response_blocklist(self) -> frozenset[str]:
        extra = getattr(type(self), "user_response_secret_keys", None) or frozenset()
        return AUTH_USER_API_RESPONSE_BLOCKLIST | frozenset(extra)

    def _serialize_user_for_public_response(self, user: Any) -> dict[str, Any]:
        """
        Serializa o utilizador para respostas públicas (ex.: GET /auth/me),
        removendo hashes e passwords mesmo que ``user_output_schema`` os exponha por engano.
        """
        data = self.user_output_schema.model_validate(user).model_dump()
        block = self._effective_user_response_blocklist()
        return {k: v for k, v in data.items() if k not in block}
    
    def _get_register_schema(self) -> type:
        """
        Resolve o schema Pydantic do body de registo (campos extra dinâmicos + ``extra="allow"`` no fluxo default).
        
        This method validates against the model to determine if fields are
        required (NOT NULL) or optional (nullable).
        
        Rules:
            - If model column is NOT NULL and has no default -> REQUIRED in schema
            - If model column is nullable or has default -> OPTIONAL in schema
        
        Returns:
            Pydantic schema class for registration

        Ordem de resolução:
            1. ``register_schema`` se diferente de ``BaseRegisterInput``
            2. ``input_schema`` da classe (atalho igual ao ``ModelViewSet``)
            3. Schema dinâmico com ``extra_register_fields``
            4. ``BaseRegisterInput``

        Se definires ``input_schema`` e ``extra_register_fields`` ao mesmo tempo,
        ``input_schema`` prevalece (os extras da lista são ignorados para o schema).
        """
        import logging
        import warnings
        logger = logging.getLogger("strider.auth")
        
        # If register_schema was explicitly overridden, use it
        if self.register_schema != BaseRegisterInput:
            return self.register_schema

        # Mesma convenção que ViewSet/ModelViewSet: só ``input_schema`` para o body de register
        cls_input = getattr(type(self), "input_schema", None)
        if cls_input is not None:
            return cls_input
        
        # If no extra fields, use base schema
        if not self.extra_register_fields:
            return BaseRegisterInput
        
        # Return cached schema if available
        if self._dynamic_register_schema is not None:
            return self._dynamic_register_schema
        
        User = self._get_user_model()
        
        # Get model column info for nullable/required check
        model_columns = {}
        try:
            from sqlalchemy import inspect
            mapper = inspect(User)
            model_columns = {col.name: col for col in mapper.columns}
        except Exception as e:
            logger.debug(f"Could not inspect User model: {e}")
        
        extra_fields = {}
        
        for field_name in self.extra_register_fields:
            col = model_columns.get(field_name)
            
            if col is not None:
                # Determine type from model
                python_type = self._get_python_type_from_column(col.type)
                
                # Check if field is required
                is_nullable = col.nullable
                has_default = col.default is not None or col.server_default is not None
                
                if not is_nullable and not has_default:
                    # REQUIRED field - use ... (Ellipsis) as default
                    extra_fields[field_name] = (python_type, ...)
                    logger.info(
                        f"Field '{field_name}' is NOT NULL in model, "
                        f"adding as REQUIRED to register schema"
                    )
                else:
                    # Optional field
                    extra_fields[field_name] = (python_type | None, None)
            else:
                # Field not in model columns, warn and make optional
                warnings.warn(
                    f"Field '{field_name}' in extra_register_fields "
                    f"not found in {User.__name__} model columns. "
                    f"Adding as optional str.",
                    UserWarning,
                    stacklevel=2,
                )
                extra_fields[field_name] = (str | None, None)
        
        # Create dynamic model
        self._dynamic_register_schema = create_model(
            "DynamicRegisterInput",
            __base__=BaseRegisterInput,
            __module__=__name__,
            **extra_fields,
        )
        
        # Alinhar com BaseRegisterInput: corpo pode trazer colunas extra (filtradas no ORM).
        self._dynamic_register_schema.model_config = {
            **BaseRegisterInput.model_config,
            "extra": "allow",
        }
        
        return self._dynamic_register_schema
    
    def _get_python_type_from_column(self, sa_type) -> type:
        """
        Convert SQLAlchemy column type to Python type.
        
        Args:
            sa_type: SQLAlchemy type instance
        
        Returns:
            Corresponding Python type
        """
        from sqlalchemy import String, Integer, Boolean, Float, Text, DateTime, Date
        
        type_map = {
            String: str,
            Text: str,
            Integer: int,
            Boolean: bool,
            Float: float,
        }
        
        for sa_cls, py_type in type_map.items():
            if isinstance(sa_type, sa_cls):
                return py_type
        
        # Check type name for dialect-specific types
        type_name = type(sa_type).__name__
        if "String" in type_name or "Text" in type_name or "VARCHAR" in type_name:
            return str
        if "Integer" in type_name or "INT" in type_name:
            return int
        if "Boolean" in type_name or "BOOL" in type_name:
            return bool
        if "Float" in type_name or "Numeric" in type_name or "Decimal" in type_name:
            return float
        if "DateTime" in type_name or "Timestamp" in type_name:
            from datetime import datetime
            return datetime
        if "Date" in type_name:
            from datetime import date
            return date
        if "UUID" in type_name:
            from uuid import UUID
            return UUID
        
        # Default to str
        return str
    
    def _get_extra_field_names(self) -> list[str]:
        """
        Auto-detect extra fields from register_schema.
        
        Compares register_schema fields with BaseRegisterInput to find
        additional fields that need to be passed to create_user().
        
        This allows users to define a custom register_schema without
        also having to define extra_register_fields (DRY principle).
        
        Returns:
            List of field names that are in register_schema but not in BaseRegisterInput
        
        Example:
            class CustomRegisterInput(BaseRegisterInput):
                name: str
                phone: str | None = None
            
            class MyAuthViewSet(AuthViewSet):
                register_schema = CustomRegisterInput
                # extra_register_fields not needed!
            
            # _get_extra_field_names() returns ["name", "phone"]
        """
        schema = self._get_register_schema()
        
        # Get base fields (email, password)
        base_fields = set(BaseRegisterInput.model_fields.keys())
        
        # Get schema fields
        schema_fields = set(schema.model_fields.keys())
        
        # Return extra fields (fields in schema but not in base)
        extra = schema_fields - base_fields
        
        return list(extra)

    _REGISTER_CREATE_USER_RESERVED: frozenset[str] = frozenset({
        "email",
        "password",
        "password_hash",
    })
    _REGISTER_PRIVILEGE_KEYS: frozenset[str] = frozenset({"is_superuser", "is_staff"})

    def _register_kwargs_for_create_user(self, User: type, validated: Any) -> dict[str, Any]:
        """
        Monta ``**kwargs`` para ``User.create_user`` a partir do body validado.

        - Só inclui chaves que existem como colunas no mapper do ``User`` (não relações).
        - Exclui PK, ``email``, ``password`` e ``password_hash``.
        - Com ``register_block_privilege_extras`` (default True), ``is_superuser`` e
          ``is_staff`` vindos só como extra JSON são ignorados a menos que declarados
          no schema de registo.

        Se ``inspect(User)`` falhar, cai no comportamento anterior: apenas campos listados
        em ``extra_register_fields`` ou inferidos por ``_get_extra_field_names()``.
        """
        schema_cls = type(validated)
        declared = set(schema_cls.model_fields.keys())
        dump = validated.model_dump(exclude_unset=True)
        reserved = self._REGISTER_CREATE_USER_RESERVED
        block_priv = bool(getattr(type(self), "register_block_privilege_extras", True))
        out: dict[str, Any] = {}

        try:
            from sqlalchemy import inspect as sa_inspect

            mapper = sa_inspect(User)
            pk_keys = {c.key for c in mapper.columns if c.primary_key}
            col_keys = {c.key for c in mapper.columns}
        except Exception:
            names = list(self.extra_register_fields) or self._get_extra_field_names()
            for field_name in names:
                if field_name in reserved:
                    continue
                if field_name not in dump:
                    continue
                out[field_name] = dump[field_name]
            return out

        for key, value in dump.items():
            if key in reserved:
                continue
            if key not in col_keys:
                continue
            if key in pk_keys:
                continue
            if (
                block_priv
                and key in self._REGISTER_PRIVILEGE_KEYS
                and key not in declared
            ):
                continue
            out[key] = value
        return out
    
    def _create_tokens(self, user) -> dict:
        """
        Bug #6 Fix: Create access and refresh tokens using current API.
        
        Uses the correct function signature with user_id and extra_claims.
        """
        access_token = create_access_token(
            user_id=str(user.id),
            extra_claims={"email": getattr(user, "email", None)},
            expires_delta=timedelta(minutes=self.access_token_expire_minutes),
        )
        refresh_token = create_refresh_token(
            user_id=str(user.id),
            expires_delta=timedelta(days=self.refresh_token_expire_days),
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.access_token_expire_minutes * 60,
        }

    async def finalize_token_response(
        self,
        request: Request,
        payload: dict[str, Any],
    ) -> dict[str, Any] | Response:
        """
        Chamado no fim de ``register``, ``login`` e ``refresh`` com o dicionário
        tipado como ``TokenResponse``. Por padrão devolve o mesmo ``dict``;
        sobrescreva para devolver ``JSONResponse`` / ``Response`` e definir cookies,
        cabeçalhos ou omitir campos sensíveis do corpo JSON.
        """
        return payload

    async def perform_user_registration(
        self,
        db: "AsyncSession",
        data: dict[str, Any] | None,
    ) -> Any:
        """
        Executa validação + criação de utilizador. Não faz ``commit``.

        Sobrescreva para anexar lógica (ex.: perfil predefinido) e chame
        ``return await super().perform_user_registration(db, data)``.
        """
        User = self._get_user_model()
        schema = self._get_register_schema()
        validated = schema.model_validate(data)

        existing = await User.get_by_email(validated.email, db)
        if existing:
            raise HTTPException(
                status_code=400,
                detail="User with this email already exists",
            )

        extra_fields = self._register_kwargs_for_create_user(User, validated)

        return await User.create_user(
            email=validated.email,
            password=validated.password,
            db=db,
            **extra_fields,
        )

    async def authenticate_login_user(
        self,
        db: "AsyncSession",
        data: dict[str, Any] | None,
    ) -> Any:
        """
        Valida o corpo com ``login_schema`` e autentica. Não faz ``commit``.

        Levanta ``HTTPException(401)`` se as credenciais forem inválidas.
        """
        User = self._get_user_model()
        validated = self.login_schema.model_validate(data)
        user = await User.authenticate(
            email=validated.email,
            password=validated.password,
            db=db,
        )
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password",
            )
        return user

    async def resolve_user_for_refresh(
        self,
        db: "AsyncSession",
        data: dict[str, Any] | None,
    ) -> Any:
        """
        Valida ``refresh_token`` no corpo e carrega o utilizador ativo.
        Levanta ``HTTPException(401)`` se o token ou utilizador forem inválidos.
        """
        User = self._get_user_model()
        validated = RefreshTokenInput.model_validate(data)
        payload = verify_token(validated.refresh_token, token_type="refresh")
        if payload is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired refresh token",
            )
        user_id_str = payload.get("sub")
        user_id = self._convert_user_id(user_id_str, User)
        user = await User.objects.using(db).filter(id=user_id).first()
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=401,
                detail="User not found or inactive",
            )
        return user
    
    def _convert_user_id(self, user_id: str, User: type) -> Any:
        """
        Bug #7 Fix: Convert user_id string to the correct type.
        
        Intelligently converts based on the User model's PK type.
        
        Args:
            user_id: String representation of user ID
            User: User model class
            
        Returns:
            Converted user ID in the correct type
        """
        # Try to detect PK type from model
        from strider.auth.models import _get_pk_column_type
        from sqlalchemy.dialects.postgresql import UUID as PG_UUID
        from sqlalchemy import Integer, BigInteger, String
        
        pk_type = _get_pk_column_type(User)
        
        if pk_type == PG_UUID:
            try:
                return UUID(user_id)
            except (ValueError, TypeError):
                return user_id
        elif pk_type in (Integer, BigInteger):
            try:
                return int(user_id)
            except (ValueError, TypeError):
                return user_id
        else:
            return user_id
    
    @action(
        methods=["POST"], detail=False, permission_classes=[AllowAny],
        input_schema=BaseRegisterInput, output_schema=TokenResponse,
    )
    async def register(
        self,
        request: Request,
        db: "AsyncSession",
        data: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict[str, Any] | Response:
        """
        Register a new user.
        
        Bug #5 Fix: Now supports extra_register_fields.
        
        Returns tokens on successful registration.
        """
        user = await self.perform_user_registration(db, data)
        await db.commit()
        payload = self._create_tokens(user)
        return await self.finalize_token_response(request, payload)
    
    @action(
        methods=["POST"], detail=False, permission_classes=[AllowAny],
        input_schema=BaseLoginInput, output_schema=TokenResponse,
    )
    async def login(
        self,
        request: Request,
        db: "AsyncSession",
        data: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict[str, Any] | Response:
        """
        Login with email and password.
        
        Returns access and refresh tokens.
        """
        user = await self.authenticate_login_user(db, data)
        await db.commit()
        payload = self._create_tokens(user)
        return await self.finalize_token_response(request, payload)
    
    @action(
        methods=["POST"], detail=False, permission_classes=[AllowAny],
        input_schema=RefreshTokenInput, output_schema=TokenResponse,
    )
    async def refresh(
        self,
        request: Request,
        db: "AsyncSession",
        data: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict[str, Any] | Response:
        """
        Refresh access token using refresh token.
        
        Bug #7 Fix: Now correctly handles UUID user IDs.
        """
        user = await self.resolve_user_for_refresh(db, data)
        payload = self._create_tokens(user)
        return await self.finalize_token_response(request, payload)
    
    @action(
        methods=["GET"], detail=False, permission_classes=[IsAuthenticated],
        output_schema=BaseUserOutput,
    )
    async def me(
        self,
        request: Request,
        db: "AsyncSession",
        **kwargs,
    ) -> dict:
        """
        Get current authenticated user.
        
        Uses request.user (Starlette pattern) with fallback to request.state.user
        for backward compatibility.
        """
        # Try request.user first (Starlette AuthenticationMiddleware pattern)
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            # user is an AuthenticatedUser wrapper - get underlying model
            if hasattr(user, "_user"):
                user = user._user
            return self._serialize_user_for_public_response(user)
        
        # Fallback to request.state.user (legacy pattern)
        user = getattr(request.state, "user", None)
        if user is not None:
            return self._serialize_user_for_public_response(user)
        
        raise HTTPException(
            status_code=401,
            detail="Not authenticated"
        )
    
    @action(
        methods=["POST"], detail=False, permission_classes=[IsAuthenticated],
        input_schema=ChangePasswordInput, output_schema=MessageResponse,
    )
    async def change_password(
        self,
        request: Request,
        db: "AsyncSession",
        data: dict[str, Any] | None = None,
        **kwargs,
    ) -> dict:
        """
        Change password for current user.
        """
        # Try request.user first (Starlette pattern)
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            if hasattr(user, "_user"):
                user = user._user
        else:
            # Fallback to request.state.user
            user = getattr(request.state, "user", None)
        
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated"
            )
        
        # Validate input
        validated = ChangePasswordInput.model_validate(data)
        
        # Verify current password
        if not user.check_password(validated.current_password):
            raise HTTPException(
                status_code=400,
                detail="Current password is incorrect"
            )
        
        # Set new password
        user.set_password(validated.new_password)
        await user.save(db)
        await db.commit()
        
        return {"message": "Password changed successfully", "success": True}


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "AuthViewSet",
]
