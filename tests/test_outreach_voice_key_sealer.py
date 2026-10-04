"""Private key sealer takes no plaintext argv and installs no configuration."""
from io import StringIO
from unittest.mock import AsyncMock
import stat
import warnings
import pytest


@pytest.mark.asyncio
async def test_private_exclusive_output(tmp_path, monkeypatch, capsys):
    from outreach.ops import voice_key_secret as cli
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'kms_v1')
    monkeypatch.setattr(cli, 'read_secret', lambda _: 'private-key')
    seal = AsyncMock(return_value='uc1:encrypted')
    monkeypatch.setattr(cli, 'seal_key', seal)
    path = tmp_path / 'voice.enc'
    args = cli.parser().parse_args(['--generation', 'g1', '--output', str(path)])
    assert (await cli.run(args))['status'] == 'encrypted_file_ready'
    assert path.read_text() == 'uc1:encrypted\n'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    seal.assert_awaited_once_with('private-key', 'g1')
    with pytest.raises(cli.SealerUnavailable): await cli.run(args)
    assert seal.await_count == 1
    assert 'private-key' not in str(capsys.readouterr())


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['symlink', 'legacy', 'kms', 'write', 'invalid'])
async def test_failure_preserves_existing_and_no_partial_file(tmp_path, monkeypatch, failure):
    from outreach.ops import voice_key_secret as cli
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'kms_v1')
    monkeypatch.setattr(cli, 'read_secret', lambda _: 'mock' if failure == 'invalid' else 'private-key')
    seal = AsyncMock(return_value='uc1:encrypted')
    monkeypatch.setattr(cli, 'seal_key', seal)
    existing = tmp_path / 'existing'; existing.write_text('original')
    path = tmp_path / 'new'
    if failure == 'symlink': path.symlink_to(existing)
    if failure == 'legacy': monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    if failure == 'kms': seal.side_effect = ValueError('private AWS detail')
    if failure == 'write': monkeypatch.setattr(cli, 'write_envelope', lambda *_: (_ for _ in ()).throw(OSError('private')))
    args = cli.parser().parse_args(['--generation', 'g1', '--output', str(path)])
    with pytest.raises(cli.SealerUnavailable) as error: await cli.run(args)
    assert 'private' not in str(error.value)
    assert existing.read_text() == 'original'
    assert path.is_symlink() or not path.exists()


@pytest.mark.parametrize('value', ['', 'two\nlines', 'x' * 1025, 'é' * 513, 'mock', 'uc1:plaintext', 'x' * 1024 + '\n\nignored'])
def test_bounded_input(monkeypatch, value):
    from outreach.ops import voice_key_secret as cli
    monkeypatch.setattr(cli.sys, 'stdin', StringIO(value))
    with pytest.raises(cli.SealerUnavailable): cli.read_secret(True)


def test_hidden_input_and_no_secret_cli_argument(monkeypatch):
    from outreach.ops import voice_key_secret as cli
    monkeypatch.setattr(cli.sys, 'stdin', StringIO('private-key\r\n'))
    assert cli.read_secret(True) == 'private-key'
    monkeypatch.setattr(cli.getpass, 'getpass', lambda _: 'private-key')
    assert cli.read_secret(False) == 'private-key'
    def echoed(_): warnings.warn('echo fallback', cli.getpass.GetPassWarning)
    monkeypatch.setattr(cli.getpass, 'getpass', echoed)
    with pytest.raises(cli.SealerUnavailable): cli.read_secret(False)
    with pytest.raises(SystemExit): cli.parser().parse_args(['--key', 'private-key'])


@pytest.mark.parametrize('failure', [False, True])
def test_main_sanitizes_failure(tmp_path, monkeypatch, capsys, failure):
    from outreach.ops import voice_key_secret as cli
    monkeypatch.setattr(cli.sys, 'argv', ['sealer', '--generation', 'g', '--output', str(tmp_path / 'out')])
    monkeypatch.setattr(cli, 'run', AsyncMock(side_effect=cli.SealerUnavailable('private') if failure else None))
    assert cli.main() == (2 if failure else 0)
    assert 'private' not in str(capsys.readouterr())


def test_invalid_cli_arguments_never_echo_accidental_key(capsys):
    from outreach.ops import voice_key_secret as cli
    with pytest.raises(SystemExit):
        cli.parser().parse_args(['--generation', 'g', '--output', '/tmp/unused', '--key', 'accidental-private-key'])
    assert 'accidental-private-key' not in str(capsys.readouterr())
