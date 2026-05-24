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
    CHAT_URL    = "https://api.bsky.chat/xrpc"
    SESSION_URL = "https://bsky.social/xrpc/com.atproto.server.createSession"
    REFRESH_URL = "https://bsky.social/xrpc/com.atproto.server.refreshSession"
    POST_URL    = "https://bsky.social/xrpc/com.atproto.repo.createRecord"
    CHAT_PROXY_DID = "did:web:api.bsky.chat#bsky_chat"

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

    async def refresh_session(self, refresh_token: str) -> dict:
        """Refresh an expired Bluesky session using refreshJwt."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.REFRESH_URL,
                headers={"Authorization": f"Bearer {refresh_token}"},
            )
            if response.status_code != 200:
                logging.error("[Bluesky] refreshSession error: %s", response.text)
                raise HTTPException(status_code=401, detail="Bluesky session expired. Reconnect the account.")
            return response.json()

    async def get_user_profile(self, access_token: str, actor: str, fallback_actor: str | None = None) -> dict:
        """Fetch Bluesky profile by DID or handle."""
        candidates: list[str] = []
        for candidate in (actor, fallback_actor):
            value = str(candidate or "").strip()
            if value and value not in candidates:
                candidates.append(value)

        if not candidates:
            raise HTTPException(status_code=400, detail="Failed to fetch Bluesky profile")

        last_error: str | None = None
        async with httpx.AsyncClient() as client:
            for candidate in candidates:
                response = await client.get(
                    f"{self.BASE_URL}/app.bsky.actor.getProfile",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"actor": candidate},
                )
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "id":          data.get("did", candidate),
                        "name":        data.get("displayName") or data.get("handle", ""),
                        "username":    data.get("handle", ""),
                        "picture_url": data.get("avatar"),
                        "followers_count": data.get("followersCount"),
                        "following_count": data.get("followsCount"),
                        "posts_count": data.get("postsCount"),
                    }

                last_error = response.text
                logging.warning("[Bluesky] getProfile failed for actor=%s: %s", candidate, response.text)

        if last_error:
            logging.error("[Bluesky] getProfile error after %s attempt(s): %s", len(candidates), last_error)
        raise HTTPException(status_code=400, detail="Failed to fetch Bluesky profile")

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
                media_type = "TEXT"
                embed_type = embed.get("$type")
                if embed_type == "app.bsky.embed.images#view":
                    images = embed.get("images", [])
                    if images:
                        media_url = images[0].get("thumb")
                    media_type = "IMAGE"
                elif embed_type == "app.bsky.embed.video#view":
                    media_url = embed.get("thumbnail")
                    media_type = "VIDEO"
                elif embed_type == "app.bsky.embed.external#view":
                    external = embed.get("external", {})
                    media_url = external.get("thumb")
                    media_type = "LINK"
                elif embed_type == "app.bsky.embed.record#view":
                    media_type = "QUOTED"
                elif embed_type == "app.bsky.embed.recordWithMedia#view":
                    media_type = "QUOTED"
                    media = embed.get("media", {})
                    media_embed_type = media.get("$type")
                    if media_embed_type == "app.bsky.embed.images#view":
                        images = media.get("images", [])
                        if images:
                            media_url = images[0].get("thumb")
                    elif media_embed_type == "app.bsky.embed.video#view":
                        media_url = media.get("thumbnail")
                    elif media_embed_type == "app.bsky.embed.external#view":
                        external = media.get("external", {})
                        media_url = external.get("thumb")

                uri = post.get("uri", "")
                handle_str = post.get("author", {}).get("handle", handle)
                # Convert AT URI to web URL
                rkey = uri.split("/")[-1] if uri else ""
                post_url = f"https://bsky.app/profile/{handle_str}/post/{rkey}" if rkey else None

                normalized.append({
                    "platform_post_id": uri,
                    "content":          text,
                    "media_url":        media_url,
                    "media_type":       media_type,
                    "post_type":        media_type,
                    "post_url":         post_url,
                    "metrics": {
                        "likes":    post.get("likeCount", 0),
                        "comments": post.get("replyCount", 0),
                        "shares":   post.get("repostCount", 0),
                        "quotes":   post.get("quoteCount", 0),
                    },
                    "published_at": rec.get("createdAt"),
                })
            return normalized

    async def list_notifications(self, access_token: str, limit: int = 100, cursor: str | None = None) -> dict:
        """List Bluesky notifications for the authenticated account."""
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/app.bsky.notification.listNotifications",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            logging.info(f"[Bluesky] list_notifications status: {response.status_code}")
            if response.status_code != 200:
                logging.warning(f"[Bluesky] list_notifications failed: {response.text}")
                return {"notifications": [], "cursor": None}
            return response.json()

    async def list_conversations(self, access_token: str, limit: int = 100, cursor: str | None = None) -> dict:
        """List Bluesky chat conversations using direct chat service with proxy fallback."""
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.CHAT_URL}/chat.bsky.convo.listConvos",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            logging.info(f"[Bluesky] list_conversations status: {response.status_code}")
            if response.status_code == 200:
                return response.json()

            proxy_response = await client.get(
                f"{self.BASE_URL}/chat.bsky.convo.listConvos",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "atproto-proxy": self.CHAT_PROXY_DID,
                },
                params=params,
            )
            logging.info(f"[Bluesky] proxied list_conversations status: {proxy_response.status_code}")
            if proxy_response.status_code != 200:
                logging.warning(f"[Bluesky] list_conversations failed: {proxy_response.text}")
                return {"convos": [], "cursor": None}
            return proxy_response.json()

    async def get_conversation_messages(
        self,
        access_token: str,
        convo_id: str,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict:
        """Get messages for a Bluesky DM conversation using direct chat service with proxy fallback."""
        params = {"convoId": convo_id, "limit": limit}
        if cursor:
            params["cursor"] = cursor

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.CHAT_URL}/chat.bsky.convo.getMessages",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            logging.info(f"[Bluesky] get_conversation_messages status: {response.status_code}")
            if response.status_code == 200:
                return response.json()

            proxy_response = await client.get(
                f"{self.BASE_URL}/chat.bsky.convo.getMessages",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "atproto-proxy": self.CHAT_PROXY_DID,
                },
                params=params,
            )
            logging.info(f"[Bluesky] proxied get_conversation_messages status: {proxy_response.status_code}")
            if proxy_response.status_code != 200:
                logging.warning(f"[Bluesky] get_conversation_messages failed: {proxy_response.text}")
                return {"messages": [], "cursor": None}
            return proxy_response.json()

    async def send_message(self, access_token: str, convo_id: str, text: str) -> dict:
        """Send a text DM in an existing Bluesky conversation."""
        payload = {
            "convoId": convo_id,
            "message": {
                "text": text[:10000],
            },
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.CHAT_URL}/chat.bsky.convo.sendMessage",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "atproto-proxy": self.CHAT_PROXY_DID,
                },
                json=payload,
            )
            logging.info(f"[Bluesky] send_message status: {response.status_code}")
            if response.status_code != 200:
                logging.warning(f"[Bluesky] send_message failed: {response.text}")
                raise Exception(f"Failed to send Bluesky message: {response.text}")
            return response.json()

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
