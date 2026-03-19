"""
Celery task definitions.
These are the async tasks that replace the APScheduler process_scheduled_posts() function.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.resolve()
load_dotenv(ROOT_DIR / ".env")

from celery_app import celery_app, is_shutdown_requested
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


def async_task(fn):
    """Decorator to run an async function inside a Celery task's sync context."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(fn(*args, **kwargs))
        finally:
            loop.close()
    return wrapper


def get_db():
    """Get a fresh MongoDB client for this task. Each task creates its own connection."""
    client = AsyncIOMotorClient(
        MONGO_URL,
        maxPoolSize=10,           # Per-worker pool size (Addendum Section B.3)
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )
    return client[DB_NAME]


@celery_app.task(
    name="celery_tasks.process_scheduled_posts_task",
    bind=True,
    max_retries=0,       # Beat triggers this every minute; don't retry the trigger itself
    soft_time_limit=50,  # Soft limit: 50s (beat fires every 60s)
    time_limit=58,       # Hard limit: 58s
)
@async_task
async def process_scheduled_posts_task(self):
    """
    Process all posts due for publishing.
    Runs every 1 minute via Beat schedule.
    """
    if is_shutdown_requested():
        logger.info("Shutdown requested, skipping process_scheduled_posts_task")
        return

    db = get_db()
    now = datetime.now(timezone.utc)

    # Import the actual publish logic from server.py
    # We re-use the same function that APScheduler used
    try:
        # Dynamically import to avoid circular dependencies
        import importlib
        server_module = importlib.import_module("server")
        await server_module.process_scheduled_posts()
        logger.info("process_scheduled_posts completed successfully")
    except Exception as e:
        logger.error(f"process_scheduled_posts failed: {e}", exc_info=True)
        raise


@celery_app.task(
    name="celery_tasks.expire_pending_review_task",
    bind=True,
    max_retries=0,
)
@async_task
async def expire_pending_review_task(self):
    """
    Expire posts stuck in pending_review past their scheduled_time.
    Runs every 5 minutes.
    """
    if is_shutdown_requested():
        return

    db = get_db()
    now = datetime.now(timezone.utc)

    result = await db.posts.update_many(
        {
            "status": "pending_review",
            "scheduled_time": {"$lt": now.isoformat()},
        },
        {"$set": {"status": "expired_approval"}},
    )
    if result.modified_count:
        logger.info(f"Expired {result.modified_count} pending_review posts")
