"""Subtitle Generation & FFmpeg Video Slicer for Video Clipping Engine.
Generates styled ASS subtitles and processes 9:16 vertical shorts (blur-pad or crop).
"""
import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def format_ass_timestamp(seconds: float) -> str:
    """Format seconds into ASS timestamp format: H:MM:SS.cs"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generate_ass_subtitles(
    segments: List[Dict[str, Any]],
    clip_start_sec: float,
    clip_end_sec: float,
    style: str = "viral_yellow",
) -> str:
    """
    Generate Advanced SubStation Alpha (.ass) subtitle file content for a vertical short.
    Subtitles are offset relative to clip_start_sec.
    """
    # Color definitions in ASS format (&HAABBGGRR)
    primary_color = "&H0000FFFF" if style == "viral_yellow" else "&H00FFFFFF"
    if style == "modern_cyan":
        primary_color = "&H00FFFF00"
    outline_color = "&H00000000"
    back_color = "&H80000000"

    header = f"""[Script Info]
Title: Unravler Viral Short Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ViralStyle,Arial,68,{primary_color},&H000000FF,{outline_color},{back_color},-1,0,0,0,100,100,0,0,1,6,3,2,60,60,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for s in segments:
        seg_start = s["start"]
        seg_end = s["end"]

        # Only include segments overlapping with the clip interval
        if seg_end <= clip_start_sec or seg_start >= clip_end_sec:
            continue

        # Adjust timestamps relative to clip start
        rel_start = max(0.0, seg_start - clip_start_sec)
        rel_end = max(rel_start + 0.5, min(clip_end_sec - clip_start_sec, seg_end - clip_start_sec))

        start_str = format_ass_timestamp(rel_start)
        end_str = format_ass_timestamp(rel_end)
        clean_text = s["text"].strip().replace("\n", " ").upper()

        events.append(f"Dialogue: 0,{start_str},{end_str},ViralStyle,,0,0,0,,{clean_text}")

    return header + "\n".join(events)


async def render_vertical_clip(
    input_video_path: str,
    output_video_path: str,
    start_sec: float,
    end_sec: float,
    fit_mode: str = "blur",
    subtitle_ass_path: Optional[str] = None,
) -> str:
    """
    Cut video to specified interval, scale to vertical 9:16 (1080x1920),
    and burn-in subtitles if provided.
    """
    duration = end_sec - start_sec
    ffmpeg_bin = shutil.which("ffmpeg")

    if not ffmpeg_bin:
        logger.warning("ffmpeg not found on PATH. Simulating render.")
        # In mock environments, copy input if exists or create dummy file
        if os.path.exists(input_video_path):
            shutil.copyfile(input_video_path, output_video_path)
        else:
            Path(output_video_path).touch()
        return output_video_path

    # Build video filtergraph
    if fit_mode == "crop":
        vf_base = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    else:
        # Default: blur background pad
        vf_base = (
            "[0:v]split=2[bg][fg];"
            "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bgblur];"
            "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fgscale];"
            "[bgblur][fgscale]overlay=(W-w)/2:(H-h)/2"
        )

    if subtitle_ass_path and os.path.exists(subtitle_ass_path):
        escaped_sub = subtitle_ass_path.replace(":", "\\:").replace("'", "\\'")
        vf_full = f"{vf_base},ass='{escaped_sub}'"
    else:
        vf_full = vf_base

    cmd = [
        ffmpeg_bin,
        "-y",
        "-ss", str(start_sec),
        "-t", str(duration),
        "-i", input_video_path,
        "-filter_complex" if "[0:v]" in vf_full else "-vf", vf_full,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_video_path,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.error("FFmpeg vertical clip render failed: %s", stderr.decode(errors="ignore"))
        raise RuntimeError(f"FFmpeg error: {stderr.decode(errors='ignore')[:300]}")

    return output_video_path
