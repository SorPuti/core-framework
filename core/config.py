"""
Configurações centralizadas do framework.

UNICO local de configuração para toda a aplicação:
- Database, Auth, API, CORS
- Kafka (aiokafka ou confluent)
- Tasks, Workers
- Middleware, Logging
- CLI, Migrations, Discovery

Uso:
    # settings.py do projeto
    from core import Settings
    
    class AppSettings(Settings):
        # Suas configurações customizadas
        stripe_api_key: str = ""
        sendgrid_api_key: str = ""
    
    settings = AppSettings()

Configuração via .env:
    DATABASE_URL=postgresql+asyncpg://localhost/myapp
    KAFKA_BACKEND=confluent
    KAFKA_BOOTSTRAP_SERVERS=kafka:9092

Ou via código (antes de iniciar a app):
    from core import configure
    
    configure(
        kafka_backend="confluent",
        database_url="postgresql+asyncpg://localhost/myapp",
    )

Resolução de .env por ambiente:
    Precedência (maior para menor):
    1. Variáveis de ambiente do OS
    2. .env.{ENVIRONMENT} (ex: .env.production)
    3. .env (base)
    4. Defaults da classe Settings
"""

import logging
import os
import secrets
import warnings
from importlib import import_module
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field as PydanticField, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("core.config")


# =========================================================================
# ENV FILE RESOLUTION
# =========================================================================

def _resolve_env_files() -> tuple[str, ...]:
    """
    Resolve .env files baseado na variável ENVIRONMENT.
    
    Precedência (maior para menor):
    1. Variáveis de ambiente do OS (sempre lidas)
    2. .env.{environment} (ex: .env.production) — sobrescreve .env base
    3. .env (base)
    4. Defaults da classe Settings
    
    Returns:
        Tupla de paths de .env files para carregar
    """
    env = os.environ.get("ENVIRONMENT", "development")
    files: list[str] = []
    
    # Base .env (carregado primeiro, menor precedência)
    if Path(".env").is_file():
        files.append(".env")
    
    # Environment-specific .env (carregado depois, maior precedência)
    env_file = f".env.{env}"
    if Path(env_file).is_file():
        files.append(env_file)
    
    # Se nenhum arquivo existe, tenta .env mesmo assim (pydantic ignora se não existir)
    return tuple(files) if files else (".env",)


class Settings(BaseSettings):
    """
    Configurações centralizadas do framework.
    
    Todas as configurações em UM lugar:
    - App, Database, API, CORS
    - Auth (JWT, sessões)
    - Kafka (aiokafka/confluent)
    - Tasks, Workers
    - Middleware
    - CLI, Migrations, Discovery
    
    Exemplo:
        class AppSettings(Settings):
            # Suas configs customizadas
            stripe_api_key: str = ""
        
        settings = AppSettings()
    
    Variáveis de ambiente carregadas automaticamente:
        DATABASE_URL, KAFKA_BACKEND, SECRET_KEY, etc.
    
    Ambientes suportados (.env por ambiente):
        .env                  # Base (sempre carregado)
        .env.development      # Sobrescreve em development
        .env.production       # Sobrescreve em production
        .env.staging          # Sobrescreve em staging
        .env.testing          # Sobrescreve em testing
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
        default="__auto_generate__",
        description=(
            "Chave secreta para criptografia e tokens. "
            "OBRIGATÓRIA em production/staging. "
            "Em development/testing, auto-gerada se não configurada."
        ),
    )
    auto_create_tables: bool = PydanticField(
        default=False,
        description=(
            "Se True, cria tabelas automaticamente no startup. "
            "Use False em produção — prefira migrations."
        ),
    )
    
    # =========================================================================
    # Validation
    # =========================================================================
    
    strict_validation: bool = PydanticField(
        default=True,
        description=(
            "Habilita validação rigorosa de schemas contra models. "
            "Em modo strict, erros críticos (campo NOT NULL opcional no schema) "
            "causam falha no startup em DEBUG mode."
        ),
    )
    validation_fail_fast: bool | None = PydanticField(
        default=None,
        description=(
            "Se True, falha no primeiro erro de validação. "
            "Se None, usa valor de DEBUG."
        ),
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
        default=None,
        description=(
            "URL da documentação Swagger (None para desabilitar). "
            "Auto-habilitado em development se não configurado."
        ),
    )
    redoc_url: str | None = PydanticField(
        default=None,
        description=(
            "URL da documentação ReDoc (None para desabilitar). "
            "Auto-habilitado em development se não configurado."
        ),
    )
    openapi_url: str | None = PydanticField(
        default=None,
        description=(
            "URL do schema OpenAPI (None para desabilitar). "
            "Auto-habilitado em development se não configurado."
        ),
    )
    
    # =========================================================================
    # CORS
    # =========================================================================
    
    cors_origins: list[str] = PydanticField(
        default=[],
        description=(
            "Origens permitidas para CORS. "
            "Vazio por padrão (seguro). Configure explicitamente por ambiente."
        ),
    )
    cors_allow_credentials: bool = PydanticField(
        default=False,
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
    # Middleware (Django-style)
    # =========================================================================
    
    middleware: list[str] = PydanticField(
        default=[],
        description="""
        Lista de middlewares a aplicar, estilo Django.
        
        Formatos aceitos:
        - String path: "core.auth.AuthenticationMiddleware"
        - Shortcut: "auth", "timing", "logging", etc
        
        Exemplo:
            MIDDLEWARE='["timing", "auth", "core.middleware.LoggingMiddleware"]'
        
        Shortcuts disponíveis:
        - auth: AuthenticationMiddleware
        - optional_auth: OptionalAuthenticationMiddleware  
        - timing: TimingMiddleware
        - request_id: RequestIDMiddleware
        - logging: LoggingMiddleware
        - security_headers: SecurityHeadersMiddleware
        - maintenance: MaintenanceModeMiddleware
        """,
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
    # KAFKA / MESSAGING
    # Plug-and-play: troque backend sem mudar código
    # =========================================================================
    
    kafka_enabled: bool = PydanticField(
        default=False,
        description="Habilita sistema de mensageria Kafka",
    )
    kafka_backend: Literal["aiokafka", "confluent"] = PydanticField(
        default="aiokafka",
        description="Backend Kafka: aiokafka (async leve) ou confluent (alta performance)",
    )
    kafka_bootstrap_servers: str = PydanticField(
        default="localhost:9092",
        description="Servidores Kafka (separados por vírgula)",
    )
    kafka_fire_and_forget: bool = PydanticField(
        default=False,
        description="Se True, não aguarda confirmação do broker (mais rápido, menos confiável)",
    )
    kafka_schema_registry_url: str | None = PydanticField(
        default=None,
        description="URL do Schema Registry para Avro (apenas confluent)",
    )
    kafka_security_protocol: Literal["PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"] = PydanticField(
        default="PLAINTEXT",
        description="Protocolo de segurança Kafka",
    )
    kafka_sasl_mechanism: str | None = PydanticField(
        default=None,
        description="Mecanismo SASL (PLAIN, SCRAM-SHA-256, SCRAM-SHA-512)",
    )
    kafka_sasl_username: str | None = PydanticField(
        default=None,
        description="Usuário SASL",
    )
    kafka_sasl_password: str | None = PydanticField(
        default=None,
        description="Senha SASL",
    )
    kafka_ssl_cafile: str | None = PydanticField(
        default=None,
        description="Caminho do certificado CA",
    )
    kafka_ssl_certfile: str | None = PydanticField(
        default=None,
        description="Caminho do certificado cliente",
    )
    kafka_ssl_keyfile: str | None = PydanticField(
        default=None,
        description="Caminho da chave privada",
    )
    kafka_client_id: str = PydanticField(
        default="core-framework",
        description="Client ID do Kafka",
    )
    kafka_compression_type: Literal["none", "gzip", "snappy", "lz4", "zstd"] = PydanticField(
        default="none",
        description="Compressão de mensagens",
    )
    kafka_linger_ms: int = PydanticField(
        default=0,
        description="Tempo para acumular batch (ms)",
    )
    kafka_max_batch_size: int = PydanticField(
        default=16384,
        description="Tamanho máximo do batch (bytes)",
    )
    kafka_request_timeout_ms: int = PydanticField(
        default=30000,
        description="Timeout de requisição (ms)",
    )
    kafka_retry_backoff_ms: int = PydanticField(
        default=100,
        description="Backoff entre retries (ms)",
    )
    
    # Consumer settings
    kafka_auto_offset_reset: Literal["earliest", "latest", "none"] = PydanticField(
        default="earliest",
        description="Onde começar a consumir quando não há offset",
    )
    kafka_enable_auto_commit: bool = PydanticField(
        default=True,
        description="Auto-commit de offsets",
    )
    kafka_auto_commit_interval_ms: int = PydanticField(
        default=5000,
        description="Intervalo de auto-commit (ms)",
    )
    kafka_max_poll_records: int = PydanticField(
        default=500,
        description="Máximo de registros por poll",
    )
    kafka_session_timeout_ms: int = PydanticField(
        default=10000,
        description="Timeout de sessão do consumer (ms)",
    )
    kafka_heartbeat_interval_ms: int = PydanticField(
        default=3000,
        description="Intervalo de heartbeat (ms)",
    )
    
    # Messaging general
    messaging_default_topic: str = PydanticField(
        default="events",
        description="Tópico padrão para eventos",
    )
    messaging_event_source: str = PydanticField(
        default="",
        description="Identificador de origem dos eventos",
    )
    messaging_dead_letter_topic: str = PydanticField(
        default="dead-letter",
        description="Tópico para mensagens que falharam",
    )
    
    # =========================================================================
    # TASKS / WORKERS
    # =========================================================================
    
    task_enabled: bool = PydanticField(
        default=False,
        description="Habilita sistema de tasks",
    )
    task_default_queue: str = PydanticField(
        default="default",
        description="Fila padrão para tasks",
    )
    task_default_retry: int = PydanticField(
        default=3,
        description="Número padrão de retries",
    )
    task_default_retry_delay: int = PydanticField(
        default=60,
        description="Delay entre retries (segundos)",
    )
    task_retry_backoff: bool = PydanticField(
        default=True,
        description="Usar backoff exponencial",
    )
    task_default_timeout: int = PydanticField(
        default=300,
        description="Timeout padrão de task (segundos)",
    )
    task_worker_concurrency: int = PydanticField(
        default=4,
        description="Tarefas concorrentes por worker",
    )
    task_result_backend: Literal["none", "redis", "database"] = PydanticField(
        default="none",
        description="Onde armazenar resultados de tasks",
    )
    
    # =========================================================================
    # REDIS (para tasks, cache, etc)
    # =========================================================================
    
    redis_url: str = PydanticField(
        default="redis://localhost:6379/0",
        description="URL de conexão Redis",
    )
    redis_max_connections: int = PydanticField(
        default=10,
        description="Máximo de conexões no pool",
    )
    
    # =========================================================================
    # CLI / PROJECT DISCOVERY
    # Campos usados pelo CLI e pelo sistema de discovery de módulos.
    # Anteriormente dispersos em load_config() — agora centralizados.
    # =========================================================================
    
    migrations_dir: str = PydanticField(
        default="./migrations",
        description="Diretório de migrations do projeto",
    )
    app_label: str = PydanticField(
        default="main",
        description="Label da aplicação (usado em migrations e CLI)",
    )
    models_module: str = PydanticField(
        default="app.models",
        description="Módulo Python dos models (ex: 'myapp.models')",
    )
    workers_module: str | None = PydanticField(
        default=None,
        description="Módulo Python dos workers (None para auto-discovery)",
    )
    tasks_module: str | None = PydanticField(
        default=None,
        description="Módulo Python das tasks (None para auto-discovery)",
    )
    app_module: str = PydanticField(
        default="src.main",
        description="Módulo Python da aplicação principal (ex: 'myapp.main')",
    )
    
    # =========================================================================
    # HEALTH CHECK
    # =========================================================================
    
    health_check_enabled: bool = PydanticField(
        default=True,
        description="Habilita endpoints /healthz e /readyz automáticos",
    )
    
    # =========================================================================
    # ADMIN PANEL
    # =========================================================================
    
    admin_enabled: bool = PydanticField(
        default=True,
        description="Habilita o admin panel nativo",
    )
    admin_url_prefix: str = PydanticField(
        default="/admin",
        description=(
            "Prefixo da URL do admin panel. Customizável para segurança "
            "por obscuridade ou convenção interna. "
            'Ex: "/admin", "/backoffice", "/ops-c7a3e1b2"'
        ),
    )
    admin_site_title: str = PydanticField(
        default="Admin",
        description="Título exibido na aba do browser",
    )
    admin_site_header: str = PydanticField(
        default="Core Admin",
        description="Header exibido no sidebar do admin",
    )
    admin_theme: str = PydanticField(
        default="default",
        description='Tema visual: "default" ou "dark"',
    )
    admin_logo_url: str | None = PydanticField(
        default=None,
        description="URL do logo custom no sidebar (None para ícone padrão)",
    )
    admin_primary_color: str = PydanticField(
        default="#3B82F6",
        description="Cor primária do admin (hex). Default: blue-500",
    )
    admin_custom_css: str | None = PydanticField(
        default=None,
        description="Path para CSS customizado adicional (relativo ao projeto)",
    )
    admin_cookie_secure: bool | None = PydanticField(
        default=None,
        description=(
            "Flag Secure do cookie de sessao do admin. "
            "None = auto-detect pelo scheme do request (HTTPS → True, HTTP → False). "
            "True = forcar Secure (requer HTTPS). "
            "False = nunca Secure (uso local/Docker via HTTP)."
        ),
    )
    
    # =========================================================================
    # Operations Center
    # =========================================================================
    
    ops_enabled: bool = PydanticField(
        default=True,
        description="Enable the Operations Center in the admin panel",
    )
    ops_task_persist: bool = PydanticField(
        default=True,
        description="Persist task execution results to the database",
    )
    ops_task_retention_days: int = PydanticField(
        default=30,
        description="Days to retain task execution records before purge",
    )
    ops_worker_heartbeat_interval: int = PydanticField(
        default=30,
        description="Worker heartbeat interval in seconds",
    )
    ops_worker_offline_ttl: int = PydanticField(
        default=24,
        description="Hours to keep OFFLINE worker records before auto-cleanup (0 = disabled)",
    )
    auto_collect_permissions: bool = PydanticField(
        default=False,
        description="Auto-generate CRUD permissions for all models on startup (default: False)",
    )
    ops_log_buffer_size: int = PydanticField(
        default=5000,
        description="Maximum entries in the admin log ring buffer",
    )
    ops_log_stream_enabled: bool = PydanticField(
        default=True,
        description="Enable SSE log streaming endpoint",
    )
    ops_infrastructure_poll_interval: int = PydanticField(
        default=60,
        description="Infrastructure metrics poll interval in seconds",
    )
    
    # =========================================================================
    # VALIDATORS — Security & Environment-Aware Defaults
    # =========================================================================
    
    @model_validator(mode="after")
    def _apply_security_and_defaults(self) -> Self:
        """
        Aplica validações de segurança e defaults baseados no ambiente.
        
        Executado automaticamente após a criação do Settings:
        1. Valida/gera secret_key baseado no ambiente
        2. Auto-habilita docs em development
        3. Emite warnings para configurações inseguras
        """
        # -- Secret key: obrigatória em production/staging --
        if self.secret_key == "__auto_generate__":
            if self.environment in ("production", "staging"):
                raise ValueError(
                    "SECRET_KEY is required in production/staging environments. "
                    "Set SECRET_KEY in your .env file or as an environment variable."
                )
            # Auto-generate for development/testing
            generated = secrets.token_urlsafe(64)
            object.__setattr__(self, "secret_key", generated)
            logger.warning(
                "SECRET_KEY not configured — auto-generated random key for '%s'. "
                "This key changes on every restart. Set SECRET_KEY for persistent tokens.",
                self.environment,
            )
        
        # -- Auto-enable docs in development --
        if self.environment == "development":
            if self.docs_url is None:
                object.__setattr__(self, "docs_url", "/docs")
            if self.redoc_url is None:
                object.__setattr__(self, "redoc_url", "/redoc")
            if self.openapi_url is None:
                object.__setattr__(self, "openapi_url", "/openapi.json")
        
        # -- Warnings para configurações inseguras em production --
        if self.environment == "production":
            if self.debug:
                logger.warning(
                    "DEBUG=True in production environment. "
                    "This exposes sensitive information. Set DEBUG=False."
                )
            if "*" in self.cors_origins:
                logger.warning(
                    "CORS_ORIGINS contains '*' in production. "
                    "This allows any origin. Restrict to specific domains."
                )
            if self.auto_create_tables:
                logger.warning(
                    "AUTO_CREATE_TABLES=True in production. "
                    "Use migrations instead. Set AUTO_CREATE_TABLES=False."
                )
        
        return self
    
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


# =========================================================================
# GLOBAL SETTINGS SINGLETON
# =========================================================================

# Instância global única
_settings: Settings | None = None
_settings_class: type[Settings] = Settings

# Callbacks pós-carregamento
_on_settings_loaded: list[Any] = []


def bootstrap_project_settings() -> None:
    """Bootstrap project settings module using explicit resolution rules."""
    if is_configured():
        return

    module_name = os.getenv("APP_SETTINGS_MODULE")

    if module_name:
        _import_settings_module(module_name)
        return

    if _import_entrypoint_settings():
        return

    _import_legacy_src_settings()


def _import_settings_module(module_name: str) -> None:
    try:
        import_module(module_name)
    except ModuleNotFoundError as exc:
        logger.error(
            "Failed to import settings module '%s' from APP_SETTINGS_MODULE.",
            module_name,
            exc_info=exc,
        )


def _import_legacy_src_settings() -> bool:
    try:
        import_module("example.settings")
        return True
    except ModuleNotFoundError as exc:
        logger.error(
            "Legacy settings module 'src.settings' not found; "
            "default core Settings will be used.",
            exc_info=exc,
        )
        return False

def _import_entrypoint_settings() -> bool:
    try:
        eps = entry_points(group="core_framework.settings")
    except Exception:
        return False

    for ep in eps:
        try:
            ep.load()
            return True
        except Exception as exc:
            logger.error(
                "Failed to load settings from entrypoint '%s'.",
                ep.name,
                exc_info=exc,
            )

    return False

def get_settings() -> Settings:
    """Return the global Settings singleton after bootstrapping project settings."""
    global _settings

    if _settings is None:
        bootstrap_project_settings()

        env_files = _resolve_env_files()
        _settings = _settings_class(_env_file=env_files)

        for callback in _on_settings_loaded:
            callback(_settings)

    return _settings


def configure(
    settings_class: type[Settings] | None = None,
    **overrides: Any,
) -> Settings:
    """
    Configura o framework ANTES de iniciar a aplicação.
    
    IMPORTANTE: Chamar ANTES de criar a app ou importar componentes.
    
    Args:
        settings_class: Classe customizada de Settings (opcional)
        **overrides: Valores para sobrescrever
    
    Returns:
        Settings configurado
    
    Raises:
        ValueError: Se override key não existir na classe Settings
    
    Exemplo:
        from core import configure, Settings
        
        # Opção 1: Apenas sobrescrever valores
        configure(
            kafka_backend="confluent",
            kafka_bootstrap_servers="kafka:9092",
            database_url="postgresql+asyncpg://localhost/myapp",
        )
        
        # Opção 2: Usar classe customizada
        class MySettings(Settings):
            stripe_api_key: str = ""
        
        configure(settings_class=MySettings)
        
        # Opção 3: Ambos
        configure(
            settings_class=MySettings,
            kafka_backend="confluent",
        )
    """
    global _settings, _settings_class
    
    if settings_class is not None:
        _settings_class = settings_class
    
    # Valida que todas as override keys existem na classe Settings
    if overrides:
        known_fields = set(_settings_class.model_fields.keys())
        unknown = set(overrides.keys()) - known_fields
        if unknown:
            logger.warning(
                "Unknown settings keys passed to configure(): %s. "
                "Available keys: check Settings class fields.",
                ", ".join(sorted(unknown)),
            )
    
    # Resolve env files e cria instância
    env_files = _resolve_env_files()
    
    if overrides:
        _settings = _settings_class(_env_file=env_files, **overrides)
    else:
        _settings = _settings_class(_env_file=env_files)
    
    # Executa callbacks pós-carregamento
    for callback in _on_settings_loaded:
        callback(_settings)
    
    return _settings


def on_settings_loaded(callback: Any) -> Any:
    """
    Registra callback executado após Settings ser carregado.
    
    O callback recebe a instância de Settings como argumento.
    
    Exemplo:
        @on_settings_loaded
        def setup_logging(settings):
            logging.basicConfig(level=settings.log_level)
    """
    _on_settings_loaded.append(callback)
    return callback


def is_configured() -> bool:
    """Verifica se o framework já foi configurado."""
    return _settings is not None


def reset_settings() -> None:
    """
    Reseta configurações. Útil para testes.
    
    AVISO: Apenas para uso em testes. Em produção, este método
    emite um warning e não executa.
    """
    global _settings, _settings_class
    
    if _settings is not None and _settings.environment == "production":
        logger.warning(
            "reset_settings() called in production environment — ignored. "
            "This function is intended for testing only."
        )
        return
    
    _settings = None
    _settings_class = Settings


# =========================================================================
# ALIASES PARA COMPATIBILIDADE
# =========================================================================

def get_settings_class_instance[T: Settings](settings_class: type[T]) -> T:
    """
    Retorna instância de uma classe de settings customizada.
    
    Deprecated: Use configure(settings_class=MySettings) em vez disso.
    """
    warnings.warn(
        "get_settings_class_instance() is deprecated. "
        "Use configure(settings_class=MySettings) instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    global _settings, _settings_class
    if _settings is None or not isinstance(_settings, settings_class):
        _settings_class = settings_class
        _settings = settings_class()
    return _settings  # type: ignore


# Alias para compatibilidade
clear_settings_cache = reset_settings
