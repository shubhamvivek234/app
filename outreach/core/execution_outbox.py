"""Atomic intent + embedded physical attempt, retaining the legacy send boundary.

Publishing/re-running a worker is safe; only an unsubmitted current owner can
cross the durable submission boundary. Expiry never authorizes re-submission.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import uuid
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from outreach.core.authorization import canonical_hash
from outreach.models import ActionAttempt, ActionIntent

CLAIM_SECONDS = 120


class ExecutionOutbox:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    async def ensure(self, *, workspace_id: str, campaign_id: str, lead_id: str, sender_id: str,
                     node_id: str, action_kind: str, sequence_version: int, authorization_revision: int,
                     credential_generation: str, legacy_operation_id: str, enrollment_id: str | None = None,
                     now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        enrollment_id = enrollment_id or f"legacy:{lead_id}"
        key = canonical_hash([workspace_id, enrollment_id, sequence_version, node_id, action_kind])
        existing = await self.db.outreach_intents.find_one({"_id": key, "workspace_id": workspace_id})
        if isinstance(existing, dict):
            # Explicit campaign reauthorization can refresh only an action
            # that has no possibly submitted attempt and no current owner.
            await self.db.outreach_intents.update_one(
                {"_id": key, "workspace_id": workspace_id, "attempt": None,
                 "authorization_revision": {"$lte": authorization_revision}, "$or": [
                     {"status": "pending"}, {"status": "claimed", "claim_expires_at": {"$lte": now}},
                 ]},
                {"$set": {"authorization_revision": authorization_revision,
                          "credential_generation": credential_generation, "sender_id": sender_id}},
            )
            return await self.db.outreach_intents.find_one({"_id": key, "workspace_id": workspace_id})
        legacy = await self.db.outreach_tasks.find_one({"id": legacy_operation_id, "workspace_id": workspace_id})
        legacy_status = legacy.get("status") if isinstance(legacy, dict) else None
        status = ("executed" if legacy_status in {"completed", "accepted", "skipped"} else
                  "unknown_outcome" if legacy_status in {"dispatching", "uncertain", "resolving"} else
                  "canceled" if legacy_status in {"failed", "not_sent_stopped", "cancelled"} else "pending")
        doc = ActionIntent(
            id=key, workspace_id=workspace_id, campaign_id=campaign_id, lead_id=lead_id,
            enrollment_id=enrollment_id, sequence_version=sequence_version, node_id=node_id,
            action_kind=action_kind, logical_dedup_key=key, legacy_operation_id=legacy_operation_id,
            authorization_revision=authorization_revision, credential_generation=credential_generation,
            status=status, next_action_due_at=now,
        ).model_dump()
        doc["_id"] = doc.pop("id")
        doc["sender_id"] = sender_id
        doc["created_at"] = now
        doc["updated_at"] = now
        try:
            await self.db.outreach_intents.insert_one(doc)
        except DuplicateKeyError:
            current = await self.db.outreach_intents.find_one({"_id": key, "workspace_id": workspace_id})
            if not isinstance(current, dict):
                raise
            return current
        return doc

    async def claim(self, workspace_id: str, intent_id: str, owner: str, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        claimed = await self.db.outreach_intents.find_one_and_update(
            {"_id": intent_id, "workspace_id": workspace_id, "attempt": None,
             "next_action_due_at": {"$lte": now}, "$or": [
                 {"status": "pending"}, {"status": "claimed", "claim_expires_at": {"$lte": now}},
             ]},
            {"$set": {"status": "claimed", "claim_token": owner,
                      "claim_expires_at": now + timedelta(seconds=CLAIM_SECONDS), "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return isinstance(claimed, dict)

    async def begin_submission(self, workspace_id: str, intent_id: str, owner: str, *,
                               content_hash: str | None = None, now: datetime | None = None,
                               expected: dict | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        current = await self.db.outreach_intents.find_one({"_id": intent_id, "workspace_id": workspace_id})
        if not isinstance(current, dict):
            return False
        attempt = ActionAttempt(sender_id=current["sender_id"], owner_token=owner, possible_submission_at=now).model_dump()
        if current.get('action_kind') == 'connection_request':
            attempt['invite_contract_version'] = 1
        changed = await self.db.outreach_intents.update_one(
            {"_id": intent_id, "workspace_id": workspace_id, "status": "claimed", "claim_token": owner,
             "claim_expires_at": {"$gt": now}, "attempt": None,
             **({"authorization_revision": expected["revision"], "credential_generation": expected["credential_generation"],
                 "sender_id": expected["sender_id"]} if expected else {})},
            {"$set": {"status": "in_flight", "attempt": attempt, "content_hash": content_hash, "updated_at": now}},
        )
        return changed.matched_count == 1

    async def defer(self, workspace_id: str, intent_id: str, owner: str, reason: str, *,
                    now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        changed = await self.db.outreach_intents.update_one(
            {"_id": intent_id, "workspace_id": workspace_id, "status": "claimed", "claim_token": owner, "attempt": None},
            {"$set": {"status": "pending", "defer_reason": reason[:100],
                      "next_action_due_at": now + timedelta(minutes=5), "updated_at": now},
             "$unset": {"claim_token": "", "claim_expires_at": ""}},
        )
        return changed.matched_count == 1

    async def finish(self, workspace_id: str, intent_id: str, owner: str, outcome: str, *,
                     provider_message_id: str | None = None, provider_thread_id: str | None = None,
                     provider_result_status: str | None = None,
                     provider_recipient_urn: str | None = None, provider_request_id: str | None = None,
                     now: datetime | None = None) -> bool:
        if outcome not in {"provider_accepted", "request_observed", "unknown_outcome", "failed"}:
            raise ValueError("Invalid execution outcome")
        now = now or datetime.now(timezone.utc)
        status = "executed" if outcome in {"provider_accepted", "request_observed"} else outcome
        changed = await self.db.outreach_intents.update_one(
            {"_id": intent_id, "workspace_id": workspace_id, "claim_token": owner, "status": "in_flight"},
            {"$set": {"status": status, "attempt.outcome": outcome, "attempt.completed_at": now,
                      "attempt.provider_message_id": provider_message_id,
                      "attempt.provider_thread_id": provider_thread_id,
                      "attempt.provider_result_status": provider_result_status,
                      **({'attempt.provider_recipient_urn': provider_recipient_urn,
                          'attempt.provider_request_id': provider_request_id,
                          'attempt.invite_contract_version': 1} if provider_recipient_urn and provider_request_id else {}),
                      "updated_at": now}},
        )
        return changed.matched_count == 1

    async def abort_before_call(self, workspace_id: str, intent_id: str, owner: str, reason: str) -> bool:
        """Only the current worker, before invoking transport, can prove no call."""
        scope = {"_id": intent_id, "workspace_id": workspace_id, "status": "in_flight", "claim_token": owner}
        current = await self.db.outreach_intents.find_one(scope)
        if not isinstance(current, dict) or not isinstance(current.get("attempt"), dict):
            return False
        now = datetime.now(timezone.utc)
        evidence = {**current["attempt"], "outcome": "not_submitted", "completed_at": now}
        changed = await self.db.outreach_intents.update_one(
            scope, {"$set": {"status": "pending", "attempt": None, "defer_reason": reason,
                             "next_action_due_at": now + timedelta(minutes=5), "updated_at": now},
                    "$push": {"attempt_history": evidence}, "$unset": {"claim_token": "", "claim_expires_at": ""}},
        )
        return changed.matched_count == 1

    async def quarantine_expired(self, workspace_id: str, intent_id: str, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        changed = await self.db.outreach_intents.update_one(
            {"_id": intent_id, "workspace_id": workspace_id, "status": "in_flight", "claim_expires_at": {"$lte": now}},
            {"$set": {"status": "unknown_outcome", "attempt.outcome": "unknown_outcome", "updated_at": now}},
        )
        return changed.matched_count == 1
