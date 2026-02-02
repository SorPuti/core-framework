# Settings (Configuracoes)

## Estrutura de Arquivos

```
/my-project
  /.env                    # Variaveis de ambiente (NAO commitar)
  /src
    /api
      config.py            # Classe de configuracao
    main.py
```

## Passo 1: Criar config.py

```python
# src/api/config.py
from core import Settings

class AppSettings(Settings):
    """
    Configuracoes da aplicacao.
    
    Campos herdados de Settings (ja disponiveis):
    - app_name, app_version, environment, debug, secret_key
    - database_url, database_echo, database_pool_size
    - api_prefix, docs_url, redoc_url, openapi_url
    - cors_origins, cors_allow_credentials
    - auth_secret_key, auth_algorithm, auth_access_token_expire_minutes
    - timezone, use_tz, datetime_format
    - host, port, workers, reload
    - log_level, log_format, log_json
    """
    
    # Adicione seus campos customizados aqui
    stripe_api_key: str = ""
    stripe_webhook_secret: str = ""
    sendgrid_api_key: str = ""
    aws_access_key: str = ""
    aws_secret_key: str = ""
    aws_bucket_name: str = "my-bucket"
    max_upload_size_mb: int = 10
    
    # Campos com validacao
    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap_servers: str = "localhost:9092"

# Instancia singleton
settings = AppSettings()
```

## Passo 2: Criar .env

```env
# .env (na raiz do projeto)

# Application
APP_NAME=My API
APP_VERSION=1.0.0
ENVIRONMENT=development
DEBUG=true
SECRET_KEY=minha-chave-secreta-muito-longa-e-segura

# Database
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

# Seus campos customizados
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

## Passo 3: Usar no Codigo

```python
# Em qualquer arquivo
from src.api.config import settings

# Acessar valores
print(settings.app_name)
print(settings.database_url)
print(settings.stripe_api_key)

# Helpers disponiveis
if settings.is_development:
    print("Modo desenvolvimento")

if settings.is_production:
    print("Modo producao")
```

## Mapeamento .env -> config.py

| .env | config.py | Tipo |
|------|-----------|------|
| `APP_NAME=My API` | `settings.app_name` | str |
| `DEBUG=true` | `settings.debug` | bool |
| `PORT=8000` | `settings.port` | int |
| `CORS_ORIGINS=["*"]` | `settings.cors_origins` | list[str] |

Regra: `NOME_EM_MAIUSCULO` no .env vira `nome_em_minusculo` no Python.

## Valores Padrao

Se uma variavel nao existir no .env, usa o valor padrao definido na classe:

```python
class AppSettings(Settings):
    # Se STRIPE_API_KEY nao existir no .env, sera string vazia
    stripe_api_key: str = ""
    
    # Se MAX_UPLOAD_SIZE_MB nao existir, sera 10
    max_upload_size_mb: int = 10
```

## Campos Obrigatorios

Para tornar um campo obrigatorio (sem valor padrao):

```python
from pydantic import Field

class AppSettings(Settings):
    # Obrigatorio - erro se nao existir no .env
    stripe_api_key: str = Field(..., description="Chave da API Stripe")
    
    # Opcional com padrao
    debug: bool = False
```

## Validacao de Campos

```python
from pydantic import Field, field_validator

class AppSettings(Settings):
    port: int = Field(default=8000, ge=1, le=65535)
    environment: str = Field(default="development")
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v):
        allowed = ["development", "staging", "production", "testing"]
        if v not in allowed:
            raise ValueError(f"environment deve ser um de: {allowed}")
        return v
```

## Multiplos Ambientes

```
/.env                  # Desenvolvimento (local)
/.env.staging          # Staging
/.env.production       # Producao
```

```python
# config.py
import os

env_file = f".env.{os.getenv('ENVIRONMENT', 'development')}"

class AppSettings(Settings):
    model_config = SettingsConfigDict(
        env_file=env_file,
        env_file_encoding="utf-8",
    )
```

## Resumo

1. Crie `src/api/config.py` com sua classe `AppSettings(Settings)`
2. Adicione campos customizados na classe
3. Crie `.env` na raiz com os valores
4. Importe `from src.api.config import settings` onde precisar

Next: [Migrations](10-migrations.md)
