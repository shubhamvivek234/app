"""
Phase 9.5.3 -- Cloudflare Edge Caching Configuration.

Defines cache rules, Cache-Control headers, edge TTL settings,
purge helpers, and regional routing hints for multi-region deployments.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CLOUDFLARE_API_URL = "https://api.cloudflare.com/client/v4"
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_ZONE_ID = os.environ.get("CLOUDFLARE_ZONE_ID", "")


# ---------------------------------------------------------------------------
# Content Types and TTL Settings
# ---------------------------------------------------------------------------

class ContentCategory(str, Enum):
    THUMBNAIL = "thumbnail"
    PROFILE_IMAGE = "profile_image"
    MEDIA = "media"
    API_RESPONSE = "api_response"
    STATIC_ASSET = "static_asset"


@dataclass(frozen=True)
class CacheRule:
    """Immutable cache rule for a content category."""

    category: ContentCategory
    edge_ttl_seconds: int
    browser_ttl_seconds: int
    cache_control: str
    file_extensions: tuple[str, ...] = ()
    path_patterns: tuple[str, ...] = ()
    stale_while_revalidate: int = 0
    stale_if_error: int = 0


# Edge TTL settings per content type
CACHE_RULES: dict[ContentCategory, CacheRule] = {
    ContentCategory.THUMBNAIL: CacheRule(
        category=ContentCategory.THUMBNAIL,
        edge_ttl_seconds=7 * 86400,      # 7 days
        browser_ttl_seconds=86400,        # 1 day
        cache_control="public, max-age=86400, s-maxage=604800",
        file_extensions=(".jpg", ".jpeg", ".png", ".webp"),
        path_patterns=("/media/thumbnails/*", "/thumbs/*"),
        stale_while_revalidate=3600,
        stale_if_error=86400,
    ),
    ContentCategory.PROFILE_IMAGE: CacheRule(
        category=ContentCategory.PROFILE_IMAGE,
        edge_ttl_seconds=7 * 86400,      # 7 days
        browser_ttl_seconds=3600,         # 1 hour (may change more often)
        cache_control="public, max-age=3600, s-maxage=604800",
        file_extensions=(".jpg", ".jpeg", ".png", ".webp"),
        path_patterns=("/avatars/*", "/profiles/*/image"),
        stale_while_revalidate=3600,
        stale_if_error=86400,
    ),
    ContentCategory.MEDIA: CacheRule(
        category=ContentCategory.MEDIA,
        edge_ttl_seconds=30 * 86400,     # 30 days
        browser_ttl_seconds=7 * 86400,   # 7 days
        cache_control="public, max-age=604800, s-maxage=2592000",
        file_extensions=(".mp4", ".mov", ".avi", ".gif", ".webm"),
        path_patterns=("/media/uploads/*", "/media/processed/*"),
        stale_while_revalidate=86400,
        stale_if_error=7 * 86400,
    ),
    ContentCategory.API_RESPONSE: CacheRule(
        category=ContentCategory.API_RESPONSE,
        edge_ttl_seconds=0,              # no-cache
        browser_ttl_seconds=0,
        cache_control="no-store, no-cache, must-revalidate",
        path_patterns=("/api/*",),
    ),
    ContentCategory.STATIC_ASSET: CacheRule(
        category=ContentCategory.STATIC_ASSET,
        edge_ttl_seconds=30 * 86400,     # 30 days
        browser_ttl_seconds=7 * 86400,   # 7 days
        cache_control="public, max-age=604800, s-maxage=2592000, immutable",
        file_extensions=(".js", ".css", ".woff2", ".woff", ".ttf", ".svg"),
        path_patterns=("/static/*", "/_next/static/*"),
        stale_while_revalidate=86400,
    ),
}


# ---------------------------------------------------------------------------
# Cache-Control Header Generator
# ---------------------------------------------------------------------------

def generate_cache_headers(category: ContentCategory) -> dict[str, str]:
    """
    Generate HTTP Cache-Control headers for a given content category.

    Returns a dict of headers suitable for adding to an HTTP response.
    """
    rule = CACHE_RULES.get(category)
    if rule is None:
        return {"Cache-Control": "no-store"}

    headers: dict[str, str] = {"Cache-Control": rule.cache_control}

    if rule.stale_while_revalidate > 0:
        headers["Cache-Control"] += f", stale-while-revalidate={rule.stale_while_revalidate}"

    if rule.stale_if_error > 0:
        headers["Cache-Control"] += f", stale-if-error={rule.stale_if_error}"

    # Cloudflare-specific edge TTL override
    if rule.edge_ttl_seconds > 0:
        headers["CDN-Cache-Control"] = f"max-age={rule.edge_ttl_seconds}"

    return headers


def get_cache_rule_for_path(path: str) -> CacheRule | None:
    """Match a request path to a cache rule. Returns None if no match."""
    for rule in CACHE_RULES.values():
        for pattern in rule.path_patterns:
            # Simple glob matching: "/media/thumbnails/*" matches "/media/thumbnails/abc.jpg"
            if pattern.endswith("/*"):
                prefix = pattern[:-2]
                if path.startswith(prefix):
                    return rule
            elif path == pattern:
                return rule

        # Match by file extension
        for ext in rule.file_extensions:
            if path.endswith(ext):
                return rule

    return None


# ---------------------------------------------------------------------------
# Purge Helpers
# ---------------------------------------------------------------------------

async def _cloudflare_request(
    method: str,
    endpoint: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make an authenticated request to the Cloudflare API."""
    if not CLOUDFLARE_API_TOKEN or not CLOUDFLARE_ZONE_ID:
        raise EnvironmentError(
            "CLOUDFLARE_API_TOKEN and CLOUDFLARE_ZONE_ID must be set"
        )

    url = f"{CLOUDFLARE_API_URL}/zones/{CLOUDFLARE_ZONE_ID}{endpoint}"
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(method, url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()


async def purge_by_urls(urls: list[str]) -> dict[str, Any]:
    """
    Purge specific URLs from the Cloudflare edge cache.

    Cloudflare supports up to 30 URLs per purge request.
    """
    if not urls:
        return {"success": True, "purged": 0}

    results: list[dict[str, Any]] = []
    # Cloudflare limit: 30 URLs per request
    batch_size = 30
    for i in range(0, len(urls), batch_size):
        batch = urls[i : i + batch_size]
        result = await _cloudflare_request(
            "POST", "/purge_cache", {"files": batch}
        )
        results.append(result)

    return {
        "success": all(r.get("success") for r in results),
        "purged": len(urls),
        "batches": len(results),
    }


async def purge_by_tags(tags: list[str]) -> dict[str, Any]:
    """
    Purge cache entries by Cache-Tag header values.

    Requires Cloudflare Enterprise plan.
    """
    if not tags:
        return {"success": True, "purged_tags": 0}

    result = await _cloudflare_request(
        "POST", "/purge_cache", {"tags": tags}
    )
    return {
        "success": result.get("success", False),
        "purged_tags": len(tags),
    }


async def purge_all() -> dict[str, Any]:
    """Purge the entire Cloudflare edge cache for the zone. Use sparingly."""
    logger.warning("Purging ALL cache for zone %s", CLOUDFLARE_ZONE_ID)
    result = await _cloudflare_request(
        "POST", "/purge_cache", {"purge_everything": True}
    )
    return {"success": result.get("success", False)}


# ---------------------------------------------------------------------------
# Regional Routing Hints
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegionConfig:
    """Immutable configuration for a deployment region."""

    region_code: str
    display_name: str
    origin_url: str
    gcs_bucket: str
    priority: int = 0  # lower = higher priority for failover


REGIONAL_CONFIGS: tuple[RegionConfig, ...] = (
    RegionConfig(
        region_code="us-central1",
        display_name="US Central (Iowa)",
        origin_url="https://us-central1-socialentangler.cloudfunctions.net",
        gcs_bucket="se-media-us-central1",
        priority=0,
    ),
    RegionConfig(
        region_code="europe-west1",
        display_name="Europe West (Belgium)",
        origin_url="https://europe-west1-socialentangler.cloudfunctions.net",
        gcs_bucket="se-media-europe-west1",
        priority=1,
    ),
    RegionConfig(
        region_code="asia-east1",
        display_name="Asia East (Taiwan)",
        origin_url="https://asia-east1-socialentangler.cloudfunctions.net",
        gcs_bucket="se-media-asia-east1",
        priority=2,
    ),
)


def get_nearest_region(client_region: str | None = None) -> RegionConfig:
    """
    Return the best region config based on client region hint.

    Falls back to the highest-priority (lowest number) region.
    """
    if client_region:
        region_map = {
            # Map Cloudflare colo regions to our deployment regions
            "NA": "us-central1",     # North America
            "EU": "europe-west1",    # Europe
            "AS": "asia-east1",      # Asia
            "OC": "asia-east1",      # Oceania -> Asia fallback
            "SA": "us-central1",     # South America -> US fallback
            "AF": "europe-west1",    # Africa -> Europe fallback
        }
        target = region_map.get(client_region.upper())
        if target:
            for cfg in REGIONAL_CONFIGS:
                if cfg.region_code == target:
                    return cfg

    # Default to highest priority
    return min(REGIONAL_CONFIGS, key=lambda r: r.priority)
