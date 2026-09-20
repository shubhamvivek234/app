"""AI Image Generation Service for Social Media Posts and RSS Feeds."""
import logging
import urllib.parse
import hashlib

logger = logging.getLogger(__name__)


def generate_banner_image(title: str, summary: str = "", style: str = "editorial") -> str:
    """
    Generate a high-quality visual banner URL for an article or post.
    Produces a 16:9 aspect ratio image (1200x675) optimized for social sharing.
    """
    clean_title = (title or "Latest News and Updates").strip()[:100]
    
    # Deterministic seed based on title to keep image consistent across retries
    seed = int(hashlib.md5(clean_title.encode()).hexdigest()[:8], 16) % 100000

    # Build prompt
    prompt = f"Minimalist professional {style} digital art banner representing: {clean_title}. Clean vector aesthetics, high dynamic range, soft gradient lighting, modern tech editorial style, 4k"
    encoded_prompt = urllib.parse.quote(prompt)

    # Pollinations Flux model provides instant, high-quality, free 1200x675 images
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1200&height=675&model=flux&nologo=true&seed={seed}"
    return image_url
