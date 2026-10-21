"""Owned real Mongo: exact campaign admission and original search-job continuity."""
import asyncio
import json
import os

from bson import Code
from fastapi import HTTPException
import pytest

from outreach.api import leads as api
from outreach.core.import_context import capture_import_scope, job_campaign_binding
from outreach.core.lead_importer import LeadImporter
from outreach.core.suppression import SuppressionUnavailable
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]
USER = {'user_id': 'u', 'firebase_uid': 'uid', 'default_workspace_id': 'w'}
ROW = {'linkedin_url': 'https://linkedin.com/in/alice', 'first_name': 'Alice'}


async def campaign(db):
    await db.outreach_campaigns.insert_one({'id': 'campaign', 'workspace_id': 'w', 'status': 'draft', 'leads_count': 0})
    return await capture_import_scope(db, USER, 'campaign')


async def test_current_scoped_import_commits_contacts_counter_and_outbox(replica_db):
    scope = await campaign(replica_db)
    result = await api.import_leads_urls(api.ImportURLsRequest(campaign_id='campaign', urls_text=ROW['linkedin_url']+', Alice'),
        current_user=USER, db=replica_db, import_scope=scope.digest)
    body = json.loads(result.body)
    assert body['import_context'] == scope.public and body['imported_count'] == 1
    assert await replica_db.outreach_leads.count_documents({'workspace_id': 'w'}) == 1
    assert await replica_db.outreach_event_outbox.count_documents({'workspace_id': 'w'}) == 1
    assert (await replica_db.outreach_campaigns.find_one({'id': 'campaign'}))['leads_count'] == 1


@pytest.mark.parametrize('change', ['replacement', 'duplicate', 'same-text-native', 'deleted-array', 'deleted-code'])
async def test_transaction_rechecks_original_campaign_after_earlier_context_capture(replica_db, change):
    scope = await campaign(replica_db)
    row = await replica_db.outreach_campaigns.find_one({'id': 'campaign'})
    if change in {'replacement', 'same-text-native'}:
        await replica_db.outreach_campaigns.delete_one({'_id': row['_id']})
        row['_id'] = str(row['_id']) if change == 'same-text-native' else 'replacement'
        await replica_db.outreach_campaigns.insert_one(row)
    elif change == 'duplicate':
        row.pop('_id'); await replica_db.outreach_campaigns.insert_one(row)
    else:
        await replica_db.outreach_campaigns.update_one({'id': 'campaign'}, {'$set': {'is_deleted': [] if change == 'deleted-array' else Code('false')}})
    with pytest.raises(HTTPException):
        await LeadImporter.ingest_leads([ROW], 'campaign', 'w', replica_db, _import_scope=scope)
    assert await replica_db.outreach_leads.count_documents({}) == 0
    assert await replica_db.outreach_event_outbox.count_documents({}) == 0
    assert all(not row.get('lead_admission_revision') for row in await replica_db.outreach_campaigns.find({}).to_list(10))


async def test_failure_after_parent_fence_rolls_back_whole_scoped_admission(replica_db, monkeypatch):
    scope = await campaign(replica_db)
    from outreach.core import event_outbox
    async def fail(*args, **kwargs):
        raise RuntimeError('injected outbox persistence failure')
    monkeypatch.setattr(event_outbox, 'record_outbox_event', fail)
    with pytest.raises(RuntimeError):
        await LeadImporter.ingest_leads([ROW], 'campaign', 'w', replica_db, _import_scope=scope)
    assert await replica_db.outreach_leads.count_documents({}) == 0
    parent = await replica_db.outreach_campaigns.find_one({'id': 'campaign'})
    assert not parent.get('lead_admission_revision') and parent['leads_count'] == 0


async def test_unknown_acknowledgement_retains_committed_contacts_without_replay(replica_db, monkeypatch):
    scope = await campaign(replica_db)
    from outreach.core import suppression
    original = suppression.mutate_suppression; calls = []
    async def commit_then_raise(*args, **kwargs):
        calls.append(1); await original(*args, **kwargs)
        raise SuppressionUnavailable('simulated acknowledgement loss after actual commit')
    monkeypatch.setattr(suppression, 'mutate_suppression', commit_then_raise)
    with pytest.raises(HTTPException) as failure:
        await LeadImporter.ingest_leads([ROW], 'campaign', 'w', replica_db, _import_scope=scope)
    assert failure.value.status_code == 503 and len(calls) == 1
    assert await replica_db.outreach_leads.count_documents({}) == 1
    assert await replica_db.outreach_event_outbox.count_documents({}) == 1


async def test_same_context_concurrent_imports_still_share_compound_deduplication(replica_db):
    scope = await campaign(replica_db)
    results = await asyncio.gather(*(LeadImporter.ingest_leads([ROW], 'campaign', 'w', replica_db,
        _import_scope=scope) for _ in range(2)))
    assert sum(result['imported_count'] for result in results) == 1
    assert await replica_db.outreach_leads.count_documents({}) == 1


async def test_actual_erasure_hold_prevents_scoped_admission(replica_db):
    scope = await campaign(replica_db)
    await replica_db.workspaces.insert_one({'workspace_id': 'w', 'owner_id': 'u'})
    from outreach.core.erasure import OutreachErasure
    await OutreachErasure(replica_db).request('w', 'u')
    with pytest.raises(HTTPException) as failure:
        await LeadImporter.ingest_leads([ROW], 'campaign', 'w', replica_db, _import_scope=scope)
    assert failure.value.status_code == 503
    assert await replica_db.outreach_leads.count_documents({}) == 0


async def test_standalone_cannot_confirm_scoped_import(real_db):
    scope = await campaign(real_db)
    before = await real_db.outreach_leads.find({}).to_list(10)
    with pytest.raises(HTTPException) as failure:
        await LeadImporter.ingest_leads([ROW], 'campaign', 'w', real_db, _import_scope=scope)
    assert failure.value.status_code == 503
    assert await real_db.outreach_leads.find({}).to_list(10) == before
    assert await real_db.outreach_leads.count_documents({'workspace_id': 'w'}) == 0


@pytest.mark.parametrize('change', ['missing', 'wrong', 'version-bool', 'array', 'duplicate-job', 'replaced-campaign'])
async def test_unproven_original_job_never_returns_staged_rows(replica_db, change):
    scope = await campaign(replica_db)
    job = {'id': 'job', 'workspace_id': 'w', 'campaign_id': 'campaign', 'status': 'completed',
        '_import_campaign_native': job_campaign_binding(scope)}
    if change == 'missing': job.pop('_import_campaign_native')
    if change == 'wrong': job['_import_campaign_native']['value'] = 'another'
    if change == 'version-bool': job['_import_campaign_native']['version'] = True
    if change == 'array': job['campaign_id'] = ['campaign']
    await replica_db.outreach_import_jobs.insert_one(job)
    if change == 'duplicate-job':
        job.pop('_id'); await replica_db.outreach_import_jobs.insert_one(job)
    if change == 'replaced-campaign':
        parent = await replica_db.outreach_campaigns.find_one({}); await replica_db.outreach_campaigns.delete_one({})
        parent.pop('_id'); await replica_db.outreach_campaigns.insert_one(parent)
    await replica_db.outreach_leads.insert_one({'id': 'private', 'workspace_id': 'w', 'campaign_id': 'campaign',
        'import_job_id': 'job', 'execution_state': 'staged', 'first_name': 'Private'})
    with pytest.raises(HTTPException):
        await api.get_staged_leads_for_job('job', current_user=USER, db=replica_db, import_scope=scope.digest)


async def test_supported_fixture_search_persists_original_binding_before_publication(replica_db, monkeypatch):
    scope = await campaign(replica_db)
    monkeypatch.setattr(api, 'require_search_collection', lambda url: {'clean_url': url, 'search_type': 'basic'})
    async def entitlement(*args): return {'id': 'synthetic-only'}
    monkeypatch.setattr(api, 'get_active_entitlement', entitlement)
    await replica_db.outreach_accounts.insert_one({'id': 'sender', 'workspace_id': 'w', 'status': 'active'})
    await replica_db.outreach_proxy_leases.insert_one({'_id': 'proxy', 'workspace_id': 'w', 'sender_id': 'sender'})
    await replica_db.outreach_proxy_inventory.insert_one({'_id': 'proxy', 'status': 'available'})
    from celery_workers.tasks.outreach import crawl_page
    published = []
    monkeypatch.setattr(crawl_page, 'delay', lambda *args: published.append(args))
    result = await api.import_search_url(api.ImportSearchRequest(campaign_id='campaign', sender_account_id='sender',
        search_url='https://linkedin.com/search/results/people/'), current_user=USER, db=replica_db, import_scope=scope.digest)
    saved = await replica_db.outreach_import_jobs.find_one({})
    assert saved['_import_campaign_native'] == job_campaign_binding(scope)
    assert published[0][0] == saved['id'] and len(published) == 1
    assert '_import_campaign_native' not in json.loads(result.body)
    status = await api.get_import_job(saved['id'], current_user=USER, db=replica_db, import_scope=scope.digest)
    assert json.loads(status.body)['import_context'] == scope.public


async def test_cancel_cannot_accept_a_replacement_native_jobs_terminal_result(replica_db, monkeypatch):
    from types import SimpleNamespace
    scope = await campaign(replica_db)
    old = {'id': 'job', 'workspace_id': 'w', 'campaign_id': 'campaign', 'status': 'crawling',
        '_import_campaign_native': job_campaign_binding(scope)}
    await replica_db.outreach_import_jobs.insert_one(old)
    collection_type = type(replica_db.outreach_import_jobs)
    original = collection_type.update_one
    async def replace_before_cancel(collection, query, update, **options):
        if (collection.database.name == replica_db.name and collection.name == 'outreach_import_jobs'
                and update.get('$set', {}).get('status') == 'stopped'):
            await collection.delete_one({'_id': old['_id']})
            replacement = {key: value for key, value in old.items() if key != '_id'}
            replacement['status'] = 'completed'
            await collection.insert_one(replacement)
            return SimpleNamespace(matched_count=0)
        return await original(collection, query, update, **options)
    monkeypatch.setattr(collection_type, 'update_one', replace_before_cancel)
    with pytest.raises(HTTPException) as failure:
        await api.cancel_import_job('job', current_user=USER, db=replica_db, import_scope=scope.digest)
    assert failure.value.status_code == 409
    current = await replica_db.outreach_import_jobs.find_one({'id': 'job'})
    assert current['_id'] != old['_id'] and current['status'] == 'completed'
