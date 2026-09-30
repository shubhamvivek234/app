import pytest
from datetime import datetime, timezone, timedelta
from outreach.core.circuit_breaker import CircuitBreaker, parse_stop_reason, get_default_cooldown_hours
from outreach.models import AccountStatus, CampaignStatus, StopReason


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length=None):
        return self.docs


class MockCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, query=None):
        query = query or {}
        results = []
        for d in self.docs:
            match = True
            for k, v in query.items():
                if isinstance(v, dict) and "$in" in v:
                    if d.get(k) not in v["$in"]:
                        match = False
                        break
                elif isinstance(d.get(k), list):
                    if v not in d.get(k):
                        match = False
                        break
                elif d.get(k) != v:
                    match = False
                    break
            if match:
                results.append(d)
        return MockCursor(results)

    async def find_one(self, query=None):
        cursor = self.find(query)
        docs = await cursor.to_list()
        return docs[0] if docs else None

    async def update_one(self, query, update, upsert=False):
        doc = await self.find_one(query)
        if doc:
            if "$set" in update:
                doc.update(update["$set"])
            return type("UpdateResult", (), {"modified_count": 1})()
        elif upsert:
            new_doc = dict(query)
            if "$set" in update:
                new_doc.update(update["$set"])
            self.docs.append(new_doc)
            return type("UpdateResult", (), {"modified_count": 1})()
        return type("UpdateResult", (), {"modified_count": 0})()

    async def update_many(self, query, update):
        cursor = self.find(query)
        docs = await cursor.to_list()
        count = 0
        for doc in docs:
            if "$set" in update:
                doc.update(update["$set"])
                count += 1
        return type("UpdateResult", (), {"modified_count": count})()

    async def count_documents(self, query):
        cursor = self.find(query)
        docs = await cursor.to_list()
        return len(docs)


class MockDB:
    def __init__(self):
        self.outreach_accounts = MockCollection()
        self.outreach_tasks = MockCollection()
        self.outreach_campaigns = MockCollection()
        self.outreach_event_outbox = MockCollection()


def test_parse_stop_reasons():
    assert parse_stop_reason(status_code=429) == StopReason.RATE_LIMITED_429
    assert parse_stop_reason(status_code=999) == StopReason.SECURITY_CHALLENGE_999
    assert parse_stop_reason(status_code=403) == StopReason.SESSION_EXPIRED
    assert parse_stop_reason(response_text="LinkedIn captcha challenge") == StopReason.CHECKPOINT_CAPTCHA
    assert parse_stop_reason(response_text="Commercial use limit reached") == StopReason.COMMERCIAL_LIMIT
    assert parse_stop_reason(status_code=200, response_text="Success") is None


@pytest.mark.asyncio
async def test_trip_circuit_breaker_on_429():
    db = MockDB()
    sender_id = "sender-429"
    workspace_id = "ws-test"

    # Seed sender, tasks, and campaign
    db.outreach_accounts.docs.append({
        "id": sender_id,
        "workspace_id": workspace_id,
        "status": "active",
    })
    db.outreach_tasks.docs.extend([
        {"id": "task-1", "assigned_account_id": sender_id, "workspace_id": workspace_id, "status": "pending"},
        {"id": "task-2", "assigned_account_id": sender_id, "workspace_id": workspace_id, "status": "pending"},
    ])
    db.outreach_campaigns.docs.append({
        "id": "camp-1",
        "workspace_id": workspace_id,
        "sender_account_ids": [sender_id],
        "status": CampaignStatus.ACTIVE.value,
    })

    result = await CircuitBreaker.trip_circuit_breaker(
        sender_id=sender_id,
        reason=StopReason.RATE_LIMITED_429,
        db=db,
        workspace_id=workspace_id,
    )

    assert result["status"] == "checkpoint_detected"
    assert result["stop_reason"] == StopReason.RATE_LIMITED_429.value
    assert result["tasks_paused"] == 2
    assert result["campaigns_paused"] == 1

    # Check sender in DB
    sender = await db.outreach_accounts.find_one({"id": sender_id})
    assert sender["status"] == AccountStatus.CHECKPOINT_DETECTED.value
    assert sender["stop_reason"] == StopReason.RATE_LIMITED_429.value
    assert sender["cooldown_until"] > datetime.now(timezone.utc)

    # Check tasks in DB
    tasks = await db.outreach_tasks.find({"assigned_account_id": sender_id}).to_list()
    assert all(t["status"] == "paused" for t in tasks)

    # Check campaign in DB
    camp = await db.outreach_campaigns.find_one({"id": "camp-1"})
    assert camp["status"] == CampaignStatus.PAUSED.value


@pytest.mark.asyncio
async def test_resume_sender_cooldown_enforcement():
    db = MockDB()
    sender_id = "sender-cooldown"
    workspace_id = "ws-test"

    # Seed stopped sender with active cooldown
    cooldown = datetime.now(timezone.utc) + timedelta(hours=12)
    db.outreach_accounts.docs.append({
        "id": sender_id,
        "workspace_id": workspace_id,
        "status": AccountStatus.CHECKPOINT_DETECTED.value,
        "stop_reason": StopReason.RATE_LIMITED_429.value,
        "cooldown_until": cooldown,
    })
    db.outreach_tasks.docs.append({
        "id": "task-1",
        "assigned_account_id": sender_id,
        "workspace_id": workspace_id,
        "status": "paused",
    })

    # Resume without force: must raise ValueError due to active cooldown
    with pytest.raises(ValueError, match="mandatory platform cooldown"):
        await CircuitBreaker.resume_sender(sender_id=sender_id, workspace_id=workspace_id, db=db, force=False)

    # Resume with force=True: succeeds!
    res = await CircuitBreaker.resume_sender(sender_id=sender_id, workspace_id=workspace_id, db=db, force=True)
    assert res["status"] == "active"
    assert res["tasks_resumed"] == 1

    sender = await db.outreach_accounts.find_one({"id": sender_id})
    assert sender["status"] == "active"
    assert sender["stop_reason"] is None
    assert sender["cooldown_until"] is None
