# Validators

Data validation system.

## Validator Types

| Type | Base Class | Usage |
|------|------------|-------|
| Sync | `Validator` | Format validation |
| Async | `AsyncValidator` | Database validation |

## Database Validators (Async)

### UniqueValidator

```python
from core.validators import UniqueValidator

validator = UniqueValidator(
    model=User,
    field_name="email",
    message="This email already exists.",
    exclude_pk=None,  # Exclude on update
)

# Usage
await validator(value, session)
```

### UniqueTogetherValidator

```python
from core.validators import UniqueTogetherValidator

validator = UniqueTogetherValidator(
    model=Post,
    fields=["slug", "workspace_id"],
    message="Slug must be unique per workspace.",
)

# Usage (pass dict)
await validator({"slug": "test", "workspace_id": 1}, session)
```

### ExistsValidator

```python
from core.validators import ExistsValidator

validator = ExistsValidator(
    model=Category,
    field_name="id",
    message="Category does not exist.",
)

# Usage
await validator(category_id, session)
```

## Format Validators (Sync)

### RegexValidator

```python
from core.validators import RegexValidator

validator = RegexValidator(
    pattern=r"^[A-Z]{3}-\d{4}$",
    message="Invalid code format. Use XXX-0000.",
)

validator("ABC-1234")  # OK
validator("abc-1234")  # Raises ValidationError
```

### EmailValidator

```python
from core.validators import EmailValidator

validator = EmailValidator()
validator("user@example.com")  # OK
```

### URLValidator

```python
from core.validators import URLValidator

validator = URLValidator(schemes=["http", "https"])
validator("https://example.com")  # OK
```

### SlugValidator

```python
from core.validators import SlugValidator

validator = SlugValidator(allow_unicode=False)
validator("my-slug-123")  # OK
```

## Brazilian Validators

### PhoneValidator

```python
from core.validators import PhoneValidator

validator = PhoneValidator()
validator("11999998888")  # OK (10 or 11 digits)
```

### CPFValidator

```python
from core.validators import CPFValidator

validator = CPFValidator()
validator("12345678909")  # Validates check digits
```

### CNPJValidator

```python
from core.validators import CNPJValidator

validator = CNPJValidator()
validator("11222333000181")  # Validates check digits
```

## Range Validators

### MinLengthValidator / MaxLengthValidator

```python
from core.validators import MinLengthValidator, MaxLengthValidator

min_validator = MinLengthValidator(min_length=3)
max_validator = MaxLengthValidator(max_length=100)

min_validator("ab")  # Raises: min 3 characters
max_validator("x" * 101)  # Raises: max 100 characters
```

### MinValueValidator / MaxValueValidator

```python
from core.validators import MinValueValidator, MaxValueValidator

min_validator = MinValueValidator(min_value=0)
max_validator = MaxValueValidator(max_value=100)

min_validator(-1)  # Raises: min value is 0
max_validator(101)  # Raises: max value is 100
```

### RangeValidator

```python
from core.validators import RangeValidator

validator = RangeValidator(min_value=1, max_value=10)
validator(5)  # OK
validator(11)  # Raises: must be between 1 and 10
```

### DecimalPlacesValidator

```python
from core.validators import DecimalPlacesValidator

validator = DecimalPlacesValidator(max_digits=10, decimal_places=2)
validator(123.45)  # OK
validator(123.456)  # Raises: max 2 decimal places
```

## Choice Validators

### ChoiceValidator

```python
from core.validators import ChoiceValidator

validator = ChoiceValidator(choices=["draft", "published", "archived"])
validator("draft")  # OK
validator("invalid")  # Raises: not a valid choice
```

### ProhibitedValidator

```python
from core.validators import ProhibitedValidator

validator = ProhibitedValidator(prohibited=["admin", "root", "system"])
validator("user")  # OK
validator("admin")  # Raises: prohibited value
```

## File Validators

### FileExtensionValidator

```python
from core.validators import FileExtensionValidator

validator = FileExtensionValidator(allowed_extensions=["jpg", "png", "gif"])
validator("image.jpg")  # OK
validator("file.exe")  # Raises: extension not allowed
```

### FileSizeValidator

```python
from core.validators import FileSizeValidator

validator = FileSizeValidator(max_size=5 * 1024 * 1024)  # 5MB
validator(file_size_bytes)
```

## Password Validator

```python
from core.validators import PasswordValidator

validator = PasswordValidator(
    min_length=8,
    max_length=128,
    require_uppercase=True,
    require_lowercase=True,
    require_digit=True,
    require_special=False,
)

validator("Password123")  # OK
validator("weak")  # Raises: doesn't meet requirements
```

## Composite Validators

### ComposeValidators (Sync)

```python
from core.validators import ComposeValidators, MinLengthValidator, MaxLengthValidator

validator = ComposeValidators([
    MinLengthValidator(3),
    MaxLengthValidator(50),
    SlugValidator(),
])

validator("my-slug")  # Runs all validators
```

### ComposeAsyncValidators (Async)

```python
from core.validators import ComposeAsyncValidators, UniqueValidator, ExistsValidator

validator = ComposeAsyncValidators([
    UniqueValidator(User, "email"),
    ExistsValidator(Workspace, "id"),
])

await validator(data, session)
```

## Usage in ViewSets

### unique_fields

Auto-validates uniqueness.

```python
class UserViewSet(ModelViewSet):
    model = User
    unique_fields = ["email", "username"]
```

### field_validators

Custom validators per field.

```python
class UserViewSet(ModelViewSet):
    model = User
    
    field_validators = {
        "email": [EmailValidator()],
        "phone": [PhoneValidator()],
    }
```

### validate_{field} Method

Custom validation method.

```python
class UserViewSet(ModelViewSet):
    model = User
    
    async def validate_email(self, value, db, instance=None):
        if value.endswith("@spam.com"):
            raise ValidationError("Email domain not allowed", field="email")
        return value
```

### validate() Method

Cross-field validation.

```python
class OrderViewSet(ModelViewSet):
    model = Order
    
    async def validate(self, data, db, instance=None):
        if data.get("quantity", 0) > data.get("stock", 0):
            raise ValidationError("Quantity exceeds stock")
        return data
```

## Utility Functions

### validate_all (Sync)

```python
from core.validators import validate_all, MinLengthValidator, MaxLengthValidator

errors = validate_all(
    value="ab",
    validators=[MinLengthValidator(3), MaxLengthValidator(50)],
)
# Returns list of ValidationError
```

### validate_all_async (Async)

```python
from core.validators import validate_all_async

errors = await validate_all_async(
    value=email,
    validators=[UniqueValidator(User, "email")],
    session=db,
)
```

## Custom Validator

### Sync Validator

```python
from core.validators import Validator, ValidationError

class NoSpacesValidator(Validator):
    message = "Value cannot contain spaces."
    code = "no_spaces"
    
    def __call__(self, value):
        if " " in value:
            self.fail()
        return value
```

### Async Validator

```python
from core.validators import AsyncValidator, ValidationError

class UniqueSlugValidator(AsyncValidator):
    message = "Slug already exists."
    code = "unique_slug"
    
    def __init__(self, model, exclude_pk=None):
        self.model = model
        self.exclude_pk = exclude_pk
    
    async def __call__(self, value, session, **context):
        query = self.model.objects.using(session).filter(slug=value)
        if self.exclude_pk:
            query = query.exclude(id=self.exclude_pk)
        if await query.exists():
            self.fail()
        return value
```

## Error Format

```json
{
  "detail": "Validation error",
  "code": "validation_error",
  "errors": [
    {
      "message": "This email already exists.",
      "code": "unique",
      "field": "email"
    }
  ]
}
```

## Next

- [Serializers](13-serializers.md) — Input/Output schemas
- [ViewSets](04-viewsets.md) — CRUD endpoints
