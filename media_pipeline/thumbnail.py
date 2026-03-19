"""
Phase 2.6 — Thumbnail generation. Thumbnails are PERMANENT, never deleted.
Video: frame at 1s via FFmpeg. Image: centre-crop 400x400 WebP via Pillow.
All process invocations use explicit arg lists with server-generated paths only.
"""
import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

THUMB_SIZE = (400, 400)
THUMB_QUALITY = 80
TEMP_DIR = "/tmp/thumbnails"
PROCESS_TIMEOUT = 60


async def generate_thumbnail(source_path: str, mime_type: str, media_id: str, user_id: str) -> str:
    """Generate a WebP thumbnail. Returns local temp path."""
    Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)
    output_path = os.path.join(TEMP_DIR, f"{media_id}.webp")

    if mime_type and mime_type.startswith("video/"):
        await _video_thumbnail(source_path, output_path)
    elif mime_type == "application/pdf":
        await _pdf_thumbnail(source_path, output_path)
    else:
        await _image_thumbnail(source_path, output_path)

    return output_path


async def _video_thumbnail(video_path: str, output_path: str) -> None:
    """Extract frame at 1-second mark, centre-crop to square WebP."""
    crop_filter = (
        f"scale={THUMB_SIZE[0]}:{THUMB_SIZE[1]}:force_original_aspect_ratio=increase,"
        f"crop={THUMB_SIZE[0]}:{THUMB_SIZE[1]}"
    )
    args = [
        "ffmpeg", "-y",
        "-ss", "1",
        "-i", video_path,
        "-vframes", "1",
        "-vf", crop_filter,
        "-f", "image2",
        "-vcodec", "libwebp",
        "-quality", str(THUMB_QUALITY),
        output_path,
    ]
    await _run_subprocess(args)


async def _image_thumbnail(image_path: str, output_path: str) -> None:
    """Centre-crop image to 400x400, strip EXIF, save as WebP using Pillow."""
    from PIL import Image

    loop = asyncio.get_event_loop()

    def _process():
        with Image.open(image_path) as img:
            # Strip EXIF by rebuilding pixel data
            clean = Image.new(img.mode, img.size)
            clean.putdata(list(img.getdata()))
            w, h = clean.size
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            cropped = clean.crop((left, top, left + side, top + side))
            resized = cropped.resize(THUMB_SIZE, Image.LANCZOS)
            resized.save(output_path, format="WEBP", quality=THUMB_QUALITY, optimize=True)

    await loop.run_in_executor(None, _process)


async def _pdf_thumbnail(pdf_path: str, output_path: str) -> None:
    """LinkedIn PDF: render first page as 400x400 WebP thumbnail."""
    from pdf2image import convert_from_path
    from PIL import Image

    loop = asyncio.get_event_loop()

    def _process():
        pages = convert_from_path(pdf_path, first_page=1, last_page=1, dpi=72)
        if not pages:
            raise ValueError("PDF has no renderable pages")
        page = pages[0]
        w, h = page.size
        side = min(w, h)
        cropped = page.crop((0, 0, side, side))
        resized = cropped.resize(THUMB_SIZE, Image.LANCZOS)
        resized.save(output_path, format="WEBP", quality=THUMB_QUALITY)

    await loop.run_in_executor(None, _process)


async def _run_subprocess(args: list[str]) -> None:
    """Safe subprocess: explicit arg list, server-generated paths only, no shell."""
    prog = args[0]
    prog_args = args[1:]
    proc = await asyncio.create_subprocess_exec(
        prog, *prog_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=PROCESS_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("Thumbnail process timed out")

    if proc.returncode != 0:
        raise RuntimeError(f"Thumbnail process failed: {stderr.decode()[-200:]}")
