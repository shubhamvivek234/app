"""Strict historical references and plaintext response contracts."""
from bson import Code
from cryptography.fernet import Fernet
from fastapi import HTTPException
import pytest

from outreach.core import template_snapshot_reads as reads
from outreach.core import template_metadata_snapshots as metadata, template_graph_snapshots as graphs
from tests.test_outreach_template_graph_snapshots import source, NOW
from utils import encryption
from outreach.core.suppression import SuppressionDatabase


@pytest.fixture(autouse=True)
def owned_key(monkeypatch):
    monkeypatch.setattr(encryption, '_fernet', Fernet(Fernet.generate_key()))


def pair():
    row, checkpoint = source()
    return row, checkpoint, metadata.seal(row, checkpoint, 'actor', NOW), graphs.seal(row, checkpoint, 'actor', NOW)


def test_response_contains_exact_allowlisted_pair_and_distinct_audits():
    row, checkpoint, meta, graph = pair()
    result = reads.content_payload(checkpoint, 'a'*64, False, meta, graph)
    assert result['metadata'] == {key: row[key] for key in ('name', 'description')}
    assert result['graph'] == {key: row[key] for key in ('nodes', 'edges', 'tree')}
    assert result['status'] == 'available' and result['revision'] == checkpoint['revision']
    assert result['snapshot_audit']['metadata']['snapshot_id'] == meta['_id']
    assert result['snapshot_audit']['graph']['snapshot_id'] == graph['_id']
    assert result['capture_complete'] is result['restore_available'] is result['execution_authorized'] is False
    assert not {'ciphertext', 'firebase_uid', 'user_id', 'future_private_field', 'compiled_dag'} & result.keys()
    assert 'never copy this' not in reads.canonical_json(result)


@pytest.mark.parametrize('kind', ['metadata', 'graph'])
@pytest.mark.parametrize('fault', ['ciphertext', 'native_identity', 'revision', 'checkpoint', 'kind', 'extra', 'audit_alias'])
def test_payload_rejects_corrupt_or_transplanted_selected_kind(kind, fault):
    _, checkpoint, meta, graph = pair()
    selected = meta if kind == 'metadata' else graph
    if fault == 'ciphertext': selected['ciphertext'] = 'private-secret'
    elif fault == 'native_identity': selected['identity_digest'] = 'b'*64
    elif fault == 'revision': selected['revision'] = True
    elif fault == 'checkpoint': selected['checkpoint_id'] = 'b'*64
    elif fault == 'kind': selected['content_kind'] = 'template_graph_v1' if kind == 'metadata' else 'template_metadata_v1'
    elif fault == 'extra': selected['private_extra'] = 'private-secret'
    else: selected['recorded_by'] = Code('actor')
    with pytest.raises(HTTPException) as caught:
        reads.content_payload(checkpoint, 'a'*64, False, meta, graph)
    assert caught.value.status_code == 409 and 'private-secret' not in str(caught.value.detail)


@pytest.mark.parametrize('field,value', [('identity', 'bad'), ('checkpoint_id', 'A'*64),
    ('history_digest', Code('a'*64)), ('template_id', 'tpl_builtin'), ('identity', ['a'*64])])
def test_reference_requires_original_plain_ids_and_hashes(field, value):
    args = dict(workspace='workspace', actor='actor', uid='uid', template_id='tpl_custom_012345abcd',
        identity='a'*64, checkpoint_id='b'*64, history_digest='c'*64)
    args[field] = value
    with pytest.raises(HTTPException) as caught:
        reads.validate_reference(**args)
    assert caught.value.status_code == 422


@pytest.mark.parametrize('value', [None, 'false', 'true ', 'TRUE', '1', 'invalid'])
def test_read_setting_never_enables_implicitly(monkeypatch, value):
    monkeypatch.delenv(reads.SETTING, raising=False)
    if value is not None: monkeypatch.setenv(reads.SETTING, value)
    with pytest.raises(HTTPException) as caught: reads.require_enabled()
    assert caught.value.status_code == 503


def test_response_byte_limit_holds_without_partial_content(monkeypatch):
    _, checkpoint, meta, graph = pair()
    monkeypatch.setattr(reads, 'MAX_RESPONSE_BYTES', 1)
    with pytest.raises(HTTPException) as caught:
        reads.content_payload(checkpoint, 'a'*64, False, meta, graph)
    assert caught.value.status_code == 409


def test_distinct_legitimate_capture_times_and_actors_are_not_an_atomic_capture_claim():
    row, checkpoint, meta, _ = pair()
    other = graphs.seal(row, checkpoint, 'other-editor', NOW.replace(second=1))
    result = reads.content_payload(checkpoint, 'a'*64, True, meta, other)
    assert result['snapshot_audit']['metadata']['recorded_by'] == 'actor'
    assert result['snapshot_audit']['graph']['recorded_by'] == 'other-editor'
    assert result['terminal_recorded'] is True and result['capture_complete'] is False


@pytest.mark.asyncio
async def test_nested_wrapper_never_enters_mutator_or_decryption(monkeypatch):
    monkeypatch.setenv(reads.SETTING, 'true')
    entered = []
    async def forbidden(*args):
        entered.append(True)
        raise AssertionError('Reader must own its commit')
    monkeypatch.setattr(reads, 'mutate_suppression', forbidden)
    with pytest.raises(HTTPException) as caught:
        await reads.read_content(SuppressionDatabase(None, 'workspace', None), 'workspace', 'actor', 'uid',
            'tpl_custom_012345abcd', 'a'*64, 'b'*64, 'c'*64)
    assert caught.value.status_code == 503
    assert entered == []


def test_exact_configured_response_byte_boundary_accepts_then_holds(monkeypatch):
    _, checkpoint, meta, graph = pair()
    result = reads.content_payload(checkpoint, 'a'*64, False, meta, graph)
    size = len(reads.canonical_json(result).encode('utf-8'))
    monkeypatch.setattr(reads, 'MAX_RESPONSE_BYTES', size)
    assert reads.content_payload(checkpoint, 'a'*64, False, meta, graph) == result
    monkeypatch.setattr(reads, 'MAX_RESPONSE_BYTES', size - 1)
    with pytest.raises(HTTPException) as caught:
        reads.content_payload(checkpoint, 'a'*64, False, meta, graph)
    assert caught.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['missing_identity', 'missing_history', 'duplicate_identity',
    'duplicate_history', 'auth', 'dependency', 'bad_checkpoint'])
async def test_route_early_errors_are_private_and_never_enter_reader(monkeypatch, fault):
    from fastapi import FastAPI
    import httpx
    from api.deps import get_current_user
    from db.mongo import get_db
    from outreach.api.sequences import router
    entered = []
    async def forbidden(*args):
        entered.append(True)
        raise AssertionError('Invalid request reached reader')
    monkeypatch.setattr(reads, 'read_content', forbidden)
    app = FastAPI(); app.include_router(router)
    def actor():
        if fault == 'auth': raise HTTPException(401, 'Sign in', headers={'WWW-Authenticate': 'Bearer'})
        return {'user_id': 'actor', 'firebase_uid': 'uid', 'default_workspace_id': 'workspace'}
    def database():
        if fault == 'dependency': raise RuntimeError('private-secret')
        return None
    app.dependency_overrides[get_current_user] = actor
    app.dependency_overrides[get_db] = database
    params = [('identity_digest', 'a'*64), ('history_digest', 'b'*64)]
    if fault.startswith('missing_'): params = [p for p in params if p[0] != fault[8:]+'_digest']
    if fault.startswith('duplicate_'): params.append((fault[10:]+'_digest', 'c'*64))
    checkpoint = 'bad' if fault == 'bad_checkpoint' else 'c'*64
    # Malformed references belong to the real reader's validation boundary.
    if fault == 'bad_checkpoint': monkeypatch.undo()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        result = await client.get('/sequences/templates/tpl_custom_012345abcd/revision-checkpoints/'+checkpoint+'/content', params=params)
    assert result.status_code == (401 if fault == 'auth' else 503 if fault == 'dependency' else 422)
    assert all(result.headers[key] == value for key, value in reads.RESPONSE_HEADERS.items())
    assert 'private-secret' not in result.text and entered == []
    if fault == 'auth': assert result.headers['www-authenticate'] == 'Bearer'
