"""
SQL Data Importer — API endpoints do admin panel.

Endpoints:
- POST /api/importer/upload   — upload e parse do arquivo SQL
- GET  /api/importer/models   — models registrados e seus fields
- POST /api/importer/preview  — preview de 10 linhas transformadas
- POST /api/importer/execute  — execução em batch com SSE streaming
- DELETE /api/importer/cancel/{upload_id} — cancela e limpa sessão
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncGenerator, TYPE_CHECKING

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from strider.admin.permissions import check_admin_access
from strider.admin.sql_parser import (
    ParseResult,
    TableSchema,
    ColumnSchema,
    parse_sql_file,
    stream_table_rows,
    preview_table_rows,
    transform_row,
    TRANSFORMS,
)

if TYPE_CHECKING:
    from strider.admin.site import AdminSite

logger = logging.getLogger("strider.admin.importer")

# ---------------------------------------------------------------------------
# In-memory session store (schema only — rows are on disk)
# ---------------------------------------------------------------------------

_sessions: dict[str, _ImportSession] = {}
_SESSION_TTL = timedelta(hours=2)


class _ImportSession:
    __slots__ = ("upload_id", "parse_result", "created_at", "filename")

    def __init__(self, upload_id: str, parse_result: ParseResult, filename: str) -> None:
        self.upload_id = upload_id
        self.parse_result = parse_result
        self.created_at = datetime.utcnow()
        self.filename = filename


def _get_session(upload_id: str) -> _ImportSession:
    sess = _sessions.get(upload_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Import session not found or expired")
    if datetime.utcnow() - sess.created_at > _SESSION_TTL:
        _cleanup_session(upload_id)
        raise HTTPException(status_code=410, detail="Import session expired")
    return sess


def _cleanup_session(upload_id: str) -> None:
    sess = _sessions.pop(upload_id, None)
    if sess:
        try:
            Path(sess.parse_result.data_file).unlink(missing_ok=True)
        except Exception:
            pass


def _purge_expired_sessions() -> None:
    now = datetime.utcnow()
    expired = [
        uid for uid, s in list(_sessions.items())
        if now - s.created_at > _SESSION_TTL
    ]
    for uid in expired:
        _cleanup_session(uid)


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class ColumnMapping(BaseModel):
    source: str
    target: str | None = None
    transform: str | None = "passthrough"
    default: Any = None


class TableMapping(BaseModel):
    source_table: str
    target_model: str | None = None
    enabled: bool = True
    columns: list[ColumnMapping] = []


class PreviewRequest(BaseModel):
    upload_id: str
    source_table: str
    columns: list[ColumnMapping] = []


class ExecuteRequest(BaseModel):
    upload_id: str
    batch_size: int = 500
    on_conflict: str = "skip"      # skip | fail
    stop_on_error: bool = False
    tables: list[TableMapping] = []


# ---------------------------------------------------------------------------
# Helper: introspect model fields
# ---------------------------------------------------------------------------

def _get_model_fields(model_class: type) -> list[dict[str, Any]]:
    """Extrai fields de um SQLAlchemy model para exibir no mapeamento."""
    fields = []
    try:
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(model_class)
        for col in mapper.columns:
            fields.append({
                "name": col.key,
                "type": str(col.type.__class__.__name__).lower(),
                "nullable": col.nullable,
                "primary_key": col.primary_key,
            })
    except Exception as e:
        logger.debug("Could not introspect model %s: %s", model_class, e)
    return fields


def _table_schema_to_dict(schema: TableSchema) -> dict[str, Any]:
    """Serializa TableSchema para JSON."""
    return {
        "name": schema.name,
        "row_count": schema.row_count,
        "columns": [
            {
                "name": c.name,
                "sql_type": c.sql_type,
                "python_type": c.python_type,
                "nullable": c.nullable,
                "default": c.default,
                "is_pk": c.is_pk,
                "is_unique": c.is_unique,
                "is_json": c.is_json,
                "is_fk": c.is_fk,
                "enum_values": c.enum_values,
            }
            for c in schema.columns
        ],
    }


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def create_importer_router(site: "AdminSite") -> APIRouter:
    router = APIRouter(prefix="/api/importer", tags=["admin-importer"])

    # =========================================================================
    # POST /api/importer/upload
    # =========================================================================

    @router.post("/upload")
    async def upload_sql(
        request: Request,
        file: UploadFile = File(...),
        _user: Any = Depends(check_admin_access),
    ) -> JSONResponse:
        """
        Recebe o arquivo SQL, faz parse streaming, armazena schema em sessão
        e dados em arquivo temporário. Retorna upload_id + schema das tabelas.
        """
        _purge_expired_sessions()

        if not file.filename or not file.filename.lower().endswith(".sql"):
            raise HTTPException(
                status_code=400,
                detail="Apenas arquivos .sql são aceitos",
            )

        content_bytes = await file.read()
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = content_bytes.decode("latin-1")
            except UnicodeDecodeError:
                raise HTTPException(status_code=400, detail="Encoding do arquivo não suportado")

        if len(content) > 512 * 1024 * 1024:  # 512 MB limit
            raise HTTPException(status_code=413, detail="Arquivo muito grande (máx 512 MB)")

        try:
            parse_result = parse_sql_file(content)
        except Exception as e:
            logger.exception("Error parsing SQL file")
            raise HTTPException(status_code=422, detail=f"Erro ao parsear SQL: {e}")

        upload_id = str(uuid.uuid4())
        sess = _ImportSession(
            upload_id=upload_id,
            parse_result=parse_result,
            filename=file.filename,
        )
        _sessions[upload_id] = sess

        tables_data = {
            name: _table_schema_to_dict(schema)
            for name, schema in parse_result.tables.items()
        }

        return JSONResponse({
            "upload_id": upload_id,
            "filename": file.filename,
            "file_size": len(content_bytes),
            "tables": tables_data,
            "row_counts": parse_result.row_counts,
            "parse_errors": parse_result.errors[:50],
            "total_rows": sum(parse_result.row_counts.values()),
        })

    # =========================================================================
    # GET /api/importer/models
    # =========================================================================

    @router.get("/models")
    async def list_models(
        request: Request,
        _user: Any = Depends(check_admin_access),
    ) -> JSONResponse:
        """
        Lista os models registrados no admin e seus fields.
        Usado para popular os dropdowns de mapeamento.
        """
        result = []
        for model_class, admin_instance in site.get_registry().items():
            app_label = admin_instance._app_label
            model_name = admin_instance._model_name
            fields = _get_model_fields(model_class)
            result.append({
                "key": f"{app_label}.{model_name}",
                "app_label": app_label,
                "model_name": model_name,
                "display_name": admin_instance.display_name or model_name,
                "table_name": getattr(model_class, "__tablename__", None),
                "fields": fields,
            })

        result.sort(key=lambda x: x["key"])
        return JSONResponse({"models": result})

    # =========================================================================
    # POST /api/importer/preview
    # =========================================================================

    @router.post("/preview")
    async def preview(
        request: Request,
        body: PreviewRequest,
        _user: Any = Depends(check_admin_access),
    ) -> JSONResponse:
        """
        Retorna até 10 linhas de uma tabela após aplicar as transformações
        de mapeamento. Útil para validar antes de executar.
        """
        sess = _get_session(body.upload_id)
        table_name = body.source_table

        if table_name not in sess.parse_result.tables:
            raise HTTPException(status_code=404, detail=f"Tabela '{table_name}' não encontrada")

        raw_rows = preview_table_rows(sess.parse_result.data_file, table_name, limit=10)

        column_mappings = [m.model_dump() for m in body.columns]
        preview_rows = []
        for raw in raw_rows:
            if column_mappings:
                transformed, errs = transform_row(raw, column_mappings)
                preview_rows.append({"data": transformed, "errors": errs})
            else:
                preview_rows.append({"data": raw, "errors": []})

        schema = sess.parse_result.tables[table_name]
        return JSONResponse({
            "table": table_name,
            "columns_source": schema.column_names,
            "row_count": schema.row_count,
            "rows": preview_rows,
        })

    # =========================================================================
    # POST /api/importer/execute (SSE streaming)
    # =========================================================================

    @router.post("/execute")
    async def execute(
        request: Request,
        body: ExecuteRequest,
        _user: Any = Depends(check_admin_access),
    ) -> StreamingResponse:
        """
        Executa a importação com SSE streaming para progresso em tempo real.

        Eventos SSE emitidos:
        - {"type": "start",    "table": "...", "total": N}
        - {"type": "progress", "table": "...", "inserted": N, "skipped": N, "errors": N, "batch": N}
        - {"type": "error",    "table": "...", "message": "...", "row": N}
        - {"type": "done",     "table": "...", "inserted": N, "skipped": N, "errors": N}
        - {"type": "complete", "summary": {...}}
        - {"type": "fatal",    "message": "..."}
        """
        sess = _get_session(body.upload_id)

        async def event_stream() -> AsyncGenerator[str, None]:
            summary: dict[str, Any] = {}
            total_inserted = 0
            total_skipped = 0
            total_errors = 0

            for table_mapping in body.tables:
                if not table_mapping.enabled:
                    continue

                source_table = table_mapping.source_table
                target_model_key = table_mapping.target_model

                if source_table not in sess.parse_result.tables:
                    yield _sse_event({
                        "type": "error",
                        "table": source_table,
                        "message": f"Tabela '{source_table}' não encontrada no arquivo SQL",
                        "row": 0,
                    })
                    continue

                if not target_model_key:
                    yield _sse_event({
                        "type": "error",
                        "table": source_table,
                        "message": "Nenhum model de destino selecionado",
                        "row": 0,
                    })
                    continue

                # Resolve target SQLAlchemy Table
                target_sa_table = _resolve_model_table(site, target_model_key)
                if target_sa_table is None:
                    yield _sse_event({
                        "type": "error",
                        "table": source_table,
                        "message": f"Model '{target_model_key}' não encontrado ou sem __tablename__",
                        "row": 0,
                    })
                    continue

                total_rows = sess.parse_result.tables[source_table].row_count
                yield _sse_event({
                    "type": "start",
                    "table": source_table,
                    "target": target_model_key,
                    "total": total_rows,
                })
                await asyncio.sleep(0)

                column_mappings = [m.model_dump() for m in table_mapping.columns]
                on_conflict = body.on_conflict
                batch_size = max(1, min(body.batch_size, 5000))

                inserted = 0
                skipped = 0
                errors = 0
                batch_num = 0
                current_batch: list[dict[str, Any]] = []
                row_index = 0

                try:
                    for raw_row in stream_table_rows(sess.parse_result.data_file, source_table):
                        row_index += 1

                        if column_mappings:
                            transformed, row_errs = transform_row(raw_row, column_mappings)
                        else:
                            transformed = raw_row
                            row_errs = []

                        if row_errs:
                            errors += 1
                            yield _sse_event({
                                "type": "error",
                                "table": source_table,
                                "message": "; ".join(row_errs),
                                "row": row_index,
                            })
                            if body.stop_on_error:
                                break
                            continue

                        current_batch.append(transformed)

                        if len(current_batch) >= batch_size:
                            batch_num += 1
                            batch_ins, batch_skip, batch_err, batch_err_msg = await _insert_batch(
                                target_sa_table,
                                current_batch,
                                on_conflict,
                            )
                            inserted += batch_ins
                            skipped += batch_skip
                            errors += batch_err
                            current_batch = []

                            if batch_err_msg and batch_err > 0:
                                yield _sse_event({
                                    "type": "db_error",
                                    "table": source_table,
                                    "message": batch_err_msg,
                                    "count": batch_err,
                                    "batch": batch_num,
                                })
                                if body.stop_on_error:
                                    break

                            yield _sse_event({
                                "type": "progress",
                                "table": source_table,
                                "inserted": inserted,
                                "skipped": skipped,
                                "errors": errors,
                                "batch": batch_num,
                                "row": row_index,
                                "total": total_rows,
                            })
                            await asyncio.sleep(0)

                    # Flush remaining
                    if current_batch:
                        batch_num += 1
                        batch_ins, batch_skip, batch_err, batch_err_msg = await _insert_batch(
                            target_sa_table,
                            current_batch,
                            on_conflict,
                        )
                        inserted += batch_ins
                        skipped += batch_skip
                        errors += batch_err
                        if batch_err_msg and batch_err > 0:
                            yield _sse_event({
                                "type": "db_error",
                                "table": source_table,
                                "message": batch_err_msg,
                                "count": batch_err,
                                "batch": batch_num,
                            })

                except Exception as e:
                    logger.exception("Fatal error importing table %s", source_table)
                    yield _sse_event({
                        "type": "fatal",
                        "table": source_table,
                        "message": f"Erro fatal: {e}",
                    })
                    if body.stop_on_error:
                        return

                total_inserted += inserted
                total_skipped += skipped
                total_errors += errors
                summary[source_table] = {
                    "inserted": inserted,
                    "skipped": skipped,
                    "errors": errors,
                }

                yield _sse_event({
                    "type": "done",
                    "table": source_table,
                    "inserted": inserted,
                    "skipped": skipped,
                    "errors": errors,
                })
                await asyncio.sleep(0)

            yield _sse_event({
                "type": "complete",
                "total_inserted": total_inserted,
                "total_skipped": total_skipped,
                "total_errors": total_errors,
                "summary": summary,
            })

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    # =========================================================================
    # DELETE /api/importer/cancel/{upload_id}
    # =========================================================================

    @router.delete("/cancel/{upload_id}")
    async def cancel(
        request: Request,
        upload_id: str,
        _user: Any = Depends(check_admin_access),
    ) -> JSONResponse:
        """Cancela e limpa a sessão de importação."""
        _cleanup_session(upload_id)
        return JSONResponse({"status": "cancelled", "upload_id": upload_id})

    # =========================================================================
    # GET /api/importer/transforms
    # =========================================================================

    @router.get("/transforms")
    async def list_transforms(
        request: Request,
        _user: Any = Depends(check_admin_access),
    ) -> JSONResponse:
        """Lista as transformações disponíveis."""
        transforms = [
            {"id": "passthrough",   "label": "Passthrough (sem mudança)"},
            {"id": "to_bool",       "label": "→ Boolean (0/1, false/true)"},
            {"id": "to_int",        "label": "→ Inteiro"},
            {"id": "to_float",      "label": "→ Float / Decimal"},
            {"id": "to_datetime",   "label": "→ Datetime (ISO)"},
            {"id": "json_parse",    "label": "→ JSON (parse string)"},
            {"id": "uuid_str",      "label": "→ UUID string"},
            {"id": "strip",         "label": "Strip (remover espaços)"},
            {"id": "lower",         "label": "→ Lowercase"},
            {"id": "upper",         "label": "→ Uppercase"},
            {"id": "null_if_empty", "label": "NULL se vazio"},
            {"id": "str",           "label": "→ String (forçar)"},
        ]
        return JSONResponse({"transforms": transforms})

    return router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse_event(data: dict[str, Any]) -> str:
    """Formata um evento SSE."""
    return f"data: {json.dumps(data, default=str)}\n\n"


def _resolve_model_table(site: "AdminSite", model_key: str) -> Any:
    """
    Resolve um model_key (app_label.model_name) para um SQLAlchemy Table object.
    """
    parts = model_key.split(".", 1)
    if len(parts) != 2:
        return None
    app_label, model_name = parts
    result = site.get_model_by_name(app_label, model_name)
    if not result:
        return None
    model_class, _ = result
    try:
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(model_class)
        return mapper.local_table
    except Exception:
        return None


def _get_dialect_name() -> str:
    """Detecta o dialeto do banco de forma segura."""
    try:
        from strider.models import _engine  # type: ignore[attr-defined]
        if _engine is not None:
            return _engine.dialect.name
    except Exception:
        pass
    return "postgresql"


def _build_insert_stmt(sa_table: Any, batch: list[dict[str, Any]], on_conflict: str) -> Any:
    """Constrói a statement de insert de acordo com o dialeto e estratégia de conflito."""
    from sqlalchemy import insert

    if on_conflict != "skip":
        return insert(sa_table).values(batch)

    dialect = _get_dialect_name()
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        return pg_insert(sa_table).values(batch).on_conflict_do_nothing()
    elif dialect in ("mysql", "mariadb"):
        return insert(sa_table).prefix_with("IGNORE").values(batch)
    else:
        # SQLite and others
        return insert(sa_table).prefix_with("OR IGNORE").values(batch)


def _coerce_value_for_sa_type(val: Any, type_name: str) -> Any:
    """
    Converte um valor para o tipo Python correto baseado no tipo SQLAlchemy.
    Evita erros de driver (ex: asyncpg rejeita string '0'/'1' para BOOLEAN).
    """
    if val is None:
        return None

    t = type_name.upper()

    if "BOOL" in t:
        if isinstance(val, bool):
            return val
        if isinstance(val, int):
            return bool(val)
        if isinstance(val, str):
            stripped = val.strip()
            if not stripped or stripped.upper() in ("NULL", "NONE"):
                return None
            return stripped not in ("0", "false", "False", "no", "No")
        return bool(val)

    if "INT" in t:
        if isinstance(val, int):
            return val
        try:
            return int(float(str(val)))
        except (ValueError, TypeError):
            return None

    if any(x in t for x in ("FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "REAL")):
        if isinstance(val, (int, float)):
            return float(val)
        try:
            return float(str(val))
        except (ValueError, TypeError):
            return None

    if "UUID" in t:
        return str(val) if val else None

    if "DATETIME" in t or "TIMESTAMP" in t:
        # Keep as string — SQLAlchemy handles ISO string → datetime
        if isinstance(val, str) and val.strip():
            return val.strip()
        return None

    return val


def _coerce_batch_for_table(
    batch: list[dict[str, Any]],
    sa_table: Any,
) -> list[dict[str, Any]]:
    """
    Auto-coerce todos os valores do batch para os tipos Python corretos,
    baseado nos tipos das colunas da tabela SQLAlchemy alvo.
    Isso evita erros de driver como 'Not a boolean value: "0"'.
    """
    col_types: dict[str, str] = {}
    try:
        for col in sa_table.columns:
            col_types[col.name] = type(col.type).__name__
    except Exception:
        return batch  # se não conseguir introspectar, retorna sem coerção

    if not col_types:
        return batch

    result = []
    for row in batch:
        coerced: dict[str, Any] = {}
        for key, val in row.items():
            type_name = col_types.get(key, "")
            coerced[key] = _coerce_value_for_sa_type(val, type_name) if type_name else val
        result.append(coerced)
    return result


async def _insert_batch(
    sa_table: Any,
    batch: list[dict[str, Any]],
    on_conflict: str,
) -> tuple[int, int, int, str | None]:
    """
    Insere um batch de linhas usando SQLAlchemy Core (sem ORM).
    Retorna (inserted, skipped, errors, first_error_message).

    Auto-coerce tipos antes de inserir para evitar erros de driver.
    Usa insert direto por dialeto:
    - PostgreSQL: ON CONFLICT DO NOTHING
    - MySQL: INSERT IGNORE
    - SQLite: INSERT OR IGNORE
    """
    if not batch:
        return 0, 0, 0, None

    # Auto-coerce tipos para evitar erros de driver (ex: bool, int, float)
    coerced = _coerce_batch_for_table(batch, sa_table)

    try:
        from strider.models import get_session

        db = await get_session()
        async with db:
            async with db.begin():
                stmt = _build_insert_stmt(sa_table, coerced, on_conflict)
                result = await db.execute(stmt)
                inserted = result.rowcount if result.rowcount >= 0 else len(coerced)
                return inserted, 0, 0, None

    except Exception as e:
        err_msg = _humanize_db_error(e)
        logger.warning("Batch insert error (falling back to row-by-row): %s", e)
        ins, skip, errs, first_err = await _insert_row_by_row(sa_table, coerced, on_conflict)
        return ins, skip, errs, first_err or err_msg


async def _insert_row_by_row(
    sa_table: Any,
    batch: list[dict[str, Any]],
    on_conflict: str,
) -> tuple[int, int, int, str | None]:
    """Fallback: insere linha por linha quando o batch falha. Retorna primeiro erro."""
    from strider.models import get_session

    inserted = 0
    skipped = 0
    errors = 0
    first_error: str | None = None

    for row in batch:
        try:
            db = await get_session()
            async with db:
                async with db.begin():
                    stmt = _build_insert_stmt(sa_table, [row], on_conflict)
                    result = await db.execute(stmt)
                    if result.rowcount == 0:
                        skipped += 1
                    else:
                        inserted += 1
        except Exception as e:
            logger.debug("Row insert error: %s", e)
            errors += 1
            if first_error is None:
                first_error = _humanize_db_error(e)

    return inserted, skipped, errors, first_error


def _humanize_db_error(exc: Exception) -> str:
    """Converte uma exceção de banco em mensagem legível para o usuário."""
    msg = str(exc)

    # asyncpg boolean
    if "Not a boolean value" in msg:
        import re
        m = re.search(r"Not a boolean value: '(.+?)'", msg)
        val = m.group(1) if m else "?"
        return (
            f"Tipo incompatível: valor '{val}' não é um boolean válido. "
            "Use a transformação 'to_bool' para campos BOOLEAN."
        )
    # asyncpg UUID
    if "badly formed hexadecimal UUID" in msg or "invalid input syntax for type uuid" in msg.lower():
        return (
            "Tipo incompatível: valor não é um UUID válido. "
            "Verifique o campo ou use a transformação 'uuid_str'."
        )
    # asyncpg timestamp
    if "invalid input syntax for type timestamp" in msg.lower():
        return (
            "Tipo incompatível: data/hora em formato inválido. "
            "Use a transformação 'to_datetime'."
        )
    # unique constraint
    if "unique constraint" in msg.lower() or "duplicate key" in msg.lower():
        return (
            "Violação de unique constraint: registro duplicado. "
            "Configure 'Conflito → Ignorar' ou remova dados existentes."
        )
    # foreign key
    if "foreign key constraint" in msg.lower():
        return (
            "Violação de chave estrangeira: a linha referencia um ID que não existe. "
            "Importe as tabelas relacionadas primeiro."
        )
    # not null
    if "null value in column" in msg.lower() or "not null constraint" in msg.lower():
        import re
        m = re.search(r'column "([^"]+)"', msg)
        col = m.group(1) if m else "?"
        return f"Campo obrigatório vazio: coluna '{col}' não pode ser NULL. Configure um valor padrão."

    # Generic — truncate at 200 chars
    return msg[:200] if len(msg) > 200 else msg
