"""
Messaging configuration.

DEPRECATED: Este módulo existe apenas para retrocompatibilidade.
Use core.config.get_settings() diretamente.

Todas as configurações de messaging estão centralizadas em core.config.Settings:

    KAFKA_ENABLED=true
    KAFKA_BACKEND=confluent
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092

Acesse via:
    from core.config import get_settings
    settings = get_settings()
    print(settings.kafka_backend)
"""

from __future__ import annotations

import warnings

from core.config import get_settings, configure


def get_messaging_settings():
    """
    DEPRECATED: Use get_settings() diretamente.
    
    Retorna configurações centralizadas (que incluem messaging).
    
    Exemplo (novo):
        from core.config import get_settings
        settings = get_settings()
        print(settings.kafka_backend)
    """
    warnings.warn(
        "get_messaging_settings() is deprecated. "
        "Use get_settings() from core.config instead. "
        "All messaging settings are in the centralized Settings class.",
        DeprecationWarning,
        stacklevel=2,
    )
    return get_settings()


def configure_messaging(**kwargs):
    """
    DEPRECATED: Use configure() ou .env diretamente.
    
    Configure diretamente no .env:
        KAFKA_BACKEND=confluent
        KAFKA_BOOTSTRAP_SERVERS=kafka:9092
    
    Ou via código:
        from core.config import configure
        configure(kafka_backend="confluent")
    """
    warnings.warn(
        "configure_messaging() is deprecated. "
        "Use configure() from core.config instead, or set values in .env.",
        DeprecationWarning,
        stacklevel=2,
    )
    return configure(**kwargs)


# Alias para compatibilidade (deprecated)
MessagingSettings = type(get_settings()) if get_settings else None
