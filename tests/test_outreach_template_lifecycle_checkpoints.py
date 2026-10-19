"""Creation/graph checkpoints retain exact event and predecessor contracts."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from bson import Code, Int64
from fastapi import HTTPException
import pytest

from outreach.core import template_revision_checkpoints as checkpoints
from outreach.core.suppression import SuppressionCollection, SuppressionDatabase
from tests.test_outreach_template_revision_checkpoints import record

NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)


def test_created_checkpoint_is_revision_one_without_invented_predecessor():
    row = record(1)
    value = checkpoints.checkpoint_for(row, 'actor', NOW, event='created')
    assert value['event'] == 'created' and value['revision'] == 1
    assert value['predecessor_revision'] is value['predecessor_review_digest'] is None
    assert len(value) == 12 and not {'name', 'description', 'nodes', 'firebase_uid'} & value.keys()
    native = checkpoints.checkpoint_for({**row, 'template_revision': Int64(1)}, 'actor', NOW, event='created')
    assert native['revision'] == 1 and native['event'] == 'created'
    # The full-record digest intentionally distinguishes BSON int32 and int64.
    assert native['identity_digest'] == value['identity_digest']
    assert native['review_digest'] != value['review_digest']


@pytest.mark.parametrize('revision', [0, 2, 2**53-1])
def test_created_cannot_relabel_existing_revision_as_creation(revision):
    with pytest.raises(HTTPException):
        checkpoints.checkpoint_for(record(revision), 'actor', NOW, event='created')


@pytest.mark.parametrize('event', ['metadata', 'graph'])
def test_linked_event_preserves_exact_original_native_digest(event):
    before = record(4); after = {**before, 'template_revision': 5, 'name': 'Changed'}
    parent = checkpoints.checkpoint_for(before, 'actor', NOW)
    value = checkpoints.checkpoint_for(after, 'actor', NOW, predecessor=before, event=event)
    assert value['event'] == event and value['predecessor_revision'] == 4
    assert value['predecessor_review_digest'] == parent['review_digest']
    assert value['review_digest'] != parent['review_digest']


@pytest.mark.parametrize('event,with_parent', [('created', True), ('observed', True),
    ('graph', False), ('metadata', False), ('deleted', False), (Code('created'), False)])
def test_event_and_parent_cannot_be_reinterpreted(event, with_parent):
    before = record(0); after = {**before, 'template_revision': 1}
    with pytest.raises(HTTPException):
        checkpoints.checkpoint_for(after, 'actor', NOW,
            predecessor=before if with_parent else None, event=event)


@pytest.mark.parametrize('event', ['created', 'graph'])
@pytest.mark.parametrize('field,value', [('predecessor_revision', True),
    ('predecessor_review_digest', 'not-a-digest'), ('recorded_at', NOW.replace(microsecond=1))])
def test_new_events_keep_strict_stored_schema(event, field, value):
    before = record(0); row = {**before, 'template_revision': 1}
    original = checkpoints.checkpoint_for(row, 'actor', NOW,
        predecessor=before if event == 'graph' else None, event=event)
    with pytest.raises(HTTPException):
        checkpoints.validate_checkpoint({**original, field: value}, 'workspace', row['id'], original['identity_digest'], 1)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['creation', 'graph'])
async def test_new_append_paths_require_active_guard_before_database_access(kind):
    db = MagicMock(); current = SuppressionDatabase(db, 'workspace', SimpleNamespace(in_transaction=False))
    before = record(0); after = {**before, 'template_revision': 1}
    with pytest.raises(HTTPException):
        if kind == 'creation':
            await checkpoints.append_creation_checkpoint(current, after, 'actor', NOW)
        else:
            await checkpoints.append_graph_checkpoints(current, before, after, 'actor', NOW)
    assert db.mock_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['metadata', 'graph'])
async def test_retained_creation_cannot_coexist_with_an_earlier_native_revision(monkeypatch, kind):
    before = record(1); after = {**before, 'template_revision': 2}
    retained = [checkpoints.checkpoint_for({**before, 'template_revision': 0}, 'actor', NOW),
        checkpoints.checkpoint_for(before, 'actor', NOW, event='created')]
    cursor = SimpleNamespace(to_list=AsyncMock(return_value=retained))
    cursor.limit = lambda _: cursor
    monkeypatch.setattr(SuppressionCollection, 'find', lambda *args, **kwargs: cursor)
    insert = AsyncMock(); monkeypatch.setattr(checkpoints, '_insert_verified', insert)
    current = SuppressionDatabase(MagicMock(), 'workspace', SimpleNamespace(in_transaction=True))
    append = checkpoints.append_metadata_checkpoints if kind == 'metadata' else checkpoints.append_graph_checkpoints
    with pytest.raises(HTTPException) as caught:
        await append(current, before, after, 'actor', NOW)
    assert caught.value.status_code == 409
    insert.assert_not_awaited()
