"""Native query/HTTP acceptance for resolved context; disposable loopback DB only."""
import os
from copy import deepcopy

import pytest

from api.routes import team
from outreach.api import prompts
from outreach.api.router import router
from outreach.core.suppression import guard_scope
from tests.test_outreach_authorized_context import app_for, client_for, auth_then_revoke
from tests.test_outreach_lead_workspace_scope import FOREIGN, USER, USER_ID, WORKSPACE
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db, admission_db  # noqa: F401
from tests.outreach_native import replica_server, replica_db  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Disposable native Mongo is opt-in',
)]


async def revoked_auth(db):
    # The focused helper uses real auth hydration and membership deletion here.
    return await auth_then_revoke(db)


@pytest.mark.parametrize('scope', [FOREIGN, USER_ID, None, [WORKSPACE, FOREIGN], 'MISSING'])
async def test_native_prompt_preview_library_delete_reject_ambiguous_creator_scope(real_db, scope):
    row = {'id': 'target', 'user_id': USER_ID, 'custom_variables': {'private': 'foreign-private'}}
    if scope != 'MISSING':
        row['workspace_id'] = scope
    await real_db.outreach_leads.delete_many({})
    await real_db.outreach_leads.insert_one(deepcopy(row))
    prompt = {**row, 'id': 'custom', 'name': 'Foreign', 'prompt_text': 'foreign-private', 'is_system': False}
    await real_db.outreach_ai_prompts.insert_one(deepcopy(prompt))
    before = await real_db.outreach_ai_prompts.find_one({'id': 'custom'})
    async with client_for(app_for(real_db, prompts.router)) as client:
        preview = await client.post('/prompts/preview', json={'lead_id': 'target', 'template': '{{private}}'})
        listed = await client.get('/prompts')
        deleted = await client.delete('/prompts/custom')
    assert preview.status_code == deleted.status_code == 404
    assert listed.status_code == 200 and 'foreign-private' not in listed.text
    assert await real_db.outreach_ai_prompts.find_one({'id': 'custom'}) == before


async def test_native_prompt_collision_catalog_and_custom_round_trip(real_db):
    await real_db.outreach_leads.insert_one({'id': 'target', 'workspace_id': WORKSPACE, 'custom_variables': {'private': 'current'}})
    await real_db.outreach_ai_prompts.insert_many([
        {'id': 'custom', 'workspace_id': FOREIGN, 'user_id': USER_ID, 'name': 'Foreign', 'prompt_text': 'foreign-private', 'is_system': False},
        {'id': 'custom', 'workspace_id': WORKSPACE, 'user_id': 'another', 'name': 'Current', 'prompt_text': 'current-custom'},
        {'id': 'forged', 'workspace_id': FOREIGN, 'prompt_text': 'forged-private', 'is_system': True},
        {'id': 'legacy-seed', 'workspace_id': WORKSPACE, 'prompt_text': 'legacy-seed-private', 'is_system': True},
        {'id': 'curated_activity-snippet', 'workspace_id': WORKSPACE, 'prompt_text': 'shadow-private', 'is_system': False},
    ])
    before = await real_db.outreach_ai_prompts.find({}).to_list(100)
    async with client_for(app_for(real_db, prompts.router)) as client:
        listed = await client.get('/prompts')
        assert listed.status_code == 200 and len(listed.json()) == 6
        assert 'current-custom' in listed.text and 'private' not in listed.text
        assert not any(p.get('runs_count') for p in listed.json() if p['is_system'])
        assert await real_db.outreach_ai_prompts.find({}).to_list(100) == before
        assert (await client.delete('/prompts/curated_activity-snippet')).status_code == 404
        assert (await client.delete('/prompts/custom')).status_code == 200
        preview = await client.post('/prompts/preview', json={'lead_id': 'target', 'template': '{{private}}'})
        assert preview.json()['evaluated_text'] == 'current'
        created = await client.post('/prompts', json={'name': 'New', 'prompt_text': 'New instructions'})
        assert created.status_code == 200 and created.json()['workspace_id'] == WORKSPACE
        assert (await client.delete('/prompts/' + created.json()['id'])).status_code == 200
    assert await real_db.outreach_ai_prompts.find_one({'id': 'custom', 'workspace_id': FOREIGN})


@pytest.mark.parametrize('current_exists,old_closed,new_closed,expected', [
    (False, False, False, 404), (True, False, False, 200),
    (True, True, False, 200), (True, False, True, 409),
])
async def test_native_mutation_uses_same_permission_and_erasure_tenant(admission_db, current_exists, old_closed, new_closed, expected):
    real_db = admission_db  # Deletion now requires the production transaction boundary.
    await real_db.workspace_members.update_one({'workspace_id': WORKSPACE}, {'$set': {'role': 'admin'}})
    if not current_exists:
        await real_db.outreach_campaigns.delete_many({})
    await real_db.outreach_campaigns.insert_one({'id': 'campaign', 'workspace_id': FOREIGN, 'status': 'draft'})
    for scope, closed in ((FOREIGN, old_closed), (WORKSPACE, new_closed)):
        if closed:
            await real_db.outreach_suppression_guards.insert_one({**guard_scope(scope), 'erasure_state': 'stopped'})
    before = await real_db.outreach_campaigns.find_one({'workspace_id': FOREIGN})
    auth = await revoked_auth(real_db)
    async with client_for(app_for(real_db, router, auth)) as client:
        result = await client.delete('/outreach/campaigns/campaign')
    assert result.status_code == expected
    assert await real_db.outreach_campaigns.find_one({'workspace_id': FOREIGN}) == before
    current = await real_db.outreach_campaigns.find_one({'workspace_id': WORKSPACE})
    if expected == 200:
        assert current['is_deleted'] is True
    elif current:
        assert not current.get('is_deleted')


async def test_native_read_fallback_ignores_old_hold_and_stops_at_current_hold(real_db):
    await real_db.outreach_suppression_guards.insert_one({**guard_scope(FOREIGN), 'erasure_state': 'stopped'})
    stale = {**USER, 'default_workspace_id': FOREIGN, 'workspace_ids': [FOREIGN, WORKSPACE]}
    async with client_for(app_for(real_db, prompts.router, lambda: deepcopy(stale))) as client:
        assert (await client.get('/prompts')).status_code == 200
        await real_db.outreach_suppression_guards.insert_one({**guard_scope(WORKSPACE), 'erasure_state': 'stopped'})
        assert (await client.get('/prompts')).status_code == 409


async def test_native_team_policy_fallback_and_verified_invite_boundary(real_db):
    await real_db.workspace_members.update_one({'workspace_id': WORKSPACE}, {'$set': {'role': 'admin'}})
    await real_db.workspaces.insert_one({'workspace_id': FOREIGN, 'owner_id': 'another'})
    auth = await revoked_auth(real_db)
    async with client_for(app_for(real_db, team.router, auth)) as client:
        response = await client.put('/workspace/approval-policy', json={'enabled': True})
        invitation = await client.post('/workspace/members/invite', json={'email': 'invitee@example.com'})
    assert response.status_code == 200 and invitation.status_code == 403
    assert (await real_db.workspaces.find_one({'workspace_id': WORKSPACE}))['approval_policy']['enabled']
    assert 'approval_policy' not in await real_db.workspaces.find_one({'workspace_id': FOREIGN})
    assert await real_db.workspace_invites.count_documents({}) == 0


@pytest.mark.parametrize('method,path,body,expected', [
    ('GET', '/workspace/members', None, 200),
    ('POST', '/workspace/members/invite', {'email': 'new-member@example.com'}, 201),
    ('DELETE', '/workspace/invites/invitation', None, 204),
    ('DELETE', '/workspace/members/target-member', None, 204),
    ('PATCH', '/workspace/members/target-member/role', {'role': 'editor'}, 200),
    ('PUT', '/workspace/approval-policy', {'enabled': True}, 200),
])
async def test_every_team_permission_handler_uses_fallback_tenant(real_db, method, path, body, expected):
    from api.routes.team import router
    db = real_db
    await db.workspace_members.update_one({'workspace_id': WORKSPACE}, {'$set': {'role': 'admin'}})
    for ws in (WORKSPACE, FOREIGN):
        await db.workspace_members.insert_one({'workspace_id': ws, 'user_id': 'target-member', 'role': 'viewer'})
        await db.workspace_invites.insert_one({'workspace_id': ws, 'invite_id': 'invitation', 'status': 'pending',
                                              'email': 'invited@example.com', 'token': 'synthetic-token', 'role': 'editor'})
    await db.workspaces.insert_one({'workspace_id': FOREIGN, 'owner_id': 'another', 'name': 'Foreign private workspace'})
    await db.users.insert_one({'user_id': 'target-member', 'email': 'target@example.com'})
    auth = await auth_then_revoke(db)

    async def verified_auth():
        return {**await auth(), 'email_verified': True}

    foreign_member = deepcopy(await db.workspace_members.find_one({'workspace_id': FOREIGN, 'user_id': 'target-member'}))
    foreign_invite = deepcopy(await db.workspace_invites.find_one({'workspace_id': FOREIGN}))
    foreign_workspace = deepcopy(await db.workspaces.find_one({'workspace_id': FOREIGN}))
    async with client_for(app_for(db, router, verified_auth)) as client:
        response = await client.request(method, path, json=body)
    assert response.status_code == expected, response.text
    assert 'Foreign private workspace' not in response.text
    assert await db.workspace_members.find_one({'workspace_id': FOREIGN, 'user_id': 'target-member'}) == foreign_member
    assert await db.workspace_invites.find_one({'workspace_id': FOREIGN}) == foreign_invite
    assert await db.workspaces.find_one({'workspace_id': FOREIGN}) == foreign_workspace
