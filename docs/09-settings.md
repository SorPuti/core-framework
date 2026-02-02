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

---

Proximo: [Migrations](10-migrations.md) - Sistema de migracoes de banco de dados.
