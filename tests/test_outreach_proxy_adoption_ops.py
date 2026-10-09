"""Reference-only CLI rejects secret/fact arguments and closes selected clients."""
from unittest.mock import AsyncMock

import pytest

from outreach.ops import proxy_adoption as ops
from outreach.ops.proxy_custody import DRAIN_ACK
from tests.test_outreach_proxy_adoption import legacy_db, scoped, webshare_db, ASSET, EVIDENCE

pytestmark = pytest.mark.asyncio


def arguments(command='inspect', **changes):
    values = ['--workspace', 'w', '--asset', ASSET]
    if command == 'adopt':
        extra = {'operator': 'operator', 'evidence-digest': EVIDENCE, 'review-digest': 'a' * 64,
            'workers-drained': DRAIN_ACK}
        extra.update(changes)
        values += [item for key, value in extra.items() for item in ('--' + key, value)]
    return ops.parser().parse_args([command, *values])


async def test_inspect_and_apply_use_exact_metadata_without_secret_inputs(legacy_db):
    view = await ops.run_db(arguments(), legacy_db)
    assert not view['blockers'] and 'private-password' not in str(view)
    result = await ops.run_db(arguments('adopt', **{'review-digest':view['digest']}), legacy_db)
    assert result['current_matches'] and not result['activation_allowed']


async def test_drain_acknowledgement_is_exact(legacy_db):
    view = await ops.run_db(arguments(), legacy_db)
    with pytest.raises(Exception):
        await ops.run_db(arguments('adopt', **{'review-digest':view['digest'], 'workers-drained':'yes'}), legacy_db)
    assert not legacy_db.outreach_proxy_adoptions.docs


@pytest.mark.parametrize('flag', ['--password', '--proxy-url', '--expires-at', '--order'])
async def test_caller_cannot_supply_new_secret_or_purchase_facts(capsys, flag):
    with pytest.raises(SystemExit) as error:
        ops.parser().parse_args(['inspect', '--workspace', 'w', '--asset', ASSET, flag, 'secret-not-echoed'])
    assert error.value.code == 2 and 'secret-not-echoed' not in capsys.readouterr().err


async def test_database_selection_failure_still_closes_client(monkeypatch):
    class Broken:
        def __getitem__(self, name): raise ValueError('secret-not-echoed')
    close = AsyncMock()
    monkeypatch.setenv('DB_NAME', 'ignored')
    monkeypatch.setattr(ops, 'get_client', AsyncMock(return_value=Broken()))
    monkeypatch.setattr(ops, 'close_client', close)
    with pytest.raises(ValueError): await ops.run(arguments())
    close.assert_awaited_once()


async def test_main_sanitizes_runtime_failure(monkeypatch, capsys):
    args = type('Args', (), {'command':'inspect', 'workspace':'w', 'asset':ASSET})()
    monkeypatch.setattr(ops, 'parser', lambda: type('Parser', (), {'parse_args':lambda self:args})())
    monkeypatch.setattr(ops.asyncio, 'run', lambda coro: (coro.close(), (_ for _ in ()).throw(ValueError('secret-not-echoed')))[1])
    assert ops.main() == 2
    captured = capsys.readouterr()
    assert 'secret-not-echoed' not in captured.err + captured.out
