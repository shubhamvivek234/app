"""
Webhook Delivery Worker and Retry Engine.
Executes external HTTP requests with bounded exponential retries,
dead-letter management, and manual replay capabilities.
"""
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any
import uuid

import httpx
from outreach.core.crypto import decrypt_secret
from outreach.core.safe_transport import SSRFSecurityError, create_safe_client
from outreach.core.webhook_signer import build_delivery_headers
from outreach.core.integrations_pilot import is_integrations_pilot_allowed

logger = logging.getLogger(__name__)

# Bounded exponential retry delays: 1m, 5m, 15m, 1h, 6h
BACKOFF_DELAYS_SECONDS = [60, 300, 900, 3600, 21600]
MAX_DELIVERY_ATTEMPTS = 6  # 1 initial + 5 retries
NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 410}
WEBHOOK_DEGRADED_THRESHOLD = 10


async def dispatch_due_deliveries(
    db: Any,
    *,
    batch_size: int = 20,
    lease_seconds: int = 30,
    safe_client: httpx.AsyncClient | None = None,
    allow_private_for_tests: bool = False,
) -> dict[str, int]:
    """
    Claim due deliveries, execute HTTP POST with DNS-pinned egress transport,
    and process outcome (delivered, retrying with backoff, or dead-lettered).
    """
    now = datetime.now(timezone.utc)
    lease_id = uuid.uuid4().hex
    leased_until = now + timedelta(seconds=lease_seconds)

    delivered_count = 0
    retried_count = 0
    failed_count = 0
    dead_letter_count = 0

    query = {
        "status": {"$in": ["pending", "retry"]},
        "next_attempt_at": {"$lte": now},
        "$or": [
            {"lease_id": None},
            {"leased_until": {"$lt": now}},
        ],
    }

    client = safe_client or create_safe_client(allow_private_for_tests=allow_private_for_tests)
    should_close_client = safe_client is None

    try:
        for _ in range(batch_size):
            delivery = await db.outreach_webhook_deliveries.find_one_and_update(
                query,
                {"$set": {"status": "leased", "lease_id": lease_id, "leased_until": leased_until}},
            )
            if not delivery:
                break

            delivery_id = delivery["id"]
            event_id = delivery["event_id"]
            destination_type = delivery.get("destination_type", "webhook")
            target_url = delivery["target_url"]
            secret_enc = delivery.get("secret_enc") or ""
            current_attempt = delivery.get("attempt", 0) + 1
            max_attempts = delivery.get("max_attempts", MAX_DELIVERY_ATTEMPTS)

            payload_data = delivery.get("payload", {})
            attempt_time = datetime.now(timezone.utc)

            if not is_integrations_pilot_allowed(delivery.get("workspace_id")):
                await db.outreach_webhook_deliveries.update_one(
                    {"id": delivery_id},
                    {"$set": {"status": "cancelled", "last_error": "Integrations not enabled for workspace in current pilot", "resolved_at": attempt_time}},
                )
                continue

            if destination_type == "slack":
                from outreach.core.slack_notifier import format_slack_event_card
                if delivery.get("target_url_enc"):
                    try:
                        target_url = decrypt_secret(delivery["target_url_enc"])
                    except Exception as exc:
                        logger.error("Failed to decrypt Slack URL for delivery %s: %s", delivery_id, exc)
                slack_body = format_slack_event_card(payload_data)
                raw_body_bytes = json.dumps(slack_body, ensure_ascii=False).encode("utf-8")
                headers = {"Content-Type": "application/json"}
            else:
                # Decrypt secret
                secret = ""
                if secret_enc:
                    try:
                        secret = decrypt_secret(secret_enc)
                    except Exception as exc:
                        logger.error("Failed to decrypt webhook secret for delivery %s: %s", delivery_id, exc)

                # Serialize payload to canonical JSON bytes
                raw_body_bytes = json.dumps(payload_data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

                # Build fresh headers (stable event_id, fresh timestamp and signature)
                headers = build_delivery_headers(
                    raw_body_bytes=raw_body_bytes,
                    secret=secret,
                    event_id=event_id,
                    delivery_id=delivery_id,
                    timestamp=attempt_time,
                )

            status_code = None
            error_str = None

            try:
                response = await client.post(
                    target_url,
                    content=raw_body_bytes,
                    headers=headers,
                )
                status_code = response.status_code
                if not (200 <= status_code < 300):
                    error_str = f"HTTP {status_code}"
            except SSRFSecurityError as ssrf_err:
                error_str = f"SSRF blocked: {ssrf_err}"
                status_code = 403
            except httpx.TimeoutException:
                error_str = "Connection timed out"
            except httpx.NetworkError as net_err:
                error_str = f"Network error: {str(net_err)[:100]}"
            except Exception as exc:
                error_str = f"Unexpected delivery error: {str(exc)[:100]}"

            # Evaluate outcome
            if status_code and 200 <= status_code < 300:
                # Success
                await db.outreach_webhook_deliveries.update_one(
                    {"id": delivery_id},
                    {"$set": {
                        "status": "delivered",
                        "attempt": current_attempt,
                        "response_status": status_code,
                        "error_sanitized": None,
                        "delivered_at": attempt_time,
                        "lease_id": None,
                        "leased_until": None,
                        "updated_at": attempt_time,
                    }},
                )
                if destination_type == "slack":
                    await _safe_update_integration(
                        db,
                        {"workspace_id": delivery["workspace_id"], "provider": "slack"},
                        {"$set": {"last_delivery_at": attempt_time, "consecutive_failures": 0, "status": "connected"}},
                    )
                else:
                    # Reset webhook failure counters
                    await db.outreach_webhooks.update_one(
                        {"id": delivery["destination_id"]},
                        {"$set": {"consecutive_failures": 0, "last_delivery_at": attempt_time}},
                    )
                delivered_count += 1

            elif status_code in NON_RETRYABLE_STATUS_CODES:
                # Permanent failure — do not retry
                await db.outreach_webhook_deliveries.update_one(
                    {"id": delivery_id},
                    {"$set": {
                        "status": "failed",
                        "attempt": current_attempt,
                        "response_status": status_code,
                        "error_sanitized": error_str,
                        "lease_id": None,
                        "leased_until": None,
                        "updated_at": attempt_time,
                    }},
                )
                if destination_type == "slack":
                    if status_code in (404, 410):
                        await _safe_update_integration(
                            db,
                            {"workspace_id": delivery["workspace_id"], "provider": "slack"},
                            {"$set": {"status": "needs_attention", "last_error": error_str}},
                        )
                else:
                    await _increment_webhook_failures(db, delivery["destination_id"])
                failed_count += 1

            else:
                # Retryable failure
                if current_attempt >= max_attempts:
                    # Exceeded max retries -> Dead Letter
                    await db.outreach_webhook_deliveries.update_one(
                        {"id": delivery_id},
                        {"$set": {
                            "status": "dead_letter",
                            "attempt": current_attempt,
                            "response_status": status_code,
                            "error_sanitized": error_str,
                            "lease_id": None,
                            "leased_until": None,
                            "updated_at": attempt_time,
                        }},
                    )
                    if destination_type == "slack":
                        await _safe_update_integration(
                            db,
                            {"workspace_id": delivery["workspace_id"], "provider": "slack"},
                            {"$set": {"last_error": f"Delivery dead lettered: {error_str}"}},
                        )
                    else:
                        await _increment_webhook_failures(db, delivery["destination_id"])
                    dead_letter_count += 1
                else:
                    # Schedule next backoff retry
                    delay_idx = min(current_attempt - 1, len(BACKOFF_DELAYS_SECONDS) - 1)
                    delay_sec = BACKOFF_DELAYS_SECONDS[delay_idx]
                    next_attempt_at = attempt_time + timedelta(seconds=delay_sec)

                    await db.outreach_webhook_deliveries.update_one(
                        {"id": delivery_id},
                        {"$set": {
                            "status": "retry",
                            "attempt": current_attempt,
                            "next_attempt_at": next_attempt_at,
                            "response_status": status_code,
                            "error_sanitized": error_str,
                            "lease_id": None,
                            "leased_until": None,
                            "updated_at": attempt_time,
                        }},
                    )
                    retried_count += 1

    finally:
        if should_close_client:
            await client.aclose()

    return {
        "delivered": delivered_count,
        "retried": retried_count,
        "failed": failed_count,
        "dead_letter": dead_letter_count,
    }


async def _safe_update_integration(db: Any, filter_doc: dict, update_doc: dict) -> None:
    """Safely update outreach_integrations across both Motor and non-async test mocks."""
    if hasattr(db, "outreach_integrations"):
        fn = getattr(db.outreach_integrations, "update_one", None)
        if fn and callable(fn):
            import inspect
            res = fn(filter_doc, update_doc)
            if inspect.isawaitable(res):
                await res


async def _increment_webhook_failures(db: Any, webhook_id: str) -> None:
    """Increment consecutive failures and mark degraded if threshold exceeded."""
    res = await db.outreach_webhooks.find_one_and_update(
        {"id": webhook_id},
        {"$inc": {"consecutive_failures": 1}},
        return_document=True,
    )
    if res and res.get("consecutive_failures", 0) >= WEBHOOK_DEGRADED_THRESHOLD:
        if res.get("status") == "active":
            await db.outreach_webhooks.update_one(
                {"id": webhook_id},
                {"$set": {"status": "degraded"}},
            )
            logger.warning("Webhook endpoint %s marked degraded after %d consecutive failures", webhook_id, res["consecutive_failures"])


async def replay_delivery(
    db: Any,
    workspace_id: str,
    delivery_id: str,
    actor_id: str,
) -> dict[str, Any]:
    """
    Manually replay a dead-lettered or failed delivery.
    Preserves the stable event_id and reschedules immediate delivery attempt.
    """
    delivery = await db.outreach_webhook_deliveries.find_one({
        "id": delivery_id,
        "workspace_id": workspace_id,
    })
    if not delivery:
        raise ValueError(f"Delivery {delivery_id} not found in workspace {workspace_id}")

    if delivery["status"] not in ("dead_letter", "failed"):
        raise ValueError(f"Cannot replay delivery in '{delivery['status']}' status (only failed or dead_letter)")

    now = datetime.now(timezone.utc)
    await db.outreach_webhook_deliveries.update_one(
        {"id": delivery_id},
        {"$set": {
            "status": "pending",
            "attempt": 0,
            "next_attempt_at": now,
            "lease_id": None,
            "leased_until": None,
            "error_sanitized": None,
            "replayed_by": actor_id,
            "replayed_at": now,
            "updated_at": now,
        }},
    )
    return {
        "id": delivery_id,
        "event_id": delivery["event_id"],
        "status": "pending",
        "next_attempt_at": now.isoformat(),
    }
