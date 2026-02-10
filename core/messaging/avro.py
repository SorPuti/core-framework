"""
Avro schema support for messaging.

Auto-generate Avro schemas from Pydantic models.

Example:
    from core.messaging import AvroModel
    
    class UserEvent(AvroModel):
        user_id: int
        email: str
        created_at: datetime
        metadata: dict[str, Any] | None = None
    
    # Get Avro schema
    schema = UserEvent.__avro_schema__()
    # {
    #     "type": "record",
    #     "name": "UserEvent",
    #     "namespace": "com.example.events",
    #     "fields": [
    #         {"name": "user_id", "type": "long"},
    #         {"name": "email", "type": "string"},
    #         {"name": "created_at", "type": {"type": "long", "logicalType": "timestamp-millis"}},
    #         {"name": "metadata", "type": ["null", {"type": "map", "values": "string"}], "default": null}
    #     ]
    # }
"""

from __future__ import annotations

from typing import Any, get_type_hints, get_origin, get_args, Union
from datetime import datetime, date, time
from decimal import Decimal
from enum import Enum
from uuid import UUID
import json

from pydantic import BaseModel


def _get_default_namespace() -> str:
    """
    Retorna o namespace padrão para schemas Avro.
    
    Usa Settings.avro_default_namespace se disponível,
    senão usa o fallback hardcoded.
    """
    try:
        from core.config import get_settings, is_configured
        if is_configured():
            return get_settings().avro_default_namespace
    except Exception:
        pass
    return "com.core.events"


# Constante para compatibilidade (use _get_default_namespace() para valor dinâmico)
DEFAULT_NAMESPACE = "com.core.events"


def _python_type_to_avro(
    python_type: type,
    field_name: str = "",
    namespace: str | None = None,
) -> dict[str, Any] | str | list:
    """
    Convert Python type to Avro type.
    
    Args:
        python_type: Python type annotation
        field_name: Field name (for nested records)
        namespace: Avro namespace (usa Settings.avro_default_namespace se None)
    
    Returns:
        Avro type definition
    """
    if namespace is None:
        namespace = _get_default_namespace()
    
    origin = get_origin(python_type)
    args = get_args(python_type)
    
    # Handle Optional (Union with None)
    if origin is Union:
        non_none_types = [t for t in args if t is not type(None)]
        if len(non_none_types) == 1:
            # Optional[X] -> ["null", X]
            inner_type = _python_type_to_avro(non_none_types[0], field_name, namespace)
            return ["null", inner_type]
        else:
            # Union of multiple types
            return [_python_type_to_avro(t, field_name, namespace) for t in args]
    
    # Handle list/List
    if origin is list:
        item_type = args[0] if args else Any
        return {
            "type": "array",
            "items": _python_type_to_avro(item_type, field_name, namespace),
        }
    
    # Handle dict/Dict
    if origin is dict:
        value_type = args[1] if len(args) > 1 else Any
        return {
            "type": "map",
            "values": _python_type_to_avro(value_type, field_name, namespace),
        }
    
    # Handle basic types
    if python_type is str:
        return "string"
    
    if python_type is int:
        return "long"
    
    if python_type is float:
        return "double"
    
    if python_type is bool:
        return "boolean"
    
    if python_type is bytes:
        return "bytes"
    
    if python_type is type(None):
        return "null"
    
    # Handle datetime types
    if python_type is datetime:
        return {
            "type": "long",
            "logicalType": "timestamp-millis",
        }
    
    if python_type is date:
        return {
            "type": "int",
            "logicalType": "date",
        }
    
    if python_type is time:
        return {
            "type": "int",
            "logicalType": "time-millis",
        }
    
    # Handle UUID
    if python_type is UUID:
        return {
            "type": "string",
            "logicalType": "uuid",
        }
    
    # Handle Decimal
    if python_type is Decimal:
        return {
            "type": "bytes",
            "logicalType": "decimal",
            "precision": 38,
            "scale": 9,
        }
    
    # Handle Enum
    if isinstance(python_type, type) and issubclass(python_type, Enum):
        return {
            "type": "enum",
            "name": python_type.__name__,
            "namespace": namespace,
            "symbols": [e.value if isinstance(e.value, str) else e.name for e in python_type],
        }
    
    # Handle nested Pydantic models
    if isinstance(python_type, type) and issubclass(python_type, BaseModel):
        return _pydantic_to_avro_schema(python_type, namespace)
    
    # Handle Any
    if python_type is Any:
        return "string"  # Fallback to string for Any
    
    # Default to string for unknown types
    return "string"


def _pydantic_to_avro_schema(
    model: type[BaseModel],
    namespace: str | None = None,
) -> dict[str, Any]:
    """
    Convert Pydantic model to Avro schema.
    
    Args:
        model: Pydantic model class
        namespace: Avro namespace (usa Settings.avro_default_namespace se None)
    
    Returns:
        Avro schema dict
    """
    if namespace is None:
        namespace = _get_default_namespace()
    fields = []
    hints = get_type_hints(model)
    
    for field_name, field_type in hints.items():
        avro_type = _python_type_to_avro(field_type, field_name, namespace)
        
        field_def: dict[str, Any] = {
            "name": field_name,
            "type": avro_type,
        }
        
        # Add default if field has one
        model_field = model.model_fields.get(field_name)
        if model_field is not None:
            if model_field.default is not None:
                field_def["default"] = model_field.default
            elif model_field.default_factory is not None:
                # Can't represent factory in Avro, use null if optional
                if isinstance(avro_type, list) and "null" in avro_type:
                    field_def["default"] = None
        
        # Handle Optional fields - set default to null
        if isinstance(avro_type, list) and avro_type[0] == "null":
            if "default" not in field_def:
                field_def["default"] = None
        
        # Add doc from field description
        if model_field and model_field.description:
            field_def["doc"] = model_field.description
        
        fields.append(field_def)
    
    schema = {
        "type": "record",
        "name": model.__name__,
        "namespace": namespace,
        "fields": fields,
    }
    
    # Add doc from model docstring
    if model.__doc__:
        schema["doc"] = model.__doc__.strip()
    
    return schema


class AvroModelMeta(type(BaseModel)):
    """Metaclass that adds Avro schema generation to Pydantic models."""
    
    def __new__(mcs, name: str, bases: tuple, namespace: dict, **kwargs):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        
        # Don't process the base AvroModel class
        if name == "AvroModel":
            return cls
        
        # Cache the Avro schema (usa namespace do Settings se não definido na classe)
        avro_namespace = getattr(cls, "__avro_namespace__", None)
        if avro_namespace is None:
            avro_namespace = _get_default_namespace()
        cls._avro_schema_cache = _pydantic_to_avro_schema(cls, avro_namespace)
        
        return cls


class AvroModel(BaseModel, metaclass=AvroModelMeta):
    """
    Pydantic model with automatic Avro schema generation.
    
    Example:
        class UserCreatedEvent(AvroModel):
            __avro_namespace__ = "com.myapp.events"
            
            user_id: int
            email: str
            created_at: datetime
            roles: list[str] = []
            metadata: dict[str, str] | None = None
        
        # Get Avro schema
        schema = UserCreatedEvent.__avro_schema__()
        
        # Serialize to Avro bytes
        avro_bytes = UserCreatedEvent(user_id=1, email="test@example.com").to_avro()
        
        # Deserialize from Avro bytes
        event = UserCreatedEvent.from_avro(avro_bytes)
    """
    
    # Override in subclass to set namespace (usa Settings.avro_default_namespace se None)
    __avro_namespace__: str | None = None
    
    # Cached schema (set by metaclass)
    _avro_schema_cache: dict[str, Any] | None = None
    
    @classmethod
    def __avro_schema__(cls) -> dict[str, Any]:
        """
        Get the Avro schema for this model.
        
        Returns:
            Avro schema dict
        """
        if cls._avro_schema_cache is None:
            avro_namespace = getattr(cls, "__avro_namespace__", None)
            if avro_namespace is None:
                avro_namespace = _get_default_namespace()
            cls._avro_schema_cache = _pydantic_to_avro_schema(cls, avro_namespace)
        return cls._avro_schema_cache
    
    @classmethod
    def avro_schema_json(cls) -> str:
        """
        Get the Avro schema as JSON string.
        
        Returns:
            JSON string of Avro schema
        """
        return json.dumps(cls.__avro_schema__(), indent=2)
    
    def to_avro(self) -> bytes:
        """
        Serialize model to Avro bytes.
        
        Requires fastavro package.
        
        Returns:
            Avro-encoded bytes
        """
        try:
            import fastavro
            from io import BytesIO
        except ImportError:
            raise ImportError(
                "fastavro is required for Avro serialization. "
                "Install with: pip install fastavro"
            )
        
        schema = fastavro.parse_schema(self.__avro_schema__())
        buffer = BytesIO()
        fastavro.schemaless_writer(buffer, schema, self.model_dump())
        return buffer.getvalue()
    
    @classmethod
    def from_avro(cls, data: bytes) -> "AvroModel":
        """
        Deserialize model from Avro bytes.
        
        Requires fastavro package.
        
        Args:
            data: Avro-encoded bytes
        
        Returns:
            Model instance
        """
        try:
            import fastavro
            from io import BytesIO
        except ImportError:
            raise ImportError(
                "fastavro is required for Avro deserialization. "
                "Install with: pip install fastavro"
            )
        
        schema = fastavro.parse_schema(cls.__avro_schema__())
        buffer = BytesIO(data)
        record = fastavro.schemaless_reader(buffer, schema)
        return cls.model_validate(record)


def avro_schema(
    namespace: str | None = None,
    name: str | None = None,
):
    """
    Decorator to add Avro schema generation to a Pydantic model.
    
    Example:
        @avro_schema(namespace="com.myapp.events")
        class UserEvent(BaseModel):
            user_id: int
            email: str
    
    Args:
        namespace: Avro namespace (usa Settings.avro_default_namespace se None)
        name: Optional schema name (defaults to class name)
    
    Returns:
        Decorated class with __avro_schema__ method
    """
    def decorator(cls: type[BaseModel]) -> type[BaseModel]:
        ns = namespace if namespace is not None else _get_default_namespace()
        schema = _pydantic_to_avro_schema(cls, ns)
        
        if name:
            schema["name"] = name
        
        cls._avro_schema_cache = schema
        cls.__avro_schema__ = classmethod(lambda c: c._avro_schema_cache)
        cls.__avro_namespace__ = namespace
        
        return cls
    
    return decorator
