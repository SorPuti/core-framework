# Dependencies

Sistema de Dependency Injection integrado com FastAPI. Fornece dependencias prontas para banco de dados, autenticacao e configuracoes.

## Dependencias Disponiveis

| Dependencia | Retorno | Uso |
|-------------|---------|-----|
| `get_db` | `AsyncSession` | Sessao de banco de dados |
| `get_current_user` | `User` | Usuario autenticado (erro se nao logado) |
| `get_optional_user` | `User \| None` | Usuario ou None (sem erro) |
| `require_user` | `User` | Alias para get_current_user |
| `get_settings_dep` | `Settings` | Configuracoes da aplicacao |
| `get_request_context` | `dict` | Contexto da requisicao |

## Type Aliases (Annotated)

Para sintaxe mais limpa com tipagem:

```python
from core.dependencies import (
    DatabaseSession,    # Annotated[AsyncSession, Depends(get_db)]
    CurrentUser,        # Annotated[Any, Depends(get_current_user)]
    OptionalUser,       # Annotated[Any | None, Depends(get_optional_user)]
    AppSettings,        # Annotated[Settings, Depends(get_settings_dep)]
    RequestContext,     # Annotated[dict, Depends(get_request_context)]
)
```

## get_db - Sessao de Banco

Fornece sessao de banco de dados com gerenciamento automatico de transacao.

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from core.dependencies import get_db

@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db)):
    """
    Sessao e injetada automaticamente.
    
    Comportamento:
    - Commit automatico se nenhuma excecao
    - Rollback automatico em caso de excecao
    - Close automatico ao final
    """
    users = await User.objects.using(db).all()
    return users
```

**Ciclo de vida**:
1. Sessao criada no inicio do request
2. Yield para o handler
3. Commit se sucesso, Rollback se excecao
4. Close sempre executado

### Com Type Alias

```python
from core.dependencies import DatabaseSession

@router.get("/users")
async def list_users(db: DatabaseSession):
    """
    DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
    
    Mesma funcionalidade, sintaxe mais limpa.
    """
    users = await User.objects.using(db).all()
    return users
```

## get_current_user - Usuario Autenticado

Retorna usuario autenticado ou levanta 401.

```python
from core.dependencies import get_current_user

@router.get("/me")
async def get_me(user = Depends(get_current_user)):
    """
    Requer header: Authorization: Bearer <token>
    
    Se token invalido ou ausente: 401 Unauthorized
    Se usuario nao encontrado: 401 Unauthorized
    """
    return {"id": user.id, "email": user.email}
```

**Efeitos colaterais**:
- Popula `request.state.user` com o usuario
- Popula `request.state.db` com a sessao

### Com Type Alias

```python
from core.dependencies import CurrentUser

@router.get("/me")
async def get_me(user: CurrentUser):
    return {"id": user.id, "email": user.email}
```

## get_optional_user - Usuario Opcional

Retorna usuario se autenticado, None caso contrario. Nunca levanta excecao.

```python
from core.dependencies import get_optional_user

@router.get("/posts")
async def list_posts(user = Depends(get_optional_user)):
    """
    Util para endpoints que funcionam com ou sem autenticacao.
    
    Exemplo: mostrar posts publicos para todos,
    posts privados apenas para o autor.
    """
    if user:
        # Usuario logado - mostra posts publicos + privados do usuario
        posts = await Post.objects.using(db).filter(
            or_(
                Post.is_public == True,
                Post.author_id == user.id,
            )
        ).all()
    else:
        # Anonimo - mostra apenas posts publicos
        posts = await Post.objects.using(db).filter(is_public=True).all()
    
    return posts
```

### Com Type Alias

```python
from core.dependencies import OptionalUser

@router.get("/posts")
async def list_posts(user: OptionalUser):
    # user pode ser User ou None
    pass
```

## get_settings_dep - Configuracoes

Retorna instancia singleton das configuracoes.

```python
from core.dependencies import get_settings_dep
from core.config import Settings

@router.get("/config")
async def get_config(settings: Settings = Depends(get_settings_dep)):
    """
    Acesso as configuracoes da aplicacao.
    
    Util para endpoints que precisam de valores de configuracao.
    """
    return {
        "app_name": settings.app_name,
        "environment": settings.environment,
    }
```

### Com Type Alias

```python
from core.dependencies import AppSettings

@router.get("/config")
async def get_config(settings: AppSettings):
    return {"app_name": settings.app_name}
```

## get_request_context - Contexto

Retorna informacoes sobre a requisicao atual.

```python
from core.dependencies import get_request_context, RequestContext

@router.post("/audit")
async def create_audit_log(context: RequestContext):
    """
    Util para logging e auditoria.
    
    Retorna:
    {
        "method": "POST",
        "url": "http://...",
        "client_ip": "192.168.1.1",
        "user_agent": "Mozilla/...",
        "user": <User ou None>
    }
    """
    await AuditLog.create(
        action="create",
        ip_address=context["client_ip"],
        user_id=context["user"].id if context["user"] else None,
    )
```

## Configurar Autenticacao

Antes de usar `get_current_user`, configure as funcoes de autenticacao:

```python
# src/main.py
from core.dependencies import configure_auth
from core.auth import verify_token

async def load_user(user_id: str) -> User | None:
    """
    Funcao que carrega usuario por ID.
    
    Chamada apos decodificar o token.
    Deve retornar User ou None.
    """
    from core.models import get_session
    async with get_session() as db:
        return await User.objects.using(db).filter(id=int(user_id)).first()

def decode_token(token: str) -> dict:
    """
    Funcao que decodifica o token JWT.
    
    Deve retornar dict com "sub" ou "user_id".
    Levanta excecao se token invalido.
    """
    return verify_token(token, token_type="access")

# Configura no startup da aplicacao
configure_auth(
    user_loader=load_user,
    token_decoder=decode_token,
)
```

**Nota**: Se usar `core.auth.configure_auth()`, isso ja e feito automaticamente.

## PaginationParams - Paginacao

Classe de dependencia para parametros de paginacao.

```python
from core.dependencies import PaginationParams, get_db

@router.get("/users")
async def list_users(
    pagination: PaginationParams = Depends(),
    db = Depends(get_db),
):
    """
    Query params aceitos:
    - page: int (default: 1)
    - page_size: int (default: 20, max: 100)
    
    Exemplo: GET /users?page=2&page_size=50
    """
    users = await User.objects.using(db)\
        .offset(pagination.offset)\
        .limit(pagination.limit)\
        .all()
    
    return {
        "items": users,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }
```

**Propriedades**:
- `pagination.page`: Numero da pagina (minimo 1)
- `pagination.page_size`: Itens por pagina (limitado a max_page_size)
- `pagination.offset`: Calculado: `(page - 1) * page_size`
- `pagination.limit`: Igual a page_size

## SortingParams - Ordenacao

Classe de dependencia para parametros de ordenacao.

```python
from core.dependencies import SortingParams, get_db

@router.get("/users")
async def list_users(
    sorting: SortingParams = Depends(),
    db = Depends(get_db),
):
    """
    Query params aceitos:
    - sort_by: str (nome do campo)
    - sort_order: "asc" | "desc" (default: "asc")
    
    Exemplo: GET /users?sort_by=created_at&sort_order=desc
    """
    users = await User.objects.using(db)\
        .order_by(*sorting.order_by)\
        .all()
    
    return users
```

### Com Campos Permitidos

```python
@router.get("/users")
async def list_users(
    sort_by: str | None = None,
    sort_order: str = "asc",
    db = Depends(get_db),
):
    """
    Restringe campos que podem ser usados para ordenacao.
    Previne ordenacao por campos sensiveis ou inexistentes.
    """
    sorting = SortingParams(
        sort_by=sort_by,
        sort_order=sort_order,
        allowed_fields=["name", "email", "created_at"],
    )
    
    users = await User.objects.using(db)\
        .order_by(*sorting.order_by)\
        .all()
    
    return users
```

## DependencyFactory - Factory Customizada

Para criar dependencias que precisam de outras dependencias.

```python
from core.dependencies import DependencyFactory, get_db

class UserService:
    """Servico com logica de negocio."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_user(self, user_id: int) -> User:
        return await User.objects.using(self.db).get(id=user_id)
    
    async def create_user(self, email: str, password: str) -> User:
        user = User(email=email)
        user.set_password(password)
        await user.save(self.db)
        return user

# Cria factory que injeta db automaticamente
user_service_dep = DependencyFactory(UserService)

@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    service: UserService = Depends(user_service_dep),
):
    """
    UserService e instanciado com db injetado.
    Permite separar logica de negocio do handler.
    """
    return await service.get_user(user_id)
```

**Vantagem**: Separa logica de negocio em classes testáveis. O handler fica responsavel apenas por receber request e retornar response.

## Combinar Dependencias

```python
from core.dependencies import DatabaseSession, CurrentUser, AppSettings

@router.post("/orders")
async def create_order(
    db: DatabaseSession,
    user: CurrentUser,
    settings: AppSettings,
):
    """
    Multiplas dependencias injetadas.
    
    Ordem de execucao:
    1. get_db (cria sessao)
    2. get_current_user (valida token, carrega user)
    3. get_settings_dep (retorna settings)
    """
    if not settings.orders_enabled:
        raise HTTPException(400, "Orders disabled")
    
    order = Order(user_id=user.id)
    await order.save(db)
    return order
```

---

Proximo: [Views](19-views.md) - Classes de views disponiveis.
