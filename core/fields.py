"""
Advanced field types for SQLAlchemy models.

Provides UUID7, JSON, FileField, and optimized field definitions.
"""

from __future__ import annotations

import time
import uuid as uuid_module
from datetime import datetime, timedelta
from typing import Any, TYPE_CHECKING, Generic, TypeVar, overload
from uuid import UUID

from sqlalchemy import Uuid, String, Text, TypeDecorator, JSON
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy.dialects.postgresql import JSONB

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect

T = TypeVar("T")


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
# File Field - Django-style file handling
# =============================================================================

class FieldFile:
    """
    Representa um arquivo armazenado em um FileField.
    
    Similar ao Django FieldFile, fornece acesso ao arquivo e suas operações.
    
    Attributes:
        name: Path relativo do arquivo (ex: "uploads/foto.jpg")
        url: URL de acesso (signed URL para bucket privado)
    
    Example:
        course.cover.name  # "uploads/cover.jpg"
        course.cover.url   # "https://...?X-Goog-Signature=..."
        course.cover.save("novo.jpg", content)
        course.cover.delete()
    """
    
    def __init__(
        self, 
        name: str | None, 
        field: "FileFieldDescriptor",
        instance: Any,
    ):
        self._name = name or ""
        self._field = field
        self._instance = instance
    
    @property
    def name(self) -> str:
        """Path relativo do arquivo."""
        return self._name
    
    @property
    def path(self) -> str:
        """Alias para name - path relativo do arquivo."""
        return self._name
    
    @property
    def url(self) -> str:
        """
        URL de acesso ao arquivo.
        
        Para buckets privados, retorna signed URL com expiração configurada.
        Para buckets públicos ou local, retorna URL direta.
        """
        if not self._name:
            return ""
        from core.storage import get_file_url
        return get_file_url(self._name, self._field.url_expiration)
    
    def save(self, filename: str, content: bytes, content_type: str | None = None) -> str:
        """
        Salva um novo arquivo no storage.
        
        Args:
            filename: Nome do arquivo (será combinado com upload_to)
            content: Conteúdo binário do arquivo
            content_type: MIME type (opcional)
        
        Returns:
            Path relativo do arquivo salvo
        
        Example:
            course.cover.save("foto.jpg", image_bytes, "image/jpeg")
        """
        from core.storage import save_file
        import uuid as uuid_mod
        
        # Gera path baseado em upload_to
        upload_to = self._field.upload_to
        if callable(upload_to):
            relative_path = upload_to(self._instance, filename)
        else:
            # Adiciona timestamp/uuid para evitar colisões
            ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
            unique_name = f"{uuid_mod.uuid4().hex[:12]}.{ext}" if ext else uuid_mod.uuid4().hex[:12]
            relative_path = f"{upload_to.rstrip('/')}/{unique_name}"
        
        # Salva no storage
        saved_path = save_file(relative_path, content, content_type)
        
        # Atualiza o valor no model
        self._name = saved_path
        setattr(self._instance, self._field.db_column, saved_path)
        
        return saved_path
    
    def delete(self, save_model: bool = False) -> bool:
        """
        Remove o arquivo do storage.
        
        Args:
            save_model: Se True, limpa o campo no model também
        
        Returns:
            True se removeu com sucesso
        """
        if not self._name:
            return True
        
        from core.storage import delete_file
        result = delete_file(self._name)
        
        if save_model:
            self._name = ""
            setattr(self._instance, self._field.db_column, "")
        
        return result
    
    def exists(self) -> bool:
        """Verifica se o arquivo existe no storage."""
        if not self._name:
            return False
        from core.storage import file_exists
        return file_exists(self._name)
    
    def __bool__(self) -> bool:
        """Retorna True se tem arquivo."""
        return bool(self._name)
    
    def __str__(self) -> str:
        """Retorna o path do arquivo."""
        return self._name
    
    def __repr__(self) -> str:
        return f"FieldFile({self._name!r})"
    
    def __eq__(self, other: Any) -> bool:
        if isinstance(other, FieldFile):
            return self._name == other._name
        if isinstance(other, str):
            return self._name == other
        return False


class FileFieldDescriptor:
    """
    Descriptor que implementa o comportamento do FileField.
    
    Intercepta get/set no atributo para retornar FieldFile ao invés de string.
    """
    
    def __init__(
        self,
        db_column: str,
        upload_to: str | callable = "uploads/",
        url_expiration: int | timedelta | None = None,
    ):
        self.db_column = db_column
        self.upload_to = upload_to
        self.url_expiration = url_expiration
        self.attr_name = None  # Será definido pelo __set_name__
    
    def __set_name__(self, owner: type, name: str) -> None:
        self.attr_name = name
    
    def __get__(self, instance: Any, owner: type) -> "FieldFile | FileFieldDescriptor":
        if instance is None:
            return self
        
        # Obtém o valor bruto do campo de banco de dados
        raw_value = getattr(instance, self.db_column, None)
        return FieldFile(raw_value, self, instance)
    
    def __set__(self, instance: Any, value: Any) -> None:
        # Aceita string (path), FieldFile, ou None
        if isinstance(value, FieldFile):
            path = value.name
        elif isinstance(value, str):
            path = value
        elif value is None:
            path = ""
        else:
            raise TypeError(f"FileField aceita str, FieldFile ou None, não {type(value)}")
        
        setattr(instance, self.db_column, path)


def FileField(
    upload_to: str | callable = "uploads/",
    url_expiration: int | timedelta | None = None,
) -> FileFieldDescriptor:
    """
    Cria um campo de arquivo no model - estilo Django FileField.
    
    O campo armazena apenas o path relativo no banco de dados, mas fornece
    uma interface rica para manipulação de arquivos com URLs assinadas.
    
    Args:
        upload_to: Diretório base para uploads ou função que retorna o path.
                  Função recebe (instance, filename) e retorna path completo.
        url_expiration: Tempo de expiração da signed URL (segundos ou timedelta).
                       None usa o padrão do settings.
    
    Returns:
        Descriptor que retorna FieldFile quando acessado.
    
    Example:
        class Course(Model):
            __tablename__ = "courses"
            
            id: Mapped[int] = Field.pk()
            name: Mapped[str] = Field.string(255)
            
            # Campo de banco que armazena o path
            cover_image_path: Mapped[str | None] = Field.string(500, nullable=True)
            
            # FileField que fornece interface rica
            cover = FileField(upload_to="courses/covers/")
        
        # Uso:
        course.cover.name     # "courses/covers/abc123.jpg"
        course.cover.url      # "https://...?X-Goog-Signature=..."
        course.cover.save("foto.jpg", content, "image/jpeg")
        course.cover.delete()
        
        # Com função upload_to personalizada:
        def course_cover_path(instance, filename):
            return f"courses/{instance.id}/cover/{filename}"
        
        cover = FileField(upload_to=course_cover_path)
    
    Note:
        O FileField é um descriptor Python que deve ser definido como atributo
        de classe. Ele referencia um campo de banco de dados (string) que
        armazena o path. Por convenção, use sufixo _path no campo de banco.
    """
    # Placeholder - o db_column será definido depois
    # O usuário deve chamar .bind() ou usar a versão integrada
    return FileFieldDescriptor(
        db_column="",  # Será inferido ou definido
        upload_to=upload_to,
        url_expiration=url_expiration,
    )


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

    @staticmethod
    def file(
        db_column: str,
        upload_to: str | callable = "uploads/",
        url_expiration: int | timedelta | None = None,
    ) -> FileFieldDescriptor:
        """
        Create a file field with Django-style interface.
        
        The field automatically handles:
        - Saving files to storage (local or GCS)
        - Generating signed URLs for private buckets
        - File deletion
        
        Args:
            db_column: Nome da coluna do banco que armazena o path (string).
                      Esta coluna deve ser definida separadamente com Field.string().
            upload_to: Diretório base para uploads ou função(instance, filename) -> path.
            url_expiration: Tempo de expiração da signed URL (segundos ou timedelta).
        
        Returns:
            FileFieldDescriptor que fornece interface FieldFile.
        
        Example:
            class Course(Model):
                __tablename__ = "courses"
                
                id: Mapped[int] = Field.pk()
                name: Mapped[str] = Field.string(255)
                
                # Coluna do banco (string que armazena o path)
                cover_path: Mapped[str | None] = Field.string(500, nullable=True)
                
                # FileField - interface rica para o arquivo
                cover = AdvancedField.file("cover_path", upload_to="courses/covers/")
            
            # Uso:
            course.cover.name   # "courses/covers/abc123.jpg"
            course.cover.url    # "https://...?X-Goog-Signature=..." (signed URL)
            course.cover.save("foto.jpg", content, "image/jpeg")  # Upload
            course.cover.delete()  # Remove do storage
            bool(course.cover)  # True se tem arquivo
            
            # Com função upload_to personalizada:
            def dynamic_path(instance, filename):
                return f"courses/{instance.id}/{filename}"
            
            cover = AdvancedField.file("cover_path", upload_to=dynamic_path)
        """
        return FileFieldDescriptor(
            db_column=db_column,
            upload_to=upload_to,
            url_expiration=url_expiration,
        )


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "uuid7",
    "uuid7_str",
    "AdaptiveJSON",
    "AdvancedField",
    "FileField",
    "FieldFile",
    "FileFieldDescriptor",
]
