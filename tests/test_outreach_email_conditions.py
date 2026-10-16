"""Stored usable-email policy is conservative and does not attest delivery."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from outreach.core.email_conditions import evaluate


@pytest.mark.asyncio
@pytest.mark.parametrize('fields,met,reason', [
    ({}, False, 'address_absent'),
    ({'email': None}, False, 'address_absent'),
    ({'email': '  '}, False, 'address_absent'),
    ({'email': 'bad'}, False, 'address_invalid'),
    ({'email': ' Person@Example.test '}, True, 'policy_available'),
    ({'email': 'a@example.test', 'email_verification_status': 'valid'}, True, 'policy_available'),
    ({'email': 'a@example.test', 'email_verification_status': 'not_verified'}, True, 'policy_available'),
    ({'email': 'a@example.test', 'email_verification_status': 'unknown'}, False, 'verification_restricted'),
    ({'email': 'a@example.test', 'email_verification_status': 'invalid'}, False, 'verification_restricted'),
    ({'email': 'a@example.test', 'email_verification_status': 'accept_all'}, False, 'verification_restricted'),
    ({'email': 'a@example.test', 'email_verification_status': 'disposable'}, False, 'verification_restricted'),
    ({'email': 'a@example.test', 'email_opted_out': True}, False, 'email_opted_out'),
    ({'email': 'a@example.test', 'email_verification_status': 'typo'}, None, 'policy_unavailable'),
    ({'email': 'a@example.test', 'email_verification_status': []}, None, 'policy_unavailable'),
    ({'email': 'a@example.test', 'email_opted_out': 'false'}, None, 'policy_unavailable'),
    ({'email': []}, None, 'address_unavailable'),
    ({'email': False}, None, 'address_unavailable'),
])
async def test_stored_policy(fields, met, reason):
    db = MagicMock()
    db.outreach_email_suppressions.find_one = AsyncMock(return_value=None)
    assert await evaluate(db, 'workspace', fields) == {'condition_met': met, 'reason': reason}
    if met:
        db.outreach_email_suppressions.find_one.assert_awaited_once_with(
            {'workspace_id': 'workspace', 'email': 'person@example.test' if 'Person' in fields['email'] else 'a@example.test'}, {'_id': 1})


@pytest.mark.asyncio
async def test_current_suppression_denies_available_without_copying_address():
    db = MagicMock()
    db.outreach_email_suppressions.find_one = AsyncMock(return_value={'_id': 'suppressed'})
    result = await evaluate(db, 'workspace', {'email': 'private@example.test'})
    assert result == {'condition_met': False, 'reason': 'email_suppressed'}
    assert 'private' not in str(result)
