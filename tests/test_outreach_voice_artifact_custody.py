"""Campaign recordings cannot cross scope, generation, or custody boundaries."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from outreach.core import session_custody
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.voice_artifacts import VoiceArtifacts
from outreach.core.voice_cloner import generate_mock_voice_wav
from tests.outreach_memory import Database
from tests.test_outreach_session_custody import scoped


def binding():
    return {'workspace_id': 'w', 'sender_id': 'a', 'content': {'body': 'Hello'},
            'context': {'lead_id': 'l', 'enrollment_id': 'e'}}


@pytest.mark.asyncio
async def test_scoped_recording_is_generation_bound_and_prepared_values_hide_content(scoped):
    db = Database()
    audio = generate_mock_voice_wav()
    doc = await VoiceArtifacts(db).store(binding(), audio, generation_id='generation')
    assert doc['audio_enc'].startswith('va1:')
    clip = await VoiceArtifacts(db).prepare_load('w', doc['_id'])
    assert clip.audio == audio and clip.matches(doc)
    assert 'RIFF' not in repr(clip) and doc['audio_enc'] not in repr(clip)
    assert await VoiceArtifacts(db).load('w', doc['_id']) == audio
    assert not db.outreach_sender_execution.docs


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [
    ('workspace_id', 'other'), ('_id', 'a' * 64), ('binding_digest', 'a' * 64),
    ('generation_id', 'replacement'), ('audio_digest', 'b' * 64), ('byte_count', 100),
    ('duration_ms', 12), ('sample_rate', 8000), ('media_type', 'audio/mpeg'),
    ('prepared_at', datetime(2026, 10, 1, tzinfo=timezone.utc)),
    ('expires_at', datetime(2027, 1, 1, tzinfo=timezone.utc)),
])
async def test_authenticated_recording_metadata_cannot_be_relabelled(scoped, field, value):
    db = Database()
    doc = await VoiceArtifacts(db).store(binding(), generate_mock_voice_wav(), generation_id='g')
    row = db.outreach_voice_artifacts.docs[0]
    row[field] = value
    with pytest.raises(ValueError):
        await VoiceArtifacts(db).load(row['workspace_id'], row['_id'])


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['workspace', 'recording', 'generation'])
async def test_copied_ciphertext_never_opens_for_another_recording(scoped, change):
    db = Database()
    first = await VoiceArtifacts(db).store(binding(), generate_mock_voice_wav(), generation_id='g')
    other = deepcopy(binding())
    if change == 'workspace': other['workspace_id'] = 'other'
    elif change == 'recording': other['context']['lead_id'] = 'other'
    second = await VoiceArtifacts(db).store(other, generate_mock_voice_wav(), generation_id='new')
    row = next(row for row in db.outreach_voice_artifacts.docs if row['_id'] == second['_id'])
    row['audio_enc'] = first['audio_enc']
    with pytest.raises(CustodyUnavailable):
        await VoiceArtifacts(db).load(row['workspace_id'], row['_id'])


@pytest.mark.asyncio
async def test_no_fernet_fallback_or_scoped_downgrade(scoped, monkeypatch):
    db = Database()
    scoped_doc = await VoiceArtifacts(db).store(binding(), generate_mock_voice_wav(), generation_id='g')
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    with pytest.raises(ValueError): await VoiceArtifacts(db).load('w', scoped_doc['_id'])
    legacy = await VoiceArtifacts(db).store(binding(), generate_mock_voice_wav(), generation_id='legacy')
    assert not legacy['audio_enc'].startswith('va1:')
    spy = AsyncMock(wraps=scoped.open)
    monkeypatch.setattr(scoped, 'open', spy)
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'kms_v1')
    with pytest.raises(ValueError): await VoiceArtifacts(db).load('w', legacy['_id'])
    spy.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['open', 'seal'])
@pytest.mark.parametrize('setting', ['OUTREACH_CUSTODY_ENVIRONMENT_ID', 'OUTREACH_KMS_ROLE_ID',
                                    'OUTREACH_CREDENTIAL_CUSTODY_MODE'])
async def test_policy_changes_during_key_work_discard_content(scoped, monkeypatch, operation, setting):
    db = Database()
    doc = await VoiceArtifacts(db).store(binding(), generate_mock_voice_wav(), generation_id='g')
    original = getattr(scoped, operation)
    async def rotate(*args):
        result = await original(*args)
        monkeypatch.setenv(setting, 'legacy_fernet' if setting.endswith('MODE') else 'replacement')
        return result
    monkeypatch.setattr(scoped, operation, rotate)
    with pytest.raises(CustodyUnavailable):
        if operation == 'open': await VoiceArtifacts(db).load('w', doc['_id'])
        else: await VoiceArtifacts(db).store(binding(), generate_mock_voice_wav(), generation_id='new')
    assert db.outreach_voice_artifacts.docs[0]['generation_id'] == 'g'


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['replace', 'scrub', 'expire', 'ciphertext'])
async def test_late_database_change_during_key_open_never_returns_old_audio(scoped, monkeypatch, change):
    db = Database()
    doc = await VoiceArtifacts(db).store(binding(), generate_mock_voice_wav(), generation_id='g')
    original = scoped.open
    async def changed(*args):
        result = await original(*args)
        row = db.outreach_voice_artifacts.docs[0]
        if change == 'replace': row['generation_id'] = 'new'
        elif change == 'scrub': row.pop('audio_enc'); row['status'] = 'failed'
        elif change == 'expire': row['expires_at'] = datetime.now(timezone.utc) - timedelta(seconds=1)
        else: row['audio_enc'] += 'bad'
        return result
    monkeypatch.setattr(scoped, 'open', changed)
    with pytest.raises(CustodyUnavailable): await VoiceArtifacts(db).load('w', doc['_id'])


@pytest.mark.asyncio
async def test_prepared_clip_checks_exact_content_and_config_without_key_work(scoped, monkeypatch):
    db = Database()
    doc = await VoiceArtifacts(db).store(binding(), generate_mock_voice_wav(), generation_id='g')
    clip = await VoiceArtifacts(db).prepare_load('w', doc['_id'])
    monkeypatch.setattr(scoped, 'open', AsyncMock(side_effect=AssertionError('No second open')))
    assert clip.matches({**doc, 'dispatch_fence_revision': 10})
    assert not clip.matches({**doc, 'generation_id': 'new'})
    assert not replace(clip, audio=b'bad').matches(doc)
    assert not clip.matches(doc, now=doc['expires_at'])
    monkeypatch.setenv('OUTREACH_KMS_REGION', 'changed')
    assert not clip.matches(doc)


@pytest.mark.asyncio
@pytest.mark.parametrize('wrapper', ['suppression', 'authority'])
@pytest.mark.parametrize('operation', ['store', 'load'])
async def test_scoped_key_work_rejected_inside_database_wrappers(scoped, monkeypatch, wrapper, operation):
    from outreach.core.suppression import SuppressionDatabase
    from outreach.core.dispatch_authority import AuthorityDatabase
    db = Database()
    doc = await VoiceArtifacts(db).store(binding(), generate_mock_voice_wav(), generation_id='g')
    current = SuppressionDatabase(db, 'w', None) if wrapper == 'suppression' else AuthorityDatabase(db, None, 'request')
    for name in ('open', 'seal'):
        monkeypatch.setattr(scoped, name, AsyncMock(side_effect=AssertionError('No KMS in transaction')))
    with pytest.raises(CustodyUnavailable):
        if operation == 'store': await VoiceArtifacts(current).store(binding(), generate_mock_voice_wav())
        else: await VoiceArtifacts(current).load('w', doc['_id'])


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', [b'', b'RIFF', b'x' * 1920045, 'plaintext'])
async def test_invalid_audio_never_seals_or_writes(scoped, monkeypatch, bad):
    db = Database()
    spy = AsyncMock(wraps=scoped.seal)
    monkeypatch.setattr(scoped, 'seal', spy)
    with pytest.raises(ValueError): await VoiceArtifacts(db).store(binding(), bad)
    spy.assert_not_awaited()
    assert not db.outreach_voice_artifacts.docs


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['', 'plaintext', 'va1:{}', 'va1:' + 'x' * 2800000])
async def test_invalid_ciphertext_is_bounded_and_sanitized_before_kms(scoped, monkeypatch, bad):
    db = Database()
    doc = await VoiceArtifacts(db).store(binding(), generate_mock_voice_wav(), generation_id='g')
    db.outreach_voice_artifacts.docs[0]['audio_enc'] = bad
    spy = AsyncMock(wraps=scoped.open)
    monkeypatch.setattr(scoped, 'open', spy)
    with pytest.raises(ValueError) as raised: await VoiceArtifacts(db).load('w', doc['_id'])
    assert 'plaintext' not in str(raised.value)
    spy.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['legacy_fernet', 'kms_v1'])
async def test_valid_sixty_second_recording_round_trips_in_both_formats(scoped, monkeypatch, mode):
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', mode)
    db = Database()
    audio = generate_mock_voice_wav(duration_s=60)
    doc = await VoiceArtifacts(db).store(binding(), audio, generation_id='maximum')
    assert doc['duration_ms'] == 60000
    assert await VoiceArtifacts(db).load('w', doc['_id']) == audio


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['prepared_at', 'expires_at'])
async def test_scoped_timestamps_have_exact_bson_precision(scoped, field):
    db = Database()
    doc = await VoiceArtifacts(db).store(binding(), generate_mock_voice_wav(), generation_id='g')
    db.outreach_voice_artifacts.docs[0][field] += timedelta(microseconds=1)
    with pytest.raises(ValueError): await VoiceArtifacts(db).load('w', doc['_id'])


@pytest.mark.asyncio
async def test_duplicate_envelope_fields_deny_before_key_access(scoped, monkeypatch):
    import json
    db = Database()
    doc = await VoiceArtifacts(db).store(binding(), generate_mock_voice_wav(), generation_id='g')
    value = doc['audio_enc'][4:]
    data = json.loads(value)
    db.outreach_voice_artifacts.docs[0]['audio_enc'] = 'va1:' + '{"key":' + json.dumps(data['key']) + ',' + value[1:]
    spy = AsyncMock(wraps=scoped.open)
    monkeypatch.setattr(scoped, 'open', spy)
    with pytest.raises(ValueError): await VoiceArtifacts(db).load('w', doc['_id'])
    spy.assert_not_awaited()
