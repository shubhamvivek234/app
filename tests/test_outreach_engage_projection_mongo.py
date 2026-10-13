"""Production worker late-result tests: owned Mongo and suspended fake provider."""
import asyncio
import os
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pymongo.errors import OperationFailure

from celery_workers.tasks import engage as worker
from outreach.api import engage
from outreach.core import engage_projection as projection
from outreach.core.suppression import SuppressionCollection, SuppressionUnavailable
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]
USER = {'user_id': 'actor', 'default_workspace_id': 'workspace'}


async def seed(db, monkeypatch, verified=True):
    await db.outreach_engage_lists.insert_one({'id': 'list', 'workspace_id': 'workspace',
        'fetch_status': 'queued', 'fetch_run_id': 'run', 'enrichment_status': 'queued', 'enrichment_run_id': 'enrich'})
    await db.outreach_engage_contacts.insert_one({'id': 'contact', 'list_id': 'list', 'workspace_id': 'workspace',
        'profile_url': 'https://linkedin.com/in/person', 'vanity_name': 'person',
        'profile_urn': 'urn:li:fsd_profile:person' if verified else '',
        'full_name': 'Person', 'enrichment_status': 'verified' if verified else 'pending'})
    await db.outreach_accounts.insert_one({'id': 'sender', 'workspace_id': 'workspace', 'status': 'active'})
    monkeypatch.setattr(worker, '_db', AsyncMock(return_value=db))
    monkeypatch.setattr(worker, 'sender_is_ready', AsyncMock(return_value=True))
    monkeypatch.setattr(worker, 'is_shutting_down', lambda: False)


@pytest.mark.parametrize('change', ['list_delete', 'contact_delete', 'list_replace', 'contact_replace', 'identity_change', 'new_run'])
async def test_late_posts_cannot_recreate_or_modify_deleted_replacement_records(replica_db, monkeypatch, change):
    await seed(replica_db, monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()
    async def read(*args, **kwargs):
        entered.set(); await release.wait()
        return [{'post_urn': 'urn:li:activity:post', 'content_text': 'Late result'}]
    voyager = AsyncMock(); voyager.fetch_profile_recent_updates.side_effect = read
    monkeypatch.setattr(worker, '_build_voyager', AsyncMock(return_value=voyager))
    task = asyncio.create_task(worker._fetch_posts('list', 'workspace', 'sender', 'run'))
    await asyncio.wait_for(entered.wait(), 5)
    if change == 'list_delete': await engage.delete_engage_list('list', current_user=USER, db=replica_db)
    elif change == 'contact_delete': await engage.delete_engage_contact('list', 'contact', current_user=USER, db=replica_db)
    elif change in {'list_replace', 'contact_replace'}:
        collection = replica_db.outreach_engage_lists if change == 'list_replace' else replica_db.outreach_engage_contacts
        row = await collection.find_one({}); await collection.delete_one({'_id': row.pop('_id')})
        await collection.insert_one(row)
    elif change == 'identity_change': await replica_db.outreach_engage_contacts.update_one({}, {'$set': {'profile_urn': 'replacement'}})
    else: await replica_db.outreach_engage_lists.update_one({}, {'$set': {'fetch_run_id': 'new', 'fetch_status': 'queued'}})
    release.set()
    assert (await task)['status'] == 'stopped'
    assert await replica_db.outreach_engage_posts.count_documents({}) == 0
    assert await replica_db.outreach_engage_drafts.count_documents({}) == 0
    if change == 'new_run': assert (await replica_db.outreach_engage_lists.find_one({}))['fetch_status'] == 'queued'


async def test_late_enrichment_does_not_continue_to_posts_after_contact_deletion(replica_db, monkeypatch):
    await seed(replica_db, monkeypatch, verified=False)
    entered, release = asyncio.Event(), asyncio.Event()
    async def read(*args, **kwargs):
        entered.set(); await release.wait()
        return {'verified': True, 'profile_urn': 'urn:li:fsd_profile:person', 'full_name': 'Person'}
    voyager = AsyncMock(); voyager.fetch_profile_info.side_effect = read
    monkeypatch.setattr(worker, '_build_voyager', AsyncMock(return_value=voyager))
    task = asyncio.create_task(worker._fetch_posts('list', 'workspace', 'sender', 'run'))
    await asyncio.wait_for(entered.wait(), 5)
    await engage.delete_engage_contact('list', 'contact', current_user=USER, db=replica_db)
    release.set()
    assert (await task)['status'] == 'stopped'
    voyager.fetch_profile_recent_updates.assert_not_awaited()
    assert await replica_db.outreach_engage_contacts.count_documents({}) == 0


async def test_live_projection_and_counter_are_atomic(replica_db, monkeypatch):
    await seed(replica_db, monkeypatch)
    voyager = AsyncMock(); voyager.fetch_profile_recent_updates.return_value = [{'post_urn': 'urn:li:activity:post'}]
    monkeypatch.setattr(worker, '_build_voyager', AsyncMock(return_value=voyager))
    assert (await worker._fetch_posts('list', 'workspace', 'sender', 'run'))['fetched'] == 1
    parent = await replica_db.outreach_engage_lists.find_one({})
    assert parent['pending_posts_count'] == 1 and parent['fetch_status'] == 'complete'
    assert (await worker._fetch_posts('list', 'workspace', 'sender', 'run'))['status'] == 'stopped'
    assert voyager.fetch_profile_recent_updates.await_count == 1


async def test_projection_failure_rolls_back_post_and_contact_timestamp(replica_db, monkeypatch):
    await seed(replica_db, monkeypatch)
    voyager = AsyncMock(); voyager.fetch_profile_recent_updates.return_value = [{'post_urn': 'urn:li:activity:post'}]
    monkeypatch.setattr(worker, '_build_voyager', AsyncMock(return_value=voyager))
    original = SuppressionCollection.update_one
    async def fail(self, query, update, **kwargs):
        if self.collection.name == 'outreach_engage_contacts' and 'last_fetched_at' in update.get('$set', {}):
            raise OperationFailure('injected')
        return await original(self, query, update, **kwargs)
    monkeypatch.setattr(SuppressionCollection, 'update_one', fail)
    assert (await worker._fetch_posts('list', 'workspace', 'sender', 'run'))['status'] == 'failed'
    assert await replica_db.outreach_engage_posts.count_documents({}) == 0
    assert 'last_fetched_at' not in await replica_db.outreach_engage_contacts.find_one({})


async def test_error_and_final_status_preserve_new_run_and_other_kind(replica_db, monkeypatch):
    await seed(replica_db, monkeypatch)
    binding = await projection.start_run(replica_db, 'workspace', 'list', 'fetch', 'run')
    await replica_db.outreach_engage_lists.update_one({}, {'$set': {'fetch_run_id': 'new', 'fetch_status': 'queued'}})
    assert not await worker._mark_job_failed(replica_db, binding, 'late failure')
    assert not await projection.finish_run(replica_db, binding, {'fetch_status': 'complete'})
    parent = await replica_db.outreach_engage_lists.find_one({})
    assert parent['fetch_status'] == 'queued' and parent['enrichment_status'] == 'queued'
    await replica_db.outreach_engage_lists.update_one({}, {'$set': {'fetch_error': 'Preserve fetch diagnostic'}})
    enrichment = await projection.start_run(replica_db, 'workspace', 'list', 'enrichment', 'enrich')
    assert await worker._mark_job_failed(replica_db, enrichment, 'Enrichment diagnostic')
    parent = await replica_db.outreach_engage_lists.find_one({})
    assert parent['fetch_error'] == 'Preserve fetch diagnostic' and parent['enrichment_error'] == 'Enrichment diagnostic'


@pytest.mark.parametrize('failure_point', ['preparation', 'contact_scan'])
async def test_post_claim_failures_finalize_only_the_captured_run(replica_db, monkeypatch, failure_point):
    await seed(replica_db, monkeypatch)
    monkeypatch.setattr(worker, '_build_voyager', AsyncMock(return_value=AsyncMock()))
    if failure_point == 'preparation':
        monkeypatch.setattr(worker, 'sender_is_ready', AsyncMock(side_effect=OperationFailure('injected readiness failure')))
    else:
        from motor.motor_asyncio import AsyncIOMotorCollection
        original = AsyncIOMotorCollection.find
        def fail(collection, *args, **kwargs):
            if collection.name == 'outreach_engage_contacts': raise OperationFailure('injected contact scan failure')
            return original(collection, *args, **kwargs)
        monkeypatch.setattr(AsyncIOMotorCollection, 'find', fail)
    with pytest.raises(OperationFailure): await worker._fetch_posts('list', 'workspace', 'sender', 'run')
    assert (await replica_db.outreach_engage_lists.find_one({}))['fetch_status'] == 'failed'


async def test_legacy_unpinned_messages_deny_before_provider(replica_db, monkeypatch):
    await seed(replica_db, monkeypatch)
    build = AsyncMock(); monkeypatch.setattr(worker, '_build_voyager', build)
    assert (await worker._fetch_posts('list', 'workspace', 'sender'))['status'] == 'stopped'
    assert (await worker._enrich_contacts('list', 'workspace', 'sender'))['status'] == 'stopped'
    build.assert_not_awaited()


@pytest.mark.parametrize('old_urn', ['', None, 'missing'])
@pytest.mark.parametrize('late_verified', [True, False])
async def test_empty_original_identity_cannot_overwrite_concurrent_verified_profile(replica_db, monkeypatch, old_urn, late_verified):
    await seed(replica_db, monkeypatch, verified=False)
    if old_urn == 'missing': await replica_db.outreach_engage_contacts.update_one({}, {'$unset': {'profile_urn': ''}})
    else: await replica_db.outreach_engage_contacts.update_one({}, {'$set': {'profile_urn': old_urn}})
    contact = await replica_db.outreach_engage_contacts.find_one({})
    binding = await projection.start_run(replica_db, 'workspace', 'list', 'enrichment', 'enrich')
    async def read(*args):
        await replica_db.outreach_engage_contacts.update_one({}, {'$set': {
            'profile_urn': 'new-identity', 'full_name': 'Replacement', 'enrichment_status': 'verified'}})
        return {'verified': late_verified, 'profile_urn': 'old-result', 'full_name': 'Late'}
    voyager = AsyncMock(); voyager.fetch_profile_info.side_effect = read
    assert (await worker._enrich_one(contact, replica_db, voyager, 'workspace', binding)) == {'status': 'stopped'}
    saved = await replica_db.outreach_engage_contacts.find_one({})
    assert saved['profile_urn'] == 'new-identity' and saved['full_name'] == 'Replacement'


async def test_deleted_contact_cannot_receive_new_draft(replica_db, monkeypatch):
    await seed(replica_db, monkeypatch)
    await replica_db.outreach_engage_posts.insert_one({'id': 'post', 'list_id': 'list', 'workspace_id': 'workspace', 'contact_id': 'absent'})
    with pytest.raises(HTTPException) as failure:
        await engage.create_engage_draft('list', engage.CreateEngageDraftRequest(post_id='post', comment_text='Draft'), current_user=USER, db=replica_db)
    assert failure.value.status_code == 409
    assert await replica_db.outreach_engage_drafts.count_documents({}) == 0


@pytest.mark.parametrize('replacement', ['list', 'contact', 'post'])
async def test_saved_draft_cannot_be_applied_to_replaced_source(replica_db, monkeypatch, replacement):
    await seed(replica_db, monkeypatch)
    await replica_db.outreach_engage_posts.insert_one({'id': 'post', 'list_id': 'list', 'workspace_id': 'workspace', 'contact_id': 'contact'})
    draft = await engage.create_engage_draft('list', engage.CreateEngageDraftRequest(post_id='post', comment_text='Reviewed'), current_user=USER, db=replica_db)
    collection = {'list': replica_db.outreach_engage_lists, 'contact': replica_db.outreach_engage_contacts,
                  'post': replica_db.outreach_engage_posts}[replacement]
    original = await collection.find_one({})
    await collection.delete_one({'_id': original.pop('_id')})
    await collection.insert_one(original)
    with pytest.raises(HTTPException) as failure:
        await engage.update_engage_draft('list', draft['id'], engage.UpdateEngageDraftRequest(status='completed'), current_user=USER, db=replica_db)
    assert failure.value.status_code == 409
    assert (await replica_db.outreach_engage_drafts.find_one({}))['status'] == 'pending'


async def test_erasure_and_standalone_reject_projection(replica_db, real_db, monkeypatch):
    from outreach.core.suppression import guard_scope
    for db in (replica_db, real_db): await seed(db, monkeypatch)
    binding = await projection.start_run(replica_db, 'workspace', 'list', 'fetch', 'run')
    contact = await replica_db.outreach_engage_contacts.find_one({})
    await replica_db.outreach_suppression_guards.update_one(guard_scope('workspace'), {'$set': {'erasure_state': 'stopped'}})
    with pytest.raises(SuppressionUnavailable): await projection.check_contact(replica_db, binding, contact)
    with pytest.raises(SuppressionUnavailable): await projection.start_run(real_db, 'workspace', 'list', 'fetch', 'run')


@pytest.mark.parametrize('original,current', [(None, 'missing'), ('missing', None), (None, ''), ('', None)])
async def test_profile_identity_presence_changes_stop_projection(replica_db, monkeypatch, original, current):
    await seed(replica_db, monkeypatch, verified=False)
    first = {'$unset': {'profile_urn': ''}} if original == 'missing' else {'$set': {'profile_urn': original}}
    await replica_db.outreach_engage_contacts.update_one({}, first)
    contact = await replica_db.outreach_engage_contacts.find_one({})
    binding = await projection.start_run(replica_db, 'workspace', 'list', 'enrichment', 'enrich')
    replacement = {'$unset': {'profile_urn': ''}} if current == 'missing' else {'$set': {'profile_urn': current}}
    await replica_db.outreach_engage_contacts.update_one({}, replacement)
    with pytest.raises(projection.ProjectionStopped):
        await projection.check_contact(replica_db, binding, contact)
