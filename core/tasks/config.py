"""
Task configuration.

Usa o Settings centralizado automaticamente - não precisa configurar nada.
Basta definir no .env:

    TASK_ENABLED=true
    TASK_WORKER_CONCURRENCY=8

E tudo funciona automaticamente.
"""

from __future__ import annotations

from core.config import get_settings


def get_task_settings():
    """
    Retorna configurações de tasks.
    
    Simplesmente retorna o Settings global que já carrega do .env.
    
    Exemplo:
        settings = get_task_settings()
        print(settings.task_worker_concurrency)
    """
    return get_settings()


def configure_tasks(**kwargs):
    """
    DEPRECATED: Não precisa mais chamar isso.
    
    Configure diretamente no .env:
        TASK_WORKER_CONCURRENCY=8
    
    Ou se precisar via código:
        from core import configure
        configure(task_worker_concurrency=8)
    """
    from core.config import configure
    return configure(**kwargs)


# Alias para compatibilidade
TaskSettings = type(get_settings())
