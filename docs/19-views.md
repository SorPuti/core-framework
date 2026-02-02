# Views

Classes base para construcao de endpoints. O framework oferece tres niveis de abstracao, do mais flexivel ao mais automatizado.

## Hierarquia de Views

```
APIView          -> Mais flexivel, menos automatico
    |
ViewSet          -> CRUD manual, com helpers
    |
ModelViewSet     -> CRUD automatico completo
    |
ReadOnlyModelViewSet -> Apenas list e retrieve
```

## APIView

View baseada em classe para endpoints que nao seguem padrao CRUD. Cada metodo HTTP e um metodo da classe.

```python
from core.views import APIView
from core.permissions import AllowAny, IsAuthenticated
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

class HealthView(APIView):
    """
    Endpoint de health check.
    
    Nao opera sobre model, apenas retorna status.
    """
    
    # Permissoes aplicadas a todos os metodos
    permission_classes = [AllowAny]
    
    # Tags para documentacao OpenAPI
    tags = ["System"]
    
    async def get(self, request: Request, db: AsyncSession, **kwargs) -> dict:
        """
        GET /health
        
        Metodos HTTP sao mapeados para metodos da classe.
        Defina apenas os metodos que deseja expor.
        """
        return {"status": "healthy", "database": "connected"}

class WebhookView(APIView):
    """
    Endpoint para receber webhooks externos.
    """
    
    permission_classes = [AllowAny]
    tags = ["Webhooks"]
    
    async def post(self, request: Request, db: AsyncSession, **kwargs) -> dict:
        """
        POST /webhooks/stripe
        
        Processa webhook do Stripe.
        """
        body = await request.json()
        # Processar evento...
        return {"received": True}
```

### Permissoes por Metodo HTTP

```python
class UserDetailView(APIView):
    # Padrao para todos os metodos
    permission_classes = [IsAuthenticated]
    
    # Override por metodo HTTP
    permission_classes_by_method = {
        "GET": [AllowAny],           # Qualquer um pode ver
        "PUT": [IsAuthenticated],    # Precisa estar logado
        "DELETE": [IsAdmin],         # Apenas admin
    }
    
    async def get(self, request: Request, db: AsyncSession, user_id: int, **kwargs):
        user = await User.objects.using(db).get(id=user_id)
        return UserOutput.model_validate(user).model_dump()
    
    async def put(self, request: Request, db: AsyncSession, user_id: int, **kwargs):
        # Atualizar usuario...
        pass
    
    async def delete(self, request: Request, db: AsyncSession, user_id: int, **kwargs):
        # Deletar usuario...
        pass
```

### Registrar APIView

```python
from core import AutoRouter
from .views import HealthView, WebhookView

router = AutoRouter(prefix="/system", tags=["System"])

# as_route() converte a view em endpoint FastAPI
path, endpoint, kwargs = HealthView.as_route("/health")
router.add_api_route(path, endpoint, **kwargs)

# Ou diretamente
router.add_api_route(
    "/webhooks/stripe",
    WebhookView.as_route("/webhooks/stripe")[1],
    methods=["POST"],
    tags=["Webhooks"],
)
```

## ViewSet

Classe base para operacoes CRUD. Fornece estrutura e helpers, mas nao implementa as acoes automaticamente.

```python
from core.views import ViewSet
from core.permissions import IsAuthenticated

class UserViewSet(ViewSet):
    """
    ViewSet com CRUD manual.
    
    Voce implementa cada acao, mas tem acesso a:
    - get_queryset(): QuerySet base
    - get_object(): Busca objeto por lookup_field
    - get_permissions(): Permissoes da acao
    - validate_data(): Validacao completa
    """
    
    model = User
    input_schema = UserInput
    output_schema = UserOutput
    permission_classes = [IsAuthenticated]
    
    # Campo usado para lookup em retrieve/update/destroy
    lookup_field = "id"
    
    # Paginacao
    page_size = 20
    max_page_size = 100
    
    # Campos com validacao de unicidade automatica
    unique_fields = ["email", "username"]
    
    async def list(self, request, db, **kwargs):
        """Implementacao customizada de list."""
        queryset = self.get_queryset(db)
        users = await queryset.all()
        return [self.get_output_schema().model_validate(u).model_dump() for u in users]
    
    async def retrieve(self, request, db, **kwargs):
        """Implementacao customizada de retrieve."""
        user = await self.get_object(db, **kwargs)
        return self.get_output_schema().model_validate(user).model_dump()
    
    async def create(self, request, db, data, **kwargs):
        """Implementacao customizada de create."""
        # validate_data() executa:
        # 1. Validacao de unicidade
        # 2. Validadores de campo
        # 3. Metodo validate()
        validated = await self.validate_data(data, db)
        user = User(**validated)
        await user.save(db)
        return self.get_output_schema().model_validate(user).model_dump()
```

### Metodos Disponiveis no ViewSet

| Metodo | Descricao |
|--------|-----------|
| `get_queryset(db)` | Retorna QuerySet base (sobrescreva para filtros) |
| `get_object(db, **kwargs)` | Busca objeto por lookup_field, 404 se nao encontrar |
| `get_permissions(action)` | Retorna lista de permissoes para a acao |
| `get_input_schema()` | Retorna schema de entrada |
| `get_output_schema()` | Retorna schema de saida |
| `validate_data(data, db, instance)` | Executa todas as validacoes |
| `validate_unique_fields(data, db, instance)` | Valida campos unicos |
| `validate_field(field, value, db, instance)` | Valida campo individual |
| `validate(data, db, instance)` | Hook para validacao customizada |

## ModelViewSet

ViewSet com CRUD completo implementado automaticamente. A classe mais usada para APIs REST.

```python
from core.views import ModelViewSet
from core.permissions import AllowAny, IsAuthenticated, IsOwner

class PostViewSet(ModelViewSet):
    """
    CRUD completo gerado automaticamente.
    
    Endpoints criados:
    - GET /posts/ -> list()
    - POST /posts/ -> create()
    - GET /posts/{id} -> retrieve()
    - PUT /posts/{id} -> update()
    - PATCH /posts/{id} -> partial_update()
    - DELETE /posts/{id} -> destroy()
    """
    
    model = Post
    input_schema = PostInput
    output_schema = PostOutput
    tags = ["Posts"]
    
    # Permissao padrao
    permission_classes = [IsAuthenticated]
    
    # Override por acao
    permission_classes_by_action = {
        "list": [AllowAny],
        "retrieve": [AllowAny],
        "update": [IsOwner],
        "partial_update": [IsOwner],
        "destroy": [IsOwner],
    }
    
    # Paginacao
    page_size = 20
    max_page_size = 100
    
    # Validacao de unicidade
    unique_fields = ["slug"]
```

### Hooks de Ciclo de Vida

```python
class PostViewSet(ModelViewSet):
    model = Post
    
    async def perform_create_validation(self, data: dict, db) -> dict:
        """
        Hook antes de criar.
        
        Chamado apos validacao, antes de instanciar o model.
        Use para adicionar campos automaticos.
        """
        data["author_id"] = self.request.state.user.id
        data["slug"] = slugify(data["title"])
        return data
    
    async def after_create(self, obj, db) -> None:
        """
        Hook apos criar.
        
        Chamado apos salvar no banco.
        Use para side effects (emails, logs, cache).
        """
        await send_notification(f"New post: {obj.title}")
    
    async def perform_update_validation(self, data: dict, instance, db) -> dict:
        """
        Hook antes de atualizar.
        
        instance e o objeto existente.
        """
        if "title" in data:
            data["slug"] = slugify(data["title"])
        return data
    
    async def after_update(self, obj, db) -> None:
        """Hook apos atualizar."""
        await invalidate_cache(f"post:{obj.id}")
```

### Customizar QuerySet

```python
class PostViewSet(ModelViewSet):
    model = Post
    
    def get_queryset(self, db):
        """
        Filtra queryset base.
        
        Afeta list(), retrieve(), update(), destroy().
        """
        qs = super().get_queryset(db)
        user = self.request.state.user
        
        # Usuarios comuns veem apenas posts publicados
        # Autores veem seus proprios posts (publicados ou nao)
        if user:
            return qs.filter(
                or_(
                    Post.is_published == True,
                    Post.author_id == user.id,
                )
            )
        return qs.filter(is_published=True)
```

### Validacao Customizada

```python
class PostViewSet(ModelViewSet):
    model = Post
    unique_fields = ["slug"]
    
    async def validate_title(self, value, db, instance=None):
        """
        Validador de campo especifico.
        
        Metodo validate_{field_name} e chamado automaticamente.
        """
        if len(value) < 5:
            from core.validators import ValidationError
            raise ValidationError("Title must be at least 5 characters", field="title")
        return value
    
    async def validate(self, data: dict, db, instance=None) -> dict:
        """
        Validacao cross-field.
        
        Chamado apos validadores de campo.
        """
        if data.get("published_at") and not data.get("content"):
            from core.validators import ValidationError
            raise ValidationError("Cannot publish without content", field="content")
        return data
```

## ReadOnlyModelViewSet

ViewSet apenas para leitura. Util para recursos que nao devem ser modificados via API.

```python
from core.views import ReadOnlyModelViewSet

class PublicPostViewSet(ReadOnlyModelViewSet):
    """
    Apenas list() e retrieve().
    
    create(), update(), partial_update(), destroy() retornam 405.
    """
    
    model = Post
    output_schema = PostOutput
    permission_classes = [AllowAny]
    tags = ["Public Posts"]
    
    def get_queryset(self, db):
        # Apenas posts publicados
        return super().get_queryset(db).filter(is_published=True)
```

**Endpoints gerados**:
- GET /posts/ -> list()
- GET /posts/{id} -> retrieve()

**Metodos bloqueados** (retornam 405 Method Not Allowed):
- POST, PUT, PATCH, DELETE

## Custom Actions

Adicione endpoints alem do CRUD com o decorator `@action`.

```python
from core.views import ModelViewSet, action

class PostViewSet(ModelViewSet):
    model = Post
    
    @action(methods=["POST"], detail=True)
    async def publish(self, request, db, **kwargs):
        """
        POST /posts/{id}/publish
        
        detail=True: Opera sobre objeto especifico (tem {id} na URL)
        """
        post = await self.get_object(db, **kwargs)
        post.is_published = True
        post.published_at = datetime.utcnow()
        await post.save(db)
        return {"status": "published"}
    
    @action(methods=["GET"], detail=False)
    async def featured(self, request, db, **kwargs):
        """
        GET /posts/featured
        
        detail=False: Opera sobre colecao (sem {id} na URL)
        """
        posts = await self.get_queryset(db).filter(is_featured=True).all()
        schema = self.get_output_schema()
        return [schema.model_validate(p).model_dump() for p in posts]
    
    @action(
        methods=["POST"],
        detail=True,
        url_path="add-comment",
        permission_classes=[IsAuthenticated],
    )
    async def add_comment(self, request, db, **kwargs):
        """
        POST /posts/{id}/add-comment
        
        url_path: Customiza o path (padrao seria /add_comment)
        permission_classes: Override de permissoes para esta acao
        """
        post = await self.get_object(db, **kwargs)
        body = await request.json()
        comment = Comment(
            post_id=post.id,
            author_id=request.state.user.id,
            content=body["content"],
        )
        await comment.save(db)
        return {"id": comment.id}
```

## Comparacao de Views

| Classe | Quando Usar |
|--------|-------------|
| `APIView` | Endpoints nao-CRUD (health, webhooks, integracao) |
| `ViewSet` | CRUD customizado, controle total sobre implementacao |
| `ModelViewSet` | CRUD padrao com customizacoes via hooks |
| `ReadOnlyModelViewSet` | Recursos somente leitura (catalogo publico, historico) |

## Resumo de Atributos

| Atributo | Tipo | Descricao |
|----------|------|-----------|
| `model` | type | Model SQLAlchemy |
| `input_schema` | type[InputSchema] | Schema de entrada |
| `output_schema` | type[OutputSchema] | Schema de saida |
| `serializer_class` | type[Serializer] | Alternativa a input/output_schema |
| `permission_classes` | list[type[Permission]] | Permissoes padrao |
| `permission_classes_by_action` | dict | Permissoes por acao |
| `lookup_field` | str | Campo para lookup (default: "id") |
| `page_size` | int | Itens por pagina (default: 20) |
| `max_page_size` | int | Maximo de itens (default: 100) |
| `unique_fields` | list[str] | Campos com validacao de unicidade |
| `tags` | list[str] | Tags OpenAPI |
