"""
Unified storage abstraction for media files.

Feature flag: STORAGE_BACKEND=r2 | firebase

- r2: Cloudflare R2 via boto3 S3-compatible API
- firebase: Firebase Storage (existing behaviour, wrapped)
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _detect_storage_backend() -> str:
    configured = os.environ.get("STORAGE_BACKEND", "").strip().lower()
    if configured in {"r2", "firebase"}:
        return configured

    has_r2 = bool(
        os.environ.get("CF_R2_ENDPOINT")
        and os.environ.get("CF_R2_ACCESS_KEY_ID")
        and os.environ.get("CF_R2_SECRET_ACCESS_KEY")
    )
    if has_r2:
        return "r2"

    has_firebase = bool(
        os.environ.get("FIREBASE_STORAGE_BUCKET")
        and os.environ.get("FIREBASE_ADMIN_SDK_JSON")
    )
    if has_firebase:
        return "firebase"

    return "r2"


_STORAGE_BACKEND = _detect_storage_backend()

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
).rstrip("/")


def get_storage_backend() -> str:
    return _STORAGE_BACKEND


def validate_storage_backend() -> dict[str, str]:
    """
    Validate the configured storage backend and basic reachability.

    Returns a small status payload that can be surfaced in readiness checks.
    Raises on invalid configuration or failed provider access.
    """
    backend = get_storage_backend()

    if backend == "r2":
        client = _get_r2_client()
        client.list_objects_v2(Bucket=_R2_BUCKET, MaxKeys=1)
        return {"backend": "r2", "bucket": _R2_BUCKET}

    bucket = _get_firebase_bucket()
    if not bucket.exists():
        raise RuntimeError(f"Firebase Storage bucket is not accessible: {bucket.name}")
    return {"backend": "firebase", "bucket": bucket.name}


async def validate_storage_backend_async() -> dict[str, str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, validate_storage_backend)


def _ensure_firebase_app():
    """Initialize Firebase Admin in non-API processes such as Celery workers."""
    import firebase_admin  # noqa: PLC0415
    from firebase_admin import credentials  # noqa: PLC0415

    try:
        return firebase_admin.get_app()
    except ValueError:
        cred_path = os.environ.get("FIREBASE_ADMIN_SDK_JSON", "/app/serviceAccountKey.json")
        if not Path(cred_path).is_file():
            raise RuntimeError(
                "Firebase Admin SDK credential file not found. "
                f"Expected FIREBASE_ADMIN_SDK_JSON at '{cred_path}'."
            )

        options = {}
        bucket_name = os.environ.get("FIREBASE_STORAGE_BUCKET", "").strip()
        if bucket_name:
            options["storageBucket"] = bucket_name

        app = firebase_admin.initialize_app(credentials.Certificate(cred_path), options)
        logger.info("Firebase Admin SDK initialized for storage from %s", cred_path)
        return app


def _get_firebase_bucket():
    import firebase_admin.storage as fb_storage  # noqa: PLC0415

    _ensure_firebase_app()
    bucket_name = os.environ.get("FIREBASE_STORAGE_BUCKET", "").strip()
    if bucket_name:
        return fb_storage.bucket(bucket_name)
    return fb_storage.bucket()


def _get_r2_client():
    """Return a boto3 S3 client pointed at Cloudflare R2."""
    import boto3  # noqa: PLC0415 — imported lazily to avoid hard dep when using Firebase
    if not _R2_ENDPOINT or not _R2_ACCESS_KEY_ID or not _R2_SECRET_ACCESS_KEY:
        raise RuntimeError(
            "Cloudflare R2 is not fully configured. Expected CF_R2_ENDPOINT, "
            "CF_R2_ACCESS_KEY_ID, and CF_R2_SECRET_ACCESS_KEY."
        )
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


def create_direct_upload_session(
    *,
    key: str,
    content_type: str,
    file_size_bytes: int,
    expires_in: int = 14_400,
) -> dict:
    if _STORAGE_BACKEND != "r2":
        raise RuntimeError("Direct browser uploads are currently supported only with R2.")
    return _r2_create_direct_upload_session(
        key=key,
        content_type=content_type,
        file_size_bytes=file_size_bytes,
        expires_in=expires_in,
    )


def complete_direct_upload_session(
    *,
    key: str,
    upload_id: str,
    parts: list[dict[str, int | str]],
) -> None:
    if _STORAGE_BACKEND != "r2":
        raise RuntimeError("Direct browser uploads are currently supported only with R2.")
    _r2_complete_direct_upload_session(key=key, upload_id=upload_id, parts=parts)


def abort_direct_upload_session(*, key: str, upload_id: str) -> None:
    if _STORAGE_BACKEND != "r2":
        raise RuntimeError("Direct browser uploads are currently supported only with R2.")
    _r2_abort_direct_upload_session(key=key, upload_id=upload_id)


def head_storage_object(reference: str) -> dict[str, str | int | None]:
    if _STORAGE_BACKEND == "r2":
        return _r2_head_object(reference)
    return _firebase_head_object(reference)


async def head_storage_object_async(reference: str) -> dict[str, str | int | None]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: head_storage_object(reference))


def download_file_to_path(reference: str, destination_path: str) -> str:
    if _STORAGE_BACKEND == "r2":
        return _r2_download_to_path(reference, destination_path)
    return _firebase_download_to_path(reference, destination_path)


async def download_file_to_path_async(reference: str, destination_path: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: download_file_to_path(reference, destination_path),
    )


# ── R2 backend ────────────────────────────────────────────────────────────────

def _r2_object_key(folder: str, filename: str) -> str:
    return f"{folder}/{filename}"


def build_storage_key(folder: str, filename: str) -> str:
    return _r2_object_key(folder, filename)


def public_url_for_key(key: str) -> str:
    normalized_key = key.lstrip("/")
    if _STORAGE_BACKEND == "r2":
        if not _R2_PUBLIC_URL_BASE:
            raise RuntimeError(
                "CF_R2_PUBLIC_URL or CLOUDFLARE_ACCOUNT_ID must be configured for R2 media URLs"
            )
        return f"{_R2_PUBLIC_URL_BASE}/{normalized_key}"
    return normalized_key


def _reference_to_r2_key(reference: str) -> str:
    parsed = urlparse(reference)
    if parsed.scheme and parsed.netloc:
        return parsed.path.lstrip("/")
    return reference.lstrip("/")


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
    public_url = public_url_for_key(key)
    logger.info("R2 upload complete: key=%s url=%s", key, public_url)
    return public_url



# ── Large file support: upload from path (streaming / multipart) ──────────

_MULTIPART_THRESHOLD = 100 * 1024 * 1024  # 100 MB — use multipart above this size
_MULTIPART_CHUNK_SIZE = 100 * 1024 * 1024  # 100 MB chunks
_DIRECT_UPLOAD_MULTIPART_THRESHOLD = 64 * 1024 * 1024
_DIRECT_UPLOAD_PART_SIZE = max(
    5 * 1024 * 1024,
    int(os.environ.get("R2_DIRECT_UPLOAD_PART_SIZE_BYTES", str(64 * 1024 * 1024))),
)


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

    public_url = public_url_for_key(key)
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
        bucket = _get_firebase_bucket()
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
    key = _reference_to_r2_key(url)
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


def _r2_create_direct_upload_session(
    *,
    key: str,
    content_type: str,
    file_size_bytes: int,
    expires_in: int,
) -> dict:
    client = _get_r2_client()

    if file_size_bytes <= _DIRECT_UPLOAD_MULTIPART_THRESHOLD:
        url = client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": _R2_BUCKET,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        return {
            "mode": "single",
            "object_key": key,
            "content_type": content_type,
            "expires_in_seconds": expires_in,
            "url": url,
            "headers": {"Content-Type": content_type},
        }

    upload = client.create_multipart_upload(
        Bucket=_R2_BUCKET,
        Key=key,
        ContentType=content_type,
    )
    upload_id = upload["UploadId"]
    part_count = math.ceil(file_size_bytes / _DIRECT_UPLOAD_PART_SIZE)
    parts = []
    for index in range(part_count):
        part_number = index + 1
        url = client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": _R2_BUCKET,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=expires_in,
        )
        parts.append({"part_number": part_number, "url": url})

    return {
        "mode": "multipart",
        "object_key": key,
        "content_type": content_type,
        "expires_in_seconds": expires_in,
        "upload_id": upload_id,
        "part_size_bytes": _DIRECT_UPLOAD_PART_SIZE,
        "parts": parts,
        "headers": {"Content-Type": content_type},
    }


def _r2_complete_direct_upload_session(
    *,
    key: str,
    upload_id: str,
    parts: list[dict[str, int | str]],
) -> None:
    client = _get_r2_client()
    normalized_parts = [
        {"PartNumber": int(part["PartNumber"]), "ETag": str(part["ETag"])}
        for part in parts
    ]
    normalized_parts.sort(key=lambda item: item["PartNumber"])
    client.complete_multipart_upload(
        Bucket=_R2_BUCKET,
        Key=key,
        UploadId=upload_id,
        MultipartUpload={"Parts": normalized_parts},
    )


def _r2_abort_direct_upload_session(*, key: str, upload_id: str) -> None:
    client = _get_r2_client()
    client.abort_multipart_upload(
        Bucket=_R2_BUCKET,
        Key=key,
        UploadId=upload_id,
    )


def _r2_head_object(reference: str) -> dict[str, str | int | None]:
    key = _reference_to_r2_key(reference)
    client = _get_r2_client()
    response = client.head_object(Bucket=_R2_BUCKET, Key=key)
    return {
        "key": key,
        "content_type": response.get("ContentType"),
        "file_size_bytes": int(response.get("ContentLength") or 0),
        "etag": str(response.get("ETag") or "").strip('"'),
    }


def _r2_download_to_path(reference: str, destination_path: str) -> str:
    key = _reference_to_r2_key(reference)
    client = _get_r2_client()
    Path(destination_path).parent.mkdir(parents=True, exist_ok=True)
    with open(destination_path, "wb") as handle:
        client.download_fileobj(_R2_BUCKET, key, handle)
    return destination_path


# ── Firebase backend (existing behaviour wrapped) ─────────────────────────────

def _firebase_upload(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    folder: str,
) -> str:
    """Wrap existing Firebase Storage upload logic."""
    try:
        bucket = _get_firebase_bucket()
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


def _firebase_head_object(reference: str) -> dict[str, str | int | None]:
    bucket = _get_firebase_bucket()
    blob_name = urlparse(reference).path.lstrip("/") if reference.startswith("http") else reference
    blob = bucket.blob(blob_name)
    if not blob.exists():
        raise FileNotFoundError(f"Firebase object not found: {blob_name}")
    blob.reload()
    return {
        "key": blob_name,
        "content_type": blob.content_type,
        "file_size_bytes": int(blob.size or 0),
        "etag": blob.etag,
    }


def _firebase_download_to_path(reference: str, destination_path: str) -> str:
    bucket = _get_firebase_bucket()
    blob_name = urlparse(reference).path.lstrip("/") if reference.startswith("http") else reference
    blob = bucket.blob(blob_name)
    Path(destination_path).parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(destination_path)
    return destination_path


def _firebase_delete(url: str) -> None:
    """Delete a Firebase Storage object identified by its public URL."""
    try:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            path = parsed.path
            parts = path.lstrip("/").split("/", 1)
            blob_name = parts[1] if len(parts) > 1 else path.lstrip("/")
        else:
            blob_name = url.lstrip("/")
        bucket = _get_firebase_bucket()
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

        bucket = _get_firebase_bucket()
        blob = bucket.blob(key)
        url = blob.generate_signed_url(
            expiration=datetime.timedelta(seconds=expires_in),
            method="GET",
        )
        return url
    except Exception as exc:
        logger.error("Firebase signed URL failed: %s", exc, exc_info=True)
        raise
