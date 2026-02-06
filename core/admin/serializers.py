"""
Auto-geração de schemas Pydantic a partir de models SQLAlchemy.

Introspecta Mapped[] columns e gera:
- ListSchema: campos para list view
- DetailSchema: todos os campos (read)
- WriteSchema: campos editáveis (create/update)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, create_model

logger = logging.getLogger("core.admin")

# Mapa de tipos SQLAlchemy para tipos Python
_TYPE_MAP: dict[str, type] = {
    "INTEGER": int,
    "BIGINT": int,
    "SMALLINT": int,
    "VARCHAR": str,
    "STRING": str,
    "TEXT": str,
    "BOOLEAN": bool,
    "FLOAT": float,
    "NUMERIC": float,
    "DECIMAL": float,
    "DATETIME": datetime,
    "TIMESTAMP": datetime,
    "DATE": datetime,
    "JSON": dict,
    "JSONB": dict,
    "UUID": str,
}


def _get_python_type(col: Any) -> type:
    """Resolve o tipo Python de uma coluna SQLAlchemy."""
    col_type = str(col.type).upper()
    
    for key, python_type in _TYPE_MAP.items():
        if key in col_type:
            return python_type
    
    return str  # fallback


def generate_list_schema(
    model: type,
    admin: Any,
) -> type[BaseModel]:
    """
    Gera schema Pydantic para list view.
    
    Inclui apenas colunas em list_display.
    """
    model_name = model.__name__
    fields: dict[str, Any] = {}
    
    try:
        columns = {col.name: col for col in model.__table__.columns}
    except Exception:
        # Model sem tabela — retorna schema vazio
        return create_model(f"{model_name}ListSchema", __base__=_AdminSchema)
    
    display_fields = admin.list_display if admin.list_display else tuple(columns.keys())
    
    for field_name in display_fields:
        if field_name in columns:
            col = columns[field_name]
            python_type = _get_python_type(col)
            if col.nullable:
                fields[field_name] = (Optional[python_type], None)
            else:
                fields[field_name] = (python_type, ...)
        else:
            # Campo computado (método no ModelAdmin)
            fields[field_name] = (Optional[str], None)
    
    return create_model(
        f"{model_name}ListSchema",
        __base__=_AdminSchema,
        **fields,
    )


def generate_detail_schema(
    model: type,
    admin: Any,
) -> type[BaseModel]:
    """
    Gera schema Pydantic para detail view.
    
    Inclui todos os campos visíveis.
    """
    model_name = model.__name__
    fields: dict[str, Any] = {}
    
    try:
        columns = {col.name: col for col in model.__table__.columns}
    except Exception:
        return create_model(f"{model_name}DetailSchema", __base__=_AdminSchema)
    
    display_fields = admin.get_display_fields() if admin.get_display_fields() else list(columns.keys())
    
    for field_name in display_fields:
        if field_name in columns:
            col = columns[field_name]
            python_type = _get_python_type(col)
            if col.nullable:
                fields[field_name] = (Optional[python_type], None)
            else:
                fields[field_name] = (python_type, ...)
    
    return create_model(
        f"{model_name}DetailSchema",
        __base__=_AdminSchema,
        **fields,
    )


def generate_write_schema(
    model: type,
    admin: Any,
) -> type[BaseModel]:
    """
    Gera schema Pydantic para create/update.
    
    Exclui readonly_fields e campos em exclude.
    Garante proteção contra mass assignment.
    """
    model_name = model.__name__
    fields: dict[str, Any] = {}
    
    try:
        columns = {col.name: col for col in model.__table__.columns}
    except Exception:
        return create_model(f"{model_name}WriteSchema", __base__=_AdminSchema)
    
    editable = admin.get_editable_fields()
    
    for field_name in editable:
        if field_name in columns:
            col = columns[field_name]
            python_type = _get_python_type(col)
            
            # Campos com default ou nullable são opcionais no write
            if col.nullable or col.default is not None or col.server_default is not None:
                fields[field_name] = (Optional[python_type], None)
            else:
                fields[field_name] = (python_type, ...)
    
    return create_model(
        f"{model_name}WriteSchema",
        __base__=_AdminSchema,
        **fields,
    )


def serialize_instance(obj: Any, schema_fields: list[str], admin: Any = None) -> dict[str, Any]:
    """
    Serializa uma instância de model para dict.
    
    Suporta campos computados (métodos no ModelAdmin).
    """
    data: dict[str, Any] = {}
    
    for field_name in schema_fields:
        # Tenta campo do model primeiro
        if hasattr(obj, field_name):
            value = getattr(obj, field_name)
            # Converte tipos não serializáveis
            if isinstance(value, datetime):
                value = value.isoformat()
            elif isinstance(value, UUID):
                value = str(value)
            data[field_name] = value
        # Tenta método do ModelAdmin
        elif admin and hasattr(admin, field_name) and callable(getattr(admin, field_name)):
            method = getattr(admin, field_name)
            try:
                value = method(obj)
                data[field_name] = value
            except Exception:
                data[field_name] = None
        else:
            data[field_name] = None
    
    return data


class _AdminSchema(BaseModel):
    """Base schema para schemas auto-gerados do admin."""
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)
