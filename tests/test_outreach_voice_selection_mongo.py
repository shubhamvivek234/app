"""Explicit voice choices through actual guarded assignment and binding queries."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import os

from cryptography.fernet import Fernet
from fastapi import HTTPException
import pytest
import pytest_asyncio

from outreach.api.voice import assign_voice, AssignVoiceRequest
from outreach.core.content_approval import ContentApproval, sequence_binding
from outreach.core.voice_selection import selected_voice
from outreach.core.voice_studio import source_digest
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_execution_outbox import execution_db

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]
USER = {'user_id': 'actor', 'default_workspace_id': 'w'}


@pytest_asyncio.fixture
async def voice_db(replica_db, monkeypatch):
    from utils import encryption
    monkeypatch.setattr(encryption, '_fernet', Fernet(Fernet.generate_key()))
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'synthetic-voice-key')
    source = execution_db()
    source.outreach_sequences.docs[0]['compiled_dag']['nodes']['n'].update(type='voice_note', config={'script': 'Hello'})
    for name, rows in source.collections.items():
        if rows.docs: await replica_db[name].insert_many(deepcopy(rows.docs))
    await replica_db.workspace_members.insert_one({'workspace_id': 'w', 'user_id': 'actor', 'role': 'owner'})
    for identifier, assigned in [('v1', ['a']), ('v2', [])]:
        await replica_db.outreach_voices.insert_one({'workspace_id': 'w', 'id': identifier,
            'elevenlabs_voice_id': 'vendor-' + identifier, 'status': 'active', 'revision': 1,
            'assigned_account_ids': assigned, 'provider_source_digest': source_digest(),
            'consent': {'version': 1, 'actor': 'actor', 'asserted_at': datetime.now(timezone.utc), 'assertion_digest': 'synthetic-consent'}})
    return replica_db


async def assign(db, voice, accounts, revision=1):
    return await assign_voice(voice, AssignVoiceRequest(account_ids=accounts, revision=revision), current_user=USER, db=db)


async def test_native_explicit_reassignment_removes_previous_choice_and_invalidates_artifact(voice_db):
    from outreach.core.voice_artifacts import VoiceArtifacts
    from outreach.core.voice_cloner import generate_mock_voice_wav
    base = await sequence_binding(voice_db, 'w', 'l')
    artifact = await VoiceArtifacts(voice_db).store(base, generate_mock_voice_wav())
    reviewed = await sequence_binding(voice_db, 'w', 'l', voice_artifact=artifact)
    service = ContentApproval(voice_db)
    review = await service.ensure(reviewed)
    await service.decide('w', review['_id'], 'actor', 'approve', revision=1)
    assert await service.allowed(reviewed)
    assert (await assign(voice_db, 'v2', ['a']))['revision'] == 2
    assert (await voice_db.outreach_voices.find_one({'id': 'v1'}))['assigned_account_ids'] == []
    assert (await selected_voice(voice_db, 'w', 'a'))['id'] == 'v2'
    assert (await sequence_binding(voice_db, 'w', 'l'))['context']['voice_selection_id'] == 'v2'
    assert not await service.allowed(await sequence_binding(voice_db, 'w', 'l'))
    with pytest.raises(ValueError, match='recording context changed'):
        await sequence_binding(voice_db, 'w', 'l', voice_artifact=artifact)
    assert await voice_db.outreach_execution_permissions.count_documents({}) == 0
    assert (await voice_db.outreach_content_approvals.find_one({'_id': review['_id']}))['status'] == 'approved'
    assert await voice_db.outreach_voice_artifacts.count_documents({'_id': artifact['_id']}) == 1


async def test_native_unassignment_has_no_workspace_fallback(voice_db):
    await assign(voice_db, 'v1', [])
    with pytest.raises(ValueError, match='Select exactly one voice'):
        await sequence_binding(voice_db, 'w', 'l')


async def test_native_ambiguous_assignments_deny_until_explicitly_resolved(voice_db):
    await voice_db.outreach_voices.update_one({'id': 'v2'}, {'$set': {'assigned_account_ids': ['a']}})
    with pytest.raises(ValueError, match='Select exactly one voice'):
        await sequence_binding(voice_db, 'w', 'l')
    await assign(voice_db, 'v2', ['a'])
    assert (await selected_voice(voice_db, 'w', 'a'))['id'] == 'v2'


@pytest.mark.parametrize('change', ['stale', 'foreign-sender', 'duplicate', 'missing', 'busy-target', 'busy-previous', 'malformed-previous', 'float-target', 'bool-target', 'viewer', 'foreign-voice'])
async def test_native_failed_selection_changes_nothing(voice_db, change):
    accounts, revision, voice = ['a'], 1, 'v2'
    if change == 'stale': revision = 99
    if change == 'foreign-sender':
        accounts = ['foreign']; await voice_db.outreach_accounts.insert_one({'workspace_id': 'elsewhere', 'id': 'foreign'})
    if change == 'duplicate': accounts = ['a', 'a']
    if change == 'missing': voice = 'missing'
    if change == 'busy-target': await voice_db.outreach_voices.update_one({'id': 'v2'}, {'$set': {'studio_job_id': 'unfinished'}})
    if change == 'busy-previous': await voice_db.outreach_voices.update_one({'id': 'v1'}, {'$set': {'studio_job_id': 'unfinished'}})
    if change == 'malformed-previous': await voice_db.outreach_voices.update_one({'id': 'v1'}, {'$unset': {'revision': ''}})
    if change == 'float-target': await voice_db.outreach_voices.update_one({'id': 'v2'}, {'$set': {'revision': 1.0}})
    if change == 'bool-target': await voice_db.outreach_voices.update_one({'id': 'v2'}, {'$set': {'revision': True}})
    if change == 'viewer': await voice_db.workspace_members.update_one({'workspace_id': 'w'}, {'$set': {'role': 'viewer'}})
    if change == 'foreign-voice': await voice_db.outreach_voices.update_one({'id': 'v2'}, {'$set': {'workspace_id': ['w', 'foreign']}})
    before = await voice_db.outreach_voices.find({}).to_list(10)
    with pytest.raises(HTTPException): await assign(voice_db, voice, accounts, revision)
    assert await voice_db.outreach_voices.find({}).to_list(10) == before


async def test_native_concurrent_same_revision_requests_have_one_winner(voice_db):
    results = await asyncio.gather(assign(voice_db, 'v2', ['a']), assign(voice_db, 'v2', []), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, HTTPException) for result in results) == 1
    voices = await voice_db.outreach_voices.find({'assigned_account_ids': 'a'}).to_list(5)
    assert len(voices) <= 1


@pytest.mark.parametrize('assigned', [None, 'a', ['a', 'a'], ['a', ['foreign']]])
async def test_native_malformed_assignment_never_selects_arbitrary_voice(voice_db, assigned):
    await voice_db.outreach_voices.update_one({'id': 'v1'}, {'$set': {'assigned_account_ids': assigned}})
    with pytest.raises(ValueError): await sequence_binding(voice_db, 'w', 'l')


async def test_native_revoked_voice_can_be_unassigned_without_reauthorizing(voice_db):
    await voice_db.outreach_voices.update_one({'id': 'v1'}, {'$set': {'status': 'consent_revoked', 'consent': {}}})
    await assign(voice_db, 'v1', [])
    profile = await voice_db.outreach_voices.find_one({'id': 'v1'})
    assert profile['status'] == 'consent_revoked' and profile['consent'] == {}
    with pytest.raises(ValueError): await selected_voice(voice_db, 'w', 'a')


async def test_native_reselecting_same_voice_never_reuses_original_approval_identity(voice_db):
    first = await sequence_binding(voice_db, 'w', 'l')
    consent = (await voice_db.outreach_voices.find_one({'id': 'v1'}))['consent']
    await assign(voice_db, 'v1', [])
    await assign(voice_db, 'v1', ['a'], revision=2)
    current = await sequence_binding(voice_db, 'w', 'l')
    assert current['context']['voice_profile_identity'] != first['context']['voice_profile_identity']
    assert (await voice_db.outreach_voices.find_one({'id': 'v1'}))['consent'] == consent


@pytest.mark.parametrize('vendor', [None, '', ['foreign']])
async def test_native_missing_provider_voice_cannot_be_selected_or_assigned(voice_db, vendor):
    await voice_db.outreach_voices.update_many({}, {'$set': {'elevenlabs_voice_id': vendor}})
    with pytest.raises(ValueError): await sequence_binding(voice_db, 'w', 'l')
    with pytest.raises(HTTPException): await assign(voice_db, 'v2', ['a'])
