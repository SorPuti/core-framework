# Auth Backends

Backends definem COMO a autenticacao acontece. O framework vem com backends para JWT e email/senha, mas permite criar backends customizados para API keys, OAuth, LDAP, etc.

## Backends Disponiveis

| Backend | Uso | Quando Usar |
|---------|-----|-------------|
| `ModelBackend` | Email/senha via banco | Login tradicional |
| `TokenAuthBackend` | JWT no header Authorization | APIs stateless |
| `MultiBackend` | Tenta multiplos backends | Suporte a multiplos metodos |

## Estrutura de Arquivos

```
/my-project
  /src
    /apps
      /users
        backends.py        # Backends customizados
        models.py          # User e models relacionados (APIKey, etc)
    main.py                # Registro de backends
```

## Fluxo de Autenticacao

```
Request com Header: Authorization: Bearer <token>
                           |
                           v
                   TokenAuthBackend.authenticate()
                           |
                           v
                   Decodifica JWT, extrai user_id
                           |
                           v
                   TokenAuthBackend.get_user(user_id)
                           |
                           v
                   request.state.user = User
```

O middleware de autenticacao executa este fluxo automaticamente para cada request.

## Configuracao Padrao

```python
# src/main.py
from core.auth import configure_auth
from src.apps.users.models import User

configure_auth(
    secret_key="sua-chave-secreta",  # Usada para assinar JWTs
    user_model=User,                  # Model que representa usuarios
    access_token_expire_minutes=30,
    refresh_token_expire_days=7,
)
```

**Efeito de configure_auth()**: Registra automaticamente tres backends:
- `"model"`: `ModelBackend` - autenticacao por email/senha
- `"token"`: `TokenAuthBackend` - autenticacao por JWT
- `"multi"`: `MultiBackend` - tenta token primeiro, depois model

## Criar Backend Customizado

### Exemplo: API Key Backend

Para autenticacao via header `X-API-Key` ao inves de JWT.

```python
# src/apps/users/backends.py
from core.auth.backends import AuthBackend
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

class APIKeyBackend(AuthBackend):
    """
    Autentica requests via header X-API-Key.
    
    Util para:
    - Integracao com servicos externos
    - Automacao e scripts
    - Clientes que nao suportam OAuth/JWT
    """
    
    async def authenticate(
        self,
        request: Request | None = None,
        **credentials,
    ):
        """
        Metodo principal de autenticacao.
        
        Chamado pelo middleware para cada request.
        Deve retornar User se autenticado, None caso contrario.
        
        IMPORTANTE: Retornar None NAO e erro - significa que este
        backend nao consegue autenticar o request. O proximo backend
        sera tentado (se usando MultiBackend).
        """
        if request is None:
            return None
        
        # Extrai API key do header customizado
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            # Sem header = este backend nao se aplica
            return None
        
        # Obtem sessao de banco
        # credentials pode conter "db" se passado explicitamente
        db = credentials.get("db")
        if db is None:
            # Cria sessao se nao fornecida
            from core.models import get_session
            async with get_session() as db:
                return await self._get_user_by_key(api_key, db)
        
        return await self._get_user_by_key(api_key, db)
    
    async def _get_user_by_key(self, api_key: str, db: AsyncSession):
        """
        Busca usuario associado a API key.
        
        Metodo auxiliar separado para reutilizacao.
        """
        from src.apps.users.models import APIKey, User
        
        # Busca API key ativa
        key = await APIKey.objects.using(db).filter(
            key=api_key,
            is_active=True,
        ).first()
        
        if key is None:
            return None
        
        # Retorna usuario associado
        return await User.objects.using(db).get(id=key.user_id)
    
    async def get_user(self, user_id, db: AsyncSession):
        """
        Busca usuario por ID.
        
        Usado internamente pelo framework para recarregar usuario.
        """
        from src.apps.users.models import User
        return await User.objects.using(db).filter(id=user_id).first()
```

**Model APIKey necessario**:

```python
# src/apps/users/models.py
class APIKey(Model):
    __tablename__ = "api_keys"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[DateTime] = mapped_column(default=DateTime.now)
```

### Registrar Backend

```python
# src/main.py
from core.auth import configure_auth
from core.auth.backends import register_auth_backend
from src.apps.users.models import User
from src.apps.users.backends import APIKeyBackend

# Configuracao padrao primeiro
configure_auth(
    secret_key="sua-chave-secreta",
    user_model=User,
)

# Registra backend customizado
# O nome "api_key" pode ser usado para obter o backend depois
register_auth_backend("api_key", APIKeyBackend())
```

### Usar Backend Especifico

Em casos onde voce precisa autenticar explicitamente (ex: endpoint de login):

```python
from core.auth.backends import get_auth_backend

# Obter backend por nome
backend = get_auth_backend("api_key")
user = await backend.authenticate(request=request, db=db)

# Backend padrao (token)
backend = get_auth_backend("token")
user = await backend.authenticate(request=request, db=db)
```

## Exemplo: OAuth Backend

Para login via Google, Facebook, etc.

```python
# src/apps/users/backends.py
from core.auth.backends import AuthBackend
import httpx

class GoogleOAuthBackend(AuthBackend):
    """
    Autentica via token OAuth do Google.
    
    Fluxo:
    1. Frontend obtem token do Google (via Google Sign-In)
    2. Frontend envia token para backend
    3. Backend valida token com Google
    4. Backend cria/busca usuario e retorna JWT proprio
    """
    
    async def authenticate(self, request=None, **credentials):
        """
        Recebe google_token via credentials, NAO via request.
        Este backend e chamado explicitamente, nao pelo middleware.
        """
        google_token = credentials.get("google_token")
        if not google_token:
            return None
        
        # Valida token com API do Google
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {google_token}"},
            )
            
            if response.status_code != 200:
                # Token invalido ou expirado
                return None
            
            google_data = response.json()
        
        # Busca ou cria usuario no banco local
        db = credentials.get("db")
        from src.apps.users.models import User
        
        user = await User.objects.using(db).filter(
            email=google_data["email"]
        ).first()
        
        if user is None:
            # Primeiro login - cria usuario
            user = User(
                email=google_data["email"],
                name=google_data.get("name", ""),
                google_id=google_data["sub"],  # ID unico do Google
                # Senha nao necessaria para OAuth
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
from fastapi import HTTPException

class AuthViewSet(ModelViewSet):
    model = User
    permission_classes = [AllowAny]
    
    @action(methods=["POST"], detail=False)
    async def google_login(self, request, db, **kwargs):
        """
        POST /auth/google_login
        Body: {"google_token": "token-do-google"}
        
        Recebe token OAuth do Google e retorna tokens JWT proprios.
        """
        body = await request.json()
        google_token = body.get("google_token")
        
        # Usa backend Google para autenticar
        backend = get_auth_backend("google")
        user = await backend.authenticate(google_token=google_token, db=db)
        
        if user is None:
            raise HTTPException(401, "Invalid Google token")
        
        # Retorna tokens JWT do nosso sistema
        return {
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
        }
```

## MultiBackend

Tenta multiplos backends em sequencia ate um autenticar com sucesso.

```python
from core.auth.backends import MultiBackend, register_auth_backend

# Cria MultiBackend com ordem especifica
multi = MultiBackend(backends=["token", "api_key", "google"])
register_auth_backend("multi", multi)
```

**Fluxo de execucao**:
1. Tenta `token` (JWT no header Authorization)
2. Se retornar None, tenta `api_key` (header X-API-Key)
3. Se retornar None, tenta `google` (se aplicavel)
4. Se todos retornarem None, `request.state.user` permanece None

**Uso comum**: Suportar JWT para frontend web e API key para integracao com sistemas externos.

## Metodos do AuthBackend

| Metodo | Obrigatorio | Descricao |
|--------|-------------|-----------|
| `authenticate(request, **credentials)` | Sim | Autentica e retorna User ou None |
| `get_user(user_id, db)` | Sim | Busca User por ID |
| `login(request, user)` | Nao | Acoes pos-login (ex: atualizar last_login) |
| `logout(request, user)` | Nao | Acoes de logout (ex: invalidar sessao) |

---

Proximo: [Validators](13-validators.md) - Sistema de validacao de dados.
