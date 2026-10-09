"""Private stop-only CLI never echoes provider arguments or grants access."""
from unittest.mock import AsyncMock
import pytest
from outreach.ops import restore_epoch as ops
from tests.test_outreach_restore_epoch import restored_db, EVIDENCE
pytestmark=[pytest.mark.asyncio,pytest.mark.restore_epoch]


def arguments(command='inspect',review=None):
    args=[command,'--workspace','w']
    if command=='prepare':args+=['--operator','operator','--evidence-digest',EVIDENCE,
        '--review-digest',review,'--all-writers-and-caches-drained']
    return ops.parser().parse_args(args)

async def test_inspect_and_prepare_stop_without_activation(restored_db):
    view=await ops.run_db(arguments(),restored_db)
    result=await ops.run_db(arguments('prepare',view['digest']),restored_db)
    assert result['prepared'] and not result['activation_allowed']

@pytest.mark.parametrize('flag',['--cookie','--proxy-url','--grant','--activate','--replay','--epoch'])
async def test_parser_never_accepts_or_echoes_private_material(capsys,flag):
    with pytest.raises(SystemExit):ops.parser().parse_args(['inspect','--workspace','w',flag,'private-material'])
    assert 'private-material' not in capsys.readouterr().err

async def test_parser_requires_identified_drain(capsys):
    with pytest.raises(SystemExit):ops.parser().parse_args(['prepare','--workspace','w','--operator','operator',
        '--evidence-digest',EVIDENCE,'--review-digest','b'*64])
    assert 'Restore control' in capsys.readouterr().err

async def test_client_closes_and_main_sanitizes_errors(monkeypatch,capsys):
    close=AsyncMock();monkeypatch.setattr(ops,'get_client',AsyncMock(return_value={}))
    monkeypatch.setattr(ops,'close_client',close);monkeypatch.setenv('DB_NAME','missing')
    with pytest.raises(KeyError):await ops.run(arguments())
    close.assert_awaited_once()
    saved=arguments();monkeypatch.setattr(ops,'parser',lambda:type('Parser',(),{'parse_args':lambda self:saved})())
    def failed(coro):coro.close();raise ValueError('private-material')
    monkeypatch.setattr(ops.asyncio,'run',failed)
    assert ops.main()==2 and 'private-material' not in capsys.readouterr().err
    monkeypatch.setattr(ops.asyncio,'run',lambda coro:(coro.close(),{'activation_allowed':False})[1])
    assert ops.main()==0 and 'false' in capsys.readouterr().out
