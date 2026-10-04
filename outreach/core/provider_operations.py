"""Provider-local stable operations; only proven non-calls may be reclaimed."""
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from outreach.core.authorization import canonical_hash
from outreach.core.request_guard import current_request_parent, RequestDenied


class ProviderOperations:
    def __init__(self, db, collection: str):
        self.db = db
        self.collection = getattr(db, collection)

    async def prior(self, workspace_id: str, key: str) -> dict | None:
        return await self.collection.find_one({"workspace_id": workspace_id, "_id": key})

    async def claim(self, document: dict) -> bool:
        parent = current_request_parent()
        if not parent:
            raise RequestDenied("provider_context_missing")
        scope = {"workspace_id": document["workspace_id"], "_id": document["_id"]}
        record = {**document, "owner_token": parent.owner, "status": "dispatching", "created_at": datetime.now(timezone.utc)}
        try:
            await self.collection.insert_one(record)
            return True
        except DuplicateKeyError:
            prior = await self.prior(scope["workspace_id"], scope["_id"])
            if not prior or prior.get("status") != "not_submitted":
                return False
            history = {key: value for key, value in prior.items() if key not in {"_id", "non_call_history"}}
            changed = await self.collection.update_one({**scope, "status": "not_submitted", "owner_token": prior["owner_token"]}, {
                "$set": {key: value for key, value in record.items() if key != "_id"},
                "$unset": {"reason": "", "completed_at": ""}, "$push": {"non_call_history": history}})
            return bool(changed.matched_count)

    async def finish(self, workspace_id: str, key: str, result: dict) -> bool:
        parent = current_request_parent()
        changed = await self.collection.update_one({"workspace_id": workspace_id, "_id": key,
            "owner_token": parent.owner if parent else None, "status": "dispatching"}, {
            "$set": {**result, "completed_at": datetime.now(timezone.utc)}})
        return bool(changed.matched_count)

    async def received(self, operation: dict) -> dict | None:
        """Repair a provider result from durable evidence; never repeat HTTP."""
        source = operation.get("source")
        if source not in {"email_send", "email_find"} or not operation.get("credential_generation"):
            return None
        from outreach.core.email_finder import HUNTER_FOUND_URL
        from outreach.core.mailbox_delivery import GMAIL_SEND_URL, GRAPH_SEND_URL
        endpoint = HUNTER_FOUND_URL if source == "email_find" else {"gmail": GMAIL_SEND_URL, "microsoft": GRAPH_SEND_URL}.get(operation.get("provider"))
        method, action = ("GET", "finder") if source == "email_find" else ("POST", "email")
        request_id = canonical_hash([operation["workspace_id"], operation["sender_account_id"], source,
            operation["logical_operation_id"], method, endpoint, action])
        receipt = await self.db.outreach_physical_requests.find_one({"_id": request_id,
            "workspace_id": operation["workspace_id"], "sender_id": operation["sender_account_id"],
            "source": source, "credential_generation": operation["credential_generation"],
            "owner_token": operation.get("owner_token"), "status": "response_received"})
        outcome = (receipt or {}).get("provider_outcome")
        if not isinstance(outcome, dict) or outcome.get("status") not in {"accepted", "found", "not_found", "rejected"}:
            return None
        return {**outcome, **({"accepted_at": receipt["completed_at"]} if outcome["status"] == "accepted" else {})}

    async def repair(self, operation: dict) -> dict | None:
        result = await self.received(operation)
        if not result:
            return None
        result = {**result, "status": "failed" if result["status"] == "rejected" else result["status"]}
        changed = await self.collection.update_one({"_id": operation["_id"], "workspace_id": operation["workspace_id"],
            "owner_token": operation.get("owner_token"), "status": {"$in": ["dispatching", "uncertain"]}}, {
            "$set": {**result, "repaired_from_physical_receipt": True, "completed_at": datetime.now(timezone.utc)}})
        return result if changed.matched_count else None
