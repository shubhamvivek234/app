"""Stable browser operation references recover originals without approval or send replay."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from outreach.api.inbox import ReplyRequest, get_reply_request, send_thread_reply, _reply_request_job_id
from outreach.core.manual_actions import ManualActions
from tests.outreach_memory import Database

pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch]
USER = {'user_id': 'actor', 'default_workspace_id': 'workspace'}
REQUEST = uuid.UUID('00000000-0000-4000-8000-000000000001')
CONTEXT = {'account_id': 'sender', 'conversation_urn': 'conversation', 'thread_revision': 3}


def original():
    return {'_id': _reply_request_job_id('workspace', 'actor', REQUEST), 'workspace_id': 'workspace',
        'actor_id': 'actor', 'source': 'inbox_reply', 'target_id': 'thread', 'account_id': 'sender',
        'content': {'body': 'Original'}, 'binding': {'recipient': 'conversation', 'context': {'thread_revision': 3}},
        'status': 'completed', 'stages': {'reply': {'status': 'provider_accepted',
            'accepted_at': datetime.now(timezone.utc), 'provenance': 'provider_response'}}}


async def test_completed_request_retry_returns_original_without_reapproval_or_publish():
    row = original()
    db = Database(outreach_manual_actions=[row])
    with patch.object(ManualActions, 'queue', new_callable=AsyncMock) as queue:
        result = await send_thread_reply('thread', ReplyRequest(body='Original', request_id=REQUEST, context=CONTEXT), current_user=USER, db=db)
    assert result['job_id'] == row['_id']
    queue.assert_not_awaited()
    assert db.outreach_manual_actions.docs == [row]
    result = await get_reply_request(REQUEST, current_user=USER, db=db)
    assert result['status'] == 'completed' and result['result']['message']['body'] == 'Original'


@pytest.mark.parametrize('field,value', [('body', 'Changed'), ('account_id', 'replacement'),
    ('conversation_urn', 'other-recipient'), ('thread_revision', 4)])
async def test_request_identity_cannot_move_to_other_content_or_recipient(field, value):
    content = {'body': 'Original', 'request_id': REQUEST, 'context': dict(CONTEXT)}
    if field == 'body': content[field] = value
    else: content['context'][field] = value
    with pytest.raises(HTTPException) as exc:
        await send_thread_reply('thread', ReplyRequest(**content), current_user=USER,
            db=Database(outreach_manual_actions=[original()]))
    assert exc.value.status_code == 409


@pytest.mark.parametrize('user', [{'user_id': 'other', 'default_workspace_id': 'workspace'},
    {'user_id': 'actor', 'default_workspace_id': 'foreign'}])
async def test_request_recovery_is_bound_to_original_actor_and_workspace(user):
    with pytest.raises(HTTPException) as exc:
        await get_reply_request(REQUEST, current_user=user, db=Database(outreach_manual_actions=[original()]))
    assert exc.value.status_code == 404


async def test_changed_recipient_is_rejected_before_slot_or_approval():
    db = Database(outreach_accounts=[{'id': 'sender', 'workspace_id': 'workspace'}],
        outreach_inbox_threads=[{'id': 'thread', 'workspace_id': 'workspace',
            **CONTEXT, 'conversation_urn': 'replacement'}])
    with pytest.raises(ValueError, match='conversation changed'):
        await ManualActions(db).queue('new', 'workspace', 'sender', 'thread', 'inbox_reply', 'reply',
            {'body': 'Original'}, 'actor', expected_target=CONTEXT)
    assert db.outreach_manual_actions.docs == []
    assert 'manual_action_id' not in db.outreach_inbox_threads.docs[0]
