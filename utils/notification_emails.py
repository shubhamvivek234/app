"""
Transactional notification emails generator and sender.
Dispatches branded emails for critical events:
- post.failed / post.dlq
- account.reconnect_required
- subscription.expiring
- billing.failed
- approval.overdue
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
from typing import Any

from utils.frontend_urls import DEFAULT_FRONTEND_URL, build_frontend_url, resolve_frontend_base_url

logger = logging.getLogger(__name__)


def _clean_env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def get_notification_email_config() -> dict[str, Any]:
    resend_api_key = _clean_env("RESEND_API_KEY")
    sender_email = _clean_env("SENDER_EMAIL")
    sender_name = _clean_env("SENDER_NAME", "Unravler") or "Unravler"
    frontend_url = resolve_frontend_base_url(_clean_env("FRONTEND_URL", DEFAULT_FRONTEND_URL))
    logo_url = _clean_env("AUTH_EMAIL_LOGO_URL") or f"{frontend_url.rstrip('/')}/favicon-256.png"

    return {
        "configured": bool(resend_api_key and sender_email),
        "resend_api_key": resend_api_key,
        "sender_email": sender_email or "notifications@unravler.com",
        "sender_name": sender_name,
        "frontend_url": frontend_url,
        "logo_url": logo_url,
        "support_email": _clean_env("SUPPORT_EMAIL", "contact@unravler.com"),
    }


def _button_label_for_event(event: str) -> str:
    if event in {"post.failed", "post.dlq"}:
        return "View in Content Library"
    if event == "account.reconnect_required":
        return "Reconnect Social Account"
    if event in {"subscription.expiring", "billing.failed"}:
        return "Manage Billing & Plan"
    if event.startswith("approval."):
        return "Review Post"
    return "Open Workspace"


def _build_notification_subject(event: str, title: str) -> str:
    if title:
        return f"[Unravler] {title}"
    if event == "post.failed":
        return "[Unravler] Social post publish failed"
    if event == "post.dlq":
        return "[Unravler] Action required: Post moved to recovery queue"
    if event == "account.reconnect_required":
        return "[Unravler] Urgent: Reconnect your social media account"
    if event == "billing.failed":
        return "[Unravler] Payment failed for your Unravler subscription"
    if event == "subscription.expiring":
        return "[Unravler] Your Unravler subscription is ending soon"
    if event == "approval.overdue":
        return "[Unravler] Overdue approval request requires your attention"
    return f"[Unravler] Notification: {event}"


def _build_notification_html(
    *,
    event: str,
    title: str,
    message: str,
    action_url: str,
    display_name: str | None,
    metadata: dict[str, Any] | None = None,
) -> str:
    config = get_notification_email_config()
    safe_name = html.escape(display_name or "there")
    safe_title = html.escape(title or _build_notification_subject(event, ""))
    safe_message = html.escape(message or "").replace("\n", "<br />")
    safe_action_url = html.escape(action_url)
    button_label = html.escape(_button_label_for_event(event))
    settings_url = html.escape(f"{config['frontend_url'].rstrip('/')}/settings")
    support_email = html.escape(config["support_email"])

    # Severity accent color
    accent_color = "#4f46e5"  # Indigo
    badge_bg = "#eef2ff"
    badge_text = "#4338ca"
    badge_label = "Update"

    if event in {"post.failed", "post.dlq", "billing.failed"}:
        accent_color = "#dc2626"  # Red
        badge_bg = "#fef2f2"
        badge_text = "#991b1b"
        badge_label = "Action Required"
    elif event in {"account.reconnect_required", "subscription.expiring", "approval.overdue"}:
        accent_color = "#d97706"  # Amber
        badge_bg = "#fffbeb"
        badge_text = "#92400e"
        badge_label = "Important"

    extra_details = ""
    if metadata:
        details_list = []
        if metadata.get("platform"):
            details_list.append(f"<strong>Platform:</strong> {html.escape(str(metadata['platform']).capitalize())}")
        if metadata.get("post_id"):
            details_list.append(f"<strong>Post ID:</strong> {html.escape(str(metadata['post_id']))}")
        if metadata.get("account_id"):
            details_list.append(f"<strong>Account:</strong> {html.escape(str(metadata['account_id']))}")
        if metadata.get("error"):
            details_list.append(f"<strong>Details:</strong> <code>{html.escape(str(metadata['error']))}</code>")
        if details_list:
            rows = '<br />'.join(details_list)
            extra_details = f'<div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 16px; margin: 16px 0; font-size: 13px; color: #475569; line-height: 1.6;">{rows}</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{safe_title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #0f172a; line-height: 1.5;">
  <div style="max-width: 580px; margin: 36px auto; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 12px rgba(15, 23, 42, 0.05);">
    
    <!-- Top Header Bar -->
    <div style="background-color: #090d16; padding: 24px 32px; border-bottom: 1px solid #1e293b;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td><span style="font-size: 20px; font-weight: 700; color: #ffffff; letter-spacing: -0.02em;">Unravler</span></td>
          <td align="right"><span style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.12em; background-color: {badge_bg}; color: {badge_text}; padding: 4px 10px; border-radius: 9999px;">{badge_label}</span></td>
        </tr>
      </table>
    </div>

    <!-- Main Content Body -->
    <div style="padding: 32px;">
      <p style="margin: 0 0 16px 0; font-size: 15px; color: #64748b;">Hi {safe_name},</p>
      
      <h1 style="margin: 0 0 14px 0; font-size: 20px; font-weight: 700; color: #0f172a; line-height: 1.3;">{safe_title}</h1>
      
      <p style="margin: 0 0 16px 0; font-size: 15px; color: #334155; line-height: 1.6;">{safe_message}</p>
      
      {extra_details}

      <!-- Primary Action Button -->
      <div style="margin: 28px 0 24px 0; text-align: left;">
        <a href="{safe_action_url}" target="_blank" style="display: inline-block; background-color: {accent_color}; color: #ffffff; text-decoration: none; font-size: 14px; font-weight: 600; padding: 12px 24px; border-radius: 10px; box-shadow: 0 2px 6px rgba(79, 70, 229, 0.2);">
          {button_label} &rarr;
        </a>
      </div>

      <p style="margin: 20px 0 0 0; font-size: 13px; color: #64748b;">
        If you are having trouble with the button above, copy and paste this link into your browser:<br />
        <a href="{safe_action_url}" style="color: #4f46e5; word-break: break-all; text-decoration: underline;">{safe_action_url}</a>
      </p>
    </div>

    <!-- Footer -->
    <div style="padding: 20px 32px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center; line-height: 1.6;">
      <p style="margin: 0 0 6px 0;">You received this email because notification preferences are enabled for your workspace.</p>
      <p style="margin: 0;">
        <a href="{settings_url}" style="color: #64748b; text-decoration: underline;">Manage Notification Preferences</a> &bull; 
        <a href="mailto:{support_email}" style="color: #64748b; text-decoration: underline;">Contact Support</a>
      </p>
    </div>
  </div>
</body>
</html>"""


def _build_notification_text(
    *,
    event: str,
    title: str,
    message: str,
    action_url: str,
    display_name: str | None,
) -> str:
    config = get_notification_email_config()
    safe_name = display_name or "there"
    safe_title = title or _build_notification_subject(event, "")
    button_label = _button_label_for_event(event)
    settings_url = f"{config['frontend_url'].rstrip('/')}/settings"
    support_email = config["support_email"]

    return (
        f"Hi {safe_name},\n\n"
        f"{safe_title}\n\n"
        f"{message}\n\n"
        f"{button_label}: {action_url}\n\n"
        f"Manage notification preferences: {settings_url}\n"
        f"Need help? Contact {support_email}\n\n"
        f"— The Unravler Team\n"
    )


async def send_notification_email_async(
    *,
    email: str,
    event: str,
    title: str,
    message: str,
    target_path: str | None = None,
    display_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Send transactional notification email to recipient via Resend or log."""
    config = get_notification_email_config()
    if not email:
        logger.warning("send_notification_email_async: missing recipient email")
        return False

    action_url = build_frontend_url(
        target_path or "/dashboard",
        raw_base_url=config["frontend_url"],
    )
    subject = _build_notification_subject(event, title)
    html_content = _build_notification_html(
        event=event,
        title=title,
        message=message,
        action_url=action_url,
        display_name=display_name,
        metadata=metadata,
    )
    text_content = _build_notification_text(
        event=event,
        title=title,
        message=message,
        action_url=action_url,
        display_name=display_name,
    )

    if not config["configured"]:
        logger.info(
            "Notification email dispatched (mock/unconfigured): to=%s subject=%s event=%s",
            email,
            subject,
            event,
        )
        return True

    try:
        import resend  # noqa: PLC0415

        resend.api_key = config["resend_api_key"]
        sender_header = f"{config['sender_name']} <{config['sender_email']}>"

        params = {
            "from": sender_header,
            "to": [email],
            "reply_to": [config["sender_email"]],
            "subject": subject,
            "html": html_content,
            "text": text_content,
        }

        await asyncio.to_thread(resend.Emails.send, params)
        logger.info("Notification email delivered successfully via Resend to %s for event %s", email, event)
        return True
    except Exception as exc:
        logger.error("Failed to deliver notification email via Resend to %s: %s", email, exc)
        return False
