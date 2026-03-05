"""
Configurações de teste compartilhadas.
"""

import pytest
import pytest_asyncio

from strider.models import init_database, create_tables, drop_tables, get_session


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Fornece uma sessão de banco de dados para testes."""
    # Usa banco em memória para testes
    await init_database("sqlite+aiosqlite:///:memory:", echo=False)
    await create_tables()
    
    session = await get_session()
    try:
        yield session
        await session.commit()
    finally:
        await session.close()
        await drop_tables()
