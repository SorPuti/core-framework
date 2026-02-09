"""
Testes para o sistema de relacionamentos (Rel).

Testa:
- _resolve_target() com diferentes formatos de target
- Sintaxe app.Model para lazy loading
- Resolução de "User" via get_user_model()
- Relacionamentos complexos User <-> Other Models
"""

import pytest
import sys
from unittest.mock import patch, MagicMock

from core.relations import _resolve_target, _resolve_app_model, Rel


class TestResolveTarget:
    """Testes para _resolve_target()."""
    
    def test_fully_qualified_path_multiple_dots(self):
        """Paths com múltiplos pontos são usados diretamente."""
        result = _resolve_target("src.apps.workspaces.models.Workspace")
        assert result == "src.apps.workspaces.models.Workspace"
    
    def test_fully_qualified_path_three_dots(self):
        """Paths com 3+ pontos são considerados fully-qualified."""
        result = _resolve_target("myapp.models.users.User")
        assert result == "myapp.models.users.User"
    
    def test_app_model_syntax_expands_to_full_path(self):
        """Sintaxe app.Model expande para path completo."""
        result = _resolve_target("workspaces.Workspace")
        # Deve expandir para convenção padrão
        assert result == "src.apps.workspaces.models.Workspace"
    
    def test_app_model_syntax_users(self):
        """Sintaxe app.Model funciona para users."""
        result = _resolve_target("users.Profile")
        assert result == "src.apps.users.models.Profile"
    
    def test_simple_name_passed_through(self):
        """Nomes simples são passados para SQLAlchemy resolver."""
        result = _resolve_target("Comment")
        assert result == "Comment"
    
    def test_simple_name_post(self):
        """Outro nome simples."""
        result = _resolve_target("Post")
        assert result == "Post"
    
    def test_user_special_case_without_auth_raises(self):
        """'User' sem auth configurado levanta ValueError."""
        with patch("core.relations.get_user_model") as mock:
            mock.side_effect = RuntimeError("No user_model configured")
            
            with pytest.raises(ValueError) as exc_info:
                _resolve_target("User")
            
            assert "Cannot resolve ambiguous target 'User'" in str(exc_info.value)
    
    def test_user_special_case_with_auth_resolves(self):
        """'User' com auth configurado resolve para path completo."""
        mock_user = MagicMock()
        mock_user.__module__ = "src.apps.users.models"
        mock_user.__name__ = "User"
        
        with patch("core.relations.get_user_model", return_value=mock_user):
            result = _resolve_target("User")
            assert result == "src.apps.users.models.User"


class TestResolveAppModel:
    """Testes para _resolve_app_model()."""
    
    def test_returns_default_convention(self):
        """Retorna convenção padrão src.apps.{app}.models.{Model}."""
        result = _resolve_app_model("posts", "Post")
        assert result == "src.apps.posts.models.Post"
    
    def test_uses_loaded_module_if_available(self):
        """Usa módulo já carregado se disponível."""
        # Simula módulo carregado
        mock_module = MagicMock()
        mock_module.Workspace = MagicMock()
        
        with patch.dict(sys.modules, {"src.apps.workspaces.models": mock_module}):
            result = _resolve_app_model("workspaces", "Workspace")
            assert result == "src.apps.workspaces.models.Workspace"
    
    def test_different_app_names(self):
        """Funciona com diferentes nomes de app."""
        assert _resolve_app_model("users", "Profile") == "src.apps.users.models.Profile"
        assert _resolve_app_model("orders", "Order") == "src.apps.orders.models.Order"
        assert _resolve_app_model("products", "Product") == "src.apps.products.models.Product"


class TestRelMethods:
    """Testes para métodos da classe Rel."""
    
    def test_many_to_one_with_app_model_syntax(self):
        """many_to_one aceita sintaxe app.Model."""
        with patch("core.relations.relationship") as mock_rel:
            mock_rel.return_value = MagicMock()
            
            Rel.many_to_one("workspaces.Workspace", back_populates="users")
            
            # Verifica que foi chamado com path expandido
            mock_rel.assert_called_once()
            args, kwargs = mock_rel.call_args
            assert args[0] == "src.apps.workspaces.models.Workspace"
            assert kwargs["back_populates"] == "users"
    
    def test_one_to_many_with_app_model_syntax(self):
        """one_to_many aceita sintaxe app.Model."""
        with patch("core.relations.relationship") as mock_rel:
            mock_rel.return_value = MagicMock()
            
            Rel.one_to_many("posts.Post", back_populates="author")
            
            mock_rel.assert_called_once()
            args, kwargs = mock_rel.call_args
            assert args[0] == "src.apps.posts.models.Post"
    
    def test_many_to_many_with_app_model_syntax(self):
        """many_to_many aceita sintaxe app.Model."""
        with patch("core.relations.relationship") as mock_rel:
            mock_rel.return_value = MagicMock()
            
            Rel.many_to_many(
                "tags.Tag",
                secondary="post_tags",
                back_populates="posts"
            )
            
            mock_rel.assert_called_once()
            args, kwargs = mock_rel.call_args
            assert args[0] == "src.apps.tags.models.Tag"
    
    def test_fully_qualified_path_not_modified(self):
        """Paths fully-qualified não são modificados."""
        with patch("core.relations.relationship") as mock_rel:
            mock_rel.return_value = MagicMock()
            
            Rel.many_to_one(
                "custom.path.to.models.MyModel",
                back_populates="items"
            )
            
            args, kwargs = mock_rel.call_args
            assert args[0] == "custom.path.to.models.MyModel"


class TestCircularDependencyResolution:
    """
    Testes para garantir que dependências circulares são resolvidas.
    
    Cenário típico:
        User → WorkspaceUser → User
    
    Com lazy loading via app.Model syntax, isso deve funcionar porque
    o SQLAlchemy resolve as strings em runtime, não em tempo de definição.
    """
    
    def test_lazy_loading_syntax_documentation(self):
        """
        Documenta o uso correto para resolver dependências circulares.
        
        Em vez de:
            workspace_users: Mapped[list["WorkspaceUser"]] = Rel.one_to_many(
                "WorkspaceUser",  # ❌ Falha se WorkspaceUser não foi importado
                back_populates="user",
            )
        
        Use:
            workspace_users: Mapped[list["WorkspaceUser"]] = Rel.one_to_many(
                "workspaces.WorkspaceUser",  # ✅ Lazy loading via app.Model
                back_populates="user",
            )
        
        Ou fully-qualified:
            workspace_users: Mapped[list["WorkspaceUser"]] = Rel.one_to_many(
                "src.apps.workspaces.models.WorkspaceUser",  # ✅ Explicit path
                back_populates="user",
            )
        """
        # Este teste serve como documentação
        # A sintaxe app.Model resolve para path completo
        assert _resolve_target("workspaces.WorkspaceUser") == \
            "src.apps.workspaces.models.WorkspaceUser"
        
        # Paths completos são usados diretamente
        assert _resolve_target("src.apps.workspaces.models.WorkspaceUser") == \
            "src.apps.workspaces.models.WorkspaceUser"


class TestPreloadModelsModule:
    """Testes para _preload_models_module() em core/config.py."""
    
    def test_preload_called_before_user_model(self):
        """
        Verifica que models_module é importado antes de resolver user_model.
        
        Isso é crucial para resolver dependências circulares.
        """
        from core.config import _preload_models_module
        
        # Mock settings com models_module
        mock_settings = MagicMock()
        mock_settings.models_module = "src.apps.models"
        
        with patch("core.config.import_module") as mock_import:
            _preload_models_module(mock_settings)
            mock_import.assert_called_once_with("src.apps.models")
    
    def test_preload_handles_missing_module(self):
        """Não falha se models_module não existe."""
        from core.config import _preload_models_module
        
        mock_settings = MagicMock()
        mock_settings.models_module = "nonexistent.module"
        
        with patch("core.config.import_module") as mock_import:
            mock_import.side_effect = ImportError("No module")
            
            # Não deve levantar exceção
            _preload_models_module(mock_settings)
    
    def test_preload_handles_list_of_modules(self):
        """Suporta lista de módulos."""
        from core.config import _preload_models_module
        
        mock_settings = MagicMock()
        mock_settings.models_module = [
            "src.apps.users.models",
            "src.apps.workspaces.models",
        ]
        
        with patch("core.config.import_module") as mock_import:
            _preload_models_module(mock_settings)
            
            assert mock_import.call_count == 2
            mock_import.assert_any_call("src.apps.users.models")
            mock_import.assert_any_call("src.apps.workspaces.models")
