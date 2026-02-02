# Quickstart

Este guia cobre a criacao de uma API funcional do zero. O objetivo e demonstrar o fluxo minimo necessario para ter endpoints CRUD operacionais.

## Instalacao

O framework e distribuido via Git. A instalacao via `pipx` disponibiliza o CLI globalmente, permitindo criar projetos em qualquer diretorio.

```bash
# pipx instala em ambiente isolado, evitando conflitos de dependencias
# Substitua TOKEN pelo seu token de acesso ao repositorio
pipx install "core-framework @ git+https://TOKEN@github.com/user/core-framework.git"
```

**Requisito**: Python 3.12 ou superior. O framework utiliza features de tipagem modernas que nao existem em versoes anteriores.

## Criacao do Projeto

```bash
# --python especifica a versao do interpretador para o virtualenv
# O comando cria estrutura de diretorios, .env, pyproject.toml e dependencias
core init my-api --python 3.13
cd my-api
```

O comando `core init` gera:
- Estrutura de pastas padrao (`src/apps/`, `src/api/`)
- Arquivo `.env` com configuracoes de desenvolvimento
- `pyproject.toml` configurado com dependencias do framework
- Virtualenv ativado automaticamente

## Primeiro Model

Models herdam de `core.Model`, que e um wrapper sobre SQLAlchemy ORM com funcionalidades adicionais como QuerySet e metodos de conveniencia.

```python
# src/apps/posts/models.py
from core import Model
from sqlalchemy.orm import Mapped, mapped_column

class Post(Model):
    # __tablename__ e obrigatorio - define o nome da tabela no banco
    __tablename__ = "posts"
    
    # Mapped[tipo] define o tipo Python e SQLAlchemy infere o tipo SQL
    # primary_key=True gera autoincrement por padrao em PostgreSQL/SQLite
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # index=True cria indice B-tree - use para campos frequentemente filtrados
    title: Mapped[str] = mapped_column(index=True)
    
    # Campos sem mapped_column() usam configuracao padrao do tipo
    content: Mapped[str]
    
    # default= define valor padrao no Python, nao no banco
    # Para default no banco, use server_default=
    published: Mapped[bool] = mapped_column(default=False)
```

**Importante**: O tipo `Mapped[str]` gera `VARCHAR(255)` por padrao. Para textos longos, use `mapped_column(Text)`.

## Primeiro ViewSet

ViewSet encapsula toda logica CRUD em uma classe. O framework gera automaticamente os endpoints baseado nos atributos definidos.

```python
# src/apps/posts/views.py
from core import ModelViewSet, action
from core.permissions import AllowAny, IsAuthenticated
from .models import Post
from .schemas import PostInput, PostOutput

class PostViewSet(ModelViewSet):
    # model: obrigatorio - define qual tabela o ViewSet manipula
    model = Post
    
    # input_schema: valida dados de entrada (POST, PUT, PATCH)
    input_schema = PostInput
    
    # output_schema: formata dados de saida (GET, respostas)
    output_schema = PostOutput
    
    # tags: agrupa endpoints na documentacao OpenAPI
    tags = ["Posts"]
    
    # permission_classes: permissao padrao para todas as acoes
    # AllowAny permite acesso sem autenticacao
    permission_classes = [AllowAny]
    
    # permission_classes_by_action: override por acao especifica
    # Acoes disponiveis: list, create, retrieve, update, partial_update, destroy
    permission_classes_by_action = {
        "create": [IsAuthenticated],      # POST /posts/
        "update": [IsAuthenticated],      # PUT /posts/{id}
        "destroy": [IsAuthenticated],     # DELETE /posts/{id}
    }
```

**Comportamento**: Se uma acao nao estiver em `permission_classes_by_action`, usa `permission_classes`. Se `permission_classes` nao estiver definido, o padrao e `IsAuthenticated`.

## Schemas

Schemas sao classes Pydantic que definem a estrutura de dados. O framework usa schemas separados para entrada e saida, permitindo controle granular sobre quais campos sao aceitos e retornados.

```python
# src/apps/posts/schemas.py
from core import InputSchema, OutputSchema

class PostInput(InputSchema):
    # Campos obrigatorios - requisicao falha se ausentes
    title: str
    content: str
    
    # Campo opcional com valor padrao
    published: bool = False

class PostOutput(OutputSchema):
    # Todos os campos que serao retornados na resposta
    # Campos do model nao listados aqui NAO aparecem na resposta
    id: int
    title: str
    content: str
    published: bool
```

**Trade-off**: `InputSchema` e `OutputSchema` herdam de `pydantic.BaseModel` com configuracoes especificas. Usar `BaseModel` diretamente funciona, mas perde integracao automatica com o ViewSet.

## Rotas

O `AutoRouter` gera rotas automaticamente a partir do ViewSet registrado.

```python
# src/apps/posts/routes.py
from core import AutoRouter
from .views import PostViewSet

# prefix: prefixo de URL para todos os endpoints deste router
# tags: tags OpenAPI (pode ser sobrescrito pelo ViewSet)
router = AutoRouter(prefix="/posts", tags=["Posts"])

# register("", ViewSet) - string vazia significa que usa apenas o prefix
# register("/sub", ViewSet) geraria /posts/sub/
router.register("", PostViewSet)
```

## Registro no Main

Routers precisam ser incluidos no router principal para serem reconhecidos pela aplicacao.

```python
# src/main.py
from core import AutoRouter
from src.apps.posts.routes import router as posts_router

# Router principal com prefixo da API
# Todos os sub-routers herdam este prefixo
api_router = AutoRouter(prefix="/api/v1")

# include_router adiciona todas as rotas do posts_router
# Resultado: /api/v1/posts/...
api_router.include_router(posts_router)
```

**Nota**: O arquivo `main.py` gerado pelo `core init` ja contem a estrutura basica. Adicione apenas o `include_router`.

## Execucao

```bash
# Gera arquivo de migracao baseado nas diferencas entre models e banco
# --name e obrigatorio e deve ser descritivo
core makemigrations --name add_posts

# Aplica migracoes pendentes ao banco de dados
# Em desenvolvimento, usa SQLite por padrao (.env DATABASE_URL)
core migrate

# Inicia servidor de desenvolvimento com hot-reload
# Padrao: http://localhost:8000
core run
```

**Producao**: `core run` usa Uvicorn com reload habilitado. Para producao, use `core run --no-reload --workers 4` ou configure via Docker.

## Endpoints Gerados

O `ModelViewSet` gera automaticamente os seguintes endpoints:

| Metodo | Path | Acao | Descricao |
|--------|------|------|-----------|
| GET | /api/v1/posts/ | list | Lista paginada de posts |
| POST | /api/v1/posts/ | create | Cria novo post |
| GET | /api/v1/posts/{id} | retrieve | Retorna post especifico |
| PUT | /api/v1/posts/{id} | update | Atualiza todos os campos |
| PATCH | /api/v1/posts/{id} | partial_update | Atualiza campos parciais |
| DELETE | /api/v1/posts/{id} | destroy | Remove post |

**Documentacao**: Acesse `/docs` para Swagger UI ou `/redoc` para ReDoc. Ambos sao gerados automaticamente.

---

Proximo: [ViewSets](02-viewsets.md) - Customizacao de CRUD, actions personalizadas e hooks de ciclo de vida.
