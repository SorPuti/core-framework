"""
Type definitions para o Admin Panel.

Tipos auxiliares para melhorar autocomplete e inferência estática no PyCharm.
Zero impacto em runtime - apenas para análise estática.

Uso:
    from core.admin.types import WidgetConfig, FieldsetConfig
    
    class UserAdmin(ModelAdmin[User]):
        widgets: dict[str, WidgetConfig] = {
            "email": {"widget": "email", "label": "E-mail"},
        }
"""

from typing import Any, Literal, TypedDict, TypeVar

from typing_extensions import NotRequired


# =============================================================================
# Widget Types
# =============================================================================

# Widgets disponíveis no frontend
WidgetType = Literal[
    "default",
    "string",
    "text",
    "integer",
    "float",
    "boolean",
    "datetime",
    "date",
    "time",
    "json",
    "uuid",
    # Widgets especiais
    "password",
    "password_hash",
    "virtual_password",
    "secret",
    "email",
    "url",
    "slug",
    "color",
    "ip",
    "choices",
    "fk",
    "m2m_select",
    "file_upload",
    "conditions_builder",
]


class WidgetConfig(TypedDict, total=False):
    """
    Configuração de widget para um campo no ModelAdmin.
    
    Exemplo:
        widgets = {
            "hostname_status": {
                "widget": "choices",
                "label": "Status do Hostname",
                "help_text": "Status atual no Cloudflare",
            },
        }
    """
    widget: WidgetType
    label: str
    help_text: str
    required_on_create: bool
    required_on_edit: bool


# =============================================================================
# Fieldset Types
# =============================================================================

class FieldsetOptions(TypedDict, total=False):
    """Opções de uma seção de fieldset."""
    fields: tuple[str, ...] | list[str]
    classes: tuple[str, ...] | list[str]
    description: str


# Fieldset é uma tupla (nome_seção, opções)
FieldsetConfig = tuple[str, FieldsetOptions]


# =============================================================================
# Column Info Types (retornado por get_column_info)
# =============================================================================

class ColumnInfo(TypedDict, total=False):
    """Metadados de uma coluna retornados para o frontend."""
    name: str
    type: str
    widget: WidgetType
    nullable: bool
    primary_key: bool
    has_default: bool
    required: bool
    readonly: bool
    help_text: str
    label: str
    # Enum/choices
    choices: list[dict[str, str]]
    # FK
    fk_table: str
    fk_column: str
    fk_display: str
    fk_app_label: str
    fk_model_name: str
    # Slug
    slug_source: str
    # Virtual fields
    virtual: bool
    password_target: str
    # M2M
    m2m_target_model: str
    m2m_target_table: str
    m2m_display_field: str
    m2m_value_field: str


# =============================================================================
# Action Types
# =============================================================================

class ActionInfo(TypedDict, total=False):
    """Informações de uma action do admin."""
    name: str
    description: str
    requires_selection: bool
    confirm: str
    permission: str


# =============================================================================
# Permission Types
# =============================================================================

PermissionType = Literal["view", "add", "change", "delete"]


# =============================================================================
# Icon Types (Lucide icons)
# =============================================================================

# Subset dos ícones Lucide mais usados no admin
IconType = Literal[
    "file",
    "folder",
    "user",
    "users",
    "settings",
    "database",
    "globe",
    "mail",
    "lock",
    "key",
    "shield",
    "activity",
    "alert-circle",
    "check-circle",
    "x-circle",
    "info",
    "home",
    "calendar",
    "clock",
    "tag",
    "bookmark",
    "star",
    "heart",
    "message-circle",
    "bell",
    "search",
    "filter",
    "edit",
    "trash",
    "plus",
    "minus",
    "refresh-cw",
    "download",
    "upload",
    "link",
    "external-link",
    "eye",
    "eye-off",
    "copy",
    "clipboard",
    "archive",
    "box",
    "package",
    "layers",
    "grid",
    "list",
    "table",
    "pie-chart",
    "bar-chart",
    "trending-up",
    "trending-down",
    "dollar-sign",
    "credit-card",
    "shopping-cart",
    "truck",
    "map-pin",
    "navigation",
    "compass",
    "flag",
    "award",
    "zap",
    "cpu",
    "server",
    "hard-drive",
    "wifi",
    "bluetooth",
    "monitor",
    "smartphone",
    "tablet",
    "printer",
    "camera",
    "image",
    "video",
    "music",
    "headphones",
    "mic",
    "volume-2",
    "play",
    "pause",
    "square",
    "circle",
    "triangle",
    "hexagon",
    "octagon",
    "hash",
    "at-sign",
    "percent",
    "code",
    "terminal",
    "git-branch",
    "git-commit",
    "git-merge",
    "git-pull-request",
    "github",
    "gitlab",
    "slack",
    "twitter",
    "facebook",
    "instagram",
    "linkedin",
    "youtube",
    "twitch",
    "rss",
    "chrome",
    "firefox",
    "safari",
    "edge",
    "opera",
]


# =============================================================================
# Generic Model TypeVar
# =============================================================================

# TypeVar para ModelAdmin genérico
# Importar de sqlalchemy.orm para bound correto
try:
    from sqlalchemy.orm import DeclarativeBase
    ModelT = TypeVar("ModelT", bound=DeclarativeBase)
except ImportError:
    # Fallback se SQLAlchemy não estiver disponível
    ModelT = TypeVar("ModelT")


__all__ = [
    # Widget types
    "WidgetType",
    "WidgetConfig",
    # Fieldset types
    "FieldsetOptions",
    "FieldsetConfig",
    # Column info
    "ColumnInfo",
    # Action types
    "ActionInfo",
    # Permission types
    "PermissionType",
    # Icon types
    "IconType",
    # Generic
    "ModelT",
]
