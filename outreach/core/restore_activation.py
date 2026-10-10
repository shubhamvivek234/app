"""Offline restore review helpers; no database transaction or activation path.

Caller assertions and input digests are review material only. The installed
restore_epoch.positive gate continues to deny all restored execution.
"""
from __future__ import annotations

from typing import Any

from outreach.core.authorization import canonical_hash
from outreach.core.restore_reconciliation import (
    GROUPS, ReconciliationError, _digest, _reference, bounded_json,
)

PLAN_FIELDS = {
    "workspace_id", "current_epoch", "new_epoch", "review_digest", "reconciliation_digest",
    "control_assertions", "input_checks_passed", "reactivation_ready", "activation_allowed", "blockers",
}


def _valid_digest(value: Any) -> bool:
    try:
        _digest(value, "digest")
        return True
    except ReconciliationError:
        return False


def _valid_reference(value: Any) -> bool:
    try:
        _reference(value, "reference")
        return True
    except ReconciliationError:
        return False


def plan_reactivation(*, reconciliation: dict[str, Any], current_epoch: str | None,
                      new_epoch: str, review_digest: str, workers_drained: bool,
                      flags_off: bool, operator_confirmed: bool) -> dict[str, Any]:
    """Check offline input consistency without certifying restart readiness."""
    errors: list[str] = []
    try:
        result = bounded_json(reconciliation)
        if not isinstance(result, dict):
            raise ReconciliationError("Reconciliation result must be an object")
    except ReconciliationError:
        result = {}
        errors.append("reconciliation_malformed")
    if not _valid_digest(current_epoch):
        errors.append("current_epoch_invalid")
    if not _valid_digest(new_epoch):
        errors.append("new_epoch_invalid")
    if new_epoch == current_epoch:
        errors.append("new_epoch_reuses_current_epoch")
    if not _valid_digest(review_digest):
        errors.append("review_digest_invalid")
    elif review_digest != canonical_hash(result):
        errors.append("review_digest_mismatch")
    assertions = {"workers_drained": workers_drained is True, "flags_off": flags_off is True,
                  "operator_confirmed": operator_confirmed is True}
    for field, valid in assertions.items():
        if not valid:
            errors.append(field + "_assertion_missing_or_malformed")
    if not _valid_reference(result.get("workspace_id")):
        errors.append("reconciliation_workspace_invalid")
    if result.get("execution_epoch") != current_epoch:
        errors.append("reconciliation_epoch_mismatch")
    for field in ("outside_backup_integrity_verified", "artifact_signer_verified", "selected_metadata_matches"):
        if result.get(field) is not True:
            errors.append(field + "_missing")
    groups = result.get("group_matches")
    if not isinstance(groups, dict) or set(groups) != set(GROUPS) or any(value is not True for value in groups.values()):
        errors.append("selected_groups_not_matched")
    for field in ("manifest_digest", "local_metadata_digest"):
        if not _valid_digest(result.get(field)):
            errors.append(field + "_invalid")
    if result.get("completeness_verified") is not False or result.get("activation_allowed") is not False:
        errors.append("unsupported_positive_reconciliation_claim")
    reviews = result.get("external_review_required")
    if not isinstance(reviews, list) or any(not _valid_reference(item) for item in reviews):
        reviews = []
        errors.append("external_reviews_malformed")
    plan = {
        "workspace_id": result.get("workspace_id") if _valid_reference(result.get("workspace_id")) else None,
        "current_epoch": current_epoch if _valid_digest(current_epoch) else None,
        "new_epoch": new_epoch if _valid_digest(new_epoch) else None,
        "review_digest": review_digest if _valid_digest(review_digest) else None,
        "reconciliation_digest": canonical_hash(result), "control_assertions": assertions,
        "input_checks_passed": not errors, "reactivation_ready": False, "activation_allowed": False,
        "blockers": sorted(set(errors + reviews + ["transactional_activation_unimplemented", "live_verification_required"])),
    }
    return {**plan, "plan_digest": canonical_hash(plan)}


def rehearse_transaction(*, plan: dict[str, Any], stopped_root: dict[str, Any],
                         authorities: list[dict[str, Any]]) -> dict[str, Any]:
    """Legacy name for an offline input review; no transaction is exercised.

    Validating supplied dictionaries cannot detect concurrent writes or prove
    the database root, credentials, authority coverage, or a fleet drain.
    """
    errors: list[str] = []
    try:
        supplied = bounded_json({"plan": plan, "root": stopped_root, "authorities": authorities})
    except ReconciliationError:
        supplied = {"plan": {}, "root": {}, "authorities": []}
        errors.append("review_input_malformed_or_unbounded")
    selected_plan, root, rows = supplied["plan"], supplied["root"], supplied["authorities"]
    if not isinstance(selected_plan, dict):
        selected_plan = {}
    digest = selected_plan.get("plan_digest")
    payload = {key: value for key, value in selected_plan.items() if key != "plan_digest"}
    assertions = selected_plan.get('control_assertions')
    blockers = selected_plan.get('blockers')
    if (set(payload) != PLAN_FIELDS or not _valid_digest(digest) or canonical_hash(payload) != digest
            or selected_plan.get("input_checks_passed") is not True
            or selected_plan.get("activation_allowed") is not False
            or selected_plan.get("reactivation_ready") is not False
            or not _valid_digest(selected_plan.get("current_epoch"))
            or not _valid_digest(selected_plan.get("new_epoch"))
            or selected_plan.get('current_epoch') == selected_plan.get('new_epoch')
            or not _valid_digest(selected_plan.get('review_digest'))
            or not _valid_digest(selected_plan.get('reconciliation_digest'))
            or selected_plan.get('review_digest') != selected_plan.get('reconciliation_digest')
            or not isinstance(assertions, dict)
            or set(assertions) != {'workers_drained', 'flags_off', 'operator_confirmed'}
            or any(value is not True for value in assertions.values())
            or not isinstance(blockers, list) or any(not _valid_reference(item) for item in blockers)
            or 'transactional_activation_unimplemented' not in blockers
            or 'live_verification_required' not in blockers
            or not _valid_reference(selected_plan.get("workspace_id"))):
        errors.append("offline_plan_invalid_or_changed")
    if (not isinstance(root, dict) or set(root) != {"workspace_id", "status", "execution_epoch"}
            or root.get("status") != "prepared_stopped"
            or root.get("workspace_id") != selected_plan.get("workspace_id")
            or root.get("execution_epoch") != selected_plan.get("current_epoch")):
        errors.append("stopped_root_inputs_invalid_or_changed")
    if not isinstance(rows, list) or not rows:
        rows = []
        errors.append("authority_inputs_empty_or_malformed")
    seen = set()
    for index, row in enumerate(rows):
        if (not isinstance(row, dict) or set(row) != {"record_id", "workspace_id", "status", "review_digest", "credential_generation"}
                or not _valid_reference(row.get("record_id"))
                or not _valid_reference(row.get("credential_generation"))):
            errors.append(f"authority_{index}_malformed")
            continue
        if row["record_id"] in seen:
            errors.append("authority_identity_ambiguous")
        seen.add(row["record_id"])
        if row["workspace_id"] != selected_plan.get("workspace_id"):
            errors.append(f"authority_{index}_scope_changed")
        if row["status"] not in ("stopped", "paused", "review_stopped"):
            errors.append(f"authority_{index}_not_stopped")
        if row["review_digest"] != selected_plan.get("review_digest"):
            errors.append(f"authority_{index}_review_changed")
    return {
        "input_checks_passed": not errors,
        "rehearsal_passed": False, "transaction_exercised": False,
        "committed": False, "activation_allowed": False,
        "blockers": sorted(set(errors + ["database_rehearsal_unimplemented"])),
        "receipt_digest": canonical_hash({"inputs": supplied, "errors": sorted(set(errors))}),
    }
