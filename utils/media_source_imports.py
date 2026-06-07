"""Helpers for importing remote media from supported provider sources."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import magic

from utils.ssrf_guard import assert_safe_url

logger = logging.getLogger(__name__)

_ALLOWED_MIME_PREFIXES = ("image/", "video/")
_DEFAULT_CHUNK_SIZE = 1024 * 1024
_MAX_REDIRECTS = 5

_PROVIDER_HOST_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "unsplash": ("images.unsplash.com", "plus.unsplash.com", "api.unsplash.com"),
    "dropbox": ("dropbox.com", "dropboxusercontent.com"),
    "google_drive": ("www.googleapis.com", "googleusercontent.com"),
    "google_photos": ("googleusercontent.com", "lh3.googleusercontent.com"),
    "onedrive": ("1drv.com", "sharepoint.com", "onedrive.live.com", "storage.live.com"),
    "canva": ("api.canva.com", "canva.com", "document-export.canva.com", "export-download.canva.com"),
}


def is_allowed_provider_url(provider: str, url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    for suffix in _PROVIDER_HOST_ALLOWLIST.get(provider, ()):
        normalized = suffix.lower().lstrip(".")
        if host == normalized or host.endswith(f".{normalized}"):
            return True
    return False


def assert_allowed_provider_url(provider: str, url: str) -> None:
    if not is_allowed_provider_url(provider, url):
        raise ValueError(f"Provider URL is not allowed for {provider}")
    assert_safe_url(url)


def build_download_url_for_google_photos(base_url: str, mime_type: str | None) -> str:
    if (mime_type or "").startswith("video/"):
        return f"{base_url}=dv"
    return f"{base_url}=d"


async def stream_remote_file_to_path(
    *,
    provider: str,
    url: str,
    destination_path: str,
    headers: dict[str, str] | None,
    max_bytes: int,
    timeout_seconds: float = 600.0,
) -> dict[str, Any]:
    """Download a provider-hosted media file to disk with SSRF and size guards."""
    current_url = url
    current_headers = headers or {}
    redirects = 0

    timeout = httpx.Timeout(connect=15.0, read=timeout_seconds, write=30.0, pool=15.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        while True:
            assert_allowed_provider_url(provider, current_url)
            response = await client.get(current_url, headers=current_headers)

            if response.status_code in {301, 302, 303, 307, 308}:
                redirects += 1
                if redirects > _MAX_REDIRECTS:
                    raise ValueError("Too many redirects while importing remote media")
                location = response.headers.get("location")
                if not location:
                    raise ValueError("Redirect response missing location header")
                current_url = urljoin(current_url, location)
                continue

            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length:
                declared_size = int(content_length)
                if declared_size > max_bytes:
                    raise ValueError("Remote media exceeds the maximum allowed size")

            total_bytes = 0
            detected_type = None
            with open(destination_path, "wb") as handle:
                async for chunk in response.aiter_bytes(_DEFAULT_CHUNK_SIZE):
                    if not chunk:
                        continue
                    if detected_type is None:
                        detected_type = magic.from_buffer(chunk, mime=True) or None
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise ValueError("Remote media exceeds the maximum allowed size")
                    handle.write(chunk)

            mime_type = detected_type or response.headers.get("content-type", "").split(";")[0].strip()
            if not mime_type or not any(mime_type.startswith(prefix) for prefix in _ALLOWED_MIME_PREFIXES):
                raise ValueError(f"Unsupported remote media type: {mime_type or 'unknown'}")
            if total_bytes <= 0:
                raise ValueError("Remote media download was empty")

            return {
                "mime_type": mime_type,
                "file_size_bytes": total_bytes,
                "final_url": current_url,
                "filename": Path(urlparse(current_url).path).name,
            }


def get_provider_setup_requirements() -> dict[str, list[str]]:
    """Human-readable provider setup hints for disabled frontend states."""
    return {
        "unsplash": ["UNSPLASH access key"],
        "dropbox": ["Dropbox app key"],
        "google_drive": ["Google Picker API key", "Google OAuth client ID"],
        "google_photos": ["Google OAuth client ID"],
        "onedrive": ["Microsoft OneDrive app ID", "OneDrive redirect URI"],
        "canva": ["Canva client ID", "Canva client secret", "Canva redirect URI"],
    }
