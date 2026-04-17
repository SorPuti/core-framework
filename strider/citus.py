"""
Suporte operacional a clusters PostgreSQL com extensão Citus.

Citus distribui dados e consultas em vários nós mantendo PostgreSQL como
motor ([visão geral](https://www.citusdata.com/overview/)). O Strider continua
usando SQLAlchemy 2 async + asyncpg: o *coordinator* Citus é um servidor
PostgreSQL comum; não é necessário driver alternativo.

Este módulo oferece:

- ``asyncpg`` ``connect_args`` opcionais (ex.: ``application_name`` para
  observabilidade em cluster).
- *Probe* leve na subida (extensão ``citus`` instalada e versão).
- Modo estrito opcional (falha se PostgreSQL sem Citus quando exigido).

Modelagem de shards (coluna de distribuição, *schema-based sharding*, etc.)
permanece no DDL/migrações e na equipe de dados; o framework não impõe
colunas mágicas além das que o app já define (ex.: *multi-tenant* via
``tenancy_field`` em ``Settings`` alinhado a uma chave de distribuição).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("strider.citus")

CITUS_OVERVIEW_URL = "https://www.citusdata.com/overview/"


@dataclass(frozen=True, slots=True)
class CitusStatus:
    """Resultado do probe da extensão ``citus`` no banco atual."""

    available: bool
    """True se ``pg_extension`` contém ``citus``."""
    extension_version: str | None = None
    """Valor de ``extversion`` da extensão, quando presente."""


def is_postgres_async_url(database_url: str) -> bool:
    """True para URLs async de PostgreSQL (inclui Citus coordinator)."""
    u = database_url.strip().lower()
    return u.startswith("postgresql+") or u.startswith("postgres+")


def merge_asyncpg_connect_args(
    user: dict[str, Any] | None,
    from_settings: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Une ``connect_args`` passados pelo app com os derivados de Settings
    (ex.: ``application_name`` Citus), sem sobrescrever chaves arbitrárias
    do usuário além de ``server_settings`` (merge superficial desse dict).
    """
    if not user and not from_settings:
        return None
    out: dict[str, Any] = dict(user or {})
    if not from_settings:
        return out
    su = dict(out.get("server_settings") or {})
    su.update(from_settings.get("server_settings") or {})
    out.update(from_settings)
    if su:
        out["server_settings"] = su
    return out


def asyncpg_connect_args_from_settings(settings: Any) -> dict[str, Any]:
    """
    Monta ``connect_args`` para ``create_async_engine`` (driver asyncpg).

    Usa ``server_settings.application_name`` quando
    ``database_citus_application_name`` está definido (útil em clusters Citus
    para correlação em ``pg_stat_activity`` / ferramentas de *tenant
    monitoring* descritas na documentação Citus).
    """
    name = getattr(settings, "database_citus_application_name", None)
    if not name:
        return {}
    return {"server_settings": {"application_name": str(name)[:64]}}


async def probe_citus_on_engine(engine: AsyncEngine) -> CitusStatus:
    """
    Consulta ``pg_extension`` por ``citus``.

    Em falha (permissão, não-PostgreSQL, conexão), retorna ``available=False``
    e registra em log — não levanta exceção (use ``database_citus_require``
    na camada de inicialização para falhar de propósito).
    """
    try:
        dialect = engine.dialect.name
    except Exception:
        return CitusStatus(False, None)

    if dialect != "postgresql":
        return CitusStatus(False, None)

    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT extversion FROM pg_extension "
                    "WHERE extname = 'citus' LIMIT 1"
                )
            )
            row = result.first()
            if row is None:
                return CitusStatus(False, None)
            ver = row[0]
            return CitusStatus(True, str(ver) if ver is not None else None)
    except Exception as e:
        logger.warning("Citus probe skipped or failed: %s", e)
        return CitusStatus(False, None)


def _mask_host(url: str) -> str:
    try:
        u = make_url(url)
        return f"{u.drivername}://{u.host}:{u.port}/{u.database}"
    except Exception:
        return "<invalid-url>"


async def run_citus_startup_checks(
    *,
    engine: AsyncEngine,
    database_url: str,
    probe: bool,
    require: bool,
) -> CitusStatus | None:
    """
    Executa probe e aplica política ``require``.

    Retorna ``CitusStatus`` se ``probe`` ou ``require``; ``None`` se SQLite
    ou URL não-Postgres e nada foi pedido.
    """
    if not is_postgres_async_url(database_url):
        if require:
            raise RuntimeError(
                "database_citus_require=True exige URL PostgreSQL "
                "(postgresql+asyncpg://...). Citus roda como extensão em Postgres."
            )
        return None

    if not probe and not require:
        return None

    status = await probe_citus_on_engine(engine)

    if status.available and status.extension_version:
        logger.info(
            "Citus extension detected (version %s) on %s",
            status.extension_version,
            _mask_host(database_url),
        )
    elif probe and not status.available:
        logger.info(
            "Citus extension not present on %s (plain PostgreSQL or extension not created). "
            "See %s",
            _mask_host(database_url),
            CITUS_OVERVIEW_URL,
        )

    if require and not status.available:
        raise RuntimeError(
            "database_citus_require=True but Citus extension is not installed "
            f"on {_mask_host(database_url)}. "
            "Install/create extension citus on the coordinator (see Citus docs). "
            f"Overview: {CITUS_OVERVIEW_URL}"
        )

    return status
