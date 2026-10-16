"""Strict local conversation metadata; never send/reply/activation authority."""
from copy import deepcopy

import pytest
from bson import BSON, ObjectId
from fastapi import HTTPException
from pydantic import ValidationError

from outreach.core import inbox_organization as org
from outreach.api.inbox import UpdateOrganizationRequest


def thread(**fields):
    return {"_id": ObjectId(), "id": "thread", "workspace_id": "w", "account_id": "sender",
            "conversation_urn": "conversation", "lead_urn": "person", **fields}


def test_absent_metadata_has_native_review_without_mutating_original():
    row = thread(); before = deepcopy(row)
    result = org.public_organization(row)
    assert result["editable"] and result["revision"] == 0
    assert not result["is_archived"] and not result["is_starred"] and result["note"] == ""
    assert len(result["review_digest"]) == 64 and row == before


@pytest.mark.parametrize("field,value", [("_id", None), ("id", []), ("workspace_id", ["w"]),
    ("account_id", ["sender"]), ("account_id", "all"), ("conversation_urn", []), ("lead_urn", {})])
def test_unproven_identity_disables_only_organization(field, value):
    result = org.public_organization(thread(**{field: value}))
    assert result["editable"] is False and result["review_digest"] is None


@pytest.mark.parametrize("metadata", [None, [], {}, {"revision": True},
    {"revision": -1, "is_starred": False, "is_archived": False, "note": ""},
    {"revision": 1, "is_starred": "false", "is_archived": False, "note": ""},
    {"revision": 1, "is_starred": False, "is_archived": [], "note": ""},
    {"revision": 1, "is_starred": False, "is_archived": False, "note": []}])
def test_malformed_saved_metadata_is_review_only(metadata):
    assert not org.public_organization(thread(inbox_organization=metadata))["editable"]


def test_native_identity_context_and_same_revision_content_change_review_digest():
    row = thread(inbox_organization={"revision": 1, "is_starred": True, "is_archived": False, "note": "original"})
    digest = org.public_organization(row)["review_digest"]
    for field, value in [("_id", str(row["_id"])), ("account_id", "replacement"),
            ("conversation_urn", "other"), ("lead_urn", "other"), ("channel", "email")]:
        assert org.public_organization({**row, field: value})["review_digest"] != digest
    row["inbox_organization"]["note"] = "changed"
    assert org.public_organization(row)["review_digest"] != digest


@pytest.mark.parametrize("changes", [{}, {"is_starred": 1}, {"is_archived": "false"},
    {"note": None}, {"note": "a" * 4001}, {"note": "bad\x00"}, {"note": "bad\ud800"},
    {"thread_revision": 2}, {"is_starred": False, "extra": "field"}])
def test_invalid_update_rejected(changes):
    with pytest.raises((ValidationError, HTTPException)):
        req = UpdateOrganizationRequest(revision=0, review_digest="a" * 64, **changes)
        org.validate_changes(req.model_dump(exclude={"revision", "review_digest"}, exclude_unset=True))


@pytest.mark.parametrize("revision", [True, 0.5, "0", -1, 2**63-1])
def test_revision_is_bounded_strict_integer(revision):
    with pytest.raises(ValidationError):
        UpdateOrganizationRequest(revision=revision, review_digest="a" * 64, note="")


def test_notes_preserve_plain_text_and_allow_explicit_empty_clear():
    assert org.validate_changes({"note": "<b>Meeting</b>\n\t👩‍💻"}) == {"note": "<b>Meeting</b>\n\t👩‍💻"}
    assert org.validate_changes({"note": ""}) == {"note": ""}


@pytest.mark.parametrize("extra", [{"updated_at": []}, {"updated_by": {}}, {"unknown_schema": True}])
def test_unsupported_saved_schema_requires_review(extra):
    saved = {"revision": 1, "is_starred": False, "is_archived": False, "note": "", **extra}
    assert not org.public_organization(thread(inbox_organization=saved))["editable"]


def test_blank_recipient_and_compound_channel_are_not_editable():
    assert not org.public_organization(thread(conversation_urn="  ", lead_urn="\t"))["editable"]
    assert not org.public_organization(thread(channel=[]))["editable"]


def test_bson_int64_revision_roundtrip_remains_json_safe():
    row = thread(inbox_organization={"revision": 2**31, "is_starred": False, "is_archived": False, "note": ""})
    decoded = BSON(BSON.encode(row)).decode()
    public = org.public_organization(decoded)
    assert public["editable"] and type(public["revision"]) is int and public["revision"] == 2**31
