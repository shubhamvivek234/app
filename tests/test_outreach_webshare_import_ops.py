"""Private import never accepts or reports credential argv / echo fallback."""
import argparse
import getpass
import io
import warnings
from unittest.mock import MagicMock

import pytest
from outreach.ops import webshare_inventory as ops


def test_unsafe_argv_error_is_sanitized(capsys):
    with pytest.raises(SystemExit):
        ops.parser().parse_args(['--proxy-url', 'http://u:private@1.1.1.1:80'])
    assert 'private@' not in capsys.readouterr().err


def test_bounded_stdin_and_oversize(monkeypatch):
    monkeypatch.setattr(ops.sys, 'stdin', io.StringIO('http://u:p@1.1.1.1:80\r\n'))
    assert ops.read_proxy(True) == 'http://u:p@1.1.1.1:80'
    monkeypatch.setattr(ops.sys, 'stdin', io.StringIO('x' * 2052))
    with pytest.raises(ops.ImportUnavailable): ops.read_proxy(True)


def test_hidden_prompt_cannot_fall_back_to_echo(monkeypatch):
    def prompt(*args):
        warnings.warn('cannot hide private material', getpass.GetPassWarning)
        return 'http://u:private@1.1.1.1:80'
    monkeypatch.setattr(ops.getpass, 'getpass', prompt)
    with pytest.raises(ops.ImportUnavailable): ops.read_proxy(False)


@pytest.mark.asyncio
async def test_client_closes_and_exception_contains_no_credentials(monkeypatch):
    args = argparse.Namespace(expires_at='2030-01-01T00:00:00Z', stdin=True)
    monkeypatch.setattr(ops, 'read_proxy', lambda _: 'http://u:private@1.1.1.1:80')
    monkeypatch.setenv('MONGODB_URI', 'mongodb://127.0.0.1:1')
    monkeypatch.delenv('DB_NAME', raising=False)
    client = MagicMock(); monkeypatch.setattr(ops, 'AsyncIOMotorClient', lambda *a, **kw: client)
    with pytest.raises(ops.ImportUnavailable) as error: await ops.run(args)
    assert 'private' not in str(error.value)
    client.close.assert_called_once()


@pytest.mark.asyncio
async def test_cli_requires_explicit_term_timezone(monkeypatch):
    monkeypatch.setattr(ops, 'read_proxy', lambda _: (_ for _ in ()).throw(AssertionError('no secret read')))
    with pytest.raises(ops.ImportUnavailable):
        await ops.run(argparse.Namespace(expires_at='2030-01-01', stdin=True))
