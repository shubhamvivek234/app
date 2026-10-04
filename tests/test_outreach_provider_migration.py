"""Stopped, bounded provider custody conversion and metadata-only replay."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest
from tests.outreach_memory import Database
from tests.test_outreach_session_custody import scoped
from outreach.core.sender_execution import SenderExecution
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.provider_credential_migration import ProviderCredentialMigration
from utils.encryption import encrypt

@pytest.fixture
def provider_db(scoped, monkeypatch):
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
    return Database(outreach_accounts=[{'workspace_id':'w','id':'a','status':'paused','credential_generation':'cookie-generation'}],
        outreach_sender_execution=[{**SenderExecution.scope('w','a'),'status':'idle','permission':{'latched':True}}],
        outreach_mailboxes=[{'workspace_id':'w','sender_account_id':'a','provider':'gmail','provider_user_id':'u',
            'email':'sender@example.com','connection_job_id':'job','status':'reauth_required','history_id':'cursor',
            'access_token_enc':encrypt('old-access'),'refresh_token_enc':encrypt('old-refresh'),
            'token_expires_at':datetime.now(timezone.utc)+timedelta(hours=1)}],
        outreach_hunter_credentials=[{'workspace_id':'w','api_key_enc':encrypt('private-hunter-key')}])

@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['mailbox','finder'])
async def test_migration_preserves_identity_stopped_permissions_and_receipt_without_reseal(provider_db, monkeypatch, kind):
    from outreach.core.provider_custody import prepare_mailbox_access, prepare_finder_key
    service=ProviderCredentialMigration(provider_db);sender='a' if kind=='mailbox' else None
    before=deepcopy(provider_db.outreach_accounts.docs)
    view=await service.inspect('w',kind,sender)
    assert not view['blockers'] and 'old-refresh' not in str(view) and 'gAAAA' not in str(view)
    result=await service.migrate('w',kind,sender,'operator',view['digest'],workers_drained=True)
    assert result['current_matches']
    if kind=='mailbox':
        row=provider_db.outreach_mailboxes.docs[0]
        assert row['status']=='reauth_required' and row['history_id']=='cursor' and row['connection_job_id']=='job'
        assert (await prepare_mailbox_access(row,'w','a')).value=='old-access'
    else: assert (await prepare_finder_key(provider_db.outreach_hunter_credentials.docs[0],'w')).value=='private-hunter-key'
    assert provider_db.outreach_accounts.docs==before and provider_db.outreach_sender_execution.docs[0]['permission']['latched']
    receipt=provider_db.outreach_credential_migrations.docs[0]
    assert 'gAAAA' not in str(receipt) and 'uc1:' not in str(receipt) and 'old-access' not in str(receipt)
    monkeypatch.setattr('outreach.core.provider_credential_migration.seal_mailbox_tokens',AsyncMock(side_effect=AssertionError('No reseal')))
    monkeypatch.setattr('outreach.core.provider_credential_migration.seal_finder_key',AsyncMock(side_effect=AssertionError('No reseal')))
    assert (await service.migrate('w',kind,sender,'operator',view['digest'],workers_drained=True))['current_matches']

@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['mailbox','finder'])
@pytest.mark.parametrize('reason', ['active','permission','physical','oauth','state','refresh','sync','capacity','missing','plaintext','mode','drain','live','stale'])
async def test_unsafe_conversion_denies_before_sealing(provider_db,monkeypatch,kind,reason):
    service=ProviderCredentialMigration(provider_db);sender='a' if kind=='mailbox' else None
    view=await service.inspect('w',kind,sender)
    if reason=='active': provider_db.outreach_accounts.docs[0]['status']='active'
    if reason=='permission': provider_db.outreach_sender_execution.docs[0]['permission']['latched']=False
    if reason=='physical': provider_db.outreach_physical_requests.docs.append({'workspace_id':'w','sender_id':'a','status':'unknown_outcome'})
    if reason=='oauth': provider_db.outreach_mailbox_connection_jobs.docs.append({'workspace_id':'w','sender_account_id':'a','status':'running'})
    if reason=='state': provider_db.outreach_mailbox_oauth_states.docs.append({'workspace_id':'w','sender_account_id':'a'})
    if reason=='refresh': provider_db.outreach_mailboxes.docs[0]['refresh_state']='unknown'
    if reason=='sync': provider_db.outreach_mailboxes.docs[0]['sync_lease_nonce']='held'
    if reason=='capacity': provider_db.outreach_accounts.docs.extend([{'workspace_id':'w','id':str(i),'status':'paused'} for i in range(6)])
    if reason=='missing':
        if kind=='mailbox': provider_db.outreach_mailboxes.docs.clear()
        else: provider_db.outreach_hunter_credentials.docs.clear()
    if reason=='plaintext':
        if kind=='mailbox': provider_db.outreach_mailboxes.docs[0]['refresh_token_enc']='unscoped'
        else: provider_db.outreach_hunter_credentials.docs[0]['api_key_enc']='unscoped'
    if reason=='mode': monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    if reason=='live': monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED','true')
    if reason=='stale': provider_db.outreach_accounts.docs[0]['operator_revision']='new'
    seal=AsyncMock(side_effect=AssertionError('No key calls'))
    monkeypatch.setattr('outreach.core.provider_credential_migration.seal_mailbox_tokens',seal)
    monkeypatch.setattr('outreach.core.provider_credential_migration.seal_finder_key',seal)
    with pytest.raises(CustodyUnavailable): await service.migrate('w',kind,sender,'operator',view['digest'],workers_drained=reason!='drain')
    seal.assert_not_awaited()

@pytest.mark.asyncio
async def test_private_cli_outputs_metadata_and_requires_exact_drain_literal(provider_db,capsys):
    import json
    from argparse import Namespace
    from outreach.ops.pilot import _run_db
    await _run_db(Namespace(command='inspect-provider-custody',workspace='w',kind='finder',sender=None),provider_db)
    output=capsys.readouterr().out;view=json.loads(output)
    assert 'gAAAA' not in output and 'private-hunter' not in output
    args=Namespace(command='migrate-provider-custody',workspace='w',kind='finder',sender=None,operator='operator',review_digest=view['digest'],workers_drained='generic-drain')
    with pytest.raises(CustodyUnavailable):await _run_db(args,provider_db)
    args.workers_drained='I_PAUSED_AND_DRAINED_ALL_CREDENTIAL_WRITERS'
    await _run_db(args,provider_db);assert json.loads(capsys.readouterr().out)['current_matches']
