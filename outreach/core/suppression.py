"""Workspace suppression ordering shared by dispatch and database-only writers.

The guard serializes participating writers even when the recipient query returns
no row. It deliberately covers all identities in a workspace for this pilot.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, TypeVar

from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection, AsyncIOMotorCursor, AsyncIOMotorClientSession
from pymongo.results import DeleteResult, InsertOneResult, InsertManyResult, UpdateResult

from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from outreach.core.authorization import canonical_hash

SUPPRESSION_TIMEOUT_SECONDS = 10
ResultT = TypeVar("ResultT")


class SuppressionUnavailable(RuntimeError):
    """No suppression success may be reported without a committed transaction."""


def guard_scope(workspace_id: str) -> dict[str, str]:
    if not isinstance(workspace_id, str) or not workspace_id:
        raise ValueError("A workspace is required for suppression ordering")
    return {"_id": canonical_hash(["suppression", workspace_id]), "workspace_id": workspace_id}


async def touch_suppression_guard(db: AsyncIOMotorDatabase, workspace_id: str,
                                 session: AsyncIOMotorClientSession) -> dict[str, str]:
    scope = guard_scope(workspace_id)
    result = await db.outreach_suppression_guards.update_one(scope, {
        "$inc": {"revision": 1}, "$set": {"updated_at": datetime.now(timezone.utc)}},
        session=session)
    if result.matched_count != 1:
        raise SuppressionUnavailable("Suppression guard was not written")
    return scope


async def ensure_suppression_guard(db: AsyncIOMotorDatabase, workspace_id: str) -> None:
    """Create the stable guard before the snapshot, including concurrent first use."""
    scope = guard_scope(workspace_id)
    collection = db.outreach_suppression_guards.with_options(
        read_concern=ReadConcern("majority"), write_concern=WriteConcern("majority"))
    if await collection.find_one(scope, {"_id": 1}):
        return
    try:
        await collection.insert_one({**scope, "revision": 0})
    except DuplicateKeyError:
        if not await collection.find_one(scope, {"_id": 1}):
            raise SuppressionUnavailable("Suppression guard identity is unavailable") from None


class SuppressionCollection:
    """Inject the same session and require explicit tenant scope on every call."""

    def __init__(self, database: SuppressionDatabase, collection: AsyncIOMotorCollection) -> None:
        self.database, self.collection = database, collection

    def scoped(self, query: dict[str, Any]) -> None:
        if query.get("workspace_id") != self.database.workspace_id:
            raise ValueError("Suppression mutation crossed workspace scope")

    def options(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        supplied = kwargs.pop("session", None)
        if supplied is not None and supplied is not self.database.session:
            raise ValueError("Suppression mutation changed transaction session")
        return {**kwargs, "session": self.database.session}

    async def find_one(self, query: dict, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        self.scoped(query)
        return await self.collection.find_one(query, *args, **self.options(kwargs))

    def find(self, query: dict, *args: Any, **kwargs: Any) -> AsyncIOMotorCursor:
        self.scoped(query)
        return self.collection.find(query, *args, **self.options(kwargs))

    async def update_one(self, query: dict, update: dict, **kwargs: Any) -> UpdateResult:
        self.scoped(query)
        return await self.collection.update_one(query, update, **self.options(kwargs))

    async def update_many(self, query: dict, update: dict, **kwargs: Any) -> UpdateResult:
        self.scoped(query)
        return await self.collection.update_many(query, update, **self.options(kwargs))

    async def insert_one(self, document: dict, **kwargs: Any) -> InsertOneResult:
        self.scoped(document)
        return await self.collection.insert_one(document, **self.options(kwargs))

    async def insert_many(self, documents: list[dict], **kwargs: Any) -> InsertManyResult:
        for document in documents:
            self.scoped(document)
        return await self.collection.insert_many(documents, **self.options(kwargs))

    async def delete_one(self, query: dict, **kwargs: Any) -> DeleteResult:
        self.scoped(query)
        return await self.collection.delete_one(query, **self.options(kwargs))

    async def delete_many(self, query: dict, **kwargs: Any) -> DeleteResult:
        self.scoped(query)
        return await self.collection.delete_many(query, **self.options(kwargs))

    async def replace_one(self, query: dict, document: dict, **kwargs: Any) -> UpdateResult:
        self.scoped(query)
        self.scoped(document)
        return await self.collection.replace_one(query, document, **self.options(kwargs))

    async def count_documents(self, query: dict, **kwargs: Any) -> int:
        self.scoped(query)
        return await self.collection.count_documents(query, **self.options(kwargs))


class SuppressionDatabase:
    def __init__(self, database: AsyncIOMotorDatabase, workspace_id: str, session: AsyncIOMotorClientSession) -> None:
        self.database, self.workspace_id, self.session = database, workspace_id, session

    def __getattr__(self, name: str) -> SuppressionCollection:
        if not name.startswith("outreach_"):
            raise AttributeError("Suppression persistence requires outreach collections")
        return SuppressionCollection(self, self.database[name])

    def __getitem__(self, name: str) -> SuppressionCollection:
        return getattr(self, name)


async def mutate_suppression(db: AsyncIOMotorDatabase | SuppressionDatabase, workspace_id: str,
                             operation: Callable[[SuppressionDatabase], Awaitable[ResultT]]) -> ResultT:
    """Commit a database-only callback with the workspace guard; retry no HTTP."""
    guard_scope(workspace_id)
    if isinstance(db, SuppressionDatabase):
        if db.workspace_id != workspace_id:
            raise ValueError("Suppression mutation crossed workspace scope")
        return await operation(db)

    async def apply(session: AsyncIOMotorClientSession) -> ResultT:
        await touch_suppression_guard(db, workspace_id, session)
        current = SuppressionDatabase(db, workspace_id, session)
        from outreach.core.erasure import workspace_is_open
        if not await workspace_is_open(current, workspace_id):
            raise SuppressionUnavailable("Workspace is closed for erasure")
        return await operation(current)

    try:
        async with asyncio.timeout(SUPPRESSION_TIMEOUT_SECONDS):
            await ensure_suppression_guard(db, workspace_id)
            # Motor 3.4 can surface a transient commit error from its context
            # exit before the internal commit-retry loop. Restart only a
            # definitely aborted DB transaction, with a fresh session and the
            # same overall deadline. Unknown commits never replay a callback.
            for restart in range(3):
                try:
                    async with await db.client.start_session() as session:
                        return await session.with_transaction(apply, read_concern=ReadConcern("snapshot"),
                            write_concern=WriteConcern("majority"), max_commit_time_ms=5000)
                except PyMongoError as exc:
                    if (restart == 2 or not exc.has_error_label("TransientTransactionError")
                            or exc.has_error_label("UnknownTransactionCommitResult")):
                        raise
                    await asyncio.sleep(0)
    except (PyMongoError, TimeoutError) as exc:
        raise SuppressionUnavailable("Suppression could not be committed") from exc
