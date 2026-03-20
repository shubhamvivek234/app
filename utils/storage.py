"""
Unified storage abstraction for media files.

Feature flag: STORAGE_BACKEND=r2 (default) | firebase

- r2: Cloudflare R2 via boto3 S3-compatible API
- firebase: Firebase Storage (existing behaviour, wrapped)
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

_STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "r2").lower()

# ── R2 configuration ──────────────────────────────────────────────────────────
_R2_ENDPOINT = os.environ.get("CF_R2_ENDPOINT", "")
_R2_ACCESS_KEY_ID = os.environ.get("CF_R2_ACCESS_KEY_ID", "")
_R2_SECRET_ACCESS_KEY = os.environ.get("CF_R2_SECRET_ACCESS_KEY", "")
_R2_BUCKET = os.environ.get("CF_R2_BUCKET", "socialentangler-media")
_CF_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")

_R2_PUBLIC_URL_BASE = os.environ.get(
    "CF_R2_PUBLIC_URL",
    f"https://pub-{_CF_ACCOUNT_ID}.r2.dev" if _CF_ACCOUNT_ID else "",
)


def _get_r2_client():
    """Return a boto3 S3 client pointed at Cloudflare R2."""
    import boto3  # noqa: PLC0415
    return boto3.client(
        "s3",
        endpoint_url=_R2_ENDPOINT,
        aws_access_key_id=_R2_ACCESS_KEY_ID,
        aws_secret_access_key=_R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


# ── Public API ────────────────────────────────────────────────────────────────

def upload_file(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    folder: str = "uploads",
) -> str:
    """
    Upload *file_bytes* and return the public URL string.

    Parameters
    ----------
    file_bytes:    Raw file content.
    filename:      Safe filename (no path components).
    content_type:  MIME type string, e.g. 'image/webp'.
    folder:        Storage path prefix, e.g. 'media/user123'.
    """
    key = f"{folder}/{filename}"

    if _STORAGE_BACKEND == "r2":
        client = _get_r2_client()
        client.put_object(
            Bucket=_R2_BUCKET,
            Key=key,
            Body=file_bytes,
            ContentType=content_type,
        )
        if not _R2_PUBLIC_URL_BASE:
            raise RuntimeError(
                "CF_R2_PUBLIC_URL or CLOUDFLARE_ACCOUNT_ID must be set for R2 uploads"
            )
        return f"{_R2_PUBLIC_URL_BASE.rstrip('/')}/{key}"

    elif _STORAGE_BACKEND == "firebase":
        import firebase_admin.storage as fb_storage  # noqa: PLC0415
        bucket = fb_storage.bucket()
        blob = bucket.blob(key)
        blob.upload_from_string(file_bytes, content_type=content_type)
        blob.make_public()
        return blob.public_url

    else:
        raise ValueError(f"Unknown STORAGE_BACKEND: {_STORAGE_BACKEND!r}")


async def upload_file_async(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    folder: str = "uploads",
) -> str:
    """Async wrapper — runs the blocking upload_file() in a thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: upload_file(file_bytes, filename, content_type, folder),
    )


def delete_file(key: str) -> None:
    """Delete a file by its storage key (folder/filename)."""
    if _STORAGE_BACKEND == "r2":
        client = _get_r2_client()
        client.delete_object(Bucket=_R2_BUCKET, Key=key)
    elif _STORAGE_BACKEND == "firebase":
        import firebase_admin.storage as fb_storage  # noqa: PLC0415
        bucket = fb_storage.bucket()
        blob = bucket.blob(key)
        blob.delete()
