"""
Tests for Outreach Granular RBAC Permissions and Uncertain Action Lockout.

Covers:
1. Workspace-scoped role permissions (Viewer, Editor, Admin, Owner).
2. Direct route-level protection across campaigns, leads, inbox, engage, action-reviews, billing, integrations.
3. Outsider access denial (403 Forbidden).
4. Campaign launch lockout when uncertain tasks exist (P0-C outcome provenance).
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from api.deps import get_current_user, get_db, require_permission
from outreach.api.campaigns import router as campaigns_router, _launch_campaign_impl
from outreach.api.leads import router as leads_router
from outreach.api.inbox import router as inbox_router
from outreach.api.engage import router as engage_router
from outreach.api.billing import router as billing_router
from outreach.api.integrations import router as integrations_router
from outreach.api.action_reconciliation import router as reconciliation_router
from utils.roles import WorkspaceRole, has_permission


# ── Fixtures & Mock Database Setup ──────────────────────────────────────────

def create_mock_db(user_role="viewer", is_member=True, is_owner=False):
    db = MagicMock()

    # User and workspace mock for ensure_active_workspace
    db.users.update_one = AsyncMock()
    db.users.find_one = AsyncMock(return_value=None)
    db.workspaces.insert_one = AsyncMock()
    db.workspaces.update_one = AsyncMock()
    db.workspace_members.insert_one = AsyncMock()

    # Workspace members mock
    if is_member:
        db.workspace_members.find_one = AsyncMock(return_value={"role": user_role, "workspace_id": "ws-1", "user_id": "user-1"})
    else:
        db.workspace_members.find_one = AsyncMock(return_value=None)

    # Workspaces mock
    if is_owner:
        db.workspaces.find_one = AsyncMock(return_value={"workspace_id": "ws-1", "owner_id": "user-1"})
    else:
        db.workspaces.find_one = AsyncMock(return_value=None)

    # Common collections
    db.outreach_campaigns.find_one = AsyncMock(return_value={"id": "camp-1", "workspace_id": "ws-1", "status": "draft"})
    db.outreach_campaigns.update_one = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))
    db.outreach_campaigns.count_documents = AsyncMock(return_value=1)

    db.outreach_leads.find_one = AsyncMock(return_value={"id": "lead-1", "workspace_id": "ws-1"})
    db.outreach_leads.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    db.outreach_leads.count_documents = AsyncMock(return_value=0)

    db.outreach_tasks.find_one = AsyncMock(return_value=None)
    db.outreach_tasks.count_documents = AsyncMock(return_value=0)

    db.outreach_engage_posts.find_one = AsyncMock(return_value={"id": "post-1", "workspace_id": "ws-1", "status": "pending"})
    db.outreach_engage_posts.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    db.outreach_entitlements.find_one = AsyncMock(return_value={
        "workspace_id": "ws-1",
        "status": "active",
        "seats": 1,
        "paid_through": "2029-10-28T00:00:00Z",
        "payment_source": "manual_verified_invoice",
    })
    db.outreach_access_requests.find_one = AsyncMock(return_value=None)

    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.skip = MagicMock(return_value=cursor)
    cursor.limit = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=[])
    db.outreach_webhooks.find = MagicMock(return_value=cursor)
    db.outreach_webhooks.count_documents = AsyncMock(return_value=0)
    db.outreach_api_keys.find = MagicMock(return_value=cursor)
    db.outreach_api_keys.count_documents = AsyncMock(return_value=0)
    db.outreach_integrations.find_one = AsyncMock(return_value=None)

    return db


def create_test_app(db_instance, user_dict):
    app = FastAPI()

    app.include_router(campaigns_router)
    app.include_router(leads_router)
    app.include_router(inbox_router)
    app.include_router(engage_router)
    app.include_router(billing_router)
    app.include_router(integrations_router)
    app.include_router(reconciliation_router)

    app.dependency_overrides[get_current_user] = lambda: user_dict
    app.dependency_overrides[get_db] = lambda: db_instance

    return app


# ── Unit Tests: Granular Role Permissions Matrix ────────────────────────────

def test_roles_permission_matrix():
    """Verify granular outreach permissions across the role hierarchy."""
    # VIEWER
    assert has_permission(WorkspaceRole.VIEWER, "campaign:read")
    assert has_permission(WorkspaceRole.VIEWER, "sequence:read")
    assert has_permission(WorkspaceRole.VIEWER, "lead:read")
    assert has_permission(WorkspaceRole.VIEWER, "inbox:read")
    assert has_permission(WorkspaceRole.VIEWER, "engage:read")
    assert not has_permission(WorkspaceRole.VIEWER, "campaign:create")
    assert not has_permission(WorkspaceRole.VIEWER, "sequence:create")
    assert not has_permission(WorkspaceRole.VIEWER, "lead:create")
    assert not has_permission(WorkspaceRole.VIEWER, "inbox:reply")
    assert not has_permission(WorkspaceRole.VIEWER, "engage:manage")
    assert not has_permission(WorkspaceRole.VIEWER, "account:connect")
    assert not has_permission(WorkspaceRole.VIEWER, "outreach:manage")
    assert not has_permission(WorkspaceRole.VIEWER, "billing:manage")
    assert not has_permission(WorkspaceRole.VIEWER, "webhook:manage")
    assert not has_permission(WorkspaceRole.VIEWER, "api_key:manage")

    # EDITOR
    assert has_permission(WorkspaceRole.EDITOR, "campaign:create")
    assert has_permission(WorkspaceRole.EDITOR, "campaign:update")
    assert has_permission(WorkspaceRole.EDITOR, "sequence:create")
    assert has_permission(WorkspaceRole.EDITOR, "sequence:update")
    assert has_permission(WorkspaceRole.EDITOR, "lead:create")
    assert has_permission(WorkspaceRole.EDITOR, "lead:update")
    assert has_permission(WorkspaceRole.EDITOR, "inbox:reply")
    assert has_permission(WorkspaceRole.EDITOR, "inbox:manage")
    assert has_permission(WorkspaceRole.EDITOR, "engage:manage")
    assert has_permission(WorkspaceRole.EDITOR, "content:manage")
    assert has_permission(WorkspaceRole.EDITOR, "voice:manage")
    # Editor cannot delete campaigns, connect/delete accounts, or manage webhooks/billing/outreach
    assert not has_permission(WorkspaceRole.EDITOR, "campaign:delete")
    assert not has_permission(WorkspaceRole.EDITOR, "account:connect")
    assert not has_permission(WorkspaceRole.EDITOR, "account:delete")
    assert not has_permission(WorkspaceRole.EDITOR, "outreach:manage")
    assert not has_permission(WorkspaceRole.EDITOR, "billing:manage")
    assert not has_permission(WorkspaceRole.EDITOR, "webhook:manage")
    assert not has_permission(WorkspaceRole.EDITOR, "api_key:manage")

    # ADMIN
    assert has_permission(WorkspaceRole.ADMIN, "campaign:delete")
    assert has_permission(WorkspaceRole.ADMIN, "account:connect")
    assert has_permission(WorkspaceRole.ADMIN, "account:delete")
    assert has_permission(WorkspaceRole.ADMIN, "outreach:manage")
    assert has_permission(WorkspaceRole.ADMIN, "webhook:manage")
    assert has_permission(WorkspaceRole.ADMIN, "api_key:manage")

    # OWNER
    assert has_permission(WorkspaceRole.OWNER, "campaign:delete")
    assert has_permission(WorkspaceRole.OWNER, "outreach:manage")
    assert has_permission(WorkspaceRole.OWNER, "billing:manage")
    assert has_permission(WorkspaceRole.OWNER, "webhook:manage")


# ── Route Integration Tests: Viewer Role Denied on Mutations ────────────────

def test_viewer_denied_on_mutations():
    """Viewer receives HTTP 403 on mutation endpoints across all outreach services."""
    user = {"user_id": "user-1", "default_workspace_id": "ws-1", "workspace_ids": ["ws-1"], "email": "viewer@example.com"}
    db = create_mock_db(user_role="viewer")
    app = create_test_app(db, user)
    client = TestClient(app)

    # Campaigns create/update/delete
    resp = client.post("/campaigns", json={"name": "New Campaign"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "lacks permission" in resp.json()["detail"]

    resp = client.delete("/campaigns/camp-1")
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # Leads import
    resp = client.post("/leads/import-search", json={"campaign_id": "camp-1", "search_url": "https://linkedin.com/search"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # Engage actions
    resp = client.post("/engage/posts/post-1/like", json={})
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    resp = client.post("/engage/posts/post-1/discard")
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # Action reviews resolve
    resp = client.post("/action-reviews/lead-1:node-1/resolve", json={
        "decision": "confirmed_sent",
        "evidence_note": "Checked manual sent mailbox",
        "acknowledged": True,
    })
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # Billing
    resp = client.post("/billing/start-trial", json={"seats": 1})
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # Webhooks & API keys
    resp = client.post("/integrations/webhooks", json={"target_url": "https://example.com/webhook", "events": ["lead.replied"]})
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    resp = client.post("/integrations/api-keys", json={"name": "Test Key", "scopes": ["leads:read"]})
    assert resp.status_code == status.HTTP_403_FORBIDDEN


# ── Route Integration Tests: Editor Role Allowed & Denied Boundaries ────────

def test_editor_allowed_and_denied_boundaries():
    """Editor can mutate campaigns, leads, engage, but is 403-forbidden on delete/billing/webhooks/reconciliation."""
    user = {"user_id": "user-1", "default_workspace_id": "ws-1", "workspace_ids": ["ws-1"], "email": "editor@example.com"}
    db = create_mock_db(user_role="editor")
    app = create_test_app(db, user)
    client = TestClient(app)

    # Editor CANNOT delete campaign (requires campaign:delete)
    resp = client.delete("/campaigns/camp-1")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "campaign:delete" in resp.json()["detail"]

    # Editor CANNOT resolve uncertain actions (requires outreach:manage)
    resp = client.post("/action-reviews/lead-1:node-1/resolve", json={
        "decision": "confirmed_sent",
        "evidence_note": "Checked manual sent mailbox",
        "acknowledged": True,
    })
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "outreach:manage" in resp.json()["detail"]

    # Editor CANNOT create webhooks (requires webhook:manage)
    resp = client.post("/integrations/webhooks", json={"target_url": "https://example.com/webhook", "events": ["lead.replied"]})
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "webhook:manage" in resp.json()["detail"]

    # Editor CANNOT create API keys (requires api_key:manage)
    resp = client.post("/integrations/api-keys", json={"name": "Test Key", "scopes": ["leads:read"]})
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "api_key:manage" in resp.json()["detail"]

    # Editor CANNOT modify billing (requires billing:manage)
    resp = client.post("/billing/cancel")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "billing:manage" in resp.json()["detail"]


# ── Route Integration Tests: Outsider Blocked ───────────────────────────────

def test_outsider_blocked():
    """User not present in workspace_members or workspaces is denied with 403."""
    user = {"user_id": "outsider-1", "default_workspace_id": "ws-1", "workspace_ids": ["ws-1"], "email": "outsider@example.com"}
    db = create_mock_db(is_member=False, is_owner=False)
    app = create_test_app(db, user)
    client = TestClient(app)

    resp = client.post("/campaigns", json={"name": "Hacker Campaign"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "not a member of this workspace" in resp.json()["detail"]


# ── Outcome Provenance & Uncertain Task Lockout (P0-C) ──────────────────────

@pytest.mark.asyncio
async def test_launch_campaign_blocks_when_uncertain_tasks_exist():
    """
    P0-C: _launch_campaign_impl prevents launching/resuming any campaign
    if there are unresolved 'uncertain' tasks in db.outreach_tasks.
    """
    now = datetime.now(timezone.utc)
    campaign = {
        "id": "camp-1",
        "workspace_id": "ws-1",
        "name": "Live Outreach",
        "status": "paused",
        "sender_account_ids": ["acc-1"],
        "lead_count": 10,
        "is_deleted": False,
    }

    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value=campaign)
    db.outreach_tasks.count_documents = AsyncMock(return_value=1)
    db.outreach_entitlements.find_one = AsyncMock(return_value={
        "workspace_id": "ws-1",
        "status": "active",
        "seats": 1,
        "paid_through": "2029-01-01T00:00:00Z",
        "payment_source": "manual_verified_invoice",
    })

    with pytest.raises(HTTPException) as exc_info:
        await _launch_campaign_impl(
            campaign_id="camp-1",
            req=None,
            current_user={"user_id": "admin-1", "default_workspace_id": "ws-1", "workspace_ids": ["ws-1"]},
            db=db,
        )

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert "uncertain provider outcomes requiring manual reconciliation" in exc_info.value.detail


@pytest.mark.asyncio
async def test_launch_campaign_clears_pause_reason_when_resolved(monkeypatch):
    """
    P0-C: When no uncertain tasks exist, campaign resumes and clears pause_reason.
    """
    import base64
    from unittest.mock import patch

    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "true")
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", "true")
    monkeypatch.setenv("ENCRYPTION_KEY", base64.urlsafe_b64encode(b"x" * 32).decode())
    from outreach.core.crypto import encrypt_secret

    campaign = {
        "id": "camp-1",
        "workspace_id": "ws-1",
        "name": "Live Outreach",
        "status": "paused",
        "pause_reason": "Manual operator intervention required",
        "sender_account_ids": ["acc-1"],
        "lead_count": 1,
        "is_deleted": False,
        "sequence": [{"id": "step-1", "type": "visit_profile"}],
    }
    account = {
        "id": "acc-1",
        "workspace_id": "ws-1",
        "status": "active",
        "session_cookie_enc": encrypt_secret("li_at=mock_cookie"),
        "jsession_id": "ajax:mock",
        "proxy": {"host": "192.168.1.1"},
        "daily_limits": {"connection_requests": 20, "messages": 50, "profile_views": 80},
    }

    db = MagicMock()
    db.outreach_campaigns.find_one = AsyncMock(return_value=campaign)
    db.outreach_tasks.count_documents = AsyncMock(return_value=0)

    cursor_accounts = MagicMock()
    cursor_accounts.to_list = AsyncMock(return_value=[account])
    db.outreach_accounts.find = MagicMock(return_value=cursor_accounts)

    db.outreach_sequences.find_one = AsyncMock(return_value={
        "campaign_id": "camp-1",
        "workspace_id": "ws-1",
        "nodes": [{"id": "root-1", "type": "visit_profile", "config": {}}],
        "edges": [],
        "is_deleted": False,
    })
    db.outreach_sequences.update_one = AsyncMock()
    db.outreach_campaigns.update_one = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))
    db.outreach_leads.count_documents = AsyncMock(return_value=1)

    cursor_leads = MagicMock()
    cursor_leads.to_list = AsyncMock(return_value=[{"id": "lead-1", "current_node_id": None}])
    db.outreach_leads.find = MagicMock(return_value=cursor_leads)
    db.outreach_leads.update_one = AsyncMock()
    db.outreach_leads.update_many = AsyncMock()

    cursor_empty = MagicMock()
    cursor_empty.to_list = AsyncMock(return_value=[])
    db.outreach_engage_lists.find = MagicMock(return_value=cursor_empty)
    db.outreach_engage_contacts.find = MagicMock(return_value=cursor_empty)

    db.outreach_entitlements.find_one = AsyncMock(return_value={
        "workspace_id": "ws-1",
        "status": "active",
        "seats": 1,
        "paid_through": "2029-01-01T00:00:00Z",
        "payment_source": "manual_verified_invoice",
    })

    with patch("outreach.api.campaigns.sender_is_ready", new_callable=AsyncMock) as mock_ready:
        mock_ready.return_value = True
        result = await _launch_campaign_impl(
            campaign_id="camp-1",
            req=None,
            current_user={"user_id": "admin-1", "default_workspace_id": "ws-1", "workspace_ids": ["ws-1"]},
            db=db,
        )

    assert result["status"] == "launched"
    db.outreach_campaigns.update_one.assert_called_once()
    call_args = db.outreach_campaigns.update_one.call_args[0]
    update_doc = call_args[1]["$set"]
    assert update_doc["status"] == "active"
    assert update_doc["pause_reason"] is None
