import pytest

from api.routes import analytics
from backend.app.social.linkedin import (
    LINKEDIN_ANALYTICS_PERMISSION_MESSAGE,
    LINKEDIN_ANALYTICS_REQUIRED_PERMISSIONS,
    LinkedInAuth,
)


@pytest.mark.asyncio
async def test_linkedin_audience_analytics_reports_permission_required_when_metrics_denied(monkeypatch):
    async def none_metric(*args, **kwargs):
        return None

    async def no_orgs(*args, **kwargs):
        return []

    monkeypatch.setattr(LinkedInAuth, "get_member_follower_total", none_metric)
    monkeypatch.setattr(LinkedInAuth, "get_member_follower_growth", none_metric)
    monkeypatch.setattr(LinkedInAuth, "get_admin_organizations", no_orgs)

    result = await LinkedInAuth().fetch_audience_analytics(
        "token",
        {"scopes": ["openid", "profile", "email", "w_member_social"]},
        days=30,
    )

    assert result["analytics_status"] == "permission_required"
    assert result["analytics_message"] == LINKEDIN_ANALYTICS_PERMISSION_MESSAGE
    assert result["required_permissions"] == LINKEDIN_ANALYTICS_REQUIRED_PERMISSIONS
    assert result["error"] == LINKEDIN_ANALYTICS_PERMISSION_MESSAGE


def test_linkedin_connected_account_normalization_includes_analytics_diagnostics():
    account = {
        "account_id": "linkedin_1",
        "platform": "linkedin",
        "display_name": "LinkedIn Account",
        "followers_count": 42,
    }
    engagement = {
        "analytics_status": "permission_required",
        "analytics_message": LINKEDIN_ANALYTICS_PERMISSION_MESSAGE,
        "required_permissions": LINKEDIN_ANALYTICS_REQUIRED_PERMISSIONS,
    }

    normalized = analytics._normalize_connected_account(account, engagement)

    assert normalized["followers_count"] == 42
    assert normalized["analytics_status"] == "permission_required"
    assert normalized["analytics"]["status"] == "permission_required"
    assert normalized["analytics"]["message"] == LINKEDIN_ANALYTICS_PERMISSION_MESSAGE
    assert normalized["analytics_required_permissions"] == LINKEDIN_ANALYTICS_REQUIRED_PERMISSIONS


def test_linkedin_access_denied_error_message_is_user_actionable():
    message = analytics._analytics_error_message(
        "linkedin",
        Exception('{"status":403,"code":"ACCESS_DENIED","message":"Not enough permissions"}'),
    )

    assert "LinkedIn is connected" in message
    assert "reconnect" in message
