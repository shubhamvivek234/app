"""Shared fixtures for legacy feature tests.

The paid sender boundary has dedicated lifecycle tests. Older campaign,
Engage and inbox tests isolate that boundary so they can keep exercising
their own sequencing and reconciliation behavior with minimal fake DBs.
"""
from unittest.mock import AsyncMock

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "atomic_dispatch: production transaction authorization over a disposable replica set")


@pytest.fixture(autouse=True)
def legacy_dispatch_fixtures(request, monkeypatch):
    """Old unit fakes isolate the new transaction method, never production code.

    Real transaction tests opt out with the atomic_dispatch marker. Crash drill
    workers run in fresh processes and always use production authorization.
    """
    if not request.node.path.name.startswith("test_outreach") or request.node.get_closest_marker("atomic_dispatch"):
        return
    from outreach.core.request_guard import RequestEnvelope, RequestDenied
    from outreach.core.sender_execution import SenderExecution
    from pymongo import ReturnDocument
    async def legacy(self, owner, request_id, action, parent, clock):
        boundary = await self.db.outreach_sender_execution.find_one_and_update({
            **SenderExecution.scope(self.workspace_id, self.sender_id), "owner_token": owner,
            "status": "in_flight", "physical_request_token": {"$exists": False},
            "permission.latched": False, "permission.credential_generation": self.generation,
            "permission.sources": self.source, "permission.expires_at": {"$gt": clock()},
            "permission.issued_at": {"$lte": clock()}}, {"$set": {"physical_request_token": request_id}},
            return_document=ReturnDocument.AFTER)
        if not boundary:
            raise RequestDenied("sender_owner_changed")
        return {"sender": boundary, "content": await self._authorize_content(action, clock()), "deadlines": []}
    monkeypatch.setattr(RequestEnvelope, "_authorize_dispatch", legacy)
    # Old feature DB fakes isolate suppression transaction persistence too.
    # Real atomic_dispatch tests and fresh crash workers use production code.
    from outreach.core import suppression
    async def legacy_suppression(db, workspace_id, operation):
        return await operation(db)
    monkeypatch.setattr(suppression, "mutate_suppression", legacy_suppression)
    # Erasure lifecycle has opt-in real transaction tests. Older minimal fakes
    # keep testing their historical behavior without an invented production fallback.
    from outreach.core import erasure
    monkeypatch.setattr(erasure, "workspace_is_open", AsyncMock(return_value=True))


@pytest.fixture
def outreach_paid_gate_stub(monkeypatch):
    # Legacy execution tests model a deployment explicitly enabled for live
    # actions; production remains disabled unless the operator opts in.
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")
    ready = AsyncMock(return_value=True)
    entitled = AsyncMock(return_value={"workspace_id": "test", "status": "active", "seats": 1})
    for target in (
        "outreach.core.paid_access.sender_is_ready",
        "outreach.api.campaigns.sender_is_ready",
        "outreach.tasks.sequence_executor.sender_is_ready",
        "outreach.engine.inbox_sync.sender_is_ready",
        "celery_workers.tasks.outreach.sender_is_ready",
        "celery_workers.tasks.engage.sender_is_ready",
    ):
        monkeypatch.setattr(target, ready)
    for target in (
        "outreach.core.paid_access.get_active_entitlement",
        "outreach.api.campaigns.get_active_entitlement",
        "outreach.tasks.sequence_executor.get_active_entitlement",
        "celery_workers.tasks.outreach.get_active_entitlement",
    ):
        monkeypatch.setattr(target, entitled)
    # Legacy feature fakes isolate the new dispatch boundary. Its real behavior
    # and database CAS are covered without this fixture in execution contracts.
    monkeypatch.setattr("outreach.tasks.sequence_executor._preflight_dispatch", AsyncMock(return_value=None))
    monkeypatch.setattr("outreach.tasks.sequence_executor.unresolved_physical", AsyncMock(return_value=None))
    monkeypatch.setattr("outreach.tasks.sequence_executor._approved_content", AsyncMock(return_value=None))
    async def legacy_voice_clip(db, binding):
        import hashlib
        from outreach.core.voice_cloner import generate_mock_voice_wav
        audio = generate_mock_voice_wav()
        return {"_id": "legacy-voice-artifact", "audio_digest": hashlib.sha256(audio).hexdigest(), "generation_id": "legacy-test"}, audio
    monkeypatch.setattr("outreach.tasks.sequence_executor._load_voice_clip", legacy_voice_clip)
    from outreach.tasks import sequence_executor
    advance = sequence_executor._advance_lead

    async def legacy_advance(*args, **kwargs):
        await advance(*args, **kwargs)
        return True

    monkeypatch.setattr(sequence_executor, "_advance_lead", legacy_advance)
    from outreach.core.execution_outbox import ExecutionOutbox
    monkeypatch.setattr(ExecutionOutbox, "ensure", AsyncMock(return_value={"_id": "legacy-feature-intent"}))
    for method in ("claim", "begin_submission", "finish", "defer", "abort_before_call"):
        monkeypatch.setattr(ExecutionOutbox, method, AsyncMock(return_value=True))
    from outreach.core.sender_execution import SenderExecution
    for method in ("acquire", "begin", "release"):
        monkeypatch.setattr(SenderExecution, method, AsyncMock(return_value=True))
    # New integration tests exercise the real lead submission CAS.
    # Legacy fakes already return nonzero mock matched counts for update_one.
    return ready
