"""
Advanced field types for SQLAlchemy models.

Provides UUID7, JSON, and optimized field definitions.
"""

from __future__ import annotations

import time
import uuid as uuid_module
from typing import Any, TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Uuid, String, Text, TypeDecorator, JSON
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy.dialects.postgresql import JSONB

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect


# =============================================================================
# Adaptive JSON Type
# =============================================================================

class AdaptiveJSON(TypeDecorator):
    """
    JSON type that automatically uses JSONB on PostgreSQL and JSON on others.
    
    This allows models to be written once and work across all databases:
    - PostgreSQL: Uses JSONB (supports indexing, GIN indexes, better performance)
    - SQLite: Uses standard JSON
    - MySQL: Uses standard JSON
    - Others: Uses standard JSON
    
    Example:
        class Settings(Model):
            data: Mapped[dict] = AdvancedField.json_field(default={})
        
        # Works on SQLite (dev), PostgreSQL (prod), MySQL, etc.
    """
    impl = JSON
    cache_ok = True
    
    def load_dialect_impl(self, dialect: "Dialect"):
        """Select the appropriate type based on database dialect."""
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


# =============================================================================
# UUID7 Implementation
# =============================================================================

def uuid7() -> UUID:
    """
    Generate a time-sortable UUID version 7.

    Superior to UUID4 for primary keys due to B-tree index optimization.
    """
    timestamp_ms = int(time.time() * 1000)
    random_bits = uuid_module.uuid4().int

    uuid_int = (timestamp_ms & 0xFFFFFFFFFFFF) << 80
    uuid_int |= (random_bits & ((1 << 80) - 1))
    uuid_int = (uuid_int & ~(0xF << 76)) | (0x7 << 76)
    uuid_int = (uuid_int & ~(0x3 << 62)) | (0x2 << 62)

    return UUID(int=uuid_int)


def uuid7_str() -> str:
    """
    Generate UUID7 as string.

    Convenience wrapper for string contexts.
    """
    return str(uuid7())


def get_default_uuid() -> UUID:
    """
    Return UUID using version from settings.

    Checks settings.uuid_version to select uuid4 or uuid7.
    """
    try:
        from core.config import get_settings
        settings = get_settings()
        if settings.uuid_version == "uuid4":
            return uuid_module.uuid4()
        return uuid7()
    except Exception:
        return uuid7()


# =============================================================================
# Advanced Field Class
# =============================================================================

class AdvancedField:
    """
    Namespace for enterprise-grade field types.

    Extends base Field with UUID7, JSON, and optimized definitions.
    """

    @staticmethod
    def uuid_pk(use_settings: bool = True) -> Mapped[UUID]:
        """
        Create UUID primary key column.

        Uses settings.uuid_version by default (uuid7 recommended).
        """
        # id: Mapped[UUID] = AdvancedField.uuid_pk()
        default_func = get_default_uuid if use_settings else uuid7

        return mapped_column(
            Uuid(as_uuid=True),
            primary_key=True,
            default=default_func,
            nullable=False,
        )

    @staticmethod
    def uuid(
        *,
        nullable: bool = False,
        default: UUID | None = None,
        unique: bool = False,
        index: bool = False,
        use_uuid7: bool = True,
    ) -> Mapped[UUID]:
        """
        Create UUID column with configurable version.

        Defaults to UUID7 for time-sortable identifiers.
        """
        # external_id: Mapped[UUID] = AdvancedField.uuid(unique=True)
        actual_default = default
        if actual_default is None and not nullable:
            actual_default = uuid7 if use_uuid7 else uuid_module.uuid4

        return mapped_column(
            Uuid(as_uuid=True),
            nullable=nullable,
            default=actual_default,
            unique=unique,
            index=index,
        )

    @staticmethod
    def uuid4(
        *,
        nullable: bool = False,
        default: UUID | None = None,
        unique: bool = False,
        index: bool = False,
    ) -> Mapped[UUID]:
        """
        Create random UUID4 column.

        Use when temporal ordering is not required.
        """
        # token: Mapped[UUID] = AdvancedField.uuid4(unique=True)
        actual_default = default
        if actual_default is None and not nullable:
            actual_default = uuid_module.uuid4

        return mapped_column(
            Uuid(as_uuid=True),
            nullable=nullable,
            default=actual_default,
            unique=unique,
            index=index,
        )

    @staticmethod
    def json_field(
        *,
        nullable: bool = False,
        default: dict | list | None = None,
    ) -> Mapped[dict | list]:
        """
        Create JSON column with automatic dialect detection.
        
        Automatically selects the best JSON type for each database:
        - PostgreSQL: Uses JSONB (supports indexing, GIN indexes, better performance)
        - SQLite: Uses standard JSON
        - MySQL: Uses standard JSON
        - Others: Uses standard JSON
        
        The model is written once and works on any database without changes.
        
        Args:
            nullable: Whether the field can be NULL (default: False)
            default: Default value - dict or list (default: {} for non-nullable)
        
        Example:
            class UserSettings(Model):
                preferences: Mapped[dict] = AdvancedField.json_field(default={})
                tags: Mapped[list] = AdvancedField.json_field(default=[])
            
            # Works on SQLite (dev/tests), PostgreSQL (production), etc.
        """
        # settings: Mapped[dict] = AdvancedField.json_field(default={})

        def default_factory():
            if default is None:
                return {} if not nullable else None
            return default.copy() if isinstance(default, (dict, list)) else default

        return mapped_column(
            AdaptiveJSON,
            nullable=nullable,
            default=default_factory,
        )

    @staticmethod
    def long_text(
        *,
        nullable: bool = False,
        default: str | None = None,
    ) -> Mapped[str]:
        """
        Create unlimited text column.

        Optimized for articles, logs, and large content.
        """
        # content: Mapped[str] = AdvancedField.long_text()
        return mapped_column(
            Text,
            nullable=nullable,
            default=default,
        )

    @staticmethod
    def slug(
        *,
        max_length: int = 255,
        nullable: bool = False,
        unique: bool = True,
        index: bool = True,
    ) -> Mapped[str]:
        """
        Create URL-friendly slug column.
        
        A slug is a short label for something, containing only letters,
        numbers, underscores or hyphens. They are generally used in URLs.
        
        Note: This field does NOT auto-generate slugs from other fields.
        You must generate the slug value yourself (e.g., using python-slugify).
        
        Args:
            max_length: Maximum length of the slug (default: 255)
            nullable: Whether the field can be NULL (default: False)
            unique: Whether values must be unique (default: True)
            index: Whether to create a database index (default: True)
        
        Example:
            from slugify import slugify
            
            class Post(Model):
                __tablename__ = "posts"
                
                id: Mapped[int] = Field.pk()
                title: Mapped[str] = Field.string(max_length=200)
                slug: Mapped[str] = AdvancedField.slug()
                
                async def before_save(self):
                    if not self.slug:
                        self.slug = slugify(self.title)
        """
        # slug: Mapped[str] = AdvancedField.slug()
        return mapped_column(
            String(max_length),
            nullable=nullable,
            unique=unique,
            index=index,
        )

    @staticmethod
    def email(
        *,
        max_length: int = 255,
        nullable: bool = False,
        unique: bool = True,
        index: bool = True,
    ) -> Mapped[str]:
        """
        Create email column with unique constraint.

        Format validation should be done in Pydantic schema.
        """
        # email: Mapped[str] = AdvancedField.email()
        return mapped_column(
            String(max_length),
            nullable=nullable,
            unique=unique,
            index=index,
        )


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "uuid7",
    "uuid7_str",
    "AdaptiveJSON",
    "AdvancedField",
]
