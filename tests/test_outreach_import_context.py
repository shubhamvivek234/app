"""Importer context is typed current authority, never a grant or replay receipt."""
import pytest
from bson import Code, ObjectId
from fastapi import HTTPException

from outreach.core.import_context import capture_import_scope, verify_import_scope, check_campaign_scope
from tests.outreach_memory import Database

USER = {'user_id': 'u', 'firebase_uid': 'uid', 'default_workspace_id': 'w'}
CAMPAIGN = {'_id': 'native-original', 'id': 'campaign', 'workspace_id': 'w', 'status': 'draft'}


def db(*rows):
    return Database(outreach_campaigns=list(rows or (CAMPAIGN,)))


@pytest.mark.asyncio
async def test_context_is_domain_bound_and_returns_no_authenticated_uid_or_native_id():
    scope = await capture_import_scope(db(), USER, 'campaign')
    assert set(scope.public) == {'contract_version', 'workspace_id', 'campaign_id', 'scope_digest'}
    assert scope.public['contract_version'] == 1
    assert scope.public['campaign_id'] == 'campaign'
    assert len(scope.public['scope_digest']) == 64
    assert 'uid' not in str(scope.public) and 'native-original' not in str(scope.public)
    assert (await verify_import_scope(db(), USER, 'campaign', scope.digest)).public == scope.public
    assert await verify_import_scope(db(), {}, 'campaign', None) is None  # legacy callers retain contract


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['user_id', 'firebase_uid', 'default_workspace_id'])
async def test_changed_actor_uid_or_workspace_denies_original_scope(field):
    scope = await capture_import_scope(db(), USER, 'campaign')
    rows = [CAMPAIGN, {**CAMPAIGN, '_id': 'native-other', 'workspace_id': 'other'}]
    with pytest.raises(HTTPException) as failure:
        await verify_import_scope(db(*rows), {**USER, field: 'other'}, 'campaign', scope.digest)
    assert failure.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [{'firebase_uid': None}, {'user_id': Code('u')},
    {'default_workspace_id': ['w']}, {'firebase_uid': ' '}, {'user_id': 'x' * 201}])
async def test_unproven_authenticated_context_never_becomes_a_scope(change):
    with pytest.raises(HTTPException):
        await capture_import_scope(db(), {**USER, **change}, 'campaign')


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [{'_id': None}, {'_id': Code('native-original')},
    {'_id': 1}, {'id': ['campaign']}, {'workspace_id': ['w']}, {'is_deleted': True},
    {'is_deleted': []}, {'is_deleted': 'false'}, {'is_deleted': 0}, {'is_deleted': Code('false')}])
async def test_malformed_or_deleted_campaign_holds_without_first_row_adoption(change):
    with pytest.raises(HTTPException):
        await capture_import_scope(db({**CAMPAIGN, **change}), USER, 'campaign')


@pytest.mark.asyncio
async def test_duplicate_native_public_identity_and_same_id_replacement_hold():
    scope = await capture_import_scope(db(), USER, 'campaign')
    replacement = {**CAMPAIGN, '_id': 'replacement'}
    with pytest.raises(HTTPException):
        await capture_import_scope(db(CAMPAIGN, replacement), USER, 'campaign')
    with pytest.raises(HTTPException) as failure:
        await verify_import_scope(db(replacement), USER, 'campaign', scope.digest)
    assert failure.value.status_code == 409
    with pytest.raises(HTTPException):
        check_campaign_scope(scope, replacement)


@pytest.mark.asyncio
async def test_objectid_is_distinct_from_its_text_representation():
    oid = ObjectId()
    scope = await capture_import_scope(db({**CAMPAIGN, '_id': oid}), USER, 'campaign')
    assert scope.digest != (await capture_import_scope(db({**CAMPAIGN, '_id': str(oid)}), USER, 'campaign')).digest
    check_campaign_scope(scope, {**CAMPAIGN, '_id': oid})
    with pytest.raises(HTTPException):
        check_campaign_scope(scope, {**CAMPAIGN, '_id': str(oid)})
