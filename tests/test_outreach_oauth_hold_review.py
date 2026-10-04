"""Drained OAuth review stops local authority without inventing provider proof."""
from datetime import datetime, timedelta, timezone
import json
import pytest

from tests.test_outreach_mailbox_job_lifecycle import lifecycle


def seed_review(db):
    db.outreach_mailbox_connection_jobs.docs[0].update(status='review_required', exchange_state='unknown', connection_owner='old')
    db.outreach_accounts.docs.append({'workspace_id': 'w', 'id': 'a', 'status': 'active'})
    db.outreach_mailboxes.docs.append({'workspace_id': 'w', 'sender_account_id': 'a', 'status': 'active',
        'connection_job_id': 'prior', 'access_token_enc': 'private-access', 'refresh_token_enc': 'private-refresh'})
    db.outreach_campaigns.docs.append({'_id': 'campaign', 'workspace_id': 'w', 'id': 'c',
        'sender_account_ids': ['a'], 'status': 'active', 'authorization_revision': 4})


@pytest.mark.asyncio
async def test_review_stop_preserves_unknown_and_closes_only_after_stop(lifecycle, monkeypatch):
    from outreach.core.oauth_hold_review import OAuthHoldReview
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
    seed_review(lifecycle)
    service = OAuthHoldReview(lifecycle)
    view = await service.inspect('w', 'job')
    assert 'private-' not in json.dumps(view, default=str)
    result = await service.stop('w', 'job', 'operator', 'All OAuth and sender writers were drained for local stop.',
        expected_digest=view['review_digest'], workers_drained=True)
    assert result['status'] == 'review_stopped'
    job = lifecycle.outreach_mailbox_connection_jobs.docs[0]
    assert job['exchange_state'] == 'unknown' and job['review']['provenance'] == 'operator_local_stop'
    assert job['review']['provider_revocation_verified'] is False
    assert not job.get('authorization_code_enc') and not job.get('code_verifier_enc')
    assert lifecycle.outreach_accounts.docs[0]['status'] == 'paused'
    assert lifecycle.outreach_campaigns.docs[0]['status'] == 'paused'
    assert lifecycle.outreach_campaigns.docs[0]['authorization_revision'] == 5
    assert lifecycle.outreach_sender_execution.docs[0]['permission']['latched'] is True
    assert not lifecycle.outreach_mailboxes.docs[0].get('access_token_enc')
    assert await service.stop('w', 'job', 'operator', 'All OAuth and sender writers were drained for local stop.',
        expected_digest=view['review_digest'], workers_drained=True) == result


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['mailbox', 'owner', 'campaign', 'fresh_lease', 'other_job'])
async def test_review_denies_changed_snapshot_and_preserves_material(lifecycle, monkeypatch, change):
    from outreach.core.oauth_hold_review import OAuthHoldReview
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', 'false')
    seed_review(lifecycle)
    service = OAuthHoldReview(lifecycle)
    view = await service.inspect('w', 'job')
    if change == 'mailbox': lifecycle.outreach_mailboxes.docs[0]['connection_job_id'] = 'replacement'
    if change == 'owner': lifecycle.outreach_mailbox_connection_jobs.docs[0]['connection_owner'] = 'replacement'
    if change == 'campaign': lifecycle.outreach_campaigns.docs[0]['authorization_revision'] += 1
    if change == 'fresh_lease': lifecycle.outreach_mailbox_connection_jobs.docs[0]['lease_until'] = datetime.now(timezone.utc) + timedelta(minutes=1)
    if change == 'other_job': lifecycle.outreach_mailbox_connection_jobs.docs.append({
        'id': 'replacement', 'workspace_id': 'w', 'sender_account_id': 'a', 'status': 'queued'})
    with pytest.raises(ValueError):
        await service.stop('w', 'job', 'operator', 'All OAuth and sender writers were drained for local stop.',
            expected_digest=view['review_digest'], workers_drained=True)
    assert lifecycle.outreach_accounts.docs[0]['status'] == 'active'
    assert lifecycle.outreach_mailboxes.docs[0]['access_token_enc'] == 'private-access'


@pytest.mark.asyncio
@pytest.mark.parametrize('drained,live', [(False, 'false'), (True, 'true')])
async def test_review_requires_drain_and_disabled_live_flag(lifecycle, monkeypatch, drained, live):
    from outreach.core.oauth_hold_review import OAuthHoldReview
    monkeypatch.setenv('OUTREACH_LIVE_ACTIONS_ENABLED', live)
    seed_review(lifecycle)
    service = OAuthHoldReview(lifecycle)
    view = await service.inspect('w', 'job')
    with pytest.raises(ValueError):
        await service.stop('w', 'job', 'operator', 'All OAuth and sender writers were drained for local stop.',
            expected_digest=view['review_digest'], workers_drained=drained)


@pytest.mark.asyncio
async def test_stopped_review_api_hides_operator_evidence_and_stale_error(lifecycle):
    from outreach.api.mailboxes import get_mailbox_connection_job
    row = lifecycle.outreach_mailbox_connection_jobs.docs[0]
    row.update(status='review_stopped', error='private-old-error', review={'operator': 'private-operator', 'evidence': 'private-evidence'})
    result = await get_mailbox_connection_job('job', current_user={'default_workspace_id': 'w'}, db=lifecycle)
    assert result == {'connection_job_id': 'job', 'status': 'review_stopped',
        'error': 'Mailbox authorization was stopped after operator review.'}
