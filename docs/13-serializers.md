# Serializers

Input/Output schemas for request/response handling.

## InputSchema vs OutputSchema

**Important:** Use `InputSchema` and `OutputSchema`, not raw `BaseModel`.

| Feature | `InputSchema` | `OutputSchema` |
|---------|---------------|----------------|
| Unknown fields | Rejects (422) | Allows |
| Strip whitespace | Yes | No |
| Purpose | Request validation | Response serialization |

## InputSchema

For request bodies.

```python
from core.serializers import InputSchema

class ItemCreateInput(InputSchema):
    name: str
    price: float
    description: str | None = None
```

Features:
- `extra="forbid"` — Rejects unknown fields
- `str_strip_whitespace=True` — Auto-strips strings
- `from_attributes=True` — ORM compatibility

## OutputSchema

For responses.

```python
from core.serializers import OutputSchema
from datetime import datetime

class ItemOutput(OutputSchema):
    id: int
    name: str
    price: float
    created_at: datetime
```

Features:
- `from_attributes=True` — ORM compatibility
- `from_orm()` and `from_orm_list()` helpers

```python
# Convert ORM object
item_data = ItemOutput.from_orm(item)

# Convert list
items_data = ItemOutput.from_orm_list(items)
```

## Usage in ViewSets

```python
from core import ModelViewSet
from .models import Item
from .schemas import ItemCreateInput, ItemOutput

class ItemViewSet(ModelViewSet):
    model = Item
    input_schema = ItemCreateInput
    output_schema = ItemOutput
```

## Field Validators

```python
from core.serializers import InputSchema
from pydantic import field_validator

class UserCreateInput(InputSchema):
    email: str
    name: str
    password: str
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v.strip()
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v
```

## Model Validators

Cross-field validation.

```python
from core.serializers import InputSchema
from pydantic import model_validator

class PasswordChangeInput(InputSchema):
    password: str
    password_confirm: str
    
    @model_validator(mode="after")
    def passwords_match(self) -> "PasswordChangeInput":
        if self.password != self.password_confirm:
            raise ValueError("Passwords don't match")
        return self
```

## Computed Fields

```python
from core.serializers import OutputSchema
from pydantic import computed_field

class PostOutput(OutputSchema):
    id: int
    title: str
    content: str
    
    @computed_field
    @property
    def excerpt(self) -> str:
        if len(self.content) <= 100:
            return self.content
        return self.content[:100] + "..."
```

## Nested Schemas

```python
# Nested output
class UserOutput(OutputSchema):
    id: int
    name: str

class PostOutput(OutputSchema):
    id: int
    title: str
    author: UserOutput | None = None

# Nested input
class AddressInput(InputSchema):
    street: str
    city: str

class UserCreateInput(InputSchema):
    name: str
    address: AddressInput

# List of nested
class OrderOutput(OutputSchema):
    id: int
    items: list[OrderItemOutput]
```

## Serializer Class

For complex serialization logic.

```python
from core.serializers import Serializer

class ItemSerializer(Serializer[Item, ItemCreateInput, ItemOutput]):
    input_schema = ItemCreateInput
    output_schema = ItemOutput
    
    def validate_input(self, data: dict) -> ItemCreateInput:
        return self.input_schema.model_validate(data)
    
    def serialize(self, obj: Item) -> ItemOutput:
        return self.output_schema.model_validate(obj)
```

## ModelSerializer

With create/update methods.

```python
from core.serializers import ModelSerializer

class ItemSerializer(ModelSerializer[Item, ItemCreateInput, ItemOutput]):
    model = Item
    input_schema = ItemCreateInput
    output_schema = ItemOutput
    
    exclude_on_create = ["id", "created_at"]
    exclude_on_update = ["id"]
    read_only_fields = ["created_at", "updated_at"]
    
    async def create(self, data: ItemCreateInput, session) -> Item:
        item = Item(**data.model_dump(exclude=set(self.exclude_on_create)))
        await item.save(session)
        return item
    
    async def update(self, instance: Item, data: ItemCreateInput, session, partial=False) -> Item:
        update_data = data.model_dump(
            exclude=set(self.exclude_on_update + self.read_only_fields),
            exclude_unset=partial
        )
        for field, value in update_data.items():
            setattr(instance, field, value)
        await instance.save(session)
        return instance
```

## Partial Updates

ViewSets auto-generate partial schemas for PATCH.

```python
# Full update (PUT) uses ItemCreateInput
# Partial update (PATCH) uses auto-generated partial schema
# where all fields are optional
```

## Common Patterns

### Create vs Update Schemas

```python
class ItemCreateInput(InputSchema):
    name: str
    price: float
    category_id: int

class ItemUpdateInput(InputSchema):
    name: str | None = None
    price: float | None = None
    # category_id not updatable

class ItemViewSet(ModelViewSet):
    model = Item
    input_schema = ItemCreateInput
    # PATCH auto-generates partial from input_schema
```

### Different Output Detail

```python
class ItemListOutput(OutputSchema):
    id: int
    name: str

class ItemDetailOutput(OutputSchema):
    id: int
    name: str
    description: str
    created_at: datetime
    author: UserOutput

class ItemViewSet(ModelViewSet):
    model = Item
    output_schema = ItemListOutput  # For list
    
    def get_output_schema(self):
        if self.action == "retrieve":
            return ItemDetailOutput
        return self.output_schema
```

### Password Handling

```python
class UserCreateInput(InputSchema):
    email: str
    password: str

class UserOutput(OutputSchema):
    id: int
    email: str
    # password NOT included in output
```

## Next

- [Validators](14-validators.md) — Data validation
- [ViewSets](04-viewsets.md) — CRUD endpoints
