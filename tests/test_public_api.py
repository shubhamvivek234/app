import pytest
from datetime import datetime, timezone

from api.routes import public_api as public_route
from utils.developer_tokens import (
    PUBLIC_SCOPES_IN_ORDER,
    PUBLIC_SCOPE_PERMISSIONS,
    allowed_public_scopes_for_role,
    normalize_requested_scopes,
)
from utils.roles import WorkspaceRole


def test_public_scopes_include_webhooks_and_approval():
    assert "webhooks:manage" in PUBLIC_SCOPES_IN_ORDER
    assert PUBLIC_SCOPE_PERMISSIONS["webhooks:manage"] == "webhook:manage"
    assert PUBLIC_SCOPE_PERMISSIONS["approval:write"] == "approval:decide"


def test_allowed_public_scopes_for_roles():
    owner_scopes = allowed_public_scopes_for_role(WorkspaceRole.OWNER)
    assert "posts:write" in owner_scopes
    assert "webhooks:manage" in owner_scopes
    assert "approval:write" in owner_scopes

    admin_scopes = allowed_public_scopes_for_role(WorkspaceRole.ADMIN)
    assert "posts:write" in admin_scopes
    assert "webhooks:manage" in admin_scopes

    editor_scopes = allowed_public_scopes_for_role(WorkspaceRole.EDITOR)
    assert "posts:write" in editor_scopes
    assert "webhooks:manage" not in editor_scopes

    client_scopes = allowed_public_scopes_for_role(WorkspaceRole.CLIENT)
    assert "approval:read" in client_scopes
    assert "approval:write" in client_scopes
    assert "posts:write" not in client_scopes


def test_public_create_post_request_model():
    now = datetime.now(timezone.utc)
    req = public_route.PublicCreatePostRequest(
        content="Public post test",
        account_ids=["acc_1"],
        scheduled_time=now,
        timeslot_category="Category 1",
    )
    assert req.content == "Public post test"
    assert req.scheduled_time == now
    assert req.timeslot_category == "Category 1"
