"""Cleanup helpers for temporary composer audio assets."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from utils.observability import event_log, shorten_provider_error
from utils.storage import delete_file_async

logger = logging.getLogger(__name__)

TEMP_AUDIO_PURPOSE = "composer_audio_temp"
TEMP_AUDIO_TTL_SECONDS = 2 * 60 * 60
TERMINAL_STATUS = {"deleted", "cleaned"}


def is_temporary_audio_asset(asset: dict[str, Any] | None) -> bool:
    if not asset:
        return False
    mime_type = str(asset.get("mime_type") or asset.get("content_type") or "")
    asset_kind = str(asset.get("asset_kind") or "")
    return (
        asset.get("temporary") is True
        and asset.get("purpose") == TEMP_AUDIO_PURPOSE
        and (asset_kind == "audio" or mime_type.startswith("audio/"))
    )


def temporary_audio_metadata(
    *,
    composer_session_id: str | None,
    now: datetime | None = None,
    ttl_seconds: int = TEMP_AUDIO_TTL_SECONDS,
) -> dict[str, Any]:
    created_at = now or datetime.now(timezone.utc)
    return {
        "temporary": True,
        "purpose": TEMP_AUDIO_PURPOSE,
        "composer_session_id": composer_session_id,
        "temporary_audio_state": "active",
        "cleanup_after": created_at + timedelta(seconds=ttl_seconds),
    }


def collect_storage_refs(asset: dict[str, Any]) -> set[str]:
    refs = {
        asset.get("storage_key"),
        asset.get("source_storage_key"),
        asset.get("media_url"),
        asset.get("url"),
    }
    return {str(ref) for ref in refs if ref}


def audio_source_id_from_rendered_asset(asset: dict[str, Any]) -> str | None:
    mix = asset.get("audio_mix") or {}
    return (
        mix.get("source_audio_media_id")
        or mix.get("audio_media_id")
        or asset.get("source_item_id")
    )


def _post_media_ids(post: dict[str, Any]) -> set[str]:
    media_ids = set(post.get("media_ids") or [])
    for override in (post.get("platform_overrides") or {}).values():
        if isinstance(override, dict):
            media_ids.update(override.get("media_ids") or [])
    for override in (post.get("account_overrides") or {}).values():
        if isinstance(override, dict):
            media_ids.update(override.get("media_ids") or [])
    return {str(media_id) for media_id in media_ids if media_id}


async def active_post_references_media(
    db,
    *,
    media_id: str,
    user_id: str,
    workspace_id: str | None,
    excluding_post_id: str | None = None,
) -> bool:
    query: dict[str, Any] = {
        "user_id": user_id,
        "deleted_at": {"$exists": False},
    }
    if workspace_id is not None:
        query["workspace_id"] = workspace_id
    if excluding_post_id:
        query["id"] = {"$ne": excluding_post_id}

    cursor = db.posts.find(
        query,
        {
            "_id": 0,
            "media_ids": 1,
            "platform_overrides": 1,
            "account_overrides": 1,
        },
    )
    async for post in cursor:
        if media_id in _post_media_ids(post):
            return True
    return False


async def temporary_audio_still_referenced(
    db,
    *,
    audio_media_id: str,
    user_id: str,
    workspace_id: str | None,
    excluding_post_id: str | None = None,
) -> bool:
    if await active_post_references_media(
        db,
        media_id=audio_media_id,
        user_id=user_id,
        workspace_id=workspace_id,
        excluding_post_id=excluding_post_id,
    ):
        return True

    render_query: dict[str, Any] = {
        "user_id": user_id,
        "$or": [
            {"audio_mix.audio_media_id": audio_media_id},
            {"audio_mix.source_audio_media_id": audio_media_id},
            {"source_item_id": audio_media_id, "source_provider": "audio_render"},
        ],
    }
    if workspace_id is not None:
        render_query["workspace_id"] = workspace_id

    cursor = db.media_assets.find(render_query, {"_id": 0, "media_id": 1})
    async for rendered_asset in cursor:
        rendered_media_id = rendered_asset.get("media_id")
        if not rendered_media_id:
            continue
        if await active_post_references_media(
            db,
            media_id=str(rendered_media_id),
            user_id=user_id,
            workspace_id=workspace_id,
            excluding_post_id=excluding_post_id,
        ):
            return True
    return False


async def delete_temporary_audio_asset(
    db,
    *,
    media_id: str,
    user_id: str,
    workspace_id: str | None,
    reason: str,
    excluding_post_id: str | None = None,
    force: bool = False,
) -> str:
    query: dict[str, Any] = {"media_id": media_id, "user_id": user_id}
    if workspace_id is not None:
        query["workspace_id"] = workspace_id

    asset = await db.media_assets.find_one(query, {"_id": 0})
    if not asset:
        return "missing"
    if str(asset.get("status") or "") in TERMINAL_STATUS:
        return "already_cleaned"
    if not is_temporary_audio_asset(asset):
        return "not_temporary_audio"
    if not force and await temporary_audio_still_referenced(
        db,
        audio_media_id=media_id,
        user_id=user_id,
        workspace_id=workspace_id,
        excluding_post_id=excluding_post_id,
    ):
        return "still_referenced"

    deletion_failed = False
    for ref in collect_storage_refs(asset):
        try:
            await delete_file_async(ref)
        except Exception as exc:
            deletion_failed = True
            event_log(
                logger,
                "warning",
                "composer_audio.cleanup.storage_failed",
                exc_info=exc,
                user_id=user_id,
                media_job_id=media_id,
                failure_type="storage_delete_failed",
                provider_error=shorten_provider_error(exc),
                outcome="retryable",
            )

    if deletion_failed:
        await db.media_assets.update_one(
            {"media_id": media_id, "user_id": user_id},
            {
                "$set": {
                    "temporary_audio_state": "cleanup_failed",
                    "cleanup_reason": reason,
                    "cleanup_failed_at": datetime.now(timezone.utc),
                }
            },
        )
        return "storage_delete_failed"

    now = datetime.now(timezone.utc)
    await db.media_assets.update_one(
        {"media_id": media_id, "user_id": user_id},
        {
            "$set": {
                "status": "deleted",
                "temporary_audio_state": "cleaned",
                "cleanup_reason": reason,
                "storage_deleted_at": now,
                "deleted_at": now,
            },
            "$unset": {
                "storage_key": "",
                "source_storage_key": "",
                "media_url": "",
                "url": "",
            },
        },
    )
    event_log(
        logger,
        "info",
        "composer_audio.cleanup.deleted",
        user_id=user_id,
        media_job_id=media_id,
        reason=reason,
        outcome="deleted",
    )
    return "deleted"


async def cleanup_temporary_audio_assets(
    db,
    *,
    user_id: str,
    workspace_id: str | None,
    media_ids: list[str] | None = None,
    composer_session_id: str | None = None,
    reason: str = "composer_abandoned",
    force: bool = False,
) -> dict[str, int | str]:
    query: dict[str, Any] = {
        "user_id": user_id,
        "temporary": True,
        "purpose": TEMP_AUDIO_PURPOSE,
        "status": {"$nin": list(TERMINAL_STATUS)},
    }
    if workspace_id is not None:
        query["workspace_id"] = workspace_id
    if media_ids:
        query["media_id"] = {"$in": list(dict.fromkeys(media_ids))[:100]}
    elif composer_session_id:
        query["composer_session_id"] = composer_session_id
    else:
        return {"status": "invalid_request", "deleted": 0, "skipped": 0, "failed": 0}

    assets = await db.media_assets.find(query, {"_id": 0, "media_id": 1}).to_list(length=100)
    counts = {"deleted": 0, "skipped": 0, "failed": 0}
    for asset in assets:
        media_id = asset.get("media_id")
        if not media_id:
            continue
        outcome = await delete_temporary_audio_asset(
            db,
            media_id=str(media_id),
            user_id=user_id,
            workspace_id=workspace_id,
            reason=reason,
            force=force,
        )
        if outcome == "deleted":
            counts["deleted"] += 1
        elif outcome == "storage_delete_failed":
            counts["failed"] += 1
        else:
            counts["skipped"] += 1
    return {"status": "complete", **counts}


async def collect_temporary_audio_ids_for_media_ids(
    db,
    *,
    media_ids: list[str],
    user_id: str,
    workspace_id: str | None,
) -> set[str]:
    ids = [media_id for media_id in dict.fromkeys(media_ids) if media_id]
    if not ids:
        return set()

    query: dict[str, Any] = {
        "user_id": user_id,
        "media_id": {"$in": ids},
    }
    if workspace_id is not None:
        query["workspace_id"] = workspace_id

    source_audio_ids: set[str] = set()
    if not hasattr(db.media_assets, "find"):
        return source_audio_ids
    cursor = db.media_assets.find(
        query,
        {
            "_id": 0,
            "media_id": 1,
            "asset_kind": 1,
            "mime_type": 1,
            "audio_mix": 1,
            "source_item_id": 1,
            "source_provider": 1,
        },
    )
    async for asset in cursor:
        if is_temporary_audio_asset(asset) and asset.get("media_id"):
            source_audio_ids.add(str(asset["media_id"]))
        source_audio_id = audio_source_id_from_rendered_asset(asset)
        if source_audio_id:
            source_audio_ids.add(str(source_audio_id))

    if not source_audio_ids:
        return set()

    temp_query: dict[str, Any] = {
        "user_id": user_id,
        "media_id": {"$in": list(source_audio_ids)},
        "temporary": True,
        "purpose": TEMP_AUDIO_PURPOSE,
        "status": {"$nin": list(TERMINAL_STATUS)},
    }
    if workspace_id is not None:
        temp_query["workspace_id"] = workspace_id
    docs = await db.media_assets.find(temp_query, {"_id": 0, "media_id": 1}).to_list(length=len(source_audio_ids))
    return {str(doc["media_id"]) for doc in docs if doc.get("media_id")}


async def cleanup_temporary_audio_for_post_media(
    db,
    *,
    post: dict[str, Any],
    media_ids: list[str],
    reason: str,
    excluding_post_id: str | None = None,
) -> dict[str, int | str]:
    user_id = post.get("user_id")
    if not user_id:
        return {"status": "missing_user", "deleted": 0, "skipped": 0, "failed": 0}
    workspace_id = post.get("workspace_id")
    audio_ids = await collect_temporary_audio_ids_for_media_ids(
        db,
        media_ids=media_ids,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    counts = {"deleted": 0, "skipped": 0, "failed": 0}
    for audio_id in sorted(audio_ids):
        outcome = await delete_temporary_audio_asset(
            db,
            media_id=audio_id,
            user_id=user_id,
            workspace_id=workspace_id,
            reason=reason,
            excluding_post_id=excluding_post_id,
        )
        if outcome == "deleted":
            counts["deleted"] += 1
        elif outcome == "storage_delete_failed":
            counts["failed"] += 1
        else:
            counts["skipped"] += 1
    return {"status": "complete", **counts}


async def cleanup_stale_temporary_audio_assets(
    db,
    *,
    limit: int = 200,
    now: datetime | None = None,
) -> dict[str, int | str]:
    current_time = now or datetime.now(timezone.utc)
    query = {
        "temporary": True,
        "purpose": TEMP_AUDIO_PURPOSE,
        "status": {"$nin": list(TERMINAL_STATUS)},
        "cleanup_after": {"$lte": current_time},
    }
    assets = await db.media_assets.find(
        query,
        {"_id": 0, "media_id": 1, "user_id": 1, "workspace_id": 1},
        limit=limit,
    ).to_list(length=limit)

    counts = {"scanned": len(assets), "deleted": 0, "skipped": 0, "failed": 0}
    for asset in assets:
        media_id = asset.get("media_id")
        user_id = asset.get("user_id")
        if not media_id or not user_id:
            counts["skipped"] += 1
            continue
        outcome = await delete_temporary_audio_asset(
            db,
            media_id=str(media_id),
            user_id=str(user_id),
            workspace_id=asset.get("workspace_id"),
            reason="stale_composer_audio",
        )
        if outcome == "deleted":
            counts["deleted"] += 1
        elif outcome == "storage_delete_failed":
            counts["failed"] += 1
        else:
            counts["skipped"] += 1

    return {"status": "complete", **counts}
