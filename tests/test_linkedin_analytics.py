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


@pytest.mark.asyncio
async def test_fetch_account_feed_and_stats_linkedin_avoids_userinfo(monkeypatch):
    class _FakeLinkedInAuth:
        async def fetch_audience_analytics(self, access_token: str, account: dict, days: int | None = None) -> dict:
            assert access_token == "linkedin-token"
            assert account["platform"] == "linkedin"
            assert days == 30
            return {
                "followers": 321,
                "followers_growth": 12,
                "impressions": 900,
                "reach": 750,
                "analytics_status": "ok",
            }

        async def get_user_profile(self, _access_token: str) -> dict:
            raise AssertionError("LinkedIn analytics should not depend on userinfo")

    monkeypatch.setattr(analytics, "decrypt", lambda value: "linkedin-token")
    monkeypatch.setattr("backend.app.social.linkedin.LinkedInAuth", _FakeLinkedInAuth)

    _feed, engagement = await analytics._fetch_account_feed_and_stats(
        None,
        {
            "platform": "linkedin",
            "account_id": "linkedin-account-1",
            "platform_user_id": "linkedin-user-1",
            "access_token": "encrypted-token",
            "display_name": "LinkedIn Org",
            "platform_username": "linkedin-org",
            "picture_url": "https://example.com/logo.png",
        },
        days=30,
    )

    assert engagement["display_name"] == "LinkedIn Org"
    assert engagement["picture_url"] == "https://example.com/logo.png"
    assert engagement["followers"] == 321
    assert engagement["reach"] == 750
