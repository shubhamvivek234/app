"""
Shared asyncio runner for synchronous Celery tasks.

Celery prefork workers are synchronous processes. Keeping one event loop per
worker process prevents Motor and redis.asyncio clients from being rebound to
different loops across tasks.
"""
from __future__ import annotations

import asyncio
import os

_runner_loop: asyncio.AbstractEventLoop | None = None
_runner_pid: int | None = None


def run_async(coro):
    global _runner_loop, _runner_pid

    current_pid = os.getpid()
    if _runner_loop is None or _runner_loop.is_closed() or _runner_pid != current_pid:
        _runner_loop = asyncio.new_event_loop()
        _runner_pid = current_pid

    asyncio.set_event_loop(_runner_loop)
    return _runner_loop.run_until_complete(coro)
