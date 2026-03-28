"""
Testes para o sistema de relacionamentos (Rel).

Inclui inferência de tipo em Rel.foreign_key e utilitários de cache.
"""

import pytest
from unittest.mock import patch, MagicMock

from sqlalchemy.orm import Mapped

from strider.relations import (
    _infer_fk_type_kind,
    clear_model_cache,
    Rel,
)
import strider.relations as relations_mod


class TestClearModelCache:
    """Testes para clear_model_cache()."""
    
    def test_clears_cache(self):
        """Limpa o cache de importação de models (_model_import_cache)."""
        relations_mod._model_import_cache["__test__"] = True
        clear_model_cache()
        assert relations_mod._model_import_cache == {}


class TestForeignKeyTypeInference:
    """Inferência automática de int vs uuid em Rel.foreign_key pelo modelo referenciado."""

    def test_infer_kind_uuid_when_referenced_pk_is_uuid(self):
        from sqlalchemy.orm import configure_mappers
        from sqlalchemy import inspect as sa_inspect
        from sqlalchemy.dialects.postgresql import UUID as PgUUID
        from uuid import UUID

        from strider.models import Model, Field
        from strider.fields import AdvancedField

        class FkInferUuidAuthor(Model):
            __tablename__ = "fk_infer_uuid_author"
            id: Mapped[UUID] = AdvancedField.uuid_pk()

        class FkInferUuidPost(Model):
            __tablename__ = "fk_infer_uuid_post"
            id: Mapped[int] = Field.pk()
            author_id: Mapped[UUID] = Rel.foreign_key("fk_infer_uuid_author.id")

        assert _infer_fk_type_kind("fk_infer_uuid_author.id") == "uuid"
        configure_mappers()
        col = sa_inspect(FkInferUuidPost).columns["author_id"]
        assert isinstance(col.type, PgUUID)

    def test_infer_kind_int_when_referenced_pk_is_int(self):
        from strider.models import Model, Field

        class FkInferIntAuthor(Model):
            __tablename__ = "fk_infer_int_author"
            id: Mapped[int] = Field.pk()

        assert _infer_fk_type_kind("fk_infer_int_author.id") == "int"

    def test_explicit_type_overrides_inference(self):
        from sqlalchemy.orm import configure_mappers
        from sqlalchemy import Integer, inspect as sa_inspect
        from uuid import UUID

        from strider.models import Model, Field
        from strider.fields import AdvancedField

        class FkOverrideUuidAuthor(Model):
            __tablename__ = "fk_infer_override_author"
            id: Mapped[UUID] = AdvancedField.uuid_pk()

        class FkOverridePost(Model):
            __tablename__ = "fk_infer_override_post"
            id: Mapped[int] = Field.pk()
            author_id: Mapped[int] = Rel.foreign_key(
                "fk_infer_override_author.id",
                type_="int",
            )

        configure_mappers()
        col = sa_inspect(FkOverridePost).columns["author_id"]
        assert isinstance(col.type, Integer)


class TestPreloadModelsModule:
    """Testes para _preload_models_module() em core/config.py."""
    
    def test_preload_called_before_user_model(self):
        """
        Verifica que models_module é importado antes de resolver user_model.
        
        Isso é crucial para resolver dependências circulares.
        """
        from strider.config import _preload_models_module
        
        # Mock settings com models_module
        mock_settings = MagicMock()
        mock_settings.models_module = "src.apps.models"
        
        with patch("strider.config.import_module") as mock_import:
            _preload_models_module(mock_settings)
            mock_import.assert_called_once_with("src.apps.models")
    
    def test_preload_handles_missing_module(self):
        """Não falha se models_module não existe."""
        from strider.config import _preload_models_module

        mock_settings = MagicMock()
        mock_settings.models_module = "nonexistent.module"

        with patch("strider.config._models_loaded", False), patch("strider.config.import_module") as mock_import:
            mock_import.side_effect = ImportError("No module")

            # Não deve levantar exceção
            _preload_models_module(mock_settings)

    def test_preload_handles_list_of_modules(self):
        """Suporta lista de módulos."""
        from strider.config import _preload_models_module

        mock_settings = MagicMock()
        mock_settings.models_module = [
            "src.apps.users.models",
            "src.apps.workspaces.models",
        ]

        with patch("strider.config._models_loaded", False), patch("strider.config.import_module") as mock_import:
            _preload_models_module(mock_settings)

            assert mock_import.call_count == 2
            mock_import.assert_any_call("src.apps.users.models")
            mock_import.assert_any_call("src.apps.workspaces.models")
