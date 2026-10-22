"""
Structured, secret-safe logging helpers for the Outreach subsystem.
"""
import logging
from typing import Any

from utils.log_scrub import LogScrubFilter
from utils.observability import event_log
from utils.request_context import get_trace_id


def get_outreach_logger(name: str) -> logging.Logger:
    """Return a stdlib logger pre-attached with LogScrubFilter."""
    log = logging.getLogger(name)
    if not any(isinstance(f, LogScrubFilter) for f in log.filters):
        log.addFilter(LogScrubFilter())
    return log


def log_outreach_event(
    logger: logging.Logger,
    level: str,
    event: str,
    *,
    error: BaseException | None = None,
    **fields: Any,
) -> None:
    """
    Emit a structured outreach log entry with trace_id correlation and
    sanitized exception metadata (never raw secret-bearing exception strings).
    """
    safe_fields: dict[str, Any] = {}
    trace_id = fields.pop("trace_id", None) or get_trace_id()
    if trace_id:
        safe_fields["trace_id"] = trace_id
    if error is not None:
        safe_fields["error_type"] = type(error).__name__
    for key, val in fields.items():
        if val is not None:
            safe_fields[key] = LogScrubFilter._scrub_value(val)
    event_log(logger, level, event, **safe_fields)
