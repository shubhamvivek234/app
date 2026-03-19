"""
Phase 9.5.1 -- SOC 2 Type I Control Mapping.

Maps SOC 2 Trust Services Criteria to SocialEntangler controls.
Each control is an immutable dataclass with evidence collection instructions
and references to the implementing module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ControlStatus(str, Enum):
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    PLANNED = "planned"
    NOT_APPLICABLE = "n/a"


class TrustServicesCriteria(str, Enum):
    CC1 = "CC1"  # Control Environment
    CC2 = "CC2"  # Communication and Information
    CC3 = "CC3"  # Risk Assessment
    CC6 = "CC6"  # Logical and Physical Access Controls
    CC7 = "CC7"  # System Operations
    CC8 = "CC8"  # Change Management


@dataclass(frozen=True)
class SOC2Control:
    """Immutable definition of a single SOC 2 control."""

    control_id: str
    criteria: TrustServicesCriteria
    title: str
    description: str
    status: ControlStatus
    implementing_module: str
    evidence_type: str
    evidence_query: str = ""


# ---------------------------------------------------------------------------
# CC1 — Control Environment
# ---------------------------------------------------------------------------

CC1_CONTROLS: tuple[SOC2Control, ...] = (
    SOC2Control(
        control_id="CC1.1",
        criteria=TrustServicesCriteria.CC1,
        title="Multi-Factor Authentication",
        description="All users with admin or owner roles must have MFA enabled.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="utils.mfa",
        evidence_type="db_query",
        evidence_query="users with role in (owner, admin) and mfa_enabled == True",
    ),
    SOC2Control(
        control_id="CC1.2",
        criteria=TrustServicesCriteria.CC1,
        title="Role-Based Access Control",
        description="Access restricted by workspace role: Owner > Admin > Editor > Viewer > Client.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="utils.roles",
        evidence_type="code_review",
        evidence_query="WorkspaceRole enum and _ROLE_PERMISSIONS mapping",
    ),
    SOC2Control(
        control_id="CC1.3",
        criteria=TrustServicesCriteria.CC1,
        title="Session Management",
        description="Sessions expire after inactivity, concurrent sessions limited.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="utils.session",
        evidence_type="config_check",
        evidence_query="SESSION_TIMEOUT and MAX_CONCURRENT_SESSIONS settings",
    ),
)

# ---------------------------------------------------------------------------
# CC2 — Communication and Information
# ---------------------------------------------------------------------------

CC2_CONTROLS: tuple[SOC2Control, ...] = (
    SOC2Control(
        control_id="CC2.1",
        criteria=TrustServicesCriteria.CC2,
        title="Audit Trail",
        description="All significant actions recorded in audit_events collection with 90-day retention.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="utils.audit",
        evidence_type="db_query",
        evidence_query="audit_events collection with TTL index",
    ),
    SOC2Control(
        control_id="CC2.2",
        criteria=TrustServicesCriteria.CC2,
        title="Notification System",
        description="Users notified of security-relevant events (MFA changes, role changes, login anomalies).",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="utils.notification_prefs",
        evidence_type="code_review",
        evidence_query="notification preferences and delivery channels",
    ),
)

# ---------------------------------------------------------------------------
# CC3 — Risk Assessment
# ---------------------------------------------------------------------------

CC3_CONTROLS: tuple[SOC2Control, ...] = (
    SOC2Control(
        control_id="CC3.1",
        criteria=TrustServicesCriteria.CC3,
        title="Circuit Breaker",
        description="Per-platform circuit breaker prevents cascade failures on API outages.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="utils.circuit_breaker",
        evidence_type="redis_check",
        evidence_query="circuit:{platform}:state keys",
    ),
    SOC2Control(
        control_id="CC3.2",
        criteria=TrustServicesCriteria.CC3,
        title="Rate Limiting",
        description="Token-bucket rate limiting per social account per platform.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="utils.rate_limit",
        evidence_type="redis_check",
        evidence_query="ratelimit:{platform}:{account}:tokens keys",
    ),
    SOC2Control(
        control_id="CC3.3",
        criteria=TrustServicesCriteria.CC3,
        title="SSRF Prevention",
        description="Outbound requests validated against SSRF guard to prevent internal network access.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="utils.ssrf_guard",
        evidence_type="code_review",
        evidence_query="SSRF guard middleware blocking private IP ranges",
    ),
)

# ---------------------------------------------------------------------------
# CC6 — Logical and Physical Access Controls
# ---------------------------------------------------------------------------

CC6_CONTROLS: tuple[SOC2Control, ...] = (
    SOC2Control(
        control_id="CC6.1",
        criteria=TrustServicesCriteria.CC6,
        title="Firebase Authentication",
        description="All API endpoints require valid Firebase JWT token.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="backend.auth",
        evidence_type="code_review",
        evidence_query="Firebase token verification middleware",
    ),
    SOC2Control(
        control_id="CC6.2",
        criteria=TrustServicesCriteria.CC6,
        title="API Key Authentication",
        description="Headless API access via scoped API keys with rate limiting.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="backend.api_keys",
        evidence_type="db_query",
        evidence_query="api_keys collection with scopes and expiry",
    ),
    SOC2Control(
        control_id="CC6.3",
        criteria=TrustServicesCriteria.CC6,
        title="Role Permission Matrix",
        description="Fine-grained permissions mapped to workspace roles.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="utils.roles",
        evidence_type="code_review",
        evidence_query="_ROLE_PERMISSIONS dict in utils/roles.py",
    ),
    SOC2Control(
        control_id="CC6.4",
        criteria=TrustServicesCriteria.CC6,
        title="Token Encryption at Rest",
        description="Social account tokens encrypted with AES-256 (Fernet) before storage.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="utils.encryption",
        evidence_type="config_check",
        evidence_query="ENCRYPTION_KEY env var and Fernet cipher usage",
    ),
)

# ---------------------------------------------------------------------------
# CC7 — System Operations
# ---------------------------------------------------------------------------

CC7_CONTROLS: tuple[SOC2Control, ...] = (
    SOC2Control(
        control_id="CC7.1",
        criteria=TrustServicesCriteria.CC7,
        title="Application Monitoring",
        description="SLO-based monitoring with Prometheus metrics and Grafana dashboards.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="config.slo",
        evidence_type="config_check",
        evidence_query="SLO_TARGETS definitions and Prometheus queries",
    ),
    SOC2Control(
        control_id="CC7.2",
        criteria=TrustServicesCriteria.CC7,
        title="Alerting",
        description="Alerts configured for SLO breaches, circuit breaker trips, and DLQ growth.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="config.alerting",
        evidence_type="config_check",
        evidence_query="Alerting rules in config/alerting/",
    ),
    SOC2Control(
        control_id="CC7.3",
        criteria=TrustServicesCriteria.CC7,
        title="Dead Letter Queue Handling",
        description="Failed publishes moved to DLQ for manual review with monitoring.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="celery_workers",
        evidence_type="db_query",
        evidence_query="dead_letter_queue collection entries",
    ),
)

# ---------------------------------------------------------------------------
# CC8 — Change Management
# ---------------------------------------------------------------------------

CC8_CONTROLS: tuple[SOC2Control, ...] = (
    SOC2Control(
        control_id="CC8.1",
        criteria=TrustServicesCriteria.CC8,
        title="CI/CD Pipeline",
        description="All changes go through automated CI with tests, linting, and security scanning.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="ci/cd",
        evidence_type="git_check",
        evidence_query="GitHub Actions workflow with required checks",
    ),
    SOC2Control(
        control_id="CC8.2",
        criteria=TrustServicesCriteria.CC8,
        title="Security Scanning",
        description="Dependency vulnerability scanning and secret detection in CI pipeline.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="ci/cd",
        evidence_type="git_check",
        evidence_query="pip-audit and secret scanning steps in CI",
    ),
    SOC2Control(
        control_id="CC8.3",
        criteria=TrustServicesCriteria.CC8,
        title="Pull Request Reviews",
        description="All changes require PR review before merge to main.",
        status=ControlStatus.IMPLEMENTED,
        implementing_module="git",
        evidence_type="git_check",
        evidence_query="Branch protection rules requiring approvals",
    ),
)

# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

ALL_CONTROLS: tuple[SOC2Control, ...] = (
    *CC1_CONTROLS,
    *CC2_CONTROLS,
    *CC3_CONTROLS,
    *CC6_CONTROLS,
    *CC7_CONTROLS,
    *CC8_CONTROLS,
)

CONTROLS_BY_CRITERIA: dict[TrustServicesCriteria, tuple[SOC2Control, ...]] = {
    TrustServicesCriteria.CC1: CC1_CONTROLS,
    TrustServicesCriteria.CC2: CC2_CONTROLS,
    TrustServicesCriteria.CC3: CC3_CONTROLS,
    TrustServicesCriteria.CC6: CC6_CONTROLS,
    TrustServicesCriteria.CC7: CC7_CONTROLS,
    TrustServicesCriteria.CC8: CC8_CONTROLS,
}


def get_controls_summary() -> dict[str, Any]:
    """Return a summary of all controls grouped by criteria and status."""
    summary: dict[str, Any] = {
        "total_controls": len(ALL_CONTROLS),
        "by_status": {},
        "by_criteria": {},
    }

    status_counts: dict[str, int] = {}
    for control in ALL_CONTROLS:
        status_counts[control.status.value] = status_counts.get(control.status.value, 0) + 1
    summary["by_status"] = dict(status_counts)

    for criteria, controls in CONTROLS_BY_CRITERIA.items():
        summary["by_criteria"][criteria.value] = {
            "count": len(controls),
            "controls": [
                {
                    "id": c.control_id,
                    "title": c.title,
                    "status": c.status.value,
                }
                for c in controls
            ],
        }

    return summary
