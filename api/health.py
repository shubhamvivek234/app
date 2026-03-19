"""
Phase 1.10 — /health and /ready endpoints.
/health  → liveness probe. ONLY confirms process is alive. Never checks DB/Redis.
/ready   → readiness probe. Returns 200 only when MongoDB AND Redis are connected.
"""
import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from db.mongo import get_client as get_mongo_client
from db.redis_client import get_queue_redis, get_cache_redis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe — always returns 200 if process is running."""
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> JSONResponse:
    """
    Readiness probe — returns 200 only if both MongoDB and Redis are reachable.
    Returns 503 if either dependency is down (Kubernetes will stop sending traffic).
    """
    checks: dict[str, str] = {}
    all_ok = True

    # MongoDB check
    try:
        client = await get_mongo_client()
        await client.admin.command("ping")
        checks["mongodb"] = "ok"
    except Exception as exc:
        logger.error("Readiness check — MongoDB unreachable: %s", exc)
        checks["mongodb"] = "error"
        all_ok = False

    # Redis queue check
    try:
        r = get_queue_redis()
        await r.ping()
        checks["redis_queue"] = "ok"
    except Exception as exc:
        logger.error("Readiness check — Redis queue unreachable: %s", exc)
        checks["redis_queue"] = "error"
        all_ok = False

    # Redis cache check
    try:
        r = get_cache_redis()
        await r.ping()
        checks["redis_cache"] = "ok"
    except Exception as exc:
        logger.error("Readiness check — Redis cache unreachable: %s", exc)
        checks["redis_cache"] = "error"
        all_ok = False

    status_code = 200 if all_ok else 503
    return JSONResponse(
        content={"status": "ready" if all_ok else "not_ready", "checks": checks},
        status_code=status_code,
    )
