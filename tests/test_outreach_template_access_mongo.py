"""Actual database/API observations and unchanged current mutation authority."""
from copy import deepcopy
import os

from bson import ObjectId, Code
from fastapi import FastAPI, HTTPException
import httpx
import pytest

from api.deps import get_current_user
from db.mongo import get_db
from outreach.api.sequences import get_sequence_templates, router
from outreach.core.template_access import inspect_access
from tests.outreach_native import replica_server, replica_db  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo opt-in')]
ACTOR = {'user_id': 'actor', 'firebase_uid': 'uid', 'default_workspace_id': 'workspace'}


async def seed(db, role='admin', creator='other'):
    await db.users.insert_one({'user_id': 'actor', 'firebase_uid': 'uid', 'status': 'active'})
    await db.workspaces.insert_one({'workspace_id': 'workspace', 'owner_id': 'actor', 'status': 'active'})
    await db.workspace_members.insert_one({'workspace_id': 'workspace', 'user_id': 'actor', 'role': role})
    node = {'id': 'root', 'type': 'visit_profile', 'delay_hours': 0, 'config': {}}
    row = {'_id': ObjectId(), 'id': 'tpl_custom_012345abcd', 'is_custom': True, 'name': 'Shared template',
        'workspace_id': 'workspace', 'user_id': creator, 'nodes': [node], 'edges': [], 'tree': [deepcopy(node)],
        'workspace_access': {'visibility': 'public', 'can_delete': True}}
    await db.outreach_templates.insert_one(row)
    await db.outreach_templates.insert_one({**row, '_id': ObjectId(), 'workspace_id': 'foreign'})
    return row


def client(db):
    app = FastAPI();app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: ACTOR.copy()
    app.dependency_overrides[get_db] = lambda: db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


@pytest.mark.parametrize('role,edit,delete', [('owner', True, True), ('admin', True, True),
    ('editor', True, False), ('viewer', False, False), ('client', False, False)])
async def test_actual_api_workspace_sharing_roles_and_builtin_protection(replica_db, role, edit, delete):
    row = await seed(replica_db, role)
    async with client(replica_db) as api:
        response = await api.get('/sequences/templates')
    assert response.status_code == 200, response.text
    catalog = response.json()
    custom = [item for item in catalog if item.get('is_custom')]
    assert len(custom) == 1 and custom[0]['id'] == row['id'] and '_id' not in custom[0]
    access = custom[0]['workspace_access']
    assert access == {'contract_version': 1, 'workspace_id': 'workspace', 'visibility': 'workspace',
        'created_by_you': False, 'can_configure': edit, 'can_edit': edit, 'can_delete': delete, 'execution_authorized': False}
    assert custom[0]['compatibility']['configuration_available'] is True
    for builtin in [item for item in catalog if not item.get('is_custom')]:
        assert builtin['workspace_access']['visibility'] == 'builtin'
        assert builtin['workspace_access']['can_edit'] is False and builtin['workspace_access']['can_delete'] is False
    assert await replica_db.outreach_templates.find_one({'_id': row['_id']}) == row
    assert await replica_db.users.count_documents({'template_authority_revision': {'$exists': True}}) == 0


async def test_direct_gallery_inspection_does_not_write_authority_or_guard_records(replica_db):
    await seed(replica_db)
    collections = ['users', 'workspace_members', 'workspaces', 'outreach_templates', 'outreach_suppression_guards']
    before = {name: await replica_db[name].find({}).to_list(100) for name in collections}
    await get_sequence_templates(ACTOR.copy(), replica_db)
    after = {name: await replica_db[name].find({}).to_list(100) for name in collections}
    assert after == before


@pytest.mark.parametrize('alias', ['public', 'uid'])
async def test_duplicate_scalar_or_array_identity_denies_before_catalog_disclosure(replica_db, alias):
    await seed(replica_db)
    await replica_db.users.insert_one({'user_id': ['actor'] if alias == 'public' else 'another',
        'firebase_uid': 'other' if alias == 'public' else ['uid']})
    with pytest.raises(HTTPException) as caught:
        await get_sequence_templates(ACTOR.copy(), replica_db)
    assert caught.value.status_code == 403


async def test_membership_has_priority_over_owner_fallback(replica_db):
    await seed(replica_db, 'viewer', creator='actor')
    access = await inspect_access(replica_db, 'workspace', 'actor', 'uid')
    assert not access['can_configure'] and not access['can_delete']
    await replica_db.workspace_members.delete_many({})
    assert (await inspect_access(replica_db, 'workspace', 'actor', 'uid'))['can_delete'] is True


async def test_stale_admin_catalog_never_overrides_current_role_on_deletion(replica_db):
    row = await seed(replica_db, creator='actor')
    async with client(replica_db) as api:
        listed = await api.get('/sequences/templates')
        template = next(item for item in listed.json() if item['id'] == row['id'])
        assert template['workspace_access']['can_delete'] is True and template['workspace_access']['created_by_you'] is True
        await replica_db.workspace_members.update_one({'user_id': 'actor'}, {'$set': {'role': 'editor'}})
        payload = {key: template['deletion_review'][key] for key in ['contract_version', 'workspace_id',
            'revision', 'review_digest', 'identity_digest', 'scope_digest']}
        denied = await api.request('DELETE', f'/sequences/templates/{row["id"]}/reviewed', json=payload)
        assert denied.status_code == 403
        fresh = await api.get('/sequences/templates')
    current = next(item for item in fresh.json() if item['id'] == row['id'])
    assert current['workspace_access']['can_delete'] is False
    assert await replica_db.outreach_templates.find_one({'_id': row['_id']}) == row


@pytest.mark.parametrize('stop', ['workspace', 'identity', 'member'])
async def test_current_stops_deny_direct_inspection(replica_db, stop):
    await seed(replica_db)
    if stop == 'workspace':
        from outreach.core.suppression import guard_scope
        await replica_db.outreach_suppression_guards.insert_one({**guard_scope('workspace'), 'erasure_state': 'pending'})
    elif stop == 'identity':
        from outreach.core.authorization import canonical_hash
        await replica_db.account_erasure_tombstones.insert_one({'_id': canonical_hash(['firebase_identity', 'uid'])})
    else:
        await replica_db.workspace_members.update_one({'user_id': 'actor'}, {'$set': {'status': 'inactive'}})
    with pytest.raises(HTTPException): await get_sequence_templates(ACTOR.copy(), replica_db)


@pytest.mark.parametrize('collection,field,value', [('users', 'status', 'active'),
    ('workspace_members', 'role', 'admin'), ('workspaces', 'owner_id', 'actor'), ('workspaces', 'status', 'active')])
async def test_actual_bson_code_never_becomes_plain_authority(replica_db, collection, field, value):
    await seed(replica_db)
    if collection == 'workspaces': await replica_db.workspace_members.delete_many({})
    await replica_db[collection].update_one({}, {'$set': {field: Code(value)}})
    with pytest.raises(HTTPException): await inspect_access(replica_db, 'workspace', 'actor', 'uid')
