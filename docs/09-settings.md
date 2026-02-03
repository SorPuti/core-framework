# Settings

O sistema de configuracao e baseado em Pydantic Settings. Variaveis de ambiente sao carregadas automaticamente e validadas com tipagem forte.

## Estrutura de Arquivos

```
/my-project
  /.env                    # Variaveis de ambiente - NAO commitar
  /src
    /api
      config.py            # Classe de configuracao
    main.py
```

## Criar config.py

A classe `AppSettings` herda de `Settings` e define configuracoes especificas da aplicacao.

```python
# src/api/config.py
from core import Settings

class AppSettings(Settings):
    """
    Configuracoes da aplicacao.
    
    A classe base Settings ja fornece campos comuns:
    
    Aplicacao:
    - app_name, app_version, environment, debug, secret_key
    
    Banco de dados:
    - database_url, database_echo, database_pool_size,
      database_max_overflow, database_pool_timeout, database_pool_recycle
    
    API:
    - api_prefix, docs_url, redoc_url, openapi_url
    
    CORS:
    - cors_origins, cors_allow_credentials, cors_allow_methods, cors_allow_headers
    
    Auth:
    - auth_secret_key, auth_algorithm, auth_access_token_expire_minutes,
      auth_refresh_token_expire_days, auth_password_hasher
    
    DateTime:
    - timezone, use_tz, datetime_format, date_format, time_format
    
    Server:
    - host, port, workers, reload
    
    Logging:
    - log_level, log_format, log_json
    """
    
    # Campos customizados da sua aplicacao
    # Tipo define validacao automatica
    stripe_api_key: str = ""           # String vazia como padrao
    stripe_webhook_secret: str = ""
    sendgrid_api_key: str = ""
    aws_access_key: str = ""
    aws_secret_key: str = ""
    aws_bucket_name: str = "my-bucket"
    max_upload_size_mb: int = 10       # Inteiro com padrao
    
    # Campos de infraestrutura
    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap_servers: str = "localhost:9092"

# Instancia singleton - importe esta variavel em outros modulos
# A instancia e criada uma vez e reutilizada
settings = AppSettings()
```

**Comportamento de carregamento**: Ao instanciar `AppSettings()`, o Pydantic automaticamente:
1. Le o arquivo `.env` da raiz do projeto
2. Le variaveis de ambiente do sistema
3. Valida tipos e aplica valores padrao

## Criar .env

O arquivo `.env` define valores especificos do ambiente. Nunca commite este arquivo.

```env
# .env (na raiz do projeto)

# Aplicacao
APP_NAME=My API
APP_VERSION=1.0.0
ENVIRONMENT=development
DEBUG=true
SECRET_KEY=minha-chave-secreta-muito-longa-e-segura

# Banco de dados
# Formato: driver+asyncdriver://user:pass@host:port/database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/mydb
DATABASE_ECHO=false

# API
API_PREFIX=/api/v1

# Auth
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=30
AUTH_REFRESH_TOKEN_EXPIRE_DAYS=7
AUTH_PASSWORD_HASHER=pbkdf2_sha256

# Timezone
TIMEZONE=America/Sao_Paulo

# Server
HOST=0.0.0.0
PORT=8000

# Campos customizados - devem corresponder aos definidos na classe
STRIPE_API_KEY=sk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
SENDGRID_API_KEY=SG.xxx
AWS_ACCESS_KEY=AKIA...
AWS_SECRET_KEY=xxx
AWS_BUCKET_NAME=my-bucket
MAX_UPLOAD_SIZE_MB=10
REDIS_URL=redis://localhost:6379/0
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```

## Usar no Codigo

```python
# Em qualquer arquivo do projeto
from src.api.config import settings

# Acesso direto aos valores
print(settings.app_name)
print(settings.database_url)
print(settings.stripe_api_key)

# Propriedades auxiliares disponiveis
if settings.is_development:
    # Logica especifica de desenvolvimento
    print("Modo desenvolvimento")

if settings.is_production:
    # Logica especifica de producao
    print("Modo producao")

if settings.is_testing:
    # Logica especifica de testes
    print("Modo teste")
```

## Mapeamento .env para Python

A conversao de nomes segue regra simples: `NOME_MAIUSCULO` no .env vira `nome_minusculo` no Python.

| .env | config.py | Tipo |
|------|-----------|------|
| `APP_NAME=My API` | `settings.app_name` | str |
| `DEBUG=true` | `settings.debug` | bool |
| `PORT=8000` | `settings.port` | int |
| `CORS_ORIGINS=["*"]` | `settings.cors_origins` | list[str] |

**Conversao de tipos**: O Pydantic converte automaticamente strings do .env para o tipo declarado. `"true"` vira `True`, `"8000"` vira `8000`.

## Valores Padrao

Se uma variavel nao existir no .env, o valor padrao definido na classe e usado.

```python
class AppSettings(Settings):
    # Se STRIPE_API_KEY nao existir no .env, sera string vazia
    # Isso evita erro de inicializacao, mas a funcionalidade pode falhar
    stripe_api_key: str = ""
    
    # Se MAX_UPLOAD_SIZE_MB nao existir, sera 10
    max_upload_size_mb: int = 10
```

**Trade-off**: Valores padrao permitem inicializacao sem todas as variaveis, mas podem mascarar configuracoes faltantes. Em producao, considere tornar campos criticos obrigatorios.

## Campos Obrigatorios

Use `Field(...)` (ellipsis) para campos sem valor padrao. A aplicacao falha ao iniciar se o campo nao estiver definido.

```python
from pydantic import Field

class AppSettings(Settings):
    # Obrigatorio - aplicacao nao inicia sem este valor no .env
    # O erro e claro: "field required"
    stripe_api_key: str = Field(..., description="Chave da API Stripe")
    
    # Opcional com padrao
    debug: bool = False
```

**Quando usar obrigatorio**: Credenciais de servicos externos, chaves de API, configuracoes criticas de seguranca.

## Validacao de Campos

Adicione validacao customizada com `@field_validator` ou restricoes em `Field()`.

```python
from pydantic import Field, field_validator

class AppSettings(Settings):
    # ge=1, le=65535 restringe o range de valores validos
    port: int = Field(default=8000, ge=1, le=65535)
    environment: str = Field(default="development")
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v):
        """
        Validacao customizada executada durante carregamento.
        Se falhar, aplicacao nao inicia.
        """
        allowed = ["development", "staging", "production", "testing"]
        if v not in allowed:
            raise ValueError(f"environment deve ser um de: {allowed}")
        return v
```

## Multiplos Ambientes

Para ambientes diferentes (dev, staging, prod), use arquivos .env separados.

```
/.env                  # Desenvolvimento (local) - padrao
/.env.staging          # Staging
/.env.production       # Producao
```

Configure qual arquivo carregar baseado em variavel de ambiente:

```python
# config.py
import os
from pydantic_settings import SettingsConfigDict

# ENVIRONMENT deve ser definida no sistema, nao no .env
# Ex: export ENVIRONMENT=production
env_file = f".env.{os.getenv('ENVIRONMENT', 'development')}"

class AppSettings(Settings):
    model_config = SettingsConfigDict(
        env_file=env_file,
        env_file_encoding="utf-8",
    )
```

**Em Docker/Kubernetes**: Defina `ENVIRONMENT` como variavel de ambiente do container, nao no .env.

## Precedencia de Valores

Ordem de precedencia (maior para menor):
1. Variaveis de ambiente do sistema
2. Arquivo .env
3. Valores padrao na classe

Isso permite sobrescrever valores do .env em runtime sem modificar arquivos.

## Enterprise Features (v0.4.0+)

As features enterprise sao configuradas automaticamente via Settings. Basta definir os valores e o CoreApp configura tudo.

### Database Replicas

Separa leituras (SELECT) das escritas (INSERT/UPDATE/DELETE) para escalar horizontalmente.

```env
# .env
DATABASE_URL=postgresql+asyncpg://user:pass@primary:5432/db
DATABASE_READ_URL=postgresql+asyncpg://user:pass@replica:5432/db

# Opcional - pool da replica (default: 2x do write)
DATABASE_READ_POOL_SIZE=10
DATABASE_READ_MAX_OVERFLOW=20
```

```python
# config.py - nada a fazer, Settings ja tem os campos
class AppSettings(Settings):
    pass  # database_read_url ja existe na classe base

# O CoreApp detecta database_read_url e configura automaticamente
# Sem database_read_url, usa database_url para tudo
```

| Campo | Tipo | Default | Descricao |
|-------|------|---------|-----------|
| `database_read_url` | str \| None | None | URL da replica de leitura |
| `database_read_pool_size` | int \| None | None | Pool size da replica (2x write se None) |
| `database_read_max_overflow` | int \| None | None | Max overflow da replica (2x write se None) |

### Multi-Tenancy

Filtra queries automaticamente por tenant (workspace/organization).

```env
# .env
TENANCY_ENABLED=true
TENANCY_FIELD=workspace_id
TENANCY_USER_ATTRIBUTE=workspace_id
TENANCY_HEADER=X-Tenant-ID
TENANCY_REQUIRE=false
```

```python
# config.py
class AppSettings(Settings):
    pass  # Campos ja existem na classe base

# O CoreApp adiciona TenantMiddleware automaticamente quando tenancy_enabled=true
```

| Campo | Tipo | Default | Descricao |
|-------|------|---------|-----------|
| `tenancy_enabled` | bool | False | Habilita multi-tenancy |
| `tenancy_field` | str | "workspace_id" | Campo de tenant nos models |
| `tenancy_user_attribute` | str | "workspace_id" | Atributo do usuario com tenant ID |
| `tenancy_header` | str | "X-Tenant-ID" | Header HTTP para tenant (fallback) |
| `tenancy_require` | bool | False | Rejeita requests sem tenant |

**Uso no codigo:**

```python
from core.tenancy import TenantMixin, for_tenant

class Domain(Model, TenantMixin):
    __tablename__ = "domains"
    # workspace_id ja vem do TenantMixin
    # Nome do campo vem de settings.tenancy_field

# Queries filtram automaticamente
domains = await for_tenant(Domain.objects.using(db)).all()
```

### Soft Delete

Exclusao logica - marca registros como deletados em vez de remover.

```env
# .env
SOFT_DELETE_FIELD=deleted_at
SOFT_DELETE_CASCADE=false
SOFT_DELETE_AUTO_FILTER=true
```

| Campo | Tipo | Default | Descricao |
|-------|------|---------|-----------|
| `soft_delete_field` | str | "deleted_at" | Nome do campo de soft delete |
| `soft_delete_cascade` | bool | False | Soft delete em cascata |
| `soft_delete_auto_filter` | bool | True | Filtra deletados automaticamente |

**Uso no codigo:**

```python
from core import Model, SoftDeleteMixin, SoftDeleteManager

class User(Model, SoftDeleteMixin):
    __tablename__ = "users"
    objects = SoftDeleteManager["User"]()
    # deleted_at ja vem do SoftDeleteMixin
    # Nome do campo vem de settings.soft_delete_field

# Queries filtram deletados automaticamente
users = await User.objects.using(db).all()  # So ativos
```

### UUID

Configura versao padrao de UUID para primary keys.

```env
# .env
UUID_VERSION=uuid7
```

| Campo | Tipo | Default | Descricao |
|-------|------|---------|-----------|
| `uuid_version` | "uuid4" \| "uuid7" | "uuid7" | Versao de UUID padrao |

**UUID7 vs UUID4:**
- UUID7: Time-sortable, melhor para indices B-tree, recomendado para PKs
- UUID4: Random, use quando nao precisa de ordenacao temporal

```python
from core.fields import AdvancedField

class User(Model):
    # Usa settings.uuid_version automaticamente
    id: Mapped[UUID] = AdvancedField.uuid_pk()
```

## Messaging Settings (v0.11.0+)

Configurações para o sistema de mensageria (Kafka, Redis, RabbitMQ).

### Configuração Básica

```env
# .env
MESSAGE_BROKER=kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```

### Kafka - Todas as Configurações

```env
# =============================================================================
# Kafka - Broker
# =============================================================================
MESSAGE_BROKER=kafka
KAFKA_BOOTSTRAP_SERVERS=kafka1:9092,kafka2:9092,kafka3:9092

# Backend: "aiokafka" (async, padrão) ou "confluent" (librdkafka, mais rápido)
KAFKA_BACKEND=confluent

# Schema Registry para Avro
KAFKA_SCHEMA_REGISTRY_URL=http://schema-registry:8081

# Fire-and-forget: não aguarda confirmação (mais rápido, menos confiável)
KAFKA_FIRE_AND_FORGET=true

# =============================================================================
# Kafka - Segurança
# =============================================================================
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=PLAIN
KAFKA_SASL_USERNAME=api-key
KAFKA_SASL_PASSWORD=api-secret

# SSL (se necessário)
KAFKA_SSL_CAFILE=/path/to/ca.pem
KAFKA_SSL_CERTFILE=/path/to/cert.pem
KAFKA_SSL_KEYFILE=/path/to/key.pem

# =============================================================================
# Kafka - Performance
# =============================================================================
# Compressão: none, gzip, snappy, lz4, zstd
KAFKA_COMPRESSION_TYPE=lz4

# Batching
KAFKA_LINGER_MS=5
KAFKA_MAX_BATCH_SIZE=32768

# Timeouts
KAFKA_REQUEST_TIMEOUT_MS=30000
KAFKA_RETRY_BACKOFF_MS=100

# =============================================================================
# Kafka - Consumer
# =============================================================================
KAFKA_AUTO_OFFSET_RESET=earliest
KAFKA_ENABLE_AUTO_COMMIT=true
KAFKA_AUTO_COMMIT_INTERVAL_MS=5000
KAFKA_MAX_POLL_RECORDS=500
KAFKA_SESSION_TIMEOUT_MS=10000
KAFKA_HEARTBEAT_INTERVAL_MS=3000

# =============================================================================
# Messaging - Geral
# =============================================================================
MESSAGING_ENABLED=true
MESSAGING_DEFAULT_TOPIC=events
MESSAGING_EVENT_SOURCE=my-service
MESSAGING_SERIALIZER=json
MESSAGING_RETRY_ATTEMPTS=3
MESSAGING_RETRY_DELAY_SECONDS=5
MESSAGING_DEAD_LETTER_TOPIC=dead-letter
```

### Tabela de Configurações Kafka

| Variável | Tipo | Padrão | Descrição |
|----------|------|--------|-----------|
| `MESSAGE_BROKER` | str | "kafka" | Broker: kafka, redis, rabbitmq, memory |
| `KAFKA_BACKEND` | str | "aiokafka" | Backend: aiokafka ou confluent |
| `KAFKA_BOOTSTRAP_SERVERS` | str | "localhost:9092" | Servidores Kafka |
| `KAFKA_SCHEMA_REGISTRY_URL` | str | None | URL do Schema Registry |
| `KAFKA_FIRE_AND_FORGET` | bool | False | Não aguardar confirmação |
| `KAFKA_SECURITY_PROTOCOL` | str | "PLAINTEXT" | Protocolo de segurança |
| `KAFKA_SASL_MECHANISM` | str | None | Mecanismo SASL |
| `KAFKA_SASL_USERNAME` | str | None | Usuário SASL |
| `KAFKA_SASL_PASSWORD` | str | None | Senha SASL |
| `KAFKA_COMPRESSION_TYPE` | str | "none" | Tipo de compressão |
| `KAFKA_LINGER_MS` | int | 0 | Tempo para acumular batch |
| `KAFKA_MAX_BATCH_SIZE` | int | 16384 | Tamanho máximo do batch |

### Redis

```env
MESSAGE_BROKER=redis
REDIS_URL=redis://localhost:6379/0
REDIS_MAX_CONNECTIONS=10
REDIS_STREAM_MAX_LEN=10000
REDIS_CONSUMER_BLOCK_MS=5000
REDIS_CONSUMER_COUNT=10
```

### RabbitMQ

```env
MESSAGE_BROKER=rabbitmq
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
RABBITMQ_EXCHANGE=core_events
RABBITMQ_EXCHANGE_TYPE=topic
RABBITMQ_PREFETCH_COUNT=10
RABBITMQ_DURABLE=true
```

### Uso no Código

```python
from core.messaging import configure_messaging, get_producer, publish

# Configuração é carregada automaticamente do .env
# Ou configure programaticamente:
configure_messaging(
    message_broker="kafka",
    kafka_backend="confluent",
    kafka_bootstrap_servers="kafka:9092",
    kafka_fire_and_forget=True,
)

# Publicar mensagem
await publish("my-topic", {"key": "value"})
```

### Comparação de Backends Kafka

| Backend | Throughput | Latência | Features | Quando Usar |
|---------|------------|----------|----------|-------------|
| `aiokafka` | Alto | Baixa | Async nativo | Apps simples |
| `confluent` | Muito Alto | Muito Baixa | Schema Registry, Avro, Transações | Enterprise |

## Exemplo Completo de .env

```env
# =============================================================================
# Aplicacao
# =============================================================================
APP_NAME=My SaaS API
APP_VERSION=1.0.0
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=sua-chave-secreta-muito-longa-e-segura

# =============================================================================
# Database - Primary (escrita)
# =============================================================================
DATABASE_URL=postgresql+asyncpg://user:pass@primary.db.com:5432/mydb
DATABASE_ECHO=false
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_RECYCLE=3600

# =============================================================================
# Database - Replica (leitura) - OPCIONAL
# =============================================================================
DATABASE_READ_URL=postgresql+asyncpg://user:pass@replica.db.com:5432/mydb
# DATABASE_READ_POOL_SIZE=10  # Default: 2x do write
# DATABASE_READ_MAX_OVERFLOW=20  # Default: 2x do write

# =============================================================================
# Multi-Tenancy - OPCIONAL
# =============================================================================
TENANCY_ENABLED=true
TENANCY_FIELD=workspace_id
TENANCY_USER_ATTRIBUTE=workspace_id
TENANCY_REQUIRE=false

# =============================================================================
# Soft Delete - OPCIONAL
# =============================================================================
SOFT_DELETE_FIELD=deleted_at
SOFT_DELETE_AUTO_FILTER=true

# =============================================================================
# UUID - OPCIONAL
# =============================================================================
UUID_VERSION=uuid7

# =============================================================================
# Auth
# =============================================================================
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=30
AUTH_REFRESH_TOKEN_EXPIRE_DAYS=7
AUTH_PASSWORD_HASHER=argon2

# =============================================================================
# API
# =============================================================================
API_PREFIX=/api/v1
HOST=0.0.0.0
PORT=8000

# =============================================================================
# Timezone
# =============================================================================
TIMEZONE=UTC

# =============================================================================
# Messaging (Kafka)
# =============================================================================
MESSAGE_BROKER=kafka
KAFKA_BACKEND=confluent
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_SCHEMA_REGISTRY_URL=http://schema-registry:8081
KAFKA_FIRE_AND_FORGET=true
KAFKA_COMPRESSION_TYPE=lz4
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=PLAIN
KAFKA_SASL_USERNAME=api-key
KAFKA_SASL_PASSWORD=api-secret
```

## Verificar Configuracao

```python
from src.api.config import settings

# Verificar se replica esta configurada
print(f"Replica: {settings.has_read_replica}")

# Verificar se tenancy esta habilitado
print(f"Tenancy: {settings.tenancy_enabled}")

# Ver todas as configuracoes (cuidado com secrets!)
print(settings.model_dump())
```

---

Proximo: [Migrations](10-migrations.md) - Sistema de migracoes de banco de dados.
