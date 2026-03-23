# Core Concepts

## Auto-discovery

- `settings.installed_apps`: lista de apps que devem ser carregadas.
- `strider.urls.autodiscover()` busca `urls.py` de cada app via `_resolve_app_module`.
- `settings.root_urlconf` pode substituir auto-discover.

## Routes

- `path(route, view)`: define rota.
- `URLPattern` encapsula rota + view.
- `include(module)`: reúne sub-rotas.
- `Router.register_viewset(...)`: cria rotas CRUD + actions customizadas.
- `Router.add_api_route` evita duplicação de path+method.

## ViewSets & APIViews

### ViewSet (CRUD)
- Métodos padrão:
  - `list`: `GET /resource/`
  - `retrieve`: `GET /resource/{id}`
  - `create`: `POST /resource/`
  - `update`: `PUT /resource/{id}`
  - `partial_update`: `PATCH /resource/{id}`
  - `destroy`: `DELETE /resource/{id}`
- Hooks:
  - `perform_create_validation`, `after_create`, `perform_update_validation`, `after_update`
  - `validate_data`, `validate_field`, `validate_unique_fields`.
- Ações customizadas com `@action(methods=[...], detail=True|False, ... )`.

### APIView (genérico)
- Usa methods `get/post/put/patch/delete`.
- `check_permissions` é chamado antes da execução.
- `as_route(path, methods)` cria endpoint para um modo estilo Django.

## Permissions

- Base `Permission` com `has_permission` e `has_object_permission`.
- `check_permissions` lança `HTTPException` ao falhar.
- Composição:
  - `IsAuthenticated() & IsOwner()`
  - `IsAdmin() | HasRole("staff")`

## Models and Fields

### Model
- Base `strider.models.Model` com hooks (`before_save`, `after_save`, etc).
- `Field` helpers para declarar colunas.
- `Manager` (`objects`) para queries: `filter`, `get`, `first`, `all`, `count`, `exists`, etc.

### DB Lifecycle
- `init_db(settings)` em `strider.database`
- `create_tables()` cria e sincroniza colunas.
- `close_database()` / `close_replicas()` em shutdown.

## Settings

- `Settings` usa `pydantic-settings`.
- Campos importantes: `database_url`, `app_name`, `debug`, `installed_apps`, `user_model`, `middleware`, `tenancy_enabled`, `auto_create_tables`.
- Auto-configuração JWT/auth via `auth_*`, `user_model`.

## Authentication (Auth)

- Backends registrados em `strider.auth`. (ModelBackend, TokenAuthBackend, etc)
- Middleware: `AuthenticationMiddleware` e `OptionalAuthenticationMiddleware`.
- Decorators: `login_required`, `require_permission`, `require_group`, etc.

## Realtime

- `WebSocketView` e `SSEView` em `strider.realtime`.
- Funções de autenticação em WebSocket: `_authenticate_ws`, `_check_ws_permissions`.
- Rotas WS registradas em `_ws_router` fora da stack HTTP.

## Messaging e Workers

- `strider.messaging` e `strider.tasks` fornecem integrações Kafka/RabbitMQ/Redis.
- Registro de produtores/consumidores em runtime.
- Não há funcionamento obrigatório sem configuração.
