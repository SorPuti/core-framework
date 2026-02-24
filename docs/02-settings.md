# Settings

Configuração centralizada e plug-and-play. Defina valores no Settings e todos os subsistemas são configurados automaticamente.

## Arquitetura Plug-and-Play

```mermaid
flowchart TB
    subgraph Settings["src/settings.py"]
        CFG[AppSettings]
    end
    
    subgraph Auto["Auto-configuração"]
        DT[DateTime]
        AUTH[Auth]
        KAFKA[Kafka]
        TASKS[Tasks]
        MW[Middleware]
    end
    
    CFG --> |configure| DT
    CFG --> |user_model| AUTH
    CFG --> |kafka_enabled| KAFKA
    CFG --> |task_enabled| TASKS
    CFG --> |middleware| MW
    
    style CFG fill:#c8e6c9
    style Auto fill:#e3f2fd
```

**Zero configuração explícita**: Você NÃO precisa chamar `configure_auth()`, `configure_datetime()`, etc. Basta definir no Settings.

## Prioridade de Configuração

```mermaid
flowchart LR
    subgraph Priority["Prioridade (alta → baixa)"]
        ENV[OS Environment]
        ENVF[".env.{ENV}"]
        ENVB[".env"]
        DEF[Class Defaults]
    end
    
    ENV --> |sobrescreve| ENVF
    ENVF --> |sobrescreve| ENVB
    ENVB --> |sobrescreve| DEF
    
    style ENV fill:#ffcdd2
    style DEF fill:#e8f5e9
```

## Setup Básico

```python
# src/settings.py
from core.config import Settings, PydanticField, configure

class AppSettings(Settings):
    # ══════════════════════════════════════════════════════════════════
    # Aplicação
    # ══════════════════════════════════════════════════════════════════
    app_name: str = "Minha API"
    app_version: str = "1.0.0"
    
    # ══════════════════════════════════════════════════════════════════
    # Auth - configurado AUTOMATICAMENTE quando user_model está definido
    # ══════════════════════════════════════════════════════════════════
    user_model: str = "src.apps.users.models.User"
    models_module: str = "src.apps"
    
    # ══════════════════════════════════════════════════════════════════
    # Kafka - configurado AUTOMATICAMENTE quando kafka_enabled=True
    # ══════════════════════════════════════════════════════════════════
    kafka_enabled: bool = True
    kafka_bootstrap_servers: str = "kafka:9092"
    
    # ══════════════════════════════════════════════════════════════════
    # Tasks - configurado AUTOMATICAMENTE quando task_enabled=True
    # ══════════════════════════════════════════════════════════════════
    task_enabled: bool = True
    
    # ══════════════════════════════════════════════════════════════════
    # Campos customizados
    # ══════════════════════════════════════════════════════════════════
    stripe_key: str = PydanticField(default="", description="Stripe API key")

# Configura TUDO automaticamente
settings = configure(settings_class=AppSettings)
```

## Arquivos de Ambiente

```bash
# .env (base)
DATABASE_URL=postgresql+asyncpg://localhost/mydb
SECRET_KEY=dev-secret
DEBUG=true

# .env.production (sobrescreve em production)
ENVIRONMENT=production
DEBUG=false
DATABASE_POOL_SIZE=20
SECRET_KEY=super-secret-production-key
```

## Múltiplos Servidores (Cluster)

### Kafka - Múltiplos Brokers

Use vírgula para separar múltiplos servidores:

```python
# src/settings.py
class AppSettings(Settings):
    kafka_bootstrap_servers: str = "kafka1:9092,kafka2:9092,kafka3:9092"
```

```bash
# .env
KAFKA_BOOTSTRAP_SERVERS=kafka1:9092,kafka2:9092,kafka3:9092
```

### Redis - Cluster e Sentinel

O sistema suporta três modos de conexão Redis:

```python
class AppSettings(Settings):
    # ══════════════════════════════════════════════════════════════════
    # Standalone (padrão)
    # ══════════════════════════════════════════════════════════════════
    redis_url: str = "redis://localhost:6379/0"
    redis_mode: str = "standalone"
    
    # ══════════════════════════════════════════════════════════════════
    # Cluster - múltiplos nós
    # ══════════════════════════════════════════════════════════════════
    redis_url: str = "redis://node1:6379,node2:6379,node3:6379"
    redis_mode: str = "cluster"
    
    # ══════════════════════════════════════════════════════════════════
    # Sentinel - alta disponibilidade
    # ══════════════════════════════════════════════════════════════════
    redis_url: str = "redis://sentinel1:26379,sentinel2:26379"
    redis_mode: str = "sentinel"
    redis_sentinel_master: str = "mymaster"
```

```bash
# .env - Standalone
REDIS_URL=redis://localhost:6379/0
REDIS_MODE=standalone

# .env - Cluster
REDIS_URL=redis://redis1:6379,redis2:6379,redis3:6379
REDIS_MODE=cluster

# .env - Sentinel
REDIS_URL=redis://sentinel1:26379,sentinel2:26379
REDIS_MODE=sentinel
REDIS_SENTINEL_MASTER=mymaster
```

### Database - Múltiplas Replicas

```python
class AppSettings(Settings):
    # Primary (escrita)
    database_url: str = "postgresql+asyncpg://user:pass@primary:5432/db"
    
    # Replica (leitura) - pode ser load balancer para múltiplas replicas
    database_read_url: str = "postgresql+asyncpg://user:pass@replica-lb:5432/db"
```

```bash
# .env - Usando PgBouncer ou HAProxy como load balancer
DATABASE_URL=postgresql+asyncpg://user:pass@pgbouncer-primary:6432/db
DATABASE_READ_URL=postgresql+asyncpg://user:pass@pgbouncer-replica:6432/db
```

### Schema Registry - Múltiplas Instâncias

```python
class AppSettings(Settings):
    # Múltiplos Schema Registry (separados por vírgula)
    kafka_schema_registry_url: str = "http://sr1:8081,http://sr2:8081"
```

```bash
# .env
KAFKA_SCHEMA_REGISTRY_URL=http://schema-registry1:8081,http://schema-registry2:8081
```

### Exemplo Completo de Produção

```bash
# .env.production

# Database Cluster
DATABASE_URL=postgresql+asyncpg://user:pass@pgbouncer-primary:6432/mydb
DATABASE_READ_URL=postgresql+asyncpg://user:pass@pgbouncer-replica:6432/mydb
DATABASE_POOL_SIZE=20
DATABASE_READ_POOL_SIZE=40

# Kafka Cluster
KAFKA_BOOTSTRAP_SERVERS=kafka1:9092,kafka2:9092,kafka3:9092
KAFKA_SCHEMA_REGISTRY_URL=http://sr1:8081,http://sr2:8081
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=SCRAM-SHA-256

# Redis Cluster
REDIS_URL=redis://redis1:6379,redis2:6379,redis3:6379
REDIS_MODE=cluster
REDIS_MAX_CONNECTIONS=50
```

## Verificar Status dos Subsistemas

```python
from core.config import get_configured_subsystems

status = get_configured_subsystems()
# {
#     'datetime': True,
#     'models': True,
#     'auth': True,
#     'storage': True,
#     'kafka': True,
#     'tasks': True
# }
```

---

## Referência Completa de Settings

### Application

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `app_name` | `str` | `"Core Framework App"` | Nome da aplicação exibido na documentação |
| `app_version` | `str` | `"0.1.0"` | Versão da aplicação |
| `environment` | `Literal` | `"development"` | Ambiente: `development`, `staging`, `production`, `testing` |
| `debug` | `bool` | `False` | Modo debug. **NUNCA use em produção** |
| `secret_key` | `str` | auto-gerado | Chave secreta para criptografia. **Obrigatória em production** |
| `auto_create_tables` | `bool` | `False` | Cria tabelas no startup. Use migrations em produção |

### Validation

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `strict_validation` | `bool` | `True` | Validação rigorosa de schemas contra models |
| `validation_fail_fast` | `bool \| None` | `None` | Falha no primeiro erro. `None` = usa valor de DEBUG |

### Database

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `database_url` | `str` | `sqlite+aiosqlite:///./app.db` | URL de conexão async |
| `database_echo` | `bool` | `False` | Log de queries SQL |
| `database_pool_size` | `int` | `5` | Tamanho do pool de conexões |
| `database_max_overflow` | `int` | `10` | Conexões extras além do pool |
| `database_pool_timeout` | `int` | `30` | Timeout para obter conexão (segundos) |
| `database_pool_recycle` | `int` | `3600` | Tempo para reciclar conexões (segundos) |

### Database Replicas

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `database_read_url` | `str \| None` | `None` | URL do banco de leitura (replica) |
| `database_read_pool_size` | `int \| None` | `None` | Pool size para replica (default: 2x write) |
| `database_read_max_overflow` | `int \| None` | `None` | Max overflow para replica (default: 2x write) |

### Storage / File Uploads

**Arquitetura inspirada em Django + django-storages (GoogleCloudStorage)**  
Você escolhe o backend via `storage_backend` e configura os detalhes por settings, assim como no Django com `DEFAULT_FILE_STORAGE`, `GS_BUCKET_NAME`, `GS_CREDENTIALS`, etc.

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `storage_backend` | `Literal["local", "gcs"]` | `"local"` | Backend de storage de arquivos. `"local"` usa sistema de arquivos, `"gcs"` usa Google Cloud Storage (GCS) com bucket configurado |
| `storage_media_url` | `str \| None` | `None` | Base URL pública para servir arquivos. Ex: `"/media/"`, `"https://storage.googleapis.com/<bucket>/"` ou URL de CDN |
| `storage_local_media_root` | `str` | `"media"` | Diretório local (relativo ao projeto) para salvar arquivos quando `storage_backend="local"` |
| `storage_gcs_bucket_name` | `str \| None` | `None` | Nome do bucket GCS quando `storage_backend="gcs"`. Equivalente a `GS_BUCKET_NAME` no django-storages |
| `storage_gcs_project` | `str \| None` | `None` | ID do projeto GCP (opcional). Se `None`, usa o projeto das credenciais |
| `storage_gcs_credentials_file` | `str \| None` | `None` | Caminho para o JSON de Service Account do GCP. Se `None`, usa Application Default Credentials (ADC). Equivalente a `GS_CREDENTIALS` quando configurado via arquivo |
| `storage_gcs_default_acl` | `str \| None` | `"publicRead"` | ACL padrão dos blobs (`"publicRead"`, `"private"`, etc.). Equivalente a `GS_DEFAULT_ACL` |
| `storage_gcs_expiration_seconds` | `int` | `300` | Validade (segundos) de URLs assinadas geradas pelo backend GCS. Equivalente a `GS_EXPIRATION` (ex: 300 = 5 minutos) |

#### Exemplo: Storage Local (padrão)

```python
# src/settings.py
from core.config import Settings, configure


class AppSettings(Settings):
    # Storage local (files em disco)
    storage_backend: str = "local"
    storage_local_media_root: str = "media"
    storage_media_url: str = "/media/"


settings = configure(settings_class=AppSettings)
```

```bash
# .env
STORAGE_BACKEND=local
STORAGE_LOCAL_MEDIA_ROOT=media
STORAGE_MEDIA_URL=/media/
```

#### Exemplo: Google Cloud Storage (estilo Django)

Configuração equivalente ao uso do `GoogleCloudStorage` do `django-storages`:

```python
# Django (referência)
DEFAULT_FILE_STORAGE = "storages.backends.gcloud.GoogleCloudStorage"
GS_BUCKET_NAME = "minha-api-media"
MEDIA_URL = "https://storage.googleapis.com/minha-api-media/"
```

No Core Framework, o modelo de Settings faz esse papel:

```python
# src/settings.py
from core.config import Settings, configure


class AppSettings(Settings):
    # Storage: Google Cloud Storage
    storage_backend: str = "gcs"
    storage_gcs_bucket_name: str = "minha-api-media"
    storage_media_url: str = "https://storage.googleapis.com/minha-api-media/"

    # Opcional: projeto e credenciais explícitas
    storage_gcs_project: str | None = "meu-projeto-gcp"
    storage_gcs_credentials_file: str | None = "config/gcp-service-account.json"
    storage_gcs_default_acl: str | None = "publicRead"
    storage_gcs_expiration_seconds: int = 300  # 5 minutos (URLs assinadas)


settings = configure(settings_class=AppSettings)
```

```bash
# .env - Google Cloud Storage

# Seleciona backend GCS (equivalente a DEFAULT_FILE_STORAGE com GoogleCloudStorage)
STORAGE_BACKEND=gcs

# Bucket (equivalente a GS_BUCKET_NAME)
STORAGE_GCS_BUCKET_NAME=minha-api-media

# URL base pública (equivalente a MEDIA_URL em Django)
STORAGE_MEDIA_URL=https://storage.googleapis.com/minha-api-media/

# Projeto (opcional)
STORAGE_GCS_PROJECT=meu-projeto-gcp

# Caminho do JSON de Service Account (opcional se usar ADC)
STORAGE_GCS_CREDENTIALS_FILE=config/gcp-service-account.json

# ACL padrão (equivalente a GS_DEFAULT_ACL)
STORAGE_GCS_DEFAULT_ACL=publicRead

# Expiração de URLs assinadas (equivalente a GS_EXPIRATION)
STORAGE_GCS_EXPIRATION_SECONDS=300
```

**Comportamento plug-and-play**:

- **Local**: defina `STORAGE_BACKEND=local` e os arquivos serão gravados no diretório `STORAGE_LOCAL_MEDIA_ROOT`, servidos a partir de `STORAGE_MEDIA_URL` (por exemplo, via Nginx ou um endpoint de arquivos estáticos).
- **GCS**: troque para `STORAGE_BACKEND=gcs` e configure os campos `STORAGE_GCS_*`. O framework auto-configura o cliente GCS (se `google-cloud-storage` estiver instalado) e valida bucket/projeto, no mesmo espírito do `django-storages`.

### API

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `api_prefix` | `str` | `"/api/v1"` | Prefixo das rotas da API |
| `docs_url` | `str \| None` | `None` | URL do Swagger. Auto-habilitado em development |
| `redoc_url` | `str \| None` | `None` | URL do ReDoc. Auto-habilitado em development |
| `openapi_url` | `str \| None` | `None` | URL do schema OpenAPI |

### CORS

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `cors_origins` | `list[str]` | `[]` | Origens permitidas. Vazio = seguro |
| `cors_allow_credentials` | `bool` | `False` | Permitir cookies |
| `cors_allow_methods` | `list[str]` | `["*"]` | Métodos HTTP permitidos |
| `cors_allow_headers` | `list[str]` | `["*"]` | Headers permitidos |

### Authentication

#### Tokens e Chaves

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `auth_secret_key` | `str \| None` | `None` | Chave para tokens. Usa `secret_key` se None |
| `auth_algorithm` | `str` | `"HS256"` | Algoritmo JWT: HS256, HS384, HS512, RS256 |
| `auth_access_token_expire_minutes` | `int` | `30` | TTL do access token (minutos) |
| `auth_refresh_token_expire_days` | `int` | `7` | TTL do refresh token (dias) |

#### User Model

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `user_model` | `str \| None` | `None` | Path do modelo User. **Obrigatório para auth** |
| `auth_username_field` | `str` | `"email"` | Campo usado como username: email, username, cpf |

#### Backends

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `auth_backends` | `list[str]` | `["model"]` | Backends a tentar: model, oauth, ldap, token, api_key |
| `auth_backend` | `str` | `"model"` | Backend padrão |
| `auth_token_backend` | `str` | `"jwt"` | Backend de tokens: jwt, opaque, redis |
| `auth_permission_backend` | `str` | `"default"` | Backend de permissões: default, rbac, abac |

#### Password

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `auth_password_hasher` | `str` | `"pbkdf2_sha256"` | Hasher: pbkdf2_sha256, argon2, bcrypt, scrypt |
| `auth_password_min_length` | `int` | `8` | Comprimento mínimo |
| `auth_password_require_uppercase` | `bool` | `False` | Exigir maiúscula |
| `auth_password_require_lowercase` | `bool` | `False` | Exigir minúscula |
| `auth_password_require_digit` | `bool` | `False` | Exigir dígito |
| `auth_password_require_special` | `bool` | `False` | Exigir caractere especial |

#### HTTP

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `auth_header` | `str` | `"Authorization"` | Header HTTP para auth |
| `auth_scheme` | `str` | `"Bearer"` | Scheme: Bearer, Basic, Token |
| `auth_warn_missing_middleware` | `bool` | `True` | Warning se middleware não configurado |

### Middleware

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `middleware` | `list[str]` | `[]` | Lista de middlewares estilo Django |

**Shortcuts disponíveis:**
- `auth` → AuthenticationMiddleware
- `optional_auth` → OptionalAuthenticationMiddleware
- `timing` → TimingMiddleware
- `request_id` → RequestIDMiddleware
- `logging` → LoggingMiddleware
- `security_headers` → SecurityHeadersMiddleware
- `maintenance` → MaintenanceModeMiddleware

```python
# Exemplo
middleware: list[str] = [
    "timing",
    "auth",
    "core.middleware.LoggingMiddleware",
]
```

### DateTime / Timezone

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `timezone` | `str` | `"UTC"` | Timezone padrão da aplicação |
| `use_tz` | `bool` | `True` | Usar datetimes aware (com timezone) |
| `datetime_format` | `str` | `"%Y-%m-%dT%H:%M:%S%z"` | Formato de datetime |
| `date_format` | `str` | `"%Y-%m-%d"` | Formato de data |
| `time_format` | `str` | `"%H:%M:%S"` | Formato de hora |

### Server

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `host` | `str` | `"0.0.0.0"` | Host do servidor |
| `port` | `int` | `8000` | Porta |
| `workers` | `int` | `1` | Número de workers |
| `reload` | `bool` | `True` | Auto-reload em desenvolvimento |

### Performance

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `request_timeout` | `int` | `30` | Timeout de requisições (segundos) |
| `max_request_size` | `int` | `10485760` | Tamanho máximo de request (10MB); usado por `content_length_limit` |

### Security middleware

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `rate_limit_requests` | `int` | `100` | Máximo de requests por IP por janela (`rate_limit`) |
| `rate_limit_window_seconds` | `int` | `60` | Janela do rate limit (segundos) |
| `rate_limit_exclude_paths` | `list[str]` | `["/healthz", "/readyz", "/docs", ...]` | Paths excluídos do rate limit |
| `security_csp` | `str \| None` | `None` | Valor do header Content-Security-Policy (`security_headers`) |
| `security_headers_hsts` | `bool` | `False` | Habilitar HSTS em HTTPS |

### Logging

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `log_level` | `Literal` | `"INFO"` | Nível: DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `log_format` | `str` | `"%(asctime)s..."` | Formato de log |
| `log_json` | `bool` | `False` | Usar formato JSON |

### Multi-Tenancy

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `tenancy_enabled` | `bool` | `False` | Habilita multi-tenancy automático |
| `tenancy_field` | `str` | `"workspace_id"` | Campo de tenant nos models |
| `tenancy_user_attribute` | `str` | `"workspace_id"` | Atributo do usuário com tenant ID |
| `tenancy_header` | `str` | `"X-Tenant-ID"` | Header HTTP para tenant (fallback) |
| `tenancy_require` | `bool` | `False` | Rejeitar requests sem tenant |

### Soft Delete

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `soft_delete_field` | `str` | `"deleted_at"` | Nome do campo de soft delete |
| `soft_delete_cascade` | `bool` | `False` | Soft delete em cascata |
| `soft_delete_auto_filter` | `bool` | `True` | Filtrar deletados automaticamente |

### UUID

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `uuid_version` | `Literal` | `"uuid7"` | Versão: uuid4 ou uuid7 (time-sortable) |

### Kafka / Messaging

#### Básico

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `kafka_enabled` | `bool` | `False` | **Habilita Kafka** (auto-configura quando True) |
| `kafka_backend` | `Literal` | `"aiokafka"` | Backend: aiokafka (async) ou confluent (performance) |
| `kafka_bootstrap_servers` | `str` | `"localhost:9092"` | Servidores Kafka |
| `kafka_client_id` | `str` | `"core-framework"` | Client ID |
| `kafka_fire_and_forget` | `bool` | `False` | Não aguardar confirmação do broker |

#### Segurança

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `kafka_security_protocol` | `Literal` | `"PLAINTEXT"` | PLAINTEXT, SSL, SASL_PLAINTEXT, SASL_SSL |
| `kafka_sasl_mechanism` | `str \| None` | `None` | PLAIN, SCRAM-SHA-256, SCRAM-SHA-512 |
| `kafka_sasl_username` | `str \| None` | `None` | Usuário SASL |
| `kafka_sasl_password` | `str \| None` | `None` | Senha SASL |
| `kafka_ssl_cafile` | `str \| None` | `None` | Certificado CA |
| `kafka_ssl_certfile` | `str \| None` | `None` | Certificado cliente |
| `kafka_ssl_keyfile` | `str \| None` | `None` | Chave privada |

#### Producer

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `kafka_compression_type` | `Literal` | `"none"` | none, gzip, snappy, lz4, zstd |
| `kafka_linger_ms` | `int` | `0` | Tempo para acumular batch (ms) |
| `kafka_max_batch_size` | `int` | `16384` | Tamanho máximo do batch (bytes) |
| `kafka_request_timeout_ms` | `int` | `30000` | Timeout de requisição (ms) |
| `kafka_retry_backoff_ms` | `int` | `100` | Backoff entre retries (ms) |

#### Consumer

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `kafka_auto_offset_reset` | `Literal` | `"earliest"` | earliest, latest, none |
| `kafka_enable_auto_commit` | `bool` | `True` | Auto-commit de offsets |
| `kafka_auto_commit_interval_ms` | `int` | `5000` | Intervalo de auto-commit (ms) |
| `kafka_max_poll_records` | `int` | `500` | Máximo de registros por poll |
| `kafka_session_timeout_ms` | `int` | `10000` | Timeout de sessão (ms) |
| `kafka_heartbeat_interval_ms` | `int` | `3000` | Intervalo de heartbeat (ms) |

#### Schema Registry

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `kafka_schema_registry_url` | `str \| None` | `None` | URL do Schema Registry (Avro) |
| `avro_default_namespace` | `str` | `"com.core.events"` | Namespace padrão para schemas Avro |

#### Messaging Geral

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `messaging_default_topic` | `str` | `"events"` | Tópico padrão |
| `messaging_event_source` | `str` | `""` | Identificador de origem |
| `messaging_dead_letter_topic` | `str` | `"dead-letter"` | Tópico para mensagens com falha |

### Tasks / Workers

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `task_enabled` | `bool` | `False` | **Habilita Tasks** (auto-configura quando True) |
| `task_default_queue` | `str` | `"default"` | Fila padrão |
| `task_default_retry` | `int` | `3` | Número de retries |
| `task_default_retry_delay` | `int` | `60` | Delay entre retries (segundos) |
| `task_retry_backoff` | `bool` | `True` | Usar backoff exponencial |
| `task_default_timeout` | `int` | `300` | Timeout de task (segundos) |
| `task_worker_concurrency` | `int` | `4` | Tarefas concorrentes por worker |
| `task_result_backend` | `Literal` | `"none"` | Backend: none, redis, database |

### Redis

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `redis_url` | `str` | `"redis://localhost:6379/0"` | URL de conexão (múltiplos hosts separados por vírgula) |
| `redis_mode` | `Literal` | `"standalone"` | Modo: standalone, cluster, sentinel |
| `redis_sentinel_master` | `str` | `"mymaster"` | Nome do master para Sentinel |
| `redis_max_connections` | `int` | `10` | Máximo de conexões no pool |
| `redis_socket_timeout` | `float` | `5.0` | Timeout de socket (segundos) |
| `redis_stream_max_len` | `int` | `10000` | Tamanho máximo de streams (MAXLEN) |

### CLI / Discovery

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `migrations_dir` | `str` | `"./migrations"` | Diretório de migrations |
| `app_label` | `str` | `"main"` | Label da aplicação |
| `models_module` | `str` | `"app.models"` | Módulo dos models |
| `workers_module` | `str \| None` | `None` | Módulo dos workers (auto-discovery) |
| `tasks_module` | `str \| None` | `None` | Módulo das tasks (auto-discovery) |
| `app_module` | `str` | `"src.main"` | Módulo da aplicação principal |

### Health Check

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `health_check_enabled` | `bool` | `True` | Habilita /healthz e /readyz |

### Admin Panel

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `admin_enabled` | `bool` | `True` | Habilita admin panel |
| `admin_url_prefix` | `str` | `"/admin"` | Prefixo da URL |
| `admin_site_title` | `str` | `"Admin"` | Título na aba do browser |
| `admin_site_header` | `str` | `"Core Admin"` | Header no sidebar |
| `admin_theme` | `str` | `"default"` | Tema: default ou dark |
| `admin_logo_url` | `str \| None` | `None` | URL do logo custom |
| `admin_primary_color` | `str` | `"#3B82F6"` | Cor primária (hex) |
| `admin_custom_css` | `str \| None` | `None` | Path para CSS custom |
| `admin_cookie_secure` | `bool \| None` | `None` | Flag Secure do cookie. None = auto-detect |

### Operations Center

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `ops_enabled` | `bool` | `True` | Habilita Operations Center |
| `ops_task_persist` | `bool` | `True` | Persistir resultados de tasks |
| `ops_task_retention_days` | `int` | `30` | Dias para reter execuções |
| `ops_worker_heartbeat_interval` | `int` | `30` | Intervalo de heartbeat (segundos) |
| `ops_worker_offline_ttl` | `int` | `24` | Horas para manter workers offline |
| `auto_collect_permissions` | `bool` | `False` | Auto-gerar permissões CRUD |
| `ops_log_buffer_size` | `int` | `5000` | Tamanho do buffer de logs |
| `ops_log_stream_enabled` | `bool` | `True` | Habilita streaming de logs (SSE) |
| `ops_infrastructure_poll_interval` | `int` | `60` | Intervalo de métricas (segundos) |

---

## Acessando Settings

```python
from core.config import get_settings

# Sem tipo - retorna Settings base
settings = get_settings()
print(settings.database_url)

# Com tipo - autocomplete completo para campos customizados
from src.settings import AppSettings
settings = get_settings(AppSettings)
print(settings.stripe_key)  # ✅ PyCharm sugere
```

## Campos Customizados

```python
class AppSettings(Settings):
    # Com validação
    max_upload_mb: int = PydanticField(
        default=10,
        ge=1,
        le=100,
        description="Max upload size in MB"
    )
    
    # Lista de JSON
    allowed_ips: list[str] = PydanticField(
        default=["127.0.0.1"],
        description="Allowed IP addresses"
    )
```

```bash
# .env
MAX_UPLOAD_MB=50
ALLOWED_IPS='["10.0.0.1", "10.0.0.2"]'
```

## Exemplo Completo

```python
# src/settings.py
from core.config import Settings, PydanticField, configure

class AppSettings(Settings):
    # ══════════════════════════════════════════════════════════════════
    # Aplicação
    # ══════════════════════════════════════════════════════════════════
    app_name: str = "Minha API"
    app_version: str = "1.0.0"
    
    # ══════════════════════════════════════════════════════════════════
    # Auth (auto-configurado)
    # ══════════════════════════════════════════════════════════════════
    user_model: str = "src.apps.users.models.User"
    models_module: str = "src.apps"
    auth_password_hasher: str = "argon2"
    auth_password_min_length: int = 10
    auth_password_require_uppercase: bool = True
    auth_password_require_digit: bool = True
    
    # ══════════════════════════════════════════════════════════════════
    # Kafka (auto-configurado)
    # ══════════════════════════════════════════════════════════════════
    kafka_enabled: bool = True
    kafka_backend: str = "confluent"
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_schema_registry_url: str = "http://schema-registry:8081"
    avro_default_namespace: str = "com.mycompany.events"
    
    # ══════════════════════════════════════════════════════════════════
    # Tasks (auto-configurado)
    # ══════════════════════════════════════════════════════════════════
    task_enabled: bool = True
    task_worker_concurrency: int = 8
    task_result_backend: str = "redis"
    
    # ══════════════════════════════════════════════════════════════════
    # Multi-tenancy
    # ══════════════════════════════════════════════════════════════════
    tenancy_enabled: bool = True
    tenancy_field: str = "workspace_id"
    
    # ══════════════════════════════════════════════════════════════════
    # Middleware
    # ══════════════════════════════════════════════════════════════════
    middleware: list[str] = [
        "timing",
        "request_id",
        "auth",
        "logging",
    ]
    
    # ══════════════════════════════════════════════════════════════════
    # Admin
    # ══════════════════════════════════════════════════════════════════
    admin_site_title: str = "Minha Empresa"
    admin_site_header: str = "Painel Administrativo"
    admin_primary_color: str = "#10B981"  # green-500
    
    # ══════════════════════════════════════════════════════════════════
    # Campos customizados
    # ══════════════════════════════════════════════════════════════════
    stripe_api_key: str = PydanticField(default="", description="Stripe API Key")
    sendgrid_api_key: str = PydanticField(default="", description="SendGrid API Key")

settings = configure(settings_class=AppSettings)
```

## Próximos Passos

- [Models](03-models.md) — Modelos de banco de dados
- [Auth](05-auth.md) — Sistema de autenticação
- [Messaging](30-messaging.md) — Kafka e eventos
- [Admin](40-admin.md) — Painel administrativo
