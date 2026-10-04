"""Sequence authority is an atomic campaign pointer to immutable data."""
from unittest.mock import AsyncMock

import pytest

from outreach.core.sequence_versions import load_sequence, publish_sequence
from tests.outreach_memory import Database


@pytest.mark.asyncio
async def test_projection_failure_cannot_lock_or_lose_published_sequence(monkeypatch):
    db = Database(outreach_campaigns=[{"id": "c", "workspace_id": "w", "status": "draft", "authorization_revision": 0}])
    monkeypatch.setattr(db.outreach_sequences, "insert_one", AsyncMock(side_effect=RuntimeError("projection unavailable")))
    assert await publish_sequence(db, "w", "c", {"nodes": [{"id": "n"}], "compiled_dag": {}}, expected_revision=0)
    assert (await load_sequence(db, "w", "c"))["nodes"] == [{"id": "n"}]
    campaign = await db.outreach_campaigns.find_one({"id": "c"})
    assert not campaign.get("sequence_edit_pending")
    assert campaign["authorization_revision"] == 1


@pytest.mark.asyncio
async def test_active_or_concurrently_modified_campaign_cannot_publish():
    db = Database(outreach_campaigns=[{"id": "c", "workspace_id": "w", "status": "active", "authorization_revision": 3}])
    assert not await publish_sequence(db, "w", "c", {"nodes": []}, expected_revision=3)
    await db.outreach_campaigns.update_one({"id": "c"}, {"$set": {"status": "paused"}})
    assert not await publish_sequence(db, "w", "c", {"nodes": []}, expected_revision=2)
    assert (await db.outreach_campaigns.find_one({"id": "c"})).get("sequence_version_id") is None


@pytest.mark.asyncio
async def test_stale_writer_cannot_replace_newer_immutable_pointer():
    db = Database(outreach_campaigns=[{"id": "c", "workspace_id": "w", "status": "paused", "authorization_revision": 1}])
    assert await publish_sequence(db, "w", "c", {"nodes": [{"id": "first"}]}, expected_revision=1)
    assert await publish_sequence(db, "w", "c", {"nodes": [{"id": "second"}]}, expected_revision=2)
    assert not await publish_sequence(db, "w", "c", {"nodes": [{"id": "late-first"}]}, expected_revision=1)
    assert (await load_sequence(db, "w", "c"))["nodes"][0]["id"] == "second"
    assert await load_sequence(db, "other", "c") is None


@pytest.mark.asyncio
async def test_legacy_missing_revision_is_zero_and_does_not_accept_newer_editor():
    db = Database(outreach_campaigns=[{"id": "c", "workspace_id": "w", "status": "draft"}])
    assert not await publish_sequence(db, "w", "c", {"nodes": []}, expected_revision=9)
    assert not db.outreach_sequence_versions.docs
    assert await publish_sequence(db, "w", "c", {"nodes": []}, expected_revision=0)
