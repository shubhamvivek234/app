"""Inbox and conversation routes for platform DMs and post comments."""
import asyncio
import base64
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument

from api.deps import CurrentUser, DB
from utils.encryption import decrypt
from utils.observability import event_log, shorten_provider_error

logger = logging.getLogger(__name__)
router = APIRouter(tags=["inbox"])

_PLATFORM_LABELS = {
    "instagram": "Instagram",
    "facebook": "Facebook",
    "bluesky": "Bluesky",
    "reddit": "Reddit",
    "youtube": "YouTube",
}

_PLATFORM_CAPABILITIES = {
    "instagram": {
        "supports_dm_inbox": True,
        "supports_dm_reply": True,
        "supports_comment_inbox": True,
        "supports_comment_reply": True,
    },
    "facebook": {
        "supports_dm_inbox": True,
        "supports_dm_reply": True,
        "supports_comment_inbox": True,
        "supports_comment_reply": True,
    },
    "bluesky": {
        "supports_dm_inbox": True,
        "supports_dm_reply": True,
        "supports_comment_inbox": True,
        "supports_comment_reply": True,
    },
    "reddit": {
        "supports_dm_inbox": False,
        "supports_dm_reply": False,
        "supports_comment_inbox": True,
        "supports_comment_reply": True,
    },
    "youtube": {
        "supports_dm_inbox": False,
        "supports_dm_reply": False,
        "supports_comment_inbox": True,
        "supports_comment_reply": True,
    },
}

_DM_PLATFORMS = {platform for platform, caps in _PLATFORM_CAPABILITIES.items() if caps["supports_dm_inbox"]}
_COMMENT_PLATFORMS = {platform for platform, caps in _PLATFORM_CAPABILITIES.items() if caps["supports_comment_inbox"]}


class InboxSyncRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    platform: str | None = None
    account_id: str | None = Field(default=None, alias="accountId")
    type: str | None = None
    post_limit: int = Field(default=5, ge=1, le=20)
    message_limit: int = Field(default=10, ge=1, le=50)
    comment_limit: int = Field(default=20, ge=1, le=100)


class ConversationReplyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    platform: str
    text: str
    account_id: str | None = Field(default=None, alias="accountId")
    recipient_id: str | None = Field(default=None, alias="recipientId")


class CommentReplyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    platform: str
    text: str
    account_id: str | None = Field(default=None, alias="accountId")
    post_id: str | None = Field(default=None, alias="postId")
    parent_cid: str | None = Field(default=None, alias="parentCid")
    root_uri: str | None = Field(default=None, alias="rootUri")
    root_cid: str | None = Field(default=None, alias="rootCid")


def _workspace_id(current_user: dict[str, Any]) -> str:
    return current_user.get("default_workspace_id") or current_user["user_id"]


def _as_iso(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    if isinstance(value, str) and value.strip():
        return value
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _build_inbox_message_id(user_id: str, platform: str, account_id: str, item_type: str, platform_message_id: str) -> str:
    raw = f"{user_id}|{platform}|{account_id}|{item_type}|{platform_message_id}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"inbox_{digest}"


def _decode_resource_id(value: str) -> str:
    if not value.startswith("b64."):
        return value
    payload = value[4:]
    padding = "=" * (-len(payload) % 4)
    try:
        return base64.urlsafe_b64decode(f"{payload}{padding}".encode("utf-8")).decode("utf-8")
    except Exception:
        return value


def _build_capability_registry(accounts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    for account in accounts:
        platform = (account.get("platform") or "").lower()
        caps = _PLATFORM_CAPABILITIES.get(platform)
        if not caps:
            continue
        platform_entry = registry.setdefault(
            platform,
            {
                "platform": platform,
                "label": _PLATFORM_LABELS.get(platform, platform.title()),
                "account_count": 0,
                **caps,
            },
        )
        platform_entry["account_count"] += 1
    return registry


async def _load_social_accounts(
    db,
    user_id: str,
    *,
    platform: str | None = None,
    account_id: str | None = None,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"user_id": user_id, "is_active": True}
    if platform:
        query["platform"] = platform
    if account_id:
        query["$or"] = [{"account_id": account_id}, {"id": account_id}]
    cursor = db.social_accounts.find(query, {"_id": 0})
    return await cursor.to_list(length=100)


def _account_identifier(account: dict[str, Any]) -> str:
    return str(account.get("account_id") or account.get("id") or "")


async def _get_account_access_token(db, account: dict[str, Any], *, force_refresh: bool = False) -> str:
    platform = (account.get("platform") or "").lower()
    encrypted_token = account.get("access_token")
    if not encrypted_token:
        raise ValueError(f"Missing {platform} access token")

    if platform == "bluesky":
        from api.routes.accounts import _get_bluesky_access_token

        return await _get_bluesky_access_token(db, account, force_refresh=force_refresh)

    if platform == "youtube":
        from api.routes.accounts import _get_youtube_access_token

        return await _get_youtube_access_token(db, account, force_refresh=force_refresh)

    return decrypt(encrypted_token)


def _peer_from_participants(account: dict[str, Any], participants: list[dict[str, Any]]) -> tuple[str | None, str, str | None]:
    own_id = str(account.get("platform_user_id") or "")
    for participant in participants:
        participant_id = str(participant.get("id") or participant.get("did") or "")
        if own_id and participant_id == own_id:
            continue
        return (
            participant_id or None,
            participant.get("name")
            or participant.get("username")
            or participant.get("displayName")
            or participant.get("handle")
            or "Unknown",
            participant.get("avatar") or participant.get("profile_picture_url"),
        )

    first = participants[0] if participants else {}
    return (
        str(first.get("id") or first.get("did") or "") or None,
        first.get("name") or first.get("username") or first.get("displayName") or first.get("handle") or "Unknown",
        first.get("avatar") or first.get("profile_picture_url"),
    )


def _normalize_recent_post(raw: dict[str, Any]) -> dict[str, Any] | None:
    post_id = raw.get("platform_post_id") or raw.get("id")
    if not post_id:
        return None
    return {
        "platform_post_id": str(post_id),
        "content": raw.get("content", ""),
        "post_url": raw.get("post_url") or raw.get("permalink"),
        "published_at": raw.get("published_at") or raw.get("timestamp"),
    }


async def _upsert_inbox_message(
    db,
    *,
    current_user: dict[str, Any],
    platform: str,
    account_id: str,
    item_type: str,
    platform_message_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    user_id = current_user["user_id"]
    workspace_id = _workspace_id(current_user)
    message_id = _build_inbox_message_id(user_id, platform, account_id, item_type, platform_message_id)
    now = datetime.now(timezone.utc)
    status_value = payload.get("status") or "unread"
    set_fields = {
        "platform": platform,
        "account_id": account_id,
        "type": item_type,
        "conversation_id": payload.get("conversation_id"),
        "platform_message_id": str(platform_message_id),
        "post_id": payload.get("post_id"),
        "post_url": payload.get("post_url"),
        "author_id": payload.get("author_id"),
        "author_name": payload.get("author_name") or "Unknown",
        "author_avatar": payload.get("author_avatar"),
        "recipient_id": payload.get("recipient_id"),
        "content": payload.get("content", ""),
        "received_at": _as_iso(payload.get("received_at")),
        "status": status_value,
        "is_read": status_value != "unread",
        "direction": payload.get("direction") or "incoming",
        "source": payload.get("source") or "platform_sync",
        "updated_at": now,
    }
    extra_fields = (
        "reply_context",
        "comment_cid",
        "root_uri",
        "root_cid",
        "thread_root_uri",
        "thread_root_cid",
    )
    for field in extra_fields:
        if payload.get(field) is not None:
            set_fields[field] = payload.get(field)

    await db.inbox_messages.update_one(
        {"id": message_id},
        {
            "$set": set_fields,
            "$setOnInsert": {
                "id": message_id,
                "message_id": message_id,
                "workspace_id": workspace_id,
                "user_id": user_id,
                "reply": None,
                "reply_status": None,
                "platform_reply_error": None,
                "replied_at": None,
                "created_at": now,
            },
        },
        upsert=True,
    )
    doc = await db.inbox_messages.find_one({"id": message_id}, {"_id": 0})
    return doc or {}


async def _list_meta_conversations(db, account: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    platform = account.get("platform")
    access_token = await _get_account_access_token(db, account)
    platform_user_id = account.get("platform_user_id")
    if platform == "instagram":
        from backend.app.social.instagram import InstagramAuth

        return await InstagramAuth().fetch_conversations(access_token, platform_user_id, limit=limit)

    from backend.app.social.facebook import FacebookAuth

    return await FacebookAuth().fetch_page_conversations(access_token, platform_user_id, limit=limit)


async def _list_bluesky_conversations(db, account: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    from backend.app.social.bluesky import BlueskyAuth

    access_token = await _get_account_access_token(db, account)
    auth = BlueskyAuth()
    own_did = str(account.get("platform_user_id") or "")
    convo_page = await auth.list_conversations(access_token, limit=limit)
    raw_convos = convo_page.get("convos") or convo_page.get("conversations") or []
    normalized: list[dict[str, Any]] = []

    for convo in raw_convos[:limit]:
        convo_id = convo.get("id") or convo.get("convoId")
        if not convo_id:
            continue
        members = convo.get("members") or convo.get("participants") or []
        participants = [
            {
                "did": member.get("did"),
                "handle": member.get("handle"),
                "displayName": member.get("displayName"),
                "avatar": member.get("avatar"),
            }
            for member in members
            if isinstance(member, dict)
        ]
        message_page = await auth.get_conversation_messages(access_token, convo_id, limit=limit)
        messages = []
        for message in message_page.get("messages") or message_page.get("items") or []:
            sender = message.get("sender") or {}
            messages.append(
                {
                    "id": message.get("id"),
                    "message": message.get("text") or message.get("message") or "",
                    "created_time": message.get("sentAt") or message.get("createdAt"),
                    "from": {
                        "id": sender.get("did") or sender.get("id"),
                        "name": sender.get("displayName") or sender.get("handle") or sender.get("did") or "Unknown",
                        "avatar": sender.get("avatar"),
                    },
                }
            )
        messages.sort(
            key=lambda item: _parse_ts(item.get("created_time")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        latest = messages[0] if messages else {}
        latest_sender = latest.get("from", {}) or {}
        normalized.append(
            {
                "id": convo_id,
                "participants": [
                    {
                        "id": participant.get("did"),
                        "name": participant.get("displayName") or participant.get("handle") or participant.get("did") or "Unknown",
                        "avatar": participant.get("avatar"),
                    }
                    for participant in participants
                ],
                "messages": messages,
                "last_message": latest.get("message", ""),
                "last_message_time": latest.get("created_time"),
                "last_message_id": latest.get("id"),
                "last_message_sender_id": latest_sender.get("id"),
                "last_message_sender_name": latest_sender.get("name"),
                "platform": "bluesky",
                "own_did": own_did,
            }
        )

    return normalized


async def _list_platform_conversations(db, account: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    platform = (account.get("platform") or "").lower()
    if platform in {"instagram", "facebook"}:
        return await _list_meta_conversations(db, account, limit=limit)
    if platform == "bluesky":
        return await _list_bluesky_conversations(db, account, limit=limit)
    return []


async def _recent_posts_for_comments(db, account: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    platform = (account.get("platform") or "").lower()
    access_token = await _get_account_access_token(db, account)
    platform_user_id = account.get("platform_user_id")

    if platform == "instagram":
        from backend.app.social.instagram import InstagramAuth

        posts = await InstagramAuth().fetch_feed(access_token, platform_user_id, limit=limit)
    elif platform == "facebook":
        from backend.app.social.facebook import FacebookAuth

        posts = await FacebookAuth().fetch_page_feed(access_token, platform_user_id, limit=limit)
    elif platform == "bluesky":
        from backend.app.social.bluesky import BlueskyAuth

        posts = await BlueskyAuth().fetch_posts(access_token, account.get("platform_username"), limit=limit)
    elif platform == "youtube":
        from backend.app.social.google import GoogleAuth

        posts = await GoogleAuth().fetch_youtube_feed(access_token, platform_user_id, limit=limit)
    elif platform == "reddit":
        from backend.app.social.reddit import RedditAuth

        posts = await RedditAuth().fetch_user_posts(access_token, account.get("platform_username"), limit=limit)
    else:
        posts = []

    normalized = [_normalize_recent_post(post) for post in posts]
    normalized = [post for post in normalized if post]

    if normalized:
        return normalized

    from api.routes.analytics import _fetch_db_published_posts

    fallback = await _fetch_db_published_posts(db, account.get("user_id"), account, limit=limit)
    return [post for post in (_normalize_recent_post(item) for item in fallback) if post]


async def _fetch_post_comments(db, account: dict[str, Any], platform_post_id: str, *, limit: int) -> list[dict[str, Any]]:
    platform = (account.get("platform") or "").lower()
    access_token = await _get_account_access_token(db, account)

    if platform == "instagram":
        from backend.app.social.instagram import InstagramAuth

        return await InstagramAuth().fetch_comments(access_token, platform_post_id, limit=limit)
    if platform == "facebook":
        from backend.app.social.facebook import FacebookAuth

        return await FacebookAuth().fetch_comments(access_token, platform_post_id, limit=limit)
    if platform == "bluesky":
        from backend.app.social.bluesky import BlueskyAuth

        return await BlueskyAuth().fetch_replies(access_token, platform_post_id, depth=2)
    if platform == "youtube":
        from backend.app.social.google import GoogleAuth

        return await GoogleAuth().fetch_youtube_comments(access_token, platform_post_id, limit=limit)
    if platform == "reddit":
        from backend.app.social.reddit import RedditAuth

        return await RedditAuth().fetch_comments(access_token, platform_post_id, limit=limit)
    return []


async def _sync_account_conversations(
    db,
    *,
    current_user: dict[str, Any],
    account: dict[str, Any],
    message_limit: int,
) -> int:
    synced = 0
    conversations = await _list_platform_conversations(db, account, limit=message_limit)
    own_id = str(account.get("platform_user_id") or "")
    account_id = _account_identifier(account)

    for conversation in conversations:
        latest_message = conversation.get("last_message", "")
        if not latest_message:
            continue
        participants = conversation.get("participants") or []
        peer_id, peer_name, peer_avatar = _peer_from_participants(account, participants)
        latest_sender_id = str(conversation.get("last_message_sender_id") or "")
        direction = "outgoing" if own_id and latest_sender_id == own_id else "incoming"
        status_value = "read" if direction == "outgoing" else "unread"
        if peer_name == "Unknown":
            peer_name = conversation.get("last_message_sender_name") or peer_name
        platform_message_id = str(conversation.get("last_message_id") or conversation.get("id"))
        await _upsert_inbox_message(
            db,
            current_user=current_user,
            platform=account.get("platform"),
            account_id=account_id,
            item_type="dm",
            platform_message_id=platform_message_id,
            payload={
                "conversation_id": conversation.get("id"),
                "author_id": peer_id,
                "author_name": peer_name,
                "author_avatar": peer_avatar,
                "recipient_id": peer_id,
                "content": latest_message,
                "received_at": conversation.get("last_message_time"),
                "status": status_value,
                "direction": direction,
                "source": "platform_sync",
            },
        )
        synced += 1

    return synced


async def _sync_account_comments(
    db,
    *,
    current_user: dict[str, Any],
    account: dict[str, Any],
    post_limit: int,
    comment_limit: int,
) -> int:
    synced = 0
    account_id = _account_identifier(account)
    posts = await _recent_posts_for_comments(db, account, limit=post_limit)
    for post in posts[:post_limit]:
        platform_post_id = str(post.get("platform_post_id") or "")
        if not platform_post_id:
            continue
        comments = await _fetch_post_comments(db, account, platform_post_id, limit=comment_limit)
        for comment in comments[:comment_limit]:
            platform_message_id = str(comment.get("id") or "")
            if not platform_message_id:
                continue
            await _upsert_inbox_message(
                db,
                current_user=current_user,
                platform=account.get("platform"),
                account_id=account_id,
                item_type="comment",
                platform_message_id=platform_message_id,
                payload={
                    "conversation_id": None,
                    "post_id": platform_post_id,
                    "post_url": post.get("post_url"),
                    "author_id": comment.get("author_id"),
                    "author_name": comment.get("author_name"),
                    "author_avatar": comment.get("author_avatar"),
                    "content": comment.get("content", ""),
                    "received_at": comment.get("timestamp"),
                    "status": "unread",
                    "direction": "incoming",
                    "source": "platform_sync",
                    "comment_cid": comment.get("cid"),
                    "root_uri": comment.get("root_uri"),
                    "root_cid": comment.get("root_cid"),
                },
            )
            synced += 1
    return synced


async def _reply_to_dm(
    db,
    *,
    account: dict[str, Any],
    conversation_id: str,
    recipient_id: str,
    text: str,
) -> dict[str, Any]:
    platform = (account.get("platform") or "").lower()
    access_token = await _get_account_access_token(db, account)
    if platform == "instagram":
        from backend.app.social.instagram import InstagramAuth

        return await InstagramAuth().send_message(access_token, recipient_id, text)
    if platform == "facebook":
        from backend.app.social.facebook import FacebookAuth

        return await FacebookAuth().send_page_message(access_token, account.get("platform_user_id"), recipient_id, text)
    if platform == "bluesky":
        from backend.app.social.bluesky import BlueskyAuth

        return await BlueskyAuth().send_message(access_token, conversation_id, text)
    raise HTTPException(status_code=422, detail=f"{platform} DM replies are not supported")


async def _reply_to_comment(
    db,
    *,
    account: dict[str, Any],
    platform_post_id: str,
    comment_id: str,
    body: CommentReplyRequest,
) -> dict[str, Any]:
    platform = (account.get("platform") or "").lower()
    access_token = await _get_account_access_token(db, account)
    text = body.text.strip()

    if platform == "instagram":
        from backend.app.social.instagram import InstagramAuth

        return await InstagramAuth().reply_to_comment(access_token, comment_id, text)
    if platform == "facebook":
        from backend.app.social.facebook import FacebookAuth

        return await FacebookAuth().reply_to_comment(access_token, comment_id, text)
    if platform == "reddit":
        from backend.app.social.reddit import RedditAuth

        return await RedditAuth().reply_to_comment(access_token, comment_id, text)
    if platform == "youtube":
        from backend.app.social.google import GoogleAuth

        return await GoogleAuth().reply_to_youtube_comment(access_token, comment_id, text)
    if platform == "bluesky":
        from backend.app.social.bluesky import BlueskyAuth

        reply_ref = {
            "parent": {
                "uri": comment_id,
                "cid": body.parent_cid or body.root_cid or "",
            },
            "root": {
                "uri": body.root_uri or platform_post_id,
                "cid": body.root_cid or body.parent_cid or "",
            },
        }
        return await BlueskyAuth().publish_post(
            access_token,
            account.get("platform_user_id"),
            text,
            reply_ref=reply_ref,
        )
    raise HTTPException(status_code=422, detail=f"{platform} comment replies are not supported")


@router.get("/inbox")
async def list_inbox(
    current_user: CurrentUser,
    db: DB,
    platform: str | None = Query(None),
    type: str | None = Query(None),
    status: str | None = Query(None),
    account_id: str | None = Query(None, alias="account_id"),
    limit: int = Query(50, ge=1, le=200),
):
    workspace_id = _workspace_id(current_user)
    query: dict[str, Any] = {
        "workspace_id": workspace_id,
        "user_id": current_user["user_id"],
    }
    if platform:
        query["platform"] = platform
    if type:
        query["type"] = type
    if account_id:
        query["account_id"] = account_id
    if status:
        if status == "unread":
            query["status"] = "unread"
        else:
            query["status"] = status

    cursor = db.inbox_messages.find(query, {"_id": 0}).sort("received_at", -1).limit(limit)
    docs = await cursor.to_list(None)
    for doc in docs:
        doc.setdefault("id", doc.get("message_id", ""))

    accounts = await _load_social_accounts(db, current_user["user_id"])
    capabilities = _build_capability_registry(accounts)
    return {
        "messages": docs,
        "capabilities": capabilities,
        "connected_platforms": sorted(capabilities.keys()),
    }


@router.get("/inbox/stats")
async def inbox_stats(current_user: CurrentUser, db: DB):
    workspace_id = _workspace_id(current_user)

    async def _count(q):
        return await db.inbox_messages.count_documents(q)

    total, unread, comments, dms, replied = await asyncio.gather(
        _count({"workspace_id": workspace_id, "user_id": current_user["user_id"]}),
        _count({"workspace_id": workspace_id, "user_id": current_user["user_id"], "status": "unread"}),
        _count({"workspace_id": workspace_id, "user_id": current_user["user_id"], "type": "comment"}),
        _count({"workspace_id": workspace_id, "user_id": current_user["user_id"], "type": "dm"}),
        _count({"workspace_id": workspace_id, "user_id": current_user["user_id"], "status": "replied"}),
    )
    return {"total": total, "unread": unread, "comments": comments, "dms": dms, "replied": replied}


@router.patch("/inbox/{message_id}")
async def update_inbox_message(message_id: str, body: dict, current_user: CurrentUser, db: DB):
    workspace_id = _workspace_id(current_user)
    allowed = {
        key: value
        for key, value in body.items()
        if key in {"is_read", "status", "assigned_to", "reply", "reply_status", "replied_at", "platform_reply_error"}
    }
    if not allowed:
        raise HTTPException(status_code=422, detail="No valid fields to update")
    if "is_read" in allowed and "status" not in allowed:
        allowed["status"] = "read" if allowed["is_read"] else "unread"
    if "status" in allowed and "is_read" not in allowed:
        allowed["is_read"] = allowed["status"] != "unread"
    allowed["updated_at"] = datetime.now(timezone.utc)
    result = await db.inbox_messages.find_one_and_update(
        {"$or": [{"message_id": message_id}, {"id": message_id}], "workspace_id": workspace_id, "user_id": current_user["user_id"]},
        {"$set": allowed},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Message not found")
    return result


@router.delete("/inbox/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inbox_message(message_id: str, current_user: CurrentUser, db: DB):
    workspace_id = _workspace_id(current_user)
    await db.inbox_messages.delete_one(
        {"$or": [{"message_id": message_id}, {"id": message_id}], "workspace_id": workspace_id, "user_id": current_user["user_id"]}
    )


@router.post("/inbox")
async def create_inbox_message(body: dict, current_user: CurrentUser, db: DB):
    """Manual message creation (for testing and local-only fallback)."""
    workspace_id = _workspace_id(current_user)
    now = datetime.now(timezone.utc)
    message_id = body.get("id") or body.get("message_id") or f"manual_{hashlib.sha256(str(now.timestamp()).encode()).hexdigest()[:20]}"
    doc = {
        "message_id": message_id,
        "id": message_id,
        "workspace_id": workspace_id,
        "user_id": current_user["user_id"],
        **{k: v for k, v in body.items() if k not in {"workspace_id", "id", "message_id", "user_id"}},
        "received_at": _as_iso(body.get("received_at") or now),
        "status": body.get("status") or "unread",
        "is_read": bool(body.get("is_read", False)),
        "created_at": now,
        "updated_at": now,
    }
    await db.inbox_messages.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/conversations")
async def get_conversations(
    current_user: CurrentUser,
    db: DB,
    platform: str = Query(...),
    account_id: str | None = Query(None, alias="accountId"),
    limit: int = Query(20, ge=1, le=50),
):
    platform = platform.lower()
    if platform not in _DM_PLATFORMS:
        return {"supported": False, "message": f"{platform} does not support DM inbox in Publish right now.", "conversations": []}

    accounts = await _load_social_accounts(db, current_user["user_id"], platform=platform, account_id=account_id)
    if not accounts:
        return {"supported": False, "message": "No connected account found for the selected platform.", "conversations": []}

    conversations: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for account in accounts:
        try:
            conversations.extend(await _list_platform_conversations(db, account, limit=limit))
        except Exception as exc:
            errors.append(
                {
                    "account_id": _account_identifier(account),
                    "error": str(exc),
                }
            )
    return {"supported": True, "conversations": conversations[:limit], "errors": errors}


@router.post("/conversations/sync")
async def sync_conversations(
    body: InboxSyncRequest,
    current_user: CurrentUser,
    db: DB,
):
    platform = (body.platform or "").lower() or None
    if platform and platform not in _PLATFORM_CAPABILITIES:
        raise HTTPException(status_code=422, detail=f"Unsupported platform for inbox sync: {platform}")

    accounts = await _load_social_accounts(db, current_user["user_id"], platform=platform, account_id=body.account_id)
    capability_registry = _build_capability_registry(accounts)
    synced_dms = 0
    synced_comments = 0
    errors: list[dict[str, str]] = []

    for account in accounts:
        account_platform = (account.get("platform") or "").lower()
        caps = _PLATFORM_CAPABILITIES.get(account_platform)
        if not caps:
            continue
        try:
            if body.type in {None, "", "dm"} and caps.get("supports_dm_inbox"):
                synced_dms += await _sync_account_conversations(
                    db,
                    current_user=current_user,
                    account=account,
                    message_limit=body.message_limit,
                )
            if body.type in {None, "", "comment"} and caps.get("supports_comment_inbox"):
                synced_comments += await _sync_account_comments(
                    db,
                    current_user=current_user,
                    account=account,
                    post_limit=body.post_limit,
                    comment_limit=body.comment_limit,
                )
        except Exception as exc:
            event_log(
                logger,
                "warning",
                "inbox.sync.account_failed",
                route="/conversations/sync",
                user_id=current_user["user_id"],
                platform=account_platform,
                account_id=_account_identifier(account),
                failure_type=type(exc).__name__,
                provider_error=shorten_provider_error(exc),
                outcome="degraded",
            )
            errors.append(
                {
                    "platform": account_platform,
                    "account_id": _account_identifier(account),
                    "error": str(exc),
                }
            )

    return {
        "success": True,
        "synced_dms": synced_dms,
        "synced_comments": synced_comments,
        "capabilities": capability_registry,
        "errors": errors,
    }


@router.post("/conversations/{conversation_id}/reply")
async def send_conversation_reply(
    conversation_id: str,
    body: ConversationReplyRequest,
    current_user: CurrentUser,
    db: DB,
):
    platform = body.platform.lower()
    if platform not in _DM_PLATFORMS:
        raise HTTPException(status_code=422, detail=f"{platform} DM replies are not supported")

    accounts = await _load_social_accounts(db, current_user["user_id"], platform=platform, account_id=body.account_id)
    if not accounts:
        raise HTTPException(status_code=404, detail="Connected account not found")

    account = accounts[0]
    recipient_id = body.recipient_id
    if not recipient_id:
        inbox_doc = await db.inbox_messages.find_one(
            {
                "user_id": current_user["user_id"],
                "platform": platform,
                "conversation_id": conversation_id,
                "type": "dm",
            },
            {"_id": 0, "recipient_id": 1},
        )
        recipient_id = (inbox_doc or {}).get("recipient_id")
    if platform in {"instagram", "facebook"} and not recipient_id:
        raise HTTPException(status_code=422, detail="recipient_id is required for this DM platform")

    return {
        "success": True,
        "result": await _reply_to_dm(
            db,
            account=account,
            conversation_id=conversation_id,
            recipient_id=recipient_id or "",
            text=body.text.strip(),
        ),
    }


@router.get("/posts/{platform_post_id}/comments")
async def get_post_comments(
    platform_post_id: str,
    current_user: CurrentUser,
    db: DB,
    platform: str = Query(...),
    account_id: str | None = Query(None, alias="accountId"),
    limit: int = Query(50, ge=1, le=100),
):
    platform_post_id = _decode_resource_id(platform_post_id)
    platform = platform.lower()
    if platform not in _COMMENT_PLATFORMS:
        return {"supported": False, "message": f"{platform} comments are not supported in Publish right now.", "comments": []}

    accounts = await _load_social_accounts(db, current_user["user_id"], platform=platform, account_id=account_id)
    if not accounts:
        return {"supported": False, "message": "No connected account found for the selected platform.", "comments": []}

    account = accounts[0]
    comments = await _fetch_post_comments(db, account, platform_post_id, limit=limit)
    account_identifier = _account_identifier(account)
    for comment in comments:
        comment_id = str(comment.get("id") or "")
        if not comment_id:
            continue
        await _upsert_inbox_message(
            db,
            current_user=current_user,
            platform=platform,
            account_id=account_identifier,
            item_type="comment",
            platform_message_id=comment_id,
            payload={
                "post_id": platform_post_id,
                "author_id": comment.get("author_id"),
                "author_name": comment.get("author_name"),
                "author_avatar": comment.get("author_avatar"),
                "content": comment.get("content", ""),
                "received_at": comment.get("timestamp"),
                "status": "unread",
                "direction": "incoming",
                "source": "platform_sync",
                "comment_cid": comment.get("cid"),
                "root_uri": comment.get("root_uri"),
                "root_cid": comment.get("root_cid"),
            },
        )
    return {"supported": True, "comments": comments}


@router.post("/posts/{platform_post_id}/comments/{comment_id}/reply")
async def reply_to_post_comment(
    platform_post_id: str,
    comment_id: str,
    body: CommentReplyRequest,
    current_user: CurrentUser,
    db: DB,
):
    platform_post_id = _decode_resource_id(platform_post_id)
    comment_id = _decode_resource_id(comment_id)
    platform = body.platform.lower()
    if platform not in _COMMENT_PLATFORMS:
        raise HTTPException(status_code=422, detail=f"{platform} comment replies are not supported")

    accounts = await _load_social_accounts(db, current_user["user_id"], platform=platform, account_id=body.account_id)
    if not accounts:
        raise HTTPException(status_code=404, detail="Connected account not found")

    account = accounts[0]
    return {
        "success": True,
        "result": await _reply_to_comment(
            db,
            account=account,
            platform_post_id=platform_post_id,
            comment_id=comment_id,
            body=body,
        ),
    }
