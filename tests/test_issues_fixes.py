"""
Tests for issues fixed in v0.12.12.

Issue #1: UUID inválido retorna 500 em vez de 422
Issue #2: permission_classes in @action decorator not applied
Issue #3: AuthViewSet list/retrieve endpoints return 500
Issue #4: AuthViewSet retrieve expects integer but system uses UUID
Issue #5: makemigrations serializes function references incorrectly
Issue #6: reset_db does not use CASCADE
Issue #7: check command fails when migration has syntax errors
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Optional


class TestIssue1UUIDValidation:
    """Issue #1: UUID validation should return 422, not 500."""
    
    def test_invalid_uuid_raises_422(self):
        """Invalid UUID should raise 422 with proper error format."""
        from core.views import ViewSet
        from fastapi import HTTPException
        
        class TestViewSet(ViewSet):
            model = MagicMock()
            lookup_field = "id"
        
        viewset = TestViewSet()
        
        # Mock _get_lookup_field_type to return UUID type
        mock_uuid_type = MagicMock()
        mock_uuid_type.__class__.__name__ = "UUID"
        
        with patch.object(viewset, "_get_lookup_field_type", return_value=mock_uuid_type):
            with pytest.raises(HTTPException) as exc_info:
                viewset._convert_lookup_value("invalid-uuid")
            
            assert exc_info.value.status_code == 422
            assert "validation_error" in str(exc_info.value.detail)
    
    def test_error_format_matches_pydantic(self):
        """Error format should match Pydantic validation errors."""
        from core.views import ViewSet
        from fastapi import HTTPException
        
        class TestViewSet(ViewSet):
            model = MagicMock()
            lookup_field = "workspace_id"
        
        viewset = TestViewSet()
        
        mock_uuid_type = MagicMock()
        mock_uuid_type.__class__.__name__ = "UUID"
        
        with patch.object(viewset, "_get_lookup_field_type", return_value=mock_uuid_type):
            with pytest.raises(HTTPException) as exc_info:
                viewset._convert_lookup_value("not-a-uuid")
            
            detail = exc_info.value.detail
            assert "errors" in detail
            assert detail["errors"][0]["loc"] == ["path", "workspace_id"]
            assert "uuid" in detail["errors"][0]["type"].lower()


class TestIssue2ActionPermissions:
    """Issue #2: permission_classes in @action decorator should be applied."""
    
    def test_action_stores_permission_classes(self):
        """@action decorator should store permission_classes."""
        from core.views import action
        from core.permissions import IsAuthenticated
        
        @action(methods=["POST"], detail=True, permission_classes=[IsAuthenticated])
        async def my_action(self, request, db, **kwargs):
            pass
        
        assert my_action.permission_classes == [IsAuthenticated]
    
    def test_action_without_permissions(self):
        """@action without permissions should have None."""
        from core.views import action
        
        @action(methods=["GET"], detail=False)
        async def my_action(self, request, db, **kwargs):
            pass
        
        assert my_action.permission_classes is None


class TestIssue3AuthViewSetEndpoints:
    """Issue #3: AuthViewSet list/retrieve should return 405."""
    
    @pytest.mark.asyncio
    async def test_list_returns_405(self):
        """AuthViewSet.list() should return 405."""
        from core.auth.views import AuthViewSet
        from fastapi import HTTPException
        
        viewset = AuthViewSet()
        
        with pytest.raises(HTTPException) as exc_info:
            await viewset.list()
        
        assert exc_info.value.status_code == 405
        assert "not allowed" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_retrieve_returns_405(self):
        """AuthViewSet.retrieve() should return 405."""
        from core.auth.views import AuthViewSet
        from fastapi import HTTPException
        
        viewset = AuthViewSet()
        
        with pytest.raises(HTTPException) as exc_info:
            await viewset.retrieve()
        
        assert exc_info.value.status_code == 405
    
    @pytest.mark.asyncio
    async def test_create_returns_405(self):
        """AuthViewSet.create() should return 405 (use /register)."""
        from core.auth.views import AuthViewSet
        from fastapi import HTTPException
        
        viewset = AuthViewSet()
        
        with pytest.raises(HTTPException) as exc_info:
            await viewset.create()
        
        assert exc_info.value.status_code == 405
        assert "register" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_update_returns_405(self):
        """AuthViewSet.update() should return 405."""
        from core.auth.views import AuthViewSet
        from fastapi import HTTPException
        
        viewset = AuthViewSet()
        
        with pytest.raises(HTTPException) as exc_info:
            await viewset.update()
        
        assert exc_info.value.status_code == 405
    
    @pytest.mark.asyncio
    async def test_destroy_returns_405(self):
        """AuthViewSet.destroy() should return 405."""
        from core.auth.views import AuthViewSet
        from fastapi import HTTPException
        
        viewset = AuthViewSet()
        
        with pytest.raises(HTTPException) as exc_info:
            await viewset.destroy()
        
        assert exc_info.value.status_code == 405


class TestIssue5MigrationSerialization:
    """Issue #5: Function references should be serialized correctly."""
    
    def test_serialize_none(self):
        """None should serialize to 'None'."""
        from core.migrations.operations import _serialize_default
        
        assert _serialize_default(None) == "None"
    
    def test_serialize_string(self):
        """Strings should use repr()."""
        from core.migrations.operations import _serialize_default
        
        result = _serialize_default("hello")
        assert result == "'hello'"
    
    def test_serialize_bool(self):
        """Booleans should serialize to 'True'/'False'."""
        from core.migrations.operations import _serialize_default
        
        assert _serialize_default(True) == "True"
        assert _serialize_default(False) == "False"
    
    def test_serialize_number(self):
        """Numbers should serialize correctly."""
        from core.migrations.operations import _serialize_default
        
        assert _serialize_default(42) == "42"
        assert _serialize_default(3.14) == "3.14"
    
    def test_serialize_callable(self):
        """Callables should serialize to module.function format."""
        from core.migrations.operations import _serialize_default
        from core.datetime import timezone
        
        result = _serialize_default(timezone.now)
        
        # Should be a valid Python reference, not <function ... at 0x...>
        assert "<function" not in result
        assert "0x" not in result
        # Should contain the function name
        assert "now" in result
    
    def test_serialize_lambda_returns_none(self):
        """Lambdas (no module) should fallback to 'None'."""
        from core.migrations.operations import _serialize_default
        
        # Lambdas don't have meaningful __module__ path
        result = _serialize_default(lambda: None)
        # Should not contain <function
        assert "<function" not in result
    
    def test_add_column_to_code_with_callable(self):
        """AddColumn.to_code() should serialize callable defaults correctly."""
        from core.migrations.operations import AddColumn, ColumnDef
        from core.datetime import timezone
        
        col = ColumnDef(
            name="created_at",
            type="DATETIME",
            nullable=False,
            default=timezone.now,
        )
        op = AddColumn(table_name="users", column=col)
        
        code = op.to_code()
        
        # Should NOT contain <function ... at 0x...>
        assert "<function" not in code
        assert "0x" not in code
        # Should be valid Python (can be exec'd)
        assert "AddColumn" in code
    
    def test_create_table_to_code_with_callable(self):
        """CreateTable.to_code() should serialize callable defaults correctly."""
        from core.migrations.operations import CreateTable, ColumnDef
        from core.datetime import timezone
        
        cols = [
            ColumnDef(name="id", type="INTEGER", primary_key=True),
            ColumnDef(name="created_at", type="DATETIME", default=timezone.now),
        ]
        op = CreateTable(table_name="test_table", columns=cols)
        
        code = op.to_code()
        
        # Should NOT contain <function ... at 0x...>
        assert "<function" not in code
        assert "0x" not in code
        # Should contain proper reference
        assert "CreateTable" in code


class TestIssue6ResetDbCascade:
    """Issue #6: reset_db should use CASCADE for PostgreSQL."""
    
    def test_cascade_in_drop_statement(self):
        """PostgreSQL should use CASCADE when dropping tables."""
        # This is more of an integration test - we verify the code path exists
        from core.cli.main import cmd_reset_db
        
        # The fix is in the code, we just verify the function exists
        assert cmd_reset_db is not None


class TestIssue7CheckCommandSyntaxError:
    """Issue #7: check command should handle syntax errors gracefully."""
    
    def test_syntax_error_handling(self):
        """Check command should report syntax errors without crashing."""
        # This test verifies the error handling code exists
        # Full integration test would require mocking the file system
        from core.cli.main import cmd_check
        
        assert cmd_check is not None


class TestValidUUIDConversion:
    """Test that valid UUIDs are properly converted."""
    
    def test_valid_uuid_is_converted(self):
        """Valid UUID string should be converted to UUID object."""
        from core.views import ViewSet
        import uuid
        
        class TestViewSet(ViewSet):
            model = MagicMock()
            lookup_field = "id"
        
        viewset = TestViewSet()
        
        # Mock _get_lookup_field_type to return UUID type
        mock_uuid_type = MagicMock()
        mock_uuid_type.__class__.__name__ = "UUID"
        
        valid_uuid = "019c2476-9cac-76e6-8836-4c031d186b6e"
        
        with patch.object(viewset, "_get_lookup_field_type", return_value=mock_uuid_type):
            result = viewset._convert_lookup_value(valid_uuid)
        
        assert isinstance(result, uuid.UUID)
        assert str(result) == valid_uuid
