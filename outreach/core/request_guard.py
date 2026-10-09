"""One fail-closed Mongo authority for every physical LinkedIn request.

The final local transition is request ownership, not remote cancellation. A
possible mutation retains ownership/evidence on cancellation, crash or timeout.
"""
import logging
import asyncio
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

from celery_workers.shutdown_handler import is_shutting_down
from outreach.core.authorization import canonical_hash
from outreach.core.execution_permission import ExecutionPermission, SOURCES
from outreach.core.inbox_freshness import credential_generation
from outreach.core.paid_access import live_actions_enabled, sender_is_ready, get_active_entitlement, _utc
from outreach.core.proxy_manager import JITProxyManager
from outreach.core.sender_execution import SenderExecution
from outreach.core.content_approval import ContentApproval

logger = logging.getLogger(__name__)
DEFAULT_HOURLY_CAP = 120
DEFAULT_DAILY_CAP = 1000
ACTION_CAPS = {"message": 100, "invite": 50, "like": 100, "comment": 50, "voice": 50, "visit": 100, "email": 100, "finder": 10}
BUSINESS_ACTIONS = {"message": "messages", "invite": "connection_invites", "like": "post_likes",
                    "comment": "comments", "voice": "voice_notes", "visit": "profile_visits", "email": "email_sends", "finder": "email_lookups"}
RESERVED_SOURCES = {"sync", "verify"}
REQUEST_TIMEOUT_SECONDS = 30


class RequestDenied(RuntimeError):
    def __init__(self, reason: str, retry_after: int = 30) -> None:
        self.reason, self.retry_after = reason, max(1, retry_after)
        super().__init__(reason)


class SubmissionUncertain(RuntimeError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__("Physical submission response is ambiguous")


async def unresolved_physical(db, workspace_id: str, sender_id: str, owner: str):
    return await db.outreach_physical_requests.find_one({"workspace_id": workspace_id, "sender_id": sender_id,
        "owner_token": owner, "mutation": True, "status": {"$in": ["in_flight", "unknown_outcome"]}})


@dataclass
class RequestParent:
    owner: str
    validator: object
    mutation_attempted: bool = False
    approval_binding: dict | None = None
    transaction_validator: object = None


_PARENT = ContextVar("outreach_request_parent", default=None)


@contextmanager
def request_parent(owner: str, validator, *, approval_binding: dict | None = None, transaction_validator=None):
    parent = RequestParent(owner, validator, approval_binding=approval_binding, transaction_validator=transaction_validator)
    token = _PARENT.set(parent)
    try:
        yield parent
    finally:
        _PARENT.reset(token)


def _bounded(value, default: int, ceiling: int) -> int:
    if value is None:
        return default
    if type(value) is not int or value < 0:
        raise ValueError("Invalid request budget")
    return min(value, ceiling)


def current_request_parent() -> RequestParent | None:
    return _PARENT.get()


class PhysicalBudget:
    def __init__(self, db) -> None:
        self.db = db

    async def reserve(self, workspace_id: str, sender_id: str, source: str, action: str, config: dict,
                      *, now: datetime | None = None, request_id: str | None = None) -> tuple[bool, int, str]:
        """CAS updates all windows/counters together. Denials never grant locally."""
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if not workspace_id or not sender_id or source not in SOURCES:
            return False, 30, "budget_scope_invalid"
        scope = SenderExecution.scope(workspace_id, sender_id)
        try:
            policy = config.get("request_budget") or {}
            hourly = _bounded(policy.get("hourly_cap"), DEFAULT_HOURLY_CAP, DEFAULT_HOURLY_CAP)
            daily = _bounded(policy.get("daily_cap"), DEFAULT_DAILY_CAP, DEFAULT_DAILY_CAP)
            reserved_h = min(hourly, _bounded(policy.get("reserved_hourly"), max(1, hourly // 5), DEFAULT_HOURLY_CAP))
            reserved_d = min(daily, _bounded(policy.get("reserved_daily"), max(1, daily // 5), DEFAULT_DAILY_CAP))
            action_default = ACTION_CAPS.get(action, DEFAULT_DAILY_CAP)
            action_cap = _bounded((policy.get("action_caps") or {}).get(action), action_default, action_default)
            field = BUSINESS_ACTIONS.get(action)
            if field:
                business_cap = _bounded((config.get("limits") or {}).get(field), 20, action_default)
                campaign_cap = _bounded((config.get("campaign_request_limits") or {}).get(field), business_cap, action_default)
                action_cap = min(action_cap, business_cap, campaign_cap)
            spacing = _bounded(policy.get("min_interval_seconds"), 0, 3600)
            try:
                await self.db.outreach_request_budgets.insert_one({**scope, "revision": 0})
            except DuplicateKeyError:
                pass
            hour, day = now.strftime("%Y%m%d%H"), now.strftime("%Y%m%d")
            wait_h = max(1, int(((now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)) - now).total_seconds()) + 1)
            wait_d = max(1, int(((now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)) - now).total_seconds()) + 1)
            for _ in range(16):
                doc = await self.db.outreach_request_budgets.find_one(scope)
                if not doc:
                    return False, 30, "budget_authority_unavailable"
                ht = doc.get("hourly_total", 0) if doc.get("hour") == hour else 0
                dt = doc.get("daily_total", 0) if doc.get("day") == day else 0
                hf = doc.get("hourly_foreground", 0) if doc.get("hour") == hour else 0
                df = doc.get("daily_foreground", 0) if doc.get("day") == day else 0
                legacy = config.get("counters") or {}
                seed = {kind: legacy.get(field, 0) for kind, field in BUSINESS_ACTIONS.items()
                        if legacy.get("date") == now.strftime("%Y-%m-%d") and type(legacy.get(field, 0)) is int and legacy.get(field, 0) > 0}
                actions = dict(doc.get("actions") or {}) if doc.get("day") == day else seed
                for kind, count in seed.items():
                    actions[kind] = max(actions.get(kind, 0), count)
                reservations = dict(doc.get("reservations") or {}) if doc.get("day") == day else {}
                foreground = source not in RESERVED_SOURCES
                last = _utc(doc.get("last_request_at"))
                if last and (now - last).total_seconds() < spacing:
                    return False, max(1, int(spacing - (now - last).total_seconds()) + 1), "min_interval_cooldown"
                if ht >= hourly or (foreground and hf >= hourly - reserved_h):
                    return False, wait_h, "physical_hourly_cap"
                if dt >= daily or (foreground and df >= daily - reserved_d):
                    return False, wait_d, "physical_daily_cap"
                if action in ACTION_CAPS and actions.get(action, 0) >= action_cap:
                    return False, wait_d, "physical_action_cap"
                actions[action] = actions.get(action, 0) + 1
                reservations[request_id or str(uuid.uuid4())] = {"action": action, "status": "reserved"}
                result = await self.db.outreach_request_budgets.update_one({**scope, "revision": doc["revision"]}, {
                    "$set": {"hour": hour, "day": day, "hourly_total": ht + 1, "daily_total": dt + 1,
                             "hourly_foreground": hf + int(foreground), "daily_foreground": df + int(foreground),
                             "actions": actions, "reservations": reservations, "updated_at": now, "last_request_at": now}, "$inc": {"revision": 1},
                })
                if getattr(result, "matched_count", 0) == 1:
                    return True, 0, "ok"
            return False, 5, "budget_contended"
        except Exception as exc:
            logger.warning("Physical request budget unavailable (%s)", type(exc).__name__)
            return False, 30, "budget_authority_unavailable"

    async def refund_non_call(self, workspace_id: str, sender_id: str, request_id: str, action: str, day: str) -> None:
        """Return action allowance once; conservative physical reservations remain charged."""
        await self.db.outreach_request_budgets.update_one({**SenderExecution.scope(workspace_id, sender_id),
            "day": day, f"reservations.{request_id}.status": "reserved", f"reservations.{request_id}.action": action},
            {"$inc": {f"actions.{action}": -1, "revision": 1}, "$set": {f"reservations.{request_id}.status": "not_submitted"}})


class RequestEnvelope:
    def __init__(self, db, workspace_id: str, sender_id: str, generation: str, source: str,
                 proxy_url: str, *, connection_job_id: str | None = None, authority_validator=None,
                 campaign_limits=None, operation_id: str | None = None, approval_binding: dict | None = None,
                 transaction_validator=None, prepared_proxy=None) -> None:
        self.db, self.workspace_id, self.sender_id = db, workspace_id, sender_id
        self.generation, self.source, self.proxy_url = generation, source, proxy_url
        self.connection_job_id = connection_job_id
        self.prepared_proxy = prepared_proxy
        self.authority_validator = authority_validator
        self.transaction_validator = transaction_validator
        self.campaign_limits = campaign_limits or {}
        self.operation_id = operation_id
        self.approval_binding = approval_binding
        from outreach.core.restore_epoch import policy
        self.epoch_policy = policy()

    def content_binding(self) -> dict | None:
        parent = _PARENT.get()
        return parent.approval_binding if parent else self.approval_binding

    def assert_content(self, action: str, recipient: str, content: dict) -> None:
        """Compare the adapter's actual arguments with the reviewed payload."""
        binding = self.content_binding()
        expected_action = {"invite": "connection_request", "message": "send_message", "reply": "inbox_reply", "comment": "comment", "voice": "voice_note"}[action]
        if (not binding or binding.get("action") != expected_action or binding.get("recipient") != recipient
                or any((binding.get("content") or {}).get(key) != value for key, value in content.items())):
            raise RequestDenied("content_changed")

    async def _validate_content(self, action: str, now: datetime) -> None:
        if action not in {"invite", "message", "comment", "voice", "like"}:
            return
        if action == "like" and not self.content_binding():
            return
        binding = self.content_binding()
        if (not binding or binding.get("workspace_id") != self.workspace_id
                or binding.get("sender_id") != self.sender_id or binding.get("source") != self.source
                or binding.get("credential_generation") != self.generation
                or not await ContentApproval(self.db).allowed(binding, now=now)):
            raise RequestDenied("content_approval_required")

    def assert_reaction(self, recipient: str, reaction: str) -> None:
        binding = self.content_binding()
        if not binding and self.source == "sequence":
            return
        content = (binding or {}).get("content") or {}
        if (not binding or binding.get("recipient") != recipient or not (
                binding.get("action") == "like" and content.get("reaction") == reaction
                or binding.get("action") == "comment" and content.get("auto_like") is True and reaction == "LIKE")):
            raise RequestDenied("content_changed")

    async def _authorize_content(self, action: str, now: datetime):
        if action not in {"invite", "message", "comment", "voice", "like"}:
            return None
        if action == "like" and not self.content_binding():
            return None
        record = await ContentApproval(self.db).authorize_submission(self.content_binding(), now=now)
        if not record:
            raise RequestDenied("content_approval_required")
        return record

    async def _authorize_dispatch(self, owner: str, request_id: str, action: str, parent, clock) -> dict:
        from outreach.core.dispatch_authority import DispatchAuthority
        return await DispatchAuthority(self.db).authorize(self, owner, request_id, action, parent, clock)

    def _proxy_config_matches(self, proxy) -> bool:
        if self.prepared_proxy is not None:
            return bool(self.proxy_url == self.prepared_proxy.url
                and self.prepared_proxy.matches(proxy, self.workspace_id))
        from outreach.core.session_custody import custody_mode
        if custody_mode() == "kms_v1":
            return False
        return bool(proxy.get("host") and self.proxy_url == JITProxyManager.format_proxy_url(proxy))

    def _proxy_matches(self, account: dict) -> bool:
        return self._proxy_config_matches(account.get("proxy") or {})

    async def _validate(self, now: datetime, parent: RequestParent | None) -> dict:
        if is_shutting_down() or not live_actions_enabled():
            raise RequestDenied("execution_disabled")
        if not await ExecutionPermission(self.db).allowed(self.workspace_id, self.sender_id, self.generation, self.source, now=now):
            raise RequestDenied("execution_permission_required")
        if self.connection_job_id:
            job = await self.db.outreach_connection_jobs.find_one({
                "id": self.connection_job_id, "workspace_id": self.workspace_id,
                "sender_id": self.sender_id, "status": "running",
            })
            if self.source != "verify" or self.generation != "pending:" + self.connection_job_id or not job:
                raise RequestDenied("verification_changed")
            from outreach.core.connection_repair import credential_deadline
            deadline = credential_deadline(job)
            if not deadline or deadline <= now or job.get("custody_expired_at"):
                raise RequestDenied("verification_custody_expired")
            if not await get_active_entitlement(self.db, self.workspace_id, now):
                raise RequestDenied("paid_access_required")
            from outreach.core.managed_proxy import _proxy_from_inventory
            slot = await self.db.outreach_sender_slots.find_one({
                "workspace_id": self.workspace_id, "sender_id": self.sender_id})
            lease = await self.db.outreach_proxy_leases.find_one({
                "_id": job["proxy_id"], "workspace_id": self.workspace_id, "sender_id": self.sender_id})
            inventory = await self.db.outreach_proxy_inventory.find_one({"_id": job["proxy_id"]})
            expiry = _utc((inventory or {}).get("expires_at"))
            if inventory and inventory.get('provider') == 'webshare_plan':
                from outreach.core.webshare_provisioning import managed_webshare_valid
                if (not await managed_webshare_valid(self.db, inventory, self.workspace_id, now=now)
                        or (lease or {}).get('provider') != 'webshare_plan'
                        or (lease or {}).get('country_code') != job.get('country_code')):
                    raise RequestDenied('proxy_changed')
            if (not slot or not lease or not inventory or inventory.get("status") != "available" or not expiry or expiry <= now
                    or inventory.get("last_workspace_id") != self.workspace_id
                    or inventory.get("workspace_id", self.workspace_id) != self.workspace_id
                    or inventory.get("country_code") != job.get("country_code")
                    or not self._proxy_config_matches(inventory if self.prepared_proxy is not None
                        else _proxy_from_inventory(inventory).model_dump())):
                raise RequestDenied("proxy_changed")
            account = {}
        else:
            account = await self.db.outreach_accounts.find_one({"id": self.sender_id, "workspace_id": self.workspace_id, "is_deleted": {"$ne": True}})
            if (not account or credential_generation(account) != self.generation
                    or not await sender_is_ready(self.db, self.workspace_id, account, now)
                    or not self._proxy_matches(account)):
                raise RequestDenied("sender_changed")
            if self.prepared_proxy is not None and self.prepared_proxy.scoped:
                proxy_id = (account.get("proxy") or {}).get("proxy_id")
                inventory = await self.db.outreach_proxy_inventory.find_one({"_id": proxy_id,
                    "last_workspace_id": self.workspace_id})
                if not inventory or inventory.get("workspace_id") != self.workspace_id or not self._proxy_config_matches(inventory):
                    raise RequestDenied("proxy_changed")
        from outreach.core.proxy_identity import restore_ip_allowed
        hosts = [inventory.get('host')] if self.connection_job_id else [(account.get('proxy') or {}).get('host')]
        if not self.connection_job_id:
            # Legacy transport may differ from its inventory; neither IP may
            # evade a restored negative. Missing legacy inventory host is not proof.
            asset = await self.db.outreach_proxy_inventory.find_one({
                '_id': (account.get('proxy') or {}).get('proxy_id'), 'last_workspace_id': self.workspace_id})
            if asset and asset.get('host') is not None:
                hosts.append(asset['host'])
        for host in set(hosts):
            if not await restore_ip_allowed(self.db, host):
                raise RequestDenied('proxy_restore_review_required')
        if parent and parent.validator:
            reason = await parent.validator()
            if reason:
                raise RequestDenied(reason)
        if self.authority_validator:
            reason = await self.authority_validator()
            if reason:
                raise RequestDenied(reason)
        return account

    async def reserve_budget(self, action: str, config: dict, now: datetime, reservation_id: str) -> tuple:
        return await PhysicalBudget(self.db).reserve(self.workspace_id, self.sender_id, self.source, action,
            {**config, "campaign_request_limits": self.campaign_limits}, now=now, request_id=reservation_id)

    async def refund_budget(self, action: str, reservation_id: str, day: str) -> None:
        await PhysicalBudget(self.db).refund_non_call(self.workspace_id, self.sender_id, reservation_id, action, day)

    def response_evidence(self, response, action: str, mutation: bool) -> dict:
        if mutation and 200 <= response.status_code < 300:
            try:
                body = response.json()
            except ValueError:
                body = None
            if body is None or (isinstance(body, dict) and (body.get("error") or body.get("errors"))):
                raise SubmissionUncertain(response.status_code)
        return {}

    async def call(self, method: str, path: str, factory, *, action: str = "read", now: datetime | None = None,
                   side_effect: bool | None = None):
        """Run one lazy network operation after durable ownership and permission."""
        fixed_now = now
        clock = lambda: fixed_now or datetime.now(timezone.utc)
        parent = _PARENT.get()
        owner = parent.owner if parent else str(uuid.uuid4())
        guard = SenderExecution(self.db)
        standalone = parent is None
        mutation = side_effect if side_effect is not None else method.upper() not in {"GET", "HEAD", "OPTIONS"}
        if mutation and action not in ACTION_CAPS:
            raise RequestDenied("request_action_required")
        request_id = (canonical_hash([self.workspace_id, self.sender_id, self.source, self.operation_id, method.upper(), path, action])
                      if mutation and self.operation_id else str(uuid.uuid4()))
        reserved_day = None
        reservation_id = str(uuid.uuid4())
        budget_reserved = False
        started = False
        uncertain = False
        audit_owned = False
        try:
            account = await self._validate(clock(), parent)
            await self._validate_content(action if mutation else "read", clock())
            if standalone:
                if not await guard.acquire(self.workspace_id, self.sender_id, owner, now=clock()):
                    raise RequestDenied("sender_busy", 5)
            else:
                owned = await self.db.outreach_sender_execution.find_one({
                    **guard.scope(self.workspace_id, self.sender_id), "owner_token": owner, "status": "in_flight"})
                if not owned:
                    raise RequestDenied("sender_owner_changed")
            reserve_now = clock()
            allowed, delay, reason = await self.reserve_budget(action, account, reserve_now, reservation_id)
            if not allowed:
                raise RequestDenied(reason, delay)
            budget_reserved = True
            reserved_day = reserve_now.strftime("%Y%m%d")
            audit = {
                "_id": request_id, "workspace_id": self.workspace_id, "sender_id": self.sender_id,
                "credential_generation": self.generation, "source": self.source, "action": action,
                "mutation": mutation, "owner_token": owner, "status": "preparing",
                "endpoint_digest": canonical_hash([method.upper(), path]), "created_at": clock(),
                "logical_operation_id": self.operation_id, "budget_reservation_id": reservation_id,
            }
            try:
                await self.db.outreach_physical_requests.insert_one(audit)
                audit_owned = True
            except DuplicateKeyError as exc:
                # Only explicit proof of no submission permits reclaim. Preserve
                # the prior non-call audit; every possible/received outcome blocks.
                scope = {"_id": request_id, "workspace_id": self.workspace_id, "sender_id": self.sender_id}
                prior = await self.db.outreach_physical_requests.find_one({**scope, "status": "not_submitted"})
                if not prior:
                    raise RequestDenied("physical_action_already_attempted") from exc
                history = {key: value for key, value in prior.items() if key not in {"_id", "non_call_history"}}
                reclaimed = await self.db.outreach_physical_requests.update_one({
                    **scope, "status": "not_submitted", "owner_token": prior["owner_token"]}, {
                    "$set": {key: value for key, value in audit.items() if key != "_id"},
                    "$unset": {"completed_at": "", "started_at": ""},
                    "$push": {"non_call_history": history},
                })
                if getattr(reclaimed, "matched_count", 0) != 1:
                    raise RequestDenied("physical_action_already_attempted") from exc
                audit_owned = True
            await self._validate(clock(), parent)
            await self._validate_content(action if mutation else "read", clock())
            if standalone and not await guard.begin(self.workspace_id, self.sender_id, owner, now=clock()):
                raise RequestDenied("sender_owner_changed")
            marked = await self.db.outreach_physical_requests.update_one({
                "_id": request_id, "workspace_id": self.workspace_id, "owner_token": owner, "status": "preparing"},
                {"$set": {"status": "in_flight", "started_at": clock()}})
            if getattr(marked, "matched_count", 0) != 1:
                raise RequestDenied("request_owner_changed")
            # Recheck after evidence writes; a rejection here is proven no call.
            await self._validate(clock(), parent)
            await self._validate_content(action if mutation else "read", clock())
            authority = await self._authorize_dispatch(owner, request_id, action if mutation else "read", parent, clock)
            boundary, content_authority = authority["sender"], authority["content"]
            if any(deadline <= clock() for deadline in authority["deadlines"]):
                raise RequestDenied("dispatch_authority_expired")
            if any(not check(clock()) for check in authority.get("checks", [])):
                raise RequestDenied("outside_working_hours")
            content_expiry = _utc((content_authority or {}).get("expires_at"))
            if content_authority and (not content_expiry or content_expiry <= clock()):
                raise RequestDenied("content_approval_required")
            permission_expiry = _utc((boundary.get("permission") or {}).get("expires_at"))
            if not permission_expiry or permission_expiry <= clock():
                raise RequestDenied("execution_permission_required")
            if self.prepared_proxy is not None and not self.prepared_proxy.current(self.proxy_url):
                raise RequestDenied('proxy_changed')
            started = True
            if parent and mutation:
                parent.mutation_attempted = True
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                response = await factory()
            if mutation and (response.status_code >= 500 or response.status_code in {408, 429}):
                raise SubmissionUncertain(response.status_code)
            evidence = self.response_evidence(response, action, mutation)
            recorded = await self.db.outreach_physical_requests.update_one({
                "_id": request_id, "workspace_id": self.workspace_id, "owner_token": owner, "status": "in_flight"},
                {"$set": {"status": "response_received", "http_status": response.status_code, "completed_at": clock(), **evidence}})
            if getattr(recorded, "matched_count", 0) != 1:
                raise RuntimeError("Physical response evidence changed")
            return response
        except BaseException:
            uncertain = bool(started and mutation)
            if uncertain:
                try:
                    await self.db.outreach_physical_requests.update_one({"_id": request_id, "workspace_id": self.workspace_id,
                        "owner_token": owner, "status": "in_flight"},
                        {"$set": {"status": "unknown_outcome", "completed_at": clock()}})
                    await ExecutionPermission(self.db).revoke(self.workspace_id, self.sender_id, "request_guard", "physical_submission_unknown", now=clock())
                except Exception as exc:
                    logger.error("Physical uncertainty recording failed (%s)", type(exc).__name__)
            elif audit_owned:
                await self.db.outreach_physical_requests.update_one({"_id": request_id, "workspace_id": self.workspace_id, "owner_token": owner,
                    "status": {"$in": ["preparing", "in_flight"]}},
                    {"$set": {"status": "read_failed" if started else "not_submitted", "completed_at": clock()}})
            raise
        finally:
            if not started and budget_reserved:
                await self.refund_budget(action, reservation_id, reserved_day)
            if not uncertain and audit_owned:
                await self.db.outreach_sender_execution.update_one({
                    **guard.scope(self.workspace_id, self.sender_id), "owner_token": owner,
                    "physical_request_token": request_id}, {"$unset": {"physical_request_token": ""}})
            if standalone and not uncertain:
                await guard.release(self.workspace_id, self.sender_id, owner)
