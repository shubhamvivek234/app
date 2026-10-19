"""Authorized plaintext reads against owned replica/standalone databases."""
import asyncio
import os

from bson import BSON, Code, ObjectId
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
import httpx
import pytest

from api.deps import get_current_user
from db.mongo import get_db
from outreach.api.sequences import router
from outreach.core import template_snapshot_reads as reads, template_history as history
from outreach.core import template_graph_snapshots as graphs, template_metadata_snapshots as metadata
from outreach.core import template_history_storage as storage
from outreach.core import template_mutation_snapshots as captures
from outreach.core.suppression import SuppressionUnavailable, mutate_suppression
from utils import encryption
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
from tests.test_outreach_template_governance_mongo import seed_authority, remove
from tests.test_outreach_template_saves_mongo import post
from tests.test_outreach_template_metadata_mongo import edit

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo opt-in')]
ACTOR = {'user_id': 'actor', 'firebase_uid': 'original-uid', 'default_workspace_id': 'workspace'}
DOMAINS = ('outreach_templates', 'outreach_template_revisions', metadata.COLLECTION, graphs.COLLECTION,
    'outreach_template_saves', 'outreach_template_metadata_updates', 'outreach_template_graph_updates',
    'outreach_template_deletions', 'outreach_execution_permissions')


@pytest.fixture(autouse=True)
def owned_settings(monkeypatch):
    monkeypatch.setattr(encryption, '_fernet', Fernet(Fernet.generate_key()))
    monkeypatch.delenv(reads.SETTING, raising=False)
    monkeypatch.delenv(captures.SETTING, raising=False)


async def setup(db, monkeypatch):
    await seed_authority(db)
    await storage.ensure_history_index(db)
    await metadata.prepare_storage(db)
    await graphs.prepare_storage(db)
    monkeypatch.setenv(captures.SETTING, 'true')
    assert (await post(db)).status_code == 200
    monkeypatch.setenv(reads.SETTING, 'true')
    return await db.outreach_templates.find_one({})


async def reference(db, revision=1):
    rows = await db.outreach_template_revisions.find({}).to_list(100)
    first = next(row for row in rows if row['event'] != 'deleted' and row['revision'] == revision)
    _, digest = history.prepare_history(rows, 'workspace', first['template_id'], first['identity_digest'])
    return {'template_id': first['template_id'], 'checkpoint_id': first['_id'],
        'identity_digest': first['identity_digest'], 'history_digest': digest}


async def get(db, proof, actor=None, extra=None):
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: dict(actor or ACTOR)
    app.dependency_overrides[get_db] = lambda: db
    path = '/sequences/templates/'+proof['template_id']+'/revision-checkpoints/'+proof['checkpoint_id']+'/content'
    params = {'identity_digest': proof['identity_digest'], 'history_digest': proof['history_digest'], **(extra or {})}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        return await client.get(path, params=params)


async def state(db, authority=False):
    names = DOMAINS + (('users', 'workspace_members') if authority else ())
    return {name: [BSON.encode(row) for row in await db[name].find({}).sort('_id', 1).to_list(100)] for name in names}


@pytest.mark.parametrize('role', ['owner', 'admin', 'editor', 'viewer', 'client'])
async def test_current_workspace_reader_gets_exact_pair_without_domain_or_storage_mutation(replica_db, monkeypatch, role):
    source = await setup(replica_db, monkeypatch)
    await replica_db.workspace_members.update_one({}, {'$set': {'role': role}})
    proof = await reference(replica_db); before = await state(replica_db, authority=True)
    result = await get(replica_db, proof)
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload['metadata'] == {key: source[key] for key in ('name', 'description')}
    assert payload['graph'] == {key: source[key] for key in ('nodes', 'edges', 'tree')}
    assert payload['capture_complete'] is payload['restore_available'] is payload['execution_authorized'] is False
    assert result.headers['cache-control'] == 'no-store, private' and result.headers['x-content-type-options'] == 'nosniff'
    assert 'ciphertext' not in payload and 'firebase_uid' not in result.text
    after = await state(replica_db, authority=True)
    for name in DOMAINS: assert after[name] == before[name]
    for name in ('users', 'workspace_members'):
        previous = BSON(before[name][0]).decode(); current = BSON(after[name][0]).decode()
        assert current.pop('template_authority_revision') == previous.pop('template_authority_revision') + 1
        assert current == previous


async def test_default_off_does_not_read_storage_or_decrypt(replica_db, monkeypatch):
    await setup(replica_db, monkeypatch); proof = await reference(replica_db)
    monkeypatch.delenv(reads.SETTING)
    def forbidden(*args): raise AssertionError('No content access while disabled')
    monkeypatch.setattr(metadata, 'open_snapshot', forbidden)
    before = await state(replica_db, authority=True)
    result = await get(replica_db, proof)
    assert result.status_code == 503 and 'metadata' not in result.json()
    assert await state(replica_db, authority=True) == before


@pytest.mark.parametrize('fault', ['uid', 'duplicate_uid', 'inactive', 'role', 'code_role', 'erased', 'closed'])
async def test_current_authority_denies_before_plaintext(replica_db, monkeypatch, fault):
    from outreach.core.erasure import stop_identity, OutreachErasure
    await setup(replica_db, monkeypatch); proof = await reference(replica_db)
    if fault == 'uid': await replica_db.users.update_one({}, {'$set': {'firebase_uid': 'different'}})
    elif fault == 'duplicate_uid': await replica_db.users.insert_one({'user_id': 'other', 'firebase_uid': 'original-uid'})
    elif fault == 'inactive': await replica_db.workspace_members.update_one({}, {'$set': {'status': 'inactive'}})
    elif fault == 'role': await replica_db.workspace_members.update_one({}, {'$set': {'role': 'unknown'}})
    elif fault == 'code_role': await replica_db.workspace_members.update_one({}, {'$set': {'role': Code('admin')}})
    elif fault == 'erased': await stop_identity(replica_db, 'original-uid')
    else:
        await replica_db.workspaces.insert_one({'workspace_id': 'workspace', 'owner_id': 'actor'})
        await OutreachErasure(replica_db).request('workspace', 'actor')
    def forbidden(*args): raise AssertionError('Unauthorized read reached decryption')
    monkeypatch.setattr(metadata, 'open_snapshot', forbidden)
    before = await state(replica_db, authority=True)
    result = await get(replica_db, proof)
    assert result.status_code in {403, 409, 503} and 'metadata' not in result.json()
    assert result.headers['cache-control'] == 'no-store, private'
    assert await state(replica_db, authority=True) == before


@pytest.mark.parametrize('missing', ['both', 'metadata', 'graph'])
async def test_missing_pair_never_falls_back_to_plain_source_or_half_content(replica_db, monkeypatch, missing):
    await setup(replica_db, monkeypatch); proof = await reference(replica_db)
    for codec in (metadata, graphs):
        if missing == 'both' or (missing == 'metadata') == (codec is metadata):
            await replica_db[codec.COLLECTION].delete_many({})
    before = await state(replica_db, authority=True)
    result = await get(replica_db, proof)
    assert result.status_code == (404 if missing == 'both' else 409)
    assert not {'metadata', 'graph'} & result.json().keys()
    assert await state(replica_db, authority=True) == before


async def test_deleted_and_replaced_original_uses_explicit_native_history(replica_db, monkeypatch):
    source = await setup(replica_db, monkeypatch)
    await remove(replica_db, source)
    proof = await reference(replica_db)
    await replica_db.outreach_templates.insert_one({**source, '_id': ObjectId(), 'name': 'Replacement'})
    result = await get(replica_db, proof)
    assert result.status_code == 200 and result.json()['metadata']['name'] == source['name']
    assert result.json()['terminal_recorded'] is True
    assert (await replica_db.outreach_templates.find_one({}))['name'] == 'Replacement'
    terminal = await replica_db.outreach_template_revisions.find_one({'event': 'deleted'})
    rejected = await get(replica_db, {**proof, 'checkpoint_id': terminal['_id']})
    assert rejected.status_code == 409 and 'metadata' not in rejected.json()


async def test_history_append_holds_stale_reference_then_explicit_refresh_reads_old_revision(replica_db, monkeypatch):
    source = await setup(replica_db, monkeypatch); original = await reference(replica_db)
    await edit(replica_db, source, name='Later')
    stale = await get(replica_db, original)
    assert stale.status_code == 409 and 'metadata' not in stale.json()
    fresh = await get(replica_db, await reference(replica_db))
    assert fresh.status_code == 200 and fresh.json()['metadata']['name'] == source['name']


@pytest.mark.parametrize('extra', [{'unknown': 'x'}, {'revision': '1'}, {'workspace_id': 'other'},
    {'kind': 'graph'}, {'identity_digest': 'bad'}, {'history_digest': 'A'*64}])
async def test_strict_query_contract(replica_db, monkeypatch, extra):
    await setup(replica_db, monkeypatch); result = await get(replica_db, await reference(replica_db), extra=extra)
    assert result.status_code == 422 and 'metadata' not in result.json()


@pytest.mark.parametrize('codec', [metadata, graphs], ids=['metadata', 'graph'])
@pytest.mark.parametrize('fault', ['corrupt', 'duplicate', 'revision_alias', 'oversized_id', 'wrong_key', 'missing_key', 'response_limit'])
async def test_selected_pair_validation_and_crypto_failures_return_no_plaintext(replica_db, monkeypatch, fault, codec):
    await setup(replica_db, monkeypatch); proof = await reference(replica_db)
    saved = await replica_db[codec.COLLECTION].find_one({})
    if fault == 'corrupt': await replica_db[codec.COLLECTION].update_one({}, {'$set': {'ciphertext': 'private-secret'}})
    elif fault == 'duplicate': await replica_db[codec.COLLECTION].insert_one({**saved, '_id': 'different'})
    elif fault == 'revision_alias': await replica_db[codec.COLLECTION].update_one({}, {'$set': {'revision': 1.0}})
    elif fault == 'oversized_id':
        await replica_db[codec.COLLECTION].delete_many({})
        await replica_db[codec.COLLECTION].insert_one({**saved, '_id': 'z'*(codec.MAX_ROW_BYTES + 1)})
    elif fault == 'wrong_key': monkeypatch.setattr(encryption, '_fernet', Fernet(Fernet.generate_key()))
    elif fault == 'missing_key':
        monkeypatch.setattr(encryption, '_fernet', None); monkeypatch.delenv('ENCRYPTION_KEY', raising=False)
    else: monkeypatch.setattr(reads, 'MAX_RESPONSE_BYTES', 1)
    before = await state(replica_db, authority=True)
    result = await get(replica_db, proof)
    assert result.status_code in {409, 503} and not {'metadata', 'graph'} & result.json().keys()
    assert 'private-secret' not in result.text and await state(replica_db, authority=True) == before


@pytest.mark.parametrize('collection', ['outreach_template_revisions', metadata.COLLECTION, graphs.COLLECTION])
@pytest.mark.parametrize('fault', ['missing', 'ttl', 'conflicting'])
async def test_storage_prerequisites_never_install_or_repair_indexes(replica_db, monkeypatch, collection, fault):
    await setup(replica_db, monkeypatch); proof = await reference(replica_db)
    if fault == 'ttl': await replica_db[collection].create_index('future_expiry', expireAfterSeconds=3600)
    else:
        await replica_db[collection].drop_index(storage.INDEX_NAME)
        if fault == 'conflicting': await replica_db[collection].create_index('revision', name=storage.INDEX_NAME)
    before = await state(replica_db, authority=True); indexes = await replica_db[collection].index_information()
    result = await get(replica_db, proof)
    assert result.status_code == 503 and 'metadata' not in result.json()
    assert await state(replica_db, authority=True) == before
    assert await replica_db[collection].index_information() == indexes


async def test_unknown_commit_returns_no_plaintext_and_retry_rechecks_authority(replica_db, monkeypatch):
    await setup(replica_db, monkeypatch); proof = await reference(replica_db)
    commit = reads.mutate_suppression
    async def lost(*args, **kwargs):
        await commit(*args, **kwargs)
        raise SuppressionUnavailable('Synthetic unknown read acknowledgement')
    monkeypatch.setattr(reads, 'mutate_suppression', lost)
    result = await get(replica_db, proof)
    assert result.status_code == 503 and 'metadata' not in result.json()
    monkeypatch.setattr(reads, 'mutate_suppression', commit)
    await replica_db.workspace_members.update_one({}, {'$set': {'status': 'inactive'}})
    assert (await get(replica_db, proof)).status_code == 403


async def test_standalone_cannot_release_snapshot_content(real_db, monkeypatch):
    monkeypatch.setenv(reads.SETTING, 'true')
    with pytest.raises(HTTPException) as caught:
        await reads.read_content(real_db, 'workspace', 'actor', 'uid', 'tpl_custom_012345abcd',
            'a'*64, 'b'*64, 'c'*64)
    assert caught.value.status_code == 503


async def test_real_nested_wrapper_rejected_without_decryption_or_authority_change(replica_db, monkeypatch):
    await setup(replica_db, monkeypatch); proof = await reference(replica_db)
    before = await state(replica_db, authority=True); decrypted = []
    def forbidden(*args):
        decrypted.append(True)
        raise AssertionError('Nested read reached decryption')
    monkeypatch.setattr(metadata, 'open_snapshot', forbidden)
    async def nested(current):
        with pytest.raises(HTTPException) as caught:
            await reads.read_content(current, 'workspace', 'actor', 'original-uid', **{
                'template_id': proof['template_id'], 'identity': proof['identity_digest'],
                'checkpoint_id': proof['checkpoint_id'], 'history_digest': proof['history_digest']})
        assert caught.value.status_code == 503
    await mutate_suppression(replica_db, 'workspace', nested)
    assert decrypted == [] and await state(replica_db, authority=True) == before


@pytest.mark.parametrize('value', [None, 'false', 'invalid'])
async def test_read_gate_is_independent_from_capture_setting(replica_db, monkeypatch, value):
    await setup(replica_db, monkeypatch)
    monkeypatch.delenv(captures.SETTING)
    if value is not None: monkeypatch.setenv(captures.SETTING, value)
    assert (await get(replica_db, await reference(replica_db))).status_code == 200


@pytest.mark.parametrize('fault', ['checkpoint', 'identity', 'foreign_workspace', 'lineage'])
async def test_bad_reference_or_full_lineage_never_discloses_selected_pair(replica_db, monkeypatch, fault):
    source = await setup(replica_db, monkeypatch); proof = await reference(replica_db); actor = None
    if fault == 'checkpoint': proof['checkpoint_id'] = 'a'*64
    elif fault == 'identity': proof['identity_digest'] = 'a'*64
    elif fault == 'foreign_workspace':
        actor = {**ACTOR, 'default_workspace_id': 'other'}
        await replica_db.workspace_members.insert_one({'workspace_id': 'other', 'user_id': 'actor', 'role': 'admin'})
    else:
        await edit(replica_db, source)
        proof = await reference(replica_db)
        await replica_db.outreach_template_revisions.update_one({'event': 'metadata'},
            {'$set': {'predecessor_review_digest': 'a'*64}})
    before = await state(replica_db, authority=True)
    result = await get(replica_db, proof, actor=actor)
    assert result.status_code in {404, 409} and not {'metadata', 'graph'} & result.json().keys()
    assert await state(replica_db, authority=True) == before


async def test_corrupt_unselected_snapshot_does_not_scan_other_encrypted_revisions(replica_db, monkeypatch):
    source = await setup(replica_db, monkeypatch)
    await edit(replica_db, source, name='Later')
    await replica_db[metadata.COLLECTION].update_one({'revision': 1}, {'$set': {'ciphertext': 'private-secret'}})
    latest = await get(replica_db, await reference(replica_db, 2))
    assert latest.status_code == 200 and latest.json()['metadata']['name'] == 'Later'
    earlier = await get(replica_db, await reference(replica_db, 1))
    assert earlier.status_code == 409 and 'private-secret' not in earlier.text


@pytest.mark.parametrize('fault', ['index', 'flag', 'storage'])
async def test_final_observation_failure_rolls_back_authority_and_returns_no_content(replica_db, monkeypatch, fault):
    await setup(replica_db, monkeypatch); proof = await reference(replica_db)
    before = await state(replica_db, authority=True)
    if fault == 'index':
        inspect = reads._indexes; calls = []
        async def drift(current):
            result = await inspect(current); calls.append(True)
            return result if len(calls) == 1 else []
        monkeypatch.setattr(reads, '_indexes', drift)
    elif fault == 'flag':
        render = reads.content_payload
        def disable(*args):
            result = render(*args); monkeypatch.setenv(reads.SETTING, 'false'); return result
        monkeypatch.setattr(reads, 'content_payload', disable)
    else:
        async def unavailable(*args): raise RuntimeError('private-secret')
        monkeypatch.setattr(reads, '_point', unavailable)
    result = await get(replica_db, proof)
    assert result.status_code in {409, 503} and not {'metadata', 'graph'} & result.json().keys()
    assert 'private-secret' not in result.text and await state(replica_db, authority=True) == before


async def test_disabled_after_commit_releases_no_content_but_does_not_claim_counter_rollback(replica_db, monkeypatch):
    await setup(replica_db, monkeypatch); proof = await reference(replica_db)
    before = await replica_db.users.find_one({}); commit = reads.mutate_suppression
    async def disable(*args):
        result = await commit(*args); monkeypatch.setenv(reads.SETTING, 'false'); return result
    monkeypatch.setattr(reads, 'mutate_suppression', disable)
    result = await get(replica_db, proof)
    assert result.status_code == 503 and 'metadata' not in result.json()
    assert (await replica_db.users.find_one({}))['template_authority_revision'] == before['template_authority_revision'] + 1


@pytest.mark.parametrize('fault', ['role', 'uid'])
async def test_authority_change_after_snapshot_starts_forces_retry_and_denial(replica_db, monkeypatch, fault):
    await setup(replica_db, monkeypatch); proof = await reference(replica_db)
    entered, release = asyncio.Event(), asyncio.Event(); authorize = reads.governance.authorize_read
    async def pause(*args):
        if not entered.is_set():
            entered.set(); await release.wait()
        return await authorize(*args)
    monkeypatch.setattr(reads.governance, 'authorize_read', pause)
    reading = asyncio.create_task(get(replica_db, proof))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        if fault == 'role': await replica_db.workspace_members.update_one({}, {'$set': {'status': 'inactive'}})
        else: await replica_db.users.update_one({}, {'$set': {'firebase_uid': 'replacement'}})
        before = await state(replica_db, authority=True)
    finally:
        release.set(); result = await reading
    assert result.status_code == 403 and 'metadata' not in result.json()
    assert await state(replica_db, authority=True) == before


async def test_read_orders_before_guarded_erasure_then_future_reads_deny_and_finish_purges(replica_db, monkeypatch):
    from outreach.core.erasure import OutreachErasure
    source = await setup(replica_db, monkeypatch)
    await remove(replica_db, source); proof = await reference(replica_db)
    await replica_db.workspaces.insert_one({'workspace_id': 'workspace', 'owner_id': 'actor'})
    entered, release = asyncio.Event(), asyncio.Event(); point = reads._point
    async def pause(*args):
        result = await point(*args)
        if not entered.is_set(): entered.set(); await release.wait()
        return result
    monkeypatch.setattr(reads, '_point', pause)
    service = OutreachErasure(replica_db)
    reading = asyncio.create_task(get(replica_db, proof)); erasing = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        erasing = asyncio.create_task(service.request('workspace', 'actor'))
        await asyncio.sleep(0.05)
        assert not erasing.done()
    finally:
        release.set()
        results = await asyncio.gather(reading, *([erasing] if erasing else []), return_exceptions=True)
    assert len(results) == 2 and results[0].status_code == 200 and results[1]['status'] == 'awaiting_drain'
    assert (await get(replica_db, proof)).status_code == 503
    review = await service.inspect('workspace')
    await service.finish('workspace', 'operator', 'Owned drained fixture', workers_drained=True,
        expected_digest=review['review_digest'])
    for codec in (metadata, graphs): assert await replica_db[codec.COLLECTION].count_documents({}) == 0
    assert (await get(replica_db, proof)).status_code == 503
