"""
Error Classification System — Stage 3.5
Structured error codes for all failure modes in the publishing pipeline.
Based on Architecture Blueprint v2.8.
"""
from enum import Enum
from typing import Optional
from fastapi import HTTPException
from fastapi.responses import JSONResponse


class ErrorCode(str, Enum):
    # Authentication errors (AUTH_*)
    AUTH_TOKEN_INVALID = "AUTH_001"
    AUTH_TOKEN_EXPIRED = "AUTH_002"
    AUTH_INSUFFICIENT_PERMISSIONS = "AUTH_003"
    AUTH_SUBSCRIPTION_REQUIRED = "AUTH_004"
    AUTH_SUBSCRIPTION_EXPIRED = "AUTH_005"

    # Upload errors (UPLOAD_*)
    UPLOAD_TOO_LARGE = "UPLOAD_001"
    UPLOAD_INVALID_FORMAT = "UPLOAD_002"
    UPLOAD_USER_LIMIT = "UPLOAD_003"       # per-user concurrent upload limit
    UPLOAD_SYSTEM_BUSY = "UPLOAD_004"      # global queue full
    UPLOAD_STORAGE_FAILED = "UPLOAD_005"

    # Post errors (POST_*)
    POST_NOT_FOUND = "POST_001"
    POST_INVALID_PLATFORM = "POST_002"
    POST_NO_ACCOUNTS = "POST_003"
    POST_SCHEDULE_REQUIRES_SUB = "POST_004"
    POST_DUPLICATE = "POST_005"

    # Publishing errors (PUB_*) — EC codes from architecture doc
    PUB_NETWORK_TIMEOUT = "PUB_001"        # EC1
    PUB_MEDIA_UNAVAILABLE = "PUB_002"      # EC2 — media URL 404 at publish time
    PUB_PLATFORM_RATE_LIMIT = "PUB_003"   # EC3
    PUB_TOKEN_EXPIRED = "PUB_004"          # EC4 — OAuth token expired
    PUB_TOKEN_REFRESH_FAILED = "PUB_005"  # EC5
    PUB_MEDIA_FORMAT_REJECTED = "PUB_006" # EC6 — platform rejected the format
    PUB_CAPTION_TOO_LONG = "PUB_007"      # EC7
    PUB_DUPLICATE_POST = "PUB_008"        # EC8 — platform flagged as duplicate
    PUB_ACCOUNT_SUSPENDED = "PUB_009"     # EC9
    PUB_MEDIA_PROCESSING_FAILED = "PUB_010"  # EC10 — video processing timed out
    PUB_UNKNOWN_PLATFORM_ERROR = "PUB_099"

    # Platform account errors (ACCT_*)
    ACCT_NOT_FOUND = "ACCT_001"
    ACCT_INACTIVE = "ACCT_002"
    ACCT_OAUTH_FAILED = "ACCT_003"
    ACCT_RECONNECT_REQUIRED = "ACCT_004"

    # Workspace errors (WS_*)
    WS_NOT_FOUND = "WS_001"
    WS_MEMBER_LIMIT = "WS_002"
    WS_INVITE_EXPIRED = "WS_003"
    WS_INVITE_WRONG_EMAIL = "WS_004"
    WS_PERMISSION_DENIED = "WS_005"

    # System errors (SYS_*)
    SYS_DATABASE_ERROR = "SYS_001"
    SYS_EXTERNAL_SERVICE = "SYS_002"
    SYS_RATE_LIMITED = "SYS_003"


def api_error(
    status_code: int,
    error_code: ErrorCode,
    message: str,
    details: Optional[dict] = None,
) -> HTTPException:
    """Create a structured API error with consistent format."""
    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": error_code.value,
            "message": message,
            "details": details or {},
        }
    )


def structured_error_response(
    status_code: int,
    error_code: ErrorCode,
    message: str,
    details: Optional[dict] = None,
) -> JSONResponse:
    """Return a JSONResponse with structured error format."""
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error_code": error_code.value,
            "message": message,
            "details": details or {},
        }
    )


# Classify platform-specific error strings into EC codes
def classify_platform_error(platform: str, error_str: str) -> ErrorCode:
    """Map platform error messages to structured EC codes."""
    err = error_str.lower()
    if any(k in err for k in ["rate limit", "too many", "quota"]):
        return ErrorCode.PUB_PLATFORM_RATE_LIMIT
    if any(k in err for k in ["token", "auth", "oauth", "expired", "invalid_token"]):
        return ErrorCode.PUB_TOKEN_EXPIRED
    if any(k in err for k in ["timeout", "timed out", "connection"]):
        return ErrorCode.PUB_NETWORK_TIMEOUT
    if any(k in err for k in ["format", "codec", "resolution", "aspect"]):
        return ErrorCode.PUB_MEDIA_FORMAT_REJECTED
    if any(k in err for k in ["duplicate", "already posted", "identical"]):
        return ErrorCode.PUB_DUPLICATE_POST
    if any(k in err for k in ["suspended", "disabled", "banned"]):
        return ErrorCode.PUB_ACCOUNT_SUSPENDED
    if any(k in err for k in ["caption", "text", "too long", "character"]):
        return ErrorCode.PUB_CAPTION_TOO_LONG
    if any(k in err for k in ["processing", "transcode", "status_code"]):
        return ErrorCode.PUB_MEDIA_PROCESSING_FAILED
    return ErrorCode.PUB_UNKNOWN_PLATFORM_ERROR
