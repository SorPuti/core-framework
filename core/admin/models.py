"""
Models do Admin Panel.

Modelos core usados internamente pelo admin:
- AuditLog: Log de ações administrativas
- AdminSession: Sessões do admin (browser-based)
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from sqlalchemy.orm import Mapped
from sqlalchemy import Text

from core.models import Model, Field
from core.fields import AdvancedField
from core.datetime import DateTime

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AuditLog(Model):
    """
    Log de ações administrativas.
    
    Registra quem fez o que, quando, e o que mudou.
    Sempre visível no admin para superusers.
    """
    __tablename__ = "admin_audit_log"
    ACTION_MAX_LENGTH = 100
    
    id: Mapped[int] = Field.pk()
    # VARCHAR para aceitar qualquer tipo de PK do User (int, UUID, string)
    user_id: Mapped[str] = Field.string(max_length=255, index=True)
    user_email: Mapped[str] = Field.string(max_length=255)
    action: Mapped[str] = Field.string(max_length=ACTION_MAX_LENGTH)  # create, update, delete, action:*, bulk_delete
    app_label: Mapped[str] = Field.string(max_length=100)
    model_name: Mapped[str] = Field.string(max_length=100)
    object_id: Mapped[str] = Field.string(max_length=255)
    object_repr: Mapped[str] = Field.string(max_length=500, default="")
    changes: Mapped[dict | None] = AdvancedField.json_field(nullable=True)
    ip_address: Mapped[str | None] = Field.string(max_length=45, nullable=True)
    user_agent: Mapped[str | None] = Field.string(max_length=500, nullable=True)
    timestamp: Mapped[DateTime] = Field.datetime(auto_now_add=True)
    
    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.model_name} #{self.object_id} by {self.user_email}>"
    
    @classmethod
    async def log_action(
        cls,
        db: "AsyncSession",
        *,
        user: Any,
        action: str,
        app_label: str,
        model_name: str,
        object_id: str,
        object_repr: str = "",
        changes: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> "AuditLog":
        """
        Registra uma ação no audit log.
        
        Args:
            db: Sessão do banco
            user: Usuário que executou a ação
            action: Tipo de ação (create, update, delete)
            app_label: Label do app
            model_name: Nome do model
            object_id: ID do objeto afetado
            object_repr: Representação textual do objeto
            changes: Dict com as alterações (antes/depois)
            ip_address: IP do cliente
            user_agent: User-Agent do browser
        """
        # Keep action DB-safe and preserve full value when truncation is needed.
        safe_changes = dict(changes or {})
        safe_action = str(action or "").strip() or "action"
        if len(safe_action) > cls.ACTION_MAX_LENGTH:
            safe_changes.setdefault("_audit_action_full", safe_action)
            safe_action = safe_action[: cls.ACTION_MAX_LENGTH]

        log = cls(
            user_id=str(getattr(user, "id", "0")),
            user_email=getattr(user, "email", str(user)),
            action=safe_action,
            app_label=app_label,
            model_name=model_name,
            object_id=str(object_id),
            object_repr=object_repr[:500],
            changes=safe_changes or None,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else None,
        )
        await log.save(db)
        return log


class TaskExecution(Model):
    """
    Persists task execution history for monitoring in the admin panel.

    Created automatically by the TaskWorker when ops_task_persist is enabled.
    """
    __tablename__ = "admin_task_executions"

    id: Mapped[int] = Field.pk()
    task_name: Mapped[str] = Field.string(max_length=255, index=True)
    task_id: Mapped[str] = Field.string(max_length=64, unique=True, index=True)
    queue: Mapped[str] = Field.string(max_length=100, default="default")
    status: Mapped[str] = Field.string(max_length=20, index=True)  # PENDING, RUNNING, SUCCESS, FAILURE, RETRY, CANCELLED
    args_json: Mapped[str | None] = Field.string(max_length=5000, nullable=True)
    kwargs_json: Mapped[str | None] = Field.string(max_length=5000, nullable=True)
    result_json: Mapped[str | None] = Field.string(max_length=5000, nullable=True)
    error: Mapped[str | None] = Field.string(max_length=5000, nullable=True)
    retries: Mapped[int] = Field.integer(default=0)
    max_retries: Mapped[int] = Field.integer(default=3)
    duration_ms: Mapped[int | None] = Field.integer(nullable=True)
    worker_id: Mapped[str | None] = Field.string(max_length=64, nullable=True)
    started_at: Mapped[DateTime | None] = Field.datetime(nullable=True)
    finished_at: Mapped[DateTime | None] = Field.datetime(nullable=True)
    created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)

    def __repr__(self) -> str:
        return f"<TaskExecution {self.task_name} [{self.status}] {self.task_id[:8]}>"

    @classmethod
    async def record_start(
        cls,
        db: "AsyncSession",
        *,
        task_name: str,
        task_id: str,
        queue: str = "default",
        args_json: str | None = None,
        kwargs_json: str | None = None,
        max_retries: int = 3,
        worker_id: str | None = None,
    ) -> "TaskExecution":
        """Record task execution start."""
        from core.datetime import timezone
        execution = cls(
            task_name=task_name,
            task_id=task_id,
            queue=queue,
            status="RUNNING",
            args_json=args_json,
            kwargs_json=kwargs_json,
            max_retries=max_retries,
            worker_id=worker_id,
            started_at=timezone.now(),
        )
        await execution.save(db)
        return execution

    @classmethod
    async def record_finish(
        cls,
        db: "AsyncSession",
        *,
        task_id: str,
        status: str,
        result_json: str | None = None,
        error: str | None = None,
        retries: int = 0,
        duration_ms: int | None = None,
    ) -> None:
        """Record task execution completion."""
        from core.datetime import timezone
        from sqlalchemy import update
        stmt = (
            update(cls)
            .where(cls.task_id == task_id)
            .values(
                status=status,
                result_json=result_json,
                error=error,
                retries=retries,
                duration_ms=duration_ms,
                finished_at=timezone.now(),
            )
        )
        await db.execute(stmt)
        await db.commit()


class PeriodicTaskSchedule(Model):
    """
    Persisted state of periodic tasks for admin management.

    Synced from the in-memory periodic task registry on startup.
    Allows admin to enable/disable periodic tasks.
    """
    __tablename__ = "admin_periodic_tasks"

    id: Mapped[int] = Field.pk()
    task_name: Mapped[str] = Field.string(max_length=255, unique=True, index=True)
    cron: Mapped[str | None] = Field.string(max_length=100, nullable=True)
    interval_seconds: Mapped[int | None] = Field.integer(nullable=True)
    queue: Mapped[str] = Field.string(max_length=100, default="scheduled")
    is_enabled: Mapped[bool] = Field.boolean(default=True)
    last_run: Mapped[DateTime | None] = Field.datetime(nullable=True)
    next_run: Mapped[DateTime | None] = Field.datetime(nullable=True)
    run_count: Mapped[int] = Field.integer(default=0)
    last_status: Mapped[str | None] = Field.string(max_length=20, nullable=True)
    last_duration_ms: Mapped[int | None] = Field.integer(nullable=True)
    created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)

    def __repr__(self) -> str:
        schedule = self.cron or f"every {self.interval_seconds}s"
        return f"<PeriodicTaskSchedule {self.task_name} ({schedule})>"


class WorkerHeartbeat(Model):
    """
    Tracks active workers via periodic heartbeat.

    Workers create a record on boot and update it periodically.
    Uses a deterministic worker_hash for UPSERT so restarts reuse
    the same row instead of creating duplicates (Issue #19).
    """
    __tablename__ = "admin_worker_heartbeats"

    id: Mapped[int] = Field.pk()
    worker_id: Mapped[str] = Field.string(max_length=64, unique=True, index=True)
    worker_hash: Mapped[str | None] = Field.string(max_length=64, unique=True, nullable=True, index=True)
    worker_type: Mapped[str] = Field.string(max_length=30)  # task_worker, message_worker
    worker_name: Mapped[str] = Field.string(max_length=255)
    hostname: Mapped[str] = Field.string(max_length=255)
    pid: Mapped[int] = Field.integer()
    status: Mapped[str] = Field.string(max_length=20, default="ONLINE")  # ONLINE, OFFLINE, DRAINING
    concurrency: Mapped[int] = Field.integer(default=1)
    active_tasks: Mapped[int] = Field.integer(default=0)
    total_processed: Mapped[int] = Field.integer(default=0)
    total_errors: Mapped[int] = Field.integer(default=0)
    queues_json: Mapped[str | None] = Field.string(max_length=1000, nullable=True)
    started_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)
    last_heartbeat: Mapped[DateTime] = Field.datetime(auto_now=True)
    metadata_json: Mapped[str | None] = Field.string(max_length=2000, nullable=True)

    def __repr__(self) -> str:
        return f"<WorkerHeartbeat {self.worker_name} [{self.status}] pid={self.pid}>"

    @staticmethod
    def compute_hash(worker_name: str, worker_type: str, identity_key: str) -> str:
        """
        Compute a deterministic hash for a worker identity.

        This ensures restarts/redeploys reuse the same DB row
        instead of creating duplicates.

        Args:
            worker_name: Name of the worker (class name or task-worker-{queues})
            worker_type: "message" or "task_worker"
            identity_key: Unique key (e.g. input_topic:group_id or queue list)
        """
        import hashlib
        identity = f"{worker_type}:{worker_name}:{identity_key}"
        return hashlib.sha256(identity.encode()).hexdigest()[:32]


class AdminSession(Model):
    """
    Sessão do admin panel (browser-based).
    
    Usado para autenticação session-based no admin,
    separada do JWT da API.
    """
    __tablename__ = "admin_sessions"
    
    id: Mapped[int] = Field.pk()
    session_key: Mapped[str] = Field.string(max_length=64, unique=True, index=True)
    user_id: Mapped[str] = Field.string(max_length=255, index=True)
    ip_address: Mapped[str | None] = Field.string(max_length=45, nullable=True)
    user_agent: Mapped[str | None] = Field.string(max_length=500, nullable=True)
    created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)
    expires_at: Mapped[DateTime] = Field.datetime()
    is_active: Mapped[bool] = Field.boolean(default=True)
    
    def __repr__(self) -> str:
        return f"<AdminSession user_id={self.user_id} active={self.is_active}>"


class EventLog(Model):
    """
    Tracking de eventos Kafka para auditoria, monitoramento e reprocessamento.
    
    Registra todos os eventos enviados (OUT) e recebidos (IN) pelo sistema,
    permitindo visualização no Operations Center, análise de throughput,
    e reenvio de eventos com falha.
    
    Campos principais:
    - event_id: UUID único do evento (do header Kafka)
    - event_name: Nome do evento (ex: user.created, order.placed)
    - topic: Tópico Kafka
    - direction: IN (recebido) ou OUT (enviado)
    - status: pending, sent, delivered, failed, requeued
    
    Usado pelo interceptor do KafkaProducer/KafkaConsumer para tracking automático.
    """
    __tablename__ = "admin_event_logs"
    
    id: Mapped[int] = Field.pk()
    
    # Identificação do evento
    event_id: Mapped[str] = Field.string(max_length=64, unique=True, index=True)
    event_name: Mapped[str] = Field.string(max_length=255, index=True)
    
    # Kafka metadata
    topic: Mapped[str] = Field.string(max_length=255, index=True)
    partition: Mapped[int | None] = Field.integer(nullable=True)
    offset: Mapped[int | None] = Field.integer(nullable=True)
    key: Mapped[str | None] = Field.string(max_length=255, nullable=True)
    
    # Headers (JSON serializado)
    headers_json: Mapped[str | None] = Field.text(nullable=True)
    
    # Payload
    payload_json: Mapped[str] = Field.text()
    payload_schema: Mapped[str | None] = Field.string(max_length=255, nullable=True)  # Nome do AvroModel
    payload_size_bytes: Mapped[int] = Field.integer(default=0)
    
    # Status e direção
    direction: Mapped[str] = Field.string(max_length=10, index=True)  # IN ou OUT
    status: Mapped[str] = Field.string(max_length=20, index=True)  # pending, sent, delivered, failed, requeued
    
    # Timestamps
    created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True, index=True)
    sent_at: Mapped[DateTime | None] = Field.datetime(nullable=True)
    delivered_at: Mapped[DateTime | None] = Field.datetime(nullable=True)
    
    # Erros e retries
    error: Mapped[str | None] = Field.text(nullable=True)
    retry_count: Mapped[int] = Field.integer(default=0)
    
    # Source tracking
    source_service: Mapped[str | None] = Field.string(max_length=100, nullable=True)
    source_worker_id: Mapped[str | None] = Field.string(max_length=64, nullable=True)
    
    # Referência para reenvio (aponta para o evento original se for um requeue)
    original_event_id: Mapped[str | None] = Field.string(max_length=64, nullable=True, index=True)
    
    def __repr__(self) -> str:
        return f"<EventLog {self.event_name} [{self.status}] {self.direction} {self.event_id[:8]}>"
    
    def to_dict(self) -> dict[str, Any]:
        """Serializa o evento para JSON/WebSocket."""
        import json
        return {
            "id": self.id,
            "event_id": self.event_id,
            "event_name": self.event_name,
            "topic": self.topic,
            "partition": self.partition,
            "offset": self.offset,
            "key": self.key,
            "headers": json.loads(self.headers_json) if self.headers_json else None,
            "payload": json.loads(self.payload_json) if self.payload_json else None,
            "payload_schema": self.payload_schema,
            "payload_size_bytes": self.payload_size_bytes,
            "direction": self.direction,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "error": self.error,
            "retry_count": self.retry_count,
            "source_service": self.source_service,
            "source_worker_id": self.source_worker_id,
            "original_event_id": self.original_event_id,
        }
    
    @classmethod
    async def log_outgoing(
        cls,
        db: "AsyncSession",
        *,
        event_id: str,
        event_name: str,
        topic: str,
        payload: dict | str,
        headers: dict | None = None,
        key: str | None = None,
        schema_name: str | None = None,
        source_service: str | None = None,
        source_worker_id: str | None = None,
    ) -> "EventLog":
        """
        Registra um evento de saída (antes de enviar ao Kafka).
        
        Args:
            db: Sessão do banco
            event_id: UUID do evento
            event_name: Nome do evento
            topic: Tópico Kafka de destino
            payload: Dados do evento (dict ou JSON string)
            headers: Headers Kafka
            key: Chave de particionamento
            schema_name: Nome do schema Avro (se aplicável)
            source_service: Nome do serviço de origem
            source_worker_id: ID do worker de origem
        """
        import json
        
        payload_str = json.dumps(payload) if isinstance(payload, dict) else payload
        headers_str = json.dumps(headers) if headers else None
        
        log = cls(
            event_id=event_id,
            event_name=event_name,
            topic=topic,
            key=key,
            headers_json=headers_str,
            payload_json=payload_str,
            payload_schema=schema_name,
            payload_size_bytes=len(payload_str.encode("utf-8")),
            direction="OUT",
            status="pending",
            source_service=source_service,
            source_worker_id=source_worker_id,
        )
        await log.save(db)
        return log
    
    @classmethod
    async def mark_sent(
        cls,
        db: "AsyncSession",
        event_id: str,
        partition: int,
        offset: int,
    ) -> None:
        """Marca um evento como enviado com sucesso."""
        from core.datetime import timezone
        from sqlalchemy import update
        
        stmt = (
            update(cls)
            .where(cls.event_id == event_id)
            .values(
                status="sent",
                partition=partition,
                offset=offset,
                sent_at=timezone.now(),
            )
        )
        await db.execute(stmt)
        await db.commit()
    
    @classmethod
    async def mark_failed(
        cls,
        db: "AsyncSession",
        event_id: str,
        error: str,
    ) -> None:
        """Marca um evento como falho."""
        from sqlalchemy import update
        
        stmt = (
            update(cls)
            .where(cls.event_id == event_id)
            .values(
                status="failed",
                error=error[:5000],  # Limita tamanho do erro
            )
        )
        await db.execute(stmt)
        await db.commit()
    
    @classmethod
    async def log_incoming(
        cls,
        db: "AsyncSession",
        *,
        event_id: str,
        event_name: str,
        topic: str,
        partition: int,
        offset: int,
        payload: dict | str,
        headers: dict | None = None,
        key: str | None = None,
        schema_name: str | None = None,
        source_worker_id: str | None = None,
    ) -> "EventLog":
        """
        Registra um evento de entrada (recebido do Kafka).
        
        Args:
            db: Sessão do banco
            event_id: UUID do evento (do header)
            event_name: Nome do evento (do header)
            topic: Tópico Kafka de origem
            partition: Partição de onde veio
            offset: Offset no Kafka
            payload: Dados do evento
            headers: Headers Kafka
            key: Chave de particionamento
            schema_name: Nome do schema Avro
            source_worker_id: ID do worker que recebeu
        """
        import json
        from core.datetime import timezone
        
        payload_str = json.dumps(payload) if isinstance(payload, dict) else payload
        headers_str = json.dumps(headers) if headers else None
        
        log = cls(
            event_id=event_id,
            event_name=event_name,
            topic=topic,
            partition=partition,
            offset=offset,
            key=key,
            headers_json=headers_str,
            payload_json=payload_str,
            payload_schema=schema_name,
            payload_size_bytes=len(payload_str.encode("utf-8")),
            direction="IN",
            status="delivered",
            delivered_at=timezone.now(),
            source_worker_id=source_worker_id,
        )
        await log.save(db)
        return log
