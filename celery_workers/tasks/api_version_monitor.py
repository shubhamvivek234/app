"""
Phase 10.2 — Platform API version monitoring.

Daily Beat task that verifies each social platform's API is still
responding at the expected version.  Logs warnings on deprecation
headers or version mismatches and stores last_checked timestamps
in Redis per platform.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx

from celery_workers.celery_app import celery_app
from db.redis_client import get_cache_redis

logger = logging.getLogger(__name__)

# ── Current API versions used by SocialEntangler ─────────────────────────────

_PLATFORM_API_VERSIONS: dict[str, dict] = {
    "instagram": {
        "version": "v19.0",
        "health_url": "https://graph.facebook.com/v19.0/me",
        "deprecation_header": "facebook-api-version",
        "docs_url": "https://developers.facebook.com/docs/instagram-api",
    },
    "facebook": {
        "version": "v19.0",
        "health_url": "https://graph.facebook.com/v19.0/me",
        "deprecation_header": "facebook-api-version",
        "docs_url": "https://developers.facebook.com/docs/graph-api",
    },
    "youtube": {
        "version": "v3",
        "health_url": "https://www.googleapis.com/youtube/v3/videos?part=id&id=dQw4w9WgXcQ",
        "deprecation_header": "x-goog-api-version",
        "docs_url": "https://developers.google.com/youtube/v3",
    },
    "twitter": {
        "version": "v2",
        "health_url": "https://api.twitter.com/2/openapi.json",
        "deprecation_header": "x-api-version",
        "docs_url": "https://developer.twitter.com/en/docs/twitter-api",
    },
    "linkedin": {
        "version": "v2",
        "health_url": "https://api.linkedin.com/v2/me",
        "deprecation_header": "x-li-api-version",
        "docs_url": "https://learn.microsoft.com/en-us/linkedin/",
    },
    "tiktok": {
        "version": "v2",
        "health_url": "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
        "deprecation_header": "x-tt-api-version",
        "docs_url": "https://developers.tiktok.com/doc/content-posting-api",
    },
}

_REDIS_KEY_PREFIX = "api_version_check"

# Standard deprecation/sunset header names across platforms
_DEPRECATION_HEADERS = ("deprecation", "sunset", "x-api-deprecation-notice")


# ── Task ─────────────────────────────────────────────────────────────────────

@celery_app.task(
    name="celery_workers.tasks.api_version_monitor.check_platform_api_versions",
    bind=True,
    acks_late=True,
    max_retries=2,
    default_retry_delay=600,
)
def check_platform_api_versions(self) -> dict:
    """Daily check: verify platform APIs are responding and not deprecated."""
    return asyncio.get_event_loop().run_until_complete(_async_check())


async def _async_check() -> dict:
    cache_redis = get_cache_redis()
    now = datetime.now(timezone.utc)
    results: dict[str, dict] = {}

    async with httpx.AsyncClient(timeout=15) as client:
        for platform, config in _PLATFORM_API_VERSIONS.items():
            result = await _check_single_platform(client, platform, config, now)
            results[platform] = result

            # Store per-platform last_checked timestamp in Redis (48h TTL)
            try:
                await cache_redis.setex(
                    f"{_REDIS_KEY_PREFIX}:{platform}:last_checked",
                    48 * 3600,
                    now.isoformat(),
                )
                await cache_redis.setex(
                    f"{_REDIS_KEY_PREFIX}:{platform}:status",
                    48 * 3600,
                    result["status"],
                )
            except Exception as exc:
                logger.warning(
                    "Failed to write Redis key for %s: %s", platform, exc
                )

    # Identify platforms with issues
    issues = {
        p: r
        for p, r in results.items()
        if r.get("status") in ("deprecated", "degraded", "version_mismatch", "timeout", "error")
    }

    healthy = sum(1 for r in results.values() if r["status"] == "ok")
    summary = {
        "checked_at": now.isoformat(),
        "total": len(results),
        "healthy": healthy,
        "issues": len(issues),
        "platforms": results,
    }

    if issues:
        logger.warning(
            "API version monitor: %d platforms with issues: %s",
            len(issues),
            list(issues.keys()),
        )
        _send_alert(issues)

    logger.info("API version monitor: checked %d platforms", len(results))
    return summary


async def _check_single_platform(
    client: httpx.AsyncClient,
    platform: str,
    config: dict,
    now: datetime,
) -> dict:
    """
    Perform a lightweight health-check for one platform.
    401/403 is expected (no token) — we only care about 5xx and deprecation signals.
    """
    warnings: list[str] = []

    try:
        resp = await client.get(config["health_url"])
        status_code = resp.status_code

        # Check for deprecation/sunset headers
        for header_name in _DEPRECATION_HEADERS:
            value = resp.headers.get(header_name)
            if value:
                warnings.append(f"Deprecation header '{header_name}': {value}")
                logger.warning(
                    "API version monitor: %s returned deprecation header %s=%s",
                    platform,
                    header_name,
                    value,
                )

        # Check API version from platform-specific response header
        deprecation_header_key = config.get("deprecation_header", "")
        if deprecation_header_key:
            returned_version = resp.headers.get(deprecation_header_key, "")
            if returned_version and config["version"] not in returned_version:
                warnings.append(
                    f"Version mismatch: expected '{config['version']}', "
                    f"got '{returned_version}'"
                )
                logger.warning(
                    "API version monitor: %s expected %s but got %s",
                    platform,
                    config["version"],
                    returned_version,
                )

        # Determine status
        if any("Deprecation header" in w for w in warnings):
            status_label = "deprecated"
        elif any("Version mismatch" in w for w in warnings):
            status_label = "version_mismatch"
        elif status_code >= 500:
            status_label = "degraded"
            logger.error(
                "API version monitor: %s returned %d — platform may be down",
                platform,
                status_code,
            )
        else:
            status_label = "ok"

        return {
            "status": status_label,
            "http_status": status_code,
            "configured_version": config["version"],
            "warnings": warnings,
            "checked_at": now.isoformat(),
        }

    except httpx.TimeoutException:
        logger.warning("API version monitor: %s timed out", platform)
        return {
            "status": "timeout",
            "http_status": None,
            "configured_version": config["version"],
            "warnings": ["Timeout after 15s"],
            "checked_at": now.isoformat(),
        }
    except Exception as exc:
        logger.error("API version monitor: %s check failed: %s", platform, exc)
        return {
            "status": "error",
            "http_status": None,
            "configured_version": config["version"],
            "warnings": [str(exc)],
            "checked_at": now.isoformat(),
        }


def _send_alert(issues: dict[str, dict]) -> None:
    """Send notification when platform APIs show deprecation or degradation."""
    try:
        from celery_workers.tasks.media import send_notification

        platform_names = list(issues.keys())
        send_notification.delay(
            ",".join(platform_names),
            "api_version_degradation",
        )
        logger.info(
            "API version alert sent for platforms: %s", platform_names
        )
    except Exception as exc:
        logger.warning("Failed to send API version alert: %s", exc)
