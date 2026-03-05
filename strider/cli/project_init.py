"""
Project initialization using external templates.

This module provides functions to create new projects using
templates stored in core/cli/templates/ directory.
"""

import os
import subprocess
from pathlib import Path

from .templates import load_all_templates, get_template_dirs


def create_project_from_template(
    project_name: str,
    python_version: str,
    template_name: str,
    skip_venv: bool = False,
    check_uv_installed_fn=None,
    install_uv_fn=None,
    print_fn=print,
) -> int:
    """
    Create a new project from a template.
    
    Args:
        project_name: Name of the project to create
        python_version: Python version to use (e.g., "3.12")
        template_name: Template to use ("default" or "minimal")
        skip_venv: Skip virtual environment creation
        check_uv_installed_fn: Function to check if uv is installed
        install_uv_fn: Function to install uv
        print_fn: Print function for output
        
    Returns:
        Exit code (0 for success)
    """
    # Template context for variable substitution
    context = {
        "project_name": project_name,
        "python_version": python_version,
    }
    
    # Create directory structure
    print_fn(f"Creating project structure...")
    Path(project_name).mkdir(parents=True, exist_ok=True)
    print_fn(f"  📁 {project_name}/")
    
    for dir_path in get_template_dirs(template_name):
        full_path = Path(project_name) / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        print_fn(f"  📁 {project_name}/{dir_path}/")
    
    # Create migrations dir (common to all templates)
    migrations_dir = Path(project_name) / "migrations"
    if not migrations_dir.exists():
        migrations_dir.mkdir(parents=True, exist_ok=True)
        print_fn(f"  📁 {project_name}/migrations/")
    
    # Load and write template files
    print_fn(f"\nCreating files...")
    files = load_all_templates(template_name, context)
    
    for file_path, content in files.items():
        full_path = Path(project_name) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        print_fn(f"  📄 {project_name}/{file_path}")
    
    # Setup virtual environment
    if not skip_venv and check_uv_installed_fn and install_uv_fn:
        print_fn(f"\nSetting up virtual environment...")
        project_path = Path(project_name).absolute()
        
        try:
            subprocess.run(
                ["uv", "venv", "--python", python_version],
                cwd=project_path,
                check=True,
                capture_output=True,
            )
            print_fn(f"  ✓ Virtual environment created")
            
            subprocess.run(
                ["uv", "sync"],
                cwd=project_path,
                check=True,
                capture_output=True,
            )
            print_fn(f"  ✓ Dependencies installed")
            
        except subprocess.CalledProcessError as e:
            print_fn(f"  Warning: {e}")
            print_fn(f"  Run manually: cd {project_name} && uv sync")
    
    return 0


def get_available_templates() -> list[str]:
    """Get list of available template names."""
    from .templates import list_available_templates
    return list_available_templates()
