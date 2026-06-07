"""Composer-side remote media source integrations."""

import base64
import hashlib
import json
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse

from api.deps import CacheRedis, CurrentUser, DB, QueueRedis, require_permission
from api.limiter import limiter
from api.models.media import (
    CanvaAuthUrlResponse,
    CanvaCallbackRequest,
    CanvaCallbackResponse,
    CanvaDesignListResponse,
    CanvaDesignResponse,
    CanvaExportRequest,
    CanvaExportResponse,
    MediaSourceStage,
    MediaStatus,
    RemoteMediaImportRequest,
    RemoteMediaImportResponse,
    RemoteMediaImportResult,
)
from api.routes.upload import (
    _check_queue_depth,
    _check_user_upload_backlog,
    _max_bytes_for_plan,
    _mime_to_ext,
    _raw_storage_key,
    _release_concurrent_slot,
    _reserve_concurrent_upload_slot,
    _safe_filename,
)
from api.task_queue import enqueue_task
from utils.media_source_imports import build_download_url_for_google_photos, get_provider_setup_requirements
from utils.observability import capture_degraded_event, event_log, shorten_provider_error
from utils.redis_resilience import safe_delete, safe_get, safe_setex

logger = logging.getLogger(__name__)
router = APIRouter(tags=["media-sources"])

_UNSPLASH_SEARCH_URL = "https://api.unsplash.com/search/photos"
_CANVA_AUTHORIZE_URL = "https://www.canva.com/api/oauth/authorize"
_CANVA_TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"
_CANVA_DESIGNS_URL = "https://api.canva.com/rest/v1/designs"
_CANVA_EXPORTS_URL = "https://api.canva.com/rest/v1/exports"
_IMPORT_AUTH_TTL_SECONDS = 900
_CANVA_STATE_TTL_SECONDS = 900
_CANVA_SESSION_TTL_SECONDS = 14_400
_CANVA_SCOPES = "design:meta:read design:content:read"
_SUCCESS_POPUP_HTML = """<!doctype html>
<html><body><script>
  (function() {
    if (window.opener) {
      window.opener.postMessage(%s, %s);
    }
    window.close();
  })();
</script></body></html>"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_unsplash_key() -> str | None:
    return (
        os.environ.get("UNSPLASH_ACCESS_KEY")
        or os.environ.get("REACT_APP_UNSPLASH_ACCESS_KEY")
        or os.environ.get("VITE_UNSPLASH_ACCESS_KEY")
    )


def _resolve_frontend_base(request: Request) -> str:
    return (
        request.headers.get("origin")
        or os.environ.get("FRONTEND_URL")
        or "http://localhost:3000"
    ).rstrip("/")


def _resolve_canva_redirect_uri(request: Request) -> str:
    return (
        os.environ.get("CANVA_REDIRECT_URI", "").strip()
        or f"{_external_request_base(request)}/api/media-sources/canva/callback"
    )


def _external_request_base(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")
    return str(request.base_url).rstrip("/")


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _canva_credentials() -> tuple[str, str]:
    client_id = os.environ.get("CANVA_CLIENT_ID", "").strip()
    client_secret = os.environ.get("CANVA_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canva import is not configured. Add CANVA_CLIENT_ID and CANVA_CLIENT_SECRET.",
        )
    return client_id, client_secret


async def _store_import_auth(cache_redis: CacheRedis, item_index: int, bearer_token: str) -> str:
    auth_ref = f"media_source_auth:{uuid.uuid4()}"
    stored = await safe_setex(
        cache_redis,
        auth_ref,
        _IMPORT_AUTH_TTL_SECONDS,
        json.dumps({"type": "bearer", "token": bearer_token, "item_index": item_index}),
        default=True,
        feature="Media source auth store",
    )
    if stored is False:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Temporary import auth store unavailable")
    return auth_ref


async def _track_unsplash_download_if_needed(item, unsplash_key: str | None) -> None:
    if item.provider != "unsplash" or not item.tracking_url or not unsplash_key:
        return
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.get(
                item.tracking_url,
                headers={"Authorization": f"Client-ID {unsplash_key}"},
            )
    except Exception as exc:
        event_log(
            logger,
            "warning",
            "media_source.unsplash_tracking.degraded",
            provider="unsplash",
            provider_error=shorten_provider_error(exc),
            outcome="degraded",
        )


async def _load_canva_session(cache_redis: CacheRedis, session_id: str) -> dict:
    raw = await safe_get(cache_redis, f"canva_import_session:{session_id}", default=None, feature="Canva session read")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Canva session expired. Reconnect Canva.")
    try:
        session = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Invalid Canva session state") from exc
    expires_at = session.get("expires_at")
    if expires_at and datetime.fromisoformat(expires_at) <= _utc_now():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Canva session expired. Reconnect Canva.")
    return session


async def _store_canva_session(cache_redis: CacheRedis, *, user_id: str, tokens: dict) -> CanvaCallbackResponse:
    session_id = str(uuid.uuid4())
    expires_at = _utc_now() + timedelta(seconds=int(tokens.get("expires_in", _CANVA_SESSION_TTL_SECONDS)))
    payload = {
        "user_id": user_id,
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "expires_at": expires_at.isoformat(),
    }
    stored = await safe_setex(
        cache_redis,
        f"canva_import_session:{session_id}",
        _CANVA_SESSION_TTL_SECONDS,
        json.dumps(payload),
        default=True,
        feature="Canva session store",
    )
    if stored is False:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Unable to persist Canva session")
    return CanvaCallbackResponse(session_id=session_id, expires_at=expires_at)


async def _exchange_canva_code(*, code: str, verifier: str, redirect_uri: str) -> dict:
    client_id, client_secret = _canva_credentials()
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            _CANVA_TOKEN_URL,
            data=data,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Canva token exchange failed")
    return response.json()


async def _canva_api_get(session: dict, url: str, *, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params, headers={"Authorization": f"Bearer {session['access_token']}"})
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Canva API request failed")
    return response.json()


async def _canva_api_post(session: dict, url: str, *, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {session['access_token']}"},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Canva API request failed")
    return response.json()


async def _handle_canva_callback(
    *,
    code: str,
    state: str,
    cache_redis: CacheRedis,
) -> CanvaCallbackResponse:
    raw_state = await safe_get(cache_redis, f"canva_import_state:{state}", default=None, feature="Canva state read")
    if not raw_state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired Canva state")
    await safe_delete(cache_redis, f"canva_import_state:{state}", default=0, feature="Canva state consume")
    try:
        state_data = json.loads(raw_state)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Malformed Canva state") from exc

    tokens = await _exchange_canva_code(
        code=code,
        verifier=state_data["code_verifier"],
        redirect_uri=state_data["redirect_uri"],
    )
    return await _store_canva_session(cache_redis, user_id=state_data["user_id"], tokens=tokens)


@router.get(
    "/media-sources/unsplash/search",
    dependencies=[require_permission("media:upload")],
)
@limiter.limit("120/hour")
async def search_unsplash(
    request: Request,
    current_user: CurrentUser,
    q: str = Query(..., min_length=1, max_length=120),
    page: int = Query(1, ge=1, le=20),
):
    unsplash_key = _resolve_unsplash_key()
    if not unsplash_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unsplash is not configured. Add UNSPLASH_ACCESS_KEY on the backend.",
        )

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                _UNSPLASH_SEARCH_URL,
                params={"query": q, "page": page, "per_page": 24},
                headers={"Authorization": f"Client-ID {unsplash_key}"},
            )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        event_log(
            logger,
            "error",
            "media_source.unsplash_search.failed",
            exc_info=exc,
            route="/media-sources/unsplash/search",
            user_id=current_user["user_id"],
            provider_error=shorten_provider_error(exc),
            outcome="failed",
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to search Unsplash") from exc

    results = []
    for photo in payload.get("results", []):
        user = photo.get("user") or {}
        results.append(
            {
                "id": photo.get("id"),
                "description": photo.get("description") or photo.get("alt_description"),
                "thumb": (photo.get("urls") or {}).get("thumb"),
                "small": (photo.get("urls") or {}).get("small"),
                "full": (photo.get("urls") or {}).get("full"),
                "download_url": (photo.get("links") or {}).get("download_location"),
                "photographer_name": user.get("name"),
                "photographer_username": user.get("username"),
                "photographer_profile": (user.get("links") or {}).get("html"),
                "source_attribution": {
                    "provider": "unsplash",
                    "photographer_name": user.get("name"),
                    "photographer_username": user.get("username"),
                    "profile_url": (user.get("links") or {}).get("html"),
                    "photo_url": (photo.get("links") or {}).get("html"),
                },
            }
        )

    return {
        "results": results,
        "page": page,
        "has_more": page < int(payload.get("total_pages") or 0),
        "setup_requirements": get_provider_setup_requirements()["unsplash"],
    }


@router.post(
    "/media-sources/import",
    response_model=RemoteMediaImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[require_permission("media:upload")],
)
async def import_media_sources(
    payload: RemoteMediaImportRequest,
    current_user: CurrentUser,
    db: DB,
    cache_redis: CacheRedis,
    queue_redis: QueueRedis,
):
    user_id = current_user["user_id"]
    plan = current_user.get("plan", "starter")
    subscription_status = current_user.get("subscription_status", "free")
    if subscription_status not in {"active", "free", "grace"}:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Active subscription required to import media")

    await _check_queue_depth(queue_redis)
    await _check_user_upload_backlog(db, user_id, plan)
    max_bytes = _max_bytes_for_plan(plan)
    unsplash_key = _resolve_unsplash_key()

    reserved_slots = 0
    import_results: list[RemoteMediaImportResult] = []
    try:
        for index, item in enumerate(payload.items):
            await _reserve_concurrent_upload_slot(cache_redis, user_id, plan, ttl_seconds=_IMPORT_AUTH_TTL_SECONDS)
            reserved_slots += 1
            await _track_unsplash_download_if_needed(item, unsplash_key)

            auth_ref = None
            if item.auth_bearer_token:
                auth_ref = await _store_import_auth(cache_redis, index, item.auth_bearer_token)

            safe_name = _safe_filename(item.name)
            ext = Path(safe_name).suffix.lower()
            if not ext and item.content_type:
                ext = _mime_to_ext(item.content_type)
            media_job_id = str(uuid.uuid4())
            source_storage_key = _raw_storage_key(user_id, media_job_id, ext or ".bin")
            now = _utc_now()
            asset_doc = {
                "media_id": media_job_id,
                "user_id": user_id,
                "status": MediaStatus.PENDING_UPLOAD,
                "source_stage": MediaSourceStage.FETCHING,
                "mime_type": item.content_type,
                "file_size_bytes": item.file_size_bytes,
                "original_filename": safe_name,
                "source_storage_key": source_storage_key,
                "created_at": now,
                "processed_at": None,
                "error_message": None,
                "source_provider": item.provider,
                "source_item_id": item.source_item_id,
                "source_label": item.source_label or item.name,
                "source_attribution": item.source_attribution,
                "source_download_url": item.download_url,
                "source_auth_ref": auth_ref,
                "max_file_size_bytes": max_bytes,
            }
            await db.media_assets.insert_one(asset_doc)
            enqueue_task(
                "celery_workers.tasks.media.import_remote_media",
                args=[media_job_id, user_id],
                queue="media_processing",
            )
            import_results.append(
                RemoteMediaImportResult(media_job_id=media_job_id, provider=item.provider, name=item.name)
            )
    except Exception:
        for _ in range(reserved_slots):
            await _release_concurrent_slot(cache_redis, user_id)
        raise

    return RemoteMediaImportResponse(imports=import_results)


@router.get(
    "/media-sources/canva/url",
    response_model=CanvaAuthUrlResponse,
    dependencies=[require_permission("media:upload")],
)
async def get_canva_import_url(
    request: Request,
    current_user: CurrentUser,
    cache_redis: CacheRedis,
) -> CanvaAuthUrlResponse:
    client_id, _client_secret = _canva_credentials()
    state = secrets.token_urlsafe(24)
    verifier = _pkce_verifier()
    challenge = _pkce_challenge(verifier)
    redirect_uri = _resolve_canva_redirect_uri(request)
    frontend_base = _resolve_frontend_base(request)
    stored = await safe_setex(
        cache_redis,
        f"canva_import_state:{state}",
        _CANVA_STATE_TTL_SECONDS,
        json.dumps(
            {
                "user_id": current_user["user_id"],
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
                "frontend_base": frontend_base,
            }
        ),
        default=True,
        feature="Canva state store",
    )
    if stored is False:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Unable to persist Canva auth state")

    params = {
        "code_challenge": challenge,
        "code_challenge_method": "s256",
        "scope": _CANVA_SCOPES,
        "response_type": "code",
        "client_id": client_id,
        "state": state,
        "redirect_uri": redirect_uri,
    }
    return CanvaAuthUrlResponse(auth_url=f"{_CANVA_AUTHORIZE_URL}?{urlencode(params)}", state=state)


@router.post(
    "/media-sources/canva/callback",
    response_model=CanvaCallbackResponse,
    dependencies=[require_permission("media:upload")],
)
async def canva_import_callback(
    payload: CanvaCallbackRequest,
    current_user: CurrentUser,
    cache_redis: CacheRedis,
) -> CanvaCallbackResponse:
    return await _handle_canva_callback(code=payload.code, state=payload.state, cache_redis=cache_redis)


@router.get("/media-sources/canva/callback", include_in_schema=False)
async def canva_import_callback_redirect(
    request: Request,
    cache_redis: CacheRedis,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    frontend_base = _resolve_frontend_base(request)
    target_origin = json.dumps(frontend_base)

    if error or not code or not state:
        payload = json.dumps({"type": "canva-import-error", "error": error or "missing_params"})
        return HTMLResponse(_SUCCESS_POPUP_HTML % (payload, target_origin), status_code=200)

    try:
        response = await _handle_canva_callback(code=code, state=state, cache_redis=cache_redis)
        payload = json.dumps(
            {
                "type": "canva-import-connected",
                "session_id": response.session_id,
                "expires_at": response.expires_at.isoformat(),
            }
        )
        return HTMLResponse(_SUCCESS_POPUP_HTML % (payload, target_origin), status_code=200)
    except HTTPException as exc:
        payload = json.dumps({"type": "canva-import-error", "error": exc.detail})
        return HTMLResponse(_SUCCESS_POPUP_HTML % (payload, target_origin), status_code=200)


@router.get(
    "/media-sources/canva/designs",
    response_model=CanvaDesignListResponse,
    dependencies=[require_permission("media:upload")],
)
async def list_canva_designs(
    current_user: CurrentUser,
    cache_redis: CacheRedis,
    session_id: str = Query(...),
    query: str | None = Query(default=None, max_length=255),
    continuation: str | None = Query(default=None),
) -> CanvaDesignListResponse:
    session = await _load_canva_session(cache_redis, session_id)
    if session["user_id"] != current_user["user_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Canva session does not belong to this user")
    payload = await _canva_api_get(
        session,
        _CANVA_DESIGNS_URL,
        params={"query": query, "continuation": continuation, "limit": 25},
    )
    designs = [
        CanvaDesignResponse(
            id=item["id"],
            title=item.get("title"),
            thumbnail_url=((item.get("thumbnail") or {}).get("url")),
            updated_at=datetime.fromtimestamp(item["updated_at"], tz=timezone.utc) if item.get("updated_at") else None,
            edit_url=((item.get("urls") or {}).get("edit_url")),
        )
        for item in payload.get("items", [])
    ]
    return CanvaDesignListResponse(designs=designs, continuation=payload.get("continuation"))


@router.post(
    "/media-sources/canva/exports",
    response_model=CanvaExportResponse,
    dependencies=[require_permission("media:upload")],
)
async def create_canva_export(
    payload: CanvaExportRequest,
    current_user: CurrentUser,
    cache_redis: CacheRedis,
) -> CanvaExportResponse:
    session = await _load_canva_session(cache_redis, payload.session_id)
    if session["user_id"] != current_user["user_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Canva session does not belong to this user")
    request_body = {
        "design_id": payload.design_id,
        "format": {"type": payload.file_type},
    }
    export = await _canva_api_post(session, _CANVA_EXPORTS_URL, payload=request_body)
    job = export.get("job") or export
    return CanvaExportResponse(
        export_id=job["id"],
        status=job["status"],
        download_urls=[url for url in job.get("urls", []) if isinstance(url, str) and url],
    )


@router.get(
    "/media-sources/canva/exports/{export_id}",
    response_model=CanvaExportResponse,
    dependencies=[require_permission("media:upload")],
)
async def get_canva_export(
    export_id: str,
    current_user: CurrentUser,
    cache_redis: CacheRedis,
    session_id: str = Query(...),
) -> CanvaExportResponse:
    session = await _load_canva_session(cache_redis, session_id)
    if session["user_id"] != current_user["user_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Canva session does not belong to this user")
    export = await _canva_api_get(session, f"{_CANVA_EXPORTS_URL}/{export_id}")
    job = export.get("job") or export
    download_urls = [url for url in job.get("urls", []) if isinstance(url, str) and url]
    return CanvaExportResponse(export_id=job["id"], status=job["status"], download_urls=download_urls)
