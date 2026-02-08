# Choices

Django-style TextChoices and IntegerChoices.

**Important:** Use `TextChoices`/`IntegerChoices` instead of Python `Enum`.

## TextChoices

For string values.

```python
from core.choices import TextChoices

class Status(TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"
```

## IntegerChoices

For integer values.

```python
from core.choices import IntegerChoices

class Priority(IntegerChoices):
    LOW = 1, "Low Priority"
    MEDIUM = 2, "Medium Priority"
    HIGH = 3, "High Priority"
    CRITICAL = 4, "Critical"
```

## Usage in Models

```python
from core import Model, Field
from sqlalchemy.orm import Mapped

class Status(TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"

class Post(Model):
    __tablename__ = "posts"
    
    status: Mapped[str] = Field.choice(Status, default=Status.DRAFT)
```

### Native PostgreSQL ENUM

```python
status: Mapped[str] = Field.choice(
    Status,
    default=Status.DRAFT,
    use_native_enum=True  # Uses PostgreSQL ENUM type
)
```

## Accessing Values

```python
# Value
Status.DRAFT.value      # "draft"
Priority.HIGH.value     # 3

# Label
Status.DRAFT.label      # "Draft"
Priority.HIGH.label     # "High Priority"

# All choices (for forms/API)
Status.choices          # [("draft", "Draft"), ("published", "Published"), ...]

# All values
Status.values           # ["draft", "published", "archived"]

# All labels
Status.labels           # ["Draft", "Published", "Archived"]

# Max length (for database column)
Status.max_length       # 9 (length of "published")
```

## Lookup Methods

```python
# Get by value
Status.from_value("draft")  # Status.DRAFT

# Get label for value
Status.get_label("draft")   # "Draft"

# Check if valid
Status.is_valid("draft")    # True
Status.is_valid("invalid")  # False
```

## Comparison

Works with both enum members and raw values:

```python
post.status == Status.PUBLISHED   # True
post.status == "published"        # True

post.priority == Priority.HIGH    # True
post.priority == 3                # True
```

## Built-in Choices

### CommonStatus

```python
from core.choices import CommonStatus

CommonStatus.ACTIVE      # "active"
CommonStatus.INACTIVE    # "inactive"
CommonStatus.PENDING     # "pending"
CommonStatus.SUSPENDED   # "suspended"
```

### PublishStatus

```python
from core.choices import PublishStatus

PublishStatus.DRAFT           # "draft"
PublishStatus.PENDING_REVIEW  # "pending_review"
PublishStatus.PUBLISHED       # "published"
PublishStatus.ARCHIVED        # "archived"
```

### OrderStatus

```python
from core.choices import OrderStatus

OrderStatus.PENDING     # "pending"
OrderStatus.PROCESSING  # "processing"
OrderStatus.COMPLETED   # "completed"
OrderStatus.CANCELLED   # "cancelled"
OrderStatus.REFUNDED    # "refunded"
```

### PaymentStatus

```python
from core.choices import PaymentStatus

PaymentStatus.PENDING     # "pending"
PaymentStatus.PROCESSING  # "processing"
PaymentStatus.PAID        # "paid"
PaymentStatus.FAILED      # "failed"
PaymentStatus.REFUNDED    # "refunded"
PaymentStatus.CANCELLED   # "cancelled"
```

### TaskPriority

```python
from core.choices import TaskPriority

TaskPriority.LOW       # 1
TaskPriority.MEDIUM    # 2
TaskPriority.HIGH      # 3
TaskPriority.CRITICAL  # 4
```

### Weekday

```python
from core.choices import Weekday

Weekday.MONDAY     # 1
Weekday.TUESDAY    # 2
# ... through
Weekday.SUNDAY     # 7
```

### Month

```python
from core.choices import Month

Month.JANUARY   # 1
Month.FEBRUARY  # 2
# ... through
Month.DECEMBER  # 12
```

### Gender

```python
from core.choices import Gender

Gender.MALE          # "M"
Gender.FEMALE        # "F"
Gender.OTHER         # "O"
Gender.NOT_INFORMED  # "N"
```

### Visibility

```python
from core.choices import Visibility

Visibility.PUBLIC    # "public"
Visibility.PRIVATE   # "private"
Visibility.UNLISTED  # "unlisted"
Visibility.MEMBERS   # "members"
```

## Validation

### In Serializers

```python
from core.serializers import InputSchema
from pydantic import field_validator

class PostInput(InputSchema):
    status: str
    
    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if not Status.is_valid(v):
            raise ValueError(f"Invalid status. Must be one of: {Status.values}")
        return v
```

### With ChoiceValidator

```python
from core.validators import ChoiceValidator

validator = ChoiceValidator(choices=Status.values)
validator("draft")    # OK
validator("invalid")  # Raises ValidationError
```

## Querying

```python
# Filter by choice
posts = await Post.objects.using(db).filter(status=Status.PUBLISHED).all()

# Or by value
posts = await Post.objects.using(db).filter(status="published").all()

# Multiple values
posts = await Post.objects.using(db).filter(
    status__in=[Status.DRAFT, Status.PUBLISHED]
).all()
```

## OpenAPI Documentation

Choices are automatically documented in OpenAPI:

```python
class PostInput(InputSchema):
    status: Status  # Shows enum values in Swagger
```

## Custom Choices

```python
from core.choices import TextChoices, IntegerChoices

class TicketType(TextChoices):
    BUG = "bug", "Bug Report"
    FEATURE = "feature", "Feature Request"
    SUPPORT = "support", "Support Request"
    QUESTION = "question", "Question"

class SeverityLevel(IntegerChoices):
    TRIVIAL = 1, "Trivial"
    MINOR = 2, "Minor"
    MAJOR = 3, "Major"
    BLOCKER = 4, "Blocker"
```

## Why Not Python Enum?

TextChoices/IntegerChoices provide:

1. **Labels** — Human-readable names
2. **`.choices`** — Ready for forms/dropdowns
3. **`.values`** — List of valid values
4. **`.max_length`** — For database column sizing
5. **Direct comparison** — Works with raw values
6. **Django compatibility** — Familiar API

## Next

- [Fields](10-fields.md) — Field types
- [Models](03-models.md) — Model basics
