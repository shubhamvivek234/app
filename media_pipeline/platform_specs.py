"""
Canonical Platform Media Specifications — Single Source of Truth.
Used across upload validation, background processing, and transformation pipelines.
"""
from typing import Any, Dict, List, Optional, Tuple

PLATFORM_SPECS: Dict[str, Dict[str, Any]] = {
    "instagram": {
        "label": "Instagram",
        "max_image_bytes": 30 * 1024 * 1024,        # 30 MB
        "max_video_bytes": 4 * 1024 * 1024 * 1024,   # 4 GB (Reels)
        "max_duration_seconds": 3600,                # 60 min
        "max_width": 1920,
        "allowed_image_types": ["image/jpeg", "image/png"],
        "allowed_video_types": ["video/mp4", "video/quicktime"],
        "aspect_ratios": {
            "Post": {"ratio": 4 / 5, "label": "4:5", "min": 0.8, "max": 1.91},
            "Reel": {"ratio": 9 / 16, "label": "9:16", "min": 0.56, "max": 0.58},
            "Story": {"ratio": 9 / 16, "label": "9:16", "min": 0.56, "max": 0.58},
        },
        "requires_audio": True,                      # Required for Reels
        "supports_hdr": False,
        "caption_limit": 2200,
    },
    "facebook": {
        "label": "Facebook",
        "max_image_bytes": 30 * 1024 * 1024,        # 30 MB
        "max_video_bytes": 4 * 1024 * 1024 * 1024,   # 4 GB (Reels) / 10 GB (Feed)
        "max_duration_seconds": 14400,               # 4 hours
        "max_width": 1920,
        "allowed_image_types": ["image/jpeg", "image/png", "image/gif", "image/webp"],
        "allowed_video_types": ["video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"],
        "aspect_ratios": {
            "Post": {"ratio": 1.0, "label": "1:1", "min": 0.56, "max": 1.91},
            "Reel": {"ratio": 9 / 16, "label": "9:16", "min": 0.56, "max": 0.58},
        },
        "requires_audio": True,
        "supports_hdr": False,
        "caption_limit": 63206,
    },
    "twitter": {
        "label": "Twitter / X",
        "max_image_bytes": 5 * 1024 * 1024,         # 5 MB
        "max_video_bytes": 512 * 1024 * 1024,       # 512 MB
        "max_duration_seconds": 140,                # 2 min 20 sec
        "max_width": 1280,
        "allowed_image_types": ["image/jpeg", "image/png", "image/gif", "image/webp"],
        "allowed_video_types": ["video/mp4", "video/quicktime"],
        "aspect_ratios": {
            "Post": {"ratio": 16 / 9, "label": "16:9", "min": 0.5, "max": 2.39},
        },
        "requires_audio": False,
        "supports_hdr": False,
        "caption_limit": 280,
    },
    "linkedin": {
        "label": "LinkedIn",
        "max_image_bytes": 5 * 1024 * 1024,         # 5 MB
        "max_video_bytes": 5 * 1024 * 1024 * 1024,   # 5 GB
        "max_duration_seconds": 600,                # 10 min
        "max_width": 1920,
        "allowed_image_types": ["image/jpeg", "image/png", "image/gif"],
        "allowed_video_types": ["video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"],
        "aspect_ratios": {
            "Post": {"ratio": 1.91, "label": "1.91:1", "min": 0.56, "max": 2.4},
        },
        "requires_audio": False,
        "supports_hdr": False,
        "caption_limit": 3000,
    },
    "tiktok": {
        "label": "TikTok",
        "max_image_bytes": 20 * 1024 * 1024,        # 20 MB
        "max_video_bytes": 500 * 1024 * 1024,       # 500 MB (web)
        "max_duration_seconds": 3600,               # 60 min
        "max_width": 1920,
        "allowed_image_types": ["image/jpeg", "image/png", "image/webp"],
        "allowed_video_types": ["video/mp4", "video/quicktime", "video/webm"],
        "aspect_ratios": {
            "Post": {"ratio": 9 / 16, "label": "9:16", "min": 0.54, "max": 0.60},
        },
        "requires_audio": True,
        "supports_hdr": False,
        "caption_limit": 2200,
    },
    "youtube": {
        "label": "YouTube",
        "max_image_bytes": 2 * 1024 * 1024,         # 2 MB thumbnail
        "max_video_bytes": 256 * 1024 * 1024 * 1024,# 256 GB
        "max_duration_seconds": 12 * 3600,          # 12 hours
        "max_width": 3840,
        "allowed_image_types": ["image/jpeg", "image/png"],
        "allowed_video_types": ["video/mp4", "video/quicktime", "video/x-msvideo", "video/webm", "video/mpeg"],
        "aspect_ratios": {
            "Post": {"ratio": 16 / 9, "label": "16:9", "min": 0.5, "max": 2.5},
            "Shorts": {"ratio": 9 / 16, "label": "9:16", "min": 0.54, "max": 0.60},
        },
        "requires_audio": False,
        "supports_hdr": True,
        "caption_limit": 5000,
    },
    "threads": {
        "label": "Threads",
        "max_image_bytes": 8 * 1024 * 1024,         # 8 MB
        "max_video_bytes": 1024 * 1024 * 1024,      # 1 GB
        "max_duration_seconds": 300,                # 5 min
        "max_width": 1920,
        "allowed_image_types": ["image/jpeg", "image/png", "image/webp"],
        "allowed_video_types": ["video/mp4", "video/quicktime"],
        "aspect_ratios": {
            "Post": {"ratio": 1.0, "label": "1:1", "min": 0.56, "max": 1.91},
        },
        "requires_audio": False,
        "supports_hdr": False,
        "caption_limit": 500,
    },
    "pinterest": {
        "label": "Pinterest",
        "max_image_bytes": 20 * 1024 * 1024,        # 20 MB
        "max_video_bytes": 2 * 1024 * 1024 * 1024,  # 2 GB
        "max_duration_seconds": 900,                # 15 min
        "max_width": 1920,
        "allowed_image_types": ["image/jpeg", "image/png", "image/webp", "image/gif"],
        "allowed_video_types": ["video/mp4", "video/quicktime", "video/x-m4v"],
        "aspect_ratios": {
            "Post": {"ratio": 2 / 3, "label": "2:3", "min": 0.5, "max": 1.5},
        },
        "requires_audio": False,
        "supports_hdr": False,
        "caption_limit": 500,
    },
    "bluesky": {
        "label": "Bluesky",
        "max_image_bytes": 8 * 1024 * 1024,         # 8 MB
        "max_video_bytes": 100 * 1024 * 1024,       # 100 MB
        "max_duration_seconds": 60,                 # 60 sec
        "max_width": 2000,
        "allowed_image_types": ["image/jpeg", "image/png", "image/webp"],
        "allowed_video_types": ["video/mp4"],
        "aspect_ratios": {
            "Post": {"ratio": 1.0, "label": "1:1", "min": 0.5, "max": 2.0},
        },
        "requires_audio": False,
        "supports_hdr": False,
        "caption_limit": 300,
    },
    "google_business": {
        "label": "Google Business Profile",
        "max_image_bytes": 10 * 1024 * 1024,        # 10 MB
        "max_video_bytes": 75 * 1024 * 1024,        # 75 MB
        "max_duration_seconds": 30,                 # 30 sec
        "max_width": 1920,
        "allowed_image_types": ["image/jpeg", "image/png"],
        "allowed_video_types": ["video/mp4", "video/quicktime"],
        "aspect_ratios": {
            "Post": {"ratio": 4 / 3, "label": "4:3", "min": 0.7, "max": 1.8},
        },
        "requires_audio": False,
        "supports_hdr": False,
        "caption_limit": 1500,
    },
}

# Synonyms/aliases
PLATFORM_SPECS["gbp"] = PLATFORM_SPECS["google_business"]


def get_platform_spec(platform: str) -> Dict[str, Any]:
    """Return spec dictionary for platform, defaulting to generic fallback."""
    key = platform.lower().strip() if platform else ""
    return PLATFORM_SPECS.get(key, {
        "label": platform or "Generic",
        "max_image_bytes": 10 * 1024 * 1024,
        "max_video_bytes": 500 * 1024 * 1024,
        "max_duration_seconds": 600,
        "max_width": 1920,
        "allowed_image_types": ["image/jpeg", "image/png"],
        "allowed_video_types": ["video/mp4", "video/quicktime"],
        "aspect_ratios": {},
        "requires_audio": False,
        "supports_hdr": False,
        "caption_limit": 2200,
    })


def is_vertical_required(platform: str, post_format: str = "Post") -> bool:
    """Check if 9:16 vertical orientation is required for this platform/format."""
    p = platform.lower().strip()
    if p == "tiktok":
        return True
    if p == "instagram" and post_format.lower() in ("reel", "story", "instagram_reel", "instagram_story"):
        return True
    if p == "youtube" and post_format.lower() in ("short", "shorts"):
        return True
    return False


def get_recommended_aspect_ratio(platform: str, post_format: str = "Post") -> Tuple[int, int]:
    """Returns (width_ratio, height_ratio), e.g. (9, 16) or (1, 1)."""
    spec = get_platform_spec(platform)
    ratios = spec.get("aspect_ratios", {})
    entry = ratios.get(post_format) or ratios.get("Post")
    if entry and entry.get("label") == "9:16":
        return (9, 16)
    if entry and entry.get("label") == "4:5":
        return (4, 5)
    if entry and entry.get("label") == "1:1":
        return (1, 1)
    if entry and entry.get("label") == "16:9":
        return (16, 9)
    if entry and entry.get("label") == "2:3":
        return (2, 3)
    return (1, 1)


def get_max_media_size(platform: str, media_type: str) -> int:
    """Return max allowed bytes for media_type ('image' or 'video')."""
    spec = get_platform_spec(platform)
    if media_type == "video":
        return spec.get("max_video_bytes", 500 * 1024 * 1024)
    return spec.get("max_image_bytes", 10 * 1024 * 1024)
