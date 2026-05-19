"""
Phase 0.11 — PII scrubbing logging filter.
Strips access_token, refresh_token, Authorization Bearer, and email addresses
from all log output before writing. Apply to emitted handlers so child loggers
inherit the same redaction behavior.
"""
import re
import logging
from collections.abc import Mapping, Sequence

_PATTERNS = [
    # OAuth tokens (key=value style)
    (re.compile(r'([\'"]?access_token[\'"]?[\s:=]+)[^\s"\',&}]{10,}', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'([\'"]?refresh_token[\'"]?[\s:=]+)[^\s"\',&}]{10,}', re.IGNORECASE), r'\1[REDACTED]'),
    # Authorization header
    (re.compile(r'(Authorization:\s*Bearer\s+)\S+', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(Bearer\s+)[A-Za-z0-9\-_\.]{20,}', re.IGNORECASE), r'\1[REDACTED]'),
    # Email addresses
    (re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'), '[EMAIL]'),
    # Generic token-like fields in JSON
    (re.compile(r'([\'"]token[\'"]\s*:\s*[\'"])[^\'"]{10,}([\'"])', re.IGNORECASE), r'\1[REDACTED]\2'),
    (re.compile(r'([\'"]password[\'"]\s*:\s*[\'"])[^\'"]+([\'"])', re.IGNORECASE), r'\1[REDACTED]\2'),
    (re.compile(r'([\'"]secret[\'"]\s*:\s*[\'"])[^\'"]+([\'"])', re.IGNORECASE), r'\1[REDACTED]\2'),
]
_SENSITIVE_KEYS = {
    "access_token",
    "refresh_token",
    "token",
    "id_token",
    "authorization",
    "password",
    "secret",
    "client_secret",
    "api_key",
    "key",
}


class LogScrubFilter(logging.Filter):
    """Attach to handlers/loggers to sanitise sensitive data before emission."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._scrub_value(record.msg)
        record.args = self._scrub_args(record.args)
        return True

    @staticmethod
    def _scrub(text: str) -> str:
        for pattern, replacement in _PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    @classmethod
    def _scrub_value(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            return cls._scrub(value)
        if isinstance(value, Mapping):
            scrubbed = {}
            for key, item in value.items():
                key_text = str(key)
                if key_text.lower() in _SENSITIVE_KEYS:
                    scrubbed[key] = "[REDACTED]"
                else:
                    scrubbed[key] = cls._scrub_value(item)
            return scrubbed
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
            scrubbed = [cls._scrub_value(item) for item in value]
            return type(value)(scrubbed) if not isinstance(value, tuple) else tuple(scrubbed)
        return cls._scrub(str(value))

    @classmethod
    def _scrub_args(cls, args):
        if not args:
            return args
        if isinstance(args, dict):
            return {k: cls._scrub_value(v) for k, v in args.items()}
        if isinstance(args, tuple):
            return tuple(cls._scrub_value(a) for a in args)
        return args


def attach_scrub_filter(handler: logging.Handler) -> None:
    """Attach the scrub filter to a handler once."""
    if any(isinstance(existing, LogScrubFilter) for existing in handler.filters):
        return
    handler.addFilter(LogScrubFilter())


def apply_scrub_filter(logger_name: str | None = None) -> None:
    """
    Apply the scrub filter to a named logger (or root logger if None).
    Call once at application startup.
    """
    target = logging.getLogger(logger_name)
    for handler in target.handlers:
        attach_scrub_filter(handler)
    if not any(isinstance(existing, LogScrubFilter) for existing in target.filters):
        target.addFilter(LogScrubFilter())


def configure_scrubbing() -> None:
    """Apply scrub filter to root logger handlers — catches propagated log output."""
    apply_scrub_filter(None)
