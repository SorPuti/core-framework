# Arquitetura

## Visão geral

Stride é um framework API-first, construído sobre FastAPI, com camadas:

1. **Camada de Configuração** (`strider.config.Settings`, `strider.config.configure`)
2. **Camada de inicialização** (`strider.app.StrideApp`, `create_app`, `get_application`)
3. **Roteamento** (`strider.urls`, `strider.routing.Router`, `AutoRouter`)
4. **Camada de regras de negócio** (`strider.views.ViewSet`, `ModelViewSet`, `APIView`)
5. **Data layer** (`strider.models.Model`, `Field`, `Manager`, `QuerySet`)
6. **Autenticação/Permissões** (`strider.auth`, `strider.permissions`)
7. **Extras** (`strider.messaging`, `strider.tenancy`, `strider.realtime`, `strider.admin`)

## Componentes principais

### StrideApp

- Cria FastAPI com `docs_url`, `openapi_url`, `redoc_url` do settings.
- Registra middleware (CORS, tenancy, custom).
- Garante validação de schemas e auto-collect permissions no startup.
- Inicializa DB via `strider.database.init_db`.
- Monta rota WebSocket fora do stack HTTP para compatibilidade.
- Exponibiliza `app` e `__call__` para ASGI.

### Roteamento

- `strider.urls.autodiscover(settings)` carrega apps em `installed_apps` ou `root_urlconf`.
- `path()` e `include()` criam objetos `URLPattern`/`URLInclude`.
- Permite ViewSets, APIViews, callables e WebSocketView.
- `Router.register_viewset()` implementa rota CRUD (list, create, retrieve, update, patch, delete) e ações customizadas com decorators `@action`.

### ViewSet

- CRUD básico via `ViewSet.list/retrieve/create/update/partial_update/destroy`.
- `ModelViewSet` injeta model + serializer + saída JSON.
- Permissões por `permission_classes`, `permission_classes_by_action`.
- Validação de dados:
  - Pydantic (InputSchema/OutputSchema)
  - `validate_unique_fields` + `UniqueValidator`
  - `validate_field`, `validate_data`, `validate` hooks.
  - `_validate_schemas` cross-check model/schema via `SchemaModelValidator`.

### Models

- Base `strider.models.Model` usa SQLAlchemy declarative e `ModelMeta`.
- `Field` helpers (`pk()`, `string()`, `email()`, `datetime()`, `choice()`, `struct()` etc).
- Manager/QuerySet inspirado em Django (`objects.filter`, `get`, `all`, `count`, `exists`, `select_related`, `prefetch_related`).
- `Model.save()`, `delete()`, e hooks `before_save`, `after_save`, etc.
- `create_tables()` (auto-migrations básicas e sync columns).

### Permissões

- Base `Permission` definido em `strider.permissions`.
- Check global e por objeto em `check_permissions`.
- Classes built-in: `AllowAny`, `DenyAll`, `IsAuthenticated`, `IsAuthenticatedOrReadOnly`, `IsAdmin`, `IsOwner`, `HasRole`.
- Suporta composição: `perm1 & perm2`, `perm1 | perm2`, `~perm`.

### Configurações

- `strider.config.Settings` centraliza app/db/auth/cors/messaging/tenancy etc.
- `.env` resize via `_resolve_env_files_at_bootstrap()`.
- Auto-configura auth via `user_model` e `auth_*`.

## Fluxos principais

### Startup
1. `StrideApp.__init__()` configura logger
2. carrega settings (ou `get_settings()`)
3. cria FastAPI
4. configura CORS, tenancy, middleware, handlers de exceção
5. `autodiscover()` + include routers + ws routes
6. (opcional) admin e health checks
7. `Lifespan`: `_startup` executa model/load, DB init, create_tables, validate viewsets, auto_collect_permissions, callbacks

### Request HTTP
1. FastAPI middleware (CORS, request id, etc)
2. route resolvida pelo Router
3. Permissões via `check_permissions` em ViewSet/APIView
4. Handler CRUD/Action executa DB e serializa response
5. Resposta JSON

### WebSocket
1. `strider.realtime` define handlers `WebSocketView`, `SSEView`
2. routes registradas em `_ws_router` no StrideApp
3. Autenticação e permissão via `AuthenticationMiddleware` e `check_permissions` em `_check_ws_permissions`

## Pontos de entrada

- `create_app`, `get_application` (ASGI app)
- `stride.cli` (commands de migrations/run/tests)
- `strider.urls.autodiscover` (routing)
- `strider.models.init_database` (DB)
- `strider.auth` APIs (login, tokens). 

## Observações de confiabilidade

- Toda documentação criada deve referenciar esses componentes (não suposições).
- Quando detectar comportamento não claro por código, incluir alerta “⚠️ Não documentado no código".
