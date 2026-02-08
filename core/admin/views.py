"""
Endpoints da API interna do admin.

Todos os endpoints são JSON-first (API-first admin).
O frontend Jinja2+HTMX consome esses endpoints.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from core.admin.permissions import check_admin_access, check_model_permission
from core.admin.serializers import serialize_instance

logger = logging.getLogger("core.admin")


def create_api_views(site: Any) -> APIRouter:
    """
    Cria router com endpoints da API do admin.
    
    Endpoints:
    - GET  /api/metadata          -- Metadados do admin (app list, erros)
    - GET  /api/{app}/{model}/    -- List view (paginado, filtros, busca)
    - GET  /api/{app}/{model}/{pk}/ -- Detail view
    - POST /api/{app}/{model}/    -- Create
    - PUT  /api/{app}/{model}/{pk}/ -- Update
    - DELETE /api/{app}/{model}/{pk}/ -- Delete
    - POST /api/{app}/{model}/bulk-delete/ -- Bulk delete
    """
    router = APIRouter(prefix="/api", tags=["admin-api"])
    
    @router.get("/metadata")
    async def get_metadata(
        request: Request,
        user: Any = Depends(check_admin_access),
    ) -> dict:
        """Retorna metadados do admin: app list, erros, status."""
        return {
            "apps": site.get_app_list(),
            "errors": site.errors.to_dict(),
            "error_count": site.errors.error_count,
            "warning_count": site.errors.warning_count,
            "site_title": getattr(site._settings, "admin_site_title", "Admin"),
            "site_header": getattr(site._settings, "admin_site_header", "Core Admin"),
            "user": {
                "id": getattr(user, "id", None),
                "email": getattr(user, "email", str(user)),
                "is_superuser": getattr(user, "is_superuser", False),
            },
        }
    
    @router.get("/{app_label}/{model_name}")
    async def list_view(
        request: Request,
        app_label: str,
        model_name: str,
        page: int = Query(1, ge=1),
        per_page: int = Query(25, ge=1, le=200),
        search: str = Query("", alias="q"),
        ordering: str = Query(""),
        user: Any = Depends(check_admin_access),
    ) -> dict:
        """List view — retorna lista paginada de objetos."""
        result = site.get_model_by_name(app_label, model_name)
        if not result:
            raise HTTPException(404, f"Model '{app_label}.{model_name}' not found in admin")
        
        model, admin_instance = result
        
        # Verificar permissão
        has_perm = await check_model_permission(user, app_label, model_name, "view")
        if not has_perm:
            raise HTTPException(403, f"No permission to view {model_name}")
        
        # Obter sessão do banco
        from core.models import get_session
        try:
            db = await get_session()
        except RuntimeError as e:
            raise HTTPException(503, f"Database not available: {e}")
        
        try:
            async with db:
                # Base queryset — converte Manager para QuerySet
                from core.querysets import QuerySet as _QS
                base = admin_instance.get_queryset(db)
                if isinstance(base, _QS):
                    qs = base
                else:
                    # Manager — cria QuerySet directamente
                    qs = _QS(model, getattr(base, '_session', db))
                
                # Busca — OR across search_fields (apenas colunas text-like)
                if search and admin_instance.search_fields:
                    from sqlalchemy import or_, cast, String
                    conditions = []
                    for field_name in admin_instance.search_fields:
                        col = getattr(model, field_name, None)
                        if col is not None:
                            try:
                                col_type = str(col.property.columns[0].type).upper()
                                if any(t in col_type for t in ("VARCHAR", "TEXT", "CHAR", "STRING")):
                                    conditions.append(col.ilike(f"%{search}%"))
                                elif "UUID" in col_type:
                                    # UUID — cast to text for LIKE search
                                    conditions.append(cast(col, String).ilike(f"%{search}%"))
                                elif "INT" in col_type:
                                    # Numeric — try exact match only if value is numeric
                                    try:
                                        conditions.append(col == int(search))
                                    except (ValueError, TypeError):
                                        pass
                                else:
                                    # Fallback: cast to string for LIKE
                                    conditions.append(cast(col, String).ilike(f"%{search}%"))
                            except Exception:
                                # If introspection fails, try ilike anyway
                                try:
                                    conditions.append(col.ilike(f"%{search}%"))
                                except Exception:
                                    pass
                    if conditions:
                        qs = qs._clone()
                        qs._filters.append(or_(*conditions))
                
                # Filtros de query params — respeita tipo da coluna com cast
                for filter_field in admin_instance.list_filter:
                    value = request.query_params.get(filter_field)
                    if value is not None and value != "":
                        col = getattr(model, filter_field, None)
                        if col is None:
                            continue
                        
                        try:
                            col_type = str(col.property.columns[0].type).upper()
                        except Exception:
                            col_type = "VARCHAR"
                        
                        # Cast valor para o tipo correto da coluna
                        if "BOOL" in col_type:
                            typed_value = value.lower() in ("true", "1")
                        elif "INT" in col_type:
                            try:
                                typed_value = int(value)
                            except (ValueError, TypeError):
                                continue
                        elif "UUID" in col_type:
                            from uuid import UUID as _UUID
                            try:
                                typed_value = _UUID(value)
                            except (ValueError, TypeError):
                                continue
                        elif "FLOAT" in col_type or "NUMERIC" in col_type or "DECIMAL" in col_type:
                            try:
                                typed_value = float(value)
                            except (ValueError, TypeError):
                                continue
                        else:
                            typed_value = value
                        
                        qs = qs.filter(**{filter_field: typed_value})
                
                # Ordering
                if ordering:
                    order_fields = [f.strip() for f in ordering.split(",") if f.strip()]
                    qs = qs.order_by(*order_fields)
                elif admin_instance.ordering:
                    qs = qs.order_by(*admin_instance.ordering)
                
                # Count total
                total = await qs.count()
                
                # Paginação
                offset = (page - 1) * per_page
                items = await qs.offset(offset).limit(per_page).all()
                
                # Serializar
                display_fields = list(admin_instance.list_display) or admin_instance._model_fields
                serialized = [
                    serialize_instance(item, display_fields, admin_instance)
                    for item in items
                ]
                
                # Busca opcoes distintas para filtros nao-boolean
                filter_options = {}
                for filter_field in admin_instance.list_filter:
                    col = getattr(model, filter_field, None)
                    if col is not None:
                        try:
                            col_type = str(col.property.columns[0].type).upper()
                            if "BOOL" in col_type:
                                filter_options[filter_field] = [
                                    {"value": "true", "label": "Yes"},
                                    {"value": "false", "label": "No"},
                                ]
                            else:
                                from sqlalchemy import select as sa_select
                                distinct_q = sa_select(col).distinct().order_by(col).limit(50)
                                result_rows = await db.execute(distinct_q)
                                filter_options[filter_field] = [
                                    {"value": str(v), "label": str(v)}
                                    for (v,) in result_rows
                                    if v is not None
                                ]
                        except Exception:
                            filter_options[filter_field] = []
                
                # ── Metadata de choices/enum para colunas da list view ──
                from core.admin.options import _detect_enum
                columns_meta = []
                for f in display_fields:
                    col_meta = {
                        "name": f,
                        "label": admin_instance.help_texts.get(f, f.replace("_", " ").title()),
                        "is_link": f in admin_instance.list_display_links,
                    }
                    # Detectar enum choices na coluna
                    col_obj = getattr(model, f, None)
                    if col_obj is not None:
                        try:
                            sa_col = col_obj.property.columns[0]
                            enum_choices = _detect_enum(sa_col)
                            if enum_choices:
                                col_meta["choices"] = enum_choices
                        except Exception:
                            pass
                    columns_meta.append(col_meta)
                
                # ── Melhorar filter_options para enums — usar labels ──
                for filter_field in admin_instance.list_filter:
                    col_obj = getattr(model, filter_field, None)
                    if col_obj is not None and filter_field in filter_options:
                        try:
                            sa_col = col_obj.property.columns[0]
                            enum_choices = _detect_enum(sa_col)
                            if enum_choices:
                                # Substituir filter_options por choices com labels legíveis
                                choices_map = {c["value"]: c["label"] for c in enum_choices}
                                filter_options[filter_field] = [
                                    {"value": c["value"], "label": c["label"]}
                                    for c in enum_choices
                                ]
                        except Exception:
                            pass
                
                return {
                    "items": serialized,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": (total + per_page - 1) // per_page if per_page else 1,
                    "columns": columns_meta,
                    "filter_options": filter_options,
                    "model_meta": {
                        "display_name": admin_instance.display_name,
                        "display_name_plural": admin_instance.display_name_plural,
                        "icon": admin_instance.icon,
                        "pk_field": admin_instance._pk_field,
                        "can_add": "add" in admin_instance.permissions and "add" not in admin_instance.exclude_actions,
                        "can_delete": "delete" in admin_instance.permissions and "delete" not in admin_instance.exclude_actions,
                        "search_fields": list(admin_instance.search_fields),
                        "list_filter": list(admin_instance.list_filter),
                    },
                }
        except Exception as e:
            logger.error("Error in admin list view for %s.%s: %s", app_label, model_name, e)
            # Registra erro para UI
            site.errors.add_runtime_error(model.__name__, e)
            raise HTTPException(500, detail={
                "error": "query_error",
                "title": f"Error loading {admin_instance.display_name_plural}",
                "detail": str(e),
                "hint": _get_error_hint(e),
            })
    
    # =========================================================================
    # Autocomplete endpoint para FK fields
    # IMPORTANTE: deve ser registrado ANTES das rotas com {pk} para evitar
    # que FastAPI interprete "autocomplete" como um path param.
    # =========================================================================
    
    @router.get("/{app_label}/{model_name}/autocomplete")
    async def autocomplete_view(
        request: Request,
        app_label: str,
        model_name: str,
        q: str = Query("", alias="q"),
        limit: int = Query(20, ge=1, le=100),
        user: Any = Depends(check_admin_access),
    ) -> dict:
        """
        Autocomplete — retorna itens de um model para popular FK dropdowns.
        
        Busca por search_fields do model ou por colunas de texto comuns.
        Retorna {items: [{pk: "...", label: "..."}]}.
        """
        result = site.get_model_by_name(app_label, model_name)
        if not result:
            raise HTTPException(404, f"Model '{app_label}.{model_name}' not found")
        
        model, admin_instance = result
        
        from core.models import get_session
        
        try:
            db = await get_session()
            async with db:
                from core.querysets import QuerySet as _QS
                base = admin_instance.get_queryset(db)
                if isinstance(base, _QS):
                    qs = base
                else:
                    qs = _QS(model, getattr(base, '_session', db))
                
                # Busca por texto se query fornecida
                if q and q.strip():
                    from sqlalchemy import or_, cast, String
                    
                    # Determina campos de busca
                    search_cols = list(admin_instance.search_fields) if admin_instance.search_fields else []
                    
                    # Fallback: usa campos de texto comuns
                    if not search_cols:
                        for col in model.__table__.columns:
                            col_type = str(col.type).upper()
                            if any(t in col_type for t in ("VARCHAR", "TEXT", "CHAR", "STRING")):
                                search_cols.append(col.name)
                                if len(search_cols) >= 5:
                                    break
                    
                    if search_cols:
                        conditions = []
                        for field_name in search_cols:
                            col = getattr(model, field_name, None)
                            if col is not None:
                                try:
                                    col_type_str = str(col.property.columns[0].type).upper()
                                    if any(t in col_type_str for t in ("VARCHAR", "TEXT", "CHAR", "STRING")):
                                        conditions.append(col.ilike(f"%{q}%"))
                                    elif "UUID" in col_type_str:
                                        conditions.append(cast(col, String).ilike(f"%{q}%"))
                                    elif "INT" in col_type_str:
                                        try:
                                            conditions.append(col == int(q))
                                        except (ValueError, TypeError):
                                            pass
                                    else:
                                        conditions.append(cast(col, String).ilike(f"%{q}%"))
                                except Exception:
                                    pass
                        
                        if conditions:
                            qs = qs._clone()
                            qs._filters.append(or_(*conditions))
                
                items_raw = await qs.limit(limit).all()
                
                # Determina o campo de exibição
                pk_field = admin_instance._pk_field
                display_field = _find_display_field(model)
                
                items = []
                for obj in items_raw:
                    pk_val = getattr(obj, pk_field, None)
                    display_val = getattr(obj, display_field, None) if display_field != pk_field else pk_val
                    
                    # Constrói label legível
                    label_parts = []
                    if display_val and str(display_val) != str(pk_val):
                        label_parts.append(str(display_val))
                    label_parts.append(f"#{pk_val}")
                    
                    items.append({
                        "pk": _safe_value(pk_val),
                        "label": " — ".join(label_parts) if len(label_parts) > 1 else str(pk_val),
                        "display": str(display_val) if display_val else str(pk_val),
                    })
                
                return {"items": items, "total": len(items)}
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Autocomplete error for %s.%s: %s", app_label, model_name, e)
            return {"items": [], "total": 0, "error": str(e)}
    
    @router.get("/{app_label}/{model_name}/m2m-options")
    async def m2m_options_view(
        request: Request,
        app_label: str,
        model_name: str,
        field: str = Query(..., description="M2M field name"),
        q: str = Query("", description="Search query"),
        user: Any = Depends(check_admin_access),
    ) -> dict:
        """
        Fetch available options for a M2M field (Issue #21).
        
        Returns all options from the target model for rendering
        multi-select checkboxes in the admin form.
        """
        result = site.get_model_by_name(app_label, model_name)
        if not result:
            raise HTTPException(404, f"Model '{app_label}.{model_name}' not found")
        
        model, admin_instance = result
        
        # Find M2M field info from column_info
        m2m_info = None
        for col in admin_instance.get_column_info():
            if col.get("name") == field and col.get("widget") == "m2m_select":
                m2m_info = col
                break
        
        if not m2m_info:
            raise HTTPException(400, f"Field '{field}' is not a M2M field on {model_name}")
        
        target_model_name = m2m_info.get("m2m_target_model", "")
        display_field = m2m_info.get("m2m_display_field", "id")
        value_field = m2m_info.get("m2m_value_field", "id")
        
        # Resolve target model class
        target_model = None
        try:
            from sqlalchemy import inspect as sa_inspect
            from sqlalchemy.orm import RelationshipProperty
            mapper = sa_inspect(model)
            rel = mapper.relationships.get(field)
            if rel and isinstance(rel, RelationshipProperty):
                target_model = rel.mapper.class_
        except Exception:
            pass
        
        if not target_model:
            raise HTTPException(500, f"Could not resolve target model for {field}")
        
        from core.models import get_session
        
        try:
            db = await get_session()
            async with db:
                from core.querysets import QuerySet as _QS
                qs = _QS(target_model, db)
                
                # Apply search if provided
                if q and q.strip():
                    from sqlalchemy import or_, cast, String
                    display_col = getattr(target_model, display_field, None)
                    if display_col is not None:
                        try:
                            qs = qs._clone()
                            qs._filters.append(display_col.ilike(f"%{q}%"))
                        except Exception:
                            pass
                
                items_raw = await qs.order_by(display_field).limit(500).all()
                
                items = []
                for obj in items_raw:
                    pk_val = getattr(obj, value_field, None)
                    display_val = getattr(obj, display_field, None)
                    # For permissions: show name (description) if available
                    name_val = getattr(obj, "name", None) if display_field != "name" else None
                    
                    items.append({
                        "id": pk_val if not hasattr(pk_val, "hex") else str(pk_val),
                        "label": str(display_val) if display_val else str(pk_val),
                        "description": str(name_val) if name_val else "",
                    })
                
                return {"items": items, "total": len(items)}
        except Exception as e:
            logger.error("M2M options error for %s.%s.%s: %s", app_label, model_name, field, e)
            return {"items": [], "total": 0, "error": str(e)}
    
    # =========================================================================
    # Detail / CRUD endpoints (rotas com {pk} — devem vir DEPOIS das literais)
    # =========================================================================
    
    @router.get("/{app_label}/{model_name}/{pk}")
    async def detail_view(
        request: Request,
        app_label: str,
        model_name: str,
        pk: str,
        user: Any = Depends(check_admin_access),
    ) -> dict:
        """Detail view — retorna um objeto por PK."""
        result = site.get_model_by_name(app_label, model_name)
        if not result:
            raise HTTPException(404, f"Model '{app_label}.{model_name}' not found in admin")
        
        model, admin_instance = result
        
        has_perm = await check_model_permission(user, app_label, model_name, "view")
        if not has_perm:
            raise HTTPException(403, f"No permission to view {model_name}")
        
        from core.models import get_session
        try:
            db = await get_session()
        except RuntimeError as e:
            raise HTTPException(503, f"Database not available: {e}")
        
        try:
            async with db:
                pk_field = admin_instance._pk_field
                pk_typed = _cast_pk(model, pk_field, pk)
                obj = await admin_instance.get_queryset(db).filter(**{pk_field: pk_typed}).first()
                
                if obj is None:
                    raise HTTPException(404, f"{admin_instance.display_name} with {pk_field}={pk} not found")
                
                # Load M2M data safely to avoid lazy load issues
                m2m_data = await _load_m2m_data(db, obj, model)
                
                display_fields = admin_instance.get_display_fields()
                data = serialize_instance(obj, display_fields, admin_instance, m2m_data)
                
                return {
                    "item": data,
                    "fields": admin_instance.get_column_info(),
                    "editable_fields": admin_instance.get_editable_fields(),
                    "readonly_fields": list(admin_instance.readonly_fields),
                    "model_meta": {
                        "display_name": admin_instance.display_name,
                        "pk_field": admin_instance._pk_field,
                        "can_change": "change" in admin_instance.permissions and "change" not in admin_instance.exclude_actions,
                        "can_delete": "delete" in admin_instance.permissions and "delete" not in admin_instance.exclude_actions,
                    },
                    "fieldsets": admin_instance.fieldsets,
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error in admin detail view: %s", e)
            site.errors.add_runtime_error(model.__name__, e)
            raise HTTPException(500, detail=str(e))
    
    @router.post("/{app_label}/{model_name}")
    async def create_view(
        request: Request,
        app_label: str,
        model_name: str,
        user: Any = Depends(check_admin_access),
    ) -> dict:
        """Create — cria um novo objeto."""
        result = site.get_model_by_name(app_label, model_name)
        if not result:
            raise HTTPException(404, f"Model '{app_label}.{model_name}' not found in admin")
        
        model, admin_instance = result
        
        has_perm = await check_model_permission(user, app_label, model_name, "add")
        if not has_perm:
            raise HTTPException(403, f"No permission to add {model_name}")
        
        body = await request.json()
        
        # Filtra campos: só aceita editable fields (proteção mass assignment)
        editable = set(admin_instance.get_editable_fields())
        safe_data = {k: v for k, v in body.items() if k in editable}
        
        # Validar campos obrigatórios e cast de tipos
        try:
            required_fields = []
            fk_fields = []  # Campos FK obrigatórios
            columns_map = {col.name: col for col in model.__table__.columns}
            
            for col in model.__table__.columns:
                is_required = (
                    not col.nullable
                    and not col.primary_key
                    and col.default is None
                    and col.server_default is None
                )
                
                if is_required and col.name in editable:
                    required_fields.append(col.name)
                
                # FK obrigatória: sempre valida mesmo se não está em editable
                # Isso evita IntegrityError no banco
                if is_required and col.foreign_keys:
                    fk_fields.append(col.name)
            
            # Virtual password: required on create if model has set_password()
            if admin_instance.password_field:
                col_info = {c["name"]: c for c in admin_instance.get_column_info()}
                vp = col_info.get("password", {})
                if vp.get("virtual") and vp.get("required_on_create", True):
                    pw_val = safe_data.get("password")
                    if not pw_val or pw_val in ("", "••••••••"):
                        required_fields.append("password")
            
            # Valida campos obrigatórios normais
            missing = [f for f in required_fields if f not in safe_data or safe_data[f] in (None, "")]
            
            # Valida FKs obrigatórias (mensagem específica)
            missing_fks = [f for f in fk_fields if f not in safe_data or safe_data[f] in (None, "")]
            
            if missing_fks:
                # Mensagem amigável para FKs
                fk_names = [f.replace("_id", "").replace("_", " ").title() for f in missing_fks]
                raise HTTPException(400, detail={
                    "error": "validation_error",
                    "missing_fields": missing_fks,
                    "message": f"Selecione: {', '.join(fk_names)}",
                    "hint": "Campos de relacionamento são obrigatórios.",
                })
            
            if missing:
                raise HTTPException(400, detail={
                    "error": "validation_error",
                    "missing_fields": missing,
                    "message": f"Required fields: {', '.join(missing)}",
                })
            
            # Cast tipos e remove campos vazios opcionais
            safe_data = _cast_and_clean_data(safe_data, columns_map, required_fields)
            
        except HTTPException:
            raise
        except Exception:
            pass  # Se introspeccao falhar, deixa o banco validar
        
        # Processa campos inteligentes (password, secrets, etc)
        safe_data = _process_smart_fields(safe_data, model, admin_instance)
        
        # Extrai plain password se detectado
        plain_password = safe_data.pop("__plain_password__", None)
        password_field = safe_data.pop("__password_field__", None)
        
        from core.models import get_session
        db = await get_session()
        
        # Extract M2M data before creating (Issue #21)
        m2m_data = {}
        m2m_field_names = set()
        for col in admin_instance.get_column_info():
            if col.get("widget") == "m2m_select":
                m2m_field_names.add(col["name"])
        
        for fname in m2m_field_names:
            if fname in body:
                m2m_data[fname] = body[fname]
            safe_data.pop(fname, None)
        
        try:
            async with db:
                # Se tem password, remove o campo hash do kwargs (set_password cuida)
                create_data = {k: v for k, v in safe_data.items() if k != password_field} if plain_password else safe_data
                obj = model(**create_data)
                
                # Aplica password hash via set_password se disponível
                if plain_password and password_field:
                    await _apply_password(obj, plain_password)
                
                await admin_instance.before_save(db, obj, is_new=True)
                await obj.save(db)
                
                # Apply M2M relationships (Issue #21)
                if m2m_data:
                    await _apply_m2m_data(db, obj, model, m2m_data)
                
                await admin_instance.after_save(db, obj, is_new=True)
                
                await db.commit()
                
                # Audit log
                await _log_action(
                    db, user, request, "create",
                    admin_instance, obj,
                )
                await db.commit()
                
                pk = getattr(obj, admin_instance._pk_field)
                display_fields = admin_instance.get_display_fields()
                
                return {
                    "item": serialize_instance(obj, display_fields, admin_instance, m2m_data),
                    "message": f"{admin_instance.display_name} created successfully",
                    "pk": str(pk),
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error creating %s: %s", model_name, e)
            raise HTTPException(400, detail=str(e))
    
    @router.put("/{app_label}/{model_name}/{pk}")
    async def update_view(
        request: Request,
        app_label: str,
        model_name: str,
        pk: str,
        user: Any = Depends(check_admin_access),
    ) -> dict:
        """Update — atualiza um objeto existente."""
        result = site.get_model_by_name(app_label, model_name)
        if not result:
            raise HTTPException(404, f"Model '{app_label}.{model_name}' not found in admin")
        
        model, admin_instance = result
        
        has_perm = await check_model_permission(user, app_label, model_name, "change")
        if not has_perm:
            raise HTTPException(403, f"No permission to change {model_name}")
        
        body = await request.json()
        
        editable = set(admin_instance.get_editable_fields())
        safe_data = {k: v for k, v in body.items() if k in editable}
        
        # Cast tipos e valida FKs obrigatórias
        try:
            columns_map = {col.name: col for col in model.__table__.columns}
            required_fields = [
                col.name for col in model.__table__.columns
                if not col.nullable and not col.primary_key
                and col.default is None and col.server_default is None
                and col.name in editable
            ]
            
            # Valida FKs obrigatórias não podem ser null
            for col in model.__table__.columns:
                if col.foreign_keys and not col.nullable:
                    val = safe_data.get(col.name)
                    if col.name in safe_data and val in (None, ""):
                        fk_name = col.name.replace("_id", "").replace("_", " ").title()
                        raise HTTPException(400, detail={
                            "error": "validation_error",
                            "missing_fields": [col.name],
                            "message": f"{fk_name} é obrigatório e não pode ser removido.",
                        })
            
            safe_data = _cast_and_clean_data(safe_data, columns_map, required_fields)
        except HTTPException:
            raise
        except Exception:
            pass
        
        # Processa campos inteligentes (password, secrets, etc)
        safe_data = _process_smart_fields(safe_data, model, admin_instance)
        plain_password = safe_data.pop("__plain_password__", None)
        password_field = safe_data.pop("__password_field__", None)
        
        # Extract M2M data 
        m2m_data = {}
        m2m_field_names = set()
        for col in admin_instance.get_column_info():
            if col.get("widget") == "m2m_select":
                m2m_field_names.add(col["name"])
        
        for fname in m2m_field_names:
            if fname in body:
                m2m_data[fname] = body[fname]
            safe_data.pop(fname, None)
        
        from core.models import get_session
        db = await get_session()
        
        try:
            async with db:
                pk_field = admin_instance._pk_field
                pk_typed = _cast_pk(model, pk_field, pk)
                obj = await admin_instance.get_queryset(db).filter(**{pk_field: pk_typed}).first()
                
                if obj is None:
                    raise HTTPException(404, f"{admin_instance.display_name} with {pk_field}={pk} not found")
                
                # Captura estado anterior para audit log
                old_data = obj.to_dict()
                
                # Aplica alterações (exceto campo de password que set_password cuida)
                for key, value in safe_data.items():
                    if key == password_field and plain_password:
                        continue
                    setattr(obj, key, value)
                
                # Aplica password hash se detectado
                if plain_password:
                    await _apply_password(obj, plain_password)
                
                await admin_instance.before_save(db, obj, is_new=False)
                await obj.save(db)
                
                # Apply M2M relationships (Issue #21)
                if m2m_data:
                    await _apply_m2m_data(db, obj, model, m2m_data)
                
                await admin_instance.after_save(db, obj, is_new=False)
                
                await db.commit()
                
                # Calcula changes para audit
                new_data = obj.to_dict()
                changes = {
                    k: {"old": _safe_value(old_data.get(k)), "new": _safe_value(new_data.get(k))}
                    for k in safe_data
                    if old_data.get(k) != new_data.get(k)
                }
                # Include M2M changes in audit
                for fname in m2m_data:
                    changes[fname] = {"old": "...", "new": f"{len(m2m_data[fname])} item(s)"}
                
                await _log_action(
                    db, user, request, "update",
                    admin_instance, obj, changes=changes,
                )
                await db.commit()
                
                display_fields = admin_instance.get_display_fields()
                return {
                    "item": serialize_instance(obj, display_fields, admin_instance, m2m_data),
                    "message": f"{admin_instance.display_name} updated successfully",
                    "changes": changes,
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error updating %s: %s", model_name, e)
            raise HTTPException(400, detail=str(e))
    
    @router.delete("/{app_label}/{model_name}/{pk}")
    async def delete_view(
        request: Request,
        app_label: str,
        model_name: str,
        pk: str,
        user: Any = Depends(check_admin_access),
    ) -> dict:
        """Delete — remove um objeto."""
        result = site.get_model_by_name(app_label, model_name)
        if not result:
            raise HTTPException(404, f"Model '{app_label}.{model_name}' not found in admin")
        
        model, admin_instance = result
        
        has_perm = await check_model_permission(user, app_label, model_name, "delete")
        if not has_perm:
            raise HTTPException(403, f"No permission to delete {model_name}")
        
        if "delete" in admin_instance.exclude_actions:
            raise HTTPException(403, f"Delete action is disabled for {admin_instance.display_name}")
        
        from core.models import get_session
        db = await get_session()
        
        try:
            async with db:
                pk_field = admin_instance._pk_field
                pk_typed = _cast_pk(model, pk_field, pk)
                obj = await admin_instance.get_queryset(db).filter(**{pk_field: pk_typed}).first()
                
                if obj is None:
                    raise HTTPException(404, f"{admin_instance.display_name} with {pk_field}={pk} not found")
                
                obj_repr = repr(obj)
                
                await admin_instance.before_delete(db, obj)
                await obj.delete(db)
                await admin_instance.after_delete(db, obj)
                
                await db.commit()
                
                await _log_action(
                    db, user, request, "delete",
                    admin_instance, None, object_id=pk, object_repr=obj_repr,
                )
                await db.commit()
                
                return {
                    "message": f"{admin_instance.display_name} deleted successfully",
                    "pk": pk,
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error deleting %s: %s", model_name, e)
            raise HTTPException(400, detail=str(e))
    
    @router.post("/{app_label}/{model_name}/bulk-delete")
    async def bulk_delete_view(
        request: Request,
        app_label: str,
        model_name: str,
        user: Any = Depends(check_admin_access),
    ) -> dict:
        """Bulk delete — remove múltiplos objetos."""
        result = site.get_model_by_name(app_label, model_name)
        if not result:
            raise HTTPException(404, f"Model '{app_label}.{model_name}' not found in admin")
        
        model, admin_instance = result
        
        has_perm = await check_model_permission(user, app_label, model_name, "delete")
        if not has_perm:
            raise HTTPException(403, f"No permission to delete {model_name}")
        
        body = await request.json()
        pks = body.get("ids", [])
        
        if not pks:
            raise HTTPException(400, "No IDs provided")
        
        from core.models import get_session
        db = await get_session()
        
        deleted_count = 0
        try:
            async with db:
                pk_field = admin_instance._pk_field
                for pk in pks:
                    pk_typed = _cast_pk(model, pk_field, pk)
                    obj = await admin_instance.get_queryset(db).filter(**{pk_field: pk_typed}).first()
                    if obj:
                        await admin_instance.before_delete(db, obj)
                        await obj.delete(db)
                        await admin_instance.after_delete(db, obj)
                        deleted_count += 1
                
                await db.commit()
                
                await _log_action(
                    db, user, request, "bulk_delete",
                    admin_instance, None,
                    object_id=",".join(str(pk) for pk in pks),
                    object_repr=f"Bulk delete: {deleted_count} items",
                )
                await db.commit()
                
                return {
                    "message": f"Deleted {deleted_count} {admin_instance.display_name_plural}",
                    "deleted_count": deleted_count,
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error in bulk delete for %s: %s", model_name, e)
            raise HTTPException(400, detail=str(e))
    
    return router


async def _log_action(
    db: Any,
    user: Any,
    request: Request,
    action: str,
    admin_instance: Any,
    obj: Any | None,
    object_id: str | None = None,
    object_repr: str | None = None,
    changes: dict | None = None,
) -> None:
    """Helper para registrar ação no audit log."""
    try:
        from core.admin.models import AuditLog
        
        pk = object_id
        if pk is None and obj is not None:
            pk = str(getattr(obj, admin_instance._pk_field, ""))
        
        obj_repr = object_repr
        if obj_repr is None and obj is not None:
            obj_repr = repr(obj)
        
        await AuditLog.log_action(
            db,
            user=user,
            action=action,
            app_label=admin_instance._app_label,
            model_name=admin_instance._model_name,
            object_id=pk or "",
            object_repr=obj_repr or "",
            changes=changes,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except Exception as e:
        # Audit log failure should not break the operation
        logger.warning("Failed to write audit log: %s", e)


def _safe_value(value: Any) -> Any:
    """Converte valor para tipo serializável."""
    from datetime import datetime
    from uuid import UUID
    
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return "<binary>"
    return value


def _find_display_field(model: Any) -> str:
    """Encontra o melhor campo para exibição de um model em autocomplete."""
    try:
        col_names = [c.name for c in model.__table__.columns]
    except Exception:
        return "id"
    
    # Ordem de preferência para display
    for candidate in ("name", "title", "email", "label", "display_name", "username", "slug"):
        if candidate in col_names:
            return candidate
    
    # Fallback: primeiro campo VARCHAR que não é PK
    try:
        for col in model.__table__.columns:
            if col.primary_key:
                continue
            col_type = str(col.type).upper()
            if any(t in col_type for t in ("VARCHAR", "TEXT", "CHAR")):
                return col.name
    except Exception:
        pass
    
    return "id"


def _cast_pk(model: Any, pk_field: str, pk_value: str) -> Any:
    """
    Converte PK string do URL para o tipo nativo da coluna.
    
    - INTEGER → int
    - UUID → UUID (ou str se falhar)
    - Outros → str (passthrough)
    """
    try:
        col = model.__table__.c[pk_field]
        col_type = str(col.type).upper()
        
        if "INT" in col_type:
            return int(pk_value)
        elif "UUID" in col_type:
            from uuid import UUID
            return UUID(pk_value)
    except (ValueError, KeyError, TypeError):
        pass
    
    return pk_value


async def _apply_password(obj: Any, plain_password: str) -> None:
    """
    Aplica password hash ao objeto usando o método disponível no model.
    
    Tenta na ordem:
    1. obj.set_password(plain_password) — padrão Django/Core
    2. obj.make_password(plain_password) — alternativo
    3. Fallback: seta diretamente no campo password_hash
    """
    if hasattr(obj, "set_password"):
        result = obj.set_password(plain_password)
        if hasattr(result, "__await__"):
            await result
    elif hasattr(obj, "make_password"):
        result = obj.make_password(plain_password)
        if hasattr(result, "__await__"):
            await result
    else:
        # Fallback: tenta hashear com passlib ou bcrypt se disponível
        try:
            from passlib.hash import pbkdf2_sha256
            hashed = pbkdf2_sha256.hash(plain_password)
            if hasattr(obj, "password_hash"):
                obj.password_hash = hashed
            elif hasattr(obj, "hashed_password"):
                obj.hashed_password = hashed
            elif hasattr(obj, "password"):
                obj.password = hashed
        except ImportError:
            try:
                import hashlib
                hashed = hashlib.pbkdf2_hmac(
                    "sha256", plain_password.encode(), b"admin-salt", 100000
                ).hex()
                if hasattr(obj, "password_hash"):
                    obj.password_hash = hashed
                elif hasattr(obj, "hashed_password"):
                    obj.hashed_password = hashed
            except Exception:
                logger.warning("Could not hash password — no hashing method available")


async def _apply_m2m_data(
    db: Any,
    obj: Any,
    model: type,
    m2m_data: dict[str, list],
) -> None:
    """
    Apply M2M relationship data to an object (Issue #21).
    
    For each M2M field, manipulates the association table directly
    to avoid greenlet/async issues with lazy-loaded collections.
    
    This approach:
    1. Deletes existing associations from the secondary table
    2. Inserts new associations
    
    This is safer than manipulating the ORM collection directly,
    which can trigger lazy loads in async context.
    """
    from sqlalchemy import inspect as sa_inspect, select, delete, insert
    from sqlalchemy.orm import RelationshipProperty
    
    try:
        mapper = sa_inspect(model)
    except Exception:
        return
    
    # Get the primary key value of the object
    obj_pk_col = list(model.__table__.primary_key.columns)[0]
    obj_pk_value = getattr(obj, obj_pk_col.name)
    
    for field_name, ids in m2m_data.items():
        rel = mapper.relationships.get(field_name)
        if rel is None or not isinstance(rel, RelationshipProperty) or rel.secondary is None:
            continue
        
        secondary_table = rel.secondary
        target_cls = rel.mapper.class_
        target_pk_col = list(target_cls.__table__.primary_key.columns)[0]
        
        # Find the columns in the secondary table
        # One references our model, one references the target
        local_fk_col = None
        remote_fk_col = None
        
        for col in secondary_table.columns:
            for fk in col.foreign_keys:
                if fk.column.table.name == model.__tablename__:
                    local_fk_col = col
                elif fk.column.table.name == target_cls.__tablename__:
                    remote_fk_col = col
        
        if local_fk_col is None or remote_fk_col is None:
            logger.warning(f"Could not identify FK columns in M2M table for {field_name}")
            continue
        
        # Step 1: Delete all existing associations for this object
        del_stmt = delete(secondary_table).where(local_fk_col == obj_pk_value)
        await db.execute(del_stmt)
        
        if not ids:
            # No new associations to add
            continue
        
        # Step 2: Cast IDs to the right type
        typed_ids = []
        for id_val in ids:
            try:
                col_type = str(target_pk_col.type).upper()
                if "INT" in col_type:
                    typed_ids.append(int(id_val))
                else:
                    typed_ids.append(id_val)
            except (ValueError, TypeError):
                typed_ids.append(id_val)
        
        # Step 3: Verify target IDs exist (optional but safer)
        verify_stmt = select(target_pk_col).where(target_pk_col.in_(typed_ids))
        result = await db.execute(verify_stmt)
        valid_ids = [row[0] for row in result.fetchall()]
        
        if not valid_ids:
            continue
        
        # Step 4: Insert new associations
        for target_id in valid_ids:
            ins_stmt = insert(secondary_table).values({
                local_fk_col.name: obj_pk_value,
                remote_fk_col.name: target_id,
            })
            try:
                await db.execute(ins_stmt)
            except Exception as e:
                # Ignore duplicate key errors (shouldn't happen after delete, but be safe)
                if "duplicate" not in str(e).lower():
                    logger.warning(f"Error inserting M2M association: {e}")
        
        # Step 5: Expire the relationship attribute so it reloads on next access
        try:
            db.expire(obj, [field_name])
        except Exception:
            pass


async def _load_m2m_data(
    db: Any,
    obj: Any,
    model: type,
) -> dict[str, list]:
    """
    Load M2M relationship data for an object safely (Issue #21).
    
    Queries the association table directly to avoid lazy loading issues
    in async context. Returns a dict mapping field names to lists of IDs.
    """
    from sqlalchemy import inspect as sa_inspect, select
    from sqlalchemy.orm import RelationshipProperty
    
    result: dict[str, list] = {}
    
    try:
        mapper = sa_inspect(model)
    except Exception:
        return result
    
    # Get the primary key value of the object
    obj_pk_col = list(model.__table__.primary_key.columns)[0]
    obj_pk_value = getattr(obj, obj_pk_col.name)
    
    for rel_name, rel in mapper.relationships.items():
        if not isinstance(rel, RelationshipProperty) or rel.secondary is None:
            continue
        
        secondary_table = rel.secondary
        target_cls = rel.mapper.class_
        target_pk_col = list(target_cls.__table__.primary_key.columns)[0]
        
        # Find the columns in the secondary table
        local_fk_col = None
        remote_fk_col = None
        
        for col in secondary_table.columns:
            for fk in col.foreign_keys:
                if fk.column.table.name == model.__tablename__:
                    local_fk_col = col
                elif fk.column.table.name == target_cls.__tablename__:
                    remote_fk_col = col
        
        if local_fk_col is None or remote_fk_col is None:
            continue
        
        # Query the association table for this object's M2M IDs
        stmt = select(remote_fk_col).where(local_fk_col == obj_pk_value)
        try:
            res = await db.execute(stmt)
            ids = [row[0] for row in res.fetchall()]
            result[rel_name] = ids
        except Exception as e:
            logger.warning(f"Error loading M2M data for {rel_name}: {e}")
            result[rel_name] = []
    
    return result


def _process_smart_fields(
    data: dict[str, Any],
    model: Any,
    admin_instance: Any,
) -> dict[str, Any]:
    """
    Processa campos inteligentes antes de salvar:
    
    - virtual_password → campo virtual "password" roteado via set_password()
    - password/password_hash → se recebeu plain password, faz hash
    - Campos sensíveis com valor placeholder → remove do payload
    """
    column_info = {c["name"]: c for c in admin_instance.get_column_info()}
    processed = dict(data)
    
    # ── Handle virtual password field first ──
    virtual_pw = column_info.get("password")
    if virtual_pw and virtual_pw.get("virtual") and virtual_pw.get("widget") == "virtual_password":
        pw_value = processed.pop("password", None)
        if pw_value and pw_value not in (None, "", "••••••••"):
            target_field = virtual_pw.get("password_target", "password_hash")
            if hasattr(model, "set_password") or hasattr(model, "make_password"):
                processed["__plain_password__"] = pw_value
                processed["__password_field__"] = target_field
    
    # ── Handle regular smart fields ──
    for field_name, meta in column_info.items():
        widget = meta.get("widget", "default")
        
        # Skip virtual fields (already handled above)
        if meta.get("virtual"):
            continue
        
        if widget in ("password", "password_hash", "secret"):
            value = processed.get(field_name)
            
            # Se valor é o placeholder mascarado, remover do payload
            if value in (None, "", "••••••••"):
                processed.pop(field_name, None)
                continue
            
            # Password: tenta usar set_password() do model se disponível
            if widget in ("password", "password_hash") and value:
                if hasattr(model, "set_password") or hasattr(model, "make_password"):
                    # Marca para processamento posterior (precisa do obj)
                    processed["__plain_password__"] = value
                    processed["__password_field__"] = field_name
                    continue
    
    return processed


def _cast_and_clean_data(
    data: dict[str, Any],
    columns_map: dict[str, Any],
    required_fields: list[str],
) -> dict[str, Any]:
    """
    Cast valores do formulário para os tipos nativos das colunas
    e remove campos opcionais vazios para que o banco aplique defaults.
    
    Resolve:
    - UUID strings → uuid.UUID
    - datetime-local strings → datetime objects (com timezone)
    - Campos opcionais vazios ("") removidos ao invés de enviados
    - Inteiros/floats convertidos a partir de strings
    """
    from datetime import datetime as _dt, timezone as _tz
    from uuid import UUID as _UUID
    
    cleaned: dict[str, Any] = {}
    
    for field_name, value in data.items():
        col = columns_map.get(field_name)
        if col is None:
            cleaned[field_name] = value
            continue
        
        col_type = str(col.type).upper()
        
        # Campo opcional vazio → não incluir (banco aplica default/NULL)
        if value in (None, "") and field_name not in required_fields:
            if col.nullable:
                cleaned[field_name] = None
            # Se não é nullable mas tem default, simplesmente não incluímos
            elif col.default is not None or col.server_default is not None:
                continue
            else:
                continue
            continue
        
        # Cast Enum — converte string value para Python Enum member se necessário
        try:
            from sqlalchemy import Enum as SAEnum
            if isinstance(col.type, SAEnum):
                if hasattr(col.type, 'enum_class') and col.type.enum_class is not None:
                    # Python Enum: converte string value para enum member
                    enum_cls = col.type.enum_class
                    try:
                        cleaned[field_name] = enum_cls(value)
                    except (ValueError, KeyError):
                        # Tenta pelo name se value não funcionar
                        try:
                            cleaned[field_name] = enum_cls[value]
                        except (ValueError, KeyError):
                            cleaned[field_name] = value
                else:
                    # String enum: passa direto
                    cleaned[field_name] = value
                continue
        except ImportError:
            pass
        except Exception:
            pass
        
        # Cast UUID
        if "UUID" in col_type and isinstance(value, str) and value:
            try:
                cleaned[field_name] = _UUID(value)
            except (ValueError, TypeError):
                cleaned[field_name] = value
            continue
        
        # Cast DATETIME / TIMESTAMP
        if ("DATETIME" in col_type or "TIMESTAMP" in col_type) and isinstance(value, str) and value:
            try:
                # HTML datetime-local: "2024-01-01T12:00"
                # Pode vir com ou sem timezone
                dt_val = value.replace("Z", "+00:00")
                
                if "T" in dt_val:
                    # Tenta ISO format completo
                    try:
                        parsed = _dt.fromisoformat(dt_val)
                    except ValueError:
                        # Tenta formato datetime-local sem segundos
                        parsed = _dt.strptime(dt_val[:16], "%Y-%m-%dT%H:%M")
                    
                    # Adiciona timezone UTC se não tem
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=_tz.utc)
                    
                    cleaned[field_name] = parsed
                else:
                    # Só data, sem hora
                    parsed = _dt.strptime(dt_val[:10], "%Y-%m-%d")
                    parsed = parsed.replace(tzinfo=_tz.utc)
                    cleaned[field_name] = parsed
            except (ValueError, TypeError):
                cleaned[field_name] = value
            continue
        
        # Cast DATE
        if "DATE" in col_type and "TIME" not in col_type and isinstance(value, str) and value:
            try:
                from datetime import date as _date
                cleaned[field_name] = _date.fromisoformat(value[:10])
            except (ValueError, TypeError):
                cleaned[field_name] = value
            continue
        
        # Cast INTEGER
        if "INT" in col_type and isinstance(value, str) and value:
            try:
                cleaned[field_name] = int(value)
            except (ValueError, TypeError):
                cleaned[field_name] = value
            continue
        
        # Cast FLOAT/NUMERIC/DECIMAL
        if any(t in col_type for t in ("FLOAT", "NUMERIC", "DECIMAL")) and isinstance(value, str) and value:
            try:
                cleaned[field_name] = float(value)
            except (ValueError, TypeError):
                cleaned[field_name] = value
            continue
        
        # Cast BOOLEAN (strings from form)
        if "BOOL" in col_type and isinstance(value, str):
            cleaned[field_name] = value.lower() in ("true", "1", "yes")
            continue
        
        cleaned[field_name] = value
    
    return cleaned


def _get_error_hint(error: Exception) -> str:
    """
    Gera hint de resolução para erro de runtime com sugestões claras.
    
    Fornece mensagens de erro úteis que ajudam o desenvolvedor a resolver
    problemas rapidamente, seguindo boas práticas de UX.
    """
    error_str = str(error).lower()
    error_type = type(error).__name__
    
    # Database errors
    if "no such table" in error_str or ("relation" in error_str and "does not exist" in error_str):
        return (
            "Tabela não encontrada. Execute 'core migrate' para criar as tabelas. "
            "Se já executou, verifique se DATABASE_URL está correto."
        )
    if "connection" in error_str or "could not connect" in error_str:
        return (
            "Não foi possível conectar ao banco de dados. "
            "Verifique se o servidor está rodando e se DATABASE_URL está correto no .env"
        )
    if "timeout" in error_str:
        return (
            "Timeout ao conectar ao banco de dados. "
            "Verifique a conectividade e se o servidor está acessível."
        )
    if "authentication failed" in error_str or "password" in error_str:
        return (
            "Falha de autenticação. Verifique usuário e senha em DATABASE_URL."
        )
    
    # Import errors
    if "import" in error_str or "module" in error_str or error_type == "ModuleNotFoundError":
        return (
            "Módulo não encontrado. Verifique se o path está correto e se o módulo existe. "
            "Use paths completos, ex: 'src.apps.users.models.User'"
        )
    
    # Model/relationship errors
    if "multiple classes found" in error_str or "ambiguous" in error_str:
        return (
            "Múltiplas classes encontradas. Use path completo, "
            "ex: 'src.apps.users.models.User' em vez de apenas 'User'"
        )
    
    # Permission errors
    if "permission" in error_str or "access" in error_str:
        return (
            "Erro de permissão. Verifique se o usuário tem acesso ao recurso."
        )
    
    # Generic fallback
    return (
        "Verifique os logs para mais detalhes. "
        "Se o problema persistir, consulte a documentação em docs/SIMPLIFICACAO.md"
    )
