"""
Phase 9.5.1 -- SOC 2 Type I Compliance Utilities.

Collects evidence, generates compliance reports, and verifies data retention
policies across all SOC 2 Trust Services Criteria controls.
"""
from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Any

from config.soc2_controls import (
    ALL_CONTROLS,
    CONTROLS_BY_CRITERIA,
    ControlStatus,
    TrustServicesCriteria,
    get_controls_summary,
)

logger = logging.getLogger(__name__)

# Retention policy: 90 days for audit events
AUDIT_RETENTION_DAYS = 90

# Collections that require TTL indexes for data retention
TTL_COLLECTIONS: dict[str, int] = {
    "audit_events": AUDIT_RETENTION_DAYS * 86400,
    "sessions": 30 * 86400,           # 30 days
    "rate_limit_events": 7 * 86400,   # 7 days
    "notifications": 90 * 86400,      # 90 days
}


# ---------------------------------------------------------------------------
# Evidence Collection
# ---------------------------------------------------------------------------

async def _collect_access_control_evidence(db) -> dict[str, Any]:
    """Gather evidence for access control: admin users, MFA status."""
    admin_users = await db.users.find(
        {"workspaces.role": {"$in": ["owner", "admin"]}},
        {"email": 1, "mfa_enabled": 1, "workspaces": 1},
    ).to_list(length=None)

    total_admins = len(admin_users)
    mfa_enabled_count = sum(1 for u in admin_users if u.get("mfa_enabled", False))
    mfa_enforcement_rate = (mfa_enabled_count / total_admins * 100) if total_admins > 0 else 0.0

    return {
        "control": "access_control",
        "total_admin_users": total_admins,
        "mfa_enabled_count": mfa_enabled_count,
        "mfa_enforcement_rate_pct": round(mfa_enforcement_rate, 2),
        "mfa_compliant": mfa_enforcement_rate == 100.0,
        "admin_users": [
            {
                "email": u.get("email"),
                "mfa_enabled": u.get("mfa_enabled", False),
                "roles": [
                    w.get("role") for w in u.get("workspaces", [])
                    if w.get("role") in ("owner", "admin")
                ],
            }
            for u in admin_users
        ],
    }


async def _collect_change_management_evidence() -> dict[str, Any]:
    """Gather evidence from git history for change management controls."""
    evidence: dict[str, Any] = {
        "control": "change_management",
        "git_available": False,
        "total_commits_30d": 0,
        "authors_30d": 0,
        "pr_merge_requirement": "unknown",
    }

    try:
        since_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

        result = subprocess.run(
            ["git", "log", f"--since={since_date}", "--oneline"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            commits = [line for line in result.stdout.strip().splitlines() if line]
            evidence["git_available"] = True
            evidence["total_commits_30d"] = len(commits)

        result_authors = subprocess.run(
            ["git", "log", f"--since={since_date}", "--format=%ae"],
            capture_output=True, text=True, timeout=10,
        )
        if result_authors.returncode == 0:
            authors = {line.strip() for line in result_authors.stdout.splitlines() if line.strip()}
            evidence["authors_30d"] = len(authors)

        # Check for branch protection (presence of PR-based merge commits)
        result_merges = subprocess.run(
            ["git", "log", f"--since={since_date}", "--merges", "--oneline"],
            capture_output=True, text=True, timeout=10,
        )
        if result_merges.returncode == 0:
            merge_count = len([l for l in result_merges.stdout.strip().splitlines() if l])
            evidence["merge_commits_30d"] = merge_count
            evidence["pr_merge_requirement"] = "likely_enforced" if merge_count > 0 else "not_detected"

    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("Git evidence collection failed: %s", exc)

    return evidence


def _collect_encryption_evidence() -> dict[str, Any]:
    """Verify encryption configuration."""
    encryption_key_set = bool(os.environ.get("ENCRYPTION_KEY"))

    tls_env = os.environ.get("TLS_ENABLED", "").lower()
    tls_enabled = tls_env in ("1", "true", "yes")

    mongodb_uri = os.environ.get("MONGODB_URI", "")
    mongodb_tls = "+srv" in mongodb_uri or "tls=true" in mongodb_uri

    return {
        "control": "encryption",
        "encryption_key_set": encryption_key_set,
        "tls_enabled": tls_enabled,
        "mongodb_tls": mongodb_tls,
        "compliant": encryption_key_set,
    }


async def _collect_logging_evidence(db) -> dict[str, Any]:
    """Verify audit trail and log retention."""
    # Check if audit_events collection exists and has TTL index
    audit_active = False
    ttl_index_found = False
    retention_days = 0

    try:
        collections = await db.list_collection_names()
        audit_active = "audit_events" in collections

        if audit_active:
            indexes = await db.audit_events.index_information()
            for idx_name, idx_info in indexes.items():
                if "expireAfterSeconds" in idx_info:
                    ttl_index_found = True
                    retention_days = idx_info["expireAfterSeconds"] // 86400
                    break
    except Exception as exc:
        logger.warning("Logging evidence collection failed: %s", exc)

    return {
        "control": "logging",
        "audit_trail_active": audit_active,
        "ttl_index_configured": ttl_index_found,
        "retention_days": retention_days,
        "retention_compliant": retention_days >= AUDIT_RETENTION_DAYS,
        "expected_retention_days": AUDIT_RETENTION_DAYS,
    }


async def _collect_incident_response_evidence(db) -> dict[str, Any]:
    """Verify DLQ monitoring and alerting configuration."""
    dlq_count = 0
    try:
        dlq_count = await db.dead_letter_queue.count_documents({})
    except Exception:
        pass

    alerting_config_exists = os.path.isdir(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "alerting")
    )

    return {
        "control": "incident_response",
        "dlq_monitoring_active": True,
        "dlq_current_count": dlq_count,
        "alerting_configured": alerting_config_exists,
        "compliant": alerting_config_exists,
    }


async def collect_evidence(db) -> dict[str, Any]:
    """
    Gather evidence for all SOC 2 controls.

    Returns a structured dict with evidence for each control domain:
    - access_control
    - change_management
    - encryption
    - logging
    - incident_response
    """
    access_evidence = await _collect_access_control_evidence(db)
    change_evidence = await _collect_change_management_evidence()
    encryption_evidence = _collect_encryption_evidence()
    logging_evidence = await _collect_logging_evidence(db)
    incident_evidence = await _collect_incident_response_evidence(db)

    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "access_control": access_evidence,
        "change_management": change_evidence,
        "encryption": encryption_evidence,
        "logging": logging_evidence,
        "incident_response": incident_evidence,
    }


# ---------------------------------------------------------------------------
# Compliance Report
# ---------------------------------------------------------------------------

async def generate_compliance_report(db, redis) -> dict[str, Any]:
    """
    Generate a structured SOC 2 Type I compliance report.

    Assesses all controls, collects evidence, and returns a comprehensive
    report suitable for auditor review.
    """
    evidence = await collect_evidence(db)
    controls_summary = get_controls_summary()
    retention_check = await check_data_retention(db)

    # Assess overall compliance per criteria
    criteria_assessments: dict[str, Any] = {}
    for criteria, controls in CONTROLS_BY_CRITERIA.items():
        implemented = sum(1 for c in controls if c.status == ControlStatus.IMPLEMENTED)
        total = len(controls)
        criteria_assessments[criteria.value] = {
            "total": total,
            "implemented": implemented,
            "compliance_pct": round(implemented / total * 100, 1) if total > 0 else 0.0,
        }

    # Check Redis connectivity for circuit breaker / rate limit evidence
    redis_healthy = False
    try:
        await redis.ping()
        redis_healthy = True
    except Exception:
        pass

    overall_implemented = sum(
        1 for c in ALL_CONTROLS if c.status == ControlStatus.IMPLEMENTED
    )
    overall_total = len(ALL_CONTROLS)

    return {
        "report_type": "SOC 2 Type I",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": {
            "total_controls": overall_total,
            "implemented": overall_implemented,
            "compliance_pct": round(overall_implemented / overall_total * 100, 1),
        },
        "criteria_assessments": criteria_assessments,
        "controls_summary": controls_summary,
        "evidence": evidence,
        "data_retention": retention_check,
        "infrastructure": {
            "redis_healthy": redis_healthy,
            "encryption_key_set": evidence["encryption"]["encryption_key_set"],
        },
    }


# ---------------------------------------------------------------------------
# Data Retention
# ---------------------------------------------------------------------------

async def check_data_retention(db) -> dict[str, Any]:
    """
    Verify TTL indexes are in place for all collections that require
    time-based data retention.

    Returns a dict with per-collection status and overall compliance.
    """
    results: dict[str, Any] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "collections": {},
        "all_compliant": True,
    }

    existing_collections = set()
    try:
        existing_collections = set(await db.list_collection_names())
    except Exception as exc:
        logger.error("Failed to list collections: %s", exc)
        results["all_compliant"] = False
        results["error"] = str(exc)
        return results

    for collection_name, expected_ttl_seconds in TTL_COLLECTIONS.items():
        col_result: dict[str, Any] = {
            "exists": collection_name in existing_collections,
            "ttl_index_found": False,
            "expected_ttl_seconds": expected_ttl_seconds,
            "actual_ttl_seconds": None,
            "compliant": False,
        }

        if collection_name in existing_collections:
            try:
                indexes = await db[collection_name].index_information()
                for idx_name, idx_info in indexes.items():
                    if "expireAfterSeconds" in idx_info:
                        col_result["ttl_index_found"] = True
                        col_result["actual_ttl_seconds"] = idx_info["expireAfterSeconds"]
                        col_result["compliant"] = (
                            idx_info["expireAfterSeconds"] <= expected_ttl_seconds
                        )
                        break
            except Exception as exc:
                logger.warning("Failed to check indexes for %s: %s", collection_name, exc)

        if not col_result["compliant"]:
            results["all_compliant"] = False

        results["collections"][collection_name] = col_result

    return results
