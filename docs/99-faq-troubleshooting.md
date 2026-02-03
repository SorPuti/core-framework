# FAQ & Troubleshooting

Guia completo de resolução de problemas do Core Framework.

---

## Índice

1. [Erros de Migrations](#1-erros-de-migrations)
2. [Erros de Autenticação](#2-erros-de-autenticação)
3. [Erros de Banco de Dados](#3-erros-de-banco-de-dados)
4. [Erros de Configuração](#4-erros-de-configuração)
5. [Erros de Middleware](#5-erros-de-middleware)
6. [Erros de Serialização](#6-erros-de-serialização)
7. [Erros de Permissões](#7-erros-de-permissões)
8. [Erros de Multi-Tenancy](#8-erros-de-multi-tenancy)
9. [Erros de Performance](#9-erros-de-performance)
10. [Erros Comuns de Desenvolvimento](#10-erros-comuns-de-desenvolvimento)

---

## 1. Erros de Migrations

### ❌ `type "datetime" does not exist`

**Erro completo:**
```
asyncpg.exceptions.UndefinedObjectError: type "datetime" does not exist
[SQL: CREATE TABLE IF NOT EXISTS "users" (..., "created_at" DATETIME NOT NULL, ...)]
```

**Causa:** Versão antiga do framework gerando tipo incompatível com PostgreSQL.

**Solução:**
1. Atualize para v0.12.2+
2. Para migrations existentes, edite manualmente:
   ```python
   # Substitua
   type='DATETIME'
   # Por
   type='TIMESTAMP WITH TIME ZONE'
   ```

---

### ❌ `column is of type boolean but default expression is of type integer`

**Erro completo:**
```
asyncpg.exceptions.DatatypeMismatchError: column "is_active" is of type boolean but default expression is of type integer
HINT: You will need to rewrite or cast the expression.
```

**Causa:** PostgreSQL exige `TRUE`/`FALSE` para boolean defaults, não `1`/`0`.

**Solução:**
1. Atualize para v0.12.2+
2. Para migrations existentes:
   ```python
   # Substitua
   default=1  # ou default=0
   # Por
   default=True  # ou default=False
   ```
   
   Ou no SQL gerado:
   ```sql
   -- De
   DEFAULT 1
   -- Para
   DEFAULT TRUE
   ```

---

### ❌ `relation "table_name" does not exist`

**Causa:** Tentando migrar sem ter criado as tabelas dependentes.

**Solução:**
```bash
# Verifique migrations pendentes
core showmigrations

# Aplique todas
core migrate

# Ou crie tabelas via SQLAlchemy
python -c "
import asyncio
from core.models import Model, init_database, create_tables

async def setup():
    await init_database('postgresql+asyncpg://...')
    await create_tables()

asyncio.run(setup())
"
```

---

### ❌ `duplicate key value violates unique constraint`

**Causa:** Tentando criar registro com valor único já existente.

**Solução:**
```python
# Verifique antes de criar
existing = await User.objects.filter(email=email).first()
if existing:
    raise HTTPException(400, "Email já cadastrado")

# Ou use get_or_create
user, created = await User.objects.get_or_create(
    email=email,
    defaults={"name": "New User"}
)
```

---

### ❌ `cannot drop column because other objects depend on it`

**Causa:** Coluna tem foreign keys ou constraints.

**Solução:**
```python
# No arquivo de migration, remova FK primeiro
from core.migrations.operations import DropForeignKey, DropColumn

operations = [
    DropForeignKey(
        table_name="orders",
        constraint_name="fk_orders_user_id",
    ),
    DropColumn(
        table_name="users",
        column_name="old_column",
    ),
]
```

---

## 2. Erros de Autenticação

### ❌ `Not authenticated` em `/auth/me`

**Causa:** `request.state.user` está None porque middleware não está configurado.

**Solução:**
```python
from core import CoreApp

app = CoreApp(
    middleware=["auth"],  # Adicione isto!
)
```

Ou formato antigo:
```python
from core.auth import AuthenticationMiddleware

app = CoreApp(
    middlewares=[(AuthenticationMiddleware, {})],
)
```

---

### ❌ `create_access_token() got an unexpected keyword argument 'data'`

**Causa:** Usando API obsoleta do token.

**Solução:**
```python
# ❌ API antiga (não funciona)
token = create_access_token(
    data={"sub": str(user.id)},
    expires_minutes=30,
)

# ✅ API atual
from datetime import timedelta

token = create_access_token(
    user_id=str(user.id),
    extra_claims={"email": user.email},
    expires_delta=timedelta(minutes=30),
)
```

---

### ❌ `invalid literal for int() with base 10: 'uuid-string'`

**Causa:** Framework tentando converter UUID para int.

**Solução:** Atualize para v0.12.2+ ou use workaround:

```python
class MyAuthViewSet(AuthViewSet):
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    async def refresh(self, request, db, data=None, **kwargs):
        # ... validação ...
        
        from uuid import UUID
        user_id = UUID(payload.get("sub"))  # Converte para UUID
        user = await User.objects.using(db).filter(id=user_id).first()
```

---

### ❌ `Invalid or expired refresh token`

**Causas possíveis:**
1. Token expirou
2. Secret key mudou
3. Token malformado

**Diagnóstico:**
```python
from core.auth import decode_token, verify_token

try:
    # Tenta decodificar (ignora expiração)
    payload = decode_token(token)
    print("Payload:", payload)
    print("Expiração:", payload.get("exp"))
except Exception as e:
    print("Token inválido:", e)

# Verifica com tipo
result = verify_token(token, token_type="refresh")
print("Válido:", result is not None)
```

**Solução:**
1. Solicite novo refresh token via login
2. Verifique se `SECRET_KEY` não mudou
3. Aumente `refresh_token_expire_days` se necessário

---

### ❌ `User with this email already exists`

**Causa:** Tentando registrar email duplicado.

**Solução no cliente:**
```javascript
// Trate o erro 400
if (error.response?.status === 400) {
    if (error.response.data.detail.includes("already exists")) {
        showError("Este email já está cadastrado. Tente fazer login.");
    }
}
```

---

### ❌ `Password must be at least 8 characters`

**Causa:** Senha não atende requisitos mínimos.

**Personalização:**
```python
from core.auth.schemas import BaseRegisterInput
from pydantic import field_validator

class CustomRegisterInput(BaseRegisterInput):
    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 12:
            raise ValueError("Senha deve ter pelo menos 12 caracteres")
        if not any(c.isupper() for c in v):
            raise ValueError("Senha deve ter letra maiúscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("Senha deve ter número")
        return v

class MyAuthViewSet(AuthViewSet):
    register_schema = CustomRegisterInput
```

---

### ❌ `No user_model configured`

**Causa:** `configure_auth()` não foi chamado.

**Solução:**
```python
from core.auth import configure_auth
from myapp.models import User

# No início da aplicação
configure_auth(
    user_model=User,
    secret_key="your-secure-key",
)
```

---

## 3. Erros de Banco de Dados

### ❌ `Cannot connect to database`

**Causas:**
1. URL incorreta
2. Banco não está rodando
3. Credenciais erradas

**Diagnóstico:**
```python
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def test_connection():
    url = "postgresql+asyncpg://user:pass@localhost:5432/db"
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            print("Conexão OK:", result.scalar())
    except Exception as e:
        print("Erro:", type(e).__name__, e)
    finally:
        await engine.dispose()

asyncio.run(test_connection())
```

**Soluções:**
```python
# SQLite (desenvolvimento)
database_url = "sqlite+aiosqlite:///./app.db"

# PostgreSQL
database_url = "postgresql+asyncpg://user:password@localhost:5432/dbname"

# Verifique se o driver está instalado
# pip install asyncpg  # Para PostgreSQL
# pip install aiosqlite  # Para SQLite
```

---

### ❌ `foreign key constraint cannot be implemented`

**Erro completo:**
```
asyncpg.exceptions.DatatypeMismatchError: foreign key constraint cannot be implemented
DETAIL: Key columns "user_id" and "id" are of incompatible types: uuid and integer.
```

**Causa:** Tipos incompatíveis entre FK e PK.

**Solução v0.12.2+:**
```python
from core.auth import AbstractUUIDUser, PermissionsMixin

class User(AbstractUUIDUser, PermissionsMixin):
    __tablename__ = "users"
    # UUID é detectado automaticamente
```

**Solução manual:**
```python
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID

# Na tabela de associação, use mesmo tipo
Column("user_id", UUID(as_uuid=True), ForeignKey("users.id"))
```

---

### ❌ `QueuePool limit overflow`

**Causa:** Pool de conexões esgotado.

**Solução:**
```python
class AppSettings(Settings):
    database_pool_size: int = 20       # Aumente
    database_max_overflow: int = 30    # Conexões extras
    database_pool_timeout: int = 60    # Timeout maior
    database_pool_recycle: int = 1800  # Recicla a cada 30min
```

**Diagnóstico:**
```python
# Verifique conexões abertas (PostgreSQL)
SELECT count(*) FROM pg_stat_activity WHERE datname = 'your_db';
```

---

### ❌ `Object is not bound to a Session`

**Causa:** Tentando acessar objeto fora da sessão.

**Solução:**
```python
# ❌ Errado
async def get_user(user_id: int):
    async with get_session() as db:
        user = await User.objects.using(db).filter(id=user_id).first()
    # db fechou, user não pode ser usado
    return user.email  # ERRO!

# ✅ Correto
async def get_user(user_id: int):
    async with get_session() as db:
        user = await User.objects.using(db).filter(id=user_id).first()
        return user.email if user else None

# ✅ Ou retorne dicionário
async def get_user(user_id: int):
    async with get_session() as db:
        user = await User.objects.using(db).filter(id=user_id).first()
        if user:
            return {"id": user.id, "email": user.email}
        return None
```

---

### ❌ `greenlet_spawn has not been called`

**Causa:** Usando operação síncrona em contexto async.

**Solução:**
```python
# ❌ Errado - acesso lazy síncrono
user = await User.objects.filter(id=1).first()
groups = user.groups  # ERRO se groups é lazy

# ✅ Correto - use selectin ou joinedload
user = await User.objects.select_related("groups").filter(id=1).first()
groups = user.groups  # OK

# ✅ Ou defina lazy="selectin" no modelo
groups: Mapped[list["Group"]] = relationship(
    "Group",
    secondary=user_groups_table,
    lazy="selectin",  # Carrega automaticamente
)
```

---

## 4. Erros de Configuração

### ❌ `SECRET_KEY not set`

**Solução:**
```bash
# .env
SECRET_KEY=sua-chave-super-secreta-com-pelo-menos-256-bits

# Gerar chave segura
python -c "import secrets; print(secrets.token_hex(32))"
```

---

### ❌ `Settings validation error`

**Causa:** Tipo incorreto em variável de ambiente.

**Exemplo:**
```bash
# ❌ Errado
DEBUG=yes  # Não é bool válido

# ✅ Correto
DEBUG=true
DEBUG=1
DEBUG=false
DEBUG=0
```

**Para listas:**
```bash
# ❌ Errado
CORS_ORIGINS=http://localhost,http://example.com

# ✅ Correto (JSON)
CORS_ORIGINS='["http://localhost", "http://example.com"]'
```

---

### ❌ `Module not found: 'core'`

**Causa:** Core Framework não está instalado ou PYTHONPATH incorreto.

**Solução:**
```bash
# Instale o framework
pip install core-framework

# Ou se é desenvolvimento local
pip install -e .

# Verifique instalação
python -c "import core; print(core.__version__)"
```

---

### ❌ `Password hasher 'argon2' requires the 'argon2-cffi' package`

**Causa:** Dependência opcional não instalada.

**Solução:**
```bash
# Para Argon2
pip install argon2-cffi

# Para BCrypt
pip install bcrypt

# Para Scrypt
pip install scrypt

# Ou use o padrão (sem dependência extra)
configure_auth(password_hasher="pbkdf2_sha256")
```

---

## 5. Erros de Middleware

### ❌ `Could not import middleware 'myapp.middleware.Custom'`

**Causas:**
1. Path incorreto
2. Módulo não existe
3. Erro de sintaxe no módulo

**Diagnóstico:**
```python
# Teste o import manualmente
try:
    from myapp.middleware import Custom
    print("Import OK")
except Exception as e:
    print("Erro:", e)
```

**Solução:**
```python
# Verifique o path completo
middleware=[
    "myapp.middleware.CustomMiddleware",  # myapp/middleware.py, class CustomMiddleware
]

# Ou use classe diretamente
from myapp.middleware import CustomMiddleware

middleware=[CustomMiddleware]
```

---

### ❌ `'NoneType' object has no attribute 'user'`

**Causa:** Acessando `request.state.user` antes do middleware executar.

**Solução:**
```python
# ✅ Sempre verifique None
user = getattr(request.state, "user", None)
if user is None:
    raise HTTPException(401, "Not authenticated")

# ✅ Ou use dependency
from core.dependencies import get_current_user

@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {"email": user.email}
```

---

### ❌ Middleware não está sendo executado

**Diagnóstico:**
```python
from core.middleware import print_middleware_stack

print_middleware_stack(app)
# Verifique se seu middleware aparece
```

**Causas comuns:**
1. Middleware não registrado
2. `exclude_paths` inclui o path
3. Ordem errada (antes de CORS pode bloquear)

**Solução:**
```python
# Verifique registro
from core.middleware import get_registered_middlewares
for mw in get_registered_middlewares():
    print(mw.name, mw.enabled)

# Verifique exclude_paths
class MyMiddleware(BaseMiddleware):
    exclude_paths = ["/api/"]  # Talvez muito amplo?
```

---

## 6. Erros de Serialização

### ❌ `Extra inputs are not permitted`

**Causa:** InputSchema com `extra="forbid"` (padrão) recebendo campos extras.

**Solução:**
```python
from core.serializers import InputSchema

class MyInput(InputSchema):
    name: str
    
    model_config = {"extra": "ignore"}  # Ignora campos extras
```

---

### ❌ `Input should be a valid string`

**Causa:** Tipo incorreto no payload.

**Exemplo:**
```json
// ❌ Errado
{"email": 123}

// ✅ Correto
{"email": "user@example.com"}
```

---

### ❌ `Object of type UUID is not JSON serializable`

**Causa:** Tentando serializar UUID sem converter.

**Solução:**
```python
# No schema de output
class UserOutput(OutputSchema):
    id: str  # UUID serializa como string
    
    @classmethod
    def from_orm(cls, obj):
        data = super().model_validate(obj)
        # UUID já é convertido automaticamente pelo Pydantic
        return data

# Ou use model_config
class UserOutput(OutputSchema):
    id: UUID
    
    model_config = {"json_encoders": {UUID: str}}
```

---

### ❌ `value is not a valid email address`

**Causa:** Email mal formatado.

**Solução no cliente:**
```javascript
// Valide antes de enviar
const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
if (!emailRegex.test(email)) {
    showError("Email inválido");
}
```

---

## 7. Erros de Permissões

### ❌ `Permission denied`

**Causa:** Usuário não tem permissão necessária.

**Diagnóstico:**
```python
# Verifique permissões do usuário
print("Permissões:", user.get_all_permissions())
print("Grupos:", user.get_group_names())
print("É superuser:", user.is_superuser)
```

**Solução:**
```python
# Adicione permissão
await user.add_permission("posts.create", db)

# Ou adicione ao grupo
await user.add_to_group("editors", db)

# Ou faça superuser (tem todas permissões)
user.is_superuser = True
await user.save(db)
```

---

### ❌ `User is not in required group`

**Solução:**
```python
# Verifique grupos
if not user.is_in_group("admin"):
    raise HTTPException(403, "Acesso negado")

# Adicione ao grupo
from core.auth import Group

admin_group = await Group.get_or_create("admin", db=db)
await user.add_to_group(admin_group, db)
```

---

## 8. Erros de Multi-Tenancy

### ❌ `Tenant not set`

**Causa:** Tentando acessar dados sem tenant definido.

**Solução:**
```python
from core.tenancy import set_tenant, tenant_context

# Opção 1: Set manual
set_tenant(workspace_id)
data = await MyModel.objects.all()

# Opção 2: Context manager
async with tenant_context(workspace_id):
    data = await MyModel.objects.all()

# Opção 3: Via middleware (automático)
# Configure TenantMiddleware
```

---

### ❌ `Cross-tenant access detected`

**Causa:** Tentando acessar dados de outro tenant.

**Solução:** Verifique lógica de filtro:
```python
# TenantQuerySet filtra automaticamente
# Mas se acessar diretamente...

# ❌ Bypass perigoso
item = await session.get(Item, item_id)  # Pode ser de outro tenant!

# ✅ Seguro
item = await Item.objects.using(db).filter(id=item_id).first()
# TenantQuerySet adiciona filtro de tenant automaticamente
```

---

## 9. Erros de Performance

### ❌ Queries N+1

**Sintoma:** Muitas queries para listar dados relacionados.

**Diagnóstico:**
```python
# Habilite logging SQL
class AppSettings(Settings):
    database_echo: bool = True
```

**Solução:**
```python
# ❌ N+1 queries
users = await User.objects.all()
for user in users:
    print(user.posts)  # Query para cada user!

# ✅ Eager loading
users = await User.objects.select_related("posts").all()
for user in users:
    print(user.posts)  # Já carregado
```

---

### ❌ Timeout em queries

**Solução:**
```python
# Configure timeout
class AppSettings(Settings):
    database_pool_timeout: int = 60  # Aumente

# Ou use timeout específico
from sqlalchemy import text

async with engine.connect() as conn:
    result = await asyncio.wait_for(
        conn.execute(text("SELECT * FROM big_table")),
        timeout=30.0
    )
```

---

### ❌ Memória alta com grandes datasets

**Solução:**
```python
# ❌ Carrega tudo na memória
users = await User.objects.all()  # 1M users!

# ✅ Paginação
users = await User.objects.offset(0).limit(100).all()

# ✅ Streaming
async for user in User.objects.stream():
    process(user)
```

---

## 10. Erros Comuns de Desenvolvimento

### ❌ `coroutine was never awaited`

**Causa:** Esqueceu `await` em função async.

**Solução:**
```python
# ❌ Errado
user = User.objects.filter(id=1).first()  # Retorna coroutine!

# ✅ Correto
user = await User.objects.filter(id=1).first()
```

---

### ❌ `This event loop is already running`

**Causa:** Usando `asyncio.run()` dentro de contexto async.

**Solução:**
```python
# ❌ Errado (em FastAPI)
@router.get("/test")
def test():  # Sync
    result = asyncio.run(async_function())  # ERRO!

# ✅ Correto
@router.get("/test")
async def test():  # Async
    result = await async_function()
```

---

### ❌ `Cannot use 'await' outside async function`

**Solução:**
```python
# ❌ Errado
def my_function():
    user = await get_user()  # ERRO!

# ✅ Correto
async def my_function():
    user = await get_user()

# ✅ Ou se precisa chamar de sync
import asyncio

def my_sync_function():
    return asyncio.run(my_async_function())
```

---

### ❌ Circular import

**Sintoma:** `ImportError: cannot import name 'X' from partially initialized module`

**Solução:**
```python
# ❌ Errado - import no topo causa circular
from myapp.models import User
from myapp.services import UserService  # UserService importa User

# ✅ Correto - import local
def get_user_service():
    from myapp.services import UserService
    return UserService()

# ✅ Ou use TYPE_CHECKING
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myapp.models import User

def process(user: "User"):  # String annotation
    pass
```

---

### ❌ `Model class not found in registry`

**Causa:** Model não foi importado antes de usar.

**Solução:**
```python
# main.py - importe todos os models
import myapp.models  # Força registro

from core import CoreApp
app = CoreApp(...)
```

---

## Checklist de Debug

Quando encontrar um erro:

1. **Leia a mensagem completa** - geralmente indica a causa
2. **Verifique a versão** - `python -c "import core; print(core.__version__)"`
3. **Habilite debug** - `DEBUG=true` no .env
4. **Verifique logs SQL** - `DATABASE_ECHO=true`
5. **Teste isoladamente** - crie script mínimo que reproduz o erro
6. **Verifique dependências** - `pip list | grep -E "(core|sqlalchemy|fastapi)"`
7. **Limpe cache** - `find . -type d -name __pycache__ -exec rm -rf {} +`

---

## Obtendo Ajuda

Se o erro persistir:

1. **Crie issue** com:
   - Versão do framework
   - Versão do Python
   - Banco de dados usado
   - Código mínimo que reproduz
   - Mensagem de erro completa
   - Stack trace

2. **Informações úteis:**
   ```python
   import sys
   import core
   import sqlalchemy
   import fastapi
   
   print(f"Python: {sys.version}")
   print(f"Core: {core.__version__}")
   print(f"SQLAlchemy: {sqlalchemy.__version__}")
   print(f"FastAPI: {fastapi.__version__}")
   ```
