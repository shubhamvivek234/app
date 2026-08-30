"""
System Health & Scaling Diagnostics API.
Inspects Redis queues, Redis memory, and scheduled post lag to provide real-time scaling alerts.
"""
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict

from fastapi import APIRouter

from api.deps import DB, CacheRedis, QueueRedis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system", tags=["system-diagnostics"])


@router.get("/scaling-alerts")
@router.get("/diagnostics")
async def get_scaling_alerts(
    db: DB,
    queue_redis: QueueRedis,
    cache_redis: CacheRedis,
) -> Dict[str, Any]:
    """
    Real-time scaling diagnostics and alert matrix.
    Inspects:
    1. Celery queue lengths (publish_light, publish_video, default, high_priority, dead_letter)
    2. Redis Memory usage % (used_memory vs maxmemory)
    3. Publishing Lag count (posts scheduled in the past > 45s still in scheduled/queued state)
    4. Actionable recommendations & status ("healthy", "warning", "critical")
    """
    now = datetime.now(timezone.utc)

    # 1. Queue depths
    queues = [
        "high_priority",
        "publish_light",
        "publish_video",
        "default",
        "media_processing",
        "dead_letter",
    ]
    queue_depths = {}
    total_queued = 0
    for q in queues:
        try:
            depth = await queue_redis.llen(q)
            queue_depths[q] = int(depth)
            if q != "dead_letter":
                total_queued += int(depth)
        except Exception:
            queue_depths[q] = 0

    # 2. Redis memory
    redis_memory_info = {
        "used_memory_human": "N/A",
        "maxmemory_human": "N/A",
        "used_percentage": 0.0,
    }
    try:
        info = await cache_redis.info("memory")
        used = int(info.get("used_memory", 0))
        maxm = int(info.get("maxmemory", 0)) or (512 * 1024 * 1024)
        pct = round((used / maxm) * 100, 1) if maxm > 0 else 0.0
        redis_memory_info = {
            "used_memory_human": f"{round(used / (1024 * 1024), 1)} MB",
            "maxmemory_human": f"{round(maxm / (1024 * 1024), 1)} MB",
            "used_percentage": pct,
        }
    except Exception:
        pass

    # 3. Post lag check (posts whose scheduled_time passed > 45s ago but remain in scheduled/queued)
    lag_threshold = now - timedelta(seconds=45)
    lagging_posts_count = 0
    try:
        lagging_posts_count = await db.posts.count_documents(
            {
                "status": {"$in": ["scheduled", "queued"]},
                "scheduled_time": {"$lte": lag_threshold},
                "deleted_at": {"$exists": False},
            }
        )
    except Exception:
        pass

    # 4. Generate Alert Level & Recommendations
    alerts = []
    status_level = "healthy"

    if queue_depths.get("publish_light", 0) > 100:
        status_level = "critical"
        alerts.append({
            "level": "critical",
            "component": "worker_light",
            "message": f"publish_light queue is backed up with {queue_depths['publish_light']} jobs. Increase worker concurrency or add worker nodes.",
        })
    elif queue_depths.get("publish_light", 0) > 30:
        if status_level != "critical":
            status_level = "warning"
        alerts.append({
            "level": "warning",
            "component": "worker_light",
            "message": f"publish_light queue has {queue_depths['publish_light']} jobs waiting. Dynamic autoscaling active.",
        })

    if queue_depths.get("publish_video", 0) > 20:
        status_level = "critical"
        alerts.append({
            "level": "critical",
            "component": "worker_video",
            "message": f"publish_video queue has {queue_depths['publish_video']} video uploads pending. Increase video worker concurrency.",
        })

    if redis_memory_info["used_percentage"] > 85.0:
        status_level = "critical"
        alerts.append({
            "level": "critical",
            "component": "redis_cache",
            "message": f"Redis memory is at {redis_memory_info['used_percentage']}%. Increase Redis maxmemory or purge stale keys.",
        })
    elif redis_memory_info["used_percentage"] > 70.0:
        if status_level != "critical":
            status_level = "warning"
        alerts.append({
            "level": "warning",
            "component": "redis_cache",
            "message": f"Redis memory usage is moderate ({redis_memory_info['used_percentage']}%).",
        })

    if lagging_posts_count > 10:
        status_level = "critical"
        alerts.append({
            "level": "critical",
            "component": "scheduler",
            "message": f"{lagging_posts_count} scheduled posts are experiencing publishing lag (>45s). Check Celery Beat and worker health.",
        })
    elif lagging_posts_count > 0:
        if status_level != "critical":
            status_level = "warning"
        alerts.append({
            "level": "warning",
            "component": "scheduler",
            "message": f"{lagging_posts_count} posts are queued for publishing.",
        })

    if queue_depths.get("dead_letter", 0) > 0:
        alerts.append({
            "level": "info",
            "component": "dead_letter",
            "message": f"{queue_depths['dead_letter']} poison-pill or terminal jobs in dead_letter queue.",
        })

    recommendation = (
        "All systems optimal. Queue depths and memory utilization within normal thresholds."
        if status_level == "healthy"
        else "Review the active scaling alerts above and adjust worker concurrency or resource allocations."
    )

    return {
        "status": status_level,
        "timestamp": now.isoformat(),
        "total_queued_tasks": total_queued,
        "queue_depths": queue_depths,
        "redis_memory": redis_memory_info,
        "lagging_posts_count": lagging_posts_count,
        "alerts": alerts,
        "recommendation": recommendation,
    }
