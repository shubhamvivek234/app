"""Bounded workspace-local identity reservations in existing sender records.

Call only within the shared workspace transaction. The account/fence is the
reservation, including stopped and uninstalled records; no identity is released
here. Old/raw writers and equivalence between different URNs are not covered.
"""
import logging
logger = logging.getLogger(__name__)
import re

MAX_WORKSPACE_SENDERS = 100


def sender_identity(value) -> str:
    """Accept one exact opaque URN, without coercion or guessed alias mapping."""
    if type(value) is not str or len(value) > 512 or not re.fullmatch(r'urn:[A-Za-z0-9:_-]+', value):
        raise ValueError('Sender identity requires review')
    return value


async def identity_owner(db, workspace: str, sender: str, urn: str) -> dict | None:
    """Return the sole native owner or deny a duplicate/ambiguous reservation.

The caller's workspace guard serializes empty reads against participating
preparations. The bounded scan also catches duplicate public IDs and malformed
array-shaped legacy authority instead of relying on Mongo scalar matching.
"""
    if any(type(value) is not str or not value or len(value) > 128 for value in (workspace, sender)):
        raise ValueError('Sender scope requires review')
    urn = sender_identity(urn)
    rows = await db.outreach_accounts.find({'workspace_id': workspace},
        {'_id': 1, 'workspace_id': 1, 'id': 1, 'linkedin_urn': 1}).limit(MAX_WORKSPACE_SENDERS + 1).to_list(MAX_WORKSPACE_SENDERS + 1)
    if len(rows) > MAX_WORKSPACE_SENDERS:
        raise ValueError('Workspace sender identity review exceeds the supported bound')
    own = []
    for row in rows:
        if (type(row.get('workspace_id')) is not str or row['workspace_id'] != workspace
                or type(row.get('id')) is not str or not row['id'] or len(row['id']) > 128):
            raise ValueError('Stored sender scope requires review')
        # An unrelated legacy row with no observed identity is not an alias
        # claim. Its eventual verified preparation must pass this same guard.
        observed = sender_identity(row['linkedin_urn']) if row.get('linkedin_urn') is not None else None
        if row['id'] == sender:
            own.append(row)
            if observed != urn:
                raise ValueError('Sender identity changed; explicit review is required')
        elif observed == urn:
            raise ValueError('Sender identity is already reserved; reconnect its original account')
    if len(own) > 1:
        raise ValueError('Duplicate native sender records require review')
    if not own and len(rows) == MAX_WORKSPACE_SENDERS:
        raise ValueError('Workspace sender identity capacity requires review')
    return own[0] if own else None
