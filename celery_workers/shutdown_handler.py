"""
Phase 1.7 — Graceful SIGTERM shutdown handler.
Worker stops accepting new tasks but finishes in-flight tasks first.
Every task checks is_shutting_down() at start and retries if True.
"""
import logging
from celery.signals import worker_shutting_down

logger = logging.getLogger(__name__)

_shutting_down: bool = False


def is_shutting_down() -> bool:
    return _shutting_down


@worker_shutting_down.connect
def handle_worker_shutdown(sig=None, how=None, exitcode=None, **kwargs):
    global _shutting_down
    _shutting_down = True
    logger.info(
        "Worker received shutdown signal (sig=%s how=%s) — "
        "draining in-flight tasks before exit",
        sig, how,
    )
