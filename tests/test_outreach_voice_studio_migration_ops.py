"""Studio conversion CLI carries only original references and review digests."""
from unittest.mock import AsyncMock

import pytest

from outreach.ops import voice_studio_migration as ops
from outreach.ops.proxy_custody import DRAIN_ACK
from tests.test_outreach_voice_studio_migration import old_preview, preview_job, scoped, studio_db, EVIDENCE

pytestmark = pytest.mark.asyncio


def arguments(job, command='inspect', **changes):
    values=['--workspace','w','--job',job]
    if command=='migrate':
        extra={'operator':'operator','evidence-digest':EVIDENCE,'review-digest':'b'*64,'workers-drained':DRAIN_ACK}
        extra.update(changes)
        values += [item for key,value in extra.items() for item in ('--'+key,value)]
    return ops.parser().parse_args([command,*values])


async def test_exact_reference_inspection_and_conversion_only(old_preview):
    job=preview_job(old_preview)
    view=await ops.run_db(arguments(job['_id']),old_preview)
    assert not view['blockers'] and 'Hello' not in str(view) and 'gAAAAA' not in str(view)
    result=await ops.run_db(arguments(job['_id'],'migrate',**{'review-digest':view['digest']}),old_preview)
    assert result['current_matches'] and not result['activation_allowed']


async def test_drain_acknowledgement_must_match(old_preview):
    with pytest.raises(Exception):
        await ops.run_db(arguments(preview_job(old_preview)['_id'],'migrate',**{'workers-drained':'yes'}),old_preview)
    assert not old_preview.outreach_credential_migrations.docs


@pytest.mark.parametrize('flag',['--audio','--password','--expires-at','--source','--generation'])
async def test_replacement_inputs_rejected_without_echo(capsys,flag):
    with pytest.raises(SystemExit) as error:
        ops.parser().parse_args(['inspect','--workspace','w','--job','a'*64,flag,'private-value'])
    assert error.value.code==2 and 'private-value' not in capsys.readouterr().err


async def test_client_closes_after_database_selection_error(monkeypatch):
    class Broken:
        def __getitem__(self,name): raise ValueError('private-value')
    close=AsyncMock()
    monkeypatch.setenv('DB_NAME','unused')
    monkeypatch.setattr(ops,'get_client',AsyncMock(return_value=Broken()))
    monkeypatch.setattr(ops,'close_client',close)
    with pytest.raises(ValueError): await ops.run(arguments('a'*64))
    close.assert_awaited_once()


async def test_runtime_error_output_contains_no_private_detail(monkeypatch,capsys):
    args=arguments('a'*64)
    monkeypatch.setattr(ops,'parser',lambda:type('Parser',(),{'parse_args':lambda self:args})())
    monkeypatch.setattr(ops.asyncio,'run',lambda coro:(coro.close(),(_ for _ in ()).throw(ValueError('private-value')))[1])
    assert ops.main()==2
    captured=capsys.readouterr()
    assert 'private-value' not in captured.out+captured.err
