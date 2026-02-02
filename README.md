# Core Framework

Framework Python para APIs REST de alta performance. Combina a produtividade do Django REST Framework com a velocidade do FastAPI.

## Por que mais um framework?

FastAPI e excelente para performance, mas exige muito codigo repetitivo para CRUD. Django REST Framework e produtivo, mas lento e sem async nativo. Core Framework resolve esse trade-off.

```python
# 30 linhas para uma API completa com CRUD, validacao, permissoes e documentacao
class UserViewSet(ModelViewSet):
    model = User
    input_schema = UserInput
    output_schema = UserOutput
    permission_classes = [IsAuthenticated]
    permission_classes_by_action = {"list": [AllowAny], "destroy": [IsAdmin]}

router = AutoRouter(prefix="/api/v1")
router.register("/users", UserViewSet)
app = CoreApp(routers=[router])

# Resultado: 6 endpoints REST, OpenAPI docs, validacao Pydantic, permissoes por acao
```

## Benchmark

Testes realizados com wrk, 10 threads, 100 conexoes, 30 segundos. Endpoint GET /users/ retornando 100 registros.

```
Framework              Requests/sec    Latency (avg)    Latency (p99)
---------------------------------------------------------------------------
FastAPI puro           15,200          6.5ms            18ms
Core Framework         14,100          7.1ms            21ms
Django + DRF           2,100           47ms             180ms
Flask + SQLAlchemy     3,400           29ms             95ms
```

Core Framework mantem 93% da performance do FastAPI puro. A diferenca de 7% vem da camada de ViewSet e permissoes - overhead aceitavel considerando a reducao de boilerplate.

**Por que Django e tao mais lento?**
- WSGI sincrono bloqueia threads
- Django ORM nao e async (sync_to_async adiciona overhead)
- Serializers DRF usam reflexao pesada

## Comparativo Tecnico

| Aspecto | Django + DRF | FastAPI Puro | Core Framework |
|---------|--------------|--------------|----------------|
| Async nativo | Parcial (sync_to_async) | Total | Total |
| Tipagem | Runtime | Compilacao | Compilacao |
| ORM | Django ORM (sync) | Manual | SQLAlchemy 2.0 (async) |
| Validacao | DRF Serializers | Pydantic | Pydantic |
| ViewSets | Sim | Manual | Sim |
| Permissoes | Sim | Manual | Sim |
| OpenAPI | drf-spectacular | Nativo | Nativo |
| Boilerplate CRUD | Baixo | Alto | Baixo |
| Performance | ~2k req/s | ~15k req/s | ~14k req/s |

## Decisoes Arquiteturais

### SQLAlchemy 2.0 ao inves de Django ORM

Django ORM nao foi projetado para async. O `sync_to_async` e um wrapper que executa queries em thread pool, adicionando overhead e complexidade. SQLAlchemy 2.0 tem async nativo com `asyncpg`.

```python
# Django: sync_to_async adiciona ~2ms por query
users = await sync_to_async(list)(User.objects.filter(is_active=True))

# Core Framework: async nativo, sem overhead
users = await User.objects.using(db).filter(is_active=True).all()
```

Alem disso, SQLAlchemy 2.0 tem tipagem forte com `Mapped[T]`, permitindo que IDEs e mypy detectem erros em tempo de desenvolvimento.

### Pydantic ao inves de DRF Serializers

DRF Serializers usam reflexao pesada (`__getattr__`, metaclasses) para funcionar. Pydantic compila validadores em Rust, resultando em validacao 10-100x mais rapida.

```python
# DRF: ~500us por validacao
class UserSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=100)

# Core Framework: ~5us por validacao
class UserInput(InputSchema):
    email: str
    name: str
```

### ViewSets simplificados

DRF ViewSets tem dispatch complexo com multiplas camadas de mixins. Core Framework usa heranca simples e metodos async diretos.

```python
# Hierarquia DRF: GenericAPIView -> mixins -> GenericViewSet -> ModelViewSet
# Hierarquia Core: ViewSet -> ModelViewSet

# Menos indiracao = menos overhead = codigo mais facil de debugar
```

### Permissoes composiveis

Sistema de permissoes inspirado no DRF, mas com operadores Python para composicao.

```python
# Permissao composta: autenticado E (dono OU admin)
permission = IsAuthenticated() & (IsOwner() | IsAdmin())
```

## Dependencias

O framework usa apenas bibliotecas estaveis e bem mantidas:

| Dependencia | Versao | Proposito |
|-------------|--------|-----------|
| `fastapi` | >=0.100 | Motor HTTP async, OpenAPI automatico |
| `pydantic` | >=2.0 | Validacao e serializacao (core em Rust) |
| `pydantic-settings` | >=2.0 | Configuracao via .env |
| `sqlalchemy` | >=2.0 | ORM async com tipagem forte |
| `asyncpg` | >=0.28 | Driver PostgreSQL async (opcional) |
| `aiosqlite` | >=0.19 | Driver SQLite async (desenvolvimento) |
| `uvicorn` | >=0.23 | Servidor ASGI |
| `python-jose` | >=3.3 | JWT para autenticacao |
| `passlib` | >=1.7 | Hash de senhas (bcrypt, argon2) |
| `aiokafka` | >=0.8 | Cliente Kafka async (opcional) |

**Dependencias opcionais por feature:**
- Messaging: `aiokafka`, `aio-pika` (RabbitMQ), `redis`
- PostgreSQL: `asyncpg`
- Argon2: `argon2-cffi`

## Instalacao

```bash
# Via pip (quando publicado)
pip install core-framework

# Via git (desenvolvimento)
pip install "core-framework @ git+https://github.com/user/core-framework.git"

# Com extras
pip install "core-framework[postgres,kafka]"
```

## Quick Start

```bash
# Criar projeto
core init my-api
cd my-api

# Configurar banco e rodar
core makemigrations --name initial
core migrate
core run
```

Acesse http://localhost:8000/docs para documentacao interativa.

## Estrutura do Projeto

```
/my-api
  /.env                    # Configuracoes (DATABASE_URL, SECRET_KEY)
  /migrations              # Migracoes de banco (geradas automaticamente)
  /src
    /apps
      /users
        models.py          # Models SQLAlchemy
        schemas.py         # Input/Output Pydantic
        views.py           # ViewSets
        routes.py          # Rotas
        permissions.py     # Permissoes customizadas
    main.py                # Entry point
```

## Documentacao

| Guia | Descricao |
|------|-----------|
| [Quickstart](docs/01-quickstart.md) | Primeira API em 5 minutos |
| [ViewSets](docs/02-viewsets.md) | CRUD, actions, hooks |
| [Authentication](docs/03-authentication.md) | JWT, permissoes |
| [Messaging](docs/04-messaging.md) | Kafka, RabbitMQ, Redis |
| [Deployment](docs/07-deployment.md) | Docker, Kubernetes |

[Documentacao completa](docs/README.md)

## Roadmap

### Suporte a WebSockets

Integracao nativa com WebSockets do FastAPI para aplicacoes real-time. Planejado: decorators para handlers, broadcast para grupos, integracao com sistema de permissoes.

```python
# Planejado
@websocket("/ws/chat/{room_id}")
class ChatConsumer(WebSocketConsumer):
    permission_classes = [IsAuthenticated]
    
    async def on_connect(self, websocket, room_id):
        await self.channel_layer.group_add(f"room_{room_id}", websocket)
    
    async def on_message(self, websocket, data):
        await self.channel_layer.group_send(f"room_{data['room_id']}", data)
```

### Cache integrado (Redis)

Camada de cache transparente para QuerySets e respostas de ViewSet. Invalidacao automatica em create/update/delete.

```python
# Planejado
class PostViewSet(ModelViewSet):
    model = Post
    cache_timeout = 300  # 5 minutos
    cache_key_prefix = "posts"
    
    # Cache automatico em list() e retrieve()
    # Invalidacao automatica em create(), update(), destroy()
```

### Rate limiting

Limitacao de requisicoes por IP, usuario ou API key. Configuravel por ViewSet ou action.

```python
# Planejado
class APIViewSet(ModelViewSet):
    throttle_classes = [AnonRateThrottle, UserRateThrottle]
    throttle_rates = {
        "anon": "100/hour",
        "user": "1000/hour",
    }
```

### Background tasks

Sistema de tarefas em background ja implementado. Suporta filas, retry, scheduling.

```python
# Ja disponivel
@task(queue="default", max_retries=3)
async def send_email(user_id: int, template: str):
    user = await User.objects.get(id=user_id)
    await email_service.send(user.email, template)

# Chamar
await send_email.delay(user_id=1, template="welcome")
```

### Admin interface

Interface administrativa auto-gerada a partir dos models. Inspirada no Django Admin, mas com frontend moderno (React/Vue).

```python
# Planejado
from core.admin import AdminSite, ModelAdmin

class UserAdmin(ModelAdmin):
    list_display = ["id", "email", "is_active", "created_at"]
    list_filter = ["is_active", "role"]
    search_fields = ["email", "name"]

admin = AdminSite()
admin.register(User, UserAdmin)
```

### CLI para scaffolding

CLI ja disponivel para operacoes comuns:

```bash
# Ja disponivel
core init my-api              # Criar projeto
core makemigrations --name x  # Gerar migracao
core migrate                  # Aplicar migracoes
core run                      # Rodar servidor
core worker                   # Rodar worker de tasks
core consumer                 # Rodar consumer de mensagens
core docker generate          # Gerar docker-compose.yml

# Planejado
core generate app users       # Gerar app com estrutura padrao
core generate model Post      # Gerar model com CRUD
core generate viewset Post    # Gerar ViewSet a partir de model
```

## Contribuindo

```bash
# Clonar e instalar
git clone https://github.com/user/core-framework.git
cd core-framework
pip install -e ".[dev]"

# Rodar testes
pytest

# Rodar linter
ruff check .
mypy core/
```

## Licenca

MIT
