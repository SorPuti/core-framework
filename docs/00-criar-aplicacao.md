# Criar uma aplicação

Guia completo para criar, configurar e publicar uma aplicação com o framework: configuração, banco de dados, ViewSets, APIView, ModelViewSet, serializers, paginação, WebSocket, SSE e validação.

## Índice

1. [Requisitos e instalação](#1-requisitos-e-instalação)
2. [Configuração](#2-configuração)
3. [Banco de dados e Models](#3-banco-de-dados-e-models)
4. [ViewSet e ModelViewSet](#4-viewset-e-modelviewset)
5. [APIView](#5-apiview)
6. [Serializers e validação](#6-serializers-e-validação)
7. [Paginação](#7-paginação)
8. [WebSocket e SSE](#8-websocket-e-sse)
9. [Validação (regras de negócio)](#9-validação-regras-de-negócio)
10. [Resumo do fluxo request → response](#10-resumo-do-fluxo-request--response)

---

## 1. Requisitos e instalação

- Python 3.12+
- PostgreSQL (ou SQLite para desenvolvimento)

```bash
pipx install stride
# ou
pip install stride
```

Criar projeto:

```bash
stride init my-api
cd my-api
```

Estrutura inicial:

```
my-api/
├── src/
│   ├── settings.py
│   ├── main.py
│   └── apps/
│       ├── models.py    # barrel de models
│       └── users/       # app de exemplo
├── migrations/
├── .env
└── pyproject.toml
```

---

## 2. Configuração

Toda a configuração fica em `src/settings.py` e em variáveis de ambiente (`.env`). O framework usa **plug-and-play**: definir um atributo no Settings ativa o subsistema correspondente.

### Settings básico

```python
# src/settings.py
from strider.config import Settings, configure

class AppSettings(Settings):
    app_name: str = "Minha API"
    app_version: str = "1.0.0"
    
    # Módulo onde estão os models (para discovery)
    models_module: str = "src.apps"
    
    # Auth (ativa JWT, user_model, etc.)
    user_model: str = "src.apps.users.models.User"

settings = configure(settings_class=AppSettings)
```

### Arquivo .env

```env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/mydb
SECRET_KEY=altere-em-producao
DEBUG=true
```

### Opções mais usadas

| Atributo | Descrição | Padrão |
|----------|-----------|--------|
| `app_name` | Nome da aplicação | — |
| `database_url` | URL do banco (asyncpg) | — |
| `secret_key` | Chave para JWT/sessão | — |
| `debug` | Modo debug | `false` |
| `user_model` | Model de usuário (ativa auth) | — |
| `models_module` | Módulo de discovery de models | — |
| `api_prefix` | Prefixo global da API | `"/api/v1"` |
| `installed_apps` | Lista de apps para carregar URLs | — |
| `middleware` | Lista de middlewares | `["timing", "request_id", "auth"]` |

Documentação completa: [Settings](02-settings.md).

---

## 3. Banco de dados e Models

### Definir um model

```python
# src/apps/posts/models.py
from datetime import datetime
from strider import Model, Field
from sqlalchemy.orm import Mapped

class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = Field.pk()
    title: Mapped[str] = Field.string(max_length=200, index=True)
    content: Mapped[str] = Field.text()
    published: Mapped[bool] = Field.boolean(default=False)
    created_at: Mapped[datetime] = Field.datetime(auto_now_add=True)
```

### Importar no barrel

```python
# src/apps/models.py
from src.apps.posts.models import Post  # noqa
```

### Migrations

```bash
stride makemigrations --name add_posts
stride migrate
```

Tipos de campos e relacionamentos: [Models](03-models.md), [Fields](10-fields.md), [Relations](11-relations.md).

---

## 4. ViewSet e ModelViewSet

ViewSets geram CRUD completo a partir do model. **ModelViewSet** é a variante mais usada.

### Básico

```python
# src/apps/posts/views.py
from strider import ModelViewSet
from strider.permissions import AllowAny
from .models import Post

class PostViewSet(ModelViewSet):
    model = Post
    permission_classes = [AllowAny]
```

Endpoints gerados:

| Método | Path | Ação |
|--------|------|------|
| GET | /api/v1/posts/ | list |
| POST | /api/v1/posts/ | create |
| GET | /api/v1/posts/{id} | retrieve |
| PUT | /api/v1/posts/{id} | update |
| PATCH | /api/v1/posts/{id} | partial_update |
| DELETE | /api/v1/posts/{id} | destroy |

### Com Serializer centralizado (UnifiedModelSerializer)

Você pode **não definir InputSchema nem OutputSchema**: use **UnifiedModelSerializer** com `fields` e `read_only_fields`. Os schemas são gerados a partir do model.

```python
# src/apps/posts/serializers.py
from strider import UnifiedModelSerializer
from .models import Post

class PostSerializer(UnifiedModelSerializer):
    model = Post
    fields = ["id", "title", "content", "published", "created_at"]
    read_only_fields = ["id", "created_at"]
```

```python
# src/apps/posts/views.py
from strider import ModelViewSet
from .models import Post
from .serializers import PostSerializer

class PostViewSet(ModelViewSet):
    model = Post
    serializer_class = PostSerializer
```

### Com Serializer e schemas explícitos (validadores/campos computados)

Quando precisar de validadores Pydantic ou campos computados, defina InputSchema e OutputSchema e use **ModelSerializer**:

```python
# src/apps/posts/schemas.py
from datetime import datetime
from strider import InputSchema, OutputSchema

class PostInput(InputSchema):
    title: str
    content: str
    published: bool = False

class PostOutput(OutputSchema):
    id: int
    title: str
    content: str
    published: bool
    created_at: datetime
```

```python
# src/apps/posts/serializers.py
from strider import ModelSerializer
from .models import Post
from .schemas import PostInput, PostOutput

class PostSerializer(ModelSerializer[Post, PostInput, PostOutput]):
    model = Post
    input_schema = PostInput
    output_schema = PostOutput
```

O padrão recomendado é **serializer_class** (UnifiedModelSerializer ou ModelSerializer).

### Permissões por ação

```python
from strider.permissions import AllowAny, IsAuthenticated, IsAdminUser

class PostViewSet(ModelViewSet):
    model = Post
    serializer_class = PostSerializer
    permission_classes = [IsAuthenticated]
    permission_classes_by_action = {
        "list": [AllowAny],
        "retrieve": [AllowAny],
        "create": [IsAuthenticated],
        "update": [IsAuthenticated],
        "destroy": [IsAdminUser],
    }
```

### Hooks do ciclo de vida

| Hook | Quando é chamado |
|------|-------------------|
| `perform_create_validation(data, db)` | Antes de criar o objeto (validação extra) |
| `after_create(obj, db)` | Depois de criar e salvar |
| `perform_update_validation(data, instance, db)` | Antes de atualizar |
| `after_update(obj, db)` | Depois de atualizar e salvar |

```python
class PostViewSet(ModelViewSet):
    model = Post
    serializer_class = PostSerializer

    async def perform_create_validation(self, data, db):
        data["author_id"] = self.request.user.id
        return data

    async def after_create(self, obj, db):
        await send_notification(f"Post {obj.id} criado")
```

### Actions customizadas (@action)

```python
from strider import ModelViewSet, action

class PostViewSet(ModelViewSet):
    model = Post
    serializer_class = PostSerializer

    @action(methods=["POST"], detail=True)
    async def publish(self, request, db, **kwargs):
        """POST /posts/{id}/publish/"""
        obj = await self.get_object(db, **kwargs)
        obj.published = True
        await obj.save(db)
        return self._serialize_for_response(obj)
```

### Outras variantes de ViewSet

- **ReadOnlyModelViewSet**: só `list` e `retrieve`
- **ListCreateModelViewSet**: `list` e `create`
- **SearchModelViewSet**: CRUD + busca textual

Documentação completa: [ViewSets](04-viewsets.md), [Routing](23-routing.md).

---

## 5. APIView

Para endpoints que não são CRUD sobre um model, use **APIView**. Você implementa os métodos HTTP que precisar.

```python
# src/apps/health/views.py
from strider import APIView
from fastapi import Request

class HealthView(APIView):
    permission_classes = [AllowAny]

    async def get(self, request: Request, db) -> dict:
        return {"status": "ok", "database": "connected"}
```

Registro de rota:

```python
# src/apps/health/urls.py
from strider import path
from .views import HealthView

urlpatterns = [
    path("health", HealthView),
]
```

Para converter em rota FastAPI com métodos explícitos:

```python
path, endpoint, kwargs = HealthView.as_route("/health", methods=["GET", "HEAD"])
router.add_api_route(path, endpoint, **kwargs)
```

---

## 6. Serializers e validação

O fluxo é: **uma única validação** na borda (FastAPI com o schema de input) → handler recebe dados já validados → regras de negócio em `validate_data` → serialização com o Serializer.

### InputSchema e OutputSchema

- **InputSchema**: body da request. Por padrão `extra="ignore"` (campos desconhecidos são ignorados).
- **OutputSchema**: corpo da response; suporta `list_include`/`list_exclude` e `@computed_orm_field`.

```python
from strider import InputSchema, OutputSchema
from pydantic import field_validator

class UserCreateInput(InputSchema):
    email: str
    name: str
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Mínimo 8 caracteres")
        return v
```

### Serializer como fonte única

O ViewSet usa `serializer_class`. O Router obtém os schemas de body/response do Serializer (`input_cls`/`output_cls` ou `input_schema`/`output_schema`).

```python
class UserSerializer(Serializer[User, UserCreateInput, UserOutput]):
    input_schema = UserCreateInput
    output_schema = UserOutput
    # Opcional: input_cls / output_cls (aliases para OpenAPI)
```

Métodos úteis do Serializer:

- `validate_input(data)` — valida dict → instância do input schema
- `to_representation(obj)` — serializa um objeto (list/detail) com `dump_for_list`
- `to_representation_many(objects)` — serializa lista

No ViewSet, a serialização passa por `_serialize_for_response(obj)` e `_serialize_many_for_response(objects)`, que usam o Serializer quando existir.

### Rejeitar campos extras (opt-in)

Por padrão, campos extras no body são **ignorados**. Para rejeitar:

```python
from pydantic import ConfigDict

class StrictInput(InputSchema):
    model_config = ConfigDict(extra="forbid")
    name: str
```

Documentação completa: [Serializers](13-serializers.md).

---

## 7. Paginação

ViewSets de listagem já retornam resposta paginada.

Parâmetros de query:

- `page` — número da página (começa em 1)
- `page_size` — itens por página (limitado por `max_page_size` do ViewSet)

Resposta:

```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "pages": 5
}
```

Configuração no ViewSet:

```python
class PostViewSet(ModelViewSet):
    model = Post
    page_size = 20   # padrão por página
    max_page_size = 100  # teto para page_size
```

---

## 8. WebSocket e SSE

### WebSocket

```python
from strider import WebSocketView, Router

class EchoWS(WebSocketView):
    encoding = "json"
    keepalive = 30

    async def on_connect(self, ws, **params):
        self.room = params.get("room", "default")

    async def on_receive(self, ws, data):
        await ws.send_json({"echo": data})

    async def on_disconnect(self, ws, code):
        pass

router = Router(prefix="/chat", tags=["Chat"])
router.register_websocket("/ws/{room}", EchoWS)
```

Protegido com JWT:

```python
from strider import WebSocketView, IsAuthenticated

class PrivateStream(WebSocketView):
    permission_classes = [IsAuthenticated]

    async def on_connect(self, ws, **params):
        # self.user preenchido após auth
        pass
```

Token: header `Authorization: Bearer <token>` ou query `?token=<token>`.

### SSE (Server-Sent Events)

```python
from strider import SSEView, Router

class SystemEvents(SSEView):
    ping_interval = 15

    async def stream(self, request, **params):
        while True:
            event = await get_next_event()
            yield {"event": "update", "data": event}

router = Router(prefix="/events", tags=["Events"])
router.register_sse("/system", SystemEvents)
```

Documentação completa: [Real-time](25-realtime.md).

---

## 9. Validação (regras de negócio)

A validação de **formato** (tipos, Pydantic) ocorre uma vez na borda. As **regras de negócio** (unicidade, existência de FK, etc.) ficam no ViewSet.

### Campos únicos

```python
class UserViewSet(ModelViewSet):
    model = User
    serializer_class = UserSerializer
    unique_fields = ["email", "username"]
```

### Validadores por campo

```python
from strider.validators import ValidationError

class UserViewSet(ModelViewSet):
    model = User
    serializer_class = UserSerializer
    unique_fields = ["email"]

    async def validate_email(self, value, db, instance=None):
        if value.endswith("@blocked.com"):
            raise ValidationError("Domínio não permitido", field="email")
        return value
```

### Validação global

```python
class OrderViewSet(ModelViewSet):
    async def validate(self, data, db, instance=None):
        if data.get("start_date") > data.get("end_date"):
            raise ValidationError("start_date deve ser anterior a end_date", field="start_date")
        return data
```

Documentação completa: [Validators](14-validators.md).

---

## 10. Resumo do fluxo request → response

1. **Request** chega ao FastAPI.
2. **Parsing**: body JSON lido pelo FastAPI.
3. **Validação (única)**: FastAPI valida o body com o schema de input do Serializer (ou do ViewSet) → instância validada ou 422.
4. **Handler**: ViewSet recebe `data` já como instância do schema (não revalida). Obtém dict com `data.model_dump()` e chama `validate_data(...)` para regras de negócio.
5. **Lógica**: create/update usam o dict validado; hooks `perform_create_validation` / `perform_update_validation` e `after_create` / `after_update` quando definidos.
6. **Serialização**: um único caminho via `_serialize_for_response(obj)` (usa Serializer quando existir).
7. **Response**: FastAPI serializa o resultado para JSON.

Nenhuma segunda validação Pydantic dentro do ViewSet; campos extras no body são ignorados por padrão (`extra="ignore"`).

---

## Próximos passos

| Doc | Assunto |
|-----|---------|
| [Quickstart](01-quickstart.md) | Primeira API em 5 minutos |
| [Settings](02-settings.md) | Todas as opções de configuração |
| [Models](03-models.md) | Campos e relacionamentos |
| [ViewSets](04-viewsets.md) | Actions, hooks e permissões |
| [Serializers](13-serializers.md) | Input/Output e Serializer único |
| [Routing](23-routing.md) | URLs e registro de rotas |
| [Real-time](25-realtime.md) | WebSocket, SSE e Channels |
| [Validators](14-validators.md) | Validação de dados e unicidade |
| [FAQ](99-faq-troubleshooting.md) | Erros comuns e solução |
