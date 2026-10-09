"""Private monitor operator controls accept no session/provider material."""
from unittest.mock import AsyncMock
import pytest
from outreach.ops import health_monitor as ops
from tests.test_outreach_health_monitor import healthy_db, EVIDENCE

pytestmark=pytest.mark.asyncio


def arguments(command='inspect', **changes):
    values={'workspace':'w','sender':'sender'}
    if command=='arm':values.update(operator='operator', **{'evidence-digest':EVIDENCE,'review-digest':'b'*64,'window-seconds':'300'})
    if command=='stop':values={'workspace':'w','control':'b'*64,'operator':'operator','evidence-digest':EVIDENCE}
    values.update(changes)
    return ops.parser().parse_args([command,*[item for key,value in values.items() for item in ('--'+key,value)]])


async def test_inspect_arm_and_stop_do_not_grant(healthy_db):
    view=await ops.run_db(arguments(),healthy_db)
    result=await ops.run_db(arguments('arm',**{'review-digest':view['digest']}),healthy_db)
    assert not healthy_db.outreach_sender_execution.docs[0]['permission'].get('health_control_id')
    result=await ops.run_db(arguments('stop',control=result['control_id']),healthy_db)
    assert result['status']=='stopped' and not result['campaigns_resumed']


@pytest.mark.parametrize('flag',['--cookie','--proxy-url','--grant','--activate','--replay'])
async def test_parser_never_echoes_private_input(capsys,flag):
    with pytest.raises(SystemExit):ops.parser().parse_args(['inspect','--workspace','w','--sender','sender',flag,'private-cookie'])
    assert 'private-cookie' not in capsys.readouterr().err


async def test_client_closes_on_error(monkeypatch):
    class Broken:
        def __getitem__(self,name):raise ValueError('private-cookie')
    close=AsyncMock();monkeypatch.setenv('DB_NAME','unused')
    monkeypatch.setattr(ops,'get_client',AsyncMock(return_value=Broken()));monkeypatch.setattr(ops,'close_client',close)
    with pytest.raises(ValueError):await ops.run(arguments())
    close.assert_awaited_once()


async def test_main_sanitizes_errors_and_prints_success(monkeypatch,capsys):
    args=arguments()
    monkeypatch.setattr(ops,'parser',lambda:type('Parser',(),{'parse_args':lambda self:args})())
    def failed(coro):
        coro.close();raise ValueError('private-cookie')
    monkeypatch.setattr(ops.asyncio,'run',failed)
    assert ops.main()==2 and 'private-cookie' not in capsys.readouterr().err
    monkeypatch.setattr(ops.asyncio,'run',lambda coro:(coro.close(),{'campaigns_resumed':False})[1])
    assert ops.main()==0 and 'false' in capsys.readouterr().out


async def test_invalid_window_sanitizes_parser_error(capsys):
    with pytest.raises(SystemExit):arguments('arm',**{'window-seconds':'private-cookie'})
    assert 'private-cookie' not in capsys.readouterr().err
