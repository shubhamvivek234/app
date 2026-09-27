"""Operator-imported dedicated IP inventory for the paid outreach pilot.

No API purchase, renewal, or cancellation is implied here. A provider order
and its expiration must be verified by an operator before import/extension.
"""
from datetime import datetime, timezone
import hashlib
import ipaddress
from urllib.parse import unquote, urlsplit

from outreach.models import ProxyConfig, ProxyStatus
from outreach.core.paid_access import _utc
from utils.encryption import encrypt
from utils.ssrf_guard import is_safe_url
from pymongo.errors import DuplicateKeyError


class ManagedProxyUnavailable(Exception):
    pass


def _proxy_from_inventory(doc: dict) -> ProxyConfig:
    return ProxyConfig(
        proxy_id=doc["_id"], provider=doc["provider"], host=doc["host"],
        port=doc["port"], username=doc["username"],
        password_enc=doc["password_enc"], country_code=doc["country_code"],
        status=ProxyStatus.HEALTHY, assigned_at=datetime.now(timezone.utc),
    )


async def import_iproyal_proxy(
    db, proxy_url: str, country_code: str, provider_order_id: str, workspace_id: str,
    expires_at: datetime, *, now: datetime | None = None,
) -> dict:
    """Validate and import one already-purchased static ISP proxy."""
    now = now or datetime.now(timezone.utc)
    country_code = country_code.strip().upper()
    provider_order_id = provider_order_id.strip()
    expires_at = _utc(expires_at)
    if len(country_code) != 2 or not country_code.isascii() or not country_code.isalpha():
        raise ValueError("A two-letter proxy country is required")
    if not provider_order_id or not workspace_id or expires_at is None or expires_at <= now:
        raise ValueError("A verified provider order and future expiration are required")
    try:
        parsed = urlsplit(proxy_url)
        host = parsed.hostname or ""
        address = ipaddress.IPv4Address(host)
        port = parsed.port
        username = unquote(parsed.username or "")
        password = unquote(parsed.password or "")
    except (ValueError, TypeError) as exc:
        raise ValueError("Proxy must have an authenticated public static IP") from exc
    if (
        parsed.scheme != "http" or not address.is_global or not port
        or not 1 <= port <= 65535 or not username or not password
        or parsed.path not in ("", "/") or parsed.query or parsed.fragment
        or not is_safe_url(f"http://{host}:{port}")
    ):
        raise ValueError("Proxy must have an authenticated public static IP")

    proxy_id = "iproyal:" + hashlib.sha256(f"{host}:{port}".encode()).hexdigest()[:24]
    doc = {
        "_id": proxy_id, "provider": "iproyal_static",
        "provider_order_id": provider_order_id, "host": host, "port": port,
        "username": username, "password_enc": encrypt(password),
        "country_code": country_code, "status": "available",
        "expires_at": expires_at, "created_at": now,
        "last_workspace_id": workspace_id, "provider_auto_renew_confirmed": False,
    }
    await db.outreach_proxy_inventory.insert_one(doc)
    return {
        "proxy_id": proxy_id, "provider": doc["provider"],
        "country_code": country_code, "expires_at": expires_at,
    }


async def reserve_sender_proxy(
    db, workspace_id: str, sender_id: str, country_code: str,
    *, now: datetime | None = None,
) -> ProxyConfig:
    """Atomically reserve one IP per sender; never reuse across customers."""
    now = now or datetime.now(timezone.utc)
    country_code = country_code.upper()
    existing = await db.outreach_proxy_leases.find_one({
        "workspace_id": workspace_id, "sender_id": sender_id,
    })
    if existing:
        inventory = await db.outreach_proxy_inventory.find_one({"_id": existing["_id"]})
        if (inventory and inventory.get("status") == "available"
                and inventory.get("country_code") == country_code
                and _utc(inventory.get("expires_at"))
                and _utc(inventory["expires_at"]) > now):
            return _proxy_from_inventory(inventory)
        if inventory and _utc(inventory.get("expires_at")) and _utc(inventory["expires_at"]) <= now:
            # The old provider term is gone. Preserve an audit entry and only
            # then allow this same sender to receive a new IP at reconnection.
            await db.outreach_proxy_lease_history.insert_one({
                **existing, "retired_at": now, "reason": "provider_term_expired",
            })
            await db.outreach_proxy_leases.delete_one({
                "_id": existing["_id"], "workspace_id": workspace_id,
                "sender_id": sender_id,
            })
        else:
            raise ManagedProxyUnavailable("Sender IP is unavailable or its country changed. Contact support.")

    candidates = await db.outreach_proxy_inventory.find({
        "provider": "iproyal_static", "country_code": country_code,
        "status": "available", "expires_at": {"$gt": now},
        "last_workspace_id": workspace_id,
    }).to_list(length=100)
    for candidate in candidates:
        expiry = _utc(candidate.get("expires_at"))
        if not expiry or expiry <= now:
            continue
        proxy_id = candidate["_id"]
        # Sticky ownership is written first. Even if connection fails, this
        # IP cannot later be assigned to an unrelated customer.
        ownership = await db.outreach_proxy_inventory.update_one(
            {"_id": proxy_id, "status": "available", "expires_at": {"$gt": now},
             "last_workspace_id": workspace_id},
            {"$set": {"last_workspace_id": workspace_id}},
        )
        if not ownership.modified_count and candidate.get("last_workspace_id") != workspace_id:
            continue
        try:
            await db.outreach_proxy_leases.insert_one({
                "_id": proxy_id, "workspace_id": workspace_id,
                "sender_id": sender_id, "country_code": country_code,
                "provider": "iproyal_static", "created_at": now,
            })
            return _proxy_from_inventory(candidate)
        except DuplicateKeyError:
            continue
    raise ManagedProxyUnavailable(
        f"No available dedicated ISP proxy in {country_code}. Request capacity; no country substitution is made."
    )


async def release_sender_reservation(db, workspace_id: str, sender_id: str, proxy_id: str) -> None:
    await db.outreach_proxy_leases.delete_one({
        "_id": proxy_id, "workspace_id": workspace_id, "sender_id": sender_id,
    })
