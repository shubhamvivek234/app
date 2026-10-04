"""Private drained Fernet-to-scoped custody migration; never grants execution."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from outreach.core import suppression
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.inbox_freshness import credential_generation
from outreach.core.session_custody import seal_installed, custody_mode
from outreach.core.paid_access import live_actions_enabled
from outreach.core.sender_execution import SenderExecution
from utils.encryption import decrypt_strict


def _stable(row: dict | None) -> dict | None:
    return {key: value for key, value in row.items() if key != "dispatch_fence_revision"} if row else None


def _material(row: dict) -> str:
    return canonical_hash({key: row.get(key) for key in ("workspace_id", "id", "credential_generation",
        "session_cookie_enc", "jsession_id", "li_a_enc", "encrypted_session_cookie", "li_at_enc", "jsession_id_enc")})


class CredentialMigration:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    async def _snapshot(self, current, workspace: str, sender: str) -> dict:
        account = await current.outreach_accounts.find_one({"workspace_id": workspace, "id": sender})
        execution = await current.outreach_sender_execution.find_one(SenderExecution.scope(workspace, sender))
        campaigns = await current.outreach_campaigns.find({"workspace_id": workspace, "sender_account_ids": sender,
            "status": {"$in": ["active", "warming_up"]}}).sort("_id", 1).limit(1).to_list(length=1)
        physical = await current.outreach_physical_requests.find_one({"workspace_id": workspace, "sender_id": sender,
            "status": {"$in": ["preparing", "in_flight", "unknown_outcome"]}})
        lock = await current.outreach_connection_locks.find_one({"workspace_id": workspace, "_id": sender})
        job = await current.outreach_connection_jobs.find_one({"workspace_id": workspace, "sender_id": sender,
            "status": {"$in": ["queued", "running", "finalizing", "repairing"]}})
        return {"account": _stable(account), "execution": _stable(execution),
            "campaigns": [_stable(row) for row in campaigns], "physical": _stable(physical), "lock": _stable(lock), "job": _stable(job)}

    @staticmethod
    def _blockers(snapshot: dict) -> list[str]:
        account, execution = snapshot["account"] or {}, snapshot["execution"] or {}
        permission = execution.get("permission") or {}
        blockers = []
        if not account or account.get("is_deleted") or account.get("status") not in {"paused", "reauth_required", "disconnected"}:
            blockers.append("sender_not_stopped")
        if (not execution or execution.get("status") != "idle" or execution.get("owner_token")
                or execution.get("physical_request_token") or permission.get("latched") is not True):
            blockers.append("execution_not_stopped")
        if (account.get("connection_finalization") or {}).get("state") in {"prepared", "installed"}:
            blockers.append("installation_unfinished")
        blockers.extend(name + "_unfinished" for name in ("campaigns", "physical", "lock", "job") if snapshot[name])
        return blockers

    async def inspect(self, workspace: str, sender: str) -> dict:
        snapshot = await self._snapshot(self.db, workspace, sender)
        return {"workspace_id": workspace, "sender_id": sender, "digest": canonical_hash(snapshot),
            "generation": credential_generation(snapshot["account"] or {}), "blockers": self._blockers(snapshot)}

    async def migrate(self, workspace: str, sender: str, operator: str, expected_digest: str, *, workers_drained: bool = False) -> dict:
        if (workers_drained is not True or not operator or not operator.strip() or not expected_digest
                or live_actions_enabled() or custody_mode() != "kms_v1"):
            raise CustodyUnavailable("Stopped execution and identified drained migration are required")
        key = canonical_hash(["credential-migration-v1", workspace, sender, expected_digest])
        scope = {"_id": key, "workspace_id": workspace}
        receipt = await self.db.outreach_credential_migrations.find_one(scope)
        if receipt:
            current = await self.db.outreach_accounts.find_one({"workspace_id": workspace, "id": sender})
            return {"status": "completed", "migration_id": key,
                "current_matches": bool(current and _material(current) == receipt["after_digest"])}
        async def verify(current):
            fenced = (AuthorityDatabase(current.database, current.session, key)
                if isinstance(current, suppression.SuppressionDatabase) else current)
            snapshot = await self._snapshot(fenced, workspace, sender)
            if canonical_hash(snapshot) != expected_digest or self._blockers(snapshot):
                raise CustodyUnavailable("Drained credential inspection changed")
            return snapshot
        snapshot = await suppression.mutate_suppression(self.db, workspace, verify)
        account = snapshot["account"]
        try:
            raw = {"li_at": decrypt_strict(account.get("session_cookie_enc") or account.get("encrypted_session_cookie") or account.get("li_at_enc") or ""),
                "jsession_id": decrypt_strict(account.get("jsession_id") or account.get("jsession_id_enc") or ""),
                "li_a": decrypt_strict(account["li_a_enc"]) if account.get("li_a_enc") else ""}
        except (ValueError, OSError):
            raise CustodyUnavailable("Legacy credentials require reconnection or separate provenance review") from None
        generation = credential_generation(account)
        # All KMS/STS work finishes outside the snapshot callback. A transaction
        # retry reuses these ciphertexts and never repeats key-service calls.
        encrypted = await seal_installed(raw, workspace, sender, generation)
        del raw
        async def apply(current):
            fenced = (AuthorityDatabase(current.database, current.session, key)
                if isinstance(current, suppression.SuppressionDatabase) else current)
            existing = await current.outreach_credential_migrations.find_one(scope)
            if existing:
                saved = await current.outreach_accounts.find_one({"workspace_id": workspace, "id": sender})
                return {"status": "completed", "migration_id": key,
                    "current_matches": bool(saved and _material(saved) == existing["after_digest"])}
            fresh = await self._snapshot(fenced, workspace, sender)
            if canonical_hash(fresh) != expected_digest or self._blockers(fresh) or live_actions_enabled():
                raise CustodyUnavailable("Drained credential inspection changed")
            updates = {**encrypted, "credential_generation": generation, "inbox_sync": {"status": "required"},
                "credential_custody_version": 1}
            changed = await current.outreach_accounts.update_one({"workspace_id": workspace, "id": sender,
                **{field: account[field] if field in account else {"$exists": False} for field in (
                    "credential_generation", "session_cookie_enc", "encrypted_session_cookie", "jsession_id", "li_a_enc", "li_at_enc", "jsession_id_enc")}},
                {"$set": updates, "$unset": {"encrypted_session_cookie": "", "li_at_enc": "", "jsession_id_enc": ""}})
            if changed.matched_count != 1:
                raise CustodyUnavailable("Credential migration owner changed")
            after = {**account, **updates}
            for field in ("encrypted_session_cookie", "li_at_enc", "jsession_id_enc"): after.pop(field, None)
            await current.outreach_credential_migrations.insert_one({**scope, "sender_id": sender, "status": "completed",
                "operator": operator.strip(), "workers_drained": True, "before_digest": expected_digest,
                "after_digest": _material(after), "generation": generation, "at": datetime.now(timezone.utc),
                "target_environment_digest": canonical_hash(os.getenv("OUTREACH_CUSTODY_ENVIRONMENT_ID", ""))})
            return {"status": "completed", "migration_id": key, "current_matches": True}
        return await suppression.mutate_suppression(self.db, workspace, apply)
