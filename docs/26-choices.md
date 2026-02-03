# Choices - Enums com Value e Label

O Core Framework fornece `TextChoices` e `IntegerChoices` no estilo Django, permitindo definir enums com valor e label de forma elegante.

## Visão Geral

Choices são enums que armazenam:
- **value**: O valor armazenado no banco de dados
- **label**: O texto legível para exibição

## Importação

```python
from core import TextChoices, IntegerChoices
# ou
from core.choices import TextChoices, IntegerChoices
```

## TextChoices

Para valores string:

```python
from core import TextChoices

class Status(TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"

# Acessar valor e label
Status.DRAFT.value      # "draft"
Status.DRAFT.label      # "Draft"

# Listar todos
Status.choices          # [("draft", "Draft"), ("published", "Published"), ...]
Status.values           # ["draft", "published", "archived"]
Status.labels           # ["Draft", "Published", "Archived"]

# Buscar por valor
Status.from_value("draft")     # Status.DRAFT
Status.get_label("published")  # "Published"
Status.is_valid("draft")       # True
```

## IntegerChoices

Para valores inteiros:

```python
from core import IntegerChoices

class Priority(IntegerChoices):
    LOW = 1, "Low Priority"
    MEDIUM = 2, "Medium Priority"
    HIGH = 3, "High Priority"
    CRITICAL = 4, "Critical"

# Acessar valor e label
Priority.HIGH.value     # 3
Priority.HIGH.label     # "High Priority"

# Listar todos
Priority.choices        # [(1, "Low Priority"), (2, "Medium Priority"), ...]
Priority.values         # [1, 2, 3, 4]
Priority.labels         # ["Low Priority", "Medium Priority", ...]
```

## Uso em Models

Use `Field.choice()` para criar campos com choices:

```python
from core import Model, Field, TextChoices, IntegerChoices

class Status(TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"

class Priority(IntegerChoices):
    LOW = 1, "Low"
    MEDIUM = 2, "Medium"
    HIGH = 3, "High"

class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = Field.pk()
    title: Mapped[str] = Field.string(max_length=200)
    
    # Campo com TextChoices
    status: Mapped[str] = Field.choice(Status, default=Status.DRAFT)
    
    # Campo com IntegerChoices
    priority: Mapped[int] = Field.choice(Priority, default=Priority.MEDIUM)
```

### Criando e Consultando

```python
# Criar com enum
post = Post(
    title="Hello World",
    status=Status.PUBLISHED,
    priority=Priority.HIGH,
)
await post.save(db)

# Comparação funciona com valor ou enum
post.status == "published"       # True
post.status == Status.PUBLISHED  # True

post.priority == 3               # True
post.priority == Priority.HIGH   # True

# Filtrar por enum
published = await Post.objects.using(db).filter(status=Status.PUBLISHED).all()
high_priority = await Post.objects.using(db).filter(priority=Priority.HIGH).all()

# Ou por valor
published = await Post.objects.using(db).filter(status="published").all()
```

### Obtendo o Label

```python
# A partir do valor armazenado
label = Status.get_label(post.status)  # "Published"

# Ou via enum member
member = Status.from_value(post.status)
if member:
    print(member.label)  # "Published"
```

## Uso em Schemas (Pydantic)

```python
from pydantic import field_validator
from core import InputSchema, OutputSchema

class PostInput(InputSchema):
    title: str
    status: str
    priority: int
    
    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if not Status.is_valid(v):
            raise ValueError(f"Invalid status. Must be one of: {Status.values}")
        return v
    
    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        if not Priority.is_valid(v):
            raise ValueError(f"Invalid priority. Must be one of: {Priority.values}")
        return v

class PostOutput(OutputSchema):
    id: int
    title: str
    status: str
    status_label: str  # Campo extra para o label
    priority: int
    priority_label: str
    
    @classmethod
    def from_model(cls, post: Post) -> "PostOutput":
        return cls(
            id=post.id,
            title=post.title,
            status=post.status,
            status_label=Status.get_label(post.status),
            priority=post.priority,
            priority_label=Priority.get_label(post.priority),
        )
```

## Uso em API Response

```python
from core import ModelViewSet

class PostViewSet(ModelViewSet):
    model = Post
    
    @action(methods=["GET"], detail=False)
    async def statuses(self, request, **kwargs):
        """Retorna todos os status disponíveis."""
        return {
            "statuses": [
                {"value": value, "label": label}
                for value, label in Status.choices
            ]
        }
    
    @action(methods=["GET"], detail=False)
    async def priorities(self, request, **kwargs):
        """Retorna todas as prioridades disponíveis."""
        return {
            "priorities": [
                {"value": value, "label": label}
                for value, label in Priority.choices
            ]
        }
```

## Choices Prontos para Usar

O framework inclui choices comuns:

### CommonStatus
```python
from core import CommonStatus

CommonStatus.ACTIVE      # "active", "Active"
CommonStatus.INACTIVE    # "inactive", "Inactive"
CommonStatus.PENDING     # "pending", "Pending"
CommonStatus.SUSPENDED   # "suspended", "Suspended"
```

### PublishStatus
```python
from core import PublishStatus

PublishStatus.DRAFT           # "draft", "Draft"
PublishStatus.PENDING_REVIEW  # "pending_review", "Pending Review"
PublishStatus.PUBLISHED       # "published", "Published"
PublishStatus.ARCHIVED        # "archived", "Archived"
```

### OrderStatus
```python
from core import OrderStatus

OrderStatus.PENDING     # "pending", "Pending"
OrderStatus.PROCESSING  # "processing", "Processing"
OrderStatus.COMPLETED   # "completed", "Completed"
OrderStatus.CANCELLED   # "cancelled", "Cancelled"
OrderStatus.REFUNDED    # "refunded", "Refunded"
```

### PaymentStatus
```python
from core import PaymentStatus

PaymentStatus.PENDING     # "pending", "Pending"
PaymentStatus.PROCESSING  # "processing", "Processing"
PaymentStatus.PAID        # "paid", "Paid"
PaymentStatus.FAILED      # "failed", "Failed"
PaymentStatus.REFUNDED    # "refunded", "Refunded"
```

### TaskPriority
```python
from core import TaskPriority

TaskPriority.LOW       # 1, "Low"
TaskPriority.MEDIUM    # 2, "Medium"
TaskPriority.HIGH      # 3, "High"
TaskPriority.CRITICAL  # 4, "Critical"
```

### Weekday
```python
from core import Weekday

Weekday.MONDAY     # 1, "Monday"
Weekday.TUESDAY    # 2, "Tuesday"
# ... até SUNDAY (7)
```

### Month
```python
from core import Month

Month.JANUARY   # 1, "January"
Month.FEBRUARY  # 2, "February"
# ... até DECEMBER (12)
```

### Gender
```python
from core import Gender

Gender.MALE              # "M", "Male"
Gender.FEMALE            # "F", "Female"
Gender.OTHER             # "O", "Other"
Gender.PREFER_NOT_TO_SAY # "N", "Prefer not to say"
```

### Visibility
```python
from core import Visibility

Visibility.PUBLIC       # "public", "Public"
Visibility.PRIVATE      # "private", "Private"
Visibility.UNLISTED     # "unlisted", "Unlisted"
Visibility.MEMBERS_ONLY # "members", "Members Only"
```

## Criando Choices Customizados

### TextChoices Customizado

```python
from core import TextChoices

class TicketType(TextChoices):
    BUG = "bug", "Bug Report"
    FEATURE = "feature", "Feature Request"
    QUESTION = "question", "Question"
    IMPROVEMENT = "improvement", "Improvement"

class DocumentType(TextChoices):
    CONTRACT = "contract", "Contract"
    INVOICE = "invoice", "Invoice"
    PROPOSAL = "proposal", "Proposal"
    REPORT = "report", "Report"
```

### IntegerChoices Customizado

```python
from core import IntegerChoices

class UserLevel(IntegerChoices):
    GUEST = 0, "Guest"
    MEMBER = 1, "Member"
    MODERATOR = 2, "Moderator"
    ADMIN = 3, "Administrator"
    SUPERADMIN = 4, "Super Administrator"

class DifficultyLevel(IntegerChoices):
    EASY = 1, "Easy"
    MEDIUM = 2, "Medium"
    HARD = 3, "Hard"
    EXPERT = 4, "Expert"
```

## Exemplo Completo

```python
from sqlalchemy.orm import Mapped
from core import Model, Field, TextChoices, IntegerChoices, ModelViewSet

# Definir choices
class ArticleStatus(TextChoices):
    DRAFT = "draft", "Draft"
    REVIEW = "review", "In Review"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"

class ArticlePriority(IntegerChoices):
    LOW = 1, "Low"
    NORMAL = 2, "Normal"
    HIGH = 3, "High"
    FEATURED = 4, "Featured"

# Model
class Article(Model):
    __tablename__ = "articles"
    
    id: Mapped[int] = Field.pk()
    title: Mapped[str] = Field.string(max_length=200)
    content: Mapped[str] = Field.text()
    status: Mapped[str] = Field.choice(ArticleStatus, default=ArticleStatus.DRAFT)
    priority: Mapped[int] = Field.choice(ArticlePriority, default=ArticlePriority.NORMAL)

# ViewSet
class ArticleViewSet(ModelViewSet):
    model = Article
    
    @action(methods=["GET"], detail=False)
    async def options(self, request, **kwargs):
        """Retorna opções para formulários."""
        return {
            "statuses": [{"value": v, "label": l} for v, l in ArticleStatus.choices],
            "priorities": [{"value": v, "label": l} for v, l in ArticlePriority.choices],
        }
    
    @action(methods=["POST"], detail=True)
    async def publish(self, request, db, id, **kwargs):
        """Publica um artigo."""
        article = await self.get_object(db, id)
        article.status = ArticleStatus.PUBLISHED
        await article.save(db)
        await db.commit()
        return {"message": "Article published", "status": article.status}
```

## Comparação com Django

| Django | Core Framework |
|--------|----------------|
| `models.TextChoices` | `TextChoices` |
| `models.IntegerChoices` | `IntegerChoices` |
| `CharField(choices=...)` | `Field.choice(ChoicesClass)` |
| `choice.label` | `choice.label` |
| `ChoicesClass.choices` | `ChoicesClass.choices` |

## Boas Práticas

1. **Defina choices em arquivo separado** para reutilização
2. **Use TextChoices para status** - mais legível no banco
3. **Use IntegerChoices para níveis/prioridades** - mais eficiente
4. **Sempre forneça labels descritivos** para i18n
5. **Exponha choices via API** para formulários dinâmicos
