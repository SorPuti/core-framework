"""
Template loader for project initialization.

Templates are stored in subdirectories and use {{variable}} syntax.
Each template can have a manifest.json with metadata.
"""

import json
from pathlib import Path
from typing import Any


# Template directory
TEMPLATES_DIR = Path(__file__).parent


# Template metadata (name, description, features)
TEMPLATE_METADATA = {
    "minimal": {
        "name": "Minimal",
        "description": "Simple CRUD API with SQLite",
        "features": [
            "Single Item model",
            "CRUD endpoints",
            "SQLite database",
            "No authentication",
        ],
        "recommended_for": "Learning, prototypes, simple APIs",
    },
    "default": {
        "name": "Default (Auth)",
        "description": "API with authentication and user management",
        "features": [
            "User model with AbstractUser",
            "JWT authentication (login, register, refresh)",
            "Permission system",
            "SQLite/PostgreSQL support",
        ],
        "recommended_for": "Most applications, SaaS, web apps",
    },
    "kafka": {
        "name": "Kafka + PostgreSQL + Redis",
        "description": "Event-driven architecture with message queues",
        "features": [
            "Kafka producers/consumers",
            "PostgreSQL database",
            "Redis for caching",
            "Docker Compose included",
            "Event logging",
        ],
        "recommended_for": "Microservices, event-driven systems, high-scale apps",
    },
    "tenant": {
        "name": "Multi-Tenant",
        "description": "Multi-tenant architecture with data isolation",
        "features": [
            "Tenant model with UUID",
            "Automatic tenant filtering",
            "TenantMixin for models",
            "PostgreSQL required",
            "X-Tenant-ID header",
        ],
        "recommended_for": "SaaS platforms, B2B applications",
    },
    "workers": {
        "name": "Background Workers",
        "description": "API with background task processing",
        "features": [
            "@worker decorator for tasks",
            "Task model for tracking",
            "Redis task queue",
            "Retry with backoff",
            "Docker Compose included",
        ],
        "recommended_for": "Email sending, data processing, scheduled jobs",
    },
}


def get_template_dir(template_name: str) -> Path:
    """Get the directory for a specific template."""
    return TEMPLATES_DIR / template_name


def render_template(content: str, context: dict[str, Any]) -> str:
    """Render template content with context variables."""
    for key, value in context.items():
        content = content.replace(f"{{{{{key}}}}}", str(value))
    return content


def load_template_file(template_name: str, file_path: str, context: dict[str, Any]) -> str:
    """Load and render a single template file."""
    template_dir = get_template_dir(template_name)
    full_path = template_dir / file_path
    
    if not full_path.exists():
        raise FileNotFoundError(f"Template file not found: {full_path}")
    
    content = full_path.read_text(encoding="utf-8")
    return render_template(content, context)


def get_template_files(template_name: str) -> dict[str, str]:
    """Get all template files for a given template."""
    template_dir = get_template_dir(template_name)
    
    if not template_dir.exists():
        raise FileNotFoundError(f"Template directory not found: {template_dir}")
    
    files = {}
    for template_file in template_dir.rglob("*.template"):
        rel_path = template_file.relative_to(template_dir)
        output_path = str(rel_path).replace(".template", "")
        files[output_path] = str(rel_path)
    
    return files


def load_all_templates(template_name: str, context: dict[str, Any]) -> dict[str, str]:
    """Load all templates for a given template name."""
    template_files = get_template_files(template_name)
    result = {}
    
    for output_path, template_path in template_files.items():
        content = load_template_file(template_name, template_path, context)
        result[output_path] = content
    
    return result


def get_template_dirs(template_name: str) -> list[str]:
    """Get all directories that need to be created for a template."""
    template_dir = get_template_dir(template_name)
    
    if not template_dir.exists():
        raise FileNotFoundError(f"Template directory not found: {template_dir}")
    
    dirs = set()
    for template_file in template_dir.rglob("*.template"):
        rel_path = template_file.relative_to(template_dir)
        parent = rel_path.parent
        while str(parent) != ".":
            dirs.add(str(parent))
            parent = parent.parent
    
    return sorted(dirs)


def list_available_templates() -> list[str]:
    """List all available template names."""
    templates = []
    for item in TEMPLATES_DIR.iterdir():
        if item.is_dir() and not item.name.startswith("_") and not item.name.startswith("."):
            templates.append(item.name)
    return sorted(templates)


def get_template_metadata(template_name: str) -> dict:
    """Get metadata for a template."""
    return TEMPLATE_METADATA.get(template_name, {
        "name": template_name.title(),
        "description": f"Template: {template_name}",
        "features": [],
        "recommended_for": "",
    })


def get_all_templates_metadata() -> dict[str, dict]:
    """Get metadata for all available templates."""
    result = {}
    for name in list_available_templates():
        result[name] = get_template_metadata(name)
    return result
