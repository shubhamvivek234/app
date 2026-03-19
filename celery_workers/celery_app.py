"""
Phase 1.1 + Phase 4 — Celery application configuration.
Two Redis instances: redis-queue (broker, noeviction) + redis-cache (backend, LRU).
Four priority queues with dedicated worker pools.
Sentry SDK integration for task error tracking (Phase 4).
"""
import os
import logging
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from celery import Celery
from kombu import Exchange, Queue


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

# ── Queue definitions ────────────────────────────────────────────────────────
default_exchange = Exchange("default", type="direct")

CELERY_QUEUES = (
    # SLA: immediate — dedicated worker pool
    Queue("high_priority", default_exchange, routing_key="high_priority"),
    # SLA: < 30 seconds
    Queue("default", default_exchange, routing_key="default"),
    # SLA: < 2 minutes — media workers only
    Queue("media_processing", default_exchange, routing_key="media_processing"),
    # Manual / admin review
    Queue("dead_letter", default_exchange, routing_key="dead_letter"),
)

# ── App factory ──────────────────────────────────────────────────────────────
def create_celery_app() -> Celery:
    broker_url = os.environ.get("REDIS_QUEUE_URL", "redis://redis-queue:6379/0")
    result_backend = os.environ.get("REDIS_CACHE_URL", "redis://redis-cache:6379/1")

    app = Celery("socialentangler", broker=broker_url, backend=result_backend)

    app.conf.update(
        # Reliability settings — critical for production
        task_acks_late=True,                  # ack only after task completes
        worker_prefetch_multiplier=1,         # one task at a time per worker slot
        task_reject_on_worker_lost=True,      # re-queue on worker crash

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

        # Memory leak prevention — restart worker after 100 tasks
        worker_max_tasks_per_child=100,

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
        "celery_workers.tasks.poll_status",   # Phase 5 — polling fallback
        "celery_workers.tasks.recurring",     # Phase 5.5 — recurring post instances
        "celery_workers.tasks.analytics",     # Phase 6 — analytics collection
        "celery_workers.tasks.bulk_import",   # Phase 6 — bulk CSV import
    ])

    return app


celery_app = create_celery_app()
