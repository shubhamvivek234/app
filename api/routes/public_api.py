"""
Developer REST API under /api/public.
Authenticated via personal tokens or workspace API keys.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from starlette.requests import Request as StarletteRequest

from api.deps import DB, ensure_active_workspace
from api.limiter import limiter
from api.models.post import PostResponse, UpdatePostRequest
from api.routes import accounts as accounts_route
from api.routes import auth as auth_route
from api.routes import posts as posts_route
from api.routes import stats as stats_route
from utils.developer_tokens import PERSONAL_TOKEN_TYPE, WORKSPACE_TOKEN_TYPE, effective_scopes, has_scope, hash_developer_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public-api"])
_PUBLIC_API_ENABLED = os.environ.get("PUBLIC_API_ENABLED", "true").lower() == "true"


class PublicPostListResponse(BaseModel):
    data: list[PostResponse]
    total: int
    page: int
    limit: int


class PublicCreatePostRequest(BaseModel):
    content: str = Field(default="", max_length=10000)
    account_ids: list[str] = Field(default_factory=list, min_length=1, max_length=20)
    platforms: list[str] = Field(default_factory=list, max_length=10)
    scheduled_at: datetime | None = None
    scheduled_time: datetime | None = None
    timeslot_category: str | None = None
    publish_now: bool = False
    media_urls: list[str] = Field(default_factory=list, max_length=10)
    title: str | None = Field(default=None, max_length=500)
    post_type: str = Field(default="text", max_length=50)
    timezone: str = Field(default="UTC", max_length=100)


class PublicUpdatePostRequest(BaseModel):
    content: str | None = Field(default=None, max_length=10000)
    scheduled_at: datetime | None = None
    scheduled_time: datetime | None = None
    platforms: list[str] | None = Field(default=None, max_length=10)
    account_ids: list[str] | None = Field(default=None, max_length=20)
    media_urls: list[str] | None = Field(default=None, max_length=10)
    title: str | None = Field(default=None, max_length=500)
    post_type: str | None = Field(default=None, max_length=50)
    timezone: str | None = Field(default=None, max_length=100)
    version: int | None = None


class PublicAIRequest(BaseModel):
    topic: str
    platform: Optional[str] = None
    tone: Optional[str] = None
    count: int = 1
    additional_context: Optional[str] = None


class PublicApprovalDecisionRequest(BaseModel):
    reason: str = ""


class PublicApprovalResubmitRequest(BaseModel):
    content: str | None = None


def _ensure_enabled() -> None:
    if not _PUBLIC_API_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Public API is disabled")


def _extract_raw_token(authorization: str | None, x_api_key: str | None) -> str:
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Authorization header. Expected Bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return parts[1].strip()
    if x_api_key:
        return x_api_key.strip()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authorization Bearer token or X-API-Key header is required",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _load_workspace_role(db: DB, user_id: str, workspace_id: str | None) -> str | None:
    if not workspace_id:
        return None
    membership = await db.workspace_members.find_one(
        {"workspace_id": workspace_id, "user_id": user_id},
        {"_id": 0, "role": 1},
    )
    if membership and membership.get("role"):
        return membership["role"]
    workspace = await db.workspaces.find_one(
        {"workspace_id": workspace_id},
        {"_id": 0, "owner_id": 1},
    )
    if workspace and workspace.get("owner_id") == user_id:
        return "owner"
    return None


async def _resolve_public_principal(
    *,
    request: Request,
    db: DB,
    authorization: str | None,
    x_api_key: str | None,
    required_scope: str | None = None,
) -> tuple[dict, dict]:
    _ensure_enabled()
    raw_token = _extract_raw_token(authorization, x_api_key)
    key_hash = hash_developer_token(raw_token)
    token_doc = await db.api_keys.find_one(
        {"key_hash": key_hash, "revoked": {"$ne": True}},
        {"_id": 0},
    )
    if not token_doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked developer token")
    if not has_scope(token_doc, required_scope):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Developer token lacks required scope: {required_scope}",
        )

    user = await db.users.find_one({"user_id": token_doc["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Developer token user no longer exists")

    user = await ensure_active_workspace(db, user, create_if_missing=False)
    workspace_id = token_doc.get("workspace_id") or user.get("default_workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Developer token is not bound to a workspace")

    role = await _load_workspace_role(db, user["user_id"], workspace_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Developer token workspace access is no longer valid")

    user["default_workspace_id"] = workspace_id
    user["workspace_role"] = role
    user["workspace_permissions"] = []
    request.state.user_id = user["user_id"]

    try:
        await db.api_keys.update_one(
            {"id": token_doc.get("id") or token_doc.get("key_id")},
            {"$set": {"last_used_at": datetime.now(timezone.utc)}},
        )
    except Exception:
        pass

    return token_doc, user


def _public_request(method: str, path: str, request: Request) -> StarletteRequest:
    headers = [(b"x-forwarded-proto", b"https")]
    auth_header = request.headers.get("authorization")
    if auth_header:
        headers.append((b"authorization", auth_header.encode()))
    return StarletteRequest(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": headers,
            "client": ("127.0.0.1", 0),
            "server": ("api.unravler.local", 443),
            "scheme": "https",
            "state": {},
        }
    )


async def _resolve_accounts_to_platforms(db: DB, user_id: str, account_ids: list[str]) -> list[str]:
    cursor = db.social_accounts.find(
        {"account_id": {"$in": account_ids}, "user_id": user_id, "is_active": True},
        {"_id": 0, "account_id": 1, "platform": 1},
    )
    accounts = await cursor.to_list(length=max(20, len(account_ids) * 2))
    found_ids = {doc["account_id"] for doc in accounts}
    invalid = [account_id for account_id in account_ids if account_id not in found_ids]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown or inactive account IDs: {invalid}",
        )
    return list(dict.fromkeys(doc["platform"] for doc in accounts))


def _request_fingerprint(payload: dict | None) -> str:
    return hash_developer_token(json.dumps(payload or {}, sort_keys=True, default=str))


async def _restore_idempotent_response(
    db: DB,
    *,
    token_doc: dict,
    method: str,
    path: str,
    key: str | None,
    request_hash: str,
) -> tuple[int, dict | None] | None:
    if not key:
        return None
    doc = await db.public_api_idempotency.find_one(
        {
            "token_id": token_doc.get("id") or token_doc.get("key_id"),
            "method": method,
            "path": path,
            "idempotency_key": key,
        },
        {"_id": 0},
    )
    if not doc:
        return None
    if doc.get("request_hash") != request_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used with a different request payload.",
        )
    return doc.get("status_code", status.HTTP_200_OK), doc.get("response_payload")


async def _store_idempotent_response(
    db: DB,
    *,
    token_doc: dict,
    method: str,
    path: str,
    key: str | None,
    request_hash: str,
    status_code: int,
    response_payload: dict | None,
) -> None:
    if not key:
        return
    await db.public_api_idempotency.update_one(
        {
            "token_id": token_doc.get("id") or token_doc.get("key_id"),
            "method": method,
            "path": path,
            "idempotency_key": key,
        },
        {
            "$set": {
                "request_hash": request_hash,
                "status_code": status_code,
                "response_payload": response_payload,
                "workspace_id": token_doc.get("workspace_id"),
                "updated_at": datetime.now(timezone.utc),
            },
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "created_at": datetime.now(timezone.utc),
            },
        },
        upsert=True,
    )


def _serialize_model(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_serialize_model(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_model(item) for key, item in value.items()}
    return value


def _response_key(request: Request, post_id: str | None = None) -> str:
    return request.url.path if post_id is None else request.url.path.replace("{post_id}", post_id)


@router.get("/me")
@limiter.limit("60/minute")
async def public_get_me(
    request: Request,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope=None,
    )
    response = await auth_route._build_user_response(db, current_user)
    payload = response.model_dump(mode="json")
    payload["token_id"] = token_doc.get("id") or token_doc.get("key_id")
    payload["token_type"] = token_doc.get("token_type") or WORKSPACE_TOKEN_TYPE
    payload["scopes"] = effective_scopes(token_doc)
    payload["token_scopes"] = effective_scopes(token_doc)
    return payload


@router.get("/accounts")
@limiter.limit("60/minute")
async def public_list_accounts(
    request: Request,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    _token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="accounts:read",
    )
    accounts = await accounts_route.list_accounts(current_user=current_user, db=db)
    data = [_serialize_model(item) for item in accounts]
    return {"accounts": data, "total": len(data)}


@router.get("/posts", response_model=PublicPostListResponse)
@limiter.limit("60/minute")
async def public_list_posts(
    request: Request,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
) -> PublicPostListResponse:
    _token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="posts:read",
    )
    posts = await posts_route.list_posts(
        current_user=current_user,
        db=db,
        workspace_id=current_user["default_workspace_id"],
        status_filter=status_filter,
        published_window=None,
        page=page,
        limit=limit,
    )
    query = {
        "workspace_id": current_user["default_workspace_id"],
        "user_id": current_user["user_id"],
        "deleted_at": {"$exists": False},
    }
    if status_filter:
        query["status"] = status_filter
    total = await db.posts.count_documents(query)
    return PublicPostListResponse(
        data=posts,
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/posts/{post_id}", response_model=PostResponse)
@limiter.limit("60/minute")
async def public_get_post(
    request: Request,
    post_id: str,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> PostResponse:
    _token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="posts:read",
    )
    return await posts_route.get_post(post_id=post_id, current_user=current_user, db=db)


@router.post("/posts", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def public_create_post(
    request: Request,
    body: PublicCreatePostRequest,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="posts:write",
    )
    platforms = await _resolve_accounts_to_platforms(db, current_user["user_id"], list(body.account_ids))
    payload = body.model_dump(mode="json")
    request_hash = _request_fingerprint(payload)
    cached = await _restore_idempotent_response(
        db,
        token_doc=token_doc,
        method="POST",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if cached:
        _status, response_payload = cached
        return response_payload or {}

    effective_scheduled_time = body.scheduled_time if body.scheduled_time is not None else body.scheduled_at
    core_request = posts_route.CreatePostRequest(
        content=body.content,
        account_ids=list(body.account_ids),
        platforms=platforms,
        publish_now=body.publish_now,
        scheduled_time=effective_scheduled_time,
        timeslot_category=body.timeslot_category,
        media_urls=list(body.media_urls),
        title=body.title,
        post_type=body.post_type,
        timezone=body.timezone,
    )
    created = await posts_route.create_post(
        request=_public_request("POST", request.url.path, request),
        body=core_request,
        current_user=current_user,
        db=db,
        queue_redis=None,
    )
    response_payload = {
        "id": created.id,
        "status": created.status.value if hasattr(created.status, "value") else str(created.status),
        "scheduled_at": created.scheduled_time.isoformat() if created.scheduled_time else None,
        "message": (
            "Post is being published now." if body.publish_now
            else f"Post scheduled for {created.scheduled_time.isoformat()}." if created.scheduled_time
            else "Post saved as draft."
        ),
    }
    await _store_idempotent_response(
        db,
        token_doc=token_doc,
        method="POST",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=status.HTTP_201_CREATED,
        response_payload=response_payload,
    )
    return response_payload


@router.patch("/posts/{post_id}", response_model=PostResponse)
@limiter.limit("30/minute")
async def public_update_post(
    request: Request,
    post_id: str,
    body: PublicUpdatePostRequest,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> PostResponse:
    token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="posts:write",
    )
    payload = body.model_dump(mode="json", exclude_none=True)
    request_hash = _request_fingerprint(payload)
    cached = await _restore_idempotent_response(
        db,
        token_doc=token_doc,
        method="PATCH",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if cached:
        _status, response_payload = cached
        return PostResponse.model_validate(response_payload)

    existing = await posts_route.get_post(post_id=post_id, current_user=current_user, db=db)
    platforms = list(body.platforms) if body.platforms is not None else None
    if body.account_ids is not None:
        platforms = await _resolve_accounts_to_platforms(db, current_user["user_id"], list(body.account_ids))

    effective_scheduled_time = body.scheduled_time if body.scheduled_time is not None else body.scheduled_at
    core_request = UpdatePostRequest(
        content=body.content,
        scheduled_time=effective_scheduled_time,
        platforms=platforms,
        account_ids=list(body.account_ids) if body.account_ids is not None else None,
        media_urls=list(body.media_urls) if body.media_urls is not None else None,
        post_type=body.post_type,
        title=body.title,
        timezone=body.timezone,
        version=body.version if body.version is not None else existing.version,
    )
    updated = await posts_route.update_post(
        post_id=post_id,
        body=core_request,
        current_user=current_user,
        db=db,
    )
    await _store_idempotent_response(
        db,
        token_doc=token_doc,
        method="PATCH",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=status.HTTP_200_OK,
        response_payload=updated.model_dump(mode="json"),
    )
    return updated


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def public_delete_post(
    request: Request,
    post_id: str,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Response:
    token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="posts:delete",
    )
    request_hash = _request_fingerprint({"post_id": post_id})
    cached = await _restore_idempotent_response(
        db,
        token_doc=token_doc,
        method="DELETE",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if cached:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    await posts_route.delete_post(post_id=post_id, current_user=current_user, db=db)
    await _store_idempotent_response(
        db,
        token_doc=token_doc,
        method="DELETE",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=status.HTTP_204_NO_CONTENT,
        response_payload={"deleted": True},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/posts/{post_id}/retry")
@limiter.limit("20/minute")
async def public_retry_post(
    request: Request,
    post_id: str,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="posts:write",
    )
    posts_route._ensure_verified_email_for_publish_action(current_user)
    request_hash = _request_fingerprint({"post_id": post_id})
    cached = await _restore_idempotent_response(
        db,
        token_doc=token_doc,
        method="POST",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if cached:
        _status, response_payload = cached
        return response_payload or {}

    retried = await posts_route.retry_failed_post(
        post_id=post_id,
        current_user=current_user,
        db=db,
        platform=None,
    )
    response_payload = _serialize_model(retried)
    await _store_idempotent_response(
        db,
        token_doc=token_doc,
        method="POST",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=status.HTTP_200_OK,
        response_payload=response_payload,
    )
    return response_payload


_PLATFORM_HINTS: dict[str, str] = {
    "twitter": " Keep it under 280 characters.",
    "linkedin": " Make it professional and insight-driven.",
    "instagram": " Make it engaging with 3–5 relevant hashtags.",
    "facebook": " Write in a conversational tone.",
    "tiktok": " Write a short, punchy caption with trending language.",
    "youtube": " Write a concise, keyword-rich description.",
}

_SYSTEM_MESSAGE_BASE = (
    "You are a social media content expert. "
    "Generate engaging, brand-safe social media posts. "
    "Return only the post text — no explanations or meta-commentary."
)


@router.post("/ai/generate")
@limiter.limit("20/minute")
async def public_generate_content(
    request: Request,
    body: PublicAIRequest,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    _token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="ai:generate",
    )

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service is not configured")
    if not body.topic.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Topic cannot be empty")

    platform_hint = _PLATFORM_HINTS.get(body.platform or "", "")
    tone_hint = f" Use a {body.tone} tone." if body.tone else ""
    context_hint = f" Additional context: {body.additional_context}" if body.additional_context else ""
    system_message = f"{_SYSTEM_MESSAGE_BASE}{platform_hint}{tone_hint}"
    prompt = f"Write a social media post about: {body.topic}.{context_hint}"
    count = max(1, min(body.count, 5))
    results = []

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore

        for _ in range(count):
            session_id = f"public-content-gen-{current_user['user_id']}-{uuid.uuid4()}"
            chat = (
                LlmChat(api_key=api_key, session_id=session_id, system_message=system_message)
                .with_model("openai", "gpt-4o-mini")
            )
            response = await chat.send_message(UserMessage(text=prompt))
            results.append(response)
    except Exception as exc:
        logger.error("Public AI generation error user=%s: %s", current_user["user_id"], exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI content generation failed. Please try again.")

    return {
        "variations": results,
        "platform": body.platform,
        "count": len(results),
    }


@router.get("/stats")
@limiter.limit("60/minute")
async def public_get_stats(
    request: Request,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    _token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="stats:read",
    )
    return await stats_route.get_stats(current_user=current_user, db=db)


@router.get("/approvals")
@limiter.limit("60/minute")
async def public_list_approvals(
    request: Request,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    limit: int = Query(default=25, ge=1, le=100),
) -> dict:
    _token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="approval:read",
    )
    return await posts_route.list_approval_queue(current_user=current_user, db=db, limit=limit)


@router.post("/posts/{post_id}/submit-review")
@limiter.limit("20/minute")
async def public_submit_post_for_review(
    request: Request,
    post_id: str,
    body: PublicApprovalResubmitRequest,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="approval:write",
    )
    payload = body.model_dump(mode="json")
    request_hash = _request_fingerprint(payload)
    cached = await _restore_idempotent_response(
        db,
        token_doc=token_doc,
        method="POST",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if cached:
        _status, response_payload = cached
        return response_payload or {}
    result = await posts_route.submit_post_for_review(
        post_id=post_id,
        body=posts_route.ApprovalResubmitBody(content=body.content),
        current_user=current_user,
        db=db,
    )
    response_payload = _serialize_model(result)
    await _store_idempotent_response(
        db,
        token_doc=token_doc,
        method="POST",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=status.HTTP_200_OK,
        response_payload=response_payload,
    )
    return response_payload


@router.post("/posts/{post_id}/approve")
@limiter.limit("20/minute")
async def public_approve_post(
    request: Request,
    post_id: str,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="approval:write",
    )
    posts_route._ensure_verified_email_for_publish_action(current_user)
    request_hash = _request_fingerprint({"post_id": post_id})
    cached = await _restore_idempotent_response(
        db,
        token_doc=token_doc,
        method="POST",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if cached:
        _status, response_payload = cached
        return response_payload or {}
    result = await posts_route.approve_post(post_id=post_id, current_user=current_user, db=db)
    response_payload = _serialize_model(result)
    await _store_idempotent_response(
        db,
        token_doc=token_doc,
        method="POST",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=status.HTTP_200_OK,
        response_payload=response_payload,
    )
    return response_payload


@router.post("/posts/{post_id}/reject")
@limiter.limit("20/minute")
async def public_reject_post(
    request: Request,
    post_id: str,
    body: PublicApprovalDecisionRequest,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="approval:write",
    )
    payload = body.model_dump(mode="json")
    request_hash = _request_fingerprint(payload)
    cached = await _restore_idempotent_response(
        db,
        token_doc=token_doc,
        method="POST",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if cached:
        _status, response_payload = cached
        return response_payload or {}
    result = await posts_route.reject_post(
        post_id=post_id,
        body=posts_route.ApprovalDecisionBody(reason=body.reason),
        current_user=current_user,
        db=db,
    )
    response_payload = _serialize_model(result)
    await _store_idempotent_response(
        db,
        token_doc=token_doc,
        method="POST",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=status.HTTP_200_OK,
        response_payload=response_payload,
    )
    return response_payload


@router.post("/posts/{post_id}/resubmit")
@limiter.limit("20/minute")
async def public_resubmit_post(
    request: Request,
    post_id: str,
    body: PublicApprovalResubmitRequest,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="approval:write",
    )
    payload = body.model_dump(mode="json")
    request_hash = _request_fingerprint(payload)
    cached = await _restore_idempotent_response(
        db,
        token_doc=token_doc,
        method="POST",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if cached:
        _status, response_payload = cached
        return response_payload or {}
    result = await posts_route.resubmit_post(
        post_id=post_id,
        body=posts_route.ApprovalResubmitBody(content=body.content),
        current_user=current_user,
        db=db,
    )
    response_payload = _serialize_model(result)
    await _store_idempotent_response(
        db,
        token_doc=token_doc,
        method="POST",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=status.HTTP_200_OK,
        response_payload=response_payload,
    )
    return response_payload


@router.post("/posts/{post_id}/return-to-draft")
@limiter.limit("20/minute")
async def public_return_post_to_draft(
    request: Request,
    post_id: str,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="approval:write",
    )
    request_hash = _request_fingerprint({"post_id": post_id})
    cached = await _restore_idempotent_response(
        db,
        token_doc=token_doc,
        method="POST",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
    )
    if cached:
        _status, response_payload = cached
        return response_payload or {}
    result = await posts_route.return_post_to_draft(
        post_id=post_id,
        current_user=current_user,
        db=db,
    )
    response_payload = _serialize_model(result)
    await _store_idempotent_response(
        db,
        token_doc=token_doc,
        method="POST",
        path=request.url.path,
        key=idempotency_key,
        request_hash=request_hash,
        status_code=status.HTTP_200_OK,
        response_payload=response_payload,
    )
    return response_payload


# ── Timeslots ─────────────────────────────────────────────────────────────────

@router.get("/timeslots")
@limiter.limit("60/minute")
async def public_list_timeslots(
    request: Request,
    db: DB,
    account_id: str = Query(..., description="Social account ID"),
    category: str = Query("Category 1"),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="accounts:read",
    )
    from api.routes import timeslots as timeslots_route
    return await timeslots_route.list_timeslots(
        current_user=current_user,
        db=db,
        account_id=account_id,
        category=category,
    )


@router.get("/timeslots/next-slot")
@limiter.limit("60/minute")
async def public_get_next_slot(
    request: Request,
    db: DB,
    account_id: str = Query(..., description="Social account ID"),
    category: str = Query("Category 1"),
    timezone: str | None = Query(None, description="User timezone"),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="accounts:read",
    )
    from api.routes import timeslots as timeslots_route
    return await timeslots_route.get_next_slot(
        current_user=current_user,
        db=db,
        account_id=account_id,
        category=category,
        timezone=timezone,
    )


# ── Webhooks ──────────────────────────────────────────────────────────────────

@router.get("/webhooks")
@limiter.limit("60/minute")
async def public_list_webhooks(
    request: Request,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="webhooks:manage",
    )
    from api.routes import user_webhooks as webhooks_route
    return await webhooks_route.list_webhooks(current_user=current_user, db=db)


@router.post("/webhooks", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def public_create_webhook(
    request: Request,
    body: dict,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="webhooks:manage",
    )
    from api.routes import user_webhooks as webhooks_route
    webhook_body = webhooks_route.WebhookEndpointCreate.model_validate(body)
    return await webhooks_route.create_webhook(body=webhook_body, current_user=current_user, db=db)


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def public_delete_webhook(
    request: Request,
    webhook_id: str,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="webhooks:manage",
    )
    from api.routes import user_webhooks as webhooks_route
    return await webhooks_route.delete_webhook(webhook_id=webhook_id, current_user=current_user, db=db)


@router.post("/webhooks/{webhook_id}/test")
@limiter.limit("10/minute")
async def public_test_webhook(
    request: Request,
    webhook_id: str,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="webhooks:manage",
    )
    from api.routes import user_webhooks as webhooks_route
    return await webhooks_route.test_webhook(webhook_id=webhook_id, current_user=current_user, db=db)


# ── Campaigns & Calendar ───────────────────────────────────────────────────────

@router.get("/campaigns")
@limiter.limit("60/minute")
async def public_list_campaigns(
    request: Request,
    db: DB,
    status: str | None = Query(None),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="posts:read",
    )
    from api.routes import campaigns as campaigns_route
    status_filter = status if isinstance(status, str) else None
    return await campaigns_route.list_campaigns(current_user=current_user, db=db, status=status_filter)


@router.get("/campaigns/{campaign_id}")
@limiter.limit("60/minute")
async def public_get_campaign(
    request: Request,
    campaign_id: str,
    db: DB,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="posts:read",
    )
    from api.routes import campaigns as campaigns_route
    return await campaigns_route.get_campaign_detail(campaign_id=campaign_id, current_user=current_user, db=db)


@router.get("/calendar")
@limiter.limit("60/minute")
async def public_get_calendar(
    request: Request,
    db: DB,
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _token_doc, current_user = await _resolve_public_principal(
        request=request,
        db=db,
        authorization=authorization,
        x_api_key=x_api_key,
        required_scope="posts:read",
    )
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    query: dict[str, Any] = {
        "$or": [{"workspace_id": workspace_id}, {"user_id": current_user["user_id"]}],
        "status": {"$in": ["scheduled", "queued", "published", "partial", "failed"]},
        "deleted_at": {"$exists": False},
    }
    start_str = start_date if isinstance(start_date, str) else None
    end_str = end_date if isinstance(end_date, str) else None
    if start_str or end_str:
        time_filter: dict[str, Any] = {}
        if start_str:
            try:
                time_filter["$gte"] = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            except ValueError:
                pass
        if end_str:
            try:
                time_filter["$lte"] = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except ValueError:
                pass
        if time_filter:
            query["scheduled_time"] = time_filter

    docs = await db.posts.find(query, {"_id": 0}).sort("scheduled_time", 1).to_list(length=200)
    return docs

