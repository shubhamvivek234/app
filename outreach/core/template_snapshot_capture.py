"""Shared current-proof capture transaction for trusted internal snapshot policies.

Policies and callbacks are selected by source wrappers, never request input.
Successful captures write guard/user-role counters; no execution grant follows.
"""
import logging
logger = logging.getLogger(__name__)
from dataclasses import dataclass
from datetime import datetime,timezone
import json
import re
from typing import Any,Callable

from bson import BSON,Int64,ObjectId
from fastapi import HTTPException

from outreach.core import template_governance as governance,template_history as history
from outreach.core import template_history_storage as storage
from outreach.core.lead_tags import unique_resource
from outreach.core.template_access import inspect_access
from outreach.core.workspace_scope import workspace_scope


@dataclass(frozen=True)
class CapturePolicy:
    collection: str
    max_snapshots: int
    max_total_bytes: int
    scope_fn: Callable
    identify: Callable
    project: Callable
    seal: Callable
    open_snapshot: Callable
    receipt: Callable
    load_retained: Callable
    label: str


def canonical_json(value: Any) -> str:
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'),sort_keys=True)


def _hold():
    raise HTTPException(409,'Template snapshots need review')


async def capture_reviewed(policy: CapturePolicy, db: Any, workspace: str, actor: str, uid: str,
    template_id: str, *, revision: int, review_digest: str, identity_digest: str, scope_digest: str,
    transaction: Callable) -> dict:
    """Authorize and persist inside one owning snapshot/majority transaction."""
    if scope_digest!=policy.scope_fn(workspace,actor,uid):raise HTTPException(403,'Snapshot account or workspace changed')
    if (type(template_id) is not str or not re.fullmatch(r'tpl_custom_[0-9a-f]{10}',template_id)
            or type(revision) is not int or not 0<=revision<=governance.MAX_REVISION
            or any(type(x) is not str or not re.fullmatch(r'[0-9a-f]{64}',x) for x in (review_digest,identity_digest,scope_digest))):
        raise HTTPException(422,'A current snapshot review is required')
    async def capture(current):
        await governance.authorize_update(current,actor,uid)
        await inspect_access(current.database,workspace,actor,uid,session=current.session)
        source=await unique_resource(current.outreach_templates,workspace,template_id)
        if source is None:raise HTTPException(404,'Current template is unavailable')
        if (type(source.get('_id')) not in {str,ObjectId} or any(type(source.get(k)) is not str for k in ('workspace_id','id','user_id'))):_hold()
        review=governance.template_review(source,workspace)
        if not review['reviewable'] or any(review[k]!=v for k,v in (
            ('revision',revision),('identity_digest',identity_digest),('review_digest',review_digest))):_hold()
        collection=current.database[policy.collection]
        await storage.require_history_index(collection)
        await storage.require_history_index(current.database.outreach_template_revisions)
        recorded=await history._load_rows(current,workspace,identity_digest)
        ordered,_=history.prepare_history(recorded,workspace,template_id,identity_digest)
        if any(r['event']=='deleted' or int(r['revision'])>revision for r in ordered):_hold()
        parents={int(r['revision']):r for r in ordered};checkpoint=parents.get(revision)
        if checkpoint is None or checkpoint['review_digest']!=review_digest:_hold()
        expected=canonical_json(policy.project(source))
        retained,total=await policy.load_retained(current,workspace,identity_digest)
        existing=None
        for row in retained:
            if type(row.get('revision')) not in {int,Int64} or int(row['revision']) not in parents:_hold()
            content=policy.open_snapshot(row,parents[int(row['revision'])])
            if row['_id']==policy.identify(checkpoint):
                if existing is not None or canonical_json(content)!=expected:_hold()
                existing=row
        if existing is None:
            now=datetime.now(timezone.utc);row=policy.seal(source,checkpoint,actor,now.replace(microsecond=now.microsecond//1000*1000))
            if len(retained)+1>policy.max_snapshots or total+len(BSON.encode(row))>policy.max_total_bytes:_hold()
            await current[policy.collection].insert_one(row)
            existing=await current[policy.collection].find_one({**workspace_scope(workspace),'_id':row['_id']})
            if (existing is None or BSON.encode(existing)!=BSON.encode(row)
                    or canonical_json(policy.open_snapshot(existing,checkpoint))!=expected):_hold()
        await storage.require_history_index(collection)
        await storage.require_history_index(current.database.outreach_template_revisions)
        return policy.receipt(existing)
    try:return await transaction(db,workspace,capture)
    except HTTPException:raise
    except Exception:raise HTTPException(503,'Could not confirm '+policy.label+' snapshot; review current source before retrying') from None
