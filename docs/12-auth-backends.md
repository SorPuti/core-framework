# Auth Backends

Backends de autenticacao customizaveis.

## Backends Disponiveis

| Backend | Descricao |
|---------|-----------|
| `ModelBackend` | Email/senha via banco de dados (padrao) |
| `TokenAuthBackend` | Token JWT no header Authorization |
| `MultiBackend` | Tenta multiplos backends em sequencia |

## Estrutura de Arquivos

```
/my-project
  /src
    /apps
      /users
        backends.py        # Backends customizados
        models.py
    main.py                # Registra backends
```

## Fluxo de Autenticacao

```
Request -> Header Authorization: Bearer <token>
                    |
                    v
            TokenAuthBackend
                    |
                    v
            Decodifica JWT
                    |
                    v
            Busca User por ID
                    |
                    v
            request.state.user = user
```

## Configuracao Padrao

```python
# src/main.py
from core.auth import configure_auth
from src.apps.users.models import User

configure_auth(
    secret_key="sua-chave-secreta",
    user_model=User,
    access_token_expire_minutes=30,
    refresh_token_expire_days=7,
)
```

Isso registra automaticamente:
- `ModelBackend` como "model"
- `TokenAuthBackend` como "token"
- `MultiBackend` como "multi"

## Criar Backend Customizado

### Exemplo: API Key Backend

```python
# src/apps/users/backends.py
from core.auth.backends import AuthBackend
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

class APIKeyBackend(AuthBackend):
    """Autentica via header X-API-Key."""
    
    async def authenticate(
        self,
        request: Request | None = None,
        **credentials,
    ):
        """
        Chamado para autenticar o request.
        
        Args:
            request: Request FastAPI
            **credentials: Credenciais extras (db, token, etc)
            
        Returns:
            User se autenticado, None caso contrario
        """
        if request is None:
            return None
        
        # Extrai API key do header
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return None
        
        # Busca no banco
        db = credentials.get("db")
        if db is None:
            from core.models import get_session
            async with get_session() as db:
                return await self._get_user_by_key(api_key, db)
        
        return await self._get_user_by_key(api_key, db)
    
    async def _get_user_by_key(self, api_key: str, db: AsyncSession):
        """Busca usuario pela API key."""
        from src.apps.users.models import APIKey
        
        key = await APIKey.objects.using(db).filter(
            key=api_key,
            is_active=True,
        ).first()
        
        if key is None:
            return None
        
        # Retorna o usuario associado
        from src.apps.users.models import User
        return await User.objects.using(db).get(id=key.user_id)
    
    async def get_user(self, user_id, db: AsyncSession):
        """Busca usuario por ID."""
        from src.apps.users.models import User
        return await User.objects.using(db).filter(id=user_id).first()
```

### Registrar Backend

```python
# src/main.py
from core.auth import configure_auth
from core.auth.backends import register_auth_backend
from src.apps.users.models import User
from src.apps.users.backends import APIKeyBackend

# Configuracao padrao
configure_auth(
    secret_key="sua-chave-secreta",
    user_model=User,
)

# Registra backend customizado
register_auth_backend("api_key", APIKeyBackend())
```

### Usar Backend Especifico

```python
from core.auth.backends import get_auth_backend

# Usar backend especifico
backend = get_auth_backend("api_key")
user = await backend.authenticate(request=request, db=db)

# Usar backend padrao (token)
backend = get_auth_backend("token")
user = await backend.authenticate(request=request, db=db)
```

## Exemplo: OAuth Backend

```python
# src/apps/users/backends.py
from core.auth.backends import AuthBackend
import httpx

class GoogleOAuthBackend(AuthBackend):
    """Autentica via Google OAuth."""
    
    async def authenticate(self, request=None, **credentials):
        google_token = credentials.get("google_token")
        if not google_token:
            return None
        
        # Valida token com Google
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {google_token}"},
            )
            
            if response.status_code != 200:
                return None
            
            google_data = response.json()
        
        # Busca ou cria usuario
        db = credentials.get("db")
        from src.apps.users.models import User
        
        user = await User.objects.using(db).filter(
            email=google_data["email"]
        ).first()
        
        if user is None:
            # Cria novo usuario
            user = User(
                email=google_data["email"],
                name=google_data.get("name", ""),
                google_id=google_data["sub"],
            )
            await user.save(db)
        
        return user
    
    async def get_user(self, user_id, db):
        from src.apps.users.models import User
        return await User.objects.using(db).filter(id=user_id).first()
```

### Endpoint de Login OAuth

```python
# src/apps/users/views.py
from core import ModelViewSet, action
from core.auth import create_access_token, create_refresh_token
from core.auth.backends import get_auth_backend
from core.permissions import AllowAny

class AuthViewSet(ModelViewSet):
    model = User
    permission_classes = [AllowAny]
    
    @action(methods=["POST"], detail=False)
    async def google_login(self, request, db, **kwargs):
        body = await request.json()
        google_token = body.get("google_token")
        
        # Usa backend Google
        backend = get_auth_backend("google")
        user = await backend.authenticate(google_token=google_token, db=db)
        
        if user is None:
            from fastapi import HTTPException
            raise HTTPException(401, "Invalid Google token")
        
        return {
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
        }
```

## MultiBackend

Tenta multiplos backends em sequencia:

```python
from core.auth.backends import MultiBackend, register_auth_backend

# Registra multi backend customizado
multi = MultiBackend(backends=["token", "api_key", "google"])
register_auth_backend("multi", multi)
```

Fluxo:
1. Tenta `token` (JWT)
2. Se falhar, tenta `api_key`
3. Se falhar, tenta `google`
4. Se todos falharem, retorna None

## Metodos do AuthBackend

| Metodo | Descricao |
|--------|-----------|
| `authenticate(request, **credentials)` | Autentica e retorna User ou None |
| `get_user(user_id, db)` | Busca User por ID |
| `login(request, user)` | Acoes pos-login (opcional) |
| `logout(request, user)` | Acoes de logout (opcional) |

## Resumo

1. Backends controlam COMO a autenticacao acontece
2. Crie backends em `src/apps/users/backends.py`
3. Herde de `AuthBackend` e implemente `authenticate()` e `get_user()`
4. Registre com `register_auth_backend("nome", MeuBackend())`
5. Use com `get_auth_backend("nome")`

Next: [Validators](13-validators.md)
