# Migration Guide — v0.12.x to v0.13.0

> **Para desenvolvedores:** este guia lista TODAS as alteracoes necessarias
> para atualizar um projeto de v0.12.x para v0.13.0, organizadas por prioridade.

---

## Passo 1 — Configuracao centralizada (OBRIGATORIO)

### 1.1 Criar arquivo de settings dedicado

**Antes (v0.12.x):** Settings definidos inline no `app.py` ou `main.py`.

```python
# app.py (ANTIGO)
from core.config import Settings

class AppSettings(Settings):
    jwt_secret: str = "..."

settings = AppSettings()
```

**Depois (v0.13.0):** Mova para um arquivo dedicado `settings.py` na raiz do seu app.

```python
# myapp/settings.py (NOVO — unico local de configuracao)
from core.config import Settings, PydanticField

class AppSettings(Settings):
    jwt_secret: str = PydanticField(default="...", description="JWT secret")

settings = AppSettings()
```

```python
# myapp/app.py (NOVO — importa de settings.py)
from myapp.settings import settings
from core.app import CoreApp

app = CoreApp(title="My API", settings=settings)
```

**O que remover:** Delete qualquer `class AppSettings(Settings)` dentro de `app.py`, `main.py`, ou qualquer outro arquivo que nao seja `settings.py`.

### 1.2 Criar `.env` por ambiente

Crie arquivos `.env` especificos por ambiente ao lado do `.env` base:

```
.env                  # Base (sempre carregado)
.env.development      # Sobrescreve em development
.env.production       # Sobrescreve em production
.env.testing          # Sobrescreve em testing
```

### 1.3 Configurar `SECRET_KEY` (OBRIGATORIO em prod/staging)

```bash
# Gerar chave segura:
python -c "import secrets; print(secrets.token_urlsafe(64))"

# Adicionar ao .env.production:
SECRET_KEY=sua-chave-gerada-aqui
```

Em `development` e `testing`, uma chave e auto-gerada (com warning). Em `production`/`staging`, o app **falha no startup** sem `SECRET_KEY`.

### 1.4 Configurar CORS (defaults mudaram)

**Antes:** `cors_origins=["*"]`, `cors_allow_credentials=True`

**Depois:** `cors_origins=[]`, `cors_allow_credentials=False`

```bash
# .env.development
CORS_ORIGINS='["http://localhost:3000", "http://localhost:5173"]'
CORS_ALLOW_CREDENTIALS=true

# .env.production
CORS_ORIGINS='["https://app.seudominio.com"]'
CORS_ALLOW_CREDENTIALS=true
```

### 1.5 Configurar `auto_create_tables` (default mudou para `False`)

**Antes:** `CoreApp(auto_create_tables=True)` era o padrao.

**Depois:** Default e `False`. Configure explicitamente:

```bash
# .env.development (se quiser auto-criar tabelas em dev)
AUTO_CREATE_TABLES=true
```

Ou via codigo:

```python
app = CoreApp(auto_create_tables=True, ...)
```

**Remover:** Se voce passava `auto_create_tables=True` explicitamente no CoreApp e quer manter, nao precisa mudar nada. Se dependia do default, adicione ao `.env`.

### 1.6 Docs/OpenAPI (default mudou para desabilitado)

**Antes:** `/docs`, `/redoc`, `/openapi.json` sempre disponiveis.

**Depois:** Desabilitados por padrao. Auto-habilitados em `ENVIRONMENT=development`.

Se precisa em producao:

```bash
# .env.production
DOCS_URL=/docs
REDOC_URL=/redoc
OPENAPI_URL=/openapi.json
```

**Nada a remover:** Se `ENVIRONMENT=development` (padrao), docs continuam funcionando automaticamente.

### 1.7 Atualizar `main.py` para ler settings

**Antes:**

```python
uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
```

**Depois:**

```python
from myapp.settings import settings

uvicorn.run("main:app", host=settings.host, port=settings.port, reload=settings.reload)
```

**Remover:** Valores hardcoded de `host`, `port`, `reload` no `main.py`.

---

## Passo 2 — Imports deprecados (RECOMENDADO)

### 2.1 Substituir `get_messaging_settings()` e `get_task_settings()`

**Buscar e substituir em todo o projeto:**

| Antigo | Novo |
|--------|------|
| `from core.messaging.config import get_messaging_settings` | `from core.config import get_settings` |
| `from core.tasks.config import get_task_settings` | `from core.config import get_settings` |
| `settings = get_messaging_settings()` | `settings = get_settings()` |
| `settings = get_task_settings()` | `settings = get_settings()` |
| `from core.messaging.config import configure_messaging` | `from core.config import configure` |
| `from core.tasks.config import configure_tasks` | `from core.config import configure` |
| `configure_messaging(...)` | `configure(...)` |
| `configure_tasks(...)` | `configure(...)` |

Os antigos continuam funcionando mas emitem `DeprecationWarning`. Serao removidos na v0.14.

### 2.2 Substituir `get_settings_class_instance()`

**Antigo:**

```python
from core.config import get_settings_class_instance
settings = get_settings_class_instance(MySettings)
```

**Novo:**

```python
from core.config import configure
settings = configure(settings_class=MySettings)
```

---

## Passo 3 — Response Schemas (CORRECAO DE TIPO)

### 3.1 Presets de resposta agora herdam de `OutputSchema`

Os seguintes schemas mudaram de `BaseModel` para `OutputSchema`:

| Schema | Base anterior | Base nova |
|--------|--------------|-----------|
| `PaginatedResponse` | `BaseModel` | `OutputSchema` |
| `ErrorResponse` | `BaseModel` | `OutputSchema` |
| `SuccessResponse` | `BaseModel` | `OutputSchema` |
| `DeleteResponse` | `BaseModel` | `OutputSchema` |
| `ValidationErrorResponse` | `BaseModel` | `OutputSchema` |
| `NotFoundResponse` | `BaseModel` | `OutputSchema` |
| `ConflictResponse` | `BaseModel` | `OutputSchema` |
| `ValidationErrorDetail` | `BaseModel` | `OutputSchema` |

**O que muda para voce:**
- Se voce herdava desses presets, agora herdam `from_attributes=True` automaticamente.
- Se voce usava `isinstance(schema, OutputSchema)`, agora esses presets passam no check.
- **Nada quebra.** A mudanca e 100% retrocompativel. So adiciona funcionalidade.

### 3.2 `_make_partial_model()` preserva heranca

Modelos parciais para PATCH agora herdam do schema original em vez de `BaseModel` puro.

**O que muda:** Schemas parciais mantam `extra="forbid"`, `str_strip_whitespace=True`, validators customizados. Se voce tinha workarounds para campos extras aceitos em PATCH, remova-os.

---

## Passo 4 — Middleware (OPCIONAL — melhoria de performance)

### 4.1 Migrar middlewares customizados para `ASGIMiddleware`

**Antes (funciona mas e deprecated):**

```python
from core.middleware import BaseMiddleware

class MyMiddleware(BaseMiddleware):
    async def before_request(self, request):
        request.state.custom = "value"
    
    async def after_request(self, request, response):
        response.headers["X-Custom"] = "value"
        return response
```

**Depois (recomendado — zero overhead):**

```python
from core.middleware import ASGIMiddleware

class MyMiddleware(ASGIMiddleware):
    async def before_request(self, scope, request):
        request.state.custom = "value"
    
    async def after_response(self, scope, request, status_code, response_headers):
        response_headers.append((b"x-custom", b"value"))
```

**Diferencas de API:**
- `before_request` recebe `scope` como primeiro argumento
- `after_request` muda para `after_response` e recebe `status_code` + `response_headers` (lista de tuplas bytes) em vez de `response` object
- `on_error` recebe `scope` como primeiro argumento

**Remover:** Nada obrigatorio. `BaseMiddleware` continua funcionando.

---

## Passo 5 — Configs que o core-framework define por padrao (REMOVER REDUNDANCIAS)

Se voce configurava explicitamente valores que agora sao defaults do framework, **remova-os** para simplificar:

### Remover do seu `settings.py` ou `.env`:

| Config | Default v0.13.0 | Remover se voce tinha |
|--------|-----------------|----------------------|
| `ENVIRONMENT=development` | `development` | Ja e o padrao |
| `DEBUG=false` | `false` | Ja e o padrao |
| `DATABASE_POOL_SIZE=5` | `5` | Ja e o padrao |
| `DATABASE_MAX_OVERFLOW=10` | `10` | Ja e o padrao |
| `DATABASE_POOL_RECYCLE=3600` | `3600` | Ja e o padrao |
| `API_PREFIX=/api/v1` | `/api/v1` | Ja e o padrao |
| `AUTH_ALGORITHM=HS256` | `HS256` | Ja e o padrao |
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=30` | `30` | Ja e o padrao |
| `AUTH_PASSWORD_HASHER=pbkdf2_sha256` | `pbkdf2_sha256` | Ja e o padrao |
| `LOG_LEVEL=INFO` | `INFO` | Ja e o padrao |
| `HOST=0.0.0.0` | `0.0.0.0` | Ja e o padrao |
| `PORT=8000` | `8000` | Ja e o padrao |
| `WORKERS=1` | `1` | Ja e o padrao |
| `TASK_DEFAULT_QUEUE=default` | `default` | Ja e o padrao |
| `TASK_DEFAULT_RETRY=3` | `3` | Ja e o padrao |
| `TASK_WORKER_CONCURRENCY=4` | `4` | Ja e o padrao |
| `HEALTH_CHECK_ENABLED=true` | `true` | Ja e o padrao |
| `MIGRATIONS_DIR=./migrations` | `./migrations` | Ja e o padrao |
| `APP_LABEL=main` | `main` | Ja e o padrao |
| `MODELS_MODULE=app.models` | `app.models` | Ja e o padrao |

### Remover do seu `app.py`:

| Codigo redundante | Motivo |
|------------------|--------|
| `auto_create_tables=False` | Ja e o padrao |
| `docs_url=None` | Ja e o padrao (auto em dev) |
| `redoc_url=None` | Ja e o padrao (auto em dev) |

### Remover imports nao usados:

```python
# REMOVER — nao precisa mais importar estas funcoes:
from core.messaging.config import get_messaging_settings   # use get_settings()
from core.messaging.config import configure_messaging       # use configure()
from core.tasks.config import get_task_settings             # use get_settings()
from core.tasks.config import configure_tasks               # use configure()
from core.config import get_settings_class_instance         # use configure(settings_class=...)
```

### Remover arquivos redundantes:

| Arquivo | Acao |
|---------|------|
| `core.toml` | Opcional — Settings (.env) e a fonte primaria agora |

---

## Passo 6 — Novos recursos disponiveis (OPCIONAL)

### Health checks automaticos

`/healthz` e `/readyz` ja estao registrados automaticamente. Nada a configurar. Desabilitar se necessario:

```bash
HEALTH_CHECK_ENABLED=false
```

### Session factory customizada

```python
from core.dependencies import set_session_factory

async def my_session():
    async with my_custom_session_maker() as session:
        yield session

set_session_factory(my_session)
```

### Hook pos-carregamento

```python
from core.config import on_settings_loaded

@on_settings_loaded
def validate_my_config(settings):
    if settings.kafka_enabled and not settings.kafka_bootstrap_servers:
        raise ValueError("KAFKA_BOOTSTRAP_SERVERS required")
```

---

## Checklist resumido para upgrade

```
[ ] 1. Criar myapp/settings.py com AppSettings(Settings)
[ ] 2. Mover class AppSettings de app.py/main.py para settings.py
[ ] 3. Criar .env.development com CORS e AUTO_CREATE_TABLES
[ ] 4. Criar .env.production com SECRET_KEY e CORS
[ ] 5. Atualizar main.py para ler host/port/reload de settings
[ ] 6. Substituir get_messaging_settings() → get_settings()
[ ] 7. Substituir get_task_settings() → get_settings()
[ ] 8. Remover configs redundantes que o framework ja define
[ ] 9. (Opcional) Migrar middlewares customizados para ASGIMiddleware
[ ] 10. Testar: python main.py (deve logar "Application started successfully")
```
