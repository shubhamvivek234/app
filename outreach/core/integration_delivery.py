"""Reference-only integration work; possible submissions never become sendable."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any, Awaitable, Callable
import uuid

from outreach.core import integration_custody as custody, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.integrations_pilot import is_integrations_pilot_allowed
from utils.roles import has_permission

LEASE = timedelta(seconds=60)
ACTIVE = ["pending", "retry", "preparing", "possible", "received", "review_required", "held_received"]
IMMUTABLE = ("id", "workspace_id", "destination_id", "destination_type", "event_id", "payload",
    "event_type", "credential_digest", "policy_digest", "actor", "lead_id", "lead_digest", "mapping_digest",
    "external_id", "portal_id", "request_expires_at", "max_attempts")


def _utc(value: Any) -> datetime | None:
    """Malformed persisted timestamps deny authorization without crashing a batch."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _due(row: dict) -> bool:
    stamp = _utc(row.get("next_attempt_at"))
    return bool(stamp and stamp <= now())


def now() -> datetime:
    value = datetime.now(timezone.utc)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


def identity(row: dict) -> str:
    values = {name: row.get(name) for name in IMMUTABLE}
    values["request_expires_at"] = _utc(values.get("request_expires_at"))
    return canonical_hash(values)


def receipt_digest(receipt: dict) -> str:
    return canonical_hash({**receipt, "received_at": _utc(receipt.get("received_at"))})


def allowed(workspace: str, deadline: datetime) -> bool:
    from celery_workers.shutdown_handler import is_shutting_down
    return is_integrations_pilot_allowed(workspace) and not is_shutting_down() and now() < deadline


async def _access(current: Any, workspace: str, actor: str | None, kind: str, *, permission: str | None = None) -> None:
    if actor is None:
        return  # Internal event fanout only; public queue endpoints supply an actor.
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("An identified integration actor is required")
    if isinstance(current, suppression.SuppressionDatabase):
        database, options = current.database, {"session": current.session}
    else:
        database, options = current, {}
    users, members = database.users, database.workspace_members
    user = await users.find_one({"user_id": actor}, **options)
    if not user or user.get("status", "active") != "active":
        raise ValueError("Integration actor is unavailable")
    uid = user.get("firebase_uid")
    if uid and await database.account_erasure_tombstones.find_one(
            {"_id": canonical_hash(["firebase_identity", uid])}, **options):
        raise ValueError("Integration actor is stopped for deletion")
    result = await users.update_one({"user_id": actor, "status": user.get("status"), "firebase_uid": uid},
        {"$inc": {"integration_authority_revision": 1}}, **options)
    if result.matched_count != 1:
        raise ValueError("Integration actor changed")
    scope = {"workspace_id": workspace, "user_id": actor}
    member = await members.find_one(scope, **options)
    permission = permission or {"webhook": "webhook:manage", "slack": "outreach:manage", "hubspot": "lead:update"}[kind]
    if (not member or member.get("status", "active") != "active"
            or not has_permission(member.get("role"), permission)):
        raise ValueError("Integration permission is unavailable")
    result = await members.update_one({**scope, "role": member["role"], "status": member.get("status")},
        {"$inc": {"integration_authority_revision": 1}}, **options)
    if result.matched_count != 1:
        raise ValueError("Integration permission changed")


async def _source(db: Any, workspace: str, kind: str, resource: str) -> dict:
    held = await db.outreach_integration_controls.find_one(custody.control_scope(workspace, kind, resource))
    if held and held.get('latched') is True:
        raise ValueError('Integration resource remains held for operator review')
    row = await custody.collection(db, kind).find_one(custody.resource_scope(workspace, kind, resource))
    if (not row or row.get("status") != ("active" if kind == "webhook" else "connected")
            or row.get("active") is False or row.get("integration_review_required") is True):
        raise ValueError("Integration is disconnected or unavailable")
    return row


async def _crm_basis(db: Any, workspace: str, lead_id: str, portal: str) -> dict:
    lead = await db.outreach_leads.find_one({"workspace_id": workspace, "id": lead_id, "is_deleted": {"$ne": True}})
    if not lead:
        raise ValueError("CRM lead is unavailable")
    properties = {}
    for source, target in (("email", "email"), ("first_name", "firstname"), ("last_name", "lastname"),
            ("company_name", "company"), ("job_title", "jobtitle"), ("linkedin_url", "website")):
        value = lead.get(source)
        if value:
            if not isinstance(value, str) or len(value) > 4096:
                raise ValueError("CRM properties exceed supported bounds")
            cleaned = value.strip()
            if cleaned:
                properties[target] = cleaned
    properties["hs_lead_status"] = {"new": "NEW", "contacted": "IN_PROGRESS", "replied": "OPEN",
        "interested": "QUALIFIED", "not_interested": "UNQUALIFIED"}.get(lead.get("pipeline_stage", "new"), "OPEN")
    scope = {"workspace_id": workspace, "provider": "hubspot", "external_account_id": portal,
             "object_type": "contact", "internal_id": lead_id}
    mapping = await db.outreach_external_mappings.find_one(scope)
    external = mapping.get("external_id") if mapping else None
    if external is not None and (not isinstance(external, str) or not re.fullmatch(r"[0-9]{1,64}", external)):
        raise ValueError("CRM mapping requires review")
    return {"properties": properties, "lead_digest": canonical_hash([lead_id, properties]),
            "mapping_digest": canonical_hash([portal, lead_id, external]), "external_id": external,
            "mapping_scope": scope, "mapping": mapping}


class IntegrationDelivery:
    def __init__(self, db: Any) -> None:
        self.db = db

    @staticmethod
    def scope(workspace: str, job_id: str) -> dict:
        return {"workspace_id": workspace, "id": job_id, "custody_protocol_version": 2}

    async def queue(self, workspace: str, kind: str, resource: str, event_id: str, payload: dict,
                    *, actor: str | None = None, lead_id: str | None = None,
                    expected_source: dict | None = None) -> dict:
        """Persist current source identity, never credentials, before publication."""
        if kind not in custody.FIELDS or not isinstance(event_id, str) or not 1 <= len(event_id) <= 256:
            raise ValueError("Integration request identity is unavailable")
        frozen = deepcopy(payload)
        if not isinstance(frozen, dict) or len(json.dumps(frozen).encode()) > 32768:
            raise ValueError("Integration payload exceeds supported bounds")
        if kind == "hubspot" and (not actor or not isinstance(lead_id, str) or not lead_id):
            raise ValueError("CRM synchronization requires an identified lead and actor")
        policy = custody.policy_digest()
        job_id = "del2_" + canonical_hash([workspace, kind, resource, event_id])
        scope = self.scope(workspace, job_id)
        async def create(current):
            existing = await current.outreach_webhook_deliveries.find_one(scope)
            if existing:
                if existing.get("payload") != frozen or existing.get("actor") != actor or existing.get("lead_id") != lead_id:
                    raise ValueError("Integration request identity was reused")
                return {**existing, "newly_queued": False}
            if not allowed(workspace, now() + timedelta(seconds=1)) or policy != custody.policy_digest():
                raise ValueError("Integrations are unavailable")
            await _access(current, workspace, actor, kind)
            source = await _source(current, workspace, kind, resource)
            digest = custody.material_digest(source, workspace, kind)
            if expected_source is not None and digest != custody.material_digest(expected_source, workspace, kind):
                raise ValueError("Integration configuration changed before fanout")
            stamp = now()
            doc = {**scope, "_id": job_id, "event_id": event_id, "destination_id": resource, "destination_type": kind,
                "payload": frozen, "event_type": frozen.get("type"), "credential_digest": digest, "policy_digest": policy,
                "actor": actor, "lead_id": lead_id, "status": "pending", "attempt": 0,
                "max_attempts": 6 if kind == "webhook" and actor is None else 1,
                "next_attempt_at": stamp, "created_at": stamp,
                "request_expires_at": stamp + (timedelta(minutes=10) if actor else timedelta(days=1))}
            if kind == "hubspot":
                portal = source.get("metadata", {}).get("portal_id", "")
                basis = await _crm_basis(current, workspace, lead_id, portal)
                slot = canonical_hash([workspace, "hubspot", portal, lead_id])
                if await current.outreach_webhook_deliveries.find_one({"workspace_id": workspace,
                        "active_slot": slot, "status": {"$in": ACTIVE}}):
                    raise ValueError("A CRM request already owns this lead; inspect its outcome")
                doc.update(active_slot=slot, portal_id=portal, **{key: basis[key] for key in
                    ("lead_digest", "mapping_digest", "external_id")})
            doc["immutable_digest"] = identity(doc)
            await current.outreach_webhook_deliveries.insert_one(doc)
            return {**doc, "newly_queued": True}
        return await suppression.mutate_suppression(self.db, workspace, create)

    async def run(self, workspace: str, job_id: str, *, provider: Callable[[dict], Awaitable[dict]] | None = None) -> dict:
        scope = self.scope(workspace, job_id)
        saved = await self.db.outreach_webhook_deliveries.find_one(scope)
        if not saved:
            raise ValueError("Integration request is unavailable")
        if saved.get("status") == "received":
            return await self._finish(saved)
        if saved.get("status") in {"possible", "preparing"}:
            if _utc(saved.get("leased_until")) and _utc(saved["leased_until"]) <= now():
                state = "review_required" if saved["status"] == "possible" else "cancelled"
                await self.db.outreach_webhook_deliveries.update_one({**scope, "status": saved["status"],
                    "lease_id": saved.get("lease_id")}, {"$set": {"status": state,
                    "error_sanitized": "Interrupted integration work requires review", "updated_at": now()}})
            return await self._result(scope)
        if saved.get("status") not in {"pending", "retry"} or not _due(saved):
            return await self._result(scope)
        from outreach.core.restore_epoch import positive
        epoch = await positive(self.db, workspace)
        owner = uuid.uuid4().hex
        async def claim(current):
            row = await current.outreach_webhook_deliveries.find_one(scope)
            if not row or row.get("status") not in {"pending", "retry"} or not _due(row):
                return None
            expiry = now() + LEASE
            result = await current.outreach_webhook_deliveries.update_one({**scope, "status": row["status"]},
                {"$set": {"status": "preparing", "lease_id": owner, "leased_until": expiry}})
            return {**row, "lease_id": owner, "leased_until": expiry} if result.matched_count == 1 else None
        job = await suppression.mutate_suppression(self.db, workspace, claim)
        if not job:
            return await self._result(scope)
        try:
            kind = job["destination_type"]
            source = await _source(self.db, workspace, kind, job["destination_id"])
            if (identity(job) != job.get("immutable_digest") or custody.material_digest(source, workspace, kind) != job["credential_digest"]
                    or custody.policy_digest() != job["policy_digest"]):
                raise ValueError("Integration source changed")
            secret = await custody.prepare(source, workspace, kind)
            basis = await _crm_basis(self.db, workspace, job["lead_id"], job["portal_id"]) if kind == "hubspot" else None
            request_expiry, lease_expiry = _utc(job.get("request_expires_at")), _utc(job.get("leased_until"))
            if not request_expiry or not lease_expiry:
                raise ValueError("Integration authorization expiry is unavailable")
            deadline = min(request_expiry, lease_expiry)
            async def authorize(current):
                await positive(current, workspace, captured=epoch.captured)
                row = await current.outreach_webhook_deliveries.find_one({**scope, "status": "preparing", "lease_id": owner})
                active = await _source(current, workspace, kind, job["destination_id"])
                if (not row or identity(row) != job["immutable_digest"] or not secret.matches(active, workspace, kind)
                        or not allowed(workspace, deadline)):
                    raise ValueError("Integration authority changed")
                await _access(current, workspace, job.get("actor"), kind)
                if basis:
                    actual = await _crm_basis(current, workspace, job["lead_id"], job["portal_id"])
                    if any(actual[key] != job.get(key) or actual[key] != basis[key] for key in ("lead_digest", "mapping_digest")):
                        raise ValueError("CRM lead or mapping changed")
                    await current.outreach_leads.update_one({"workspace_id": workspace, "id": job["lead_id"]},
                        {"$inc": {"integration_authority_revision": 1}})
                if not allowed(workspace, deadline) or not secret.policy_matches():
                    raise ValueError("Integration authorization expired")
                result = await current.outreach_webhook_deliveries.update_one({**scope, "status": "preparing", "lease_id": owner},
                    {"$set": {"status": "possible", "possible_at": now(), "authorization_expires_at": deadline}, "$inc": {"attempt": 1}})
                if result.matched_count != 1:
                    raise ValueError("Integration owner changed")
            await suppression.mutate_suppression(self.db, workspace, authorize)
        except (ValueError, suppression.SuppressionUnavailable):
            await self.db.outreach_webhook_deliveries.update_one({**scope, "status": "preparing", "lease_id": owner},
                {"$set": {"status": "cancelled", "error_sanitized": "Integration configuration or authorization changed"}})
            return await self._result(scope)
        request = {"job": job, "credential": secret, "source": source, "basis": basis,
                   "allowed": lambda: epoch.live() and allowed(workspace, deadline) and secret.policy_matches()}
        try:
            if not request["allowed"]():
                raise ValueError("Integration authorization expired")
            async with asyncio.timeout(30):
                receipt = await (provider or integration_http)(request)
            receipt = self._receipt(receipt, kind)
        except (Exception, asyncio.CancelledError) as error:
            await self.db.outreach_webhook_deliveries.update_one({**scope, "status": "possible", "lease_id": owner},
                {"$set": {"status": "review_required", "error_sanitized": "Integration submission outcome requires review"}})
            if isinstance(error, asyncio.CancelledError):
                raise
            return await self._result(scope)
        # Preserve minimal original HTTP evidence even if erasure stopped new work.
        result = await self.db.outreach_webhook_deliveries.update_one({**scope, "status": "possible", "lease_id": owner},
            {"$set": {"status": "received", "receipt": receipt, "receipt_digest": receipt_digest(receipt), "updated_at": now()}})
        if result.matched_count != 1:
            return await self._result(scope)
        return await self._finish({**job, "status": "received", "receipt": receipt})

    @staticmethod
    def _receipt(receipt: dict, kind: str) -> dict:
        code = receipt.get("status_code") if isinstance(receipt, dict) else None
        if type(code) is not int or not 100 <= code <= 599:
            raise ValueError("Integration HTTP receipt is unavailable")
        result = {"status_code": code, "received_at": now()}
        if kind == "hubspot" and 200 <= code < 300:
            remote = receipt.get("external_id")
            if not isinstance(remote, str) or not re.fullmatch(r"[0-9]{1,64}", remote):
                raise ValueError("CRM contact receipt is unavailable")
            result["external_id"] = remote
        return result

    async def _finish(self, job: dict) -> dict:
        workspace, kind = job["workspace_id"], job["destination_type"]
        scope = self.scope(workspace, job["id"])
        async def project(current):
            row = await current.outreach_webhook_deliveries.find_one({**scope, "status": "received", "lease_id": job.get("lease_id")})
            if not row:
                return
            source = await _source(current, workspace, kind, job["destination_id"])
            if (identity(row) != row.get("immutable_digest") or custody.material_digest(source, workspace, kind) != row["credential_digest"]
                    or custody.policy_digest() != row["policy_digest"]):
                raise ValueError("Received integration source changed")
            receipt = row.get("receipt", {})
            received = _utc(receipt.get("received_at"))
            possible = _utc(row.get("possible_at"))
            expires = _utc(row.get("authorization_expires_at"))
            if (receipt_digest(receipt) != row.get("receipt_digest") or not possible or not received or not expires
                    or not possible <= received <= expires or received > now()):
                raise ValueError("Integration receipt binding requires review")
            code = receipt.get("status_code")
            if type(code) is not int:
                raise ValueError("Integration receipt requires review")
            success = 200 <= code < 300
            if success and kind == "hubspot":
                basis = await _crm_basis(current, workspace, row["lead_id"], row["portal_id"])
                installed = (basis.get("mapping") or {}).get("integration_delivery_id") == row["id"]
                if not installed and any(basis[key] != row.get(key) for key in ("lead_digest", "mapping_digest")):
                    raise ValueError("Received CRM projection changed")
                remote = receipt.get("external_id")
                if not isinstance(remote, str) or not re.fullmatch(r"[0-9]{1,64}", remote):
                    raise ValueError("CRM receipt requires review")
                await current.outreach_external_mappings.update_one(basis["mapping_scope"], {"$set": {
                    "external_id": remote, "synced_at": receipt["received_at"], "status": "synced",
                    "integration_delivery_id": row["id"]}}, upsert=True)
            ambiguous = code == 408 or kind != "webhook" and code >= 500 or kind == "hubspot" and code == 409
            state = "delivered" if success else "review_required" if ambiguous else "failed"
            changes = {"status": state, "response_status": code, "error_sanitized": None if success else f"HTTP {code}",
                       "updated_at": now(), "leased_until": None, "lease_id": None}
            if success:
                changes["delivered_at"] = receipt["received_at"]
                await custody.collection(current, kind).update_one(custody.resource_scope(workspace, kind, row["destination_id"]),
                    {"$set": {"last_delivery_at": receipt["received_at"]}})
            elif code in {429, 500, 502, 503, 504} and kind == "webhook" and row["attempt"] < row["max_attempts"]:
                state = "retry"
                changes.update(status=state, next_attempt_at=now() + timedelta(seconds=[60, 300, 900, 3600, 21600][min(row["attempt"] - 1, 4)]))
            if state not in {"retry", "review_required"}:
                changes["active_slot"] = None
            await current.outreach_webhook_deliveries.update_one({**scope, "status": "received", "lease_id": row["lease_id"]},
                {"$set": changes, "$push": {"attempt_receipts": {
                    "attempt": row["attempt"], "owner": row["lease_id"], "possible_at": row["possible_at"],
                    "authorization_expires_at": row["authorization_expires_at"],
                    "receipt": receipt, "receipt_digest": row["receipt_digest"]}}})
        try:
            await suppression.mutate_suppression(self.db, workspace, project)
        except (ValueError, suppression.SuppressionUnavailable):
            # Never overwrite a successful commit after an unknown acknowledgement.
            await self.db.outreach_webhook_deliveries.update_one({**scope, "status": "received", "lease_id": job.get("lease_id")},
                {"$set": {"status": "held_received", "error_sanitized": "Saved integration receipt requires review"}})
        return await self._result(scope)

    async def _result(self, scope: dict) -> dict:
        row = await self.db.outreach_webhook_deliveries.find_one(scope)
        if not row:
            return {"id": scope["id"], "status": "unavailable"}
        return {"id": row["id"], "status": row["status"], "event_id": row["event_id"],
                "status_code": row.get("response_status"), "error": row.get("error_sanitized")}

    async def dispatch_due(self, batch_size: int = 20, *, provider: Callable[[dict], Awaitable[dict]] | None = None) -> dict:
        # Cross-tenant scheduler discovers references; every operation is scoped.
        rows = await self.db.outreach_webhook_deliveries.find({"custody_protocol_version": 2, "$or": [
            {"status": {"$in": ["pending", "retry"]}, "next_attempt_at": {"$lte": now()}},
            {"status": "received"}, {"status": {"$in": ["preparing", "possible"]}, "leased_until": {"$lte": now()}}
        ]}).sort("next_attempt_at", 1).limit(batch_size).to_list(length=batch_size)
        counts = {"delivered": 0, "failed": 0, "review_required": 0, "cancelled": 0, "retry": 0}
        for row in rows:
            try:
                result = await self.run(row["workspace_id"], row["id"], provider=provider)
            except (ValueError, suppression.SuppressionUnavailable):
                continue  # Database failures retain the durable record for recovery.
            if result["status"] in counts:
                counts[result["status"]] += 1
        return counts


async def integration_http(request: dict) -> dict:
    """One bounded, DNS-pinned request; no environment proxy or redirects."""
    from outreach.core.safe_transport import create_safe_client, validate_webhook_url
    from outreach.core.slack_notifier import format_slack_event_card, format_slack_test_card
    from outreach.core.webhook_signer import build_delivery_headers
    job, credential = request["job"], request["credential"]
    kind = job["destination_type"]
    if (not isinstance(credential, custody.PreparedIntegration) or not request["allowed"]()
            or not credential.matches(request["source"], job["workspace_id"], kind)
            or identity(job) != job.get("immutable_digest")):
        raise ValueError("Integration authorization is unavailable")
    method, headers = "POST", {"Content-Type": "application/json", "Accept-Encoding": "identity"}
    if kind == "webhook":
        url = request["source"]["target_url"]
        validate_webhook_url(url)
        body = json.dumps(job["payload"], separators=(",", ":"), ensure_ascii=False).encode()
        headers.update(build_delivery_headers(body, credential.value, job["event_id"], job["id"], timestamp=now()))
    elif kind == "slack":
        url = credential.value
        body = json.dumps(format_slack_test_card() if job["payload"].get("type") == "system.ping"
                          else format_slack_event_card(job["payload"]), ensure_ascii=False).encode()
    elif kind == "hubspot":
        external = request["basis"]["external_id"]
        url = "https://api.hubapi.com/crm/v3/objects/contacts" + ("/" + external if external else "")
        method = "PATCH" if external else "POST"
        headers["Authorization"] = "Bearer " + credential.value
        body = json.dumps({"properties": request["basis"]["properties"]}).encode()
    else:
        raise ValueError("Unsupported integration destination")
    if len(body) > 32768:
        raise ValueError("Integration request exceeds supported bounds")
    async with create_safe_client(preflight=request["allowed"]) as client:
        if not request["allowed"]() or not credential.policy_matches():
            raise ValueError("Integration authorization expired")
        async with client.stream(method, url, content=body, headers=headers) as response:
            result = {"status_code": response.status_code}
            if kind == "hubspot" and 200 <= response.status_code < 300:
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise ValueError("Encoded CRM receipt is unavailable")
                raw = bytearray()
                async for part in response.aiter_raw(chunk_size=8192):
                    if len(raw) + len(part) > 65536:
                        raise ValueError("CRM receipt exceeds supported bounds")
                    raw.extend(part)
                parsed = json.loads(raw)
                if not isinstance(parsed, dict) or parsed.get("status") == "error":
                    raise ValueError("CRM receipt is unavailable")
                result["external_id"] = str(parsed.get("id", ""))
            return result
