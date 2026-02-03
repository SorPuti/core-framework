# Changelog v0.12.2

**Data de Release:** 03/02/2026

Esta versão foca em correções críticas de bugs e melhorias na experiência do desenvolvedor.

---

## Bugs Corrigidos

### Bug #1: DATETIME → TIMESTAMP para PostgreSQL
**Arquivo:** `core/migrations/operations.py`

**Problema:** O gerador de migrations usava `DATETIME` que não existe no PostgreSQL.

**Antes:**
```sql
CREATE TABLE users (..., created_at DATETIME NOT NULL, ...)
-- Erro: type "datetime" does not exist
```

**Depois:**
```sql
CREATE TABLE users (..., created_at TIMESTAMP WITH TIME ZONE NOT NULL, ...)
```

**Correção:** Adicionado mapeamento automático de tipos por dialeto:
- PostgreSQL: `DATETIME` → `TIMESTAMP WITH TIME ZONE`
- MySQL: `DATETIME` → `DATETIME`
- SQLite: `DATETIME` → `DATETIME`

---

### Bug #2: Boolean defaults TRUE/FALSE para PostgreSQL
**Arquivo:** `core/migrations/operations.py`

**Problema:** Boolean defaults usavam `1`/`0` que PostgreSQL rejeita.

**Antes:**
```sql
is_active BOOLEAN DEFAULT 1
-- Erro: column "is_active" is of type boolean but default expression is of type integer
```

**Depois:**
```sql
is_active BOOLEAN DEFAULT TRUE
```

---

### Bug #3: PermissionsMixin detecta UUID em Foreign Keys
**Arquivo:** `core/auth/models.py`

**Problema:** Tabelas de associação (user_groups, user_permissions) assumiam INTEGER para user_id.

**Correção:** Detecção robusta do tipo de PK em 3 níveis:
1. Via tabela já mapeada (`__table__.columns`)
2. Via annotations (`__annotations__`)
3. Via atributos da classe

---

### Bug #4: AbstractUser suporta UUID como PK
**Arquivo:** `core/auth/models.py`

**Problema:** `AbstractUser` definia `id` como INTEGER fixo.

**Correção:** 
- `AbstractUser` agora permite sobrescrever o campo `id`
- Nova classe `AbstractUUIDUser` com UUID por padrão

```python
# Antes - não funcionava
class User(AbstractUser):
    id: Mapped[UUID] = AdvancedField.uuid_pk()  # Ignorado

# Depois - funciona!
class User(AbstractUUIDUser, PermissionsMixin):
    __tablename__ = "users"
    # UUID já é o padrão
```

---

### Bug #5: extra_register_fields funciona
**Arquivo:** `core/auth/views.py`

**Problema:** Atributo `extra_register_fields` era ignorado.

**Correção:** Implementação completa com schema dinâmico:

```python
class MyAuthViewSet(AuthViewSet):
    user_model = User
    extra_register_fields = ["name", "phone"]  # Agora funciona!
```

---

### Bug #6: _create_tokens usa API correta
**Arquivo:** `core/auth/views.py`

**Problema:** Método usava assinatura obsoleta (`data={"sub": ...}`).

**Correção:** Atualizado para nova API:
```python
create_access_token(
    user_id=str(user.id),
    extra_claims={"email": user.email},
    expires_delta=timedelta(minutes=30),
)
```

---

### Bug #7: refresh converte tipo de ID inteligentemente
**Arquivo:** `core/auth/views.py`

**Problema:** Método fazia `int(user_id)` assumindo INTEGER.

**Correção:** Conversão automática baseada no tipo do modelo:
- UUID → `UUID(user_id)`
- INTEGER → `int(user_id)`
- STRING → `user_id`

---

### Bug #8: AuthenticationMiddleware built-in
**Novo arquivo:** `core/auth/middleware.py`

**Problema:** Framework não fornecia middleware para popular `request.state.user`.

**Correção:** Novo middleware completo:

```python
from core.auth import AuthenticationMiddleware

app = CoreApp(
    middleware=["auth"],  # Shortcut
)

# Agora request.state.user funciona!
```

---

## Novas Funcionalidades

### Sistema de Middleware Django-style

Novo sistema de configuração de middlewares similar ao Django:

```python
# Via CoreApp
app = CoreApp(
    middleware=[
        "timing",
        "auth",
        "logging",
    ],
)

# Via Settings
class AppSettings(Settings):
    middleware = ["timing", "auth"]

# Via função
from core.middleware import configure_middleware
configure_middleware(["timing", "auth"])
```

### Shortcuts de Middleware

| Shortcut | Classe |
|----------|--------|
| `auth` | `AuthenticationMiddleware` |
| `optional_auth` | `OptionalAuthenticationMiddleware` |
| `timing` | `TimingMiddleware` |
| `request_id` | `RequestIDMiddleware` |
| `logging` | `LoggingMiddleware` |
| `security_headers` | `SecurityHeadersMiddleware` |
| `maintenance` | `MaintenanceModeMiddleware` |

### Classe Base para Middlewares

```python
from core.middleware import BaseMiddleware

class MyMiddleware(BaseMiddleware):
    async def before_request(self, request):
        pass
    
    async def after_request(self, request, response):
        return response
    
    async def on_error(self, request, exc):
        return None
```

### Helpers de Validação

```python
from core.auth import (
    validate_auth_configuration,
    get_auth_setup_checklist,
)

# Verifica problemas de configuração
issues = validate_auth_configuration()

# Imprime checklist
print(get_auth_setup_checklist())
```

---

## Breaking Changes

Nenhum breaking change nesta versão. Todas as correções são retrocompatíveis.

---

## Migração

### De v0.12.1 para v0.12.2

1. **Migrations existentes:** Não precisam ser alteradas. Novas migrations já serão geradas corretamente.

2. **UUID Users:** Se você tinha workarounds, pode removê-los:
   ```python
   # Antes (workaround)
   class User(AbstractUser, SoftDeleteMixin):  # Sem PermissionsMixin
       id: Mapped[UUID] = AdvancedField.uuid_pk()
   
   # Depois (funciona direto)
   class User(AbstractUUIDUser, PermissionsMixin, SoftDeleteMixin):
       __tablename__ = "users"
   ```

3. **AuthViewSet:** Remova overrides desnecessários:
   ```python
   # Antes (workaround)
   class MyAuthViewSet(AuthViewSet):
       def _create_tokens(self, user):  # Override manual
           ...
   
   # Depois (funciona direto)
   class MyAuthViewSet(AuthViewSet):
       user_model = User
       extra_register_fields = ["name"]
   ```

4. **Middleware:** Adicione o middleware de autenticação:
   ```python
   app = CoreApp(
       middleware=["auth"],  # Novo!
   )
   ```

---

## Dependências

Nenhuma nova dependência adicionada.
