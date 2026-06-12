import os
from urllib.parse import urlencode, urlparse


DEFAULT_FRONTEND_URL = "https://www.unravler.com"


def resolve_frontend_base_url(raw: str | None = None, *, default: str = DEFAULT_FRONTEND_URL) -> str:
    candidate = (raw if raw is not None else os.environ.get("FRONTEND_URL") or default).strip()
    if not candidate:
        return default

    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    host = (parsed.hostname or "").lower()

    if host in {"unravler.com", "www.unravler.com"}:
        return default
    if host.endswith(".vercel.app"):
        return default

    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or parsed.path
    return f"{scheme}://{netloc}".rstrip("/")


def build_frontend_url(
    path: str,
    *,
    query: dict[str, str] | None = None,
    raw_base_url: str | None = None,
    default: str = DEFAULT_FRONTEND_URL,
) -> str:
    base = resolve_frontend_base_url(raw_base_url, default=default)
    url = f"{base.rstrip('/')}{path}"
    if query:
        encoded = urlencode({key: value for key, value in query.items() if value})
        if encoded:
            url = f"{url}?{encoded}"
    return url
