# Core Framework - Guia Completo

Framework Python inspirado no Django, construido sobre FastAPI. Alta performance, baixo acoplamento, produtividade extrema.

## Indice

1. [Instalacao](#instalacao)
2. [Configuracao](#configuracao)
3. [Models e ORM](#models-e-orm)
4. [Serializers](#serializers)
5. [Views e ViewSets](#views-e-viewsets)
6. [Roteamento](#roteamento)
7. [Autenticacao](#autenticacao)
8. [Usuario Customizado](#usuario-customizado)
9. [Permissoes](#permissoes)
10. [Banco de Dados](#banco-de-dados)
11. [Migracoes](#migracoes)

---

## Instalacao

```bash
# Instalacao global do CLI
pipx install "core-framework @ git+https://TOKEN@github.com/usuario/core-framework.git"

# Criar novo projeto
core init meu-projeto --python 3.13

# Entrar no projeto
cd meu-projeto
source .venv/bin/activate
```

---

## Configuracao

### Arquivo .env

```env
# Application
APP_NAME=Minha API
ENVIRONMENT=development
DEBUG=true
SECRET_KEY=sua-chave-secreta-aqui

# Database
DATABASE_URL=sqlite+aiosqlite:///./app.db
DATABASE_ECHO=false

# API
API_PREFIX=/api/v1

# Auth
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=30
AUTH_REFRESH_TOKEN_EXPIRE_DAYS=7
AUTH_PASSWORD_HASHER=pbkdf2_sha256
```

### Settings Customizado

O arquivo `src/api/config.py` ja vem com todas as configuracoes disponiveis documentadas.
Para adicionar configuracoes customizadas, basta definir novos campos:

```python
# src/api/config.py
from core import Settings

class AppSettings(Settings):
    # Configuracoes customizadas (alem das padrao)
    stripe_api_key: str = ""
    sendgrid_api_key: str = ""
    max_upload_size: int = 10 * 1024 * 1024  # 10MB
    redis_url: str = "redis://localhost:6379"

settings = AppSettings()
```

### Usando Settings

```python
from src.api.config import settings

# Acessar configuracoes
print(settings.database_url)
print(settings.is_production)
print(settings.stripe_api_key)
print(settings.secret_key)
```

### Configuracoes Disponiveis

| Variavel | Tipo | Padrao | Descricao |
|----------|------|--------|-----------|
| APP_NAME | str | "My App" | Nome da aplicacao |
| APP_VERSION | str | "0.1.0" | Versao da aplicacao |
| ENVIRONMENT | str | "development" | development, staging, production, testing |
| DEBUG | bool | false | Modo debug (nunca use em producao) |
| SECRET_KEY | str | - | Chave secreta para tokens JWT |
| DATABASE_URL | str | sqlite+aiosqlite:///./app.db | URL de conexao async |
| DATABASE_ECHO | bool | false | Log de SQL |
| API_PREFIX | str | "/api/v1" | Prefixo das rotas |
| CORS_ORIGINS | list | ["*"] | Origens permitidas |
| AUTH_ACCESS_TOKEN_EXPIRE_MINUTES | int | 30 | Expiracao do access token |
| AUTH_REFRESH_TOKEN_EXPIRE_DAYS | int | 7 | Expiracao do refresh token |
| AUTH_PASSWORD_HASHER | str | "pbkdf2_sha256" | Algoritmo de hash |
| TIMEZONE | str | "UTC" | Timezone padrao |
| USE_TZ | bool | true | Usar datetimes aware |
| HOST | str | "0.0.0.0" | Host do servidor |
| PORT | int | 8000 | Porta do servidor |
| LOG_LEVEL | str | "INFO" | Nivel de log |

---

## Models e ORM

### Definindo Models

```python
# src/apps/posts/models.py
from sqlalchemy.orm import Mapped
from core import Model, Field
from core.datetime import DateTime

class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = Field.pk()
    title: Mapped[str] = Field.string(max_length=200)
    slug: Mapped[str] = Field.string(max_length=200, unique=True, index=True)
    content: Mapped[str] = Field.text()
    is_published: Mapped[bool] = Field.boolean(default=False)
    views_count: Mapped[int] = Field.integer(default=0)
    created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)
    updated_at: Mapped[DateTime] = Field.datetime(auto_now=True)
    
    # Chave estrangeira
    author_id: Mapped[int] = Field.foreign_key("users.id")
```

### Tipos de Campos

```python
Field.pk()                                    # Chave primaria autoincrement
Field.integer(default=0, nullable=False)      # Inteiro
Field.string(max_length=255, unique=True)     # String com tamanho maximo
Field.text(nullable=True)                     # Texto sem limite
Field.boolean(default=True)                   # Booleano
Field.float(default=0.0)                      # Float
Field.datetime(auto_now_add=True)             # DateTime (sempre UTC)
Field.foreign_key("tabela.coluna")            # Chave estrangeira
```

### Queries com Manager

```python
from src.apps.posts.models import Post

# Todas as queries sao async
async def exemplos(db):
    # Listar todos
    posts = await Post.objects.using(db).all()
    
    # Filtrar
    published = await Post.objects.using(db).filter(is_published=True).all()
    
    # Excluir da query
    drafts = await Post.objects.using(db).exclude(is_published=True).all()
    
    # Ordenar
    recent = await Post.objects.using(db).order_by("-created_at").all()
    
    # Paginacao
    page = await Post.objects.using(db).offset(0).limit(10).all()
    
    # Obter um registro
    post = await Post.objects.using(db).get(id=1)
    
    # Obter ou None
    post = await Post.objects.using(db).get_or_none(slug="meu-post")
    
    # Primeiro registro
    first = await Post.objects.using(db).filter(is_published=True).first()
    
    # Contar
    total = await Post.objects.using(db).count()
    
    # Verificar existencia
    exists = await Post.objects.using(db).exists(slug="meu-post")
    
    # Criar
    post = await Post.objects.using(db).create(
        title="Novo Post",
        slug="novo-post",
        content="Conteudo...",
        author_id=1,
    )
    
    # Criar em massa
    posts = await Post.objects.using(db).bulk_create([
        {"title": "Post 1", "slug": "post-1", "content": "..."},
        {"title": "Post 2", "slug": "post-2", "content": "..."},
    ])
    
    # Atualizar em massa
    count = await Post.objects.using(db).update(
        {"is_published": False},
        is_published=True,
    )
    
    # Deletar em massa
    count = await Post.objects.using(db).delete(is_published=False)
```

### Operacoes em Instancia

```python
# Salvar
post = Post(title="Titulo", slug="titulo", content="...")
await post.save(db)

# Atualizar
post.title = "Novo Titulo"
await post.save(db)

# Deletar
await post.delete(db)

# Recarregar do banco
await post.refresh(db)

# Converter para dict
data = post.to_dict()
```

### Hooks de Ciclo de Vida

```python
class Post(Model):
    __tablename__ = "posts"
    
    # ... campos ...
    
    async def before_save(self) -> None:
        """Executado antes de salvar."""
        if not self.slug:
            self.slug = self.title.lower().replace(" ", "-")
    
    async def after_save(self) -> None:
        """Executado apos salvar."""
        # Invalidar cache, enviar notificacao, etc.
        pass
    
    async def before_delete(self) -> None:
        """Executado antes de deletar."""
        # Limpar arquivos relacionados, etc.
        pass
    
    async def after_delete(self) -> None:
        """Executado apos deletar."""
        pass
```

---

## Serializers

### Input e Output Schemas

```python
# src/apps/posts/schemas.py
from pydantic import field_validator, EmailStr
from core import InputSchema, OutputSchema
from core.datetime import DateTime

class PostInput(InputSchema):
    """Schema para criacao/atualizacao de posts."""
    title: str
    slug: str
    content: str
    is_published: bool = False
    
    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if " " in v:
            raise ValueError("Slug nao pode conter espacos")
        return v.lower()

class PostOutput(OutputSchema):
    """Schema para retorno de posts."""
    id: int
    title: str
    slug: str
    content: str
    is_published: bool
    views_count: int
    created_at: DateTime
    updated_at: DateTime | None
```

### Serializer Completo

```python
from core import Serializer, ModelSerializer

class PostSerializer(Serializer[Post, PostInput, PostOutput]):
    input_schema = PostInput
    output_schema = PostOutput

# Uso
serializer = PostSerializer()

# Validar entrada
validated = serializer.validate_input({"title": "...", "slug": "..."})

# Serializar saida
output = serializer.serialize(post)

# Serializar lista
outputs = serializer.serialize_many(posts)

# Para dicionario
data = serializer.to_dict(post)
```

### ModelSerializer com CRUD

```python
class PostSerializer(ModelSerializer[Post, PostInput, PostOutput]):
    model = Post
    input_schema = PostInput
    output_schema = PostOutput
    
    # Campos a excluir na criacao
    exclude_on_create = ["id", "created_at", "updated_at"]
    
    # Campos a excluir na atualizacao
    exclude_on_update = ["id", "slug"]
    
    # Campos somente leitura
    read_only_fields = ["views_count"]

# Uso
serializer = PostSerializer()
post = await serializer.create(validated_data, db)
post = await serializer.update(post, validated_data, db)
```

### Validacao Customizada

```python
from pydantic import field_validator, model_validator

class UserInput(InputSchema):
    email: EmailStr
    password: str
    password_confirm: str
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Senha deve ter pelo menos 8 caracteres")
        return v
    
    @model_validator(mode="after")
    def passwords_match(self) -> "UserInput":
        if self.password != self.password_confirm:
            raise ValueError("Senhas nao conferem")
        return self
```

---

## Views e ViewSets

### APIView Basica

```python
# src/apps/posts/views.py
from fastapi import Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core import APIView
from core.permissions import IsAuthenticated

class PostDetailView(APIView):
    permission_classes = [IsAuthenticated]
    tags = ["posts"]
    
    async def get(self, request: Request, post_id: int, db: AsyncSession) -> dict:
        post = await Post.objects.using(db).get_or_none(id=post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post nao encontrado")
        return PostOutput.model_validate(post).model_dump()
    
    async def delete(self, request: Request, post_id: int, db: AsyncSession) -> dict:
        post = await Post.objects.using(db).get(id=post_id)
        await post.delete(db)
        return {"message": "Post deletado"}
```

### ModelViewSet Completo

```python
from core import ModelViewSet
from core.permissions import IsAuthenticated, AllowAny

class PostViewSet(ModelViewSet[Post, PostInput, PostOutput]):
    model = Post
    input_schema = PostInput
    output_schema = PostOutput
    
    # Permissoes
    permission_classes = [IsAuthenticated]
    permission_classes_by_action = {
        "list": [AllowAny],
        "retrieve": [AllowAny],
        "create": [IsAuthenticated],
        "update": [IsAuthenticated],
        "destroy": [IsAuthenticated],
    }
    
    # Configuracoes
    lookup_field = "id"
    page_size = 20
    max_page_size = 100
    tags = ["posts"]
    
    # Campos unicos para validacao automatica
    unique_fields = ["slug"]
    
    def get_queryset(self, db):
        """Customizar queryset base."""
        return Post.objects.using(db).filter(is_published=True)
    
    async def validate_title(self, value, db, instance=None):
        """Validacao customizada de campo."""
        if "spam" in value.lower():
            from core.validators import ValidationError
            raise ValidationError("Titulo invalido", field="title")
        return value
    
    async def validate(self, data, db, instance=None):
        """Validacao geral (cross-field)."""
        # Validacoes que envolvem multiplos campos
        return data
    
    async def perform_create_validation(self, data, db):
        """Hook antes de criar."""
        data["slug"] = data["title"].lower().replace(" ", "-")
        return data
    
    async def after_create(self, obj, db):
        """Hook apos criar."""
        # Enviar notificacao, etc.
        pass
```

### Actions Customizadas

```python
from core.views import action

class PostViewSet(ModelViewSet[Post, PostInput, PostOutput]):
    model = Post
    # ...
    
    @action(methods=["POST"], detail=True)
    async def publish(self, request: Request, db: AsyncSession, **kwargs):
        """POST /posts/{id}/publish"""
        post = await self.get_object(db, **kwargs)
        post.is_published = True
        await post.save(db)
        return {"message": "Post publicado"}
    
    @action(methods=["GET"], detail=False)
    async def featured(self, request: Request, db: AsyncSession, **kwargs):
        """GET /posts/featured"""
        posts = await Post.objects.using(db).filter(
            is_published=True,
            views_count__gt=100,
        ).limit(5).all()
        return [PostOutput.model_validate(p).model_dump() for p in posts]
```

### ReadOnlyModelViewSet

```python
from core import ReadOnlyModelViewSet

class PublicPostViewSet(ReadOnlyModelViewSet[Post, PostInput, PostOutput]):
    """ViewSet apenas para leitura (list e retrieve)."""
    model = Post
    output_schema = PostOutput
    permission_classes = [AllowAny]
```

---

## Roteamento

### Router Basico

```python
# src/apps/posts/routes.py
from core import Router
from src.apps.posts.views import PostViewSet

router = Router(prefix="/posts", tags=["posts"])
router.register_viewset("", PostViewSet)
```

### AutoRouter

```python
# src/main.py
from core import AutoRouter
from src.apps.posts.views import PostViewSet
from src.apps.users.views import UserViewSet

api_router = AutoRouter(prefix="/api/v1")
api_router.register("/posts", PostViewSet)
api_router.register("/users", UserViewSet)

# Incluir sub-routers
from src.apps.comments.routes import router as comments_router
api_router.include_router(comments_router, prefix="/comments")
```

### Registrar na Aplicacao

```python
# src/main.py
from core import CoreApp

app = CoreApp(
    title="Minha API",
    version="1.0.0",
)

# Incluir router
app.include_router(api_router.router)
```

### Rotas Geradas Automaticamente

Para um ViewSet registrado em `/posts`:

| Metodo | Rota | Action | Nome |
|--------|------|--------|------|
| GET | /posts/ | list | posts-list |
| POST | /posts/ | create | posts-create |
| GET | /posts/{id} | retrieve | posts-detail |
| PUT | /posts/{id} | update | posts-update |
| PATCH | /posts/{id} | partial_update | posts-partial-update |
| DELETE | /posts/{id} | destroy | posts-delete |

---

## Autenticacao

### Configuracao Basica

```python
from core.auth import configure_auth, AuthConfig

configure_auth(
    secret_key="sua-chave-secreta",
    access_token_expire_minutes=30,
    refresh_token_expire_days=7,
    password_hasher="pbkdf2_sha256",  # ou argon2, bcrypt, scrypt
)
```

### Criar e Verificar Tokens

```python
from core.auth import create_access_token, create_refresh_token, verify_token

# Criar tokens
access_token = create_access_token({"sub": str(user.id), "email": user.email})
refresh_token = create_refresh_token({"sub": str(user.id)})

# Verificar token
payload = verify_token(access_token, token_type="access")
if payload:
    user_id = payload["sub"]
```

### Endpoint de Login

```python
from fastapi import HTTPException
from core.auth import create_access_token, create_refresh_token

class AuthViewSet:
    @staticmethod
    async def login(request: Request, db: AsyncSession, data: dict):
        user = await User.authenticate(
            email=data["email"],
            password=data["password"],
            db=db,
        )
        
        if not user:
            raise HTTPException(status_code=401, detail="Credenciais invalidas")
        
        return {
            "access_token": create_access_token({"sub": str(user.id)}),
            "refresh_token": create_refresh_token({"sub": str(user.id)}),
            "token_type": "bearer",
        }
```

### Proteger Rotas

```python
from core.auth import login_required, require_permission, require_group

class ProtectedViewSet(ModelViewSet):
    # Via permission_classes
    permission_classes = [IsAuthenticated]

# Ou via decorators
@router.get("/admin/dashboard")
@login_required
async def admin_dashboard(request: Request, db: AsyncSession):
    return {"message": "Area administrativa"}

@router.delete("/posts/{id}")
@require_permission("posts.delete")
async def delete_post(request: Request, post_id: int, db: AsyncSession):
    # ...
    pass

@router.get("/moderator/queue")
@require_group("moderators")
async def moderator_queue(request: Request, db: AsyncSession):
    # ...
    pass
```

---

## Usuario Customizado

### Extendendo AbstractUser

```python
# src/apps/users/models.py
from sqlalchemy.orm import Mapped, relationship
from core import Model, Field
from core.auth import AbstractUser, PermissionsMixin
from core.datetime import DateTime

class User(AbstractUser, PermissionsMixin):
    """Usuario customizado com campos adicionais."""
    
    __tablename__ = "users"
    
    # Campos adicionais
    username: Mapped[str] = Field.string(max_length=50, unique=True)
    phone: Mapped[str | None] = Field.string(max_length=20, nullable=True)
    avatar_url: Mapped[str | None] = Field.string(max_length=500, nullable=True)
    bio: Mapped[str | None] = Field.text(nullable=True)
    birth_date: Mapped[DateTime | None] = Field.datetime(nullable=True)
    
    # Relacionamentos
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="author")
    
    # Configuracao
    USERNAME_FIELD = "email"  # Campo usado para login
    REQUIRED_FIELDS = ["username"]  # Campos obrigatorios alem do email
```

### Campos Herdados do AbstractUser

O `AbstractUser` ja inclui:

- `id`: Chave primaria
- `email`: Email unico (usado para login)
- `password_hash`: Hash da senha
- `is_active`: Se o usuario esta ativo
- `is_staff`: Se pode acessar area administrativa
- `is_superuser`: Se tem todas as permissoes
- `date_joined`: Data de criacao
- `last_login`: Ultimo login

### Campos do PermissionsMixin

O `PermissionsMixin` adiciona:

- `groups`: Relacionamento com grupos
- `user_permissions`: Permissoes diretas

### Metodos Disponiveis

```python
# Criar usuario
user = await User.create_user(
    email="user@example.com",
    password="senha123",
    db=db,
    username="usuario",
    phone="+5511999999999",
)

# Criar superusuario
admin = await User.create_superuser(
    email="admin@example.com",
    password="senha123",
    db=db,
    username="admin",
)

# Autenticar
user = await User.authenticate("user@example.com", "senha123", db)

# Buscar por email
user = await User.get_by_email("user@example.com", db)

# Verificar/definir senha
user.set_password("nova_senha")
is_valid = user.check_password("senha_teste")

# Verificar permissoes
if user.has_perm("posts.delete"):
    # ...

if user.has_perms(["posts.create", "posts.edit"]):
    # ...

if user.has_any_perm(["posts.delete", "admin.access"]):
    # ...

# Obter todas as permissoes
perms = user.get_all_permissions()  # {"posts.create", "posts.edit", ...}

# Grupos
if user.is_in_group("editors"):
    # ...

groups = user.get_group_names()  # ["editors", "moderators"]

# Gerenciar grupos
await user.add_to_group("editors", db)
await user.remove_from_group("editors", db)
await user.set_groups(["editors", "moderators"], db)

# Gerenciar permissoes diretas
await user.add_permission("posts.delete", db)
await user.remove_permission("posts.delete", db)
await user.set_permissions(["posts.create", "posts.edit"], db)
```

### Schemas para Usuario

```python
# src/apps/users/schemas.py
from pydantic import EmailStr, field_validator
from core import InputSchema, OutputSchema
from core.datetime import DateTime

class UserCreateInput(InputSchema):
    email: EmailStr
    username: str
    password: str
    phone: str | None = None
    
    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError("Username deve ter pelo menos 3 caracteres")
        return v.lower()
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Senha deve ter pelo menos 8 caracteres")
        return v

class UserOutput(OutputSchema):
    id: int
    email: str
    username: str
    phone: str | None
    avatar_url: str | None
    is_active: bool
    date_joined: DateTime
```

### ViewSet para Usuario

```python
# src/apps/users/views.py
from core import ModelViewSet
from core.permissions import IsAuthenticated, AllowAny
from src.apps.users.models import User
from src.apps.users.schemas import UserCreateInput, UserOutput

class UserViewSet(ModelViewSet[User, UserCreateInput, UserOutput]):
    model = User
    input_schema = UserCreateInput
    output_schema = UserOutput
    
    permission_classes = [IsAuthenticated]
    permission_classes_by_action = {
        "create": [AllowAny],  # Registro publico
    }
    
    unique_fields = ["email", "username"]
    
    async def perform_create_validation(self, data, db):
        """Hash da senha antes de criar."""
        password = data.pop("password")
        data["password_hash"] = User.make_password(password)
        return data
```

---

## Permissoes

### Classes de Permissao Disponiveis

```python
from core.permissions import (
    AllowAny,           # Permite qualquer acesso
    IsAuthenticated,    # Requer autenticacao
    IsAdmin,            # Requer is_superuser=True
    IsOwner,            # Verifica se usuario e dono do objeto
    HasPermission,      # Verifica permissao especifica
    IsInGroup,          # Verifica se esta em grupo
    IsSuperUser,        # Alias para IsAdmin
    IsStaff,            # Requer is_staff=True
)
```

### Usando em ViewSets

```python
class PostViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    
    permission_classes_by_action = {
        "list": [AllowAny],
        "retrieve": [AllowAny],
        "create": [IsAuthenticated],
        "update": [IsAuthenticated, IsOwner],
        "destroy": [IsAuthenticated, HasPermission("posts.delete")],
    }
```

### Permissao Customizada

```python
from core.permissions import Permission

class IsVerifiedUser(Permission):
    """Permite apenas usuarios verificados."""
    
    async def has_permission(self, request, view) -> bool:
        user = getattr(request.state, "user", None)
        if not user:
            return False
        return getattr(user, "is_verified", False)
    
    async def has_object_permission(self, request, view, obj) -> bool:
        return await self.has_permission(request, view)

# Uso
class VerifiedOnlyViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, IsVerifiedUser]
```

### Grupos e Permissoes no Banco

```python
from core.auth import Group, Permission

# Criar grupo
editors = await Group.get_or_create("editors", db=db)

# Adicionar permissoes ao grupo
await editors.add_permission("posts.create", db)
await editors.add_permission("posts.edit", db)
await editors.add_permission("posts.delete", db)

# Ou definir todas de uma vez
await editors.set_permissions([
    "posts.create",
    "posts.edit",
    "posts.delete",
    "comments.moderate",
], db)

# Verificar permissao do grupo
if editors.has_permission("posts.delete"):
    # ...

# Criar permissao
perm = await Permission.get_or_create(
    codename="posts.feature",
    name="Can feature posts",
    description="Permite destacar posts na home",
    db=db,
)

# Criar multiplas permissoes
perms = await Permission.bulk_create([
    "posts.create",
    "posts.edit",
    "posts.delete",
    "posts.publish",
], db=db)
```

---

## Banco de Dados

### Configuracao

```python
# Via .env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname

# SQLite (desenvolvimento)
DATABASE_URL=sqlite+aiosqlite:///./app.db

# PostgreSQL (producao)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/dbname

# MySQL
DATABASE_URL=mysql+aiomysql://user:pass@localhost:3306/dbname
```

### Inicializacao Manual

```python
from core.models import init_database, create_tables, close_database

async def startup():
    await init_database(
        database_url="sqlite+aiosqlite:///./app.db",
        echo=True,  # Log SQL
        pool_size=5,
        max_overflow=10,
    )
    await create_tables()

async def shutdown():
    await close_database()
```

### Usando CoreApp (Recomendado)

```python
from core import CoreApp

app = CoreApp(
    title="Minha API",
    database_url="sqlite+aiosqlite:///./app.db",
)

# O CoreApp gerencia automaticamente:
# - Inicializacao do banco no startup
# - Fechamento no shutdown
# - Dependency injection de sessoes
```

### Dependency Injection

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from core.dependencies import get_db

@router.get("/posts")
async def list_posts(db: AsyncSession = Depends(get_db)):
    posts = await Post.objects.using(db).all()
    return posts
```

---

## Migracoes

### Comandos CLI

```bash
# Criar migracao
core makemigrations --name add_phone_to_users

# Aplicar migracoes
core migrate

# Verificar migracoes pendentes
core check

# Reverter ultima migracao
core migrate --rollback

# Listar migracoes
core showmigrations
```

### Estrutura de Migracao

```python
# migrations/0002_add_phone_to_users.py
from core.migrations import Migration, AddColumn

class Migration0002(Migration):
    dependencies = ["0001_initial"]
    
    operations = [
        AddColumn(
            table_name="users",
            column_name="phone",
            column_type="VARCHAR(20)",
            nullable=True,
        ),
    ]
```

### Operacoes Disponiveis

```python
from core.migrations import (
    CreateTable,
    DropTable,
    AddColumn,
    DropColumn,
    AlterColumn,
    CreateIndex,
    DropIndex,
    AddForeignKey,
    DropForeignKey,
    RunSQL,
    RunPython,
)

# Exemplo: Migracao de dados
class Migration0003(Migration):
    operations = [
        RunPython(
            forward=migrate_data,
            reverse=reverse_migrate_data,
        ),
        RunSQL(
            forward="UPDATE users SET is_verified = true WHERE email_confirmed = true",
            reverse="UPDATE users SET is_verified = false",
        ),
    ]
```

### Analise Pre-Migracao

O sistema analisa migracoes antes de aplicar e alerta sobre:

- Adicao de colunas NOT NULL sem default
- Operacoes destrutivas (DROP TABLE, DROP COLUMN)
- Violacoes de constraints UNIQUE
- Problemas de compatibilidade com SQLite

```bash
# Verificar sem aplicar
core check --verbose

# Aplicar ignorando avisos
core migrate --yes
```

---

## Estrutura de Projeto Recomendada

```
meu-projeto/
  src/
    __init__.py
    main.py                 # Aplicacao principal
    apps/
      __init__.py
      users/
        __init__.py
        models.py           # Models do app
        schemas.py          # Input/Output schemas
        views.py            # ViewSets e APIViews
        services.py         # Logica de negocio
        routes.py           # Rotas do app
        tests/
          __init__.py
          test_users.py
      posts/
        __init__.py
        models.py
        schemas.py
        views.py
        services.py
        routes.py
        tests/
    api/
      __init__.py
      config.py             # Settings da aplicacao
  migrations/
    __init__.py
    0001_initial.py
  tests/
    __init__.py
    conftest.py
  .env
  .env.example
  pyproject.toml
  README.md
```

---

## Exemplo Completo

### src/main.py

```python
from core import CoreApp, AutoRouter
from src.apps.users.views import UserViewSet
from src.apps.posts.views import PostViewSet
from src.core.config import settings

# Criar aplicacao
app = CoreApp(
    title=settings.app_name,
    version=settings.app_version,
    database_url=settings.database_url,
)

# Configurar rotas
api_router = AutoRouter(prefix=settings.api_prefix)
api_router.register("/users", UserViewSet)
api_router.register("/posts", PostViewSet)

# Incluir rotas
app.include_router(api_router.router)
```

### Executar

```bash
# Desenvolvimento
core run

# Producao
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Acessar

- API: http://localhost:8000
- Documentacao: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
