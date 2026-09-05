"""
Unified email delivery service for Unravler.
Supports Amazon SES (via boto3) as primary high-scale provider,
with graceful fallback to Resend or mock mode for testing/local dev.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Sequence

logger = logging.getLogger(__name__)


class EmailConfigurationError(RuntimeError):
    """Raised when email delivery configuration is incomplete or invalid."""


class EmailDeliveryError(RuntimeError):
    """Raised when email transmission to the upstream provider fails."""


def _clean_env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def get_email_provider() -> str:
    """
    Resolve active email provider: 'ses', 'resend', or 'mock'.
    Defaults to 'ses' when running on EC2 or AWS credentials/region configured,
    or falls back to 'resend' when RESEND_API_KEY is explicitly set.
    """
    explicit = _clean_env("EMAIL_PROVIDER").lower()
    if explicit in {"ses", "resend", "mock"}:
        return explicit

    if _clean_env("AWS_SES_ACCESS_KEY_ID") or _clean_env("AWS_SES_SECRET_ACCESS_KEY") or _clean_env("AWS_SES_REGION"):
        return "ses"

    if _clean_env("RESEND_API_KEY"):
        return "resend"

    return "ses"


def get_email_service_status() -> dict[str, Any]:
    """Inspect current email provider configuration and diagnostic readiness."""
    provider = get_email_provider()
    sender_email = _clean_env("SENDER_EMAIL")
    sender_name = _clean_env("SENDER_NAME", "Unravler") or "Unravler"
    support_email = _clean_env("SUPPORT_EMAIL", "contact@unravler.com")
    region = _clean_env("AWS_SES_REGION") or _clean_env("AWS_REGION", "eu-north-1")

    missing: list[str] = []

    if provider == "ses":
        if not sender_email:
            missing.append("SENDER_EMAIL")
        # On AWS EC2, boto3 discovers IAM role credentials automatically without needing keys.
        # However, if explicit SES keys are partially set, flag the missing half.
        has_id = bool(_clean_env("AWS_SES_ACCESS_KEY_ID") or _clean_env("AWS_ACCESS_KEY_ID"))
        has_secret = bool(_clean_env("AWS_SES_SECRET_ACCESS_KEY") or _clean_env("AWS_SECRET_ACCESS_KEY"))
        if has_id and not has_secret:
            missing.append("AWS_SES_SECRET_ACCESS_KEY")
        elif has_secret and not has_id:
            missing.append("AWS_SES_ACCESS_KEY_ID")

    elif provider == "resend":
        resend_key = _clean_env("RESEND_API_KEY")
        if not resend_key:
            missing.append("RESEND_API_KEY")
        if not sender_email:
            missing.append("SENDER_EMAIL")

    configured = not missing and bool(sender_email or provider == "mock")
    custom_sender = bool(sender_email) and not sender_email.endswith("@resend.dev")

    return {
        "provider": provider,
        "configured": configured,
        "missing": missing,
        "sender_email": sender_email or None,
        "sender_name": sender_name,
        "support_email": support_email,
        "region": region if provider == "ses" else None,
        "custom_sender_configured": custom_sender,
    }


def _sender_header(status: dict[str, Any], explicit_sender: str | None = None, explicit_name: str | None = None) -> str:
    email = explicit_sender or status.get("sender_email") or "notifications@unravler.com"
    name = explicit_name or status.get("sender_name") or "Unravler"
    return f"{name} <{email}>"


def _send_via_ses_sync(
    *,
    to_addresses: list[str],
    sender_header: str,
    reply_to: list[str],
    subject: str,
    html: str,
    text: str,
    region: str,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
) -> dict[str, Any]:
    """Execute synchronous SES send_email call via boto3."""
    try:
        import boto3  # noqa: PLC0415
    except ImportError as exc:
        raise EmailConfigurationError("boto3 is required for Amazon SES email delivery") from exc

    client_kwargs: dict[str, Any] = {"region_name": region}
    if access_key_id and secret_access_key:
        client_kwargs["aws_access_key_id"] = access_key_id
        client_kwargs["aws_secret_access_key"] = secret_access_key

    client = boto3.client("ses", **client_kwargs)

    params = {
        "Source": sender_header,
        "Destination": {
            "ToAddresses": to_addresses,
        },
        "Message": {
            "Subject": {
                "Data": subject,
                "Charset": "UTF-8",
            },
            "Body": {
                "Html": {
                    "Data": html,
                    "Charset": "UTF-8",
                },
                "Text": {
                    "Data": text,
                    "Charset": "UTF-8",
                },
            },
        },
        "ReplyToAddresses": reply_to,
    }
    return client.send_email(**params)


def _send_via_resend_sync(
    *,
    to_addresses: list[str],
    sender_header: str,
    reply_to: list[str],
    subject: str,
    html: str,
    text: str,
    api_key: str,
) -> dict[str, Any]:
    """Execute synchronous Resend send call."""
    try:
        import resend  # noqa: PLC0415
    except ImportError as exc:
        raise EmailConfigurationError("resend package is required for Resend email delivery") from exc

    resend.api_key = api_key
    params = {
        "from": sender_header,
        "to": to_addresses,
        "reply_to": reply_to,
        "subject": subject,
        "html": html,
        "text": text,
    }
    return resend.Emails.send(params)


async def send_email_or_raise_async(
    *,
    to: str | Sequence[str],
    subject: str,
    html: str,
    text: str,
    reply_to: str | Sequence[str] | None = None,
    sender_email: str | None = None,
    sender_name: str | None = None,
) -> dict[str, Any]:
    """
    Deliver transactional email via configured provider (Amazon SES or Resend),
    raising EmailDeliveryError on upstream failure.
    """
    status = get_email_service_status()
    provider = status["provider"]

    if isinstance(to, str):
        to_addresses = [to.strip()]
    else:
        to_addresses = [addr.strip() for addr in to if addr and addr.strip()]

    if not to_addresses:
        raise EmailDeliveryError("Cannot send email: recipient list is empty")

    if not reply_to:
        reply_to_list = [status["sender_email"] or status["support_email"]]
    elif isinstance(reply_to, str):
        reply_to_list = [reply_to.strip()]
    else:
        reply_to_list = [addr.strip() for addr in reply_to if addr and addr.strip()]

    sender = _sender_header(status, sender_email, sender_name)

    if provider == "mock" or not status["configured"]:
        logger.info(
            "Email dispatched (mock/unconfigured mode): provider=%s to=%s subject=%s sender=%s",
            provider,
            to_addresses,
            subject,
            sender,
        )
        return {"id": "mock-email-id", "provider": "mock"}

    if provider == "ses":
        region = status["region"] or "eu-north-1"
        key_id = _clean_env("AWS_SES_ACCESS_KEY_ID") or _clean_env("AWS_ACCESS_KEY_ID") or None
        secret_key = _clean_env("AWS_SES_SECRET_ACCESS_KEY") or _clean_env("AWS_SECRET_ACCESS_KEY") or None

        try:
            result = await asyncio.to_thread(
                _send_via_ses_sync,
                to_addresses=to_addresses,
                sender_header=sender,
                reply_to=reply_to_list,
                subject=subject,
                html=html,
                text=text,
                region=region,
                access_key_id=key_id,
                secret_access_key=secret_key,
            )
            logger.info("Email sent via Amazon SES: to=%s message_id=%s", to_addresses, result.get("MessageId"))
            return result
        except Exception as exc:
            logger.error("Amazon SES delivery failed for %s: %s", to_addresses, exc)
            raise EmailDeliveryError(f"Amazon SES delivery failed: {exc}") from exc

    elif provider == "resend":
        api_key = _clean_env("RESEND_API_KEY")
        if not api_key:
            raise EmailConfigurationError("RESEND_API_KEY is not configured")

        try:
            result = await asyncio.to_thread(
                _send_via_resend_sync,
                to_addresses=to_addresses,
                sender_header=sender,
                reply_to=reply_to_list,
                subject=subject,
                html=html,
                text=text,
                api_key=api_key,
            )
            logger.info("Email sent via Resend: to=%s id=%s", to_addresses, result.get("id") if isinstance(result, dict) else result)
            return result if isinstance(result, dict) else {"id": str(result)}
        except Exception as exc:
            logger.error("Resend delivery failed for %s: %s", to_addresses, exc)
            raise EmailDeliveryError(f"Resend delivery failed: {exc}") from exc

    raise EmailConfigurationError(f"Unsupported email provider: {provider}")


async def send_email_async(
    *,
    to: str | Sequence[str],
    subject: str,
    html: str,
    text: str,
    reply_to: str | Sequence[str] | None = None,
    sender_email: str | None = None,
    sender_name: str | None = None,
) -> bool:
    """Non-raising wrapper around send_email_or_raise_async for background tasks."""
    try:
        await send_email_or_raise_async(
            to=to,
            subject=subject,
            html=html,
            text=text,
            reply_to=reply_to,
            sender_email=sender_email,
            sender_name=sender_name,
        )
        return True
    except Exception as exc:
        logger.error("send_email_async failed: to=%s error=%s", to, exc)
        return False
