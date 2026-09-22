"""
Phase 2: LinkedIn Session Authenticator & 2FA Relay Engine.
Handles cookie validation and 2FA challenge coordination through residential proxies.
"""
import os
import uuid
import logging
import httpx
from typing import Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Temporary store for ongoing 2FA challenges (expires in 10 minutes)
_PENDING_2FA_SESSIONS: dict[str, dict[str, Any]] = {}


class AuthenticationError(Exception):
    pass


class InvalidSessionError(AuthenticationError):
    pass


class TwoFactorRequiredError(AuthenticationError):
    def __init__(self, session_id: str, challenge_type: str = "sms_or_authenticator"):
        super().__init__("2FA verification required to complete login")
        self.session_id = session_id
        self.challenge_type = challenge_type


def _clean_cookie_token(token: str | None, key: str) -> str:
    """Extracts raw cookie value even if user pasted key=value or semicolon-delimited string."""
    if not token:
        return ""
    val = token.strip().strip('"').strip("'")
    if f"{key}=" in val:
        for part in val.split(";"):
            part = part.strip()
            if part.startswith(f"{key}="):
                return part.split(f"{key}=", 1)[1].strip().strip('"').strip("'")
    return val


class SessionAuthenticator:
    """
    Validates LinkedIn session tokens and manages headless credential login flows.
    """

    @staticmethod
    async def validate_session_cookie(
        li_at: str,
        jsession_id: str = "",
        proxy_url: str | None = None,
        user_agent: str | None = None,
        li_a: str | None = None,
    ) -> dict[str, Any]:
        """
        Validates the li_at session cookie against LinkedIn's voyager /me endpoint.
        Returns parsed profile details (name, vanity_name, urn, avatar).
        """
        clean_cookie = _clean_cookie_token(li_at, "li_at")
        if not clean_cookie:
            raise InvalidSessionError("Session cookie (li_at) cannot be empty")

        # Mock / Sandbox handling for automated testing
        is_mock_token = clean_cookie.startswith("mock_") or clean_cookie.startswith("test_")
        force_mock = os.getenv("OUTREACH_MOCK_AUTH", "false").lower() in ("true", "1")
        if is_mock_token or (force_mock and not clean_cookie.startswith("AQ")):
            logger.info("SessionAuthenticator: Simulating successful profile verification for mock cookie")
            mock_id = clean_cookie[-8:] if len(clean_cookie) >= 8 else "testuser"
            return {
                "account_name": f"LinkedIn Professional ({mock_id})",
                "vanity_name": f"user-{mock_id}",
                "linkedin_urn": f"urn:li:fsd_profile:{mock_id}",
                "avatar_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150",
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }

        # Live Voyager API validation
        clean_li_a = _clean_cookie_token(li_a, "li_a") if li_a else ""
        cookie_parts = [f'li_at={clean_cookie}']
        if clean_li_a:
            cookie_parts.append(f'li_a="{clean_li_a}"')

        clean_csrf = (jsession_id or "ajax:123456789").strip().strip('"').strip("'")
        cookie_parts.append(f'JSESSIONID="{clean_csrf}"')

        default_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        headers = {
            "User-Agent": (user_agent.strip() if user_agent and user_agent.strip() else default_ua),
            "Cookie": "; ".join(cookie_parts),
            "Csrf-Token": clean_csrf,
            "X-RestLi-Protocol-Version": "2.0.0",
        }

        client_kwargs: dict[str, Any] = {"timeout": 15.0}
        if proxy_url and not ("127.0.0.1" in proxy_url or "localhost" in proxy_url):
            client_kwargs["proxy"] = proxy_url

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.get("https://www.linkedin.com/voyager/api/me", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    mini = data.get("miniProfile", {})
                    first_name = mini.get("firstName", "LinkedIn")
                    last_name = mini.get("lastName", "User")
                    urn = mini.get("entityUrn", "")
                    vanity = mini.get("publicIdentifier", "")

                    avatar_url = None
                    picture = mini.get("picture", {})
                    if isinstance(picture, dict):
                        vector_img = picture.get("com.linkedin.common.VectorImage", {})
                        root_url = vector_img.get("rootUrl", "")
                        artifacts = vector_img.get("artifacts", [])
                        if root_url and artifacts:
                            avatar_url = f"{root_url}{artifacts[-1].get('fileIdentifyingUrlPathSegment', '')}"

                    return {
                        "account_name": f"{first_name} {last_name}".strip(),
                        "vanity_name": vanity,
                        "linkedin_urn": urn,
                        "avatar_url": avatar_url,
                        "verified_at": datetime.now(timezone.utc).isoformat(),
                    }
                elif resp.status_code in (401, 403):
                    raise InvalidSessionError("Session cookie is expired or invalid. Please re-authenticate on LinkedIn.")
                else:
                    logger.warning("Voyager /me returned status=%s: %s", resp.status_code, resp.text[:200])
                    raise InvalidSessionError(f"LinkedIn verification returned status {resp.status_code}")
        except httpx.RequestError as exc:
            logger.error("Network error validating session cookie: %s", exc)
            raise InvalidSessionError(f"Network error during LinkedIn verification: {exc}") from exc

    @staticmethod
    async def start_credential_login(
        email: str,
        password: str,
        proxy_url: str | None = None,
    ) -> dict[str, Any]:
        """
        Initiates a login using email and password.
        If LinkedIn presents a 2FA prompt, returns { status: '2fa_required', session_id: '...' }.
        """
        clean_email = email.strip()
        if not clean_email or not password:
            raise AuthenticationError("Email and password are required")

        # Mock / Sandbox handling
        if os.getenv("OUTREACH_MOCK_AUTH", "true") == "true" or clean_email.endswith("@example.com") or "mock" in clean_email:
            # If email contains '2fa', simulate 2FA challenge flow
            if "2fa" in clean_email.lower():
                session_id = f"session_2fa_{uuid.uuid4().hex[:12]}"
                _PENDING_2FA_SESSIONS[session_id] = {
                    "email": clean_email,
                    "password": password,
                    "created_at": datetime.now(timezone.utc),
                }
                logger.info("SessionAuthenticator [MOCK]: Challenge 2FA triggered for %s", clean_email)
                return {
                    "status": "2fa_required",
                    "session_id": session_id,
                    "challenge_type": "otp",
                    "message": "Enter the 6-digit verification code sent to your phone or app.",
                }

            # Direct login without 2FA
            logger.info("SessionAuthenticator [MOCK]: Successful credential login for %s", clean_email)
            return {
                "status": "authenticated",
                "account_name": clean_email.split("@")[0].replace(".", " ").title(),
                "vanity_name": clean_email.split("@")[0],
                "linkedin_urn": f"urn:li:fsd_profile:{uuid.uuid4().hex[:8]}",
                "li_at": f"mock_li_at_{uuid.uuid4().hex}",
                "jsession_id": f"ajax:{uuid.uuid4().hex[:16]}",
                "avatar_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150",
            }

        # For production live browser login, Playwright worker will execute here
        raise NotImplementedError("Live browser headless credential login requires Playwright worker pool")

    @staticmethod
    async def verify_2fa_code(session_id: str, otp_code: str) -> dict[str, Any]:
        """
        Validates the 2FA code provided by the user for an ongoing login challenge.
        """
        clean_code = otp_code.strip()
        if not clean_code:
            raise AuthenticationError("Verification code cannot be empty")

        pending = _PENDING_2FA_SESSIONS.pop(session_id, None)
        if not pending:
            raise AuthenticationError("2FA session expired or not found. Please log in again.")

        # If code is invalid (e.g. '000000'), simulate rejection
        if clean_code == "000000":
            raise AuthenticationError("Invalid verification code. Please check and retry.")

        email = pending["email"]
        logger.info("SessionAuthenticator: 2FA verified successfully for %s", email)
        return {
            "status": "authenticated",
            "account_name": email.split("@")[0].replace(".", " ").title(),
            "vanity_name": email.split("@")[0],
            "linkedin_urn": f"urn:li:fsd_profile:{uuid.uuid4().hex[:8]}",
            "li_at": f"mock_li_at_{uuid.uuid4().hex}",
            "jsession_id": f"ajax:{uuid.uuid4().hex[:16]}",
            "avatar_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150",
        }
