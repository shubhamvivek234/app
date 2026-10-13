"""Immutable exact-content review, separate from execution and outcome authority."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from outreach.core.authorization import canonical_hash
from outreach.core.dag_compiler import interpolate_template, contains_ai_prompt_token
from outreach.core.inbox_freshness import credential_generation
from outreach.core.paid_access import _utc
from outreach.core.sequence_versions import load_sequence
from outreach.core.voice_artifact_custody import PreparedClip

POLICY_VERSION = 1
POLICY = {"mode": "exact_human_review", "max_content_chars": 10000, "valid_seconds": 86400}
POLICY_DIGEST = canonical_hash(POLICY)
CONTENT_ACTIONS = {"connection_request", "send_message", "voice_note", "send_email", "comment", "inbox_reply"}


def make_binding(*, workspace_id: str, account: dict, source: str, recipient: str,
                 action: str, content: dict, context: dict) -> dict:
    """Server-owned structured framing; no client-supplied scope or policy."""
    if (not workspace_id or not account.get("id") or not recipient or not action
            or account.get("workspace_id", workspace_id) != workspace_id
            or source not in {"sequence", "engage", "inbox_reply"}
            or action not in CONTENT_ACTIONS | {"like"}):
        raise ValueError("Content review scope is incomplete")
    if (not isinstance(content, dict) or not isinstance(context, dict)
            or any(not isinstance(key, str) or not isinstance(value, (str, bool)) for key, value in content.items())
            or any(not isinstance(key, str) or not isinstance(value, (str, int, bool, type(None))) for key, value in context.items())
            or sum(len(value) for value in content.values() if isinstance(value, str)) > POLICY["max_content_chars"]
            or contains_ai_prompt_token(content)):
        raise ValueError("Content needs finished, bounded copy")
    return {"workspace_id": workspace_id, "sender_id": account["id"],
            "credential_generation": credential_generation(account), "source": source,
            "recipient": recipient, "action": action, "content": deepcopy(content),
            "context": deepcopy(context), "policy_version": POLICY_VERSION, "policy_digest": POLICY_DIGEST}


async def sequence_binding(db: AsyncIOMotorDatabase, workspace_id: str, lead_id: str, *, voice_artifact: dict | None = None) -> dict | None:
    """Render from current tenant records; personalization edits change the binding."""
    lead = await db.outreach_leads.find_one({"id": lead_id, "workspace_id": workspace_id})
    if not lead:
        raise ValueError("Lead is unavailable")
    campaign = await db.outreach_campaigns.find_one({"id": lead["campaign_id"], "workspace_id": workspace_id, "is_deleted": {"$ne": True}})
    account = await db.outreach_accounts.find_one({"id": lead.get("assigned_account_id"), "workspace_id": workspace_id, "is_deleted": {"$ne": True}})
    sequence = await load_sequence(db, workspace_id, lead["campaign_id"], campaign=campaign)
    if not campaign or not account or not sequence:
        raise ValueError("Content review context is unavailable")
    node = (sequence.get("compiled_dag") or {}).get("nodes", {}).get(lead.get("current_node_id"), {})
    action = node.get("type")
    if action not in CONTENT_ACTIONS:
        return None
    config = node.get("config") or {}
    recipient = lead.get("linkedin_urn") or lead.get("linkedin_url") or ""
    context = {"campaign_id": lead["campaign_id"], "lead_id": lead["id"],
               "enrollment_id": lead.get("enrollment_id") or "legacy:" + lead["id"], "node_id": lead.get("current_node_id"),
               "sequence_version": sequence.get("version", 1), "sequence_digest": canonical_hash(sequence.get("compiled_dag")),
               "authorization_revision": campaign.get("authorization_revision", 0)}
    if action == "send_email":
        from outreach.core.mailbox_delivery import render_email_body
        from outreach.core.email_finder import normalize_email
        recipient = normalize_email(lead.get("email")) or ""
        body = interpolate_template(config.get("body") or "", lead)
        content = {"subject": interpolate_template(config.get("subject") or "", lead).strip(), "body": render_email_body(body)}
        if not content["subject"] or not body.strip():
            raise ValueError("Email content is incomplete")
        mailbox = await db.outreach_mailboxes.find_one({"workspace_id": workspace_id, "sender_account_id": account["id"]}) or {}
        context["mailbox_identity"] = canonical_hash([mailbox.get("provider"), mailbox.get("provider_user_id"),
            mailbox.get("email"), mailbox.get("connection_job_id")])
        content["sender_email"] = mailbox.get("email") or ""
        if not content["sender_email"]:
            raise ValueError("Email review needs a connected mailbox identity")
    elif action == "voice_note":
        from outreach.core.voice_selection import selected_voice
        voice = await selected_voice(db, workspace_id, account['id'])
        from outreach.core.voice_studio import require_profile, profile_identity
        require_profile(voice)
        script = config.get("script", "Hey {{first_name}}, saw your work at {{company_name}} and wanted to send a quick voice note!")
        content = {"body": interpolate_template(script, lead), "voice_id": voice['elevenlabs_voice_id']}
        from outreach.core.voice_policy import VOICE_POLICY_DIGEST
        context["voice_profile_identity"] = profile_identity(voice)
        context["voice_selection_id"] = voice['id']
        context["voice_policy_digest"] = VOICE_POLICY_DIGEST
        context["voice_provider_source_digest"] = voice["provider_source_digest"]
        if voice_artifact:
            base = make_binding(workspace_id=workspace_id, account=account, source="sequence", recipient=recipient,
                action=action, content=content, context=context)
            if (voice_artifact.get("_id") != canonical_hash(base)
                    or voice_artifact.get("binding_digest") != canonical_hash(base)):
                raise ValueError("Prepared voice recording context changed")
            content["audio_digest"] = voice_artifact["audio_digest"]
            context["voice_artifact_id"] = voice_artifact["_id"]
            context["voice_artifact_generation"] = voice_artifact.get("generation_id", "legacy")
    else:
        template = config.get("note", "") if action == "connection_request" else config.get("body", "Hi {{first_name}}")
        content = {"body": interpolate_template(template, lead)}
    return make_binding(workspace_id=workspace_id, account=account, source="sequence", recipient=recipient,
                        action=action, content=content, context=context)


class ContentApproval:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    async def ensure(self, binding: dict, *, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        key = canonical_hash(binding)
        doc = {"_id": key, "workspace_id": binding["workspace_id"], "binding": deepcopy(binding),
               "status": "pending", "revision": 1, "created_at": now, "updated_at": now}
        await self.db.outreach_content_approvals.update_one({"_id": key, "workspace_id": binding["workspace_id"]},
            {"$setOnInsert": doc}, upsert=True)
        return await self.db.outreach_content_approvals.find_one({"_id": key, "workspace_id": binding["workspace_id"]})

    async def allowed(self, binding: dict, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if binding.get("policy_version") != POLICY_VERSION or binding.get("policy_digest") != POLICY_DIGEST:
            return False
        doc = await self.db.outreach_content_approvals.find_one({"_id": canonical_hash(binding), "workspace_id": binding.get("workspace_id")})
        if not doc or doc.get("status") != "approved" or doc.get("binding") != binding or not doc.get("reviewed_by"):
            return False
        approved, expiry = _utc(doc.get("approved_at")), _utc(doc.get("expires_at"))
        return bool(approved and expiry and approved <= now < expiry
                    and (expiry - approved).total_seconds() <= POLICY["valid_seconds"])

    async def decide(self, workspace_id: str, approval_id: str, actor: str, decision: str,
                     *, revision: int, now: datetime | None = None) -> None:
        if not actor or not actor.strip() or decision not in {"approve", "reject", "revoke"} or type(revision) is not int:
            raise ValueError("An identified reviewer and current decision revision are required")
        now = now or datetime.now(timezone.utc)
        current = await self.db.outreach_content_approvals.find_one({"_id": approval_id, "workspace_id": workspace_id})
        if (not current or current.get("revision") != revision
                or current["binding"].get("policy_version") != POLICY_VERSION
                or current["binding"].get("policy_digest") != POLICY_DIGEST):
            raise ValueError("Content review changed; reload it")
        if decision == "approve" and current["binding"].get("action") == "voice_note" and not current["binding"]["content"].get("audio_digest"):
            raise ValueError("Prepare and listen to the exact voice clip before approving")
        status = {"approve": "approved", "reject": "rejected", "revoke": "revoked"}[decision]
        changed = await self.db.outreach_content_approvals.update_one({"_id": approval_id, "workspace_id": workspace_id, "revision": revision}, {
            "$set": {"status": status, "reviewed_by": actor.strip(), "updated_at": now,
                      "approved_at": now if decision == "approve" else None,
                      "expires_at": now + timedelta(seconds=POLICY["valid_seconds"]) if decision == "approve" else now},
            "$inc": {"revision": 1}, "$push": {"history": {"decision": decision, "actor_id": actor.strip(), "at": now, "revision": revision}},
        })
        if getattr(changed, "matched_count", 0) != 1:
            raise ValueError("Content review changed; reload it")

    async def authorize_submission(self, binding: dict, *, now: datetime | None = None) -> dict | None:
        """Approval's ordering boundary; this does not grant sender permission."""
        now = now or datetime.now(timezone.utc)
        if binding.get("policy_version") != POLICY_VERSION or binding.get("policy_digest") != POLICY_DIGEST:
            return None
        return await self.db.outreach_content_approvals.find_one_and_update({
            "_id": canonical_hash(binding), "workspace_id": binding["workspace_id"], "binding": binding,
            "status": "approved", "approved_at": {"$lte": now}, "expires_at": {"$gt": now},
            "reviewed_by": {"$nin": [None, ""]}},
            {"$set": {"last_authorized_at": now}, "$inc": {"authorized_submissions": 1}}, return_document=ReturnDocument.AFTER)

    async def require_sequence(self, lead: dict, expected: dict, action: str, content: dict | str | None,
                               *, voice_clip: PreparedClip | None = None) -> dict | None:
        if action not in CONTENT_ACTIONS:
            return None
        artifact = None
        if action == "voice_note" and isinstance(content, dict):
            from outreach.core.voice_artifacts import VoiceArtifacts
            artifact = await self.db.outreach_voice_artifacts.find_one({"_id": content.get("voice_artifact_id"),
                "workspace_id": expected["workspace_id"], "status": "prepared"})
            if (not artifact or artifact.get("audio_digest") != content.get("audio_digest")
                    or artifact.get("generation_id") != content.get("voice_artifact_generation")):
                raise ValueError("Prepared voice recording changed")
            if voice_clip is None:
                # Compatibility for independent callers; scoped transactions
                # require a worker-prepared clip and cannot open keys here.
                voice_clip = await VoiceArtifacts(self.db).prepare_load(expected["workspace_id"], artifact["_id"])
            if not voice_clip.matches(artifact):
                raise ValueError('Prepared voice recording changed')
            from outreach.core.dispatch_authority import AuthorityDatabase
            if isinstance(self.db, AuthorityDatabase):
                self.db.checks.append(lambda now: voice_clip.matches(artifact, now=now))
        binding = await sequence_binding(self.db, expected["workspace_id"], lead["id"], voice_artifact=artifact)
        rendered = {"body": content} if isinstance(content, str) else dict(content or {})
        rendered.pop("voice_artifact_id", None)
        rendered.pop("voice_artifact_generation", None)
        if (not binding or binding["action"] != action or binding["content"] != rendered
                or binding["sender_id"] != expected["sender_id"]
                or binding["credential_generation"] != expected["credential_generation"]
                or binding["context"]["authorization_revision"] != expected["revision"]
                or binding["context"]["sequence_version"] != expected["sequence_version"]
                or binding["context"]["sequence_digest"] != expected["sequence_digest"]):
            raise ValueError("Content changed during preparation")
        await self.ensure(binding)
        return binding
