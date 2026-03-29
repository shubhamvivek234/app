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
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "r2").lower()

# ── R2 configuration ──────────────────────────────────────────────────────────
_R2_ENDPOINT = os.environ.get("CF_R2_ENDPOINT", "")
_R2_ACCESS_KEY_ID = os.environ.get("CF_R2_ACCESS_KEY_ID", "")
_R2_SECRET_ACCESS_KEY = os.environ.get("CF_R2_SECRET_ACCESS_KEY", "")
_R2_BUCKET = os.environ.get("CF_R2_BUCKET", "socialentangler-media")
_CF_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")

# Public R2 URL base (r2.dev public bucket or custom domain)
_R2_PUBLIC_URL_BASE = os.environ.get(
    "CF_R2_PUBLIC_URL",
    f"https://pub-{_CF_ACCOUNT_ID}.r2.dev" if _CF_ACCOUNT_ID else "",
)


def _get_r2_client():
    """Return a boto3 S3 client pointed at Cloudflare R2."""
    import boto3  # noqa: PLC0415 — imported lazily to avoid hard dep when using Firebase
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
    content_type:  MIME type string, e.g. "image/jpeg".
    folder:        Logical folder prefix, e.g. "thumbnails" or "uploads".

    Returns
    -------
    str  — publicly accessible URL for the uploaded object.
    """
    if _STORAGE_BACKEND == "r2":
        return _r2_upload(file_bytes, filename, content_type, folder)
    return _firebase_upload(file_bytes, filename, content_type, folder)


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


def delete_file(url: str) -> None:
    """
    Delete the object identified by *url*.

    The URL must have been produced by :func:`upload_file`.
    """
    if _STORAGE_BACKEND == "r2":
        _r2_delete(url)
    else:
        _firebase_delete(url)


async def delete_file_async(url: str) -> None:
    """Async wrapper — runs the blocking delete_file() in a thread pool."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: delete_file(url))


def get_signed_url(key: str, expires_in: int = 3600) -> str:
    """
    Generate a pre-signed URL for *key* that expires after *expires_in* seconds.

    For R2, *key* is the object key (e.g. ``uploads/abc.jpg``).
    For Firebase, *key* is treated as the full GCS path.
    """
    if _STORAGE_BACKEND == "r2":
        return _r2_signed_url(key, expires_in)
    return _firebase_signed_url(key, expires_in)


# ── R2 backend ────────────────────────────────────────────────────────────────

def _r2_object_key(folder: str, filename: str) -> str:
    return f"{folder}/{filename}"


def _r2_upload(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    folder: str,
) -> str:
    key = _r2_object_key(folder, filename)
    client = _get_r2_client()
    client.put_object(
        Bucket=_R2_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )
    public_url = f"{_R2_PUBLIC_URL_BASE}/{key}"
    logger.info("R2 upload complete: key=%s url=%s", key, public_url)
    return public_url



# ── Large file support: upload from path (streaming / multipart) ──────────

_MULTIPART_THRESHOLD = 100 * 1024 * 1024  # 100 MB — use multipart above this size
_MULTIPART_CHUNK_SIZE = 100 * 1024 * 1024  # 100 MB chunks


def upload_file_from_path(
    file_path: str,
    filename: str,
    content_type: str,
    folder: str = "uploads",
) -> str:
    """
    Upload a file from disk path — uses multipart upload for files > 100 MB.
    Does NOT load the entire file into memory.
    """
    if _STORAGE_BACKEND == "r2":
        return _r2_upload_from_path(file_path, filename, content_type, folder)
    return _firebase_upload_from_path(file_path, filename, content_type, folder)


async def upload_file_from_path_async(
    file_path: str,
    filename: str,
    content_type: str,
    folder: str = "uploads",
) -> str:
    """Async wrapper — runs the blocking upload_file_from_path() in a thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: upload_file_from_path(file_path, filename, content_type, folder),
    )


def _r2_upload_from_path(
    file_path: str,
    filename: str,
    content_type: str,
    folder: str,
) -> str:
    """
    Upload from file path using boto3 multipart upload for large files.
    Files under _MULTIPART_THRESHOLD use single put_object.
    Files over _MULTIPART_THRESHOLD use multipart upload in _MULTIPART_CHUNK_SIZE chunks.
    """
    import os as _os
    key = _r2_object_key(folder, filename)
    client = _get_r2_client()
    file_size = _os.path.getsize(file_path)

    if file_size <= _MULTIPART_THRESHOLD:
        # Small file — single PUT (no multipart overhead)
        with open(file_path, "rb") as f:
            client.put_object(
                Bucket=_R2_BUCKET,
                Key=key,
                Body=f,
                ContentType=content_type,
            )
    else:
        # Large file — multipart upload
        mpu = client.create_multipart_upload(
            Bucket=_R2_BUCKET,
            Key=key,
            ContentType=content_type,
        )
        upload_id = mpu["UploadId"]
        parts = []
        part_number = 1

        try:
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(_MULTIPART_CHUNK_SIZE)
                    if not chunk:
                        break
                    resp = client.upload_part(
                        Bucket=_R2_BUCKET,
                        Key=key,
                        UploadId=upload_id,
                        PartNumber=part_number,
                        Body=chunk,
                    )
                    parts.append({"ETag": resp["ETag"], "PartNumber": part_number})
                    logger.info(
                        "R2 multipart part %d uploaded (%d bytes) for key=%s",
                        part_number, len(chunk), key,
                    )
                    part_number += 1

            client.complete_multipart_upload(
                Bucket=_R2_BUCKET,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
        except Exception:
            # Abort multipart upload on any failure to avoid orphaned parts
            try:
                client.abort_multipart_upload(
                    Bucket=_R2_BUCKET,
                    Key=key,
                    UploadId=upload_id,
                )
                logger.warning("R2 multipart upload aborted for key=%s", key)
            except Exception as abort_exc:
                logger.error("R2 multipart abort failed for key=%s: %s", key, abort_exc)
            raise

    public_url = f"{_R2_PUBLIC_URL_BASE}/{key}"
    logger.info("R2 upload complete: key=%s size=%d url=%s", key, file_size, public_url)
    return public_url


def _firebase_upload_from_path(
    file_path: str,
    filename: str,
    content_type: str,
    folder: str,
) -> str:
    """Upload from file path to Firebase Storage using streaming."""
    try:
        import firebase_admin.storage as fb_storage

        bucket = fb_storage.bucket()
        blob_path = f"{folder}/{filename}"
        blob = bucket.blob(blob_path)
        blob.upload_from_filename(file_path, content_type=content_type)
        blob.make_public()
        url: str = blob.public_url
        logger.info("Firebase upload from path complete: blob=%s url=%s", blob_path, url)
        return url
    except Exception as exc:
        logger.error("Firebase upload from path failed: %s", exc, exc_info=True)
        raise


def _r2_delete(url: str) -> None:
    parsed = urlparse(url)
    # Strip leading slash to get the object key
    key = parsed.path.lstrip("/")
    client = _get_r2_client()
    client.delete_object(Bucket=_R2_BUCKET, Key=key)
    logger.info("R2 delete complete: key=%s", key)


def _r2_signed_url(key: str, expires_in: int) -> str:
    client = _get_r2_client()
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": _R2_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )
    return url


# ── Firebase backend (existing behaviour wrapped) ─────────────────────────────

def _firebase_upload(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    folder: str,
) -> str:
    """Wrap existing Firebase Storage upload logic."""
    try:
        import firebase_admin.storage as fb_storage  # noqa: PLC0415

        bucket = fb_storage.bucket()
        blob_path = f"{folder}/{filename}"
        blob = bucket.blob(blob_path)
        blob.upload_from_string(file_bytes, content_type=content_type)
        blob.make_public()
        url: str = blob.public_url
        logger.info("Firebase upload complete: blob=%s url=%s", blob_path, url)
        return url
    except Exception as exc:
        logger.error("Firebase upload failed: %s", exc, exc_info=True)
        raise


def _firebase_delete(url: str) -> None:
    """Delete a Firebase Storage object identified by its public URL."""
    try:
        import firebase_admin.storage as fb_storage  # noqa: PLC0415

        parsed = urlparse(url)
        # GCS public URL path: /storage/v1/b/<bucket>/o/<encoded-path>
        # Simple approach: strip prefix to derive blob name
        path = parsed.path  # e.g. /bucket-name/folder/file.jpg
        parts = path.lstrip("/").split("/", 1)
        blob_name = parts[1] if len(parts) > 1 else path
        bucket = fb_storage.bucket()
        blob = bucket.blob(blob_name)
        blob.delete()
        logger.info("Firebase delete complete: blob=%s", blob_name)
    except Exception as exc:
        logger.error("Firebase delete failed: %s", exc, exc_info=True)
        raise


def _firebase_signed_url(key: str, expires_in: int) -> str:
    """Generate a signed URL for a Firebase Storage object."""
    try:
        import datetime  # noqa: PLC0415
        import firebase_admin.storage as fb_storage  # noqa: PLC0415

        bucket = fb_storage.bucket()
        blob = bucket.blob(key)
        url = blob.generate_signed_url(
            expiration=datetime.timedelta(seconds=expires_in),
            method="GET",
        )
        return url
    except Exception as exc:
        logger.error("Firebase signed URL failed: %s", exc, exc_info=True)
        raise
