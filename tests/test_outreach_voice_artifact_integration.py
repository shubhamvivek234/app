"""Storage failures and artifact races cannot silently resend paid voice work."""
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from outreach.core import suppression, voice_key_custody
from outreach.core.content_approval import ContentApproval, sequence_binding
from outreach.core.voice_artifacts import VoiceArtifacts
from outreach.core.voice_cloner import generate_mock_voice_wav
from outreach.core.voice_preparation import VoicePreparation
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_voice_key_custody import installed
from tests.test_outreach_voice_preparation import voice_db


async def ready(db, monkeypatch):
    await installed(monkeypatch)
    db.outreach_voices.docs[0]['provider_source_digest'] = voice_key_custody.source_digest()
    return await VoicePreparation(db).queue('w', 'l', 'human')


@pytest.mark.asyncio
async def test_generation_and_api_preparation_never_open_keys_in_database_callback(voice_db, scoped, monkeypatch):
    inside = ContextVar('artifact_transaction', default=False)
    original_transaction = suppression.mutate_suppression
    async def transaction(db, workspace, callback):
        async def run(current):
            token = inside.set(True)
            try: return await callback(current)
            finally: inside.reset(token)
        return await original_transaction(db, workspace, run)
    monkeypatch.setattr(suppression, 'mutate_suppression', transaction)
    seen = []
    for operation in ('open', 'seal'):
        original = getattr(scoped, operation)
        async def keys(value, context, original=original):
            assert not inside.get()
            seen.append(context.purpose)
            return await original(value, context)
        monkeypatch.setattr(scoped, operation, keys)
    job = await ready(voice_db, monkeypatch)
    generator = AsyncMock(return_value=generate_mock_voice_wav())
    assert (await VoicePreparation(voice_db).run('w', job['_id'], generator=generator))['status'] == 'prepared'
    assert seen.count('voice_artifact_key') == 1
    assert (await VoicePreparation(voice_db).queue('w', 'l', 'human'))['status'] == 'prepared'
    from outreach.api.content_approvals import prepare_content_reviews, current_binding, content_audio
    user = {'user_id': 'human', 'default_workspace_id': 'w'}
    assert (await prepare_content_reviews('c', 0, 50, user, voice_db))['prepared'] == 1
    assert seen.count('voice_artifact_key') == 1  # Reuse is metadata-only.
    review = voice_db.outreach_content_approvals.docs[0]
    assert await current_binding(voice_db, review) == review['binding']
    response = await content_audio(review['_id'], user, voice_db)
    assert response.body == generator.return_value
    assert response.headers['cache-control'] == 'private, no-store'
    assert seen.count('voice_artifact_key') == 3
    generator.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_provider_sealing_failure_holds_without_paid_replay(voice_db, scoped, monkeypatch):
    job = await ready(voice_db, monkeypatch)
    original = scoped.seal
    async def fail(value, context):
        if context.purpose == 'voice_artifact_key': raise ValueError('private storage failure')
        return await original(value, context)
    monkeypatch.setattr(scoped, 'seal', fail)
    generator = AsyncMock(return_value=generate_mock_voice_wav())
    service = VoicePreparation(voice_db)
    assert (await service.run('w', job['_id'], generator=generator))['status'] == 'held_outcome'
    assert (await service.run('w', job['_id'], generator=generator))['status'] == 'held_outcome'
    assert (await service.queue('w', 'l', 'human'))['status'] == 'held_outcome'
    generator.assert_awaited_once()
    assert voice_db.outreach_voice_preparation_budgets.docs[0]['clips'] == 1
    assert not voice_db.outreach_voice_artifacts.docs and not voice_db.outreach_content_approvals.docs
    assert 'private storage failure' not in str(voice_db.outreach_voice_preparation_jobs.docs)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['missing', 'changed'])
async def test_unproven_artifact_policy_stops_before_paid_generation(voice_db, scoped, monkeypatch, change):
    job = await ready(voice_db, monkeypatch)
    row = voice_db.outreach_voice_preparation_jobs.docs[0]
    if change == 'missing': row.pop('artifact_policy_digest')
    else: row['artifact_policy_digest'] = 'changed'
    generator = AsyncMock()
    assert (await VoicePreparation(voice_db).run('w', job['_id'], generator=generator))['status'] == 'blocked'
    generator.assert_not_awaited()
    assert not voice_db.outreach_voice_preparation_budgets.docs


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['profile', 'recipient', 'lease', 'policy'])
async def test_context_changes_while_sealing_never_install_stale_audio(voice_db, scoped, monkeypatch, change):
    job = await ready(voice_db, monkeypatch)
    original = scoped.seal
    async def edit(value, context):
        sealed = await original(value, context)
        if context.purpose == 'voice_artifact_key':
            if change == 'profile': voice_db.outreach_voices.docs[0]['revision'] = 2
            elif change == 'recipient': voice_db.outreach_leads.docs[0]['linkedin_urn'] = 'other'
            elif change == 'lease': voice_db.outreach_voice_preparation_jobs.docs[0]['claim_expires_at'] = datetime.now(timezone.utc) - timedelta(seconds=1)
            else: monkeypatch.setenv('OUTREACH_KMS_ROLE_ID', 'changed')
        return sealed
    monkeypatch.setattr(scoped, 'seal', edit)
    generator = AsyncMock(return_value=generate_mock_voice_wav())
    result = await VoicePreparation(voice_db).run('w', job['_id'], generator=generator)
    assert result['status'] in {'superseded', 'owner_changed', 'held_outcome'}
    assert not voice_db.outreach_voice_artifacts.docs and not voice_db.outreach_content_approvals.docs
    generator.assert_awaited_once()


@pytest.mark.asyncio
async def test_scoped_executor_uses_one_preopened_clip_and_still_requires_review(voice_db, scoped, monkeypatch):
    from tests.test_outreach_execution_outbox import stub_transport
    job = await ready(voice_db, monkeypatch)
    generator = AsyncMock(return_value=generate_mock_voice_wav())
    await VoicePreparation(voice_db).run('w', job['_id'], generator=generator)
    executor, transport = stub_transport(monkeypatch, review_content=True)
    transport.send_voice_note = AsyncMock(return_value={'status': 'voice_note_sent'})
    assert (await executor.SequenceExecutor.execute_lead_step('l', voice_db, workspace_id='w'))['status'] == 'content_approval_required'
    review = voice_db.outreach_content_approvals.docs[0]
    await ContentApproval(voice_db).decide('w', review['_id'], 'human', 'approve', revision=1)
    voice_db.outreach_intents.docs[0]['next_action_due_at'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    spy = AsyncMock(wraps=scoped.open)
    monkeypatch.setattr(scoped, 'open', spy)
    assert (await executor.SequenceExecutor.execute_lead_step('l', voice_db, workspace_id='w'))['status'] == 'success'
    assert transport.send_voice_note.await_args.kwargs['audio_bytes'] == generator.return_value
    assert len([call for call in spy.await_args_list if call.args[1].purpose == 'voice_artifact_key']) == 1
    generator.assert_awaited_once()


@pytest.mark.asyncio
async def test_replacement_generation_invalidates_preview_even_when_audio_digest_matches(voice_db, scoped, monkeypatch):
    from fastapi import HTTPException
    from outreach.api.content_approvals import content_audio
    job = await ready(voice_db, monkeypatch)
    await VoicePreparation(voice_db).run('w', job['_id'], generator=AsyncMock(return_value=generate_mock_voice_wav()))
    review = deepcopy(voice_db.outreach_content_approvals.docs[0])
    base = await sequence_binding(voice_db, 'w', 'l')
    await VoiceArtifacts(voice_db).store(base, generate_mock_voice_wav(), generation_id='replacement')
    with pytest.raises(HTTPException) as raised:
        await content_audio(review['_id'], {'default_workspace_id': 'w'}, voice_db)
    assert raised.value.status_code == 409
