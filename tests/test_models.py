"""
Testes para o sistema de Models.
"""

import pytest
from datetime import datetime

from sqlalchemy.orm import Mapped

from strider.models import Model, Field, init_database, create_tables, drop_tables, get_session


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


# =============================================================================
# Testes para campos Struct (StructDescriptor auto-creation)
# =============================================================================

from strider.schema import StructSchema, StringField, IntegerField, BooleanField


class RuntimeSettings(StructSchema):
    """Schema de teste para runtime_overrides."""
    timeout = IntegerField(default=30)
    retries = IntegerField(default=3)
    mode = StringField(default="standard", choices=["standard", "aggressive"])


class TestSession(Model):
    """Model com campo struct para testes."""

    __tablename__ = "test_sessions"

    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=100)
    # Este campo deve automaticamente retornar uma StructSchema, nunca um dict
    runtime_overrides: Mapped[RuntimeSettings] = Field.struct(RuntimeSettings)


@pytest.mark.asyncio
async def test_struct_field_returns_struct_instance(setup_db):
    """
    Testa que campos struct automaticamente retornam StructSchema.

    Isso garante que não ocorra o erro:
    AttributeError: 'dict' object has no attribute 'to_dict'
    """
    session = await get_session()

    try:
        # Cria sessão com valores padrão
        test_session = await TestSession.objects.using(session).create(
            name="Test Session",
        )

        # O campo runtime_overrides deve retornar uma StructSchema, nunca um dict
        assert isinstance(test_session.runtime_overrides, RuntimeSettings), \
            f"Expected RuntimeSettings, got {type(test_session.runtime_overrides)}"

        # Deve ter o método to_dict()
        assert hasattr(test_session.runtime_overrides, 'to_dict'), \
            "Struct instance should have to_dict() method"

        # Valores padrão devem estar presentes
        assert test_session.runtime_overrides.timeout == 30
        assert test_session.runtime_overrides.retries == 3
        assert test_session.runtime_overrides.mode == "standard"

        # to_dict() deve funcionar corretamente
        overrides_dict = test_session.runtime_overrides.to_dict()
        assert isinstance(overrides_dict, dict)
        assert overrides_dict["timeout"] == 30
        assert overrides_dict["retries"] == 3
        assert overrides_dict["mode"] == "standard"

        await session.commit()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_struct_field_with_custom_values(setup_db):
    """Testa campo struct com valores customizados."""
    session = await get_session()

    try:
        # Cria com valores customizados via dict
        test_session = TestSession(name="Custom Session")
        test_session.runtime_overrides = {"timeout": 60, "mode": "aggressive"}
        session.add(test_session)
        await session.flush()

        # Recarrega do banco
        await session.refresh(test_session)

        # Deve retornar StructSchema, não dict
        assert isinstance(test_session.runtime_overrides, RuntimeSettings)

        # Valores customizados devem estar presentes
        assert test_session.runtime_overrides.timeout == 60
        assert test_session.runtime_overrides.mode == "aggressive"
        # Valor não especificado usa default
        assert test_session.runtime_overrides.retries == 3

        # to_dict() deve funcionar
        data = test_session.runtime_overrides.to_dict()
        assert data["timeout"] == 60
        assert data["mode"] == "aggressive"

        await session.commit()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_struct_field_partial_update(setup_db):
    """Testa atualização parcial do campo struct."""
    session = await get_session()

    try:
        # Cria sessão
        test_session = await TestSession.objects.using(session).create(
            name="Update Test",
            runtime_overrides={"timeout": 45, "retries": 5}
        )

        # Atualiza parcialmente
        test_session.runtime_overrides = {"mode": "aggressive"}
        await session.flush()
        await session.refresh(test_session)

        # Valores devem estar mergeados
        assert test_session.runtime_overrides.timeout == 45  # Mantido
        assert test_session.runtime_overrides.retries == 5    # Mantido
        assert test_session.runtime_overrides.mode == "aggressive"  # Atualizado

        await session.commit()
    finally:
        await session.close()


# =============================================================================
# Teste para StructSchema em Pydantic OutputSchema
# =============================================================================

from strider import OutputSchema


class AddressStruct(StructSchema):
    """Struct de endereço para testes Pydantic."""
    street = StringField(default="")
    city = StringField(default="")
    zip_code = StringField(default="")


class UserWithAddressOutput(OutputSchema):
    """OutputSchema que usa StructSchema diretamente."""
    id: int
    name: str
    address: AddressStruct


@pytest.mark.asyncio
async def test_struct_schema_in_pydantic_output():
    """
    Testa que StructSchema pode ser usado diretamente em OutputSchema.

    Isso garante que __get_pydantic_core_schema__ funciona corretamente
    para serialização em responses da API.
    """
    # Criar instância com StructSchema
    output = UserWithAddressOutput(
        id=1,
        name="John Doe",
        address=AddressStruct(street="123 Main St", city="NYC", zip_code="10001")
    )

    # Verificar que o StructSchema está presente
    assert isinstance(output.address, AddressStruct)
    assert output.address.street == "123 Main St"
    assert output.address.city == "NYC"

    # Verificar serialização para JSON (o que realmente importa para a API)
    from pydantic import TypeAdapter
    ta = TypeAdapter(UserWithAddressOutput)
    json_bytes = ta.dump_json(output)
    json_str = json_bytes.decode('utf-8')

    # Verificar que o JSON contém os valores corretos
    assert '"street":"123 Main St"' in json_str
    assert '"city":"NYC"' in json_str
    assert '"zip_code":"10001"' in json_str
    assert '"id":1' in json_str
    assert '"name":"John Doe"' in json_str

    # Verificar que pode fazer parse de JSON com dict
    json_input = '{"id":2,"name":"Jane","address":{"street":"456 Oak","city":"LA","zip_code":"90001"}}'
    parsed = ta.validate_json(json_input)
    assert isinstance(parsed.address, AddressStruct)
    assert parsed.address.street == "456 Oak"


# =============================================================================
# Teste para ListField com NestedField
# =============================================================================

from strider.schema import ListField, NestedField


class FilterItem(StructSchema):
    """Item de filtro para testes de lista."""
    id = StringField(default="")
    name = StringField(default="")
    enabled = BooleanField(default=True)


class ConfigWithFilters(StructSchema):
    """Schema com lista de filtros."""
    filters = ListField(
        item_field=NestedField(FilterItem),
        default=[]
    )


class TestConfigModel(Model):
    """Model com campo struct contendo lista de nested schemas."""

    __tablename__ = "test_config_models"

    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=100)
    config: Mapped[ConfigWithFilters] = Field.struct(ConfigWithFilters)


@pytest.mark.asyncio
async def test_list_field_with_nested_serialization(setup_db):
    """
    Testa que ListField com NestedField serializa corretamente para dict.

    Isso garante que itens de lista sejam convertidos de StructSchema para dict
    quando serializados para o banco (JSON).
    """
    session = await get_session()

    try:
        # Cria modelo com lista de filtros
        test_config = await TestConfigModel.objects.using(session).create(
            name="Test Config",
            config={
                "filters": [
                    {"id": "filter-1", "name": "Filter One", "enabled": True},
                    {"id": "filter-2", "name": "Filter Two", "enabled": False},
                ]
            }
        )

        # O campo config deve retornar uma instância ConfigWithFilters
        assert isinstance(test_config.config, ConfigWithFilters)

        # A lista de filtros deve conter instâncias FilterItem
        assert len(test_config.config.filters) == 2
        assert isinstance(test_config.config.filters[0], FilterItem)
        assert isinstance(test_config.config.filters[1], FilterItem)

        # Verifica valores
        assert test_config.config.filters[0].id == "filter-1"
        assert test_config.config.filters[0].name == "Filter One"
        assert test_config.config.filters[0].enabled is True

        assert test_config.config.filters[1].id == "filter-2"
        assert test_config.config.filters[1].name == "Filter Two"
        assert test_config.config.filters[1].enabled is False

        # to_dict() deve converter tudo corretamente (incluindo itens da lista)
        config_dict = test_config.config.to_dict()
        assert isinstance(config_dict, dict)
        assert "filters" in config_dict
        assert isinstance(config_dict["filters"], list)
        assert len(config_dict["filters"]) == 2

        # Itens da lista devem ser dicts, não StructSchema
        assert isinstance(config_dict["filters"][0], dict)
        assert config_dict["filters"][0]["id"] == "filter-1"
        assert config_dict["filters"][0]["name"] == "Filter One"

        await session.commit()
    finally:
        await session.close()
