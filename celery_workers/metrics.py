"""
Phase 4 — Prometheus custom metrics for Celery workers.
Exposes queue depth, task success/failure rates, and platform-level publish metrics.
Scraped by the Prometheus pushgateway from worker containers.
"""
from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, push_to_gateway
import os
import logging

logger = logging.getLogger(__name__)

# ── Registry ─────────────────────────────────────────────────────────────────
# Use default registry so metrics are exported via /metrics if instrumentator
# is attached, or pushed via pushgateway from worker processes.
REGISTRY = CollectorRegistry()

# ── Counters ──────────────────────────────────────────────────────────────────
publish_attempts_total = Counter(
    "socialentangler_publish_attempts_total",
    "Total publish task attempts, labelled by platform and outcome",
    ["platform", "outcome"],   # outcome: success | failure | dlq | retry
    registry=REGISTRY,
)

platform_api_errors_total = Counter(
    "socialentangler_platform_api_errors_total",
    "Platform API errors by error class",
    ["platform", "error_class"],   # error_class: TRANSIENT | PERMANENT | RATE_LIMITED
    registry=REGISTRY,
)

webhook_events_total = Counter(
    "socialentangler_webhook_events_total",
    "Inbound webhook events by platform and status",
    ["platform", "status"],   # status: accepted | duplicate | invalid_signature
    registry=REGISTRY,
)

token_refreshes_total = Counter(
    "socialentangler_token_refreshes_total",
    "Token refresh attempts by platform and outcome",
    ["platform", "outcome"],   # outcome: success | failure
    registry=REGISTRY,
)

# ── Gauges ────────────────────────────────────────────────────────────────────
queue_depth = Gauge(
    "socialentangler_queue_depth",
    "Current approximate message count per Celery queue",
    ["queue_name"],
    registry=REGISTRY,
)

circuit_breaker_state = Gauge(
    "socialentangler_circuit_breaker_state",
    "Circuit breaker state per platform (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
    ["platform"],
    registry=REGISTRY,
)

dlq_depth = Gauge(
    "socialentangler_dlq_depth",
    "Current number of messages in the dead-letter queue",
    [],
    registry=REGISTRY,
)

# ── Histograms ────────────────────────────────────────────────────────────────
publish_duration_seconds = Histogram(
    "socialentangler_publish_duration_seconds",
    "End-to-end publish task duration in seconds",
    ["platform"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60, 120, 300],
    registry=REGISTRY,
)

media_processing_seconds = Histogram(
    "socialentangler_media_processing_seconds",
    "Media validation + transcoding duration",
    ["media_type"],   # media_type: image | video | gif
    buckets=[1, 5, 15, 30, 60, 120, 300, 600],
    registry=REGISTRY,
)

# ── State helpers ─────────────────────────────────────────────────────────────
_CB_STATE_MAP = {"CLOSED": 0, "OPEN": 1, "HALF_OPEN": 2}


def record_circuit_breaker(platform: str, state: str) -> None:
    """Update circuit breaker gauge. State must be CLOSED/OPEN/HALF_OPEN."""
    circuit_breaker_state.labels(platform=platform).set(
        _CB_STATE_MAP.get(state, 0)
    )


def push_metrics() -> None:
    """Push all metrics to the Prometheus Pushgateway (for worker processes)."""
    gateway = os.getenv("PROMETHEUS_PUSHGATEWAY_URL")
    if not gateway:
        return
    job_name = os.getenv("PROMETHEUS_JOB_NAME", "celery_worker")
    try:
        push_to_gateway(gateway, job=job_name, registry=REGISTRY)
    except Exception as exc:
        logger.warning("Failed to push metrics to Pushgateway: %s", exc)
