"""Private recording CLI contains no replacement audio/credential inputs."""
from unittest.mock import AsyncMock

import pytest

from outreach.ops import voice_artifact_migration as ops
from outreach.ops.proxy_custody import DRAIN_ACK
from tests.test_outreach_voice_artifact_migration import old_clip, scoped, voice_db, EVIDENCE

pytestmark = pytest.mark.asyncio


def arguments(asset, command='inspect', **changes):
    values = ['--workspace', 'w', '--artifact', asset]
    if command == 'migrate':
        extra = {'operator':'operator', 'evidence-digest':EVIDENCE, 'review-digest':'b'*64, 'workers-drained':DRAIN_ACK}
        extra.update(changes)
        values += [item for key,value in extra.items() for item in ('--'+key,value)]
    return ops.parser().parse_args([command, *values])


async def test_inspect_and_migrate_use_only_exact_references(old_clip):
    asset=old_clip.outreach_voice_artifacts.docs[0]['_id']
    view=await ops.run_db(arguments(asset),old_clip)
    assert not view['blockers'] and 'Hello' not in str(view) and 'gAAAAA' not in str(view)
    result=await ops.run_db(arguments(asset,'migrate',**{'review-digest':view['digest']}),old_clip)
    assert result['current_matches'] and not result['activation_allowed']


async def test_exact_drain_acknowledgement_required(old_clip):
    asset=old_clip.outreach_voice_artifacts.docs[0]['_id']
    with pytest.raises(Exception): await ops.run_db(arguments(asset,'migrate',**{'workers-drained':'yes'}),old_clip)
    assert not old_clip.outreach_credential_migrations.docs


@pytest.mark.parametrize('flag',['--audio','--password','--expires-at','--generation'])
async def test_source_replacement_arguments_are_rejected_without_echo(capsys,flag):
    with pytest.raises(SystemExit) as error:
        ops.parser().parse_args(['inspect','--workspace','w','--artifact','a'*64,flag,'private-value'])
    assert error.value.code==2 and 'private-value' not in capsys.readouterr().err


async def test_client_closes_after_database_selection_failure(monkeypatch):
    class Broken:
        def __getitem__(self,name): raise ValueError('private-value')
    close=AsyncMock()
    monkeypatch.setenv('DB_NAME','unused')
    monkeypatch.setattr(ops,'get_client',AsyncMock(return_value=Broken()))
    monkeypatch.setattr(ops,'close_client',close)
    with pytest.raises(ValueError): await ops.run(arguments('a'*64))
    close.assert_awaited_once()


async def test_runtime_errors_are_sanitized(monkeypatch,capsys):
    args=arguments('a'*64)
    monkeypatch.setattr(ops,'parser',lambda:type('Parser',(),{'parse_args':lambda self:args})())
    monkeypatch.setattr(ops.asyncio,'run',lambda coro:(coro.close(),(_ for _ in ()).throw(ValueError('private-value')))[1])
    assert ops.main()==2
    captured=capsys.readouterr()
    assert 'private-value' not in captured.err+captured.out
