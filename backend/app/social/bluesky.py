import httpx
import os
import logging
from fastapi import HTTPException
from datetime import datetime, timezone

class BlueskyAuth:
    """
    Bluesky / AT Protocol integration.

    Bluesky doesn't use standard OAuth — it uses app passwords.
    Users create an App Password at bsky.app/settings/app-passwords,
    then we use createSession to get a JWT access token.
    """

    BASE_URL    = "https://bsky.social/xrpc"
    SESSION_URL = "https://bsky.social/xrpc/com.atproto.server.createSession"
    POST_URL    = "https://bsky.social/xrpc/com.atproto.repo.createRecord"

    def __init__(self):
        # No global app credentials — each user connects with their own
        # handle + app password stored in social_accounts.
        pass

    def get_auth_url(self, state: str) -> str:
        """
        Bluesky doesn't have a redirect-based OAuth flow.
        Return a sentinel URL — the frontend will show a
        username/app-password form instead.
        """
        return f"bluesky://connect?state={state}"

    async def create_session(self, identifier: str, app_password: str) -> dict:
        """
        Authenticate with Bluesky using handle + app password.
        Returns session dict with accessJwt, refreshJwt, did, handle.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.SESSION_URL,
                json={"identifier": identifier, "password": app_password},
            )
            if response.status_code != 200:
                logging.error(f"[Bluesky] createSession error: {response.text}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Bluesky authentication failed: {response.json().get('message', 'Invalid credentials')}"
                )
            return response.json()

    async def get_user_profile(self, access_token: str, did: str) -> dict:
        """Fetch Bluesky profile by DID."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/app.bsky.actor.getProfile",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"actor": did},
            )
            if response.status_code != 200:
                logging.error(f"[Bluesky] getProfile error: {response.text}")
                raise HTTPException(status_code=400, detail="Failed to fetch Bluesky profile")
            data = response.json()
            return {
                "id":          data.get("did", did),
                "name":        data.get("displayName") or data.get("handle", ""),
                "username":    data.get("handle", ""),
                "picture_url": data.get("avatar"),
            }

    async def publish_post(
        self,
        access_token: str,
        did: str,
        text: str,
        media_urls: list = None,
        reply_ref: dict = None,
    ) -> dict:
        """
        Create a Bluesky post (app.bsky.feed.post).
        Returns {uri, cid} of the created record.
        """
        record = {
            "$type":     "app.bsky.feed.post",
            "text":      text[:300],
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

        # Attach images if provided (upload blobs first)
        if media_urls:
            images = []
            async with httpx.AsyncClient() as client:
                for url in media_urls[:4]:  # Bluesky max 4 images
                    try:
                        img_response = await client.get(url)
                        if img_response.status_code == 200:
                            blob_response = await client.post(
                                f"{self.BASE_URL}/com.atproto.repo.uploadBlob",
                                headers={
                                    "Authorization":  f"Bearer {access_token}",
                                    "Content-Type":   img_response.headers.get("content-type", "image/jpeg"),
                                },
                                content=img_response.content,
                            )
                            if blob_response.status_code == 200:
                                blob = blob_response.json().get("blob")
                                images.append({
                                    "image": blob,
                                    "alt":   "",
                                })
                    except Exception as e:
                        logging.warning(f"[Bluesky] Image upload failed: {e}")

            if images:
                record["embed"] = {
                    "$type":  "app.bsky.embed.images",
                    "images": images,
                }

        if reply_ref:
            record["reply"] = reply_ref

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.POST_URL,
                json={
                    "repo":       did,
                    "collection": "app.bsky.feed.post",
                    "record":     record,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type":  "application/json",
                },
            )
            if response.status_code not in [200, 201]:
                logging.error(f"[Bluesky] createRecord error: {response.text}")
                raise Exception(f"Failed to post to Bluesky: {response.text}")
            return response.json()

    async def fetch_posts(self, access_token: str, handle: str, limit: int = 20) -> list:
        """Fetch recent posts for a Bluesky account."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/app.bsky.feed.getAuthorFeed",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"actor": handle, "limit": limit, "filter": "posts_no_replies"},
            )
            logging.info(f"[Bluesky] fetch_posts status: {response.status_code}")
            if response.status_code != 200:
                logging.warning(f"[Bluesky] fetch_posts failed: {response.text}")
                return []

            feed = response.json().get("feed", [])
            normalized = []
            for item in feed:
                post = item.get("post", {})
                rec  = post.get("record", {})
                text = rec.get("text", "")

                embed = post.get("embed", {})
                media_url = None
                if embed.get("$type") == "app.bsky.embed.images#view":
                    images = embed.get("images", [])
                    if images:
                        media_url = images[0].get("thumb")

                uri = post.get("uri", "")
                cid = post.get("cid", "")
                handle_str = post.get("author", {}).get("handle", handle)
                # Convert AT URI to web URL
                rkey = uri.split("/")[-1] if uri else ""
                post_url = f"https://bsky.app/profile/{handle_str}/post/{rkey}" if rkey else None

                normalized.append({
                    "platform_post_id": uri,
                    "content":          text,
                    "media_url":        media_url,
                    "media_type":       "IMAGE" if media_url else "TEXT",
                    "post_url":         post_url,
                    "metrics": {
                        "likes":    post.get("likeCount", 0),
                        "comments": post.get("replyCount", 0),
                        "shares":   post.get("repostCount", 0),
                    },
                    "published_at": rec.get("createdAt"),
                })
            return normalized

    async def fetch_replies(self, access_token: str, post_uri: str, depth: int = 1) -> list:
        """Fetch replies to a Bluesky post"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/app.bsky.feed.getPostThread",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"uri": post_uri, "depth": depth},
            )
            logging.info(f"[Bluesky] fetch_replies status: {response.status_code}")
            if response.status_code != 200:
                logging.error(f"[Bluesky] fetch_replies failed: {response.text}")
                return []

            thread = response.json().get("thread", {})
            replies_list = thread.get("replies", [])
            comments = []
            for reply in replies_list:
                post = reply.get("post", {})
                author = post.get("author", {})
                record = post.get("record", {})
                comments.append({
                    "id": post.get("uri", ""),
                    "author_name": author.get("handle", "Unknown"),
                    "author_avatar": author.get("avatar"),
                    "content": record.get("text", ""),
                    "timestamp": record.get("createdAt"),
                    "likes": post.get("likeCount", 0),
                    "can_reply": True,
                    "platform": "bluesky",
                    # Extra fields needed for Bluesky reply threading
                    "cid": post.get("cid"),
                    "root_uri": thread.get("post", {}).get("uri"),
                    "root_cid": thread.get("post", {}).get("cid"),
                })
            return comments
