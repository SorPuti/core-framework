"""
Configurações da aplicação de exemplo.

ESTE é o único local de configuração da aplicação.
Todas as settings do framework + customizações ficam aqui.

Variáveis de ambiente carregadas automaticamente de:
    .env                (base)
    .env.development    (sobrescreve em dev)
    .env.production     (sobrescreve em prod)

user_model: pode ser definido aqui, em USER_MODEL env, ou em core.toml [core] user_model.
O framework auto-registra via configure_auth; configure_auth explícito é opcional.
"""
from core.config import Settings, PydanticField, configure


class AppSettings(Settings):
    """Configurações específicas da aplicação de exemplo."""
    
    user_model: str = "example.models.User"

    # Customizações específicas desta app
    jwt_secret: str = PydanticField(
        default="your-secret-key-change-in-production",
        description="Secret key para JWT da aplicação",
    )
    jwt_expiration_hours: int = PydanticField(
        default=24,
        description="Tempo de expiração do JWT em horas",
    )


# Registrar AppSettings globalmente no core-framework.
settings = configure(settings_class=AppSettings)
