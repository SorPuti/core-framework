"""
WebSocket endpoint for real-time Operations Center updates.

Provides real-time streaming of:
- Kafka events (sent, delivered, failed)
- Worker heartbeats
- Task status changes

Usage:
    # Connect to WebSocket
    ws = new WebSocket('ws://localhost:8000/admin/ws/ops/events')
    
    # Receive updates
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        switch(data.type) {
            case 'kafka_sent': ...
            case 'kafka_delivered': ...
            case 'worker_heartbeat': ...
        }
    }
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, TYPE_CHECKING

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Request
from starlette.websockets import WebSocketState

from core.admin.event_tracking import subscribe_events, unsubscribe_events

if TYPE_CHECKING:
    from core.admin.site import AdminSite

logger = logging.getLogger("core.admin.ws_events")


def create_ws_router(site: "AdminSite") -> APIRouter:
    """Create the WebSocket router for Operations Center."""
    router = APIRouter(tags=["admin-ws"])

    async def _ws_ops_stream_handler(websocket: WebSocket) -> None:
        """Unified stream: events, worker heartbeats, task started/finished, metrics push."""
        await websocket.accept()
        queue = subscribe_events()
        metrics_interval = 10.0
        ping_interval = 30.0
        last_ping = time.monotonic()
        last_metrics = 0.0
        try:
            await websocket.send_json({
                "type": "connected",
                "message": "Connected to Operations Center stream",
            })
            while True:
                try:
                    wait = min(metrics_interval, ping_interval)
                    message = await asyncio.wait_for(queue.get(), timeout=wait)
                    if websocket.client_state != WebSocketState.CONNECTED:
                        break
                    await websocket.send_text(message)
                except asyncio.TimeoutError:
                    if websocket.client_state != WebSocketState.CONNECTED:
                        break
                    now = time.monotonic()
                    if now - last_metrics >= metrics_interval:
                        last_metrics = now
                        try:
                            from core.admin.ops_views import get_dashboard_snapshot
                            snapshot = await get_dashboard_snapshot()
                            await websocket.send_json({
                                "type": "dashboard_snapshot",
                                "data": snapshot,
                            })
                        except Exception as e:
                            logger.debug("Dashboard snapshot push failed: %s", e)
                    if now - last_ping >= ping_interval:
                        last_ping = now
                        await websocket.send_json({"type": "ping"})
        except WebSocketDisconnect:
            logger.debug("WebSocket client disconnected")
        except Exception as e:
            logger.warning("WebSocket error: %s", e)
        finally:
            unsubscribe_events(queue)
            if websocket.client_state == WebSocketState.CONNECTED:
                try:
                    await websocket.close()
                except Exception:
                    pass

    @router.websocket("/ws/ops/stream")
    async def ws_ops_stream(websocket: WebSocket):
        """Unified real-time stream for Operations Center (events, tasks, workers)."""
        await _ws_ops_stream_handler(websocket)

    @router.websocket("/ws/ops/events")
    async def ws_ops_events(websocket: WebSocket):
        """
        WebSocket endpoint for real-time Operations Center events.
        
        Streams:
        - kafka_pending: Event queued for sending
        - kafka_sent: Event successfully sent to Kafka
        - kafka_delivered: Event received from Kafka
        - kafka_failed: Event failed to send
        - worker_heartbeat: Worker status update
        - task_started: Task execution started
        - task_finished: Task execution finished
        
        Message format:
        {
            "type": "kafka_sent",
            "data": {
                "event_id": "...",
                "event_name": "...",
                "topic": "...",
                ...
            }
        }
        """
        await websocket.accept()
        
        # Check authentication (optional - can be enforced via middleware)
        # For now, we allow connection but could add session check here
        
        # Subscribe to event broadcasts
        queue = subscribe_events()
        
        try:
            # Send initial connection message
            await websocket.send_json({
                "type": "connected",
                "message": "Connected to Operations Center events stream",
            })
            
            # Main loop: forward events from queue to WebSocket
            while True:
                try:
                    # Wait for events with timeout for keepalive
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    
                    # Check if websocket is still connected
                    if websocket.client_state != WebSocketState.CONNECTED:
                        break
                    
                    # Send the event
                    await websocket.send_text(message)
                    
                except asyncio.TimeoutError:
                    # Send keepalive ping
                    if websocket.client_state == WebSocketState.CONNECTED:
                        await websocket.send_json({"type": "ping"})
                    else:
                        break
                        
        except WebSocketDisconnect:
            logger.debug("WebSocket client disconnected")
        except Exception as e:
            logger.warning(f"WebSocket error: {e}")
        finally:
            # Unsubscribe from events
            unsubscribe_events(queue)
            
            # Close websocket if still open
            if websocket.client_state == WebSocketState.CONNECTED:
                try:
                    await websocket.close()
                except Exception:
                    pass

    return router


# ─── Worker Heartbeat Broadcasting ─────────────────────────────────


async def broadcast_worker_heartbeat(worker_data: dict) -> None:
    """
    Broadcast a worker heartbeat update to all WebSocket clients.
    
    Called by the worker heartbeat system to notify the dashboard
    of worker status changes.
    
    Args:
        worker_data: Serialized worker data
    """
    from core.admin.event_tracking import broadcast_event
    await broadcast_event("worker_heartbeat", worker_data)


async def broadcast_worker_offline(worker_id: str) -> None:
    """
    Broadcast that a worker has gone offline.
    
    Args:
        worker_id: ID of the worker that went offline
    """
    from core.admin.event_tracking import broadcast_event
    await broadcast_event("worker_offline", {"worker_id": worker_id})


# ─── Task Status Broadcasting ─────────────────────────────────


async def broadcast_task_started(task_data: dict) -> None:
    """
    Broadcast that a task has started execution.
    
    Args:
        task_data: Serialized task execution data
    """
    from core.admin.event_tracking import broadcast_event
    await broadcast_event("task_started", task_data)


async def broadcast_task_finished(task_data: dict) -> None:
    """
    Broadcast that a task has finished execution.
    
    Args:
        task_data: Serialized task execution data
    """
    from core.admin.event_tracking import broadcast_event
    await broadcast_event("task_finished", task_data)
