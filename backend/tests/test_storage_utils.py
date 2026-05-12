import importlib
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _clear_storage_env(monkeypatch):
    for key in [
        "STORAGE_BACKEND",
        "CF_R2_ENDPOINT",
        "CF_R2_ACCESS_KEY_ID",
        "CF_R2_SECRET_ACCESS_KEY",
        "CF_R2_BUCKET",
        "CF_R2_PUBLIC_URL",
        "CLOUDFLARE_R2_ENDPOINT",
        "CLOUDFLARE_R2_ACCESS_KEY_ID",
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY",
        "CLOUDFLARE_R2_BUCKET_NAME",
        "CLOUDFLARE_CDN_DOMAIN",
        "CLOUDFLARE_ACCOUNT_ID",
    ]:
        monkeypatch.delenv(key, raising=False)


def _reload_storage():
    sys.modules.pop("utils.storage", None)
    return importlib.import_module("utils.storage")


def test_legacy_cloudflare_env_aliases_enable_r2(monkeypatch):
    _clear_storage_env(monkeypatch)
    monkeypatch.setenv("CLOUDFLARE_R2_ENDPOINT", "https://abc123.r2.cloudflarestorage.com")
    monkeypatch.setenv("CLOUDFLARE_R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("CLOUDFLARE_R2_BUCKET_NAME", "socialentangler-media")
    monkeypatch.setenv("CLOUDFLARE_CDN_DOMAIN", "media.unravler.com")

    storage = _reload_storage()

    assert storage.get_storage_backend() == "r2"
    assert (
        storage.build_public_url("uploads/user_123/file.mp4")
        == "https://media.unravler.com/uploads/user_123/file.mp4"
    )


def test_extract_object_key_handles_custom_domain_and_bucket_endpoint(monkeypatch):
    _clear_storage_env(monkeypatch)
    monkeypatch.setenv("CF_R2_ENDPOINT", "https://abc123.r2.cloudflarestorage.com")
    monkeypatch.setenv("CF_R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("CF_R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("CF_R2_BUCKET", "socialentangler-media")
    monkeypatch.setenv("CF_R2_PUBLIC_URL", "https://media.unravler.com")

    storage = _reload_storage()

    assert (
        storage.extract_object_key("https://media.unravler.com/uploads/u1/demo.jpg")
        == "uploads/u1/demo.jpg"
    )
    assert (
        storage.extract_object_key(
            "https://abc123.r2.cloudflarestorage.com/socialentangler-media/uploads/u1/demo.jpg"
        )
        == "uploads/u1/demo.jpg"
    )


def test_is_managed_storage_url_only_matches_configured_r2_urls(monkeypatch):
    _clear_storage_env(monkeypatch)
    monkeypatch.setenv("CF_R2_ENDPOINT", "https://abc123.r2.cloudflarestorage.com")
    monkeypatch.setenv("CF_R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("CF_R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("CF_R2_BUCKET", "socialentangler-media")
    monkeypatch.setenv("CF_R2_PUBLIC_URL", "https://media.unravler.com")

    storage = _reload_storage()

    assert storage.is_managed_storage_url("https://media.unravler.com/uploads/u1/demo.jpg") is True
    assert storage.is_managed_storage_url(
        "https://abc123.r2.cloudflarestorage.com/socialentangler-media/uploads/u1/demo.jpg"
    ) is True
    assert storage.is_managed_storage_url("https://example.com/uploads/u1/demo.jpg") is False
