# Quickstart

## Install

```bash
pipx install "core-framework @ git+https://TOKEN@github.com/user/core-framework.git"
```

## Create Project

```bash
core init my-api --python 3.13
cd my-api
```

## First Model

```python
# src/apps/posts/models.py
from core import Model
from sqlalchemy.orm import Mapped, mapped_column

class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(index=True)
    content: Mapped[str]
    published: Mapped[bool] = mapped_column(default=False)
```

## First ViewSet

```python
# src/apps/posts/views.py
from core import ModelViewSet, action
from core.permissions import AllowAny, IsAuthenticated
from .models import Post
from .schemas import PostInput, PostOutput

class PostViewSet(ModelViewSet):
    model = Post
    input_schema = PostInput
    output_schema = PostOutput
    tags = ["Posts"]
    
    permission_classes = [AllowAny]
    permission_classes_by_action = {
        "create": [IsAuthenticated],
        "update": [IsAuthenticated],
        "destroy": [IsAuthenticated],
    }
```

## Schemas

```python
# src/apps/posts/schemas.py
from core import InputSchema, OutputSchema

class PostInput(InputSchema):
    title: str
    content: str
    published: bool = False

class PostOutput(OutputSchema):
    id: int
    title: str
    content: str
    published: bool
```

## Routes

```python
# src/apps/posts/routes.py
from core import AutoRouter
from .views import PostViewSet

router = AutoRouter(prefix="/posts", tags=["Posts"])
router.register("", PostViewSet)
```

## Register in Main

```python
# src/main.py
from src.apps.posts.routes import router as posts_router

api_router = AutoRouter(prefix="/api/v1")
api_router.include_router(posts_router)
```

## Run

```bash
core makemigrations --name add_posts
core migrate
core run
```

## Generated Endpoints

| Method | Path | Action |
|--------|------|--------|
| GET | /api/v1/posts/ | List |
| POST | /api/v1/posts/ | Create |
| GET | /api/v1/posts/{id} | Retrieve |
| PUT | /api/v1/posts/{id} | Update |
| PATCH | /api/v1/posts/{id} | Partial Update |
| DELETE | /api/v1/posts/{id} | Delete |

Next: [ViewSets](02-viewsets.md)
