"""Private proxy controls cannot echo accidental credential arguments or errors."""
import argparse
from unittest.mock import AsyncMock, MagicMock

import pytest

from outreach.ops import proxy_custody as ops
from tests.test_outreach_webshare_migration import webshare_db, scoped, ASSET, EVIDENCE


@pytest.mark.parametrize('argv', [ ['migrate','--proxy-url','http://u:private-password@1.1.1.1:80'],
    ['unsafe-private-password'], ['migrate','--workspace','w','--asset','a','--operator','o',
    '--evidence-digest','x','--review-digest','x','--workers-drained','x','--cookie','private-password'] ])
def test_argument_errors_never_echo_supplied_secrets(argv,capsys):
    with pytest.raises(SystemExit):ops.parser().parse_args(argv)
    assert 'private-password' not in capsys.readouterr().err


@pytest.mark.asyncio
async def test_cli_uses_exact_review_and_cache_drain_acknowledgement(webshare_db):
    inspect=argparse.Namespace(command='inspect',workspace='w',asset=ASSET)
    view=await ops.run_db(inspect,webshare_db)
    migrate=argparse.Namespace(command='migrate',workspace='w',asset=ASSET,operator='operator',
        evidence_digest=EVIDENCE,review_digest=view['digest'],workers_drained='I_PAUSED_AND_DRAINED_ALL_CREDENTIAL_WRITERS')
    with pytest.raises(ValueError):await ops.run_db(migrate,webshare_db)
    migrate.workers_drained=ops.DRAIN_ACK
    assert (await ops.run_db(migrate,webshare_db))['current_matches']


@pytest.mark.asyncio
async def test_client_closes_when_database_selection_fails(monkeypatch):
    client=MagicMock();get=AsyncMock(return_value=client);close=AsyncMock()
    monkeypatch.setattr(ops,'get_client',get);monkeypatch.setattr(ops,'close_client',close)
    monkeypatch.delenv('DB_NAME',raising=False)
    with pytest.raises(KeyError):await ops.run(argparse.Namespace())
    close.assert_awaited_once()


def test_runtime_errors_never_echo_credential_material(monkeypatch,capsys):
    monkeypatch.setattr(ops.sys,'argv',['proxy_custody','inspect','--workspace','w','--asset',ASSET])
    monkeypatch.setattr(ops,'run',AsyncMock(side_effect=ValueError('private-password')))
    assert ops.main()==2
    assert 'private-password' not in capsys.readouterr().err
