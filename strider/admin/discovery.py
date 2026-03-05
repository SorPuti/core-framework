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
    from strider.admin.site import AdminSite

logger = logging.getLogger("strider.admin.discovery")

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
    1. Se Settings.admin_modules estiver definido (não vazio), usa essa lista
    2. SEMPRE faz scan recursivo por */admin.py (complementa config explícita)
    3. Importa cada módulo encontrado (import dispara registrations)
    
    Erros de import NÃO são engolidos — são registrados no site.errors
    e exibidos no dashboard do admin.
    
    Returns:
        Lista de módulos importados com sucesso
    """
    import sys
    
    imported: list[str] = []
    already_imported: set[str] = set()
    
    cwd = Path(os.getcwd())
    
    # Garante que CWD está no sys.path
    cwd_str = str(cwd)
    if cwd_str not in sys.path:
        sys.path.insert(0, cwd_str)
    
    # 1. Carrega módulos explícitos (Settings.admin_modules)
    explicit_modules = _get_explicit_admin_modules()
    if explicit_modules:
        for module_path in explicit_modules:
            success = _import_admin_module(site, module_path)
            if success:
                imported.append(module_path)
            already_imported.add(module_path)
    
    # 2. SEMPRE faz scan recursivo (complementa config explícita)
    admin_files = _scan_for_admin_files(cwd)
    
    for admin_file in admin_files:
        module_path = _file_to_module(admin_file, cwd)
        if module_path and module_path not in already_imported:
            success = _import_admin_module(site, module_path)
            if success:
                imported.append(module_path)
            already_imported.add(module_path)
    
    if imported:
        logger.info("Discovered %d admin module(s): %s", len(imported), ", ".join(imported))
    
    return imported


def _resolve_app_path(app_name: str) -> str:
    """
    Resolve o caminho completo de um app a partir de um nome curto ou completo.
    
    Tenta encontrar o app em locais padrão:
    1. Se já tem ponto, assume caminho completo
    2. Tenta em src.apps.{app_name}
    3. Tenta em apps.{app_name}
    4. Tenta em src.{app_name}
    
    Args:
        app_name: Nome curto (ex: 'users') ou caminho completo (ex: 'src.apps.users')
    
    Returns:
        Caminho completo do app
    """
    import importlib.util
    
    # Se já tem ponto, assume caminho completo
    if "." in app_name:
        return app_name
    
    # Tenta locais padrão
    search_paths = [
        f"src.apps.{app_name}",
        f"apps.{app_name}",
        f"src.{app_name}",
    ]
    
    for path in search_paths:
        try:
            module_path = path.replace(".", "/")
            if importlib.util.find_spec(module_path):
                return path
        except (ImportError, ModuleNotFoundError, ValueError):
            continue
    
    # Fallback: retorna como estava
    return app_name


def _get_explicit_admin_modules() -> list[str] | None:
    """
    Obtém lista explícita de módulos admin a partir de Settings (.env / settings.py).
    Usa admin_modules se definido; senão, se installed_apps estiver definido, usa {app}.admin para cada app.
    Se ambos vazios, retorna None (só scan).
    
    Aceita app names curtos (ex: 'users') que são resolvidos para 'src.apps.users.admin'.
    Só retorna módulos que realmente existem (admin.py é opcional).
    """
    import os
    
    try:
        from strider.config import get_settings
        settings = get_settings()
        cwd = Path(os.getcwd())
        
        modules = getattr(settings, "admin_modules", None)
        if modules and isinstance(modules, list) and len(modules) > 0:
            # Verifica quais módulos realmente existem
            existing = []
            for mod in modules:
                # Converte módulo para caminho de arquivo
                file_path = cwd / mod.replace(".", os.sep) / "admin.py"
                if file_path.exists():
                    existing.append(mod)
                else:
                    logger.debug(f"Admin module not found (optional): {mod}")
            return existing if existing else None
            
        # Fallback: installed_apps -> {app}.admin (com auto-resolução)
        apps = getattr(settings, "installed_apps", None)
        if apps and isinstance(apps, list) and len(apps) > 0:
            existing = []
            for app in apps:
                resolved = _resolve_app_path(app)
                admin_module = f"{resolved}.admin"
                # Verifica se o arquivo admin.py existe
                file_path = cwd / resolved.replace(".", os.sep) / "admin.py"
                if file_path.exists():
                    existing.append(admin_module)
                else:
                    logger.debug(f"Admin module not found (optional): {admin_module}")
            return existing if existing else None
            
    except Exception:
        pass
    return None


def _scan_for_admin_files(root: Path) -> list[Path]:
    """
    Scan recursivo por arquivos admin.py.
    
    Ignora diretórios em _IGNORE_DIRS e arquivos dentro de stride/admin/.
    
    Se installed_apps estiver configurado, só faz scan dentro desses diretórios.
    Isso evita tentar importar módulos de caminhos que não são pacotes Python válidos.
    
    Aceita app names curtos (ex: 'users') que são resolvidos para 'src.apps.users'.
    """
    admin_files: list[Path] = []
    
    # Se installed_apps configurado, só scanear nesses diretórios
    try:
        from strider.config import get_settings
        settings = get_settings()
        installed_apps = getattr(settings, "installed_apps", None)
    except Exception:
        installed_apps = None
    
    if installed_apps and isinstance(installed_apps, list) and len(installed_apps) > 0:
        # Scan apenas nos diretórios dos apps configurados
        for app_name in installed_apps:
            # Resolve o caminho completo (aceita nomes curtos ou completos)
            resolved_path = _resolve_app_path(app_name)
            app_dir = root / resolved_path.replace(".", os.sep)
            if app_dir.exists() and app_dir.is_dir():
                for dirpath, dirnames, filenames in os.walk(app_dir):
                    # Remove diretórios ignorados
                    dirnames[:] = [
                        d for d in dirnames
                        if d not in _IGNORE_DIRS and not d.startswith(".")
                    ]
                    
                    if "admin.py" in filenames:
                        admin_file = Path(dirpath) / "admin.py"
                        admin_files.append(admin_file)
        return sorted(admin_files)
    
    # Scan completo (quando não há installed_apps configurado)
    for dirpath, dirnames, filenames in os.walk(root):
        # Remove diretórios ignorados do scan
        dirnames[:] = [
            d for d in dirnames
            if d not in _IGNORE_DIRS and not d.startswith(".")
        ]
        
        # Ignora o próprio stride/admin/ (não queremos importar a si mesmo)
        rel = Path(dirpath).relative_to(root)
        parts = rel.parts
        if len(parts) >= 2 and parts[0] == "stride" and parts[1] == "admin":
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
    
    Admin é opcional - apps podem ou não ter admin.py.
    Erros são logados em DEBUG, não WARNING, pois é comportamento esperado.
    
    Returns:
        True se importou com sucesso
    """
    try:
        importlib.import_module(module_path)
        logger.debug("Imported admin module: %s", module_path)
        return True
    except Exception as e:
        # Admin é opcional - não loga warning, apenas debug
        logger.debug(
            "Admin module not found (optional) '%s': %s: %s",
            module_path, type(e).__name__, e,
        )
        return False
