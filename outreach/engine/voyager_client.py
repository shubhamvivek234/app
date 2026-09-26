"""
Phase 5: LinkedIn Private Voyager REST API Client.
Executes 80% of lightweight network operations (profile viewing, connection checking,
messaging polling, post liking) without headless browser overhead.
"""
import os
import logging
from typing import Any
from urllib.parse import urlparse
import httpx
from datetime import datetime, timezone, timedelta
from outreach.core.crypto import decrypt_secret

logger = logging.getLogger(__name__)

VOYAGER_BASE_URL = "https://www.linkedin.com/voyager/api"


class VoyagerRestrictionError(RuntimeError):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"LinkedIn returned HTTP {status_code}")


class VoyagerClient:
    """
    Authenticated client for LinkedIn internal Voyager API.
    Routes all traffic through the account's 1:1 dedicated residential proxy.
    """

    def __init__(self, session_cookie_enc: str, jsession_id: str = "", proxy_url: str | None = None):
        self.session_cookie = decrypt_secret(session_cookie_enc).removeprefix("li_at=")
        mock_mode = os.getenv("OUTREACH_MOCK_AUTH", "false").lower() in {"true", "1"}
        csrf_cookie = decrypt_secret(jsession_id) if jsession_id.startswith("gAAAAA") else jsession_id
        if not mock_mode and self.session_cookie.startswith(("mock_", "test_")):
            raise ValueError("Test LinkedIn sessions cannot be used for live outreach")
        if not mock_mode and not csrf_cookie:
            raise ValueError("Sender JSESSIONID is missing. Reconnect the LinkedIn account.")
        self.jsession_id = csrf_cookie or "ajax:123456789"
        self.proxy_url = proxy_url
        self.is_mock = mock_mode

    def _get_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Cookie": f'li_at={self.session_cookie}; JSESSIONID="{self.jsession_id}"',
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
                resp = await client.get(url, headers=self._get_headers())
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
        except Exception as exc:
            logger.error("Voyager check_connection_status error: %s", exc)
            return False

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
                resp = await client.get(url, headers=self._get_headers())
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

                return {
                    "full_name": full_name,
                    "headline": profile.get("headline", ""),
                    "avatar_url": avatar_url,
                    "profile_urn": profile_urn,
                    "company": current_position.get("companyName", "") or profile.get("companyName", ""),
                    "job_title": current_position.get("title", "") or profile.get("occupation", ""),
                    "verified": bool(entity_urn and full_name),
                }
        except Exception as exc:
            logger.error("Voyager fetch_profile_info error for %s: %s", vanity_name, exc)
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
                resp = await client.post(url, headers=self._get_headers(), json={"profileUrl": profile_url})
                if resp.status_code in (200, 201, 202, 204):
                    return {"status": "viewed", "http_status": resp.status_code}
                return {"status": "failed", "http_status": resp.status_code, "text": resp.text[:200]}
        except Exception as exc:
            logger.error("Voyager visit_profile error: %s", exc)
            return {"status": "failed", "error": str(exc)}

    async def send_connection_invite(self, profile_urn: str, custom_note: str = "") -> dict[str, Any]:
        """
        Dispatches a connection invitation to a 2nd/3rd degree prospect.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Dispatched connection invite to %s with note=%s", profile_urn, custom_note[:30])
            return {"status": "invite_sent", "timestamp": datetime.now(timezone.utc).isoformat()}

        resolved_urn = await self._resolve_profile_urn(profile_urn)
        if not resolved_urn:
            return {"status": "failed", "error": "Could not resolve this LinkedIn profile to a verified member ID."}

        url = f"{VOYAGER_BASE_URL}/growth/normInvitations"
        payload = {
            "invitee": {"inviteeUnion": {"memberProfileUrn": resolved_urn}},
            "customMessage": custom_note if custom_note else None,
        }
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await client.post(url, headers=self._get_headers(), json=payload)
                if resp.status_code in (200, 201):
                    return {"status": "invite_sent"}
                return {"status": "failed", "status_code": resp.status_code, "text": resp.text[:200]}
        except Exception as exc:
            logger.error("Voyager send_connection_invite error: %s", exc)
            return {"status": "error", "error": str(exc)}

    async def send_direct_message(self, recipient_urn: str, message_body: str) -> dict[str, Any]:
        """
        Sends a standard text direct message to a 1st degree connection.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Dispatched DM to %s: %s", recipient_urn, message_body[:40])
            return {"status": "message_sent", "timestamp": datetime.now(timezone.utc).isoformat()}

        resolved_urn = await self._resolve_profile_urn(recipient_urn)
        if not resolved_urn:
            return {"status": "failed", "error": "Could not resolve this LinkedIn profile to a verified member ID."}

        url = f"{VOYAGER_BASE_URL}/messaging/conversations"
        payload = {
            "recipients": [resolved_urn],
            "message": {"body": message_body},
        }
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await client.post(url, headers=self._get_headers(), json=payload)
                if resp.status_code in (200, 201):
                    return {"status": "message_sent"}
                return {"status": "failed", "status_code": resp.status_code}
        except Exception as exc:
            logger.error("Voyager send_direct_message error: %s", exc)
            return {"status": "error", "error": str(exc)}

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

        resolved_urn = await self._resolve_profile_urn(recipient_urn)
        if not resolved_urn:
            return {"status": "failed", "error": "Could not resolve this LinkedIn profile to a verified member ID."}

        url = f"{VOYAGER_BASE_URL}/messaging/conversations"
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=25.0) as client:
                files = {"file": ("voicenote.wav", audio_bytes, "audio/wav")}
                data = {"recipientUrn": resolved_urn, "messageType": "VOICE_NOTE"}
                resp = await client.post(url, headers=self._get_headers(), data=data, files=files)
                if resp.status_code in (200, 201):
                    return {"status": "voice_note_sent"}
                return {"status": "failed", "status_code": resp.status_code}
        except Exception as exc:
            logger.error("Voyager send_voice_note error: %s", exc)
            return {"status": "error", "error": str(exc)}

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
                resp = await client.get(url, headers=self._get_headers())
                if resp.status_code == 200:
                    data = resp.json()
                    # In production Voyager returns elements in elements array
                    elements = data.get("elements")
                    if not isinstance(elements, list):
                        raise ValueError("LinkedIn returned an unexpected inbox response")
                    return elements
                raise VoyagerRestrictionError(resp.status_code)
        except Exception as exc:
            logger.error("Voyager fetch_conversations error: %s", exc)
            raise

    async def send_conversation_reply(self, thread_urn: str, message_body: str) -> dict[str, Any]:
        """
        Replies directly inside an existing conversation thread.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Sent reply to thread %s: %s", thread_urn, message_body[:40])
            return {
                "status": "sent",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        url = f"{VOYAGER_BASE_URL}/messaging/conversations/{thread_urn}/events"
        payload = {
            "eventCreate": {
                "value": {
                    "com.linkedin.voyager.messaging.create.MessageCreate": {
                        "body": message_body,
                    }
                }
            }
        }
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await client.post(url, headers=self._get_headers(), json=payload)
                if resp.status_code in (200, 201):
                    return {"status": "sent"}
                return {"status": "failed", "status_code": resp.status_code}
        except Exception as exc:
            logger.error("Voyager send_conversation_reply error: %s", exc)
            return {"status": "error", "error": str(exc)}

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
                resp = await client.get(url, headers=self._get_headers())
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
        except Exception as exc:
            logger.error("Voyager fetch_profile_recent_updates error: %s", exc)
            raise

    async def like_update(self, update_urn: str, reaction_type: str = "LIKE") -> dict[str, Any]:
        """
        Likes a specific post/update on LinkedIn.
        """
        if self.is_mock:
            logger.info("VoyagerClient [MOCK]: Liked update %s (type=%s)", update_urn, reaction_type)
            return {"status": "liked", "update_urn": update_urn, "timestamp": datetime.now(timezone.utc).isoformat()}

        url = f"{VOYAGER_BASE_URL}/feed/reactions"
        payload = {
            "root": update_urn,
            "reactionType": reaction_type,
        }
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await client.post(url, headers=self._get_headers(), json=payload)
                if resp.status_code in (200, 201):
                    return {"status": "liked", "update_urn": update_urn}
                return {"status": "failed", "status_code": resp.status_code}
        except Exception as exc:
            logger.error("Voyager like_update error: %s", exc)
            return {"status": "error", "error": str(exc)}

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

        url = f"{VOYAGER_BASE_URL}/feed/comments"
        payload = {
            "root": update_urn,
            "comment": {
                "values": [{"value": comment_text}]
            }
        }
        try:
            async with httpx.AsyncClient(proxy=self.proxy_url, timeout=15.0) as client:
                resp = await client.post(url, headers=self._get_headers(), json=payload)
                if resp.status_code in (200, 201):
                    return {"status": "commented", "update_urn": update_urn}
                return {"status": "failed", "status_code": resp.status_code}
        except Exception as exc:
            logger.error("Voyager comment_on_update error: %s", exc)
            return {"status": "error", "error": str(exc)}

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
