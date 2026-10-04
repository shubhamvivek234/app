"""Private app-secret sealer never emits plaintext or overwrites evidence."""
import os
import stat
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_sealer_uses_environment_app_and_exclusive_private_output(tmp_path, monkeypatch, capsys):
    from outreach.ops import oauth_app_secret as cli
    monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_ID", "app-id")
    monkeypatch.setenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "kms_v1")
    monkeypatch.setattr(cli, "read_secret", lambda _: "private-secret")
    seal = AsyncMock(return_value="uc1:encrypted")
    monkeypatch.setattr(cli, "seal_app_secret", seal)
    target = tmp_path / "app.enc"
    args = cli.parser().parse_args(["--provider", "gmail", "--generation", "generation", "--output", str(target)])
    await cli.run(args)
    assert target.read_text() == "uc1:encrypted\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    seal.assert_awaited_once_with("private-secret", "gmail", "app-id", "generation")
    assert "private-secret" not in str(capsys.readouterr())
    with pytest.raises(cli.SealerUnavailable): await cli.run(args)
    assert seal.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["symlink", "mode", "missing_id", "key", "size", "write"])
async def test_sealer_failure_never_leaves_partial_file_or_changes_existing(tmp_path, monkeypatch, failure):
    from outreach.ops import oauth_app_secret as cli
    monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_ID", "app-id")
    monkeypatch.setenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "kms_v1")
    monkeypatch.setattr(cli, "read_secret", lambda _: "x" * 32769 if failure == "size" else "private-secret")
    seal = AsyncMock(return_value="uc1:encrypted")
    monkeypatch.setattr(cli, "seal_app_secret", seal)
    target = tmp_path / "new.enc"
    existing = tmp_path / "existing"
    existing.write_text("original")
    if failure == "symlink": target.symlink_to(existing)
    if failure == "mode": monkeypatch.setenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "legacy_fernet")
    if failure == "missing_id": monkeypatch.delenv("OUTREACH_GMAIL_CLIENT_ID")
    if failure == "key": seal.side_effect = ValueError("private provider failure")
    if failure == "write": monkeypatch.setattr(cli, "write_envelope", lambda *_: (_ for _ in ()).throw(OSError("private disk error")))
    args = cli.parser().parse_args(["--provider", "gmail", "--generation", "g", "--output", str(target)])
    with pytest.raises(cli.SealerUnavailable) as error: await cli.run(args)
    assert "private" not in str(error.value)
    assert existing.read_text() == "original"
    assert target.is_symlink() or not target.exists()


def test_sealer_input_is_bounded_and_cli_never_accepts_secret_argument(monkeypatch):
    from io import StringIO
    from outreach.ops import oauth_app_secret as cli
    monkeypatch.setattr(cli.sys, "stdin", StringIO("private-secret\n"))
    assert cli.read_secret(True) == "private-secret"
    monkeypatch.setattr(cli.sys, "stdin", StringIO("x" * 32769))
    with pytest.raises(cli.SealerUnavailable): cli.read_secret(True)
    with pytest.raises(SystemExit): cli.parser().parse_args(["--client-secret", "secret"])


@pytest.mark.parametrize("value", ["x" * 32768 + "\n\n" + "ignored", "é" * 17000, "", "two\nlines"])
def test_sealer_rejects_truncated_multiline_or_byte_oversized_input(monkeypatch, value):
    from io import StringIO
    from outreach.ops import oauth_app_secret as cli
    monkeypatch.setattr(cli.sys, "stdin", StringIO(value))
    with pytest.raises(cli.SealerUnavailable): cli.read_secret(True)


def test_sealer_never_falls_back_to_echoed_terminal_input(monkeypatch):
    from outreach.ops import oauth_app_secret as cli
    import warnings
    def no_hidden_terminal(_): warnings.warn("terminal fallback", cli.getpass.GetPassWarning)
    monkeypatch.setattr(cli.getpass, "getpass", no_hidden_terminal)
    with pytest.raises(cli.SealerUnavailable): cli.read_secret(False)


@pytest.mark.parametrize("replacement", [False, True])
def test_real_partial_output_cleanup_preserves_replacement_inode(tmp_path, monkeypatch, replacement):
    from outreach.ops import oauth_app_secret as cli
    target = tmp_path / "app.enc"
    def failed(_):
        if replacement:
            target.unlink()
            target.write_text("replacement")
        raise OSError("local disk failure")
    monkeypatch.setattr(cli.os, "fsync", failed)
    with pytest.raises(OSError): cli.write_envelope(target, "uc1:encrypted")
    if replacement: assert target.read_text() == "replacement"
    else: assert not target.exists()


@pytest.mark.parametrize("value", ["plain", "uc1:" + "x" * 60001, None])
def test_sealer_rejects_invalid_envelope_before_creating_file(tmp_path, value):
    from outreach.ops import oauth_app_secret as cli
    target = tmp_path / "app.enc"
    with pytest.raises(cli.SealerUnavailable): cli.write_envelope(target, value)
    assert not target.exists()


@pytest.mark.asyncio
async def test_app_identity_change_while_sealing_does_not_write_output(tmp_path, monkeypatch):
    from outreach.ops import oauth_app_secret as cli
    monkeypatch.setenv("OUTREACH_CREDENTIAL_CUSTODY_MODE", "kms_v1")
    monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_ID", "original")
    monkeypatch.setattr(cli, "read_secret", lambda _: "private")
    async def rotated(*args):
        monkeypatch.setenv("OUTREACH_GMAIL_CLIENT_ID", "replacement")
        return "uc1:encrypted"
    monkeypatch.setattr(cli, "seal_app_secret", rotated)
    target = tmp_path / "app.enc"
    args = cli.parser().parse_args(["--provider", "gmail", "--generation", "g", "--output", str(target)])
    with pytest.raises(cli.SealerUnavailable): await cli.run(args)
    assert not target.exists()


@pytest.mark.parametrize("failure", [False, True])
def test_cli_exit_is_sanitized_and_prompt_is_hidden(tmp_path, monkeypatch, capsys, failure):
    from outreach.ops import oauth_app_secret as cli
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: "prompt-secret")
    assert cli.read_secret(False) == "prompt-secret"
    monkeypatch.setattr(cli.sys, "argv", ["sealer", "--provider", "gmail", "--generation", "g", "--output", str(tmp_path / "out")])
    monkeypatch.setattr(cli, "run", AsyncMock(side_effect=cli.SealerUnavailable("private") if failure else None))
    assert cli.main() == (2 if failure else 0)
    assert "private" not in str(capsys.readouterr())
