"""
Cloudflare Turnstile server-side token verification.

Usage:
    from utils.turnstile import verify_turnstile

    ok = await verify_turnstile(token=cf_token, ip=client_ip)
    if not ok:
        raise HTTPException(status_code=403, detail="Turnstile verification failed")

Environment variables:
    TURNSTILE_SECRET_KEY  — Cloudflare Turnstile secret key (required when enabled)
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "")


async def verify_turnstile(token: str, ip: str) -> bool:
    """
    Verify a Cloudflare Turnstile challenge token with the siteverify API.

    Parameters
    ----------
    token : str
        The ``cf-turnstile-response`` value submitted by the client widget.
    ip : str
        The connecting client's IP address (passed as ``remoteip`` for
        improved fraud detection; Cloudflare treats this as advisory).

    Returns
    -------
    bool
        ``True`` if Cloudflare reports the token as valid, ``False`` otherwise.
        Network/API errors are caught and logged; the function returns
        ``False`` on any unexpected failure so that callers can decide
        how to handle degraded state.
    """
    if not _TURNSTILE_SECRET_KEY:
        logger.warning(
            "TURNSTILE_SECRET_KEY is not set — verify_turnstile will always return False"
        )
        return False

    if not token:
        logger.debug("verify_turnstile: empty token, returning False")
        return False

    payload = {
        "secret": _TURNSTILE_SECRET_KEY,
        "response": token,
        "remoteip": ip,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_TURNSTILE_VERIFY_URL, data=payload)
            resp.raise_for_status()
            data = resp.json()

        success: bool = bool(data.get("success", False))
        if not success:
            logger.info(
                "Turnstile verification failed: error_codes=%s",
                data.get("error-codes", []),
            )
        return success

    except httpx.HTTPStatusError as exc:
        logger.error(
            "Turnstile API HTTP error: status=%s body=%s",
            exc.response.status_code,
            exc.response.text,
        )
        return False
    except Exception as exc:
        logger.error("Turnstile verification unexpected error: %s", exc, exc_info=True)
        return False
