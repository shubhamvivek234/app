from unittest.mock import MagicMock, patch
import pytest

from utils.email_service import (
    EmailConfigurationError,
    EmailDeliveryError,
    get_email_provider,
    get_email_service_status,
    send_email_async,
    send_email_or_raise_async,
)
from utils.notification_emails import (
    _build_notification_html,
    _build_notification_subject,
    _button_label_for_event,
    send_notification_email_async,
)
from utils.notification_prefs import should_notify


def test_get_email_provider_resolution(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "ses")
    assert get_email_provider() == "ses"

    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    assert get_email_provider() == "resend"

    monkeypatch.setenv("EMAIL_PROVIDER", "mock")
    assert get_email_provider() == "mock"

    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("AWS_SES_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SES_REGION", raising=False)
    # Default without any env is ses
    assert get_email_provider() == "ses"

    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    assert get_email_provider() == "resend"

    monkeypatch.setenv("AWS_SES_REGION", "eu-north-1")
    assert get_email_provider() == "ses"


def test_get_email_service_status_ses(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "ses")
    monkeypatch.delenv("SENDER_EMAIL", raising=False)
    monkeypatch.delenv("AWS_SES_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SES_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setenv("AWS_SES_REGION", "eu-north-1")

    status = get_email_service_status()
    assert status["provider"] == "ses"
    assert status["configured"] is False
    assert "SENDER_EMAIL" in status["missing"]

    monkeypatch.setenv("SENDER_EMAIL", "notifications@unravler.com")
    status = get_email_service_status()
    assert status["configured"] is True
    assert status["custom_sender_configured"] is True
    assert status["region"] == "eu-north-1"


@pytest.mark.asyncio
async def test_send_email_via_ses_boto3(monkeypatch):
    mock_boto_client = MagicMock()
    mock_boto_client.send_email.return_value = {"MessageId": "ses-msg-12345"}
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_boto_client

    monkeypatch.setenv("EMAIL_PROVIDER", "ses")
    monkeypatch.setenv("SENDER_EMAIL", "notifications@unravler.com")
    monkeypatch.setenv("SENDER_NAME", "Unravler")
    monkeypatch.setenv("AWS_SES_REGION", "eu-north-1")

    with patch.dict("sys.modules", {"boto3": mock_boto3}):
        success = await send_email_async(
            to="recipient@example.com",
            subject="Test SES Email",
            html="<p>Hello world</p>",
            text="Hello world",
        )

        assert success is True
        mock_boto3.client.assert_called_once_with("ses", region_name="eu-north-1")
        mock_boto_client.send_email.assert_called_once()
        call_kwargs = mock_boto_client.send_email.call_args[1]
        assert call_kwargs["Source"] == "Unravler <notifications@unravler.com>"
        assert call_kwargs["Destination"]["ToAddresses"] == ["recipient@example.com"]
        assert call_kwargs["Message"]["Subject"]["Data"] == "Test SES Email"
        assert call_kwargs["Message"]["Body"]["Html"]["Data"] == "<p>Hello world</p>"
        assert call_kwargs["Message"]["Body"]["Text"]["Data"] == "Hello world"


@pytest.mark.asyncio
async def test_send_email_via_ses_error_handling(monkeypatch):
    mock_boto_client = MagicMock()
    mock_boto_client.send_email.side_effect = RuntimeError("AWS SES rate exceeded")
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_boto_client

    monkeypatch.setenv("EMAIL_PROVIDER", "ses")
    monkeypatch.setenv("SENDER_EMAIL", "notifications@unravler.com")
    monkeypatch.setenv("AWS_SES_REGION", "eu-north-1")

    with patch.dict("sys.modules", {"boto3": mock_boto3}):
        success = await send_email_async(
            to="recipient@example.com",
            subject="Test Fail",
            html="<p>Fail</p>",
            text="Fail",
        )
        assert success is False

        with pytest.raises(EmailDeliveryError):
            await send_email_or_raise_async(
                to="recipient@example.com",
                subject="Test Fail",
                html="<p>Fail</p>",
                text="Fail",
            )


@pytest.mark.asyncio
async def test_send_email_via_resend_fallback(monkeypatch):
    mock_resend = MagicMock()
    mock_resend.Emails.send.return_value = {"id": "resend-msg-999"}

    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key_123")
    monkeypatch.setenv("SENDER_EMAIL", "notifications@unravler.com")

    with patch.dict("sys.modules", {"resend": mock_resend}):
        success = await send_email_async(
            to="creator@example.com",
            subject="Welcome!",
            html="<p>Welcome</p>",
            text="Welcome",
        )
        assert success is True
        mock_resend.Emails.send.assert_called_once()
        params = mock_resend.Emails.send.call_args[0][0]
        assert params["to"] == ["creator@example.com"]
        assert params["from"] == "Unravler <notifications@unravler.com>"


def test_user_welcome_email_template_rendering():
    subject = _build_notification_subject("user.welcome", "")
    assert "Welcome to Unravler" in subject

    button = _button_label_for_event("user.welcome")
    assert "Get Started" in button

    html = _build_notification_html(
        event="user.welcome",
        title="Welcome to Unravler!",
        message="Your multi-platform workspace is ready.",
        action_url="https://app.unravler.com/dashboard",
        display_name="Jordan",
    )
    assert "Welcome" in html
    assert "Jordan" in html
    assert "Your multi-platform workspace is ready." in html
    assert "Get Started &amp; Connect Accounts" in html or "Get Started & Connect Accounts" in html


@pytest.mark.asyncio
async def test_should_notify_permits_user_welcome():
    class DummyDB:
        pass

    assert await should_notify(DummyDB(), "user-123", "user.welcome", "email") is True
    assert await should_notify(DummyDB(), "user-123", "user.welcome", "in_app") is True


@pytest.mark.asyncio
async def test_bootstrap_user_enqueues_welcome_email():
    from unittest.mock import AsyncMock
    from api.deps import _bootstrap_user_from_claims

    mock_db = MagicMock()
    mock_db.users = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=None)
    mock_db.users.insert_one = AsyncMock()

    mock_task = MagicMock()
    with patch("celery_workers.tasks.notifications.send_notification_email_task.delay", mock_task):
        claims = {
            "uid": "fb-new-user-123",
            "email": "newuser@example.com",
            "name": "New User",
        }
        user_doc = await _bootstrap_user_from_claims(mock_db, claims)

        assert user_doc["email"] == "newuser@example.com"
        mock_db.users.insert_one.assert_called_once()
        mock_task.assert_called_once()
        kwargs = mock_task.call_args[1]
        assert kwargs["event"] == "user.welcome"
        assert kwargs["user_id"] == user_doc["user_id"]

