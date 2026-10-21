"""
Phase 5: LinkedIn Private Voyager REST API Client.
Executes 80% of lightweight network operations (profile viewing, connection checking,
messaging polling, post liking) without headless browser overhead.
"""
import os
import logging
import hashlib
from typing import Any
from urllib.parse import urlparse, parse_qs
import httpx
from datetime import datetime, timezone, timedelta
from outreach.core.crypto import decrypt_secret
from outreach.core.request_guard import RequestEnvelope, RequestDenied

logger = logging.getLogger(__name__)

VOYAGER_BASE_URL = "https://www.linkedin.com/voyager/api"


def parse_linkedin_search_url(url: str) -> dict[str, Any]:
    from outreach.core.search_sources import SearchSourceError, parse_search_source
    try:
        return parse_search_source(url)
    except SearchSourceError as exc:
        return {"is_valid": False, "error_code": exc.code, "error": str(exc)}


class VoyagerRestrictionError(RuntimeError):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"LinkedIn returned HTTP {status_code}")


class VoyagerClient:
    """
    Authenticated client for LinkedIn internal Voyager API.
    Routes all traffic through the account's 1:1 dedicated residential proxy.
    """

    def __init__(
        self,
        session_cookie_enc: str = "",
        jsession_id: str = "",
        proxy_url: str | None = None,
        li_at: str | None = None,
        li_a: str | None = None,
        user_agent: str | None = None,
        request_envelope: RequestEnvelope | None = None,
    ):
        if any(value and value.startswith("uc1:") for value in (session_cookie_enc, jsession_id, li_at, li_a)):
            from outreach.core.credential_custody import CustodyUnavailable
            raise CustodyUnavailable("Scoped session opening is required before transport")
        raw_cookie = li_at or (decrypt_secret(session_cookie_enc) if session_cookie_enc else "")
        self.session_cookie = raw_cookie.removeprefix("li_at=")
        mock_mode = os.getenv("OUTREACH_MOCK_AUTH", "false").lower() in {"true", "1"}
        csrf_cookie = decrypt_secret(jsession_id) if jsession_id.startswith("gAAAAA") else jsession_id
        if not mock_mode and self.session_cookie.startswith(("mock_", "test_")):
            raise ValueError("Test LinkedIn sessions cannot be used for live outreach")
        if not mock_mode and not csrf_cookie and not mock_mode:
            raise ValueError("Sender JSESSIONID is missing. Reconnect the LinkedIn account.")
        self.jsession_id = csrf_cookie or "ajax:123456789"
        self.proxy_url = proxy_url
        self.li_a = li_a
        self.user_agent = user_agent or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        self.is_mock = mock_mode
        self.request_envelope = request_envelope

    async def _request(self, client, method: str, url: str, **kwargs):
        """Every live Voyager subrequest enters the shared physical boundary."""
        parsed = urlparse(url)
        if (not self.request_envelope or not self.proxy_url or self.proxy_url != self.request_envelope.proxy_url
                or parsed.scheme != "https" or parsed.hostname != "www.linkedin.com"
                or not parsed.path.startswith("/voyager/api/")):
            raise RequestDenied("request_scope_required")
        action = kwargs.pop("action", "read")
        if method != "GET" and action == "read":
            path = parsed.path.lower()
            action = ("invite" if "invitation" in path else "voice" if "audio" in path else
                      "message" if "messaging" in path else "comment" if "comment" in path else
                      "like" if "reaction" in path or "like" in path else "visit")
        return await self.request_envelope.call(method, parsed.path,
            lambda: getattr(client, method.lower())(url, **kwargs), action=action)

    def _get_headers(self) -> dict[str, str]:
        cookie_parts = [f"li_at={self.session_cookie}", f'JSESSIONID="{self.jsession_id}"']
        if self.li_a:
            cookie_parts.append(f"li_a={self.li_a}")
        return {
            "User-Agent": self.user_agent,
            "Cookie": "; ".join(cookie_parts),
            "Csrf-Token": self.jsession_id,
            "X-RestLi-Protocol-Version": "2.0.0",
            "Accept": "application/vnd.linkedin.normalized+json+2.1",
        }

    @staticmethod
    def _update_media_urls(update: dict[str, Any]) -> list[str]:
        """Extract linked images/documents/articles from supported Voyager media shapes."""
        found: list[str] = []

        def add(value: Any) -> None:
            if isinstance(value, str) and value.startswith("https://") and value not in found:
                found.append(value)

        def walk(value: Any, depth: int = 0) -> None:
            if depth > 5 or len(found) >= 8:
                return
            if isinstance(value, list):
                for item in value:
                    walk(item, depth + 1)
            elif isinstance(value, dict):
                root = value.get("rootUrl")
                for artifact in value.get("artifacts") or []:
                    if isinstance(artifact, dict) and isinstance(root, str):
                        add(root + str(artifact.get("fileIdentifyingUrlPathSegment", "")))
                for key in ("url", "navigationUrl", "originalUrl"):
                    add(value.get(key))
                for key in ("media", "content", "images", "image", "attachments", "article", "document", "vectorImage"):
                    if key in value:
                        walk(value[key], depth + 1)

        for key in ("media", "content", "attachments", "article", "document"):
            if key in update:
                walk(update[key])
        return found[:8]

    async def _resolve_profile_urn(self, profile_identifier: str) -> str | None:
        """Resolve a profile URL to a verified LinkedIn member URN."""
        if profile_identifier.startswith("urn:"):
            return profile_identifier
        parsed = urlparse(profile_identifier)
        hostname = (parsed.hostname or "").lower()
        if hostname in {"linkedin.com", "www.linkedin.com"} and "/in/" in parsed.path:
            vanity_name = parsed.path.rstrip("/").split("/")[-1]
        else:
            vanity_name = profile_identifier.strip().strip("/")
        if not vanity_name or "/" in vanity_name:
            return None
        profile = await self.fetch_profile_info(vanity_name)
        if not profile.get("verified"):
            return None
        return profile.get("profile_urn")

    async def check_connection_status(self, profile_urn: str) -> bool:
        """
        Checks if the target profile has accepted our connection request.
        """
        if self.is_mock:
            # In mock mode, profiles ending in 'accepted' or even IDs return True
            logger.info("VoyagerClient [MOCK]: check_connection_status for %s", profile_urn)
            return True

        target_vanity = urlparse(profile_urn).path.rstrip("/").split("/")[-1] if "/in/" in profile_urn else ""
        target_urn = await self._resolve_profile_urn(profile_urn)
        if not target_urn:
            return False

        url = f"{VOYAGER_BASE_URL}/relationships/connections?count=1000"
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=12.0) as client:
                resp = await self._request(client, "GET", url, headers=self._get_headers())
                if resp.status_code == 200:
                    data = resp.json()
                    elements = data.get("elements", []) if isinstance(data, dict) else []
                    identifiers = {value for value in (target_urn, profile_urn, target_vanity) if value}
                    for element in elements:
                        if not isinstance(element, dict):
                            continue
                        candidate_values = {
                            element.get("entityUrn"),
                            element.get("profileUrn"),
                            element.get("memberUrn"),
                            element.get("publicIdentifier"),
                            (element.get("miniProfile") or {}).get("entityUrn") if isinstance(element.get("miniProfile"), dict) else None,
                        }
                        if identifiers.intersection(value for value in candidate_values if isinstance(value, str)):
                            return True
                return False
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager check_connection_status error: %s", type(exc).__name__)
            return False

    async def check_connection_status_strict(self, profile_urn: str) -> bool | None:
        """Return True/False only with conclusive evidence; None means unknown.

        A failed request or a partial connection page cannot prove that a lead
        is not connected. The sequence runner must never route those cases to
        the negative branch.
        """
        if self.is_mock:
            return True
        target_urn = await self._resolve_profile_urn(profile_urn)
        if not target_urn:
            return None
        target_vanity = urlparse(profile_urn).path.rstrip("/").split("/")[-1] if "/in/" in profile_urn else ""
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=12.0) as client:
                response = await self._request(client, "GET",
                    f"{VOYAGER_BASE_URL}/relationships/connections?count=1000",
                    headers=self._get_headers(),
                )
            if response.status_code != 200:
                return None
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
                return None
            elements = data["elements"]
            identifiers = {value for value in (target_urn, profile_urn, target_vanity) if value}
            for element in elements:
                if not isinstance(element, dict):
                    continue
                mini_profile = element.get("miniProfile")
                values = (
                    element.get("entityUrn"), element.get("profileUrn"),
                    element.get("memberUrn"), element.get("publicIdentifier"),
                    mini_profile.get("entityUrn") if isinstance(mini_profile, dict) else None,
                )
                if identifiers.intersection(value for value in values if isinstance(value, str)):
                    return True
            paging = data.get("paging") or {}
            total = paging.get("total") if isinstance(paging, dict) else None
            if isinstance(total, int) and total <= len(elements):
                return False
            return None
        except RequestDenied:
            raise
        except Exception as exc:
            logger.warning("Voyager connection status uncertain (%s)", type(exc).__name__)
            return None

    async def observe_original_connection(self, recipient_urn: str) -> dict[str, Any]:
        """Observe only the immutable recipient recorded by the original invite.

        Never resolve a current vanity URL or manufacture mock acceptance.
        """
        from outreach.core.connection_evidence import recipient_key, parse_connection_page
        unknown = {'connected': None, 'request_id': None}
        if self.is_mock or not recipient_key(recipient_urn) or not self.request_envelope:
            return unknown
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=12.0) as client:
                response = await self._request(client, 'GET',
                    f'{VOYAGER_BASE_URL}/relationships/connections?count=1000', headers=self._get_headers())
            if response.status_code != 200 or len(response.content) > 1_000_000:
                return unknown
            connected = parse_connection_page(response.json(), recipient_urn)
            receipt = await self.request_envelope.record_connection_fact(recipient_urn,
                kind='observed_connection', connected=connected)
            return {'connected': connected, 'request_id': receipt}
        except RequestDenied:
            raise
        except Exception as exc:
            logger.warning('Original connection observation unavailable (%s)', type(exc).__name__)
            return unknown

    async def fetch_profile_info(self, vanity_name: str) -> dict[str, Any]:
        """
        Fetches real profile data (name, headline, avatar, URN) from LinkedIn Voyager.
        Used during contact enrichment to replace fake data derived from vanity slugs.
        """
        if self.is_mock:
            return {
                "full_name": "LinkedIn Member",
                "headline": "",
                "avatar_url": "",
                "profile_urn": "",
                "verified": False,
                "mock": True,
            }

        url = f"{VOYAGER_BASE_URL}/identity/profiles/{vanity_name}/profileView"
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=12.0) as client:
                resp = await self._request(client, "GET", url, headers=self._get_headers())
                if resp.status_code != 200:
                    return {
                        "full_name": "",
                        "headline": "",
                        "avatar_url": "",
                        "profile_urn": "",
                        "status_code": resp.status_code,
                        "verified": False,
                    }

                data = resp.json()
                if not isinstance(data, dict):
                    return {"full_name": "", "headline": "", "avatar_url": "", "profile_urn": "", "verified": False}
                candidates = [data.get("profile"), data.get("data"), data]
                candidates.extend(data.get("included", []) if isinstance(data.get("included"), list) else [])
                profile = next((item for item in candidates if isinstance(item, dict)
                                and (item.get("firstName") or item.get("lastName"))), {})
                first_name = profile.get("firstName", "")
                last_name = profile.get("lastName", "")
                full_name = f"{first_name} {last_name}".strip()

                # Extract avatar URL from display image
                avatar_url = ""
                display = profile.get("displayImageReference") or {}
                vector = (display.get("vectorImage") or {}) if isinstance(display, dict) else {}
                img_artifacts = vector.get("artifacts", [])
                if img_artifacts:
                    # Pick the 200x200 or last available size
                    best = img_artifacts[-1]
                    root = vector.get("rootUrl", "")
                    avatar_url = f"{root}{best.get('fileIdentifyingUrlPathSegment', '')}"

                # Extract profile URN
                entity_urn = profile.get("entityUrn", "")
                profile_urn = entity_urn or ""
                current_position = profile.get("currentPosition") or {}
                if not isinstance(current_position, dict):
                    current_position = {}

                skills = profile.get("skills") or data.get("skillView", {}).get("elements") or []
                top_skill = ""
                if isinstance(skills, list) and skills:
                    first_skill = skills[0]
                    top_skill = first_skill.get("name", "") if isinstance(first_skill, dict) else str(first_skill)

                educations = profile.get("educations") or data.get("educationView", {}).get("elements") or []
                school_name = ""
                if isinstance(educations, list) and educations:
                    first_edu = educations[0]
                    if isinstance(first_edu, dict):
                        school_name = first_edu.get("schoolName", "")

                return {
                    "full_name": full_name,
                    "headline": profile.get("headline", ""),
                    "avatar_url": avatar_url,
                    "profile_urn": profile_urn,
                    "company": current_position.get("companyName", "") or profile.get("companyName", ""),
                    "job_title": current_position.get("title", "") or profile.get("occupation", ""),
                    "industry": profile.get("industryName", ""),
                    "summary": profile.get("summary", ""),
                    "company_location": current_position.get("locationName", "") or profile.get("geoLocationName", ""),
                    "connections_count": profile.get("connectionsCount") or profile.get("numConnections"),
                    "top_skill": top_skill,
                    "school": school_name,
                    "is_open_profile": bool(profile.get("openLink") or profile.get("premiumOpenLink")),
                    "verified": bool(entity_urn and full_name),
                }
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager fetch_profile_info error (%s)", type(exc).__name__)
            return {
                "full_name": "",
                "headline": "",
                "avatar_url": "",
                "profile_urn": "",
                "verified": False,
            }

    async def visit_profile(self, profile_url: str) -> dict[str, Any]:
        """
        Triggers a genuine profile view on LinkedIn so the prospect sees 'Viewed your profile'.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Simulated profile view on %s", profile_url)
            return {"status": "viewed", "timestamp": datetime.now(timezone.utc).isoformat()}

        # Live Voyager view endpoint
        url = f"{VOYAGER_BASE_URL}/identity/profiles/view"
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=12.0) as client:
                resp = await self._request(client, "POST", url, headers=self._get_headers(), json={"profileUrl": profile_url})
                if resp.status_code in (200, 201, 202, 204):
                    return {"status": "viewed", "http_status": resp.status_code}
                return {"status": "failed", "http_status": resp.status_code, "text": resp.text[:200]}
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager visit_profile error: %s", type(exc).__name__)
            return {"status": "failed", "error": "LinkedIn request could not be confirmed", "status_code": getattr(exc, "status_code", None)}

    async def send_connection_invite(self, profile_urn: str, custom_note: str = "") -> dict[str, Any]:
        """
        Dispatches a connection invitation to a 2nd/3rd degree prospect.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Dispatched connection invite to %s with note=%s", profile_urn, custom_note[:30])
            return {"status": "invite_sent", "timestamp": datetime.now(timezone.utc).isoformat()}

        if not self.request_envelope:
            raise RequestDenied("content_approval_required")
        self.request_envelope.assert_content("invite", profile_urn, {"body": custom_note})

        resolved_urn = await self._resolve_profile_urn(profile_urn)
        from outreach.core.connection_evidence import recipient_key
        if not recipient_key(resolved_urn):
            raise RequestDenied('original_recipient_identity_unavailable')
        if not resolved_urn:
            return {"status": "failed", "error": "Could not resolve this LinkedIn profile to a verified member ID."}

        url = f"{VOYAGER_BASE_URL}/growth/normInvitations"
        payload = {
            "invitee": {"inviteeUnion": {"memberProfileUrn": resolved_urn}},
            "customMessage": custom_note if custom_note else None,
        }
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await self._request(client, "POST", url, headers=self._get_headers(), json=payload)
                if resp.status_code in (200, 201):
                    from outreach.core.connection_evidence import recipient_key
                    body = resp.json()
                    if not isinstance(body, dict) or any(key in body for key in ('error', 'errors')):
                        return {'status': 'failed', 'http_status': resp.status_code}
                    if (recipient_key(resolved_urn) and isinstance(body, dict)
                            and not any(key in body for key in ('error', 'errors'))
                            and isinstance(self.request_envelope.received_receipt, dict)):
                        receipt = await self.request_envelope.record_connection_fact(resolved_urn, kind='invite_target')
                        return {'status': 'invite_sent', 'provider_recipient_urn': resolved_urn, 'provider_request_id': receipt}
                    return {"status": "invite_sent"}
                return {"status": "failed", "status_code": resp.status_code, "text": resp.text[:200]}
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager send_connection_invite error: %s", type(exc).__name__)
            return {"status": "error", "error": "LinkedIn request could not be confirmed", "status_code": getattr(exc, "status_code", None)}

    async def send_direct_message(
        self,
        recipient_urn: str,
        message_body: str,
        attachment_url: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Sends a standard text direct message (with optional attachment) to a 1st degree connection.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Dispatched DM to %s: %s", recipient_urn, message_body[:40])
            res: dict[str, Any] = {"status": "message_sent", "timestamp": datetime.now(timezone.utc).isoformat()}
            if attachment_url:
                res["attachment_url"] = attachment_url
                res["attachment_name"] = attachment_name or "attachment"
            return res

        if not self.request_envelope:
            raise RequestDenied("content_approval_required")
        self.request_envelope.assert_content("message", recipient_urn, {"body": message_body})

        resolved_urn = await self._resolve_profile_urn(recipient_urn)
        if not resolved_urn:
            return {"status": "failed", "error": "Could not resolve this LinkedIn profile to a verified member ID."}

        url = f"{VOYAGER_BASE_URL}/messaging/conversations"
        msg_obj: dict[str, Any] = {"body": message_body}
        if attachment_url:
            msg_obj["attachments"] = [{"name": attachment_name or "document", "reference": attachment_url}]
        payload = {
            "recipients": [resolved_urn],
            "message": msg_obj,
        }
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await self._request(client, "POST", url, headers=self._get_headers(), json=payload)
                if resp.status_code in (200, 201):
                    return {"status": "message_sent"}
                return {"status": "failed", "status_code": resp.status_code}
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager send_direct_message error: %s", type(exc).__name__)
            return {"status": "error", "error": "LinkedIn request could not be confirmed", "status_code": getattr(exc, "status_code", None)}

    async def like_last_post(self, profile_urn: str, max_age_days: int = 30) -> dict[str, Any]:
        """
        Likes the prospect's most recent post or article.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Liked last post for %s", profile_urn)
            return {"status": "liked", "timestamp": datetime.now(timezone.utc).isoformat()}

        resolved_urn = await self._resolve_profile_urn(profile_urn)
        if not resolved_urn:
            return {"status": "failed", "error": "Could not resolve this LinkedIn profile to a verified member ID."}
        profile_urn = resolved_urn
        updates = await self.fetch_profile_recent_updates(profile_urn, count=20)
        if not updates:
            return {"status": "failed", "error": "No recent post found for this profile"}
        max_age = max(1, int(max_age_days))
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age)
        for update in updates:
            published_at = update.get("published_at")
            if isinstance(published_at, (int, float)):
                published_at = datetime.fromtimestamp(published_at / (1000 if published_at > 10**12 else 1), tz=timezone.utc)
            elif isinstance(published_at, str):
                try:
                    published_at = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    if published_at.tzinfo is None:
                        published_at = published_at.replace(tzinfo=timezone.utc)
                except ValueError:
                    published_at = None
            if published_at is None or published_at < cutoff:
                continue
            if update.get("post_urn"):
                return await self.like_update(update["post_urn"])
        return {"status": "failed", "error": f"No post found within the last {max_age} days"}

    async def follow_profile(self, profile_urn: str) -> dict[str, Any]:
        """
        Follows a target LinkedIn member profile.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Followed profile %s", profile_urn)
            return {"status": "followed", "timestamp": datetime.now(timezone.utc).isoformat()}

        resolved_urn = await self._resolve_profile_urn(profile_urn)
        if not resolved_urn:
            return {"status": "failed", "error": "Could not resolve this LinkedIn profile to a verified member ID."}

        url = f"{VOYAGER_BASE_URL}/feed/follows"
        payload = {"urn": resolved_urn}
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await self._request(client, "POST", url, headers=self._get_headers(), json=payload, action="visit")
                if resp.status_code in (200, 201, 202, 204):
                    return {"status": "followed", "http_status": resp.status_code}
                return {"status": "failed", "status_code": resp.status_code, "text": resp.text[:200]}
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager follow_profile error: %s", type(exc).__name__)
            return {"status": "error", "error": "LinkedIn request could not be confirmed", "status_code": getattr(exc, "status_code", None)}

    async def endorse_top_skill(self, profile_urn: str, skill_name: str | None = None) -> dict[str, Any]:
        """
        Endorses the top skill on a target LinkedIn profile.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Endorsed skill for %s (skill=%s)", profile_urn, skill_name or "top")
            return {"status": "endorsed", "skill": skill_name or "Leadership", "timestamp": datetime.now(timezone.utc).isoformat()}

        resolved_urn = await self._resolve_profile_urn(profile_urn)
        if not resolved_urn:
            return {"status": "failed", "error": "Could not resolve this LinkedIn profile to a verified member ID."}

        url = f"{VOYAGER_BASE_URL}/identity/profiles/{resolved_urn}/skillEndorsements"
        payload = {"skillName": skill_name} if skill_name else {}
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await self._request(client, "POST", url, headers=self._get_headers(), json=payload, action="visit")
                if resp.status_code in (200, 201, 202, 204):
                    return {"status": "endorsed", "http_status": resp.status_code}
                return {"status": "failed", "status_code": resp.status_code, "text": resp.text[:200]}
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager endorse_top_skill error: %s", type(exc).__name__)
            return {"status": "error", "error": "LinkedIn request could not be confirmed", "status_code": getattr(exc, "status_code", None)}

    async def withdraw_invitation(self, profile_urn: str) -> dict[str, Any]:
        """
        Withdraws a pending outbound connection invitation to a prospect on LinkedIn.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Withdrew pending invitation for %s", profile_urn)
            return {"status": "withdrawn", "timestamp": datetime.now(timezone.utc).isoformat()}

        resolved_urn = await self._resolve_profile_urn(profile_urn)
        if not resolved_urn:
            return {"status": "failed", "error": "Could not resolve this LinkedIn profile to a verified member ID."}

        url = f"{VOYAGER_BASE_URL}/relationships/invitations"
        payload = {"action": "withdraw", "inviteeProfileUrn": resolved_urn}
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await self._request(client, "POST", url, headers=self._get_headers(), json=payload, action="visit")
                if resp.status_code in (200, 201, 202, 204):
                    return {"status": "withdrawn", "http_status": resp.status_code}
                return {"status": "failed", "status_code": resp.status_code, "text": resp.text[:200]}
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager withdraw_invitation error: %s", type(exc).__name__)
            return {"status": "error", "error": "LinkedIn request could not be confirmed", "status_code": getattr(exc, "status_code", None)}

    async def send_inmail(
        self,
        recipient_urn: str,
        subject: str,
        message_body: str,
        attachment_url: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Sends a LinkedIn InMail to a 2nd/3rd degree lead (Open Profile or Sales Navigator/Premium).
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Sent InMail to %s: %s", recipient_urn, subject[:30])
            res: dict[str, Any] = {"status": "inmail_sent", "subject": subject, "timestamp": datetime.now(timezone.utc).isoformat()}
            if attachment_url:
                res["attachment_url"] = attachment_url
                res["attachment_name"] = attachment_name or "attachment"
            return res

        if not self.request_envelope:
            raise RequestDenied("content_approval_required")
        self.request_envelope.assert_content("message", recipient_urn, {"subject": subject, "body": message_body})

        resolved_urn = await self._resolve_profile_urn(recipient_urn)
        if not resolved_urn:
            return {"status": "failed", "error": "Could not resolve this LinkedIn profile to a verified member ID."}

        url = f"{VOYAGER_BASE_URL}/messaging/conversations"
        msg_obj: dict[str, Any] = {"body": message_body}
        if attachment_url:
            msg_obj["attachments"] = [{"name": attachment_name or "document", "reference": attachment_url}]
        payload = {
            "recipients": [resolved_urn],
            "subject": subject,
            "message": msg_obj,
            "subtype": "INMAIL",
        }
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await self._request(client, "POST", url, headers=self._get_headers(), json=payload, action="message")
                if resp.status_code in (200, 201):
                    return {"status": "inmail_sent"}
                return {"status": "failed", "status_code": resp.status_code, "text": resp.text[:200]}
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager send_inmail error: %s", type(exc).__name__)
            return {"status": "error", "error": "LinkedIn request could not be confirmed", "status_code": getattr(exc, "status_code", None)}

    async def comment_last_post(self, profile_urn: str, comment_text: str, max_age_days: int = 30) -> dict[str, Any]:
        """
        Comments on the prospect's most recent post within max_age_days.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Commented on last post for %s: %s", profile_urn, comment_text[:40])
            return {"status": "commented", "comment_text": comment_text, "timestamp": datetime.now(timezone.utc).isoformat()}

        resolved_urn = await self._resolve_profile_urn(profile_urn)
        if not resolved_urn:
            return {"status": "failed", "error": "Could not resolve this LinkedIn profile to a verified member ID."}
        updates = await self.fetch_profile_recent_updates(resolved_urn, count=20)
        if not updates:
            return {"status": "failed", "error": "No recent post found for this profile"}
        max_age = max(1, int(max_age_days))
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age)
        for update in updates:
            published_at = update.get("published_at")
            if isinstance(published_at, (int, float)):
                published_at = datetime.fromtimestamp(published_at / (1000 if published_at > 10**12 else 1), tz=timezone.utc)
            elif isinstance(published_at, str):
                try:
                    published_at = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    if published_at.tzinfo is None:
                        published_at = published_at.replace(tzinfo=timezone.utc)
                except ValueError:
                    published_at = None
            if published_at is None or published_at < cutoff:
                continue
            if update.get("post_urn"):
                return await self.comment_on_update(update["post_urn"], comment_text)
        return {"status": "failed", "error": f"No post found within the last {max_age} days"}

    async def check_open_profile(self, profile_identifier: str) -> bool | None:
        """
        Checks if a prospect's LinkedIn profile has Open Profile enabled (eligible for free InMail).
        """
        if self.is_mock:
            return True
        parsed = urlparse(profile_identifier)
        vanity_name = parsed.path.rstrip("/").split("/")[-1] if "/in/" in (parsed.path or "") else profile_identifier.strip().strip("/")
        if not vanity_name or "/" in vanity_name:
            return None
        info = await self.fetch_profile_info(vanity_name)
        if not info.get("verified"):
            return None
        return bool(info.get("is_open_profile"))

    async def send_voice_note(self, recipient_urn: str, audio_bytes: bytes, transcript: str = "") -> dict[str, Any]:
        """
        Dispatches an audio voice note to a prospect on LinkedIn.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Dispatched voice note to %s (%d bytes)", recipient_urn, len(audio_bytes))
            return {
                "status": "voice_note_sent",
                "bytes": len(audio_bytes),
                "transcript": transcript,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        if not self.request_envelope:
            raise RequestDenied("content_approval_required")
        self.request_envelope.assert_content("voice", recipient_urn, {"body": transcript, "audio_digest": hashlib.sha256(audio_bytes).hexdigest()})

        resolved_urn = await self._resolve_profile_urn(recipient_urn)
        if not resolved_urn:
            return {"status": "failed", "error": "Could not resolve this LinkedIn profile to a verified member ID."}

        url = f"{VOYAGER_BASE_URL}/messaging/conversations"
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=25.0) as client:
                files = {"file": ("voicenote.wav", audio_bytes, "audio/wav")}
                data = {"recipientUrn": resolved_urn, "messageType": "VOICE_NOTE"}
                resp = await self._request(client, "POST", url, headers=self._get_headers(), data=data, files=files, action="voice")
                if resp.status_code in (200, 201):
                    return {"status": "voice_note_sent"}
                return {"status": "failed", "status_code": resp.status_code}
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager send_voice_note error: %s", type(exc).__name__)
            return {"status": "error", "error": "LinkedIn request could not be confirmed", "status_code": getattr(exc, "status_code", None)}

    async def fetch_conversations(self, count: int = 20, start: int = 0) -> list[dict[str, Any]]:
        """
        Fetches active conversation threads for this LinkedIn account.
        """
        if self.is_mock:
            now = datetime.now(timezone.utc)
            return [
                {
                    "thread_urn": "urn:li:fs_conversation:mock-jordan",
                    "lead_urn": "urn:li:fsd_profile:ACoAABuilder1",
                    "lead_profile_url": "https://www.linkedin.com/in/jordan-davis",
                    "lead_name": "Jordan Davis",
                    "lead_headline": "Head of Growth at FinTech Labs",
                    "lead_avatar": "",
                    "last_message_snippet": "Thanks for reaching out! Would love to chat next week.",
                    "last_message_at": now.isoformat(),
                    "unread_count": 1,
                    "intent_tag": "interested",
                    "messages": [
                        {
                            "sender_type": "user",
                            "sender_name": "You",
                            "body": "Hey Jordan, saw your team at FinTech Labs is scaling outbound!",
                            "timestamp": (now - timedelta(hours=3)).isoformat(),
                        },
                        {
                            "sender_type": "lead",
                            "sender_name": "Jordan Davis",
                            "body": "Thanks for reaching out! Would love to chat next week.",
                            "timestamp": (now - timedelta(minutes=15)).isoformat(),
                        },
                    ],
                }
            ]

        url = f"{VOYAGER_BASE_URL}/messaging/conversations?count={count}&start={start}"
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await self._request(client, "GET", url, headers=self._get_headers())
                if resp.status_code == 200:
                    data = resp.json()
                    # In production Voyager returns elements in elements array
                    elements = data.get("elements")
                    if not isinstance(elements, list):
                        raise ValueError("LinkedIn returned an unexpected inbox response")
                    return elements
                raise VoyagerRestrictionError(resp.status_code)
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager fetch_conversations error: %s", type(exc).__name__)
            raise

    async def send_conversation_reply(
        self,
        thread_urn: str,
        message_body: str,
        attachment_url: str | None = None,
        attachment_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Replies directly inside an existing conversation thread (with optional attachment).
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Sent reply to thread %s: %s", thread_urn, message_body[:40])
            res: dict[str, Any] = {
                "status": "sent",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if attachment_url:
                res["attachment_url"] = attachment_url
                res["attachment_name"] = attachment_name or "attachment"
            return res

        if not self.request_envelope:
            raise RequestDenied("content_approval_required")
        self.request_envelope.assert_content("reply", thread_urn, {"body": message_body})

        url = f"{VOYAGER_BASE_URL}/messaging/conversations/{thread_urn}/events"
        msg_create: dict[str, Any] = {"body": message_body}
        if attachment_url:
            msg_create["attachments"] = [{"name": attachment_name or "document", "reference": attachment_url}]
        payload = {
            "eventCreate": {
                "value": {
                    "com.linkedin.voyager.messaging.create.MessageCreate": msg_create
                }
            }
        }
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await self._request(client, "POST", url, headers=self._get_headers(), json=payload)
                if resp.status_code in (200, 201):
                    return {"status": "sent"}
                return {"status": "failed", "status_code": resp.status_code}
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager send_conversation_reply error: %s", type(exc).__name__)
            return {"status": "error", "error": "LinkedIn request could not be confirmed", "status_code": getattr(exc, "status_code", None)}

    async def edit_conversation_message(
        self,
        thread_urn: str,
        message_id: str,
        new_body: str,
    ) -> dict[str, Any]:
        """
        Edits a previously sent LinkedIn message within 1 hour of sending.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Edited message %s in thread %s", message_id, thread_urn)
            return {
                "status": "edited",
                "message_id": message_id,
                "body": new_body,
                "edited_at": datetime.now(timezone.utc).isoformat(),
            }

        url = f"{VOYAGER_BASE_URL}/messaging/conversations/{thread_urn}/events/{message_id}"
        payload = {"patch": {"$set": {"body": new_body}}}
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await self._request(client, "POST", url, headers=self._get_headers(), json=payload)
                if resp.status_code in (200, 201, 202, 204):
                    return {"status": "edited", "message_id": message_id, "edited_at": datetime.now(timezone.utc).isoformat()}
                return {"status": "failed", "status_code": resp.status_code}
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager edit_conversation_message error: %s", type(exc).__name__)
            return {"status": "error", "error": "LinkedIn message edit could not be confirmed", "status_code": getattr(exc, "status_code", None)}

    async def fetch_profile_recent_updates(self, profile_urn: str, count: int = 5) -> list[dict[str, Any]]:
        """
        Fetches the recent posts/updates authored by a target profile.
        """
        if self.is_mock:
            now = datetime.now(timezone.utc)
            return [
                {
                    "post_urn": f"urn:li:activity:{hash(profile_urn) % 1000000 + 101}",
                    "post_url": f"https://www.linkedin.com/feed/update/urn:li:activity:{hash(profile_urn) % 1000000 + 101}/",
                    "published_at": (now - timedelta(hours=4)).strftime("%b %d, %Y"),
                    "content_text": (
                        "Most founders spend 90% of their time tweaking cold email copy when the real bottleneck "
                        "is lack of pre-outreach engagement. If a prospect has seen your insightful comment on their "
                        "latest post 24 hours prior, your connection acceptance skyrockets from 12% to over 50%.\n\n"
                        "Stop pitching into the void. Build familiarity first."
                    ),
                    "reactions_count": 48,
                    "comments_count": 12,
                    "media_urls": [],
                },
                {
                    "post_urn": f"urn:li:activity:{hash(profile_urn) % 1000000 + 102}",
                    "post_url": f"https://www.linkedin.com/feed/update/urn:li:activity:{hash(profile_urn) % 1000000 + 102}/",
                    "published_at": (now - timedelta(days=1)).strftime("%b %d, %Y"),
                    "content_text": (
                        "We just shipped our Q3 outbound experiments. Here are 3 counter-intuitive takeaways:\n"
                        "1. Shorter messages (under 50 words) beat detailed essays.\n"
                        "2. Voice notes get 3.2x higher replies on warm leads than text alone.\n"
                        "3. Speed matters — responding within 15 minutes triples meeting booking rates."
                    ),
                    "reactions_count": 89,
                    "comments_count": 27,
                    "media_urls": [],
                },
            ]

        url = f"{VOYAGER_BASE_URL}/identity/profileUpdatesV2?profileUrn={profile_urn}&count={count}"
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=20.0) as client:
                resp = await self._request(client, "GET", url, headers=self._get_headers())
                if resp.status_code == 200:
                    data = resp.json()
                    elements = data.get("elements", [])
                    results = []
                    for el in elements:
                        update_urn = el.get("urn", "")
                        commentary = el.get("commentary", {}).get("text", {}).get("text", "")
                        total_reactions = el.get("socialDetail", {}).get("totalSocialActivityCounts", {}).get("numLikes", 0)
                        total_comments = el.get("socialDetail", {}).get("totalSocialActivityCounts", {}).get("numComments", 0)
                        results.append({
                            "post_urn": update_urn,
                            "post_url": f"https://www.linkedin.com/feed/update/{update_urn}/" if update_urn else "",
                            "published_at": el.get("createdAt") or el.get("lastModifiedAt"),
                            "content_text": commentary,
                            "reactions_count": total_reactions,
                            "comments_count": total_comments,
                            "media_urls": self._update_media_urls(el),
                        })
                    return results
                if resp.status_code in (401, 403, 429):
                    raise VoyagerRestrictionError(resp.status_code)
                raise RuntimeError(f"LinkedIn post fetch failed with HTTP {resp.status_code}")
        except VoyagerRestrictionError:
            raise
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager fetch_profile_recent_updates error: %s", type(exc).__name__)
            raise

    async def like_update(self, update_urn: str, reaction_type: str = "LIKE") -> dict[str, Any]:
        """
        Likes a specific post/update on LinkedIn.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Liked update %s (type=%s)", update_urn, reaction_type)
            return {"status": "liked", "update_urn": update_urn, "timestamp": datetime.now(timezone.utc).isoformat()}

        if self.request_envelope:
            self.request_envelope.assert_reaction(update_urn, reaction_type)

        url = f"{VOYAGER_BASE_URL}/feed/reactions"
        payload = {
            "root": update_urn,
            "reactionType": reaction_type,
        }
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await self._request(client, "POST", url, headers=self._get_headers(), json=payload)
                if resp.status_code in (200, 201):
                    return {"status": "liked", "update_urn": update_urn}
                return {"status": "failed", "status_code": resp.status_code}
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager like_update error: %s", type(exc).__name__)
            return {"status": "error", "error": "LinkedIn request could not be confirmed", "status_code": getattr(exc, "status_code", None)}

    async def comment_on_update(self, update_urn: str, comment_text: str) -> dict[str, Any]:
        """
        Dispatches a comment to a LinkedIn post/update.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Commented on %s: %s", update_urn, comment_text[:40])
            return {
                "status": "commented",
                "update_urn": update_urn,
                "comment_text": comment_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        if not self.request_envelope:
            raise RequestDenied("content_approval_required")
        self.request_envelope.assert_content("comment", update_urn, {"body": comment_text})

        url = f"{VOYAGER_BASE_URL}/feed/comments"
        payload = {
            "root": update_urn,
            "comment": {
                "values": [{"value": comment_text}]
            }
        }
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await self._request(client, "POST", url, headers=self._get_headers(), json=payload)
                if resp.status_code in (200, 201):
                    return {"status": "commented", "update_urn": update_urn}
                return {"status": "failed", "status_code": resp.status_code}
        except RequestDenied:
            raise
        except Exception as exc:
            logger.error("Voyager comment_on_update error: %s", type(exc).__name__)
            return {"status": "error", "error": "LinkedIn request could not be confirmed", "status_code": getattr(exc, "status_code", None)}

    async def auto_like_and_comment(self, update_urn: str, comment_text: str) -> dict[str, Any]:
        """
        Human-mimicking action: auto-likes post before posting comment with a realistic jitter.
        """
        import asyncio
        from outreach.core.rate_limiter import OutboundRateLimiter

        like_res = await self.like_update(update_urn)
        if like_res.get("status") != "liked":
            return {"status": "failed", "like": like_res, "comment": None, "jitter_seconds": 0}
        # Realistic human delay between like and comment to avoid bot fingerprinting
        jitter = OutboundRateLimiter.calculate_human_jitter(3.0)
        if not self.is_mock:
            await asyncio.sleep(jitter)
        comment_res = await self.comment_on_update(update_urn, comment_text)
        return {
            "status": "success" if comment_res.get("status") == "commented" else "failed",
            "like": like_res,
            "comment": comment_res,
            "jitter_seconds": round(jitter, 1),
        }

    async def search_people_entities(
        self,
        search_url: str,
        start: int = 0,
        count: int = 10,
    ) -> dict[str, Any]:
        """
        Internal bounded keyword-only transport contract; public collection stays unavailable.
        Extracts candidate entities without establishing source fidelity or completeness.
        """
        from outreach.models import SearchImportStopReason
        from outreach.core.lead_importer import normalize_linkedin_url, extract_vanity_name, extract_member_urn

        from outreach.core.search_sources import SearchSourceError, parse_search_source, validate_search_page
        parsed_info = parse_search_source(search_url)
        if self.is_mock or os.getenv("OUTREACH_MOCK_AUTH", "false").lower() in {"true", "1"}:
            raise SearchSourceError("mock_search_unavailable", "Test search data cannot be collected as customer contacts.")
        if type(start) is not int or not 0 <= start < 1000 or type(count) is not int or not 1 <= count <= 10:
            raise SearchSourceError("invalid_search_page", "Unsupported search page bounds.")
        keywords = parsed_info["keywords"]
        is_sales_nav = False
        endpoint = f"{VOYAGER_BASE_URL}/search/blended"
        params = {"start": start, "count": count, "origin": "FACETED_SEARCH", "q": "all",
                  "query": f"(keywords:{keywords},flagshipSearchIntent:SEARCH_SRP)"}

        headers = self._get_headers()
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=20.0, follow_redirects=False) as client:
                resp = await self._request(client, "GET", endpoint, headers=headers, params=params)

                if resp.status_code == 429:
                    return {
                        "entities": [],
                        "total_results": None,
                        "stop_reason": SearchImportStopReason.RATE_LIMITED,
                        "user_error_message": "LinkedIn rate limit reached. Pausing search import.",
                        "status_code": 429,
                    }
                if resp.status_code in (401,):
                    return {
                        "entities": [],
                        "total_results": None,
                        "stop_reason": SearchImportStopReason.SESSION_EXPIRED,
                        "user_error_message": "LinkedIn session cookie expired. Reconnect the sender in Settings.",
                        "status_code": 401,
                    }
                if resp.status_code in (403, 999):
                    return {
                        "entities": [],
                        "total_results": None,
                        "stop_reason": SearchImportStopReason.CHECKPOINT,
                        "user_error_message": "LinkedIn security checkpoint detected. Automation paused for your safety.",
                        "status_code": resp.status_code,
                    }
                if resp.status_code != 200:
                    return {
                        "entities": [],
                        "total_results": None,
                        "stop_reason": SearchImportStopReason.CANCELLED,
                        "user_error_message": f"LinkedIn returned HTTP {resp.status_code}",
                        "status_code": resp.status_code,
                    }

                try:
                    data = resp.json()
                except ValueError:
                    raise SearchSourceError("search_response_unverified", "Search response could not be verified.") from None

                # Check for Commercial Use Limit warning in payload
                text_content = resp.text.lower()
                if "commercial use limit" in text_content or "commercialuselimit" in text_content:
                    return {
                        "entities": [],
                        "total_results": None,
                        "stop_reason": SearchImportStopReason.COMMERCIAL_USE_LIMIT,
                        "user_error_message": "Monthly LinkedIn commercial search limit reached on this account. Upgrade to Sales Navigator or resume next month.",
                        "status_code": 200,
                    }

                total_results = validate_search_page(data, start=start)

                elements = data.get("elements", [])
                entities = []
                for item in elements:
                    target = item.get("searchHorizontalResult") or item
                    title_obj = target.get("title", {})
                    raw_name = title_obj.get("text", "").strip() if isinstance(title_obj, dict) else str(title_obj)
                    if not raw_name:
                        raw_name = target.get("name", "").strip()

                    nav_url = target.get("navigationUrl") or target.get("url") or ""
                    cleaned_url = normalize_linkedin_url(nav_url) if nav_url else ""
                    vanity = extract_vanity_name(cleaned_url) if cleaned_url else None
                    target_urn = target.get("targetUrn") or target.get("entityUrn") or ""
                    member_urn = extract_member_urn(target_urn) or extract_member_urn(nav_url)

                    is_unresolvable = (
                        "linkedin member" in raw_name.lower()
                        or (not cleaned_url and not member_urn)
                    )

                    primary_sub = target.get("primarySubtitle", {})
                    headline = primary_sub.get("text", "") if isinstance(primary_sub, dict) else str(primary_sub)
                    sec_sub = target.get("secondarySubtitle", {})
                    location = sec_sub.get("text", "") if isinstance(sec_sub, dict) else str(sec_sub)

                    name_parts = raw_name.split() if raw_name else []
                    first_name = name_parts[0] if name_parts else ""
                    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

                    entities.append({
                        "raw_name": raw_name,
                        "first_name": first_name,
                        "last_name": last_name,
                        "job_title": headline.split(" at ")[0].strip() if " at " in headline else headline,
                        "company_name": headline.split(" at ")[1].strip() if " at " in headline else "",
                        "location": location,
                        "headline": headline,
                        "profile_url": cleaned_url or nav_url,
                        "vanity_name": vanity,
                        "member_urn": member_urn,
                        "sales_lead_urn": target_urn if is_sales_nav else None,
                        "is_unresolvable": is_unresolvable,
                    })

                return {
                    "entities": entities,
                    "total_results": total_results,
                    "stop_reason": None,
                    "user_error_message": None,
                    "status_code": 200,
                }
        except httpx.RequestError as exc:
            logger.error("Voyager search request error: %s", type(exc).__name__)
            return {
                "entities": [],
                "total_results": None,
                "stop_reason": SearchImportStopReason.PROXY_UNHEALTHY,
                "user_error_message": "Proxy connection dropped during search crawl.",
                "status_code": 502,
            }


LinkedInVoyagerClient = VoyagerClient
