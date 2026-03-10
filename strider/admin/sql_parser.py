"""
SQL Parser — Importador de dumps MySQL/MariaDB.

Faz parsing de dumps SQL (phpMyAdmin, mysqldump) de forma streaming,
sem carregar tudo na memória de uma vez. Suporta:
- CREATE TABLE com tipos, constraints, índices
- INSERT INTO com multi-row VALUES
- Inferência automática de tipos Python a partir de tipos SQL
- Detecção de campos JSON, ENUMs, UUIDs, booleans
"""

from __future__ import annotations

import io
import json
import re
import tempfile
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator, Iterator

logger = logging.getLogger("strider.admin.importer")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ColumnSchema:
    name: str
    sql_type: str          # tipo raw do SQL
    python_type: str       # bool, int, float, str, datetime, json, uuid
    nullable: bool = True
    default: Any = None
    is_pk: bool = False
    is_unique: bool = False
    enum_values: list[str] = field(default_factory=list)
    is_json: bool = False
    is_fk: bool = False    # detectado por convenção _id suffix


@dataclass
class TableSchema:
    name: str
    columns: list[ColumnSchema]
    row_count: int = 0

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def column_by_name(self, name: str) -> ColumnSchema | None:
        for c in self.columns:
            if c.name == name:
                return c
        return None


@dataclass
class ParseResult:
    tables: dict[str, TableSchema]
    data_file: Path
    row_counts: dict[str, int]
    errors: list[str]


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------

_JSON_HINT_RE = re.compile(r"json_valid", re.IGNORECASE)
_ENUM_RE = re.compile(r"enum\((.+?)\)", re.IGNORECASE)
_DECIMAL_RE = re.compile(r"decimal|numeric|double|real", re.IGNORECASE)
_INT_RE = re.compile(r"int|bigint|mediumint|smallint|tinyint", re.IGNORECASE)
_BOOL_RE = re.compile(r"tinyint\s*\(\s*1\s*\)", re.IGNORECASE)
_FLOAT_RE = re.compile(r"float|double|real|decimal|numeric", re.IGNORECASE)
_DATETIME_RE = re.compile(r"datetime|timestamp", re.IGNORECASE)
_DATE_RE = re.compile(r"^date$", re.IGNORECASE)
_UUID_RE = re.compile(r"char\s*\(\s*36\s*\)", re.IGNORECASE)
_TEXT_RE = re.compile(r"text|varchar|char|blob|clob", re.IGNORECASE)


def _infer_python_type(sql_type: str, col_name: str, col_def_line: str = "") -> tuple[str, bool]:
    """
    Retorna (python_type, is_json) inferido do tipo SQL.
    """
    # JSON detectado por CHECK json_valid() ou campo longtext com nome sugestivo
    if _JSON_HINT_RE.search(col_def_line):
        return "json", True

    name_lower = col_name.lower()
    json_names = {"data", "metadata", "config", "settings", "extra", "payload",
                  "properties", "attributes", "raw", "options", "features", "benefits",
                  "ticks_data", "plan_ids", "keywords", "deriv_raw"}
    if name_lower in json_names and "text" in sql_type.lower():
        return "json", True

    if _BOOL_RE.search(sql_type):
        return "bool", False
    if _UUID_RE.search(sql_type):
        return "uuid", False
    if _ENUM_RE.search(sql_type):
        return "str", False
    if _DATETIME_RE.search(sql_type):
        return "datetime", False
    if _DATE_RE.search(sql_type):
        return "date", False
    if _FLOAT_RE.search(sql_type):
        return "float", False
    if _INT_RE.search(sql_type):
        return "int", False
    if _TEXT_RE.search(sql_type):
        return "str", False

    # FK heuristic
    if col_name.endswith("_id"):
        return "uuid", False

    return "str", False


# ---------------------------------------------------------------------------
# CREATE TABLE parser
# ---------------------------------------------------------------------------

# Matches: `col_name` TYPE [constraints...]
_COL_DEF_RE = re.compile(
    r"^\s*`(?P<name>[^`]+)`\s+(?P<type>\S+(?:\s*\([^)]*\))?)"
    r"(?P<rest>.*)",
    re.IGNORECASE,
)
_TABLE_NAME_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`'\"]?(?P<name>\w+)[`'\"]?",
    re.IGNORECASE,
)
_PK_RE = re.compile(r"\bPRIMARY\s+KEY\b", re.IGNORECASE)
_UNIQUE_RE = re.compile(r"\bUNIQUE\b", re.IGNORECASE)
_NOT_NULL_RE = re.compile(r"\bNOT\s+NULL\b", re.IGNORECASE)
_AUTO_INC_RE = re.compile(r"\bAUTO_INCREMENT\b", re.IGNORECASE)


def _parse_create_table(block: str) -> TableSchema | None:
    """
    Parseia um bloco CREATE TABLE e retorna TableSchema.
    """
    m = _TABLE_NAME_RE.search(block)
    if not m:
        return None

    table_name = m.group("name")
    columns: list[ColumnSchema] = []
    pk_cols: set[str] = set()
    unique_cols: set[str] = set()

    # Extrair apenas as linhas de definição dentro dos parênteses
    paren_content = _extract_paren_content(block)
    if not paren_content:
        return None

    lines = paren_content.split("\n")
    for raw_line in lines:
        line = raw_line.strip().rstrip(",")
        if not line:
            continue

        # PRIMARY KEY (...) — table-level constraint
        pk_m = re.search(r"PRIMARY\s+KEY\s*\(([^)]+)\)", line, re.IGNORECASE)
        if pk_m:
            for col in pk_m.group(1).split(","):
                pk_cols.add(col.strip().strip("`'\""))
            continue

        # UNIQUE KEY / UNIQUE INDEX — table-level
        uq_m = re.search(r"UNIQUE\s+(?:KEY|INDEX)?\s*`?\w*`?\s*\(([^)]+)\)", line, re.IGNORECASE)
        if uq_m:
            for col in uq_m.group(1).split(","):
                unique_cols.add(col.strip().strip("`'\""))
            continue

        # Skip KEY/INDEX/CONSTRAINT lines
        if re.match(r"^\s*(KEY|INDEX|CONSTRAINT|CHECK|FULLTEXT|SPATIAL)", line, re.IGNORECASE):
            continue

        # Column definition
        cm = _COL_DEF_RE.match(line)
        if not cm:
            continue

        col_name = cm.group("name")
        sql_type = cm.group("type")
        rest = cm.group("rest")
        full_def = line

        python_type, is_json = _infer_python_type(sql_type, col_name, full_def)

        is_pk = bool(_PK_RE.search(rest)) or col_name in pk_cols
        is_unique = bool(_UNIQUE_RE.search(rest)) or col_name in unique_cols
        nullable = not bool(_NOT_NULL_RE.search(rest)) and not is_pk

        # Extract ENUM values
        enum_values: list[str] = []
        enum_m = _ENUM_RE.search(sql_type)
        if enum_m:
            raw_vals = enum_m.group(1)
            enum_values = [v.strip().strip("'\"") for v in raw_vals.split(",")]

        # Default value
        default = None
        def_m = re.search(r"DEFAULT\s+('([^']*)'|\"([^\"]*)\"|(\S+))", rest, re.IGNORECASE)
        if def_m:
            default = def_m.group(2) or def_m.group(3) or def_m.group(4)
            if default and default.upper() in ("NULL", "CURRENT_TIMESTAMP"):
                default = None

        columns.append(ColumnSchema(
            name=col_name,
            sql_type=sql_type,
            python_type=python_type,
            nullable=nullable,
            default=default,
            is_pk=is_pk,
            is_unique=is_unique,
            enum_values=enum_values,
            is_json=is_json,
            is_fk=col_name.endswith("_id") and not is_pk,
        ))

    # Apply table-level PK/UNIQUE
    for col in columns:
        if col.name in pk_cols:
            col.is_pk = True
        if col.name in unique_cols:
            col.is_unique = True

    return TableSchema(name=table_name, columns=columns)


def _extract_paren_content(block: str) -> str | None:
    """Extrai o conteúdo entre o primeiro ( e o último )."""
    start = block.find("(")
    if start == -1:
        return None
    depth = 0
    end = start
    for i, ch in enumerate(block[start:], start):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    return block[start + 1:end]


# ---------------------------------------------------------------------------
# INSERT parser
# ---------------------------------------------------------------------------

_INSERT_TABLE_RE = re.compile(
    r"INSERT\s+INTO\s+[`'\"]?(?P<table>\w+)[`'\"]?\s*\((?P<cols>[^)]+)\)\s*VALUES\s*",
    re.IGNORECASE,
)


def _parse_insert_line(line: str) -> tuple[str, list[str], list[list[Any]]] | None:
    """
    Parseia uma linha INSERT INTO e retorna (table_name, col_names, rows).
    Suporta INSERT com múltiplos VALUES agrupados.
    """
    m = _INSERT_TABLE_RE.search(line)
    if not m:
        return None

    table_name = m.group("table")
    cols_raw = m.group("cols")
    col_names = [c.strip().strip("`'\"") for c in cols_raw.split(",")]

    # Tudo após VALUES
    values_start = m.end()
    values_str = line[values_start:].rstrip(";")

    rows = _parse_values_string(values_str)
    return table_name, col_names, rows


def _parse_values_string(values_str: str) -> list[list[Any]]:
    """
    Parseia a string de VALUES de um INSERT, retornando lista de listas de valores.
    Suporta strings com vírgulas, aspas escapadas, NULLs e valores numéricos.
    """
    rows: list[list[Any]] = []
    i = 0
    s = values_str.strip()
    n = len(s)

    while i < n:
        # pula até o próximo '('
        while i < n and s[i] != "(":
            i += 1
        if i >= n:
            break
        i += 1  # skip '('

        row: list[Any] = []
        while i < n and s[i] != ")":
            # NULL
            if s[i:i+4].upper() == "NULL":
                row.append(None)
                i += 4
                # skip comma/space
                while i < n and s[i] in (" ", "\t", ","):
                    i += 1
                continue

            # String: 'value' ou "value"
            if s[i] in ("'", '"'):
                quote = s[i]
                i += 1
                buf: list[str] = []
                while i < n:
                    if s[i] == "\\" and i + 1 < n:
                        nx = s[i + 1]
                        if nx == "n":
                            buf.append("\n")
                        elif nx == "t":
                            buf.append("\t")
                        elif nx == "r":
                            buf.append("\r")
                        elif nx == "'":
                            buf.append("'")
                        elif nx == '"':
                            buf.append('"')
                        elif nx == "\\":
                            buf.append("\\")
                        else:
                            buf.append(nx)
                        i += 2
                        continue
                    if s[i] == quote:
                        i += 1
                        break
                    buf.append(s[i])
                    i += 1
                row.append("".join(buf))
                # skip comma/space
                while i < n and s[i] in (" ", "\t", ","):
                    i += 1
                continue

            # Number or identifier
            j = i
            while j < n and s[j] not in (",", ")", " ", "\t"):
                j += 1
            token = s[i:j].strip()
            i = j
            if token:
                row.append(token)
            # skip comma/space
            while i < n and s[i] in (" ", "\t", ","):
                i += 1

        rows.append(row)
        i += 1  # skip ')'
        # skip comma between row groups
        while i < n and s[i] in (" ", "\t", "\n", "\r", ","):
            i += 1

    return rows


# ---------------------------------------------------------------------------
# Main parse function — streaming
# ---------------------------------------------------------------------------

def parse_sql_file(content: str) -> ParseResult:
    """
    Parseia um dump SQL MySQL/MariaDB de forma eficiente.

    Estratégia:
    - CREATE TABLE blocks: acumulados e parseados para schema
    - INSERT INTO lines: processadas em streaming, escritas em tempfile (JSONL)
    - Nunca mantém todas as rows em RAM simultaneamente

    Returns:
        ParseResult com schema em memória e dados em arquivo temporário
    """
    tables: dict[str, TableSchema] = {}
    errors: list[str] = []
    row_counts: dict[str, int] = {}

    # Tempfile para armazenar rows em formato JSONL (uma row por linha)
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".jsonl",
        prefix="strider_import_",
        delete=False,
        encoding="utf-8",
    )
    data_file = Path(tmp.name)

    try:
        lines = content.splitlines()
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i]
            stripped = line.strip()

            # --- CREATE TABLE ---
            if re.match(r"CREATE\s+TABLE", stripped, re.IGNORECASE):
                block_lines = []
                depth = 0
                while i < n:
                    block_lines.append(lines[i])
                    depth += lines[i].count("(") - lines[i].count(")")
                    i += 1
                    if depth <= 0 and len(block_lines) > 1:
                        break
                block = "\n".join(block_lines)
                schema = _parse_create_table(block)
                if schema:
                    tables[schema.name] = schema
                    row_counts[schema.name] = 0
                continue

            # --- INSERT INTO ---
            # Dumps do phpMyAdmin podem ter INSERT multi-linha (VALUES em linha separada)
            # Acumula linhas até encontrar ';' para montar o INSERT completo
            if re.match(r"INSERT\s+INTO", stripped, re.IGNORECASE):
                insert_lines = [stripped]
                # Se a linha já termina com ';', é single-line
                if not stripped.rstrip().endswith(";"):
                    i += 1
                    while i < n:
                        next_stripped = lines[i].strip()
                        insert_lines.append(next_stripped)
                        i += 1
                        if next_stripped.rstrip().endswith(";"):
                            break

                full_insert = " ".join(insert_lines)
                result = _parse_insert_line(full_insert)
                if result:
                    table_name, col_names, rows = result
                    for row_values in rows:
                        if len(row_values) != len(col_names):
                            errors.append(
                                f"[{table_name}] Column count mismatch: "
                                f"expected {len(col_names)}, got {len(row_values)}"
                            )
                            continue
                        row_dict = dict(zip(col_names, row_values))
                        record = {"_table": table_name, **row_dict}
                        tmp.write(json.dumps(record, default=str) + "\n")
                        row_counts[table_name] = row_counts.get(table_name, 0) + 1
                continue

            i += 1

    finally:
        tmp.close()

    # Atualizar row_counts nos schemas
    for tname, count in row_counts.items():
        if tname in tables:
            tables[tname].row_count = count

    logger.info(
        "SQL parse complete: %d tables, %d total rows, %d errors",
        len(tables),
        sum(row_counts.values()),
        len(errors),
    )

    return ParseResult(
        tables=tables,
        data_file=data_file,
        row_counts=row_counts,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Row streaming from tempfile
# ---------------------------------------------------------------------------

def stream_table_rows(data_file: Path, table_name: str) -> Generator[dict[str, Any], None, None]:
    """
    Lê linhas de uma tabela do arquivo temporário (JSONL), sem carregar tudo.
    """
    with open(data_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("_table") == table_name:
                # Remove internal key
                record.pop("_table", None)
                yield record


def preview_table_rows(
    data_file: Path,
    table_name: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Retorna até `limit` linhas de uma tabela para preview."""
    result = []
    for row in stream_table_rows(data_file, table_name):
        result.append(row)
        if len(result) >= limit:
            break
    return result


# ---------------------------------------------------------------------------
# Type conversion pipeline
# ---------------------------------------------------------------------------

import datetime as _dt


def _coerce_bool(v: Any) -> bool | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return bool(v)
    if isinstance(v, str):
        return v not in ("0", "false", "False", "no", "No", "NULL", "null")
    return bool(v)


def _coerce_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(str(v)))
    except (ValueError, TypeError):
        return None


def _coerce_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v))
    except (ValueError, TypeError):
        return None


def _coerce_datetime(v: Any, config: dict[str, Any] | None = None) -> str | None:
    """Retorna string ISO para compatibilidade com SQLAlchemy.

    config keys:
        source_format: strftime format string (auto-detect if None)
        source_tz: pytz/zoneinfo timezone name for naive datetimes (None = assume UTC)
        target_tz: output timezone name (default "UTC")
        assume_utc: treat naive datetimes as UTC (default True)
    """
    if v is None or v == "":
        return None
    s = str(v).strip()
    cfg = config or {}

    source_fmt = cfg.get("source_format")
    source_tz_name: str | None = cfg.get("source_tz")
    target_tz_name: str = cfg.get("target_tz") or "UTC"
    assume_utc: bool = cfg.get("assume_utc", True)

    # Parse the datetime value
    parsed: _dt.datetime | None = None
    if source_fmt:
        try:
            parsed = _dt.datetime.strptime(s, source_fmt)
        except (ValueError, TypeError):
            pass

    if parsed is None:
        # Auto-detect: try common MySQL/ISO formats
        s_norm = s.replace("T", " ")
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = _dt.datetime.strptime(s_norm, fmt)
                break
            except (ValueError, TypeError):
                continue

    if parsed is None:
        return s  # pass-through if unparseable

    # Attach timezone info if datetime is naive
    if parsed.tzinfo is None:
        try:
            import zoneinfo
            tz_name = source_tz_name or ("UTC" if assume_utc else None)
            if tz_name:
                parsed = parsed.replace(tzinfo=zoneinfo.ZoneInfo(tz_name))
        except Exception:
            pass

    # Convert to target timezone
    try:
        import zoneinfo as _zi
        tgt_tz = _zi.ZoneInfo(target_tz_name)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(tgt_tz)
    except Exception:
        pass

    return parsed.isoformat()


def _coerce_json(v: Any) -> Any:
    if v is None or v == "":
        return None
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return v
    return v


def _apply_struct_map(v: Any, config: dict[str, Any] | None = None) -> Any:
    """
    Maps a JSON value to a StructSchema-compatible dict.

    config keys:
        field_map: dict mapping source JSON keys → StructSchema field names
        use_aliases: if True, also search aliases defined in StructSchema
        drop_unknown: if True, discard keys not in field_map
    """
    if v is None or v == "":
        return None

    # Parse JSON string if needed
    data: dict[str, Any]
    if isinstance(v, str):
        try:
            data = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return v
    elif isinstance(v, dict):
        data = v
    else:
        return v

    if not config:
        return data

    field_map: dict[str, str] = config.get("field_map") or {}
    drop_unknown: bool = config.get("drop_unknown", False)

    result: dict[str, Any] = {}
    for src_key, val in data.items():
        dest_key = field_map.get(src_key, src_key)
        if drop_unknown and src_key not in field_map:
            continue
        result[dest_key] = val

    return result


TRANSFORMS: dict[str, Any] = {
    "passthrough":    lambda v: v,
    "to_bool":        _coerce_bool,
    "to_int":         _coerce_int,
    "to_float":       _coerce_float,
    "to_datetime":    _coerce_datetime,
    "json_parse":     _coerce_json,
    "struct_map":     _apply_struct_map,
    "uuid_str":       lambda v: str(v) if v is not None else None,
    "strip":          lambda v: v.strip() if isinstance(v, str) else v,
    "lower":          lambda v: v.lower() if isinstance(v, str) else v,
    "upper":          lambda v: v.upper() if isinstance(v, str) else v,
    "null_if_empty":  lambda v: None if v == "" else v,
    "str":            lambda v: str(v) if v is not None else None,
}


def apply_transform(
    value: Any,
    transform: str | None,
    config: dict[str, Any] | None = None,
) -> Any:
    """Aplica uma transformação a um valor. Retorna o valor original se transform inválido."""
    if transform is None or transform == "passthrough":
        return value
    fn = TRANSFORMS.get(transform)
    if fn is None:
        return value
    try:
        # Functions that accept an optional config param
        if transform in ("to_datetime", "struct_map") and config is not None:
            return fn(value, config)
        return fn(value)
    except Exception:
        return value


def transform_row(
    row: dict[str, Any],
    column_mappings: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """
    Aplica mapeamento de colunas a uma row.

    Args:
        row: dict original com valores brutos
        column_mappings: lista de {source, target, transform, default,
                                   struct_config, datetime_config}

    Returns:
        (transformed_row, errors)
    """
    result: dict[str, Any] = {}
    errs: list[str] = []

    for mapping in column_mappings:
        source = mapping.get("source")
        target = mapping.get("target")
        transform = mapping.get("transform", "passthrough")
        default = mapping.get("default")

        if not target:  # skip column
            continue

        raw_value = row.get(source)
        if raw_value is None and default is not None:
            raw_value = default

        # Resolve per-transform config
        config: dict[str, Any] | None = None
        if transform == "struct_map":
            config = mapping.get("struct_config")
        elif transform == "to_datetime":
            config = mapping.get("datetime_config")

        try:
            result[target] = apply_transform(raw_value, transform, config)
        except Exception as e:
            errs.append(f"Column '{source}' → '{target}': {e}")
            result[target] = None

    return result, errs
