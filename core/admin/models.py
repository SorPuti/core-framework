"""
Models do Admin Panel.

Modelos core usados internamente pelo admin:
- AuditLog: Log de ações administrativas
- AdminSession: Sessões do admin (browser-based)
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from sqlalchemy.orm import Mapped
from sqlalchemy import Text

from core.models import Model, Field
from core.fields import AdvancedField
from core.datetime import DateTime

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AuditLog(Model):
    """
    Log de ações administrativas.
    
    Registra quem fez o que, quando, e o que mudou.
    Sempre visível no admin para superusers.
    """
    __tablename__ = "admin_audit_log"
    
    id: Mapped[int] = Field.pk()
    user_id: Mapped[int] = Field.integer(index=True)
    user_email: Mapped[str] = Field.string(max_length=255)
    action: Mapped[str] = Field.string(max_length=20)  # create, update, delete, bulk_delete
    app_label: Mapped[str] = Field.string(max_length=100)
    model_name: Mapped[str] = Field.string(max_length=100)
    object_id: Mapped[str] = Field.string(max_length=255)
    object_repr: Mapped[str] = Field.string(max_length=500, default="")
    changes: Mapped[dict | None] = AdvancedField.json_field(nullable=True)
    ip_address: Mapped[str | None] = Field.string(max_length=45, nullable=True)
    user_agent: Mapped[str | None] = Field.string(max_length=500, nullable=True)
    timestamp: Mapped[DateTime] = Field.datetime(auto_now_add=True)
    
    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.model_name} #{self.object_id} by {self.user_email}>"
    
    @classmethod
    async def log_action(
        cls,
        db: "AsyncSession",
        *,
        user: Any,
        action: str,
        app_label: str,
        model_name: str,
        object_id: str,
        object_repr: str = "",
        changes: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> "AuditLog":
        """
        Registra uma ação no audit log.
        
        Args:
            db: Sessão do banco
            user: Usuário que executou a ação
            action: Tipo de ação (create, update, delete)
            app_label: Label do app
            model_name: Nome do model
            object_id: ID do objeto afetado
            object_repr: Representação textual do objeto
            changes: Dict com as alterações (antes/depois)
            ip_address: IP do cliente
            user_agent: User-Agent do browser
        """
        log = cls(
            user_id=getattr(user, "id", 0),
            user_email=getattr(user, "email", str(user)),
            action=action,
            app_label=app_label,
            model_name=model_name,
            object_id=str(object_id),
            object_repr=object_repr[:500],
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else None,
        )
        await log.save(db)
        return log


class AdminSession(Model):
    """
    Sessão do admin panel (browser-based).
    
    Usado para autenticação session-based no admin,
    separada do JWT da API.
    """
    __tablename__ = "admin_sessions"
    
    id: Mapped[int] = Field.pk()
    session_key: Mapped[str] = Field.string(max_length=64, unique=True, index=True)
    user_id: Mapped[int] = Field.integer(index=True)
    ip_address: Mapped[str | None] = Field.string(max_length=45, nullable=True)
    user_agent: Mapped[str | None] = Field.string(max_length=500, nullable=True)
    created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)
    expires_at: Mapped[DateTime] = Field.datetime()
    is_active: Mapped[bool] = Field.boolean(default=True)
    
    def __repr__(self) -> str:
        return f"<AdminSession user_id={self.user_id} active={self.is_active}>"
