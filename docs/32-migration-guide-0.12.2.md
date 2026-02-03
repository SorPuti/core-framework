# Guia de Migração para v0.12.2

Este guia ajuda a migrar de versões anteriores (especialmente v0.12.1) para v0.12.2, removendo workarounds que não são mais necessários.

---

## Resumo das Mudanças

| Problema | Antes (Workaround) | Depois (Nativo) |
|----------|-------------------|-----------------|
| DATETIME no PostgreSQL | `sed` manual | Automático |
| Boolean defaults | `sed` manual | Automático |
| UUID em User | Override manual | `AbstractUUIDUser` |
| PermissionsMixin + UUID | Remover mixin | Funciona direto |
| extra_register_fields | Override completo | Atributo funciona |
| _create_tokens | Override método | Funciona direto |
| refresh com UUID | Override método | Funciona direto |
| AuthMiddleware | Criar manual | Built-in |

---

## Passo 1: Remover Workaround de Migrations

### Antes (v0.12.1)

Você provavelmente tinha um script ou comandos manuais:

```bash
# Script que você usava
core makemigrations -n "initial"
sed -i "s/type='DATETIME'/type='TIMESTAMP'/g" migrations/*.py
sed -i "s/DEFAULT 1/DEFAULT TRUE/g" migrations/*.py
sed -i "s/DEFAULT 0/DEFAULT FALSE/g" migrations/*.py
core migrate
```

### Depois (v0.12.2)

Simplesmente:

```bash
core makemigrations -n "initial"
core migrate
# Tipos corretos automaticamente!
```

**Ação:** Delete seus scripts de correção de migrations.

---

## Passo 2: Simplificar User Model

### Antes (v0.12.1) - Com Workarounds

```python
# models.py
from uuid import UUID
from core.auth import AbstractUser, SoftDeleteMixin
from core.fields import AdvancedField

class User(AbstractUser, SoftDeleteMixin):  # SEM PermissionsMixin (bug)
    __tablename__ = "users"
    
    # Override forçado do id
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    
    # Campos extras
    name: Mapped[str] = Field.string(max_length=100)
```

### Depois (v0.12.2) - Limpo

```python
# models.py
from core.auth import AbstractUUIDUser, PermissionsMixin, SoftDeleteMixin
from core.models import Field
from sqlalchemy.orm import Mapped

class User(AbstractUUIDUser, PermissionsMixin, SoftDeleteMixin):
    __tablename__ = "users"
    
    # Não precisa override de id - já é UUID!
    name: Mapped[str] = Field.string(max_length=100)
```

**Ação:** 
1. Mude `AbstractUser` para `AbstractUUIDUser`
2. Adicione `PermissionsMixin` de volta
3. Remova override do campo `id`

---

## Passo 3: Simplificar AuthViewSet

### Antes (v0.12.1) - Com Workarounds

```python
# views.py
from datetime import timedelta
from uuid import UUID
from core.auth.views import AuthViewSet
from core.auth import create_access_token, create_refresh_token, verify_token
from core.auth.schemas import BaseRegisterInput
from pydantic import create_model

class UserRegisterInput(BaseRegisterInput):
    """Schema customizado porque extra_register_fields não funciona."""
    name: str
    model_config = {"extra": "allow"}

class MyAuthViewSet(AuthViewSet):
    user_model = User
    register_schema = UserRegisterInput  # Workaround
    
    def _create_tokens(self, user):
        """Override porque API mudou."""
        access_token = create_access_token(
            user_id=str(user.id),
            extra_claims={"email": user.email},
            expires_delta=timedelta(minutes=self.access_token_expire_minutes),
        )
        refresh_token = create_refresh_token(
            user_id=str(user.id),
            expires_delta=timedelta(days=self.refresh_token_expire_days),
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.access_token_expire_minutes * 60,
        }
    
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    async def register(self, request, db, data=None, **kwargs):
        """Override porque extra_register_fields não funciona."""
        User = self._get_user_model()
        validated = self.register_schema.model_validate(data)
        
        existing = await User.get_by_email(validated.email, db)
        if existing:
            raise HTTPException(400, "User exists")
        
        user = await User.create_user(
            email=validated.email,
            password=validated.password,
            name=validated.name,  # Campo extra manual
            db=db,
        )
        await db.commit()
        return self._create_tokens(user)
    
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    async def refresh(self, request, db, data=None, **kwargs):
        """Override porque assume int para user_id."""
        User = self._get_user_model()
        validated = RefreshTokenInput.model_validate(data)
        
        payload = verify_token(validated.refresh_token, token_type="refresh")
        if payload is None:
            raise HTTPException(401, "Invalid token")
        
        # Workaround: converte para UUID
        user_id = UUID(payload.get("sub"))
        user = await User.objects.using(db).filter(id=user_id).first()
        
        if user is None or not user.is_active:
            raise HTTPException(401, "User not found")
        
        return self._create_tokens(user)
```

### Depois (v0.12.2) - Limpo

```python
# views.py
from core.auth.views import AuthViewSet

class MyAuthViewSet(AuthViewSet):
    user_model = User
    extra_register_fields = ["name"]  # Agora funciona!
    
    # Nenhum override necessário!
```

**Ação:**
1. Remova schema customizado
2. Remova override de `_create_tokens`
3. Remova override de `register`
4. Remova override de `refresh`
5. Use `extra_register_fields` nativo

---

## Passo 4: Adicionar AuthenticationMiddleware

### Antes (v0.12.1) - Middleware Manual

```python
# main.py
from starlette.middleware.base import BaseHTTPMiddleware
from core.auth import TokenAuthBackend
from core.database import get_read_session

class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware manual porque framework não fornece."""
    
    async def dispatch(self, request, call_next):
        request.state.user = None
        
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                async for db in get_read_session():
                    backend = TokenAuthBackend(user_model=User)
                    user = await backend.authenticate(request=request, db=db)
                    if user:
                        request.state.user = user
                    break
            except Exception:
                pass
        
        return await call_next(request)

app = CoreApp(
    middlewares=[(AuthenticationMiddleware, {})],
)
```

### Depois (v0.12.2) - Built-in

```python
# main.py
from core import CoreApp

app = CoreApp(
    middleware=["auth"],  # Só isso!
)

# Ou com configuração
app = CoreApp(
    middleware=[
        ("auth", {"skip_paths": ["/health", "/docs"]}),
    ],
)
```

**Ação:**
1. Delete sua classe `AuthenticationMiddleware` manual
2. Use o middleware built-in via string

---

## Passo 5: Atualizar Configuração

### Antes (v0.12.1)

```python
# config.py ou main.py
from core.auth import configure_auth

configure_auth(
    user_model=User,
    secret_key=settings.secret_key,
)

# Middleware manual em CoreApp
app = CoreApp(
    middlewares=[
        (AuthenticationMiddleware, {}),
        (OtherMiddleware, {"option": "value"}),
    ],
)
```

### Depois (v0.12.2)

```python
# config.py
from core.auth import configure_auth

configure_auth(
    user_model=User,
    secret_key=settings.secret_key,
)

# main.py - middleware declarativo
app = CoreApp(
    middleware=[
        "timing",
        "auth",
        ("myapp.middleware.OtherMiddleware", {"option": "value"}),
    ],
)
```

Ou via Settings:

```python
# settings.py
class AppSettings(Settings):
    middleware: list[str] = [
        "timing",
        "auth",
        "logging",
    ]
```

---

## Passo 6: Limpar Código Morto

Após migração, remova:

1. **Scripts de correção de migrations** (`fix_migrations.sh`, etc.)
2. **Schemas customizados** que apenas adicionavam campos extras
3. **Overrides de métodos** do AuthViewSet
4. **Middleware de autenticação manual**
5. **Funções helper** de conversão UUID/int
6. **Comentários** sobre workarounds

---

## Checklist Final

- [ ] Atualizei para v0.12.2+ (`pip install --upgrade core-framework`)
- [ ] Mudei `AbstractUser` para `AbstractUUIDUser` (se uso UUID)
- [ ] Adicionei `PermissionsMixin` de volta ao User
- [ ] Removi override do campo `id`
- [ ] Removi schema customizado de registro
- [ ] Removi overrides de `_create_tokens`, `register`, `refresh`
- [ ] Uso `extra_register_fields` nativo
- [ ] Uso middleware `"auth"` built-in
- [ ] Deletei scripts de correção de migrations
- [ ] Deletei middleware de autenticação manual
- [ ] Testei todas as rotas de auth:
  - [ ] POST /auth/register
  - [ ] POST /auth/login
  - [ ] POST /auth/refresh
  - [ ] GET /auth/me
  - [ ] POST /auth/change-password

---

## Comparação de Linhas de Código

### Antes (com workarounds)

```
models.py:      25 linhas (override de id, sem PermissionsMixin)
views.py:       85 linhas (overrides de register, refresh, _create_tokens)
schemas.py:     15 linhas (schema customizado)
middleware.py:  40 linhas (middleware manual)
main.py:        20 linhas (configuração de middleware)
─────────────────────────────
Total:         ~185 linhas de workarounds
```

### Depois (v0.12.2)

```
models.py:      10 linhas (User limpo)
views.py:        5 linhas (AuthViewSet limpo)
schemas.py:      0 linhas (usa built-in)
middleware.py:   0 linhas (usa built-in)
main.py:        10 linhas (configuração limpa)
─────────────────────────────
Total:          ~25 linhas
```

**Redução:** ~160 linhas de código de contorno eliminadas!

---

## Troubleshooting da Migração

### Erro: `Table already exists`

Se você já tem tabelas criadas:

```bash
# Não precisa recriar - migrações futuras já serão corretas
core migrate  # Aplica apenas mudanças pendentes
```

### Erro: `Column type mismatch`

Se há conflito de tipos em migrations antigas:

```python
# Crie migration de correção manual
# migrations/0002_fix_types.py

from core.migrations import Migration
from core.migrations.operations import RunSQL

class FixTypesMigration(Migration):
    dependencies = ["0001_initial"]
    
    operations = [
        RunSQL(
            forward_sql="ALTER TABLE users ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE",
            backward_sql="ALTER TABLE users ALTER COLUMN created_at TYPE TIMESTAMP",
        ),
    ]
```

### Erro: Testes falhando

Limpe cache e reinstale:

```bash
# Limpa cache Python
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete

# Reinstala dependências
pip install --upgrade --force-reinstall core-framework

# Roda testes
pytest -v
```
