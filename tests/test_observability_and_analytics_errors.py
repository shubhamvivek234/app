import json
import logging

from fastapi import HTTPException

from api.routes.analytics import _analytics_error_message
from utils.observability import JsonFormatter


def test_analytics_error_message_prefers_http_exception_detail():
    exc = HTTPException(status_code=400, detail="Unable to fetch YouTube Analytics API metrics for this account right now.")

    message = _analytics_error_message("youtube", exc)

    assert message == "Unable to fetch YouTube Analytics API metrics for this account right now."


def test_json_formatter_handles_malformed_httpx_style_log_record():
    formatter = JsonFormatter(service_name="test-service")
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='HTTP Request: %s %s "%s %d %s"',
        args=("GET", "https://example.com", "HTTP/1.1", "200", "OK"),
        exc_info=None,
    )

    payload = json.loads(formatter.format(record))

    assert payload["logger"] == "httpx"
    assert "HTTP Request" in payload["message"]
    assert "args=" in payload["message"]
