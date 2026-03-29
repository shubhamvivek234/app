"""
Phase 2 — FFmpeg video processing worker.
H.264 transcoding, HDR->SDR conversion, audio injection, GIF->MP4.
All subprocess calls use create_subprocess_exec with explicit arg lists (no shell=True).
Paths are server-generated UUIDs — never user-supplied strings passed to shell.
"""
import asyncio
import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

_FFMPEG_BASE_TIMEOUT = 300   # 5-minute base for files under 500 MB
_FFMPEG_SECS_PER_GB = 600   # +10 min per GB above 500 MB


def _ffmpeg_timeout_for_file(file_path: str) -> int:
    """Dynamic FFmpeg timeout based on file size. Larger files get proportionally more time."""
    try:
        size_bytes = os.path.getsize(file_path)
    except OSError:
        return _FFMPEG_BASE_TIMEOUT
    size_gb = size_bytes / (1024 * 1024 * 1024)
    if size_gb <= 0.5:
        return _FFMPEG_BASE_TIMEOUT
    extra = int((size_gb - 0.5) * _FFMPEG_SECS_PER_GB)
    return min(_FFMPEG_BASE_TIMEOUT + extra, 7200)  # cap at 2 hours

TEMP_DIR = "/tmp/media_processing"


async def process_video(input_path: str, metadata: dict) -> str:
    """Process a video. Returns path to processed output."""
    Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)
    output_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}.mp4")

    if metadata.get("needs_hdr_conversion"):
        return await _convert_hdr_to_sdr(input_path, output_path)

    if metadata.get("is_animated_gif"):
        return await _convert_gif_to_mp4(input_path, output_path)

    needs_transcode = (
        metadata.get("codec") not in ("h264", "avc1") or
        (metadata.get("width") or 0) > 1920
    )
    if needs_transcode:
        return await _transcode_h264(input_path, output_path)

    return input_path


async def _transcode_h264(input_path: str, output_path: str) -> str:
    cmd_args = [
        "ffmpeg", "-y", "-i", input_path,
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-vf", "scale=min(1920\\,iw):min(1080\\,ih):force_original_aspect_ratio=decrease",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]
    await _run_process(cmd_args, timeout=_ffmpeg_timeout_for_file(input_path))
    return output_path


async def _convert_hdr_to_sdr(input_path: str, output_path: str) -> str:
    """Phase 2.3 — HDR (PQ/HLG) to SDR via FFmpeg tone-mapping."""
    tone_map_filter = (
        "zscale=transfer=linear,tonemap=hable,"
        "zscale=transfer=bt709,format=yuv420p"
    )
    cmd_args = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", tone_map_filter,
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ]
    await _run_process(cmd_args, timeout=_ffmpeg_timeout_for_file(input_path))
    logger.info("HDR->SDR conversion complete")
    return output_path


async def _convert_gif_to_mp4(input_path: str, output_path: str) -> str:
    """Phase 2.7 — Animated GIF to H.264 MP4."""
    cmd_args = [
        "ffmpeg", "-y",
        "-ignore_loop", "0",
        "-i", input_path,
        "-vf", "fps=25,scale=min(1280\\,iw):-2:flags=lanczos",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-an",
        "-movflags", "+faststart",
        output_path,
    ]
    await _run_process(cmd_args)
    return output_path


async def add_silent_audio_track(input_path: str) -> str:
    """Phase 2.3 — Add silent audio for platforms that require it (Instagram Stories, TikTok)."""
    output_path = input_path.replace(".mp4", "_with_audio.mp4")
    cmd_args = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path,
    ]
    await _run_process(cmd_args)
    return output_path


async def convert_gif_for_platforms(
    input_path: str, platforms: list[str], output_dir: str
) -> dict[str, str]:
    """
    EC30 — Convert animated GIF per-platform.

    Returns dict mapping platform name -> output file path (or error string).
    - Instagram/TikTok: GIF -> MP4 (H.264, silent audio, loop once)
    - YouTube: GIF -> MP4 with 3x loop (-stream_loop 2)
    - Twitter: Validate GIF < 15MB and < 6s; error if over limits
    - LinkedIn: Warning that only first frame shown (no conversion)
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}

    for platform in platforms:
        platform_lower = platform.lower()

        if platform_lower in ("instagram", "tiktok"):
            output_path = os.path.join(output_dir, f"{uuid.uuid4()}_{platform_lower}.mp4")
            cmd_args = [
                "ffmpeg", "-y",
                "-ignore_loop", "0",
                "-i", input_path,
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-vf", "fps=25,scale=min(1280\\,iw):-2:flags=lanczos",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-c:a", "aac",
                "-shortest",
                "-movflags", "+faststart",
                output_path,
            ]
            try:
                await _run_process(cmd_args)
                results[platform_lower] = output_path
            except RuntimeError as exc:
                results[platform_lower] = f"error: {exc}"

        elif platform_lower == "youtube":
            output_path = os.path.join(output_dir, f"{uuid.uuid4()}_youtube.mp4")
            cmd_args = [
                "ffmpeg", "-y",
                "-stream_loop", "2",
                "-ignore_loop", "0",
                "-i", input_path,
                "-vf", "fps=25,scale=min(1280\\,iw):-2:flags=lanczos",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                "-an",
                "-movflags", "+faststart",
                output_path,
            ]
            try:
                await _run_process(cmd_args)
                results["youtube"] = output_path
            except RuntimeError as exc:
                results["youtube"] = f"error: {exc}"

        elif platform_lower == "twitter":
            # Validate GIF: must be < 15MB and < 6s duration.
            try:
                file_size = os.path.getsize(input_path)
                max_size = 15 * 1024 * 1024  # 15 MB
                if file_size > max_size:
                    results["twitter"] = (
                        f"error: GIF is {file_size / (1024 * 1024):.1f}MB, "
                        f"exceeds Twitter's 15MB limit"
                    )
                    continue

                # Probe duration with ffprobe.
                probe_args = [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    input_path,
                ]
                proc = await asyncio.create_subprocess_exec(
                    *probe_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=_FFMPEG_BASE_TIMEOUT
                )
                duration_str = stdout.decode().strip()
                duration = float(duration_str) if duration_str else 0.0

                if duration > 6.0:
                    results["twitter"] = (
                        f"error: GIF duration is {duration:.1f}s, "
                        f"exceeds Twitter's 6s limit"
                    )
                    continue

                # GIF passes validation — return original path.
                results["twitter"] = input_path

            except (ValueError, RuntimeError) as exc:
                results["twitter"] = f"error: {exc}"

        elif platform_lower == "linkedin":
            results["linkedin"] = (
                "warning: LinkedIn displays only the first frame of animated GIFs; "
                "no conversion performed"
            )

        else:
            results[platform_lower] = f"error: unsupported platform '{platform}'"

    return results


async def _run_process(args: list[str], *, timeout: int | None = None) -> None:
    """Run a process with explicit arg list — no shell interpolation."""
    # All args are server-generated constants or server-side temp file paths.
    # No user-supplied data is passed here.
    effective_timeout = timeout or _FFMPEG_BASE_TIMEOUT
    logger.debug("Running: %s %s ... (timeout=%ds)", args[0], args[1], effective_timeout)
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=effective_timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"FFmpeg/FFprobe process timed out after {effective_timeout}s")

    if proc.returncode != 0:
        raise RuntimeError(
            f"Process failed (exit {proc.returncode}): {stderr.decode()[-300:]}"
        )
