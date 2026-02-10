"""
Settings system. Docs: https://github.com/your-org/core-framework/docs/02-settings.md

Single source of truth: src/settings.py

Usage:
    from core.config import Settings, configure
    
    class AppSettings(Settings):
        user_model: str = "app.models.User"
    
    settings = configure(settings_class=AppSettings)
"""

import logging
import os
import secrets
import warnings
from importlib import import_module
from pathlib import Path
from typing import Any, Literal, Self, TypeVar, cast, overload

from pydantic import Field as PydanticField, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("core.config")

# TypeVar para get_settings() genérico - permite autocomplete de subclasses
_SettingsT = TypeVar("_SettingsT", bound="Settings")


# =========================================================================
# ENV FILE RESOLUTION (carregado apenas no bootstrap)
# =========================================================================

def _resolve_env_files_at_bootstrap() -> tuple[str, ...]:
    """
    Resolve .env files baseado em ENVIRONMENT.
    
    Chamado APENAS no bootstrap (uma vez).
    Não deve ser chamado em runtime.
    
    Precedência:
    1. OS env vars
    2. .env.{ENVIRONMENT}
    3. .env
    4. Settings defaults
    """
    env = os.environ.get("ENVIRONMENT", "development")
    files: list[str] = []
    
    if Path(".env").is_file():
        files.append(".env")
    
    env_file = f".env.{env}"
    if Path(env_file).is_file():
        files.append(env_file)
    
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
    
    # --- Chaves e Tokens ---
    
    auth_secret_key: str | None = PydanticField(
        default=None,
        description="Chave secreta para tokens (usa secret_key se None)",
    )
    auth_algorithm: str = PydanticField(
        default="HS256",
        description="Algoritmo JWT (HS256, HS384, HS512, RS256, etc.)",
    )
    auth_access_token_expire_minutes: int = PydanticField(
        default=30,
        description="Tempo de expiração do access token em minutos",
    )
    auth_refresh_token_expire_days: int = PydanticField(
        default=7,
        description="Tempo de expiração do refresh token em dias",
    )
    
    # --- User Model ---
    
    user_model: str | None = PydanticField(
        default=None,
        description=(
            "Path do modelo User (ex: 'src.apps.users.models.User'). "
            "Obrigatório para autenticação funcionar."
        ),
    )
    auth_username_field: str = PydanticField(
        default="email",
        description="Campo usado como username para login (email, username, cpf, etc.)",
    )
    
    # --- Backends ---
    
    auth_backends: list[str] = PydanticField(
        default=["model"],
        description=(
            "Lista de backends de autenticação a tentar (em ordem). "
            "Opções: model, oauth, ldap, token, api_key"
        ),
    )
    auth_backend: str = PydanticField(
        default="model",
        description="Backend de autenticação padrão (model, oauth, ldap)",
    )
    auth_token_backend: str = PydanticField(
        default="jwt",
        description="Backend de tokens (jwt, opaque, redis)",
    )
    auth_permission_backend: str = PydanticField(
        default="default",
        description="Backend de permissões (default, rbac, abac)",
    )
    
    # --- Password Hashing ---
    
    auth_password_hasher: str = PydanticField(
        default="pbkdf2_sha256",
        description="Algoritmo de hash de senha (pbkdf2_sha256, argon2, bcrypt, scrypt)",
    )
    auth_password_min_length: int = PydanticField(
        default=8,
        description="Comprimento mínimo da senha",
    )
    auth_password_require_uppercase: bool = PydanticField(
        default=False,
        description="Exigir pelo menos uma letra maiúscula na senha",
    )
    auth_password_require_lowercase: bool = PydanticField(
        default=False,
        description="Exigir pelo menos uma letra minúscula na senha",
    )
    auth_password_require_digit: bool = PydanticField(
        default=False,
        description="Exigir pelo menos um dígito na senha",
    )
    auth_password_require_special: bool = PydanticField(
        default=False,
        description="Exigir pelo menos um caractere especial na senha",
    )
    
    # --- HTTP Headers ---
    
    auth_header: str = PydanticField(
        default="Authorization",
        description="Nome do header HTTP para autenticação",
    )
    auth_scheme: str = PydanticField(
        default="Bearer",
        description="Scheme de autenticação (Bearer, Basic, Token)",
    )
    
    # --- Middleware ---
    
    auth_warn_missing_middleware: bool = PydanticField(
        default=True,
        description="Emitir warning se AuthenticationMiddleware não estiver configurado",
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
    avro_default_namespace: str = PydanticField(
        default="com.core.events",
        description="Namespace padrão para schemas Avro (ex: com.mycompany.events)",
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
        description=(
            "URL de conexão Redis. Formatos suportados:\n"
            "- Standalone: redis://host:6379/0\n"
            "- Cluster: redis://node1:6379,node2:6379,node3:6379 (com redis_mode='cluster')\n"
            "- Sentinel: redis://sentinel1:26379,sentinel2:26379 (com redis_mode='sentinel')"
        ),
    )
    redis_mode: Literal["standalone", "cluster", "sentinel"] = PydanticField(
        default="standalone",
        description="Modo de conexão Redis: standalone, cluster ou sentinel",
    )
    redis_sentinel_master: str = PydanticField(
        default="mymaster",
        description="Nome do master para Redis Sentinel",
    )
    redis_max_connections: int = PydanticField(
        default=10,
        description="Máximo de conexões no pool",
    )
    redis_socket_timeout: float = PydanticField(
        default=5.0,
        description="Timeout de socket em segundos",
    )
    redis_stream_max_len: int = PydanticField(
        default=10000,
        description="Tamanho máximo de streams Redis (MAXLEN)",
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

# Instância global única (configurada via configure() ou bootstrap)
_settings: Settings | None = None
_settings_class: type[Settings] = Settings


def bootstrap_project_settings() -> None:
    """
    Bootstrap settings importando src.settings.
    
    Ordem de resolução (fail-fast):
    1. APP_SETTINGS_MODULE env var (se definido)
    2. src.settings (convenção padrão)
    3. Erro explícito se nenhum encontrado
    
    Não há fallbacks implícitos ou auto-discovery.
    """
    if is_configured():
        return

    # 1. Variável de ambiente explícita
    module_name = os.getenv("APP_SETTINGS_MODULE")
    if module_name:
        try:
            import_module(module_name)
            return
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"APP_SETTINGS_MODULE='{module_name}' not found. "
                f"Verify the module path is correct."
            ) from exc

    # 2. Convenção padrão: src.settings
    try:
        import_module("src.settings")
        return
    except ModuleNotFoundError:
        pass

    # 3. Fail-fast: não há fonte de configuração
    raise RuntimeError(
        "No settings module found. Create 'src/settings.py' with your configuration.\n"
        "Example:\n"
        "  from core.config import Settings, configure\n"
        "  class AppSettings(Settings):\n"
        "      user_model: str = 'app.models.User'\n"
        "  settings = configure(settings_class=AppSettings)"
    )

def _configure_auth_from_settings() -> None:
    """
    Configura auth baseado em settings.user_model.
    
    Chamado APENAS no bootstrap, após carregar settings.
    Fail-fast: erro explícito se user_model estiver mal configurado.
    """
    from core.auth.base import get_auth_config, configure_auth

    # Já configurado (configure_auth chamado explicitamente)
    if get_auth_config().user_model is not None:
        return

    # Obtém settings (já deve estar carregado)
    s = get_settings()
    if not hasattr(s, "user_model") or not s.user_model:
        # Sem user_model configurado - OK se não usar auth
        return

    user_model_path = s.user_model
    if not isinstance(user_model_path, str):
        raise TypeError(
            f"settings.user_model must be str, got {type(user_model_path).__name__}. "
            f"Example: user_model = 'app.models.User'"
        )

    try:
        module_path, class_name = user_model_path.rsplit(".", 1)
        module = import_module(module_path)
        User = getattr(module, class_name)
        configure_auth(user_model=User)
        logger.debug("Configured auth from settings.user_model: %s", user_model_path)
    except ValueError as exc:
        raise ValueError(
            f"Invalid user_model format: '{user_model_path}'. "
            f"Expected 'module.path.ClassName', got invalid format."
        ) from exc
    except (ImportError, ModuleNotFoundError) as exc:
        raise ImportError(
            f"Cannot import user_model '{user_model_path}': module not found. "
            f"Verify the module path is correct."
        ) from exc
    except AttributeError as exc:
        raise AttributeError(
            f"Cannot find class '{class_name}' in module '{module_path}'. "
            f"Verify the class name is correct."
        ) from exc


@overload
def get_settings() -> Settings: ...

@overload
def get_settings(settings_type: type[_SettingsT]) -> _SettingsT: ...

def get_settings(settings_type: type[_SettingsT] | None = None) -> Settings | _SettingsT:
    """
    Retorna a instância global de Settings.
    
    Se settings ainda não foi carregado, executa bootstrap uma vez.
    Após o bootstrap inicial, apenas retorna o valor cacheado.
    
    Args:
        settings_type: Classe de Settings para cast de tipo (opcional).
                       Usado apenas para inferência estática, não afeta runtime.
    
    Returns:
        Settings instance (singleton), tipado como a classe passada se fornecida.
    
    Raises:
        RuntimeError: Se bootstrap falhar (src.settings não encontrado)
    """
    global _settings

    if _settings is not None:
        if settings_type is not None:
            return cast(_SettingsT, _settings)
        return _settings

    bootstrap_project_settings()

    if _settings is None:
        env_files = _resolve_env_files_at_bootstrap()
        _settings = _settings_class(_env_file=env_files)
        logger.warning(
            "Settings not explicitly configured. Using default Settings. "
            "Configure explicitly in src/settings.py via configure()."
        )

    # NOTA: Auto-configuração é executada em configure(), não aqui.
    # Se get_settings() é chamado antes de configure() (ex: import circular),
    # o bootstrap carrega src.settings que chama configure() internamente.

    if settings_type is not None:
        return cast(_SettingsT, _settings)
    return _settings


# =========================================================================
# Auto-configuration helpers (plug-and-play)
# =========================================================================
#
# Sistema de auto-configuração: basta definir valores no Settings e todos
# os subsistemas são configurados automaticamente. Zero configuração explícita.
#
# Ordem de configuração (respeitando dependências):
#   1. DateTime (sem dependências)
#   2. Models (pré-carrega para resolver relacionamentos)
#   3. Auth (depende de models)
#   4. Kafka/Messaging (sem dependências, mas opcional)
#   5. Tasks (depende de kafka se habilitado)
#
# =========================================================================

_datetime_configured = False
_auth_configured = False
_kafka_configured = False
_tasks_configured = False
_models_loaded = False


def _auto_configure_datetime(settings: Settings) -> bool:
    """
    Auto-configura o sistema de DateTime a partir das Settings.
    
    Configurado automaticamente quando:
    - timezone != "UTC" (valor padrão)
    - OU use_tz está definido
    - OU qualquer formato de data/hora customizado
    
    Returns:
        True se configurado, False se já estava ou falhou
    """
    global _datetime_configured
    
    if _datetime_configured:
        return False
    
    try:
        from core.datetime import configure_datetime
        
        configure_datetime(
            default_timezone=settings.timezone,
            use_aware_datetimes=settings.use_tz,
            datetime_format=settings.datetime_format,
            date_format=settings.date_format,
            time_format=settings.time_format,
        )
        _datetime_configured = True
        logger.debug("DateTime auto-configured (timezone=%s)", settings.timezone)
        return True
    except ImportError:
        # core.datetime não existe - OK, módulo opcional
        return False
    except Exception as e:
        logger.warning("Failed to auto-configure DateTime: %s", e)
        return False


def _auto_configure_models(settings: Settings) -> bool:
    """
    Pré-carrega o módulo de models para registrar todos no SQLAlchemy.
    
    Isso é CRÍTICO para resolver relacionamentos circulares como:
        User → relationship("workspaces.WorkspaceUser") → WorkspaceUser
    
    Sem pré-carregar, WorkspaceUser não existiria no registry quando
    User fosse importado, causando erro de relacionamento.
    
    Returns:
        True se carregou models, False se já estava ou falhou
    """
    global _models_loaded
    
    if _models_loaded:
        return False
    
    models_module = getattr(settings, "models_module", None)
    if not models_module:
        return False
    
    # Suporta string única ou lista de módulos
    modules = [models_module] if isinstance(models_module, str) else list(models_module)
    
    loaded_any = False
    for module_path in modules:
        try:
            import_module(module_path)
            logger.debug("Pre-loaded models module: %s", module_path)
            loaded_any = True
        except ImportError as e:
            # Não é erro crítico - o módulo pode não existir ainda
            logger.debug(
                "Could not pre-load models module '%s': %s (continuing)",
                module_path, e
            )
    
    _models_loaded = loaded_any
    return loaded_any


def _auto_configure_auth(settings: Settings) -> bool:
    """
    Auto-configura o sistema de Auth a partir das Settings.
    
    Configurado automaticamente quando:
    - user_model está definido no Settings
    
    IMPORTANTE: Requer que models já tenham sido pré-carregados
    para resolver relacionamentos corretamente.
    
    Returns:
        True se configurado, False se já estava, não aplicável, ou falhou
    """
    global _auth_configured
    
    if _auth_configured:
        return False
    
    # Verifica se user_model está configurado
    if not settings.user_model:
        logger.debug("Auth: skipped (user_model not set)")
        return False
    
    try:
        from core.auth import configure_auth as _configure_auth
        
        # Resolve user_model string para classe
        user_class = _resolve_user_model(settings.user_model)
        if user_class is None:
            logger.warning(
                "Auth: could not resolve user_model '%s'",
                settings.user_model
            )
            return False
        
        # Configura auth com todos os valores das Settings
        _configure_auth(
            # Chaves e Tokens
            secret_key=settings.auth_secret_key or settings.secret_key,
            jwt_algorithm=settings.auth_algorithm,
            access_token_expire_minutes=settings.auth_access_token_expire_minutes,
            refresh_token_expire_days=settings.auth_refresh_token_expire_days,
            # User Model
            user_model=user_class,
            username_field=settings.auth_username_field,
            # Backends
            auth_backends=settings.auth_backends,
            auth_backend=settings.auth_backend,
            token_backend=settings.auth_token_backend,
            permission_backend=settings.auth_permission_backend,
            # Password
            password_hasher=settings.auth_password_hasher,
            password_min_length=settings.auth_password_min_length,
            password_require_uppercase=settings.auth_password_require_uppercase,
            password_require_lowercase=settings.auth_password_require_lowercase,
            password_require_digit=settings.auth_password_require_digit,
            password_require_special=settings.auth_password_require_special,
            # HTTP Headers
            auth_header=settings.auth_header,
            auth_scheme=settings.auth_scheme,
            # Middleware
            warn_missing_middleware=settings.auth_warn_missing_middleware,
        )
        _auth_configured = True
        logger.debug("Auth auto-configured (user_model=%s)", settings.user_model)
        return True
    except ImportError:
        # core.auth não existe - OK, módulo opcional
        return False
    except Exception as e:
        logger.warning("Failed to auto-configure Auth: %s", e)
        return False


def _auto_configure_kafka(settings: Settings) -> bool:
    """
    Auto-configura o sistema de Kafka/Messaging a partir das Settings.
    
    Configurado automaticamente quando:
    - kafka_enabled = True
    
    O sistema de messaging já lê diretamente do Settings, então esta
    função apenas valida e registra que foi configurado.
    
    Returns:
        True se configurado, False se já estava, não aplicável, ou falhou
    """
    global _kafka_configured
    
    if _kafka_configured:
        return False
    
    if not settings.kafka_enabled:
        logger.debug("Kafka: skipped (kafka_enabled=False)")
        return False
    
    try:
        # Valida configuração básica
        if not settings.kafka_bootstrap_servers:
            logger.warning(
                "Kafka enabled but kafka_bootstrap_servers not set. "
                "Set KAFKA_BOOTSTRAP_SERVERS in .env"
            )
            return False
        
        # O sistema de messaging já usa get_settings() internamente,
        # então não precisa de configuração explícita. Apenas validamos.
        _kafka_configured = True
        logger.debug(
            "Kafka auto-configured (backend=%s, servers=%s)",
            settings.kafka_backend,
            settings.kafka_bootstrap_servers,
        )
        return True
    except Exception as e:
        logger.warning("Failed to auto-configure Kafka: %s", e)
        return False


def _auto_configure_tasks(settings: Settings) -> bool:
    """
    Auto-configura o sistema de Tasks/Workers a partir das Settings.
    
    Configurado automaticamente quando:
    - task_enabled = True
    
    Returns:
        True se configurado, False se já estava, não aplicável, ou falhou
    """
    global _tasks_configured
    
    if _tasks_configured:
        return False
    
    if not settings.task_enabled:
        logger.debug("Tasks: skipped (task_enabled=False)")
        return False
    
    try:
        # O sistema de tasks já usa get_settings() internamente
        _tasks_configured = True
        logger.debug(
            "Tasks auto-configured (queue=%s, concurrency=%d)",
            settings.task_default_queue,
            settings.task_worker_concurrency,
        )
        return True
    except Exception as e:
        logger.warning("Failed to auto-configure Tasks: %s", e)
        return False


def _run_auto_configuration(settings: Settings) -> dict[str, bool]:
    """
    Executa auto-configuração de todos os subsistemas.
    
    Ordem de execução respeita dependências:
    1. DateTime (sem dependências)
    2. Models (pré-carrega para auth)
    3. Auth (depende de models)
    4. Kafka (sem dependências)
    5. Tasks (sem dependências diretas)
    
    Returns:
        Dict com status de cada subsistema configurado
    """
    results = {}
    
    # 1. DateTime - sempre primeiro, sem dependências
    results["datetime"] = _auto_configure_datetime(settings)
    
    # 2. Models - pré-carrega antes de auth
    results["models"] = _auto_configure_models(settings)
    
    # 3. Auth - depende de models carregados
    results["auth"] = _auto_configure_auth(settings)
    
    # 4. Kafka - independente
    results["kafka"] = _auto_configure_kafka(settings)
    
    # 5. Tasks - independente (mas pode usar kafka)
    results["tasks"] = _auto_configure_tasks(settings)
    
    # Log resumo
    configured = [k for k, v in results.items() if v]
    if configured:
        logger.info("Auto-configured subsystems: %s", ", ".join(configured))
    
    return results


# =========================================================================
# Funções públicas de verificação de estado
# =========================================================================

def auto_configure_auth(settings: Settings | None = None) -> bool:
    """
    Auto-configura o sistema de Auth a partir das Settings.
    
    NOTA: Esta função é chamada automaticamente por configure().
    Você NÃO precisa chamá-la explicitamente.
    
    Mantida como API pública para casos onde você precisa forçar
    a reconfiguração ou verificar se auth foi configurado.
    
    Args:
        settings: Settings instance (usa get_settings() se None)
    
    Returns:
        True se configurado com sucesso, False se já configurado ou falhou
    """
    if settings is None:
        settings = get_settings()
    return _auto_configure_auth(settings)


def _resolve_user_model(user_model_path: str) -> type | None:
    """
    Resolve user_model string para classe.
    
    Args:
        user_model_path: Path como "src.apps.users.models.User"
    
    Returns:
        Classe do User ou None se não encontrada
    """
    try:
        module_path, class_name = user_model_path.rsplit(".", 1)
        module = import_module(module_path)
        return getattr(module, class_name, None)
    except (ValueError, ImportError, AttributeError) as e:
        logger.debug("Could not resolve user_model '%s': %s", user_model_path, e)
        return None


def is_auth_configured() -> bool:
    """Verifica se o sistema de auth foi configurado."""
    return _auth_configured


def is_datetime_configured() -> bool:
    """Verifica se o sistema de datetime foi configurado."""
    return _datetime_configured


def is_kafka_configured() -> bool:
    """Verifica se o sistema de kafka/messaging foi configurado."""
    return _kafka_configured


def is_tasks_configured() -> bool:
    """Verifica se o sistema de tasks foi configurado."""
    return _tasks_configured


def get_configured_subsystems() -> dict[str, bool]:
    """
    Retorna status de todos os subsistemas.
    
    Útil para debugging e health checks.
    
    Returns:
        Dict com nome do subsistema → bool configurado
    """
    return {
        "datetime": _datetime_configured,
        "models": _models_loaded,
        "auth": _auth_configured,
        "kafka": _kafka_configured,
        "tasks": _tasks_configured,
    }


def configure(
    settings_class: type[Settings] | None = None,
    **overrides: Any,
) -> Settings:
    """
    Configura o framework registrando a instância global de Settings.
    
    Auto-configura TODOS os subsistemas baseado nos valores do Settings:
    - DateTime (timezone, formatos)
    - Auth (se user_model definido)
    - Kafka (se kafka_enabled=True)
    - Tasks (se task_enabled=True)
    
    Você NÃO precisa chamar configure_auth(), configure_datetime(), etc.
    Basta definir os valores no Settings e tudo é configurado automaticamente.
    
    Args:
        settings_class: Classe de Settings customizada
        **overrides: Valores para sobrescrever (raramente usado)
    
    Returns:
        Settings instance (registrado globalmente)
    
    Raises:
        RuntimeError: Se configure() for chamado múltiplas vezes
    
    Exemplo:
        # src/settings.py
        from core.config import Settings, configure
        
        class AppSettings(Settings):
            # Auth - configurado automaticamente
            user_model: str = "src.apps.users.models.User"
            
            # Kafka - configurado automaticamente se enabled
            kafka_enabled: bool = True
            kafka_bootstrap_servers: str = "kafka:9092"
            
            # Tasks - configurado automaticamente se enabled
            task_enabled: bool = True
        
        settings = configure(settings_class=AppSettings)
        # Pronto! Auth, Kafka e Tasks já estão configurados.
    """
    global _settings, _settings_class
    
    if _settings is not None:
        raise RuntimeError(
            "configure() called multiple times. "
            "Settings can only be configured once during bootstrap."
        )
    
    if settings_class is not None:
        _settings_class = settings_class
    
    # Valida overrides
    if overrides:
        known_fields = set(_settings_class.model_fields.keys())
        unknown = set(overrides.keys()) - known_fields
        if unknown:
            raise ValueError(
                f"Unknown settings keys: {', '.join(sorted(unknown))}. "
                f"Check Settings class for available fields."
            )
    
    # Cria instância (lê .env uma vez aqui via Pydantic)
    env_files = _resolve_env_files_at_bootstrap()
    
    if overrides:
        _settings = _settings_class(_env_file=env_files, **overrides)
    else:
        _settings = _settings_class(_env_file=env_files)
    
    logger.debug("Settings configured: %s", _settings_class.__name__)
    
    # =========================================================================
    # Auto-configure ALL subsystems from Settings (plug-and-play)
    # =========================================================================
    # Ordem respeita dependências:
    # 1. DateTime (sem dependências)
    # 2. Models (pré-carrega para auth)
    # 3. Auth (depende de models)
    # 4. Kafka (independente)
    # 5. Tasks (independente)
    # =========================================================================
    
    _run_auto_configuration(_settings)
    
    return _settings


def is_configured() -> bool:
    """Verifica se o framework já foi configurado."""
    return _settings is not None


def reset_settings() -> None:
    """
    Reseta configurações para testes.
    
    Reseta:
    - Settings singleton
    - Todos os flags de auto-configuração (datetime, auth, kafka, tasks)
    
    AVISO: Apenas para testes. Não usar em production.
    """
    global _settings, _settings_class
    global _datetime_configured, _auth_configured, _kafka_configured, _tasks_configured, _models_loaded
    
    if _settings is not None and _settings.environment == "production":
        raise RuntimeError(
            "reset_settings() cannot be called in production. "
            "This function is for testing only."
        )
    
    _settings = None
    _settings_class = Settings
    
    # Reset todos os flags de auto-configuração
    _datetime_configured = False
    _auth_configured = False
    _kafka_configured = False
    _tasks_configured = False
    _models_loaded = False


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
