"""
Testes para o sistema de relacionamentos (Rel).

Testa:
- _resolve_target() com diferentes formatos de target
- Sintaxe app.Model para lazy loading
- Resolução de "User" via get_user_model()
- Relacionamentos complexos User <-> Other Models
- Cache de importação de models
"""

import pytest
import sys
from unittest.mock import patch, MagicMock

from core.relations import (
    _resolve_target,
    _ensure_model_loaded,
    _get_model_path,
    clear_model_cache,
    Rel,
)


class TestResolveTarget:
    """Testes para _resolve_target()."""
    
    def setup_method(self):
        """Limpa cache antes de cada teste."""
        clear_model_cache()
    
    def test_fully_qualified_path_multiple_dots(self):
        """Paths com múltiplos pontos são usados diretamente."""
        result = _resolve_target("src.apps.workspaces.models.Workspace")
        assert result == "src.apps.workspaces.models.Workspace"
    
    def test_fully_qualified_path_three_dots(self):
        """Paths com 3+ pontos são considerados fully-qualified."""
        result = _resolve_target("myapp.models.users.User")
        assert result == "myapp.models.users.User"
    
    def test_app_model_syntax_returns_simple_name_when_loaded(self):
        """Sintaxe app.Model retorna nome simples quando model está carregado."""
        # Simula módulo carregado com o model
        mock_module = MagicMock()
        mock_module.Workspace = MagicMock()
        
        with patch.dict(sys.modules, {"src.apps.workspaces.models": mock_module}):
            result = _resolve_target("workspaces.Workspace")
            # Deve retornar nome simples (model está no registry)
            assert result == "Workspace"
    
    def test_app_model_syntax_returns_simple_name_as_fallback(self):
        """Sintaxe app.Model retorna nome simples como fallback."""
        # Quando o módulo não existe, retorna nome simples
        result = _resolve_target("nonexistent.SomeModel")
        assert result == "SomeModel"
    
    def test_simple_name_passed_through(self):
        """Nomes simples são passados para SQLAlchemy resolver."""
        result = _resolve_target("Comment")
        assert result == "Comment"
    
    def test_simple_name_post(self):
        """Outro nome simples."""
        result = _resolve_target("Post")
        assert result == "Post"
    
    def test_user_special_case_without_auth_returns_simple_name(self):
        """'User' sem auth configurado retorna nome simples."""
        with patch("core.auth.models.get_user_model") as mock:
            mock.side_effect = RuntimeError("No user_model configured")
            
            # Agora retorna "User" em vez de levantar exceção
            result = _resolve_target("User")
            assert result == "User"
    
    def test_user_special_case_with_auth_returns_simple_name(self):
        """'User' com auth configurado retorna nome simples."""
        mock_user = MagicMock()
        mock_user.__module__ = "src.apps.users.models"
        mock_user.__name__ = "User"
        
        with patch("core.auth.models.get_user_model", return_value=mock_user):
            result = _resolve_target("User")
            # Retorna nome simples (model já está no registry)
            assert result == "User"


class TestEnsureModelLoaded:
    """Testes para _ensure_model_loaded()."""
    
    def setup_method(self):
        """Limpa cache antes de cada teste."""
        clear_model_cache()
    
    def test_returns_true_when_module_already_loaded(self):
        """Retorna True quando módulo já está carregado."""
        mock_module = MagicMock()
        mock_module.Workspace = MagicMock()
        
        with patch.dict(sys.modules, {"src.apps.workspaces.models": mock_module}):
            result = _ensure_model_loaded("workspaces", "Workspace")
            assert result is True
    
    def test_returns_false_when_model_not_found(self):
        """Retorna False quando model não é encontrado."""
        result = _ensure_model_loaded("nonexistent", "SomeModel")
        assert result is False
    
    def test_tries_import_when_not_loaded(self):
        """Tenta importar módulo quando não está carregado."""
        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.TestModel = MagicMock()
            mock_import.return_value = mock_module
            
            result = _ensure_model_loaded("testapp", "TestModel")
            assert result is True
            # Verifica que tentou importar
            assert mock_import.called
    
    def test_caches_results(self):
        """Usa cache para evitar importações repetidas."""
        with patch("importlib.import_module") as mock_import:
            mock_import.side_effect = ImportError("No module")
            
            # Primeira chamada
            _ensure_model_loaded("cached", "Model")
            # Segunda chamada
            _ensure_model_loaded("cached", "Model")
            
            # import_module deve ser chamado apenas nas convenções da primeira vez
            # (4 convenções tentadas)
            first_call_count = mock_import.call_count
            
            # Terceira chamada - deve usar cache
            _ensure_model_loaded("cached", "Model")
            
            # Não deve ter chamadas adicionais
            assert mock_import.call_count == first_call_count


class TestGetModelPath:
    """Testes para _get_model_path()."""
    
    def test_returns_path_when_module_loaded(self):
        """Retorna path quando módulo está carregado."""
        mock_module = MagicMock()
        mock_module.Post = MagicMock()
        
        with patch.dict(sys.modules, {"src.apps.posts.models": mock_module}):
            result = _get_model_path("posts", "Post")
            assert result == "src.apps.posts.models.Post"
    
    def test_returns_none_when_not_found(self):
        """Retorna None quando model não é encontrado."""
        result = _get_model_path("nonexistent", "Model")
        assert result is None
    
    def test_tries_multiple_conventions(self):
        """Tenta múltiplas convenções de path."""
        mock_module = MagicMock()
        mock_module.CustomModel = MagicMock()
        
        # Simula módulo em convenção alternativa
        with patch.dict(sys.modules, {"apps.custom.models": mock_module}):
            result = _get_model_path("custom", "CustomModel")
            assert result == "apps.custom.models.CustomModel"


class TestClearModelCache:
    """Testes para clear_model_cache()."""
    
    def test_clears_cache(self):
        """Limpa o cache de importação."""
        # Popula o cache
        _ensure_model_loaded("test", "Model")
        
        # Limpa
        clear_model_cache()
        
        # Verifica que cache foi limpo (nova chamada tentará importar novamente)
        with patch("importlib.import_module") as mock_import:
            mock_import.side_effect = ImportError("No module")
            _ensure_model_loaded("test", "Model")
            assert mock_import.called


class TestRelMethods:
    """Testes para métodos da classe Rel."""
    
    def setup_method(self):
        """Limpa cache antes de cada teste."""
        clear_model_cache()
    
    def test_many_to_one_with_app_model_syntax(self):
        """many_to_one aceita sintaxe app.Model."""
        # Simula módulo carregado
        mock_module = MagicMock()
        mock_module.Workspace = MagicMock()
        
        with patch.dict(sys.modules, {"src.apps.workspaces.models": mock_module}):
            with patch("core.relations.relationship") as mock_rel:
                mock_rel.return_value = MagicMock()
                
                Rel.many_to_one("workspaces.Workspace", back_populates="users")
                
                # Verifica que foi chamado com nome simples
                mock_rel.assert_called_once()
                args, kwargs = mock_rel.call_args
                assert args[0] == "Workspace"
                assert kwargs["back_populates"] == "users"
    
    def test_one_to_many_with_app_model_syntax(self):
        """one_to_many aceita sintaxe app.Model."""
        mock_module = MagicMock()
        mock_module.Post = MagicMock()
        
        with patch.dict(sys.modules, {"src.apps.posts.models": mock_module}):
            with patch("core.relations.relationship") as mock_rel:
                mock_rel.return_value = MagicMock()
                
                Rel.one_to_many("posts.Post", back_populates="author")
                
                mock_rel.assert_called_once()
                args, kwargs = mock_rel.call_args
                assert args[0] == "Post"
    
    def test_many_to_many_with_app_model_syntax(self):
        """many_to_many aceita sintaxe app.Model."""
        mock_module = MagicMock()
        mock_module.Tag = MagicMock()
        
        with patch.dict(sys.modules, {"src.apps.tags.models": mock_module}):
            with patch("core.relations.relationship") as mock_rel:
                mock_rel.return_value = MagicMock()
                
                Rel.many_to_many(
                    "tags.Tag",
                    secondary="post_tags",
                    back_populates="posts"
                )
                
                mock_rel.assert_called_once()
                args, kwargs = mock_rel.call_args
                assert args[0] == "Tag"
    
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
    
    def setup_method(self):
        """Limpa cache antes de cada teste."""
        clear_model_cache()
    
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
        # Simula módulo carregado
        mock_module = MagicMock()
        mock_module.WorkspaceUser = MagicMock()
        
        with patch.dict(sys.modules, {"src.apps.workspaces.models": mock_module}):
            # A sintaxe app.Model resolve para nome simples quando carregado
            assert _resolve_target("workspaces.WorkspaceUser") == "WorkspaceUser"
        
        # Paths completos são usados diretamente
        assert _resolve_target("src.apps.workspaces.models.WorkspaceUser") == \
            "src.apps.workspaces.models.WorkspaceUser"
    
    def test_app_model_imports_module_automatically(self):
        """Sintaxe app.Model importa módulo automaticamente se necessário."""
        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.WorkspaceUser = MagicMock()
            mock_import.return_value = mock_module
            
            result = _resolve_target("workspaces.WorkspaceUser")
            
            # Deve ter tentado importar
            assert mock_import.called
            # Deve retornar nome simples
            assert result == "WorkspaceUser"


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
