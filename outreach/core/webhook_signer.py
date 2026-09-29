"""
Cryptographic Webhook Payload Signer and Verifier.
Implements HMAC-SHA256 signature scheme with timestamped replay prevention.
"""
from datetime import datetime, timezone
import hashlib
import hmac


def compute_signature(raw_body_bytes: bytes, secret: str, timestamp_str: str) -> str:
    """
    Compute HMAC-SHA256 signature for a webhook payload.
    Signed base string format: {timestamp}.{body}
    """
    if isinstance(secret, str):
        secret_bytes = secret.encode("utf-8")
    else:
        secret_bytes = secret

    base_string = f"{timestamp_str}.".encode("utf-8") + raw_body_bytes
    signature = hmac.new(secret_bytes, base_string, hashlib.sha256).hexdigest()
    return f"sha256={signature}"


def verify_signature(
    raw_body_bytes: bytes,
    secret: str,
    signature_header: str,
    timestamp_header: str,
    *,
    tolerance_seconds: int = 300,
    current_time: datetime | None = None,
) -> bool:
    """
    Verify an incoming signature header against the raw body and secret.
    Enforces a strict clock tolerance window (default: 5 minutes) to prevent replay attacks.
    """
    if not signature_header or not timestamp_header or not secret:
        return False

    try:
        # Parse ISO timestamp or unix epoch
        try:
            ts = datetime.fromisoformat(timestamp_header.replace("Z", "+00:00"))
        except ValueError:
            ts = datetime.fromtimestamp(float(timestamp_header), tz=timezone.utc)

        now = current_time or datetime.now(timezone.utc)
        if abs((now - ts).total_seconds()) > tolerance_seconds:
            return False
    except Exception:
        return False

    expected_signature = compute_signature(raw_body_bytes, secret, timestamp_header)
    return hmac.compare_digest(expected_signature, signature_header)


def build_delivery_headers(
    raw_body_bytes: bytes,
    secret: str,
    event_id: str,
    delivery_id: str,
    *,
    timestamp: datetime | None = None,
) -> dict[str, str]:
    """
    Construct HTTP headers for an outbound delivery attempt.
    The event ID remains stable across retries, while the timestamp and
    signature are freshly calculated for each attempt.
    """
    now = timestamp or datetime.now(timezone.utc)
    ts_str = now.isoformat()
    sig = compute_signature(raw_body_bytes, secret, ts_str)

    return {
        "Content-Type": "application/json",
        "User-Agent": "Unravler-Outreach-Webhooks/1.0",
        "X-Unravler-Event-Id": event_id,
        "X-Unravler-Delivery-Id": delivery_id,
        "X-Unravler-Timestamp": ts_str,
        "X-Unravler-Signature": sig,
    }
