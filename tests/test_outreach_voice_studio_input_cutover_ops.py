"""Private cutover CLI exposes references and exact drain assertions only."""
from unittest.mock import AsyncMock

import pytest

from outreach.ops import voice_studio_input_cutover as ops
from outreach.ops.proxy_custody import DRAIN_ACK
from tests.test_outreach_voice_studio_input_cutover import pending, studio_db, EVIDENCE

pytestmark = pytest.mark.asyncio


def arguments(job, command='inspect', **changes):
    values = ['--workspace', 'w', '--job', job]
    if command == 'stop':
        extra = {'operator': 'operator', 'evidence-digest': EVIDENCE, 'review-digest': 'b'*64, 'workers-drained': DRAIN_ACK}
        extra.update(changes)
        values += [item for key, value in extra.items() for item in ('--'+key, value)]
    return ops.parser().parse_args([command, *values])


async def test_inspection_and_stop_only(pending):
    db, job = pending
    view = await ops.run_db(arguments(job['_id']), db)
    result = await ops.run_db(arguments(job['_id'], 'stop', **{'review-digest': view['digest']}), db)
    assert result['current_matches'] and not result['activation_allowed']


async def test_exact_drain_required(pending):
    db, job = pending
    with pytest.raises(Exception): await ops.run_db(arguments(job['_id'], 'stop', **{'workers-drained': 'yes'}), db)
    assert 'input_enc' in job


@pytest.mark.parametrize('flag', ['--audio', '--password', '--source', '--replay', '--activate'])
async def test_private_values_are_not_echoed(capsys, flag):
    with pytest.raises(SystemExit) as error:
        ops.parser().parse_args(['inspect', '--workspace', 'w', '--job', 'a'*64, flag, 'private-value'])
    assert error.value.code == 2 and 'private-value' not in capsys.readouterr().err


async def test_client_closes_on_error(monkeypatch):
    class Broken:
        def __getitem__(self, name): raise ValueError('private-value')
    close = AsyncMock()
    monkeypatch.setenv('DB_NAME', 'unused')
    monkeypatch.setattr(ops, 'get_client', AsyncMock(return_value=Broken()))
    monkeypatch.setattr(ops, 'close_client', close)
    with pytest.raises(ValueError): await ops.run(arguments('a'*64))
    close.assert_awaited_once()


async def test_main_sanitizes_runtime_errors_and_prints_success(monkeypatch, capsys):
    args = arguments('a'*64)
    monkeypatch.setattr(ops, 'parser', lambda: type('Parser', (), {'parse_args': lambda self: args})())
    def failed(coro):
        coro.close()
        raise ValueError('private-value')
    monkeypatch.setattr(ops.asyncio, 'run', failed)
    assert ops.main() == 2 and 'private-value' not in capsys.readouterr().err
    monkeypatch.setattr(ops.asyncio, 'run', lambda coro: (coro.close(), {'activation_allowed': False})[1])
    assert ops.main() == 0 and 'false' in capsys.readouterr().out
