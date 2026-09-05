import asyncio
import inspect
import logging
import os
from typing import Literal

from firebase_admin import auth as firebase_auth

from api.deps import get_firebase_app
from utils.email_service import get_email_provider, send_email_or_raise_async
from utils.frontend_urls import DEFAULT_FRONTEND_URL, build_frontend_url, resolve_frontend_base_url
from utils.observability import event_log, shorten_provider_error

logger = logging.getLogger(__name__)

AuthEmailKind = Literal["password_reset", "verify_email"]
_SUPPORTS_LINK_DOMAIN = "link_domain" in inspect.signature(firebase_auth.ActionCodeSettings.__init__).parameters


class AuthEmailConfigError(RuntimeError):
    """Raised when transactional auth email config is incomplete."""


class AuthEmailUnknownRecipientError(RuntimeError):
    """Raised when the target email does not map to a Firebase auth user."""


class AuthEmailDeliveryError(RuntimeError):
    """Raised when link generation or outbound delivery fails."""


def _clean_env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _firebase_web_api_key() -> str:
    return _clean_env("FIREBASE_WEB_API_KEY")


def _is_relative_return_to(value: str | None) -> bool:
    if not value:
        return False
    return value.startswith("/") and not value.startswith("//")


def _normalize_return_to(value: str | None) -> str | None:
    if _is_relative_return_to(value):
        return value
    return None


def get_auth_email_config_status() -> dict[str, object]:
    provider = get_email_provider()
    resend_api_key = _clean_env("RESEND_API_KEY")
    sender_email = _clean_env("SENDER_EMAIL")
    sender_name = _clean_env("SENDER_NAME", "Unravler") or "Unravler"
    frontend_url = resolve_frontend_base_url(_clean_env("FRONTEND_URL", DEFAULT_FRONTEND_URL))
    logo_url = _clean_env("AUTH_EMAIL_LOGO_URL") or f"{frontend_url.rstrip('/')}/favicon-256.png"
    link_domain = _clean_env("FIREBASE_AUTH_EMAIL_LINK_DOMAIN")

    missing: list[str] = []
    if provider == "ses":
        if not sender_email:
            missing.append("SENDER_EMAIL")
        has_id = bool(_clean_env("AWS_SES_ACCESS_KEY_ID") or _clean_env("AWS_ACCESS_KEY_ID"))
        has_secret = bool(_clean_env("AWS_SES_SECRET_ACCESS_KEY") or _clean_env("AWS_SECRET_ACCESS_KEY"))
        if has_id and not has_secret:
            missing.append("AWS_SES_SECRET_ACCESS_KEY")
        elif has_secret and not has_id:
            missing.append("AWS_SES_ACCESS_KEY_ID")
    elif provider == "resend":
        if not resend_api_key:
            missing.append("RESEND_API_KEY")
        if not sender_email:
            missing.append("SENDER_EMAIL")

    if not frontend_url:
        missing.append("FRONTEND_URL")

    custom_sender = bool(sender_email) and not sender_email.endswith("@resend.dev")
    sender_name_ok = bool(sender_name)

    return {
        "provider": provider,
        "configured": not missing,
        "missing": missing,
        "sender_email": sender_email or None,
        "sender_name": sender_name,
        "frontend_url": frontend_url,
        "logo_url": logo_url or None,
        "custom_link_domain_configured": bool(link_domain),
        "custom_sender_configured": custom_sender,
        "sender_name_configured": sender_name_ok,
    }


def _require_auth_email_config() -> dict[str, object]:
    status = get_auth_email_config_status()
    if not status["configured"]:
        missing = ", ".join(status["missing"]) or "unknown"
        raise AuthEmailConfigError(f"Missing auth email config: {missing}")
    return status


def _build_frontend_url(path: str, query: dict[str, str] | None = None) -> str:
    return build_frontend_url(path, query=query, raw_base_url=_clean_env("FRONTEND_URL", DEFAULT_FRONTEND_URL))


def _build_action_code_settings(path: str, *, query: dict[str, str] | None = None, handle_code_in_app: bool) -> firebase_auth.ActionCodeSettings:
    kwargs = {
        "url": _build_frontend_url(path, query=query),
        "handle_code_in_app": handle_code_in_app,
    }
    link_domain = _clean_env("FIREBASE_AUTH_EMAIL_LINK_DOMAIN")
    if link_domain:
        if _SUPPORTS_LINK_DOMAIN:
            kwargs["link_domain"] = link_domain
        else:
            kwargs["dynamic_link_domain"] = link_domain
    return firebase_auth.ActionCodeSettings(**kwargs)


def _build_button_label(kind: AuthEmailKind) -> str:
    if kind == "password_reset":
        return "Reset password"
    return "Verify email"


def _build_subject(kind: AuthEmailKind) -> str:
    if kind == "password_reset":
        return "Reset your Unravler password"
    return "Verify your email for Unravler"


def _build_body_copy(kind: AuthEmailKind, display_name: str | None) -> tuple[str, str, str]:
    greeting = f"Hi {display_name}," if display_name else "Hi,"
    if kind == "password_reset":
        title = "Reset your password"
        intro = "Use the button below to choose a new password for your Unravler account."
        outro = "If you did not request a password reset, you can ignore this email."
    else:
        title = "Verify your email"
        intro = "Confirm your email address to unlock sensitive actions in Unravler, including publishing, scheduling, and team access."
        outro = "If you did not create this account, you can ignore this email."
    return greeting, title, intro + " For your security, use this link soon.", outro


def _build_email_html(kind: AuthEmailKind, action_url: str, display_name: str | None) -> str:
    status = get_auth_email_config_status()
    logo_url = status["logo_url"]
    support_email = status["sender_email"] or "contact@unravler.com"
    greeting, title, intro, outro = _build_body_copy(kind, display_name)
    button_label = _build_button_label(kind)

    header = (
        f'<img src="{logo_url}" alt="Unravler" width="156" '
        'style="display:block;height:auto;max-width:156px;border:0;outline:none;text-decoration:none;">'
        if logo_url
        else '<div style="font-size:24px;font-weight:700;letter-spacing:-0.02em;color:#0f172a;">Unravler</div>'
    )

    return f"""\
<!DOCTYPE html>
<html lang="en">
  <body style="margin:0;padding:0;background:#f5f7fb;color:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
      {title} for your Unravler account.
    </div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f5f7fb;padding:24px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border:1px solid #e2e8f0;border-radius:20px;overflow:hidden;">
            <tr>
              <td style="padding:32px 32px 20px 32px;">
                {header}
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 12px 32px;font-size:16px;line-height:1.7;color:#334155;">
                <p style="margin:0 0 12px 0;">{greeting}</p>
                <h1 style="margin:0 0 16px 0;font-size:28px;line-height:1.2;letter-spacing:-0.03em;color:#0f172a;">{title}</h1>
                <p style="margin:0 0 22px 0;">{intro}</p>
                <table role="presentation" cellspacing="0" cellpadding="0" style="margin:0 0 24px 0;">
                  <tr>
                    <td align="center" bgcolor="#4f46e5" style="border-radius:12px;">
                      <a href="{action_url}" style="display:inline-block;padding:14px 22px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:12px;">{button_label}</a>
                    </td>
                  </tr>
                </table>
                <p style="margin:0 0 12px 0;">{outro}</p>
                <p style="margin:0 0 8px 0;font-size:13px;color:#64748b;">If the button does not work, copy this link into your browser:</p>
                <p style="margin:0;font-size:13px;line-height:1.6;word-break:break-word;color:#4f46e5;">{action_url}</p>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 32px 28px 32px;border-top:1px solid #e2e8f0;font-size:12px;line-height:1.7;color:#64748b;">
                <p style="margin:0 0 6px 0;">Need help? Reply to <a href="mailto:{support_email}" style="color:#4f46e5;text-decoration:none;">{support_email}</a>.</p>
                <p style="margin:0;">Unravler</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def _build_email_text(kind: AuthEmailKind, action_url: str, display_name: str | None) -> str:
    support_email = get_auth_email_config_status()["sender_email"] or "contact@unravler.com"
    greeting, title, intro, outro = _build_body_copy(kind, display_name)
    button_label = _build_button_label(kind)
    return (
        f"{greeting}\n\n"
        f"{title}\n\n"
        f"{intro}\n\n"
        f"{button_label}: {action_url}\n\n"
        f"{outro}\n\n"
        f"Need help? Reply to {support_email}.\n\n"
        "Unravler\n"
    )


def _sender_header() -> str:
    status = _require_auth_email_config()
    sender_name = status["sender_name"] or "Unravler"
    sender_email = status["sender_email"]
    return f"{sender_name} <{sender_email}>"


async def _send_email(kind: AuthEmailKind, email: str, action_url: str, display_name: str | None) -> None:
    status = _require_auth_email_config()
    sender_email = str(status.get("sender_email") or "")
    sender_name = str(status.get("sender_name") or "Unravler")

    try:
        await send_email_or_raise_async(
            to=email,
            subject=_build_subject(kind),
            html=_build_email_html(kind, action_url, display_name),
            text=_build_email_text(kind, action_url, display_name),
            reply_to=sender_email,
            sender_email=sender_email,
            sender_name=sender_name,
        )
    except Exception as exc:
        raise AuthEmailDeliveryError(str(exc)) from exc


async def _send_password_reset_via_firebase(email: str) -> None:
    api_key = _firebase_web_api_key()
    if not api_key:
        raise AuthEmailConfigError("Missing FIREBASE_WEB_API_KEY for password reset fallback")

    try:
        import httpx  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - import failure is environment-specific
        raise AuthEmailDeliveryError(f"httpx unavailable: {exc}") from exc

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={api_key}"
    payload = {
        "requestType": "PASSWORD_RESET",
        "email": email,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
    except Exception as exc:
        raise AuthEmailDeliveryError(str(exc)) from exc

    if response.status_code == 200:
        return

    try:
        data = response.json()
    except Exception:
        data = {}
    message = (
        data.get("error", {}).get("message")
        or data.get("message")
        or response.text
        or f"Firebase password reset fallback failed with {response.status_code}"
    )
    normalized = str(message).upper()
    if normalized in {"EMAIL_NOT_FOUND", "INVALID_EMAIL"}:
        raise AuthEmailUnknownRecipientError(message)
    raise AuthEmailDeliveryError(message)


async def send_password_reset_email(email: str) -> None:
    _require_auth_email_config()
    settings = _build_action_code_settings(
        "/login",
        query={"passwordReset": "completed"},
        handle_code_in_app=False,
    )

    try:
        action_url = await asyncio.wait_for(
            asyncio.to_thread(
                firebase_auth.generate_password_reset_link,
                email,
                settings,
                get_firebase_app(),
            ),
            timeout=2.5,
        )
    except (firebase_auth.UserNotFoundError, firebase_auth.EmailNotFoundError) as exc:
        raise AuthEmailUnknownRecipientError(str(exc)) from exc
    except Exception as exc:
        event_log(
            logger,
            "warning",
            "auth.password_reset.firebase_fallback",
            email=email,
            failure_type=type(exc).__name__,
            provider_error=shorten_provider_error(exc),
            outcome="fallback_attempted",
        )
        try:
            await _send_password_reset_via_firebase(email)
            event_log(
                logger,
                "info",
                "auth.password_reset.firebase_fallback_succeeded",
                email=email,
                outcome="fallback_succeeded",
            )
            return
        except AuthEmailUnknownRecipientError:
            raise
        except Exception as fallback_exc:
            raise AuthEmailDeliveryError(str(fallback_exc)) from fallback_exc

    await _send_email("password_reset", email, action_url, None)


async def send_verification_email(email: str, *, display_name: str | None = None, return_to: str | None = None) -> None:
    _require_auth_email_config()
    normalized_return_to = _normalize_return_to(return_to)
    query = {"returnTo": normalized_return_to} if normalized_return_to else None
    settings = _build_action_code_settings(
        "/verify-email",
        query=query,
        handle_code_in_app=True,
    )

    try:
        action_url = await asyncio.to_thread(
            firebase_auth.generate_email_verification_link,
            email,
            settings,
            get_firebase_app(),
        )
    except (firebase_auth.UserNotFoundError, firebase_auth.EmailNotFoundError) as exc:
        raise AuthEmailUnknownRecipientError(str(exc)) from exc
    except Exception as exc:
        raise AuthEmailDeliveryError(str(exc)) from exc

    await _send_email("verify_email", email, action_url, display_name)


async def send_magic_link_email(email: str, token: str, display_name: str | None = None) -> None:
    status = _require_auth_email_config()
    frontend_url = str(status.get("frontend_url") or "")
    action_url = f"{frontend_url.rstrip('/')}/magic-login/{token}"
    sender_email = str(status.get("sender_email") or "")
    sender_name = str(status.get("sender_name") or "Unravler")

    subject = "Your Unravler Magic Login Link"
    greeting = f"Hi {display_name}," if display_name else "Hi,"
    
    html_body = f"""\
<!DOCTYPE html>
<html>
<body style="font-family: sans-serif; padding: 20px;">
  <h2>{subject}</h2>
  <p>{greeting}</p>
  <p>Click the button below to log in to your Unravler account instantly. No password required.</p>
  <p>
    <a href="{action_url}" style="display: inline-block; padding: 12px 20px; background-color: #4f46e5; color: #ffffff; text-decoration: none; border-radius: 8px; font-weight: 600;">
      Log In Instantly
    </a>
  </p>
  <p>Or copy and paste this link in your browser:</p>
  <p style="word-break: break-all;"><a href="{action_url}">{action_url}</a></p>
  <p style="color: #666; font-size: 13px;">This link is valid for 24 hours and can only be used once.</p>
</body>
</html>
"""

    text_body = f"{greeting}\n\nClick the link below to log in to Unravler:\n{action_url}\n\nThis link is valid for 24 hours and can only be used once."

    try:
        await send_email_or_raise_async(
            to=email,
            subject=subject,
            html=html_body,
            text=text_body,
            reply_to=sender_email,
            sender_email=sender_email,
            sender_name=sender_name,
        )
    except Exception as exc:
        raise AuthEmailDeliveryError(str(exc)) from exc


async def send_approval_notification_email(email: str, name: str | None, post_title: str, action_url: str) -> None:
    status = _require_auth_email_config()
    sender_email = str(status.get("sender_email") or "")
    sender_name = str(status.get("sender_name") or "Unravler")

    subject = f"Approval Required: {post_title}"
    greeting = f"Hi {name}," if name else "Hi,"
    
    html_body = f"""\
<!DOCTYPE html>
<html>
<body style="font-family: sans-serif; padding: 20px;">
  <h2>Approval Required</h2>
  <p>{greeting}</p>
  <p>A new social media post, <strong>"{post_title}"</strong>, has been submitted and requires your approval before it can go live.</p>
  <p>
    <a href="{action_url}" style="display: inline-block; padding: 12px 20px; background-color: #10b981; color: #ffffff; text-decoration: none; border-radius: 8px; font-weight: 600;">
      Review & Approve Post
    </a>
  </p>
  <p>Or copy and paste this link in your browser:</p>
  <p style="word-break: break-all;"><a href="{action_url}">{action_url}</a></p>
  <p style="color: #666; font-size: 13px;">This login link is valid for 7 days.</p>
</body>
</html>
"""

    text_body = f"{greeting}\n\nA new post, \"{post_title}\", requires your approval. Review it here:\n{action_url}\n\nThis link is valid for 7 days."

    try:
        await send_email_or_raise_async(
            to=email,
            subject=subject,
            html=html_body,
            text=text_body,
            reply_to=sender_email,
            sender_email=sender_email,
            sender_name=sender_name,
        )
    except Exception as exc:
        raise AuthEmailDeliveryError(str(exc)) from exc


