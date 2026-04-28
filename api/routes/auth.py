"""
Auth routes — /me, /logout (JTI blocklist), /workspace (get-or-create).
Auto-creates MongoDB user + personal workspace on first Firebase login.
Phase 3.6.3: Login brute-force protection (Redis-backed attempt tracking).
Phase 9.6: Cloudflare Turnstile bot protection (opt-in via TURNSTILE_ENABLED env var).
"""
import logging
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from redis.exceptions import RedisError

from api.deps import CurrentUser, DB, CacheRedis
from api.limiter import limiter
from api.models.user import Plan, SubscriptionStatus, UserResponse, WorkspaceResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])

_TURNSTILE_ENABLED = os.environ.get("TURNSTILE_ENABLED", "false").lower() == "true"

# ── Request models ────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """Optional body accepted by /auth/login for Turnstile token."""
    cf_turnstile_token: str | None = None


class SignupRequest(BaseModel):
    """Optional body accepted by /auth/signup for Turnstile token."""
    cf_turnstile_token: str | None = None


# ── Turnstile helper ──────────────────────────────────────────────────────────

async def _verify_turnstile_if_enabled(token: str | None, ip: str) -> None:
    """
    When TURNSTILE_ENABLED=true, verify the Turnstile token.
    Raises HTTP 403 if verification fails or token is missing.
    When TURNSTILE_ENABLED=false (dev default) this is a no-op.
    """
    if not _TURNSTILE_ENABLED:
        return
    from utils.turnstile import verify_turnstile  # noqa: PLC0415
    ok = await verify_turnstile(token=token or "", ip=ip)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bot protection check failed. Please try again.",
        )


# ── Brute-force protection constants ──────────────────────────────────────────
_MAX_LOGIN_ATTEMPTS = 5
_IP_MAX_LOGIN_ATTEMPTS = 20   # higher threshold for IP — shared NAT/proxies
_LOGIN_LOCKOUT_SECONDS = 15 * 60  # 15 minutes

_DEFAULT_WORKSPACE_NAME = "Personal Workspace"


# ── Brute-force helpers ───────────────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    """Return real client IP, respecting X-Forwarded-For behind proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _check_login_attempts(cache_redis, email: str, ip: str) -> None:
    """Raise 429 if too many failed login attempts for this email or IP."""
    email_key = f"login_attempts:{email}"
    ip_key = f"login_attempts:ip:{ip}"
    try:
        email_count, ip_count = await cache_redis.mget(email_key, ip_key)
    except RedisError as exc:
        logger.warning("Skipping login-attempt check because cache Redis is unavailable: %s", exc)
        return
    if email_count and int(email_count) >= _MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account temporarily locked. Try again in 15 minutes.",
        )
    if ip_count and int(ip_count) >= _IP_MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again in 15 minutes.",
        )


async def _record_failed_login(cache_redis, email: str, ip: str) -> None:
    """Increment failed login counters (per-email and per-IP) with TTL."""
    try:
        pipe = cache_redis.pipeline()
        pipe.incr(f"login_attempts:{email}")
        pipe.expire(f"login_attempts:{email}", _LOGIN_LOCKOUT_SECONDS)
        pipe.incr(f"login_attempts:ip:{ip}")
        pipe.expire(f"login_attempts:ip:{ip}", _LOGIN_LOCKOUT_SECONDS)
        await pipe.execute()
    except RedisError as exc:
        logger.warning("Skipping failed-login tracking because cache Redis is unavailable: %s", exc)


async def _clear_login_attempts(cache_redis, email: str) -> None:
    """Clear per-email failed login counter on successful login."""
    try:
        await cache_redis.delete(f"login_attempts:{email}")
    except RedisError as exc:
        logger.warning("Skipping login-attempt reset because cache Redis is unavailable: %s", exc)


# ── /me ──────────────────────────────────────────────────────────────────────

@router.get("/auth/me", response_model=UserResponse)
@limiter.limit("20/minute")
async def get_me(
    request: Request,
    current_user: CurrentUser,
    db: DB,
) -> UserResponse:
    """
    Return authenticated user. Auto-creates user + personal workspace on first login.
    get_current_user dep verifies the Firebase JWT and fetches from MongoDB.
    If user doesn't exist yet (new Firebase signup), create it here.
    """
    # deps.get_current_user already guarantees user exists; but handle bootstrap
    # for deployments where user creation is deferred to this endpoint.
    user = current_user

    if not user.get("workspace_ids"):
        ws_id = await _ensure_personal_workspace(db, user["user_id"], user.get("display_name"))
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {
                "$set": {"default_workspace_id": ws_id},
                "$addToSet": {"workspace_ids": ws_id},
            },
        )
        user = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})

    # Coerce legacy DB null values so Pydantic validation doesn't crash on log-in
    if user.get("plan") is None:
        user["plan"] = "starter"
    if user.get("subscription_status") is None:
        user["subscription_status"] = "free"

    return UserResponse(**user)


# ── /login (with brute-force protection) ─────────────────────────────────────

@router.post("/auth/login", response_model=UserResponse)
@limiter.limit("20/minute")
async def login(
    request: Request,
    db: DB,
    cache_redis: CacheRedis,
    body: LoginRequest | None = None,
) -> UserResponse:
    """
    Verify Firebase ID token and return user record.
    Enforces brute-force protection: max 5 failed attempts per email per 15 min.
    When TURNSTILE_ENABLED=true, also verifies the cf_turnstile_token field.
    """
    import firebase_admin.auth as fb_auth
    from api.deps import get_firebase_app

    # Turnstile bot-protection check (no-op when TURNSTILE_ENABLED=false)
    client_ip = request.client.host if request.client else ""
    cf_token = body.cf_turnstile_token if body else None
    await _verify_turnstile_if_enabled(cf_token, client_ip)

    ip = _client_ip(request)

    auth_header = request.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing token",
        )

    # Decode token to extract email for rate-limit key
    try:
        get_firebase_app()
        decoded = fb_auth.verify_id_token(token)
    except Exception:
        # Record IP-level failure — email unknown at this point
        await _record_failed_login(cache_redis, "invalid_token", ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    email = decoded.get("email", decoded.get("uid", "unknown"))

    # Check brute-force lockout (per-email + per-IP)
    await _check_login_attempts(cache_redis, email, ip)

    uid = decoded.get("uid")
    user = await db.users.find_one({"firebase_uid": uid}, {"_id": 0})

    if user is None:
        # Auto-create user on first login
        display_name = decoded.get("name")
        user = await _auto_create_user(db, uid, email, display_name)

    # Phase 6.5 — MFA check (TOTP required if mfa_enabled)
    if user.get("mfa_enabled") and user.get("mfa_secret"):
        totp_code = request.headers.get("X-TOTP-Code", "").strip()
        if not totp_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"mfa_required": True, "message": "TOTP code required"},
            )
        from utils.mfa import verify_totp
        if not verify_totp(user["mfa_secret"], totp_code):
            await _record_failed_login(cache_redis, email, ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid TOTP code",
            )

    # Successful login — clear attempt counters
    await _clear_login_attempts(cache_redis, email)
    logger.info("Login successful: user=%s email=%s", user["user_id"], email)

    # Phase 6.5 — Account takeover detection (fire-and-forget, non-blocking)
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (
        request.client.host if request.client else "unknown"
    )
    import asyncio as _asyncio
    _asyncio.ensure_future(
        _check_account_takeover(db, user["user_id"], client_ip)
    )

    return UserResponse(**user)


# ── /signup ───────────────────────────────────────────────────────────────────

@router.post("/auth/signup", response_model=UserResponse)
@limiter.limit("10/minute")
async def signup(
    request: Request,
    db: DB,
    cache_redis: CacheRedis,
    body: SignupRequest | None = None,
) -> UserResponse:
    """
    Register / verify a new user after Firebase signup.

    The client performs Firebase signup client-side, then calls this endpoint
    with the resulting Firebase ID token in the Authorization header.
    When TURNSTILE_ENABLED=true, a valid cf_turnstile_token must be supplied
    in the request body to pass bot-protection before account creation.
    """
    import firebase_admin.auth as fb_auth
    from api.deps import get_firebase_app

    # Turnstile bot-protection check (no-op when TURNSTILE_ENABLED=false)
    client_ip = request.client.host if request.client else ""
    cf_token = body.cf_turnstile_token if body else None
    await _verify_turnstile_if_enabled(cf_token, client_ip)

    auth_header = request.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing token",
        )

    try:
        get_firebase_app()
        decoded = fb_auth.verify_id_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    uid = decoded.get("uid")
    email = decoded.get("email", decoded.get("uid", "unknown"))

    user = await db.users.find_one({"firebase_uid": uid}, {"_id": 0})
    if user is None:
        display_name = decoded.get("name")
        user = await _auto_create_user(db, uid, email, display_name)

    logger.info("Signup verified: user=%s email=%s", user["user_id"], email)
    return UserResponse(**user)


# ── /logout ───────────────────────────────────────────────────────────────────

@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def logout(
    request: Request,
    current_user: CurrentUser,
    cache_redis: CacheRedis,
) -> None:
    """
    Add the Firebase token JTI to Redis blocklist so it cannot be reused.
    get_current_user already verified the token; extract JTI from request state
    or re-examine the Authorization header.
    """
    # JTI is set on request state by the bearer dep if available;
    # fall back to extracting it directly from the decoded token.
    jti: str | None = getattr(request.state, "jti", None)

    if not jti:
        # Re-decode to get jti (already verified — safe to use .get without re-verify)
        auth_header = request.headers.get("authorization", "")
        token = auth_header.removeprefix("Bearer ").strip()
        if token:
            try:
                import firebase_admin.auth as fb_auth
                decoded = fb_auth.verify_id_token(token, check_revoked=False)
                jti = decoded.get("jti") or decoded.get("sub")
            except Exception:
                pass  # Token already verified by dep — proceed without jti

    if jti:
        # Block JTI for the remainder of its TTL (Firebase tokens last 1 hour = 3600s)
        block_key = f"jti_blocklist:{jti}"
        try:
            await cache_redis.setex(block_key, 3600, "1")
            logger.info("JTI blocklisted on logout: user=%s", current_user["user_id"])
        except RedisError as exc:
            logger.warning("Failed to persist logout JTI blocklist entry: %s", exc)


# ── /workspace ────────────────────────────────────────────────────────────────

@router.get("/auth/workspace", response_model=WorkspaceResponse)
@limiter.limit("20/minute")
async def get_or_create_workspace(
    request: Request,
    current_user: CurrentUser,
    db: DB,
) -> WorkspaceResponse:
    user_id = current_user["user_id"]
    default_ws_id = current_user.get("default_workspace_id")

    if default_ws_id:
        ws = await db.workspaces.find_one(
            {"workspace_id": default_ws_id, "owner_id": user_id},
            {"_id": 0},
        )
        if ws:
            return WorkspaceResponse(**ws)

    # Create personal workspace if missing
    ws_id = await _ensure_personal_workspace(db, user_id, current_user.get("display_name"))
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"default_workspace_id": ws_id}, "$addToSet": {"workspace_ids": ws_id}},
    )

    ws = await db.workspaces.find_one({"workspace_id": ws_id}, {"_id": 0})
    return WorkspaceResponse(**ws)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _ensure_personal_workspace(db, user_id: str, display_name: str | None) -> str:
    """Get or create the personal workspace for a user. Returns workspace_id."""
    existing = await db.workspaces.find_one(
        {"owner_id": user_id, "workspace_type": "personal"},
        {"workspace_id": 1},
    )
    if existing:
        return existing["workspace_id"]

    now = datetime.now(timezone.utc)
    workspace_name = f"{display_name or 'My'} {_DEFAULT_WORKSPACE_NAME}"
    ws_id = f"ws_{secrets.token_hex(12)}"

    ws_doc = {
        "workspace_id": ws_id,
        "name": workspace_name,
        "owner_id": user_id,
        "workspace_type": "personal",
        "members": [
            {"user_id": user_id, "role": "owner", "joined_at": now}
        ],
        "created_at": now,
    }
    await db.workspaces.insert_one(ws_doc)
    await db.workspace_members.insert_one({
        "workspace_id": ws_id,
        "user_id": user_id,
        "role": "owner",
        "joined_at": now,
    })
    logger.info("Personal workspace created: %s user=%s", ws_id, user_id)
    return ws_id


async def _check_account_takeover(db, user_id: str, client_ip: str) -> None:
    """
    Phase 6.5 — Background impossible-travel check.
    Performs a best-effort IP geo lookup then delegates to account_takeover module.
    Never raises — errors are logged and silently swallowed so login is unaffected.
    """
    try:
        lat: float | None = None
        lon: float | None = None
        try:
            import httpx
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(
                    f"http://ip-api.com/json/{client_ip}",
                    params={"fields": "status,lat,lon"},
                )
                geo = resp.json()
                if geo.get("status") == "success":
                    lat = float(geo["lat"])
                    lon = float(geo["lon"])
        except Exception:
            pass  # Geo lookup is best-effort — proceed with None lat/lon

        from utils.account_takeover import check_and_flag_takeover
        await check_and_flag_takeover(db, user_id, lat, lon, client_ip)
    except Exception as exc:
        logger.warning("Account takeover check failed (non-fatal): %s", exc)


async def _auto_create_user(db, firebase_uid: str, email: str, display_name: str | None) -> dict:
    """Bootstrap user record on first Firebase login."""
    now = datetime.now(timezone.utc)
    user_id = f"usr_{secrets.token_hex(12)}"

    user_doc = {
        "user_id": user_id,
        "firebase_uid": firebase_uid,
        "email": email,
        "display_name": display_name,
        "avatar_url": None,
        "plan": Plan.STARTER,
        "subscription_status": SubscriptionStatus.FREE,
        "subscription_end_date": None,
        "subscription_grace_period_end": None,
        "timezone": "UTC",
        "mfa_enabled": False,
        "role": "user",
        "onboarding_completed": False,
        "workspace_ids": [],
        "default_workspace_id": None,
        "created_at": now,
    }
    await db.users.insert_one(user_doc)
    user_doc.pop("_id", None)
    logger.info("User auto-created: %s firebase_uid=%s", user_id, firebase_uid)
    return user_doc


# ── MFA routes (Phase 6.5) ────────────────────────────────────────────────────

@router.post("/auth/mfa/setup")
@limiter.limit("10/minute")
async def mfa_setup(
    request: Request,
    current_user: CurrentUser,
    db: DB,
) -> dict:
    """
    Generate a TOTP secret and return the otpauth:// URI for QR code display.
    The secret is stored as pending_mfa_secret until the user calls /mfa/enable
    to confirm they can generate valid codes.
    """
    from utils.mfa import generate_totp_secret, get_totp_uri, encrypt_totp_secret

    secret = generate_totp_secret()
    uri = get_totp_uri(secret, current_user["email"])
    encrypted = encrypt_totp_secret(secret)

    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {"pending_mfa_secret": encrypted}},
    )
    logger.info("MFA setup initiated: user=%s", current_user["user_id"])
    # Return plain secret so the user can manually enter it in their authenticator app
    return {"totp_uri": uri, "secret": secret}


@router.post("/auth/mfa/enable")
@limiter.limit("10/minute")
async def mfa_enable(
    request: Request,
    current_user: CurrentUser,
    db: DB,
) -> dict:
    """
    Confirm MFA setup by verifying a TOTP code against the pending secret.
    On success, promotes pending_mfa_secret → mfa_secret and sets mfa_enabled=True.
    """
    from utils.mfa import verify_totp

    totp_code = request.headers.get("X-TOTP-Code", "").strip()
    if not totp_code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="X-TOTP-Code header required",
        )

    user = await db.users.find_one({"user_id": current_user["user_id"]}, {"_id": 0})
    pending = (user or {}).get("pending_mfa_secret")
    if not pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending MFA setup. Call /auth/mfa/setup first.",
        )

    if not verify_totp(pending, totp_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid TOTP code",
        )

    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {
            "$set": {"mfa_enabled": True, "mfa_secret": pending},
            "$unset": {"pending_mfa_secret": ""},
        },
    )
    logger.info("MFA enabled: user=%s", current_user["user_id"])
    return {"mfa_enabled": True}


@router.post("/auth/mfa/disable")
@limiter.limit("10/minute")
async def mfa_disable(
    request: Request,
    current_user: CurrentUser,
    db: DB,
) -> dict:
    """
    Disable MFA. Requires a valid TOTP code to prevent unauthorised disablement.
    """
    from utils.mfa import verify_totp

    totp_code = request.headers.get("X-TOTP-Code", "").strip()
    if not totp_code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="X-TOTP-Code header required to disable MFA",
        )

    user = await db.users.find_one({"user_id": current_user["user_id"]}, {"_id": 0})
    if not (user or {}).get("mfa_enabled"):
        return {"mfa_enabled": False}  # Already disabled — idempotent

    if not verify_totp(user["mfa_secret"], totp_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid TOTP code",
        )

    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {"mfa_enabled": False}, "$unset": {"mfa_secret": "", "pending_mfa_secret": ""}},
    )
    logger.info("MFA disabled: user=%s", current_user["user_id"])
    return {"mfa_enabled": False}
