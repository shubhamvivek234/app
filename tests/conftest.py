"""Shared fixtures for legacy feature tests.

The paid sender boundary has dedicated lifecycle tests. Older campaign,
Engage and inbox tests isolate that boundary so they can keep exercising
their own sequencing and reconciliation behavior with minimal fake DBs.
"""
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def outreach_paid_gate_stub(monkeypatch):
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
        "celery_workers.tasks.outreach.get_active_entitlement",
    ):
        monkeypatch.setattr(target, entitled)
    return ready
