"""Developer endpoints for registering and managing OAuth2 Applications."""
import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import List

from bson import ObjectId
from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUser, DB, require_permission
from api.models.developer_apps import OAuthAppCreate, OAuthAppResponse, OAuthAppUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/developer/apps", tags=["developer-apps"])

MAX_OAUTH_APPS_PER_WORKSPACE = 10


def _generate_client_credentials() -> tuple[str, str, str]:
    """Generate (client_id, client_secret, client_secret_hash)."""
    client_id = f"unr_app_{secrets.token_hex(12)}"
    client_secret = f"unr_sec_{secrets.token_urlsafe(32)}"
    secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
    return client_id, client_secret, secret_hash


@router.get(
    "",
    response_model=List[OAuthAppResponse],
    dependencies=[require_permission("api_key:manage")],
)
async def list_oauth_apps(
    current_user: CurrentUser,
    db: DB,
) -> List[OAuthAppResponse]:
    """List all registered OAuth applications in the workspace."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    cursor = db.oauth_applications.find(
        {"workspace_id": workspace_id, "is_active": True},
        {"client_secret_hash": 0},
    ).sort("created_at", -1)

    apps = await cursor.to_list(length=MAX_OAUTH_APPS_PER_WORKSPACE)
    return [
        OAuthAppResponse(
            id=str(app["_id"]),
            name=app["name"],
            client_id=app["client_id"],
            client_secret=None,
            redirect_uris=app.get("redirect_uris", []),
            description=app.get("description", ""),
            homepage_url=app.get("homepage_url", ""),
            logo_url=app.get("logo_url", ""),
            created_at=app["created_at"],
            is_active=app.get("is_active", True),
        )
        for app in apps
    ]


@router.post(
    "",
    response_model=OAuthAppResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("api_key:manage")],
)
async def create_oauth_app(
    body: OAuthAppCreate,
    current_user: CurrentUser,
    db: DB,
) -> OAuthAppResponse:
    """Register a new OAuth application and return client credentials."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    count = await db.oauth_applications.count_documents(
        {"workspace_id": workspace_id, "is_active": True}
    )
    if count >= MAX_OAUTH_APPS_PER_WORKSPACE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Maximum {MAX_OAUTH_APPS_PER_WORKSPACE} OAuth applications allowed per workspace.",
        )

    client_id, client_secret, secret_hash = _generate_client_credentials()
    now = datetime.now(timezone.utc)

    doc = {
        "_id": ObjectId(),
        "workspace_id": workspace_id,
        "created_by": current_user["user_id"],
        "name": body.name.strip(),
        "client_id": client_id,
        "client_secret_hash": secret_hash,
        "redirect_uris": [u.strip() for u in body.redirect_uris if u.strip()],
        "description": (body.description or "").strip(),
        "homepage_url": (body.homepage_url or "").strip(),
        "logo_url": (body.logo_url or "").strip(),
        "created_at": now,
        "updated_at": now,
        "is_active": True,
    }

    await db.oauth_applications.insert_one(doc)
    logger.info("Created OAuth App %s (%s) for workspace %s", doc["name"], client_id, workspace_id)

    return OAuthAppResponse(
        id=str(doc["_id"]),
        name=doc["name"],
        client_id=client_id,
        client_secret=client_secret,
        redirect_uris=doc["redirect_uris"],
        description=doc["description"],
        homepage_url=doc["homepage_url"],
        logo_url=doc["logo_url"],
        created_at=now,
        is_active=True,
    )


@router.post(
    "/{app_id}/rotate-secret",
    response_model=OAuthAppResponse,
    dependencies=[require_permission("api_key:manage")],
)
async def rotate_oauth_app_secret(
    app_id: str,
    current_user: CurrentUser,
    db: DB,
) -> OAuthAppResponse:
    """Rotate the client secret for an existing OAuth application."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    try:
        oid = ObjectId(app_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    app = await db.oauth_applications.find_one({"_id": oid, "workspace_id": workspace_id, "is_active": True})
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    new_secret = f"unr_sec_{secrets.token_urlsafe(32)}"
    new_secret_hash = hashlib.sha256(new_secret.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    await db.oauth_applications.update_one(
        {"_id": oid},
        {"$set": {"client_secret_hash": new_secret_hash, "updated_at": now}},
    )

    return OAuthAppResponse(
        id=str(app["_id"]),
        name=app["name"],
        client_id=app["client_id"],
        client_secret=new_secret,
        redirect_uris=app.get("redirect_uris", []),
        description=app.get("description", ""),
        homepage_url=app.get("homepage_url", ""),
        logo_url=app.get("logo_url", ""),
        created_at=app["created_at"],
        is_active=True,
    )


@router.delete(
    "/{app_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("api_key:manage")],
)
async def delete_oauth_app(
    app_id: str,
    current_user: CurrentUser,
    db: DB,
) -> None:
    """Soft delete / revoke an OAuth application."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    try:
        oid = ObjectId(app_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    result = await db.oauth_applications.update_one(
        {"_id": oid, "workspace_id": workspace_id, "is_active": True},
        {"$set": {"is_active": False, "deleted_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
