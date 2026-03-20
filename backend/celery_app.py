"""
Celery application — replaces APScheduler for distributed task processing.
Architecture v2.8 — Section 1: Core Infrastructure (Celery + Redis Beat)

Worker: celery -A celery_app worker --loglevel=info --concurrency=4
Beat:   celery -A celery_app beat --loglevel=info
"""
import os
import signal
import threading
from datetime import timedelta

from celery import Celery
from celery.signals import worker_shutting_down, worker_init
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent.resolve()
load_dotenv(ROOT_DIR / ".env")

# EC26: Separate broker and result-backend Redis instances/DBs so a result-backend
# storm (e.g., many task results piling up) cannot starve the broker queue.
# In production, point REDIS_BROKER_URL at a dedicated Redis instance.
# Fall back to the same REDIS_URL so local dev keeps working with a single Redis.
_REDIS_DEFAULT = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_BROKER_URL = os.environ.get("REDIS_BROKER_URL", _REDIS_DEFAULT)
REDIS_BACKEND_URL = os.environ.get("REDIS_BACKEND_URL", _REDIS_DEFAULT)

# ── App ──────────────────────────────────────────────────────────────────────
celery_app = Celery(
    "social_entangler",
    broker=REDIS_BROKER_URL,
    backend=REDIS_BACKEND_URL,
    include=["celery_tasks"],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Reliability
    task_acks_late=True,           # Acknowledge AFTER task completes (re-queue on crash)
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # One task at a time per worker thread
    task_track_started=True,

    # Worker lifecycle
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks (prevent memory leaks)
    worker_max_memory_per_child=512000,  # Restart if worker exceeds 512MB RSS

    # Result expiry
    result_expires=3600,  # 1 hour

    # Connection resilience
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_transport_options={
        "visibility_timeout": 3600,  # 1 hour (for long video uploads)
        "socket_timeout": 30,
        "socket_connect_timeout": 10,
    },

    # Beat schedule — 30s interval (matches APScheduler spec)
    beat_schedule={
        "process-scheduled-posts": {
            "task": "celery_tasks.process_scheduled_posts_task",
            "schedule": timedelta(seconds=30),
            "options": {"expires": 28},
        },
        "check-instagram-containers": {
            "task": "celery_tasks.check_instagram_containers_task",
            "schedule": timedelta(seconds=30),
            "options": {"expires": 28},
        },
        "expire-pending-review-posts": {
            "task": "celery_tasks.expire_pending_review_task",
            "schedule": timedelta(minutes=5),
            "options": {"expires": 290},
        },
        "beat-heartbeat": {
            "task": "celery_tasks.beat_heartbeat_task",
            "schedule": timedelta(seconds=30),
            "options": {"expires": 28},
        },
        # EC6: Proactive OAuth token refresh — every 30 minutes
        "refresh-expiring-tokens": {
            "task": "celery_tasks.refresh_expiring_tokens_task",
            "schedule": timedelta(minutes=30),
            "options": {"expires": 1790},
        },
    },
)


# ── Graceful Shutdown ─────────────────────────────────────────────────────────
# Addendum Section B.2 — Graceful Shutdown for Workers
_shutdown_requested = threading.Event()


@worker_shutting_down.connect
def handle_worker_shutdown(sig, how, exitcode, **kwargs):
    """
    On SIGTERM, signal all tasks to stop accepting new work.
    In-flight tasks get up to terminationGracePeriodSeconds (120s) to complete.
    """
    _shutdown_requested.set()


def is_shutdown_requested() -> bool:
    """Check if a graceful shutdown has been requested. Call this in long-running tasks."""
    return _shutdown_requested.is_set()
