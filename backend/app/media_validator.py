"""
Media Validation — Stage 2.4
Validates uploaded files before storage: size, format, MIME type, video metadata.
"""
import os
import subprocess
import json
import mimetypes
from typing import Optional
from fastapi import UploadFile, HTTPException

# Per-platform limits (bytes)
MAX_IMAGE_SIZE = 8 * 1024 * 1024        # 8 MB
MAX_VIDEO_SIZE = 500 * 1024 * 1024      # 500 MB
MAX_DOCUMENT_SIZE = 20 * 1024 * 1024    # 20 MB (LinkedIn docs)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/gif",
    "image/webp", "image/bmp", "image/tiff",
}
ALLOWED_VIDEO_TYPES = {
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "video/x-matroska", "video/webm", "video/mpeg",
}
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
    "application/vnd.ms-powerpoint",  # ppt
}

# Image extensions → MIME
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg", ".m4v"}
DOCUMENT_EXTENSIONS = {".pdf", ".pptx", ".ppt"}

# YouTube video constraints
YT_MAX_DURATION_SEC = 12 * 3600      # 12 hours
YT_MIN_RESOLUTION = (426, 240)       # 240p minimum

# Instagram video constraints
IG_MAX_DURATION_SEC = 90             # 90s for Reels
IG_MAX_ASPECT_RATIO = 1.91           # landscape max
IG_MIN_ASPECT_RATIO = 0.5            # portrait min (4:5 ~ 0.8, allowed down to 9:16 ~ 0.56)


# ── Legacy error class kept for backward-compatibility with existing callers ──
class MediaValidationError(ValueError):
    def __init__(self, message: str, error_code: str = "EC5:INVALID_MEDIA_FORMAT"):
        super().__init__(message)
        self.error_code = error_code


def get_file_ext(filename: str) -> str:
    return os.path.splitext(filename.lower())[1]


def detect_media_type(filename: str, content_type: str) -> str:
    """Returns 'image', 'video', 'document', or 'unknown'."""
    ext = get_file_ext(filename)
    if ext in IMAGE_EXTENSIONS or content_type in ALLOWED_IMAGE_TYPES:
        return "image"
    if ext in VIDEO_EXTENSIONS or content_type in ALLOWED_VIDEO_TYPES:
        return "video"
    if ext in DOCUMENT_EXTENSIONS or content_type in ALLOWED_DOCUMENT_TYPES:
        return "document"
    return "unknown"


def validate_file_size(size_bytes: int, media_type: str, platform: Optional[str] = None) -> None:
    """Raise HTTPException if file exceeds size limit."""
    limits = {
        "image": MAX_IMAGE_SIZE,
        "video": MAX_VIDEO_SIZE,
        "document": MAX_DOCUMENT_SIZE,
    }
    limit = limits.get(media_type, MAX_IMAGE_SIZE)
    if size_bytes > limit:
        limit_mb = limit // (1024 * 1024)
        size_mb = round(size_bytes / (1024 * 1024), 1)
        raise HTTPException(
            status_code=413,
            detail={
                "error_code": "UPLOAD_TOO_LARGE",
                "message": f"File too large: {size_mb} MB. Maximum allowed: {limit_mb} MB for {media_type}s.",
                "details": {"size_mb": size_mb, "limit_mb": limit_mb},
            }
        )


def validate_mime_type(filename: str, content_type: str) -> str:
    """Validate MIME type and return media_type. Raise if not allowed."""
    media_type = detect_media_type(filename, content_type)
    ext = get_file_ext(filename)

    if media_type == "image":
        if content_type not in ALLOWED_IMAGE_TYPES and ext not in IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail={
                    "error_code": "UPLOAD_INVALID_FORMAT",
                    "message": f"Unsupported image format: {content_type}. Allowed: JPEG, PNG, GIF, WebP.",
                }
            )
    elif media_type == "video":
        if content_type not in ALLOWED_VIDEO_TYPES and ext not in VIDEO_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail={
                    "error_code": "UPLOAD_INVALID_FORMAT",
                    "message": f"Unsupported video format: {content_type}. Allowed: MP4, MOV, AVI, MKV, WebM.",
                }
            )
    elif media_type == "document":
        pass  # Documents checked loosely by extension
    else:
        raise HTTPException(
            status_code=415,
            detail={
                "error_code": "UPLOAD_INVALID_FORMAT",
                "message": f"Unsupported file type: {content_type}. Upload images (JPEG/PNG/GIF/WebP), videos (MP4/MOV/AVI), or documents (PDF/PPTX).",
            }
        )
    return media_type


def get_video_metadata(file_path: str) -> Optional[dict]:
    """
    Use ffprobe to extract video metadata.
    Returns dict with duration, width, height, codec, fps — or None if ffprobe unavailable.
    """
    ffprobe_path = None
    for candidate in ["ffprobe", "/usr/bin/ffprobe", "/usr/local/bin/ffprobe"]:
        if subprocess.run(["which", candidate], capture_output=True).returncode == 0:
            ffprobe_path = candidate
            break

    if not ffprobe_path:
        return None  # ffprobe not installed — skip video metadata validation

    try:
        result = subprocess.run(
            [
                ffprobe_path, "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-show_format",
                file_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        video_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
            None
        )
        if not video_stream:
            return None

        duration = float(data.get("format", {}).get("duration", 0))
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        codec = video_stream.get("codec_name", "unknown")
        fps_str = video_stream.get("r_frame_rate", "0/1")
        try:
            num, den = fps_str.split("/")
            fps = round(float(num) / float(den), 2) if float(den) > 0 else 0
        except Exception:
            fps = 0

        return {
            "duration_sec": round(duration, 2),
            "width": width,
            "height": height,
            "codec": codec,
            "fps": fps,
            "aspect_ratio": round(width / height, 3) if height > 0 else 0,
        }
    except Exception:
        return None


def validate_video_for_platform(metadata: dict, platform: str) -> None:
    """Validate video metadata against platform-specific constraints."""
    if not metadata:
        return  # Can't validate without metadata — allow upload, catch at publish time

    duration = metadata.get("duration_sec", 0)
    width = metadata.get("width", 0)
    height = metadata.get("height", 0)
    aspect = metadata.get("aspect_ratio", 1.0)

    if platform == "youtube":
        if duration > YT_MAX_DURATION_SEC:
            raise HTTPException(400, detail={
                "error_code": "UPLOAD_INVALID_FORMAT",
                "message": f"Video too long for YouTube: {duration/3600:.1f}h. Max: 12 hours.",
            })

    elif platform == "instagram":
        if duration > IG_MAX_DURATION_SEC:
            raise HTTPException(400, detail={
                "error_code": "UPLOAD_INVALID_FORMAT",
                "message": f"Video too long for Instagram Reels: {int(duration)}s. Max: 90 seconds.",
            })
        if aspect > IG_MAX_ASPECT_RATIO or aspect < IG_MIN_ASPECT_RATIO:
            raise HTTPException(400, detail={
                "error_code": "UPLOAD_INVALID_FORMAT",
                "message": f"Video aspect ratio {aspect:.2f} not supported for Instagram. Use between 0.56 (9:16) and 1.91 (16:9).",
            })


async def validate_upload(file: UploadFile, content: bytes, platform: Optional[str] = None) -> dict:
    """
    Full validation pipeline for an uploaded file.
    Returns metadata dict with media_type, size_bytes, and optionally video_metadata.
    Call this BEFORE saving the file to storage.
    """
    filename = file.filename or "upload"
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    size_bytes = len(content)

    # 1. MIME type validation
    media_type = validate_mime_type(filename, content_type)

    # 2. File size validation
    validate_file_size(size_bytes, media_type)

    result = {
        "media_type": media_type,
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2),
        "content_type": content_type,
        "filename": filename,
    }

    # 3. Video metadata validation (if video and ffprobe available)
    if media_type == "video":
        import tempfile, uuid as _uuid
        ext = get_file_ext(filename) or ".mp4"
        tmp_path = f"/tmp/validate_{_uuid.uuid4().hex}{ext}"
        try:
            with open(tmp_path, "wb") as f:
                f.write(content)
            metadata = get_video_metadata(tmp_path)
            if metadata:
                result["video_metadata"] = metadata
                if platform:
                    validate_video_for_platform(metadata, platform)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    return result
