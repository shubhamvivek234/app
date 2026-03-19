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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from api.deps import CurrentUser, CacheRedis, get_current_user, get_cache_redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stream"])

_HEARTBEAT_INTERVAL = 30  # seconds
_SUBSCRIBE_TIMEOUT = 1.0  # seconds between pubsub polls
_RECONNECT_RETRY_MS = 3000  # client reconnect interval
_MAX_SSE_PER_USER = 2  # max concurrent SSE connections per user
_SSE_EVENT_TYPES = {"post_status_update", "publish_complete", "publish_failed", "media_ready", "notification"}


# ── SSE formatting helpers ────────────────────────────────────────────────────

def _sse_event(
    data: str,
    event: str | None = None,
    id: str | None = None,
    retry: int | None = None,
) -> str:
    lines = []
    if id:
        lines.append(f"id: {id}")
    if event:
        lines.append(f"event: {event}")
    if retry is not None:
        lines.append(f"retry: {retry}")
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
    last_event_id: str | None = None,
) -> AsyncGenerator[str, None]:
    channel = f"user:{user_id}:updates"
    pubsub = cache_redis.pubsub()

    try:
        await pubsub.subscribe(channel)
        logger.info("SSE stream opened: user=%s channel=%s last_event_id=%s", user_id, channel, last_event_id)

        # Replay missed events if Last-Event-ID provided
        if last_event_id:
            try:
                missed_key = f"sse:history:{user_id}"
                missed_events = await cache_redis.lrange(missed_key, 0, -1)
                replay_started = False
                for raw_event in missed_events:
                    if isinstance(raw_event, bytes):
                        raw_event = raw_event.decode("utf-8", errors="replace")
                    try:
                        evt = json.loads(raw_event)
                        if replay_started:
                            yield _sse_event(raw_event, event=evt.get("type", "update"), id=evt.get("event_id", ""))
                        elif evt.get("event_id") == last_event_id:
                            replay_started = True
                    except (json.JSONDecodeError, ValueError):
                        continue
            except Exception as replay_err:
                logger.warning("SSE replay failed for user=%s: %s", user_id, replay_err)

        # Emit a connected confirmation event with retry directive
        yield _sse_event(
            json.dumps({"type": "connected", "channel": channel}),
            event="connected",
            retry=_RECONNECT_RETRY_MS,
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
                    parsed = json.loads(raw)
                    event_id = str(int(asyncio.get_event_loop().time() * 1000))
                    event_type = parsed.get("type", "update")
                    # Map to SSE event types
                    if event_type not in _SSE_EVENT_TYPES:
                        event_type = "post_status_update"
                    # Store in history for Last-Event-ID replay (keep last 100, 1h TTL)
                    parsed["event_id"] = event_id
                    history_key = f"sse:history:{user_id}"
                    try:
                        await cache_redis.rpush(history_key, json.dumps(parsed))
                        await cache_redis.ltrim(history_key, -100, -1)
                        await cache_redis.expire(history_key, 3600)
                    except Exception:
                        pass  # non-critical — best-effort replay
                    yield _sse_event(raw, event=event_type, id=event_id)
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
    request: Request,
    current_user: CurrentUser,
    cache_redis: CacheRedis,
) -> StreamingResponse:
    """
    SSE endpoint — subscribe to real-time post status updates.

    Events:
      connected          — emitted on successful subscribe
      post_status_update — post status change payload (JSON)
      publish_complete   — post published to all platforms
      publish_failed     — post failed on one or more platforms
      media_ready        — media processing complete
      notification       — general user notification
      reconnect          — server-side error, client should reconnect

    Headers:
      Last-Event-ID  — resume from a previous event (reconnection support)
      retry: 3000    — client reconnect interval

    Fallback: if SSE is unavailable, poll GET /api/v1/posts every 30s.
    """
    user_id = current_user["user_id"]

    # Rate limit: max concurrent SSE connections per user
    conn_key = f"sse:conn:{user_id}"
    conn_count = await cache_redis.get(conn_key)
    if conn_count and int(conn_count) >= _MAX_SSE_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Maximum {_MAX_SSE_PER_USER} concurrent SSE connections",
        )
    await cache_redis.incr(conn_key)
    await cache_redis.expire(conn_key, 3600)  # auto-cleanup after 1h

    # Last-Event-ID for reconnection (resuming missed events)
    last_event_id = request.headers.get("Last-Event-ID")

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",       # disable nginx buffering
        "Connection": "keep-alive",
        "X-SSE-Fallback": "polling-30s",
    }

    async def _cleanup_generator():
        try:
            async for chunk in _event_generator(user_id, cache_redis, last_event_id):
                yield chunk
        finally:
            # Decrement connection count on disconnect
            try:
                val = await cache_redis.get(conn_key)
                if val and int(val) > 0:
                    await cache_redis.decr(conn_key)
            except Exception:
                pass

    return StreamingResponse(
        _cleanup_generator(),
        media_type="text/event-stream",
        headers=headers,
    )
