"""
Viral Auto-Plug task.
Monitors published posts that have auto-plug enabled. When engagement (e.g. likes) crosses
the user-configured threshold, automatically publishes a follow-up reply/comment with the plug/CTA.
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from db.mongo import get_client
from utils.first_comment import post_first_comment
from utils.notifications import emit_notification
from utils.observability import event_log

logger = logging.getLogger(__name__)

# Register 10-minute periodic check in Celery Beat
celery_app.conf.beat_schedule.update({
    "check-viral-auto-plugs": {
        "task": "celery_workers.tasks.auto_plug.check_and_trigger_auto_plugs",
        "schedule": 10 * 60,  # every 10 minutes
        "options": {"queue": "default"},
    },
})


@celery_app.task(name="celery_workers.tasks.auto_plug.check_and_trigger_auto_plugs")
def check_and_trigger_auto_plugs() -> dict:
    """Periodic task: scan eligible posts with active auto-plugs and trigger comments if viral."""
    return run_async(_async_check_and_trigger_auto_plugs())


async def _async_check_and_trigger_auto_plugs() -> dict:
    from celery_workers.tasks.analytics import _fetch_platform_metrics

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    # Find published posts with pending auto-plug within the last 7 days
    cursor = db.posts.find(
        {
            "status": "published",
            "auto_plug.enabled": True,
            "auto_plug.executed": False,
            "$or": [
                {"published_at": {"$gte": seven_days_ago}},
                {"updated_at": {"$gte": seven_days_ago}},
            ],
        },
        limit=200,
    )

    checked = 0
    triggered = 0
    failed = 0

    async for post in cursor:
        checked += 1
        post_id = post.get("id")
        user_id = post.get("user_id")
        workspace_id = post.get("workspace_id")
        auto_plug = post.get("auto_plug") or {}
        trigger_metric = auto_plug.get("trigger_metric", "likes")
        threshold = int(auto_plug.get("threshold", 50))
        plug_content = (auto_plug.get("content") or "").strip()

        if not plug_content:
            await db.posts.update_one(
                {"id": post_id},
                {"$set": {"auto_plug.status": "skipped", "auto_plug.error": "Empty plug content"}},
            )
            continue

        platform_results = post.get("platform_results") or {}
        publish_targets = post.get("publish_targets") or []

        for platform, pres in platform_results.items():
            if pres.get("status") not in ("published", "success"):
                continue

            platform_post_id = pres.get("platform_post_id")
            if not platform_post_id:
                continue

            # Find matching account
            account = None
            account_id = None
            for target in publish_targets:
                if target.get("platform") == platform:
                    account_id = target.get("account_id")
                    break

            if account_id:
                account = await db.social_accounts.find_one(
                    {"account_id": account_id},
                    {"_id": 0},
                )
            if not account:
                account = await db.social_accounts.find_one(
                    {
                        "$or": [{"workspace_id": workspace_id}, {"user_id": user_id}],
                        "platform": platform,
                        "is_active": True,
                    },
                    {"_id": 0},
                )

            if not account:
                continue

            # Fetch live metrics
            try:
                metrics = await _fetch_platform_metrics(db, platform, platform_post_id, workspace_id)
            except Exception as exc:
                logger.warning("Failed to fetch metrics for auto_plug on post %s: %s", post_id, exc)
                metrics = None

            if not metrics or not isinstance(metrics, dict):
                continue

            current_count = int(metrics.get(trigger_metric) or metrics.get("likes") or 0)
            if current_count >= threshold:
                # Post the auto-plug comment!
                logger.info(
                    "Auto-plug triggered for post %s on %s! Threshold: %d, Current: %d",
                    post_id,
                    platform,
                    threshold,
                    current_count,
                )
                try:
                    res = await post_first_comment(
                        platform=platform,
                        platform_post_id=platform_post_id,
                        first_comment_text=plug_content,
                        account=account,
                    )
                except Exception as exc:
                    res = {"status": "failed", "error": str(exc)}

                if res.get("status") == "published":
                    triggered += 1
                    comment_id = res.get("comment_id")
                    await db.posts.update_one(
                        {"id": post_id},
                        {
                            "$set": {
                                "auto_plug.executed": True,
                                "auto_plug.executed_at": now,
                                "auto_plug.status": "triggered",
                                "auto_plug.comment_id": comment_id,
                                "auto_plug.triggered_metric_value": current_count,
                            },
                        },
                    )
                    event_log(
                        logger,
                        "info",
                        "auto_plug.executed",
                        post_id=post_id,
                        platform=platform,
                        threshold=threshold,
                        metric_value=current_count,
                        comment_id=comment_id,
                    )

                    # Notify user
                    try:
                        await emit_notification(
                            db,
                            user_id=user_id,
                            notification_type="auto_plug.triggered",
                            title="🚀 Viral Auto-Plug Published!",
                            message=(
                                f"Your post on {platform.capitalize()} reached {current_count} {trigger_metric}! "
                                f"Your viral auto-plug comment was automatically posted."
                            ),
                            severity="info",
                            target_path=f"/posts/{post_id}",
                        )
                    except Exception as notif_exc:
                        logger.warning("Failed to emit notification for auto_plug on post %s: %s", post_id, notif_exc)

                    # Stop checking other platforms for this post once plugged
                    break
                else:
                    failed += 1
                    error_msg = res.get("error") or "Comment publication failed"
                    await db.posts.update_one(
                        {"id": post_id},
                        {
                            "$set": {
                                "auto_plug.status": "failed",
                                "auto_plug.error": error_msg,
                                "auto_plug.last_attempt_at": now,
                            }
                        },
                    )

    logger.info(
        "auto_plug: checked=%d, triggered=%d, failed=%d",
        checked,
        triggered,
        failed,
    )
    return {"checked": checked, "triggered": triggered, "failed": failed}
