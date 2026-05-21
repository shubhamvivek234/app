"""Shared logging and non-fatal error capture helpers."""

import json
import logging
import os
import threading
import time
from datetime import datetime, date
from decimal import Decimal
from typing import Any

import sentry_sdk

from utils.request_context import get_trace_id

_EVENT_LOCK = threading.Lock()
_LAST_EVENT_AT: dict[str, float] = {}


def _serialize(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple, set)):
        return [_serialize(item) for item in value]
    if isinstance(value, Exception):
        return {"type": type(value).__name__, "message": str(value)}
    return str(value)


def event_log(
    logger: logging.Logger,
    level: str,
    event: str,
    /,
    *,
    exc_info: Any = None,
    **fields: Any,
) -> None:
    payload = {"event": event}
    trace_id = fields.pop("trace_id", None) or get_trace_id()
    if trace_id:
        payload["trace_id"] = trace_id
    for key, value in fields.items():
        if value is not None:
            payload[key] = _serialize(value)
    log_kwargs: dict[str, Any] = {}
    if exc_info is not None:
        log_kwargs["exc_info"] = exc_info
    getattr(logger, level.lower())(payload, **log_kwargs)


def rate_limited_event_log(
    logger: logging.Logger,
    level: str,
    event: str,
    *,
    dedupe_key: str,
    interval_seconds: int = 300,
    **fields: Any,
) -> bool:
    now = time.monotonic()
    with _EVENT_LOCK:
        previous = _LAST_EVENT_AT.get(dedupe_key, 0.0)
        if previous and now - previous < interval_seconds:
            return False
        _LAST_EVENT_AT[dedupe_key] = now
    event_log(logger, level, event, **fields)
    return True


def sentry_enabled() -> bool:
    return bool(os.getenv("SENTRY_DSN"))


def capture_degraded_event(message: str, **fields: Any) -> None:
    if not sentry_enabled():
        return
    with sentry_sdk.push_scope() as scope:
        for key, value in fields.items():
            if value is not None:
                scope.set_extra(key, _serialize(value))
        trace_id = get_trace_id()
        if trace_id:
            scope.set_tag("trace_id", trace_id)
        scope.level = "warning"
        sentry_sdk.capture_message(message, level="warning")


def shorten_provider_error(value: Any, limit: int = 220) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit - 3]}..."


class JsonFormatter(logging.Formatter):
    """Emit plain stdlib logs as JSON, including request trace context."""

    def __init__(self, *, service_name: str | None = None) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "level": record.levelname.lower(),
            "logger": record.name,
        }
        if self.service_name:
            payload["service"] = self.service_name
        trace_id = get_trace_id()
        if trace_id:
            payload["trace_id"] = trace_id

        if isinstance(record.msg, dict):
            payload.update(_serialize(record.msg))
        else:
            try:
                payload["message"] = record.getMessage()
            except Exception:
                fallback_message = str(record.msg)
                if record.args:
                    fallback_message = f"{fallback_message} | args={_serialize(record.args)}"
                payload["message"] = fallback_message

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload["exception"] = record.exc_text

        return json.dumps(payload, ensure_ascii=True, default=_serialize)
