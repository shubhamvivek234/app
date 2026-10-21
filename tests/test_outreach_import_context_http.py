"""Real route/permission/erasure dependencies; auth and DB transport are replaced."""
import httpx
import pytest
from fastapi import FastAPI

from api.deps import get_current_user
from db.mongo import get_db
from outreach.api.leads import router
from outreach.core.import_context import capture_import_scope
from tests.outreach_memory import Database

USER = {'user_id': 'u', 'firebase_uid': 'uid', 'default_workspace_id': 'w', 'workspace_ids': ['w']}


def database(role='editor'):
    return Database(workspaces=[{'workspace_id': 'w', 'owner_id': 'owner'}],
        workspace_members=[{'workspace_id': 'w', 'user_id': 'u', 'role': role}],
        outreach_campaigns=[{'_id': 'original', 'id': 'campaign', 'workspace_id': 'w', 'status': 'draft', 'leads_count': 0}],
        outreach_import_jobs=[{'_id': 'native-job', 'id': 'job', 'campaign_id': 'campaign', 'workspace_id': 'w', 'status': 'completed'}])


def client_for(db, identity):
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: identity
    app.dependency_overrides[get_db] = lambda: db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


@pytest.mark.asyncio
async def test_bootstrap_is_private_and_scoped_preview_and_commit_echo_exact_context():
    db = database()
    async with client_for(db, dict(USER)) as client:
        bootstrap = await client.get('/leads/import-context', params={'campaign_id': 'campaign'})
        assert bootstrap.status_code == 200
        assert 'no-store' in bootstrap.headers['cache-control']
        context = bootstrap.json()
        headers = {'X-Outreach-Import-Scope': context['scope_digest']}
        preview = await client.post('/leads/preview', headers=headers, json={'campaign_id': 'campaign', 'source_type': 'pasted_urls',
            'raw_text': 'https://linkedin.com/in/alice, Alice'})
        assert preview.status_code == 200 and preview.json()['import_context'] == context
        assert 'no-store' in preview.headers['cache-control']
        saved = await client.post('/leads/import-urls', headers=headers,
            json={'campaign_id': 'campaign', 'urls_text': 'https://linkedin.com/in/alice, Alice'})
        assert saved.status_code == 200 and saved.json()['import_context'] == context
        assert saved.json()['imported_count'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('method,path,body', [
    ('post','/preview', {'campaign_id': 'campaign', 'raw_text': 'private'}),
    ('post','/preview-staged', {'campaign_id': 'campaign', 'leads': [{'linkedin_url': 'https://linkedin.com/in/alice'}]}),
    ('post','/import-urls', {'campaign_id': 'campaign', 'urls_text': 'https://linkedin.com/in/alice, Alice'}),
    ('post','/import-csv', {'campaign_id': 'campaign', 'csv_text': 'linkedin_url\nhttps://linkedin.com/in/alice'}),
    ('post','/import-staged', {'campaign_id': 'campaign', 'leads': [{'linkedin_url': 'https://linkedin.com/in/alice'}]}),
    ('post','/import-search', {'campaign_id': 'campaign', 'search_url': 'https://linkedin.com/search/results/people/'}),
    ('get','/import-jobs/job', None), ('get','/import-jobs/job/staged', None),
    ('post','/import-jobs/job/cancel', None), ('post','/import-jobs/job/commit', {'selected_lead_ids': ['lead']}),
])
async def test_old_context_is_denied_on_every_import_route_before_read_or_mutation(method, path, body):
    db = database(); identity = dict(USER)
    original = await capture_import_scope(db, identity, 'campaign')
    identity['firebase_uid'] = 'replacement-uid'  # same browser token can resolve another session
    async with client_for(db, identity) as client:
        result = await client.request(method, '/leads'+path, headers={'X-Outreach-Import-Scope': original.digest}, json=body)
    assert result.status_code == 409, result.text
    assert not db.outreach_leads.docs
    assert db.outreach_import_jobs.docs[0]['status'] == 'completed'
    assert not db.outreach_campaigns.docs[0].get('lead_admission_revision')


@pytest.mark.asyncio
@pytest.mark.parametrize('digest', ['', 'A'*64, 'x', 'a'*65])
async def test_malformed_header_is_not_silently_treated_as_legacy(digest):
    db = database()
    async with client_for(db, dict(USER)) as client:
        response = await client.post('/leads/import-urls', headers={'X-Outreach-Import-Scope': digest},
            json={'campaign_id': 'campaign', 'urls_text': 'https://linkedin.com/in/alice, Alice'})
    assert response.status_code == 422
    assert not db.outreach_leads.docs


@pytest.mark.asyncio
async def test_bootstrap_still_requires_create_permission():
    async with client_for(database('viewer'), dict(USER)) as client:
        result = await client.get('/leads/import-context', params={'campaign_id': 'campaign'})
    assert result.status_code == 403
