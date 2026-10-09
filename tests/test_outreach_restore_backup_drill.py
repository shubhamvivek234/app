"""Opt-in physical dump/restore rehearsal with synthetic data and loopback only.

Generated databases are disposable. No production URI, database name, archive
or provider credentials can be supplied to this drill.
"""
import asyncio
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import uuid

from motor.motor_asyncio import AsyncIOMotorClient
import pytest
import pytest_asyncio

from outreach.core import erasure, suppression, restore_epoch as epoch
from outreach.core import restore_exclusions, restore_suppressions, restore_reply_stops
from outreach.core import restore_invoices, restore_proxy_exclusions
from outreach.core.authorization import canonical_hash
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.paid_access import claim_invoice_reference
from outreach.core.proxy_identity import identity, restore_ip_allowed
from outreach.core.email_finder import is_lead_email_available
from outreach.core.lead_importer import check_compound_suppression
from outreach.ops.restore_exclusions import write_manifest, read_manifest
from outreach.tasks.sequence_executor import _recipient_has_reply

URI = 'mongodb://127.0.0.1:27028/?directConnection=true'
PREFIX = 'test_backup_drill_'
SENDER = 'urn:li:fsd_profile:Sender'
RECIPIENT = 'urn:li:fs_miniProfile:Recipient'
IP = '191.116.125.248'
EMAIL = 'synthetic-reply@example.com'
DATE = datetime(2026, 1, 2, 3, 4, 5, 123000)
EVIDENCE = 'e' * 64
NEW_ANCHOR = '1' * 64

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1'
    or os.getenv('OUTREACH_TEST_PHYSICAL_BACKUP') != '1',
    reason='Owned loopback Mongo and physical backup drill require explicit opt-in')]


async def tool(name: str, *arguments: str) -> None:
    binary = shutil.which(name)
    assert binary, f'{name} is required for the explicitly requested physical drill'
    result = await asyncio.to_thread(subprocess.run, [binary, '--uri', URI, *arguments],
        capture_output=True, timeout=30, check=False)
    assert result.returncode == 0, f'{name} failed in the owned loopback drill'


async def prepare(db, workspace: str) -> None:
    service = epoch.RestoreEpoch(db)
    view = await service.inspect(workspace)
    assert not view['blockers']
    result = await service.prepare(workspace, 'synthetic-operator', EVIDENCE,
        view['digest'], workers_drained=True)
    assert result['prepared'] and result['activation_allowed'] is False


@pytest_asyncio.fixture
async def physical_drill(tmp_path, monkeypatch):
    for flag in epoch.FLAGS:
        monkeypatch.setenv(flag, 'false')
    monkeypatch.setenv('OUTREACH_RESTORE_FENCING_ENABLED', 'true')
    monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH', NEW_ANCHOR)
    names = [PREFIX + kind + '_' + uuid.uuid4().hex for kind in ('source', 'target')]
    assert all(len(name) < 64 for name in names)
    client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=2000)
    owned = False
    try:
        assert (await client.admin.command('hello')).get('setName') == 'unravler-test'
        assert not set(names).intersection(await client.list_database_names())
        owned = True
        tmp_path.chmod(0o700)
        artifacts = tmp_path / 'outside-backup'
        artifacts.mkdir(mode=0o700)
        yield client[names[0]], client[names[1]], tmp_path, artifacts
    finally:
        try:
            if owned:
                for name in names:
                    assert name.startswith(PREFIX) and len(name) < 64
                    await client.drop_database(name)
        finally:
            client.close()


async def seed(db) -> None:
    await db.workspaces.insert_many([{'workspace_id': w, 'owner_id': w + '-actor'}
                                    for w in ('w', 'deleted', 'unrelated')])
    await db.outreach_accounts.create_index([('workspace_id', 1), ('id', 1)], unique=True)
    await db.outreach_accounts.insert_one({'_id': 'sender-row', 'workspace_id': 'w',
        'id': 'sender', 'linkedin_urn': SENDER, 'credential_generation': 'original-g',
        'session_cookie_enc': 'synthetic-retained-ciphertext', 'proxy': {'host': IP, 'proxy_id': 'asset'}})
    await db.outreach_sender_execution.insert_one({**ExecutionPermission.scope('w', 'sender'),
        'status': 'held', 'owner_token': 'original-owner', 'physical_request_token': 'unknown-token',
        'permission_revision': 3, 'permission': {'latched': False, 'credential_generation': 'original-g'}})
    await db.outreach_manual_actions.insert_many([
        {'_id': 'unknown', 'workspace_id': 'w', 'status': 'unknown_outcome', 'owner': 'original-owner',
         'receipt': {'accepted_at': DATE}},
        {'_id': 'pending', 'workspace_id': 'w', 'status': 'queued', 'stages': {'reply': {'status': 'pending'}}}])
    await db.outreach_physical_requests.insert_one({'_id': 'physical', 'workspace_id': 'w',
        'status': 'unknown_outcome', 'mutation': True, 'physical_request_token': 'unknown-token'})
    await db.outreach_request_budgets.insert_one({'_id': 'budget', 'workspace_id': 'w', 'daily_total': 4})
    await db.outreach_campaigns.insert_one({'_id': 'campaign', 'workspace_id': 'w', 'status': 'active',
                                          'authorization_revision': 2, 'auto_launch_enabled': True})
    await db.outreach_proxy_inventory.insert_one({'_id': 'asset', 'workspace_id': 'w',
        'last_workspace_id': 'w', 'provider': 'iproyal_static', 'host': IP,
        'password_enc': 'synthetic-retained-password', 'expires_at': datetime(2027, 1, 1)})
    await db.outreach_proxy_leases.insert_one({'_id': 'asset', 'workspace_id': 'w', 'sender_id': 'sender'})
    await db.outreach_entitlements.insert_one({'_id': 'old-term', 'workspace_id': 'w', 'status': 'revoked',
                                             'seats': 1, 'paid_through': datetime(2027, 1, 1)})
    await db.outreach_payment_receipts.insert_one({'_id': 'old-receipt', 'workspace_id': 'w',
                                                 'seats': 1, 'paid_through': datetime(2027, 1, 1)})


async def later_manifests(db, directory: Path) -> list[tuple[object, str, bytes]]:
    """Synthetic source facts written AFTER the older archive was closed."""
    await db.outreach_email_suppressions.insert_one({'_id': 'email-source', 'workspace_id': 'w',
        'email': EMAIL, 'reason': 'reply', 'created_at': DATE})
    await db.outreach_do_not_contact.insert_one({'_id': 'dnc-source', 'workspace_id': 'w',
        'created_at': DATE, 'vanity_name': 'current', 'identifiers': {'vanity_name': 'old'}})
    await db.outreach_inbox_threads.insert_one({'_id': 'thread-source', 'workspace_id': 'w',
        'account_id': 'sender', 'lead_urn': RECIPIENT, 'has_lead_reply': True,
        'messages': [{'sender_type': 'lead', 'timestamp': DATE, 'body': 'synthetic-private-reply'}]})
    await claim_invoice_reference(db, 'synthetic-new-invoice', 'w', 1, datetime(2027, 1, 1, tzinfo=timezone.utc))
    invoice = await db.account_invoice_guards.find_one({'_id': canonical_hash(['verified_invoice', 'synthetic-new-invoice'])})
    proxy = identity(IP, 'w', 'asset', 'iproyal_static')
    await db.account_proxy_ip_guards.insert_one(proxy)
    await db.outreach_suppression_guards.update_one(suppression.guard_scope('deleted'), {'$set': {
        'erasure_state': 'erased', 'erasure_requested_at': DATE}}, upsert=True)
    uid = canonical_hash(['firebase_identity', 'synthetic-deleted-uid'])
    await db.account_erasure_tombstones.insert_one({'_id': uid, 'requested_at': DATE})
    documents = [
        (restore_exclusions.RestoreExclusions, 'deleted', await restore_exclusions.export_manifest(db, 'deleted', [uid])),
        (restore_suppressions.RestoreSuppressions, 'w', await restore_suppressions.export_manifest(
            db, 'w', ['dnc-source'], ['email-source'], workers_drained=True)),
        (restore_reply_stops.RestoreReplyStops, 'w', await restore_reply_stops.export_manifest(
            db, 'w', ['thread-source'], workers_drained=True)),
        (restore_invoices.RestoreInvoices, 'w', await restore_invoices.export_manifest(
            db, 'w', [invoice['_id']], workers_drained=True)),
        (restore_proxy_exclusions.RestoreProxyExclusions, 'w', await restore_proxy_exclusions.export_manifest(
            db, 'w', [proxy['_id']], workers_drained=True))]
    sources = []
    for number, (service, workspace, document) in enumerate(documents):
        path = directory / f'selected-{number}.json'
        raw = write_manifest(str(path), document)
        assert path.stat().st_mode & 0o777 == 0o600
        assert read_manifest(SimpleNamespace(manifest_file=str(path), manifest_stdin=False)) == raw
        sources.append((service, workspace, raw))
    return sources


@pytest.mark.parametrize('old_prepared_epoch', [False, True])
async def test_physical_older_backup_and_second_rollback_remain_stopped(physical_drill, monkeypatch, old_prepared_epoch):
    original, target, directory, artifacts = physical_drill
    await seed(original)
    if old_prepared_epoch:
        monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH', '0' * 64)
        for workspace in ('w', 'deleted'):
            await prepare(original, workspace)
    archive = directory / 'older.archive.gz'
    archive.touch(mode=0o600, exist_ok=False)
    await tool('mongodump', '--db', original.name, '--gzip', '--archive=' + str(archive))
    assert archive.stat().st_size > 0 and archive.stat().st_mode & 0o777 == 0o600
    archive_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    sources = await later_manifests(original, artifacts)
    monkeypatch.setenv('OUTREACH_EXECUTION_EPOCH', NEW_ANCHOR)
    for cycle in range(2):
        # Database replacement is explicit: --drop alone leaves collections
        # absent from the archive intact. Only this generated target is dropped.
        assert target.name.startswith(PREFIX) and target.client == original.client
        await target.client.drop_database(target.name)
        await tool('mongorestore', '--gzip', '--archive=' + str(archive), '--stopOnError',
            '--nsInclude=' + original.name + '.*', '--nsFrom=' + original.name + '.*',
            '--nsTo=' + target.name + '.*')
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == archive_digest
        assert (await target.outreach_accounts.index_information())['workspace_id_1_id_1']['unique']
        protected = {name: await target[name].find({}).sort('_id', 1).to_list(length=100) for name in (
            'workspaces', 'outreach_accounts', 'outreach_manual_actions', 'outreach_physical_requests',
            'outreach_request_budgets', 'outreach_proxy_inventory', 'outreach_proxy_leases',
            'outreach_entitlements', 'outreach_payment_receipts')}
        original_execution = await target.outreach_sender_execution.find_one({})
        for collection in ('outreach_email_suppressions', 'outreach_do_not_contact', 'outreach_reply_stops',
            'account_invoice_guards', 'account_proxy_ip_guards', 'account_erasure_tombstones',
            'outreach_restore_exclusions', 'outreach_restore_suppressions', 'outreach_restore_reply_stops',
            'outreach_restore_invoices', 'outreach_restore_proxy_exclusions'):
            assert await target[collection].count_documents({}) == 0, (cycle, collection)
        assert await erasure.workspace_is_open(target, 'deleted')
        assert await is_lead_email_available(target, 'w', {'email': EMAIL})
        assert not await _recipient_has_reply(target, 'w', 'sender', {'linkedin_urn': RECIPIENT})
        assert await restore_ip_allowed(target, IP)  # Negative absence, never an activation grant.
        for workspace in ('w', 'deleted'):
            with pytest.raises(epoch.EpochUnavailable):
                await epoch.positive(target, workspace)
            await prepare(target, workspace)
        for service_type, workspace, raw in sources:
            service = service_type(target)
            view = await service.inspect(workspace, raw)
            args = dict(operator='synthetic-operator', source_digest=hashlib.sha256(raw).hexdigest(),
                evidence_digest=EVIDENCE, review_digest=view['digest'], workers_drained=True)
            result = await service.apply(workspace, raw, **args)
            assert result['applied'] and result['activation_allowed'] is False
            assert (await service.apply(workspace, raw, **args))['recovered']
        assert not await erasure.workspace_is_open(target, 'deleted')
        assert await erasure.workspace_is_open(target, 'unrelated')
        assert await erasure.identity_is_erased(target, 'synthetic-deleted-uid')
        assert not await is_lead_email_available(target, 'w', {'email': EMAIL})
        for alias in ('old', 'current'):
            assert await check_compound_suppression('w', [{'vanity_name': alias}], target)
        assert await _recipient_has_reply(target, 'w', 'sender', {'linkedin_urn': RECIPIENT})
        assert not await _recipient_has_reply(target, 'w', 'other', {'linkedin_urn': RECIPIENT})
        assert not await restore_ip_allowed(target, IP)
        assert (await target.account_invoice_guards.find_one({}))['restore_reuse_blocked'] is True
        with pytest.raises(ValueError, match='restore-blocked'):
            await claim_invoice_reference(target, 'synthetic-new-invoice', 'w', 1,
                datetime(2027, 1, 1, tzinfo=timezone.utc), reject_restore_blocked=True)
        for workspace in ('w', 'deleted'):
            with pytest.raises(epoch.EpochUnavailable):
                await epoch.positive(target, workspace)
        with pytest.raises(epoch.EpochUnavailable):
            await ExecutionPermission(target).grant('w', 'sender', 'original-g', ['sequence'], 'synthetic-operator', clear_latch=True)
        for name, before in protected.items():
            after = await target[name].find({}).sort('_id', 1).to_list(length=100)
            if name == 'outreach_manual_actions':
                # Preparation may advance only the shared authority fence counter.
                assert epoch.stable(next(row for row in after if row['_id'] == 'unknown')) == epoch.stable(
                    next(row for row in before if row['_id'] == 'unknown'))
                assert next(row for row in after if row['_id'] == 'pending')['status'] == 'cancelled'
            else:
                assert epoch.stable(after) == epoch.stable(before), name
        execution = await target.outreach_sender_execution.find_one({})
        assert execution['physical_request_token'] == 'unknown-token' and execution['owner_token'] == 'original-owner'
        assert execution['status'] == original_execution['status'] == 'held'
        assert execution['permission']['latched'] is True
        assert execution['permission_revision'] == original_execution['permission_revision'] + 1
        assert (await target.outreach_campaigns.find_one({}))['status'] == 'paused'
        assert await target.outreach_inbox_threads.count_documents({}) == 0
        assert await target.outreach_event_outbox.count_documents({}) == 0
