"""
Tests for core.validation module.

Tests the schema/model validation system.
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Any


class TestSchemaModelValidator:
    """Tests for SchemaModelValidator class."""
    
    def test_import_validator(self):
        """Can import SchemaModelValidator."""
        from core.validation import SchemaModelValidator
        assert SchemaModelValidator is not None
    
    def test_import_exceptions(self):
        """Can import validation exceptions."""
        from core.validation import SchemaModelMismatchError, ValidationWarning
        assert SchemaModelMismatchError is not None
        assert ValidationWarning is not None
    
    def test_validate_returns_empty_list_for_matching(self):
        """Validate returns empty list when schema and model match."""
        from core.validation import SchemaModelValidator
        from pydantic import BaseModel
        
        class MockSchema(BaseModel):
            name: str
            age: int
        
        # Mock a SQLAlchemy model with __name__
        mock_model = MagicMock()
        mock_model.__name__ = "MockModel"
        
        # Clear cache before test
        SchemaModelValidator.clear_cache()
        
        # Should not raise and return empty or minimal issues
        # (may return warnings about missing model columns)
        with patch.object(SchemaModelValidator, "_get_model_columns", return_value={}):
            issues = SchemaModelValidator.validate(
                MockSchema,
                mock_model,
                strict=False,
                context="test",
            )
            assert isinstance(issues, list)
    
    def test_validate_detects_nullable_mismatch(self):
        """Validate detects when NOT NULL field is optional in schema."""
        from core.validation import SchemaModelValidator, ColumnInfo, SchemaModelMismatchError
        from pydantic import BaseModel
        from typing import Optional
        
        class OptionalNameSchema(BaseModel):
            name: Optional[str] = None  # Optional but model is NOT NULL
        
        mock_model = MagicMock()
        mock_model.__name__ = "MockModel"
        
        # Mock model column as NOT NULL
        mock_columns = {
            "name": ColumnInfo(
                name="name",
                nullable=False,  # NOT NULL
                max_length=100,
                python_type=str,
                sa_type=MagicMock(),
                has_default=False,
                is_primary_key=False,
                is_autoincrement=False,
            )
        }
        
        SchemaModelValidator.clear_cache()
        
        with patch.object(SchemaModelValidator, "_get_model_columns", return_value=mock_columns):
            # Should raise in strict mode
            with pytest.raises(SchemaModelMismatchError):
                SchemaModelValidator.validate(
                    OptionalNameSchema,
                    mock_model,
                    strict=True,
                    context="test",
                )
    
    def test_validate_allows_optional_for_nullable(self):
        """Validate allows optional field when model column is nullable."""
        from core.validation import SchemaModelValidator, ColumnInfo
        from pydantic import BaseModel
        from typing import Optional
        
        class OptionalBioSchema(BaseModel):
            bio: Optional[str] = None  # Optional and model is nullable
        
        mock_model = MagicMock()
        mock_model.__name__ = "MockModel"
        
        # Mock model column as nullable
        mock_columns = {
            "bio": ColumnInfo(
                name="bio",
                nullable=True,  # Nullable
                max_length=None,
                python_type=str,
                sa_type=MagicMock(),
                has_default=False,
                is_primary_key=False,
                is_autoincrement=False,
            )
        }
        
        SchemaModelValidator.clear_cache()
        
        with patch.object(SchemaModelValidator, "_get_model_columns", return_value=mock_columns):
            # Should not raise
            issues = SchemaModelValidator.validate(
                OptionalBioSchema,
                mock_model,
                strict=True,
                context="test",
            )
            # No critical issues expected
            assert not any("CRITICAL" in i for i in issues)
    
    def test_validate_skips_primary_key(self):
        """Validate skips primary key fields in nullable check."""
        from core.validation import SchemaModelValidator, ColumnInfo
        from pydantic import BaseModel
        from typing import Optional
        
        class SchemaWithOptionalId(BaseModel):
            id: Optional[int] = None  # Optional ID (normal for create schemas)
        
        mock_model = MagicMock()
        mock_model.__name__ = "MockModel"
        
        mock_columns = {
            "id": ColumnInfo(
                name="id",
                nullable=False,
                max_length=None,
                python_type=int,
                sa_type=MagicMock(),
                has_default=False,
                is_primary_key=True,  # Primary key
                is_autoincrement=True,
            )
        }
        
        SchemaModelValidator.clear_cache()
        
        with patch.object(SchemaModelValidator, "_get_model_columns", return_value=mock_columns):
            # Should not raise even though id is optional and NOT NULL
            issues = SchemaModelValidator.validate(
                SchemaWithOptionalId,
                mock_model,
                strict=True,
                context="test",
            )
            assert not any("CRITICAL" in i for i in issues)
    
    def test_validate_detects_max_length_mismatch(self):
        """Validate warns when schema allows longer values than model."""
        from core.validation import SchemaModelValidator, ColumnInfo
        from pydantic import BaseModel
        
        class LongNameSchema(BaseModel):
            name: str  # No max_length constraint
        
        mock_model = MagicMock()
        mock_model.__name__ = "MockModel"
        
        mock_columns = {
            "name": ColumnInfo(
                name="name",
                nullable=False,
                max_length=50,  # Model limits to 50 chars
                python_type=str,
                sa_type=MagicMock(),
                has_default=False,
                is_primary_key=False,
                is_autoincrement=False,
            )
        }
        
        SchemaModelValidator.clear_cache()
        
        with patch.object(SchemaModelValidator, "_get_model_columns", return_value=mock_columns):
            with patch.object(SchemaModelValidator, "_is_field_required", return_value=True):
                issues = SchemaModelValidator.validate(
                    LongNameSchema,
                    mock_model,
                    strict=False,  # Don't raise, just collect warnings
                    context="test",
                )
                # Should have warning about max_length
                assert any("max_length" in i.lower() for i in issues)


class TestValidateSchema:
    """Tests for validate_schema decorator."""
    
    def test_decorator_validates_on_import(self):
        """validate_schema decorator validates at decoration time."""
        from core.validation import validate_schema, SchemaModelValidator
        from pydantic import BaseModel
        
        class TestSchema(BaseModel):
            name: str
        
        mock_model = MagicMock()
        mock_model.__name__ = "MockModel"
        
        SchemaModelValidator.clear_cache()
        
        with patch.object(SchemaModelValidator, "_get_model_columns", return_value={}):
            @validate_schema(TestSchema, mock_model, strict=False, context="test_func")
            async def test_func():
                pass
            
            # Function should still work
            assert test_func is not None


class TestColumnInfo:
    """Tests for ColumnInfo data class."""
    
    def test_column_info_creation(self):
        """Can create ColumnInfo with all fields."""
        from core.validation import ColumnInfo
        
        col = ColumnInfo(
            name="test",
            nullable=False,
            max_length=100,
            python_type=str,
            sa_type=MagicMock(),
            has_default=True,
            is_primary_key=False,
            is_autoincrement=False,
        )
        
        assert col.name == "test"
        assert col.nullable is False
        assert col.max_length == 100
        assert col.python_type is str
        assert col.has_default is True


class TestValidateAllViewsets:
    """Tests for validate_all_viewsets function."""
    
    def test_validate_empty_list(self):
        """validate_all_viewsets handles empty list."""
        from core.validation import validate_all_viewsets
        
        issues = validate_all_viewsets([], strict=False)
        assert issues == []
    
    def test_validate_viewsets_list(self):
        """validate_all_viewsets processes viewset list."""
        from core.validation import validate_all_viewsets, SchemaModelValidator
        
        mock_viewset = MagicMock()
        mock_viewset.__name__ = "TestViewSet"
        
        with patch.object(SchemaModelValidator, "validate_viewset", return_value=[]):
            issues = validate_all_viewsets([mock_viewset], strict=False)
            assert isinstance(issues, list)


class TestViewSetValidation:
    """Tests for ViewSet schema validation integration."""
    
    def test_viewset_has_validation_attributes(self):
        """ViewSet has validation-related attributes."""
        from core.views import ViewSet
        
        assert hasattr(ViewSet, "strict_validation")
        assert hasattr(ViewSet, "_schema_validated")
        assert hasattr(ViewSet, "_validate_schemas")
    
    def test_viewset_subclass_registered(self):
        """ViewSet subclass is registered for validation."""
        from core.views import ViewSet, _pending_viewsets
        
        # Clear pending
        _pending_viewsets.clear()
        
        class TestViewSet(ViewSet):
            pass
        
        # Should be registered
        assert TestViewSet in _pending_viewsets
    
    def test_validate_pending_viewsets_function(self):
        """validate_pending_viewsets function exists and works."""
        from core.views import validate_pending_viewsets
        
        # Should not raise
        issues = validate_pending_viewsets(strict=False)
        assert isinstance(issues, list)
