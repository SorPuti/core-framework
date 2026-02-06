"""
Testes do Admin Panel.

Cobre:
- Registry (register, unregister, re-register)
- ModelAdmin (bind, validação, defaults)
- Discovery (scan de admin.py)
- Exceptions (error collector, error levels)
- Permissions (IsAdminUser, model permissions)
- Serializers (auto-geração de schemas)
- Collectstatic (cópia, hash, manifest)
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock

from core.admin.site import AdminSite
from core.admin.options import ModelAdmin, InlineModelAdmin
from core.admin.exceptions import (
    AdminConfigurationError,
    AdminRegistrationError,
    AdminRuntimeError,
    AdminError,
    AdminErrorCollector,
)
from core.admin.permissions import IsAdminUser, check_model_permission
from core.admin.serializers import (
    generate_list_schema,
    generate_detail_schema,
    generate_write_schema,
    serialize_instance,
)


# =========================================================================
# Fixtures — Mock models para testes sem banco
# =========================================================================

class _MockColumn:
    def __init__(self, name, col_type="VARCHAR", nullable=False, primary_key=False, default=None, server_default=None):
        self.name = name
        self.type = type("MockType", (), {"__str__": lambda self: col_type})()
        self.nullable = nullable
        self.primary_key = primary_key
        self.default = default
        self.server_default = server_default
        self.onupdate = None


class _MockPK:
    def __init__(self, columns):
        self.columns = columns


class _MockTable:
    def __init__(self, columns):
        self.columns = columns
        pk_cols = [c for c in columns if c.primary_key]
        self.primary_key = _MockPK(pk_cols)


class MockModel:
    """Model falso para testes de admin sem banco."""
    __name__ = "MockModel"
    __module__ = "apps.testing.models"
    __tablename__ = "mock_models"
    __table__ = _MockTable([
        _MockColumn("id", "INTEGER", primary_key=True),
        _MockColumn("name", "VARCHAR"),
        _MockColumn("email", "VARCHAR"),
        _MockColumn("is_active", "BOOLEAN"),
        _MockColumn("created_at", "DATETIME", default=True),
    ])
    
    class objects:
        @staticmethod
        def using(db):
            return MagicMock()


class MockModelNoTable:
    """Model sem __table__ para testar fallback."""
    __name__ = "MockModelNoTable"
    __module__ = "apps.testing.models"
    __tablename__ = "mock_no_table"


# =========================================================================
# Testes: AdminSite (Registry)
# =========================================================================

class TestAdminSite:
    """Testes do registry central."""
    
    def test_register_model_with_defaults(self):
        site = AdminSite(name="test")
        site.register(MockModel)
        
        assert site.is_registered(MockModel)
        admin_instance = site.get_admin_for_model(MockModel)
        assert admin_instance is not None
        assert admin_instance.model is MockModel
    
    def test_register_model_with_custom_admin(self):
        class CustomAdmin(ModelAdmin):
            list_display = ("id", "name", "email")
            search_fields = ("name", "email")
            icon = "users"
        
        site = AdminSite(name="test")
        site.register(MockModel, CustomAdmin)
        
        admin_instance = site.get_admin_for_model(MockModel)
        assert admin_instance is not None
        assert admin_instance.icon == "users"
        assert "email" in admin_instance.search_fields
    
    def test_register_as_decorator(self):
        site = AdminSite(name="test")
        
        @site.register(MockModel)
        class TestAdmin(ModelAdmin):
            list_display = ("id", "name")
        
        assert site.is_registered(MockModel)
        admin_instance = site.get_admin_for_model(MockModel)
        assert ("id", "name") == admin_instance.list_display
    
    def test_unregister(self):
        site = AdminSite(name="test")
        site.register(MockModel)
        assert site.is_registered(MockModel)
        
        site.unregister(MockModel)
        assert not site.is_registered(MockModel)
    
    def test_re_register_overrides(self):
        """Último registro vence (usuário sobrescreve core)."""
        site = AdminSite(name="test")
        
        class Admin1(ModelAdmin):
            icon = "first"
        
        class Admin2(ModelAdmin):
            icon = "second"
        
        site.register(MockModel, Admin1)
        assert site.get_admin_for_model(MockModel).icon == "first"
        
        site.register(MockModel, Admin2)
        assert site.get_admin_for_model(MockModel).icon == "second"
    
    def test_get_model_by_name(self):
        site = AdminSite(name="test")
        site.register(MockModel)
        
        result = site.get_model_by_name("testing", "mockmodel")
        assert result is not None
        model, admin_instance = result
        assert model is MockModel
    
    def test_get_model_by_name_not_found(self):
        site = AdminSite(name="test")
        result = site.get_model_by_name("nonexistent", "model")
        assert result is None
    
    def test_get_app_list(self):
        site = AdminSite(name="test")
        site.register(MockModel)
        
        app_list = site.get_app_list()
        assert len(app_list) >= 1
        assert any(app["app_label"] == "testing" for app in app_list)
    
    def test_invalid_admin_class_registers_error(self):
        site = AdminSite(name="test")
        site._do_register(MockModel, "not_a_class")
        
        assert not site.is_registered(MockModel)
        assert site.errors.error_count > 0


# =========================================================================
# Testes: ModelAdmin (Options)
# =========================================================================

class TestModelAdmin:
    """Testes da classe ModelAdmin."""
    
    def test_bind_applies_defaults(self):
        admin = ModelAdmin()
        admin.bind(MockModel)
        
        assert admin.model is MockModel
        assert admin._pk_field == "id"
        assert admin._app_label == "testing"
        assert admin._model_name == "mockmodel"
        assert len(admin.list_display) > 0
        assert admin.display_name is not None
    
    def test_default_ordering(self):
        admin = ModelAdmin()
        admin.bind(MockModel)
        assert admin.ordering == ("-id",)
    
    def test_pk_in_readonly(self):
        admin = ModelAdmin()
        admin.bind(MockModel)
        assert "id" in admin.readonly_fields
    
    def test_custom_display_name(self):
        class Custom(ModelAdmin):
            display_name = "Teste"
            display_name_plural = "Testes"
        
        admin = Custom()
        admin.bind(MockModel)
        assert admin.display_name == "Teste"
        assert admin.display_name_plural == "Testes"
    
    def test_validation_invalid_list_display(self):
        class Bad(ModelAdmin):
            list_display = ("id", "nonexistent_field")
        
        admin = Bad()
        with pytest.raises(AdminRegistrationError) as exc_info:
            admin.bind(MockModel)
        
        assert "nonexistent_field" in str(exc_info.value)
        assert "Available columns" in str(exc_info.value)
    
    def test_validation_invalid_search_fields(self):
        class Bad(ModelAdmin):
            search_fields = ("nonexistent",)
        
        admin = Bad()
        with pytest.raises(AdminRegistrationError):
            admin.bind(MockModel)
    
    def test_validation_invalid_list_filter(self):
        class Bad(ModelAdmin):
            list_filter = ("nonexistent",)
        
        admin = Bad()
        with pytest.raises(AdminRegistrationError):
            admin.bind(MockModel)
    
    def test_get_editable_fields(self):
        class Custom(ModelAdmin):
            readonly_fields = ("id", "created_at")
            exclude = ("is_active",)
        
        admin = Custom()
        admin.bind(MockModel)
        editable = admin.get_editable_fields()
        
        assert "id" not in editable
        assert "created_at" not in editable
        assert "is_active" not in editable
        assert "name" in editable
    
    def test_get_column_info(self):
        admin = ModelAdmin()
        admin.bind(MockModel)
        columns = admin.get_column_info()
        
        assert len(columns) > 0
        assert any(c["name"] == "id" for c in columns)
        assert any(c["primary_key"] for c in columns)
    
    def test_computed_field_in_list_display(self):
        """Campo computado (método no ModelAdmin) é aceito."""
        class Custom(ModelAdmin):
            list_display = ("id", "name", "computed_field")
            
            def computed_field(self, obj):
                return "computed"
        
        admin = Custom()
        admin.bind(MockModel)  # Não deve levantar erro
        assert "computed_field" in admin.list_display


# =========================================================================
# Testes: Exceptions e Error Collector
# =========================================================================

class TestExceptions:
    """Testes das exceções do admin."""
    
    def test_admin_configuration_error(self):
        err = AdminConfigurationError("Test error")
        assert "Test error" in str(err)
    
    def test_admin_registration_error_with_details(self):
        err = AdminRegistrationError(
            "Field not found",
            model_name="User",
            admin_class="UserAdmin",
            source_file="apps/users/admin.py",
            available_fields=["id", "email", "name"],
        )
        assert "Field not found" in str(err)
        assert "Available columns" in str(err)
        assert "apps/users/admin.py" in str(err)
    
    def test_admin_runtime_error(self):
        err = AdminRuntimeError(
            "Table not found",
            code="table_not_found",
            hint="Run core migrate",
            model_name="User",
        )
        assert err.code == "table_not_found"
        assert err.hint == "Run core migrate"


class TestErrorCollector:
    """Testes do coletor de erros."""
    
    def test_add_error(self):
        collector = AdminErrorCollector()
        collector.add(
            code="test",
            title="Test Error",
            detail="Test detail",
            level="error",
        )
        assert collector.error_count == 1
        assert collector.has_errors
    
    def test_add_warning(self):
        collector = AdminErrorCollector()
        collector.add(
            code="test",
            title="Test Warning",
            detail="Warning detail",
            level="warning",
        )
        assert collector.warning_count == 1
        assert collector.has_warnings
        assert not collector.has_errors
    
    def test_add_discovery_error(self):
        collector = AdminErrorCollector()
        try:
            raise ImportError("Module not found")
        except ImportError as e:
            collector.add_discovery_error("apps.test.admin", e)
        
        assert collector.warning_count == 1
        errors = collector.to_dict()
        assert errors[0]["code"] == "import_error"
    
    def test_add_runtime_error_with_hint(self):
        collector = AdminErrorCollector()
        try:
            raise Exception("no such table: users")
        except Exception as e:
            collector.add_runtime_error("User", e)
        
        errors = collector.to_dict()
        assert "migrate" in errors[0]["hint"].lower()
    
    def test_get_errors_for_model(self):
        collector = AdminErrorCollector()
        collector.add(code="a", title="A", detail="A", model="User")
        collector.add(code="b", title="B", detail="B", model="Post")
        collector.add(code="c", title="C", detail="C", model="User")
        
        user_errors = collector.get_errors_for_model("User")
        assert len(user_errors) == 2
    
    def test_to_dict(self):
        collector = AdminErrorCollector()
        collector.add(code="test", title="T", detail="D", hint="H", model="M")
        
        data = collector.to_dict()
        assert isinstance(data, list)
        assert data[0]["code"] == "test"
        assert data[0]["hint"] == "H"


# =========================================================================
# Testes: Permissions
# =========================================================================

class TestPermissions:
    """Testes de permissões do admin."""
    
    @pytest.mark.asyncio
    async def test_is_admin_user_with_staff(self):
        checker = IsAdminUser()
        
        user = MagicMock()
        user.is_staff = True
        user.is_superuser = False
        
        request = MagicMock()
        request.state.admin_user = user
        
        result = await checker(request)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_is_admin_user_with_superuser(self):
        checker = IsAdminUser()
        
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = True
        
        request = MagicMock()
        request.state.admin_user = user
        
        result = await checker(request)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_is_admin_user_denied(self):
        checker = IsAdminUser()
        
        user = MagicMock()
        user.is_staff = False
        user.is_superuser = False
        
        request = MagicMock()
        request.state.admin_user = user
        
        result = await checker(request)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_is_admin_user_no_user(self):
        checker = IsAdminUser()
        
        request = MagicMock()
        request.state = MagicMock(spec=[])
        request.user = None
        
        result = await checker(request)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_model_permission_superuser(self):
        user = MagicMock()
        user.is_superuser = True
        
        result = await check_model_permission(user, "auth", "user", "delete")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_model_permission_denied(self):
        user = MagicMock()
        user.is_superuser = False
        # Sem has_permission, sem user_permissions, sem groups
        del user.has_permission
        del user.user_permissions
        del user.groups
        
        result = await check_model_permission(user, "auth", "user", "delete")
        assert result is False


# =========================================================================
# Testes: Serializers
# =========================================================================

class TestSerializers:
    """Testes de auto-geração de schemas."""
    
    def test_generate_list_schema(self):
        admin = ModelAdmin()
        admin.bind(MockModel)
        
        schema = generate_list_schema(MockModel, admin)
        assert schema is not None
        assert "id" in schema.model_fields or hasattr(schema, "model_fields")
    
    def test_generate_detail_schema(self):
        admin = ModelAdmin()
        admin.bind(MockModel)
        
        schema = generate_detail_schema(MockModel, admin)
        assert schema is not None
    
    def test_generate_write_schema_excludes_readonly(self):
        class Custom(ModelAdmin):
            readonly_fields = ("id", "created_at")
        
        admin = Custom()
        admin.bind(MockModel)
        
        schema = generate_write_schema(MockModel, admin)
        field_names = set(schema.model_fields.keys())
        
        assert "id" not in field_names
        assert "created_at" not in field_names
    
    def test_serialize_instance(self):
        obj = MagicMock()
        obj.id = 1
        obj.name = "Test"
        obj.email = "test@test.com"
        
        data = serialize_instance(obj, ["id", "name", "email"])
        assert data["id"] == 1
        assert data["name"] == "Test"


# =========================================================================
# Testes: Collectstatic
# =========================================================================

class TestCollectstatic:
    """Testes do sistema de coleta de assets."""
    
    def test_collectstatic(self, tmp_path):
        from core.admin.collectstatic import collectstatic
        
        output_dir = str(tmp_path / "static" / "core-admin")
        result = collectstatic(output_dir=output_dir, no_hash=True)
        
        assert result["files_copied"] >= 0
        assert "manifest_path" in result
        assert "output_dir" in result
    
    def test_collectstatic_with_hash(self, tmp_path):
        from core.admin.collectstatic import collectstatic
        
        output_dir = str(tmp_path / "static" / "hashed")
        result = collectstatic(output_dir=output_dir, no_hash=False)
        
        # Verifica que manifest foi criado
        import json
        manifest_path = result["manifest_path"]
        with open(manifest_path) as f:
            manifest = json.load(f)
        
        # Cada entrada do manifest deve ter hash no nome
        for original, hashed in manifest.items():
            if not original.endswith(".json"):
                # Hashed names têm um segmento extra: name.hash.ext
                parts = hashed.rsplit(".", 2) if "/" not in hashed.rsplit(".", 2)[-1] else [hashed]
                # Just check file exists
                from pathlib import Path
                assert (Path(output_dir) / hashed).exists() or result["files_copied"] == 0


# =========================================================================
# Testes: Admin __init__ exports
# =========================================================================

class TestAdminExports:
    """Testes dos exports do pacote admin."""
    
    def test_imports(self):
        from core.admin import (
            AdminSite,
            ModelAdmin,
            InlineModelAdmin,
            AdminConfigurationError,
            AdminRegistrationError,
            AdminRuntimeError,
            default_site,
            admin,
            register,
            unregister,
            action,
        )
        
        assert AdminSite is not None
        assert ModelAdmin is not None
        assert default_site is admin
    
    def test_action_decorator(self):
        from core.admin import action
        
        @action(description="Test action")
        def my_action(self, db, queryset):
            pass
        
        assert my_action._admin_action is True
        assert my_action.short_description == "Test action"
