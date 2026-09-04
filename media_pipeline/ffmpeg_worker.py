"""
Phase 2 — FFmpeg video processing worker.
H.264 transcoding, HDR->SDR conversion, audio injection, GIF->MP4.
All subprocess calls use create_subprocess_exec with explicit arg lists (no shell=True).
Paths are server-generated UUIDs — never user-supplied strings passed to shell.
"""
import asyncio
import json
import logging
import os
import struct
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


def _build_transcode_scale_filter(width: int | None, height: int | None) -> str:
    width = int(width or 0)
    height = int(height or 0)
    if height > width:
        return "scale=-2:min(1920\\,ih):flags=lanczos"
    return "scale=min(1920\\,iw):-2:flags=lanczos"


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
        max(int(metadata.get("width") or 0), int(metadata.get("height") or 0)) > 1920
    )
    if needs_transcode:
        return await _transcode_h264(input_path, output_path, metadata)

    return input_path


async def _transcode_h264(input_path: str, output_path: str, metadata: dict) -> str:
    scale_filter = _build_transcode_scale_filter(
        metadata.get("width"),
        metadata.get("height"),
    )
    cmd_args = [
        "ffmpeg", "-y", "-i", input_path,
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-vf", scale_filter,
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


def _seconds_from_ms(value: int | float | None) -> float:
    try:
        return max(float(value or 0) / 1000.0, 0.0)
    except (TypeError, ValueError):
        return 0.0


def _volume_fraction(value: int | float | None, default: float = 1.0) -> float:
    try:
        return min(max(float(default if value is None else value), 0.0), 1.0)
    except (TypeError, ValueError):
        return min(max(float(default), 0.0), 1.0)


def build_audio_mix_command(
    *,
    video_path: str,
    audio_path: str,
    output_path: str,
    video_duration_seconds: float,
    video_has_audio: bool,
    mix: dict,
) -> list[str]:
    """Build the FFmpeg command for baking selected audio into a video."""
    duration = max(float(video_duration_seconds or 0), 0.1)
    trim_start = _seconds_from_ms(mix.get("trim_start_ms"))
    trim_end = mix.get("trim_end_ms")
    trim_end_seconds = _seconds_from_ms(trim_end) if trim_end is not None else None
    offset_seconds = min(_seconds_from_ms(mix.get("video_offset_ms")), max(duration - 0.1, 0.0))
    selected_duration = max(duration - offset_seconds, 0.1)
    selected_volume = _volume_fraction(mix.get("selected_volume"), 1.0)
    original_volume = _volume_fraction(mix.get("original_volume"), 1.0)
    fade_in = min(_seconds_from_ms(mix.get("fade_in_ms")), selected_duration)
    fade_out = min(_seconds_from_ms(mix.get("fade_out_ms")), selected_duration)
    delay_ms = int(round(offset_seconds * 1000))

    selected_filters = []
    atrim_parts = [f"start={trim_start:.3f}"]
    if trim_end_seconds is not None and trim_end_seconds > trim_start:
        atrim_parts.append(f"end={trim_end_seconds:.3f}")
    selected_filters.append(f"atrim={':'.join(atrim_parts)}")
    selected_filters.append("asetpts=PTS-STARTPTS")
    if mix.get("loop_to_video_end", True):
        selected_filters.append("aloop=loop=-1:size=2147483647")
    selected_filters.append(f"atrim=duration={selected_duration:.3f}")
    selected_filters.append("asetpts=PTS-STARTPTS")
    selected_filters.append(f"volume={selected_volume:.4f}")
    if mix.get("normalize_audio", True):
        selected_filters.append("dynaudnorm=f=150:g=5")
    if fade_in > 0:
        selected_filters.append(f"afade=t=in:st=0:d={fade_in:.3f}")
    if fade_out > 0:
        fade_start = max(selected_duration - fade_out, 0.0)
        selected_filters.append(f"afade=t=out:st={fade_start:.3f}:d={fade_out:.3f}")
    selected_filters.append(f"adelay={delay_ms}|{delay_ms}")
    selected_filters.append(f"apad=whole_dur={duration:.3f}")
    selected_filters.append("atrim=duration={:.3f}".format(duration))
    selected_filters.append("aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo")

    use_original_audio = video_has_audio and not mix.get("mute_original", False) and original_volume > 0
    if selected_volume <= 0 and not use_original_audio:
        raise ValueError("Audio mix would be silent")

    filter_parts = [f"[1:a]{','.join(selected_filters)}[selected]"]
    if use_original_audio:
        filter_parts.append(
            f"[0:a]volume={original_volume:.4f},"
            "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[original]"
        )
        filter_parts.append("[original][selected]amix=inputs=2:duration=longest:dropout_transition=0,alimiter=limit=0.95[aout]")
    else:
        filter_parts.append("[selected]alimiter=limit=0.95[aout]")

    return [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-filter_complex", ";".join(filter_parts),
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", f"{duration:.3f}",
        "-movflags", "+faststart",
        output_path,
    ]


async def render_video_with_audio(
    *,
    video_path: str,
    audio_path: str,
    output_path: str,
    video_metadata: dict,
    mix: dict,
) -> str:
    """Bake a selected audio track into a processed MP4 video."""
    cmd_args = build_audio_mix_command(
        video_path=video_path,
        audio_path=audio_path,
        output_path=output_path,
        video_duration_seconds=float(video_metadata.get("duration") or 0),
        video_has_audio=bool(video_metadata.get("has_audio")),
        mix=mix,
    )
    await _run_process(
        cmd_args,
        timeout=max(
            _ffmpeg_timeout_for_file(video_path),
            _ffmpeg_timeout_for_file(audio_path),
        ),
    )
    return output_path


async def extract_audio_waveform_peaks(audio_path: str, bar_count: int = 64) -> list[float]:
    """Return normalized RMS peaks for a compact UI waveform."""
    safe_bar_count = max(16, min(int(bar_count or 64), 256))
    cmd_args = [
        "ffmpeg", "-v", "error",
        "-i", audio_path,
        "-vn",
        "-ac", "1",
        "-ar", "2000",
        "-f", "f32le",
        "pipe:1",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=_ffmpeg_timeout_for_file(audio_path),
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("Waveform extraction timed out")
    if proc.returncode != 0:
        raise RuntimeError((stderr or b"Waveform extraction failed").decode(errors="ignore").strip())
    sample_count = len(stdout) // 4
    if sample_count <= 0:
        return []

    samples_per_bar = max(1, sample_count // safe_bar_count)
    peaks: list[float] = []
    for index in range(safe_bar_count):
        start = index * samples_per_bar
        end = sample_count if index == safe_bar_count - 1 else min(sample_count, start + samples_per_bar)
        if start >= sample_count:
            peaks.append(0.0)
            continue
        total = 0.0
        count = 0
        for (sample,) in struct.iter_unpack("<f", stdout[start * 4:end * 4]):
            total += float(sample) * float(sample)
            count += 1
        peaks.append((total / max(count, 1)) ** 0.5)

    max_peak = max(peaks) if peaks else 0.0
    if max_peak <= 0:
        return [0.0 for _ in range(safe_bar_count)]
    return [round(min(max(peak / max_peak, 0.0), 1.0), 4) for peak in peaks]


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


async def _probe_has_audio(file_path: str) -> bool:
    """Check whether a media file has an audio stream."""
    args = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "a",
        file_path,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        data = json.loads(stdout)
        return len(data.get("streams", [])) > 0
    except Exception:
        return False


async def _probe_duration(file_path: str) -> float:
    """Return video duration in seconds."""
    args = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        file_path,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        data = json.loads(stdout)
        dur = data.get("format", {}).get("duration", "0")
        return float(dur) if dur else 0.0
    except Exception:
        return 0.0


async def auto_fit_video_vertical(
    input_path: str,
    output_path: str,
    mode: str = "blur_pad",
    ensure_audio: bool = True,
) -> str:
    """
    Transform video to 1080x1920 (9:16) for TikTok, Reels, Shorts.
    - mode="blur_pad": Scale to fit with blurred video background
    - mode="center_crop": Center crop to 1080x1920
    - If ensure_audio is True and input has no audio, injects a silent stereo AAC track.
    """
    has_audio = await _probe_has_audio(input_path)
    need_silent_audio = ensure_audio and not has_audio

    if mode == "center_crop":
        filter_str = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        if need_silent_audio:
            cmd_args = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-vf", filter_str,
                "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                "-movflags", "+faststart",
                output_path,
            ]
        elif has_audio:
            cmd_args = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", filter_str,
                "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                output_path,
            ]
        else:
            cmd_args = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", filter_str,
                "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
                "-an",
                "-movflags", "+faststart",
                output_path,
            ]
    else:
        # blur_pad (default)
        blur_filter = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:5[bg];"
            "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
        )
        if need_silent_audio:
            cmd_args = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-filter_complex", blur_filter,
                "-map", "[v]",
                "-map", "1:a",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                "-movflags", "+faststart",
                output_path,
            ]
        elif has_audio:
            cmd_args = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-filter_complex", blur_filter,
                "-map", "[v]",
                "-map", "0:a:0",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                output_path,
            ]
        else:
            cmd_args = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-filter_complex", blur_filter,
                "-map", "[v]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
                "-an",
                "-movflags", "+faststart",
                output_path,
            ]

    await _run_process(cmd_args, timeout=_ffmpeg_timeout_for_file(input_path))
    return output_path


async def auto_compress_video(
    input_path: str,
    output_path: str,
    target_max_bytes: int,
    duration_sec: float | None = None,
) -> str:
    """
    Compress video to fit within target_max_bytes by computing bitrate constraint.
    """
    dur = duration_sec or (await _probe_duration(input_path))
    dur = max(float(dur or 0), 1.0)

    # 93% budget for container muxing overhead
    target_bits = float(target_max_bytes) * 8.0 * 0.93
    has_audio = await _probe_has_audio(input_path)
    audio_bitrate_bps = 128_000 if has_audio else 0
    video_bitrate_bps = max(int((target_bits / dur) - audio_bitrate_bps), 200_000)
    max_rate = int(video_bitrate_bps * 1.25)
    buf_size = int(video_bitrate_bps * 2.0)

    cmd_args = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-c:v", "libx264",
        "-b:v", str(video_bitrate_bps),
        "-maxrate", str(max_rate),
        "-bufsize", str(buf_size),
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
    ]
    if has_audio:
        cmd_args.extend(["-c:a", "aac", "-b:a", "128k"])
    else:
        cmd_args.append("-an")

    cmd_args.extend(["-movflags", "+faststart", output_path])
    await _run_process(cmd_args, timeout=_ffmpeg_timeout_for_file(input_path))
    return output_path

