"""
Phase 5.8.1 -- SLO Definitions for SocialEntangler.

Each SLO target is defined as a dataclass with a Prometheus query, threshold,
comparator, and human-readable description.  ``evaluate_slo()`` evaluates every
SLO against a live Prometheus instance and returns per-SLO pass/fail results.
"""
from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)

PROMETHEUS_URL = "http://localhost:9090"


class Comparator(str, enum.Enum):
    LESS_THAN = "lt"
    GREATER_THAN = "gt"


@dataclass(frozen=True)
class SLOTarget:
    """Immutable definition of a single SLO."""

    name: str
    description: str
    prometheus_query: str
    threshold: float
    comparator: Comparator
    unit: str = ""

    def passes(self, value: float) -> bool:
        if self.comparator is Comparator.LESS_THAN:
            return value < self.threshold
        return value > self.threshold


@dataclass(frozen=True)
class SLOResult:
    """Immutable result of evaluating one SLO."""

    slo: SLOTarget
    current_value: float | None
    passed: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# SLO Targets
# ---------------------------------------------------------------------------

SLO_TARGETS: tuple[SLOTarget, ...] = (
    SLOTarget(
        name="api_p99_latency",
        description="API p99 latency < 500ms",
        prometheus_query=(
            'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))'
        ),
        threshold=0.5,
        comparator=Comparator.LESS_THAN,
        unit="seconds",
    ),
    SLOTarget(
        name="publish_success_rate",
        description="Publish success rate > 99.5%",
        prometheus_query=(
            'sum(rate(publish_success_total[5m])) '
            '/ sum(rate(publish_attempts_total[5m])) * 100'
        ),
        threshold=99.5,
        comparator=Comparator.GREATER_THAN,
        unit="percent",
    ),
    SLOTarget(
        name="webhook_processing_p99",
        description="Webhook processing < 5s p99",
        prometheus_query=(
            'histogram_quantile(0.99, sum(rate(webhook_processing_duration_seconds_bucket[5m])) by (le))'
        ),
        threshold=5.0,
        comparator=Comparator.LESS_THAN,
        unit="seconds",
    ),
    SLOTarget(
        name="token_refresh_success",
        description="Token refresh success rate > 99%",
        prometheus_query=(
            'sum(rate(token_refresh_success_total[5m])) '
            '/ sum(rate(token_refresh_attempts_total[5m])) * 100'
        ),
        threshold=99.0,
        comparator=Comparator.GREATER_THAN,
        unit="percent",
    ),
    SLOTarget(
        name="media_pipeline_p95",
        description="Media pipeline processing < 60s p95",
        prometheus_query=(
            'histogram_quantile(0.95, sum(rate(media_pipeline_duration_seconds_bucket[5m])) by (le))'
        ),
        threshold=60.0,
        comparator=Comparator.LESS_THAN,
        unit="seconds",
    ),
    SLOTarget(
        name="system_uptime",
        description="System uptime 99.9%",
        prometheus_query=(
            'avg_over_time(up[30d]) * 100'
        ),
        threshold=99.9,
        comparator=Comparator.GREATER_THAN,
        unit="percent",
    ),
    SLOTarget(
        name="dlq_drain_time",
        description="DLQ drain < 15 minutes",
        prometheus_query=(
            'max(dlq_oldest_message_age_seconds)'
        ),
        threshold=900.0,
        comparator=Comparator.LESS_THAN,
        unit="seconds",
    ),
)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _query_prometheus(query: str, prometheus_url: str) -> float:
    """Execute an instant query against Prometheus and return scalar value."""
    response = requests.get(
        f"{prometheus_url}/api/v1/query",
        params={"query": query},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("status") != "success":
        raise ValueError(f"Prometheus query failed: {data.get('error', 'unknown')}")

    results = data.get("data", {}).get("result", [])
    if not results:
        raise ValueError("Prometheus query returned no results")

    # Scalar or single-vector result -- take the first value.
    value_pair = results[0].get("value", [None, None])
    raw = value_pair[1]
    if raw is None:
        raise ValueError("Prometheus returned null value")

    return float(raw)


def evaluate_slo(
    *,
    prometheus_url: str = PROMETHEUS_URL,
    targets: tuple[SLOTarget, ...] | None = None,
) -> list[SLOResult]:
    """Evaluate all SLO targets and return a list of results.

    Parameters
    ----------
    prometheus_url:
        Base URL of the Prometheus server.
    targets:
        SLO targets to evaluate.  Defaults to ``SLO_TARGETS``.

    Returns
    -------
    list[SLOResult]
        One result per SLO target with pass/fail status.
    """
    if targets is None:
        targets = SLO_TARGETS

    results: list[SLOResult] = []

    for slo in targets:
        try:
            value = _query_prometheus(slo.prometheus_query, prometheus_url)
            passed = slo.passes(value)
            results.append(SLOResult(slo=slo, current_value=value, passed=passed))
        except Exception as exc:
            logger.warning("SLO evaluation failed for %s: %s", slo.name, exc)
            results.append(
                SLOResult(
                    slo=slo,
                    current_value=None,
                    passed=False,
                    error=str(exc),
                )
            )

    return results


def evaluate_slo_summary(
    *,
    prometheus_url: str = PROMETHEUS_URL,
) -> dict[str, Any]:
    """Return a JSON-serialisable summary of all SLO evaluations."""
    results = evaluate_slo(prometheus_url=prometheus_url)
    all_passed = all(r.passed for r in results)
    return {
        "all_passed": all_passed,
        "total": len(results),
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(1 for r in results if not r.passed),
        "details": [
            {
                "name": r.slo.name,
                "description": r.slo.description,
                "threshold": r.slo.threshold,
                "current_value": r.current_value,
                "unit": r.slo.unit,
                "passed": r.passed,
                "error": r.error,
            }
            for r in results
        ],
    }
