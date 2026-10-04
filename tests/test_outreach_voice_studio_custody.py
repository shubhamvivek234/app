"""Studio envelopes are bound to workspace/job/content/purpose."""
import pytest
from outreach.core.voice_studio_custody import seal_blob, open_blob
from outreach.core.credential_custody import CustodyUnavailable
from tests.test_outreach_session_custody import scoped


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['input', 'result'])
async def test_scoped_blob_and_cross_scope_denial(scoped, kind):
    job = {'_id': 'job', 'workspace_id': 'w', 'payload_digest': 'binding'}
    sealed = await seal_blob(b'private-content', job, kind)
    assert await open_blob(sealed, job, kind) == b'private-content'
    for field in ('_id', 'workspace_id', 'payload_digest'):
        with pytest.raises(CustodyUnavailable): await open_blob(sealed, {**job, field: 'other'}, kind)
    with pytest.raises(CustodyUnavailable): await open_blob(sealed, job, 'result' if kind == 'input' else 'input')
    with pytest.raises(CustodyUnavailable): await open_blob(sealed[:-3] + 'bad', job, kind)


@pytest.mark.asyncio
async def test_downgrade_and_bounds(scoped, monkeypatch):
    job = {'_id': 'job', 'workspace_id': 'w', 'payload_digest': 'binding'}
    sealed = await seal_blob(b'private', job, 'input')
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    with pytest.raises(CustodyUnavailable): await open_blob(sealed, job, 'input')
    for value in (b'', b'x' * 2000001, 'plaintext'):
        with pytest.raises(CustodyUnavailable): await seal_blob(value, job, 'input')
    for value in ('', 'plaintext', 'x' * 4000001):
        with pytest.raises(CustodyUnavailable): await open_blob(value, job, 'input')
    legacy = await seal_blob(b'private', job, 'input')
    assert await open_blob(legacy, job, 'input') == b'private'
    with pytest.raises(CustodyUnavailable): await open_blob(legacy, {**job, 'payload_digest': 'changed'}, 'input')
