# Permissions

Sistema de controle de acesso baseado em classes. Permissoes determinam se um usuario pode executar uma acao em um endpoint ou objeto.

## Estrutura de Arquivos

```
/my-project
  /src
    /apps
      /users
        permissions.py     # Permissoes customizadas do app
        views.py           # ViewSets que usam as permissoes
```

## Permissoes Built-in

| Classe | Comportamento | Codigo HTTP em falha |
|--------|---------------|---------------------|
| `AllowAny` | Permite qualquer acesso, mesmo sem token | N/A |
| `IsAuthenticated` | Exige `request.state.user` nao-nulo | 401 |
| `IsAuthenticatedOrReadOnly` | GET/HEAD/OPTIONS publicos, outros autenticados | 401 |
| `IsAdmin` | Exige `user.is_admin=True` ou `user.is_superuser=True` | 403 |
| `IsOwner` | Exige que `obj.user_id == user.id` | 403 |
| `HasRole` | Exige role especifico em `user.roles` | 403 |

## Usar em ViewSet

### Permissao Global

Aplica a mesma permissao para todas as acoes do ViewSet.

```python
# src/apps/posts/views.py
from core import ModelViewSet
from core.permissions import IsAuthenticated
from .models import Post

class PostViewSet(ModelViewSet):
    model = Post
    
    # Todas as acoes (list, create, retrieve, update, destroy)
    # exigem usuario autenticado
    permission_classes = [IsAuthenticated]
```

### Permissao por Acao

Permite configuracao granular por acao CRUD.

```python
from core import ModelViewSet
from core.permissions import AllowAny, IsAuthenticated, IsAdmin, IsOwner

class PostViewSet(ModelViewSet):
    model = Post
    
    # Fallback para acoes nao listadas em permission_classes_by_action
    permission_classes = [IsAuthenticated]
    
    # Override especifico por acao
    # Acoes validas: list, create, retrieve, update, partial_update, destroy
    permission_classes_by_action = {
        "list": [AllowAny],           # GET /posts/ - qualquer um pode listar
        "retrieve": [AllowAny],       # GET /posts/{id} - qualquer um pode ver
        "create": [IsAuthenticated],  # POST /posts/ - precisa estar logado
        "update": [IsOwner],          # PUT /posts/{id} - apenas autor
        "partial_update": [IsOwner],  # PATCH /posts/{id} - apenas autor
        "destroy": [IsAdmin],         # DELETE /posts/{id} - apenas admin
    }
```

**Ordem de resolucao**: `permission_classes_by_action[acao]` > `permission_classes` > `[IsAuthenticated]` (padrao do framework)

### Permissao em Custom Action

O parametro `permission_classes` do decorator `@action` sobrescreve qualquer configuracao do ViewSet.

```python
from core import ModelViewSet, action
from core.permissions import IsAdmin

class PostViewSet(ModelViewSet):
    model = Post
    permission_classes = [AllowAny]  # Padrao: publico
    
    @action(methods=["POST"], detail=True, permission_classes=[IsAdmin])
    async def publish(self, request, db, **kwargs):
        """
        POST /posts/{id}/publish
        
        Mesmo com ViewSet publico, esta acao exige admin.
        permission_classes do @action tem precedencia absoluta.
        """
        post = await self.get_object(db, **kwargs)
        post.published = True
        await post.save(db)
        return {"status": "published"}
```

## Criar Permissao Customizada

### Arquivo de Permissoes

```python
# src/apps/users/permissions.py
from core.permissions import Permission
from fastapi import Request

class IsPremiumUser(Permission):
    """
    Permite acesso apenas para usuarios com assinatura premium.
    
    Requer que o model User tenha campo is_premium: bool
    """
    
    # Mensagem retornada no JSON de erro
    message = "Premium subscription required"
    
    # Codigo HTTP retornado (padrao: 403 Forbidden)
    status_code = 403
    
    async def has_permission(self, request: Request, view=None) -> bool:
        """
        Verificacao a nivel de endpoint.
        
        Chamado ANTES de qualquer operacao no banco.
        Se retornar False, a acao e bloqueada imediatamente.
        
        Args:
            request: Request FastAPI com state.user populado (ou None)
            view: Instancia do ViewSet (pode ser None em alguns contextos)
        
        Returns:
            True para permitir, False para negar
        """
        # getattr com default None evita AttributeError se state.user nao existir
        user = getattr(request.state, "user", None)
        if user is None:
            return False
        
        # Verifica atributo is_premium no usuario
        return getattr(user, "is_premium", False)
```

### Usar no ViewSet

```python
# src/apps/premium/views.py
from core import ModelViewSet
from src.apps.users.permissions import IsPremiumUser
from .models import PremiumContent

class PremiumContentViewSet(ModelViewSet):
    model = PremiumContent
    permission_classes = [IsPremiumUser]
```

## Permissao a Nivel de Objeto

Para verificacoes que dependem do objeto sendo acessado (ex: apenas autor pode editar).

```python
# src/apps/posts/permissions.py
from core.permissions import Permission
from fastapi import Request

class IsPostOwner(Permission):
    """
    Permite acesso apenas ao autor do post.
    
    Diferente de IsOwner built-in, esta versao e especifica
    para posts e usa author_id ao inves de user_id.
    """
    
    message = "You can only edit your own posts"
    
    async def has_permission(self, request: Request, view=None) -> bool:
        """
        Verificacao geral - sempre True.
        
        A verificacao real acontece em has_object_permission.
        Retornar True aqui permite que o fluxo continue ate
        o objeto ser carregado do banco.
        """
        return True
    
    async def has_object_permission(self, request: Request, view=None, obj=None) -> bool:
        """
        Verificacao a nivel de objeto.
        
        Chamado APOS o objeto ser carregado do banco.
        Apenas para acoes que operam em objeto especifico:
        retrieve, update, partial_update, destroy, e actions com detail=True.
        
        Args:
            obj: Instancia do model carregada do banco
        """
        if obj is None:
            return True
        
        user = getattr(request.state, "user", None)
        if user is None:
            return False
        
        # Compara author_id do post com id do usuario logado
        return obj.author_id == user.id
```

**Fluxo de verificacao**:
1. `has_permission()` e chamado
2. Se False, retorna 403 imediatamente
3. Se True, objeto e carregado do banco
4. `has_object_permission()` e chamado com o objeto
5. Se False, retorna 403
6. Se True, acao e executada

## Combinar Permissoes

### AND (todas devem passar)

Lista de permissoes funciona como AND. Todas devem retornar True.

```python
from core.permissions import IsAuthenticated, IsAdmin

# Usuario deve estar logado E ser admin
# Se qualquer uma falhar, acesso e negado
permission_classes = [IsAuthenticated, IsAdmin]
```

### OR (uma deve passar)

Crie permissao customizada que implementa logica OR.

```python
from core.permissions import Permission, IsAdmin, IsOwner

class IsAdminOrOwner(Permission):
    """
    Permite acesso se usuario for admin OU dono do objeto.
    
    Util para endpoints onde admins podem gerenciar qualquer recurso,
    mas usuarios comuns so podem gerenciar os proprios.
    """
    
    message = "Must be admin or owner"
    
    async def has_permission(self, request, view=None) -> bool:
        # Verificacao geral - permite continuar para verificacao de objeto
        return True
    
    async def has_object_permission(self, request, view=None, obj=None) -> bool:
        admin_perm = IsAdmin()
        owner_perm = IsOwner()
        
        # Verifica se e admin (nao precisa de objeto)
        is_admin = await admin_perm.has_permission(request, view)
        if is_admin:
            return True
        
        # Se nao e admin, verifica se e dono
        is_owner = await owner_perm.has_object_permission(request, view, obj)
        return is_owner
```

### Operadores Python

Permissoes suportam operadores `&`, `|`, `~` para composicao.

```python
from core.permissions import IsAuthenticated, IsAdmin

# AND - ambas devem passar
combined = IsAuthenticated() & IsAdmin()

# OR - uma deve passar
combined = IsAuthenticated() | IsAdmin()

# NOT - inverte resultado
combined = ~IsAdmin()  # Permite apenas quem NAO e admin
```

**Nota**: Operadores criam novas instancias de permissao. Use em `permission_classes` como `[combined]`.

## HasRole

Verifica roles especificos do usuario.

```python
from core.permissions import HasRole

class AdminViewSet(ModelViewSet):
    model = AdminLog
    # Usuario deve ter role "admin" OU "superuser"
    permission_classes = [HasRole("admin", "superuser")]
```

**Requisito no Model**: User deve ter campo `roles`:

```python
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import String

class User(AbstractUser):
    # PostgreSQL: usa ARRAY nativo
    roles: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    
    # SQLite/MySQL: armazena como JSON string
    # roles: Mapped[list[str]] = mapped_column(JSON, default=list)
```

## Resposta de Erro

Quando permissao falha, o framework retorna:

```json
{
  "detail": "Premium subscription required"
}
```

Com status code definido na permissao (padrao 403).

---

Proximo: [Auth Backends](12-auth-backends.md) - Customizacao de mecanismos de autenticacao.
