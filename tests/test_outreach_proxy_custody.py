"""Proxy custody binds an imported asset; dispatch comparisons require no KMS."""
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from outreach.core.credential_custody import CustodyUnavailable
from outreach.core import proxy_custody
from tests.test_outreach_session_custody import scoped


def asset(**changes):
    return {"proxy_id": "iproyal:p", "provider": "iproyal_static", "host": "191.116.125.248",
        "port": 12323, "username": "local-user", "country_code": "IN", **changes}


@pytest.mark.asyncio
async def test_scoped_proxy_preparation_has_private_url_and_database_only_exact_comparison(scoped, monkeypatch):
    row = asset()
    row.update(await proxy_custody.seal_proxy_password('private-password', row, 'w'))
    prepared = await proxy_custody.prepare_proxy(row, 'w')
    assert prepared.url == 'http://local-user:private-password@191.116.125.248:12323'
    assert 'private-password' not in repr(prepared)
    monkeypatch.setattr(scoped, 'open', AsyncMock(side_effect=AssertionError('No KMS inside final checks')))
    assert prepared.matches(row, 'w')
    assert not prepared.matches(row, 'other-workspace')
    assert not prepared.matches({**row, 'password_enc': 'replacement'}, 'w')
    assert not prepared.matches({**row, 'credential_generation': 'replacement'}, 'w')
    assert not replace(prepared, url='http://different:8000').matches(row, 'w')


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('proxy_id', 'other'), ('host', '1.1.1.1'), ('port', 8080),
    ('username', 'other'), ('country_code', 'US'), ('provider', 'webshare_plan'),
    ('credential_generation', 'replacement'), ('custody_workspace_id', 'other')])
async def test_asset_identity_or_transport_swap_cannot_open_scoped_password(scoped, field, value):
    row = asset()
    row.update(await proxy_custody.seal_proxy_password('private-password', row, 'w'))
    with pytest.raises(CustodyUnavailable): await proxy_custody.prepare_proxy({**row, field: value}, 'w')


@pytest.mark.asyncio
async def test_proxy_password_cannot_cross_workspace_or_session_purpose(scoped):
    from outreach.core.session_custody import context
    row = asset()
    row.update(await proxy_custody.seal_proxy_password('private-password', row, 'w'))
    with pytest.raises(CustodyUnavailable): await proxy_custody.prepare_proxy(row, 'other')
    with pytest.raises(CustodyUnavailable):
        await scoped.open(row['password_enc'], context('w', 'iproyal:p', row['credential_generation'], 'session_li_at'))


@pytest.mark.asyncio
async def test_kms_proxy_mode_rejects_plaintext_fernet_missing_scope_and_legacy_mode_cannot_downgrade(scoped, monkeypatch):
    from outreach.core.crypto import encrypt_secret
    for password in ('plaintext', encrypt_secret('legacy-password'), ''):
        with pytest.raises(CustodyUnavailable): await proxy_custody.prepare_proxy(asset(password_enc=password), 'w')
    row = asset()
    row.update(await proxy_custody.seal_proxy_password('private-password', row, 'w'))
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    with pytest.raises(CustodyUnavailable): await proxy_custody.prepare_proxy(row, 'w')


@pytest.mark.asyncio
async def test_default_proxy_preparation_preserves_fernet_and_escapes_credentials(scoped, monkeypatch):
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    row = asset(username='user@local')
    row.update(await proxy_custody.seal_proxy_password('pass:/word', row, 'w'))
    prepared = await proxy_custody.prepare_proxy(row, 'w')
    assert prepared.url == 'http://user%40local:pass%3A%2Fword@191.116.125.248:12323'
    assert prepared.matches(row, 'w')


@pytest.mark.asyncio
async def test_proxy_config_retains_custody_metadata_and_inventory_normalizes_identically(scoped):
    from outreach.core.managed_proxy import _proxy_from_inventory
    row = asset()
    row.update(await proxy_custody.seal_proxy_password('private-password', row, 'w'))
    inventory = {**row, '_id': row['proxy_id'], 'workspace_id': 'w', 'last_workspace_id': 'w'}
    model = _proxy_from_inventory(inventory)
    assert model.credential_generation == row['credential_generation']
    assert model.custody_workspace_id == 'w'
    prepared = await proxy_custody.prepare_proxy(model, 'w')
    assert prepared.matches(inventory, 'w') and prepared.matches(model.model_dump(), 'w')


@pytest.mark.asyncio
async def test_final_proxy_match_requires_prepared_scope_exact_url_and_current_inventory(scoped, monkeypatch):
    from outreach.core.request_guard import RequestEnvelope
    from tests.outreach_memory import Database
    row = asset()
    row.update(await proxy_custody.seal_proxy_password('private-password', row, 'w'))
    prepared = await proxy_custody.prepare_proxy(row, 'w')
    guard = RequestEnvelope(Database(), 'w', 'a', 'g', 'sync', prepared.url, prepared_proxy=prepared)
    monkeypatch.setattr(scoped, 'open', AsyncMock(side_effect=AssertionError('No KMS in transaction')))
    assert guard._proxy_matches({'proxy': row})
    assert guard._proxy_config_matches({**row, '_id': row['proxy_id']})
    assert not guard._proxy_matches({'proxy': {**row, 'password_enc': 'replacement'}})
    guard.proxy_url = 'http://direct-host:8000'
    assert not guard._proxy_matches({'proxy': row})
    no_preparation = RequestEnvelope(Database(), 'w', 'a', 'g', 'sync', prepared.url)
    assert not no_preparation._proxy_matches({'proxy': row})


@pytest.mark.asyncio
async def test_inventory_alias_cannot_change_primary_asset_identity(scoped):
    row = asset()
    row.update(await proxy_custody.seal_proxy_password('private-password', row, 'w'))
    with pytest.raises(CustodyUnavailable):
        await proxy_custody.prepare_proxy({**row, '_id': 'replacement'}, 'w')

@pytest.mark.asyncio
async def test_preparation_captures_same_record_across_key_service_await(scoped, monkeypatch):
    row = asset()
    row.update(await proxy_custody.seal_proxy_password('secret', row, 'w'))
    original = row.copy()
    opening = scoped.open
    async def change(secret, context):
        row['host'] = '8.8.4.4'
        return await opening(secret, context)
    monkeypatch.setattr(scoped, 'open', change)
    prepared = await proxy_custody.prepare_proxy(row, 'w')
    assert prepared.matches(original, 'w')
    assert not prepared.matches(row, 'w')

@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('host', '127.0.0.1'), ('host', 'example.com'), ('port', True),
    ('port', 0), ('credential_generation', {'bad': 'object'}), ('username', ['bad']), ('provider', 'x' * 257)])
async def test_malformed_transport_and_private_assets_deny_before_key_service(scoped, monkeypatch, field, value):
    row = asset()
    row.update(await proxy_custody.seal_proxy_password('private', row, 'w'))
    row[field] = value
    opening = AsyncMock(side_effect=AssertionError('Must deny before key service'))
    monkeypatch.setattr(scoped, 'open', opening)
    with pytest.raises(CustodyUnavailable): await proxy_custody.prepare_proxy(row, 'w')
    opening.assert_not_awaited()

@pytest.mark.asyncio
async def test_warmup_session_check_uses_prepared_asset(scoped, monkeypatch):
    from tests.outreach_memory import Database
    from outreach.core.session_custody import seal_installed
    from celery_workers.tasks import outreach as worker
    row = asset(); row.update(await proxy_custody.seal_proxy_password('private', row, 'w'))
    account = {'workspace_id': 'w', 'id': 'a', 'status': 'active', 'credential_generation': 'g', 'linkedin_urn': 'urn:a', 'proxy': row}
    account.update(await seal_installed({'li_at': 'local-cookie', 'jsession_id': 'ajax:csrf'}, 'w', 'a', 'g'))
    validate = AsyncMock(return_value={'linkedin_urn': 'urn:a'})
    monkeypatch.setattr(worker.SessionAuthenticator, 'validate_session_cookie', validate)
    await worker._verify_auto_launch_senders({'workspace_id': 'w', 'sender_account_ids': ['a']}, Database(outreach_accounts=[account]))
    envelope = validate.await_args.kwargs['request_envelope']
    assert envelope.prepared_proxy.matches(row, 'w') and envelope.proxy_url == validate.await_args.kwargs['proxy_url']

@pytest.mark.asyncio
async def test_scoped_managed_import_and_reservation_require_workspace_compatible_inventory(scoped):
    from datetime import datetime, timedelta, timezone
    from outreach.core.managed_proxy import import_iproyal_proxy, reserve_sender_proxy, ManagedProxyUnavailable
    from tests.outreach_memory import Database
    db = Database()
    result = await import_iproyal_proxy(db, 'http://local-user:private@191.116.125.248:12323', 'IN', 'local-order', 'w', datetime.now(timezone.utc) + timedelta(days=1))
    saved = db.outreach_proxy_inventory.docs[0]
    assert saved['password_enc'].startswith('uc1:') and 'private' not in str(result)
    reserved = await reserve_sender_proxy(db, 'w', 'a', 'IN')
    assert (await proxy_custody.prepare_proxy(reserved, 'w')).matches(saved, 'w')
    saved['last_workspace_id'] = 'other'
    with pytest.raises(ManagedProxyUnavailable): await reserve_sender_proxy(db, 'w', 'a', 'IN')
