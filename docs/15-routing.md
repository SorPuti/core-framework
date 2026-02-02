# Routing

Sistema de rotas que gera endpoints automaticamente a partir de ViewSets. Baseado no FastAPI Router, mas com integracao especifica para ViewSets.

## Estrutura de Arquivos

```
/my-project
  /src
    /apps
      /users
        routes.py          # Define rotas do app
        views.py           # ViewSets
      /posts
        routes.py
        views.py
    main.py                # Combina todos os routers
```

## AutoRouter

`AutoRouter` e um wrapper sobre `APIRouter` do FastAPI que adiciona o metodo `register()` para ViewSets.

### Criar Rotas do App

```python
# src/apps/users/routes.py
from core import AutoRouter
from .views import UserViewSet, AuthViewSet

# prefix: prefixo de URL para todos os endpoints deste router
# tags: agrupa endpoints na documentacao OpenAPI
router = AutoRouter(prefix="/users", tags=["Users"])

# register() gera automaticamente rotas CRUD
# "" significa usar apenas o prefix do router
router.register("", UserViewSet)

# Routers separados para contextos diferentes
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
# Todos os sub-routers herdam este prefixo
api_router = AutoRouter(prefix="/api/v1")

# include_router() adiciona todas as rotas do sub-router
api_router.include_router(users_router)      # /api/v1/users/...
api_router.include_router(auth_router)       # /api/v1/auth/...
api_router.include_router(posts_router)      # /api/v1/posts/...

# CoreApp recebe lista de routers
app = CoreApp(
    title="My API",
    routers=[api_router],
)
```

## Rotas Geradas

Para um `ModelViewSet` registrado com `router.register("", UserViewSet)`:

| Metodo | Path | Acao | Nome da Rota |
|--------|------|------|--------------|
| GET | /users/ | list | users-list |
| POST | /users/ | create | users-create |
| GET | /users/{id} | retrieve | users-retrieve |
| PUT | /users/{id} | update | users-update |
| PATCH | /users/{id} | partial_update | users-partial-update |
| DELETE | /users/{id} | destroy | users-destroy |

**Nome da rota**: Gerado automaticamente. Util para `url_for()` em templates ou testes.

## Custom Actions

Metodos decorados com `@action` geram rotas adicionais.

```python
class UserViewSet(ModelViewSet):
    model = User
    
    @action(methods=["POST"], detail=False)
    async def bulk_create(self, request, db, **kwargs):
        """
        POST /users/bulk_create
        
        detail=False: Acao na colecao, sem {id} na URL
        """
        pass
    
    @action(methods=["GET"], detail=True)
    async def posts(self, request, db, **kwargs):
        """
        GET /users/{id}/posts
        
        detail=True: Acao em recurso especifico, com {id} na URL
        """
        pass
    
    @action(methods=["POST"], detail=True, url_path="change-password")
    async def change_password(self, request, db, **kwargs):
        """
        POST /users/{id}/change-password
        
        url_path: Customiza o path (padrao seria /users/{id}/change_password)
        Util para URLs com hifen ou caracteres especiais
        """
        pass
```

**Parametros do @action**:

| Parametro | Tipo | Descricao |
|-----------|------|-----------|
| `methods` | list[str] | Metodos HTTP aceitos |
| `detail` | bool | True: `/{id}/action`, False: `/action` |
| `url_path` | str | Path customizado (padrao: nome do metodo) |
| `permission_classes` | list | Override de permissoes para esta acao |

## Prefixos e Tags

```python
# Prefixo no router
router = AutoRouter(prefix="/users", tags=["Users"])

# Prefixo adicional no register
router.register("/admins", AdminViewSet)  # Resultado: /users/admins/

# Tags no ViewSet sobrescrevem tags do router
class UserViewSet(ModelViewSet):
    tags = ["Users", "Admin"]  # Aparece em ambas as tags no Swagger
```

## Incluir Routers com Prefixo

```python
api_router = AutoRouter(prefix="/api/v1")

# Incluir normalmente
api_router.include_router(users_router)      # /api/v1/users/
api_router.include_router(posts_router)      # /api/v1/posts/

# Incluir com prefixo adicional
api_router.include_router(
    admin_router,
    prefix="/admin",  # /api/v1/admin/...
    tags=["Admin"],   # Sobrescreve tags do admin_router
)
```

## Rotas Manuais

Para endpoints que nao sao ViewSets, use decorators do FastAPI diretamente.

```python
from core import AutoRouter

router = AutoRouter(prefix="/health", tags=["System"])

@router.get("")
async def health_check():
    """GET /health"""
    return {"status": "healthy"}

@router.get("/version")
async def version():
    """GET /health/version"""
    return {"version": "1.0.0"}
```

**Quando usar rotas manuais**: Health checks, webhooks, endpoints de integracao que nao seguem padrao REST.

## Lookup Field Customizado

Por padrao, rotas usam `{id}` como identificador. Altere com `lookup_field`.

```python
class UserViewSet(ModelViewSet):
    model = User
    lookup_field = "username"  # Usa username ao inves de id
```

Rotas geradas:

| Path | Exemplo |
|------|---------|
| /users/{username} | /users/john_doe |

**Requisito**: O campo deve ser unico no banco. O framework detecta o tipo automaticamente (int, UUID, string).

## Multiplos ViewSets no Mesmo Router

```python
router = AutoRouter(prefix="/api/v1", tags=["API"])

# Cada register adiciona rotas com prefixo diferente
router.register("/users", UserViewSet)       # /api/v1/users/
router.register("/posts", PostViewSet)       # /api/v1/posts/
router.register("/comments", CommentViewSet) # /api/v1/comments/
```

## Versionamento de API

```python
# Routers separados por versao
v1_router = AutoRouter(prefix="/api/v1")
v1_router.register("/users", UserViewSetV1)

v2_router = AutoRouter(prefix="/api/v2")
v2_router.register("/users", UserViewSetV2)

# Ambas as versoes ativas simultaneamente
app = CoreApp(
    title="My API",
    routers=[v1_router, v2_router],
)
```

**Estrategia de versionamento**: Mantenha versoes antigas funcionando enquanto clientes migram. Deprecie com headers antes de remover.

## Documentacao OpenAPI

Tags organizam endpoints no Swagger UI e ReDoc.

```python
router = AutoRouter(prefix="/users", tags=["Users"])
```

Endpoints aparecem agrupados por tag. Use tags descritivas para facilitar navegacao.

---

Proximo: [Serializers](16-serializers.md) - Validacao e transformacao de dados.
