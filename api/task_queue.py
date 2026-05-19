import os

from celery import Celery
from utils.request_context import get_trace_id


def _create_celery_client() -> Celery:
    broker_url = os.environ.get("REDIS_QUEUE_URL", "redis://redis:6379/0")
    result_backend = os.environ.get("REDIS_CACHE_URL") or broker_url
    return Celery("socialentangler_api", broker=broker_url, backend=result_backend)


celery_client = _create_celery_client()


def enqueue_task(
    task_name: str,
    *,
    args: list | None = None,
    kwargs: dict | None = None,
    queue: str | None = None,
    countdown: int | None = None,
):
    trace_id = get_trace_id()
    headers = {"x-trace-id": trace_id} if trace_id else None
    return celery_client.send_task(
        task_name,
        args=args or [],
        kwargs=kwargs or {},
        queue=queue,
        countdown=countdown,
        headers=headers,
    )


def revoke_task(task_id: str, *, terminate: bool = False) -> None:
    celery_client.control.revoke(task_id, terminate=terminate)
