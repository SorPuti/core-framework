"""
Messaging configuration.

Usa o Settings centralizado automaticamente - não precisa configurar nada.
Basta definir no .env:

    KAFKA_ENABLED=true
    KAFKA_BACKEND=confluent
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092

E tudo funciona automaticamente.
"""

from __future__ import annotations

from core.config import get_settings


def get_messaging_settings():
    """
    Retorna configurações de messaging.
    
    Simplesmente retorna o Settings global que já carrega do .env.
    
    Exemplo:
        settings = get_messaging_settings()
        print(settings.kafka_backend)
        print(settings.kafka_bootstrap_servers)
    """
    return get_settings()


def configure_messaging(**kwargs):
    """
    DEPRECATED: Não precisa mais chamar isso.
    
    Configure diretamente no .env:
        KAFKA_BACKEND=confluent
        KAFKA_BOOTSTRAP_SERVERS=kafka:9092
    
    Ou se precisar via código:
        from core import configure
        configure(kafka_backend="confluent")
    """
    from core.config import configure
    return configure(**kwargs)


# Alias para compatibilidade
MessagingSettings = type(get_settings())
