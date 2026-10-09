"""Private exclusion files deny symlink, overwrite, unsafe mode and oversized input."""
import hashlib
import io
import json
import os
from unittest.mock import AsyncMock
import pytest
from outreach.ops import restore_exclusions as ops
from tests.test_outreach_restore_exclusions import excluded_db, source, IDENTITY
from tests.test_outreach_restore_epoch import EVIDENCE, restored_db
pytestmark = [pytest.mark.asyncio, pytest.mark.restore_epoch]


def args(path, command='inspect', view=None):
    flags = [command, '--workspace', 'w', '--manifest-file', str(path)]
    if command == 'apply':
        flags += ['--operator', 'operator', '--evidence-digest', EVIDENCE,
                  '--source-digest', hashlib.sha256(source()).hexdigest(), '--review-digest', view['digest'],
                  '--all-writers-and-caches-drained']
    return ops.parser().parse_args(flags)


async def test_inspect_apply_private_file_and_no_identity_echo(excluded_db, tmp_path):
    path = tmp_path / 'source.json'; path.write_bytes(source()); path.chmod(0o600)
    view = await ops.run_db(args(path), excluded_db)
    result = await ops.run_db(args(path, 'apply', view), excluded_db)
    assert result['applied'] and not result['purged']
    assert IDENTITY not in json.dumps(result)


@pytest.mark.parametrize('fault', ['symlink', 'mode', 'hardlink', 'empty', 'oversize', 'directory'])
async def test_unproven_file_rejected(tmp_path, fault):
    path = tmp_path / 'source'; path.write_bytes(source()); path.chmod(0o600)
    if fault == 'symlink':
        link = tmp_path / 'link'; link.symlink_to(path); path = link
    if fault == 'mode': path.chmod(0o644)
    if fault == 'hardlink': os.link(path, tmp_path / 'linked')
    if fault == 'empty': path.write_bytes(b'')
    if fault == 'oversize': path.write_bytes(b'x' * 65537)
    if fault == 'directory': path = tmp_path
    with pytest.raises((ValueError, OSError)): ops.read_manifest(args(path))


async def test_bounded_stdin_and_exclusive_export(tmp_path, monkeypatch):
    namespace = ops.parser().parse_args(['inspect', '--workspace', 'w', '--manifest-stdin'])
    monkeypatch.setattr(ops.sys, 'stdin', type('Input', (), {'buffer': io.BytesIO(source())})())
    assert ops.read_manifest(namespace) == source()
    monkeypatch.setattr(ops.sys, 'stdin', type('Input', (), {'buffer': io.BytesIO(b'x' * 65537)})())
    with pytest.raises(ValueError): ops.read_manifest(namespace)
    tmp_path.chmod(0o700); path = tmp_path / 'export'
    raw = ops.write_manifest(str(path), json.loads(source()))
    assert path.read_bytes() == raw and path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError): ops.write_manifest(str(path), {})
    assert path.read_bytes() == raw
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError): ops.write_manifest(str(tmp_path / 'another'), {})


async def test_export_writes_only_private_source_and_returns_digest(excluded_db, tmp_path):
    from datetime import datetime, timezone
    db = excluded_db
    db.outreach_suppression_guards.docs[0].update({'erasure_state': 'stopped',
        'erasure_requested_at': datetime(2026, 1, 1, tzinfo=timezone.utc)})
    db.account_erasure_tombstones.docs.append({'_id': IDENTITY,
        'requested_at': datetime(2026, 1, 1, tzinfo=timezone.utc)})
    tmp_path.chmod(0o700); path = tmp_path / 'manifest.json'
    namespace = ops.parser().parse_args(['export', '--workspace', 'w', '--identity-digest', IDENTITY, '--output-file', str(path)])
    result = await ops.run_db(namespace, db)
    assert result['source_digest'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert IDENTITY not in json.dumps(result) and result['exported']


@pytest.mark.parametrize('flag', ['--cookie', '--uid', '--key', '--grant', '--activate', '--replay'])
async def test_parser_never_accepts_or_echoes_private_material(capsys, flag):
    with pytest.raises(SystemExit): ops.parser().parse_args(['inspect', '--workspace', 'w', '--manifest-stdin', flag, 'private-value'])
    assert 'private-value' not in capsys.readouterr().err


async def test_runtime_sanitizes_failure_closes_client_and_rejects_input_first(monkeypatch, tmp_path, capsys):
    get = AsyncMock(return_value={}); close = AsyncMock()
    monkeypatch.setattr(ops, 'get_client', get); monkeypatch.setattr(ops, 'close_client', close)
    path = tmp_path / 'missing'
    with pytest.raises(OSError): await ops.run(args(path))
    get.assert_not_awaited()
    path.write_bytes(source()); path.chmod(0o600); monkeypatch.setenv('DB_NAME', 'missing')
    with pytest.raises(KeyError): await ops.run(args(path))
    close.assert_awaited_once()
    namespace = args(path)
    monkeypatch.setattr(ops, 'parser', lambda: type('Parser', (), {'parse_args': lambda self: namespace})())
    def fail(coro): coro.close(); raise ValueError('private-value')
    monkeypatch.setattr(ops.asyncio, 'run', fail)
    assert ops.main() == 2 and 'private-value' not in capsys.readouterr().err
    monkeypatch.setattr(ops.asyncio, 'run', lambda coro: (coro.close(), {'activation_allowed': False})[1])
    assert ops.main() == 0 and 'false' in capsys.readouterr().out


async def test_source_changed_during_read_is_rejected(monkeypatch, tmp_path):
    from types import SimpleNamespace
    path = tmp_path / 'source'; path.write_bytes(source()); path.chmod(0o600)
    original = ops.os.fstat; calls = 0
    def changed(fd):
        nonlocal calls
        row = original(fd); calls += 1
        if calls == 2:
            return SimpleNamespace(st_dev=row.st_dev, st_ino=row.st_ino,
                st_size=row.st_size, st_mtime_ns=row.st_mtime_ns + 1)
        return row
    monkeypatch.setattr(ops.os, 'fstat', changed)
    with pytest.raises(ValueError): ops.read_manifest(args(path))


@pytest.mark.parametrize('replacement', [False, True])
async def test_failed_export_removes_only_its_own_partial_file(monkeypatch, tmp_path, replacement):
    tmp_path.chmod(0o700); path = tmp_path / 'output'
    def failed(fd):
        if replacement:
            path.unlink(); path.write_bytes(b'replacement'); path.chmod(0o600)
        raise OSError('Synthetic write failure')
    monkeypatch.setattr(ops.os, 'fsync', failed)
    with pytest.raises(OSError): ops.write_manifest(str(path), json.loads(source()))
    assert path.exists() == replacement
    if replacement: assert path.read_bytes() == b'replacement'


async def test_oversize_export_never_creates_output(tmp_path):
    tmp_path.chmod(0o700); path = tmp_path / 'output'
    with pytest.raises(ValueError): ops.write_manifest(str(path), {'unknown': 'x' * 65536})
    assert not path.exists()
