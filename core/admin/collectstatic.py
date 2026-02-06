"""
core collectstatic — Coleta e prepara static assets do admin.

Responsabilidades:
1. Copiar assets do core (core/admin/static/core-admin/)
2. Copiar assets de apps/plugins (scan por */static/)
3. Resolver conflitos (último vence, com warning)
4. Cache busting via hash no nome ({name}.{hash8}.{ext})
5. Gerar manifest.json (mapeia original -> com hash)
6. Output CDN-ready
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger("core.admin")


def collectstatic(
    output_dir: str | None = None,
    no_hash: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    """
    Coleta static assets do admin para diretório de output.
    
    Args:
        output_dir: Diretório destino (default: ./static/core-admin)
        no_hash: Se True, não aplica cache busting hash
        verbose: Se True, mostra detalhes de cada arquivo copiado
    
    Returns:
        Dict com estatísticas:
        {
            "files_copied": 15,
            "conflicts": [],
            "manifest_path": "static/core-admin/manifest.json",
            "output_dir": "static/core-admin",
        }
    """
    cwd = Path(os.getcwd())
    
    if output_dir:
        dest = Path(output_dir)
    else:
        dest = cwd / "static" / "core-admin"
    
    # Limpa diretório destino
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    
    files_copied = 0
    conflicts: list[str] = []
    manifest: dict[str, str] = {}
    
    # 1. Coletar assets do core
    core_static = Path(__file__).parent / "static" / "core-admin"
    if core_static.is_dir():
        count, confs = _copy_tree(core_static, dest, manifest, no_hash, verbose, "core")
        files_copied += count
        conflicts.extend(confs)
    
    # 2. Coletar assets de apps do usuário (scan por */static/)
    apps_static_dirs = _find_app_static_dirs(cwd)
    for app_name, static_dir in apps_static_dirs:
        count, confs = _copy_tree(static_dir, dest, manifest, no_hash, verbose, app_name)
        files_copied += count
        conflicts.extend(confs)
    
    # 3. Gerar manifest.json
    manifest_path = dest / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    
    result = {
        "files_copied": files_copied,
        "conflicts": conflicts,
        "manifest_path": str(manifest_path),
        "output_dir": str(dest),
    }
    
    return result


def _copy_tree(
    src: Path,
    dest: Path,
    manifest: dict[str, str],
    no_hash: bool,
    verbose: bool,
    source_label: str,
) -> tuple[int, list[str]]:
    """
    Copia árvore de arquivos de src para dest.
    
    Returns:
        (count, conflicts)
    """
    count = 0
    conflicts: list[str] = []
    
    for src_file in src.rglob("*"):
        if src_file.is_dir():
            continue
        
        # Caminho relativo ao diretório static
        rel = src_file.relative_to(src)
        original_name = str(rel)
        
        if no_hash:
            dest_name = original_name
        else:
            dest_name = _hash_filename(src_file, rel)
        
        dest_file = dest / dest_name
        
        # Verifica conflitos
        if original_name in manifest:
            conflicts.append(
                f"'{original_name}' from '{source_label}' overrides previous version"
            )
            # Remove arquivo anterior se nome diferente
            old_dest = dest / manifest[original_name]
            if old_dest.exists() and old_dest != dest_file:
                old_dest.unlink()
            if verbose:
                logger.info("  CONFLICT: %s (overridden by %s)", original_name, source_label)
        
        # Copia arquivo
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest_file)
        
        # Registra no manifest
        manifest[original_name] = dest_name
        
        count += 1
        if verbose:
            logger.info("  %s -> %s", original_name, dest_name)
    
    return count, conflicts


def _hash_filename(file_path: Path, rel_path: Path) -> str:
    """
    Gera nome com hash para cache busting.
    
    Ex: css/admin.css -> css/admin.a1b2c3d4.css
    """
    content = file_path.read_bytes()
    file_hash = hashlib.md5(content).hexdigest()[:8]
    
    stem = rel_path.stem
    suffix = rel_path.suffix
    parent = str(rel_path.parent)
    
    hashed_name = f"{stem}.{file_hash}{suffix}"
    
    if parent and parent != ".":
        return f"{parent}/{hashed_name}"
    return hashed_name


def _find_app_static_dirs(root: Path) -> list[tuple[str, Path]]:
    """
    Encontra diretórios static/ em apps do usuário.
    
    Returns:
        Lista de (app_name, static_dir_path)
    """
    results: list[tuple[str, Path]] = []
    
    ignore_dirs = {
        "venv", ".venv", "env", ".env",
        "node_modules", "__pycache__", ".git",
        "core",  # Não re-escanear core (já copiado)
    }
    
    for entry in root.iterdir():
        if not entry.is_dir() or entry.name in ignore_dirs or entry.name.startswith("."):
            continue
        
        # Procura static/ dentro do app
        static_dir = entry / "static"
        if static_dir.is_dir():
            results.append((entry.name, static_dir))
        
        # Procura em subdiretórios (apps/users/static/)
        for sub_entry in entry.iterdir():
            if sub_entry.is_dir() and sub_entry.name not in ignore_dirs:
                sub_static = sub_entry / "static"
                if sub_static.is_dir():
                    results.append((sub_entry.name, sub_static))
    
    return results
