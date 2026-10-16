"""Stopped workspace erasure, bounded batches and minimal retention review.

No provider calls. Drain acknowledgement is an operator assertion, not a
detector of cached credentials, old workers, backups or remote vendor data.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, TypeVar, TYPE_CHECKING

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from outreach.core.authorization import canonical_hash
from outreach.core.paid_access import _utc
from outreach.core.suppression import (
    SuppressionDatabase, SuppressionUnavailable, ensure_suppression_guard,
    guard_scope, touch_suppression_guard,
)

if TYPE_CHECKING:
    from outreach.core.dispatch_authority import AuthorityDatabase

BATCH_SIZE = 200
INSPECTION_LIMIT = 10000
DATA_COLLECTIONS = tuple("""
outreach_access_requests outreach_accounts outreach_ai_prompts outreach_analytics
outreach_api_keys outreach_campaigns outreach_campaign_deletions outreach_connection_jobs outreach_connection_locks
outreach_content_approvals outreach_do_not_contact outreach_email_discoveries
outreach_email_inbound_events outreach_email_operations outreach_email_suppressions
outreach_engage_contacts outreach_engage_drafts outreach_engage_lists outreach_engage_posts
outreach_entitlements outreach_event_outbox outreach_lead_admissions outreach_execution_permissions
outreach_execution_epochs outreach_restore_proxy_exclusions outreach_restore_invoices outreach_restore_exclusions outreach_restore_suppressions outreach_restore_reply_stops outreach_reply_stops outreach_external_mappings outreach_health outreach_health_controls outreach_hunter_credentials outreach_import_jobs
outreach_inbox_jobs outreach_inbox_reminders outreach_inbox_snippets outreach_inbox_tags
outreach_inbox_threads outreach_integrations outreach_integration_reviews outreach_integration_controls outreach_intents outreach_lead_notes outreach_lead_tags outreach_lead_lists outreach_lead_list_members outreach_lead_list_imports outreach_leads
outreach_mailbox_connection_jobs outreach_mailbox_oauth_states outreach_mailboxes outreach_mailbox_exchange_budgets
outreach_mailbox_sync_jobs outreach_mailbox_sync_reads outreach_mailbox_read_budgets
outreach_manual_actions outreach_payment_receipts outreach_physical_requests
outreach_provider_budgets outreach_proxy_inventory outreach_proxy_lease_history
outreach_proxy_leases outreach_proxy_lifecycle_reviews outreach_proxy_adoptions outreach_request_budgets outreach_sender_execution outreach_sender_slots
outreach_sequence_jobs outreach_sequence_versions outreach_sequences outreach_connection_waits outreach_swipe_files
outreach_tasks outreach_templates outreach_voice_artifacts outreach_voices
outreach_voice_preparation_jobs outreach_voice_preparation_budgets outreach_voice_studio_jobs outreach_voice_studio_budgets outreach_voice_source_migrations outreach_voice_vendor_reads outreach_credential_migrations
outreach_webhook_deliveries outreach_webhooks outreach_withdrawn_invites outreach_writing_styles
""".split())
CONTROLS = frozenset({"outreach_suppression_guards", "outreach_erasure_requests", "outreach_erasure_holds"})
PERSISTENT = frozenset({"outreach_proxy_inventory", "outreach_proxy_leases"})
LEDGERS = frozenset({"outreach_physical_requests", "outreach_manual_actions", "outreach_intents",
    "outreach_tasks", "outreach_email_operations", "outreach_email_discoveries", "outreach_connection_jobs",
    "outreach_voice_preparation_jobs", "outreach_voice_studio_jobs"})
AMBIGUOUS = frozenset({"preparing", "in_flight", "unknown_outcome", "uncertain", "dispatching",
    "resolving", "received", "projection_pending", "finalizing", "repairing", "generating", "held_outcome", "possible", "held_received"})
ResultT = TypeVar("ResultT")


async def workspace_is_open(db: AsyncIOMotorDatabase | SuppressionDatabase | AuthorityDatabase, workspace_id: str) -> bool:
    """Missing guard means no erasure request; a persistent stop never reopens."""
    doc = await db.outreach_suppression_guards.find_one(guard_scope(workspace_id))
    return not doc or not doc.get("erasure_state")


async def identity_is_erased(db: AsyncIOMotorDatabase, firebase_uid: str | None) -> bool:
    """Check a persistent UID digest before allowing profile recreation."""
    if not firebase_uid:
        return False
    collection = db.account_erasure_tombstones.with_options(read_concern=ReadConcern("majority"))
    return await collection.find_one({"_id": canonical_hash(["firebase_identity", firebase_uid])}) is not None


async def stop_identity(db: AsyncIOMotorDatabase, firebase_uid: str | None) -> None:
    """Retain only a UID digest; no token, email, name or plaintext UID."""
    if firebase_uid:
        await db.account_erasure_tombstones.with_options(write_concern=WriteConcern("majority")).update_one(
            {"_id": canonical_hash(["firebase_identity", firebase_uid])}, {"$setOnInsert": {
                "requested_at": datetime.now(timezone.utc)}}, upsert=True)


async def require_open_workspace(current_user: dict, db: AsyncIOMotorDatabase) -> None:
    """Block new tenant API work while erasure awaits a full writer drain."""
    workspace = current_user.get("default_workspace_id") or current_user.get("workspace_id") or current_user.get("user_id")
    if not workspace or not await workspace_is_open(db, workspace):
        raise HTTPException(409, "This workspace is closed for data deletion.")


def _scope(name: str, workspace: str) -> dict:
    if name == "outreach_proxy_inventory":
        return {"$or": [{"last_workspace_id": workspace}, {"workspace_id": workspace}]}
    return {"workspace_id": workspace}


async def _control(db: AsyncIOMotorDatabase, workspace: str,
                   operation: Callable[[SuppressionDatabase], Awaitable[ResultT]]) -> ResultT:
    """Private control writes share ordering, and can only keep erasure stopped."""
    async def apply(session):
        await touch_suppression_guard(db, workspace, session)
        return await operation(SuppressionDatabase(db, workspace, session))
    try:
        async with asyncio.timeout(30):
            await ensure_suppression_guard(db, workspace)
            async with await db.client.start_session() as session:
                return await session.with_transaction(apply, read_concern=ReadConcern("snapshot"),
                    write_concern=WriteConcern("majority"), max_commit_time_ms=5000)
    except (PyMongoError, TimeoutError) as exc:
        raise SuppressionUnavailable("Workspace deletion could not be committed") from exc


class OutreachErasure:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    async def _snapshot(self, workspace: str, current: Any | None = None) -> dict[str, list[dict]]:
        current = self.db if current is None else current
        session = current.session if isinstance(current, SuppressionDatabase) else None
        names = await self.db.list_collection_names()
        unknown = set(names) - set(DATA_COLLECTIONS) - CONTROLS
        for name in sorted(unknown):
            if name.startswith("outreach_") and await self.db[name].find_one({"workspace_id": workspace}):
                raise ValueError("Unclassified outreach collection requires an erasure policy")
        records = {}
        for name in DATA_COLLECTIONS:
            if name not in names:
                continue
            # Inventory has sticky ownership rather than the ordinary tenant key.
            if name == "outreach_proxy_inventory":
                rows = await self.db[name].find(_scope(name, workspace), session=session).limit(INSPECTION_LIMIT + 1).to_list(length=INSPECTION_LIMIT + 1)
            else:
                rows = await current[name].find(_scope(name, workspace)).limit(INSPECTION_LIMIT + 1).to_list(length=INSPECTION_LIMIT + 1)
            if len(rows) > INSPECTION_LIMIT:
                raise ValueError("Workspace exceeds bounded erasure inspection capacity")
            records[name] = rows
        return records

    @staticmethod
    def _digest(workspace: str, request: dict, records: dict[str, list[dict]]) -> str:
        return canonical_hash([workspace, request.get("status"), request.get("completed_collections", []),
            [(name, sorted(canonical_hash(row) for row in rows)) for name, rows in sorted(records.items())]])

    async def request(self, workspace: str, user_id: str) -> dict:
        """Latch owned workspace execution and scrub immediately usable secrets."""
        if not user_id:
            raise ValueError("Workspace owner is required")
        owner_hash = canonical_hash(["erasure_owner", user_id])
        scope = guard_scope(workspace)
        async def stop(current):
            previous = await current.outreach_erasure_requests.find_one(scope)
            owner = await self.db.workspaces.find_one({"workspace_id": workspace}, session=current.session)
            if owner and owner.get("owner_id") != user_id:
                raise ValueError("Actual workspace owner changed")
            legacy_owner = workspace == user_id and not owner and await self.db.users.find_one({"user_id": user_id}, session=current.session)
            if not owner and not legacy_owner and (not previous or previous.get("owner_hash") != owner_hash):
                raise ValueError("Actual workspace owner is required for deletion")
            if previous:
                if previous.get("owner_hash") != owner_hash:
                    raise ValueError("Workspace owner changed")
                if previous["status"] == "erased" and self._has_mutable_data(await self._snapshot(workspace, current)):
                    await self._stop(current, workspace, datetime.now(timezone.utc))
                    await current.outreach_suppression_guards.update_one(scope, {"$set": {"erasure_state": "stopped"}})
                    await current.outreach_erasure_requests.update_one(scope, {"$set": {"status": "awaiting_drain"}})
                    return {"workspace_id": workspace, "status": "awaiting_drain"}
                return {"workspace_id": workspace, "status": previous["status"]}
            now = datetime.now(timezone.utc)
            await current.outreach_suppression_guards.update_one(scope, {"$set": {
                "erasure_state": "stopped", "erasure_requested_at": now}})
            await self._stop(current, workspace, now)
            await current.outreach_erasure_requests.insert_one({**scope, "owner_hash": owner_hash,
                "status": "awaiting_drain", "requested_at": now, "completed_collections": []})
            return {"workspace_id": workspace, "status": "awaiting_drain"}
        return await _control(self.db, workspace, stop)

    @staticmethod
    def _has_mutable_data(records: dict[str, list[dict]]) -> bool:
        return any(row for name, rows in records.items() for row in rows
            if name not in PERSISTENT or not row.get("erasure_sanitized_at"))

    async def _stop(self, current: SuppressionDatabase, workspace: str, now: datetime) -> None:
        scope = {"workspace_id": workspace}
        await current.outreach_entitlements.update_many(scope, {"$set": {"is_revoked": True, "status": "revoked"}})
        await current.outreach_campaigns.update_many(scope, {"$set": {"status": "paused", "auto_launch_enabled": False},
            "$inc": {"authorization_revision": 1}, "$addToSet": {"pause_reasons": "erasure_requested"}})
        await current.outreach_sender_execution.update_many(scope, {"$set": {
            "permission.latched": True, "permission.expires_at": now, "permission.stop_reason": "erasure_requested"},
            "$inc": {"permission_revision": 1}})
        await current.outreach_health_controls.update_many({**scope, 'status': 'armed'}, {'$set': {
            'status': 'stopped', 'stop_reason': 'erasure_requested', 'stopped_at': now}})
        scrub = {
            "outreach_accounts": ("session_cookie_enc", "encrypted_session_cookie", "jsession_id", "li_a_enc", "li_at_enc", "jsession_id_enc", "proxy", "proxy_config"),
            "outreach_connection_jobs": ("li_at_enc", "jsession_id_enc", "li_a_enc", "password_enc", "created_at"),
            "outreach_mailboxes": ("access_token_enc", "refresh_token_enc"),
            "outreach_mailbox_connection_jobs": ("authorization_code_enc", "code_verifier_enc"),
            "outreach_mailbox_oauth_states": ("code_verifier_enc",),
            "outreach_mailbox_sync_reads": ("response_enc",),
            "outreach_hunter_credentials": ("api_key_enc",),
            "outreach_voice_artifacts": ("audio_enc",),
            "outreach_voice_studio_jobs": ("input_enc", "result_enc"),
            "outreach_integrations": ("secret_enc", "access_token_enc", "refresh_token_enc"),
            "outreach_webhooks": ("secret_enc",),
            "outreach_webhook_deliveries": ("secret_enc", "target_url_enc"),
        }
        for name, fields in scrub.items():
            changes = {"erasure_requested_at": now}
            if name in {"outreach_accounts", "outreach_mailboxes"}:
                changes.update({"status": "disconnected", "is_deleted": True})
            if name == "outreach_voice_artifacts":
                changes["status"] = "failed"
            await current[name].update_many(scope, {"$unset": dict.fromkeys(fields, ""), "$set": changes})
        await current.outreach_accounts.update_many({**scope, "connection_finalization": {"$exists": True}}, {
            "$set": {"connection_finalization.state": "closed", "connection_finalization.closed_at": now}})
        await current.outreach_api_keys.update_many(scope, {"$set": {"revoked_at": now}})
        await current.outreach_voice_preparation_jobs.update_many({**scope, "status": {"$in": ["queued", "claimed"]}},
            {"$set": {"status": "cancelled", "error_code": "erasure_requested", "updated_at": now}, "$unset": {"binding": ""}})
        await current.outreach_voice_studio_jobs.update_many({**scope, 'status': {'$in': ['queued', 'preparing']}},
            {'$set': {'status': 'cancelled', 'error_code': 'erasure_requested', 'updated_at': now}})
        await current.outreach_webhooks.update_many(scope, {"$set": {"active": False}})
        await current.outreach_integrations.update_many(scope, {"$set": {"status": "disconnected", "active": False}})
        await current.outreach_webhook_deliveries.update_many({**scope, "status": {"$in": ["pending", "retry", "retrying"]}}, {
            "$set": {"status": "cancelled"}})
        # Inventory is not a SuppressionCollection: its tenant identity is sticky ownership.
        await self.db.outreach_proxy_inventory.update_many(_scope("outreach_proxy_inventory", workspace), {
            "$unset": dict.fromkeys(("password_enc", "username", "username_enc", "proxy_url_enc", "credentials_enc"), ""),
            "$set": {"status": "erasure_hold"}}, session=current.session)

    async def inspect(self, workspace: str) -> dict:
        """Return counts/digests only; never return credentials or recipient content."""
        request = await self.db.outreach_erasure_requests.find_one(guard_scope(workspace))
        if not request:
            raise ValueError("Request workspace deletion before inspection")
        records = await self._snapshot(workspace)
        holds = await self.db.outreach_erasure_holds.find({"workspace_id": workspace}).to_list(length=INSPECTION_LIMIT)
        return {"workspace_id": workspace, "status": request["status"],
            "review_digest": self._digest(workspace, request, records),
            "counts": {name: len(rows) for name, rows in records.items() if rows},
            "holds": [{key: row[key] for key in ("_id", "kind", "source_collection", "state", "expires_at") if key in row} for row in holds]}

    async def _archive(self, current: SuppressionDatabase, name: str, workspace: str, row: dict) -> None:
        kind = None
        if name == "outreach_proxy_inventory":
            kind = "provider_term"
        elif name in {"outreach_payment_receipts", "outreach_entitlements"}:
            kind = "financial_reference"
            if name == "outreach_payment_receipts":
                from outreach.core.paid_access import claim_invoice_reference
                await claim_invoice_reference(self.db, str(row["_id"]), workspace, row["seats"], row["paid_through"], session=current.session)
        elif name == 'outreach_mailboxes' and row.get('refresh_state') in {'possible', 'unknown'}:
            kind = 'unresolved_submission'
        elif name == 'outreach_mailbox_connection_jobs' and (
                row.get('exchange_state') in {'possible', 'unknown'} or row.get('status') in {'running', 'review_required'}):
            kind = 'unresolved_submission'
        elif name == 'outreach_mailbox_connection_jobs' and row.get('exchange_state') == 'installed':
            kind = 'submission_receipt'
        elif name == 'outreach_mailbox_sync_reads' and row.get('status') in {'possible', 'read_interrupted', 'received'}:
            kind = 'submission_receipt' if row['status'] == 'received' else 'unresolved_submission'
        elif name == 'outreach_voices' and row.get('elevenlabs_voice_id'):
            kind = 'remote_voice_cleanup'
        elif name == 'outreach_voice_source_migrations' and row.get('provenance') == 'same_key_continuity':
            kind = 'voice_source_continuity'
        elif name == 'outreach_voice_vendor_reads':
            kind = 'unresolved_submission' if row.get('status') in {'possible', 'read_interrupted'} else 'voice_vendor_evidence'
        elif name == 'outreach_voice_studio_jobs' and row.get('receipt'):
            kind = 'submission_receipt'
        elif name == 'outreach_webhook_deliveries':
            if row.get('status') in {'possible', 'review_required', 'held_received'}:
                kind = 'unresolved_submission'
            elif row.get('receipt'):
                kind = 'submission_receipt'
        elif name == 'outreach_integration_reviews':
            kind = 'unresolved_submission' if row.get('outcome_at_review') == 'unknown' else 'integration_review'
        elif name == 'outreach_integration_controls':
            kind = 'integration_resource_stop'
        elif name == 'outreach_execution_epochs':
            kind = 'restore_epoch_provenance'
        elif name == 'outreach_restore_exclusions':
            kind = 'restore_exclusion_provenance'
        elif name == 'outreach_restore_invoices':
            kind = 'restore_invoice_provenance'
        elif name == 'outreach_restore_proxy_exclusions':
            kind = 'restore_proxy_exclusion_provenance'
        elif name == 'outreach_restore_reply_stops':
            kind = 'restore_reply_stop_provenance'
        elif name == 'outreach_restore_suppressions':
            kind = 'restore_suppression_provenance'
        elif name == 'outreach_health_controls':
            kind = 'execution_health_control'
        elif name == 'outreach_credential_migrations' and row.get('kind') == 'integration':
            kind = 'integration_custody_migration'
        elif name == 'outreach_credential_migrations' and row.get('kind') == 'proxy':
            kind = 'proxy_custody_migration'
        elif name == 'outreach_credential_migrations' and row.get('kind') == 'voice_artifact':
            kind = 'voice_artifact_custody_migration'
        elif name == 'outreach_credential_migrations' and row.get('kind') == 'voice_studio_result':
            kind = 'voice_studio_result_custody_migration'
        elif name == 'outreach_credential_migrations' and row.get('kind') == 'voice_studio_input_stop':
            kind = 'voice_studio_input_stop'
        elif name == 'outreach_proxy_lifecycle_reviews':
            kind = 'proxy_lifecycle_review'
        elif name == 'outreach_proxy_adoptions':
            kind = 'proxy_legacy_adoption'
        elif name == 'outreach_voice_studio_jobs' and (row.get('review') or {}).get('outcome_at_review') == 'unknown':
            kind = 'unresolved_submission'
        elif name in LEDGERS:
            status = row.get("status")
            if status == "response_received":
                kind = "submission_receipt"
            elif (status in AMBIGUOUS
                    or row.get("finalization_prepared") and status not in {"completed", "repaired_stopped"}
                    or any(stage.get("status") == "possible_submission" for stage in (row.get("stages") or {}).values())):
                kind = "unresolved_submission"
            elif name == "outreach_connection_jobs" and status in {"completed", "repaired_stopped"} and (
                    row.get("connection_cleanup_complete") is False
                    or row.get("repair") and not row.get("repair_cleanup_complete")):
                kind = "connection_cleanup"
        if not kind:
            return
        identity = canonical_hash([workspace, name, str(row["_id"])])
        hold = {"_id": identity, "workspace_id": workspace, "kind": kind, "source_collection": name,
            "record_id_hash": canonical_hash(str(row["_id"])), "record_digest": canonical_hash(row),
            "state": "held", "retained_at": datetime.now(timezone.utc)}
        if kind == "provider_term":
            hold.update({"asset_id": row["_id"], "expires_at": _utc(row.get("expires_at"))})
        if kind == 'restore_epoch_provenance':
            hold.update({key: row.get(key) for key in ('execution_epoch', 'before_digest', 'after_digest',
                'evidence_digest', 'review_digest', 'prepared_at', 'version')})
            hold.update({'operator_digest': canonical_hash(row.get('operator')), 'activation_allowed': False})
        if kind == 'restore_invoice_provenance':
            hold.update({key: row.get(key) for key in ('execution_epoch', 'source_digest', 'evidence_digest',
                'review_digest', 'facts_digest', 'invoice_count', 'operator_digest', 'applied_at', 'version')})
            hold.update({'activation_allowed': False, 'payment_restored': False})
        if kind == 'restore_proxy_exclusion_provenance':
            hold.update({key: row.get(key) for key in ('execution_epoch', 'source_digest', 'evidence_digest',
                'review_digest', 'facts_digest', 'ip_count', 'operator_digest', 'applied_at', 'version')})
            hold.update({'activation_allowed': False, 'assets_restored': False})
        if kind == 'restore_exclusion_provenance':
            hold.update({key: row.get(key) for key in ('execution_epoch', 'source_digest', 'evidence_digest',
                'review_digest', 'identity_set_digest', 'facts_digest', 'identity_count', 'operator_digest', 'applied_at', 'version')})
            hold.update({'activation_allowed': False, 'purged': False})
        if kind in {'restore_suppression_provenance', 'restore_reply_stop_provenance'}:
            hold.update({key: row.get(key) for key in ('execution_epoch', 'source_digest', 'evidence_digest',
                'review_digest', 'facts_digest', 'fact_count', 'operator_digest', 'applied_at', 'version')})
            hold.update({'activation_allowed': False, 'reply_history_restored': False})
        if kind == 'execution_health_control':
            hold.update({key: row.get(key) for key in ('provenance', 'operator_digest', 'evidence_digest',
                'arm_digest', 'policy_digest', 'created_at', 'expires_at', 'stopped_at', 'stop_reason',
                'stop_operator_digest', 'stop_evidence_digest', 'renewals')})
            hold.update({'sender_digest': canonical_hash(row.get('sender_id')),
                'generation_digest': canonical_hash(row.get('generation')), 'outcome_state': row.get('status'),
                'activation_allowed': False})
        if kind == 'proxy_legacy_adoption':
            hold.update({key: row.get(key) for key in ('provenance', 'before_digest', 'after_digest',
                'source_digest', 'adopted_basis_digest', 'operator_digest', 'evidence_digest',
                'original_evidence_digest', 'original_order_digest', 'original_operator_digest',
                'original_verified_at', 'provider_term_expires_at', 'target_policy_digest',
                'generation_digest', 'generation_created', 'at')})
            hold.update({'asset_id_digest': canonical_hash(row.get('proxy_id')),
                'operation_kind': 'proxy_legacy_adoption', 'activation_allowed': False})
        if kind == 'proxy_custody_migration':
            hold.update({key: row.get(key) for key in ('provenance', 'before_digest', 'after_digest',
                'target_policy_digest', 'generation_digest', 'original_basis_digest', 'at', 'evidence_digest')})
            hold.update({'operator_digest': row.get('operator_digest') or canonical_hash(row.get('operator')),
                'asset_id_digest': canonical_hash(row.get('proxy_id')), 'operation_kind': 'proxy_custody_migration',
                'activation_allowed': False})
        if kind == 'voice_artifact_custody_migration':
            hold.update({key: row.get(key) for key in ('provenance', 'before_digest', 'after_digest',
                'original_record_digest', 'original_job_digest', 'audio_digest', 'generation_digest',
                'target_policy_digest', 'operator_digest', 'evidence_digest', 'prepared_at', 'expires_at', 'at')})
            hold.update({'artifact_id_digest': canonical_hash(row.get('artifact_id')),
                'operation_kind': 'voice_artifact_custody_migration', 'activation_allowed': False})
        if kind == 'voice_studio_result_custody_migration':
            hold.update({key: row.get(key) for key in ('provenance', 'before_digest', 'after_digest',
                'original_job_digest', 'audio_digest', 'generation_digest', 'target_policy_digest',
                'operator_digest', 'evidence_digest', 'received_at', 'expires_at', 'at')})
            hold.update({'job_id_digest': canonical_hash(row.get('job_id')),
                'operation_kind': 'voice_studio_result_custody_migration', 'activation_allowed': False})
        if kind == 'voice_studio_input_stop':
            hold.update({key: row.get(key) for key in ('provenance', 'before_digest', 'after_digest',
                'original_job_digest', 'original_profile_digest', 'original_status', 'operation',
                'owner_digest', 'input_digest', 'consent_digest', 'policy_digest', 'operator_digest',
                'evidence_digest', 'at')})
            hold.update({'job_id_digest': canonical_hash(row.get('job_id')),
                'operation_kind': 'voice_studio_input_stop', 'activation_allowed': False})
        if kind == 'proxy_lifecycle_review':
            hold.update({key: row.get(key) for key in ('provenance', 'operation', 'revision',
                'root_import_basis_digest', 'after_basis_digest', 'previous_review_digest', 'before_digest',
                'after_digest', 'target_policy_digest', 'operator_digest', 'evidence_digest',
                'provider_reference_digest', 'generation_digest', 'before_expires_at', 'after_expires_at', 'at')})
            hold.update({'asset_id_digest': canonical_hash(row.get('proxy_id')),
                'operation_kind': 'proxy_lifecycle_review', 'activation_allowed': False})
        if kind == 'voice_source_continuity':
            hold.update({key: row.get(key) for key in ('provenance', 'before_source', 'after_source',
                'root_clone_digest', 'clone_source', 'remote_digest', 'review_digest', 'after_digest', 'at')})
            hold.update({'operator_digest': canonical_hash(row.get('operator')),
                'evidence_digest': canonical_hash(row.get('evidence')), 'activation_allowed': False})
        if name == 'outreach_voice_vendor_reads':
            hold.update({key: row.get(key) for key in ('provider_source_digest', 'configuration_digest',
                'root_clone_digest', 'profile_digest', 'receipt_digest', 'inspection_digest',
                'operator_digest', 'evidence_digest', 'possible_at')})
            release = row.get('release') or {}
            hold.update({'operation_kind': 'voice_metadata_read', 'mutation': False,
                'outcome_state': row.get('status'), 'remote_digest': canonical_hash(row.get('provider_voice_id')),
                'received_at': (row.get('receipt') or {}).get('received_at'), 'activation_allowed': False,
                'release_digest': canonical_hash(release) if release else None,
                'release_provenance': release.get('provenance'), 'released_at': release.get('at')})
        if name == 'outreach_webhook_deliveries':
            hold.update({'operation_kind': 'integration_delivery', 'outcome_state': row.get('status'),
                'destination_digest': canonical_hash([row.get('destination_type'), row.get('destination_id')]),
                'credential_digest': row.get('credential_digest') or canonical_hash([row.get('secret_enc'), row.get('target_url_enc')]),
                'protocol_version': row.get('custody_protocol_version'), 'receipt_digest': row.get('receipt_digest'),
                'possible_at': row.get('possible_at'), 'received_at': (row.get('receipt') or {}).get('received_at'),
                'activation_allowed': False})
        if name in {'outreach_integration_reviews', 'outreach_integration_controls', 'outreach_credential_migrations'} and kind in {
                'unresolved_submission', 'integration_review', 'integration_resource_stop', 'integration_custody_migration'}:
            hold.update({key: row.get(key) for key in ('provenance', 'outcome_at_review', 'original_status',
                'original_owner_digest', 'credential_digest', 'receipt_digest', 'possible_at', 'received_at',
                'inspection_digest', 'before_digest', 'after_digest', 'target_policy_digest', 'generation_digest', 'at')})
            hold.update({'operation_kind': 'integration_review' if name == 'outreach_integration_reviews'
                else 'integration_resource_stop' if name == 'outreach_integration_controls'
                else 'integration_custody_migration', 'activation_allowed': False})
        if name in LEDGERS:
            status = row.get("status")
            outcome = (row.get("provider_outcome") or {}).get("status")
            hold["outcome_state"] = (outcome if kind == "submission_receipt" and outcome in {
                "accepted", "found", "not_found", "rejected"} else status if status in AMBIGUOUS | {
                "response_received", "completed", "repaired_stopped"} else "unresolved")
            hold["mutation"] = bool(row.get("mutation"))
        if name == 'outreach_mailboxes':
            hold.update({'operation_kind': 'oauth_refresh', 'outcome_state': row['refresh_state'], 'mutation': True})
        if name == 'outreach_mailbox_connection_jobs':
            hold.update({'operation_kind': 'oauth_exchange', 'outcome_state':
                row.get('exchange_state') if row.get('exchange_state') in {'possible', 'unknown', 'installed'} else 'unresolved', 'mutation': True})
        if name == 'outreach_mailbox_sync_reads':
            hold.update({'operation_kind': 'mailbox_read', 'outcome_state': row['status'], 'mutation': False})
        if name in {'outreach_voice_studio_jobs', 'outreach_voices'}:
            remote = (row.get('receipt') or {}).get('voice_id') or row.get('elevenlabs_voice_id') or row.get('provider_voice_id')
            hold.update({'operation_kind': row.get('operation', 'remote_voice_cleanup'),
                'provider_voice_id': remote, 'provider_source_digest': row.get('provider_source_digest'),
                'received_at': (row.get('receipt') or {}).get('received_at')})
            review = row.get('review') or {}
            if review.get('provenance') in {'operator_local_stop', 'saved_provider_receipt'}:
                hold.update({'review_provenance': review['provenance'], 'review_decision': review.get('decision'),
                    'reviewed_at': review.get('at'), 'review_digest': review.get('review_digest'),
                    'original_outcome': review.get('outcome_at_review'),
                    'operator_digest': canonical_hash(review.get('operator')), 'evidence_digest': canonical_hash(review.get('evidence')),
                    'original_owner_digest': canonical_hash(row.get('owner')), 'payload_digest': row.get('payload_digest')})
        await current.outreach_erasure_holds.update_one({"_id": identity, "workspace_id": workspace}, {"$setOnInsert": hold}, upsert=True)

    async def _erase_batch(self, current: SuppressionDatabase, workspace: str, name: str) -> bool:
        scope = _scope(name, workspace)
        if name in PERSISTENT:
            scope = {**scope, "erasure_sanitized_at": {"$exists": False}}
        collection = self.db[name] if name == "outreach_proxy_inventory" else current[name]
        options = {"session": current.session} if name == "outreach_proxy_inventory" else {}
        rows = await collection.find(scope, **options).limit(BATCH_SIZE).to_list(length=BATCH_SIZE)
        for row in rows:
            await self._archive(current, name, workspace, row)
            identity = {**_scope(name, workspace), "_id": row["_id"]}
            if name in PERSISTENT:
                fields = ("provider", "provider_order_id", "country_code", "expires_at", "last_workspace_id", "sender_id", "proxy_id")
                replacement = {key: row[key] for key in fields if key in row}
                replacement.update({"_id": row["_id"], "workspace_id": workspace, "status": "erasure_hold", "erasure_sanitized_at": datetime.now(timezone.utc)})
                await collection.replace_one(identity, replacement, **options)
            else:
                await collection.delete_one(identity)
        return len(rows) < BATCH_SIZE

    async def finish(self, workspace: str, operator: str, evidence: str, *, workers_drained: bool,
                     expected_digest: str) -> dict:
        """Private drained cleanup, resumable after a batch abort or process loss."""
        if not workers_drained or not operator.strip() or not 20 <= len(evidence.strip()) <= 2000:
            raise ValueError("Drain all workspace writers and provide operator evidence")
        scope = guard_scope(workspace)
        async def review(current):
            request = await current.outreach_erasure_requests.find_one(scope)
            if not request:
                raise ValueError("Workspace deletion was not requested")
            records = await self._snapshot(workspace, current)
            if self._digest(workspace, request, records) != expected_digest:
                raise ValueError("Erasure inspection changed; inspect and drain again")
            if request["status"] == "erased" and not self._has_mutable_data(records):
                return request
            # A fresh drain/review can revisit a previously completed collection
            # after an older admitted writer or interrupted batch wrote again.
            await current.outreach_erasure_requests.update_one(scope, {"$set": {"status": "purging", "completed_collections": []}, "$push": {"reviews": {
                "operator_hash": canonical_hash(operator.strip()), "evidence_hash": canonical_hash(evidence.strip()),
                "review_digest": expected_digest, "workers_drained": True, "at": datetime.now(timezone.utc)}}})
            return {**request, "status": "purging"}
        request = await _control(self.db, workspace, review)
        if request["status"] == "erased":
            return {"workspace_id": workspace, "status": "erased"}
        for name in DATA_COLLECTIONS:
            async def batch(current):
                saved = await current.outreach_erasure_requests.find_one(scope)
                if name in saved["completed_collections"]:
                    return True
                done = await self._erase_batch(current, workspace, name)
                if done:
                    await current.outreach_erasure_requests.update_one(scope, {"$addToSet": {"completed_collections": name}})
                return done
            while not await _control(self.db, workspace, batch):
                pass
        async def complete(current):
            records = await self._snapshot(workspace, current)
            if any(rows for name, rows in records.items() if name not in PERSISTENT) or any(
                    not row.get("erasure_sanitized_at") for name in PERSISTENT for row in records.get(name, [])):
                raise ValueError("Workspace writers changed after drain; cleanup is incomplete")
            now = datetime.now(timezone.utc)
            await current.outreach_suppression_guards.update_one(scope, {"$set": {"erasure_state": "erased", "erasure_completed_at": now}})
            await current.outreach_erasure_requests.update_one(scope, {"$set": {"status": "erased", "completed_at": now}})
            return {"workspace_id": workspace, "status": "erased"}
        return await _control(self.db, workspace, complete)

    async def inspect_hold(self, workspace: str, hold_id: str) -> dict:
        """Inspect one minimal retained record without disclosing original data."""
        row = await self.db.outreach_erasure_holds.find_one({"_id": hold_id, "workspace_id": workspace})
        if not row:
            raise ValueError("Retained erasure record was not found")
        return {"hold_id": hold_id, "kind": row["kind"], "state": row["state"],
            "expires_at": row.get("expires_at"), "review_digest": canonical_hash(row)}

    async def release_hold(self, workspace: str, hold_id: str, operator: str, evidence: str,
                           *, expected_digest: str) -> dict:
        """Explicit retention review removes evidence; it never resolves or replays an action."""
        if not operator.strip() or not 20 <= len(evidence.strip()) <= 2000:
            raise ValueError("Retention review needs an identified operator and evidence")
        async def release(current):
            request = await current.outreach_erasure_requests.find_one(guard_scope(workspace))
            if not request or request["status"] != "erased":
                raise ValueError("Finish workspace erasure before retention review")
            scope = {"_id": hold_id, "workspace_id": workspace}
            row = await current.outreach_erasure_holds.find_one(scope)
            if not row or canonical_hash(row) != expected_digest:
                raise ValueError("Retention inspection changed or record was removed")
            now = datetime.now(timezone.utc)
            if row["kind"] == "provider_term":
                expiry = _utc(row.get("expires_at"))
                if not expiry or expiry > now:
                    raise ValueError("Provider term has not ended or remains unverified")
                asset_scope = {"_id": row["asset_id"], **_scope("outreach_proxy_inventory", workspace)}
                asset = await self.db.outreach_proxy_inventory.find_one(asset_scope, session=current.session)
                if not asset:
                    raise ValueError("Current provider ownership remains unverified")
                current_expiry = _utc(asset.get("expires_at"))
                if not current_expiry or current_expiry > now:
                    raise ValueError("Current provider term has not ended")
                await self.db.outreach_proxy_inventory.update_one(asset_scope,
                    {"$set": {"status": "retired", "erasure_retention_reviewed_at": now}}, session=current.session)
                await current.outreach_proxy_leases.delete_one({"workspace_id": workspace, "_id": row["asset_id"]})
            await current.outreach_erasure_requests.update_one(guard_scope(workspace), {"$push": {"retention_reviews": {
                "hold_id": hold_id, "kind": row["kind"], "operator_hash": canonical_hash(operator.strip()),
                "evidence_hash": canonical_hash(evidence.strip()), "review_digest": expected_digest, "at": now}}})
            await current.outreach_erasure_holds.delete_one(scope)
            return {"workspace_id": workspace, "status": "retention_record_removed"}
        return await _control(self.db, workspace, release)


async def begin_user_erasure(db: AsyncIOMotorDatabase, user_id: str) -> dict:
    """Resolve all owned tenants; an active shared workspace confers no ownership."""
    user = await db.users.find_one({"user_id": user_id}) or {}
    if user:
        await db.users.update_one({"user_id": user_id}, {"$set": {"status": "deletion_pending"}})
        await stop_identity(db, user.get("firebase_uid"))
    owned = await db.workspaces.find({"owner_id": user_id}).limit(1001).to_list(length=1001)
    if len(owned) > 1000:
        raise ValueError("Owned workspace manifest exceeds bounded inspection capacity")
    workspaces = set(user.get("deletion_owned_workspace_ids", []))
    workspaces.update(row["workspace_id"] for row in owned)
    # Older prompt/voice APIs used the authenticated user's ID as a personal
    # tenant, or stored user-owned rows without a tenant. Adopt only that
    # proven personal scope; a same-named workspace owned by someone else denies.
    legacy_names = []
    private_scope = {"user_id": user_id, "$or": [{"workspace_id": {"$exists": False}}, {"workspace_id": None}]}
    for name in await db.list_collection_names():
        if name.startswith("outreach_") and name not in CONTROLS and (
                await db[name].find_one({"workspace_id": user_id}) or await db[name].find_one(private_scope)):
            legacy_names.append(name)
    if legacy_names:
        existing = await db.workspaces.find_one({"workspace_id": user_id})
        if existing and existing.get("owner_id") != user_id:
            raise ValueError("Legacy personal scope ownership requires review")
        if not user:
            raise ValueError("Legacy personal scope owner is unavailable")
        async def adopt(current):
            for name in legacy_names:
                await db[name].update_many(private_scope, {"$set": {"workspace_id": user_id}}, session=current.session)
        await _control(db, user_id, adopt)
        workspaces.add(user_id)
    await db.users.update_one({"user_id": user_id}, {"$set": {
        "deletion_owned_workspace_ids": sorted(workspaces), "status": "deletion_pending"}})
    pending = []
    service = OutreachErasure(db)
    for workspace in sorted(workspaces):
        if (await service.request(workspace, user_id))["status"] != "erased":
            pending.append(workspace)
    return {"owned_workspace_ids": sorted(workspaces), "pending": pending}
