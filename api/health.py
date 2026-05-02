"""
Phase 1.10 — /health and /ready endpoints.
/health  → liveness probe. ONLY confirms process is alive. Never checks DB/Redis.
/ready   → readiness probe. Returns 200 only when MongoDB AND Redis are connected.
"""
import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.deps import get_firebase_app
from db.mongo import get_client as get_mongo_client
from db.redis_client import get_queue_redis, get_cache_redis
from utils.storage import get_storage_backend, validate_storage_backend_async

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe — always returns 200 if process is running."""
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> JSONResponse:
    """
    Readiness probe.

    Hard dependencies:
      - MongoDB
      - Redis queue (Celery broker path)
      - Firebase Admin SDK
      - Active storage backend

    Degradable dependency:
      - Redis cache

    Returns 200 when hard dependencies are healthy, even if cache Redis is down.
    Cache Redis failures are reported as "degraded" so the API can stay in
    service and rely on graceful fallbacks where implemented.
    """
    checks: dict[str, str] = {}
    hard_ok = True
    degraded = False

    # MongoDB check
    try:
        client = await get_mongo_client()
        await client.admin.command("ping")
        checks["mongodb"] = "ok"
    except Exception as exc:
        logger.error("Readiness check — MongoDB unreachable: %s", exc)
        checks["mongodb"] = "error"
        hard_ok = False

    # Redis queue check
    try:
        r = get_queue_redis()
        await r.ping()
        checks["redis_queue"] = "ok"
    except Exception as exc:
        logger.error("Readiness check — Redis queue unreachable: %s", exc)
        checks["redis_queue"] = "error"
        hard_ok = False

    # Redis cache check
    try:
        r = get_cache_redis()
        await r.ping()
        checks["redis_cache"] = "ok"
    except Exception as exc:
        logger.warning("Readiness check — Redis cache unreachable (degraded mode): %s", exc)
        checks["redis_cache"] = "degraded"
        degraded = True

    # Firebase Admin SDK check
    try:
        get_firebase_app()
        checks["firebase_admin"] = "ok"
    except Exception as exc:
        logger.error("Readiness check — Firebase Admin SDK unavailable: %s", exc)
        checks["firebase_admin"] = "error"
        hard_ok = False

    # Active storage backend check
    try:
        storage_info = await validate_storage_backend_async()
        checks["storage"] = f"ok:{storage_info['backend']}"
    except Exception as exc:
        backend = get_storage_backend()
        if backend == "r2":
            logger.error("Readiness check — R2 storage unavailable: %s", exc)
            checks["storage"] = "error:r2"
            hard_ok = False
        else:
            logger.warning("Readiness check — Firebase storage unavailable (degraded mode): %s", exc)
            checks["storage"] = "degraded:firebase"
            degraded = True

    status_code = 200 if hard_ok else 503
    return JSONResponse(
        content={
            "status": "ready" if hard_ok and not degraded else "degraded" if hard_ok else "not_ready",
            "checks": checks,
        },
        status_code=status_code,
    )
