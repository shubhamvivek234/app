"""Private Studio commands expose references and require exact drain evidence."""
import json
from argparse import Namespace
from unittest.mock import AsyncMock
import pytest
from tests.test_outreach_voice_studio import studio_db
from tests.test_outreach_voice_studio_review import held, EVIDENCE

DRAIN = 'I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES'


@pytest.mark.asyncio
async def test_cli_inspection_and_stop_print_only_sanitized_result(studio_db, monkeypatch, capsys):
    from outreach.ops.pilot import _run_db
    job = await held(studio_db, monkeypatch)
    await _run_db(Namespace(command='inspect-studio-review', workspace='w', job=job['_id']), studio_db)
    output = capsys.readouterr().out
    view = json.loads(output)
    assert 'input_enc' not in output and 'provider_source_digest' not in output and 'consent' not in output
    await _run_db(Namespace(command='resolve-studio-review', workspace='w', job=job['_id'], decision='stop_local',
        operator='private-operator', evidence=EVIDENCE, workers_drained=DRAIN, review_digest=view['review_digest']), studio_db)
    output = capsys.readouterr().out
    assert json.loads(output)['status'] == 'review_stopped'
    assert 'private-operator' not in output and EVIDENCE not in output


@pytest.mark.asyncio
@pytest.mark.parametrize('ack', ['', 'true', 'I_PAUSED_AND_DRAINED_SENDER_WORKERS', 'I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS'])
async def test_incomplete_drain_ack_is_rejected(studio_db, monkeypatch, ack):
    from outreach.ops.pilot import _run_db
    from outreach.core.voice_studio_review import VoiceStudioReview
    job = await held(studio_db, monkeypatch)
    view = await VoiceStudioReview(studio_db).inspect('w', job['_id'])
    with pytest.raises(ValueError):
        await _run_db(Namespace(command='resolve-studio-review', workspace='w', job=job['_id'], decision='stop_local',
            operator='operator', evidence=EVIDENCE, workers_drained=ack, review_digest=view['review_digest']), studio_db)
    assert not job.get('review')


@pytest.mark.parametrize('decision', ['stop_local', 'use_receipt'])
def test_operator_parser_accepts_only_supported_decisions(monkeypatch, decision):
    from outreach.ops import pilot
    run = AsyncMock()
    monkeypatch.setattr(pilot, '_run', run)
    monkeypatch.setattr('sys.argv', ['pilot', 'resolve-studio-review', '--workspace', 'w', '--job', 'j', '--decision', decision,
        '--operator', 'operator', '--evidence', EVIDENCE, '--review-digest', 'a'*64, '--workers-drained', DRAIN])
    pilot.main()
    assert run.await_args.args[0].decision == decision


@pytest.mark.parametrize('decision', ['confirmed_sent', 'retry', 'adopt_source', 'verify_vendor'])
def test_parser_does_not_offer_replay_or_adoption(monkeypatch, decision):
    from outreach.ops import pilot
    monkeypatch.setattr('sys.argv', ['pilot', 'resolve-studio-review', '--workspace', 'w', '--job', 'j', '--decision', decision,
        '--operator', 'operator', '--evidence', EVIDENCE, '--review-digest', 'a'*64, '--workers-drained', DRAIN])
    with pytest.raises(SystemExit): pilot.main()
