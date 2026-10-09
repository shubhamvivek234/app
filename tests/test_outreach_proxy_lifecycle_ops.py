"""Lazy hidden input and sanitized errors for reviewed proxy lifecycle commands."""
import argparse
import getpass
import io
import warnings
from unittest.mock import AsyncMock, Mock

import pytest

from outreach.ops import proxy_lifecycle as ops
from tests.test_outreach_webshare_migration import webshare_db, scoped, ASSET, EVIDENCE, convert


@pytest.mark.parametrize('argv',[['rotate','--password','private-password'],['private-password'],
    ['rotate','--proxy-url','http://u:private-password@1.1.1.1:80']])
def test_argv_rejections_do_not_echo_credentials(argv,capsys):
    with pytest.raises(SystemExit):ops.parser().parse_args(argv)
    assert 'private-password' not in capsys.readouterr().err


def test_hidden_prompt_never_falls_back_to_echo(monkeypatch):
    def prompt(*args):
        warnings.warn('Cannot hide input',getpass.GetPassWarning);return 'private-password'
    monkeypatch.setattr(ops.getpass,'getpass',prompt)
    with pytest.raises(ValueError):ops.read_password(False)


def test_bounded_explicit_stdin(monkeypatch):
    monkeypatch.setattr(ops.sys,'stdin',io.StringIO('private-password\r\n'))
    assert ops.read_password(True)=='private-password'
    monkeypatch.setattr(ops.sys,'stdin',io.StringIO('x'*300))
    with pytest.raises(ValueError):ops.read_password(True)


@pytest.mark.asyncio
async def test_lazy_cli_skips_password_for_rejected_review_and_saved_receipt(webshare_db,monkeypatch):
    db=webshare_db;await convert(db)
    view=await ops.run_db(argparse.Namespace(command='inspect-rotate',workspace='w',asset=ASSET),db)
    args=argparse.Namespace(command='rotate',workspace='w',asset=ASSET,operator='operator',evidence_digest=EVIDENCE,
        provider_reference='change-1',review_digest=view['digest'],workers_drained='incorrect',stdin=False)
    read=Mock(side_effect=AssertionError('No hidden input'));monkeypatch.setattr(ops,'read_password',read)
    with pytest.raises(ValueError):await ops.run_db(args,db)
    read.assert_not_called()
    read.side_effect=None;read.return_value='private-password';args.workers_drained=ops.DRAIN_ACK
    first=await ops.run_db(args,db);read.assert_called_once()
    read.reset_mock();read.side_effect=AssertionError('No retry input')
    assert await ops.run_db(args,db)==first;read.assert_not_called()


@pytest.mark.asyncio
async def test_client_closes_after_missing_database(monkeypatch):
    close=AsyncMock();monkeypatch.setattr(ops,'close_client',close)
    monkeypatch.setattr(ops,'get_client',AsyncMock(return_value=Mock()))
    monkeypatch.delenv('DB_NAME',raising=False)
    with pytest.raises(KeyError):await ops.run(argparse.Namespace())
    close.assert_awaited_once()


def test_main_sanitizes_runtime_errors(monkeypatch,capsys):
    monkeypatch.setattr(ops.sys,'argv',['proxy_lifecycle','inspect-renew','--workspace','w','--asset',ASSET])
    monkeypatch.setattr(ops,'run',AsyncMock(side_effect=RuntimeError('private-password')))
    assert ops.main()==2 and 'private-password' not in capsys.readouterr().err


@pytest.mark.asyncio
@pytest.mark.parametrize('timezone_present',[True,False])
async def test_renew_cli_requires_explicit_timezone_and_never_requests_password(webshare_db,monkeypatch,timezone_present):
    from datetime import datetime,timedelta,timezone
    db=webshare_db;monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    view=await ops.run_db(argparse.Namespace(command='inspect-renew',workspace='w',asset=ASSET),db)
    target=datetime.now(timezone.utc)+timedelta(days=60)
    if not timezone_present:target=target.replace(tzinfo=None)
    args=argparse.Namespace(command='renew',workspace='w',asset=ASSET,operator='operator',evidence_digest=EVIDENCE,
        provider_reference='change-1',review_digest=view['digest'],workers_drained=ops.DRAIN_ACK,expires_at=target.isoformat())
    read=Mock(side_effect=AssertionError('No password read'));monkeypatch.setattr(ops,'read_password',read)
    if timezone_present:assert (await ops.run_db(args,db))['current_matches']
    else:
        with pytest.raises(ValueError):await ops.run_db(args,db)
    read.assert_not_called()
