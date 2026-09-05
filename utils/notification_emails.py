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

from utils.email_service import get_email_service_status, send_email_async
from utils.frontend_urls import DEFAULT_FRONTEND_URL, build_frontend_url, resolve_frontend_base_url

logger = logging.getLogger(__name__)


def _clean_env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def get_notification_email_config() -> dict[str, Any]:
    svc = get_email_service_status()
    frontend_url = resolve_frontend_base_url(_clean_env("FRONTEND_URL", DEFAULT_FRONTEND_URL))
    logo_url = _clean_env("AUTH_EMAIL_LOGO_URL") or f"{frontend_url.rstrip('/')}/unravler-logo-dark.png"

    return {
        "configured": svc["configured"],
        "provider": svc["provider"],
        "resend_api_key": _clean_env("RESEND_API_KEY"),
        "sender_email": svc["sender_email"] or "notifications@unravler.com",
        "sender_name": svc["sender_name"],
        "frontend_url": frontend_url,
        "logo_url": logo_url,
        "support_email": svc["support_email"],
    }


def _button_label_for_event(event: str) -> str:
    if event == "user.welcome":
        return "Get Started & Connect Accounts"
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
    if event == "user.welcome":
        return "[Unravler] Welcome to Unravler! Let's get started"
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


def _build_welcome_email_html(
    *,
    action_url: str,
    display_name: str | None,
    message: str | None = None,
) -> str:
    config = get_notification_email_config()
    safe_name = html.escape(display_name or "there")
    safe_action_url = html.escape(action_url)
    frontend_url = html.escape(config["frontend_url"].rstrip("/"))
    logo_url = html.escape(config["logo_url"])
    support_email = html.escape(config["support_email"])
    settings_url = f"{frontend_url}/settings"
    bio_url = f"{frontend_url}/link-in-bio"
    button_label = html.escape(_button_label_for_event("user.welcome"))
    
    default_intro = "Your workspace is ready. Unravler is engineered to be your complete growth command center—streamlining multi-platform publishing, AI-powered repurposing, and audience expansion across every major network."
    safe_intro = html.escape(message).replace("\n", "<br />") if message else default_intro

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Welcome to Unravler</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f4f4f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #09090b; -webkit-font-smoothing: antialiased; line-height: 1.5;">
  <div style="max-width: 600px; margin: 40px auto; background-color: #ffffff; border: 1px solid #e4e4e7; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.05);">
    
    <!-- Top Brand Accent Strip -->
    <div style="height: 3px; background: linear-gradient(90deg, #4f46e5 0%, #7c3aed 50%, #2563eb 100%);"></div>

    <!-- Header Bar with Single Brand Logo & Status Pill -->
    <div style="padding: 24px 32px 20px 32px; border-bottom: 1px solid #f1f5f9; background-color: #ffffff;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td valign="middle" align="left">
            <img src="{logo_url}" alt="Unravler" height="24" style="display: block; height: 24px; border: 0; outline: none;" />
          </td>
          <td align="right" valign="middle">
            <span style="display: inline-block; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; background-color: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; padding: 4px 12px; border-radius: 9999px;">
              ● Workspace Active
            </span>
          </td>
        </tr>
      </table>
    </div>

    <!-- Main Content Body -->
    <div style="padding: 36px 32px 32px 32px;">
      <!-- Eyebrow -->
      <p style="margin: 0 0 8px 0; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.12em; color: #4f46e5;">Welcome Aboard</p>
      
      <!-- Headline -->
      <h1 style="margin: 0 0 14px 0; font-size: 24px; font-weight: 800; color: #09090b; line-height: 1.25; letter-spacing: -0.02em;">
        Welcome to Unravler, {safe_name}
      </h1>

      <!-- Intro Copy -->
      <p style="margin: 0 0 32px 0; font-size: 14.5px; color: #52525b; line-height: 1.6; letter-spacing: -0.01em;">
        {safe_intro}
      </p>

      <!-- Feature Grid Showcase -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom: 24px;">
        <tr>
          <!-- Feature 1: Multi-Platform Publishing -->
          <td width="48%" valign="top" style="background-color: #fafafa; border: 1px solid #e4e4e7; border-radius: 12px; padding: 18px 16px;">
            <div style="display: inline-block; width: 28px; height: 28px; line-height: 28px; text-align: center; border-radius: 6px; background-color: #eff6ff; color: #2563eb; font-size: 13px; font-weight: 700; margin-bottom: 10px;">✦</div>
            <h3 style="margin: 0 0 6px 0; font-size: 13.5px; font-weight: 700; color: #09090b; letter-spacing: -0.01em;">Multi-Platform Publishing</h3>
            <p style="margin: 0; font-size: 12.5px; color: #71717a; line-height: 1.5;">Schedule and publish simultaneously to YouTube, Instagram, LinkedIn, TikTok, X, Threads, Pinterest, and Facebook.</p>
          </td>
          <td width="4%">&nbsp;</td>
          <!-- Feature 2: LinkedIn Growth Suite -->
          <td width="48%" valign="top" style="background-color: #fafafa; border: 1px solid #e4e4e7; border-radius: 12px; padding: 18px 16px;">
            <div style="display: inline-block; width: 28px; height: 28px; line-height: 28px; text-align: center; border-radius: 6px; background-color: #f0fdf4; color: #16a34a; font-size: 13px; font-weight: 700; margin-bottom: 10px;">◆</div>
            <h3 style="margin: 0 0 6px 0; font-size: 13.5px; font-weight: 700; color: #09090b; letter-spacing: -0.01em;">LinkedIn Growth Suite</h3>
            <p style="margin: 0; font-size: 12.5px; color: #71717a; line-height: 1.5;">Generate viral PDF carousels, craft engaging text hooks, preview mobile/desktop layouts, and upload HD video.</p>
          </td>
        </tr>
        <tr><td height="12" colspan="3"></td></tr>
        <tr>
          <!-- Feature 3: AI Repurposer -->
          <td width="48%" valign="top" style="background-color: #fafafa; border: 1px solid #e4e4e7; border-radius: 12px; padding: 18px 16px;">
            <div style="display: inline-block; width: 28px; height: 28px; line-height: 28px; text-align: center; border-radius: 6px; background-color: #faf5ff; color: #9333ea; font-size: 13px; font-weight: 700; margin-bottom: 10px;">⚡</div>
            <h3 style="margin: 0 0 6px 0; font-size: 13.5px; font-weight: 700; color: #09090b; letter-spacing: -0.01em;">AI Content Repurposer</h3>
            <p style="margin: 0; font-size: 12.5px; color: #71717a; line-height: 1.5;">Turn any YouTube video, article, or raw draft into platform-tailored threads, carousels, and captions instantly.</p>
          </td>
          <td width="4%">&nbsp;</td>
          <!-- Feature 4: Campaigns & Recycling -->
          <td width="48%" valign="top" style="background-color: #fafafa; border: 1px solid #e4e4e7; border-radius: 12px; padding: 18px 16px;">
            <div style="display: inline-block; width: 28px; height: 28px; line-height: 28px; text-align: center; border-radius: 6px; background-color: #fff7ed; color: #ea580c; font-size: 13px; font-weight: 700; margin-bottom: 10px;">◈</div>
            <h3 style="margin: 0 0 6px 0; font-size: 13.5px; font-weight: 700; color: #09090b; letter-spacing: -0.01em;">Campaigns &amp; Recycling</h3>
            <p style="margin: 0; font-size: 12.5px; color: #71717a; line-height: 1.5;">Organize content into strategic campaigns, track collective momentum, and automatically recycle top evergreen posts.</p>
          </td>
        </tr>
        <tr><td height="12" colspan="3"></td></tr>
        <tr>
          <!-- Feature 5: Smart Bio Studio -->
          <td width="48%" valign="top" style="background-color: #fafafa; border: 1px solid #e4e4e7; border-radius: 12px; padding: 18px 16px;">
            <div style="display: inline-block; width: 28px; height: 28px; line-height: 28px; text-align: center; border-radius: 6px; background-color: #fdf2f8; color: #db2777; font-size: 13px; font-weight: 700; margin-bottom: 10px;">↗</div>
            <h3 style="margin: 0 0 6px 0; font-size: 13.5px; font-weight: 700; color: #09090b; letter-spacing: -0.01em;">Smart Bio Studio</h3>
            <p style="margin: 0; font-size: 12.5px; color: #71717a; line-height: 1.5;">Build an aesthetic link-in-bio page with custom themes, rich media widgets, email capture, and click analytics.</p>
          </td>
          <td width="4%">&nbsp;</td>
          <!-- Feature 6: Team Governance -->
          <td width="48%" valign="top" style="background-color: #fafafa; border: 1px solid #e4e4e7; border-radius: 12px; padding: 18px 16px;">
            <div style="display: inline-block; width: 28px; height: 28px; line-height: 28px; text-align: center; border-radius: 6px; background-color: #f1f5f9; color: #475569; font-size: 13px; font-weight: 700; margin-bottom: 10px;">❖</div>
            <h3 style="margin: 0 0 6px 0; font-size: 13.5px; font-weight: 700; color: #09090b; letter-spacing: -0.01em;">Team Governance &amp; Approvals</h3>
            <p style="margin: 0; font-size: 12.5px; color: #71717a; line-height: 1.5;">Collaborate with teammates and clients using role-based permissions, review queues, and one-click email approvals.</p>
          </td>
        </tr>
      </table>

      <!-- 3-Step Quick Start Card -->
      <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 22px 24px; margin: 28px 0 32px 0;">
        <p style="margin: 0 0 16px 0; font-size: 11.5px; font-weight: 700; color: #0f172a; text-transform: uppercase; letter-spacing: 0.08em;">
          Three Steps to Get Started
        </p>
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td width="28" valign="top" style="padding-bottom: 12px;">
              <span style="display: inline-block; width: 20px; height: 20px; line-height: 20px; text-align: center; border-radius: 9999px; background-color: #09090b; color: #ffffff; font-size: 10.5px; font-weight: 700;">1</span>
            </td>
            <td style="font-size: 13.5px; color: #18181b; line-height: 1.5; padding-bottom: 12px;">
              <strong>Connect your social channels</strong> in Settings (YouTube, LinkedIn, Instagram, etc.).
            </td>
          </tr>
          <tr>
            <td width="28" valign="top" style="padding-bottom: 12px;">
              <span style="display: inline-block; width: 20px; height: 20px; line-height: 20px; text-align: center; border-radius: 9999px; background-color: #09090b; color: #ffffff; font-size: 10.5px; font-weight: 700;">2</span>
            </td>
            <td style="font-size: 13.5px; color: #18181b; line-height: 1.5; padding-bottom: 12px;">
              <strong>Craft your first post</strong> using the multi-platform composer or AI repurposer.
            </td>
          </tr>
          <tr>
            <td width="28" valign="top">
              <span style="display: inline-block; width: 20px; height: 20px; line-height: 20px; text-align: center; border-radius: 9999px; background-color: #09090b; color: #ffffff; font-size: 10.5px; font-weight: 700;">3</span>
            </td>
            <td style="font-size: 13.5px; color: #18181b; line-height: 1.5;">
              <strong>Schedule or publish</strong> and let Unravler optimize peak engagement delivery.
            </td>
          </tr>
        </table>
      </div>

      <!-- Primary Action Button -->
      <div style="margin: 32px 0 24px 0; text-align: center;">
        <a href="{safe_action_url}" target="_blank" style="display: inline-block; background-color: #09090b; color: #ffffff; text-decoration: none; font-size: 14px; font-weight: 600; padding: 14px 36px; border-radius: 10px; letter-spacing: -0.01em; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);">
          {button_label} &rarr;
        </a>
      </div>

      <!-- Quick Links -->
      <p style="margin: 20px 0 0 0; font-size: 12.5px; color: #71717a; text-align: center;">
        Quick links: 
        <a href="{safe_action_url}" style="color: #09090b; text-decoration: underline; font-weight: 600;">Dashboard</a> &bull; 
        <a href="{settings_url}" style="color: #09090b; text-decoration: underline; font-weight: 600;">Connect Accounts</a> &bull; 
        <a href="{bio_url}" style="color: #09090b; text-decoration: underline; font-weight: 600;">Smart Bio Studio</a>
      </p>
    </div>

    <!-- Footer -->
    <div style="padding: 24px 32px; background-color: #fafafa; border-top: 1px solid #f4f4f5; font-size: 12px; color: #a1a1aa; text-align: center; line-height: 1.6;">
      <p style="margin: 0 0 6px 0;">You received this welcome email because you registered an account on Unravler.</p>
      <p style="margin: 0;">
        <a href="{settings_url}" style="color: #71717a; text-decoration: underline;">Notification Preferences</a> &bull; 
        <a href="mailto:{support_email}" style="color: #71717a; text-decoration: underline;">Contact Support</a> &bull; 
        <a href="{frontend_url}" style="color: #71717a; text-decoration: underline;">unravler.com</a>
      </p>
    </div>
  </div>
</body>
</html>"""


def _build_welcome_email_text(
    *,
    action_url: str,
    display_name: str | None,
    message: str | None = None,
) -> str:
    config = get_notification_email_config()
    safe_name = display_name or "there"
    frontend_url = config["frontend_url"].rstrip("/")
    support_email = config["support_email"]
    intro = f"{message}\n\n" if message else (
        "Your workspace is ready. Unravler is engineered to be your complete growth command center—streamlining multi-platform publishing, AI-powered repurposing, and audience expansion across every major network.\n\n"
    )

    return (
        f"Hi {safe_name},\n\n"
        f"Welcome to Unravler!\n\n"
        f"{intro}"
        f"WHAT YOU CAN DO WITH UNRAVLER:\n"
        f"• Multi-Platform Publishing: Schedule and publish simultaneously to YouTube, Instagram, LinkedIn, TikTok, X, Threads, Pinterest & Facebook.\n"
        f"• LinkedIn Growth Suite: Generate PDF document carousels, format hooks, preview mobile/desktop feeds, and stream native HD video.\n"
        f"• AI Content Repurposer: Turn YouTube videos, blogs, or drafts into platform-tailored threads, hooks, and hashtags in seconds.\n"
        f"• Smart Campaigns & Evergreen Recycling: Group content into campaigns, track collective momentum, and automatically recycle top posts.\n"
        f"• Smart Bio Studio: Build an aesthetic link-in-bio page with custom widgets, newsletter capture, and deep click analytics.\n"
        f"• Team Governance & Approvals: Collaborate with teammates and clients using review queues and automated approvals.\n\n"
        f"3 STEPS TO GET STARTED:\n"
        f"1. Connect your social channels in Settings: {frontend_url}/settings\n"
        f"2. Craft your first post or try the AI Repurposer: {frontend_url}/create-post\n"
        f"3. Schedule or launch your campaign: {frontend_url}/dashboard\n\n"
        f"Launch Your Workspace: {action_url}\n\n"
        f"Need help? Reply to {support_email} or visit {frontend_url}.\n\n"
        f"— The Unravler Team\n"
    )


def _build_notification_html(
    *,
    event: str,
    title: str,
    message: str,
    action_url: str,
    display_name: str | None,
    metadata: dict[str, Any] | None = None,
) -> str:
    if event == "user.welcome":
        return _build_welcome_email_html(
            action_url=action_url,
            display_name=display_name,
            message=message,
        )

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
    if event == "user.welcome":
        return _build_welcome_email_text(
            action_url=action_url,
            display_name=display_name,
            message=message,
        )

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

    return await send_email_async(
        to=email,
        subject=subject,
        html=html_content,
        text=text_content,
        reply_to=config["sender_email"],
        sender_email=config["sender_email"],
        sender_name=config["sender_name"],
    )
