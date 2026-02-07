"""
Registry centralizado para modelos SQLAlchemy.

Fornece cache e lazy loading para evitar carregamentos duplicados de modelos,
módulos e relações. Integra com CoreApp, workers e migrations.

Uso:
    from core.registry import ModelRegistry
    
    registry = ModelRegistry.get_instance()
    models = registry.discover_models(models_module="app.models")
    
    # Lazy load de modelo específico
    User = registry.get_model("app.models.User")
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from core.models import Model

logger = logging.getLogger("core.registry")

# Cache de módulos que falharam ao importar (evitar retry infinito)
_FAILED_MODULES: set[str] = set()

# Diretórios a ignorar durante scan
_IGNORE_DIRS = {
    "__pycache__", ".venv", "venv", "node_modules",
    "migrations", ".git", "tests", "test", "site-packages",
}


class ModelRegistry:
    """
    Registry centralizado para modelos SQLAlchemy com cache e lazy loading.
    
    Singleton pattern garante que há apenas uma instância em todo o processo.
    Cache evita carregamentos duplicados de modelos e módulos.
    
    Características:
    - Cache de modelos descobertos
    - Cache de módulos importados
    - Cache de resoluções de relações
    - Lazy loading com verificações fortes
    - Thread-safe para operações de escrita
    """
    
    _instance: ClassVar[ModelRegistry | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()
    
    def __init__(self) -> None:
        """Inicializa o registry com caches vazios."""
        # Cache de modelos: module_path.class_name -> Model class
        self._models_cache: dict[str, type[Model]] = {}
        
        # Módulos já importados (evita re-imports)
        self._modules_loaded: set[str] = set()
        
        # Modelos já descobertos (usando id() para detectar duplicatas)
        self._models_discovered: dict[int, type[Model]] = {}
        
        # Cache de resoluções de relações: target -> resolved_path
        self._relationships_cache: dict[str, str] = {}
        
        # Módulos que falharam ao importar (evitar retry)
        self._failed_modules: set[str] = set()
        
        # Flag para indicar se discovery já foi executado
        self._discovery_executed: bool = False
    
    @classmethod
    def get_instance(cls) -> ModelRegistry:
        """
        Retorna a instância singleton do registry.
        
        Thread-safe usando double-checked locking pattern.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def discover_models(
        self,
        models_module: str | list[str] | None = None,
        force_rescan: bool = False,
    ) -> list[type[Model]]:
        """
        Descobre modelos com cache e deduplicação.
        
        Estratégia:
        1. Se já foi executado e não é force_rescan, retorna cache
        2. Carrega módulos core internos primeiro
        3. Carrega módulos do projeto do usuário
        4. Extrai modelos de cada módulo (evitando duplicatas)
        5. Cacheia resultados
        
        Args:
            models_module: Módulo(s) explícito(s) para importar. Se None, auto-descobre.
            force_rescan: Se True, ignora cache e reescaneia tudo.
        
        Returns:
            Lista de classes Model descobertas (sem duplicatas).
        """
        from core.models import Model
        
        # Se já foi executado e não é force_rescan, retorna cache
        if self._discovery_executed and not force_rescan:
            return list(self._models_discovered.values())
        
        with self._lock:
            # Double-check após adquirir lock
            if self._discovery_executed and not force_rescan:
                return list(self._models_discovered.values())
            
            models: list[type[Model]] = []
            
            # ── 1. Carrega módulos core internos ──
            core_modules = self._get_core_internal_models()
            for mod_path in core_modules:
                if mod_path in self._failed_modules:
                    continue
                
                module = self._import_module(mod_path)
                if module is not None:
                    core_models = self._extract_models_from_module(module, mod_path)
                    for model in core_models:
                        if id(model) not in self._models_discovered:
                            models.append(model)
                            self._models_discovered[id(model)] = model
                            self._models_cache[f"{mod_path}.{model.__name__}"] = model
            
            # ── 2. Determina módulos do projeto do usuário ──
            if models_module:
                if isinstance(models_module, str):
                    modules_to_check = [models_module]
                else:
                    modules_to_check = list(models_module)
            else:
                # Auto-discovery: scan do projeto
                root_dir = self._get_project_root()
                cache_file = root_dir / ".core_models_cache.json"
                
                if not force_rescan:
                    cache = self._load_models_cache(cache_file)
                    if cache:
                        modules_to_check = cache["modules"]
                        logger.debug("Using cached model discovery (%d modules)", len(modules_to_check))
                    else:
                        modules_to_check = self._scan_for_models(root_dir)
                        if modules_to_check:
                            self._save_models_cache(cache_file, modules_to_check)
                else:
                    modules_to_check = self._scan_for_models(root_dir)
                    if modules_to_check:
                        self._save_models_cache(cache_file, modules_to_check)
            
            # ── 3. Carrega módulos do projeto do usuário ──
            for module_path in modules_to_check:
                # Skip se já foi carregado como core module
                if module_path in core_modules:
                    continue
                
                # Skip se já foi importado
                if module_path in self._modules_loaded:
                    # Módulo já carregado, extrai modelos novamente se necessário
                    if module_path not in sys.modules:
                        continue
                    module = sys.modules[module_path]
                    user_models = self._extract_models_from_module(module, module_path)
                    for model in user_models:
                        if id(model) not in self._models_discovered:
                            models.append(model)
                            self._models_discovered[id(model)] = model
                            self._models_cache[f"{module_path}.{model.__name__}"] = model
                    continue
                
                # Skip se falhou anteriormente
                if module_path in self._failed_modules:
                    continue
                
                # Importa módulo
                module = self._import_module(module_path)
                if module is None:
                    self._failed_modules.add(module_path)
                    continue
                
                # Extrai modelos
                user_models = self._extract_models_from_module(module, module_path)
                for model in user_models:
                    # Verifica duplicata usando id()
                    if id(model) not in self._models_discovered:
                        models.append(model)
                        self._models_discovered[id(model)] = model
                        self._models_cache[f"{module_path}.{model.__name__}"] = model
                    else:
                        logger.debug(
                            "Skipping duplicate model %s (already registered)",
                            f"{module_path}.{model.__name__}",
                        )
            
            self._discovery_executed = True
            
            if models:
                logger.info(
                    "Discovered %d model(s) via registry (cached for future use)",
                    len(models),
                )
            
            return models
    
    def get_model(self, model_path: str) -> type[Model] | None:
        """
        Lazy load de modelo por path completo.
        
        Args:
            model_path: Path completo do modelo (ex: "app.models.User")
        
        Returns:
            Classe Model ou None se não encontrado.
        """
        # Verifica cache primeiro
        if model_path in self._models_cache:
            return self._models_cache[model_path]
        
        # Tenta importar módulo e extrair modelo
        parts = model_path.rsplit(".", 1)
        if len(parts) != 2:
            logger.warning("Invalid model path format: %s (expected 'module.Class')", model_path)
            return None
        
        module_path, class_name = parts
        
        # Importa módulo se necessário
        module = self._import_module(module_path)
        if module is None:
            return None
        
        # Extrai modelo do módulo
        if hasattr(module, class_name):
            model_class = getattr(module, class_name)
            from core.models import Model
            
            if isinstance(model_class, type) and issubclass(model_class, Model):
                # Cacheia modelo
                self._models_cache[model_path] = model_class
                if id(model_class) not in self._models_discovered:
                    self._models_discovered[id(model_class)] = model_class
                return model_class
        
        logger.warning("Model %s not found in module %s", class_name, module_path)
        return None
    
    def register_model(self, model: type[Model]) -> None:
        """
        Registra modelo no cache manualmente.
        
        Útil para modelos criados dinamicamente ou importados de outras formas.
        
        Args:
            model: Classe Model a registrar.
        """
        from core.models import Model
        
        if not isinstance(model, type) or not issubclass(model, Model):
            raise TypeError(f"Expected Model subclass, got {type(model)}")
        
        with self._lock:
            # Verifica duplicata
            model_id = id(model)
            if model_id in self._models_discovered:
                existing = self._models_discovered[model_id]
                logger.warning(
                    "Model %s already registered (existing: %s)",
                    model.__name__,
                    existing.__name__,
                )
                return
            
            # Registra
            model_path = f"{model.__module__}.{model.__name__}"
            self._models_cache[model_path] = model
            self._models_discovered[model_id] = model
            
            logger.debug("Registered model: %s", model_path)
    
    def is_module_loaded(self, module_path: str) -> bool:
        """
        Verifica se módulo já foi importado.
        
        Args:
            module_path: Path do módulo (ex: "app.models")
        
        Returns:
            True se módulo já foi importado.
        """
        return module_path in self._modules_loaded or module_path in sys.modules
    
    def cache_relationship(self, target: str, resolved: str) -> None:
        """
        Cacheia resolução de relação.
        
        Args:
            target: Target original (ex: "User")
            resolved: Path resolvido (ex: "app.models.User")
        """
        with self._lock:
            self._relationships_cache[target] = resolved
    
    def get_cached_relationship(self, target: str) -> str | None:
        """
        Obtém relação resolvida do cache.
        
        Args:
            target: Target original (ex: "User")
        
        Returns:
            Path resolvido ou None se não estiver em cache.
        """
        return self._relationships_cache.get(target)
    
    def clear_cache(self) -> None:
        """
        Limpa todos os caches.
        
        AVISO: Apenas para uso em testes. Em produção, este método
        emite um warning e não executa.
        """
        import os as os_module
        
        if os_module.environ.get("ENVIRONMENT") == "production":
            logger.warning(
                "clear_cache() called in production environment — ignored. "
                "This function is intended for testing only."
            )
            return
        
        with self._lock:
            self._models_cache.clear()
            self._modules_loaded.clear()
            self._models_discovered.clear()
            self._relationships_cache.clear()
            self._failed_modules.clear()
            self._discovery_executed = False
            logger.debug("Registry cache cleared")
    
    # ── Métodos auxiliares privados ──
    
    def _import_module(self, module_path: str) -> Any:
        """
        Importa módulo com cache e tratamento de erros.
        
        Args:
            module_path: Path do módulo
        
        Returns:
            Módulo importado ou None se falhar.
        """
        # Verifica se já foi importado
        if module_path in sys.modules:
            self._modules_loaded.add(module_path)
            return sys.modules[module_path]
        
        # Verifica se falhou anteriormente
        if module_path in self._failed_modules:
            return None
        
        # Tenta importar módulo core interno
        if module_path.startswith("core."):
            module = self._import_core_module(module_path)
            if module is not None:
                self._modules_loaded.add(module_path)
                return module
            else:
                self._failed_modules.add(module_path)
                return None
        
        # Import normal
        try:
            module = importlib.import_module(module_path)
            self._modules_loaded.add(module_path)
            return module
        except (ImportError, ModuleNotFoundError) as e:
            logger.debug("Failed to import module %s: %s", module_path, e)
            self._failed_modules.add(module_path)
            return None
        except Exception as e:
            logger.warning("Unexpected error importing module %s: %s", module_path, e)
            self._failed_modules.add(module_path)
            return None
    
    def _import_core_module(self, module_path: str) -> Any:
        """
        Importa módulo interno do core-framework com fallback robusto.
        
        Reutiliza lógica do CLI para lidar com pipx/venvs isolados.
        """
        # Tentativa 1: import normal
        try:
            return importlib.import_module(module_path)
        except (ImportError, ModuleNotFoundError):
            pass
        
        # Tentativa 2: localizar arquivo no pacote core
        try:
            import core as core_pkg
            core_dir = Path(core_pkg.__file__).parent
            
            relative = module_path.replace("core.", "", 1).replace(".", os.sep) + ".py"
            target_file = core_dir / relative
            
            if target_file.exists():
                spec = importlib.util.spec_from_file_location(module_path, target_file)
                if spec and spec.loader:
                    # Garantir pacotes pais em sys.modules
                    parts = module_path.split(".")
                    for i in range(1, len(parts)):
                        parent = ".".join(parts[:i])
                        if parent not in sys.modules:
                            parent_path = core_dir / os.sep.join(parts[1:i])
                            parent_init = parent_path / "__init__.py"
                            if parent_init.exists():
                                parent_spec = importlib.util.spec_from_file_location(
                                    parent,
                                    parent_init,
                                    submodule_search_locations=[str(parent_path)],
                                )
                                if parent_spec and parent_spec.loader:
                                    parent_mod = importlib.util.module_from_spec(parent_spec)
                                    sys.modules[parent] = parent_mod
                                    parent_spec.loader.exec_module(parent_mod)
                    
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[module_path] = mod
                    spec.loader.exec_module(mod)
                    return mod
        except Exception:
            pass
        
        # Tentativa 3: diretório de trabalho atual (editable install)
        try:
            cwd_file = Path.cwd() / module_path.replace(".", os.sep) + ".py"
            if cwd_file.exists():
                spec = importlib.util.spec_from_file_location(module_path, cwd_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[module_path] = mod
                    spec.loader.exec_module(mod)
                    return mod
        except Exception:
            pass
        
        return None
    
    def _extract_models_from_module(
        self,
        module: Any,
        module_path: str,
    ) -> list[type[Model]]:
        """
        Extrai classes Model de um módulo.
        
        Args:
            module: Módulo Python importado
            module_path: Path do módulo (para logging)
        
        Returns:
            Lista de classes Model encontradas.
        """
        from core.models import Model
        
        models: list[type[Model]] = []
        
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, Model)
                and obj is not Model
                and hasattr(obj, "__table__")
            ):
                models.append(obj)
        
        return models
    
    def _get_core_internal_models(self) -> list[str]:
        """Retorna lista de módulos internos do core-framework."""
        return [
            "core.admin.models",  # AuditLog, AdminSession, TaskExecution, etc.
            "core.auth.models",  # User, Group, Permission (se existirem)
        ]
    
    def _get_project_root(self) -> Path:
        """Encontra raiz do projeto (onde pyproject.toml ou core.toml está)."""
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents):
            if (parent / "pyproject.toml").exists() or (parent / "core.toml").exists():
                return parent
        return cwd
    
    def _scan_for_models(self, root_dir: Path) -> list[str]:
        """
        Escaneia recursivamente por arquivos Python contendo Model subclasses.
        
        Args:
            root_dir: Diretório raiz do projeto
        
        Returns:
            Lista de paths de módulos encontrados.
        """
        model_modules: list[str] = []
        
        for py_file in root_dir.rglob("*.py"):
            # Skip diretórios ignorados
            if any(part in py_file.parts for part in _IGNORE_DIRS):
                continue
            
            try:
                content = py_file.read_text()
                # Heurística: arquivo provavelmente contém models
                if "from core.models import" in content or "from core import Model" in content:
                    if "(Model)" in content or "(Model," in content:
                        # Converte path para módulo
                        rel_path = py_file.relative_to(root_dir)
                        module = str(rel_path.with_suffix("")).replace(os.sep, ".")
                        model_modules.append(module)
            except Exception:
                continue
        
        return model_modules
    
    def _load_models_cache(self, cache_file: Path) -> dict | None:
        """Carrega cache de módulos de modelos se válido."""
        import json
        from datetime import datetime
        
        if not cache_file.exists():
            return None
        
        try:
            data = json.loads(cache_file.read_text())
            # Cache válido por 1 hora
            cache_time = datetime.fromisoformat(data["timestamp"])
            if (datetime.now() - cache_time).total_seconds() > 3600:
                return None
            return data
        except Exception:
            return None
    
    def _save_models_cache(self, cache_file: Path, modules: list[str]) -> None:
        """Salva módulos descobertos em cache."""
        import json
        from datetime import datetime
        
        data = {
            "timestamp": datetime.now().isoformat(),
            "modules": modules,
        }
        cache_file.write_text(json.dumps(data, indent=2))


# ── Função de conveniência ──

def get_model_registry() -> ModelRegistry:
    """
    Retorna instância singleton do ModelRegistry.
    
    Conveniência para evitar ModelRegistry.get_instance().
    """
    return ModelRegistry.get_instance()
