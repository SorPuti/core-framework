"""Testes do módulo Citus (probe, connect_args, URLs)."""

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from strider.citus import (
    CitusStatus,
    asyncpg_connect_args_from_settings,
    is_postgres_async_url,
    merge_asyncpg_connect_args,
    probe_citus_on_engine,
    run_citus_startup_checks,
)


def test_is_postgres_async_url():
    assert is_postgres_async_url("postgresql+asyncpg://localhost/db")
    assert is_postgres_async_url("postgres+asyncpg://localhost/db")
    assert not is_postgres_async_url("sqlite+aiosqlite:///:memory:")


def test_asyncpg_connect_args_from_settings_empty():
    class S:
        database_citus_application_name = None

    assert asyncpg_connect_args_from_settings(S()) == {}


def test_asyncpg_connect_args_from_settings_name():
    class S:
        database_citus_application_name = "my-app"

    assert asyncpg_connect_args_from_settings(S()) == {
        "server_settings": {"application_name": "my-app"}
    }


def test_merge_asyncpg_connect_args():
    user = {"server_settings": {"jit": "off"}}
    from_settings = {"server_settings": {"application_name": "svc"}}
    out = merge_asyncpg_connect_args(user, from_settings)
    assert out is not None
    assert out["server_settings"]["jit"] == "off"
    assert out["server_settings"]["application_name"] == "svc"


@pytest.mark.asyncio
async def test_probe_citus_sqlite_returns_absent():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        st = await probe_citus_on_engine(engine)
        assert isinstance(st, CitusStatus)
        assert st.available is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_citus_startup_checks_sqlite_skips():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        r = await run_citus_startup_checks(
            engine=engine,
            database_url="sqlite+aiosqlite:///:memory:",
            probe=True,
            require=False,
        )
        assert r is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_citus_require_non_postgres_raises():
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    with pytest.raises(RuntimeError, match="database_citus_require"):
        await run_citus_startup_checks(
            engine=mock_engine,
            database_url="sqlite+aiosqlite:///:memory:",
            probe=False,
            require=True,
        )
