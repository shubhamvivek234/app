import pytest
from starlette.requests import Request
from unittest.mock import AsyncMock, MagicMock, patch
from api.routes.support import (
    PublicContactRequest,
    submit_public_contact_request,
)


def _make_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/contact",
        "headers": [(b"user-agent", b"pytest-agent")],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_public_contact_inquiry_dispatches_to_contact_unravler_com():
    body = PublicContactRequest(
        name="Alex Morgan",
        email="alex@acme.io",
        company="Acme Growth",
        topic="Pilot & Dedicated IPs",
        seats="3 sender seats ($177/mo)",
        country="United States",
        message="We would like 3 dedicated US static ISP seats for our outbound team.",
        attachment_name="team-plan.pdf",
        acknowledged_terms=True,
        honeypot="",
    )
    fake_db = MagicMock()
    fake_db.support_tickets.insert_one = AsyncMock(return_value=MagicMock(inserted_id="1"))

    with patch(
        "api.routes.support.send_email_or_raise_async", new_callable=AsyncMock
    ) as mock_send_email:
        mock_send_email.return_value = None
        result = await submit_public_contact_request(
            request=_make_request(), body=body, db=fake_db
        )

    assert result["status"] == "received"
    assert result["recipient_email"] == "contact@unravler.com"
    assert result["ticket_id"].startswith("UNR-")
    assert result["email_dispatched"] is True
    fake_db.support_tickets.insert_one.assert_awaited_once()
    inserted_doc = fake_db.support_tickets.insert_one.call_args[0][0]
    assert inserted_doc["recipient_email"] == "contact@unravler.com"
    assert inserted_doc["email"] == "alex@acme.io"
    assert inserted_doc["seats"] == "3 sender seats ($177/mo)"
    assert inserted_doc["country"] == "United States"
    mock_send_email.assert_awaited_once()
    assert mock_send_email.call_args.kwargs["to"] == "contact@unravler.com"
    assert mock_send_email.call_args.kwargs["reply_to"] == "alex@acme.io"


@pytest.mark.asyncio
async def test_public_contact_honeypot_short_circuits_without_sending_email():
    body = PublicContactRequest(
        name="Bot User",
        email="bot@example.com",
        message="Automated spam payload that is more than ten chars",
        acknowledged_terms=True,
        honeypot="https://spam.example.com",
    )
    fake_db = MagicMock()
    with patch(
        "api.routes.support.send_email_or_raise_async", new_callable=AsyncMock
    ) as mock_send_email:
        result = await submit_public_contact_request(
            request=_make_request(), body=body, db=fake_db
        )
    assert result["status"] == "received"
    mock_send_email.assert_not_awaited()
