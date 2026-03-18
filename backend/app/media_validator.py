"""
Media validation — Stage 2.4
Validates uploaded files before storing them.
"""
import os
import subprocess
from pathlib import Path
from typing import Optional

# ── Platform Limits ───────────────────────────────────────────────────────────
PLATFORM_LIMITS = {
    "instagram": {
        "image": {"max_size_mb": 8,  "formats": {"jpg", "jpeg", "png", "webp"},         "max_w": 1080, "max_h": 1350},
        "video": {"max_size_mb": 100, "formats": {"mp4", "mov"},                          "max_duration_s": 60},
    },
    "facebook": {
        "image": {"max_size_mb": 10, "formats": {"jpg", "jpeg", "png", "gif", "webp"},   "max_w": 2048, "max_h": 2048},
        "video": {"max_size_mb": 4096, "formats": {"mp4", "mov", "avi"},                  "max_duration_s": 14400},
    },
    "youtube":  {
        "video": {"max_size_mb": 128000, "formats": {"mp4", "mov", "avi", "mkv", "wmv"}, "max_duration_s": 43200},
    },
    "twitter":  {
        "image": {"max_size_mb": 5,  "formats": {"jpg", "jpeg", "png", "gif", "webp"},   "max_w": 4096, "max_h": 4096},
        "video": {"max_size_mb": 512, "formats": {"mp4", "mov"},                          "max_duration_s": 140},
    },
    "tiktok":   {
        "video": {"max_size_mb": 287, "formats": {"mp4", "webm", "mov"},                 "max_duration_s": 600},
    },
    "linkedin": {
        "image": {"max_size_mb": 5,  "formats": {"jpg", "jpeg", "png", "gif"},           "max_w": 7680, "max_h": 4320},
        "video": {"max_size_mb": 5120, "formats": {"mp4", "mov", "avi"},                  "max_duration_s": 600},
    },
}

# Global defaults
DEFAULT_MAX_IMAGE_MB = 10
DEFAULT_MAX_VIDEO_MB = 500
ALLOWED_IMAGE_FORMATS = {"jpg", "jpeg", "png", "gif", "webp", "bmp"}
ALLOWED_VIDEO_FORMATS = {"mp4", "mov", "avi", "mkv", "wmv", "webm", "m4v"}


class MediaValidationError(ValueError):
    def __init__(self, message: str, error_code: str = "EC5:INVALID_MEDIA_FORMAT"):
        super().__init__(message)
        self.error_code = error_code


def get_file_extension(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower()


def validate_file_size(file_size_bytes: int, media_type: str, platform: Optional[str] = None) -> None:
    """Raise MediaValidationError if file exceeds size limits."""
    size_mb = file_size_bytes / (1024 * 1024)

    if platform and platform in PLATFORM_LIMITS:
        limits = PLATFORM_LIMITS[platform].get(media_type, {})
        max_mb = limits.get("max_size_mb")
        if max_mb and size_mb > max_mb:
            raise MediaValidationError(
                f"File size {size_mb:.1f}MB exceeds {platform} limit of {max_mb}MB for {media_type}",
                error_code="EC4:MEDIA_TOO_LARGE"
            )
    else:
        limit = DEFAULT_MAX_VIDEO_MB if media_type == "video" else DEFAULT_MAX_IMAGE_MB
        if size_mb > limit:
            raise MediaValidationError(
                f"File size {size_mb:.1f}MB exceeds {limit}MB limit",
                error_code="EC4:MEDIA_TOO_LARGE"
            )


def validate_file_format(filename: str, media_type: str) -> str:
    """Validate file format. Returns the extension."""
    ext = get_file_extension(filename)
    allowed = ALLOWED_VIDEO_FORMATS if media_type == "video" else ALLOWED_IMAGE_FORMATS
    if ext not in allowed:
        raise MediaValidationError(
            f"File format '.{ext}' is not supported for {media_type}. "
            f"Allowed: {', '.join(sorted(allowed))}",
            error_code="EC5:INVALID_MEDIA_FORMAT"
        )
    return ext


def detect_media_type(filename: str) -> str:
    """Detect image or video from extension."""
    ext = get_file_extension(filename)
    if ext in ALLOWED_VIDEO_FORMATS:
        return "video"
    return "image"


def get_video_duration_ffprobe(file_path: str) -> Optional[float]:
    """Get video duration in seconds using ffprobe if available."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", file_path],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    duration = float(stream.get("duration", 0))
                    if duration > 0:
                        return duration
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return None


def validate_upload(
    filename: str,
    file_size_bytes: int,
    platforms: list[str] = None,
) -> dict:
    """
    Full validation pipeline for an uploaded file.
    Returns {"media_type": "image|video", "extension": "mp4", "size_mb": 12.3}
    Raises MediaValidationError on any violation.
    """
    media_type = detect_media_type(filename)
    ext = validate_file_format(filename, media_type)

    # Check size against all target platforms
    if platforms:
        for platform in platforms:
            validate_file_size(file_size_bytes, media_type, platform)
    else:
        validate_file_size(file_size_bytes, media_type)

    return {
        "media_type": media_type,
        "extension": ext,
        "size_mb": round(file_size_bytes / (1024 * 1024), 2),
    }
