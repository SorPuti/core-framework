"""
Core Framework - Django-inspired, FastAPI-powered.

Um framework minimalista de alta performance que combina:
- Produtividade do Django
- Performance do FastAPI
- Controle total do desenvolvedor

Princípios:
- Zero abstrações desnecessárias
- Async por padrão
- Tipagem forte (mypy friendly)
- Performance first
"""

from core.models import Model, Field
from core.serializers import InputSchema, OutputSchema, Serializer
from core.views import APIView, ViewSet, ModelViewSet
from core.routing import Router, AutoRouter
from core.permissions import Permission, IsAuthenticated, AllowAny
from core.dependencies import Depends, get_db, get_current_user
from core.config import Settings, get_settings
from core.app import CoreApp

# Migrations
from core.migrations import (
    makemigrations,
    migrate,
    showmigrations,
    rollback,
    MigrationEngine,
    Migration,
)

__version__ = "0.1.0"
__all__ = [
    # Models
    "Model",
    "Field",
    # Serializers
    "InputSchema",
    "OutputSchema",
    "Serializer",
    # Views
    "APIView",
    "ViewSet",
    "ModelViewSet",
    # Routing
    "Router",
    "AutoRouter",
    # Permissions
    "Permission",
    "IsAuthenticated",
    "AllowAny",
    # Dependencies
    "Depends",
    "get_db",
    "get_current_user",
    # Config
    "Settings",
    "get_settings",
    # App
    "CoreApp",
    # Migrations
    "makemigrations",
    "migrate",
    "showmigrations",
    "rollback",
    "MigrationEngine",
    "Migration",
]
