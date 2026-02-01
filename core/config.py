"""
Configurações centralizadas do framework.

Baseado em Pydantic Settings para validação e tipagem forte.
Suporta variáveis de ambiente e arquivos .env.
"""

from functools import lru_cache
from typing import Any

from pydantic import Field as PydanticField
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configurações base do framework.
    
    Extenda esta classe para adicionar configurações específicas da aplicação.
    
    Exemplo:
        class AppSettings(Settings):
            api_key: str
            debug_mode: bool = False
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
    
    # Database
    database_url: str = PydanticField(
        default="sqlite+aiosqlite:///./app.db",
        description="URL de conexão do banco de dados (async)",
    )
    database_echo: bool = PydanticField(
        default=False,
        description="Habilita logging de SQL",
    )
    database_pool_size: int = PydanticField(
        default=5,
        description="Tamanho do pool de conexões",
    )
    database_max_overflow: int = PydanticField(
        default=10,
        description="Conexões extras além do pool",
    )
    
    # Application
    app_name: str = PydanticField(
        default="Core Framework App",
        description="Nome da aplicação",
    )
    debug: bool = PydanticField(
        default=False,
        description="Modo debug",
    )
    secret_key: str = PydanticField(
        default="change-me-in-production",
        description="Chave secreta para criptografia",
    )
    
    # API
    api_prefix: str = PydanticField(
        default="/api/v1",
        description="Prefixo das rotas da API",
    )
    docs_url: str | None = PydanticField(
        default="/docs",
        description="URL da documentação Swagger",
    )
    redoc_url: str | None = PydanticField(
        default="/redoc",
        description="URL da documentação ReDoc",
    )
    
    # CORS
    cors_origins: list[str] = PydanticField(
        default=["*"],
        description="Origens permitidas para CORS",
    )
    cors_allow_credentials: bool = PydanticField(
        default=True,
        description="Permitir credenciais em CORS",
    )
    
    # Performance
    request_timeout: int = PydanticField(
        default=30,
        description="Timeout de requisições em segundos",
    )


# Cache global de settings
_settings_cache: dict[type, Any] = {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Retorna instância singleton das configurações.
    
    Usa lru_cache para garantir uma única instância.
    """
    return Settings()


def get_settings_class[T: Settings](settings_class: type[T]) -> T:
    """
    Retorna instância de uma classe de settings customizada.
    
    Exemplo:
        class MySettings(Settings):
            custom_value: str
        
        settings = get_settings_class(MySettings)
    """
    if settings_class not in _settings_cache:
        _settings_cache[settings_class] = settings_class()
    return _settings_cache[settings_class]


def clear_settings_cache() -> None:
    """Limpa o cache de settings. Útil para testes."""
    _settings_cache.clear()
    get_settings.cache_clear()
