"""Database-only dispatch authorization; HTTP starts after transaction commit.

Existing authority rows read by validation are written in the same snapshot
transaction. Concurrent changes to those rows therefore serialize or retry.
The workspace guard also orders participating suppression writers when a
recipient lookup is empty. Direct database writes do not follow that protocol.
"""
import asyncio
import hashlib
from copy import copy, deepcopy
from datetime import datetime, timedelta
from bson import BSON

from pymongo import ReturnDocument
from pymongo.errors import PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from outreach.core.authorization import canonical_hash
from outreach.core.paid_access import _utc

AUTHORIZATION_TIMEOUT_SECONDS = 10
IMMUTABLE_COLLECTIONS = {"outreach_sequence_versions"}


class AuthorityDatabase:
    def __init__(self, database, session, request_id: str) -> None:
        self.database, self.session, self.request_id = database, session, request_id
        self.fenced = set()
        self.native_fenced = {}
        self.deadlines = []
        self.checks = []

    def note_inbox_deadline(self, account: dict) -> None:
        from outreach.core.inbox_freshness import MAX_FRESHNESS_SECONDS
        started = _utc((account.get("inbox_sync") or {}).get("coverage_started_at"))
        if started:
            self.deadlines.append(started + timedelta(seconds=MAX_FRESHNESS_SECONDS))

    def note_connection_deadline(self, deadline: datetime) -> None:
        self.deadlines.append(deadline)

    async def fence_suppression(self, workspace_id: str) -> None:
        from outreach.core.suppression import touch_suppression_guard
        scope = await touch_suppression_guard(self.database, workspace_id, self.session)
        self.fenced.add(("outreach_suppression_guards", canonical_hash(scope["_id"])))
        from outreach.core.request_guard import RequestDenied
        record = await self.database.outreach_suppression_guards.find_one(scope, session=self.session)
        if record and record.get("erasure_state"):
            raise RequestDenied("workspace_erasure_requested")

    def note_schedule(self, schedule: dict) -> None:
        from outreach.core.rate_limiter import OutboundRateLimiter
        captured = deepcopy(schedule)
        self.checks.append(lambda now: OutboundRateLimiter.is_within_working_hours(captured, now_dt=now))

    def __getattr__(self, name: str):
        if not name.startswith("outreach_"):
            raise AttributeError("Dispatch validation requires an outreach collection")
        return AuthorityCollection(self, self.database[name], name)

    def __getitem__(self, name: str):
        return getattr(self, name)

    def remember_deadlines(self, name: str, document: dict) -> None:
        values = []
        if name == "outreach_sender_execution":
            values.append(document.get("permission", {}).get("expires_at"))
        elif name == "outreach_entitlements":
            values.append(document.get("paid_through"))
        elif name in {"outreach_content_approvals", "outreach_proxy_inventory", "outreach_voice_artifacts"}:
            values.append(document.get("expires_at"))
        elif name == "outreach_connection_jobs":
            from outreach.core.connection_repair import credential_deadline
            values.append(credential_deadline(document))
        elif name == 'outreach_mailbox_connection_jobs':
            values.append(document.get('authorization_expires_at'))
        elif name in {"outreach_manual_actions", "outreach_sequence_jobs", "outreach_import_jobs"}:
            values.append(document.get("claim_expires_at"))
        elif name == "outreach_mailboxes":
            values.append(document.get('token_expires_at'))
            synced = _utc(document.get("last_sync_at"))
            if synced:
                values.append(synced + timedelta(minutes=10))
        for value in values:
            expiry = _utc(value)
            if expiry:
                self.deadlines.append(expiry)


class AuthorityCursor:
    def __init__(self, collection, cursor, query) -> None:
        self.collection, self.cursor, self.query = collection, cursor, query

    def sort(self, *args):
        self.cursor = self.cursor.sort(*args)
        return self

    def limit(self, count):
        self.cursor = self.cursor.limit(count)
        return self

    async def to_list(self, length=None):
        documents = await self.cursor.to_list(length=length)
        for document in documents:
            await self.collection.fence(document, self.query)
        return documents


class AuthorityCollection:
    def __init__(self, database: AuthorityDatabase, collection, name: str) -> None:
        self.database, self.collection, self.name = database, collection, name

    async def fence(self, document: dict, query: dict) -> None:
        self.database.remember_deadlines(self.name, document)
        if self.name in IMMUTABLE_COLLECTIONS:
            return
        if "_id" not in document:
            raise RuntimeError("Authority row identity is unavailable")
        key = (self.name, canonical_hash(document["_id"]))
        native_hash = hashlib.sha256(BSON.encode({'_id': document['_id']})).hexdigest()
        if key in self.database.native_fenced and self.database.native_fenced[key] != native_hash:
            from outreach.core.request_guard import RequestDenied
            raise RequestDenied('ambiguous_native_authority')
        self.database.native_fenced[key] = native_hash
        if key in self.database.fenced:
            return
        changed = await self.collection.update_one({**query, "_id": document["_id"]}, {
            "$inc": {"dispatch_fence_revision": 1}}, session=self.database.session)
        if changed.matched_count != 1:
            from outreach.core.request_guard import RequestDenied
            raise RequestDenied("dispatch_authority_changed")
        self.database.fenced.add(key)

    async def find_one(self, query: dict, projection=None, **kwargs):
        # Internal validators need full row identity for their write fence.
        # This wrapper is never used by customer-facing read endpoints.
        document = await self.collection.find_one(query, session=self.database.session, **kwargs)
        if document:
            await self.fence(document, query)
        return document

    def find(self, query=None, projection=None):
        query = query or {}
        return AuthorityCursor(self, self.collection.find(query, session=self.database.session), query)

    async def update_one(self, query: dict, update: dict, **kwargs):
        return await self.collection.update_one(query, update, session=self.database.session, **kwargs)

    async def find_one_and_update(self, query: dict, update: dict, **kwargs):
        document = await self.collection.find_one_and_update(query, update, session=self.database.session, **kwargs)
        if document:
            self.database.remember_deadlines(self.name, document)
        return document


class DispatchAuthority:
    def __init__(self, database) -> None:
        self.database = database

    async def authorize(self, envelope, owner: str, request_id: str, action: str, parent, clock) -> dict:
        from outreach.core.request_guard import RequestDenied, request_parent
        from outreach.core.sender_execution import SenderExecution
        from outreach.core.suppression import ensure_suppression_guard, SuppressionUnavailable
        if parent and not parent.transaction_validator:
            raise RequestDenied("transaction_context_required")
        if envelope.authority_validator and not envelope.transaction_validator:
            raise RequestDenied("transaction_context_required")

        async def authorize_in_session(session):
            scoped = AuthorityDatabase(self.database, session, request_id)
            # Take the shared writer guard before any authority snapshot read.
            await scoped.fence_suppression(envelope.workspace_id)
            from outreach.core.restore_epoch import positive, EpochUnavailable
            try:
                epoch = await positive(scoped, envelope.workspace_id, captured=envelope.epoch_policy)
            except EpochUnavailable as exc:
                raise RequestDenied('restore_epoch_required') from exc
            scoped.checks.append(lambda stamp: epoch.live())
            current = copy(envelope)
            current.db = scoped
            current.authority_validator = (lambda: envelope.transaction_validator(scoped)) if envelope.transaction_validator else None
            async def validate():
                return await parent.transaction_validator(scoped) if parent else None
            with request_parent(owner, validate, approval_binding=envelope.content_binding(),
                    transaction_validator=parent.transaction_validator if parent else None) as scoped_parent:
                await current._validate(clock(), scoped_parent if parent else None)
                await current._validate_content(action, clock())
                guard = SenderExecution(scoped)
                boundary = await scoped.outreach_sender_execution.find_one_and_update({
                    **guard.scope(envelope.workspace_id, envelope.sender_id), "owner_token": owner,
                    "status": "in_flight", "physical_request_token": {"$exists": False},
                    "permission.latched": False, "permission.credential_generation": envelope.generation,
                    "permission.sources": envelope.source, "permission.expires_at": {"$gt": clock()},
                    "permission.issued_at": {"$lte": clock()}},
                    {"$set": {"physical_request_token": request_id}}, return_document=ReturnDocument.AFTER)
                if not boundary:
                    raise RequestDenied("sender_owner_changed")
                content = await current._authorize_content(action, clock())
                authorization = {"mode": "transaction", "authorized_at": clock(),
                    "authority_refs": [{"collection": name, "id_hash": identity,
                        "native_hash": scoped.native_fenced.get((name, identity))} for name, identity in sorted(scoped.fenced)]}
                saved = await scoped.outreach_physical_requests.update_one({"_id": request_id,
                    "workspace_id": envelope.workspace_id, "sender_id": envelope.sender_id,
                    "owner_token": owner, "status": "in_flight", "credential_generation": envelope.generation,
                    "source": envelope.source}, {"$set": {"dispatch_authorization": authorization}})
                if saved.matched_count != 1:
                    raise RequestDenied("request_owner_changed")
                return {"sender": boundary, "content": content, "deadlines": scoped.deadlines, "checks": scoped.checks}

        try:
            async with asyncio.timeout(AUTHORIZATION_TIMEOUT_SECONDS):
                await ensure_suppression_guard(self.database, envelope.workspace_id)
                async with await self.database.client.start_session() as session:
                    return await session.with_transaction(authorize_in_session,
                        read_concern=ReadConcern("snapshot"), write_concern=WriteConcern("majority"),
                        max_commit_time_ms=5000)
        except (PyMongoError, TimeoutError, SuppressionUnavailable) as exc:
            raise RequestDenied("dispatch_authority_unavailable") from exc
