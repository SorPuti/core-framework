"""
ModelAdmin — Classe base para configuração de models no admin.

Define como cada model é exibido e editado no admin panel.
Inspirado no Django Admin, com melhorias para async e Pydantic.
"""

from __future__ import annotations

import inspect
import logging
import re
from typing import Any, ClassVar, TYPE_CHECKING

from core.admin.exceptions import AdminRegistrationError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("core.admin")


def _detect_widget(col_name: str, field_type: str, all_columns: list[str]) -> str:
    """
    Detecta o widget ideal para um campo baseado no nome e tipo.
    
    Retorna um string que o frontend usa para decidir qual
    componente de input renderizar.
    """
    name = col_name.lower()
    
    # Password fields — hash ou plain
    if name in ("password_hash", "hashed_password", "password_digest"):
        return "password_hash"
    if name in ("password", "passwd", "pwd", "new_password"):
        return "password"
    
    # Secret/token fields — nunca exibir
    if any(s in name for s in ("_secret", "_token", "_key", "api_key", "secret_key")):
        if name not in ("is_active", "primary_key"):
            return "secret"
    if name.endswith("_hash") and "password" not in name:
        return "secret"
    
    # Slug
    if name == "slug" or name.endswith("_slug"):
        return "slug"
    
    # Email
    if name == "email" or name.endswith("_email") or name == "email_address":
        return "email"
    
    # URL
    if name in ("url", "website", "homepage", "avatar_url", "image_url", "photo_url"):
        return "url"
    if name.endswith("_url") or name.endswith("_link"):
        return "url"
    
    # Color
    if name in ("color", "hex_color", "bg_color", "text_color", "background_color"):
        return "color"
    if name.endswith("_color"):
        return "color"
    
    # IP Address
    if name in ("ip_address", "ip", "remote_ip", "client_ip"):
        return "ip"
    
    return "default"


def _camel_to_title(name: str) -> str:
    """Converte CamelCase para Title Case com espaços."""
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    return s.title()


class ModelAdmin:
    """
    Classe base para configuração de exibição de um model no admin.
    
    Exemplo:
        @admin.register(User)
        class UserAdmin(ModelAdmin):
            list_display = ("id", "email", "is_active")
            search_fields = ("email",)
            ordering = ("-created_at",)
            display_name = "Usuário"
    """
    
    # -- Metadados --
    display_name: str | None = None
    display_name_plural: str | None = None
    icon: str = "file"  # Lucide icon name
    
    # -- List View --
    list_display: tuple[str, ...] = ()
    list_display_links: tuple[str, ...] = ()
    list_filter: tuple[str, ...] = ()
    search_fields: tuple[str, ...] = ()
    ordering: tuple[str, ...] = ()
    list_per_page: int = 25
    list_max_show_all: int = 200
    actions: list[str] = ["delete_selected"]
    
    # -- Detail/Edit View --
    fields: tuple[str, ...] | None = None
    exclude: tuple[str, ...] = ()
    readonly_fields: tuple[str, ...] = ()
    fieldsets: list[tuple[str, dict[str, Any]]] | None = None
    help_texts: dict[str, str] = {}
    
    # -- Permissions --
    permissions: tuple[str, ...] = ("view", "add", "change", "delete")
    exclude_actions: tuple[str, ...] = ()
    
    # -- Internal (set by registry) --
    model: type | None = None
    _model_fields: list[str] = []
    _pk_field: str = "id"
    _app_label: str = ""
    _model_name: str = ""
    
    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Garante que listas são independentes por subclasse."""
        super().__init_subclass__(**kwargs)
        # Copia listas mutáveis para evitar compartilhamento entre subclasses
        if "actions" not in cls.__dict__:
            cls.actions = list(cls.actions) if hasattr(cls, "actions") else ["delete_selected"]
    
    def bind(self, model: type) -> None:
        """
        Vincula este ModelAdmin a um model SQLAlchemy.
        Chamado durante o registro. Valida a configuração.
        """
        self.model = model
        self._model_name = model.__name__.lower()
        self._app_label = self._resolve_app_label(model)
        
        # Introspecta colunas do model
        try:
            columns = [col.name for col in model.__table__.columns]
        except Exception:
            # Model pode não ter __table__ ainda (abstract, etc)
            columns = []
        
        self._model_fields = columns
        
        # Detecta PK
        try:
            pk_cols = [col.name for col in model.__table__.primary_key.columns]
            self._pk_field = pk_cols[0] if pk_cols else "id"
        except Exception:
            self._pk_field = "id"
        
        # Aplica defaults sensatos
        self._apply_defaults(columns)
        
        # Valida configuração
        self._validate(columns)
    
    def _resolve_app_label(self, model: type) -> str:
        """Resolve app_label a partir do módulo do model."""
        module = model.__module__
        # Ex: apps.users.models -> users
        # Ex: core.auth.models -> auth
        parts = module.split(".")
        if len(parts) >= 2:
            # Pega o penúltimo segmento (geralmente o nome do app)
            return parts[-2]
        return parts[0]
    
    def _apply_defaults(self, columns: list[str]) -> None:
        """Aplica defaults sensatos quando campos não foram configurados."""
        if not self.list_display and columns:
            # PK + primeiras 5 colunas string/int
            display = [self._pk_field] if self._pk_field in columns else []
            for col_name in columns:
                if col_name == self._pk_field:
                    continue
                if len(display) >= 6:
                    break
                display.append(col_name)
            self.list_display = tuple(display)
        
        if not self.list_display_links and self.list_display:
            # Primeira coluna é link para detail
            self.list_display_links = (self.list_display[0],)
        
        if not self.ordering:
            # Ordena por PK descendente por default
            self.ordering = (f"-{self._pk_field}",)
        
        if not self.display_name:
            self.display_name = _camel_to_title(self.model.__name__) if self.model else ""
        
        if not self.display_name_plural:
            self.display_name_plural = self.display_name + "s"
        
        # Readonly inclui PK automaticamente
        if self._pk_field and self._pk_field not in self.readonly_fields:
            self.readonly_fields = (self._pk_field,) + tuple(self.readonly_fields)
        
        # Detecta campos auto_now_add como readonly
        if self.model and columns:
            try:
                for col in self.model.__table__.columns:
                    if col.default is not None or col.server_default is not None:
                        if col.name not in self.readonly_fields:
                            # Campos com default que parecem timestamps
                            col_type = str(col.type).upper()
                            if "DATETIME" in col_type and col.default is not None:
                                self.readonly_fields = tuple(self.readonly_fields) + (col.name,)
            except Exception:
                pass
    
    def _validate(self, columns: list[str]) -> None:
        """
        Valida a configuração do ModelAdmin contra o model.
        Levanta AdminRegistrationError com mensagens acionáveis.
        """
        if not columns:
            return  # Model sem tabela (abstrato) — skip validação
        
        source = None
        try:
            source = inspect.getfile(type(self))
        except (TypeError, OSError):
            pass
        
        model_name = self.model.__name__ if self.model else "Unknown"
        admin_class = type(self).__name__
        
        # Valida list_display
        for field_name in self.list_display:
            if field_name not in columns and not hasattr(self, field_name) and not callable(getattr(type(self), field_name, None)):
                raise AdminRegistrationError(
                    f"{admin_class}.list_display references '{field_name}' "
                    f"which does not exist on model {model_name} "
                    f"and is not a method on {admin_class}.",
                    model_name=model_name,
                    admin_class=admin_class,
                    source_file=source,
                    available_fields=columns,
                )
        
        # Valida list_filter
        for field_name in self.list_filter:
            if isinstance(field_name, str) and field_name not in columns:
                raise AdminRegistrationError(
                    f"{admin_class}.list_filter references '{field_name}' "
                    f"which does not exist on model {model_name}.",
                    model_name=model_name,
                    admin_class=admin_class,
                    source_file=source,
                    available_fields=columns,
                )
        
        # Valida search_fields
        for field_name in self.search_fields:
            if field_name not in columns:
                raise AdminRegistrationError(
                    f"{admin_class}.search_fields references '{field_name}' "
                    f"which does not exist on model {model_name}.",
                    model_name=model_name,
                    admin_class=admin_class,
                    source_file=source,
                    available_fields=columns,
                )
        
        # Valida readonly_fields
        for field_name in self.readonly_fields:
            if field_name not in columns and not hasattr(self, field_name):
                raise AdminRegistrationError(
                    f"{admin_class}.readonly_fields references '{field_name}' "
                    f"which does not exist on model {model_name}.",
                    model_name=model_name,
                    admin_class=admin_class,
                    source_file=source,
                    available_fields=columns,
                )
    
    # -- Hooks (override nos subclasses) --
    
    async def before_save(self, db: "AsyncSession", obj: Any, is_new: bool) -> None:
        """Hook executado antes de salvar (create ou update)."""
        pass
    
    async def after_save(self, db: "AsyncSession", obj: Any, is_new: bool) -> None:
        """Hook executado após salvar."""
        pass
    
    async def before_delete(self, db: "AsyncSession", obj: Any) -> None:
        """Hook executado antes de deletar."""
        pass
    
    async def after_delete(self, db: "AsyncSession", obj: Any) -> None:
        """Hook executado após deletar."""
        pass
    
    # -- Customização de queryset --
    
    def get_queryset(self, db: "AsyncSession") -> Any:
        """Retorna queryset base para list/detail. Override para filtrar."""
        return self.model.objects.using(db)
    
    # -- Serialization helpers --
    
    def get_column_info(self) -> list[dict[str, Any]]:
        """
        Retorna metadados das colunas do model para o frontend.
        
        Inclui detecção automática de widget type baseada no nome
        e tipo da coluna para renderização inteligente:
        - password/password_hash → widget "password" (nunca exibe valor)
        - slug → widget "slug" (auto-gera a partir de name/title)
        - email → widget "email" (validação HTML5)
        - url/website → widget "url" (validação + link preview)
        - color/hex_color → widget "color" (color picker)
        - *_secret/*_token/*_key → widget "secret" (nunca exibe valor)
        """
        if not self.model:
            return []
        
        columns = []
        all_col_names = []
        
        try:
            all_col_names = [c.name for c in self.model.__table__.columns]
        except Exception:
            pass
        
        try:
            for col in self.model.__table__.columns:
                col_type = str(col.type).upper()
                field_type = "string"
                if "INT" in col_type:
                    field_type = "integer"
                elif "BOOL" in col_type:
                    field_type = "boolean"
                elif "DATETIME" in col_type or "TIMESTAMP" in col_type:
                    field_type = "datetime"
                elif "FLOAT" in col_type or "NUMERIC" in col_type or "DECIMAL" in col_type:
                    field_type = "float"
                elif "TEXT" in col_type:
                    field_type = "text"
                elif "JSON" in col_type:
                    field_type = "json"
                elif "UUID" in col_type:
                    field_type = "uuid"
                
                has_default = col.default is not None or col.server_default is not None
                is_required = (
                    not col.nullable
                    and not col.primary_key
                    and not has_default
                    and col.name not in self.readonly_fields
                )
                
                # ── Smart widget detection ──
                widget = _detect_widget(col.name, field_type, all_col_names)
                
                # Slug source field: detect companion name/title field
                slug_source = None
                if widget == "slug":
                    for candidate in ("name", "title", "label", "display_name"):
                        if candidate in all_col_names and candidate != col.name:
                            slug_source = candidate
                            break
                
                columns.append({
                    "name": col.name,
                    "type": field_type,
                    "widget": widget,
                    "nullable": col.nullable,
                    "primary_key": col.primary_key,
                    "has_default": has_default,
                    "required": is_required,
                    "readonly": col.name in self.readonly_fields,
                    "help_text": self.help_texts.get(col.name, ""),
                    **({"slug_source": slug_source} if slug_source else {}),
                })
        except Exception:
            pass
        
        return columns
    
    def get_editable_fields(self) -> list[str]:
        """Retorna campos editáveis (não readonly, não excluídos)."""
        if not self.model:
            return []
        
        if self.fields is not None:
            base = list(self.fields)
        else:
            base = list(self._model_fields)
        
        return [
            f for f in base
            if f not in self.readonly_fields and f not in self.exclude
        ]
    
    def get_display_fields(self) -> list[str]:
        """Retorna campos para exibição no detail view."""
        if self.fields is not None:
            return list(self.fields)
        
        fields = [f for f in self._model_fields if f not in self.exclude]
        return fields
    
    def __repr__(self) -> str:
        model_name = self.model.__name__ if self.model else "Unbound"
        return f"<{type(self).__name__} for {model_name}>"


class InlineModelAdmin:
    """
    Configuração para exibição inline de models relacionados (Fase 2).
    
    Exemplo:
        class CommentInline(InlineModelAdmin):
            model = Comment
            fields = ("text", "author")
            extra = 0
    """
    model: type | None = None
    fields: tuple[str, ...] | None = None
    exclude: tuple[str, ...] = ()
    readonly_fields: tuple[str, ...] = ()
    extra: int = 3  # Número de forms vazios
    max_num: int | None = None
    fk_name: str | None = None
