# Quickstart

Crie uma API funcional em 5 minutos.

## Visão Geral da Arquitetura

```mermaid
flowchart TB
    subgraph Client
        REQ[HTTP Request]
    end
    
    subgraph "Core Framework"
        MW[Middleware Stack]
        RT[AutoRouter]
        VS[ViewSet]
        MD[Model]
        DB[(Database)]
    end
    
    REQ --> MW
    MW --> RT
    RT --> VS
    VS --> MD
    MD --> DB
    
    style MW fill:#e1f5fe
    style VS fill:#fff3e0
    style MD fill:#e8f5e9
```

## Requisitos

- Python 3.12+
- PostgreSQL (ou SQLite para dev)

## Instalação

```bash
# Instalação global (recomendado)
pipx install core-framework

# Ou por projeto
pip install core-framework
```

## Criar Projeto

```bash
core init my-api
cd my-api
```

Isso cria:

```
my-api/
├── src/
│   ├── settings.py      # Configuração
│   ├── main.py          # Entry point
│   └── apps/
│       ├── models.py    # Imports de models
│       └── users/       # App de exemplo
├── migrations/
├── .env
└── pyproject.toml
```

## Configurar

Edite `src/settings.py`:

```python
from core.config import Settings, configure

class AppSettings(Settings):
    app_name: str = "Minha API"
    
    # Auth - auto-configurado quando user_model definido
    user_model: str = "src.apps.users.models.User"
    models_module: str = "src.apps"

settings = configure(settings_class=AppSettings)
```

Edite `.env`:

```env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/mydb
SECRET_KEY=change-me-in-production
DEBUG=true
```

## Criar Model

```python
# src/apps/posts/models.py
from core import Model, Field
from sqlalchemy.orm import Mapped

class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = Field.pk()
    title: Mapped[str] = Field.string(max_length=200, index=True)
    content: Mapped[str] = Field.text()
    published: Mapped[bool] = Field.boolean(default=False)
```

Importe no arquivo barrel:

```python
# src/apps/models.py
from src.apps.posts.models import Post  # noqa
```

## Criar ViewSet

```python
# src/apps/posts/views.py
from core import ModelViewSet
from core.permissions import AllowAny
from .models import Post

class PostViewSet(ModelViewSet):
    model = Post
    permission_classes = [AllowAny]  # Acesso público
```

## Criar Rotas

```python
# src/apps/posts/routes.py
from core import AutoRouter
from .views import PostViewSet

router = AutoRouter(prefix="/posts", tags=["Posts"])
router.register("", PostViewSet)
```

## Registrar Rotas

```python
# src/main.py
from core import CoreApp, AutoRouter
from core.config import get_settings
from src.apps.posts.routes import router as posts_router

settings = get_settings()

api = AutoRouter(prefix="/api/v1")
api.include_router(posts_router)

app = CoreApp(routers=[api])
```

## Executar

```bash
# Criar migration
core makemigrations --name add_posts

# Aplicar migration
core migrate

# Iniciar servidor
core run
```

## Testar

Abra http://localhost:8000/docs

Endpoints gerados:

| Método | Path | Ação |
|--------|------|------|
| GET | /api/v1/posts/ | Listar |
| POST | /api/v1/posts/ | Criar |
| GET | /api/v1/posts/{id} | Obter um |
| PUT | /api/v1/posts/{id} | Atualizar |
| PATCH | /api/v1/posts/{id} | Atualização parcial |
| DELETE | /api/v1/posts/{id} | Deletar |

## Exemplo com Auto-Configuração Completa

```python
# src/settings.py
from core.config import Settings, PydanticField, configure

class AppSettings(Settings):
    # ══════════════════════════════════════════════════════════════════
    # Aplicação
    # ══════════════════════════════════════════════════════════════════
    app_name: str = "Minha API"
    
    # ══════════════════════════════════════════════════════════════════
    # Auth (auto-configurado)
    # ══════════════════════════════════════════════════════════════════
    user_model: str = "src.apps.users.models.User"
    models_module: str = "src.apps"
    
    # ══════════════════════════════════════════════════════════════════
    # Middleware
    # ══════════════════════════════════════════════════════════════════
    middleware: list[str] = [
        "timing",
        "request_id",
        "auth",
    ]
    
    # ══════════════════════════════════════════════════════════════════
    # Campos customizados
    # ══════════════════════════════════════════════════════════════════
    stripe_key: str = PydanticField(default="", description="Stripe API Key")

# Configura TUDO automaticamente
settings = configure(settings_class=AppSettings)
```

## Próximos Passos

- [Settings](02-settings.md) — Opções de configuração
- [Models](03-models.md) — Tipos de campos, relacionamentos
- [ViewSets](04-viewsets.md) — Actions customizadas, hooks
- [Auth](05-auth.md) — Autenticação JWT
