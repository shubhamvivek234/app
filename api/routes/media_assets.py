"""Media asset library — list, upload, delete."""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile, File, status
from pydantic import BaseModel

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["media-assets"])


@router.get("/media-assets")
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


@router.post("/media-assets", status_code=status.HTTP_201_CREATED)
async def upload_media_asset(
    current_user: CurrentUser,
    db: DB,
    file: UploadFile = File(...),
):
    """Upload a file to media library. Delegates actual storage to /upload endpoint logic."""
    from utils.storage import upload_file_async
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc)
    asset_id = str(uuid.uuid4())

    content = await file.read()
    url = await upload_file_async(content, file.filename or asset_id, f"media/{user_id}/")

    doc = {
        "asset_id": asset_id,
        "id": asset_id,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "url": url,
        "status": "ready",
        "created_at": now,
    }
    await db.media_assets.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/media-assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media_asset(asset_id: str, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    result = await db.media_assets.update_one(
        {"$or": [{"asset_id": asset_id}, {"id": asset_id}], "workspace_id": workspace_id},
        {"$set": {"status": "deleted", "deleted_at": datetime.now(timezone.utc)}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Asset not found")
