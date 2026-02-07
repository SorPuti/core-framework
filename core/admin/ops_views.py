"""
Operations Center — API endpoints.

Provides JSON endpoints for:
- Infrastructure monitoring
- Task management (list, detail, retry, cancel)
- Worker management (list, detail, heartbeats)
- Log streaming (SSE) and recent logs
- Resource inventory
"""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
from typing import Any, TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from core.admin.permissions import check_admin_access

if TYPE_CHECKING:
    from core.admin.site import AdminSite

logger = logging.getLogger("core.admin.ops")


def create_ops_api(site: "AdminSite") -> APIRouter:
    """Create the Operations Center API router."""
    router = APIRouter(prefix="/api/ops", tags=["admin-ops"])

    # =====================================================================
    # Infrastructure
    # =====================================================================

    @router.get("/infrastructure")
    async def infrastructure_view(
        request: Request,
        user: Any = Depends(check_admin_access),
    ) -> dict:
        """Full infrastructure report."""
        from core.admin.infrastructure import InfraDetector
        return await InfraDetector.collect()

    @router.get("/infrastructure/health")
    async def infrastructure_health(
        request: Request,
        user: Any = Depends(check_admin_access),
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
        user: Any = Depends(check_admin_access),
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
        user: Any = Depends(check_admin_access),
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
        user: Any = Depends(check_admin_access),
    ) -> dict:
        """List all registered tasks (from registry)."""
        from core.tasks.registry import list_tasks
        return {"tasks": list_tasks()}

    @router.get("/tasks/{task_id}")
    async def task_detail(
        request: Request,
        task_id: str,
        user: Any = Depends(check_admin_access),
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
        user: Any = Depends(check_admin_access),
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
        user: Any = Depends(check_admin_access),
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
        user: Any = Depends(check_admin_access),
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
        user: Any = Depends(check_admin_access),
    ) -> dict:
        """List periodic tasks (from registry + persisted state)."""
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
        user: Any = Depends(check_admin_access),
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
        user: Any = Depends(check_admin_access),
    ) -> dict:
        """Manually trigger a periodic task."""
        from core.tasks.registry import get_periodic_tasks, get_task_producer
        from core.tasks.base import TaskMessage
        import uuid

        tasks = get_periodic_tasks()
        if task_name not in tasks:
            raise HTTPException(404, f"Periodic task '{task_name}' not found")

        pt = tasks[task_name]
        msg = TaskMessage(
            task_id=str(uuid.uuid4()),
            task_name=task_name,
            queue=pt.queue,
        )

        try:
            producer = await get_task_producer()
            await producer.send(f"tasks.{msg.queue}", msg.to_dict())
            return {"status": "dispatched", "task_id": msg.task_id}
        except Exception as e:
            raise HTTPException(500, f"Failed to dispatch: {e}")

    # =====================================================================
    # Workers
    # =====================================================================

    @router.get("/workers")
    async def workers_list(
        request: Request,
        user: Any = Depends(check_admin_access),
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
        user: Any = Depends(check_admin_access),
    ) -> dict:
        """List all registered message workers (from registry)."""
        try:
            from core.messaging.workers import get_all_workers
            workers = get_all_workers()
            items = []
            for name, cfg in workers.items():
                items.append({
                    "name": name,
                    "input_topic": cfg.input_topic,
                    "output_topic": cfg.output_topic,
                    "concurrency": cfg.concurrency,
                    "group_id": cfg.group_id,
                })
            return {"items": items, "total": len(items)}
        except Exception as e:
            logger.warning("Failed to list registered workers: %s", e)
            return {"items": [], "total": 0}

    @router.get("/workers/{worker_id}")
    async def worker_detail(
        request: Request,
        worker_id: str,
        user: Any = Depends(check_admin_access),
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
        user: Any = Depends(check_admin_access),
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
        user: Any = Depends(check_admin_access),
    ):
        """SSE endpoint for real-time log streaming."""
        from core.admin.log_handler import get_log_buffer

        buffer = get_log_buffer()
        level_no = getattr(logging, level.upper(), logging.INFO) if level else logging.INFO

        async def event_generator():
            queue = buffer.subscribe()
            try:
                while True:
                    try:
                        entry = await asyncio.wait_for(queue.get(), timeout=30.0)
                    except asyncio.TimeoutError:
                        # Send keepalive
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

            except asyncio.CancelledError:
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
        user: Any = Depends(check_admin_access),
    ) -> dict:
        """Unified resource inventory."""
        from core.admin.resource_inventory import ResourceInventory
        return await ResourceInventory.collect(site)

    return router


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
