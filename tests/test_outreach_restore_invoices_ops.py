"""Private file reuse and recipient-free CLI output/failures."""
import hashlib
import io
import json
from unittest.mock import AsyncMock
import pytest
from outreach.ops import restore_invoices as ops
from tests.test_outreach_restore_invoices import suppression_db, source, fake_closed_control, INVOICE, BINDING
EMAIL = "private-invoice"
from tests.test_outreach_restore_epoch import EVIDENCE, restored_db

pytestmark = [pytest.mark.asyncio, pytest.mark.restore_epoch]


def args(path, command='inspect', view=None):
    flags = [command, '--workspace', 'w', '--manifest-file', str(path)]
    if command == 'apply':
        flags += ['--operator', 'operator', '--evidence-digest', EVIDENCE,
                  '--source-digest', hashlib.sha256(source()).hexdigest(), '--review-digest', view['digest'],
                  '--all-writers-and-caches-drained']
    return ops.parser().parse_args(flags)


async def test_private_file_inspect_apply_has_no_recipient_echo(suppression_db, tmp_path):
    path = tmp_path / 'source'; path.write_bytes(source()); path.chmod(0o600)
    view = await ops.run_db(args(path), suppression_db)
    result = await ops.run_db(args(path, 'apply', view), suppression_db)
    assert result['applied'] and EMAIL not in json.dumps([view, result])


async def test_export_exclusive_private_output_and_source_reference_only(suppression_db, tmp_path):
    suppression_db.account_invoice_guards.docs.append({'_id': INVOICE, 'binding_digest': BINDING})
    tmp_path.chmod(0o700); path = tmp_path / 'export'
    argv = ['export', '--workspace', 'w', '--invoice-digest', INVOICE, '--output-file', str(path),
            '--all-writers-and-caches-drained']
    result = await ops.run_db(ops.parser().parse_args(argv), suppression_db)
    assert EMAIL not in json.dumps(result) and EMAIL not in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError): await ops.run_db(ops.parser().parse_args(argv), suppression_db)


@pytest.mark.parametrize('flag', ['--cookie', '--uid', '--key', '--recipient', '--grant', '--activate', '--replay'])
async def test_parser_rejects_and_never_echoes_material(capsys, flag):
    with pytest.raises(SystemExit): ops.parser().parse_args(['inspect', '--workspace', 'w', '--manifest-stdin', flag, EMAIL])
    assert EMAIL not in capsys.readouterr().err


@pytest.mark.parametrize('unsafe', ['mode', 'symlink', 'oversize'])
async def test_import_reuses_private_file_guards(tmp_path, unsafe):
    path = tmp_path / 'source'; path.write_bytes(source()); path.chmod(0o600)
    if unsafe == 'mode': path.chmod(0o644)
    if unsafe == 'symlink':
        linked = tmp_path / 'link'; linked.symlink_to(path); path = linked
    if unsafe == 'oversize': path.write_bytes(b'x' * 65537)
    with pytest.raises((ValueError, OSError)): ops.read_manifest(args(path))


async def test_stdin_runtime_input_precedes_connection_and_closes_on_failure(monkeypatch, tmp_path, capsys):
    get = AsyncMock(return_value={}); close = AsyncMock()
    monkeypatch.setattr(ops, 'get_client', get); monkeypatch.setattr(ops, 'close_client', close)
    with pytest.raises(OSError): await ops.run(args(tmp_path / 'missing'))
    get.assert_not_awaited()
    namespace = ops.parser().parse_args(['inspect', '--workspace', 'w', '--manifest-stdin'])
    monkeypatch.setattr('sys.stdin', type('Input', (), {'buffer': io.BytesIO(source())})())
    monkeypatch.setenv('DB_NAME', 'missing')
    with pytest.raises(KeyError): await ops.run(namespace)
    close.assert_awaited_once()
    monkeypatch.setattr(ops, 'parser', lambda: type('Parser', (), {'parse_args': lambda self: namespace})())
    def fail(coro): coro.close(); raise ValueError(EMAIL)
    monkeypatch.setattr(ops.asyncio, 'run', fail)
    assert ops.main() == 2 and EMAIL not in capsys.readouterr().err
    monkeypatch.setattr(ops.asyncio, 'run', lambda coro: (coro.close(), {'activation_allowed': False})[1])
    assert ops.main() == 0 and 'false' in capsys.readouterr().out


async def test_source_drain_is_required_for_export(capsys):
    with pytest.raises(SystemExit): ops.parser().parse_args(['export', '--workspace', 'w', '--invoice-digest',
        'original', '--output-file', '/tmp/unused'])


@pytest.mark.parametrize('status,revoked', [('active', False), ('expired', False), ('active', True)])
async def test_pilot_payment_output_reports_current_state_without_activation_claim(monkeypatch, capsys, status, revoked):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from outreach.ops import pilot
    term = datetime(2026, 11, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(pilot, 'record_verified_payment', AsyncMock(return_value={'workspace_id': 'w',
        'status': status, 'is_revoked': revoked, 'seats': 1, 'paid_through': term}))
    args = SimpleNamespace(command='record-payment', verified_in_processor='I_VERIFIED_THIS_INVOICE',
        workspace='w', invoice_id='private-invoice', operator='operator', seats=1, paid_through=term)
    await pilot._run_db(args, object())
    output = capsys.readouterr().out
    returned = json.loads(output)
    assert returned['status'] == status and returned['is_revoked'] == revoked
    assert 'Activated' not in output and 'private-invoice' not in output
