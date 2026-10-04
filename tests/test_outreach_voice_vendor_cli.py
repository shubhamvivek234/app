"""Private operator commands provide no activation/adoption/secret ingress."""
import argparse
import sys
from unittest.mock import AsyncMock
import pytest
from tests.test_outreach_voice_vendor_evidence import studio_db, scoped, prepared, METADATA, EVIDENCE


def args(voice, command='inspect', **changes):
    return argparse.Namespace(**{'command': command, 'workspace': 'w', 'voice': voice, 'job': None,
        'operator': 'operator', 'evidence': EVIDENCE, 'review_digest': '',
        'workers_drained': 'I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES', **changes})


@pytest.mark.asyncio
async def test_cli_inspect_capture_release_reference_only(studio_db, scoped, monkeypatch):
    from outreach.ops import voice_vendor_review as cli
    from outreach.core import voice_vendor_provider
    profile, _ = await prepared(studio_db, monkeypatch)
    monkeypatch.setattr(voice_vendor_provider, 'metadata_call', AsyncMock(return_value=METADATA))
    view = await cli.run_db(args(profile['id']), studio_db)
    job = await cli.run_db(args(profile['id'], 'capture', review_digest=view['review_digest']), studio_db)
    view = await cli.run_db(args(profile['id'], job=job['job_id']), studio_db)
    result = await cli.run_db(args(profile['id'], 'release', job=job['job_id'], review_digest=view['review_digest']), studio_db)
    assert result['current_matches'] and not result['activation_allowed']


@pytest.mark.asyncio
async def test_exact_drain_ack_precedes_key_or_http(studio_db, scoped, monkeypatch):
    from outreach.ops import voice_vendor_review as cli
    from outreach.core import voice_key_custody
    profile, _ = await prepared(studio_db, monkeypatch)
    view = await cli.run_db(args(profile['id']), studio_db)
    monkeypatch.setattr(voice_key_custody, 'prepare_key', AsyncMock(side_effect=AssertionError('No key')))
    with pytest.raises(ValueError): await cli.run_db(args(profile['id'], 'capture', review_digest=view['review_digest'],
        workers_drained='yes'), studio_db)


@pytest.mark.parametrize('command', ['activate', 'retry', 'adopt', 'verify_captcha'])
def test_no_unsafe_cli_command(command, capsys):
    from outreach.ops import voice_vendor_review as cli
    with pytest.raises(SystemExit): cli.parser().parse_args([command, '--workspace', 'w', '--voice', 'v'])


def test_parser_never_echoes_accidental_secret(capsys):
    from outreach.ops import voice_vendor_review as cli
    with pytest.raises(SystemExit): cli.parser().parse_args(['inspect', '--workspace', 'w', '--voice', 'v', '--key', 'private-secret'])
    assert 'private-secret' not in capsys.readouterr().err


def test_runtime_error_is_static(monkeypatch, capsys):
    from outreach.ops import voice_vendor_review as cli
    monkeypatch.setattr(sys, 'argv', ['voice-vendor-review', 'inspect', '--workspace', 'w', '--voice', 'v'])
    monkeypatch.setattr(cli, 'run', AsyncMock(side_effect=ValueError('private-vendor-metadata')))
    assert cli.main() == 2
    output = capsys.readouterr()
    assert not output.out and 'private-vendor-metadata' not in output.err


@pytest.mark.asyncio
async def test_cli_close_interrupted_read_and_unknown_command(studio_db, scoped, monkeypatch):
    from outreach.ops import voice_vendor_review as cli
    from outreach.core import voice_vendor_provider
    from outreach.core.voice_studio import now
    from datetime import timedelta
    profile, _ = await prepared(studio_db, monkeypatch)
    monkeypatch.setattr(voice_vendor_provider, 'metadata_call', AsyncMock(side_effect=TimeoutError()))
    view = await cli.run_db(args(profile['id']), studio_db)
    job = await cli.run_db(args(profile['id'], 'capture', review_digest=view['review_digest']), studio_db)
    studio_db.outreach_voice_vendor_reads.docs[0]['authorization_expires_at'] = now() - timedelta(seconds=1)
    view = await cli.run_db(args(profile['id'], job=job['job_id']), studio_db)
    result = await cli.run_db(args(profile['id'], 'close-read', job=job['job_id'], review_digest=view['review_digest']), studio_db)
    assert result['status'] == 'read_interrupted'
    with pytest.raises(ValueError): await cli.run_db(args(profile['id'], 'unknown'), studio_db)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [False, True])
async def test_cli_closes_database_on_success_and_failure(monkeypatch, failure):
    from outreach.ops import voice_vendor_review as cli
    monkeypatch.setenv('DB_NAME', 'local')
    client = {'local': object()}; closing = AsyncMock(); get = AsyncMock(return_value=client)
    monkeypatch.setattr(cli, 'get_client', get); monkeypatch.setattr(cli, 'close_client', closing)
    monkeypatch.setattr(cli, 'run_db', AsyncMock(side_effect=ValueError('private') if failure else None, return_value={'status': 'ok'}))
    if failure:
        with pytest.raises(ValueError): await cli.run(args('v'))
    else: assert await cli.run(args('v')) == {'status': 'ok'}
    closing.assert_awaited_once()


def test_cli_main_success_and_parser_require_bounded_references(monkeypatch, capsys):
    from outreach.ops import voice_vendor_review as cli
    for command in ['capture', 'release', 'close-read']:
        arguments = [command, '--workspace', 'w', '--voice', 'v', '--operator', 'operator', '--evidence', EVIDENCE,
            '--review-digest', 'a' * 64, '--workers-drained', cli.DRAIN_ACK]
        if command != 'capture': arguments += ['--job', 'b' * 64]
        parsed = cli.parser().parse_args(arguments)
        assert parsed.command == command
    monkeypatch.setattr(sys, 'argv', ['voice-vendor-review', 'inspect', '--workspace', 'w', '--voice', 'v'])
    monkeypatch.setattr(cli, 'run', AsyncMock(return_value={'activation_allowed': False}))
    assert cli.main() == 0 and 'false' in capsys.readouterr().out
