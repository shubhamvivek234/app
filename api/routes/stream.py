"""
Server-Sent Events (SSE) stream — real-time post status updates via Redis pub/sub.
Channel: user:{user_id}:updates
Heartbeat every 30s. Reconnect event on Redis failure.
Client fallback: if SSE is lost, poll GET /posts every 30s (documented in response headers).
"""
import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from api.deps import CurrentUser, CacheRedis, get_current_user, get_cache_redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stream"])

_HEARTBEAT_INTERVAL = 30  # seconds
_SUBSCRIBE_TIMEOUT = 1.0  # seconds between pubsub polls


# ── SSE formatting helpers ────────────────────────────────────────────────────

def _sse_event(data: str, event: str | None = None, id: str | None = None) -> str:
    lines = []
    if id:
        lines.append(f"id: {id}")
    if event:
        lines.append(f"event: {event}")
    lines.append(f"data: {data}")
    lines.append("")  # blank line terminates event
    return "\n".join(lines) + "\n"


def _sse_comment(text: str = "") -> str:
    """Heartbeat / keep-alive (SSE comment)."""
    return f": {text}\n\n"


# ── Generator ────────────────────────────────────────────────────────────────

async def _event_generator(
    user_id: str,
    cache_redis: CacheRedis,
) -> AsyncGenerator[str, None]:
    channel = f"user:{user_id}:updates"
    pubsub = cache_redis.pubsub()

    try:
        await pubsub.subscribe(channel)
        logger.info("SSE stream opened: user=%s channel=%s", user_id, channel)

        # Emit a connected confirmation event
        yield _sse_event(
            json.dumps({"type": "connected", "channel": channel}),
            event="connected",
        )

        last_heartbeat = asyncio.get_event_loop().time()

        while True:
            now = asyncio.get_event_loop().time()

            # Heartbeat
            if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
                ts = datetime.now(timezone.utc).isoformat()
                yield _sse_comment(f"heartbeat {ts}")
                last_heartbeat = now

            # Poll for a message (non-blocking, 1s timeout)
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=_SUBSCRIBE_TIMEOUT,
                )
            except asyncio.TimeoutError:
                message = None
            except Exception as redis_err:
                logger.warning("Redis pubsub error for user=%s: %s", user_id, redis_err)
                yield _sse_event(
                    json.dumps({"type": "reconnect", "reason": "redis_error", "retry_ms": 5000}),
                    event="reconnect",
                )
                return

            if message and message.get("type") == "message":
                raw = message.get("data", "")
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")

                # Forward the message; validate JSON but do not alter shape
                try:
                    json.loads(raw)   # validate it's JSON
                    event_id = str(int(asyncio.get_event_loop().time() * 1000))
                    yield _sse_event(raw, event="update", id=event_id)
                except (json.JSONDecodeError, ValueError):
                    logger.debug("Non-JSON message on %s: %s", channel, raw[:100])

    except asyncio.CancelledError:
        logger.info("SSE stream cancelled: user=%s", user_id)
    except Exception as exc:
        logger.error("SSE stream error for user=%s: %s", user_id, exc)
        try:
            yield _sse_event(
                json.dumps({"type": "reconnect", "reason": "server_error", "retry_ms": 10000}),
                event="reconnect",
            )
        except Exception:
            pass
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        except Exception:
            pass
        logger.info("SSE stream closed: user=%s", user_id)


# ── Route ─────────────────────────────────────────────────────────────────────

@router.get("/stream/posts")
async def stream_post_updates(
    current_user: CurrentUser,
    cache_redis: CacheRedis,
) -> StreamingResponse:
    """
    SSE endpoint — subscribe to real-time post status updates.

    Events:
      connected  — emitted on successful subscribe
      update     — post status change payload (JSON)
      reconnect  — server-side error, client should reconnect
      heartbeat  — SSE comment every 30s (keeps connection alive)

    Fallback: if SSE is unavailable, poll GET /api/v1/posts every 30s.
    """
    user_id = current_user["user_id"]

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",       # disable nginx buffering
        "Connection": "keep-alive",
        "X-SSE-Fallback": "poll /api/v1/posts interval=30s",
    }

    return StreamingResponse(
        _event_generator(user_id, cache_redis),
        media_type="text/event-stream",
        headers=headers,
    )
