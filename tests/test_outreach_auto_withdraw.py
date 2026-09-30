import pytest
from datetime import datetime, timedelta, timezone
from outreach.core.safety_shield import SafetyShield
from outreach.core.lead_importer import LeadImporter
from outreach.core.rate_budget import RateBudget
from outreach.models import LeadExecutionState
from celery_workers.tasks.outreach import _withdraw_stale_invitations


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def limit(self, n):
        return MockCursor(self.docs[:n])

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        if length is not None:
            return self.docs[:length]
        return self.docs


class MockCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, query=None, projection=None):
        query = query or {}
        results = []
        workspace_id = query.get("workspace_id")
        or_clauses = query.get("$or", [])

        for doc in self.docs:
            if workspace_id and doc.get("workspace_id") != workspace_id:
                continue

            # id check
            if "id" in query:
                q_id = query["id"]
                if isinstance(q_id, dict) and "$in" in q_id:
                    if doc.get("id") not in q_id["$in"]:
                        continue
                elif doc.get("id") != q_id:
                    continue

            # auto_withdraw_enabled check
            if "auto_withdraw_enabled" in query:
                if doc.get("auto_withdraw_enabled") != query["auto_withdraw_enabled"]:
                    continue
            if "status" in query:
                st = query["status"]
                if isinstance(st, dict) and "$in" in st:
                    if doc.get("status") not in st["$in"]:
                        continue
                elif doc.get("status") != st:
                    continue
            if "is_deleted" in query:
                is_del = query["is_deleted"]
                if isinstance(is_del, dict) and "$ne" in is_del:
                    if doc.get("is_deleted") == is_del["$ne"]:
                        continue

            # assigned_account_id check
            if "assigned_account_id" in query:
                assigned = query["assigned_account_id"]
                if isinstance(assigned, dict) and "$in" in assigned:
                    if doc.get("assigned_account_id") not in assigned["$in"]:
                        continue
                elif doc.get("assigned_account_id") != assigned:
                    continue

            # connection status checks
            if "is_connected" in query:
                c_check = query["is_connected"]
                if isinstance(c_check, dict) and "$ne" in c_check:
                    if doc.get("is_connected") == c_check["$ne"]:
                        continue

            if "invitation_withdrawn" in query:
                w_check = query["invitation_withdrawn"]
                if isinstance(w_check, dict) and "$ne" in w_check:
                    if doc.get("invitation_withdrawn") == w_check["$ne"]:
                        continue

            # reinvite_blocked_until check
            if "reinvite_blocked_until" in query:
                rb_check = query["reinvite_blocked_until"]
                if isinstance(rb_check, dict) and "$gt" in rb_check:
                    blocked_until = doc.get("reinvite_blocked_until")
                    if not blocked_until or blocked_until <= rb_check["$gt"]:
                        continue

            if "campaign_id" in query and doc.get("campaign_id") != query["campaign_id"]:
                continue

            if not or_clauses:
                results.append(doc)
                continue

            # Evaluate $or (e.g. compound identifier matching or date matching)
            matched = False
            for clause in or_clauses:
                clause_matched = True
                for k, v in clause.items():
                    target_val = None
                    if "." in k:
                        parts = k.split(".")
                        obj = doc
                        for p in parts:
                            obj = obj.get(p, {}) if isinstance(obj, dict) else None
                        target_val = obj
                    else:
                        target_val = doc.get(k)

                    if isinstance(v, dict) and "$in" in v:
                        in_list = v["$in"]
                        if target_val and any(isinstance(target_val, str) and isinstance(x, str) and target_val.lower() == x.lower() for x in in_list):
                            pass
                        elif target_val in in_list:
                            pass
                        else:
                            clause_matched = False
                            break
                    elif isinstance(v, dict) and "$lte" in v:
                        if target_val is None or target_val > v["$lte"]:
                            clause_matched = False
                            break
                    elif target_val != v:
                        clause_matched = False
                        break
                if clause_matched:
                    matched = True
                    break

            if matched:
                results.append(doc)

        return MockCursor(results)

    async def find_one(self, query=None):
        cursor = self.find(query)
        docs = await cursor.to_list()
        return docs[0] if docs else None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return type("InsertResult", (), {"inserted_id": doc.get("id") or "id-1"})()

    async def insert_many(self, docs):
        self.docs.extend([dict(d) for d in docs])

    async def update_one(self, filter_q, update_q, upsert=False):
        doc = await self.find_one(filter_q)
        if doc:
            if "$set" in update_q:
                doc.update(update_q["$set"])
            return type("UpdateResult", (), {"modified_count": 1})()
        elif upsert:
            new_doc = dict(update_q.get("$set", {}))
            self.docs.append(new_doc)
            return type("UpdateResult", (), {"modified_count": 1})()
        return type("UpdateResult", (), {"modified_count": 0})()

    async def update_many(self, filter_q, update_q):
        cursor = self.find(filter_q)
        docs = await cursor.to_list()
        for doc in docs:
            if "$set" in update_q:
                doc.update(update_q["$set"])
        return type("UpdateResult", (), {"modified_count": len(docs)})()

    async def count_documents(self, filter_q):
        cursor = self.find(filter_q)
        docs = await cursor.to_list()
        return len(docs)


class MockDB:
    def __init__(self):
        self.outreach_accounts = MockCollection()
        self.outreach_leads = MockCollection()
        self.outreach_withdrawn_invites = MockCollection()
        self.outreach_campaigns = MockCollection()
        self.outreach_sequences = MockCollection()
        self.outreach_do_not_contact = MockCollection()


@pytest.mark.asyncio
async def test_auto_withdraw_disabled_sender_returns_zero():
    """Disabled auto_withdraw_enabled should perform 0 withdrawals."""
    db = MockDB()
    account_id = "acc-disabled"
    workspace_id = "ws-1"

    await db.outreach_accounts.insert_one({
        "id": account_id,
        "workspace_id": workspace_id,
        "status": "active",
        "auto_withdraw_enabled": False,
        "withdraw_after_days": 21,
    })

    # Add a stale lead
    now = datetime.now(timezone.utc)
    stale_date = now - timedelta(days=25)
    await db.outreach_leads.insert_one({
        "id": "lead-1",
        "workspace_id": workspace_id,
        "assigned_account_id": account_id,
        "is_connected": False,
        "invitation_withdrawn": False,
        "waiting_for_connection_at": stale_date,
    })

    count = await SafetyShield.withdraw_stale_invitations(
        account_id=account_id,
        db=db,
        workspace_id=workspace_id,
    )
    assert count == 0
    # Lead must not be withdrawn
    lead = await db.outreach_leads.find_one({"id": "lead-1"})
    assert lead.get("invitation_withdrawn") is not True


@pytest.mark.asyncio
async def test_auto_withdraw_stopped_sender_is_skipped():
    """Checkpointed/stopped sender must be skipped without taking actions."""
    db = MockDB()
    account_id = "acc-stopped"
    workspace_id = "ws-1"

    await db.outreach_accounts.insert_one({
        "id": account_id,
        "workspace_id": workspace_id,
        "status": "checkpoint_detected",
        "auto_withdraw_enabled": True,
        "withdraw_after_days": 21,
    })

    now = datetime.now(timezone.utc)
    stale_date = now - timedelta(days=30)
    await db.outreach_leads.insert_one({
        "id": "lead-stale",
        "workspace_id": workspace_id,
        "assigned_account_id": account_id,
        "is_connected": False,
        "invitation_withdrawn": False,
        "waiting_for_connection_at": stale_date,
    })

    count = await SafetyShield.withdraw_stale_invitations(
        account_id=account_id,
        db=db,
        workspace_id=workspace_id,
    )
    assert count == 0
    lead = await db.outreach_leads.find_one({"id": "lead-stale"})
    assert lead.get("invitation_withdrawn") is not True


@pytest.mark.asyncio
async def test_auto_withdraw_stale_invites_within_rate_budget():
    """Active opted-in sender withdraws stale invites up to limit and records block."""
    db = MockDB()
    account_id = "acc-active"
    workspace_id = "ws-1"

    await db.outreach_accounts.insert_one({
        "id": account_id,
        "workspace_id": workspace_id,
        "status": "active",
        "auto_withdraw_enabled": True,
        "withdraw_after_days": 21,
        "max_daily_withdrawals": 2,  # Cap at 2
        "min_interval_seconds": 0,   # Allow instant batch processing in test
    })

    now = datetime.now(timezone.utc)
    stale_date = now - timedelta(days=25)
    fresh_date = now - timedelta(days=10)

    # 3 stale leads, 1 fresh lead
    for i in range(1, 4):
        await db.outreach_leads.insert_one({
            "id": f"lead-stale-{i}",
            "workspace_id": workspace_id,
            "assigned_account_id": account_id,
            "linkedin_url": f"https://www.linkedin.com/in/stale-user-{i}",
            "vanity_name": f"stale-user-{i}",
            "is_connected": False,
            "invitation_withdrawn": False,
            "waiting_for_connection_at": stale_date,
            "execution_state": "in_progress",
        })

    await db.outreach_leads.insert_one({
        "id": "lead-fresh",
        "workspace_id": workspace_id,
        "assigned_account_id": account_id,
        "linkedin_url": "https://www.linkedin.com/in/fresh-user",
        "vanity_name": "fresh-user",
        "is_connected": False,
        "invitation_withdrawn": False,
        "waiting_for_connection_at": fresh_date,
        "execution_state": "in_progress",
    })

    count = await SafetyShield.withdraw_stale_invitations(
        account_id=account_id,
        db=db,
        workspace_id=workspace_id,
    )

    # Should have withdrawn exactly 2 due to max_daily_withdrawals cap
    assert count == 2

    # Check outreach_withdrawn_invites records
    withdrawn_records = db.outreach_withdrawn_invites.docs
    assert len(withdrawn_records) == 2
    for record in withdrawn_records:
        assert record["workspace_id"] == workspace_id
        assert record["account_id"] == account_id
        # Reinvite blocked for 21 days
        assert record["reinvite_blocked_until"] > now + timedelta(days=20)

    # Fresh lead must remain unaffected
    fresh_lead = await db.outreach_leads.find_one({"id": "lead-fresh"})
    assert fresh_lead.get("invitation_withdrawn") is not True

    # Withdrawn leads should have execution_state=finished
    w1 = await db.outreach_leads.find_one({"id": "lead-stale-1"})
    assert w1["invitation_withdrawn"] is True
    assert w1["execution_state"] == LeadExecutionState.FINISHED.value


@pytest.mark.asyncio
async def test_reimport_suppression_blocks_withdrawn_leads():
    """LeadImporter preview and ingest must reject leads with active withdrawn cooldown."""
    db = MockDB()
    workspace_id = "ws-cooldown"
    campaign_id = "camp-1"

    now = datetime.now(timezone.utc)
    # Add a withdrawn invite with block ending in 15 days
    await db.outreach_withdrawn_invites.insert_one({
        "workspace_id": workspace_id,
        "account_id": "acc-1",
        "vanity_name": "alex-cooldown",
        "linkedin_url": "https://www.linkedin.com/in/alex-cooldown",
        "withdrawn_at": now - timedelta(days=6),
        "reinvite_blocked_until": now + timedelta(days=15),
    })

    importer = LeadImporter()

    # Test preview_leads
    preview_csv = (
        "LinkedIn URL,First Name,Last Name\n"
        "https://www.linkedin.com/in/alex-cooldown,Alex,Cooldown\n"
        "https://www.linkedin.com/in/sarah-allowed,Sarah,Allowed\n"
    )

    parsed_leads = importer.parse_csv_content(preview_csv)
    preview_res = await importer.preview_leads(
        leads=parsed_leads,
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        db=db,
    )

    assert preview_res["valid_count"] == 1
    assert preview_res["withdrawn_count"] == 1
    rejected_row = next(r for r in preview_res["rows"] if r["rejection_code"] == "withdrawn_cooldown")
    assert rejected_row["vanity_name"] == "alex-cooldown"
    assert "21 days" in rejected_row["error_reason"]

    # Test ingest_leads
    valid_lead = {
        "linkedin_url": "https://www.linkedin.com/in/sarah-allowed",
        "first_name": "Sarah",
        "last_name": "Allowed",
        "vanity_name": "sarah-allowed",
    }
    withdrawn_lead = {
        "linkedin_url": "https://www.linkedin.com/in/alex-cooldown",
        "first_name": "Alex",
        "last_name": "Cooldown",
        "vanity_name": "alex-cooldown",
    }

    ingest_res = await importer.ingest_leads(
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        leads=[valid_lead, withdrawn_lead],
        db=db,
        include_rejections=True,
    )

    assert ingest_res["imported_count"] == 1
    assert ingest_res["skipped_count"] == 1
    rejection = ingest_res["rejections"][0]
    assert rejection["rejection_code"] == "withdrawn_cooldown"


@pytest.mark.asyncio
async def test_celery_periodic_worker_withdraw_stale_invitations():
    """Celery periodic task runner finds opted-in active senders and processes withdrawals."""
    db = MockDB()
    workspace_id = "ws-celery"

    # Sender 1: Opted in and active
    await db.outreach_accounts.insert_one({
        "id": "sender-opted-in",
        "workspace_id": workspace_id,
        "status": "active",
        "auto_withdraw_enabled": True,
        "withdraw_after_days": 21,
        "max_daily_withdrawals": 10,
    })

    # Sender 2: Opted out
    await db.outreach_accounts.insert_one({
        "id": "sender-opted-out",
        "workspace_id": workspace_id,
        "status": "active",
        "auto_withdraw_enabled": False,
    })

    # Sender 3: Deleted
    await db.outreach_accounts.insert_one({
        "id": "sender-deleted",
        "workspace_id": workspace_id,
        "status": "active",
        "auto_withdraw_enabled": True,
        "is_deleted": True,
    })

    # Add stale lead for sender 1
    now = datetime.now(timezone.utc)
    stale_date = now - timedelta(days=22)
    await db.outreach_leads.insert_one({
        "id": "lead-celery-1",
        "workspace_id": workspace_id,
        "assigned_account_id": "sender-opted-in",
        "linkedin_url": "https://www.linkedin.com/in/celery-stale-lead",
        "vanity_name": "celery-stale-lead",
        "is_connected": False,
        "invitation_withdrawn": False,
        "waiting_for_connection_at": stale_date,
    })

    result = await _withdraw_stale_invitations(db=db)
    assert result["processed_senders"] == 1
    assert result["total_withdrawn"] == 1


@pytest.mark.asyncio
async def test_rate_budget_off_peak_withdraw_permits_withdraw_blocks_outbound():
    """Rate budget allows maintenance withdrawals off-peak but blocks outbound connection requests."""
    account_config = {
        "id": "sender-off-peak",
        "working_hours_start": "09:00",
        "working_hours_end": "17:00",
        "sender_timezone": "UTC",
        "daily_action_cap": 50,
        "hourly_action_cap": 10,
        "min_interval_seconds": 0,
    }
    # 2:30 AM UTC - Off peak
    off_peak_time = datetime(2026, 9, 30, 2, 30, 0, tzinfo=timezone.utc)

    # 1. Outbound connection_request should be blocked as before_working_hours
    allowed, retry_after, reason = await RateBudget.acquire_token(
        sender_id="sender-off-peak",
        sender_config=account_config,
        action_type="connection_request",
        now=off_peak_time,
    )
    assert allowed is False
    assert reason == "before_working_hours"
    assert retry_after > 0

    # 2. Maintenance withdraw should be permitted off-peak
    allowed_w, retry_after_w, reason_w = await RateBudget.acquire_token(
        sender_id="sender-off-peak",
        sender_config=account_config,
        action_type="withdraw",
        now=off_peak_time,
    )
    assert allowed_w is True
    assert reason_w == "ok"
    assert retry_after_w == 0

