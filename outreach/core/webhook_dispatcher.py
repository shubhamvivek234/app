"""Outbound webhook signing and delivery with SSRF protection and HMAC-SHA256."""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
from uuid import uuid4
import httpx

from outreach.core.crypto import decrypt_secret
from utils.ssrf_guard import is_safe_url

logger = logging.getLogger(__name__)


def sign_payload(payload_bytes: bytes, secret: str) -> str:
    """Computes HMAC-SHA256 hex digest of the raw request body."""
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


async def dispatch_webhook(
    url: str,
    secret: str,
    event_type: str,
    data: dict,
    *,
    timeout: float = 10.0,
    http_client: httpx.AsyncClient | None = None,
) -> dict:
    """
    Validates URL safety, signs payload with HMAC-SHA256, and posts JSON data.
    Returns status code and delivery status.
    """
    if not is_safe_url(url):
        logger.warning("Blocked outbound webhook attempt to unsafe URL: %s", url)
        return {
            "success": False,
            "status_code": 0,
            "error": "Destination URL rejected by SSRF security policy",
        }

    envelope = {
        "event": event_type,
        "event_id": f"evt_{uuid4().hex[:16]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    payload_bytes = json.dumps(envelope, separators=(",", ":"), default=str).encode("utf-8")
    signature = sign_payload(payload_bytes, secret)

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Unravler-Webhooks/1.0",
        "X-Unravler-Event": event_type,
        "X-Unravler-Signature": f"sha256={signature}",
    }

    try:
        if http_client:
            resp = await http_client.post(url, content=payload_bytes, headers=headers, timeout=timeout)
        else:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, content=payload_bytes, headers=headers)

        success = 200 <= resp.status_code < 300
        return {
            "success": success,
            "status_code": resp.status_code,
            "response_text": resp.text[:300] if not success else "OK",
            "event_id": envelope["event_id"],
        }
    except Exception as exc:
        logger.info("Webhook dispatch failed to %s: %s", url, exc)
        return {
            "success": False,
            "status_code": 0,
            "error": str(exc)[:200],
            "event_id": envelope["event_id"],
        }


async def broadcast_workspace_event(
    db,
    workspace_id: str,
    event_type: str,
    data: dict,
) -> list[dict]:
    """Finds all active webhooks for the workspace subscribed to this event and dispatches them."""
    cursor = db.outreach_webhooks.find({
        "workspace_id": workspace_id,
        "status": "active",
        "events": event_type,
    })
    webhooks = await cursor.to_list(length=50)
    results = []

    now = datetime.now(timezone.utc)
    for whk in webhooks:
        secret = decrypt_secret(whk.get("secret_enc", "")) if whk.get("secret_enc") else ""
        res = await dispatch_webhook(whk["target_url"], secret, event_type, data)
        results.append({"webhook_id": whk["id"], **res})

        updates: dict = {"last_delivery_at": now}
        if res["success"]:
            updates["consecutive_failures"] = 0
            if whk.get("status") == "degraded":
                updates["status"] = "active"
        else:
            failures = whk.get("consecutive_failures", 0) + 1
            updates["consecutive_failures"] = failures
            if failures >= 10:
                updates["status"] = "degraded"

        await db.outreach_webhooks.update_one(
            {"id": whk["id"], "workspace_id": workspace_id},
            {"$set": updates},
        )

    return results
