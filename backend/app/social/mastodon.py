import logging
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException


class MastodonAuth:
    """Validate a user-provided Mastodon instance URL and access token."""

    @staticmethod
    def normalize_instance_url(instance_url: str) -> str:
        value = (instance_url or "").strip()
        if not value:
            raise HTTPException(status_code=400, detail="Mastodon instance URL is required")

        if not value.startswith(("http://", "https://")):
            value = f"https://{value}"

        parsed = urlparse(value)
        if not parsed.netloc:
            raise HTTPException(status_code=400, detail="Enter a valid Mastodon instance URL")

        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")

    async def get_user_profile(self, instance_url: str, access_token: str) -> dict:
        normalized_instance = self.normalize_instance_url(instance_url)
        token = (access_token or "").strip()
        if not token:
            raise HTTPException(status_code=400, detail="Mastodon access token is required")

        verify_url = f"{normalized_instance}/api/v1/accounts/verify_credentials"

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                verify_url,
                headers={"Authorization": f"Bearer {token}"},
            )

        if response.status_code in (401, 403):
            raise HTTPException(status_code=400, detail="Invalid Mastodon access token")
        if response.status_code != 200:
            logging.error("[Mastodon] verify_credentials failed: %s", response.text[:400])
            raise HTTPException(
                status_code=502,
                detail="Failed to reach Mastodon. Check the instance URL and try again.",
            )

        data = response.json()
        username = data.get("username") or data.get("acct") or str(data.get("id", ""))
        profile_url = data.get("url") or (
            f"{normalized_instance}/@{data.get('acct') or username}" if username else normalized_instance
        )

        return {
            "id": str(data.get("id", "")),
            "username": username,
            "acct": data.get("acct") or username,
            "display_name": data.get("display_name") or username,
            "picture_url": data.get("avatar"),
            "url": profile_url,
            "instance_url": normalized_instance,
        }
