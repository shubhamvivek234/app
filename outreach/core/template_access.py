"""Read-only workspace template access observations, never mutation authority.

Reads are sequential and may become stale. Existing transactional mutation
guards must still recheck current role, UID, erasure and original native proof.
No authority counters, sharing settings, ownership records or grants are written.
An optional caller-owned session binds every observation to its snapshot; the
history caller separately writes authority counters in that same transaction.
"""
import logging
logger = logging.getLogger(__name__)
from typing import Any

from fastapi import HTTPException

from outreach.core.authorization import canonical_hash
from outreach.core.erasure import workspace_is_open
from outreach.core.suppression import guard_scope
from outreach.core.template_governance import review_scope
from outreach.core.workspace_scope import workspace_scope
from utils.roles import has_permission


def _same_text(value: Any, expected: str) -> bool:
    return type(value) is str and value == expected


def _active(row: dict) -> bool:
    return _same_text(row.get('status', 'active'), 'active')


async def inspect_access(db: Any, workspace: str, actor: str, authenticated_uid: str, *, session: Any = None) -> dict:
    if any(type(value) is not str for value in (workspace, actor, authenticated_uid)):
        raise HTTPException(403, 'Template access is unavailable')
    review_scope(workspace, actor, authenticated_uid)
    options = {'session': session} if session is not None else {}

    async def rows(collection, query):
        return await collection.find(query, **options).limit(2).to_list(2)

    def deny():
        raise HTTPException(403, 'Template access is unavailable')

    users = await rows(db.users, {'user_id': actor})
    if len(users) != 1:
        deny()
    user = users[0]
    if (not _same_text(user.get('user_id'), actor) or not _same_text(user.get('firebase_uid'), authenticated_uid)
            or not _active(user)):
        deny()
    identities = await rows(db.users, {'firebase_uid': authenticated_uid})
    if (len(identities) != 1 or identities[0].get('_id') != user.get('_id')
            or not _same_text(identities[0].get('firebase_uid'), authenticated_uid)
            or not _same_text(identities[0].get('user_id'), actor) or not _active(identities[0])):
        deny()
    if await db.account_erasure_tombstones.find_one({'_id': canonical_hash(['firebase_identity', authenticated_uid])}, **options):
        deny()
    if session is None:
        opened = await workspace_is_open(db, workspace)
    else:
        guard = await db.outreach_suppression_guards.find_one(guard_scope(workspace), **options)
        opened = not guard or not guard.get('erasure_state')
    if not opened:
        raise HTTPException(409, 'This workspace is closed for data deletion.')
    members = await rows(db.workspace_members, {**workspace_scope(workspace), 'user_id': actor})
    if len(members) > 1:
        deny()
    if members:
        member = members[0]
        if (not _same_text(member.get('workspace_id'), workspace) or not _same_text(member.get('user_id'), actor)
                or not _active(member)):
            deny()
        role = member.get('role')
    else:
        owners = await rows(db.workspaces, workspace_scope(workspace))
        if (len(owners) != 1 or not _same_text(owners[0].get('workspace_id'), workspace)
                or not _same_text(owners[0].get('owner_id'), actor) or not _active(owners[0])):
            deny()
        role = 'owner'
    try:
        if type(role) is not str or not has_permission(role, 'sequence:read'):
            deny()
        return {'contract_version': 1, 'workspace_id': workspace,
            'can_configure': has_permission(role, 'campaign:create') and has_permission(role, 'sequence:update'),
            'can_edit': has_permission(role, 'sequence:update'),
            'can_delete': has_permission(role, 'sequence:delete'), 'execution_authorized': False}
    except (ValueError, TypeError, KeyError):
        deny()


def describe_access(access: dict, row: dict, *, custom: bool, actor: str) -> dict:
    return {**access, 'visibility': 'workspace' if custom else 'builtin',
        'created_by_you': custom and _same_text(row.get('user_id'), actor),
        'can_edit': custom and access['can_edit'], 'can_delete': custom and access['can_delete']}
