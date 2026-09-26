"""Validate an existing LinkedIn session through its assigned proxy."""
import os
import logging
import httpx
from typing import Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class AuthenticationError(Exception):
    pass


class InvalidSessionError(AuthenticationError):
    pass


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
    Validates LinkedIn session tokens without accepting a member password.
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
        if is_mock_token and not force_mock:
            raise InvalidSessionError("Test LinkedIn cookies are unavailable outside sandbox mode")
        if force_mock and (is_mock_token or not clean_cookie.startswith("AQ")):
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

        clean_csrf = (jsession_id or "").strip().strip('"').strip("'")
        if not clean_csrf:
            raise InvalidSessionError("JSESSIONID is required to verify a LinkedIn session cookie")
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
                    first_name = mini.get("firstName", "")
                    last_name = mini.get("lastName", "")
                    urn = mini.get("entityUrn", "")
                    vanity = mini.get("publicIdentifier", "")
                    if not urn or not (first_name or last_name):
                        raise InvalidSessionError("LinkedIn did not return a verifiable profile for this session")

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
            logger.error("Network error validating LinkedIn session (%s)", type(exc).__name__)
            raise InvalidSessionError("Network error during LinkedIn verification") from exc
