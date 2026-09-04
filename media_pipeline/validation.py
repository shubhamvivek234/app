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

from media_pipeline.platform_specs import PLATFORM_SPECS, get_platform_spec, is_vertical_required

PLATFORM_LIMITS = {
    platform: {
        "max_size_bytes": spec["max_video_bytes"],
        "max_duration": spec["max_duration_seconds"],
        "max_width": spec["max_width"],
    }
    for platform, spec in PLATFORM_SPECS.items()
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
            ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac",
            ".wav": "audio/wav", ".ogg": "audio/ogg", ".flac": "audio/flac",
        }.get(suffix, "application/octet-stream")


def _detect_mime_from_buffer(header_bytes: bytes) -> str:
    """Detect MIME from header bytes without disk I/O."""
    detected = None
    try:
        import magic
        detected = magic.from_buffer(header_bytes, mime=True)
    except Exception:
        detected = None

    if detected and detected != "application/octet-stream":
        return detected

    if len(header_bytes) >= 12 and header_bytes[4:8] == b"ftyp":
        return "video/mp4"
    if header_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header_bytes.startswith(b"RIFF") and len(header_bytes) >= 12 and header_bytes[8:12] == b"WEBP":
        return "image/webp"
    return detected or "application/octet-stream"


async def probe_remote_media_stream(url: str, timeout: int = 60) -> dict:
    """
    Run ffprobe directly on a remote HTTP/HTTPS URL via HTTP Range requests.
    Inspects codec, streams, duration, and dimensions without downloading the file.
    """
    args = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        "-analyzeduration", "10000000",
        "-probesize", "10000000",
        url,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            raise ValueError(f"Remote FFprobe failed (exit {proc.returncode}): {stderr.decode()[:300]}")
        return json.loads(stdout)
    except asyncio.TimeoutError:
        raise ValueError("Remote FFprobe timed out — network slow or object inaccessible")


async def validate_remote_media(
    url: str,
    claimed_mime: str | None = None,
    file_size_bytes: int = 0,
    header_bytes: bytes | None = None,
    timeout: int = 60,
) -> dict:
    """
    Validate remote media stored in cloud storage (R2/S3) without downloading to disk.
    Uses header_bytes for magic byte detection and ffprobe over HTTP Range for video specs.
    """
    detected_mime = claimed_mime or "application/octet-stream"
    if header_bytes:
        detected = _detect_mime_from_buffer(header_bytes)
        if detected and detected != "application/octet-stream":
            detected_mime = detected

    is_video = detected_mime.startswith("video/") or (
        claimed_mime and claimed_mime.startswith("video/")
    )
    is_image = (
        detected_mime.startswith("image/")
        or (claimed_mime and claimed_mime.startswith("image/"))
    ) and detected_mime != "image/gif"
    is_audio = detected_mime.startswith("audio/") or (
        claimed_mime and claimed_mime.startswith("audio/")
    )

    result: dict = {
        "mime_type": detected_mime,
        "file_size_bytes": file_size_bytes,
        "is_video": is_video,
        "is_image": is_image,
        "is_audio": is_audio,
        "is_animated_gif": False,
    }

    if is_video or is_audio or detected_mime == "image/gif":
        probe = await probe_remote_media_stream(url, timeout=timeout)
        result.update(_parse_ffprobe(probe))
        if "codec" in result and not result.get("is_video") and not result.get("is_audio"):
            result["is_video"] = True

    return result


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
        "is_audio": detected_mime.startswith("audio/"),
        "is_animated_gif": False,
    }

    if result["is_video"] or result["is_audio"] or detected_mime == "image/gif":
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
            raw_width = int(stream.get("width") or 0)
            raw_height = int(stream.get("height") or 0)
            rotation = 0
            for side_data in stream.get("side_data_list", []) or []:
                side_rotation = side_data.get("rotation")
                if side_rotation is None:
                    continue
                try:
                    rotation = int(round(float(side_rotation))) % 360
                    break
                except (TypeError, ValueError):
                    continue
            if not rotation:
                try:
                    rotation = int(round(float((stream.get("tags", {}) or {}).get("rotate", 0)))) % 360
                except (TypeError, ValueError):
                    rotation = 0
            if rotation in (90, 270):
                result["width"] = raw_height
                result["height"] = raw_width
            else:
                result["width"] = raw_width
                result["height"] = raw_height
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
