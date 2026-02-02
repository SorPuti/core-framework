# Permissions

Sistema de permissoes para controle de acesso.

## Estrutura de Arquivos

```
/my-project
  /src
    /apps
      /users
        permissions.py     # Permissoes customizadas
        views.py           # Usa as permissoes
```

## Permissoes Built-in

| Classe | Descricao |
|--------|-----------|
| `AllowAny` | Permite qualquer acesso |
| `IsAuthenticated` | Requer usuario logado |
| `IsAuthenticatedOrReadOnly` | Leitura publica, escrita autenticada |
| `IsAdmin` | Requer is_admin ou is_superuser |
| `IsOwner` | Apenas dono do objeto |
| `HasRole` | Requer role especifico |

## Usar em ViewSet

### Permissao Global

```python
# src/apps/posts/views.py
from core import ModelViewSet
from core.permissions import IsAuthenticated
from .models import Post

class PostViewSet(ModelViewSet):
    model = Post
    permission_classes = [IsAuthenticated]  # Todas as acoes requerem login
```

### Permissao por Acao

```python
from core import ModelViewSet
from core.permissions import AllowAny, IsAuthenticated, IsAdmin, IsOwner

class PostViewSet(ModelViewSet):
    model = Post
    
    # Padrao para todas as acoes
    permission_classes = [IsAuthenticated]
    
    # Override por acao
    permission_classes_by_action = {
        "list": [AllowAny],           # GET /posts/ - publico
        "retrieve": [AllowAny],       # GET /posts/{id} - publico
        "create": [IsAuthenticated],  # POST /posts/ - logado
        "update": [IsOwner],          # PUT /posts/{id} - apenas dono
        "partial_update": [IsOwner],  # PATCH /posts/{id} - apenas dono
        "destroy": [IsAdmin],         # DELETE /posts/{id} - apenas admin
    }
```

### Permissao em Custom Action

```python
from core import ModelViewSet, action
from core.permissions import IsAdmin

class PostViewSet(ModelViewSet):
    model = Post
    
    @action(methods=["POST"], detail=True, permission_classes=[IsAdmin])
    async def publish(self, request, db, **kwargs):
        """Apenas admin pode publicar."""
        post = await self.get_object(db, **kwargs)
        post.published = True
        await post.save(db)
        return {"status": "published"}
```

## Criar Permissao Customizada

### Passo 1: Criar Arquivo

```python
# src/apps/users/permissions.py
from core.permissions import Permission
from fastapi import Request

class IsPremiumUser(Permission):
    """Permite apenas usuarios premium."""
    
    message = "Premium subscription required"
    status_code = 403
    
    async def has_permission(self, request: Request, view=None) -> bool:
        user = getattr(request.state, "user", None)
        if user is None:
            return False
        return getattr(user, "is_premium", False)
```

### Passo 2: Usar no ViewSet

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

Para verificar permissao em um objeto especifico (ex: apenas dono pode editar):

```python
# src/apps/posts/permissions.py
from core.permissions import Permission
from fastapi import Request

class IsPostOwner(Permission):
    """Permite apenas o autor do post."""
    
    message = "You can only edit your own posts"
    
    async def has_permission(self, request: Request, view=None) -> bool:
        # Permissao geral - sempre True
        # Verificacao real e feita em has_object_permission
        return True
    
    async def has_object_permission(self, request: Request, view=None, obj=None) -> bool:
        if obj is None:
            return True
        
        user = getattr(request.state, "user", None)
        if user is None:
            return False
        
        # Verifica se o usuario e o autor
        return obj.author_id == user.id
```

## Combinar Permissoes

### AND (todas devem passar)

```python
from core.permissions import IsAuthenticated, IsAdmin

# Usuario deve estar logado E ser admin
permission_classes = [IsAuthenticated, IsAdmin]
```

### OR (uma deve passar)

```python
from core.permissions import Permission, IsAdmin, IsOwner

class IsAdminOrOwner(Permission):
    """Admin ou dono do objeto."""
    
    message = "Must be admin or owner"
    
    async def has_permission(self, request, view=None) -> bool:
        return True
    
    async def has_object_permission(self, request, view=None, obj=None) -> bool:
        admin_perm = IsAdmin()
        owner_perm = IsOwner()
        
        is_admin = await admin_perm.has_permission(request, view)
        is_owner = await owner_perm.has_object_permission(request, view, obj)
        
        return is_admin or is_owner
```

### Usando Operadores

```python
from core.permissions import IsAuthenticated, IsAdmin

# AND
combined = IsAuthenticated() & IsAdmin()

# OR
combined = IsAuthenticated() | IsAdmin()

# NOT
combined = ~IsAdmin()  # Nao e admin
```

## HasRole

```python
from core.permissions import HasRole

class AdminViewSet(ModelViewSet):
    model = AdminLog
    permission_classes = [HasRole("admin", "superuser")]
```

Requer que o User tenha campo `roles`:

```python
class User(AbstractUser):
    roles: Mapped[list[str]] = mapped_column(default=list)
```

## Mensagens de Erro

```python
class IsPremiumUser(Permission):
    message = "Assinatura premium necessaria"  # Mensagem customizada
    status_code = 403  # Codigo HTTP (padrao: 403)
```

Resposta de erro:

```json
{
  "detail": "Assinatura premium necessaria"
}
```

## Fluxo de Verificacao

1. Request chega no endpoint
2. `has_permission()` e chamado
3. Se False, retorna erro imediatamente
4. Se True e endpoint acessa objeto, `has_object_permission()` e chamado
5. Se False, retorna erro
6. Se True, executa a acao

## Resumo

1. Use `permission_classes` para permissao global no ViewSet
2. Use `permission_classes_by_action` para permissao por acao
3. Crie permissoes customizadas em `permissions.py` do app
4. Implemente `has_permission()` para verificacao geral
5. Implemente `has_object_permission()` para verificacao de objeto

Next: [Auth Backends](12-auth-backends.md)
