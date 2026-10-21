"""Bound current import requests to an exact campaign, without granting access.

The permission/erasure dependency remains authoritative. These are request
admission observations, not distributed in-flight revocation or replay receipts.
"""
from dataclasses import dataclass

from bson import ObjectId
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from outreach.core.authorization import canonical_hash
from outreach.core.workspace_scope import workspace_scope


def _plain_id(value) -> bool:
    return type(value) is str and bool(value.strip()) and len(value) <= 200


def _native(value) -> tuple[str, str]:
    if type(value) is ObjectId:
        return ('objectid', str(value))
    if _plain_id(value):
        return ('string', value)
    raise HTTPException(503, 'Campaign identity needs review before importing')


@dataclass(frozen=True)
class ImportScope:
    workspace: str
    actor: str
    uid: str
    campaign: str
    native: tuple[str, str]
    digest: str

    @property
    def public(self) -> dict:
        return {'contract_version': 1, 'workspace_id': self.workspace,
                'campaign_id': self.campaign, 'scope_digest': self.digest}


def check_campaign_scope(scope: ImportScope, campaign: dict) -> None:
    deleted = campaign.get('is_deleted') if type(campaign) is dict else None
    if (type(campaign) is not dict or type(campaign.get('id')) is not str
            or campaign['id'] != scope.campaign
            or type(campaign.get('workspace_id')) is not str
            or campaign['workspace_id'] != scope.workspace
            or deleted is not None and (type(deleted) is not bool or deleted)
            or _native(campaign.get('_id')) != scope.native):
        raise HTTPException(409, 'Import campaign changed; close and review it again')


async def capture_import_scope(db, user: dict, campaign_id: str) -> ImportScope:
    values = [user.get(key) for key in ('default_workspace_id', 'user_id', 'firebase_uid')]
    if not all(_plain_id(value) for value in [*values, campaign_id]):
        raise HTTPException(503, 'Current import context is unavailable; sign in again')
    workspace, actor, uid = values
    rows = await db.outreach_campaigns.find({'id': campaign_id, **workspace_scope(workspace),
        'is_deleted': {'$ne': True}}, {'_id': 1, 'id': 1, 'workspace_id': 1, 'is_deleted': 1}).limit(2).to_list(2)
    if not rows:
        raise HTTPException(404, 'Campaign not found')
    if len(rows) != 1:
        raise HTTPException(409, 'Campaign identity is ambiguous; contact support')
    row = rows[0]
    native = _native(row.get('_id'))
    digest = canonical_hash(['lead-import-context', 1, workspace, actor, uid, campaign_id, list(native)])
    result = ImportScope(workspace, actor, uid, campaign_id, native, digest)
    check_campaign_scope(result, row)
    return result


async def verify_import_scope(db, user: dict, campaign_id: str, digest: str | None) -> ImportScope | None:
    if digest is None:
        return None  # Existing unscoped callers retain their earlier contract.
    scope = await capture_import_scope(db, user, campaign_id)
    if type(digest) is not str or digest != scope.digest:
        raise HTTPException(409, 'Import workspace or account changed; close and review it again')
    return scope


def scoped_result(scope: ImportScope | None, result: dict):
    result = {key: value for key, value in result.items() if key != '_import_campaign_native'}
    if scope is None:
        return result
    return JSONResponse(jsonable_encoder({**result, 'import_context': scope.public}),
        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


def job_campaign_binding(scope: ImportScope) -> dict:
    return {'version': 1, 'kind': scope.native[0], 'value': scope.native[1]}


def check_job_scope(scope: ImportScope, job: dict) -> None:
    binding = job.get('_import_campaign_native')
    if (not _plain_id(job.get('id')) or type(job.get('workspace_id')) is not str
            or job['workspace_id'] != scope.workspace or type(job.get('campaign_id')) is not str
            or job['campaign_id'] != scope.campaign or type(binding) is not dict
            or set(binding) != {'version', 'kind', 'value'} or type(binding.get('version')) is not int
            or binding['version'] != 1 or not _plain_id(binding.get('kind'))
            or not _plain_id(binding.get('value')) or binding != job_campaign_binding(scope)):
        raise HTTPException(409, 'Original import job campaign identity needs review; do not create a replacement')
    _native(job.get('_id'))


async def import_job_scope(db, user: dict, job_id: str, digest: str | None):
    workspace = user.get('default_workspace_id') or user.get('current_workspace_id') or user.get('workspace_id')
    query = {'id': job_id, **workspace_scope(workspace)}
    if digest is None:
        return await db.outreach_import_jobs.find_one(query), None
    rows = await db.outreach_import_jobs.find(query).limit(2).to_list(2)
    if not rows:
        raise HTTPException(404, 'Import job not found')
    if len(rows) != 1 or not _plain_id(job_id) or type(rows[0].get('id')) is not str or rows[0]['id'] != job_id:
        raise HTTPException(409, 'Import job identity is ambiguous; contact support')
    job = rows[0]
    scope = await verify_import_scope(db, user, job.get('campaign_id'), digest)
    check_job_scope(scope, job)
    return job, scope
