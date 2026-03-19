"""
Phase 2.5 + 3.5 + 5 — Abstract base adapter with permanent error classifier.
All platform adapters inherit from PlatformAdapter.
Permanent errors: never retry. Transient errors: exponential backoff. Rate limits: requeue only.
"""
import logging
from abc import ABC, abstractmethod
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorClass(str, Enum):
    TRANSIENT = "transient"         # network timeouts, 5xx — retry with backoff
    PERMANENT = "permanent"         # content policy, auth revoked — no retry
    RATE_LIMITED = "rate_limited"   # 429 — requeue, do NOT count as retry


# EC5 — Permanent error code map (Phase 3.5.1)
_PERMANENT_ERROR_CODES: dict[str, set] = {
    "instagram": {
        190,    # invalid access token
        10,     # permission denied
        200,    # no permission to manage posts
        9007,   # already published (treat as success — EC29)
        368,    # content policy violation
        32,     # page request limit reached (permanent for this page)
        100,    # invalid parameter
        "account_suspended",   # EC16: platform ban/suspension
        "access_revoked",      # EC16: user revoked access
    },
    "facebook": {
        190, 10, 200, 368, 100, 32,
        368,    # content policy blocked
        "account_suspended",   # EC16: platform ban/suspension
        "access_revoked",      # EC16: user revoked access
    },
    "youtube": {
        "forbidden", "quotaExceeded", "uploadLimitExceeded",
        "invalidVideoTitle", "invalidVideoDescription",
        "account_suspended",   # EC16: platform ban/suspension
        "access_revoked",      # EC16: user revoked access
    },
    "twitter": {
        187,    # duplicate tweet
        226,    # automated content policy
        261,    # app cannot perform write actions (suspended)
        326,    # account locked
        "account_suspended",   # EC16: platform ban/suspension
        "access_revoked",      # EC16: user revoked access
    },
    "linkedin": {
        "MEMBER_NOT_ELIGIBLE",
        "UNAUTHORIZED",
        "INVALID_CONTENT",
        "account_suspended",   # EC16: platform ban/suspension
        "access_revoked",      # EC16: user revoked access
    },
    "tiktok": {
        2200,   # video does not meet community guidelines
        2201,   # video content policy violation
        "account_suspended",   # EC16: platform ban/suspension
        "access_revoked",      # EC16: user revoked access
    },
}

_REVOCATION_SUBCODES = {458, 460}    # Instagram: permanent — do NOT refresh token (EC24)
_EXPIRY_SUBCODES = {463, 467}        # Instagram: temporary — refresh token


class PlatformError(Exception):
    """Base exception for all platform API errors."""
    def __init__(self, message: str, code=None, subcode=None, retry_after: int | None = None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.retry_after = retry_after


class PlatformHTTPError(PlatformError):
    """Non-200 HTTP response from platform."""
    def __init__(self, status_code: int, message: str, **kwargs):
        super().__init__(message, **kwargs)
        self.status_code = status_code


class PlatformAPIError(PlatformError):
    """Platform returned HTTP 200 but response body contains error field."""


class PlatformResponseError(PlatformError):
    """Platform response missing expected fields."""


class AlreadyPublishedError(PlatformError):
    """EC29 — Post was already published (treat as success)."""
    pass


def classify_error(exc: Exception, platform: str = "") -> ErrorClass:
    """
    Classifies an exception as TRANSIENT, PERMANENT, or RATE_LIMITED.
    This is the single source of truth for retry decisions.
    """
    if isinstance(exc, AlreadyPublishedError):
        return ErrorClass.PERMANENT  # Handled upstream as success

    if isinstance(exc, PlatformHTTPError):
        if exc.status_code == 429:
            return ErrorClass.RATE_LIMITED
        if exc.status_code in (401, 403):
            return ErrorClass.PERMANENT
        if exc.status_code >= 500:
            return ErrorClass.TRANSIENT

    if isinstance(exc, (PlatformAPIError, PlatformResponseError)):
        code = getattr(exc, "code", None)
        subcode = getattr(exc, "subcode", None)

        # EC16: account suspension / access revocation → always permanent
        if code in ("account_suspended", "access_revoked"):
            return ErrorClass.PERMANENT

        # EC24: Instagram revocation subcodes → permanent (don't refresh token)
        if subcode in _REVOCATION_SUBCODES:
            return ErrorClass.PERMANENT

        platform_codes = _PERMANENT_ERROR_CODES.get(platform, set())
        if code in platform_codes or str(code) in platform_codes:
            # EC29: Instagram error 9007 = already published → treat as success upstream
            return ErrorClass.PERMANENT

        # Default API errors: transient (network flap, platform outage)
        return ErrorClass.TRANSIENT

    # Unknown exceptions: transient by default
    return ErrorClass.TRANSIENT


class PlatformAdapter(ABC):
    """Abstract base class for all platform publishing adapters."""

    platform: str = ""

    @abstractmethod
    async def publish(self, post: dict) -> dict:
        """
        Publish a post. Returns dict with at least:
        {"post_url": str, "platform_post_id": str}
        Raises PlatformError subclass on failure.
        """

    async def pre_upload(self, post: dict) -> dict:
        """
        Phase 1.5 — Pre-upload phase for platforms with two-step publishing.
        Returns {"container_id": str} or {"video_id": str}.
        Default: no-op (platforms that don't need pre-upload).
        """
        return {}

    async def check_status(self, platform_post_id: str) -> str:
        """
        Phase 5 — Polling fallback. Query platform API for current post status.
        Returns: "published" | "processing" | "failed" | "pending"
        Default: raises NotImplementedError — platforms without polling support
        fall back to webhook-only confirmation.
        """
        raise NotImplementedError(f"{self.platform} does not support status polling")

    async def refresh_token(self, refresh_token: str) -> dict:
        """
        Refresh OAuth tokens. Returns {"access_token": str, "expires_at": datetime, ...}.
        Override in adapters that support token refresh.
        """
        raise NotImplementedError(f"{self.platform} does not support token refresh")

    def _check_response_for_error(self, response_json: dict, platform: str) -> None:
        """
        Phase 2.4.2 — Defensive response parsing.
        Raises PlatformAPIError if response body contains error field.
        """
        if "error" in response_json:
            err = response_json["error"]
            code = err.get("code") if isinstance(err, dict) else None
            subcode = err.get("error_subcode") if isinstance(err, dict) else None
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)

            # EC29: Instagram error 9007 = already published
            if platform == "instagram" and code == 9007:
                raise AlreadyPublishedError(msg, code=code)

            raise PlatformAPIError(msg, code=code, subcode=subcode)

        # Verify expected fields exist — log warning if missing
        if "id" not in response_json and "data" not in response_json:
            logger.warning("Platform response missing expected 'id' or 'data' field: %s", list(response_json.keys())[:5])
