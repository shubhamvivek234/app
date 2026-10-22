"""Durable offline campaign voice jobs; possible paid calls never auto-replay."""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable
from motor.motor_asyncio import AsyncIOMotorDatabase

from outreach.core import suppression, session_custody
from outreach.core.voice_key_custody import prepare_key, configuration_digest
from outreach.core.authorization import canonical_hash
from outreach.core.content_approval import ContentApproval, sequence_binding
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.paid_access import get_active_entitlement, _utc
from outreach.core.suppression import SuppressionDatabase
from outreach.core.voice_artifacts import VoiceArtifacts
from outreach.core.voice_artifact_custody import policy_digest as artifact_policy_digest
from outreach.core.voice_policy import VOICE_POLICY, preparation_enabled, require_configuration, validate_audio
from outreach.core.voice_provider import generate_campaign_voice
from utils.encryption import validate_encryption_key

Generator = Callable[[dict], Awaitable[bytes]]
LEASE = timedelta(minutes=2)
logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def authority(current: AsyncIOMotorDatabase | SuppressionDatabase) -> AsyncIOMotorDatabase | AuthorityDatabase:
    """Production callbacks always carry a transaction; old test fakes isolate it."""
    return AuthorityDatabase(current.database, current.session, "voice_preparation") if isinstance(current, SuppressionDatabase) else current


class VoicePreparation:
    def __init__(self, db: AsyncIOMotorDatabase | SuppressionDatabase) -> None:
        self.db = db

    async def _binding(self, current: AsyncIOMotorDatabase | SuppressionDatabase, workspace: str, lead_id: str, *, deadlines: list | None = None) -> dict:
        fenced = authority(current)
        entitlement = await get_active_entitlement(fenced, workspace)
        if not entitlement:
            raise ValueError("Voice preparation needs an active paid workspace")
        if deadlines is not None:
            deadlines.append(_utc(entitlement["paid_through"]))
        lead = await fenced.outreach_leads.find_one({"workspace_id": workspace, "id": lead_id})
        if not lead or lead.get("execution_state") not in {"queued", "waiting_delay"}:
            raise ValueError("The current lead step is no longer available")
        binding = await sequence_binding(fenced, workspace, lead_id)
        if not binding or binding["action"] != "voice_note":
            raise ValueError("The current step is not a voice note")
        require_configuration(binding)
        try:
            if session_custody.custody_mode() == 'legacy_fernet':
                validate_encryption_key()
            else:
                # Construction validates pinned configuration, with no AWS call.
                session_custody.configured_custody()
        except (ValueError, OSError) as exc:
            raise ValueError("Voice preparation requires working encrypted storage") from exc
        return binding

    async def queue(self, workspace: str, lead_id: str, actor: str) -> dict:
        if not actor or not actor.strip():
            raise ValueError("An identified user must request voice preparation")
        async def apply(current):
            binding = await self._binding(current, workspace, lead_id)
            scope = {"_id": canonical_hash(binding), "workspace_id": workspace}
            job = await current.outreach_voice_preparation_jobs.find_one(scope)
            now = utcnow()
            if job and job["status"] == "prepared":
                try:
                    await VoiceArtifacts(current).metadata(workspace, job["_id"], now=now)
                    return job
                except ValueError as exc:
                    logger.debug("Prepared voice artifact requires re-preparation for job=%s (%s)", job.get("_id"), type(exc).__name__)
            elif job and job["status"] not in {"blocked", "superseded"}:
                return job
            await current.outreach_voice_preparation_jobs.update_one(scope, {"$set": {
                "binding": binding, "status": "queued", "requested_by": actor.strip(), "updated_at": now,
                "provider_config_digest": configuration_digest(),
                "artifact_policy_digest": artifact_policy_digest(),
                "next_publish_at": now, "next_due_at": now}, "$setOnInsert": {"created_at": now, "mutation": True},
                "$unset": {"owner": "", "claim_expires_at": "", "error_code": ""}}, upsert=True)
            return await current.outreach_voice_preparation_jobs.find_one(scope)
        return await suppression.mutate_suppression(self.db, workspace, apply)

    async def recover(self, workspace: str, job_id: str) -> None:
        now = utcnow()
        async def apply(current):
            scope = {"_id": job_id, "workspace_id": workspace, "claim_expires_at": {"$lte": now}}
            await current.outreach_voice_preparation_jobs.update_one({**scope, "status": "claimed"}, {
                "$set": {"status": "queued", "next_due_at": now, "next_publish_at": now},
                "$unset": {"owner": "", "claim_expires_at": ""}})
            await current.outreach_voice_preparation_jobs.update_one({**scope, "status": "generating"}, {
                "$set": {"status": "held_outcome", "error_code": "generation_interrupted", "updated_at": now},
                "$unset": {"binding": ""}})
        await suppression.mutate_suppression(self.db, workspace, apply)

    async def _mark(self, workspace: str, job_id: str, owner: str, status: str, reason: str) -> dict:
        async def apply(current):
            changes = {"$set": {"status": status, "error_code": reason, "updated_at": utcnow()}}
            if status == "held_outcome":
                changes["$unset"] = {"binding": ""}
            await current.outreach_voice_preparation_jobs.update_one({"workspace_id": workspace, "_id": job_id,
                "owner": owner, "status": {"$in": ["claimed", "generating"]}}, changes)
        await suppression.mutate_suppression(self.db, workspace, apply)
        return {"status": status}

    async def run(self, workspace: str, job_id: str, *, generator: Generator | None = None) -> dict:
        if not preparation_enabled():
            return {"status": "disabled"}
        from outreach.core.restore_epoch import positive
        epoch = await positive(self.db, workspace)
        await self.recover(workspace, job_id)
        owner = str(uuid.uuid4())
        async def claim(current):
            now = utcnow()
            changed = await current.outreach_voice_preparation_jobs.update_one({"workspace_id": workspace,
                "_id": job_id, "status": "queued", "next_due_at": {"$lte": now}}, {"$set": {
                    "status": "claimed", "owner": owner, "claim_expires_at": now + LEASE, "next_recovery_due_at": now + LEASE}})
            if changed.modified_count:
                return await current.outreach_voice_preparation_jobs.find_one({"workspace_id": workspace, "_id": job_id, "owner": owner})
            return None
        job = await suppression.mutate_suppression(self.db, workspace, claim)
        if not job:
            current = await self.db.outreach_voice_preparation_jobs.find_one({"workspace_id": workspace, "_id": job_id})
            return {"status": current["status"] if current else "missing"}

        try:
            proof = job.get('provider_config_digest')
            artifact_proof = job.get('artifact_policy_digest')
            if ((artifact_proof is not None and artifact_proof != artifact_policy_digest())
                    or (session_custody.custody_mode() == 'kms_v1' and not artifact_proof)):
                raise ValueError('Voice artifact custody is unproven')
            if session_custody.custody_mode() == 'kms_v1' and not proof:
                raise ValueError('Voice provider configuration is unproven')
            credential = await prepare_key(expected_digest=proof,
                expected_source=job['binding']['context']['voice_provider_source_digest'])
        except ValueError:
            return await self._mark(workspace, job_id, owner, 'blocked', 'provider_custody_unavailable')

        async def begin(current):
            await positive(current, workspace, captured=epoch.captured)
            now = utcnow()
            if not credential.matches() or (artifact_proof is not None and artifact_proof != artifact_policy_digest()):
                raise ValueError('Voice provider configuration changed')
            deadlines = []
            if await self._binding(current, workspace, job["binding"]["context"]["lead_id"], deadlines=deadlines) != job["binding"]:
                return {"status": "superseded"}
            day = now.date().isoformat()
            budget = {"_id": workspace + ":" + day, "workspace_id": workspace}
            await current.outreach_voice_preparation_budgets.update_one(budget, {"$setOnInsert": {
                "day": day, "clips": 0, "chars": 0}}, upsert=True)
            chars = len(job["binding"]["content"]["body"])
            reserved = await current.outreach_voice_preparation_budgets.update_one({**budget,
                "clips": {"$lt": VOICE_POLICY["daily_clips"]},
                "chars": {"$lte": VOICE_POLICY["daily_chars"] - chars}}, {"$inc": {"clips": 1, "chars": chars}})
            if not reserved.modified_count:
                due = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
                await current.outreach_voice_preparation_jobs.update_one({"workspace_id": workspace, "_id": job_id,
                    "owner": owner, "status": "claimed"}, {"$set": {"status": "queued", "next_due_at": due,
                        "next_publish_at": due, "error_code": "daily_budget_exhausted"}})
                return {"status": "budget_wait"}
            marked = await current.outreach_voice_preparation_jobs.update_one({"workspace_id": workspace, "_id": job_id,
                "owner": owner, "status": "claimed", "claim_expires_at": {"$gt": now}}, {"$set": {
                    "status": "generating", "generation_started_at": now}, "$inc": {"generation_count": 1}})
            if not marked.modified_count:
                # Roll back the reservation together with the failed owner fence.
                raise ValueError("Voice preparation owner changed")
            return {"status": "generating", "deadline": min(*deadlines, _utc(job["claim_expires_at"]))}
        try:
            boundary = await suppression.mutate_suppression(self.db, workspace, begin)
        except ValueError:
            return await self._mark(workspace, job_id, owner, "blocked", "preparation_context_unavailable")
        if boundary["status"] == "superseded":
            return await self._mark(workspace, job_id, owner, "superseded", "preparation_context_changed")
        if boundary["status"] != "generating":
            return boundary
        if not preparation_enabled() or boundary["deadline"] <= utcnow():
            return await self._mark(workspace, job_id, owner, "blocked", "generation_not_called")
        try:
            def allowed():
                return (epoch.live() and preparation_enabled() and utcnow() < boundary['deadline'] and credential.matches()
                        and (artifact_proof is None or artifact_proof == artifact_policy_digest()))
            if not allowed():
                raise ValueError('Voice provider configuration changed')
            audio = (await generator(job['binding']) if generator is not None else
                     await generate_campaign_voice(job['binding'], credential=credential, allowed=allowed))
            validate_audio(audio)
        except Exception:
            # Every error after this durable marker is potentially billable.
            return await self._mark(workspace, job_id, owner, "held_outcome", "generation_needs_review")

        # Receipt already exists in this worker. Key wrapping must never run in
        # a retryable Mongo callback or cause a second paid generation call.
        prepared = None
        if credential.matches() and (artifact_proof is None or artifact_proof == artifact_policy_digest()):
            try:
                prepared = await VoiceArtifacts(self.db).prepare(job['binding'], audio, generation_id=owner)
            except ValueError:
                return await self._mark(workspace, job_id, owner, 'held_outcome', 'artifact_custody_unavailable')

        async def finish(current):
            await positive(current, workspace, captured=epoch.captured)
            now = utcnow()
            own = await current.outreach_voice_preparation_jobs.find_one({"workspace_id": workspace, "_id": job_id,
                "owner": owner, "status": "generating", "claim_expires_at": {"$gt": now}})
            if not own:
                return {"status": "owner_changed"}
            try:
                fresh = await self._binding(current, workspace, job["binding"]["context"]["lead_id"])
            except ValueError:
                fresh = None
            if (fresh != job["binding"] or not credential.matches() or prepared is None
                    or not prepared.matches(now=now)):
                await current.outreach_voice_preparation_jobs.update_one({"workspace_id": workspace, "_id": job_id, "owner": owner},
                    {"$set": {"status": "superseded", "updated_at": now, "generation_result": "received_discarded"},
                        "$unset": {"binding": ""}})
                return {"status": "superseded"}
            artifact = await VoiceArtifacts(current).install(prepared)
            reviewed = await sequence_binding(authority(current), workspace, fresh["context"]["lead_id"], voice_artifact=artifact)
            await ContentApproval(current).ensure(reviewed, now=now)
            await current.outreach_voice_preparation_jobs.update_one({"workspace_id": workspace, "_id": job_id, "owner": owner,
                "status": "generating"}, {"$set": {"status": "prepared", "updated_at": now,
                    "audio_digest": artifact["audio_digest"], "generation_result": "received"}, "$unset": {"binding": ""}})
            epoch.assert_live()
            return {"status": "prepared"}
        # Commit-only retries cannot repeat the already completed HTTP request.
        return await suppression.mutate_suppression(self.db, workspace, finish)


async def publish_voice_jobs(db: AsyncIOMotorDatabase, publisher: Callable[[str, str], Awaitable[None]], *, limit: int = 50) -> int:
    """Fair reference-only publication; recovery also runs with generation disabled."""
    now = utcnow()
    expired = await db.outreach_voice_preparation_jobs.find({"status": {"$in": ["claimed", "generating"]},
        "claim_expires_at": {"$lte": now}, "$or": [{"next_recovery_due_at": {"$exists": False}},
            {"next_recovery_due_at": {"$lte": now}}]}).sort("next_recovery_due_at", 1).limit(limit).to_list(length=limit)
    for job in expired:
        async def backoff(current):
            return await current.outreach_voice_preparation_jobs.update_one({"workspace_id": job["workspace_id"],
                "_id": job["_id"], "status": job["status"], "owner": job.get("owner"),
                "claim_expires_at": job["claim_expires_at"]}, {"$set": {"next_recovery_due_at": now + timedelta(minutes=5)}})
        try:
            await suppression.mutate_suppression(db, job["workspace_id"], backoff)
            await VoicePreparation(db).recover(job["workspace_id"], job["_id"])
        except suppression.SuppressionUnavailable:
            # Scheduling metadata is a private stopped-work control: no upsert,
            # no content/owner/status/permission change and no provider replay.
            # Keep it ordered against stop/purge without reopening the tenant.
            from outreach.core.erasure import _control
            try:
                await _control(db, job["workspace_id"], backoff)
            except suppression.SuppressionUnavailable:
                logger.warning("Voice recovery scheduling unavailable")
    if not preparation_enabled():
        return 0
    now = utcnow()
    jobs = await db.outreach_voice_preparation_jobs.find({"status": "queued", "next_due_at": {"$lte": now},
        "next_publish_at": {"$lte": now}}).sort("next_publish_at", 1).limit(limit).to_list(length=limit)
    published = 0
    for job in jobs:
        async def reserve(current):
            return await current.outreach_voice_preparation_jobs.update_one({"workspace_id": job["workspace_id"],
                "_id": job["_id"], "status": "queued", "next_publish_at": {"$lte": now}},
                {"$set": {"next_publish_at": now + timedelta(seconds=60)}})
        try:
            claim = await suppression.mutate_suppression(db, job["workspace_id"], reserve)
            if claim.modified_count:
                await publisher(job["_id"], job["workspace_id"])
                published += 1
        except Exception as exc:
            # Reservation times out after 60s; no lost Mongo job or secret payload.
            logger.warning("Voice job publication deferred (%s)", type(exc).__name__)
            continue
    return published
