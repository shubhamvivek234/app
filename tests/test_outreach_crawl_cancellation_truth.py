from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from outreach.api.leads import cancel_import_job
from tests.outreach_memory import Database
pytestmark = [pytest.mark.asyncio, pytest.mark.atomic_dispatch]
USER = {'user_id': 'actor', 'default_workspace_id': 'workspace'}

@pytest.mark.parametrize('change', [{'lease_token': 'replacement'}, {'status': 'completed'}, {'status': 'failed'}])
async def test_cancellation_does_not_overwrite_new_owner_or_terminal_outcome(change):
    db = Database(outreach_import_jobs=[{'id': 'job', 'workspace_id': 'workspace', 'status': 'crawling', 'lease_token': 'original'}])
    update = db.outreach_import_jobs.update_one
    async def race(query, patch):
        db.outreach_import_jobs.docs[0].update(change)
        return await update(query, patch)
    db.outreach_import_jobs.update_one = race
    if 'lease_token' in change:
        with pytest.raises(HTTPException) as exc: await cancel_import_job('job', current_user=USER, db=db)
        assert exc.value.status_code == 409
    else:
        assert (await cancel_import_job('job', current_user=USER, db=db))['status'] == change['status']
    assert db.outreach_import_jobs.docs[0].get('stop_reason') is None

async def test_stop_is_idempotent_and_retains_original_completion_time():
    db = Database(outreach_import_jobs=[{'id': 'job', 'workspace_id': 'workspace', 'status': 'crawling'}])
    assert (await cancel_import_job('job', current_user=USER, db=db))['status'] == 'stopped'
    completed = db.outreach_import_jobs.docs[0]['completed_at']
    assert (await cancel_import_job('job', current_user=USER, db=db))['status'] == 'stopped'
    assert db.outreach_import_jobs.docs[0]['completed_at'] == completed
