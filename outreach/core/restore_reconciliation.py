"""Offline comparison of selected restore metadata and an external artifact.

Integrity and signatures verify the canonical payload digest/signer only. Neither
the artifact nor a caller-supplied local view proves provider facts, database
completeness, stopped authority, or permission to reactivate.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from outreach.core.authorization import canonical_hash

HEX = frozenset("0123456789abcdef")
MAX_SOURCES = 12
MAX_RECORDS = 100
MAX_BYTES = 65_536
GROUPS = ("financial", "provider_resource", "reply_evidence")
PAYLOAD_FIELDS = {"version", "workspace_id", "execution_epoch", "sources", "summaries", "local_metadata"}


class ReconciliationError(ValueError):
    """Malformed or unverifiable offline review input; never echo material."""


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in HEX for char in value):
        raise ReconciliationError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _reference(value: Any, label: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 256
            or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ReconciliationError(f"{label} must be a bounded reference")
    return value


def bounded_json(value: Any) -> Any:
    """Copy only bounded JSON values, excluding cycles, nonfinite/opaque objects.

    This bounds the accepted review artifact after construction, not a parser
    or wire ingress. No arbitrary object is stringified while hashing it.
    """
    remaining = MAX_BYTES

    def spend(count: int) -> None:
        nonlocal remaining
        remaining -= count
        if remaining < 0:
            raise ReconciliationError("Review input exceeds bounded capacity")

    def copy(item: Any, depth: int) -> Any:
        if depth > 8:
            raise ReconciliationError("Review input nesting exceeds bounded capacity")
        if type(item) is str:
            if len(item) > MAX_BYTES:
                raise ReconciliationError("Review input exceeds bounded capacity")
            try:
                spend(len(json.dumps(item, ensure_ascii=False).encode("utf-8")))
            except UnicodeError:
                raise ReconciliationError("Review input is not valid UTF-8") from None
            return item
        if item is None or type(item) is bool or type(item) is int:
            if type(item) is int and not -(2**63) <= item < 2**63:
                raise ReconciliationError("Review integer exceeds bounded capacity")
            spend(len(json.dumps(item)))
            return item
        if type(item) is list:
            if len(item) > MAX_RECORDS:
                raise ReconciliationError("Review rows exceed bounded capacity")
            spend(2 + len(item))
            return [copy(child, depth + 1) for child in item]
        if type(item) is dict:
            if len(item) > MAX_RECORDS or any(type(key) is not str for key in item):
                raise ReconciliationError("Review object is malformed")
            spend(2 + 2 * len(item))
            return {copy(key, depth + 1): copy(child, depth + 1) for key, child in item.items()}
        raise ReconciliationError("Review input must contain JSON values only")

    return copy(value, 0)


def _metadata(value: Any) -> dict[str, list[dict[str, str]]]:
    if not isinstance(value, dict) or set(value) != set(GROUPS):
        raise ReconciliationError("All three selected metadata groups are required")
    result = {}
    for group in GROUPS:
        rows = value[group]
        if not isinstance(rows, list) or len(rows) > MAX_RECORDS:
            raise ReconciliationError("Selected metadata exceeds bounded capacity")
        seen = set()
        selected = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"record_id", "state"}:
                raise ReconciliationError("Selected metadata contains unsupported fields")
            record = _reference(row["record_id"], "record_id")
            state = _reference(row["state"], "state")
            if len(state) > 64 or record in seen:
                raise ReconciliationError("Selected metadata identity or state is ambiguous")
            seen.add(record)
            selected.append({"record_id": record, "state": state})
        result[group] = sorted(selected, key=lambda row: row["record_id"])
    return result


def verify_manifest(manifest: Mapping[str, Any], *, workspace_id: str,
                    execution_epoch: str | None, trusted_digest: str,
                    local_metadata: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, Any]:
    """Compare an intact artifact with a separate caller-supplied local view.

    The required local view must be obtained independently of the artifact.
    This function cannot enforce that origin or prove a complete DB snapshot.
    """
    payload = bounded_json(manifest)
    if not isinstance(payload, dict) or set(payload) != PAYLOAD_FIELDS:
        raise ReconciliationError("Manifest fields are malformed")
    _reference(workspace_id, "workspace_id")
    _digest(execution_epoch, "execution_epoch")
    expected = _digest(trusted_digest, "trusted_digest")
    if type(payload["version"]) is not int or payload["version"] != 1:
        raise ReconciliationError("Unsupported manifest version")
    if payload["workspace_id"] != workspace_id or payload["execution_epoch"] != execution_epoch:
        raise ReconciliationError("Manifest scope or epoch does not match")
    if canonical_hash(payload) != expected:
        raise ReconciliationError("Manifest integrity digest does not match")
    sources = payload["sources"]
    if not isinstance(sources, list) or not 1 <= len(sources) <= MAX_SOURCES:
        raise ReconciliationError("Bounded source descriptors are required")
    source_ids, covered = set(), set()
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"source_id", "group", "snapshot_digest", "evidence_digest"}:
            raise ReconciliationError("Source descriptor fields are malformed")
        source_id = _reference(source["source_id"], "source_id")
        if source_id in source_ids or source["group"] not in GROUPS:
            raise ReconciliationError("Source descriptor identity or group is ambiguous")
        source_ids.add(source_id)
        covered.add(source["group"])
        _digest(source["snapshot_digest"], "snapshot_digest")
        _digest(source["evidence_digest"], "evidence_digest")
    if covered != set(GROUPS):
        raise ReconciliationError("Source descriptors must cover all selected groups")
    summaries = payload["summaries"]
    if not isinstance(summaries, dict) or set(summaries) != set(GROUPS):
        raise ReconciliationError("Exactly three selected summaries are required")
    embedded = _metadata(payload["local_metadata"])
    independent = _metadata(bounded_json(local_metadata))
    matches = {}
    for group in GROUPS:
        summary = summaries[group]
        if not isinstance(summary, dict) or set(summary) != {"record_count", "metadata_digest"}:
            raise ReconciliationError("Selected summary fields are malformed")
        count = summary["record_count"]
        if type(count) is not int or not 0 <= count <= MAX_RECORDS:
            raise ReconciliationError("Selected summary count is out of bounds")
        digest = _digest(summary["metadata_digest"], "metadata_digest")
        matches[group] = (count == len(embedded[group]) == len(independent[group])
                          and digest == canonical_hash(embedded[group]) == canonical_hash(independent[group]))
    return {
        "version": 1, "workspace_id": workspace_id, "execution_epoch": execution_epoch,
        "outside_backup_integrity_verified": True, "group_matches": matches,
        "selected_metadata_matches": all(matches.values()),
        "local_metadata_digest": canonical_hash(independent),
        "completeness_verified": False, "activation_allowed": False,
        "artifact_signer_verified": False, "source_provenance_verified": False,
        "provider_ownership_verified": False, "payment_authenticated": False,
        "reply_evidence_authenticated": False,
        "external_review_required": [group for group, ok in matches.items() if not ok] + [
            "financial_facts", "provider_resources", "reply_provenance", "source_completeness"],
        "manifest_digest": expected,
    }


def verify_signed_manifest(manifest: Mapping[str, Any], *, workspace_id: str,
                           execution_epoch: str | None, trusted_public_key: str,
                           local_metadata: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, Any]:
    """Authenticate a review artifact signer with a key trusted out of band.

    A signature cannot prove true or complete source facts, original JSON byte
    spelling/duplicate-key parsing, or storage outside all applicable backups.
    """
    payload = bounded_json(manifest)
    if not isinstance(payload, dict) or set(payload) != PAYLOAD_FIELDS | {"attestation"}:
        raise ReconciliationError("Signed manifest fields are malformed")
    attestation = payload.pop("attestation")
    if (not isinstance(attestation, dict)
            or set(attestation) != {"algorithm", "signature", "payload_digest"}
            or attestation["algorithm"] != "ed25519"):
        raise ReconciliationError("An exact Ed25519 artifact attestation is required")
    try:
        if not isinstance(trusted_public_key, str) or len(trusted_public_key) != 44:
            raise ValueError
        public_key = base64.b64decode(trusted_public_key, validate=True)
        signature = base64.b64decode(attestation["signature"], validate=True)
    except (ValueError, TypeError):
        raise ReconciliationError("Artifact attestation encoding is malformed") from None
    if len(public_key) != 32 or len(signature) != 64:
        raise ReconciliationError("Artifact attestation key or signature length is invalid")
    digest = _digest(attestation["payload_digest"], "payload_digest")
    if canonical_hash(payload) != digest:
        raise ReconciliationError("Artifact attestation payload digest does not match")
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, digest.encode())
    except (InvalidSignature, ValueError):
        raise ReconciliationError("Artifact attestation signature is invalid") from None
    result = verify_manifest(payload, workspace_id=workspace_id, execution_epoch=execution_epoch,
                             trusted_digest=digest, local_metadata=local_metadata)
    result["artifact_signer_verified"] = True
    return result
