"""
StructSchema - Sistema de schemas estruturados para JSON complexo.

Similar a TextChoices mas para estruturas JSON complexas com validação,
conversão automática e acesso por atributos tipados.

Example:
    class UserPreferences(StructSchema):
        theme = StringField(default="system", choices=["light", "dark", "system"])
        language = StringField(default="pt-BR", aliases=["lang"])
        notifications = NestedField({
            "email": BooleanField(default=True),
            "push": BooleanField(default=True),
        })
    
    class User(Model):
        preferences: Mapped[UserPreferences] = Field.struct(UserPreferences)
    
    # Uso
    user.preferences.theme  # Acesso tipado!
    user.preferences.notifications.email  # Acesso aninhado!
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any, ClassVar, Generic, TypeVar, get_type_hints
from weakref import WeakKeyDictionary

logger = logging.getLogger("strider.schema")

T = TypeVar("T")


# =============================================================================
# Field Base Class
# =============================================================================

class Field(ABC):
    """Base class for all schema fields."""
    
    def __init__(
        self,
        default: Any = None,
        nullable: bool = False,
        validators: list[callable] | None = None,
        aliases: list[str] | None = None,
    ):
        self.default = default
        self.nullable = nullable
        self.validators = validators or []
        self.aliases = aliases or []
    
    @abstractmethod
    def validate(self, value: Any) -> Any:
        """Validate and return the value. Raise ValidationError if invalid."""
        pass
    
    @abstractmethod
    def coerce(self, value: Any) -> Any:
        """Coerce value to the correct type. Raise ValueError/TypeError if fails."""
        pass
    
    def fast_coerce(self, value: Any) -> Any:
        """Fast coercion without full validation (for loading)."""
        return self.coerce(value)
    
    def serialize(self, value: Any) -> Any:
        """Serialize value for JSON storage."""
        return value
    
    def get_default(self) -> Any:
        """Get default value (calls callable if needed)."""
        if callable(self.default):
            return self.default()
        return deepcopy(self.default) if self.default is not None else None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert field definition to dict for serialization."""
        return {
            "type": self.__class__.__name__,
            "default": self.default,
            "nullable": self.nullable,
            "aliases": self.aliases,
        }


# =============================================================================
# Concrete Field Types
# =============================================================================

class StringField(Field):
    """String field with optional max_length, choices, and regex."""
    
    def __init__(
        self,
        default: str = "",
        max_length: int | None = None,
        choices: list[str] | None = None,
        regex: str | None = None,
        nullable: bool = False,
        aliases: list[str] | None = None,
    ):
        super().__init__(default=default, nullable=nullable, aliases=aliases)
        self.max_length = max_length
        self.choices = choices
        self.regex = regex
        if regex:
            import re
            self._compiled_regex = re.compile(regex)
        else:
            self._compiled_regex = None
    
    def validate(self, value: Any) -> str:
        if value is None:
            if self.nullable:
                return None
            value = self.get_default()
        
        if not isinstance(value, str):
            raise ValueError(f"Expected string, got {type(value).__name__}")
        
        if self.choices and value not in self.choices:
            raise ValueError(f"Value must be one of {self.choices}, got {value!r}")
        
        if self.max_length and len(value) > self.max_length:
            raise ValueError(f"String too long (max {self.max_length} chars)")
        
        if self._compiled_regex and not self._compiled_regex.match(value):
            raise ValueError(f"Value does not match required pattern")
        
        return value
    
    def coerce(self, value: Any) -> str:
        if value is None:
            return self.get_default() if not self.nullable else None
        return str(value)
    
    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "max_length": self.max_length,
            "choices": self.choices,
            "regex": self.regex,
        })
        return d


class IntegerField(Field):
    """Integer field with optional min/max bounds."""
    
    def __init__(
        self,
        default: int = 0,
        min_value: int | None = None,
        max_value: int | None = None,
        nullable: bool = False,
        aliases: list[str] | None = None,
    ):
        super().__init__(default=default, nullable=nullable, aliases=aliases)
        self.min_value = min_value
        self.max_value = max_value
    
    def validate(self, value: Any) -> int:
        if value is None:
            if self.nullable:
                return None
            value = self.get_default()
        
        if not isinstance(value, int):
            raise ValueError(f"Expected int, got {type(value).__name__}")
        
        if self.min_value is not None and value < self.min_value:
            raise ValueError(f"Value must be >= {self.min_value}")
        
        if self.max_value is not None and value > self.max_value:
            raise ValueError(f"Value must be <= {self.max_value}")
        
        return value
    
    def coerce(self, value: Any) -> int:
        if value is None:
            return self.get_default() if not self.nullable else None
        return int(value)
    
    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "min_value": self.min_value,
            "max_value": self.max_value,
        })
        return d


class FloatField(Field):
    """Float field with optional min/max bounds."""
    
    def __init__(
        self,
        default: float = 0.0,
        min_value: float | None = None,
        max_value: float | None = None,
        nullable: bool = False,
        aliases: list[str] | None = None,
    ):
        super().__init__(default=default, nullable=nullable, aliases=aliases)
        self.min_value = min_value
        self.max_value = max_value
    
    def validate(self, value: Any) -> float:
        if value is None:
            if self.nullable:
                return None
            value = self.get_default()
        
        if not isinstance(value, (int, float)):
            raise ValueError(f"Expected float, got {type(value).__name__}")
        
        value = float(value)
        
        if self.min_value is not None and value < self.min_value:
            raise ValueError(f"Value must be >= {self.min_value}")
        
        if self.max_value is not None and value > self.max_value:
            raise ValueError(f"Value must be <= {self.max_value}")
        
        return value
    
    def coerce(self, value: Any) -> float:
        if value is None:
            return self.get_default() if not self.nullable else None
        return float(value)
    
    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "min_value": self.min_value,
            "max_value": self.max_value,
        })
        return d


class BooleanField(Field):
    """Boolean field."""
    
    def __init__(
        self,
        default: bool = False,
        nullable: bool = False,
        aliases: list[str] | None = None,
    ):
        super().__init__(default=default, nullable=nullable, aliases=aliases)
    
    def validate(self, value: Any) -> bool:
        if value is None:
            if self.nullable:
                return None
            value = self.get_default()
        
        if not isinstance(value, bool):
            raise ValueError(f"Expected bool, got {type(value).__name__}")
        
        return value
    
    def coerce(self, value: Any) -> bool:
        if value is None:
            return self.get_default() if not self.nullable else None
        return bool(value)


class ListField(Field):
    """List field with item validation and optional max_size."""
    
    def __init__(
        self,
        item_field: Field | None = None,
        default: list | None = None,
        max_size: int | None = None,
        nullable: bool = False,
        aliases: list[str] | None = None,
    ):
        super().__init__(default=default or [], nullable=nullable, aliases=aliases)
        self.item_field = item_field
        self.max_size = max_size
    
    def validate(self, value: Any) -> list:
        if value is None:
            if self.nullable:
                return None
            value = self.get_default()
        
        if not isinstance(value, list):
            raise ValueError(f"Expected list, got {type(value).__name__}")
        
        if self.max_size and len(value) > self.max_size:
            raise ValueError(f"List too long (max {self.max_size} items)")
        
        if self.item_field:
            validated = []
            for i, item in enumerate(value):
                try:
                    validated.append(self.item_field.validate(item))
                except ValueError as e:
                    raise ValueError(f"Item {i}: {e}")
            return validated
        
        return value
    
    def coerce(self, value: Any) -> list:
        if value is None:
            return self.get_default() if not self.nullable else None
        
        if not isinstance(value, list):
            return [value]
        
        # Limit size during coercion
        if self.max_size and len(value) > self.max_size:
            logger.warning(f"ListField: truncating list from {len(value)} to {self.max_size} items")
            return value[:self.max_size]
        
        return value
    
    def fast_coerce(self, value: Any) -> list:
        """Fast path: don't validate items during loading."""
        if value is None:
            return self.get_default() if not self.nullable else None
        
        if not isinstance(value, list):
            return [value]
        
        if self.max_size and len(value) > self.max_size:
            return value[:self.max_size]
        
        return value
    
    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "item_field": self.item_field.to_dict() if self.item_field else None,
            "max_size": self.max_size,
        })
        return d


class NestedField(Field):
    """Nested StructSchema field."""
    
    def __init__(
        self,
        schema: type[StructSchema] | dict[str, Field],
        default: dict | None = None,
        nullable: bool = False,
        aliases: list[str] | None = None,
    ):
        # For schema classes, default should be an empty dict that gets converted
        super().__init__(default=default or {}, nullable=nullable, aliases=aliases)
        
        if isinstance(schema, dict):
            # Inline schema definition
            self.schema_class = None
            self._inline_fields = schema
        else:
            # Reference to StructSchema class
            self.schema_class = schema
            self._inline_fields = None
    
    def get_default(self) -> Any:
        """Get default value - for nested schemas, create an instance."""
        if self.schema_class:
            # Return a new instance of the nested schema with its defaults
            return self.schema_class()
        return deepcopy(self.default) if self.default is not None else {}
    
    def validate(self, value: Any) -> StructSchema | dict:
        if value is None:
            if self.nullable:
                return None
            value = self.get_default()
        
        if isinstance(value, self.schema_class) if self.schema_class else False:
            return value
        
        if not isinstance(value, dict):
            raise ValueError(f"Expected dict, got {type(value).__name__}")
        
        if self.schema_class:
            return self.schema_class.from_dict_safe(value)
        else:
            # Inline validation
            result = {}
            for name, field in self._inline_fields.items():
                if name in value:
                    result[name] = field.validate(value[name])
                else:
                    result[name] = field.get_default()
            return result
    
    def coerce(self, value: Any) -> StructSchema | dict:
        if value is None:
            return self.get_default() if not self.nullable else None
        
        if isinstance(value, self.schema_class) if self.schema_class else False:
            return value
        
        if not isinstance(value, dict):
            return self.get_default()
        
        if self.schema_class:
            return self.schema_class.from_dict_safe(value)
        return value
    
    def fast_coerce(self, value: Any) -> StructSchema | dict:
        """Fast path: use from_dict_fast if available."""
        if value is None:
            return self.get_default() if not self.nullable else None
        
        if isinstance(value, self.schema_class) if self.schema_class else False:
            return value
        
        if not isinstance(value, dict):
            return self.get_default()
        
        if self.schema_class:
            return self.schema_class.from_dict_fast(value)
        return value
    
    def serialize(self, value: Any) -> Any:
        """Serialize nested schema to dict."""
        if value is None:
            return None
        if isinstance(value, StructSchema):
            return value.to_dict()
        return value
    
    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        if self.schema_class:
            d["schema_class"] = self.schema_class.__name__
            # Include field definitions for the admin widget
            d["fields"] = {
                name: field.to_dict()
                for name, field in self.schema_class._fields.items()
            }
        else:
            d["fields"] = {k: v.to_dict() for k, v in self._inline_fields.items()}
        return d


class DictField(Field):
    """Dict field with optional key/value validation."""
    
    def __init__(
        self,
        value_field: Field | None = None,
        default: dict | None = None,
        max_size: int | None = None,
        nullable: bool = False,
        aliases: list[str] | None = None,
    ):
        super().__init__(default=default or {}, nullable=nullable, aliases=aliases)
        self.value_field = value_field
        self.max_size = max_size
    
    def validate(self, value: Any) -> dict:
        if value is None:
            if self.nullable:
                return None
            value = self.get_default()
        
        if not isinstance(value, dict):
            raise ValueError(f"Expected dict, got {type(value).__name__}")
        
        if self.max_size and len(value) > self.max_size:
            raise ValueError(f"Dict too large (max {self.max_size} keys)")
        
        if self.value_field:
            return {k: self.value_field.validate(v) for k, v in value.items()}
        
        return value
    
    def coerce(self, value: Any) -> dict:
        if value is None:
            return self.get_default() if not self.nullable else None
        
        if not isinstance(value, dict):
            return {}
        
        if self.max_size and len(value) > self.max_size:
            return dict(list(value.items())[:self.max_size])
        
        return value
    
    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "value_field": self.value_field.to_dict() if self.value_field else None,
            "max_size": self.max_size,
        })
        return d


class ChoiceField(Field):
    """Field that wraps TextChoices or IntegerChoices."""
    
    def __init__(
        self,
        choices_class: type,
        default: Any = None,
        nullable: bool = False,
        aliases: list[str] | None = None,
    ):
        super().__init__(default=default, nullable=nullable, aliases=aliases)
        self.choices_class = choices_class
    
    def validate(self, value: Any) -> Any:
        if value is None:
            if self.nullable:
                return None
            value = self.get_default()
        
        # Handle enum members
        if hasattr(value, "value"):
            value = value.value
        
        if not self.choices_class.is_valid(value):
            raise ValueError(f"Value must be one of {self.choices_class.values}, got {value!r}")
        
        return value
    
    def coerce(self, value: Any) -> Any:
        if value is None:
            return self.get_default() if not self.nullable else None
        
        if hasattr(value, "value"):
            return value.value
        
        return value
    
    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "choices_class": self.choices_class.__name__,
            "choices": self.choices_class.choices,
        })
        return d


# =============================================================================
# StructSchema Metaclass and Base Class
# =============================================================================

class StructSchemaMeta(type):
    """Metaclass for StructSchema that collects field definitions."""
    
    def __new__(mcs, name: str, bases: tuple, namespace: dict, **kwargs):
        # Collect field definitions from class body
        fields: dict[str, Field] = {}
        
        for key, value in list(namespace.items()):
            if isinstance(value, Field) and not key.startswith("_"):
                fields[key] = value
        
        # Inherit fields from base classes
        for base in bases:
            if hasattr(base, "_fields"):
                for field_name, field in base._fields.items():
                    if field_name not in fields:
                        fields[field_name] = field
        
        # Build alias map
        alias_map: dict[str, str] = {}
        for field_name, field in fields.items():
            for alias in field.aliases:
                alias_map[alias] = field_name
        
        # Create the class
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        
        # Store metadata on the class
        cls._fields = fields
        cls._alias_map = alias_map
        cls._schema_name = name
        
        return cls


class StructSchema(metaclass=StructSchemaMeta):
    """
    Base class for structured JSON schemas.
    
    Similar to TextChoices but for complex JSON structures.
    Provides automatic validation, coercion, and migration support.
    """
    
    # Class-level metadata (set by metaclass)
    _fields: ClassVar[dict[str, Field]] = {}
    _alias_map: ClassVar[dict[str, str]] = {}
    _schema_name: ClassVar[str] = ""
    
    def __init__(self, **kwargs):
        """Initialize with field values."""
        # Initialize all fields with defaults
        for name, field in self._fields.items():
            value = kwargs.get(name, field.get_default())
            super().__setattr__(name, value)
        
        # Store extra data (unknown fields)
        self._extra_data: dict[str, Any] = {}
    
    def __setattr__(self, name: str, value: Any) -> None:
        """Set attribute with validation for known fields."""
        if name.startswith("_"):
            # Private attributes bypass validation
            super().__setattr__(name, value)
            return
        
        if name in self._fields:
            field = self._fields[name]
            validated_value = field.validate(value)
            super().__setattr__(name, validated_value)
        else:
            # Unknown field - store in extra_data
            if not hasattr(self, "_extra_data"):
                super().__setattr__("_extra_data", {})
            self._extra_data[name] = value
    
    @classmethod
    def from_dict_safe(cls, data: dict[str, Any]) -> StructSchema:
        """
        Load from dict with maximum tolerance. Never fails.
        
        - Missing fields: use defaults
        - Extra fields: preserve in _extra_data
        - Aliases: map to current names
        - Invalid types: try to coerce, use default if fails
        """
        if data is None:
            data = {}
        
        result = {}
        extra_data = {}
        
        # 1. Resolve aliases (e.g., "lang" -> "language")
        normalized = {}
        for key, value in data.items():
            if key in cls._fields:
                normalized[key] = value
            elif key in cls._alias_map:
                actual_key = cls._alias_map[key]
                normalized[actual_key] = value
                logger.debug(f"Mapped alias '{key}' -> '{actual_key}'")
            else:
                # Unknown field - will be preserved in extra_data
                extra_data[key] = value
        
        # 2. Load defined fields
        for name, field in cls._fields.items():
            if name in normalized:
                try:
                    result[name] = field.coerce(normalized[name])
                except (ValueError, TypeError) as e:
                    # Coercion failed - log warning and use default
                    logger.warning(f"Field '{name}' coercion failed: {e}. Using default.")
                    result[name] = field.get_default()
            else:
                # Field missing - use default
                result[name] = field.get_default()
        
        # 3. Create instance
        instance = cls.__new__(cls)
        for name, value in result.items():
            super(StructSchema, instance).__setattr__(name, value)
        
        # 4. Store extra data
        super(StructSchema, instance).__setattr__("_extra_data", extra_data)
        
        return instance
    
    @classmethod
    def from_dict_fast(cls, data: dict[str, Any]) -> StructSchema:
        """
        Fast loading for large schemas. No validation during load.
        
        - Uses fast_coerce instead of coerce
        - Preserves dict reference for extra_data (no copy)
        """
        if data is None:
            data = {}
        
        result = {}
        extra_data = data  # Reference, not copy!
        
        # 1. Resolve aliases and separate known/unknown fields
        for key, value in data.items():
            if key in cls._fields:
                field = cls._fields[key]
                try:
                    result[key] = field.fast_coerce(value)
                except (ValueError, TypeError):
                    result[key] = field.get_default()
                # Remove from extra_data (it's a known field)
                extra_data = {k: v for k, v in extra_data.items() if k != key}
            elif key in cls._alias_map:
                actual_key = cls._alias_map[key]
                field = cls._fields[actual_key]
                try:
                    result[actual_key] = field.fast_coerce(value)
                except (ValueError, TypeError):
                    result[actual_key] = field.get_default()
                # Remove from extra_data
                extra_data = {k: v for k, v in extra_data.items() if k != key}
        
        # 2. Fill missing fields with defaults
        for name, field in cls._fields.items():
            if name not in result:
                result[name] = field.get_default()
        
        # 3. Create instance
        instance = cls.__new__(cls)
        for name, value in result.items():
            super(StructSchema, instance).__setattr__(name, value)
        
        # 4. Store extra data (unknown fields only)
        super(StructSchema, instance).__setattr__("_extra_data", extra_data)
        
        return instance
    
    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dict for JSON storage.
        
        - Uses current field names (never aliases)
        - Includes extra data (preserved fields)
        """
        result = {}
        
        # Serialize defined fields
        for name, field in self._fields.items():
            value = getattr(self, name, field.get_default())
            result[name] = field.serialize(value)
        
        # Include extra data (preserved unknown fields)
        if hasattr(self, "_extra_data"):
            result.update(self._extra_data)
        
        return result
    
    def to_dict_stream(self):
        """
        Stream fields for large schemas.
        
        Yields (name, value) pairs without building full dict in memory.
        """
        for name, field in self._fields.items():
            value = getattr(self, name, field.get_default())
            yield name, field.serialize(value)
        
        if hasattr(self, "_extra_data"):
            for key, value in self._extra_data.items():
                yield key, value
    
    def validate(self) -> list[str]:
        """Validate all fields and return list of errors."""
        errors = []
        
        for name, field in self._fields.items():
            value = getattr(self, name, None)
            try:
                field.validate(value)
            except ValueError as e:
                errors.append(f"{name}: {e}")
        
        return errors
    
    def is_valid(self) -> bool:
        """Check if all fields are valid."""
        return len(self.validate()) == 0
    
    def get(self, name: str, default: Any = None) -> Any:
        """Get field value by name (with optional default)."""
        if name in self._fields:
            return getattr(self, name, default)
        return self._extra_data.get(name, default)
    
    def set(self, name: str, value: Any) -> None:
        """Set field value by name."""
        setattr(self, name, value)
    
    def copy(self) -> StructSchema:
        """Create a deep copy of this schema."""
        return self.__class__.from_dict_safe(self.to_dict())
    
    def merge(self, other: dict | StructSchema) -> StructSchema:
        """Merge another dict/schema into this one. Returns new instance."""
        if isinstance(other, StructSchema):
            other = other.to_dict()
        
        merged = {**self.to_dict(), **other}
        return self.__class__.from_dict_safe(merged)
    
    @classmethod
    def default_dict(cls) -> dict[str, Any]:
        """Get default values as a dict."""
        return {name: field.get_default() for name, field in cls._fields.items()}
    
    @classmethod
    def get_field(cls, name: str) -> Field | None:
        """Get field definition by name."""
        return cls._fields.get(name)
    
    @classmethod
    def get_fields(cls) -> dict[str, Field]:
        """Get all field definitions."""
        return cls._fields.copy()
    
    def __repr__(self) -> str:
        fields_str = ", ".join(f"{name}={getattr(self, name, None)!r}" for name in self._fields)
        return f"{self.__class__.__name__}({fields_str})"
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, StructSchema):
            return False
        return self.to_dict() == other.to_dict()
    
    def __contains__(self, name: str) -> bool:
        """Check if field exists."""
        return name in self._fields or name in self._extra_data


# =============================================================================
# StructDescriptor for Model Integration
# =============================================================================

class StructDescriptor(Generic[T]):
    """
    Descriptor that converts between dict (database) and StructSchema instance (Python).
    
    Provides:
    - __get__: dict → StructSchema instance (typed access)
    - __set__: StructSchema/dict → dict (for database storage)
    - Caching for performance
    - Automatic merge for partial updates
    """
    
    def __init__(self, schema_class: type[T], column_name: str, cache: bool = True):
        self.schema_class = schema_class
        self.column_name = column_name
        self._cache_enabled = cache
        self._cache: WeakKeyDictionary = WeakKeyDictionary()
    
    def __set_name__(self, owner: type, name: str) -> None:
        """Called when descriptor is assigned to a class attribute."""
        self.public_name = name
    
    def __get__(self, obj, objtype=None) -> T:
        """Get StructSchema instance from dict stored in database."""
        if obj is None:
            return self
        
        # Check cache
        if self._cache_enabled and obj in self._cache:
            return self._cache[obj]
        
        # Get raw dict from database column
        raw_value = getattr(obj, self.column_name, None)
        if raw_value is None:
            raw_value = {}
        
        # Convert to StructSchema instance
        if isinstance(raw_value, dict):
            instance = self.schema_class.from_dict_safe(raw_value)
        elif isinstance(raw_value, StructSchema):
            instance = raw_value
        else:
            logger.warning(f"Unexpected type {type(raw_value)} in StructDescriptor, using defaults")
            instance = self.schema_class()
        
        # Cache the instance
        if self._cache_enabled:
            self._cache[obj] = instance
        
        return instance
    
    def __set__(self, obj, value: T | dict | None) -> None:
        """Set value, converting StructSchema/dict to dict for storage."""
        # Invalidate cache
        if obj in self._cache:
            del self._cache[obj]
        
        if value is None:
            setattr(obj, self.column_name, {} if not getattr(self.schema_class, "_nullable", False) else None)
            return
        
        if isinstance(value, self.schema_class):
            # StructSchema instance → dict
            raw_dict = value.to_dict()
        elif isinstance(value, dict):
            # Dict - merge with existing for partial updates
            existing = getattr(obj, self.column_name, None) or {}
            if isinstance(existing, dict):
                merged = {**existing, **value}
            else:
                merged = value
            
            # Convert through schema for validation/normalization
            instance = self.schema_class.from_dict_safe(merged)
            raw_dict = instance.to_dict()
        else:
            raise TypeError(f"Expected {self.schema_class.__name__} or dict, got {type(value).__name__}")
        
        setattr(obj, self.column_name, raw_dict)
    
    def __delete__(self, obj) -> None:
        """Delete the value."""
        if obj in self._cache:
            del self._cache[obj]
        setattr(obj, self.column_name, None)


# =============================================================================
# Validation Error
# =============================================================================

class ValidationError(ValueError):
    """Error raised when schema validation fails."""
    
    def __init__(self, message: str, field_name: str | None = None):
        super().__init__(message)
        self.field_name = field_name
        self.message = message
    
    def __str__(self) -> str:
        if self.field_name:
            return f"Validation error in field '{self.field_name}': {self.message}"
        return f"Validation error: {self.message}"


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Base classes
    "StructSchema",
    "StructSchemaMeta",
    "StructDescriptor",
    "Field",
    # Field types
    "StringField",
    "IntegerField",
    "FloatField",
    "BooleanField",
    "ListField",
    "NestedField",
    "DictField",
    "ChoiceField",
    # Errors
    "ValidationError",
]
