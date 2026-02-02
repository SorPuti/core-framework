# ViewSets

ViewSets encapsulate CRUD logic in a single class. No decorators needed.

## ModelViewSet

Full CRUD with automatic routing.

```python
from core import ModelViewSet
from .models import Product
from .schemas import ProductInput, ProductOutput

class ProductViewSet(ModelViewSet):
    model = Product
    input_schema = ProductInput
    output_schema = ProductOutput
    tags = ["Products"]
    
    # Pagination
    page_size = 20
    max_page_size = 100
    
    # Lookup field (default: id)
    lookup_field = "id"
```

## Custom Actions

Add endpoints beyond CRUD using `@action`.

```python
from core import ModelViewSet, action
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

class ProductViewSet(ModelViewSet):
    model = Product
    
    @action(methods=["POST"], detail=True)
    async def publish(self, request: Request, db: AsyncSession, **kwargs):
        """POST /products/{id}/publish"""
        product = await self.get_object(db, **kwargs)
        product.published = True
        await product.save(db)
        return {"status": "published"}
    
    @action(methods=["GET"], detail=False)
    async def featured(self, request: Request, db: AsyncSession, **kwargs):
        """GET /products/featured"""
        products = await self.get_queryset(db).filter(featured=True).all()
        schema = self.get_output_schema()
        return [schema.model_validate(p).model_dump() for p in products]
```

## Action Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| methods | list[str] | HTTP methods (GET, POST, PUT, DELETE) |
| detail | bool | True = /{id}/action, False = /action |
| url_path | str | Custom URL path (default: method name) |
| permission_classes | list | Override permissions for this action |

## Hooks

Override to customize behavior.

```python
class ProductViewSet(ModelViewSet):
    model = Product
    
    async def perform_create(self, data: dict, db: AsyncSession) -> Product:
        """Called after validation, before save."""
        data["created_by"] = self.request.state.user.id
        return await super().perform_create(data, db)
    
    async def perform_update(self, obj: Product, data: dict, db: AsyncSession) -> Product:
        """Called after validation, before save."""
        data["updated_by"] = self.request.state.user.id
        return await super().perform_update(obj, data, db)
    
    async def perform_destroy(self, obj: Product, db: AsyncSession) -> None:
        """Called before delete. Use for soft delete."""
        obj.deleted = True
        await obj.save(db)
        # Don't call super() to prevent actual deletion
```

## Validation Hooks

```python
class ProductViewSet(ModelViewSet):
    model = Product
    unique_fields = ["sku"]  # Auto-validate uniqueness
    
    async def validate(self, data: dict, db: AsyncSession, instance=None) -> dict:
        """Cross-field validation."""
        if data.get("price", 0) < data.get("cost", 0):
            from core.validators import ValidationError
            raise ValidationError("Price must be greater than cost", field="price")
        return data
    
    async def validate_field(self, field: str, value, db: AsyncSession, instance=None):
        """Per-field validation."""
        if field == "sku" and not value.startswith("SKU-"):
            from core.validators import ValidationError
            raise ValidationError("SKU must start with 'SKU-'", field="sku")
        return value
```

## QuerySet Customization

```python
class ProductViewSet(ModelViewSet):
    model = Product
    
    def get_queryset(self, db: AsyncSession):
        """Filter queryset based on user."""
        qs = super().get_queryset(db)
        user = self.request.state.user
        
        if not user or not user.is_staff:
            return qs.filter(published=True)
        return qs
```

## ReadOnlyModelViewSet

Only list and retrieve.

```python
from core import ReadOnlyModelViewSet

class PublicProductViewSet(ReadOnlyModelViewSet):
    model = Product
    output_schema = ProductOutput
    permission_classes = [AllowAny]
```

## APIView

For non-model endpoints.

```python
from core import APIView
from core.permissions import AllowAny

class HealthView(APIView):
    permission_classes = [AllowAny]
    tags = ["System"]
    
    async def get(self, request, **kwargs):
        return {"status": "healthy"}
    
    async def post(self, request, **kwargs):
        body = await request.json()
        return {"received": body}
```

Next: [Authentication](03-authentication.md)
