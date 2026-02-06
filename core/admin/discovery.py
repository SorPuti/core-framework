"""
Auto-descoberta de módulos admin.py.

Reutiliza o pattern de discover_models do CLI,
adaptado para importar admin.py de apps.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.admin.site import AdminSite

logger = logging.getLogger("core.admin.discovery")

# Diretórios a ignorar durante scan
_IGNORE_DIRS = {
    "venv", ".venv", "env", ".env",
    "node_modules", "__pycache__", ".git",
    "migrations", ".mypy_cache", ".pytest_cache",
    ".tox", "dist", "build", "egg-info",
    "static", "templates", "media",
}


def discover_admin_modules(site: "AdminSite") -> list[str]:
    """
    Descobre e importa todos os módulos admin.py no projeto.
    
    Estratégia:
    1. Verifica core.toml / pyproject.toml por 'admin_modules' explícito
    2. Scan recursivo por */admin.py excluindo diretórios ignorados
    3. Importa cada módulo encontrado (import dispara registrations)
    
    Erros de import NÃO são engolidos — são registrados no site.errors
    e exibidos no dashboard do admin.
    
    Returns:
        Lista de módulos importados com sucesso
    """
    imported: list[str] = []
    
    # 1. Tenta carregar de configuração explícita
    explicit_modules = _get_explicit_admin_modules()
    if explicit_modules:
        for module_path in explicit_modules:
            success = _import_admin_module(site, module_path)
            if success:
                imported.append(module_path)
        return imported
    
    # 2. Scan recursivo
    cwd = Path(os.getcwd())
    
    # Garante que CWD está no sys.path
    import sys
    cwd_str = str(cwd)
    if cwd_str not in sys.path:
        sys.path.insert(0, cwd_str)
    
    admin_files = _scan_for_admin_files(cwd)
    
    for admin_file in admin_files:
        module_path = _file_to_module(admin_file, cwd)
        if module_path:
            success = _import_admin_module(site, module_path)
            if success:
                imported.append(module_path)
    
    if imported:
        logger.info("Discovered %d admin module(s): %s", len(imported), ", ".join(imported))
    
    return imported


def _get_explicit_admin_modules() -> list[str] | None:
    """
    Tenta obter lista explícita de módulos admin.
    
    Fontes:
    1. core.toml: [admin] modules = ["apps.users.admin", "apps.payments.admin"]
    2. pyproject.toml: [tool.core.admin] modules = [...]
    """
    cwd = Path(os.getcwd())
    
    # Tenta core.toml
    core_toml = cwd / "core.toml"
    if core_toml.is_file():
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore
            except ImportError:
                return None
        
        try:
            with open(core_toml, "rb") as f:
                config = tomllib.load(f)
            modules = config.get("admin", {}).get("modules")
            if modules and isinstance(modules, list):
                return modules
        except Exception:
            pass
    
    # Tenta pyproject.toml
    pyproject = cwd / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore
            except ImportError:
                return None
        
        try:
            with open(pyproject, "rb") as f:
                config = tomllib.load(f)
            modules = config.get("tool", {}).get("core", {}).get("admin", {}).get("modules")
            if modules and isinstance(modules, list):
                return modules
        except Exception:
            pass
    
    return None


def _scan_for_admin_files(root: Path) -> list[Path]:
    """
    Scan recursivo por arquivos admin.py.
    
    Ignora diretórios em _IGNORE_DIRS e arquivos dentro de core/admin/.
    """
    admin_files: list[Path] = []
    
    for dirpath, dirnames, filenames in os.walk(root):
        # Remove diretórios ignorados do scan
        dirnames[:] = [
            d for d in dirnames
            if d not in _IGNORE_DIRS and not d.startswith(".")
        ]
        
        # Ignora o próprio core/admin/ (não queremos importar a si mesmo)
        rel = Path(dirpath).relative_to(root)
        parts = rel.parts
        if len(parts) >= 2 and parts[0] == "core" and parts[1] == "admin":
            continue
        
        if "admin.py" in filenames:
            admin_file = Path(dirpath) / "admin.py"
            admin_files.append(admin_file)
    
    return sorted(admin_files)


def _file_to_module(file_path: Path, root: Path) -> str | None:
    """Converte caminho de arquivo para nome de módulo Python."""
    try:
        relative = file_path.relative_to(root)
        # Remove .py e converte separadores para pontos
        module = str(relative).replace(os.sep, ".").replace("/", ".")
        if module.endswith(".py"):
            module = module[:-3]
        return module
    except (ValueError, Exception):
        return None


def _import_admin_module(site: "AdminSite", module_path: str) -> bool:
    """
    Importa um módulo admin.py.
    
    Erros de import são registrados no site.errors,
    NÃO são engolidos silenciosamente.
    
    Returns:
        True se importou com sucesso
    """
    try:
        importlib.import_module(module_path)
        logger.debug("Imported admin module: %s", module_path)
        return True
    except Exception as e:
        logger.warning(
            "Failed to import admin module '%s': %s: %s",
            module_path, type(e).__name__, e,
        )
        site.errors.add_discovery_error(module_path, e)
        return False
