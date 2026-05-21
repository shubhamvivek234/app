import pytest

from api.routes import analytics


@pytest.mark.asyncio
async def test_load_social_accounts_for_report_matches_secondary_identifiers(monkeypatch):
    calls = []
    youtube_account = {
        "id": "youtube_user_abc",
        "account_id": "youtube_user_abc",
        "platform": "youtube",
        "platform_user_id": "UC123456",
        "platform_username": "Prodcaster",
        "display_name": "Prodcaster",
    }

    async def fake_load_social_accounts(db, user_id, platform=None, account_id=None):
        calls.append((user_id, platform, account_id))
        if account_id:
            return []
        return [youtube_account]

    monkeypatch.setattr(analytics, "_load_social_accounts", fake_load_social_accounts)

    accounts, fallback_used = await analytics._load_social_accounts_for_report(
        db=None,
        user_id="user_1",
        platform="youtube",
        account_id="Prodcaster",
    )

    assert accounts == [youtube_account]
    assert fallback_used is True
    assert calls == [
        ("user_1", "youtube", "Prodcaster"),
        ("user_1", "youtube", None),
    ]


@pytest.mark.asyncio
async def test_load_social_accounts_for_report_uses_single_account_fallback(monkeypatch):
    calls = []
    youtube_account = {
        "id": "youtube_user_only",
        "account_id": "youtube_user_only",
        "platform": "youtube",
    }

    async def fake_load_social_accounts(db, user_id, platform=None, account_id=None):
        calls.append((user_id, platform, account_id))
        if account_id:
            return []
        return [youtube_account]

    monkeypatch.setattr(analytics, "_load_social_accounts", fake_load_social_accounts)

    accounts, fallback_used = await analytics._load_social_accounts_for_report(
        db=None,
        user_id="user_1",
        platform="youtube",
        account_id="stale_cached_identifier",
    )

    assert accounts == [youtube_account]
    assert fallback_used is True
    assert calls == [
        ("user_1", "youtube", "stale_cached_identifier"),
        ("user_1", "youtube", None),
    ]

