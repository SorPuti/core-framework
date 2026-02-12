"""
Operations Center — API endpoints.

Provides JSON endpoints for:
- Infrastructure monitoring
- Task management (list, detail, retry, cancel)
- Worker management (list, detail, heartbeats)
- Log streaming (SSE) and recent logs
- Resource inventory

SECURITY: All endpoints require SUPERUSER access.
Operations Center contains infrastructure controls that could compromise
the server. Only superusers (created via CLI) should have access.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from core.admin.permissions import check_admin_access

if TYPE_CHECKING:
    from core.admin.site import AdminSite

logger = logging.getLogger("core.admin.ops")


async def check_superuser_access(request: Request) -> Any:
    """
    Dependency that requires SUPERUSER access for Operations Center.
    
    Operations Center contains infrastructure controls that could compromise
    the server. Only superusers (created via CLI) should have access,
    never regular staff/admin users.
    """
    # First check basic admin access
    user = await check_admin_access(request)
    
    # Then verify superuser status
    if not getattr(user, "is_superuser", False):
        raise HTTPException(
            status_code=403,
            detail="Operations Center requires superuser access. Contact your system administrator.",
        )
    
    return user


def create_ops_api(site: "AdminSite") -> APIRouter:
    """Create the Operations Center API router."""
    router = APIRouter(prefix="/api/ops", tags=["admin-ops"])

    # =====================================================================
    # Consolidated API (Operations Center unified frontend)
    # =====================================================================

    @router.get("/dashboard")
    async def ops_dashboard(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Aggregated dashboard data: overview, health, task/event stats, workers."""
        from core.admin.infrastructure import InfraDetector
        services = await InfraDetector.get_service_health()
        try:
            from core.models import get_session
            from core.admin.models import TaskExecution, WorkerHeartbeat, EventLog
            from sqlalchemy import select, func
            from core.datetime import timezone
            from datetime import timedelta

            db = await get_session()
            async with db:
                task_total = (await db.execute(select(func.count()).select_from(TaskExecution))).scalar() or 0
                task_stmt = select(TaskExecution.status, func.count()).group_by(TaskExecution.status)
                task_by_status = {r[0]: r[1] for r in (await db.execute(task_stmt))}
                worker_count = (await db.execute(select(func.count()).select_from(WorkerHeartbeat))).scalar() or 0
                event_total = (await db.execute(select(func.count()).select_from(EventLog))).scalar() or 0
                event_stmt = select(EventLog.status, func.count()).group_by(EventLog.status)
                event_by_status = {r[0]: r[1] for r in (await db.execute(event_stmt))}
                now = timezone.now()
                five_min = now - timedelta(minutes=5)
                recent_events = (await db.execute(
                    select(func.count()).select_from(EventLog).where(EventLog.created_at >= five_min)
                )).scalar() or 0
        except Exception as e:
            logger.warning("Dashboard aggregate error: %s", e)
            task_total = task_by_status = worker_count = event_total = event_by_status = 0
            recent_events = 0
        return {
            "infrastructure": {"services": services},
            "tasks": {"total": task_total, "by_status": task_by_status},
            "workers": {"total": worker_count},
            "events": {
                "total": event_total,
                "by_status": event_by_status,
                "throughput_per_min": round(recent_events / 5.0, 2) if recent_events else 0,
            },
        }

    @router.get("/activity")
    async def ops_activity_list(
        request: Request,
        page: int = Query(1, ge=1),
        per_page: int = Query(50, ge=1, le=200),
        view: str = Query("tasks", description="tasks | workers | periodic"),
        status: str = Query(""),
        queue: str = Query(""),
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Unified activity list: tasks, workers, or periodic depending on view."""
        if view == "workers":
            try:
                from core.models import get_session
                from core.admin.models import WorkerHeartbeat
                from core.querysets import QuerySet
                from core.datetime import timezone
                from datetime import timedelta
                db = await get_session()
                async with db:
                    qs = QuerySet(WorkerHeartbeat, db)
                    total = await qs.count()
                    items = await qs.order_by("-last_heartbeat").offset(
                        (page - 1) * per_page
                    ).limit(per_page).all()
                    now = timezone.now()
                    stale = now - timedelta(minutes=2)
                    result = []
                    for w in items:
                        d = _serialize_worker(w)
                        if w.status == "ONLINE" and w.last_heartbeat and w.last_heartbeat < stale:
                            d["status"] = "OFFLINE"
                            d["_stale"] = True
                        result.append(d)
                    return {"items": result, "total": total, "page": page, "per_page": per_page, "view": "workers"}
            except Exception as e:
                logger.warning("ops_activity workers: %s", e)
                return {"items": [], "total": 0, "page": 1, "per_page": per_page, "view": "workers"}
        if view == "periodic":
            from core.config import get_settings
            import importlib
            settings = get_settings()
            if getattr(settings, "tasks_module", None):
                try:
                    importlib.import_module(settings.tasks_module)
                except ImportError:
                    pass
            from core.tasks.registry import get_periodic_tasks
            tasks = get_periodic_tasks()
            items = [
                {
                    "name": name,
                    "cron": pt.cron,
                    "interval": pt.interval,
                    "queue": pt.queue,
                    "enabled": pt.enabled,
                    "last_run": pt.last_run.isoformat() if pt.last_run else None,
                    "next_run": pt.next_run.isoformat() if pt.next_run else None,
                    "run_count": pt.run_count,
                }
                for name, pt in tasks.items()
            ]
            return {"items": items, "total": len(items), "page": 1, "per_page": len(items), "view": "periodic"}
        # default: tasks
        try:
            from core.models import get_session
            from core.admin.models import TaskExecution
            from core.querysets import QuerySet
            db = await get_session()
            async with db:
                qs = QuerySet(TaskExecution, db)
                if status:
                    qs = qs.filter(status=status.upper())
                if queue:
                    qs = qs.filter(queue=queue)
                total = await qs.count()
                items = await qs.order_by("-created_at").offset(
                    (page - 1) * per_page
                ).limit(per_page).all()
                return {
                    "items": [_serialize_task_execution(t) for t in items],
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "view": "tasks",
                }
        except Exception as e:
            logger.warning("ops_activity tasks: %s", e)
            return {"items": [], "total": 0, "page": 1, "per_page": per_page, "view": "tasks"}

    @router.get("/activity/{entity_id}")
    async def ops_activity_detail(
        request: Request,
        entity_id: str,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Detail for a task or worker by id (tries task first, then worker)."""
        try:
            from core.models import get_session
            from core.admin.models import TaskExecution, WorkerHeartbeat
            from core.querysets import QuerySet
            db = await get_session()
            async with db:
                qs_task = QuerySet(TaskExecution, db)
                task = await qs_task.filter(task_id=entity_id).first()
                if task:
                    return {"kind": "task", "item": _serialize_task_execution(task)}
                qs_worker = QuerySet(WorkerHeartbeat, db)
                worker = await qs_worker.filter(worker_id=entity_id).first()
                if worker:
                    return {"kind": "worker", "item": _serialize_worker(worker)}
            raise HTTPException(404, "Activity entity not found")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    @router.post("/activity/{entity_id}/action")
    async def ops_activity_action(
        request: Request,
        entity_id: str,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Unified action: retry/cancel for tasks, toggle/run for periodic (body: { action, ... })."""
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        action = (body or {}).get("action", "")
        try:
            from core.models import get_session
            from core.admin.models import TaskExecution, WorkerHeartbeat
            from core.querysets import QuerySet
            db = await get_session()
            async with db:
                qs_task = QuerySet(TaskExecution, db)
                task = await qs_task.filter(task_id=entity_id).first()
                if task:
                    if action == "retry":
                        from core.tasks.registry import get_task_producer
                        from core.tasks.base import TaskMessage
                        import uuid
                        if task.status not in ("FAILURE", "CANCELLED"):
                            raise HTTPException(400, f"Cannot retry task with status {task.status}")
                        new_id = str(uuid.uuid4())
                        args = json.loads(task.args_json) if task.args_json else []
                        kwargs = json.loads(task.kwargs_json) if task.kwargs_json else {}
                        msg = TaskMessage(
                            task_id=new_id, task_name=task.task_name, args=tuple(args),
                            kwargs=kwargs, queue=task.queue, max_retries=task.max_retries,
                        )
                        producer = await get_task_producer()
                        await producer.send(f"tasks.{msg.queue}", msg.to_dict())
                        return {"status": "retried", "new_task_id": new_id}
                    if action == "cancel":
                        from sqlalchemy import update
                        stmt = (
                            update(TaskExecution)
                            .where(TaskExecution.task_id == entity_id)
                            .where(TaskExecution.status.in_(["PENDING", "RETRY"]))
                            .values(status="CANCELLED")
                        )
                        r = await db.execute(stmt)
                        await db.commit()
                        if r.rowcount == 0:
                            raise HTTPException(400, "Task not found or cannot be cancelled")
                        return {"status": "cancelled"}
                    raise HTTPException(400, f"Unknown action for task: {action}")
                qs_worker = QuerySet(WorkerHeartbeat, db)
                worker = await qs_worker.filter(worker_id=entity_id).first()
                if worker:
                    raise HTTPException(400, "No actions supported for worker entity")
            from core.tasks.registry import get_periodic_tasks
            if entity_id in get_periodic_tasks():
                if action == "toggle":
                    pt = get_periodic_tasks()[entity_id]
                    pt.enabled = not pt.enabled
                    return {"status": "ok", "enabled": pt.enabled}
                if action == "run":
                    import time as _time
                    from core.tasks.registry import get_periodic_tasks as _get_pt
                    pt = _get_pt()[entity_id]
                    task_id = str(__import__("uuid").uuid4())
                    start = _time.perf_counter()
                    recorded = False
                    try:
                        from core.admin.models import TaskExecution
                        db = await get_session()
                        async with db:
                            await TaskExecution.record_start(
                                db, task_name=entity_id, task_id=task_id,
                                queue=pt.queue, worker_id="admin-panel",
                            )
                            recorded = True
                    except Exception:
                        pass
                    result, error, status = None, None, "SUCCESS"
                    try:
                        result = await pt.func()
                        pt.mark_run()
                    except Exception as e:
                        logger.error("Periodic run %s failed: %s", entity_id, e)
                        error = str(e)
                        status = "FAILURE"
                    duration_ms = int((_time.perf_counter() - start) * 1000)
                    if recorded:
                        try:
                            from core.admin.models import TaskExecution
                            db = await get_session()
                            async with db:
                                await TaskExecution.record_finish(
                                    db, task_id=task_id, status=status,
                                    result_json=str(result) if result is not None else None,
                                    error=error, duration_ms=duration_ms,
                                )
                        except Exception:
                            pass
                    if error:
                        raise HTTPException(500, f"Task execution failed: {error}")
                    return {"status": "executed", "task_id": task_id, "duration_ms": duration_ms}
            raise HTTPException(404, "Activity entity not found")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    @router.get("/system")
    async def ops_system(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """System info: Kafka overview, infrastructure, registered topics, schemas."""
        from core.admin.infrastructure import InfraDetector
        infra = await InfraDetector.collect()
        kafka = {"enabled": False}
        admin = await _get_kafka_admin()
        if admin:
            try:
                cluster = await admin.get_cluster_info()
                kafka = {
                    "enabled": True,
                    "cluster_id": cluster.cluster_id,
                    "brokers_count": len(cluster.brokers),
                    "topics_count": cluster.topics_count,
                    "partitions_count": cluster.partitions_count,
                }
            except Exception as e:
                kafka["error"] = str(e)
            finally:
                await admin.close()
        topics_resp = await _list_registered_topics()
        topics = topics_resp.get("items", [])
        schemas_resp = await _list_avro_schemas()
        schemas = schemas_resp.get("items", [])
        return {"infrastructure": infra, "kafka": kafka, "topics": topics, "schemas": schemas}

    @router.get("/system/kafka/{resource}")
    async def ops_system_kafka(
        request: Request,
        resource: str,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Kafka resource: consumer-groups, topics, throughput (resource name + optional query params)."""
        if resource == "consumer-groups":
            admin = await _get_kafka_admin()
            if not admin:
                return {"items": [], "error": "Kafka not configured"}
            try:
                groups = await admin.list_consumer_groups()
                items = []
                for g in groups:
                    detail = await admin.describe_consumer_group(g.group_id)
                    items.append({
                        "group_id": g.group_id,
                        "state": g.state,
                        "members_count": g.members_count,
                        "topics": g.topics,
                        "total_lag": detail.total_lag if detail else 0,
                    })
                return {"items": items, "total": len(items)}
            except Exception as e:
                return {"items": [], "error": str(e)}
            finally:
                await admin.close()
        if resource == "topics":
            admin = await _get_kafka_admin()
            if not admin:
                return {"items": [], "total": 0, "error": "Kafka not configured"}
            try:
                topics = await admin.list_topics_with_info()
                items = [{"name": t.name, "partitions": t.partitions, "replication_factor": t.replication_factor} for t in topics]
                return {"items": items, "total": len(items)}
            except Exception as e:
                return {"items": [], "total": 0, "error": str(e)}
            finally:
                await admin.close()
        if resource == "throughput":
            period = request.query_params.get("period", "6h")
            granularity = request.query_params.get("granularity", "5min")
            return await _kafka_throughput(period, granularity)
        raise HTTPException(404, f"Unknown Kafka resource: {resource}")

    @router.get("/logs")
    async def ops_logs(
        request: Request,
        limit: int = Query(200, ge=1, le=5000),
        level: str = Query(""),
        logger_name: str = Query("", alias="logger"),
        search: str = Query(""),
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Recent logs with filters."""
        from core.admin.log_handler import get_log_buffer
        buffer = get_log_buffer()
        entries = buffer.get_recent(limit=limit, level_filter=level or None, logger_filter=logger_name or None, search=search or None)
        return {
            "entries": [e.to_json() for e in entries],
            "total_captured": buffer.total_count,
            "buffer_size": buffer.buffer_size,
            "subscribers": buffer.subscriber_count,
        }

    @router.post("/purge")
    async def ops_purge(
        request: Request,
        target: str = Query("tasks", description="tasks | events"),
        days: int = Query(30, ge=1),
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Unified purge: tasks or events older than N days."""
        if target == "events":
            from core.models import get_session
            from core.admin.models import EventLog
            from core.datetime import timezone
            from datetime import timedelta
            from sqlalchemy import delete
            cutoff = timezone.now() - timedelta(days=days)
            db = await get_session()
            async with db:
                stmt = delete(EventLog).where(EventLog.created_at < cutoff)
                r = await db.execute(stmt)
                await db.commit()
                return {"purged": r.rowcount, "target": "events", "older_than_days": days}
        # tasks
        from core.models import get_session
        from core.admin.models import TaskExecution
        from core.datetime import timezone
        from datetime import timedelta
        from sqlalchemy import delete
        cutoff = timezone.now() - timedelta(days=days)
        db = await get_session()
        async with db:
            stmt = delete(TaskExecution).where(TaskExecution.created_at < cutoff)
            r = await db.execute(stmt)
            await db.commit()
            return {"purged": r.rowcount, "target": "tasks", "older_than_days": days}

    # =====================================================================
    # Infrastructure
    # =====================================================================

    @router.get("/infrastructure")
    async def infrastructure_view(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Full infrastructure report."""
        from core.admin.infrastructure import InfraDetector
        return await InfraDetector.collect()

    @router.get("/infrastructure/health")
    async def infrastructure_health(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Service health check only (faster)."""
        from core.admin.infrastructure import InfraDetector
        services = await InfraDetector.get_service_health()
        return {"services": services}

    # =====================================================================
    # Tasks
    # =====================================================================

    @router.get("/tasks")
    async def tasks_list(
        request: Request,
        page: int = Query(1, ge=1),
        per_page: int = Query(50, ge=1, le=200),
        status: str = Query("", description="Filter by status"),
        task_name: str = Query("", description="Filter by task name"),
        queue: str = Query("", description="Filter by queue"),
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """List task executions with filters."""
        try:
            from core.models import get_session
            from core.admin.models import TaskExecution
            from core.querysets import QuerySet

            db = await get_session()
            async with db:
                qs = QuerySet(TaskExecution, db)

                if status:
                    qs = qs.filter(status=status.upper())
                if task_name:
                    qs = qs.filter(task_name=task_name)
                if queue:
                    qs = qs.filter(queue=queue)

                total = await qs.count()
                items = await qs.order_by("-created_at").offset(
                    (page - 1) * per_page
                ).limit(per_page).all()

                return {
                    "items": [_serialize_task_execution(t) for t in items],
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": (total + per_page - 1) // per_page if per_page else 1,
                }
        except Exception as e:
            logger.warning("Failed to list task executions: %s", e)
            return {"items": [], "total": 0, "page": 1, "per_page": per_page, "total_pages": 0}

    @router.get("/tasks/stats")
    async def tasks_stats(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Task execution statistics."""
        try:
            from core.models import get_session
            from core.admin.models import TaskExecution
            from sqlalchemy import select, func

            db = await get_session()
            async with db:
                # Count by status
                stmt = (
                    select(TaskExecution.status, func.count())
                    .group_by(TaskExecution.status)
                )
                result = await db.execute(stmt)
                counts = {row[0]: row[1] for row in result}

                # Total
                total_stmt = select(func.count()).select_from(TaskExecution)
                total = (await db.execute(total_stmt)).scalar() or 0

                return {
                    "total": total,
                    "by_status": counts,
                    "success": counts.get("SUCCESS", 0),
                    "failure": counts.get("FAILURE", 0),
                    "running": counts.get("RUNNING", 0),
                    "pending": counts.get("PENDING", 0),
                    "retry": counts.get("RETRY", 0),
                    "cancelled": counts.get("CANCELLED", 0),
                }
        except Exception as e:
            logger.warning("Failed to get task stats: %s", e)
            return {"total": 0, "by_status": {}}

    @router.get("/tasks/registered")
    async def tasks_registered(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """List all registered tasks (from registry)."""
        from core.tasks.registry import list_tasks
        return {"tasks": list_tasks()}

    @router.get("/tasks/{task_id}")
    async def task_detail(
        request: Request,
        task_id: str,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Get task execution detail."""
        try:
            from core.models import get_session
            from core.admin.models import TaskExecution
            from core.querysets import QuerySet

            db = await get_session()
            async with db:
                qs = QuerySet(TaskExecution, db)
                item = await qs.filter(task_id=task_id).first()
                if not item:
                    raise HTTPException(404, "Task execution not found")
                return {"item": _serialize_task_execution(item)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    @router.post("/tasks/{task_id}/retry")
    async def task_retry(
        request: Request,
        task_id: str,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Retry a failed task."""
        try:
            from core.models import get_session
            from core.admin.models import TaskExecution
            from core.querysets import QuerySet
            from core.tasks.registry import get_task, get_task_producer
            from core.tasks.base import TaskMessage
            import uuid

            db = await get_session()
            async with db:
                qs = QuerySet(TaskExecution, db)
                item = await qs.filter(task_id=task_id).first()
                if not item:
                    raise HTTPException(404, "Task execution not found")

                if item.status not in ("FAILURE", "CANCELLED"):
                    raise HTTPException(400, f"Cannot retry task with status {item.status}")

                # Re-dispatch
                new_task_id = str(uuid.uuid4())
                args = json.loads(item.args_json) if item.args_json else []
                kwargs = json.loads(item.kwargs_json) if item.kwargs_json else {}

                msg = TaskMessage(
                    task_id=new_task_id,
                    task_name=item.task_name,
                    args=tuple(args),
                    kwargs=kwargs,
                    queue=item.queue,
                    max_retries=item.max_retries,
                )

                producer = await get_task_producer()
                await producer.send(f"tasks.{msg.queue}", msg.to_dict())

                return {"status": "retried", "new_task_id": new_task_id}

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    @router.post("/tasks/{task_id}/cancel")
    async def task_cancel(
        request: Request,
        task_id: str,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Cancel a pending/retry task."""
        try:
            from core.models import get_session
            from core.admin.models import TaskExecution
            from sqlalchemy import update

            db = await get_session()
            async with db:
                stmt = (
                    update(TaskExecution)
                    .where(TaskExecution.task_id == task_id)
                    .where(TaskExecution.status.in_(["PENDING", "RETRY"]))
                    .values(status="CANCELLED")
                )
                result = await db.execute(stmt)
                await db.commit()

                if result.rowcount == 0:
                    raise HTTPException(400, "Task not found or cannot be cancelled")

                return {"status": "cancelled"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    @router.post("/tasks/purge")
    async def tasks_purge(
        request: Request,
        days: int = Query(30, ge=1),
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Purge old task executions."""
        try:
            from core.models import get_session
            from core.admin.models import TaskExecution
            from core.datetime import timezone
            from datetime import timedelta
            from sqlalchemy import delete

            cutoff = timezone.now() - timedelta(days=days)

            db = await get_session()
            async with db:
                stmt = delete(TaskExecution).where(TaskExecution.created_at < cutoff)
                result = await db.execute(stmt)
                await db.commit()
                return {"purged": result.rowcount, "older_than_days": days}
        except Exception as e:
            raise HTTPException(500, str(e))

    # =====================================================================
    # Periodic Tasks
    # =====================================================================

    @router.get("/periodic")
    async def periodic_list(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """List periodic tasks (from registry + persisted state)."""
        # Import tasks_module to ensure periodic tasks are registered
        from core.config import get_settings
        import importlib
        
        settings = get_settings()
        tasks_module = getattr(settings, "tasks_module", None)
        if tasks_module:
            try:
                importlib.import_module(tasks_module)
            except ImportError as e:
                logger.debug(f"Could not import tasks_module '{tasks_module}': {e}")
        
        from core.tasks.registry import get_periodic_tasks

        tasks = get_periodic_tasks()
        items = []
        for name, pt in tasks.items():
            items.append({
                "name": name,
                "cron": pt.cron,
                "interval": pt.interval,
                "queue": pt.queue,
                "enabled": pt.enabled,
                "last_run": pt.last_run.isoformat() if pt.last_run else None,
                "next_run": pt.next_run.isoformat() if pt.next_run else None,
                "run_count": pt.run_count,
            })
        return {"items": items, "total": len(items)}

    @router.post("/periodic/{task_name}/toggle")
    async def periodic_toggle(
        request: Request,
        task_name: str,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Enable/disable a periodic task."""
        from core.tasks.registry import get_periodic_tasks

        tasks = get_periodic_tasks()
        if task_name not in tasks:
            raise HTTPException(404, f"Periodic task '{task_name}' not found")

        pt = tasks[task_name]
        pt.enabled = not pt.enabled
        return {"name": task_name, "enabled": pt.enabled}

    @router.post("/periodic/{task_name}/run")
    async def periodic_run_now(
        request: Request,
        task_name: str,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """
        Manually trigger a periodic task.
        
        Executes the task directly in this process (synchronous execution).
        This is useful for testing and debugging without needing a worker.
        Records execution in the database for history tracking.
        """
        # Import tasks_module to ensure periodic tasks are registered
        from core.config import get_settings
        import importlib
        import uuid
        import time
        
        settings = get_settings()
        tasks_module = getattr(settings, "tasks_module", None)
        if tasks_module:
            try:
                importlib.import_module(tasks_module)
            except ImportError as e:
                logger.debug(f"Could not import tasks_module '{tasks_module}': {e}")
        
        from core.tasks.registry import get_periodic_tasks

        tasks = get_periodic_tasks()
        if task_name not in tasks:
            raise HTTPException(404, f"Periodic task '{task_name}' not found")

        pt = tasks[task_name]
        task_id = str(uuid.uuid4())
        start_time = time.perf_counter()
        
        # Try to record execution start in database
        recorded = False
        try:
            from core.models import get_session
            from core.admin.models import TaskExecution
            
            db = await get_session()
            async with db:
                await TaskExecution.record_start(
                    db,
                    task_name=task_name,
                    task_id=task_id,
                    queue=pt.queue,
                    worker_id="admin-panel",
                )
                recorded = True
        except Exception as db_err:
            logger.debug(f"Could not create task execution record: {db_err}")
        
        # Execute the task directly
        result = None
        error = None
        status = "SUCCESS"
        
        try:
            result = await pt.func()
            pt.mark_run()
        except Exception as e:
            logger.error(f"Failed to execute periodic task {task_name}: {e}", exc_info=True)
            error = str(e)
            status = "FAILURE"
        
        # Calculate duration
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        # Update execution record
        if recorded:
            try:
                from core.models import get_session
                from core.admin.models import TaskExecution
                
                db = await get_session()
                async with db:
                    await TaskExecution.record_finish(
                        db,
                        task_id=task_id,
                        status=status,
                        result_json=str(result) if result is not None else None,
                        error=error,
                        duration_ms=duration_ms,
                    )
            except Exception as db_err:
                logger.debug(f"Could not update task execution record: {db_err}")
        
        if error:
            raise HTTPException(500, f"Task execution failed: {error}")
        
        return {
            "status": "executed",
            "task_id": task_id,
            "result": str(result) if result is not None else None,
            "duration_ms": duration_ms,
            "message": f"Task '{task_name}' executed successfully"
        }

    # =====================================================================
    # Workers
    # =====================================================================

    @router.get("/workers")
    async def workers_list(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """List active workers."""
        try:
            from core.models import get_session
            from core.admin.models import WorkerHeartbeat
            from core.querysets import QuerySet
            from core.datetime import timezone
            from datetime import timedelta

            db = await get_session()
            async with db:
                qs = QuerySet(WorkerHeartbeat, db)
                items = await qs.order_by("-last_heartbeat").limit(100).all()

                # Mark stale workers as OFFLINE
                now = timezone.now()
                stale_threshold = now - timedelta(minutes=2)

                result = []
                for w in items:
                    data = _serialize_worker(w)
                    if w.status == "ONLINE" and w.last_heartbeat and w.last_heartbeat < stale_threshold:
                        data["status"] = "OFFLINE"
                        data["_stale"] = True
                    result.append(data)

                return {"items": result, "total": len(result)}
        except Exception as e:
            logger.warning("Failed to list workers: %s", e)
            return {"items": [], "total": 0}

    @router.get("/workers/registered")
    async def workers_registered(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """List all registered message workers (from registry)."""
        def _safe_topic(val: Any) -> str | None:
            """Resolve TopicMeta/Topic classes para string (fallback defensivo)."""
            if val is None:
                return None
            if isinstance(val, str):
                return val
            if hasattr(val, "name"):
                return val.name
            if hasattr(val, "value"):
                return val.value
            return str(val)
        
        try:
            # Import workers_module to ensure workers are registered
            from core.config import get_settings
            import importlib
            
            settings = get_settings()
            workers_module = getattr(settings, "workers_module", None)
            if workers_module:
                try:
                    importlib.import_module(workers_module)
                except ImportError as e:
                    logger.debug(f"Could not import workers_module '{workers_module}': {e}")
            
            from core.messaging.workers import get_all_workers
            workers = get_all_workers()
            items = []
            for name, cfg in workers.items():
                items.append({
                    "name": name,
                    "input_topic": _safe_topic(cfg.input_topic),
                    "output_topic": _safe_topic(cfg.output_topic),
                    "concurrency": cfg.concurrency,
                    "group_id": cfg.group_id,
                })
            return {"items": items, "total": len(items)}
        except Exception as e:
            logger.warning("Failed to list registered workers: %s", e)
            return {"items": [], "total": 0}

    @router.delete("/workers/{worker_id}")
    async def worker_delete(
        request: Request,
        worker_id: str,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """
        Delete an OFFLINE or stale worker record.
        
        Allows deletion of workers that are:
        1. Explicitly marked as OFFLINE in the database, OR
        2. Marked as ONLINE but stale (no heartbeat for >2 minutes)
        
        This fixes the issue where frontend shows worker as OFFLINE (based on
        stale heartbeat) but database still has status=ONLINE.
        """
        try:
            from core.models import get_session
            from core.admin.models import WorkerHeartbeat
            from core.datetime import timezone
            from datetime import timedelta
            from sqlalchemy import select

            db = await get_session()
            async with db:
                # First, fetch the worker to check its state
                stmt = select(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == worker_id)
                result = await db.execute(stmt)
                worker = result.scalar_one_or_none()
                
                if not worker:
                    raise HTTPException(404, "Worker not found")
                
                # Check if worker can be deleted:
                # 1. Status is OFFLINE in database, OR
                # 2. Status is ONLINE but stale (>2min without heartbeat)
                now = timezone.now()
                stale_threshold = now - timedelta(minutes=2)
                
                is_offline = worker.status == "OFFLINE"
                is_stale = (
                    worker.status == "ONLINE" 
                    and worker.last_heartbeat 
                    and worker.last_heartbeat < stale_threshold
                )
                
                if not (is_offline or is_stale):
                    raise HTTPException(
                        400,
                        "Worker is still active. Only OFFLINE or stale workers can be removed.",
                    )
                
                # Delete the worker
                await db.delete(worker)
                await db.commit()

                return {"status": "deleted", "worker_id": worker_id}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    @router.get("/workers/{worker_id}")
    async def worker_detail(
        request: Request,
        worker_id: str,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Get worker detail."""
        try:
            from core.models import get_session
            from core.admin.models import WorkerHeartbeat
            from core.querysets import QuerySet

            db = await get_session()
            async with db:
                qs = QuerySet(WorkerHeartbeat, db)
                item = await qs.filter(worker_id=worker_id).first()
                if not item:
                    raise HTTPException(404, "Worker not found")
                return {"item": _serialize_worker(item)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    # =====================================================================
    # Logs
    # =====================================================================

    @router.get("/logs/recent")
    async def logs_recent(
        request: Request,
        limit: int = Query(200, ge=1, le=5000),
        level: str = Query(""),
        logger_name: str = Query("", alias="logger"),
        search: str = Query(""),
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Get recent log entries."""
        from core.admin.log_handler import get_log_buffer

        buffer = get_log_buffer()
        entries = buffer.get_recent(
            limit=limit,
            level_filter=level or None,
            logger_filter=logger_name or None,
            search=search or None,
        )
        return {
            "entries": [e.to_json() for e in entries],
            "total_captured": buffer.total_count,
            "buffer_size": buffer.buffer_size,
            "subscribers": buffer.subscriber_count,
        }

    @router.get("/logs/stream")
    async def logs_stream(
        request: Request,
        level: str = Query("INFO"),
        logger_name: str = Query("", alias="logger"),
        search: str = Query(""),
        user: Any = Depends(check_superuser_access),
    ):
        """SSE endpoint for real-time log streaming."""
        from core.admin.log_handler import get_log_buffer

        buffer = get_log_buffer()
        level_no = getattr(logging, level.upper(), logging.INFO) if level else logging.INFO

        async def event_generator():
            queue = buffer.subscribe()
            try:
                # Send initial connection event
                yield f"data: {json.dumps({'type': 'connected', 'message': 'Log stream connected'})}\n\n"
                
                while True:
                    # Check if client disconnected
                    if await request.is_disconnected():
                        break
                    
                    try:
                        entry = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        # Send keepalive to keep connection alive
                        yield ": keepalive\n\n"
                        continue

                    # Apply filters
                    if entry.level_no < level_no:
                        continue
                    if logger_name and not entry.logger.startswith(logger_name):
                        continue
                    if search and search.lower() not in entry.message.lower():
                        continue

                    yield f"data: {entry.to_json()}\n\n"

            except (asyncio.CancelledError, GeneratorExit):
                pass
            finally:
                buffer.unsubscribe(queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # =====================================================================
    # Resource Inventory
    # =====================================================================

    @router.get("/inventory")
    async def resource_inventory(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """Unified resource inventory."""
        from core.admin.resource_inventory import ResourceInventory
        return await ResourceInventory.collect(site)

    # =====================================================================
    # Kafka - Cluster Overview
    # =====================================================================

    @router.get("/kafka/overview")
    async def kafka_overview(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ):
        """Get Kafka cluster overview."""
        admin = await _get_kafka_admin()
        if not admin:
            return {"error": "Kafka not configured", "enabled": False}
        
        try:
            cluster_info = await admin.get_cluster_info()
            consumer_groups = await admin.list_consumer_groups()
            
            return {
                "enabled": True,
                "cluster_id": cluster_info.cluster_id,
                "brokers": [
                    {"id": b.id, "host": b.host, "port": b.port, "rack": b.rack}
                    for b in cluster_info.brokers
                ],
                "brokers_count": len(cluster_info.brokers),
                "controller_id": cluster_info.controller_id,
                "topics_count": cluster_info.topics_count,
                "partitions_count": cluster_info.partitions_count,
                "consumer_groups_count": len(consumer_groups),
            }
        except Exception as e:
            logger.error(f"Error getting Kafka overview: {e}")
            return {"error": str(e), "enabled": False}
        finally:
            await admin.close()

    @router.get("/kafka/consumer-groups")
    async def kafka_consumer_groups(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ):
        """List all Kafka consumer groups with state and lag info."""
        admin = await _get_kafka_admin()
        if not admin:
            return {"items": [], "error": "Kafka not configured"}
        
        try:
            groups = await admin.list_consumer_groups()
            items = []
            for group in groups:
                detail = await admin.describe_consumer_group(group.group_id)
                items.append({
                    "group_id": group.group_id,
                    "state": group.state,
                    "members_count": group.members_count,
                    "topics": group.topics,
                    "total_lag": detail.total_lag if detail else 0,
                })
            return {"items": items, "total": len(items)}
        except Exception as e:
            logger.error(f"Error listing consumer groups: {e}")
            return {"items": [], "error": str(e)}
        finally:
            await admin.close()

    @router.get("/kafka/consumer-groups/{group_id}")
    async def kafka_consumer_group_detail(
        request: Request,
        group_id: str,
        user: Any = Depends(check_superuser_access),
    ):
        """Get detailed information about a consumer group."""
        admin = await _get_kafka_admin()
        if not admin:
            raise HTTPException(503, "Kafka not configured")
        
        try:
            detail = await admin.describe_consumer_group(group_id)
            if not detail:
                raise HTTPException(404, f"Consumer group '{group_id}' not found")
            
            return {
                "group_id": detail.group_id,
                "state": detail.state,
                "coordinator": detail.coordinator,
                "protocol_type": detail.protocol_type,
                "protocol": detail.protocol,
                "members": [
                    {"member_id": m.member_id, "client_id": m.client_id, "host": m.host, "partitions": m.partitions}
                    for m in detail.members
                ],
                "offsets": {
                    topic: [
                        {"partition": po.partition, "current_offset": po.current_offset, "end_offset": po.end_offset, "lag": po.lag}
                        for po in offsets
                    ]
                    for topic, offsets in detail.offsets.items()
                },
                "total_lag": detail.total_lag,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting consumer group {group_id}: {e}")
            raise HTTPException(500, f"Error fetching consumer group: {e}")
        finally:
            await admin.close()

    @router.get("/kafka/topics")
    async def kafka_topics(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ):
        """List all Kafka topics with partition info."""
        admin = await _get_kafka_admin()
        if not admin:
            return {"items": [], "total": 0, "error": "Kafka not configured"}
        
        try:
            topics = await admin.list_topics_with_info()
            items = [
                {"name": t.name, "partitions": t.partitions, "replication_factor": t.replication_factor}
                for t in topics
            ]
            return {"items": items, "total": len(items)}
        except Exception as e:
            logger.error(f"Error listing Kafka topics: {e}")
            return {"items": [], "total": 0, "error": str(e)}
        finally:
            await admin.close()

    @router.get("/kafka/topics/{topic_name}")
    async def kafka_topic_detail(
        request: Request,
        topic_name: str,
        user: Any = Depends(check_superuser_access),
    ):
        """Get detailed information about a topic."""
        admin = await _get_kafka_admin()
        if not admin:
            raise HTTPException(503, "Kafka not configured")
        
        try:
            info = await admin.describe_topic(topic_name)
            if not info:
                raise HTTPException(404, f"Topic '{topic_name}' not found")
            
            partitions = await admin.describe_topic_partitions(topic_name)
            
            return {
                "name": info.name,
                "partitions_count": info.partitions,
                "replication_factor": info.replication_factor,
                "configs": info.configs,
                "partitions": [
                    {"partition": p.partition, "leader": p.leader, "replicas": p.replicas, "isr": p.isr}
                    for p in partitions
                ],
            }
        finally:
            await admin.close()

    @router.get("/kafka/throughput")
    async def kafka_throughput(
        request: Request,
        period: str = Query("6h", description="Period: 1h, 6h, 24h, 7d"),
        granularity: str = Query("5min", description="Granularity: 1min, 5min, 15min, 1h"),
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """
        Get Kafka throughput data for charts.
        
        Returns event counts aggregated by time buckets for produce/consume rate visualization.
        Based on EventLog data (requires event tracking to be enabled).
        """
        try:
            from core.models import get_session
            from core.admin.models import EventLog
            from core.datetime import timezone
            from datetime import timedelta
            from sqlalchemy import select, func
            
            # Parse period
            period_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}
            hours = period_map.get(period, 6)
            
            # Parse granularity
            granularity_map = {"1min": 60, "5min": 300, "15min": 900, "1h": 3600}
            bucket_seconds = granularity_map.get(granularity, 300)
            
            now = timezone.now()
            start = now - timedelta(hours=hours)
            
            db = await get_session()
            async with db:
                # Query events grouped by time bucket and direction
                # Using date_trunc for PostgreSQL or strftime for SQLite
                stmt = (
                    select(
                        EventLog.direction,
                        func.count().label("count"),
                        # Truncate to bucket
                        func.date_trunc("minute", EventLog.created_at).label("bucket"),
                    )
                    .where(EventLog.created_at >= start)
                    .group_by(EventLog.direction, "bucket")
                    .order_by("bucket")
                )
                
                result = await db.execute(stmt)
                rows = result.all()
                
                # Build time series
                labels = []
                produce_rate = []
                consume_rate = []
                
                # Group by bucket
                buckets: dict[str, dict[str, int]] = {}
                for row in rows:
                    bucket_key = row.bucket.isoformat() if row.bucket else ""
                    if bucket_key not in buckets:
                        buckets[bucket_key] = {"OUT": 0, "IN": 0}
                    buckets[bucket_key][row.direction] = row.count
                
                for bucket_key in sorted(buckets.keys()):
                    labels.append(bucket_key)
                    produce_rate.append(buckets[bucket_key].get("OUT", 0))
                    consume_rate.append(buckets[bucket_key].get("IN", 0))
                
                return {
                    "labels": labels,
                    "produce_rate": produce_rate,
                    "consume_rate": consume_rate,
                    "period_start": start.isoformat(),
                    "period_end": now.isoformat(),
                    "granularity_seconds": bucket_seconds,
                }
        except Exception as e:
            logger.error(f"Error getting Kafka throughput: {e}")
            return {"labels": [], "produce_rate": [], "consume_rate": [], "error": str(e)}

    @router.get("/kafka/consumer-groups/{group_id}/lag-history")
    async def kafka_consumer_group_lag_history(
        request: Request,
        group_id: str,
        period: str = Query("6h", description="Period: 1h, 6h, 24h, 7d"),
        granularity: str = Query("5min", description="Granularity: 1min, 5min, 15min, 1h"),
        user: Any = Depends(check_superuser_access),
    ):
        """Get consumer group lag history for charts."""
        admin = await _get_kafka_admin()
        if not admin:
            raise HTTPException(503, "Kafka not configured")
        
        try:
            detail = await admin.describe_consumer_group(group_id)
            if not detail:
                raise HTTPException(404, f"Consumer group '{group_id}' not found")
            
            from core.datetime import timezone
            now = timezone.now()
            
            return {
                "labels": [now.isoformat()],
                "lag": [detail.total_lag],
                "topics": {topic: [sum(po.lag for po in offsets)] for topic, offsets in detail.offsets.items()},
                "note": "Historical lag tracking requires periodic snapshots (not yet implemented)",
            }
        finally:
            await admin.close()

    # =====================================================================
    # Topics & Schemas Registry
    # =====================================================================

    @router.get("/topics/registered")
    async def topics_registered(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """
        List all registered Topic classes from the application.
        
        Discovers topics by importing the models/topics modules.
        """
        from core.config import get_settings
        import importlib
        
        settings = get_settings()
        
        # Try to import modules that might define topics
        modules_to_try = [
            getattr(settings, "topics_module", None),
            getattr(settings, "models_module", None),
            getattr(settings, "workers_module", None),
            "src.infra.topics",
            "src.topics",
            "src.events",
        ]
        
        imported_modules = []
        for module_name in modules_to_try:
            if module_name:
                try:
                    importlib.import_module(module_name)
                    imported_modules.append(module_name)
                except ImportError as e:
                    logger.debug(f"Could not import {module_name}: {e}")
        
        try:
            from core.messaging.topics import get_all_topics, Topic
            
            # Get topics from registry
            topics = get_all_topics()
            
            # Also find Topic subclasses directly (in case metaclass didn't register them)
            def find_topic_subclasses(cls, found=None):
                """Recursively find all Topic subclasses."""
                if found is None:
                    found = {}
                for subclass in cls.__subclasses__():
                    # Skip base pattern classes
                    if subclass.__name__ in {"EventTopic", "CommandTopic", "StateTopic"}:
                        find_topic_subclasses(subclass, found)
                        continue
                    # Add if it has a name
                    if hasattr(subclass, "name") and subclass.name:
                        found[subclass.name] = subclass
                    find_topic_subclasses(subclass, found)
                return found
            
            # Merge registry with discovered subclasses
            discovered = find_topic_subclasses(Topic)
            topics = {**discovered, **topics}  # Registry takes precedence
            
            logger.debug(f"Topics found: {len(topics)} items: {list(topics.keys())}")
            
            items = []
            for name, topic_cls in topics.items():
                schema_name = None
                avro_schema = None
                
                if hasattr(topic_cls, "schema") and topic_cls.schema:
                    schema_name = topic_cls.schema.__name__
                    if hasattr(topic_cls.schema, "__avro_schema__"):
                        try:
                            avro_schema = topic_cls.schema.__avro_schema__()
                        except Exception:
                            pass
                
                items.append({
                    "name": name,
                    "class_name": topic_cls.__name__,
                    "schema": schema_name,
                    "partitions": getattr(topic_cls, "partitions", 1),
                    "replication_factor": getattr(topic_cls, "replication_factor", 1),
                    "cleanup_policy": getattr(topic_cls, "cleanup_policy", "delete"),
                    "retention_ms": getattr(topic_cls, "retention_ms", None),
                    "value_serializer": getattr(topic_cls, "value_serializer", "json"),
                    "has_avro_schema": avro_schema is not None,
                })
            
            return {"items": items, "total": len(items)}
        except Exception as e:
            logger.warning("Failed to list registered topics: %s", e)
            return {"items": [], "total": 0, "error": str(e)}

    @router.get("/schemas/avro")
    async def schemas_avro(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """
        List all AvroModel classes discovered in the application.
        """
        from core.config import get_settings
        import importlib
        import json
        
        settings = get_settings()
        
        # Try to import modules that might define AvroModels
        modules_to_try = [
            getattr(settings, "topics_module", None),
            getattr(settings, "models_module", None),
            getattr(settings, "workers_module", None),
            "src.infra.topics",
            "src.topics",
            "src.events",
            "src.schemas",
        ]
        
        for module_name in modules_to_try:
            if module_name:
                try:
                    importlib.import_module(module_name)
                except ImportError:
                    pass
        
        def sanitize_for_json(obj):
            """Convert non-JSON-serializable objects to strings."""
            try:
                json.dumps(obj)
                return obj
            except (TypeError, ValueError):
                if isinstance(obj, dict):
                    return {k: sanitize_for_json(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [sanitize_for_json(v) for v in obj]
                else:
                    return str(obj)
        
        try:
            from core.messaging.avro import AvroModel
            
            # Find all AvroModel subclasses
            items = []
            
            def find_avro_models(cls):
                """Recursively find all AvroModel subclasses."""
                for subclass in cls.__subclasses__():
                    if subclass.__name__ != "AvroModel":
                        try:
                            schema = subclass.__avro_schema__()
                            # Sanitize schema to ensure JSON-serializable
                            safe_schema = sanitize_for_json(schema)
                            items.append({
                                "name": subclass.__name__,
                                "namespace": safe_schema.get("namespace", ""),
                                "fields": [
                                    {
                                        "name": f["name"],
                                        "type": str(f["type"]) if isinstance(f["type"], (dict, list)) else f["type"],
                                    }
                                    for f in safe_schema.get("fields", [])
                                ],
                                "schema": safe_schema,
                            })
                        except Exception as e:
                            items.append({
                                "name": subclass.__name__,
                                "error": str(e),
                            })
                    find_avro_models(subclass)
            
            find_avro_models(AvroModel)
            
            return {"items": items, "total": len(items)}
        except Exception as e:
            logger.warning("Failed to list Avro schemas: %s", e)
            return {"items": [], "total": 0, "error": str(e)}

    # =====================================================================
    # Events - Event Log Tracking
    # =====================================================================

    @router.get("/events")
    async def events_list(
        request: Request,
        page: int = Query(1, ge=1),
        per_page: int = Query(50, ge=1, le=200),
        topic: str = Query("", description="Filter by topic"),
        event_name: str = Query("", description="Filter by event name"),
        status: str = Query("", description="Filter by status"),
        direction: str = Query("", description="Filter by direction (IN/OUT)"),
        search: str = Query("", description="Search in event_id, event_name, key"),
        time_start: str = Query("", description="Filter events after this ISO timestamp"),
        time_end: str = Query("", description="Filter events before this ISO timestamp"),
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """List event logs with filters, search, and pagination."""
        try:
            from core.models import get_session
            from core.admin.models import EventLog
            from sqlalchemy import select, func, or_
            from datetime import datetime

            db = await get_session()
            async with db:
                filters = []

                if topic:
                    filters.append(EventLog.topic == topic)
                if event_name:
                    filters.append(EventLog.event_name == event_name)
                if status:
                    filters.append(EventLog.status == status)
                if direction:
                    filters.append(EventLog.direction == direction.upper())
                if search:
                    search_pattern = f"%{search}%"
                    filters.append(or_(
                        EventLog.event_id.ilike(search_pattern),
                        EventLog.event_name.ilike(search_pattern),
                        EventLog.key.ilike(search_pattern),
                        EventLog.topic.ilike(search_pattern),
                    ))
                if time_start:
                    try:
                        ts = datetime.fromisoformat(time_start.replace("Z", "+00:00"))
                        filters.append(EventLog.created_at >= ts)
                    except ValueError:
                        pass
                if time_end:
                    try:
                        te = datetime.fromisoformat(time_end.replace("Z", "+00:00"))
                        filters.append(EventLog.created_at <= te)
                    except ValueError:
                        pass

                base_query = select(EventLog)
                if filters:
                    base_query = base_query.where(*filters)

                count_query = select(func.count()).select_from(base_query.subquery())
                total = (await db.execute(count_query)).scalar() or 0

                items_query = (
                    base_query
                    .order_by(EventLog.created_at.desc())
                    .offset((page - 1) * per_page)
                    .limit(per_page)
                )
                result = await db.execute(items_query)
                items = result.scalars().all()

                return {
                    "items": [e.to_dict() for e in items],
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": (total + per_page - 1) // per_page if per_page else 1,
                }
        except Exception as e:
            logger.warning("Failed to list events: %s", e)
            return {"items": [], "total": 0, "page": 1, "per_page": per_page, "total_pages": 0}

    @router.get("/events/stats")
    async def events_stats(
        request: Request,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """
        Get event statistics.
        
        Returns counts by status, direction, top topics, and throughput.
        """
        try:
            from core.models import get_session
            from core.admin.models import EventLog
            from core.datetime import timezone
            from datetime import timedelta
            from sqlalchemy import select, func

            db = await get_session()
            async with db:
                # Total count
                total_stmt = select(func.count()).select_from(EventLog)
                total = (await db.execute(total_stmt)).scalar() or 0

                # Count by status
                status_stmt = (
                    select(EventLog.status, func.count())
                    .group_by(EventLog.status)
                )
                status_result = await db.execute(status_stmt)
                by_status = {row[0]: row[1] for row in status_result}

                # Count by direction
                direction_stmt = (
                    select(EventLog.direction, func.count())
                    .group_by(EventLog.direction)
                )
                direction_result = await db.execute(direction_stmt)
                by_direction = {row[0]: row[1] for row in direction_result}

                # Top topics
                topics_stmt = (
                    select(EventLog.topic, func.count().label("count"))
                    .group_by(EventLog.topic)
                    .order_by(func.count().desc())
                    .limit(10)
                )
                topics_result = await db.execute(topics_stmt)
                top_topics = [{"topic": row[0], "count": row[1]} for row in topics_result]

                # Top event names
                names_stmt = (
                    select(EventLog.event_name, func.count().label("count"))
                    .group_by(EventLog.event_name)
                    .order_by(func.count().desc())
                    .limit(10)
                )
                names_result = await db.execute(names_stmt)
                top_events = [{"event_name": row[0], "count": row[1]} for row in names_result]

                # Throughput (last 5 minutes)
                now = timezone.now()
                five_min_ago = now - timedelta(minutes=5)
                throughput_stmt = (
                    select(func.count())
                    .select_from(EventLog)
                    .where(EventLog.created_at >= five_min_ago)
                )
                recent_count = (await db.execute(throughput_stmt)).scalar() or 0
                throughput_per_min = recent_count / 5.0

                # Success rate
                sent = by_status.get("sent", 0)
                delivered = by_status.get("delivered", 0)
                failed = by_status.get("failed", 0)
                success_total = sent + delivered + failed
                success_rate = ((sent + delivered) / success_total * 100) if success_total > 0 else 100.0

                return {
                    "total": total,
                    "by_status": by_status,
                    "by_direction": by_direction,
                    "top_topics": top_topics,
                    "top_events": top_events,
                    "throughput_per_min": round(throughput_per_min, 2),
                    "success_rate": round(success_rate, 2),
                    "sent": sent,
                    "delivered": delivered,
                    "failed": failed,
                    "pending": by_status.get("pending", 0),
                }
        except Exception as e:
            logger.warning("Failed to get event stats: %s", e)
            return {"total": 0, "by_status": {}, "by_direction": {}}

    @router.get("/events/timeline")
    async def events_timeline(
        request: Request,
        period: str = Query("1h", description="Period: 1h, 6h, 24h, 7d"),
        granularity: str = Query("1min", description="Granularity: 1min, 5min, 15min, 1h"),
        topic: str = Query("", description="Filter by topic"),
        event_name: str = Query("", description="Filter by event name"),
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """
        Get event timeline data for charts.
        
        Returns aggregated event counts by time bucket for visualization.
        """
        try:
            from core.models import get_session
            from core.admin.models import EventLog
            from core.datetime import timezone
            from datetime import timedelta
            from sqlalchemy import select, func, and_

            # Parse period
            period_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}
            hours = period_map.get(period, 1)

            # Parse granularity
            granularity_map = {"1min": 60, "5min": 300, "15min": 900, "1h": 3600}
            bucket_seconds = granularity_map.get(granularity, 60)

            now = timezone.now()
            start = now - timedelta(hours=hours)

            db = await get_session()
            async with db:
                # Build filters
                filters = [EventLog.created_at >= start]
                if topic:
                    filters.append(EventLog.topic == topic)
                if event_name:
                    filters.append(EventLog.event_name == event_name)

                # Query events grouped by time bucket and status
                stmt = (
                    select(
                        EventLog.status,
                        func.count().label("count"),
                        func.date_trunc("minute", EventLog.created_at).label("bucket"),
                    )
                    .where(and_(*filters))
                    .group_by(EventLog.status, "bucket")
                    .order_by("bucket")
                )

                result = await db.execute(stmt)
                rows = result.all()

                # Build time series
                buckets: dict[str, dict[str, int]] = {}
                for row in rows:
                    bucket_key = row.bucket.isoformat() if row.bucket else ""
                    if bucket_key not in buckets:
                        buckets[bucket_key] = {"total": 0, "sent": 0, "delivered": 0, "failed": 0, "pending": 0}
                    buckets[bucket_key][row.status] = row.count
                    buckets[bucket_key]["total"] += row.count

                labels = sorted(buckets.keys())
                datasets = {
                    "total": [buckets[k]["total"] for k in labels],
                    "sent": [buckets[k]["sent"] for k in labels],
                    "delivered": [buckets[k]["delivered"] for k in labels],
                    "failed": [buckets[k]["failed"] for k in labels],
                    "pending": [buckets[k]["pending"] for k in labels],
                }

                return {
                    "labels": labels,
                    "datasets": datasets,
                    "period_start": start.isoformat(),
                    "period_end": now.isoformat(),
                    "granularity_seconds": bucket_seconds,
                }
        except Exception as e:
            logger.error(f"Error getting events timeline: {e}")
            return {"labels": [], "datasets": {}, "error": str(e)}

    @router.get("/events/range")
    async def events_in_range(
        request: Request,
        start: str = Query(..., description="Start datetime (ISO format)"),
        end: str = Query(..., description="End datetime (ISO format)"),
        topic: str = Query("", description="Filter by topic"),
        status: str = Query("", description="Filter by status"),
        page: int = Query(1, ge=1),
        per_page: int = Query(50, ge=1, le=200),
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """
        Get events in a specific time range.
        
        Used for drill-down when clicking on chart points.
        """
        try:
            from core.models import get_session
            from core.admin.models import EventLog
            from core.querysets import QuerySet
            from datetime import datetime

            # Parse dates
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))

            db = await get_session()
            async with db:
                qs = QuerySet(EventLog, db)
                qs = qs.filter(created_at__gte=start_dt, created_at__lte=end_dt)

                if topic:
                    qs = qs.filter(topic=topic)
                if status:
                    qs = qs.filter(status=status)

                total = await qs.count()
                items = await qs.order_by("-created_at").offset(
                    (page - 1) * per_page
                ).limit(per_page).all()

                return {
                    "items": [e.to_dict() for e in items],
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": (total + per_page - 1) // per_page if per_page else 1,
                    "range_start": start,
                    "range_end": end,
                }
        except Exception as e:
            logger.error(f"Error getting events in range: {e}")
            return {"items": [], "total": 0, "error": str(e)}

    @router.get("/events/{event_id}")
    async def event_detail(
        request: Request,
        event_id: str,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """
        Get detailed information about a specific event.
        """
        try:
            from core.models import get_session
            from core.admin.models import EventLog
            from core.querysets import QuerySet

            db = await get_session()
            async with db:
                qs = QuerySet(EventLog, db)
                item = await qs.filter(event_id=event_id).first()
                if not item:
                    raise HTTPException(404, "Event not found")
                return {"item": item.to_dict()}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    @router.post("/events/{event_id}/resend")
    async def event_resend(
        request: Request,
        event_id: str,
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """
        Resend an event to its original topic.
        
        Creates a new EventLog entry referencing the original event.
        """
        try:
            from core.models import get_session
            from core.admin.models import EventLog
            from core.querysets import QuerySet
            from core.config import get_settings
            import uuid
            import json

            db = await get_session()
            async with db:
                qs = QuerySet(EventLog, db)
                original = await qs.filter(event_id=event_id).first()
                if not original:
                    raise HTTPException(404, "Event not found")

                # Get producer
                settings = get_settings()
                if not settings.kafka_enabled:
                    raise HTTPException(503, "Kafka not configured")

                backend = getattr(settings, "kafka_backend", "aiokafka")
                if backend == "confluent":
                    from core.messaging.confluent import ConfluentProducer
                    producer = ConfluentProducer()
                else:
                    from core.messaging.kafka import KafkaProducer
                    producer = KafkaProducer()

                await producer.start()

                try:
                    # Create new event ID
                    new_event_id = str(uuid.uuid4())

                    # Parse original payload and headers
                    payload = json.loads(original.payload_json) if original.payload_json else {}
                    headers = json.loads(original.headers_json) if original.headers_json else {}

                    # Update headers with new event ID and resend info
                    headers["event_id"] = new_event_id
                    headers["original_event_id"] = original.event_id
                    headers["resent_at"] = timezone.now().isoformat()

                    # Create new EventLog entry
                    new_log = EventLog(
                        event_id=new_event_id,
                        event_name=original.event_name,
                        topic=original.topic,
                        key=original.key,
                        headers_json=json.dumps(headers),
                        payload_json=original.payload_json,
                        payload_schema=original.payload_schema,
                        payload_size_bytes=original.payload_size_bytes,
                        direction="OUT",
                        status="pending",
                        original_event_id=original.event_id,
                        source_service="admin-resend",
                    )
                    await new_log.save(db)

                    # Send to Kafka
                    result = await producer.send(
                        original.topic,
                        payload,
                        key=original.key,
                        headers=[(k, v.encode() if isinstance(v, str) else v) for k, v in headers.items()],
                    )

                    # Update log with result
                    from core.datetime import timezone
                    new_log.status = "sent"
                    new_log.partition = result.partition if hasattr(result, "partition") else None
                    new_log.offset = result.offset if hasattr(result, "offset") else None
                    new_log.sent_at = timezone.now()
                    await new_log.save(db)

                    return {
                        "status": "resent",
                        "new_event_id": new_event_id,
                        "original_event_id": original.event_id,
                        "topic": original.topic,
                    }

                finally:
                    await producer.stop()

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error resending event: {e}")
            raise HTTPException(500, str(e))

    @router.post("/events/purge")
    async def events_purge(
        request: Request,
        days: int = Query(30, ge=1, description="Purge events older than N days"),
        user: Any = Depends(check_superuser_access),
    ) -> dict:
        """
        Purge old event logs.
        """
        try:
            from core.models import get_session
            from core.admin.models import EventLog
            from core.datetime import timezone
            from datetime import timedelta
            from sqlalchemy import delete

            cutoff = timezone.now() - timedelta(days=days)

            db = await get_session()
            async with db:
                stmt = delete(EventLog).where(EventLog.created_at < cutoff)
                result = await db.execute(stmt)
                await db.commit()
                return {"purged": result.rowcount, "older_than_days": days}
        except Exception as e:
            raise HTTPException(500, str(e))

    return router


# ─── Kafka Admin Helper ─────────────────────────────────────────────


async def _get_kafka_admin():
    """
    Get the appropriate Kafka admin client based on configuration.
    
    Returns KafkaAdmin (aiokafka) or ConfluentAdmin based on kafka_backend setting.
    Returns None if Kafka is not configured or connection fails.
    """
    from core.config import get_settings
    
    settings = get_settings()
    
    if not settings.kafka_enabled:
        return None
    
    backend = getattr(settings, "kafka_backend", "aiokafka")
    
    try:
        if backend == "confluent":
            from core.messaging.confluent import ConfluentAdmin
            admin = ConfluentAdmin()
        else:
            from core.messaging.kafka import KafkaAdmin
            admin = KafkaAdmin()
        
        await admin.connect()
        return admin
    except Exception as e:
        logger.warning(f"Failed to connect to Kafka admin: {e}")
        return None


async def _list_registered_topics() -> dict:
    """Return { items, total } for registered Topic classes (used by ops_system)."""
    from core.config import get_settings
    import importlib
    settings = get_settings()
    for module_name in [
        getattr(settings, "topics_module", None),
        getattr(settings, "models_module", None),
        getattr(settings, "workers_module", None),
    ]:
        if module_name:
            try:
                importlib.import_module(module_name)
            except ImportError:
                pass
    try:
        from core.messaging.topics import get_all_topics, Topic
        topics = get_all_topics()

        def find_topic_subclasses(cls, found=None):
            if found is None:
                found = {}
            for subclass in cls.__subclasses__():
                if subclass.__name__ in {"EventTopic", "CommandTopic", "StateTopic"}:
                    find_topic_subclasses(subclass, found)
                    continue
                if hasattr(subclass, "name") and subclass.name:
                    found[subclass.name] = subclass
                find_topic_subclasses(subclass, found)
            return found
        discovered = find_topic_subclasses(Topic)
        topics = {**discovered, **topics}
        items = []
        for name, topic_cls in topics.items():
            schema_name = getattr(topic_cls.schema, "__name__", None) if getattr(topic_cls, "schema", None) else None
            avro_schema = None
            if hasattr(topic_cls, "schema") and topic_cls.schema and hasattr(topic_cls.schema, "__avro_schema__"):
                try:
                    avro_schema = topic_cls.schema.__avro_schema__()
                except Exception:
                    pass
            items.append({
                "name": name,
                "class_name": topic_cls.__name__,
                "schema": schema_name,
                "partitions": getattr(topic_cls, "partitions", 1),
                "replication_factor": getattr(topic_cls, "replication_factor", 1),
                "cleanup_policy": getattr(topic_cls, "cleanup_policy", "delete"),
                "retention_ms": getattr(topic_cls, "retention_ms", None),
                "value_serializer": getattr(topic_cls, "value_serializer", "json"),
                "has_avro_schema": avro_schema is not None,
            })
        return {"items": items, "total": len(items)}
    except Exception as e:
        logger.warning("_list_registered_topics: %s", e)
        return {"items": [], "total": 0, "error": str(e)}


async def _list_avro_schemas() -> dict:
    """Return { items, total } for AvroModel classes (used by ops_system)."""
    from core.config import get_settings
    import importlib
    settings = get_settings()
    for module_name in [
        getattr(settings, "topics_module", None),
        getattr(settings, "models_module", None),
        getattr(settings, "workers_module", None),
        "src.schemas",
    ]:
        if module_name:
            try:
                importlib.import_module(module_name)
            except ImportError:
                pass

    def sanitize_for_json(obj):
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            if isinstance(obj, dict):
                return {k: sanitize_for_json(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [sanitize_for_json(v) for v in obj]
            return str(obj)

    try:
        from core.messaging.avro import AvroModel
        items = []

        def find_avro_models(cls):
            for subclass in cls.__subclasses__():
                if subclass.__name__ != "AvroModel":
                    try:
                        schema = subclass.__avro_schema__()
                        safe_schema = sanitize_for_json(schema)
                        items.append({
                            "name": subclass.__name__,
                            "namespace": safe_schema.get("namespace", ""),
                            "fields": [
                                {"name": f["name"], "type": str(f["type"]) if isinstance(f["type"], (dict, list)) else f["type"]}
                                for f in safe_schema.get("fields", [])
                            ],
                            "schema": safe_schema,
                        })
                    except Exception as e:
                        items.append({"name": subclass.__name__, "error": str(e)})
                find_avro_models(subclass)
        find_avro_models(AvroModel)
        return {"items": items, "total": len(items)}
    except Exception as e:
        logger.warning("_list_avro_schemas: %s", e)
        return {"items": [], "total": 0, "error": str(e)}


async def _kafka_throughput(period: str, granularity: str) -> dict:
    """Return throughput data for charts (used by ops_system_kafka resource=throughput)."""
    try:
        from core.models import get_session
        from core.admin.models import EventLog
        from core.datetime import timezone
        from datetime import timedelta
        from sqlalchemy import select, func
        period_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}
        hours = period_map.get(period, 6)
        granularity_map = {"1min": 60, "5min": 300, "15min": 900, "1h": 3600}
        bucket_seconds = granularity_map.get(granularity, 300)
        now = timezone.now()
        start = now - timedelta(hours=hours)
        db = await get_session()
        async with db:
            stmt = (
                select(
                    EventLog.direction,
                    func.count().label("count"),
                    func.date_trunc("minute", EventLog.created_at).label("bucket"),
                )
                .where(EventLog.created_at >= start)
                .group_by(EventLog.direction, "bucket")
                .order_by("bucket")
            )
            result = await db.execute(stmt)
            rows = result.all()
            buckets = {}
            for row in rows:
                bucket_key = row.bucket.isoformat() if row.bucket else ""
                if bucket_key not in buckets:
                    buckets[bucket_key] = {"OUT": 0, "IN": 0}
                buckets[bucket_key][row.direction] = row.count
            labels = sorted(buckets.keys())
            produce_rate = [buckets[k].get("OUT", 0) for k in labels]
            consume_rate = [buckets[k].get("IN", 0) for k in labels]
            return {
                "labels": labels,
                "produce_rate": produce_rate,
                "consume_rate": consume_rate,
                "period_start": start.isoformat(),
                "period_end": now.isoformat(),
                "granularity_seconds": bucket_seconds,
            }
    except Exception as e:
        logger.error("_kafka_throughput: %s", e)
        return {"labels": [], "produce_rate": [], "consume_rate": [], "error": str(e)}


# ─── Serializers ─────────────────────────────────────────────────


def _serialize_task_execution(task: Any) -> dict[str, Any]:
    """Serialize a TaskExecution model instance."""
    return {
        "id": task.id,
        "task_name": task.task_name,
        "task_id": task.task_id,
        "queue": task.queue,
        "status": task.status,
        "args_json": task.args_json,
        "kwargs_json": task.kwargs_json,
        "result_json": task.result_json,
        "error": task.error,
        "retries": task.retries,
        "max_retries": task.max_retries,
        "duration_ms": task.duration_ms,
        "worker_id": task.worker_id,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


def _serialize_worker(worker: Any) -> dict[str, Any]:
    """Serialize a WorkerHeartbeat model instance."""
    return {
        "id": worker.id,
        "worker_id": worker.worker_id,
        "worker_type": worker.worker_type,
        "worker_name": worker.worker_name,
        "hostname": worker.hostname,
        "pid": worker.pid,
        "status": worker.status,
        "concurrency": worker.concurrency,
        "active_tasks": worker.active_tasks,
        "total_processed": worker.total_processed,
        "total_errors": worker.total_errors,
        "queues_json": worker.queues_json,
        "started_at": worker.started_at.isoformat() if worker.started_at else None,
        "last_heartbeat": worker.last_heartbeat.isoformat() if worker.last_heartbeat else None,
        "metadata_json": worker.metadata_json,
    }
