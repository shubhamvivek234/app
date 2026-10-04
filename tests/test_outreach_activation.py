from datetime import datetime, timedelta, timezone

import pytest

from outreach.core.activation import claim_activation, release_activation, activation_lead_filter
from tests.outreach_memory import Database


@pytest.mark.asyncio
async def test_two_launchers_cannot_prepare_same_revision():
    campaign = {"id": "c", "workspace_id": "w", "status": "paused", "authorization_revision": 1}
    db = Database(outreach_campaigns=[campaign])
    claim = await claim_activation(db, campaign)
    assert claim and claim["revision"] == 2
    assert await claim_activation(db, campaign) is None
    assert await claim_activation(db, {**campaign, "authorization_revision": 2}) is None
    assert not await release_activation(db, "other", "c", claim["token"])
    assert await release_activation(db, "w", "c", claim["token"])


@pytest.mark.asyncio
async def test_expired_launcher_cannot_overwrite_newer_lead_authorization():
    now = datetime.now(timezone.utc)
    db = Database(outreach_campaigns=[{"id": "c", "workspace_id": "w", "status": "paused",
                                      "authorization_revision": 4, "launch_claim_expires_at": now - timedelta(seconds=1)}],
                  outreach_leads=[{"id": "l", "workspace_id": "w", "campaign_id": "c", "authorized_revision": 4}])
    campaign = await db.outreach_campaigns.find_one({"id": "c"})
    newer = await claim_activation(db, campaign)
    assert newer["revision"] == 5
    await db.outreach_leads.update_many(activation_lead_filter("w", "c", 5), {"$set": {"authorized_revision": 5}})
    await db.outreach_leads.update_many(activation_lead_filter("w", "c", 4), {"$set": {"authorized_revision": 4}})
    assert (await db.outreach_leads.find_one({"id": "l"}))["authorized_revision"] == 5


@pytest.mark.asyncio
async def test_pause_invalidates_launcher_and_other_workspace_cannot_claim():
    db = Database(outreach_campaigns=[{"id": "c", "workspace_id": "w", "status": "draft"}])
    campaign = await db.outreach_campaigns.find_one({"id": "c"})
    assert await claim_activation(db, {**campaign, "workspace_id": "other"}) is None
    claim = await claim_activation(db, campaign)
    await db.outreach_campaigns.update_one({"id": "c"}, {"$inc": {"authorization_revision": 1}, "$set": {"status": "paused"}})
    result = await db.outreach_campaigns.update_one(
        {"id": "c", "workspace_id": "w", "launch_claim_token": claim["token"], "authorization_revision": claim["revision"]},
        {"$set": {"status": "active"}},
    )
    assert result.matched_count == 0


@pytest.mark.asyncio
async def test_launch_binds_null_legacy_metadata_and_initializes_assigned_lead_node(monkeypatch):
    from unittest.mock import AsyncMock
    from outreach.api import campaigns
    from outreach.models import WorkingSchedule
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")
    monkeypatch.setattr(campaigns, "get_active_entitlement", AsyncMock(return_value={"status": "active"}))
    monkeypatch.setattr(campaigns, "sender_is_ready", AsyncMock(return_value=True))
    monkeypatch.setattr(campaigns, "decrypt_secret", lambda value: "real-cookie")
    db = Database(
        outreach_campaigns=[{"id": "c", "workspace_id": "w", "status": "draft", "authorization_revision": 0,
                             "sender_account_ids": ["a"], "schedule": WorkingSchedule().model_dump()}],
        outreach_accounts=[{"id": "a", "workspace_id": "w", "status": "active", "session_cookie_enc": "cipher",
                            "jsession_id": "csrf", "proxy": {"host": "192.0.2.1"}}],
        outreach_sequences=[{"workspace_id": "w", "campaign_id": "c", "nodes": [{"id": "n", "type": "visit_profile"}], "edges": []}],
        outreach_leads=[{"id": "l", "workspace_id": "w", "campaign_id": "c", "assigned_account_id": "a",
                         "execution_state": "queued", "authorized_revision": None, "current_node_id": None}],
    )
    result = await campaigns._launch_campaign_impl("c", None, {"user_id": "u", "default_workspace_id": "w"}, db)
    assert result["status"] == "launched" and result["allocated_leads_count"] == 0
    lead = await db.outreach_leads.find_one({"id": "l"})
    assert (lead["authorized_revision"], lead["sequence_version"], lead["current_node_id"]) == (1, 1, "n")
