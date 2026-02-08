# Testing

Test utilities for Core Framework apps.

## Setup

```bash
pip install pytest pytest-asyncio httpx
```

## Test Client

```python
# tests/conftest.py
import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
```

## Basic Tests

```python
# tests/test_items.py
import pytest

@pytest.mark.asyncio
async def test_list_items(client):
    response = await client.get("/api/v1/items/")
    assert response.status_code == 200
    assert "items" in response.json()

@pytest.mark.asyncio
async def test_create_item(client):
    response = await client.post(
        "/api/v1/items/",
        json={"name": "Test Item", "price": 9.99}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Item"

@pytest.mark.asyncio
async def test_get_item(client):
    # Create first
    create = await client.post(
        "/api/v1/items/",
        json={"name": "Test", "price": 10.0}
    )
    item_id = create.json()["id"]
    
    # Get
    response = await client.get(f"/api/v1/items/{item_id}")
    assert response.status_code == 200
    assert response.json()["id"] == item_id
```

## Test Database

```python
# tests/conftest.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from core.models import Base

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="function")
async def db():
    engine = create_async_engine(TEST_DATABASE_URL)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
```

## Authenticated Tests

```python
# tests/conftest.py
@pytest.fixture
async def auth_client(client):
    # Register user
    await client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "SecurePass123"}
    )
    
    # Login
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "SecurePass123"}
    )
    token = response.json()["access_token"]
    
    # Set auth header
    client.headers["Authorization"] = f"Bearer {token}"
    return client

@pytest.mark.asyncio
async def test_protected_endpoint(auth_client):
    response = await auth_client.get("/api/v1/users/me")
    assert response.status_code == 200
```

## Model Tests

```python
# tests/test_models.py
import pytest
from src.apps.items.models import Item

@pytest.mark.asyncio
async def test_create_item(db):
    item = Item(name="Test", price=10.0)
    db.add(item)
    await db.commit()
    
    assert item.id is not None
    assert item.name == "Test"

@pytest.mark.asyncio
async def test_queryset(db):
    # Create items
    for i in range(5):
        item = Item(name=f"Item {i}", price=i * 10)
        db.add(item)
    await db.commit()
    
    # Query
    items = await Item.objects.using(db).filter(price__gt=20).all()
    assert len(items) == 2
```

## Run Tests

```bash
# All tests
core test

# With coverage
core test --cov

# Specific file
core test tests/test_items.py

# Verbose
core test -v

# Stop on first failure
core test -x
```

## pytest.ini

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_functions = test_*
```

## Next

- [CLI](07-cli.md) — Test command options
- [ViewSets](04-viewsets.md) — Endpoints to test
