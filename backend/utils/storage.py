"""
Unified storage abstraction for media files.

Feature flag: STORAGE_BACKEND=r2 | firebase

- r2: Cloudflare R2 via boto3 S3-compatible API
- firebase: Firebase Storage (existing behaviour, wrapped)
"""
from __future__ import annotations

import logging
import math
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _env(primary: str, *aliases: str, default: str = "") -> str:
    for name in (primary, *aliases):
        value = os.environ.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _normalize_public_url_base(raw_value: str) -> str:
    value = (raw_value or "").strip().rstrip("/")
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    return f"https://{value}"


def _detect_storage_backend() -> str:
    configured = os.environ.get("STORAGE_BACKEND", "").strip().lower()
    if configured in {"r2", "firebase"}:
        return configured

    has_r2 = bool(
        _env("CF_R2_ENDPOINT", "CLOUDFLARE_R2_ENDPOINT")
        and _env("CF_R2_ACCESS_KEY_ID", "CLOUDFLARE_R2_ACCESS_KEY_ID")
        and _env("CF_R2_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_SECRET_ACCESS_KEY")
    )
    if has_r2:
        return "r2"

    if os.environ.get("FIREBASE_STORAGE_BUCKET"):
        return "firebase"

    return "r2"


_STORAGE_BACKEND = _detect_storage_backend()

_R2_ENDPOINT = _env("CF_R2_ENDPOINT", "CLOUDFLARE_R2_ENDPOINT")
_R2_ACCESS_KEY_ID = _env("CF_R2_ACCESS_KEY_ID", "CLOUDFLARE_R2_ACCESS_KEY_ID")
_R2_SECRET_ACCESS_KEY = _env("CF_R2_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_SECRET_ACCESS_KEY")
_R2_BUCKET = _env("CF_R2_BUCKET", "CLOUDFLARE_R2_BUCKET_NAME", default="socialentangler-media")
_CF_ACCOUNT_ID = _env("CLOUDFLARE_ACCOUNT_ID")
_R2_PUBLIC_URL_BASE = _normalize_public_url_base(
    _env(
        "CF_R2_PUBLIC_URL",
        "CLOUDFLARE_CDN_DOMAIN",
        default=f"https://pub-{_CF_ACCOUNT_ID}.r2.dev" if _CF_ACCOUNT_ID else "",
    )
)
_R2_PUBLIC_HOST = urlparse(_R2_PUBLIC_URL_BASE).netloc.lower() if _R2_PUBLIC_URL_BASE else ""
_R2_ENDPOINT_HOST = urlparse(_R2_ENDPOINT).netloc.lower() if _R2_ENDPOINT else ""


def get_storage_backend() -> str:
    return _STORAGE_BACKEND


def build_public_url(key: str) -> str:
    if not _R2_PUBLIC_URL_BASE:
        raise RuntimeError("CF_R2_PUBLIC_URL or CLOUDFLARE_CDN_DOMAIN must be configured for R2")
    return f"{_R2_PUBLIC_URL_BASE}/{key.lstrip('/')}"


def _get_r2_client():
    import boto3  # noqa: PLC0415
    from botocore.client import Config  # noqa: PLC0415

    return boto3.client(
        "s3",
        endpoint_url=_R2_ENDPOINT,
        aws_access_key_id=_R2_ACCESS_KEY_ID,
        aws_secret_access_key=_R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def _ensure_r2_ready() -> None:
    missing = [
        name
        for name, value in {
            "CF_R2_ENDPOINT": _R2_ENDPOINT,
            "CF_R2_ACCESS_KEY_ID": _R2_ACCESS_KEY_ID,
            "CF_R2_SECRET_ACCESS_KEY": _R2_SECRET_ACCESS_KEY,
            "CF_R2_BUCKET": _R2_BUCKET,
            "CF_R2_PUBLIC_URL": _R2_PUBLIC_URL_BASE,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"R2 storage is not fully configured. Missing: {', '.join(missing)}")


def _r2_object_key(folder: str, filename: str) -> str:
    safe_folder = folder.strip("/ ")
    if safe_folder:
        return f"{safe_folder}/{filename}"
    return filename


def extract_object_key(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        return url.lstrip("/")

    path = parsed.path.lstrip("/")
    host = parsed.netloc.lower()

    if host == _R2_PUBLIC_HOST:
        return path
    if host == _R2_ENDPOINT_HOST and path.startswith(f"{_R2_BUCKET}/"):
        return path[len(_R2_BUCKET) + 1 :]
    if path.startswith(f"{_R2_BUCKET}/"):
        return path[len(_R2_BUCKET) + 1 :]
    return path


def is_managed_storage_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = parsed.netloc.lower()
    if host in {_R2_PUBLIC_HOST, _R2_ENDPOINT_HOST}:
        return True
    path = parsed.path.lstrip("/")
    return bool(host and _R2_BUCKET and path.startswith(f"{_R2_BUCKET}/"))


def create_direct_upload_session(
    *,
    filename: str,
    content_type: str,
    folder: str,
    file_size_bytes: int,
    multipart_threshold_bytes: int = 25 * 1024 * 1024,
    part_size_bytes: int = 25 * 1024 * 1024,
    multipart_max_parts: int = 10,
) -> dict:
    _ensure_r2_ready()

    key = _r2_object_key(folder, filename)
    public_url = build_public_url(key)
    client = _get_r2_client()

    if file_size_bytes > multipart_threshold_bytes:
        create_resp = client.create_multipart_upload(
            Bucket=_R2_BUCKET,
            Key=key,
            ContentType=content_type,
        )
        upload_id = create_resp["UploadId"]
        total_parts = max(1, math.ceil(file_size_bytes / part_size_bytes))
        parts = []
        for part_number in range(1, total_parts + 1):
            parts.append(
                {
                    "part_number": part_number,
                    "url": client.generate_presigned_url(
                        "upload_part",
                        Params={
                            "Bucket": _R2_BUCKET,
                            "Key": key,
                            "UploadId": upload_id,
                            "PartNumber": part_number,
                        },
                        ExpiresIn=3600,
                    ),
                }
            )
        return {
            "mode": "multipart",
            "upload_id": upload_id,
            "key": key,
            "public_url": public_url,
            "part_size_bytes": part_size_bytes,
            "parts": parts,
            "headers": {"Content-Type": "application/octet-stream"},
        }

    return {
        "mode": "singlepart",
        "key": key,
        "public_url": public_url,
        "url": client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": _R2_BUCKET,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=3600,
            HttpMethod="PUT",
        ),
        "headers": {"Content-Type": content_type},
    }


def complete_multipart_upload(key: str, upload_id: str, parts: list[dict]) -> None:
    _ensure_r2_ready()
    client = _get_r2_client()
    client.complete_multipart_upload(
        Bucket=_R2_BUCKET,
        Key=key,
        UploadId=upload_id,
        MultipartUpload={"Parts": parts},
    )


def abort_multipart_upload(key: str, upload_id: str) -> None:
    _ensure_r2_ready()
    client = _get_r2_client()
    client.abort_multipart_upload(Bucket=_R2_BUCKET, Key=key, UploadId=upload_id)


def get_object_metadata(key: str) -> dict:
    _ensure_r2_ready()
    client = _get_r2_client()
    return client.head_object(Bucket=_R2_BUCKET, Key=key)


def upload_file(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    folder: str = "uploads",
) -> str:
    if _STORAGE_BACKEND == "r2":
        return _r2_upload(file_bytes, filename, content_type, folder)
    return _firebase_upload(file_bytes, filename, content_type, folder)


def delete_file(url: str) -> None:
    if _STORAGE_BACKEND == "r2":
        _r2_delete(url)
    else:
        _firebase_delete(url)


def get_signed_url(key: str, expires_in: int = 3600) -> str:
    if _STORAGE_BACKEND == "r2":
        return _r2_signed_url(key, expires_in)
    return _firebase_signed_url(key, expires_in)


def _r2_upload(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    folder: str,
) -> str:
    _ensure_r2_ready()
    key = _r2_object_key(folder, filename)
    client = _get_r2_client()
    client.put_object(
        Bucket=_R2_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )
    public_url = build_public_url(key)
    logger.info("R2 upload complete: key=%s url=%s", key, public_url)
    return public_url


def _r2_delete(url: str) -> None:
    _ensure_r2_ready()
    key = extract_object_key(url)
    client = _get_r2_client()
    client.delete_object(Bucket=_R2_BUCKET, Key=key)
    logger.info("R2 delete complete: key=%s", key)


def _r2_signed_url(key: str, expires_in: int) -> str:
    _ensure_r2_ready()
    client = _get_r2_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": _R2_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )


def _firebase_upload(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    folder: str,
) -> str:
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
    try:
        import firebase_admin.storage as fb_storage  # noqa: PLC0415

        parsed = urlparse(url)
        path = parsed.path
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
    try:
        import datetime  # noqa: PLC0415
        import firebase_admin.storage as fb_storage  # noqa: PLC0415

        bucket = fb_storage.bucket()
        blob = bucket.blob(key)
        return blob.generate_signed_url(
            expiration=datetime.timedelta(seconds=expires_in),
            method="GET",
        )
    except Exception as exc:
        logger.error("Firebase signed URL failed: %s", exc, exc_info=True)
        raise
