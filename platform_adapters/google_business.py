"""
Google Business Profile (GBP) platform adapter.
Publishes Local Posts / Updates (Standard, Event, Offer) with Call-To-Action buttons and photos
to verified Google Maps business locations via Google My Business / Business Profile APIs.
"""
import json
import logging
from datetime import datetime, timezone
import httpx

from platform_adapters.base import (
    PlatformAdapter,
    PlatformHTTPError,
    PlatformAPIError,
)
from utils.encryption import decrypt

logger = logging.getLogger(__name__)


class GoogleBusinessAdapter(PlatformAdapter):
    platform = "google_business"

    async def publish(self, post: dict, account: dict | None = None) -> dict:
        account = account or post.get("account") or {}
        access_token = post.get("access_token") or account.get("access_token")
        location_id = (
            account.get("location_id")
            or account.get("platform_user_id")
            or "accounts/primary/locations/primary"
        )

        content = post.get("effective_content") or post.get("content", "")
        media_urls = post.get("media_urls") or ([post.get("media_url")] if post.get("media_url") else [])
        call_to_action = post.get("google_business_call_to_action")
        action_url = post.get("google_business_action_url")

        # Fallback / simulated publish if running with mock/sandbox tokens or in sandbox environment
        if not access_token or access_token.startswith("mock_") or access_token == "simulated":
            logger.info("Publishing to Google Business Profile (sandbox mode) for location: %s", location_id)
            return {
                "platform_post_id": f"gbp_post_{post.get('id')}",
                "post_url": f"https://maps.google.com/?cid={location_id}",
                "published_at": datetime.now(timezone.utc).isoformat(),
            }

        # Real Google My Business API call
        # https://mybusiness.googleapis.com/v4/{name=accounts/*/locations/*}/localPosts
        api_url = f"https://mybusiness.googleapis.com/v4/{location_id}/localPosts"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "languageCode": "en-US",
            "summary": content[:1500],
            "topicType": post.get("google_business_topic_type") or "STANDARD",
        }

        if action_url and call_to_action:
            payload["callToAction"] = {
                "actionType": call_to_action,
                "url": action_url,
            }

        if media_urls:
            payload["media"] = [
                {
                    "mediaFormat": "PHOTO",
                    "sourceUrl": media_urls[0],
                }
            ]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(api_url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    err_data = (
                        resp.json().get("error", {})
                        if resp.headers.get("content-type", "").startswith("application/json")
                        else {}
                    )
                    err_msg = err_data.get("message") or resp.text
                    raise PlatformAPIError(f"Google Business Profile API error ({resp.status_code}): {err_msg}")

                result = resp.json()
                return {
                    "platform_post_id": result.get("name") or result.get("searchUrl") or f"gbp_{post.get('id')}",
                    "post_url": result.get("searchUrl") or f"https://maps.google.com/?cid={location_id}",
                }
        except PlatformAPIError:
            raise
        except Exception as exc:
            logger.error("Google Business Profile publish exception: %s", exc)
            raise PlatformAPIError(f"Failed to publish to Google Business Profile: {str(exc)}")
