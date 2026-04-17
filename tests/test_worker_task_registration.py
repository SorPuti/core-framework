"""Validação unificada de registo de stream workers e @task."""

import pytest

from strider.messaging.workers import (
    Worker,
    WorkerRegistrationError,
    worker,
    _worker_registry,
)
from strider.tasks.base import Task, PeriodicTask
from strider.tasks.registry import (
    TaskRegistrationError,
    clear_registry,
    register_periodic_task,
    register_task,
)


@pytest.fixture(autouse=True)
def _reset_task_registry():
    clear_registry()
    yield
    clear_registry()


def test_register_task_rejects_duplicate():
    async def a():
        pass

    async def b():
        pass

    t1 = Task(a, name="same.name", queue="q1")
    t2 = Task(b, name="same.name", queue="q2")
    register_task(t1)
    with pytest.raises(TaskRegistrationError, match="já registado"):
        register_task(t2)


def test_register_task_rejects_bad_queue():
    async def a():
        pass

    t = Task(a, name="x", queue="bad/queue")
    with pytest.raises(TaskRegistrationError, match="queue inválida"):
        register_task(t)


def test_register_periodic_conflicts_with_task_name():
    async def a():
        pass

    async def b():
        pass

    register_task(Task(a, name="dup", queue="default"))
    with pytest.raises(TaskRegistrationError, match="@task"):
        register_periodic_task(
            PeriodicTask(b, name="dup", interval=60, queue="default")
        )


def test_stream_worker_decorator_validates_topic():
    _worker_registry.clear()
    try:
        with pytest.raises(WorkerRegistrationError, match="input_topic"):

            @worker(topic="")
            async def bad_empty(_msg):
                return {}

    finally:
        _worker_registry.clear()


def test_stream_worker_decorator_rejects_tasks_prefix():
    _worker_registry.clear()
    try:

        def _define():
            @worker(topic="tasks.evils")
            async def w(_m):
                return {}

        with pytest.raises(WorkerRegistrationError, match="tasks\\."):
            _define()
    finally:
        _worker_registry.clear()


def test_stream_worker_class_skips_without_input_topic():
    _worker_registry.clear()
    try:

        class Base(Worker):
            """Sem input_topic — não deve registar."""

        assert Base.__name__ not in _worker_registry

        class Concrete(Worker):
            input_topic = "orders-created"
            group_id = "g1"

            async def process(self, message: dict):
                return message

        assert "Concrete" in _worker_registry
    finally:
        _worker_registry.clear()
