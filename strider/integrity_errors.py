"""
Respostas seguras para erros de integridade (FK, UNIQUE, NOT NULL).

O texto bruto do driver (asyncpg/psycopg/sqlite) não deve ir para o cliente:
apenas códigos estáveis, mensagem genérica e, quando seguro, o nome da coluna.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("strider.database")

# Mensagens estáveis (API); não expor SQL, valores nem nomes internos de tabelas em detalhe.
_FK_DETAIL = (
    "Referência inválida: o registo associado não existe ou não pode ser usado."
)
_FK_HINT = (
    "Confirme que o identificador enviado existe na entidade referenciada "
    "(ex.: utilizador / recurso pai)."
)
_UNIQUE_DETAIL = "Já existe um registo com estes dados."
_NOT_NULL_DETAIL = "Falta um campo obrigatório."
_GENERIC_INTEGRITY_DETAIL = "Os dados não puderam ser guardados por uma regra de integridade."


@dataclass(frozen=True)
class SafeIntegrityBody:
    """Corpo JSON seguro para respostas de integridade."""

    detail: str
    code: str
    status_code: int
    field: str | None = None
    constraint: str | None = None
    hint: str | None = None
    value: str | None = None  # apenas conflito único; opcional

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "detail": self.detail,
            "code": self.code,
        }
        if self.field is not None:
            out["field"] = self.field
        if self.constraint is not None:
            out["constraint"] = self.constraint
        if self.hint is not None:
            out["hint"] = self.hint
        if self.value is not None:
            out["value"] = self.value
        return out


def _pg_fk_key_not_present(msg: str) -> tuple[str | None, str | None]:
    """
    PostgreSQL: Key (author_id)=(2) is not present in table "users".
    Devolve (field_name, referenced_table) só para logging; cliente recebe field opcional.
    """
    m = re.search(r"Key \(([^)]+)\)=\([^)]*\)\s+is not present in table", msg, re.IGNORECASE)
    if not m:
        return None, None
    field = m.group(1).strip()
    tm = re.search(r'is not present in table\s+"([^"]+)"', msg, re.IGNORECASE)
    table = tm.group(1) if tm else None
    return field, table


def _sqlite_fk_failed(msg: str) -> bool:
    return "FOREIGN KEY constraint failed" in msg


def _unique_sqlite(msg: str) -> str | None:
    if "UNIQUE constraint failed:" not in msg:
        return None
    field_match = msg.split("UNIQUE constraint failed:")[-1].strip()
    return field_match.split(".")[-1] if "." in field_match else field_match


def _not_null_sqlite(msg: str) -> str | None:
    if "NOT NULL constraint failed:" not in msg:
        return None
    field_match = msg.split("NOT NULL constraint failed:")[-1].strip()
    return field_match.split(".")[-1] if "." in field_match else field_match


def _pg_duplicate_key(msg: str, orig: Any) -> tuple[str | None, str | None, str | None]:
    import re as _re

    pg_detail = getattr(orig, "detail", None) or str(msg)
    constraint_name: str | None = getattr(orig, "constraint_name", None)
    field: str | None = None
    value: str | None = None
    if pg_detail:
        m = _re.search(
            r"Key \(([^)]+)\)=\(([^)]*)\) already exists",
            str(pg_detail),
        )
        if m:
            field = m.group(1).strip()
            value = m.group(2).strip()
    if not field and constraint_name:
        parts = constraint_name.split("_")
        if len(parts) >= 3 and parts[-1] in ("key", "idx", "uniq", "unique"):
            field = "_".join(parts[1:-1])
    return field, value, constraint_name


def safe_body_from_integrity_error(exc: Any, *, log_full: bool = True) -> SafeIntegrityBody:
    """
    Constrói corpo de resposta a partir de sqlalchemy.exc.IntegrityError (ou similar).

    log_full: se True, regista o erro completo no log do servidor (não no cliente).
    """
    error_msg = str(exc.orig) if getattr(exc, "orig", None) else str(exc)
    if log_full:
        logger.warning("IntegrityError (sanitized for client): %s", error_msg, exc_info=True)

    em = error_msg
    em_lower = em.lower()

    # --- Foreign key (PostgreSQL / asyncpg) ---
    if "is not present in table" in em or (
        "foreign key" in em_lower and "violates" in em_lower
    ):
        field, ref_table = _pg_fk_key_not_present(em)
        if ref_table:
            logger.info(
                "FK violation (sanitized): field=%s referenced_table=%s",
                field,
                ref_table,
            )
        return SafeIntegrityBody(
            detail=_FK_DETAIL,
            code="foreign_key_violation",
            status_code=400,
            field=field,
            hint=_FK_HINT,
        )

    # --- Foreign key (SQLite) ---
    if _sqlite_fk_failed(em):
        return SafeIntegrityBody(
            detail=_FK_DETAIL,
            code="foreign_key_violation",
            status_code=400,
            hint=_FK_HINT,
        )

    # --- UNIQUE (SQLite) ---
    fn = _unique_sqlite(em)
    if fn is not None:
        return SafeIntegrityBody(
            detail=f"Já existe um registo com este {fn}.",
            code="unique_constraint",
            status_code=409,
            field=fn,
        )

    # --- NOT NULL (SQLite) ---
    nn = _not_null_sqlite(em)
    if nn is not None:
        return SafeIntegrityBody(
            detail=f"O campo '{nn}' é obrigatório.",
            code="required_field",
            status_code=422,
            field=nn,
        )

    # --- UNIQUE (PostgreSQL duplicate key) ---
    if "duplicate key" in em_lower:
        orig = getattr(exc, "orig", None)
        constraint_name: str | None = getattr(orig, "constraint_name", None) if orig else None
        field, value, cname = _pg_duplicate_key(em, orig)
        constraint_name = constraint_name or cname
        content_detail = (
            f"Já existe um registo com este '{field}'."
            if field
            else _UNIQUE_DETAIL
        )
        return SafeIntegrityBody(
            detail=content_detail,
            code="unique_constraint",
            status_code=409,
            field=field,
            constraint=constraint_name,
            hint=None,
            value=value,
        )

    # --- Genérico ---
    return SafeIntegrityBody(
        detail=_GENERIC_INTEGRITY_DETAIL,
        code="integrity_error",
        status_code=400,
        hint="Verifique campos obrigatórios e referências a outros registos.",
    )
