"""Current stored usable-email policy for guarded condition decisions.

Missing verification remains compatible with provided addresses. This is a
policy check, not a provider lookup, authentication or delivery attestation.
"""
from typing import Any

from outreach.core.email_finder import normalize_email

POLICY_VERSION = 1
RESTRICTED = ('invalid', 'unknown', 'accept_all', 'disposable')
ALLOWED = (None, '', 'not_verified', 'valid')


async def evaluate(db: Any, workspace_id: str, lead: dict[str, Any]) -> dict[str, Any]:
    """Read suppression in the caller's transaction; return codes only."""
    address = lead.get('email')
    if address is not None and not isinstance(address, str):
        return {'condition_met': None, 'reason': 'address_unavailable'}
    verification, opted_out = lead.get('email_verification_status'), lead.get('email_opted_out')
    if (verification is not None and not isinstance(verification, str)
            or verification not in ALLOWED + RESTRICTED
            or opted_out is not None and type(opted_out) is not bool):
        return {'condition_met': None, 'reason': 'policy_unavailable'}
    if not address or not address.strip():
        return {'condition_met': False, 'reason': 'address_absent'}
    email = normalize_email(address)
    if not email:
        return {'condition_met': False, 'reason': 'address_invalid'}
    if verification in RESTRICTED:
        return {'condition_met': False, 'reason': 'verification_restricted'}
    if opted_out is True:
        return {'condition_met': False, 'reason': 'email_opted_out'}
    suppressed = await db.outreach_email_suppressions.find_one(
        {'workspace_id': workspace_id, 'email': email}, {'_id': 1})
    return {'condition_met': not bool(suppressed),
        'reason': 'email_suppressed' if suppressed else 'policy_available'}
