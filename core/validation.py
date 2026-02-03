"""
Sistema de Validação Rigorosa para Core Framework.

Este módulo implementa validação automática entre Pydantic schemas e
SQLAlchemy models, garantindo consistência e prevenindo erros em runtime.

Regras de Validação:
    R1: Campo NOT NULL no model = REQUIRED no schema (Erro em strict)
    R2: max_length do model >= max_length do schema (Warning)
    R3: Tipo do schema deve ser compatível com model (Warning)
    R4: Campo extra não existe no model (Warning)
    R5: Validação executada no startup (Fail-fast em DEBUG)

Usage:
    from core.validation import SchemaModelValidator
    
    # Validar manualmente
    issues = SchemaModelValidator.validate(
        UserInput,
        User,
        strict=True,
        context="UserViewSet"
    )
    
    # Ou deixar o framework validar automaticamente no startup
"""

from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING, Any, get_args, get_origin

if TYPE_CHECKING:
    from pydantic import BaseModel
    from pydantic.fields import FieldInfo

logger = logging.getLogger("core.validation")


# =============================================================================
# Exceptions
# =============================================================================

class SchemaModelMismatchError(Exception):
    """
    Raised when schema and model have incompatible field definitions.
    
    This error indicates a critical mismatch that will likely cause
    runtime errors (e.g., database integrity violations).
    """
    pass


class ValidationWarning(UserWarning):
    """Warning for non-critical schema/model mismatches."""
    pass


# =============================================================================
# Type Mapping
# =============================================================================

# SQLAlchemy type to Python type mapping
_SQLALCHEMY_TYPE_MAP: dict[str, type] = {
    "String": str,
    "Text": str,
    "VARCHAR": str,
    "CHAR": str,
    "Integer": int,
    "BigInteger": int,
    "SmallInteger": int,
    "BIGINT": int,
    "SMALLINT": int,
    "INT": int,
    "INTEGER": int,
    "Boolean": bool,
    "BOOLEAN": bool,
    "Float": float,
    "FLOAT": float,
    "Numeric": float,
    "DECIMAL": float,
    "DateTime": "datetime",
    "DATETIME": "datetime",
    "Date": "date",
    "DATE": "date",
    "Time": "time",
    "TIME": "time",
    "UUID": "uuid",
    "JSON": dict,
    "JSONB": dict,
    "ARRAY": list,
    "LargeBinary": bytes,
    "BLOB": bytes,
}


# =============================================================================
# Schema Model Validator
# =============================================================================

class SchemaModelValidator:
    """
    Validates that Pydantic schemas match SQLAlchemy models.
    
    This validator ensures consistency between your API contracts (schemas)
    and your database structure (models), preventing common errors like:
    
    - Allowing None for NOT NULL columns
    - Accepting strings longer than the column allows
    - Type mismatches between schema and model
    
    Rules:
        1. If model field is NOT NULL, schema field MUST be required
        2. If model field has max_length, schema should validate it
        3. If model field has constraints, schema should mirror them
        4. Fields in schema but not in model generate warnings
    
    Example:
        >>> from core.validation import SchemaModelValidator
        >>> 
        >>> class User(Model):
        ...     name = Column(String(100), nullable=False)
        ...     bio = Column(Text, nullable=True)
        >>> 
        >>> class UserInput(BaseModel):
        ...     name: str | None = None  # BUG: Should be required!
        ...     bio: str | None = None   # OK: nullable in model
        >>> 
        >>> SchemaModelValidator.validate(UserInput, User, strict=True)
        # Raises SchemaModelMismatchError!
    """
    
    # Cache for validated pairs to avoid re-validation
    _validated_pairs: set[tuple[type, type]] = set()
    
    @classmethod
    def validate(
        cls,
        schema: type["BaseModel"],
        model: type,
        *,
        strict: bool = True,
        context: str = "",
        check_output: bool = False,
    ) -> list[str]:
        """
        Validate schema against model.
        
        Args:
            schema: Pydantic schema class (BaseModel subclass)
            model: SQLAlchemy model class
            strict: If True, raise error on critical mismatch.
                   If False, just warn and continue.
            context: Context for error messages (e.g., "UserViewSet.register")
            check_output: If True, this is an output schema (less strict)
        
        Returns:
            List of issues found (warnings and errors)
        
        Raises:
            SchemaModelMismatchError: If strict=True and critical issues found
        
        Example:
            >>> issues = SchemaModelValidator.validate(
            ...     UserCreateInput,
            ...     User,
            ...     strict=True,
            ...     context="UserViewSet.create"
            ... )
        """
        # Check cache
        cache_key = (schema, model)
        if cache_key in cls._validated_pairs:
            return []
        
        issues: list[str] = []
        critical_issues: list[str] = []
        
        # Get schema fields
        schema_fields = cls._get_schema_fields(schema)
        if not schema_fields:
            return []
        
        # Get model columns
        model_columns = cls._get_model_columns(model)
        if not model_columns:
            logger.debug(f"Could not inspect model {model.__name__}, skipping validation")
            return []
        
        ctx = f"[{context}] " if context else ""
        
        for field_name, field_info in schema_fields.items():
            # Skip fields not in model (could be computed fields)
            if field_name not in model_columns:
                continue
            
            col_info = model_columns[field_name]
            
            # Rule 1: NOT NULL check (critical for input schemas)
            if not check_output:
                r1_issue = cls._check_nullable_mismatch(
                    field_name, field_info, col_info, ctx
                )
                if r1_issue:
                    critical_issues.append(r1_issue)
            
            # Rule 2: max_length check
            r2_issue = cls._check_max_length(
                field_name, field_info, col_info, ctx
            )
            if r2_issue:
                issues.append(r2_issue)
            
            # Rule 3: Type compatibility check
            r3_issue = cls._check_type_compatibility(
                field_name, field_info, col_info, ctx
            )
            if r3_issue:
                issues.append(r3_issue)
        
        # Rule 4: Check for unknown fields (fields in schema not in model)
        for field_name in schema_fields:
            if field_name not in model_columns and field_name not in ("id", "created_at", "updated_at"):
                issues.append(
                    f"{ctx}Field '{field_name}' in schema but not in model "
                    f"{model.__name__}. This may be intentional for computed fields."
                )
        
        # Process issues
        all_issues = critical_issues + issues
        
        for issue in issues:
            logger.warning(issue)
            if not strict:
                warnings.warn(issue, ValidationWarning, stacklevel=3)
        
        for issue in critical_issues:
            logger.error(issue)
        
        # Raise if strict mode and critical issues found
        if strict and critical_issues:
            cls._validated_pairs.discard(cache_key)
            raise SchemaModelMismatchError(
                f"Schema/Model validation failed:\n" + "\n".join(critical_issues)
            )
        
        # Cache successful validation
        cls._validated_pairs.add(cache_key)
        
        return all_issues
    
    @classmethod
    def validate_viewset(
        cls,
        viewset_class: type,
        *,
        strict: bool = True,
    ) -> list[str]:
        """
        Validate all schemas in a ViewSet against its model.
        
        Args:
            viewset_class: ViewSet class to validate
            strict: If True, raise on critical issues
        
        Returns:
            List of all issues found
        """
        issues: list[str] = []
        context = viewset_class.__name__
        
        model = getattr(viewset_class, "model", None)
        if not model:
            return []
        
        # Validate input schema (strict for required fields)
        input_schema = getattr(viewset_class, "input_schema", None)
        if input_schema:
            issues.extend(cls.validate(
                input_schema,
                model,
                strict=strict,
                context=f"{context}.input_schema",
                check_output=False,
            ))
        
        # Validate output schema (less strict)
        output_schema = getattr(viewset_class, "output_schema", None)
        if output_schema:
            issues.extend(cls.validate(
                output_schema,
                model,
                strict=False,  # Output can have fewer/different fields
                context=f"{context}.output_schema",
                check_output=True,
            ))
        
        # Validate create schema
        create_schema = getattr(viewset_class, "create_schema", None)
        if create_schema and create_schema != input_schema:
            issues.extend(cls.validate(
                create_schema,
                model,
                strict=strict,
                context=f"{context}.create_schema",
                check_output=False,
            ))
        
        # Validate update schema (optional fields OK)
        update_schema = getattr(viewset_class, "update_schema", None)
        if update_schema and update_schema != input_schema:
            issues.extend(cls.validate(
                update_schema,
                model,
                strict=False,  # Update schemas can have optional fields
                context=f"{context}.update_schema",
                check_output=False,
            ))
        
        return issues
    
    @classmethod
    def clear_cache(cls) -> None:
        """Clear the validation cache."""
        cls._validated_pairs.clear()
    
    # =========================================================================
    # Private Methods
    # =========================================================================
    
    @classmethod
    def _get_schema_fields(cls, schema: type["BaseModel"]) -> dict[str, "FieldInfo"]:
        """Extract field info from Pydantic schema."""
        try:
            return schema.model_fields
        except AttributeError:
            # Pydantic v1 fallback
            try:
                return schema.__fields__
            except AttributeError:
                return {}
    
    @classmethod
    def _get_model_columns(cls, model: type) -> dict[str, "ColumnInfo"]:
        """
        Extract column info from SQLAlchemy model.
        
        Returns dict with column name -> ColumnInfo containing:
        - nullable: bool
        - max_length: int | None
        - python_type: type
        - sa_type: SQLAlchemy type instance
        """
        try:
            from sqlalchemy import inspect
            from sqlalchemy.orm import Mapper
            
            mapper: Mapper = inspect(model)
            columns = {}
            
            for col in mapper.columns:
                columns[col.name] = ColumnInfo(
                    name=col.name,
                    nullable=col.nullable,
                    max_length=getattr(col.type, "length", None),
                    python_type=cls._get_python_type(col.type),
                    sa_type=col.type,
                    has_default=col.default is not None or col.server_default is not None,
                    is_primary_key=col.primary_key,
                    is_autoincrement=getattr(col, "autoincrement", False),
                )
            
            return columns
        except Exception as e:
            logger.debug(f"Could not inspect model: {e}")
            return {}
    
    @classmethod
    def _get_python_type(cls, sa_type: Any) -> type:
        """Convert SQLAlchemy type to Python type."""
        type_name = type(sa_type).__name__
        
        # Check direct mapping
        if type_name in _SQLALCHEMY_TYPE_MAP:
            mapped = _SQLALCHEMY_TYPE_MAP[type_name]
            if isinstance(mapped, str):
                # Handle special types
                if mapped == "datetime":
                    from datetime import datetime
                    return datetime
                elif mapped == "date":
                    from datetime import date
                    return date
                elif mapped == "time":
                    from datetime import time
                    return time
                elif mapped == "uuid":
                    from uuid import UUID
                    return UUID
            return mapped
        
        # Try to get impl type
        try:
            impl = getattr(sa_type, "impl", None)
            if impl:
                return cls._get_python_type(impl)
        except Exception:
            pass
        
        # Default to Any
        return Any
    
    @classmethod
    def _check_nullable_mismatch(
        cls,
        field_name: str,
        field_info: "FieldInfo",
        col_info: "ColumnInfo",
        ctx: str,
    ) -> str | None:
        """
        Rule 1: Check if NOT NULL column has optional schema field.
        
        This is a CRITICAL issue - will cause IntegrityError at runtime.
        """
        # Skip primary keys and auto-generated fields
        if col_info.is_primary_key or col_info.is_autoincrement:
            return None
        
        # Skip fields with defaults
        if col_info.has_default:
            return None
        
        # Check if model requires the field (NOT NULL, no default)
        model_requires = not col_info.nullable and not col_info.has_default
        
        # Check if schema makes field optional
        schema_optional = not cls._is_field_required(field_info)
        
        if model_requires and schema_optional:
            return (
                f"{ctx}CRITICAL: Field '{field_name}' is NOT NULL in model "
                f"but OPTIONAL in schema. This WILL cause IntegrityError! "
                f"Make the field required in the schema."
            )
        
        return None
    
    @classmethod
    def _check_max_length(
        cls,
        field_name: str,
        field_info: "FieldInfo",
        col_info: "ColumnInfo",
        ctx: str,
    ) -> str | None:
        """
        Rule 2: Check if schema allows values longer than model accepts.
        """
        if not col_info.max_length:
            return None
        
        schema_max = cls._get_schema_max_length(field_info)
        
        if schema_max is None:
            return (
                f"{ctx}Field '{field_name}' has max_length={col_info.max_length} "
                f"in model but no length validation in schema. "
                f"Add max_length constraint to prevent truncation."
            )
        
        if schema_max > col_info.max_length:
            return (
                f"{ctx}Field '{field_name}' allows {schema_max} chars in schema "
                f"but model only accepts {col_info.max_length}. "
                f"Values may be truncated or cause errors."
            )
        
        return None
    
    @classmethod
    def _check_type_compatibility(
        cls,
        field_name: str,
        field_info: "FieldInfo",
        col_info: "ColumnInfo",
        ctx: str,
    ) -> str | None:
        """
        Rule 3: Check if schema type is compatible with model type.
        """
        schema_type = cls._get_schema_type(field_info)
        model_type = col_info.python_type
        
        if schema_type is None or model_type is Any:
            return None
        
        # Handle Optional types
        if get_origin(schema_type) is type(None):
            return None
        
        # Unwrap Optional/Union
        schema_type = cls._unwrap_optional(schema_type)
        
        if schema_type is Any:
            return None
        
        # Check compatibility
        if not cls._types_compatible(schema_type, model_type):
            return (
                f"{ctx}Field '{field_name}' has type {model_type.__name__} in model "
                f"but {schema_type} in schema. Types may be incompatible."
            )
        
        return None
    
    @classmethod
    def _is_field_required(cls, field_info: "FieldInfo") -> bool:
        """Check if Pydantic field is required."""
        try:
            # Pydantic v2
            return field_info.is_required()
        except (AttributeError, TypeError):
            pass
        
        try:
            # Check default
            if field_info.default is not None:
                return False
            if field_info.default_factory is not None:
                return False
            # Check if explicitly required
            from pydantic_core import PydanticUndefined
            return field_info.default is PydanticUndefined
        except Exception:
            pass
        
        # Fallback: assume required if no default
        return getattr(field_info, "default", ...) is ...
    
    @classmethod
    def _get_schema_max_length(cls, field_info: "FieldInfo") -> int | None:
        """Extract max_length from Pydantic field metadata."""
        # Check metadata
        metadata = getattr(field_info, "metadata", []) or []
        for meta in metadata:
            if hasattr(meta, "max_length"):
                return meta.max_length
        
        # Check json_schema_extra
        json_extra = getattr(field_info, "json_schema_extra", None)
        if json_extra and isinstance(json_extra, dict):
            return json_extra.get("maxLength")
        
        return None
    
    @classmethod
    def _get_schema_type(cls, field_info: "FieldInfo") -> type | None:
        """Extract type from Pydantic field."""
        try:
            return field_info.annotation
        except AttributeError:
            return getattr(field_info, "outer_type_", None)
    
    @classmethod
    def _unwrap_optional(cls, t: type) -> type:
        """Unwrap Optional[X] or X | None to X."""
        from types import UnionType
        
        origin = get_origin(t)
        
        # Handle Union types (including X | None)
        if origin is UnionType or (hasattr(t, "__class__") and t.__class__ is UnionType):
            args = get_args(t)
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return non_none[0]
            return t
        
        # Handle typing.Union
        try:
            from typing import Union
            if origin is Union:
                args = get_args(t)
                non_none = [a for a in args if a is not type(None)]
                if len(non_none) == 1:
                    return non_none[0]
        except Exception:
            pass
        
        return t
    
    @classmethod
    def _types_compatible(cls, schema_type: type, model_type: type) -> bool:
        """Check if schema type is compatible with model type."""
        # Same type
        if schema_type is model_type:
            return True
        
        # Both are string-like
        if schema_type is str and model_type is str:
            return True
        
        # Both are numeric
        numeric = (int, float)
        if schema_type in numeric and model_type in numeric:
            return True
        
        # Check subclass
        try:
            if isinstance(schema_type, type) and isinstance(model_type, type):
                return issubclass(schema_type, model_type) or issubclass(model_type, schema_type)
        except TypeError:
            pass
        
        return True  # Be permissive for unknown types


# =============================================================================
# Column Info Data Class
# =============================================================================

class ColumnInfo:
    """Information about a SQLAlchemy column."""
    
    __slots__ = (
        "name",
        "nullable",
        "max_length",
        "python_type",
        "sa_type",
        "has_default",
        "is_primary_key",
        "is_autoincrement",
    )
    
    def __init__(
        self,
        name: str,
        nullable: bool,
        max_length: int | None,
        python_type: type,
        sa_type: Any,
        has_default: bool = False,
        is_primary_key: bool = False,
        is_autoincrement: bool = False,
    ):
        self.name = name
        self.nullable = nullable
        self.max_length = max_length
        self.python_type = python_type
        self.sa_type = sa_type
        self.has_default = has_default
        self.is_primary_key = is_primary_key
        self.is_autoincrement = is_autoincrement


# =============================================================================
# Validation Decorator
# =============================================================================

def validate_schema(
    schema: type["BaseModel"],
    model: type,
    *,
    strict: bool = True,
    context: str = "",
):
    """
    Decorator to validate schema against model.
    
    Usage:
        @validate_schema(UserInput, User, context="create_user")
        async def create_user(data: UserInput) -> User:
            ...
    """
    def decorator(func):
        # Validate on decoration (import time)
        SchemaModelValidator.validate(
            schema,
            model,
            strict=strict,
            context=context or func.__name__,
        )
        return func
    return decorator


# =============================================================================
# Startup Validation
# =============================================================================

def validate_all_viewsets(
    viewsets: list[type],
    *,
    strict: bool | None = None,
    fail_fast: bool | None = None,
) -> list[str]:
    """
    Validate all registered viewsets.
    
    Called automatically during application startup.
    
    Args:
        viewsets: List of ViewSet classes to validate
        strict: Override strict mode (default: based on DEBUG setting)
        fail_fast: If True, raise on first error (default: DEBUG mode)
    
    Returns:
        List of all issues found
    
    Raises:
        SchemaModelMismatchError: If fail_fast and critical issues found
    """
    from core.config import get_settings
    
    settings = get_settings()
    
    if strict is None:
        strict = getattr(settings, "strict_validation", getattr(settings, "debug", True))
    
    if fail_fast is None:
        fail_fast = getattr(settings, "debug", True)
    
    logger.info(f"Validating {len(viewsets)} viewsets (strict={strict}, fail_fast={fail_fast})")
    
    all_issues: list[str] = []
    critical_errors: list[str] = []
    
    for viewset in viewsets:
        try:
            issues = SchemaModelValidator.validate_viewset(
                viewset,
                strict=strict,
            )
            all_issues.extend(issues)
        except SchemaModelMismatchError as e:
            critical_errors.append(str(e))
            if fail_fast:
                raise
    
    if critical_errors and not fail_fast:
        logger.error(
            f"Schema validation found {len(critical_errors)} critical errors:\n" +
            "\n".join(critical_errors)
        )
    
    if all_issues:
        logger.warning(f"Schema validation found {len(all_issues)} total issues")
    else:
        logger.info("Schema validation passed")
    
    return all_issues


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "SchemaModelValidator",
    "SchemaModelMismatchError",
    "ValidationWarning",
    "ColumnInfo",
    "validate_schema",
    "validate_all_viewsets",
]
