"""
Configurações centralizadas do framework.

Baseado em Pydantic Settings para validação e tipagem forte.
Suporta variáveis de ambiente e arquivos .env.

Uso:
    # settings.py do projeto
    from core import Settings
    
    class AppSettings(Settings):
        # Suas configurações customizadas
        stripe_api_key: str
        sendgrid_api_key: str
    
    settings = AppSettings()
    
    # Em qualquer lugar
    from core import get_settings
    settings = get_settings()
"""

from functools import lru_cache
from typing import Any, Literal

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
    
    Variáveis de ambiente são carregadas automaticamente:
        - DATABASE_URL -> database_url
        - SECRET_KEY -> secret_key
        - DEBUG -> debug
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
    
    # =========================================================================
    # Application
    # =========================================================================
    
    app_name: str = PydanticField(
        default="Core Framework App",
        description="Nome da aplicação",
    )
    app_version: str = PydanticField(
        default="0.1.0",
        description="Versão da aplicação",
    )
    environment: Literal["development", "staging", "production", "testing"] = PydanticField(
        default="development",
        description="Ambiente de execução",
    )
    debug: bool = PydanticField(
        default=False,
        description="Modo debug (NUNCA use em produção)",
    )
    secret_key: str = PydanticField(
        default="change-me-in-production",
        description="Chave secreta para criptografia e tokens",
    )
    
    # =========================================================================
    # Database
    # =========================================================================
    
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
    database_pool_timeout: int = PydanticField(
        default=30,
        description="Timeout para obter conexão do pool",
    )
    database_pool_recycle: int = PydanticField(
        default=3600,
        description="Tempo em segundos para reciclar conexões",
    )
    
    # =========================================================================
    # API
    # =========================================================================
    
    api_prefix: str = PydanticField(
        default="/api/v1",
        description="Prefixo das rotas da API",
    )
    docs_url: str | None = PydanticField(
        default="/docs",
        description="URL da documentação Swagger (None para desabilitar)",
    )
    redoc_url: str | None = PydanticField(
        default="/redoc",
        description="URL da documentação ReDoc (None para desabilitar)",
    )
    openapi_url: str | None = PydanticField(
        default="/openapi.json",
        description="URL do schema OpenAPI (None para desabilitar)",
    )
    
    # =========================================================================
    # CORS
    # =========================================================================
    
    cors_origins: list[str] = PydanticField(
        default=["*"],
        description="Origens permitidas para CORS",
    )
    cors_allow_credentials: bool = PydanticField(
        default=True,
        description="Permitir credenciais em CORS",
    )
    cors_allow_methods: list[str] = PydanticField(
        default=["*"],
        description="Métodos HTTP permitidos em CORS",
    )
    cors_allow_headers: list[str] = PydanticField(
        default=["*"],
        description="Headers permitidos em CORS",
    )
    
    # =========================================================================
    # Authentication
    # =========================================================================
    
    auth_secret_key: str | None = PydanticField(
        default=None,
        description="Chave secreta para tokens (usa secret_key se None)",
    )
    auth_algorithm: str = PydanticField(
        default="HS256",
        description="Algoritmo JWT",
    )
    auth_access_token_expire_minutes: int = PydanticField(
        default=30,
        description="Tempo de expiração do access token em minutos",
    )
    auth_refresh_token_expire_days: int = PydanticField(
        default=7,
        description="Tempo de expiração do refresh token em dias",
    )
    auth_password_hasher: str = PydanticField(
        default="pbkdf2_sha256",
        description="Algoritmo de hash de senha (pbkdf2_sha256, argon2, bcrypt, scrypt)",
    )
    
    # =========================================================================
    # DateTime / Timezone
    # =========================================================================
    
    timezone: str = PydanticField(
        default="UTC",
        description="Timezone padrão da aplicação",
    )
    use_tz: bool = PydanticField(
        default=True,
        description="Usar datetimes aware (com timezone)",
    )
    datetime_format: str = PydanticField(
        default="%Y-%m-%dT%H:%M:%S%z",
        description="Formato padrão de datetime",
    )
    date_format: str = PydanticField(
        default="%Y-%m-%d",
        description="Formato padrão de data",
    )
    time_format: str = PydanticField(
        default="%H:%M:%S",
        description="Formato padrão de hora",
    )
    
    # =========================================================================
    # Server
    # =========================================================================
    
    host: str = PydanticField(
        default="0.0.0.0",
        description="Host do servidor",
    )
    port: int = PydanticField(
        default=8000,
        description="Porta do servidor",
    )
    workers: int = PydanticField(
        default=1,
        description="Número de workers (use 1 em desenvolvimento)",
    )
    reload: bool = PydanticField(
        default=True,
        description="Auto-reload em desenvolvimento",
    )
    
    # =========================================================================
    # Performance
    # =========================================================================
    
    request_timeout: int = PydanticField(
        default=30,
        description="Timeout de requisições em segundos",
    )
    max_request_size: int = PydanticField(
        default=10 * 1024 * 1024,  # 10MB
        description="Tamanho máximo de requisição em bytes",
    )
    
    # =========================================================================
    # Logging
    # =========================================================================
    
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = PydanticField(
        default="INFO",
        description="Nível de log",
    )
    log_format: str = PydanticField(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Formato de log",
    )
    log_json: bool = PydanticField(
        default=False,
        description="Usar formato JSON para logs",
    )
    
    # =========================================================================
    # Database Replicas (Enterprise)
    # =========================================================================
    
    database_read_url: str | None = PydanticField(
        default=None,
        description="URL do banco de leitura (replica). Se None, usa database_url para tudo",
    )
    database_read_pool_size: int | None = PydanticField(
        default=None,
        description="Pool size para replica (default: 2x do write)",
    )
    database_read_max_overflow: int | None = PydanticField(
        default=None,
        description="Max overflow para replica (default: 2x do write)",
    )
    
    # =========================================================================
    # Multi-Tenancy (Enterprise)
    # =========================================================================
    
    tenancy_enabled: bool = PydanticField(
        default=False,
        description="Habilita multi-tenancy automático",
    )
    tenancy_field: str = PydanticField(
        default="workspace_id",
        description="Nome do campo de tenant nos models",
    )
    tenancy_user_attribute: str = PydanticField(
        default="workspace_id",
        description="Atributo do usuário que contém o tenant ID",
    )
    tenancy_header: str = PydanticField(
        default="X-Tenant-ID",
        description="Header HTTP para tenant ID (fallback)",
    )
    tenancy_require: bool = PydanticField(
        default=False,
        description="Se True, rejeita requests sem tenant",
    )
    
    # =========================================================================
    # Soft Delete (Enterprise)
    # =========================================================================
    
    soft_delete_field: str = PydanticField(
        default="deleted_at",
        description="Nome do campo de soft delete",
    )
    soft_delete_cascade: bool = PydanticField(
        default=False,
        description="Se True, soft delete em cascata para relacionamentos",
    )
    soft_delete_auto_filter: bool = PydanticField(
        default=True,
        description="Se True, filtra deletados automaticamente em queries",
    )
    
    # =========================================================================
    # UUID (Enterprise)
    # =========================================================================
    
    uuid_version: Literal["uuid4", "uuid7"] = PydanticField(
        default="uuid7",
        description="Versão de UUID padrão (uuid7 é time-sortable, melhor para PKs)",
    )
    
    # =========================================================================
    # Helpers
    # =========================================================================
    
    @property
    def has_read_replica(self) -> bool:
        """Verifica se replica de leitura está configurada."""
        return (
            self.database_read_url is not None 
            and self.database_read_url != self.database_url
        )
    
    @property
    def is_development(self) -> bool:
        """Verifica se está em desenvolvimento."""
        return self.environment == "development"
    
    @property
    def is_production(self) -> bool:
        """Verifica se está em produção."""
        return self.environment == "production"
    
    @property
    def is_testing(self) -> bool:
        """Verifica se está em testes."""
        return self.environment == "testing"
    
    @property
    def effective_auth_secret(self) -> str:
        """Retorna a chave secreta efetiva para auth."""
        return self.auth_secret_key or self.secret_key
    
    def get_database_url(self, sync: bool = False) -> str:
        """
        Retorna URL do banco de dados.
        
        Args:
            sync: Se True, retorna URL síncrona
        """
        url = self.database_url
        
        if sync:
            # Converte async para sync
            url = url.replace("+aiosqlite", "")
            url = url.replace("+asyncpg", "+psycopg2")
            url = url.replace("+aiomysql", "+pymysql")
        
        return url


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
