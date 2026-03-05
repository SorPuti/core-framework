"""
Task configuration.

DEPRECATED: Este módulo existe apenas para retrocompatibilidade.
Use core.config.get_settings() diretamente.

Todas as configurações de tasks estão centralizadas em core.config.Settings:

    TASK_ENABLED=true
    TASK_WORKER_CONCURRENCY=8

Acesse via:
    from stride.config import get_settings
    settings = get_settings()
    print(settings.task_worker_concurrency)
"""

from __future__ import annotations

import warnings

from stride.config import get_settings, configure


def get_task_settings():
    """
    DEPRECATED: Use get_settings() diretamente.
    
    Retorna configurações centralizadas (que incluem tasks).
    
    Exemplo (novo):
        from stride.config import get_settings
        settings = get_settings()
        print(settings.task_worker_concurrency)
    """
    warnings.warn(
        "get_task_settings() is deprecated. "
        "Use get_settings() from stride.config instead. "
        "All task settings are in the centralized Settings class.",
        DeprecationWarning,
        stacklevel=2,
    )
    return get_settings()


def configure_tasks(**kwargs):
    """
    DEPRECATED: Use configure() ou .env diretamente.
    
    Configure diretamente no .env:
        TASK_WORKER_CONCURRENCY=8
    
    Ou via código:
        from stride.config import configure
        configure(task_worker_concurrency=8)
    """
    warnings.warn(
        "configure_tasks() is deprecated. "
        "Use configure() from stride.config instead, or set values in .env.",
        DeprecationWarning,
        stacklevel=2,
    )
    return configure(**kwargs)


# Alias para compatibilidade (deprecated)
TaskSettings = type(get_settings()) if get_settings else None
