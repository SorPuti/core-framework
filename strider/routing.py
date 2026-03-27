"""
Sistema de Roteamento automático inspirado no DRF.

Características:
- Auto-registro de ViewSets
- Geração automática de rotas REST
- Nomes previsíveis
- OpenAPI consistente com schemas tipados para request/response
- Exportação rica para Postman (campos pré-configurados)
- Override manual quando necessário
- Integração nativa com FastAPI
"""

from __future__ import annotations

import inspect
import logging
import os
import types
from uuid import UUID
from collections.abc import Callable
from typing import Any, Optional, TYPE_CHECKING, TypeVar as TypingTypeVar, Union, get_args, get_origin

from fastapi import APIRouter, Request, Depends, Body, File, UploadFile, Path
from pydantic import BaseModel, ValidationError as PydanticValidationError, create_model
from sqlalchemy.ext.asyncio import AsyncSession

from strider.dependencies import get_db, get_optional_user
from strider.exceptions import StridePathParamBindingError
from strider.openapi_examples import build_schema_example, build_response_example
from strider.serializers import (
    InputSchema,
    OutputSchema,
    PaginatedResponse,
    DeleteResponse,
    ValidationErrorResponse,
    NotFoundResponse,
    ConflictResponse,
)

if TYPE_CHECKING:
    from strider.views import ViewSet, APIView

logger = logging.getLogger("strider.routing")


# =============================================================================
# Helpers para OpenAPI / Schema resolution
# =============================================================================

# Cache para modelos parciais (PATCH)
_partial_model_cache: dict[type, type] = {}

# Cache for list item schema (when output_schema has list_include / list_exclude)
_list_item_schema_cache: dict[tuple[type, frozenset[str]], type[BaseModel]] = {}

# Cache for model-based fallback schemas (OpenAPI docs when user does not set input_schema/output_schema)
_fallback_schemas_cache: dict[type, tuple[type[BaseModel], type[BaseModel]]] = {}

# SQLAlchemy column type -> Python type for OpenAPI fallback schemas
_SA_TYPE_MAP: dict[str, type] = {
    "INTEGER": int,
    "BIGINT": int,
    "SMALLINT": int,
    "VARCHAR": str,
    "STRING": str,
    "TEXT": str,
    "CHAR": str,
    "BOOLEAN": bool,
    "FLOAT": float,
    "NUMERIC": float,
    "DECIMAL": float,
    "JSON": dict,
    "JSONB": dict,
}


def _openapi_python_type_for_column(col: Any) -> type:
    """Resolve Python type for a SQLAlchemy column (for doc-only fallback schemas)."""
    type_str = str(col.type).upper()
    for key, py_type in _SA_TYPE_MAP.items():
        if key in type_str:
            return py_type
    if "UUID" in type_str:
        from uuid import UUID
        return UUID
    if "DATETIME" in type_str or "TIMESTAMP" in type_str or "DATE" in type_str:
        from datetime import datetime
        return datetime
    return str


def _build_fallback_schemas_from_model(
    model: type,
) -> tuple[type[InputSchema], type[OutputSchema]]:
    """
    Build input/output Pydantic schemas from a SQLAlchemy model for OpenAPI docs.
    Used when the ViewSet does not define input_schema/output_schema.
    """
    if model in _fallback_schemas_cache:
        return _fallback_schemas_cache[model]
    try:
        table = getattr(model, "__table__", None)
        if table is None:
            raise ValueError("Model has no __table__")
    except Exception:
        # Return minimal placeholder schemas so docs still show something
        inp = create_model(
            f"{getattr(model, '__name__', 'Model')}InputFallback",
            __base__=InputSchema,
            body=(dict[str, Any], ...),
        )
        out = create_model(
            f"{getattr(model, '__name__', 'Model')}OutputFallback",
            __base__=OutputSchema,
            id=(int, ...),
            data=(dict[str, Any], ...),
        )
        _fallback_schemas_cache[model] = (inp, out)
        return inp, out

    name = getattr(model, "__name__", "Model")
    out_fields: dict[str, Any] = {}
    in_fields: dict[str, Any] = {}

    for col in table.columns:
        py_type = _openapi_python_type_for_column(col)
        ann = py_type if not col.nullable else Optional[py_type]
        default = None if col.nullable else ...
        out_fields[col.name] = (ann, default)

        # Input: skip PK and autoincrement
        if getattr(col, "primary_key", False) or getattr(col, "autoincrement", False):
            continue
        in_ann = py_type if not col.nullable and col.default is None and col.server_default is None else Optional[py_type]
        in_default = None if (col.nullable or col.default is not None or col.server_default is not None) else ...
        in_fields[col.name] = (in_ann, in_default)

    if not in_fields:
        in_fields["body"] = (dict[str, Any], ...)
    out_schema = create_model(
        f"{name}OutputFallback",
        __base__=OutputSchema,
        **out_fields,
    )
    in_schema = create_model(
        f"{name}InputFallback",
        __base__=InputSchema,
        **in_fields,
    )
    _fallback_schemas_cache[model] = (in_schema, out_schema)
    return in_schema, out_schema


def _make_partial_model(schema: type[BaseModel]) -> type[BaseModel]:
    """
    Cria um modelo Pydantic com todos os campos opcionais.
    
    Usado para endpoints PATCH onde apenas alguns campos são enviados.
    O resultado é cacheado por classe de schema.
    
    Herda do schema original para preservar:
    - model_config (extra="forbid", str_strip_whitespace, etc.)
    - Validators customizados
    - Métodos e propriedades
    
    Args:
        schema: Modelo Pydantic original com campos obrigatórios
    
    Returns:
        Novo modelo com todos os campos Optional e default None
    """
    if schema in _partial_model_cache:
        return _partial_model_cache[schema]
    
    fields = {}
    for field_name, field_info in schema.model_fields.items():
        annotation = field_info.annotation
        if annotation is not None:
            fields[field_name] = (Optional[annotation], None)
        else:
            fields[field_name] = (Optional[Any], None)
    
    # Herda do schema original para preservar model_config e validators
    partial_model = create_model(
        f"Partial{schema.__name__}",
        __base__=schema,
        **fields,
    )
    
    _partial_model_cache[schema] = partial_model
    return partial_model


def _get_list_item_schema(output_schema: type[BaseModel]) -> type[BaseModel]:
    """
    Retorna o schema a usar para cada item da listagem.
    Se o output_schema define list_include ou list_exclude (OutputSchema),
    cria um modelo com o subconjunto de campos; senão retorna o próprio output_schema.
    
    Inclui campos computados (@computed_field e @computed_orm_field) automaticamente.
    """
    list_include = getattr(output_schema, "list_include", None)
    list_exclude = getattr(output_schema, "list_exclude", None)
    if not list_include and not list_exclude:
        return output_schema
    
    # Usar _get_all_fields() para incluir campos computados
    all_names = output_schema._get_all_fields() if hasattr(output_schema, '_get_all_fields') else set(output_schema.model_fields.keys())
    
    if list_include is not None:
        names = all_names & set(list_include)
    else:
        names = all_names - set(list_exclude)
    if not names:
        return output_schema
    key = (output_schema, frozenset(names))
    if key in _list_item_schema_cache:
        return _list_item_schema_cache[key]
    # Coletar campos do modelo base
    fields: dict[str, Any] = {}
    computed_field_names: set[str] = set()
    
    for name in sorted(names):
        if name in output_schema.model_fields:
            fi = output_schema.model_fields[name]
            default = ... if fi.is_required() else fi.default
            fields[name] = (fi.annotation, default)
        else:
            computed_field_names.add(name)
    
    list_item_model = create_model(
        f"{output_schema.__name__}ListItem",
        __base__=OutputSchema,
        **fields,
    )
    
    if computed_field_names:
        computed_fields: dict[str, Any] = {
            name: (Any | None, None) for name in computed_field_names
        }
        list_item_model = create_model(
            f"{output_schema.__name__}ListItem",
            __base__=list_item_model,
            **computed_fields,
        )
    
    _list_item_schema_cache[key] = list_item_model
    return list_item_model


def _resolve_schemas(
    viewset_class: type,
) -> tuple[type[InputSchema] | None, type[OutputSchema] | None]:
    """
    Resolve input and output schemas from a ViewSet class.
    Prefer serializer_class (input_cls/output_cls ou input_schema/output_schema) como fonte única.
    """
    serializer_class = getattr(viewset_class, "serializer_class", None)
    if serializer_class:
        input_schema = (
            getattr(serializer_class, "input_cls", None)
            or getattr(serializer_class, "input_schema", None)
        )
        output_schema = (
            getattr(serializer_class, "output_cls", None)
            or getattr(serializer_class, "output_schema", None)
        )
    else:
        input_schema = getattr(viewset_class, "input_schema", None)
        output_schema = getattr(viewset_class, "output_schema", None)

    # Fallback for OpenAPI: when user did not set schemas, build from model so docs are not null.
    # If we cannot build a proper schema (e.g. model without __table__), we fall back to a permissive
    # schema to avoid 422 errors caused by `extra_forbidden`.
    model = getattr(viewset_class, "model", None)
    if model is not None:
        if input_schema is None or output_schema is None:
            fallback_in, fallback_out = _build_fallback_schemas_from_model(model)
            if input_schema is None:
                input_schema = fallback_in
            if output_schema is None:
                output_schema = fallback_out
            logger.debug(
                "Resolved schemas for %s using fallback: input=%s output=%s",
                viewset_class.__name__,
                getattr(input_schema, "__name__", repr(input_schema)),
                getattr(output_schema, "__name__", repr(output_schema)),
            )

    return input_schema, output_schema


def _is_dynamic_path_segment(segment: str) -> bool:
    """Return True when segment represents a dynamic parameter."""
    if segment.startswith("{") and segment.endswith("}"):
        return True
    # Regex-style FastAPI segments (e.g. (?P<id>[^/]+))
    return "(?P<" in segment


def _default_custom_action_sort_key(
    action_name: str,
    url_path: str,
    detail: bool,
) -> tuple[int, int, int, int, int, str]:
    """
    Automatic route ordering:
    - more static segments first
    - fewer dynamic segments first
    - path wildcards / regex segments last
    - longer paths first
    """
    segments = [seg for seg in (url_path or "").strip("/").split("/") if seg]
    static_count = 0
    dynamic_count = 0
    wildcard_count = 0
    regex_count = 0

    for segment in segments:
        if segment.startswith("{") and segment.endswith("}"):
            dynamic_count += 1
            inner = segment[1:-1]
            if ":" in inner:
                _, converter = inner.split(":", 1)
                if converter.strip().lower() == "path":
                    wildcard_count += 1
            continue

        if _is_dynamic_path_segment(segment):
            dynamic_count += 1
            regex_count += 1
            continue

        static_count += 1

    return (
        -static_count,
        dynamic_count,
        wildcard_count,
        regex_count,
        -len(segments),
        action_name,
    )


def _iter_sorted_custom_actions(
    viewset_class: type["ViewSet"],
    detail_filter: bool | None = None,
) -> list[tuple[str, Callable]]:
    """
    Collect custom actions and return them in deterministic priority order.
    """
    items: list[tuple[tuple[Any, ...], str, Callable]] = []
    custom_sorter = getattr(viewset_class, "custom_action_sort_key", None)

    for name, method in inspect.getmembers(viewset_class, predicate=inspect.isfunction):
        if not getattr(method, "is_action", False):
            continue

        detail = method.detail
        if detail_filter is not None and detail != detail_filter:
            continue

        url_path = method.url_path
        if callable(custom_sorter):
            try:
                key = custom_sorter(name, url_path, detail)
            except Exception as exc:
                logger.warning(
                    "custom_action_sort_key failed in %s.%s (%s); using default sorter",
                    viewset_class.__name__,
                    name,
                    exc,
                )
                key = _default_custom_action_sort_key(name, url_path, detail)
        else:
            key = _default_custom_action_sort_key(name, url_path, detail)

        items.append((key, name, method))

    items.sort(key=lambda item: item[0])
    return [(name, method) for _, name, method in items]


def _build_error_responses(
    include_404: bool = False,
    include_409: bool = False,
    include_422: bool = True,
) -> dict[int, dict[str, Any]]:
    """
    Constrói respostas de erro comuns para documentação OpenAPI.
    
    Args:
        include_404: Incluir resposta 404 Not Found
        include_409: Incluir resposta 409 Conflict
        include_422: Incluir resposta 422 Validation Error
    
    Returns:
        Dict de status_code → schema para OpenAPI responses
    """
    responses: dict[int, dict[str, Any]] = {}
    
    if include_422:
        responses[422] = {
            "description": "Erro de validação nos dados enviados",
            "model": ValidationErrorResponse,
        }
    
    if include_404:
        responses[404] = {
            "description": "Recurso não encontrado",
            "model": NotFoundResponse,
        }
    
    if include_409:
        responses[409] = {
            "description": "Conflito - registro com valor duplicado",
            "model": ConflictResponse,
        }
    
    return responses


def _get_openapi_example_settings() -> Any:
    """Load settings lazily to avoid import-time coupling."""
    try:
        from strider.config import get_settings

        return get_settings()
    except Exception:
        return None


def _merge_response_specs(
    base: dict[int, dict[str, Any]] | None,
    extra: dict[int, dict[str, Any]] | None,
) -> dict[int, dict[str, Any]]:
    merged: dict[int, dict[str, Any]] = dict(base or {})
    for code, spec in (extra or {}).items():
        existing = merged.get(code)
        if isinstance(existing, dict):
            patched = dict(existing)
            patched.update(spec)
            merged[code] = patched
        else:
            merged[code] = spec
    return merged


def _build_openapi_examples(
    *,
    input_schema: type[BaseModel] | None = None,
    output_schema: type[BaseModel] | None = None,
    success_status: int = 200,
    settings: Any = None,
) -> tuple[dict[str, Any] | None, dict[int, dict[str, Any]]]:
    request_example = build_schema_example(input_schema, settings=settings) if input_schema else None
    response_example = build_response_example(output_schema, settings=settings) if output_schema else None

    openapi_extra: dict[str, Any] | None = None
    if request_example is not None:
        openapi_extra = {
            "requestBody": {
                "content": {
                    "application/json": {
                        "example": request_example,
                    },
                },
            },
        }

    responses: dict[int, dict[str, Any]] = {}
    if response_example is not None:
        responses[success_status] = {
            "description": "Exemplo de resposta",
            "content": {
                "application/json": {
                    "example": response_example,
                },
            },
        }

    return openapi_extra, responses


def _annotation_contains_basemodel(annotation: Any) -> bool:
    """Return True when annotation references a Pydantic BaseModel."""
    if annotation in (inspect._empty, Any, None):
        return False
    if isinstance(annotation, type):
        try:
            return issubclass(annotation, BaseModel)
        except TypeError:
            return False
    if isinstance(annotation, TypingTypeVar):
        bound = getattr(annotation, "__bound__", None)
        if bound is not None:
            return _annotation_contains_basemodel(bound)
        return False
    origin = get_origin(annotation)
    if origin is None:
        return False
    return any(_annotation_contains_basemodel(arg) for arg in get_args(annotation))


def _annotation_accepts_mapping(annotation: Any) -> bool:
    """Return True when annotation accepts a dict-like payload."""
    if annotation in (inspect._empty, Any):
        return True
    if annotation is dict:
        return True
    origin = get_origin(annotation)
    if origin is dict:
        return True
    if origin is None:
        return False
    return any(_annotation_accepts_mapping(arg) for arg in get_args(annotation))


def _extract_first_basemodel_type(annotation: Any) -> type[BaseModel] | None:
    """Extract first BaseModel type found in an annotation tree."""
    if annotation in (inspect._empty, Any, None):
        return None
    if isinstance(annotation, type):
        try:
            if issubclass(annotation, BaseModel):
                return annotation
        except TypeError:
            return None
    origin = get_origin(annotation)
    if origin is None:
        return None
    for arg in get_args(annotation):
        model_type = _extract_first_basemodel_type(arg)
        if model_type is not None:
            return model_type
    return None


def _pick_body_param_name(
    target_callable: Callable,
    *,
    path_params: dict[str, Any],
) -> tuple[str | None, bool, dict[str, inspect.Parameter]]:
    """
    Resolve which callable parameter should receive request body.
    Returns (target_param_name, has_var_kwargs, method_params).
    """
    method_sig = inspect.signature(target_callable)
    method_params = method_sig.parameters
    has_var_kwargs = any(
        p.kind == inspect.Parameter.VAR_KEYWORD
        for p in method_params.values()
    )
    candidate_body_params = [
        p.name
        for p in method_params.values()
        if p.name not in {"self", "request", "db", "_user"}
        and p.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    ]
    preferred_names = ("data", "payload", "body", "input", "dto", "schema")

    for preferred in preferred_names:
        if preferred in candidate_body_params and preferred not in path_params:
            return preferred, has_var_kwargs, method_params
    for candidate in candidate_body_params:
        if candidate not in path_params:
            return candidate, has_var_kwargs, method_params
    return None, has_var_kwargs, method_params


def _unwrap_optional(annotation: Any) -> Any:
    """Resolve Optional[T] / T | None para T quando há um único tipo não-None."""
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _coerce_path_string(value: str, annotation: Any, *, param_name: str) -> Any:
    """
    Converte segmentos de path (sempre str na origem) para tipos anotados na assinatura.
    """
    ann = _unwrap_optional(annotation)
    if ann is str:
        return value
    if ann is int:
        try:
            return int(value, 10)
        except ValueError as e:
            raise StridePathParamBindingError(
                f"Parâmetro de path {param_name!r}: não foi possível converter {value!r} para int.",
                hint=(
                    f"Use um número inteiro válido na URL ou declare `{param_name}: str` "
                    "se o identificador não for numérico."
                ),
                original=e,
            ) from e
    if ann is bool:
        lv = value.strip().lower()
        if lv in ("true", "1", "yes", "on"):
            return True
        if lv in ("false", "0", "no", "off"):
            return False
        raise StridePathParamBindingError(
            f"Parâmetro de path {param_name!r}: valor booleano inválido {value!r}.",
            hint="Use true/false, 1/0 ou yes/no.",
        )
    if ann is float:
        try:
            return float(value)
        except ValueError as e:
            raise StridePathParamBindingError(
                f"Parâmetro de path {param_name!r}: não foi possível converter {value!r} para float.",
                hint=f"Declare `{param_name}: str` ou envie um número válido.",
                original=e,
            ) from e
    if ann is UUID:
        try:
            return UUID(value)
        except ValueError as e:
            raise StridePathParamBindingError(
                f"Parâmetro de path {param_name!r}: não foi possível converter {value!r} para UUID.",
                hint="Use um UUID válido no segmento da URL ou declare o parâmetro como str.",
                original=e,
            ) from e
    return value


def _apply_path_coercions(fn: Callable[..., Any], merged: dict[str, Any]) -> dict[str, Any]:
    """Aplica coerção str → int/bool/float/UUID conforme anotações explícitas na assinatura."""
    sig = inspect.signature(fn)
    out = dict(merged)
    for name in list(out.keys()):
        if name not in sig.parameters:
            continue
        p = sig.parameters[name]
        if p.kind == inspect.Parameter.VAR_KEYWORD:
            continue
        val = out[name]
        if not isinstance(val, str):
            continue
        if p.annotation is inspect.Parameter.empty:
            continue
        out[name] = _coerce_path_string(val, p.annotation, param_name=name)
    return out


def _build_binding_hint(
    fn: Callable[..., Any],
    path_like: dict[str, Any],
    viewset_class: type | None,
    kwargs: dict[str, Any],
    args: tuple[Any, ...],
    original: TypeError,
) -> str:
    sig = inspect.signature(fn)
    names = [n for n, p in sig.parameters.items() if n != "self" and p.kind != inspect.Parameter.VAR_POSITIONAL]
    lines = [
        f"Handler: {getattr(fn, '__qualname__', repr(fn))}",
        f"Parâmetros na assinatura (exc. self): {names}",
        f"Contexto de URL / path: {path_like}",
        f"Chaves em kwargs na chamada: {sorted(kwargs.keys())}",
    ]
    if args:
        lines.append(f"args posicionais extras: {len(args)} elemento(s)")
    orig_msg = str(original.args[0]) if original.args else str(original)
    if "multiple values" in orig_msg.lower():
        lines.append(
            "O que fazer: em rotas CRUD o Stride chama o método já ligado (ex.: `vs.create(**kwargs)`). "
            "Se você ver este erro com o framework atualizado, reporte; não deve ser necessário passar `vs`/`self` à mão."
        )
    if viewset_class is not None:
        url_kw = getattr(viewset_class, "lookup_url_kwarg", None) or getattr(
            viewset_class, "lookup_field", "id"
        )
        lf = getattr(viewset_class, "lookup_field", "id")
        lines.append(
            f"ViewSet: lookup_field={lf!r}, nome do segmento na rota={url_kw!r}. "
            f"Declare o mesmo nome, ou `pk`, ou `{lf}`, ou use só `**kwargs` e "
            f"`await self.get_object(db, **kwargs)` (o lookup da URL entra em kwargs)."
        )
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            lines.append(
                "Assinatura com `**kwargs`: os placeholders da rota são repassados em kwargs; "
                "não é obrigatório tipar `pk: int` — `get_object` usa `lookup_url_kwarg`."
            )
    else:
        lines.append(
            "APIView: cada {{nome}} na rota deve corresponder a um parâmetro na assinatura "
            "(ou use **kwargs no handler)."
        )
    lines.append(
        "Dica: valores de path chegam como str; use anotações como pk: int ou id: uuid.UUID "
        "para coerção automática no Stride."
    )
    return "\n".join(lines)


def _is_signature_binding_typeerror(exc: TypeError) -> bool:
    """
    Só TypeErrors típicos de assinatura viram StridePathParamBindingError.
    Outros (ex.: await em str) propagam sem mascarar.
    """
    msg = str(exc).lower()
    if "can't be used in 'await'" in msg:
        return False
    if "await" in msg and "expression" in msg:
        return False
    markers = (
        "unexpected keyword argument",
        "got an unexpected keyword argument",
        "got multiple values for argument",
        "missing",
        "required positional argument",
        "positional argument",
        "takes",
        "no arguments",
    )
    return any(m in msg for m in markers)


async def _call_viewset_handler_with_hint(
    fn: Callable[..., Any],
    *,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    path_like: dict[str, Any],
    viewset_class: type | None,
) -> Any:
    try:
        result = fn(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result
    except TypeError as e:
        if not _is_signature_binding_typeerror(e):
            raise
        hint = _build_binding_hint(fn, path_like, viewset_class, kwargs, args, e)
        orig = e.args[0] if e.args else str(e)
        full = f"{orig}\n\n--- Stride (assinatura e path) ---\n{hint}"
        raise StridePathParamBindingError(full, hint=hint, original=e) from e


def _merge_path_params_for_signature(
    fn: Callable[..., Any],
    path_like: dict[str, Any],
    viewset_class: type | None = None,
) -> dict[str, Any]:
    """
    Repassa só chaves que a função aceita; mapeia o segmento de lookup da URL
    (ex.: `id`) para nomes comuns na assinatura (`pk`, `lookup_field`).

    Evita ``unexpected keyword argument 'id'`` quando a action declara só ``pk``
    ou não declara o lookup (usa só ``get_object()``).
    """
    sig = inspect.signature(fn)
    param_names = {n for n in sig.parameters if n != "self"}
    has_var_kw = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )

    out: dict[str, Any] = {}
    for k, v in path_like.items():
        if k in param_names:
            out[k] = v

    if viewset_class is not None:
        url_kw = getattr(viewset_class, "lookup_url_kwarg", None) or getattr(
            viewset_class, "lookup_field", "id"
        )
        lf = getattr(viewset_class, "lookup_field", "id")
        if url_kw in path_like and url_kw not in out:
            val = path_like[url_kw]
            for alias in (lf, "pk", url_kw):
                if alias in param_names and alias not in out:
                    out[alias] = val
                    break
    else:
        # Sem ViewSet: alias genérico id → pk (estilo DRF)
        if (
            "id" in path_like
            and "id" not in out
            and "pk" in param_names
            and "pk" not in out
        ):
            out["pk"] = path_like["id"]

    # Com `**kwargs`, encaminha segmentos que não viraram parâmetros explícitos (ex.: id → pk).
    # Evita duplicar o segmento de lookup se já mapeamos para `pk`.
    if has_var_kw:
        uw = None
        if viewset_class is not None:
            uw = getattr(viewset_class, "lookup_url_kwarg", None) or getattr(
                viewset_class, "lookup_field", "id"
            )
        for k, v in path_like.items():
            if k in out:
                continue
            if uw is not None and k == uw and "pk" in out:
                continue
            out[k] = v

    return _apply_path_coercions(fn, out)


def _build_body_call_kwargs(
    target_callable: Callable,
    *,
    path_params: dict[str, Any],
    body: Any,
    default_name: str = "data",
    exclude_unset: bool = False,
    viewset_class: type | None = None,
) -> dict[str, Any]:
    """Build kwargs for a callable, injecting body into the most suitable parameter."""
    merged_path = _merge_path_params_for_signature(
        target_callable, path_params, viewset_class
    )
    kwargs: dict[str, Any] = dict(merged_path)
    if body is None:
        return kwargs

    target_param, has_var_kwargs, method_params = _pick_body_param_name(
        target_callable,
        path_params=merged_path,
    )

    body_value = body
    if target_param is not None:
        target_annotation = method_params[target_param].annotation
        if not hasattr(body_value, "model_dump"):
            target_model_type = _extract_first_basemodel_type(target_annotation)
            if target_model_type is not None:
                try:
                    body_value = target_model_type.model_validate(body_value)
                except PydanticValidationError:
                    # Let FastAPI/global exception handlers render structured 422
                    raise
        if (
            hasattr(body, "model_dump")
            and _annotation_accepts_mapping(target_annotation)
            and not _annotation_contains_basemodel(target_annotation)
        ):
            body_value = body.model_dump(exclude_unset=exclude_unset)
    elif hasattr(body, "model_dump"):
        body_value = body.model_dump(exclude_unset=exclude_unset)

    if target_param is not None:
        kwargs[target_param] = body_value
    elif has_var_kwargs:
        kwargs[default_name] = body_value
    return kwargs


def _build_viewset_call_kwargs(
    fn: Callable[..., Any],
    request: Request,
    db: AsyncSession,
    _user: Any,
    extra_kwargs: dict[str, Any] | None = None,
    *,
    viewset_class: type | None = None,
) -> dict[str, Any]:
    """Build kwargs for a ViewSet method based on its signature.

    This allows ViewSet handlers to omit optional dependencies like `db`
    or `_user` without causing `got multiple values`/unexpected keyword argument
    errors.
    """
    params = inspect.signature(fn).parameters
    kwargs: dict[str, Any] = {}
    if "request" in params:
        kwargs["request"] = request
    if "db" in params:
        kwargs["db"] = db
    if "_user" in params:
        kwargs["_user"] = _user
    if extra_kwargs:
        merged = _merge_path_params_for_signature(fn, extra_kwargs, viewset_class)
        kwargs.update(merged)
    return kwargs


def _require_lookup_url_identifier(lookup_url_kwarg: str) -> str:
    """
    O placeholder na URL ({id}) precisa ser um identificador Python válido: o FastAPI
    só inclui parâmetros de path no OpenAPI (Swagger / ChatGPT / Postman) quando
    eles aparecem na assinatura com o mesmo nome do segmento da rota.
    """
    if not lookup_url_kwarg.isidentifier():
        raise ValueError(
            "ViewSet.lookup_url_kwarg / lookup_field deve ser um identificador Python válido "
            "(ex.: id, pk, bug_id). Valor inválido para OpenAPI: "
            f"{lookup_url_kwarg!r}"
        )
    return lookup_url_kwarg


def _create_detail_action_endpoint_upload(
    viewset_class: type,
    action_method: Callable[..., Any],
    lookup_url_kwarg: str,
    perm_classes: list | None,
) -> Callable[..., Any]:
    """Action detail com multipart: expõe {lookup} no OpenAPI."""
    lp = _require_lookup_url_identifier(lookup_url_kwarg)
    ns: dict[str, Any] = {
        "Request": Request,
        "Depends": Depends,
        "get_db": get_db,
        "get_optional_user": get_optional_user,
        "UploadFile": UploadFile,
        "File": File,
        "Path": Path,
        "AsyncSession": AsyncSession,
        "Any": Any,
        "viewset_class": viewset_class,
        "action_method": action_method,
        "perm_classes": perm_classes or [],
        "_build_viewset_call_kwargs": _build_viewset_call_kwargs,
        "_call_viewset_handler_with_hint": _call_viewset_handler_with_hint,
    }
    src = f"""
async def _stride_detail_upload(
    request: Request,
    {lp}: str = Path(..., description="Identificador do recurso na URL"),
    db: AsyncSession = Depends(get_db),
    _user: Any = Depends(get_optional_user),
    file: UploadFile = File(...),
):
    vs = viewset_class()
    pc = perm_classes
    if pc:
        from strider.permissions import check_permissions
        perms = [p() if isinstance(p, type) else p for p in pc]
        await check_permissions(perms, request, vs)
    extra = dict(request.path_params)
    extra["file"] = file
    path_params = dict(request.path_params)
    full = _build_viewset_call_kwargs(
        action_method,
        request=request,
        db=db,
        _user=_user,
        extra_kwargs=extra,
        viewset_class=viewset_class,
    )
    return await _call_viewset_handler_with_hint(
        action_method,
        args=(vs,),
        kwargs=full,
        path_like=path_params,
        viewset_class=viewset_class,
    )
"""
    exec(src, ns)
    ep: Callable[..., Any] = ns["_stride_detail_upload"]
    ep.__name__ = getattr(action_method, "__name__", "detail_upload_action")
    return ep


def _create_detail_action_endpoint_body(
    viewset_class: type,
    action_method: Callable[..., Any],
    lookup_url_kwarg: str,
    perm_classes: list | None,
    a_input_schema: type | None,
) -> Callable[..., Any]:
    """Action detail com JSON body."""
    lp = _require_lookup_url_identifier(lookup_url_kwarg)
    ns: dict[str, Any] = {
        "Request": Request,
        "Depends": Depends,
        "get_db": get_db,
        "get_optional_user": get_optional_user,
        "Body": Body,
        "Path": Path,
        "AsyncSession": AsyncSession,
        "Any": Any,
        "Optional": Optional,
        "viewset_class": viewset_class,
        "action_method": action_method,
        "perm_classes": perm_classes or [],
        "_build_body_call_kwargs": _build_body_call_kwargs,
        "_build_viewset_call_kwargs": _build_viewset_call_kwargs,
        "_call_viewset_handler_with_hint": _call_viewset_handler_with_hint,
    }
    if a_input_schema:
        ns["data_type"] = Optional[a_input_schema]
    else:
        ns["data_type"] = Optional[dict[str, Any]]
    src = f"""
async def _stride_detail_body(
    request: Request,
    {lp}: str = Path(..., description="Identificador do recurso na URL"),
    db: AsyncSession = Depends(get_db),
    _user: Any = Depends(get_optional_user),
    data: data_type = Body(None),
):
    vs = viewset_class()
    pc = perm_classes
    if pc:
        from strider.permissions import check_permissions
        perms = [p() if isinstance(p, type) else p for p in pc]
        await check_permissions(perms, request, vs)
    path_params = dict(request.path_params)
    if data is not None:
        call_kwargs = _build_body_call_kwargs(
            action_method,
            path_params=path_params,
            body=data,
            viewset_class=viewset_class,
        )
        full = _build_viewset_call_kwargs(
            action_method,
            request=request,
            db=db,
            _user=_user,
            extra_kwargs=call_kwargs,
            viewset_class=viewset_class,
        )
        return await _call_viewset_handler_with_hint(
            action_method,
            args=(vs,),
            kwargs=full,
            path_like=path_params,
            viewset_class=viewset_class,
        )
    full = _build_viewset_call_kwargs(
        action_method,
        request=request,
        db=db,
        _user=_user,
        extra_kwargs=path_params,
        viewset_class=viewset_class,
    )
    return await _call_viewset_handler_with_hint(
        action_method,
        args=(vs,),
        kwargs=full,
        path_like=path_params,
        viewset_class=viewset_class,
    )
"""
    exec(src, ns)
    ep: Callable[..., Any] = ns["_stride_detail_body"]
    ep.__name__ = getattr(action_method, "__name__", "detail_body_action")
    return ep


def _create_detail_action_endpoint_no_body(
    viewset_class: type,
    action_method: Callable[..., Any],
    lookup_url_kwarg: str,
    perm_classes: list | None,
) -> Callable[..., Any]:
    """Action detail sem body (GET/DELETE)."""
    lp = _require_lookup_url_identifier(lookup_url_kwarg)
    ns: dict[str, Any] = {
        "Request": Request,
        "Depends": Depends,
        "get_db": get_db,
        "get_optional_user": get_optional_user,
        "Path": Path,
        "AsyncSession": AsyncSession,
        "Any": Any,
        "viewset_class": viewset_class,
        "action_method": action_method,
        "perm_classes": perm_classes or [],
        "_build_viewset_call_kwargs": _build_viewset_call_kwargs,
        "_call_viewset_handler_with_hint": _call_viewset_handler_with_hint,
    }
    src = f"""
async def _stride_detail_no_body(
    request: Request,
    {lp}: str = Path(..., description="Identificador do recurso na URL"),
    db: AsyncSession = Depends(get_db),
    _user: Any = Depends(get_optional_user),
):
    vs = viewset_class()
    pc = perm_classes
    if pc:
        from strider.permissions import check_permissions
        perms = [p() if isinstance(p, type) else p for p in pc]
        await check_permissions(perms, request, vs)
    path_params = dict(request.path_params)
    full = _build_viewset_call_kwargs(
        action_method,
        request=request,
        db=db,
        _user=_user,
        extra_kwargs=path_params,
        viewset_class=viewset_class,
    )
    return await _call_viewset_handler_with_hint(
        action_method,
        args=(vs,),
        kwargs=full,
        path_like=path_params,
        viewset_class=viewset_class,
    )
"""
    exec(src, ns)
    ep: Callable[..., Any] = ns["_stride_detail_no_body"]
    ep.__name__ = getattr(action_method, "__name__", "detail_no_body_action")
    return ep


# =============================================================================
# Router
# =============================================================================

class Router(APIRouter):
    """
    Router estendido com funcionalidades extras.
    
    Compatível com FastAPI APIRouter, mas com métodos adicionais
    para registro de ViewSets com documentação OpenAPI rica.
    
    Inclui proteção contra registro duplicado de rotas.
    
    Exemplo:
        router = Router(prefix="/api/v1", tags=["api"])
        router.register_viewset("/users", UserViewSet)
    """
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._viewsets: list[tuple[str, type]] = []
        self._ws_routes: list = []
        # Rastreia rotas registradas para prevenir duplicação
        self._registered_routes: set[tuple[str, str]] = set()  # (path, method)
        self._route_conflict_policy = os.getenv(
            "STRIDER_ROUTE_CONFLICT_POLICY",
            "raise",
        ).lower()
        if self._route_conflict_policy not in {"raise", "warn", "ignore"}:
            logger.warning(
                "Invalid STRIDER_ROUTE_CONFLICT_POLICY=%r; using 'raise'",
                self._route_conflict_policy,
            )
            self._route_conflict_policy = "raise"
    
    def add_api_route(
        self,
        path: str,
        endpoint: Callable,
        *,
        methods: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Override para prevenir registro duplicado de rotas.
        
        Se uma rota com o mesmo (path, method) já foi registrada,
        emite um warning e ignora o registro duplicado.
        """
        import warnings
        
        route_methods = methods or ["GET"]
        
        # Verifica duplicatas
        duplicates = []
        for m in route_methods:
            key = (path, m.upper())
            if key in self._registered_routes:
                duplicates.append(m.upper())
            else:
                self._registered_routes.add(key)
        
        if duplicates:
            route_name = kwargs.get("name", endpoint.__name__)
            message = (
                f"Rota duplicada detectada: {duplicates} {path} (name={route_name}). "
                "Verifique includes, auto-discovery e registro duplicado de ViewSet/router."
            )
            if self._route_conflict_policy == "raise":
                raise RuntimeError(message)
            if self._route_conflict_policy == "warn":
                warnings.warn(message, UserWarning, stacklevel=2)
            return
        
        super().add_api_route(path, endpoint, methods=methods, **kwargs)

    def include_router(self, router: "APIRouter", **kwargs: Any) -> None:
        """Include another router, propagating WebSocket routes with prefix."""
        super().include_router(router, **kwargs)
        extra_prefix = kwargs.get("prefix", "")
        router_prefix = getattr(router, "prefix", "")
        combined = extra_prefix + router_prefix
        child_ws = getattr(router, "_ws_routes", [])
        if child_ws:
            from starlette.routing import WebSocketRoute
            for r in child_ws:
                full_path = combined + r.path
                self._ws_routes.append(
                    WebSocketRoute(full_path, r.endpoint, name=r.name)
                )

    def register_viewset(
        self,
        prefix: str,
        viewset_class: type["ViewSet"],
        basename: str | None = None,
        tags: list[str] | None = None,
        include_crud: bool | None = None,
    ) -> None:
        """
        Registra um ViewSet com rotas REST automáticas e OpenAPI tipado.
        
        Gera documentação OpenAPI completa com:
        - Request body schemas (campos de entrada tipados)
        - Response schemas (campos de saída tipados)
        - Modelo parcial automático para PATCH
        - Respostas de erro documentadas (422, 404, 409)
        
        Para ViewSet com model: cria rotas CRUD + actions customizadas.
        Para ViewSet sem model: cria apenas actions customizadas.
        
        Args:
            prefix: Prefixo da URL (ex: "/users")
            viewset_class: Classe do ViewSet
            basename: Nome base para as rotas (default: nome do model)
            tags: Tags para OpenAPI
            include_crud: Forçar criação de rotas CRUD (default: auto-detecta por model)
        """
        viewset = viewset_class()
        openapi_settings = _get_openapi_example_settings()
        
        # Detecta se tem model (para decidir sobre CRUD routes)
        has_model = hasattr(viewset_class, "model") and viewset_class.model is not None
        
        # Respeita _exclude_crud do ViewSet (ex: AuthViewSet nunca cria CRUD)
        exclude_crud = getattr(viewset_class, "_exclude_crud", False)
        
        # Auto-detecta include_crud baseado em model, ou usa valor explícito
        if include_crud is None:
            include_crud = has_model and not exclude_crud
        
        # Infer basename from model or class name
        if basename is None:
            model = getattr(viewset_class, "model", None)
            if model is not None:
                basename = getattr(model, "__tablename__", None) or model.__name__.lower()
            else:
                class_name = viewset_class.__name__
                basename = class_name.lower().replace("viewset", "").replace("view", "") or "api"
        
        tags = tags or viewset_class.tags or [basename]
        
        lookup_field = viewset_class.lookup_field
        lookup_url_kwarg = viewset_class.lookup_url_kwarg or lookup_field
        
        # Normaliza o prefixo
        prefix = prefix.rstrip("/")
        
        # Se não tem model e não forçou CRUD, registra apenas actions customizadas
        if not include_crud:
            self._register_custom_actions(
                prefix, viewset_class, basename, tags, lookup_url_kwarg,
                detail_filter=None  # Registra todas as actions
            )
            return
        
        # ==================================================================
        # Resolve schemas para documentação OpenAPI tipada
        # ==================================================================
        input_schema, output_schema = _resolve_schemas(viewset_class)
        partial_input_schema = _make_partial_model(input_schema) if input_schema else None
        
        # Response models (list pode usar subset de campos via list_include/list_exclude)
        list_item_schema = _get_list_item_schema(output_schema) if output_schema else None
        list_response_model = PaginatedResponse[list_item_schema] if list_item_schema else None
        detail_response_model = output_schema
        
        # Nome do model para descrições
        model_cls = getattr(viewset_class, "model", None)
        model_label = model_cls.__name__ if model_cls else basename.title()
        
        # ==================================================================
        # 1. LIST (GET) - Lista paginada
        # ==================================================================
        async def list_route(
            request, db=Depends(get_db), _user=Depends(get_optional_user),
            page=1, page_size=viewset_class.page_size,
        ):
            vs = viewset_class()
            path_like = {**dict(request.path_params), "page": page, "page_size": page_size}
            full = _build_viewset_call_kwargs(
                vs.list,
                request=request,
                db=db,
                _user=_user,
                extra_kwargs={"page": page, "page_size": page_size},
                viewset_class=viewset_class,
            )
            return await _call_viewset_handler_with_hint(
                vs.list,
                args=(),
                kwargs=full,
                path_like=path_like,
                viewset_class=viewset_class,
            )
        
        # Annotations programáticas (bypass de __future__.annotations)
        list_route.__annotations__ = {
            "request": Request,
            "db": AsyncSession,
            "_user": Any,
            "page": int,
            "page_size": int,
        }
        
        list_openapi_extra, list_success_responses = _build_openapi_examples(
            output_schema=list_response_model,
            success_status=200,
            settings=openapi_settings,
        )
        self.add_api_route(
            f"{prefix}/",
            list_route,
            methods=["GET"],
            tags=tags,
            name=f"{basename}-list",
            summary=f"List {basename}s",
            description=(
                f"Retorna lista paginada de **{model_label}**.\n\n"
                f"Suporta paginação via query params `page` e `page_size`.\n"
                f"O `page_size` máximo é {viewset_class.max_page_size}."
            ),
            response_model=list_response_model,
            responses=_merge_response_specs(
                _build_error_responses(include_422=False),
                list_success_responses,
            ),
            openapi_extra=list_openapi_extra,
        )
        
        # ==================================================================
        # 2. CREATE (POST) - Criação com schema tipado
        # ==================================================================
        async def create_route(
            request, data=Body(...), db=Depends(get_db),
            _user=Depends(get_optional_user),
        ):
            vs = viewset_class()
            call_kwargs = _build_body_call_kwargs(
                vs.create,
                path_params={},
                body=data,
                viewset_class=viewset_class,
            )
            full = _build_viewset_call_kwargs(
                vs.create,
                request=request,
                db=db,
                _user=_user,
                extra_kwargs=call_kwargs,
                viewset_class=viewset_class,
            )
            return await _call_viewset_handler_with_hint(
                vs.create,
                args=(),
                kwargs=full,
                path_like=dict(request.path_params),
                viewset_class=viewset_class,
            )
        
        create_route.__annotations__ = {
            "request": Request,
            "data": input_schema if input_schema else dict[str, Any],
            "db": AsyncSession,
            "_user": Any,
        }
        
        create_openapi_extra, create_success_responses = _build_openapi_examples(
            input_schema=input_schema,
            output_schema=detail_response_model,
            success_status=201,
            settings=openapi_settings,
        )
        self.add_api_route(
            f"{prefix}/",
            create_route,
            methods=["POST"],
            tags=tags,
            name=f"{basename}-create",
            summary=f"Create {basename}",
            description=f"Cria um novo **{model_label}**.",
            status_code=201,
            response_model=detail_response_model,
            responses=_merge_response_specs(
                _build_error_responses(include_422=True, include_409=True),
                create_success_responses,
            ),
            openapi_extra=create_openapi_extra,
        )
        
        # ==================================================================
        # 3. Actions detail=False (ANTES das rotas {id} para evitar conflitos)
        #    Ex: /users/me deve ser registrada antes de /users/{id}
        # ==================================================================
        self._register_custom_actions(
            prefix, viewset_class, basename, tags, lookup_url_kwarg,
            detail_filter=False  # Só registra detail=False
        )
        
        # ==================================================================
        # 4. RETRIEVE (GET detail) - Detalhes com response tipado
        # ==================================================================
        async def retrieve_route(
            request, db=Depends(get_db), _user=Depends(get_optional_user),
        ):
            vs = viewset_class()
            path_params = dict(request.path_params)
            full = _build_viewset_call_kwargs(
                vs.retrieve,
                request=request,
                db=db,
                _user=_user,
                extra_kwargs=path_params,
                viewset_class=viewset_class,
            )
            return await _call_viewset_handler_with_hint(
                vs.retrieve,
                args=(),
                kwargs=full,
                path_like=path_params,
                viewset_class=viewset_class,
            )
        
        retrieve_route.__annotations__ = {
            "request": Request,
            "db": AsyncSession,
            "_user": Any,
        }
        
        retrieve_openapi_extra, retrieve_success_responses = _build_openapi_examples(
            output_schema=detail_response_model,
            success_status=200,
            settings=openapi_settings,
        )
        self.add_api_route(
            f"{prefix}/{{{lookup_url_kwarg}}}",
            retrieve_route,
            methods=["GET"],
            tags=tags,
            name=f"{basename}-detail",
            summary=f"Get {basename} by {lookup_url_kwarg}",
            description=f"Retorna detalhes de um **{model_label}** específico pelo `{lookup_url_kwarg}`.",
            response_model=detail_response_model,
            responses=_merge_response_specs(
                _build_error_responses(include_404=True, include_422=False),
                retrieve_success_responses,
            ),
            openapi_extra=retrieve_openapi_extra,
        )
        
        # ==================================================================
        # 5. UPDATE (PUT) - Atualização completa com schema tipado
        # ==================================================================
        async def update_route(
            request, data=Body(...), db=Depends(get_db),
            _user=Depends(get_optional_user),
        ):
            vs = viewset_class()
            path_params = dict(request.path_params)
            call_kwargs = _build_body_call_kwargs(
                vs.update,
                path_params=path_params,
                body=data,
                viewset_class=viewset_class,
            )
            full = _build_viewset_call_kwargs(
                vs.update,
                request=request,
                db=db,
                _user=_user,
                extra_kwargs=call_kwargs,
                viewset_class=viewset_class,
            )
            return await _call_viewset_handler_with_hint(
                vs.update,
                args=(),
                kwargs=full,
                path_like=path_params,
                viewset_class=viewset_class,
            )
        
        update_route.__annotations__ = {
            "request": Request,
            "data": input_schema if input_schema else dict[str, Any],
            "db": AsyncSession,
            "_user": Any,
        }
        
        update_openapi_extra, update_success_responses = _build_openapi_examples(
            input_schema=input_schema,
            output_schema=detail_response_model,
            success_status=200,
            settings=openapi_settings,
        )
        self.add_api_route(
            f"{prefix}/{{{lookup_url_kwarg}}}",
            update_route,
            methods=["PUT"],
            tags=tags,
            name=f"{basename}-update",
            summary=f"Update {basename}",
            description=(
                f"Atualiza completamente um **{model_label}** existente.\n\n"
                f"Todos os campos obrigatórios devem ser enviados."
            ),
            response_model=detail_response_model,
            responses=_merge_response_specs(
                _build_error_responses(
                    include_404=True, include_409=True, include_422=True,
                ),
                update_success_responses,
            ),
            openapi_extra=update_openapi_extra,
        )
        
        # ==================================================================
        # 6. PARTIAL UPDATE (PATCH) - Atualização parcial com modelo parcial
        # ==================================================================
        async def partial_update_route(
            request, data=Body(...), db=Depends(get_db),
            _user=Depends(get_optional_user),
        ):
            vs = viewset_class()
            path_params = dict(request.path_params)
            call_kwargs = _build_body_call_kwargs(
                vs.partial_update,
                path_params=path_params,
                body=data,
                exclude_unset=True,
                viewset_class=viewset_class,
            )
            full = _build_viewset_call_kwargs(
                vs.partial_update,
                request=request,
                db=db,
                _user=_user,
                extra_kwargs=call_kwargs,
                viewset_class=viewset_class,
            )
            return await _call_viewset_handler_with_hint(
                vs.partial_update,
                args=(),
                kwargs=full,
                path_like=path_params,
                viewset_class=viewset_class,
            )
        
        partial_update_route.__annotations__ = {
            "request": Request,
            "data": partial_input_schema if partial_input_schema else dict[str, Any],
            "db": AsyncSession,
            "_user": Any,
        }
        
        patch_openapi_extra, patch_success_responses = _build_openapi_examples(
            input_schema=partial_input_schema if partial_input_schema else input_schema,
            output_schema=detail_response_model,
            success_status=200,
            settings=openapi_settings,
        )
        self.add_api_route(
            f"{prefix}/{{{lookup_url_kwarg}}}",
            partial_update_route,
            methods=["PATCH"],
            tags=tags,
            name=f"{basename}-partial-update",
            summary=f"Partial update {basename}",
            description=(
                f"Atualiza parcialmente um **{model_label}**.\n\n"
                f"Apenas os campos enviados serão atualizados. "
                f"Campos omitidos permanecem inalterados."
            ),
            response_model=detail_response_model,
            responses=_merge_response_specs(
                _build_error_responses(
                    include_404=True, include_409=True, include_422=True,
                ),
                patch_success_responses,
            ),
            openapi_extra=patch_openapi_extra,
        )
        
        # ==================================================================
        # 7. DELETE - Deleção com response tipado
        # ==================================================================
        async def destroy_route(
            request, db=Depends(get_db), _user=Depends(get_optional_user),
        ):
            vs = viewset_class()
            path_params = dict(request.path_params)
            full = _build_viewset_call_kwargs(
                vs.destroy,
                request=request,
                db=db,
                _user=_user,
                extra_kwargs=path_params,
                viewset_class=viewset_class,
            )
            return await _call_viewset_handler_with_hint(
                vs.destroy,
                args=(),
                kwargs=full,
                path_like=path_params,
                viewset_class=viewset_class,
            )
        
        destroy_route.__annotations__ = {
            "request": Request,
            "db": AsyncSession,
            "_user": Any,
        }
        
        delete_openapi_extra, delete_success_responses = _build_openapi_examples(
            output_schema=DeleteResponse,
            success_status=200,
            settings=openapi_settings,
        )
        self.add_api_route(
            f"{prefix}/{{{lookup_url_kwarg}}}",
            destroy_route,
            methods=["DELETE"],
            tags=tags,
            name=f"{basename}-delete",
            summary=f"Delete {basename}",
            description=f"Remove permanentemente um **{model_label}** pelo `{lookup_url_kwarg}`.",
            response_model=DeleteResponse,
            responses=_merge_response_specs(
                _build_error_responses(include_404=True, include_422=False),
                delete_success_responses,
            ),
            openapi_extra=delete_openapi_extra,
        )
        
        # ==================================================================
        # 8. Actions detail=True (DEPOIS das rotas {id})
        #    Ex: /users/{id}/activate
        # ==================================================================
        self._register_custom_actions(
            prefix, viewset_class, basename, tags, lookup_url_kwarg,
            detail_filter=True  # Só registra detail=True
        )
        
        # Guarda referência
        self._viewsets.append((prefix, viewset_class))
    
    def _register_custom_actions(
        self,
        prefix: str,
        viewset_class: type["ViewSet"],
        basename: str,
        tags: list[str],
        lookup_url_kwarg: str,
        detail_filter: bool | None = None,
    ) -> None:
        """
        Registra actions customizadas decoradas com @action.
        
        Suporta schemas tipados para request/response via parâmetros
        do decorator @action(input_schema=..., output_schema=...).
        
        Args:
            prefix: Prefixo da URL
            viewset_class: Classe do ViewSet
            basename: Nome base para as rotas
            tags: Tags para OpenAPI
            lookup_url_kwarg: Nome do parâmetro de URL para lookup
            detail_filter: Se especificado, filtra actions por detail:
                          - True: só registra actions com detail=True
                          - False: só registra actions com detail=False
                          - None: registra todas as actions
        """
        viewset_input_schema, viewset_output_schema = _resolve_schemas(viewset_class)
        openapi_settings = _get_openapi_example_settings()

        registered_signatures: set[tuple[str, str]] = set()
        conflict_policy = str(getattr(viewset_class, "route_conflict_policy", "warn")).lower()
        if conflict_policy not in {"warn", "raise", "ignore"}:
            logger.warning(
                "Invalid route_conflict_policy=%r in %s; using 'warn'",
                conflict_policy,
                viewset_class.__name__,
            )
            conflict_policy = "warn"

        for name, method in _iter_sorted_custom_actions(viewset_class, detail_filter):
            action_methods = method.methods
            detail = method.detail
            url_path = method.url_path

            if detail:
                path = f"{prefix}/{{{lookup_url_kwarg}}}/{url_path}"
            else:
                path = f"{prefix}/{url_path}"

            # Action schemas: from @action or fallback to viewset/model so OpenAPI docs are not null
            action_input_schema = getattr(method, "action_input_schema", None)
            action_output_schema = getattr(method, "action_output_schema", None)
            if action_input_schema is None and viewset_input_schema is not None:
                action_input_schema = viewset_input_schema
            if action_output_schema is None and viewset_output_schema is not None:
                action_output_schema = viewset_output_schema

            # Cria endpoint para cada método HTTP
            for http_method in action_methods:
                method_upper = http_method.upper()
                signature = (path, method_upper)
                if signature in registered_signatures:
                    msg = (
                        f"Duplicate custom action route detected in {viewset_class.__name__}: "
                        f"{method_upper} {path} (action={name})"
                    )
                    if conflict_policy == "raise":
                        raise ValueError(msg)
                    if conflict_policy == "warn":
                        logger.warning(msg)
                else:
                    registered_signatures.add(signature)

                route_name = f"{basename}-{name}"
                
                # Get action-specific permission_classes
                action_permission_classes = getattr(method, "permission_classes", None)
                
                # Determina se o método HTTP suporta body
                method_has_body = http_method.upper() in ("POST", "PUT", "PATCH")
                
                # Captura method em closure para evitar late binding
                def _method_accepts_upload_file(method: Callable) -> bool:
                    """Verifica se o método aceita UploadFile como parâmetro."""
                    sig = inspect.signature(method)
                    for param in sig.parameters.values():
                        anno = param.annotation
                        # Verificar se é UploadFile diretamente
                        if anno is UploadFile:
                            return True
                        # Verificar por nome da classe
                        if hasattr(anno, "__name__") and anno.__name__ == "UploadFile":
                            return True
                        # Verificar se é uma classe que herda de UploadFile
                        try:
                            if isinstance(anno, type) and issubclass(anno, UploadFile):
                                return True
                        except TypeError:
                            pass
                        # Verificar em unions (Optional[UploadFile], Union[UploadFile, None])
                        origin = get_origin(anno)
                        if origin is not None:
                            args = get_args(anno)
                            for arg in args:
                                if arg is UploadFile:
                                    return True
                                if hasattr(arg, "__name__") and arg.__name__ == "UploadFile":
                                    return True
                                try:
                                    if isinstance(arg, type) and issubclass(arg, UploadFile):
                                        return True
                                except TypeError:
                                    pass
                    return False
                
                def make_action_endpoint(
                    action_method: Callable,
                    perm_classes: list | None = None,
                    a_input_schema: type | None = None,
                    with_body: bool = True,
                    detail: bool = False,
                ) -> Callable:
                    accepts_file = _method_accepts_upload_file(action_method) or getattr(action_method, "accepts_upload", False)
                    
                    if accepts_file:
                        if detail:
                            return _create_detail_action_endpoint_upload(
                                viewset_class,
                                action_method,
                                lookup_url_kwarg,
                                perm_classes,
                            )
                        # Endpoint COM upload (sem segmento {lookup} na URL)
                        async def action_endpoint(
                            request,
                            db=Depends(get_db),
                            _user=Depends(get_optional_user),
                            file: UploadFile = File(...),
                        ):
                            vs = viewset_class()
                            
                            if perm_classes:
                                from strider.permissions import check_permissions
                                perms = [p() if isinstance(p, type) else p for p in perm_classes]
                                await check_permissions(perms, request, vs)
                            
                            path_params = dict(request.path_params)
                            path_params["file"] = file
                            pl = dict(request.path_params)
                            full = _build_viewset_call_kwargs(
                                action_method,
                                request=request,
                                db=db,
                                _user=_user,
                                extra_kwargs=path_params,
                                viewset_class=viewset_class,
                            )
                            return await _call_viewset_handler_with_hint(
                                action_method,
                                args=(vs,),
                                kwargs=full,
                                path_like=pl,
                                viewset_class=viewset_class,
                            )
                        
                        action_endpoint.__annotations__ = {
                            "request": Request,
                            "db": AsyncSession,
                            "_user": Any,
                            "file": UploadFile,
                        }
                    elif with_body:
                        if detail:
                            return _create_detail_action_endpoint_body(
                                viewset_class,
                                action_method,
                                lookup_url_kwarg,
                                perm_classes,
                                a_input_schema,
                            )
                        # Endpoint COM body JSON (POST, PUT, PATCH)
                        async def action_endpoint(
                            request,
                            db=Depends(get_db),
                            _user=Depends(get_optional_user),
                            data=Body(None),
                        ):
                            vs = viewset_class()
                            
                            if perm_classes:
                                from strider.permissions import check_permissions
                                perms = [p() if isinstance(p, type) else p for p in perm_classes]
                                await check_permissions(perms, request, vs)
                            
                            path_params = dict(request.path_params)
                            if data is not None:
                                call_kwargs = _build_body_call_kwargs(
                                    action_method,
                                    path_params=path_params,
                                    body=data,
                                    viewset_class=viewset_class,
                                )
                                full = _build_viewset_call_kwargs(
                                    action_method,
                                    request=request,
                                    db=db,
                                    _user=_user,
                                    extra_kwargs=call_kwargs,
                                    viewset_class=viewset_class,
                                )
                                return await _call_viewset_handler_with_hint(
                                    action_method,
                                    args=(vs,),
                                    kwargs=full,
                                    path_like=path_params,
                                    viewset_class=viewset_class,
                                )
                            full = _build_viewset_call_kwargs(
                                action_method,
                                request=request,
                                db=db,
                                _user=_user,
                                extra_kwargs=path_params,
                                viewset_class=viewset_class,
                            )
                            return await _call_viewset_handler_with_hint(
                                action_method,
                                args=(vs,),
                                kwargs=full,
                                path_like=path_params,
                                viewset_class=viewset_class,
                            )
                        
                        # Typed annotations para OpenAPI
                        if a_input_schema:
                            data_type = Optional[a_input_schema]
                        else:
                            data_type = Optional[dict[str, Any]]
                        
                        action_endpoint.__annotations__ = {
                            "request": Request,
                            "db": AsyncSession,
                            "_user": Any,
                            "data": data_type,
                        }
                    else:
                        if detail:
                            return _create_detail_action_endpoint_no_body(
                                viewset_class,
                                action_method,
                                lookup_url_kwarg,
                                perm_classes,
                            )
                        # Endpoint SEM body (GET, DELETE)
                        async def action_endpoint(
                            request,
                            db=Depends(get_db),
                            _user=Depends(get_optional_user),
                        ):
                            vs = viewset_class()
                            
                            if perm_classes:
                                from strider.permissions import check_permissions
                                perms = [p() if isinstance(p, type) else p for p in perm_classes]
                                await check_permissions(perms, request, vs)
                            
                            path_params = dict(request.path_params)
                            full = _build_viewset_call_kwargs(
                                action_method,
                                request=request,
                                db=db,
                                _user=_user,
                                extra_kwargs=path_params,
                                viewset_class=viewset_class,
                            )
                            return await _call_viewset_handler_with_hint(
                                action_method,
                                args=(vs,),
                                kwargs=full,
                                path_like=path_params,
                                viewset_class=viewset_class,
                            )
                        
                        action_endpoint.__annotations__ = {
                            "request": Request,
                            "db": AsyncSession,
                            "_user": Any,
                        }
                    
                    return action_endpoint
                
                action_openapi_extra, action_success_responses = _build_openapi_examples(
                    input_schema=action_input_schema if method_has_body else None,
                    output_schema=action_output_schema,
                    success_status=200,
                    settings=openapi_settings,
                )
                self.add_api_route(
                    path,
                    make_action_endpoint(
                        method,
                        action_permission_classes,
                        action_input_schema,
                        with_body=method_has_body,
                        detail=detail,
                    ),
                    methods=[method_upper],
                    tags=tags,
                    name=route_name,
                    summary=f"{name.replace('_', ' ').title()}",
                    response_model=action_output_schema,
                    responses=action_success_responses if action_success_responses else None,
                    openapi_extra=action_openapi_extra,
                )
    
    def register_view(
        self,
        path: str,
        view_class: type["APIView"],
        methods: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Registra uma APIView.
        
        Args:
            path: Caminho da rota
            view_class: Classe da view
            methods: Métodos HTTP permitidos
            **kwargs: Argumentos extras para a rota
        """
        view = view_class()
        methods = methods or ["GET", "POST", "PUT", "PATCH", "DELETE"]
        tags = kwargs.pop("tags", view_class.tags or [])
        input_schema = getattr(view_class, "input_schema", None)
        output_schema = getattr(view_class, "output_schema", None)
        openapi_settings = _get_openapi_example_settings()
        
        async def endpoint(
            request: Request,
            db: AsyncSession = Depends(get_db),
            _user: Any = Depends(get_optional_user),
            data: Any = Body(None),
        ) -> Any:
            method = request.method.lower()
            handler = getattr(view, method, None)
            
            if handler is None:
                from fastapi import HTTPException
                raise HTTPException(status_code=405, detail="Method not allowed")
            
            await view.check_permissions(request, method)
            path_params = dict(request.path_params)
            if request.method.upper() in {"POST", "PUT", "PATCH"} and data is not None:
                call_kwargs = _build_body_call_kwargs(
                    handler,
                    path_params=path_params,
                    body=data,
                    viewset_class=None,
                )
                full = _build_viewset_call_kwargs(
                    handler,
                    request=request,
                    db=db,
                    _user=_user,
                    extra_kwargs=call_kwargs,
                    viewset_class=None,
                )
                return await _call_viewset_handler_with_hint(
                    handler,
                    args=(),
                    kwargs=full,
                    path_like=path_params,
                    viewset_class=None,
                )
            full = _build_viewset_call_kwargs(
                handler,
                request=request,
                db=db,
                _user=_user,
                extra_kwargs=path_params,
                viewset_class=None,
            )
            return await _call_viewset_handler_with_hint(
                handler,
                args=(),
                kwargs=full,
                path_like=path_params,
                viewset_class=None,
            )
        
        view_openapi_extra, view_success_responses = _build_openapi_examples(
            input_schema=input_schema,
            output_schema=output_schema,
            success_status=200,
            settings=openapi_settings,
        )
        existing_responses = kwargs.pop("responses", None)
        merged_responses = _merge_response_specs(existing_responses, view_success_responses)
        self.add_api_route(
            path,
            endpoint,
            methods=methods,
            tags=tags,
            responses=merged_responses if merged_responses else None,
            openapi_extra=view_openapi_extra,
            **kwargs,
        )

    def register_websocket(
        self,
        path: str,
        view_class: type,
    ) -> None:
        """
        Register a ``WebSocketView`` subclass on this router.

        The route is stored as a Starlette ``WebSocketRoute`` and collected
        by ``StrideApp`` at startup so it can be served **outside** the HTTP
        middleware stack (which would otherwise crash on WebSocket scopes).

        Args:
            path: URL path (may contain path parameters, e.g. ``/ws/{room}``)
            view_class: A ``WebSocketView`` subclass
        """
        route = view_class.as_route(path)
        if not hasattr(self, "_ws_routes"):
            self._ws_routes: list = []
        self._ws_routes.append(route)

    def register_sse(
        self,
        path: str,
        view_class: type,
        **kwargs: Any,
    ) -> None:
        """
        Register an ``SSEView`` subclass as a standard GET route.

        SSE is plain HTTP so it goes through the normal middleware stack.

        Args:
            path: URL path (may contain path parameters)
            view_class: An ``SSEView`` subclass
        """
        from starlette.responses import StreamingResponse as _SR
        from starlette.requests import Request as _Req

        async def endpoint(request: _Req) -> _SR:
            view = view_class()
            params = request.path_params or {}
            return _SR(
                view._generate(request, params),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    **view.headers,
                },
            )

        tags = kwargs.pop("tags", [])
        self.add_api_route(path, endpoint, methods=["GET"], tags=tags, **kwargs)


class AutoRouter:
    """
    Router automático que descobre e registra ViewSets.
    
    Similar ao DefaultRouter do DRF.
    
    Tags são resolvidas UMA vez no register(), sem duplicação no OpenAPI:
    - tags explícitas em register() → prioridade máxima
    - tags do AutoRouter(tags=...) → fallback padrão
    - ViewSet.tags → fallback da classe
    - [basename] → último recurso
    
    Exemplo:
        auto_router = AutoRouter(tags=["Auth"])
        auto_router.register("/login", LoginViewSet)                    # → tags=["Auth"]
        auto_router.register("/users", UserViewSet, tags=["Users"])     # → tags=["Users"]
        
        app.include_router(auto_router.router)
    """
    
    def __init__(
        self,
        prefix: str = "",
        tags: list[str] | None = None,
    ) -> None:
        self._default_tags = tags or []
        # Tags NÃO são passadas ao Router — resolução acontece em register()
        # para evitar que FastAPI acumule router-tags + route-tags no OpenAPI
        self.router = Router(prefix=prefix)
        self._registry: list[tuple[str, type, dict[str, Any]]] = []
    
    def _resolve_tags(
        self,
        explicit_tags: list[str] | None,
        viewset_or_view: type | None = None,
    ) -> list[str] | None:
        """
        Resolve tags com prioridade, sem duplicação.
        
        Ordem: explicit > AutoRouter default > ViewSet/APIView.tags > None
        Retorna None para deixar register_viewset usar [basename] como último recurso.
        """
        if explicit_tags is not None:
            return explicit_tags
        if self._default_tags:
            return self._default_tags
        if viewset_or_view is not None:
            cls_tags = getattr(viewset_or_view, "tags", None)
            if cls_tags:
                return cls_tags
        return None
    
    def register(
        self,
        prefix: str,
        viewset_class: type["ViewSet"],
        basename: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """
        Registra um ViewSet.
        
        Tags são resolvidas aqui com prioridade:
        1. tags (argumento explícito)
        2. AutoRouter._default_tags
        3. ViewSet.tags
        4. [basename] (resolvido em register_viewset)
        
        Args:
            prefix: Prefixo da URL
            viewset_class: Classe do ViewSet
            basename: Nome base para as rotas
            tags: Tags para OpenAPI (prioridade máxima)
        """
        resolved_tags = self._resolve_tags(tags, viewset_class)
        
        self._registry.append((prefix, viewset_class, {
            "basename": basename,
            "tags": resolved_tags,
        }))
        self.router.register_viewset(prefix, viewset_class, basename, resolved_tags)
    
    def register_view(
        self,
        path: str,
        view_class: type["APIView"],
        **kwargs: Any,
    ) -> None:
        """Registra uma APIView, aplicando tags padrão do AutoRouter se não fornecidas."""
        if "tags" not in kwargs:
            resolved = self._resolve_tags(None, view_class)
            if resolved:
                kwargs["tags"] = resolved
        self.router.register_view(path, view_class, **kwargs)

    def register_websocket(
        self,
        path: str,
        view_class: type,
    ) -> None:
        """Register a ``WebSocketView`` on the inner router."""
        self.router.register_websocket(path, view_class)

    def register_sse(
        self,
        path: str,
        view_class: type,
        **kwargs: Any,
    ) -> None:
        """Register an ``SSEView`` on the inner router."""
        if "tags" not in kwargs:
            resolved = self._resolve_tags(None, view_class)
            if resolved:
                kwargs["tags"] = resolved
        self.router.register_sse(path, view_class, **kwargs)

    def include_router(
        self,
        router: "AutoRouter | Router",
        prefix: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """
        Inclui outro router neste router.
        
        Args:
            router: Router a incluir (AutoRouter ou Router)
            prefix: Prefixo adicional para as rotas
            tags: Tags adicionais para OpenAPI
        """
        # Se for AutoRouter, pega o router interno
        if isinstance(router, AutoRouter):
            inner_router = router.router
        else:
            inner_router = router
        
        # Inclui no router interno — tags já foram resolvidas em register(),
        # só passa tags aqui se explicitamente fornecidas pelo caller
        self.router.include_router(inner_router, prefix=prefix, tags=tags or [])
    
    @property
    def urls(self) -> list[dict[str, Any]]:
        """Retorna lista de URLs registradas."""
        return [
            {
                "path": route.path,
                "name": route.name,
                "methods": route.methods,
            }
            for route in self.router.routes
        ]
    
    def get_api_root_view(self) -> Callable:
        """
        Retorna uma view que lista todas as URLs da API.
        
        Similar ao api_root do DRF.
        """
        registry = self._registry
        
        async def api_root(request: Request) -> dict[str, str]:
            return {
                basename or viewset.__name__.lower(): str(request.url_for(f"{basename or viewset.__name__.lower()}-list"))
                for prefix, viewset, opts in registry
                for basename in [opts.get("basename")]
            }
        
        return api_root


def include_router(
    app_or_router: Any,
    router: Router | AutoRouter,
    prefix: str = "",
    tags: list[str] | None = None,
) -> None:
    """
    Inclui um router em uma aplicação ou outro router.
    
    Função utilitária para simplificar a inclusão de routers.
    
    Args:
        app_or_router: FastAPI app ou APIRouter
        router: Router ou AutoRouter a incluir
        prefix: Prefixo adicional
        tags: Tags adicionais
    """
    actual_router = router.router if isinstance(router, AutoRouter) else router
    app_or_router.include_router(actual_router, prefix=prefix, tags=tags or [])
