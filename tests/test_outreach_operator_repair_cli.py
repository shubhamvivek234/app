"""Private operator commands return sanitized inspection and enforce drain evidence."""
import json
from argparse import Namespace

import pytest

from outreach.ops.pilot import _run_db
from tests.test_outreach_connection_repair import database, prepared
from tests.test_outreach_manual_resolution import unknown


@pytest.mark.asyncio
async def test_connection_inspection_never_prints_pending_or_installed_secrets(capsys):
    db = database()
    await prepared(db)
    await _run_db(Namespace(command="inspect-connection-repair", workspace="w", job="j"), db)
    output = capsys.readouterr().out
    assert "cipher" not in output and "li_at_enc" not in output
    assert json.loads(output)["review_digest"]


@pytest.mark.asyncio
async def test_manual_cli_resolves_original_stage_without_grant_or_provider(capsys):
    db, job = await unknown()
    await _run_db(Namespace(command="inspect-manual-review", workspace="w", job="j"), db)
    digest = json.loads(capsys.readouterr().out)["review_digest"]
    await _run_db(Namespace(command="resolve-manual-review", workspace="w", job="j", decision=["comment=confirmed_sent"],
        operator="operator", evidence="Inspected this original comment after sender workers were drained.",
        workers_drained="I_PAUSED_AND_DRAINED_SENDER_WORKERS", review_digest=digest), db)
    assert json.loads(capsys.readouterr().out)["status"] == "resolved"
    assert job["stages"]["comment"]["status"] == "human_confirmed"
    assert db.outreach_sender_execution.docs[0]["permission"]["latched"]


@pytest.mark.asyncio
async def test_duplicate_manual_stage_cli_entries_are_rejected():
    db, _ = await unknown()
    with pytest.raises(ValueError, match="unique"):
        await _run_db(Namespace(command="resolve-manual-review", workspace="w", job="j", decision=["comment=confirmed_sent", "comment=not_sent_stop"]), db)
