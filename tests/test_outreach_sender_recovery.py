"""Bounded current-context job discovery never exposes encrypted session material."""
from datetime import datetime, timedelta, timezone

from bson import Code
import pytest
from fastapi import HTTPException

from outreach.core.sender_verification_recovery import discover_jobs, recovery_context
from tests.outreach_memory import Database

USER = {'user_id': 'u', 'firebase_uid': 'uid', 'default_workspace_id': 'w'}


def record(**changes):
    return {'id': 'job', 'workspace_id': 'w', 'user_id': 'u', 'sender_id': 'sender',
        'status': 'running', 'created_at': datetime.now(timezone.utc), 'reconnect': False,
        'li_at_enc': 'never-return', 'verification_owner_token': 'never-return', **changes}


@pytest.mark.asyncio
async def test_actor_and_workspace_scoped_discovery_returns_only_explicit_metadata():
    db = Database(outreach_connection_jobs=[record(), record(id='other-user', user_id='other'),
        record(id='other-workspace', workspace_id='other')])
    result = await discover_jobs(db, USER)
    assert [row['job_id'] for row in result['jobs']] == ['job']
    assert set(result['jobs'][0]) == {'job_id', 'sender_id', 'status', 'reconnect'}
    assert 'never-return' not in str(result)
    assert result['context'] == recovery_context(USER)


@pytest.mark.asyncio
async def test_recent_completion_and_old_pending_are_discoverable_but_old_terminals_expire():
    old = datetime.now(timezone.utc) - timedelta(days=2)
    db = Database(outreach_connection_jobs=[record(id='pending', created_at=old),
        record(id='recent', status='completed'), record(id='old', status='failed', created_at=old)])
    result = await discover_jobs(db, USER)
    assert {row['job_id'] for row in result['jobs']} == {'pending', 'recent'}


@pytest.mark.asyncio
@pytest.mark.parametrize('change', [{'workspace_id': ['w']}, {'user_id': ['u']}, {'sender_id': []},
    {'status': ['running']}, {'status': 'unrecognized'}, {'reconnect': []}, {'id': Code('job')}])
async def test_malformed_discovery_fails_without_partial_payload(change):
    with pytest.raises(HTTPException) as failure:
        await discover_jobs(Database(outreach_connection_jobs=[record(**change)]), USER)
    assert failure.value.status_code == 503


@pytest.mark.asyncio
async def test_discovery_overflow_holds_instead_of_returning_incomplete_list():
    with pytest.raises(HTTPException) as failure:
        await discover_jobs(Database(outreach_connection_jobs=[record(id=str(i)) for i in range(21)]), USER)
    assert failure.value.status_code == 503


@pytest.mark.asyncio
async def test_unknown_storage_lock_remains_visible_as_a_support_hold():
    db = Database(outreach_connection_locks=[{'_id': 'sender', 'workspace_id': 'w', 'job_id': 'missing',
        'storage_outcome_unknown': True, 'storage_proof': {'private': 'never-return'}}])
    result = await discover_jobs(db, USER)
    assert result['operator_review_required'] is True
    assert not result['jobs'] and 'never-return' not in str(result)


@pytest.mark.parametrize('key,value', [('user_id', None), ('firebase_uid', None),
    ('default_workspace_id', ['w']), ('firebase_uid', Code('uid'))])
def test_context_requires_plain_current_authenticated_identity(key, value):
    with pytest.raises(HTTPException):
        recovery_context({**USER, key: value})


def test_context_changes_with_workspace_actor_or_authenticated_uid():
    initial = recovery_context(USER)['scope_digest']
    for key in USER:
        assert recovery_context({**USER, key: 'other'})['scope_digest'] != initial
