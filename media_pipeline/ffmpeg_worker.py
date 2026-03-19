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

FFMPEG_TIMEOUT = 300  # 5-minute hard limit
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
    await _run_process(cmd_args)
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
    await _run_process(cmd_args)
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


async def _run_process(args: list[str]) -> None:
    """Run a process with explicit arg list — no shell interpolation."""
    # All args are server-generated constants or server-side temp file paths.
    # No user-supplied data is passed here.
    logger.debug("Running: %s %s ...", args[0], args[1])
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=FFMPEG_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("FFmpeg/FFprobe process timed out after 5 minutes")

    if proc.returncode != 0:
        raise RuntimeError(
            f"Process failed (exit {proc.returncode}): {stderr.decode()[-300:]}"
        )
