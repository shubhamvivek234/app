"""
Slack Pilot Integration Module.
Provides secure Slack Incoming Webhook URL validation, Slack Block Kit card formatting,
test ping delivery, and fail-closed egress via PinnedAsyncNetworkBackend.
"""
from datetime import datetime, timezone
import logging
from typing import Any
from urllib.parse import urlparse

import httpx
from outreach.core.safe_transport import SSRFSecurityError, create_safe_client

logger = logging.getLogger(__name__)

ALLOWED_SLACK_HOSTS = {"hooks.slack.com", "hooks.gov-slack.com"}


def validate_slack_webhook_url(url: str) -> str:
    """
    Strictly validate a Slack Incoming Webhook URL.
    Enforces HTTPS, approved Slack domains, standard /services/ path structure,
    disallows query parameters, URL credentials, and fragments.
    """
    clean_url = url.strip()
    if not clean_url:
        raise ValueError("Slack webhook URL cannot be empty")

    parsed = urlparse(clean_url)
    if parsed.scheme.lower() != "https":
        raise ValueError("Slack webhook URL must use HTTPS")

    if not parsed.hostname or parsed.hostname.lower() not in ALLOWED_SLACK_HOSTS:
        raise ValueError("Slack webhook URL must be hosted on hooks.slack.com or hooks.gov-slack.com")

    if parsed.username or parsed.password:
        raise ValueError("Slack webhook URL must not contain embedded user credentials")

    if not parsed.path.startswith("/services/"):
        raise ValueError("Slack webhook URL path must start with /services/")

    # Standard Slack webhook path has at least 3 parts: /services/T.../B.../X...
    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) < 4:
        raise ValueError("Slack webhook URL is missing expected service/team/token path components")

    if parsed.query or parsed.fragment:
        raise ValueError("Slack webhook URL must not include query parameters or fragments")

    return clean_url


def format_slack_test_card() -> dict[str, Any]:
    """Build a Slack Block Kit card for the test notification ping."""
    return {
        "text": "🎉 *Unravler Outreach Test Alert*\nYour Slack integration is connected and verified!",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🎉 Unravler Outreach Connected",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*Status:* Active & Verified\n"
                        "Real-time notifications for confirmed prospect replies and accepted "
                        "connections will be delivered to this channel."
                    ),
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "🔒 *Egress Security:* DNS-pinned transport • Zero message body leakage",
                    }
                ],
            },
        ],
    }


def format_slack_event_card(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Format a verified event envelope into a clean Slack Block Kit card.
    Strictly avoids leaking private message bodies into Slack (per security spec).
    """
    event_type = payload.get("type", "unknown")
    event_id = payload.get("id", "unknown")
    data = payload.get("data", {})
    occurred_at = payload.get("occurred_at") or datetime.now(timezone.utc).isoformat()

    channel = data.get("channel", "linkedin").upper()
    lead_id = data.get("lead_id", "N/A")
    campaign_id = data.get("campaign_id", "N/A")
    linkedin_url = data.get("linkedin_url")

    # Titles & Emojis based on verified event type
    titles = {
        "lead.replied": ("💬 Prospect Replied", "A prospect has responded to your outreach sequence."),
        "lead.connection_accepted": ("🤝 Connection Accepted", "A prospect accepted your LinkedIn connection request."),
        "campaign.paused": ("⏸️ Campaign Paused", "A campaign execution was paused."),
        "email.accepted": ("✉️ Email Accepted", "An outbound message was accepted by the email provider."),
        "lead.created": ("👤 Lead Enrolled", "A new lead was successfully enrolled into a campaign."),
        "lead.stage_changed": ("📊 Stage Changed", "A prospect's pipeline stage was updated."),
    }

    title, summary = titles.get(event_type, ("📢 Outreach Event", f"Event `{event_type}` occurred."))

    fields = [
        {"type": "mrkdwn", "text": f"*Event:* `{event_type}`"},
        {"type": "mrkdwn", "text": f"*Channel:* `{channel}`"},
        {"type": "mrkdwn", "text": f"*Lead ID:* `{lead_id}`"},
        {"type": "mrkdwn", "text": f"*Campaign ID:* `{campaign_id}`"},
    ]

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": title,
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": summary,
            },
            "fields": fields,
        },
    ]

    # Add LinkedIn action button/link if profile URL is available
    if linkedin_url:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🔗 <{linkedin_url}|View Prospect LinkedIn Profile>",
            },
        })

    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"Event ID: `{event_id}` | Time: {occurred_at} | Verified Production Alert",
            }
        ],
    })

    return {
        "text": f"{title} - Lead {lead_id} ({channel})",
        "blocks": blocks,
    }


async def send_slack_notification(
    webhook_url: str,
    payload: dict[str, Any],
    *,
    client: httpx.AsyncClient | None = None,
    allow_private_for_tests: bool = False,
) -> tuple[bool, int, str | None]:
    """
    Delivers a Block Kit payload to a validated Slack Incoming Webhook URL.
    Returns (success, status_code, error_message).
    """
    validated_url = validate_slack_webhook_url(webhook_url)
    safe_cli = client or create_safe_client(allow_private_for_tests=allow_private_for_tests)
    should_close = client is None

    try:
        resp = await safe_cli.post(
            validated_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        success = (200 <= resp.status_code < 300)
        err = None if success else f"Slack returned HTTP {resp.status_code}: {resp.text[:100]}"
        return success, resp.status_code, err
    except SSRFSecurityError as ssrf_err:
        return False, 403, f"SSRF blocked: {ssrf_err}"
    except httpx.TimeoutException:
        return False, 504, "Slack connection timed out"
    except httpx.NetworkError as net_err:
        return False, 502, f"Network error: {str(net_err)[:100]}"
    except Exception as exc:
        return False, 500, f"Delivery error: {str(exc)[:100]}"
    finally:
        if should_close:
            await safe_cli.aclose()
