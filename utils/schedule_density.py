"""
Phase 10 — Schedule density warnings.
Warns users when they schedule too many posts in a short window,
which can trigger platform rate limiting or shadow-banning.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class DensityWarning:
    platform: str
    window_start: datetime
    window_end: datetime
    post_count: int
    recommended_max: int
    message: str


# Recommended max posts per platform per time window (derived from platform docs)
_PLATFORM_DENSITY_LIMITS: dict[str, dict] = {
    "instagram": {"max_per_hour": 1,  "max_per_day": 4},
    "facebook":  {"max_per_hour": 2,  "max_per_day": 10},
    "twitter":   {"max_per_hour": 5,  "max_per_day": 30},
    "linkedin":  {"max_per_hour": 1,  "max_per_day": 3},
    "tiktok":    {"max_per_hour": 1,  "max_per_day": 5},
    "youtube":   {"max_per_hour": 1,  "max_per_day": 6},
}


async def check_schedule_density(
    db,
    workspace_id: str,
    platforms: list[str],
    proposed_time: datetime,
) -> list[DensityWarning]:
    """
    Check if scheduling a new post at proposed_time would exceed density limits
    for any of the specified platforms.
    Returns a list of DensityWarning objects (empty if all clear).
    """
    warnings: list[DensityWarning] = []

    for platform in platforms:
        limits = _PLATFORM_DENSITY_LIMITS.get(platform.lower())
        if not limits:
            continue

        hour_start = proposed_time - timedelta(hours=1)
        day_start = proposed_time - timedelta(hours=24)

        # Count scheduled + queued posts in hour window
        hour_count = await db.posts.count_documents({
            "workspace_id": workspace_id,
            "platforms": platform,
            "scheduled_time": {"$gte": hour_start, "$lte": proposed_time},
            "status": {"$in": ["scheduled", "queued", "processing", "published"]},
        })

        day_count = await db.posts.count_documents({
            "workspace_id": workspace_id,
            "platforms": platform,
            "scheduled_time": {"$gte": day_start, "$lte": proposed_time},
            "status": {"$in": ["scheduled", "queued", "processing", "published"]},
        })

        if hour_count >= limits["max_per_hour"]:
            warnings.append(DensityWarning(
                platform=platform,
                window_start=hour_start,
                window_end=proposed_time,
                post_count=hour_count + 1,
                recommended_max=limits["max_per_hour"],
                message=(
                    f"{platform}: scheduling {hour_count + 1} posts within 1 hour "
                    f"(recommended max: {limits['max_per_hour']}). "
                    "This may trigger rate limiting or reduced reach."
                ),
            ))
        elif day_count >= limits["max_per_day"]:
            warnings.append(DensityWarning(
                platform=platform,
                window_start=day_start,
                window_end=proposed_time,
                post_count=day_count + 1,
                recommended_max=limits["max_per_day"],
                message=(
                    f"{platform}: scheduling {day_count + 1} posts within 24 hours "
                    f"(recommended max: {limits['max_per_day']}). "
                    "Consider spreading posts across more days."
                ),
            ))

    return warnings
