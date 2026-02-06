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
                # Base queryset
                qs = admin_instance.get_queryset(db)
                
                # Busca
                if search and admin_instance.search_fields:
                    from sqlalchemy import or_
                    conditions = []
                    for field_name in admin_instance.search_fields:
                        col = getattr(model, field_name, None)
                        if col is not None:
                            conditions.append(col.ilike(f"%{search}%"))
                    if conditions:
                        qs = qs.filter_raw(or_(*conditions))
                
                # Filtros de query params — respeita tipo da coluna
                filters = {}
                for filter_field in admin_instance.list_filter:
                    value = request.query_params.get(filter_field)
                    if value is not None and value != "":
                        # Detecta tipo da coluna para cast correto
                        col = getattr(model, filter_field, None)
                        is_boolean = False
                        if col is not None:
                            try:
                                col_type = str(col.property.columns[0].type).upper()
                                is_boolean = "BOOL" in col_type
                            except Exception:
                                pass
                        
                        if is_boolean:
                            filters[filter_field] = value.lower() in ("true", "1")
                        else:
                            filters[filter_field] = value
                if filters:
                    qs = qs.filter(**filters)
                
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
                
                return {
                    "items": serialized,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": (total + per_page - 1) // per_page if per_page else 1,
                    "columns": [
                        {
                            "name": f,
                            "label": admin_instance.help_texts.get(f, f.replace("_", " ").title()),
                            "is_link": f in admin_instance.list_display_links,
                        }
                        for f in display_fields
                    ],
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
                
                display_fields = admin_instance.get_display_fields()
                data = serialize_instance(obj, display_fields, admin_instance)
                
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
        
        # Validar campos obrigatórios antes do INSERT
        try:
            required_fields = []
            for col in model.__table__.columns:
                if (
                    not col.nullable
                    and not col.primary_key
                    and col.default is None
                    and col.server_default is None
                    and col.name in editable
                ):
                    required_fields.append(col.name)
            
            missing = [f for f in required_fields if f not in safe_data or safe_data[f] in (None, "")]
            if missing:
                raise HTTPException(400, detail={
                    "error": "validation_error",
                    "missing_fields": missing,
                    "message": f"Required fields: {', '.join(missing)}",
                })
        except HTTPException:
            raise
        except Exception:
            pass  # Se introspeccao falhar, deixa o banco validar
        
        from core.models import get_session
        db = await get_session()
        
        try:
            async with db:
                obj = model(**safe_data)
                
                await admin_instance.before_save(db, obj, is_new=True)
                await obj.save(db)
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
                    "item": serialize_instance(obj, display_fields, admin_instance),
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
                
                # Aplica alterações
                for key, value in safe_data.items():
                    setattr(obj, key, value)
                
                await admin_instance.before_save(db, obj, is_new=False)
                await obj.save(db)
                await admin_instance.after_save(db, obj, is_new=False)
                
                await db.commit()
                
                # Calcula changes para audit
                new_data = obj.to_dict()
                changes = {
                    k: {"old": _safe_value(old_data.get(k)), "new": _safe_value(new_data.get(k))}
                    for k in safe_data
                    if old_data.get(k) != new_data.get(k)
                }
                
                await _log_action(
                    db, user, request, "update",
                    admin_instance, obj, changes=changes,
                )
                await db.commit()
                
                display_fields = admin_instance.get_display_fields()
                return {
                    "item": serialize_instance(obj, display_fields, admin_instance),
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


def _get_error_hint(error: Exception) -> str:
    """Gera hint de resolução para erro de runtime."""
    error_str = str(error).lower()
    if "no such table" in error_str or ("relation" in error_str and "does not exist" in error_str):
        return "Execute 'core migrate' para criar as tabelas."
    if "connection" in error_str:
        return "Verifique se o banco de dados está acessível."
    if "timeout" in error_str:
        return "Verifique a conectividade com o banco de dados."
    return "Verifique os logs para mais detalhes."
