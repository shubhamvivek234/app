"""Explicit mailbox/finder policies using shared sender ownership and receipts."""
import os
from copy import deepcopy
from datetime import datetime, timezone
from email import message_from_bytes, policy

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from celery_workers.shutdown_handler import is_shutting_down
from outreach.core.authorization import canonical_hash
from outreach.core.content_approval import ContentApproval, sequence_binding
from outreach.core.email_finder import HUNTER_FOUND_URL, normalize_email, _linkedin_handle, is_lead_email_available
from outreach.core.inbox_freshness import credential_generation
from outreach.core.mailbox_connection import get_ready_mailbox, is_email_send_pilot_allowed
from outreach.core.mailbox_delivery import GMAIL_SEND_URL, GRAPH_SEND_URL
from outreach.core.paid_access import get_active_entitlement, live_actions_enabled
from outreach.core.request_guard import RequestEnvelope, RequestDenied, SubmissionUncertain, current_request_parent
from outreach.core.sequence_versions import load_sequence
from outreach.core.provider_custody import PreparedSecret
from outreach.core.session_custody import custody_mode
from outreach.core.paid_access import _utc


def mailbox_identity(resource: dict) -> str:
    return canonical_hash([resource.get("provider"), resource.get("provider_user_id"), resource.get("email"), resource.get("connection_job_id")])


def provider_generation(account: dict, resource: dict, source: str) -> str:
    identity = mailbox_identity(resource) if source == "email_send" else canonical_hash(resource.get("api_key_enc"))
    return canonical_hash([credential_generation(account), source, identity])


class ProviderEnvelope(RequestEnvelope):
    def __init__(self, db: AsyncIOMotorDatabase, workspace_id: str, sender_id: str, account: dict, source: str,
                 resource: dict, *, operation_id: str, lead_id: str) -> None:
        if source not in {"email_send", "email_find"} or not operation_id or not lead_id:
            raise ValueError("A stable provider operation and lead are required")
        self.resource = deepcopy(resource)
        self.account_generation = credential_generation(account)
        self.lead_id = lead_id
        self.finder_handle = None
        self.prepared_secret: PreparedSecret | None = None
        self.endpoint = HUNTER_FOUND_URL if source == "email_find" else {
            "gmail": GMAIL_SEND_URL, "microsoft": GRAPH_SEND_URL}.get(resource.get("provider"))
        if not self.endpoint:
            raise ValueError("Unsupported provider")
        super().__init__(db, workspace_id, sender_id, provider_generation(account, resource, source), source, "", operation_id=operation_id)

    async def _validate(self, now: datetime, parent) -> dict:
        if is_shutting_down() or not live_actions_enabled():
            raise RequestDenied("live_actions_disabled")
        if not parent or not parent.validator:
            raise RequestDenied("provider_context_missing")
        account = await self.db.outreach_accounts.find_one({"workspace_id": self.workspace_id, "id": self.sender_id,
            "status": "active", "is_deleted": {"$ne": True}})
        if not account or credential_generation(account) != self.account_generation:
            raise RequestDenied("sender_changed")
        if not await get_active_entitlement(self.db, self.workspace_id):
            raise RequestDenied("paid_access_required")
        if self.source == "email_send":
            if not is_email_send_pilot_allowed(self.workspace_id):
                raise RequestDenied("action_disabled")
            resource = await get_ready_mailbox(self.db, self.workspace_id, self.sender_id)
        else:
            if os.getenv("OUTREACH_HUNTER_ENABLED", "false").lower() not in {"true", "1"}:
                raise RequestDenied("action_disabled")
            resource = await self.db.outreach_hunter_credentials.find_one({"workspace_id": self.workspace_id})
        if not resource or provider_generation(account, resource, self.source) != self.generation:
            raise RequestDenied("provider_generation_changed")
        if ((self.prepared_secret and not self.prepared_secret.matches(resource, self.workspace_id,
                self.sender_id if self.source == 'email_send' else None))
                or not self.prepared_secret and custody_mode() == 'kms_v1'):
            raise RequestDenied("provider_credential_changed")
        if self.prepared_secret:
            from outreach.core.dispatch_authority import AuthorityDatabase
            if isinstance(self.db, AuthorityDatabase):
                captured = self.prepared_secret
                self.db.checks.append(lambda _: captured.policy_matches())
        if custody_mode() == 'kms_v1' and self.source == 'email_send' and (
                not _utc(resource.get('token_expires_at')) or _utc(resource['token_expires_at']) <= now):
            raise RequestDenied('mailbox_token_expired')
        lead = await self.db.outreach_leads.find_one({"workspace_id": self.workspace_id, "id": self.lead_id, "assigned_account_id": self.sender_id})
        if not lead or lead.get("has_replied") or lead.get("do_not_contact") or lead.get("is_suppressed"):
            raise RequestDenied("lead_suppressed")
        if self.source == "email_send" and not await is_lead_email_available(self.db, self.workspace_id, lead):
            raise RequestDenied("lead_suppressed")
        if self.source == "email_find" and (not self.finder_handle or _linkedin_handle(lead.get("linkedin_url")) != self.finder_handle
                or normalize_email(lead.get("email")) or lead.get("email_opted_out")):
            raise RequestDenied("lookup_target_changed")
        campaign = await self.db.outreach_campaigns.find_one({"workspace_id": self.workspace_id, "id": lead.get("campaign_id"),
            "status": "active", "is_deleted": {"$ne": True}})
        sequence = await load_sequence(self.db, self.workspace_id, lead.get("campaign_id"), campaign=campaign) if campaign else None
        node = (sequence or {}).get("compiled_dag", {}).get("nodes", {}).get(lead.get("current_node_id"), {})
        if (not campaign or campaign.get("pause_reasons") or campaign.get("sequence_edit_pending")
                or lead.get("execution_state") not in {"queued", "waiting_delay"}
                or lead.get("authorized_revision") != campaign.get("authorization_revision")
                or lead.get("sequence_version") != (sequence or {}).get("version", 1)
                or node.get("type") != {"email_send": "send_email", "email_find": "find_email"}[self.source]):
            raise RequestDenied("provider_context_changed")
        self.campaign_limits = campaign.get("limits") or {}
        reason = await parent.validator()
        if reason:
            raise RequestDenied(reason)
        from outreach.core.execution_permission import ExecutionPermission
        if not await ExecutionPermission(self.db).allowed(self.workspace_id, self.sender_id, self.generation, self.source, now=now):
            raise RequestDenied("execution_permission_required")
        return account

    def bind_finder(self, prepared: PreparedSecret) -> None:
        if self.source != "email_find" or prepared.kind != "finder" or not prepared.matches(self.resource, self.workspace_id):
            raise RequestDenied("finder_credential_changed")
        self.prepared_secret = prepared

    def bind_mailbox(self, prepared: PreparedSecret) -> None:
        if (self.source != "email_send" or prepared.kind != "mailbox" or prepared.workspace_id != self.workspace_id
                or prepared.sender_id != self.sender_id or prepared.identity_digest != mailbox_identity(self.resource)):
            raise RequestDenied("mailbox_credential_changed")
        self.prepared_secret = prepared

    def assert_bearer(self, value: str) -> None:
        if ((self.prepared_secret and (not self.prepared_secret.policy_matches() or value != self.prepared_secret.value))
                or not self.prepared_secret and custody_mode() == 'kms_v1'):
            raise RequestDenied("mailbox_credential_changed")

    def assert_finder(self, params: dict) -> None:
        if self.prepared_secret:
            if not self.prepared_secret.matches(self.resource, self.workspace_id):
                raise RequestDenied("finder_credential_changed")
            value = self.prepared_secret.value
        else:
            if custody_mode() == "kms_v1": raise RequestDenied("finder_credential_changed")
            from utils.encryption import decrypt_strict
            value = decrypt_strict(self.resource["api_key_enc"])
        if params != {"linkedin_handle": self.finder_handle, "api_key": value}:
            raise RequestDenied("lookup_target_changed")

    def assert_email(self, mime: bytes) -> None:
        binding = self.content_binding()
        try:
            message = message_from_bytes(mime, policy=policy.default)
            body = message.get_content().replace("\r\n", "\n")
            content = {"subject": str(message["Subject"]), "body": body, "sender_email": str(message["From"])}
        except (ValueError, TypeError, AttributeError):
            raise RequestDenied("content_changed") from None
        if (not binding or binding.get("action") != "send_email" or binding.get("recipient") != str(message["To"])
                or binding.get("content") != content or content["sender_email"] != self.resource.get("email")):
            raise RequestDenied("content_changed")

    async def _validate_content(self, action: str, now: datetime) -> None:
        if self.source == "email_find":
            return
        binding = self.content_binding()
        if (action != "email" or not binding or binding.get("workspace_id") != self.workspace_id
                or binding.get("sender_id") != self.sender_id or binding.get("source") != "sequence"
                or binding.get("credential_generation") != self.account_generation
                or binding.get("context", {}).get("lead_id") != self.lead_id
                or binding.get("context", {}).get("mailbox_identity") != mailbox_identity(self.resource)
                or await sequence_binding(self.db, self.workspace_id, self.lead_id) != binding
                or not await ContentApproval(self.db).allowed(binding, now=now)):
            raise RequestDenied("content_approval_required")

    async def _authorize_content(self, action: str, now: datetime) -> dict | None:
        if self.source == "email_find":
            return None
        record = await ContentApproval(self.db).authorize_submission(self.content_binding(), now=now)
        if not record:
            raise RequestDenied("content_approval_required")
        return record

    async def call(self, method: str, path: str, factory, *, action: str = "read", now: datetime | None = None,
                   side_effect: bool | None = None):
        expected_method, expected_action = ("POST", "email") if self.source == "email_send" else ("GET", "finder")
        if method != expected_method or path != self.endpoint or action != expected_action:
            raise RequestDenied("provider_endpoint_changed")
        # A finder GET can consume credits. It always crosses the effect boundary.
        return await super().call(method, path, factory, action=action, now=now, side_effect=True)

    async def reserve_budget(self, action: str, config: dict, now: datetime, reservation_id: str) -> tuple:
        day = now.strftime("%Y%m%d")
        scope = {"_id": canonical_hash([self.workspace_id, self.source, day]), "workspace_id": self.workspace_id, "source": self.source, "day": day}
        cap = 100 if self.source == "email_send" else 10
        try:
            await self.db.outreach_provider_budgets.insert_one({**scope, "count": 0})
        except DuplicateKeyError:
            pass
        reserved = await self.db.outreach_provider_budgets.update_one({**scope, "count": {"$lt": cap}}, {
            "$inc": {"count": 1}, "$set": {f"reservations.{reservation_id}": "reserved"}})
        if not reserved.matched_count:
            return False, 3600, "provider_workspace_cap"
        result = await super().reserve_budget(action, config, now, reservation_id)
        if not result[0]:
            await self._refund_workspace(reservation_id, day)
        return result

    async def _refund_workspace(self, reservation_id: str, day: str) -> None:
        await self.db.outreach_provider_budgets.update_one({"_id": canonical_hash([self.workspace_id, self.source, day]),
            "workspace_id": self.workspace_id, f"reservations.{reservation_id}": "reserved"}, {
            "$inc": {"count": -1}, "$set": {f"reservations.{reservation_id}": "not_submitted"}})

    async def refund_budget(self, action: str, reservation_id: str, day: str) -> None:
        await super().refund_budget(action, reservation_id, day)
        await self._refund_workspace(reservation_id, day)

    def response_evidence(self, response, action: str, mutation: bool) -> dict:
        code = response.status_code
        if self.source == "email_send":
            expected = 200 if self.resource["provider"] == "gmail" else 202
            if code != expected:
                if 200 <= code < 300:
                    raise SubmissionUncertain(code)
                return {"provider_outcome": {"status": "rejected"}}
            body = response.json() if self.resource["provider"] == "gmail" else {}
            if (not isinstance(body, dict) or body.get("error") or body.get("errors")
                    or self.resource["provider"] == "gmail" and (not isinstance(body.get("id"), str) or not body["id"].strip())):
                raise SubmissionUncertain(code)
            return {"provider_outcome": {"status": "accepted", "provider_message_id": body.get("id"), "provider_thread_id": body.get("threadId")}}
        if code == 404:
            return {"provider_outcome": {"status": "not_found"}}
        if code != 200:
            return {"provider_outcome": {"status": "rejected"}}
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or payload.get("error") or payload.get("errors") or data.get("error"):
            raise SubmissionUncertain(code)
        verification = data.get("verification") or {}
        email = normalize_email(data.get("email"))
        found = bool(email and data.get("source_type") == "found" and isinstance(verification, dict) and verification.get("status") == "valid")
        sources = data.get("sources") or []
        urls = [item["uri"][:2048] for item in sources[:3] if isinstance(item, dict) and isinstance(item.get("uri"), str)] if isinstance(sources, list) else []
        return {"provider_outcome": {"status": "found" if found else "not_found", "email": email if found else None,
            "verification": "valid" if found else None, "source_urls": urls if found else []}}


async def create_provider_envelope(db: AsyncIOMotorDatabase, workspace_id: str, sender_id: str, source: str,
                                   resource: dict, operation_id: str, lead_id: str) -> ProviderEnvelope:
    if not current_request_parent():
        raise RequestDenied("provider_context_missing")
    account = await db.outreach_accounts.find_one({"workspace_id": workspace_id, "id": sender_id})
    if not account:
        raise RequestDenied("sender_changed")
    return ProviderEnvelope(db, workspace_id, sender_id, account, source, resource, operation_id=operation_id, lead_id=lead_id)
