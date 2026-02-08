# QuerySets

Django-style query API for SQLAlchemy models.

## Basic Queries

```python
from .models import Post

# Get all
posts = await Post.objects.all()

# Filter
posts = await Post.objects.filter(published=True).all()

# Get single object (raises DoesNotExist if not found)
post = await Post.objects.get(id=1)

# Get or None
post = await Post.objects.get_or_none(id=1)

# First
post = await Post.objects.filter(author_id=1).first()

# Count
count = await Post.objects.filter(published=True).count()

# Exists
exists = await Post.objects.filter(email="test@example.com").exists()
```

## Filtering

```python
# Exact match
posts = await Post.objects.filter(status="published").all()

# Multiple conditions (AND)
posts = await Post.objects.filter(status="published", author_id=1).all()

# Chained filters (AND)
posts = await Post.objects.filter(status="published").filter(author_id=1).all()

# Exclude
posts = await Post.objects.exclude(status="draft").all()
```

## Lookups

```python
# Greater than
posts = await Post.objects.filter(views__gt=100).all()

# Less than
posts = await Post.objects.filter(views__lt=50).all()

# Greater/less than or equal
posts = await Post.objects.filter(views__gte=100).all()
posts = await Post.objects.filter(views__lte=50).all()

# Contains (LIKE %value%)
posts = await Post.objects.filter(title__contains="python").all()

# Starts with
posts = await Post.objects.filter(title__startswith="How").all()

# Ends with
posts = await Post.objects.filter(title__endswith="?").all()

# In list
posts = await Post.objects.filter(status__in=["published", "featured"]).all()

# Is null
posts = await Post.objects.filter(deleted_at__isnull=True).all()

# Case insensitive
posts = await Post.objects.filter(title__icontains="PYTHON").all()
posts = await Post.objects.filter(title__iexact="hello world").all()
```

## Ordering

```python
# Ascending
posts = await Post.objects.order_by("created_at").all()

# Descending
posts = await Post.objects.order_by("-created_at").all()

# Multiple fields
posts = await Post.objects.order_by("-featured", "-created_at").all()
```

## Pagination

```python
# Limit
posts = await Post.objects.limit(10).all()

# Offset
posts = await Post.objects.offset(20).limit(10).all()

# Slice (equivalent to offset + limit)
posts = await Post.objects.all()[20:30]
```

## Aggregations

```python
# Count
count = await Post.objects.filter(published=True).count()

# Sum
total = await Post.objects.sum("views")

# Average
avg = await Post.objects.avg("views")

# Min/Max
min_views = await Post.objects.min("views")
max_views = await Post.objects.max("views")
```

## Select Related (Eager Loading)

```python
# Load related author
posts = await Post.objects.select_related("author").all()

# Multiple relations
posts = await Post.objects.select_related("author", "category").all()

# Access without additional queries
for post in posts:
    print(post.author.email)  # No extra query
```

## Values (Partial Select)

```python
# Select specific columns
posts = await Post.objects.values("id", "title").all()
# Returns: [{"id": 1, "title": "..."}, ...]

# Values list (tuples)
posts = await Post.objects.values_list("id", "title").all()
# Returns: [(1, "..."), (2, "..."), ...]

# Flat values (single column)
ids = await Post.objects.values_list("id", flat=True).all()
# Returns: [1, 2, 3, ...]
```

## Distinct

```python
# Unique values
authors = await Post.objects.values("author_id").distinct().all()
```

## Raw SQL

```python
# Raw query
posts = await Post.objects.raw("SELECT * FROM posts WHERE views > 100")

# With parameters
posts = await Post.objects.raw(
    "SELECT * FROM posts WHERE author_id = :author_id",
    {"author_id": 1}
)
```

## Using Session

```python
from core.models import get_session

async def get_posts():
    db = await get_session()
    async with db:
        posts = await Post.objects.using(db).filter(published=True).all()
        return posts
```

## Create/Update/Delete

```python
# Create
post = Post(title="New Post", content="...")
await post.save()

# Update
post.title = "Updated Title"
await post.save()

# Delete
await post.delete()

# Bulk update
await Post.objects.filter(author_id=1).update(status="archived")

# Bulk delete
await Post.objects.filter(status="draft").delete()
```

## Next

- [Models](03-models.md) — Model definitions
- [ViewSets](04-viewsets.md) — CRUD endpoints
