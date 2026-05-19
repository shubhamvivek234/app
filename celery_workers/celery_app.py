"""
Phase 1.1 + Phase 4 — Celery application configuration.
Two Redis instances: redis-queue (broker, noeviction) + redis-cache (backend, LRU).
Four priority queues with dedicated worker pools.
Sentry SDK integration for task error tracking (Phase 4).
"""
import os
import logging
from urllib.parse import urlparse
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from celery import Celery
from celery.signals import task_postrun, task_prerun
from kombu import Exchange, Queue
from utils.log_scrub import configure_scrubbing
from utils.observability import JsonFormatter
from utils.request_context import clear_trace_id, set_trace_id


def _configure_celery_sentry() -> None:
    """Initialise Sentry for Celery workers — no-op if SENTRY_DSN unset."""
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("ENV", "development"),
        release=os.getenv("SENTRY_RELEASE", "2.9.0"),
        # Lower sample rate for workers — tasks are high volume
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        integrations=[
            CeleryIntegration(monitor_beat_tasks=True),
            LoggingIntegration(
                level=logging.WARNING,
                event_level=logging.ERROR,
            ),
        ],
        send_default_pii=False,
    )


_configure_celery_sentry()


def _configure_worker_logging() -> None:
    is_prod = os.getenv("ENV", "development") == "production"
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    if is_prod:
        handler.setFormatter(JsonFormatter(service_name="celery"))
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
    root_logger.addHandler(handler)
    configure_scrubbing()


_configure_worker_logging()


@task_prerun.connect
def _bind_task_trace_id(task=None, **kwargs) -> None:
    headers = getattr(getattr(task, "request", None), "headers", None) or {}
    set_trace_id(headers.get("x-trace-id"))


@task_postrun.connect
def _clear_task_trace_id(task=None, **kwargs) -> None:
    clear_trace_id()


def _warn_if_serverless_broker(url: str) -> None:
    """
    Celery broker semantics assume stable long-lived Redis connections.
    Using serverless/quota-bound Redis for REDIS_QUEUE_URL is operationally risky.
    """
    host = (urlparse(url).hostname or "").lower()
    if "upstash" in host:
        logging.getLogger(__name__).critical(
            "REDIS_QUEUE_URL points to Upstash (%s). "
            "This is not recommended for Celery broker traffic. "
            "Use dedicated Redis for the queue path.",
            host,
        )

# ── Queue definitions ────────────────────────────────────────────────────────
default_exchange = Exchange("default", type="direct")

CELERY_QUEUES = (
    # SLA: immediate — dedicated worker pool
    Queue("high_priority", default_exchange, routing_key="high_priority"),
    # SLA: < 30 seconds
    Queue("default", default_exchange, routing_key="default"),
    # SLA: light publish work (text/image) with higher parallelism
    Queue("publish_light", default_exchange, routing_key="publish_light"),
    # SLA: heavy publish work (video / long-running uploads) isolated from light work
    Queue("publish_video", default_exchange, routing_key="publish_video"),
    # SLA: < 2 minutes — media workers only
    Queue("media_processing", default_exchange, routing_key="media_processing"),
    # Manual / admin review
    Queue("dead_letter", default_exchange, routing_key="dead_letter"),
)

# ── App factory ──────────────────────────────────────────────────────────────
def create_celery_app() -> Celery:
    broker_url = os.environ.get("REDIS_QUEUE_URL", "redis://redis-queue:6379/0")
    result_backend = os.environ.get("REDIS_CACHE_URL", "redis://redis-cache:6379/1")
    _warn_if_serverless_broker(broker_url)

    app = Celery("socialentangler", broker=broker_url, backend=result_backend)

    app.conf.update(
        # Reliability settings — critical for production
        task_acks_late=True,                  # ack only after task completes
        worker_prefetch_multiplier=1,         # one task at a time per worker slot
        task_reject_on_worker_lost=True,      # re-queue on worker crash
        broker_connection_retry_on_startup=True,
        broker_transport_options={
            "visibility_timeout": 3600,
            "socket_connect_timeout": 5,
            "socket_timeout": 10,
            "retry_on_timeout": True,
        },
        redis_backend_health_check_interval=30,
        result_backend_always_retry=True,
        result_backend_max_retries=3,

        # Queue config
        task_queues=CELERY_QUEUES,
        task_default_queue="default",
        task_default_exchange="default",
        task_default_routing_key="default",

        # Serialization
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],

        # Result expiry
        result_expires=3600,

        # Memory leak prevention — configurable via WORKER_MAX_TASKS_PER_CHILD (default: 100)
        worker_max_tasks_per_child=int(os.environ.get("WORKER_MAX_TASKS_PER_CHILD", "100")),
        worker_hijack_root_logger=False,

        # Timezone
        timezone="UTC",
        enable_utc=True,

        # Beat schedule (populated in tasks/scheduler.py)
        beat_schedule={},
    )

    # Auto-discover task modules
    app.autodiscover_tasks([
        "celery_workers.tasks.publish",
        "celery_workers.tasks.media",
        "celery_workers.tasks.scheduler",
        "celery_workers.tasks.cleanup",
        "celery_workers.tasks.tokens",
        "celery_workers.tasks.reconcile",
        "celery_workers.tasks.poll_status",        # Phase 5 — polling fallback
        "celery_workers.tasks.recurring",          # Phase 5.5 — recurring post instances
        "celery_workers.tasks.analytics",          # Phase 6 — analytics collection
        "celery_workers.tasks.bulk_import",        # Phase 6 — bulk CSV import
        "celery_workers.tasks.ai_caption",         # Phase 7.5 — AI caption generation
        "celery_workers.tasks.gdpr",               # Phase 8 — GDPR erasure + export
        "celery_workers.tasks.subscription_check", # EC15 — subscription expiry grace period
        "celery_workers.tasks.api_version_monitor",# Phase 10.2 — platform API version monitoring
        "celery_workers.tasks.container_status",   # EC12 — non-blocking Instagram container check
    ])

    return app


celery_app = create_celery_app()
