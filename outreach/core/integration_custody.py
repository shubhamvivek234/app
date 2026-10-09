"""Scoped integration credentials; key work stays outside Mongo callbacks."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hmac
import os
from typing import Any
import uuid

from outreach.core import session_custody, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable, PREFIX
from outreach.core.oauth_app_custody import KMS_SETTINGS
from utils.encryption import decrypt_strict, encrypt

FIELDS = {"webhook": "secret_enc", "slack": "access_token_enc", "hubspot": "access_token_enc"}
MAX_VALUE_BYTES = 8192


def policy_digest() -> str:
    """Capture mode/environment/key/role policy without exposing configuration."""
    return canonical_hash([session_custody.custody_mode(),
        os.getenv("OUTREACH_CUSTODY_ENVIRONMENT_ID", "").strip(),
        *(os.getenv(name, "").strip() for name in KMS_SETTINGS)])


def resource_scope(workspace: str, kind: str, resource_id: str) -> dict:
    if (kind not in FIELDS or not isinstance(workspace, str) or not workspace.strip()
            or not isinstance(resource_id, str) or not resource_id.strip()):
        raise CustodyUnavailable("Integration identity is unavailable")
    return {"workspace_id": workspace, **({"id": resource_id} if kind == "webhook" else {"provider": kind})}


def collection(db: Any, kind: str) -> Any:
    return db.outreach_webhooks if kind == "webhook" else db.outreach_integrations


def control_scope(workspace: str, kind: str, resource_id: str) -> dict:
    resource_scope(workspace, kind, resource_id)
    return {'workspace_id': workspace, '_id': canonical_hash(['integration_control', workspace, kind, resource_id])}


def _identity(row: dict, workspace: str, kind: str) -> list:
    if not isinstance(row, dict) or kind not in FIELDS or row.get("workspace_id") != workspace:
        raise CustodyUnavailable("Integration workspace changed")
    if not isinstance(row.get("metadata", {}), dict):
        raise CustodyUnavailable("Integration configuration is malformed")
    resource = row.get("id") if kind == "webhook" else row.get("provider")
    destination = (row.get("target_url") if kind == "webhook" else
                   row.get("metadata", {}).get("portal_id", "") if kind == "hubspot" else "slack-incoming-webhook")
    if (not isinstance(resource, str) or not resource or kind != "webhook" and resource != kind
            or not isinstance(destination, str) or not destination):
        raise CustodyUnavailable("Integration destination changed")
    return [kind, resource, destination]


def material_digest(row: dict, workspace: str, kind: str) -> str:
    values = {name: row.get(name) for name in ("workspace_id", "credential_generation", "custody_workspace_id",
        FIELDS[kind], "status", "active", "events", "metadata")}
    if 'integration_review_required' in row:
        values['integration_review_required'] = row['integration_review_required']
    return canonical_hash([_identity(row, workspace, kind), values])


def _context(row: dict, workspace: str, kind: str):
    identity = _identity(row, workspace, kind)
    if row.get("custody_workspace_id") != workspace:
        raise CustodyUnavailable("Integration credential scope is unavailable")
    return session_custody.context(workspace, canonical_hash(identity), row.get("credential_generation"),
                                   "integration_" + kind)


def _validate(value: str, kind: str) -> None:
    if (not isinstance(value, str) or not 1 <= len(value.encode()) <= MAX_VALUE_BYTES
            or value != value.strip() or value.startswith(PREFIX)
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise CustodyUnavailable("Integration credential is unavailable")
    if kind == "slack":
        from outreach.core.slack_notifier import validate_slack_webhook_url
        try:
            validate_slack_webhook_url(value)
        except ValueError:
            raise CustodyUnavailable("Integration credential is unavailable") from None


async def seal(value: str, record: dict, workspace: str, kind: str) -> dict:
    """Prepare one new generation before a guarded configuration write."""
    row = deepcopy(record)
    _identity(row, workspace, kind)
    _validate(value, kind)
    policy = policy_digest()
    row.update(credential_generation=uuid.uuid4().hex, custody_workspace_id=workspace)
    envelope = (await session_custody.configured_custody().seal(value, _context(row, workspace, kind))
                if session_custody.custody_mode() == "kms_v1" else encrypt(value))
    if policy != policy_digest():
        raise CustodyUnavailable("Integration custody changed during sealing")
    return {"credential_generation": row["credential_generation"], "custody_workspace_id": workspace,
            FIELDS[kind]: envelope}


@dataclass(frozen=True)
class PreparedIntegration:
    workspace: str
    kind: str
    binding: str
    policy: str
    value: str = field(repr=False)
    value_digest: str = field(repr=False)

    def policy_matches(self) -> bool:
        try:
            _validate(self.value, self.kind)
            return (hmac.compare_digest(self.policy, policy_digest())
                    and hmac.compare_digest(self.value_digest, canonical_hash(self.value)))
        except (ValueError, TypeError, AttributeError):
            return False

    def matches(self, record: dict, workspace: str, kind: str) -> bool:
        try:
            return (workspace == self.workspace and kind == self.kind and self.policy_matches()
                    and hmac.compare_digest(self.binding, material_digest(record, workspace, kind)))
        except (ValueError, TypeError, AttributeError):
            return False


async def prepare(record: dict, workspace: str, kind: str) -> PreparedIntegration:
    row = deepcopy(record)
    binding, policy = material_digest(row, workspace, kind), policy_digest()
    storage = row.get(FIELDS[kind])
    try:
        if session_custody.custody_mode() == "kms_v1":
            value = await session_custody.configured_custody().open(storage, _context(row, workspace, kind))
        else:
            if not isinstance(storage, str) or storage.startswith(PREFIX):
                raise ValueError("Storage")
            value = decrypt_strict(storage)
        _validate(value, kind)
    except (ValueError, OSError, TypeError):
        raise CustodyUnavailable("Integration credential opening is unavailable") from None
    result = PreparedIntegration(workspace, kind, binding, policy, value, canonical_hash(value))
    if not result.policy_matches():
        raise CustodyUnavailable("Integration custody changed during opening")
    return result


def _check_deadline(deadline: datetime | None) -> None:
    from outreach.core.integration_delivery import now
    if deadline is not None and deadline <= now():
        raise CustodyUnavailable("Integration API key authority expired")


async def check_authority(current: Any, workspace: str, authority: dict) -> datetime | None:
    """Fence the captured initiating member/key in the final configuration transaction."""
    from outreach.core.integration_delivery import _access, _utc, now
    if not isinstance(authority, dict):
        raise CustodyUnavailable("Integration configuration authority is unavailable")
    if authority.get("actor"):
        await _access(current, workspace, authority["actor"], "webhook",
                      permission=authority.get("permission", "webhook:manage"))
        return
    key_id, key_hash = authority.get("api_key_id"), authority.get("key_hash")
    if not isinstance(key_id, str) or not key_id or not isinstance(key_hash, str) or not key_hash:
        raise CustodyUnavailable("Integration API key authority is unavailable")
    scope = {"workspace_id": workspace, "id": key_id, "key_hash": key_hash}
    key = await current.outreach_api_keys.find_one(scope)
    expiry = _utc((key or {}).get("expires_at"))
    if (not key or key.get("revoked_at") or "leads:read" not in key.get("scopes", [])
            or key.get("expires_at") is not None and (not expiry or expiry <= now())):
        raise CustodyUnavailable("Integration API key authority changed")
    changed = await current.outreach_api_keys.update_one({**scope, "revoked_at": key.get("revoked_at"),
        "scopes": "leads:read", "expires_at": key.get("expires_at")}, {"$inc": {"integration_authority_revision": 1}})
    if changed.matched_count != 1:
        raise CustodyUnavailable("Integration API key authority changed")
    _check_deadline(expiry)
    return expiry


async def save(db: Any, workspace: str, kind: str, row: dict, *, previous: dict | None, policy: str, authority: dict) -> None:
    """Install only the exact inspected source, ordered against erasure/dispatch."""
    captured = deepcopy(row)
    identity = captured.get("id") if kind == "webhook" else kind
    scope = resource_scope(workspace, kind, identity)
    expected = material_digest(previous, workspace, kind) if previous else None
    async def write(current):
        from outreach.core.integrations_pilot import is_integrations_pilot_allowed
        if not is_integrations_pilot_allowed(workspace):
            raise CustodyUnavailable("Integrations are unavailable")
        deadline = await check_authority(current, workspace, authority)
        held = await current.outreach_integration_controls.find_one(control_scope(workspace, kind, identity))
        _check_deadline(deadline)
        if held and held.get('latched') is True:
            raise CustodyUnavailable('Integration resource remains held for operator review')
        found = await collection(current, kind).find_one(scope)
        _check_deadline(deadline)
        if (not is_integrations_pilot_allowed(workspace) or policy != policy_digest()
                or (material_digest(found, workspace, kind) if found else None) != expected):
            raise CustodyUnavailable("Integration configuration changed; reload before saving")
        if found:
            changed = await collection(current, kind).update_one(scope, {"$set": captured})
            if changed.matched_count != 1:
                raise CustodyUnavailable("Integration configuration changed")
        else:
            await collection(current, kind).insert_one({**scope, **captured})
        _check_deadline(deadline)
    await suppression.mutate_suppression(db, workspace, write)


async def disconnect(db: Any, workspace: str, kind: str, resource_id: str, *, authority: dict) -> bool:
    async def remove(current):
        deadline = await check_authority(current, workspace, authority)
        _check_deadline(deadline)
        result = await collection(current, kind).delete_one(resource_scope(workspace, kind, resource_id))
        _check_deadline(deadline)
        await current.outreach_webhook_deliveries.update_many({"workspace_id": workspace,
            "destination_id": resource_id, "status": {"$in": ["pending", "retry"]}},
            {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc)}})
        _check_deadline(deadline)
        return result.deleted_count == 1
    return await suppression.mutate_suppression(db, workspace, remove)
