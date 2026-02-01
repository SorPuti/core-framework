"""
Testes para o sistema de QuerySets.
"""

import pytest
from datetime import datetime

from sqlalchemy.orm import Mapped

from core.models import Model, Field, init_database, create_tables, drop_tables, get_session
from core.querysets import DoesNotExist, MultipleObjectsReturned


class TestProduct(Model):
    """Model de teste para querysets."""
    
    __tablename__ = "test_products"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=100)
    price: Mapped[float] = Field.float(default=0.0)
    category: Mapped[str] = Field.string(max_length=50)
    is_available: Mapped[bool] = Field.boolean(default=True)


@pytest.fixture
async def setup_db():
    """Setup do banco de dados para testes."""
    await init_database("sqlite+aiosqlite:///:memory:", echo=False)
    await create_tables()
    yield
    await drop_tables()


@pytest.fixture
async def sample_products(setup_db):
    """Cria produtos de exemplo."""
    session = await get_session()
    
    try:
        products = [
            {"name": "Laptop", "price": 1000.0, "category": "electronics", "is_available": True},
            {"name": "Mouse", "price": 50.0, "category": "electronics", "is_available": True},
            {"name": "Keyboard", "price": 100.0, "category": "electronics", "is_available": False},
            {"name": "Chair", "price": 200.0, "category": "furniture", "is_available": True},
            {"name": "Desk", "price": 500.0, "category": "furniture", "is_available": True},
        ]
        
        for product_data in products:
            await TestProduct.objects.using(session).create(**product_data)
        
        await session.commit()
        yield
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_filter_exact(sample_products):
    """Testa filtro exato."""
    session = await get_session()
    
    try:
        products = await TestProduct.objects.using(session)\
            .filter(category="electronics")\
            .all()
        
        assert len(products) == 3
        for p in products:
            assert p.category == "electronics"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_filter_gt(sample_products):
    """Testa filtro greater than."""
    session = await get_session()
    
    try:
        products = await TestProduct.objects.using(session)\
            .filter(price__gt=100.0)\
            .all()
        
        assert len(products) == 3  # Laptop, Chair, Desk
        for p in products:
            assert p.price > 100.0
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_filter_gte(sample_products):
    """Testa filtro greater than or equal."""
    session = await get_session()
    
    try:
        products = await TestProduct.objects.using(session)\
            .filter(price__gte=100.0)\
            .all()
        
        assert len(products) == 4  # Laptop, Keyboard, Chair, Desk
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_filter_lt(sample_products):
    """Testa filtro less than."""
    session = await get_session()
    
    try:
        products = await TestProduct.objects.using(session)\
            .filter(price__lt=100.0)\
            .all()
        
        assert len(products) == 1  # Mouse
        assert products[0].name == "Mouse"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_filter_contains(sample_products):
    """Testa filtro contains."""
    session = await get_session()
    
    try:
        products = await TestProduct.objects.using(session)\
            .filter(name__contains="a")\
            .all()
        
        # Laptop, Keyboard, Chair
        assert len(products) >= 2
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_filter_in(sample_products):
    """Testa filtro in."""
    session = await get_session()
    
    try:
        products = await TestProduct.objects.using(session)\
            .filter(name__in=["Laptop", "Mouse"])\
            .all()
        
        assert len(products) == 2
        names = {p.name for p in products}
        assert names == {"Laptop", "Mouse"}
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_exclude(sample_products):
    """Testa exclusão."""
    session = await get_session()
    
    try:
        products = await TestProduct.objects.using(session)\
            .exclude(category="electronics")\
            .all()
        
        assert len(products) == 2  # Chair, Desk
        for p in products:
            assert p.category != "electronics"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_order_by_asc(sample_products):
    """Testa ordenação ascendente."""
    session = await get_session()
    
    try:
        products = await TestProduct.objects.using(session)\
            .order_by("price")\
            .all()
        
        prices = [p.price for p in products]
        assert prices == sorted(prices)
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_order_by_desc(sample_products):
    """Testa ordenação descendente."""
    session = await get_session()
    
    try:
        products = await TestProduct.objects.using(session)\
            .order_by("-price")\
            .all()
        
        prices = [p.price for p in products]
        assert prices == sorted(prices, reverse=True)
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_limit(sample_products):
    """Testa limite de resultados."""
    session = await get_session()
    
    try:
        products = await TestProduct.objects.using(session)\
            .limit(2)\
            .all()
        
        assert len(products) == 2
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_offset(sample_products):
    """Testa offset de resultados."""
    session = await get_session()
    
    try:
        all_products = await TestProduct.objects.using(session)\
            .order_by("id")\
            .all()
        
        offset_products = await TestProduct.objects.using(session)\
            .order_by("id")\
            .offset(2)\
            .all()
        
        assert len(offset_products) == len(all_products) - 2
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_first(sample_products):
    """Testa primeiro resultado."""
    session = await get_session()
    
    try:
        product = await TestProduct.objects.using(session)\
            .order_by("price")\
            .first()
        
        assert product is not None
        assert product.name == "Mouse"  # Menor preço
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_first_empty():
    """Testa primeiro resultado em queryset vazio."""
    await init_database("sqlite+aiosqlite:///:memory:", echo=False)
    await create_tables()
    
    session = await get_session()
    
    try:
        product = await TestProduct.objects.using(session)\
            .filter(name="NonExistent")\
            .first()
        
        assert product is None
    finally:
        await session.close()
        await drop_tables()


@pytest.mark.asyncio
async def test_get_success(sample_products):
    """Testa get com sucesso."""
    session = await get_session()
    
    try:
        product = await TestProduct.objects.using(session)\
            .filter(name="Laptop")\
            .get()
        
        assert product.name == "Laptop"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_get_does_not_exist(sample_products):
    """Testa get com registro inexistente."""
    session = await get_session()
    
    try:
        with pytest.raises(DoesNotExist):
            await TestProduct.objects.using(session)\
                .filter(name="NonExistent")\
                .get()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_get_multiple_objects(sample_products):
    """Testa get com múltiplos resultados."""
    session = await get_session()
    
    try:
        with pytest.raises(MultipleObjectsReturned):
            await TestProduct.objects.using(session)\
                .filter(category="electronics")\
                .get()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_values(sample_products):
    """Testa retorno de valores específicos."""
    session = await get_session()
    
    try:
        values = await TestProduct.objects.using(session)\
            .filter(category="electronics")\
            .values("name", "price")
        
        assert len(values) == 3
        for v in values:
            assert set(v.keys()) == {"name", "price"}
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_values_list_flat(sample_products):
    """Testa retorno de lista de valores."""
    session = await get_session()
    
    try:
        names = await TestProduct.objects.using(session)\
            .filter(category="electronics")\
            .values_list("name", flat=True)
        
        assert len(names) == 3
        assert "Laptop" in names
        assert "Mouse" in names
        assert "Keyboard" in names
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_chained_filters(sample_products):
    """Testa filtros encadeados."""
    session = await get_session()
    
    try:
        products = await TestProduct.objects.using(session)\
            .filter(category="electronics")\
            .filter(is_available=True)\
            .filter(price__lt=500)\
            .all()
        
        assert len(products) == 2  # Mouse, Laptop (Keyboard is not available)
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_update_queryset(sample_products):
    """Testa update em queryset."""
    session = await get_session()
    
    try:
        count = await TestProduct.objects.using(session)\
            .filter(category="electronics")\
            .update(is_available=False)
        
        assert count == 3
        
        available = await TestProduct.objects.using(session)\
            .filter(category="electronics", is_available=True)\
            .count()
        
        assert available == 0
        
        await session.commit()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_delete_queryset(sample_products):
    """Testa delete em queryset."""
    session = await get_session()
    
    try:
        initial_count = await TestProduct.objects.using(session).count()
        
        deleted = await TestProduct.objects.using(session)\
            .filter(category="furniture")\
            .delete()
        
        assert deleted == 2
        
        final_count = await TestProduct.objects.using(session).count()
        assert final_count == initial_count - 2
        
        await session.commit()
    finally:
        await session.close()
