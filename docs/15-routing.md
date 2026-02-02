# Routing

Sistema de rotas automaticas para ViewSets.

## Estrutura de Arquivos

```
/my-project
  /src
    /apps
      /users
        routes.py          # Rotas do app
        views.py
      /posts
        routes.py
        views.py
    main.py                # Registra todas as rotas
```

## AutoRouter

Gera rotas automaticamente a partir de ViewSets.

### Criar Rotas do App

```python
# src/apps/users/routes.py
from core import AutoRouter
from .views import UserViewSet, AuthViewSet

router = AutoRouter(prefix="/users", tags=["Users"])
router.register("", UserViewSet)

auth_router = AutoRouter(prefix="/auth", tags=["Auth"])
auth_router.register("", AuthViewSet)
```

### Registrar no Main

```python
# src/main.py
from core import CoreApp, AutoRouter
from src.apps.users.routes import router as users_router, auth_router
from src.apps.posts.routes import router as posts_router

# Router principal com prefixo da API
api_router = AutoRouter(prefix="/api/v1")
api_router.include_router(users_router)
api_router.include_router(auth_router)
api_router.include_router(posts_router)

app = CoreApp(
    title="My API",
    routers=[api_router],
)
```

## Rotas Geradas

Para um `ModelViewSet`:

```python
router.register("", UserViewSet)
```

| Metodo | Path | Action | Nome |
|--------|------|--------|------|
| GET | /users/ | list | users-list |
| POST | /users/ | create | users-create |
| GET | /users/{id} | retrieve | users-retrieve |
| PUT | /users/{id} | update | users-update |
| PATCH | /users/{id} | partial_update | users-partial-update |
| DELETE | /users/{id} | destroy | users-destroy |

## Custom Actions

```python
class UserViewSet(ModelViewSet):
    model = User
    
    @action(methods=["POST"], detail=False)
    async def bulk_create(self, request, db, **kwargs):
        """POST /users/bulk_create"""
        pass
    
    @action(methods=["GET"], detail=True)
    async def posts(self, request, db, **kwargs):
        """GET /users/{id}/posts"""
        pass
    
    @action(methods=["POST"], detail=True, url_path="change-password")
    async def change_password(self, request, db, **kwargs):
        """POST /users/{id}/change-password"""
        pass
```

| Parametro | Descricao |
|-----------|-----------|
| `methods` | Lista de metodos HTTP |
| `detail` | True = /{id}/action, False = /action |
| `url_path` | Path customizado (padrao: nome do metodo) |
| `permission_classes` | Override de permissoes |

## Prefixos e Tags

```python
# Prefixo no router
router = AutoRouter(prefix="/users", tags=["Users"])

# Prefixo no register
router.register("/admins", AdminViewSet)  # /users/admins/

# Tags no ViewSet
class UserViewSet(ModelViewSet):
    tags = ["Users", "Admin"]  # Override das tags do router
```

## Incluir Routers

```python
# Router principal
api_router = AutoRouter(prefix="/api/v1")

# Incluir sub-routers
api_router.include_router(users_router)      # /api/v1/users/
api_router.include_router(posts_router)      # /api/v1/posts/
api_router.include_router(comments_router)   # /api/v1/comments/

# Incluir com prefixo adicional
api_router.include_router(
    admin_router,
    prefix="/admin",  # /api/v1/admin/...
    tags=["Admin"],
)
```

## Rotas Manuais

Para endpoints que nao sao ViewSets:

```python
from core import AutoRouter
from fastapi import Request

router = AutoRouter(prefix="/health", tags=["System"])

@router.get("")
async def health_check():
    return {"status": "healthy"}

@router.get("/version")
async def version():
    return {"version": "1.0.0"}
```

## Lookup Field Customizado

```python
class UserViewSet(ModelViewSet):
    model = User
    lookup_field = "username"  # Usa username ao inves de id
```

Rotas geradas:

| Path | Exemplo |
|------|---------|
| /users/{username} | /users/john_doe |

## Multiplos ViewSets no Mesmo Router

```python
router = AutoRouter(prefix="/api/v1", tags=["API"])

router.register("/users", UserViewSet)
router.register("/posts", PostViewSet)
router.register("/comments", CommentViewSet)
```

## Versionamento

```python
# v1
v1_router = AutoRouter(prefix="/api/v1")
v1_router.register("/users", UserViewSetV1)

# v2
v2_router = AutoRouter(prefix="/api/v2")
v2_router.register("/users", UserViewSetV2)

app = CoreApp(
    title="My API",
    routers=[v1_router, v2_router],
)
```

## Documentacao OpenAPI

Tags organizam a documentacao:

```python
router = AutoRouter(prefix="/users", tags=["Users"])
```

No Swagger UI, endpoints aparecem agrupados por tag.

## Resumo

1. Crie `routes.py` em cada app
2. Use `AutoRouter` para criar routers
3. Use `router.register()` para registrar ViewSets
4. Use `api_router.include_router()` para combinar routers
5. Registre no `CoreApp` com `routers=[api_router]`

Next: [Serializers](16-serializers.md)
