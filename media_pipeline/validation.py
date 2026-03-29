"""
Phase 2.2 + 2.3 — Media validation pipeline.
Magic byte MIME detection, FFprobe extended validation, HDR detection,
animated GIF detection, aspect ratio enforcement.
Note: FFprobe called via asyncio.create_subprocess_exec (not shell exec) to prevent injection.
"""
import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

FFPROBE_TIMEOUT = 120  # doubled — large files (10GB) need more time for ffprobe
FFMPEG_TIMEOUT = 300   # 5 minutes (base — ffmpeg_worker uses dynamic timeout)
MAX_IMAGE_PIXELS = 178_956_970  # ~12000x12000 (decompression bomb limit)

PLATFORM_LIMITS = {
    "instagram": {"max_size_bytes": 650 * 1024 * 1024, "max_duration": 3600, "max_width": 1920},
    "facebook":  {"max_size_bytes": 4 * 1024 * 1024 * 1024, "max_duration": 7200, "max_width": 1920},
    "youtube":   {"max_size_bytes": 256 * 1024 * 1024 * 1024, "max_duration": None, "max_width": None},
    "twitter":   {"max_size_bytes": 512 * 1024 * 1024, "max_duration": 140, "max_width": 1280},
    "linkedin":  {"max_size_bytes": 5 * 1024 * 1024 * 1024, "max_duration": 600, "max_width": 1920},
    "tiktok":    {"max_size_bytes": 4 * 1024 * 1024 * 1024, "max_duration": 600, "max_width": 1920},
}


def _detect_mime(file_path: str) -> str:
    """Detect MIME from magic bytes. Never trusts Content-Type header."""
    try:
        import magic
        return magic.from_file(file_path, mime=True)
    except ImportError:
        # Fallback: basic extension mapping if python-magic not installed
        suffix = Path(file_path).suffix.lower()
        return {
            ".mp4": "video/mp4", ".mov": "video/quicktime", ".avi": "video/x-msvideo",
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".gif": "image/gif", ".webp": "image/webp",
        }.get(suffix, "application/octet-stream")


async def validate_media(file_path: str, claimed_mime: str | None = None) -> dict:
    """
    Full validation pipeline. Returns metadata dict.
    Raises ValueError with a user-readable message on failure.
    """
    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"File not found: {file_path}")

    detected_mime = _detect_mime(str(path))
    logger.info("MIME detection: claimed=%s detected=%s", claimed_mime, detected_mime)

    size_bytes = path.stat().st_size
    if size_bytes == 0:
        raise ValueError("File is empty")

    result: dict = {
        "mime_type": detected_mime,
        "file_size_bytes": size_bytes,
        "is_video": detected_mime.startswith("video/"),
        "is_image": detected_mime.startswith("image/") and detected_mime != "image/gif",
        "is_animated_gif": False,
    }

    if result["is_video"] or detected_mime == "image/gif":
        probe = await _ffprobe(str(path))
        result.update(_parse_ffprobe(probe))
    elif result["is_image"]:
        result.update(await _validate_image(str(path)))

    return result


async def _ffprobe(file_path: str) -> dict:
    """Run ffprobe using create_subprocess_exec (no shell=True, prevents injection)."""
    args = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        file_path,  # file_path is a server-side temp path — not user-supplied string
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=FFPROBE_TIMEOUT)
        if proc.returncode != 0:
            raise ValueError(f"FFprobe failed (exit {proc.returncode}): {stderr.decode()[:300]}")
        return json.loads(stdout)
    except asyncio.TimeoutError:
        raise ValueError("FFprobe timed out — file may be corrupted or too large")


def _parse_ffprobe(probe: dict) -> dict:
    streams = probe.get("streams", [])
    fmt = probe.get("format", {})
    result: dict = {"has_audio": False, "needs_hdr_conversion": False, "is_animated_gif": False}

    duration_str = fmt.get("duration", "0")
    result["duration"] = float(duration_str) if duration_str else 0.0

    for stream in streams:
        codec_type = stream.get("codec_type")
        if codec_type == "video":
            result["width"] = stream.get("width")
            result["height"] = stream.get("height")
            result["codec"] = stream.get("codec_name")
            result["color_transfer"] = stream.get("color_transfer", "")
            nb_frames = int(stream.get("nb_frames") or 0)

            if stream.get("codec_name") == "gif" and nb_frames > 1:
                result["is_animated_gif"] = True

            if result["color_transfer"] in ("smpte2084", "arib-std-b67"):
                result["needs_hdr_conversion"] = True

        elif codec_type == "audio":
            result["has_audio"] = True

    return result


async def _validate_image(file_path: str) -> dict:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

    loop = asyncio.get_event_loop()

    def _open_image():
        with Image.open(file_path) as img:
            img.verify()  # raises on corrupted files
        with Image.open(file_path) as img:
            return {"width": img.width, "height": img.height, "mode": img.mode}

    return await loop.run_in_executor(None, _open_image)


async def validate_for_platform(metadata: dict, platform: str, post_type: str) -> None:
    """Phase 2.5 — Raises ValueError if file doesn't meet platform constraints."""
    limits = PLATFORM_LIMITS.get(platform, {})

    max_size = limits.get("max_size_bytes")
    if max_size and metadata.get("file_size_bytes", 0) > max_size:
        raise ValueError(
            f"File too large for {platform}: {metadata['file_size_bytes'] / 1024 / 1024:.1f}MB "
            f"(max {max_size / 1024 / 1024:.0f}MB)"
        )

    max_dur = limits.get("max_duration")
    if max_dur and metadata.get("duration", 0) > max_dur:
        raise ValueError(f"Video too long for {platform}: {metadata['duration']:.0f}s (max {max_dur}s)")

    if platform == "instagram" and post_type in ("reel", "instagram_reel"):
        w = metadata.get("width", 1) or 1
        h = metadata.get("height", 1) or 1
        if w > h:
            raise ValueError("Instagram Reels must be portrait (9:16). Landscape videos are not allowed.")

    if platform == "tiktok":
        w = metadata.get("width", 1) or 1
        h = metadata.get("height", 1) or 1
        if (w / h) > 1.1:
            raise ValueError("TikTok requires 9:16 (portrait) aspect ratio")
