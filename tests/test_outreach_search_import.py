"""
Integration & unit tests for 1-Click LinkedIn Search & Sales Navigator Lead Extraction.
Covers:
1. Worker killed mid-run and resumed without duplicates
2. Concurrent import lock (409 Conflict)
3. Sender circuit breaker trip & sender-level halt
4. Cross-source compound suppression across CSV and Sales Nav copies of one person
5. Zero-lead canary alert (stops cleanly without looping)
6. Commercial use limit handling with dedicated user message
7. Sales Navigator seat preflight enforcement
8. Proxy fails-closed verification (zero direct egress)
9. Staged leads review and campaign commit
10. Cancel import job
"""
import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from cryptography.fernet import Fernet
if not os.environ.get("ENCRYPTION_KEY"):
    os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest
from fastapi import HTTPException

from outreach.api.leads import (
    import_search_url,
    get_import_job,
    cancel_import_job,
    get_staged_leads_for_job,
    commit_staged_leads,
    ImportSearchRequest,
    CommitStagedLeadsRequest,
)
from outreach.core.crypto import encrypt_secret
from outreach.core.lead_importer import build_lead_identifiers
from outreach.models import (
    LeadExecutionState,
    SearchImportJobStatus,
    SearchImportStopReason,
)
from celery_workers.tasks.outreach import _crawl_page, _reap_stale_search_crawlers


class MockCursor:
    def __init__(self, docs):
        self.docs = list(docs)

    async def to_list(self, length=None):
        return self.docs[:length] if length is not None else self.docs


class MockCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, query=None, projection=None):
        query = query or {}
        for d in self.docs:
            match = True
            for k, v in query.items():
                if k == "$or":
                    or_match = False
                    for clause in v:
                        if all(d.get(ck) == cv for ck, cv in clause.items()):
                            or_match = True
                            break
                    if not or_match:
                        match = False
                        break
                elif isinstance(v, dict):
                    if "$in" in v and d.get(k) not in v["$in"]:
                        match = False
                        break
                    if "$ne" in v and d.get(k) == v["$ne"]:
                        match = False
                        break
                    if "$lt" in v and not (d.get(k) and d[k] < v["$lt"]):
                        match = False
                        break
                    if "$gt" in v and not (d.get(k) and d[k] > v["$gt"]):
                        match = False
                        break
                elif d.get(k) != v:
                    match = False
                    break
            if match:
                return dict(d)
        return None

    def find(self, query=None, projection=None):
        query = query or {}
        matched = []
        for d in self.docs:
            match = True
            for k, v in query.items():
                if k == "$or":
                    or_match = False
                    for clause in v:
                        sub_m = True
                        for ck, cv in clause.items():
                            if isinstance(cv, dict) and "$in" in cv:
                                if d.get(ck) not in cv["$in"]:
                                    sub_m = False
                                    break
                            elif d.get(ck) != cv:
                                sub_m = False
                                break
                        if sub_m:
                            or_match = True
                            break
                    if not or_match:
                        match = False
                        break
                elif isinstance(v, dict):
                    if "$in" in v and d.get(k) not in v["$in"]:
                        match = False
                        break
                    if "$ne" in v and d.get(k) == v["$ne"]:
                        match = False
                        break
                    if "$lt" in v and not (d.get(k) and d[k] < v["$lt"]):
                        match = False
                        break
                    if "$gt" in v and not (d.get(k) and d[k] > v["$gt"]):
                        match = False
                        break
                elif d.get(k) != v:
                    match = False
                    break
            if match:
                matched.append(dict(d))
        return MockCursor(matched)

    async def insert_one(self, doc):
        doc = dict(doc)
        if "_id" not in doc and "id" in doc:
            doc["_id"] = doc["id"]
        self.docs.append(doc)
        return MagicMock(inserted_id=doc.get("_id"))

    async def update_one(self, query, update, upsert=False):
        doc = await self.find_one(query)
        if not doc:
            return MagicMock(matched_count=0, modified_count=0)
        idx = next(i for i, d in enumerate(self.docs) if d.get("id") == doc.get("id") or d.get("_id") == doc.get("_id"))
        if "$set" in update:
            self.docs[idx].update(update["$set"])
        if "$inc" in update:
            for ik, iv in update["$inc"].items():
                self.docs[idx][ik] = self.docs[idx].get(ik, 0) + iv
        return MagicMock(matched_count=1, modified_count=1)

    async def find_one_and_update(self, query, update, return_document=None):
        doc = await self.find_one(query)
        if not doc:
            return None
        idx = next(i for i, d in enumerate(self.docs) if d.get("id") == doc.get("id") or d.get("_id") == doc.get("_id"))
        if "$set" in update:
            self.docs[idx].update(update["$set"])
        if "$inc" in update:
            for ik, iv in update["$inc"].items():
                self.docs[idx][ik] = self.docs[idx].get(ik, 0) + iv
        return dict(self.docs[idx])

    async def update_many(self, query, update):
        matched = 0
        for i, d in enumerate(self.docs):
            match = True
            for k, v in query.items():
                if isinstance(v, dict) and "$in" in v:
                    if d.get(k) not in v["$in"]:
                        match = False
                        break
                elif d.get(k) != v:
                    match = False
                    break
            if match:
                matched += 1
                if "$set" in update:
                    self.docs[i].update(update["$set"])
        return MagicMock(matched_count=matched, modified_count=matched)


class MockDatabase:
    def __init__(self):
        self.outreach_campaigns = MockCollection()
        self.outreach_accounts = MockCollection()
        self.outreach_import_jobs = MockCollection()
        self.outreach_leads = MockCollection()
        self.outreach_proxy_leases = MockCollection()
        self.outreach_proxy_inventory = MockCollection()
        self.outreach_do_not_contact = MockCollection()
        self.outreach_withdrawn_invites = MockCollection()
        self.outreach_entitlements = MockCollection()
        self.outreach_action_queue = MockCollection()
        self.outreach_tasks = MockCollection()


@pytest.fixture(autouse=True)
def set_mock_env(monkeypatch):
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "true")


@pytest.fixture
def mock_db():
    db = MockDatabase()
    # Workspace & active campaign
    db.outreach_campaigns.docs.append({
        "id": "camp-1",
        "workspace_id": "ws-1",
        "user_id": "u-1",
        "name": "Q3 Growth Campaign",
        "status": "draft",
        "is_deleted": False,
        "leads_count": 0,
    })
    # Active entitlement
    db.outreach_entitlements.docs.append({
        "workspace_id": "ws-1",
        "status": "active",
        "seats": 2,
        "paid_through": datetime.now(timezone.utc) + timedelta(days=30),
        "payment_source": "manual_verified_invoice",
    })
    # Dedicated proxy inventory & lease
    db.outreach_proxy_inventory.docs.append({
        "_id": "proxy-1",
        "provider": "iproyal",
        "host": "185.190.140.1",
        "port": 10000,
        "username": "user1",
        "password_enc": encrypt_secret("pass1"),
        "status": "available",
        "country_code": "US",
        "expires_at": datetime.now(timezone.utc) + timedelta(days=30),
    })
    db.outreach_proxy_leases.docs.append({
        "_id": "proxy-1",
        "workspace_id": "ws-1",
        "sender_id": "sender-1",
    })
    # Active sender account
    db.outreach_accounts.docs.append({
        "id": "sender-1",
        "workspace_id": "ws-1",
        "user_id": "u-1",
        "account_name": "Test Recruiter",
        "status": "active",
        "premium_product": "sales_navigator",
        "li_at_enc": encrypt_secret("li_at_cookie_val"),
        "jsession_id_enc": encrypt_secret("ajax:12345678"),
        "li_a_enc": encrypt_secret("li_a_sales_nav_cookie"),
        "user_agent": "Mozilla/5.0",
        "is_deleted": False,
        "limits": {"search": 100},
        "hourly_action_cap": 20,
        "daily_action_cap": 100,
        "working_hours_start": "00:00",
        "working_hours_end": "23:59",
        "working_days": [0, 1, 2, 3, 4, 5, 6],
        "min_interval_seconds": 0,
    })
    return db


@pytest.mark.asyncio
async def test_sales_nav_preflight_rejected_for_standard_account(mock_db):
    """Scenario 7: Sender without Sales Nav credentials cannot import Sales Nav URLs."""
    # Create standard sender without li_a or sales_navigator badge
    mock_db.outreach_accounts.docs.append({
        "id": "sender-basic",
        "workspace_id": "ws-1",
        "user_id": "u-1",
        "account_name": "Basic Sender",
        "status": "active",
        "premium_product": None,
        "li_at_enc": encrypt_secret("cookie"),
        "jsession_id_enc": encrypt_secret("ajax:1"),
        "li_a_enc": None,
        "is_deleted": False,
    })
    mock_db.outreach_proxy_leases.docs.append({
        "_id": "proxy-1",
        "workspace_id": "ws-1",
        "sender_id": "sender-basic",
    })

    req = ImportSearchRequest(
        campaign_id="camp-1",
        search_url="https://www.linkedin.com/sales/search/people?query=(recentSearchParam%3A(id%3A123))",
        sender_account_id="sender-basic",
    )
    with pytest.raises(HTTPException) as exc_info:
        await import_search_url(
            req=req,
            current_user={"user_id": "u-1", "workspace_id": "ws-1"},
            db=mock_db,
        )
    assert exc_info.value.status_code == 400
    assert "Sales Navigator seat or session cookie" in exc_info.value.detail


@pytest.mark.asyncio
async def test_concurrent_import_lock(mock_db):
    """Scenario 2: Unique active import lock per sender rejects duplicate concurrent imports."""
    # First active job exists for sender-1
    mock_db.outreach_import_jobs.docs.append({
        "id": "job-existing",
        "workspace_id": "ws-1",
        "campaign_id": "camp-1",
        "sender_account_id": "sender-1",
        "status": "crawling",
    })

    req = ImportSearchRequest(
        campaign_id="camp-1",
        search_url="https://www.linkedin.com/search/results/people/?keywords=engineer",
        sender_account_id="sender-1",
    )
    with pytest.raises(HTTPException) as exc_info:
        await import_search_url(
            req=req,
            current_user={"user_id": "u-1", "workspace_id": "ws-1"},
            db=mock_db,
        )
    assert exc_info.value.status_code == 409
    assert "already running for this sender" in exc_info.value.detail


@pytest.mark.asyncio
async def test_proxy_fails_closed_when_lease_missing(mock_db):
    """Scenario 8: If proxy lease is missing, search import preflight rejects direct host egress."""
    # Delete lease
    mock_db.outreach_proxy_leases.docs.clear()

    req = ImportSearchRequest(
        campaign_id="camp-1",
        search_url="https://www.linkedin.com/search/results/people/?keywords=cto",
        sender_account_id="sender-1",
    )
    with pytest.raises(HTTPException) as exc_info:
        await import_search_url(
            req=req,
            current_user={"user_id": "u-1", "workspace_id": "ws-1"},
            db=mock_db,
        )
    assert exc_info.value.status_code == 400
    assert "dedicated proxy lease" in exc_info.value.detail


@pytest.mark.asyncio
async def test_worker_killed_midrun_and_resumed_without_duplicates(mock_db):
    """Scenario 1: Worker killed mid-run is resumed by watchdog and imports remaining leads without duplicate staged rows."""
    job_id = "job-resume-test"
    initial_lease = "lease-1"
    now = datetime.now(timezone.utc)

    # Simulate existing job where worker crashed after 1 page (cursor=10, 10 leads imported, stale heartbeat)
    mock_db.outreach_import_jobs.docs.append({
        "id": job_id,
        "workspace_id": "ws-1",
        "campaign_id": "camp-1",
        "sender_account_id": "sender-1",
        "search_url": "https://www.linkedin.com/search/results/people/?keywords=founder",
        "search_type": "basic",
        "cursor": 10,
        "page_size": 10,
        "target_count": 20,
        "total_available": 100,
        "leads_imported": 10,
        "duplicates_skipped": 0,
        "dnc_suppressed": 0,
        "withdrawn_cooldown_skipped": 0,
        "unresolvable_skipped": 0,
        "pages_scanned": 1,
        "status": "crawling",
        "lease_token": initial_lease,
        "heartbeat_at": now - timedelta(seconds=240),  # Missed heartbeat (>180s)
    })

    # Page 1 leads already staged
    for i in range(10):
        mock_db.outreach_leads.docs.append({
            "id": f"lead-p1-{i}",
            "workspace_id": "ws-1",
            "campaign_id": "camp-1",
            "first_name": f"Founder{i}",
            "linkedin_url": f"https://www.linkedin.com/in/founder{i}",
            "identifiers": {"vanity_name": f"founder{i}", "normalized_url": f"https://www.linkedin.com/in/founder{i}"},
            "execution_state": "staged",
            "import_job_id": job_id,
            "staged_at": now,
        })

    # Watchdog detects stale worker and issues fresh lease
    with patch("celery_workers.tasks.outreach.crawl_page.delay") as mock_delay:
        reap_res = await _reap_stale_search_crawlers(db=mock_db)
        assert reap_res["reaped"] == 1
        assert mock_delay.call_count == 1
        call_job_id, call_cursor, new_lease = mock_delay.call_args[0]
        assert call_job_id == job_id
        assert call_cursor == 10
        assert new_lease != initial_lease

    # Simulate new worker executing page 2 with new lease
    with patch("celery_workers.tasks.outreach.crawl_page.apply_async") as mock_reschedule:
        crawl_res = await _crawl_page(job_id=job_id, cursor=10, lease_token=new_lease, db=mock_db)
        assert crawl_res["status"] in ("completed", "next_page_scheduled")

    # Verify total leads in job are now 20 and no page 1 leads were duplicated
    job = await mock_db.outreach_import_jobs.find_one({"id": job_id})
    assert job["leads_imported"] == 20
    assert job["status"] == "completed"
    assert job["stop_reason"] == "completed"

    all_staged = [l for l in mock_db.outreach_leads.docs if l.get("import_job_id") == job_id]
    assert len(all_staged) == 20
    urls = [l["linkedin_url"] for l in all_staged]
    assert len(set(urls)) == 20


@pytest.mark.asyncio
async def test_sender_circuit_breaker_trip_on_checkpoint(mock_db):
    """Scenario 3: Checkpoint detection trips the sender circuit breaker and stops import."""
    job_id = "job-checkpoint-test"
    lease_token = "lease-chk"
    mock_db.outreach_import_jobs.docs.append({
        "id": job_id,
        "workspace_id": "ws-1",
        "campaign_id": "camp-1",
        "sender_account_id": "sender-1",
        "search_url": "https://www.linkedin.com/search/results/people/?keywords=checkpoint_canary",
        "search_type": "basic",
        "cursor": 0,
        "page_size": 10,
        "target_count": 50,
        "leads_imported": 0,
        "status": "queued",
        "lease_token": lease_token,
        "heartbeat_at": datetime.now(timezone.utc),
    })

    res = await _crawl_page(job_id=job_id, cursor=0, lease_token=lease_token, db=mock_db)
    assert res["status"] == "stopped"
    assert res["stop_reason"] == "checkpoint"

    # Job is marked stopped
    job = await mock_db.outreach_import_jobs.find_one({"id": job_id})
    assert job["status"] == "stopped"
    assert job["stop_reason"] == "checkpoint"
    assert "security checkpoint detected" in job["user_error_message"].lower()

    # Sender account circuit breaker tripped
    sender = await mock_db.outreach_accounts.find_one({"id": "sender-1"})
    assert sender["status"] == "checkpoint_detected"


@pytest.mark.asyncio
async def test_cross_source_compound_suppression_csv_and_sales_nav(mock_db):
    """Scenario 4: Sales Nav search candidate is suppressed by an existing CSV contact via compound identifiers."""
    # Existing lead from CSV
    mock_db.outreach_leads.docs.append({
        "id": "csv-lead-1",
        "workspace_id": "ws-1",
        "campaign_id": "camp-1",
        "first_name": "Jane",
        "last_name": "Doe",
        "linkedin_url": "https://www.linkedin.com/in/janedoe",
        "identifiers": {
            "vanity_name": "janedoe",
            "normalized_url": "https://www.linkedin.com/in/janedoe",
            "member_urn": "urn:li:member:998877",
            "sales_lead_urn": None,
            "email": None,
        },
        "execution_state": "queued",
        "is_deleted": False,
    })

    job_id = "job-suppress-test"
    lease_token = "lease-sup"
    mock_db.outreach_import_jobs.docs.append({
        "id": job_id,
        "workspace_id": "ws-1",
        "campaign_id": "camp-1",
        "sender_account_id": "sender-1",
        "search_url": "https://www.linkedin.com/sales/search/people?query=test",
        "search_type": "sales_nav",
        "cursor": 0,
        "page_size": 1,
        "target_count": 5,
        "leads_imported": 0,
        "duplicates_skipped": 0,
        "status": "queued",
        "lease_token": lease_token,
        "heartbeat_at": datetime.now(timezone.utc),
    })

    # Mock Voyager client to return a Sales Nav candidate matching the same vanity & member URN
    sales_nav_entity = {
        "raw_name": "Jane Doe",
        "first_name": "Jane",
        "last_name": "Doe",
        "job_title": "VP Engineering",
        "company_name": "Acme Corp",
        "profile_url": "https://www.linkedin.com/sales/lead/ACwAABjanedoe,NAME_SEARCH",
        "vanity_name": "janedoe",
        "member_urn": "urn:li:member:998877",
        "sales_lead_urn": "urn:li:fs_salesProfile:998877",
        "is_unresolvable": False,
    }

    with patch("outreach.engine.voyager_client.LinkedInVoyagerClient.search_people_entities") as mock_search:
        mock_search.return_value = {
            "entities": [sales_nav_entity],
            "total_results": 1,
            "stop_reason": None,
            "user_error_message": None,
        }
        res = await _crawl_page(job_id=job_id, cursor=0, lease_token=lease_token, db=mock_db)

    job = await mock_db.outreach_import_jobs.find_one({"id": job_id})
    assert job["duplicates_skipped"] == 1
    assert job["leads_imported"] == 0


@pytest.mark.asyncio
async def test_zero_lead_canary_alert(mock_db):
    """Scenario 5: Empty search results terminate cleanly without infinite loop."""
    job_id = "job-empty-test"
    lease_token = "lease-empty"
    mock_db.outreach_import_jobs.docs.append({
        "id": job_id,
        "workspace_id": "ws-1",
        "campaign_id": "camp-1",
        "sender_account_id": "sender-1",
        "search_url": "https://www.linkedin.com/search/results/people/?keywords=empty_canary",
        "search_type": "basic",
        "cursor": 0,
        "page_size": 10,
        "target_count": 50,
        "leads_imported": 0,
        "status": "queued",
        "lease_token": lease_token,
        "heartbeat_at": datetime.now(timezone.utc),
    })

    res = await _crawl_page(job_id=job_id, cursor=0, lease_token=lease_token, db=mock_db)
    assert res["status"] == "completed"
    assert res["reason"] == "search_exhausted"

    job = await mock_db.outreach_import_jobs.find_one({"id": job_id})
    assert job["status"] == "completed"
    assert job["stop_reason"] == "search_exhausted"
    assert job["leads_imported"] == 0


@pytest.mark.asyncio
async def test_commercial_use_limit_handling(mock_db):
    """Scenario 6: Commercial Use Limit stops the crawl and sets dedicated user error copy."""
    job_id = "job-cul-test"
    lease_token = "lease-cul"
    mock_db.outreach_import_jobs.docs.append({
        "id": job_id,
        "workspace_id": "ws-1",
        "campaign_id": "camp-1",
        "sender_account_id": "sender-1",
        "search_url": "https://www.linkedin.com/search/results/people/?keywords=commercial_limit_canary",
        "search_type": "basic",
        "cursor": 0,
        "page_size": 10,
        "target_count": 50,
        "leads_imported": 0,
        "status": "queued",
        "lease_token": lease_token,
        "heartbeat_at": datetime.now(timezone.utc),
    })

    res = await _crawl_page(job_id=job_id, cursor=0, lease_token=lease_token, db=mock_db)
    assert res["status"] == "stopped"
    assert res["stop_reason"] == "commercial_use_limit"

    job = await mock_db.outreach_import_jobs.find_one({"id": job_id})
    assert job["status"] == "stopped"
    assert job["stop_reason"] == "commercial_use_limit"
    assert "commercial search limit reached" in job["user_error_message"].lower()


@pytest.mark.asyncio
async def test_staged_leads_review_and_commit_flow(mock_db):
    """Scenario 9: Staged leads can be queried for review, edited, and committed to queued campaign leads."""
    job_id = "job-commit-test"
    mock_db.outreach_import_jobs.docs.append({
        "id": job_id,
        "workspace_id": "ws-1",
        "campaign_id": "camp-1",
        "sender_account_id": "sender-1",
        "status": "completed",
    })

    # Add 2 staged leads
    mock_db.outreach_leads.docs.append({
        "id": "staged-1",
        "workspace_id": "ws-1",
        "campaign_id": "camp-1",
        "first_name": "Bob",
        "last_name": "Smith",
        "execution_state": "staged",
        "import_job_id": job_id,
        "staged_at": datetime.now(timezone.utc),
    })
    mock_db.outreach_leads.docs.append({
        "id": "staged-2",
        "workspace_id": "ws-1",
        "campaign_id": "camp-1",
        "first_name": "Alice",
        "last_name": "Wonder",
        "execution_state": "staged",
        "import_job_id": job_id,
        "staged_at": datetime.now(timezone.utc),
    })

    # 1. Fetch staged leads
    staged_resp = await get_staged_leads_for_job(
        job_id=job_id,
        current_user={"user_id": "u-1", "workspace_id": "ws-1"},
        db=mock_db,
    )
    assert staged_resp["count"] == 2
    assert len(staged_resp["leads"]) == 2

    # 2. Commit with a name override
    commit_req = CommitStagedLeadsRequest(
        selected_lead_ids=["staged-1", "staged-2"],
        name_overrides={"staged-1": "Robert"},
    )
    commit_resp = await commit_staged_leads(
        job_id=job_id,
        req=commit_req,
        current_user={"user_id": "u-1", "workspace_id": "ws-1"},
        db=mock_db,
    )
    assert commit_resp["status"] == "committed"
    assert commit_resp["enrolled_count"] == 2

    # Verify leads updated in DB
    lead1 = await mock_db.outreach_leads.find_one({"id": "staged-1"})
    assert lead1["first_name"] == "Robert"
    assert lead1["execution_state"] == "queued"
    assert lead1["staged_at"] is None

    lead2 = await mock_db.outreach_leads.find_one({"id": "staged-2"})
    assert lead2["execution_state"] == "queued"
    assert lead2["staged_at"] is None

    # Campaign leads_count updated
    camp = await mock_db.outreach_campaigns.find_one({"id": "camp-1"})
    assert camp["leads_count"] == 2


@pytest.mark.asyncio
async def test_cancel_import_job(mock_db):
    """Scenario 10: Gracefully cancel a running import job."""
    job_id = "job-cancel-test"
    mock_db.outreach_import_jobs.docs.append({
        "id": job_id,
        "workspace_id": "ws-1",
        "campaign_id": "camp-1",
        "sender_account_id": "sender-1",
        "status": "crawling",
    })

    cancel_res = await cancel_import_job(
        job_id=job_id,
        current_user={"user_id": "u-1", "workspace_id": "ws-1"},
        db=mock_db,
    )
    assert cancel_res["status"] == "stopped"

    job = await mock_db.outreach_import_jobs.find_one({"id": job_id})
    assert job["status"] == "stopped"
    assert job["stop_reason"] == "cancelled"
