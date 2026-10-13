"""Database-only parent fences for late Engage results and per-kind run status."""
from typing import Any, Awaitable, Callable
from motor.motor_asyncio import AsyncIOMotorDatabase
from outreach.core.suppression import mutate_suppression, SuppressionDatabase
from outreach.core.workspace_scope import workspace_scope


Document = dict[str, Any]
Database = AsyncIOMotorDatabase | SuppressionDatabase


class ProjectionStopped(RuntimeError):
    pass


def run_query(binding: Document) -> Document:
    return {"_id": binding["_id"], "id": binding["id"],
            **workspace_scope(binding["workspace_id"]), binding["run_field"]: binding["run_id"]}


async def start_run(db: Database, workspace_id: str, list_id: str, kind: str, run_id: str | None) -> Document | None:
    # Old broker messages cannot prove the publication-time list generation.
    if not run_id:
        return None
    field = kind + "_run_id"
    async def apply(current):
        query = {"id": list_id, **workspace_scope(workspace_id), field: run_id,
                 kind + "_status": "queued"}
        parent = await current.outreach_engage_lists.find_one(query)
        if not parent:
            return None
        changed = await current.outreach_engage_lists.update_one({**query, "_id": parent["_id"]},
            {"$set": {kind + "_status": "running"}, "$inc": {"projection_revision": 1}})
        if changed.matched_count != 1:
            return None
        return {"_id": parent["_id"], "id": list_id, "workspace_id": workspace_id,
                "kind": kind, "run_field": field, "run_id": run_id}
    return await mutate_suppression(db, workspace_id, apply)


async def project(db: Database, binding: Document, contact: Document,
                  operation: Callable[[SuppressionDatabase, Document], Awaitable[Any]]) -> Any:
    async def apply(current):
        parent_query = {**run_query(binding), binding["kind"] + "_status": "running"}
        parent = await current.outreach_engage_lists.update_one(parent_query, {"$inc": {"projection_revision": 1}})
        if parent.matched_count != 1:
            raise ProjectionStopped("Engage list or run changed")
        query = {"_id": contact["_id"], "id": contact["id"], "list_id": binding["id"],
                 **workspace_scope(binding["workspace_id"]), "profile_url": contact.get("profile_url"),
                 "vanity_name": contact.get("vanity_name")}
        query["profile_urn"] = ({"$eq": contact["profile_urn"], "$exists": True}
                                if "profile_urn" in contact else {"$exists": False})
        survivor = await current.outreach_engage_contacts.update_one(query, {"$inc": {"projection_revision": 1}})
        if survivor.matched_count != 1:
            raise ProjectionStopped("Engage contact changed")
        return await operation(current, query)
    return await mutate_suppression(db, binding["workspace_id"], apply)


async def check_contact(db: Database, binding: Document, contact: Document) -> bool:
    async def no_projection(current, query):
        return True
    return await project(db, binding, contact, no_projection)


async def finish_run(db: Database, binding: Document, values: Document) -> bool:
    async def apply(current):
        query = {**run_query(binding), binding["kind"] + "_status": "running"}
        if binding["kind"] == "fetch":
            values["pending_posts_count"] = await current.outreach_engage_posts.count_documents({
                "list_id": binding["id"], **workspace_scope(binding["workspace_id"]), "status": "pending"})
        changed = await current.outreach_engage_lists.update_one(query, {"$set": values})
        return changed.matched_count == 1
    return await mutate_suppression(db, binding["workspace_id"], apply)
