"""Workspace template access is advisory and never creator or execution authority."""
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

from bson import ObjectId, Code
from fastapi import HTTPException
import pytest

from outreach.core.template_access import inspect_access, describe_access


def database(role='editor', *, owner=False):
    db = MagicMock()
    user = {'_id': ObjectId(), 'user_id': 'actor', 'firebase_uid': 'uid', 'status': 'active'}
    member = {'workspace_id': 'workspace', 'user_id': 'actor', 'role': role}
    for name, rows in [('users', [user]), ('workspace_members', [] if owner else [member]),
                       ('workspaces', [{'workspace_id': 'workspace', 'owner_id': 'actor'}])]:
        collection = getattr(db, name)
        collection.find.return_value.limit.return_value.to_list = AsyncMock(return_value=rows)
    db.account_erasure_tombstones.find_one = AsyncMock(return_value=None)
    db.outreach_suppression_guards.find_one = AsyncMock(return_value=None)
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize('role,configure,edit,delete', [
    ('owner', True, True, True), ('admin', True, True, True),
    ('editor', True, True, False), ('viewer', False, False, False), ('client', False, False, False)])
async def test_existing_roles_control_workspace_actions_without_writes(role, configure, edit, delete):
    db = database(role)
    access = await inspect_access(db, 'workspace', 'actor', 'uid')
    assert (access['can_configure'], access['can_edit'], access['can_delete']) == (configure, edit, delete)
    descriptor = describe_access(access, {'user_id': 'another-creator'}, custom=True, actor='actor')
    assert descriptor == {'contract_version': 1, 'workspace_id': 'workspace', 'visibility': 'workspace',
        'created_by_you': False, 'can_configure': configure, 'can_edit': edit, 'can_delete': delete,
        'execution_authorized': False}
    assert db.mock_calls and not any(call[0].endswith(('update_one', 'insert_one', 'delete_one', 'start_session')) for call in db.mock_calls)


@pytest.mark.asyncio
async def test_unique_owner_fallback_and_builtin_cannot_be_edited():
    db = database(owner=True)
    access = await inspect_access(db, 'workspace', 'actor', 'uid')
    assert access['can_delete'] is True
    original = deepcopy(access)
    builtin = describe_access(access, {}, custom=False, actor='actor')
    assert builtin['visibility'] == 'builtin' and builtin['can_configure'] is True
    assert builtin['can_edit'] is False and builtin['can_delete'] is False and builtin['created_by_you'] is False
    assert access == original


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['missing_user', 'duplicate_user', 'array_actor', 'wrong_uid', 'array_uid',
    'duplicate_uid', 'stopped_user', 'erased', 'closed', 'duplicate_member', 'array_member',
    'stopped_member', 'invalid_role', 'missing_member', 'wrong_owner', 'duplicate_owner'])
async def test_missing_ambiguous_stopped_or_foreign_authority_denies(case):
    db = database()
    users = db.users.find.return_value.limit.return_value.to_list
    members = db.workspace_members.find.return_value.limit.return_value.to_list
    owners = db.workspaces.find.return_value.limit.return_value.to_list
    user = users.return_value[0]
    if case == 'missing_user': users.return_value = []
    elif case == 'duplicate_user': users.return_value *= 2
    elif case == 'array_actor': user['user_id'] = ['actor']
    elif case == 'wrong_uid': user['firebase_uid'] = 'other'
    elif case == 'array_uid': user['firebase_uid'] = ['uid']
    elif case == 'duplicate_uid': users.side_effect = [[user], [user, {**user, '_id': ObjectId(), 'user_id': 'other'}]]
    elif case == 'stopped_user': user['status'] = 'inactive'
    elif case == 'erased': db.account_erasure_tombstones.find_one.return_value = {'_id': 'tombstone'}
    elif case == 'closed': db.outreach_suppression_guards.find_one.return_value = {'erasure_state': 'pending'}
    elif case == 'duplicate_member': members.return_value *= 2
    elif case == 'array_member': members.return_value[0]['user_id'] = ['actor']
    elif case == 'stopped_member': members.return_value[0]['status'] = 'inactive'
    elif case == 'invalid_role': members.return_value[0]['role'] = ['admin']
    else:
        members.return_value = []
        if case == 'missing_member': owners.return_value = []
        elif case == 'wrong_owner': owners.return_value[0]['owner_id'] = 'other'
        else: owners.return_value *= 2
    with pytest.raises(HTTPException) as caught:
        await inspect_access(db, 'workspace', 'actor', 'uid')
    assert caught.value.status_code in {403, 409}


@pytest.mark.asyncio
@pytest.mark.parametrize('values', [(' ', 'actor', 'uid'), ('workspace', [], 'uid'), ('workspace', 'actor', None)])
async def test_invalid_original_context_denies_before_database_reads(values):
    db = database()
    with pytest.raises(HTTPException): await inspect_access(db, *values)
    assert db.mock_calls == []


@pytest.mark.asyncio
async def test_creator_attribution_does_not_upgrade_editor_deletion():
    access = await inspect_access(database('editor'), 'workspace', 'actor', 'uid')
    own = describe_access(access, {'user_id': 'actor'}, custom=True, actor='actor')
    assert own['created_by_you'] is True and own['can_delete'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('changes', [{'user_id': 'replacement'}, {'status': 'inactive'}])
async def test_observed_identity_reread_drift_cannot_reuse_earlier_authority(changes):
    db = database()
    users = db.users.find.return_value.limit.return_value.to_list
    original = deepcopy(users.return_value[0])
    users.side_effect = [[original], [{**original, **changes}]]
    with pytest.raises(HTTPException): await inspect_access(db, 'workspace', 'actor', 'uid')


@pytest.mark.asyncio
async def test_bson_code_role_cannot_supply_advisory_admin_permission():
    db = database(Code('admin'))
    with pytest.raises(HTTPException): await inspect_access(db, 'workspace', 'actor', 'uid')


@pytest.mark.asyncio
@pytest.mark.parametrize('collection,field,value', [('users', 'user_id', 'actor'), ('users', 'firebase_uid', 'uid'),
    ('users', 'status', 'active'), ('workspace_members', 'status', 'active'),
    ('workspaces', 'owner_id', 'actor'), ('workspaces', 'status', 'active')])
async def test_bson_code_authority_fields_are_not_plain_text(collection, field, value):
    db = database(owner=collection == 'workspaces')
    getattr(db, collection).find.return_value.limit.return_value.to_list.return_value[0][field] = Code(value)
    with pytest.raises(HTTPException): await inspect_access(db, 'workspace', 'actor', 'uid')


@pytest.mark.asyncio
async def test_access_database_failure_is_sanitized_without_partial_starters():
    from outreach.api.sequences import get_sequence_templates
    db = database()
    db.users.find.side_effect = RuntimeError('private database address')
    with pytest.raises(HTTPException) as caught:
        await get_sequence_templates({'default_workspace_id': 'workspace', 'user_id': 'actor', 'firebase_uid': 'uid'}, db)
    assert caught.value.status_code == 503 and 'private' not in caught.value.detail
    db.outreach_templates.find.assert_not_called()
