import csv
import io
import re
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Response, status

from api.deps import CurrentUser, DB, require_permission
from api.models.bio import (
    BioPageResponse,
    BioPageUpdate,
    SeoConfig,
    ThemeConfig,
)

router = APIRouter(prefix="/bio", tags=["smart-bio"])

HANDLE_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]{3,30}$")


def _sanitize_handle(raw: str) -> str:
    cleaned = raw.strip().lstrip("@").lower()
    if not HANDLE_REGEX.match(cleaned):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Handle must be 3-30 characters and contain only letters, numbers, hyphens, or underscores.",
        )
    return cleaned


@router.get("/me", response_model=BioPageResponse)
async def get_my_bio_page(
    current_user: CurrentUser,
    db: DB,
) -> BioPageResponse:
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    user_id = current_user["user_id"]

    page = await db.bio_pages.find_one({"workspace_id": workspace_id})
    now = datetime.now(timezone.utc)

    if not page:
        # Generate default handle from user email or name
        email_prefix = current_user.get("email", "user").split("@")[0]
        cleaned_handle = re.sub(r"[^a-zA-Z0-9_-]", "", email_prefix)[:20] or "creator"
        
        # Ensure uniqueness
        existing = await db.bio_pages.find_one({"handle": cleaned_handle})
        if existing:
            cleaned_handle = f"{cleaned_handle}_{int(now.timestamp()) % 10000}"

        display_name = current_user.get("name") or current_user.get("email", "My Bio").split("@")[0].capitalize()

        default_doc = {
            "_id": ObjectId(),
            "workspace_id": workspace_id,
            "user_id": user_id,
            "handle": cleaned_handle,
            "title": display_name,
            "bio": "Welcome to my official social hub ✨ Explore my latest links & projects below.",
            "avatar_url": current_user.get("picture") or "",
            "verified_badge": False,
            "theme": ThemeConfig().model_dump(),
            "social_links": [],
            "blocks": [
                {
                    "id": "blk_feed",
                    "type": "feed_grid",
                    "title": "Recent Social Posts",
                    "limit": 6,
                    "show_caption": True,
                    "active": True,
                },
                {
                    "id": "blk_welcome",
                    "type": "link",
                    "title": "Visit My Main Website 🌐",
                    "subtitle": "Portfolio, case studies, and services",
                    "url": "https://unravler.com",
                    "icon": "globe",
                    "badge": "Featured",
                    "active": True,
                    "click_count": 0,
                },
                {
                    "id": "blk_newsletter",
                    "type": "lead_capture",
                    "headline": "Stay Updated with My Newsletter 💌",
                    "subheadline": "Get weekly curation and behind-the-scenes insights directly in your inbox.",
                    "button_label": "Subscribe",
                    "active": True,
                }
            ],
            "custom_domain": "",
            "seo": {
                "meta_title": f"{display_name} | Smart Bio",
                "meta_description": f"Explore links, latest social posts, and updates from {display_name}.",
                "meta_image_url": "",
            },
            "published": True,
            "total_views": 0,
            "total_clicks": 0,
            "created_at": now,
            "updated_at": now,
        }
        await db.bio_pages.insert_one(default_doc)
        page = default_doc

    return BioPageResponse(
        id=str(page["_id"]),
        workspace_id=page["workspace_id"],
        handle=page["handle"],
        title=page.get("title", ""),
        bio=page.get("bio", ""),
        avatar_url=page.get("avatar_url", ""),
        verified_badge=page.get("verified_badge", False),
        theme=ThemeConfig(**(page.get("theme") or {})),
        social_links=page.get("social_links", []),
        blocks=page.get("blocks", []),
        custom_domain=page.get("custom_domain", ""),
        seo=SeoConfig(**(page.get("seo") or {})),
        published=page.get("published", True),
        total_views=page.get("total_views", 0),
        total_clicks=page.get("total_clicks", 0),
        created_at=page.get("created_at", now),
        updated_at=page.get("updated_at", now),
    )


@router.put("/me", response_model=BioPageResponse)
async def update_my_bio_page(
    body: BioPageUpdate,
    current_user: CurrentUser,
    db: DB,
) -> BioPageResponse:
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    sanitized_handle = _sanitize_handle(body.handle)
    now = datetime.now(timezone.utc)

    # Check handle uniqueness
    existing_handle_owner = await db.bio_pages.find_one({
        "handle": sanitized_handle,
        "workspace_id": {"$ne": workspace_id},
    })
    if existing_handle_owner:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"The handle '@{sanitized_handle}' is already taken by another creator.",
        )

    update_payload = {
        "handle": sanitized_handle,
        "title": body.title.strip(),
        "bio": body.bio.strip(),
        "avatar_url": body.avatar_url.strip(),
        "verified_badge": body.verified_badge,
        "theme": body.theme.model_dump(),
        "social_links": [s.model_dump() for s in body.social_links],
        "blocks": [b.model_dump() for b in body.blocks],
        "custom_domain": body.custom_domain.strip().lower(),
        "seo": (body.seo or SeoConfig()).model_dump(),
        "published": body.published,
        "updated_at": now,
    }

    result = await db.bio_pages.find_one_and_update(
        {"workspace_id": workspace_id},
        {"$set": update_payload},
        return_document=True,
    )

    if not result:
        # Create if not exists
        doc = {
            "_id": ObjectId(),
            "workspace_id": workspace_id,
            "user_id": current_user["user_id"],
            "total_views": 0,
            "total_clicks": 0,
            "created_at": now,
            **update_payload,
        }
        await db.bio_pages.insert_one(doc)
        result = doc

    return BioPageResponse(
        id=str(result["_id"]),
        workspace_id=result["workspace_id"],
        handle=result["handle"],
        title=result.get("title", ""),
        bio=result.get("bio", ""),
        avatar_url=result.get("avatar_url", ""),
        verified_badge=result.get("verified_badge", False),
        theme=ThemeConfig(**(result.get("theme") or {})),
        social_links=result.get("social_links", []),
        blocks=result.get("blocks", []),
        custom_domain=result.get("custom_domain", ""),
        seo=SeoConfig(**(result.get("seo") or {})),
        published=result.get("published", True),
        total_views=result.get("total_views", 0),
        total_clicks=result.get("total_clicks", 0),
        created_at=result.get("created_at", now),
        updated_at=result.get("updated_at", now),
    )


@router.get("/analytics")
async def get_bio_analytics(
    current_user: CurrentUser,
    db: DB,
):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    page = await db.bio_pages.find_one({"workspace_id": workspace_id})
    if not page:
        return {"views": 0, "clicks": 0, "ctr": 0, "referrers": [], "top_blocks": []}

    total_views = page.get("total_views", 0)
    total_clicks = page.get("total_clicks", 0)
    ctr = round((total_clicks / total_views * 100), 1) if total_views > 0 else 0

    # Aggregate top referrers from analytics collection
    pipeline = [
        {"$match": {"workspace_id": workspace_id, "event_type": "click"}},
        {"$group": {"_id": "$referrer", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    raw_referrers = await db.bio_analytics.aggregate(pipeline).to_list(length=5)
    referrers = [
        {"source": r["_id"] or "Direct / Social Bio", "clicks": r["count"]}
        for r in raw_referrers
    ]

    # Block clicks breakdown
    blocks = page.get("blocks", [])
    top_blocks = [
        {"id": b.get("id"), "title": b.get("title") or b.get("headline") or "Block", "type": b.get("type"), "clicks": b.get("click_count", 0)}
        for b in blocks if b.get("type") in ("link", "embed", "media_card")
    ]
    top_blocks.sort(key=lambda x: x["clicks"], reverse=True)

    return {
        "views": total_views,
        "clicks": total_clicks,
        "ctr": ctr,
        "referrers": referrers,
        "top_blocks": top_blocks,
    }


@router.get("/leads")
async def get_bio_leads(
    current_user: CurrentUser,
    db: DB,
):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    cursor = db.workspace_leads.find({"workspace_id": workspace_id}).sort("created_at", -1).limit(200)
    leads = await cursor.to_list(length=200)
    return [
        {
            "id": str(lead["_id"]),
            "email": lead["email"],
            "created_at": lead["created_at"].isoformat() if hasattr(lead["created_at"], "isoformat") else str(lead["created_at"]),
        }
        for lead in leads
    ]


@router.get("/leads/export")
async def export_bio_leads_csv(
    current_user: CurrentUser,
    db: DB,
):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    cursor = db.workspace_leads.find({"workspace_id": workspace_id}).sort("created_at", -1)
    leads = await cursor.to_list(length=5000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Email", "Subscribed At", "Source"])
    for lead in leads:
        ts = lead["created_at"].isoformat() if hasattr(lead["created_at"], "isoformat") else str(lead["created_at"])
        writer.writerow([lead["email"], ts, "Smart Bio Lead Form"])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=unravler_bio_leads_{int(datetime.now().timestamp())}.csv"},
    )
