"""
Phase 0.11 — PII scrubbing logging filter.
Strips access_token, refresh_token, Authorization Bearer, and email addresses
from all log output before writing. Apply to ALL loggers.
"""
import re
import logging

_PATTERNS = [
    # OAuth tokens (key=value style)
    (re.compile(r'(access_token["\s:=]+)[^\s"&,}]{10,}', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(refresh_token["\s:=]+)[^\s"&,}]{10,}', re.IGNORECASE), r'\1[REDACTED]'),
    # Authorization header
    (re.compile(r'(Authorization:\s*Bearer\s+)\S+', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(Bearer\s+)[A-Za-z0-9\-_\.]{20,}', re.IGNORECASE), r'\1[REDACTED]'),
    # Email addresses
    (re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'), '[EMAIL]'),
    # Generic token-like fields in JSON
    (re.compile(r'("token"\s*:\s*")[^"]{10,}(")', re.IGNORECASE), r'\1[REDACTED]\2'),
    (re.compile(r'("password"\s*:\s*")[^"]{1,}(")', re.IGNORECASE), r'\1[REDACTED]\2'),
    (re.compile(r'("secret"\s*:\s*")[^"]{1,}(")', re.IGNORECASE), r'\1[REDACTED]\2'),
]


class LogScrubFilter(logging.Filter):
    """Attach to handlers/loggers to sanitise sensitive data before emission."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._scrub(str(record.msg))
        record.args = tuple(self._scrub(str(a)) for a in record.args) if record.args else record.args
        return True

    @staticmethod
    def _scrub(text: str) -> str:
        for pattern, replacement in _PATTERNS:
            text = pattern.sub(replacement, text)
        return text


def apply_scrub_filter(logger_name: str | None = None) -> None:
    """
    Apply the scrub filter to a named logger (or root logger if None).
    Call once at application startup.
    """
    target = logging.getLogger(logger_name)
    target.addFilter(LogScrubFilter())


def configure_scrubbing() -> None:
    """Apply scrub filter to root logger — catches all log output."""
    apply_scrub_filter(None)
