"""Scope-bound mailbox/finder material and database-only prepared comparisons."""
from dataclasses import replace
from unittest.mock import AsyncMock
import pytest
from outreach.core import provider_custody as custody
from outreach.core.credential_custody import CustodyUnavailable
from tests.test_outreach_session_custody import scoped


def mailbox(**changes):
    return {'workspace_id': 'w', 'sender_account_id': 'a', 'provider': 'gmail', 'provider_user_id': 'provider-user',
        'email': 'sender@example.com', 'connection_job_id': 'job', **changes}

@pytest.mark.asyncio
async def test_mailbox_seal_prepare_and_exact_pure_comparison(scoped, monkeypatch):
    row = mailbox(); row.update(await custody.seal_mailbox_tokens({'access_token': 'private-access', 'refresh_token': 'private-refresh'}, row, 'w', 'a'))
    prepared = await custody.prepare_mailbox_access(row, 'w', 'a')
    assert prepared.value == 'private-access' and 'private-access' not in repr(prepared)
    assert await custody.open_mailbox_refresh(row, 'w', 'a') == 'private-refresh'
    monkeypatch.setattr(scoped, 'open', AsyncMock(side_effect=AssertionError('No KMS inside comparisons')))
    assert prepared.matches(row, 'w', 'a')
    assert not prepared.matches({**row, 'access_token_enc': 'replacement'}, 'w', 'a')
    assert not prepared.matches({**row, 'refresh_state': 'possible'}, 'w', 'a')
    assert not replace(prepared, value='tampered').matches(row, 'w', 'a')

@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('workspace_id','other'), ('sender_account_id','other'), ('provider','microsoft'),
    ('email','other@example.com'), ('provider_user_id','other'), ('connection_job_id','other'), ('custody_generation','other')])
async def test_mailbox_context_swap_denies(scoped, field, value):
    row = mailbox(); row.update(await custody.seal_mailbox_tokens({'access_token': 'access', 'refresh_token': 'refresh'}, row, 'w', 'a'))
    with pytest.raises(CustodyUnavailable): await custody.prepare_mailbox_access({**row,field:value}, 'w', 'a')

@pytest.mark.asyncio
async def test_access_refresh_purposes_and_legacy_downgrade_deny(scoped, monkeypatch):
    row = mailbox(); row.update(await custody.seal_mailbox_tokens({'access_token':'access','refresh_token':'refresh'},row,'w','a'))
    with pytest.raises(CustodyUnavailable): await custody.open_mailbox_refresh({**row,'refresh_token_enc':row['access_token_enc']},'w','a')
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    with pytest.raises(CustodyUnavailable): await custody.prepare_mailbox_access(row,'w','a')

@pytest.mark.asyncio
async def test_finder_key_is_workspace_bound_and_exact_capture_across_await(scoped, monkeypatch):
    row = {'workspace_id':'w', **await custody.seal_finder_key('private-key','w')}; original = row.copy()
    opening=scoped.open
    async def mutate(*args):
        row['credential_generation']='replaced'
        return await opening(*args)
    monkeypatch.setattr(scoped,'open',mutate)
    prepared=await custody.prepare_finder_key(row,'w')
    assert prepared.value=='private-key' and 'private-key' not in repr(prepared)
    assert prepared.matches(original,'w') and not prepared.matches(row,'w')
    with pytest.raises(CustodyUnavailable): await custody.prepare_finder_key(original,'other')

@pytest.mark.asyncio
async def test_pending_oauth_code_and_pkce_bind_job_provider_sender_and_distinct_purposes(scoped):
    job={'workspace_id':'w','sender_account_id':'a','provider':'gmail','id':'pending-job'}
    code=await custody.seal_oauth_secret('private-code',job,'w','a','oauth_code')
    verifier=await custody.seal_oauth_secret('private-verifier',job,'w','a','oauth_pkce')
    assert await custody.open_oauth_secret(code,job,'w','a','oauth_code')=='private-code'
    assert await custody.open_oauth_secret(verifier,job,'w','a','oauth_pkce')=='private-verifier'
    for bad in ({**job,'id':'other'}, {**job,'provider':'microsoft'}, {**job,'sender_account_id':'other'}):
        with pytest.raises(CustodyUnavailable): await custody.open_oauth_secret(code,bad,'w','a','oauth_code')
    with pytest.raises(CustodyUnavailable): await custody.open_oauth_secret(verifier,job,'w','a','oauth_code')

@pytest.mark.asyncio
async def test_kms_mode_never_adopts_unscoped_legacy_credentials(scoped):
    from utils.encryption import encrypt
    with pytest.raises(CustodyUnavailable): await custody.prepare_mailbox_access(mailbox(access_token_enc=encrypt('legacy')), 'w','a')
    with pytest.raises(CustodyUnavailable): await custody.prepare_finder_key({'workspace_id':'w','api_key_enc':encrypt('legacy')},'w')
