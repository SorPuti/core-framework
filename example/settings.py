"""
Configurações da aplicação de exemplo.

ESTE é o único local de configuração da aplicação.
Todas as settings do framework + customizações ficam aqui.

Variáveis de ambiente carregadas automaticamente de:
    .env                (base)
    .env.development    (sobrescreve em dev)
    .env.production     (sobrescreve em prod)
"""

from core.config import Settings, PydanticField


class AppSettings(Settings):
    """Configurações específicas da aplicação de exemplo."""
    
    # Customizações específicas desta app
    jwt_secret: str = PydanticField(
        default="your-secret-key-change-in-production",
        description="Secret key para JWT da aplicação",
    )
    jwt_expiration_hours: int = PydanticField(
        default=24,
        description="Tempo de expiração do JWT em horas",
    )


# Instância singleton — importada por toda a aplicação
settings = AppSettings()
