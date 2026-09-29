"""
Outreach Webhook Dispatcher and Event Pipeline Bridge.
Connects workspace events with safe egress transport, HMAC-SHA256 signatures,
and the transactional event outbox.
"""
from datetime import datetime, timezone
import json
import logging
from typing import Any
import uuid
import httpx

from outreach.core.crypto import decrypt_secret
from outreach.core.event_definitions import WebhookEvent
from outreach.core.event_outbox import record_outbox_event, scan_and_fanout_outbox
from outreach.core.safe_transport import SSRFSecurityError, create_safe_client
from outreach.core.webhook_delivery import dispatch_due_deliveries
from outreach.core.webhook_signer import build_delivery_headers, compute_signature
from utils.ssrf_guard import is_safe_url

logger = logging.getLogger(__name__)


def sign_payload(payload_bytes: bytes, secret: str, timestamp_str: str | None = None) -> str:
    """
    Computes HMAC-SHA256 signature.
    If timestamp_str is provided, uses '{timestamp}.{body}', else signs body directly.
    """
    if timestamp_str:
        return compute_signature(payload_bytes, secret, timestamp_str)
    # Direct HMAC-SHA256 fallback for legacy test compatibility
    import hashlib
    import hmac
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


async def dispatch_webhook(
    url: str,
    secret: str,
    event_type: str,
    data: dict[str, Any],
    *,
    timeout: float = 10.0,
    http_client: httpx.AsyncClient | None = None,
    allow_private_for_tests: bool = False,
) -> dict[str, Any]:
    """
    Validates URL safety with DNS pinning, signs payload with HMAC-SHA256,
    and executes external HTTP POST request with bounded response size.
    """
    if not is_safe_url(url) and not allow_private_for_tests:
        logger.warning("Blocked outbound webhook attempt to unsafe URL: %s", url)
        return {
            "success": False,
            "status_code": 0,
            "error": "Destination URL rejected by SSRF security policy",
        }

    event_id = f"evt_{uuid.uuid4().hex}"
    delivery_id = f"del_{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc)

    envelope = {
        "id": event_id,
        "type": event_type,
        "version": 1,
        "occurred_at": now.isoformat(),
        "data": data,
    }
    payload_bytes = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    headers = build_delivery_headers(
        raw_body_bytes=payload_bytes,
        secret=secret,
        event_id=event_id,
        delivery_id=delivery_id,
        timestamp=now,
    )

    client = http_client or create_safe_client(timeout=timeout, allow_private_for_tests=allow_private_for_tests)
    should_close_client = http_client is None

    try:
        resp = await client.post(url, content=payload_bytes, headers=headers)
        success = 200 <= resp.status_code < 300
        return {
            "success": success,
            "status_code": resp.status_code,
            "response_text": resp.text[:300] if not success else "OK",
            "event_id": event_id,
            "delivery_id": delivery_id,
        }
    except SSRFSecurityError as ssrf_err:
        logger.warning("SSRF guard blocked destination '%s': %s", url[:100], ssrf_err)
        return {
            "success": False,
            "status_code": 0,
            "error": f"Destination URL rejected by SSRF security policy: {ssrf_err}",
            "event_id": event_id,
            "delivery_id": delivery_id,
        }
    except httpx.TimeoutException:
        return {
            "success": False,
            "status_code": 0,
            "error": "Connection timed out",
            "event_id": event_id,
            "delivery_id": delivery_id,
        }
    except Exception as exc:
        logger.info("Webhook dispatch failed to %s: %s", url[:100], exc)
        return {
            "success": False,
            "status_code": 0,
            "error": str(exc)[:200],
            "event_id": event_id,
            "delivery_id": delivery_id,
        }
    finally:
        if should_close_client:
            await client.aclose()


async def emit_workspace_event(
    db: Any,
    workspace_id: str,
    event_type: WebhookEvent | str,
    aggregate_id: str,
    dedupe_key: str,
    data: dict[str, Any],
    *,
    session: Any = None,
) -> dict[str, Any]:
    """
    Standard entry point for recording an event to the transactional outbox.
    All source state transitions should call this method to emit durable events.
    """
    return await record_outbox_event(
        db=db,
        workspace_id=workspace_id,
        event_type=event_type,
        aggregate_id=aggregate_id,
        dedupe_key=dedupe_key,
        data=data,
        session=session,
    )


async def broadcast_workspace_event(
    db: Any,
    workspace_id: str,
    event_type: str,
    data: dict[str, Any],
    *,
    aggregate_id: str | None = None,
    dedupe_key: str | None = None,
) -> list[dict[str, Any]]:
    """
    Durable event broadcast: writes to outbox, fans out to active webhooks,
    and runs delivery worker.
    """
    agg_id = aggregate_id or data.get("lead_id") or data.get("campaign_id") or uuid.uuid4().hex
    dedup = dedupe_key or f"{event_type}:{agg_id}:{uuid.uuid4().hex[:8]}"

    await record_outbox_event(
        db=db,
        workspace_id=workspace_id,
        event_type=event_type,
        aggregate_id=agg_id,
        dedupe_key=dedupe_key or dedup,
        data=data,
    )

    # Fan out to deliveries
    await scan_and_fanout_outbox(db, batch_size=20)

    # Immediate dispatch attempt
    dispatch_stats = await dispatch_due_deliveries(db, batch_size=20)
    return [dispatch_stats]
