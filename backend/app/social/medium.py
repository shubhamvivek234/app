"""
Medium legacy integration-token helper.

Medium no longer supports new OAuth integrations broadly, but existing
integration tokens can still be used to access the legacy API.
Docs:
- https://github.com/Medium/medium-api-docs
- https://help.medium.com/hc/en-us/articles/213480228-API-Importing
"""
import httpx
from fastapi import HTTPException


class MediumAuth:
    BASE_URL = "https://api.medium.com/v1"

    async def get_user_profile(self, integration_token: str) -> dict:
        headers = {
            "Authorization": f"Bearer {integration_token}",
            "Accept": "application/json",
            "Accept-Charset": "utf-8",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.BASE_URL}/me", headers=headers)

        if response.status_code in (401, 403):
            raise HTTPException(status_code=400, detail="Invalid Medium integration token")
        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail="Failed to verify Medium token",
            )

        data = response.json().get("data", {})
        return {
            "id": data.get("id", ""),
            "username": data.get("username") or "",
            "name": data.get("name") or "",
            "url": data.get("url"),
            "image_url": data.get("imageUrl"),
        }
