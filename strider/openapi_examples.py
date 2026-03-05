"""
Geração automática de exemplos para OpenAPI.

Estratégia híbrida:
- Geradores nativos (sempre disponíveis)
- Faker opcional (quando habilitado em Settings e instalado)
"""

from __future__ import annotations

from datetime import date, datetime, time
import secrets
import types
from typing import Any, Literal, Union, get_args, get_origin
from uuid import UUID, uuid4

from pydantic import BaseModel


def _get_setting(settings: Any, key: str, default: Any) -> Any:
    try:
        return getattr(settings, key, default)
    except Exception:
        return default


def _extract_explicit_example(schema_cls: type[BaseModel] | None) -> Any | None:
    """Prioriza model_config.json_schema_extra['example'] quando disponível."""
    if schema_cls is None:
        return None
    try:
        config = getattr(schema_cls, "model_config", None)
        if not config:
            return None
        extra = config.get("json_schema_extra") if isinstance(config, dict) else None
        if not isinstance(extra, dict):
            return None
        if "example" in extra:
            return extra["example"]
        examples = extra.get("examples")
        if isinstance(examples, list) and examples:
            first = examples[0]
            if isinstance(first, dict) and "value" in first:
                return first["value"]
            return first
    except Exception:
        return None
    return None


def _build_faker(settings: Any) -> Any | None:
    provider = str(_get_setting(settings, "openapi_examples_provider", "native")).lower()
    if provider not in {"faker", "hybrid"}:
        return None
    try:
        from faker import Faker  # type: ignore

        locale = str(_get_setting(settings, "openapi_examples_locale", "pt_BR"))
        return Faker(locale)
    except Exception:
        return None


def _is_type(annotation: Any, target: type) -> bool:
    try:
        return annotation is target or (isinstance(annotation, type) and issubclass(annotation, target))
    except Exception:
        return False


def _gen_cpf() -> str:
    nums = [int(x) for x in f"{secrets.randbelow(10**9):09d}"]
    d1 = (sum(v * w for v, w in zip(nums, range(10, 1, -1))) * 10) % 11
    d1 = 0 if d1 == 10 else d1
    d2 = (sum(v * w for v, w in zip(nums + [d1], range(11, 1, -1))) * 10) % 11
    d2 = 0 if d2 == 10 else d2
    return "".join(map(str, nums + [d1, d2]))


def _gen_cnpj() -> str:
    base = [int(x) for x in f"{secrets.randbelow(10**8):08d}{secrets.randbelow(10**4):04d}"]
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6] + w1
    r1 = sum(a * b for a, b in zip(base, w1)) % 11
    d1 = 0 if r1 < 2 else 11 - r1
    r2 = sum(a * b for a, b in zip(base + [d1], w2)) % 11
    d2 = 0 if r2 < 2 else 11 - r2
    return "".join(map(str, base + [d1, d2]))


def _example_by_name(name: str, faker: Any | None) -> Any | None:
    n = name.lower()
    if "email" in n:
        return faker.email() if faker else "usuario@example.com"
    if "cpf" in n:
        return _gen_cpf()
    if "cnpj" in n:
        return _gen_cnpj()
    if "token" in n:
        return secrets.token_urlsafe(24)
    if "code" in n:
        return "123456"
    if "phone" in n or "telefone" in n:
        return faker.phone_number() if faker else "+5511999999999"
    if "timestamp" in n or "datetime" in n or n.endswith("_at") or n in {"created_at", "updated_at", "expires_at"}:
        return datetime.utcnow().isoformat() + "Z"
    if n == "id" or n.endswith("_id"):
        return str(uuid4())
    return None


def _example_by_annotation(annotation: Any, name: str, settings: Any, faker: Any | None, depth: int = 0) -> Any:
    if depth > 4:
        return None

    name_based = _example_by_name(name, faker)
    if name_based is not None:
        return name_based

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is None:
        if _is_type(annotation, str):
            return faker.word() if faker else "string"
        if _is_type(annotation, bool):
            return True
        if _is_type(annotation, int):
            return 1
        if _is_type(annotation, float):
            return 1.23
        if _is_type(annotation, UUID):
            return str(uuid4())
        if _is_type(annotation, datetime):
            return datetime.utcnow().isoformat() + "Z"
        if _is_type(annotation, date):
            return date.today().isoformat()
        if _is_type(annotation, time):
            return "12:00:00"
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return _build_model_example(annotation, settings, faker, depth + 1)
        return "value"

    if origin in {list, tuple, set}:
        inner = args[0] if args else str
        return [_example_by_annotation(inner, name, settings, faker, depth + 1)]
    if origin is dict:
        return {"key": "value"}
    if origin in {Union, types.UnionType}:
        non_none = [a for a in args if a is not type(None)]  # noqa: E721
        selected = non_none[0] if non_none else str
        return _example_by_annotation(selected, name, settings, faker, depth + 1)
    if origin is Literal:
        return args[0] if args else "value"

    return "value"


def _build_model_example(
    schema_cls: type[BaseModel],
    settings: Any,
    faker: Any | None,
    depth: int = 0,
) -> dict[str, Any]:
    explicit = _extract_explicit_example(schema_cls)
    if explicit is not None:
        return explicit if isinstance(explicit, dict) else {"value": explicit}

    example: dict[str, Any] = {}
    for field_name, field in schema_cls.model_fields.items():
        annotation = field.annotation
        example[field_name] = _example_by_annotation(
            annotation,
            field_name,
            settings,
            faker,
            depth,
        )
    return example


def build_schema_example(schema_cls: type[BaseModel] | None, settings: Any = None) -> dict[str, Any] | None:
    """Exemplo de request para um schema Pydantic."""
    if schema_cls is None:
        return None
    enabled = bool(_get_setting(settings, "openapi_examples_enabled", True))
    if not enabled:
        return None
    faker = _build_faker(settings)
    try:
        return _build_model_example(schema_cls, settings, faker)
    except Exception:
        return None


def build_response_example(schema_cls: type[BaseModel] | None, settings: Any = None) -> dict[str, Any] | None:
    """Exemplo de response para um schema Pydantic."""
    if schema_cls is None:
        return None
    enabled = bool(_get_setting(settings, "openapi_examples_enabled", True))
    if not enabled:
        return None
    faker = _build_faker(settings)
    try:
        return _build_model_example(schema_cls, settings, faker)
    except Exception:
        return None
