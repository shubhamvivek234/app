"""
Phase 2 — Image processing and optimization worker.
Handles vertical 9:16 fitting (blur pad / center crop) and smart compression using Pillow.
"""
import asyncio
import logging
import os
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

MAX_IMAGE_PIXELS = 178_956_970
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def _sync_fit_image_vertical(
    input_path: str,
    output_path: str,
    mode: str = "blur_pad",
    target_w: int = 1080,
    target_h: int = 1920,
) -> str:
    with Image.open(input_path) as img:
        img = img.convert("RGB")
        orig_w, orig_h = img.size

        if mode == "center_crop":
            target_ratio = target_w / target_h
            current_ratio = orig_w / orig_h
            if current_ratio > target_ratio:
                # Too wide -> crop sides
                new_w = int(orig_h * target_ratio)
                left = (orig_w - new_w) // 2
                cropped = img.crop((left, 0, left + new_w, orig_h))
            else:
                # Too tall -> crop top/bottom
                new_h = int(orig_w / target_ratio)
                top = (orig_h - new_h) // 2
                cropped = img.crop((0, top, orig_w, top + new_h))
            final_img = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
        else:
            # blur_pad
            scale_bg = max(target_w / orig_w, target_h / orig_h)
            bg_size = (int(orig_w * scale_bg), int(orig_h * scale_bg))
            bg = img.resize(bg_size, Image.Resampling.BILINEAR)
            bg_left = (bg.width - target_w) // 2
            bg_top = (bg.height - target_h) // 2
            bg = bg.crop((bg_left, bg_top, bg_left + target_w, bg_top + target_h))
            bg = bg.filter(ImageFilter.GaussianBlur(radius=30))

            scale_fg = min(target_w / orig_w, target_h / orig_h)
            fg_size = (int(orig_w * scale_fg), int(orig_h * scale_fg))
            fg = img.resize(fg_size, Image.Resampling.LANCZOS)

            paste_x = (target_w - fg_size[0]) // 2
            paste_y = (target_h - fg_size[1]) // 2
            bg.paste(fg, (paste_x, paste_y))
            final_img = bg

        ext = os.path.splitext(output_path)[1].lower()
        fmt = "JPEG" if ext in (".jpg", ".jpeg") else ("PNG" if ext == ".png" else "WEBP")
        final_img.save(output_path, format=fmt, quality=90, optimize=True)
        return output_path


def _sync_compress_image(input_path: str, output_path: str, target_max_bytes: int) -> str:
    with Image.open(input_path) as img:
        img = img.convert("RGB")
        cur_w, cur_h = img.size
        ext = os.path.splitext(output_path)[1].lower()
        fmt = "JPEG" if ext in (".jpg", ".jpeg") else ("PNG" if ext == ".png" else "WEBP")

        quality = 90
        for _ in range(6):
            img.save(output_path, format=fmt, quality=quality, optimize=True)
            if os.path.getsize(output_path) <= target_max_bytes:
                return output_path
            quality -= 10
            if quality < 40:
                break

        # If still over limit, downscale dimensions
        while os.path.getsize(output_path) > target_max_bytes and cur_w > 640 and cur_h > 640:
            cur_w = int(cur_w * 0.8)
            cur_h = int(cur_h * 0.8)
            downscaled = img.resize((cur_w, cur_h), Image.Resampling.LANCZOS)
            downscaled.save(output_path, format=fmt, quality=75, optimize=True)

        return output_path


async def auto_fit_image_vertical(
    input_path: str,
    output_path: str,
    mode: str = "blur_pad",
    target_w: int = 1080,
    target_h: int = 1920,
) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _sync_fit_image_vertical,
        input_path,
        output_path,
        mode,
        target_w,
        target_h,
    )


async def auto_compress_image(input_path: str, output_path: str, target_max_bytes: int) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _sync_compress_image,
        input_path,
        output_path,
        target_max_bytes,
    )
