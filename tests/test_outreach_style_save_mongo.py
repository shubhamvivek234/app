"""Actual transaction default selection and rollback; no model/provider requests."""
import asyncio
import os
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from pymongo.errors import OperationFailure
from outreach.api import styles
from outreach.core.suppression import SuppressionCollection, guard_scope
from tests.outreach_native import replica_server, replica_db  # noqa: F401
from tests.test_outreach_lead_workspace_scope_mongo import mongo_server, real_db  # noqa: F401
pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch, pytest.mark.skipif(
    os.getenv('OUTREACH_TEST_LOCAL_MONGO') != '1', reason='Owned native Mongo is opt-in')]
USER = {'user_id': 'actor', 'default_workspace_id': 'workspace'}

@pytest.fixture(autouse=True)
def synthetic_analysis(monkeypatch):
    monkeypatch.setattr(styles.free_llm, 'generate_text', AsyncMock(return_value=('Use exact observed tone.', '', '')))

async def create(db, name):
    return await styles.create_writing_style(styles.CreateWritingStyleRequest(name=name, sample_posts=['Real sample'], is_default=True), current_user=USER, db=db)

async def test_default_save_rolls_back_if_insert_fails(replica_db, monkeypatch):
    row = {'workspace_id': 'workspace', 'id': 'original', 'is_default': True}
    await replica_db.outreach_writing_styles.insert_one(row)
    insert = SuppressionCollection.insert_one
    async def fail(self, doc, **kwargs):
        if self.collection.name == 'outreach_writing_styles': raise OperationFailure('Synthetic rejected insert')
        return await insert(self, doc, **kwargs)
    monkeypatch.setattr(SuppressionCollection, 'insert_one', fail)
    with pytest.raises(HTTPException) as exc: await create(replica_db, 'Replacement')
    assert exc.value.status_code == 503
    rows = await replica_db.outreach_writing_styles.find({}).to_list(None)
    assert len(rows) == 1 and rows[0]['is_default'] is True

async def test_concurrent_default_saves_leave_exactly_one_current_default(replica_db):
    first, second = await asyncio.gather(create(replica_db, 'First'), create(replica_db, 'Second'))
    assert first['id'] != second['id']
    rows = await replica_db.outreach_writing_styles.find({'workspace_id': 'workspace'}).to_list(None)
    assert len(rows) == 2 and sum(row['is_default'] for row in rows) == 1
    assert all(row['analysis_source'] == 'sample_analysis' for row in rows)

async def test_erased_workspace_cannot_save_style_after_analysis(replica_db):
    await replica_db.outreach_suppression_guards.insert_one({**guard_scope('workspace'), 'erasure_state': 'stopped'})
    with pytest.raises(HTTPException) as exc: await create(replica_db, 'Blocked')
    assert exc.value.status_code == 503
    assert await replica_db.outreach_writing_styles.count_documents({}) == 0

async def test_standalone_database_cannot_partially_clear_default(real_db):
    await real_db.outreach_writing_styles.insert_one({'workspace_id': 'workspace', 'id': 'original', 'is_default': True})
    with pytest.raises(HTTPException) as exc: await create(real_db, 'Blocked')
    assert exc.value.status_code == 503
    assert (await real_db.outreach_writing_styles.find_one({'id': 'original'}))['is_default'] is True
    assert await real_db.outreach_writing_styles.count_documents({}) == 1
