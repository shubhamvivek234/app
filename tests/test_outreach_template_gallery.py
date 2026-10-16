"""Read-only gallery eligibility must never become execution authority."""
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from outreach.api.sequences import get_sequence_templates


def database(rows):
    db = MagicMock()
    db.outreach_templates.find.return_value.sort.return_value.to_list = AsyncMock(return_value=rows)
    return db


def template(kind="send_email"):
    config = {"subject": "Hello", "body": "Hello {{first_name}}"} if kind == "send_email" else {}
    node = {"id": "root", "type": kind, "delay_hours": 0, "config": config}
    return {"_id": "native-id", "id": "custom-email", "name": "Email starter",
            "nodes": [node], "edges": [], "tree": [deepcopy(node)], "workspace_id": "workspace"}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["send_email", "find_email", "if_email_available", "has_data_in_column", "visit_profile"])
async def test_supported_templates_configure_with_live_flags_off_without_mutating_source(kind, monkeypatch):
    for flag in ["OUTREACH_LIVE_ACTIONS_ENABLED", "OUTREACH_EMAIL_SEND_ENABLED", "OUTREACH_EMAIL_SYNC_ENABLED", "OUTREACH_HUNTER_ENABLED"]:
        monkeypatch.setenv(flag, "false")
    row = template(kind)
    if kind == "has_data_in_column":
        row["nodes"][0]["config"] = {"condition_contract_version": 1, "field": "first_name", "operator": "has_value"}
        row["tree"][0]["config"] = deepcopy(row["nodes"][0]["config"])
    before = deepcopy(row)
    result = await get_sequence_templates({"user_id": "actor", "default_workspace_id": "workspace"}, database([row]))
    assert result[-1]["compatibility"]["configuration_available"] is True
    assert result[-1]["compatibility"]["execution_authorized"] is False
    assert result[-1]["nodes"] == before["nodes"]
    assert row == before and "_id" not in result[-1]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["missing_tree", "mismatched_tree", "unsupported", "bad_delay"])
async def test_uneditable_or_incompatible_graphs_remain_visible_for_review(change):
    row = template()
    if change == "missing_tree":
        row.pop("tree")
    elif change == "mismatched_tree":
        row["tree"][0]["type"] = "visit_profile"
    elif change == "unsupported":
        row["tree"][0]["type"] = row["nodes"][0]["type"] = "inmail"
    else:
        row["tree"][0]["delay_hours"] = row["nodes"][0]["delay_hours"] = True
    result = await get_sequence_templates({"user_id": "actor", "default_workspace_id": "workspace"}, database([row]))
    assert result[-1]["id"] == row["id"]
    assert result[-1]["compatibility"]["configuration_available"] is False
    assert result[-1]["compatibility"]["execution_authorized"] is False


@pytest.mark.asyncio
async def test_failed_workspace_catalog_read_is_unavailable_not_prebuilt_success():
    db = database([])
    db.outreach_templates.find.return_value.sort.return_value.to_list.side_effect = RuntimeError("private database address")
    with pytest.raises(HTTPException) as caught:
        await get_sequence_templates({"user_id": "actor", "default_workspace_id": "workspace"}, db)
    assert caught.value.status_code == 503
    assert "private" not in caught.value.detail


@pytest.mark.asyncio
async def test_gallery_requires_admitted_user_and_database():
    for actor, db in [(None, database([])), ({"user_id": "actor"}, None)]:
        with pytest.raises(HTTPException):
            await get_sequence_templates(actor, db)
