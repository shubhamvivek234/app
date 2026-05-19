"""Media asset library — list, upload, delete."""
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import magic
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, status

from api.deps import CurrentUser, DB, require_permission

logger = logging.getLogger(__name__)
router = APIRouter(tags=["media-assets"])

_MAX_MEDIA_ASSET_BYTES = int(os.environ.get("MEDIA_ASSET_MAX_BYTES", str(500 * 1024 * 1024)))
_STREAM_CHUNK_SIZE = 8 * 1024 * 1024
_ALLOWED_MIME_PREFIXES = ("image/", "video/")


@router.get("/media-assets", dependencies=[require_permission("media:read")])
async def list_media_assets(current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    cursor = db.media_assets.find(
        {"workspace_id": workspace_id, "status": {"$ne": "deleted"}},
        {"_id": 0},
    ).sort("created_at", -1).limit(200)
    docs = await cursor.to_list(None)
    for d in docs:
        d.setdefault("id", d.get("asset_id", ""))
    return docs


@router.post("/media-assets", status_code=status.HTTP_201_CREATED,
             dependencies=[require_permission("media:upload")])
async def upload_media_asset(
    request: Request,
    current_user: CurrentUser,
    db: DB,
    file: UploadFile = File(...),
):
    """Upload a bounded image/video file to media library."""
    from utils.storage import build_storage_key, upload_file_async
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc)
    asset_id = str(uuid.uuid4())

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_MEDIA_ASSET_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds maximum media library upload size",
        )

    first_chunk = await file.read(_STREAM_CHUNK_SIZE)
    detected_type = magic.from_buffer(first_chunk, mime=True) if first_chunk else ""
    content_type = detected_type or file.content_type or "application/octet-stream"
    if not any(content_type.startswith(prefix) for prefix in _ALLOWED_MIME_PREFIXES):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {content_type}",
        )

    content = bytearray(first_chunk)
    while True:
        chunk = await file.read(_STREAM_CHUNK_SIZE)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > _MAX_MEDIA_ASSET_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File exceeds maximum media library upload size",
            )

    original_name = Path(file.filename or "").name
    original_ext = Path(original_name).suffix.lower()
    safe_filename = f"{asset_id}{original_ext}" if original_ext else asset_id
    storage_folder = f"media/{user_id}"
    storage_key = build_storage_key(storage_folder, safe_filename)
    url = await upload_file_async(bytes(content), safe_filename, content_type, storage_folder)

    doc = {
        "asset_id": asset_id,
        "id": asset_id,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "filename": original_name or safe_filename,
        "content_type": content_type,
        "file_size_bytes": len(content),
        "url": url,
        "storage_key": storage_key,
        "status": "ready",
        "created_at": now,
    }
    await db.media_assets.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/media-assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[require_permission("media:upload")])
async def delete_media_asset(asset_id: str, current_user: CurrentUser, db: DB):
    from utils.storage import delete_file_async

    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    doc = await db.media_assets.find_one(
        {"$or": [{"asset_id": asset_id}, {"id": asset_id}], "workspace_id": workspace_id},
        {"_id": 0, "storage_key": 1, "url": 1},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Asset not found")

    storage_ref = doc.get("storage_key") or doc.get("url")
    if storage_ref:
        try:
            await delete_file_async(storage_ref)
        except Exception as exc:
            logger.warning("Media asset storage delete failed for %s: %s", asset_id, exc)

    result = await db.media_assets.update_one(
        {"$or": [{"asset_id": asset_id}, {"id": asset_id}], "workspace_id": workspace_id},
        {"$set": {"status": "deleted", "deleted_at": datetime.now(timezone.utc)}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Asset not found")
