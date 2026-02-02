"""
Multi-tenancy system for SaaS applications.

Provides automatic tenant filtering via context variables and middleware.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from fastapi import Request
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.responses import Response
    from core.querysets import QuerySet


# =============================================================================
# Context Variables
# =============================================================================

_current_tenant: ContextVar[UUID | None] = ContextVar("current_tenant", default=None)
_tenant_field: ContextVar[str] = ContextVar("tenant_field", default="workspace_id")


# =============================================================================
# Tenant Context Functions
# =============================================================================

def set_tenant(tenant_id: UUID | str | None) -> None:
    """
    Set current tenant in context.

    Called by middleware at request start.
    """
    # set_tenant(request.state.user.workspace_id)
    if isinstance(tenant_id, str):
        tenant_id = UUID(tenant_id)
    _current_tenant.set(tenant_id)


def get_tenant() -> UUID | None:
    """
    Return current tenant from context.

    Returns None if no tenant is set.
    """
    # tenant_id = get_tenant()
    return _current_tenant.get()


def require_tenant() -> UUID:
    """
    Return current tenant or raise exception.

    Use when tenant is mandatory for the operation.
    """
    # tenant_id = require_tenant()
    tenant_id = get_tenant()
    if tenant_id is None:
        raise RuntimeError(
            "No tenant set in current context. "
            "Ensure TenantMiddleware is configured or call set_tenant() manually."
        )
    return tenant_id


def clear_tenant() -> None:
    """
    Clear tenant from current context.

    Called automatically by middleware at request end.
    """
    _current_tenant.set(None)


def set_tenant_field(field_name: str) -> None:
    """
    Set tenant field name for current context.

    Overrides settings.tenancy_field for this request.
    """
    # set_tenant_field("organization_id")
    _tenant_field.set(field_name)


def get_tenant_field() -> str:
    """
    Return configured tenant field name.

    Priority: context var > settings > default.
    """
    context_field = _tenant_field.get()

    try:
        from core.config import get_settings
        settings = get_settings()
        settings_field = settings.tenancy_field
    except Exception:
        settings_field = "workspace_id"

    if context_field != "workspace_id" and context_field != settings_field:
        return context_field

    return settings_field


# =============================================================================
# Tenant Mixins
# =============================================================================

class TenantMixin:
    """
    Mixin adding workspace_id with foreign key.

    Requires 'workspaces' table with UUID primary key.
    """
    # class Domain(Model, TenantMixin): ...

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class FlexibleTenantMixin:
    """
    Mixin adding workspace_id without foreign key.

    Use when workspace table has different name or is external.
    """
    # class Domain(Model, FlexibleTenantMixin): ...

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )


# =============================================================================
# QuerySet Extension
# =============================================================================

def for_tenant(
    queryset: "QuerySet",
    tenant_field: str | None = None,
    tenant_id: UUID | None = None,
) -> "QuerySet":
    """
    Add tenant filter to QuerySet.

    Uses context tenant if tenant_id not provided.
    """
    # qs = for_tenant(Domain.objects.using(db))
    if tenant_field is None:
        tenant_field = get_tenant_field()

    if tenant_id is None:
        tenant_id = require_tenant()

    return queryset.filter(**{tenant_field: tenant_id})


# =============================================================================
# Middleware
# =============================================================================

class TenantMiddleware:
    """
    ASGI middleware for automatic tenant extraction.

    Extracts tenant from authenticated user and sets context.
    """
    # app.add_middleware(TenantMiddleware)

    def __init__(
        self,
        app: Any,
        user_tenant_attr: str = "workspace_id",
        tenant_field: str = "workspace_id",
        require_tenant: bool = False,
    ) -> None:
        """
        Initialize middleware with configuration.

        Accepts user attribute name and model field name.
        """
        self.app = app
        self.user_tenant_attr = user_tenant_attr
        self.tenant_field = tenant_field
        self.require_tenant_flag = require_tenant

    async def __call__(
        self,
        scope: dict,
        receive: Any,
        send: Any,
    ) -> None:
        """
        Process ASGI request.

        Sets tenant field and clears context on completion.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        set_tenant_field(self.tenant_field)

        try:
            await self.app(scope, receive, send)
        finally:
            clear_tenant()


async def extract_tenant_from_request(
    request: "Request",
    user_tenant_attr: str = "workspace_id",
) -> UUID | None:
    """
    Extract tenant ID from request sources.

    Checks user, header, and query param in order.
    """
    # tenant_id = await extract_tenant_from_request(request)
    user = getattr(request.state, "user", None)
    if user is not None:
        tenant_id = getattr(user, user_tenant_attr, None)
        if tenant_id is not None:
            return tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))

    tenant_header = request.headers.get("X-Tenant-ID")
    if tenant_header:
        try:
            return UUID(tenant_header)
        except ValueError:
            pass

    tenant_param = request.query_params.get("tenant_id")
    if tenant_param:
        try:
            return UUID(tenant_param)
        except ValueError:
            pass

    return None


# =============================================================================
# FastAPI Dependency
# =============================================================================

async def get_tenant_dependency() -> UUID:
    """
    FastAPI dependency returning current tenant.

    Raises HTTPException 400 if no tenant set.
    """
    # async def handler(tenant_id: UUID = Depends(get_tenant_dependency)): ...
    from fastapi import HTTPException

    tenant_id = get_tenant()
    if tenant_id is None:
        raise HTTPException(
            status_code=400,
            detail="No tenant context. Ensure you are authenticated with a workspace."
        )
    return tenant_id


# =============================================================================
# Context Manager
# =============================================================================

class tenant_context:
    """
    Context manager for temporary tenant scope.

    Useful for tests and background tasks.
    """
    # with tenant_context(workspace_id): ...

    def __init__(self, tenant_id: UUID | str) -> None:
        """
        Initialize with tenant ID.

        Accepts UUID or string representation.
        """
        self.tenant_id = tenant_id if isinstance(tenant_id, UUID) else UUID(tenant_id)
        self._token = None

    def __enter__(self) -> "tenant_context":
        """Enter context and set tenant."""
        self._token = _current_tenant.set(self.tenant_id)
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context and restore previous tenant."""
        _current_tenant.reset(self._token)

    async def __aenter__(self) -> "tenant_context":
        """Async enter delegates to sync."""
        return self.__enter__()

    async def __aexit__(self, *args: Any) -> None:
        """Async exit delegates to sync."""
        self.__exit__(*args)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "set_tenant",
    "get_tenant",
    "require_tenant",
    "clear_tenant",
    "set_tenant_field",
    "get_tenant_field",
    "TenantMixin",
    "FlexibleTenantMixin",
    "for_tenant",
    "TenantMiddleware",
    "extract_tenant_from_request",
    "get_tenant_dependency",
    "tenant_context",
]
