from copy import deepcopy
import base64
from datetime import datetime, timezone

import pytest

from outreach.core.authorization import canonical_hash
from outreach.core.restore_reconciliation import ReconciliationError, verify_manifest, verify_signed_manifest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from outreach.core.restore_activation import plan_reactivation, rehearse_transaction
from outreach.core.restore_reply_evidence import validate as validate_reply_evidence

pytestmark = pytest.mark.restore_epoch


@pytest.fixture(autouse=True)
def fixed_reply_clock(monkeypatch):
    monkeypatch.setattr('outreach.core.restore_reply_evidence.now',
                        lambda: datetime(2026, 10, 10, 12, tzinfo=timezone.utc))


def manifest():
    local = {
        "financial": [{"record_id": "invoice", "state": "review"}],
        "provider_resource": [{"record_id": "proxy", "state": "review"}],
        "reply_evidence": [{"record_id": "thread", "state": "review"}],
    }
    value = {
        "version": 1,
        "workspace_id": "workspace",
        "execution_epoch": "a" * 64,
        "sources": [
            {"source_id": "payment-ledger", "group": "financial", "snapshot_digest": "1" * 64, "evidence_digest": "2" * 64},
            {"source_id": "provider-ledger", "group": "provider_resource", "snapshot_digest": "3" * 64, "evidence_digest": "4" * 64},
            {"source_id": "reply-export", "group": "reply_evidence", "snapshot_digest": "5" * 64, "evidence_digest": "6" * 64},
        ],
        "summaries": {group: {"record_count": len(rows), "metadata_digest": canonical_hash(rows)}
                      for group, rows in local.items()},
        "local_metadata": local,
    }
    return value, canonical_hash(value)


def test_matching_selected_metadata_never_establishes_completeness_or_authority():
    value, digest = manifest()
    result = verify_manifest(value, workspace_id="workspace", execution_epoch="a" * 64,
                             trusted_digest=digest, local_metadata=deepcopy(value['local_metadata']))
    assert result["outside_backup_integrity_verified"]
    assert result["selected_metadata_matches"] and not result["completeness_verified"]
    assert all(result["group_matches"].values())
    assert not result["activation_allowed"]
    assert not result["payment_authenticated"]
    assert not result["provider_ownership_verified"]


@pytest.mark.parametrize("change", ["digest", "workspace", "epoch"])
def test_tampered_manifest_or_scope_is_rejected(change):
    value, digest = manifest()
    tampered = deepcopy(value)
    if change == "digest": tampered["summaries"]["financial"]["record_count"] = 2
    if change == "workspace": tampered["workspace_id"] = "other"
    if change == "epoch": tampered["execution_epoch"] = "b" * 64
    with pytest.raises(ReconciliationError):
        verify_manifest(tampered, workspace_id="workspace", execution_epoch="a" * 64,
                        trusted_digest=digest, local_metadata=value['local_metadata'])


def test_matching_artifact_with_one_group_mismatch_requires_review():
    value, digest = manifest()
    value["local_metadata"]["reply_evidence"].append({"record_id": "new", "state": "review"})
    result = verify_manifest(value, workspace_id="workspace", execution_epoch="a" * 64,
                             trusted_digest=canonical_hash(value), local_metadata=value['local_metadata'])
    assert result["outside_backup_integrity_verified"]
    assert not result["completeness_verified"]
    assert 'reply_evidence' in result["external_review_required"]
    assert not result["activation_allowed"]


def test_reactivation_plan_requires_provenance_and_stays_nonactivating():
    value, digest = manifest()
    result = {
        **verify_manifest(value, workspace_id="workspace", execution_epoch="a" * 64,
                          trusted_digest=digest, local_metadata=value['local_metadata']),
        "artifact_signer_verified": True,
    }
    plan = plan_reactivation(reconciliation=result, current_epoch="a" * 64,
                             new_epoch="b" * 64, review_digest=canonical_hash(result),
                             workers_drained=True, flags_off=True, operator_confirmed=True)
    assert plan["input_checks_passed"] and not plan['reactivation_ready'] and not plan["activation_allowed"]


def test_reactivation_plan_reports_fail_closed_blockers():
    plan = plan_reactivation(reconciliation={}, current_epoch="a" * 64,
                             new_epoch="a" * 64, review_digest="bad",
                             workers_drained=False, flags_off=False, operator_confirmed=False)
    assert not plan["reactivation_ready"]
    assert {"new_epoch_reuses_current_epoch", "review_digest_invalid",
            "workers_drained_assertion_missing_or_malformed", "flags_off_assertion_missing_or_malformed",
            "operator_confirmed_assertion_missing_or_malformed", "outside_backup_integrity_verified_missing",
            "artifact_signer_verified_missing", "selected_metadata_matches_missing"}.issubset(plan["blockers"])


def test_signed_manifest_requires_the_out_of_band_public_key():
    value, _ = manifest()
    key = Ed25519PrivateKey.generate()
    payload = deepcopy(value)
    signed = canonical_hash(payload).encode()
    payload["attestation"] = {
        "algorithm": "ed25519",
        "payload_digest": canonical_hash(value),
        "signature": base64.b64encode(key.sign(signed)).decode(),
    }
    result = verify_signed_manifest(payload, workspace_id="workspace", execution_epoch="a" * 64,
                                    trusted_public_key=base64.b64encode(
                                        key.public_key().public_bytes_raw()).decode(),
                                    local_metadata=value["local_metadata"])
    assert result['artifact_signer_verified'] and not result["source_provenance_verified"]


def test_offline_authority_input_review_cannot_exercise_a_transaction():
    value, digest = manifest()
    reconciliation = {**verify_manifest(value, workspace_id="workspace", execution_epoch="a" * 64,
                                        trusted_digest=digest, local_metadata=value['local_metadata']),
                      "artifact_signer_verified": True}
    review = canonical_hash(reconciliation)
    plan = plan_reactivation(
        reconciliation=reconciliation,
        current_epoch="a" * 64, new_epoch="b" * 64, review_digest=review,
        workers_drained=True, flags_off=True, operator_confirmed=True)
    result = rehearse_transaction(
        plan=plan, stopped_root={"workspace_id": "workspace", "status": "prepared_stopped",
                                 "execution_epoch": "a" * 64},
        authorities=[{"record_id": 'sender', "workspace_id": "workspace", "status": "stopped", "review_digest": review,
                      "credential_generation": "generation-1"}])
    assert result['input_checks_passed'] and not result["rehearsal_passed"]
    assert not result['transaction_exercised'] and not result["committed"] and not result["activation_allowed"]


def test_offline_authority_input_review_rejects_inconsistent_scope_and_status():
    result = rehearse_transaction(
        plan={"reactivation_ready": True, "new_epoch": "b" * 64, "review_digest": "c" * 64},
        stopped_root={"workspace_id": "workspace", "status": "prepared_stopped", "execution_epoch": "a" * 64},
        authorities=[{"record_id": 'sender', "workspace_id": "other", "status": "active", "review_digest": "old",
                      "credential_generation": "generation-1"}])
    assert not result["rehearsal_passed"]
    assert {"authority_0_scope_changed", "authority_0_not_stopped", "authority_0_review_changed"}.issubset(result["blockers"])


def test_reply_evidence_validates_metadata_without_restoring_history():
    row = {"record_id": "reply-1", "workspace_id": "workspace", "sender_digest": "1" * 64,
           "recipient_digest": "2" * 64, "event_digest": "3" * 64,
           "observed_at": "2026-10-10T10:00:00Z"}
    result = validate_reply_evidence([row], workspace_id="workspace")
    assert result['reply_metadata_valid'] and not result["reply_evidence_verified"]
    assert result["suppression_review_required"]
    assert not result["reply_history_restored"] and not result["activation_allowed"]


@pytest.mark.parametrize("mutation", [
    {"body": "private"}, {"observed_at": "bad"},
    {"sender_digest": "bad"}, {"workspace_id": "other"},
])
def test_reply_evidence_rejects_private_or_unproven_facts(mutation):
    row = {"record_id": "reply-1", "workspace_id": "workspace", "sender_digest": "1" * 64,
           "recipient_digest": "2" * 64, "event_digest": "3" * 64,
           "observed_at": "2026-10-10T10:00:00Z"}
    row.update(mutation)
    with pytest.raises(ReconciliationError):
        validate_reply_evidence([row], workspace_id="workspace")
