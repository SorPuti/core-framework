"""
Testes para o sistema de Models.
"""

import pytest
from datetime import datetime

from sqlalchemy.orm import Mapped

from core.models import Model, Field, init_database, create_tables, drop_tables, get_session


class TestUser(Model):
    """Model de teste."""
    
    __tablename__ = "test_users"
    
    id: Mapped[int] = Field.pk()
    email: Mapped[str] = Field.string(max_length=255, unique=True)
    name: Mapped[str] = Field.string(max_length=100)
    is_active: Mapped[bool] = Field.boolean(default=True)
    created_at: Mapped[datetime] = Field.datetime(auto_now_add=True)


@pytest.fixture
async def setup_db():
    """Setup do banco de dados para testes."""
    await init_database("sqlite+aiosqlite:///:memory:", echo=False)
    await create_tables()
    yield
    await drop_tables()


@pytest.mark.asyncio
async def test_create_model(setup_db):
    """Testa criação de model."""
    session = await get_session()
    
    try:
        user = await TestUser.objects.using(session).create(
            email="test@example.com",
            name="Test User",
        )
        
        assert user.id is not None
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.is_active is True
        
        await session.commit()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_filter_models(setup_db):
    """Testa filtro de models."""
    session = await get_session()
    
    try:
        # Cria usuários
        await TestUser.objects.using(session).create(
            email="active@example.com",
            name="Active User",
            is_active=True,
        )
        await TestUser.objects.using(session).create(
            email="inactive@example.com",
            name="Inactive User",
            is_active=False,
        )
        
        # Filtra ativos
        active_users = await TestUser.objects.using(session)\
            .filter(is_active=True)\
            .all()
        
        assert len(active_users) == 1
        assert active_users[0].email == "active@example.com"
        
        await session.commit()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_get_model(setup_db):
    """Testa busca de model único."""
    session = await get_session()
    
    try:
        created = await TestUser.objects.using(session).create(
            email="get@example.com",
            name="Get User",
        )
        
        found = await TestUser.objects.using(session).get(id=created.id)
        
        assert found.id == created.id
        assert found.email == "get@example.com"
        
        await session.commit()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_update_model(setup_db):
    """Testa atualização de model."""
    session = await get_session()
    
    try:
        user = await TestUser.objects.using(session).create(
            email="update@example.com",
            name="Original Name",
        )
        
        user.name = "Updated Name"
        await user.save(session)
        
        found = await TestUser.objects.using(session).get(id=user.id)
        assert found.name == "Updated Name"
        
        await session.commit()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_delete_model(setup_db):
    """Testa deleção de model."""
    session = await get_session()
    
    try:
        user = await TestUser.objects.using(session).create(
            email="delete@example.com",
            name="Delete User",
        )
        user_id = user.id
        
        await user.delete(session)
        
        found = await TestUser.objects.using(session).get_or_none(id=user_id)
        assert found is None
        
        await session.commit()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_count_models(setup_db):
    """Testa contagem de models."""
    session = await get_session()
    
    try:
        await TestUser.objects.using(session).create(
            email="count1@example.com",
            name="User 1",
        )
        await TestUser.objects.using(session).create(
            email="count2@example.com",
            name="User 2",
        )
        
        count = await TestUser.objects.using(session).count()
        assert count == 2
        
        await session.commit()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_exists(setup_db):
    """Testa verificação de existência."""
    session = await get_session()
    
    try:
        await TestUser.objects.using(session).create(
            email="exists@example.com",
            name="Exists User",
        )
        
        exists = await TestUser.objects.using(session).exists(email="exists@example.com")
        assert exists is True
        
        not_exists = await TestUser.objects.using(session).exists(email="notexists@example.com")
        assert not_exists is False
        
        await session.commit()
    finally:
        await session.close()
