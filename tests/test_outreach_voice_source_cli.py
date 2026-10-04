"""Private original material is bounded, hidden and never read on saved retry."""
import argparse
import json
import os
import sys
from unittest.mock import AsyncMock
import pytest

from tests.test_outreach_voice_source_review import studio_db,scoped,ready,KEY,EVIDENCE


def args(voice, digest='', **changes):
    values=dict(command='migrate',workspace='w',voice=voice,operator='operator',evidence=EVIDENCE,
        review_digest=digest,workers_drained='I_PAUSED_AND_DRAINED_ALL_WORKSPACE_WRITERS_AND_CACHES',
        prior_envelope=None,prior_generation='',prior_key_stdin=False)
    return argparse.Namespace(**{**values,**changes})


@pytest.mark.asyncio
async def test_private_cli_inspection_migration_and_retry_are_sanitized(studio_db,scoped,monkeypatch):
    from outreach.ops import voice_source_review as cli
    profile,job,prior=await ready(studio_db,monkeypatch)
    inspected=await cli.run_db(args(profile['id'],command='inspect'),studio_db)
    assert KEY not in json.dumps(inspected) and 'original-remote' not in json.dumps(inspected)
    monkeypatch.setattr(cli,'read_secret',lambda stdin: KEY)
    request=args(profile['id'],inspected['review_digest'])
    result=await cli.run_db(request,studio_db)
    assert result['status']=='completed' and KEY not in json.dumps(result)
    monkeypatch.setattr(cli,'read_secret',lambda stdin: pytest.fail('Saved retry never reads stdin/hidden input'))
    assert await cli.run_db(request,studio_db)==result


@pytest.mark.asyncio
async def test_exact_drain_ack_and_inspection_precede_secret_read(studio_db,scoped,monkeypatch):
    from outreach.ops import voice_source_review as cli
    profile,job,prior=await ready(studio_db,monkeypatch)
    view=await cli.run_db(args(profile['id'],command='inspect'),studio_db)
    monkeypatch.setattr(cli,'read_secret',lambda stdin: pytest.fail('No secret read'))
    for request in (args(profile['id'],view['review_digest'],workers_drained='yes'),args(profile['id'],'a'*64)):
        with pytest.raises(ValueError): await cli.run_db(request,studio_db)


@pytest.mark.asyncio
async def test_scoped_original_envelope_file_works_without_plaintext_prompt(studio_db,scoped,monkeypatch,tmp_path):
    from outreach.ops import voice_source_review as cli
    profile,job,prior=await ready(studio_db,monkeypatch,kind='kms_v1')
    path=tmp_path/'original-envelope';path.write_text(prior.storage+'\n');path.chmod(0o600)
    view=await cli.run_db(args(profile['id'],command='inspect'),studio_db)
    monkeypatch.setattr(cli,'read_secret',lambda stdin: pytest.fail('No raw key prompt'))
    result=await cli.run_db(args(profile['id'],view['review_digest'],prior_envelope=path,prior_generation='g1'),studio_db)
    assert result['status']=='completed' and path.read_text()==prior.storage+'\n'


@pytest.mark.parametrize('failure',['symlink','public','fifo','oversize','missing','plaintext'])
def test_original_envelope_ingress_rejects_unsafe_or_unbounded_files(tmp_path,failure):
    from outreach.ops import voice_source_review as cli
    path=tmp_path/'input'
    if failure=='symlink':
        original=tmp_path/'target';original.write_text('uc1:dummy');original.chmod(0o600);path.symlink_to(original)
    elif failure=='fifo': os.mkfifo(path,0o600)
    elif failure!='missing':
        path.write_text('x'*60001 if failure=='oversize' else 'secret-key' if failure=='plaintext' else 'uc1:dummy')
        path.chmod(0o644 if failure=='public' else 0o600)
    with pytest.raises(ValueError): cli.read_envelope(path)


def test_accidental_key_arguments_are_not_echoed(capsys):
    from outreach.ops import voice_source_review as cli
    with pytest.raises(SystemExit): cli.parser().parse_args(['inspect','--workspace','w','--voice','v','--key','private-key-argument'])
    assert 'private-key-argument' not in capsys.readouterr().err


def test_provider_verification_adoption_and_replay_are_not_cli_commands(capsys):
    from outreach.ops import voice_source_review as cli
    for command in ['verify_vendor','adopt_source','activate','retry']:
        with pytest.raises(SystemExit): cli.parser().parse_args([command,'--workspace','w','--voice','v'])


def test_cli_failure_never_prints_private_exception_or_args(monkeypatch,capsys):
    from outreach.ops import voice_source_review as cli
    monkeypatch.setattr(sys,'argv',['voice-source-review','inspect','--workspace','w','--voice','v'])
    monkeypatch.setattr(cli,'run',AsyncMock(side_effect=ValueError('private-provider-key uc1:private-envelope')))
    assert cli.main()==2
    output=capsys.readouterr()
    assert 'private-provider-key' not in output.err and 'private-envelope' not in output.err and not output.out
