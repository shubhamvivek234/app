"""Explicit encrypted metadata capture, not automatic content history or restore.

This source entry point has no HTTP/UI or mutation-path integration. Capturing
requires still-current original proof and writes authority counters plus one
immutable encrypted allowlist row. Existing templates remain plaintext.
"""
from datetime import datetime, timezone
import json
import re
from typing import Any

from bson import BSON, Int64, ObjectId
from fastapi import HTTPException

from utils import encryption
from outreach.core import template_governance as governance, template_history as history
from outreach.core import template_history_storage as storage
from outreach.core.authorization import canonical_hash
from outreach.core.lead_tags import unique_resource
from outreach.core.suppression import mutate_suppression
from outreach.core.template_access import inspect_access
from outreach.core.template_metadata import validate_metadata
from outreach.core.template_revision_checkpoints import validate_checkpoint
from outreach.core.workspace_scope import workspace_scope

COLLECTION='outreach_template_metadata_snapshots'
MAX_SNAPSHOTS=1000
MAX_ROW_BYTES=16384
MAX_TOKEN_BYTES=14000
MAX_TOTAL_BYTES=8*1024*1024
FIELDS=frozenset({'_id','contract_version','workspace_id','template_id','identity_digest','revision',
    'review_digest','checkpoint_id','recorded_by','recorded_at','content_kind','ciphertext'})


def _hold():
    raise HTTPException(409,'Template metadata snapshots need review')


def _json(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'),sort_keys=True)


def snapshot_scope(workspace: str, actor: str, uid: str) -> str:
    if any(type(x) is not str for x in (workspace,actor,uid)):
        raise HTTPException(403,'Snapshot account or workspace changed')
    governance.review_scope(workspace,actor,uid)
    return canonical_hash(['template-metadata-snapshot-scope-v1',workspace,actor,uid])


def _id(checkpoint):
    return canonical_hash(['template-metadata-snapshot-v1',checkpoint['workspace_id'],
        checkpoint['identity_digest'],int(checkpoint['revision'])])


def _context(row):
    value={k:v for k,v in row.items() if k!='ciphertext'}
    value['revision']=int(value['revision'])
    value['recorded_at']=value['recorded_at'].replace(tzinfo=timezone.utc).isoformat(timespec='milliseconds')
    return value


def _metadata(row):
    try:
        name,description=validate_metadata(row.get('name'),row.get('description'))
        return {'name':name,'description':description}
    except HTTPException:
        _hold()


def _validate(row,checkpoint):
    validate_checkpoint(checkpoint,checkpoint['workspace_id'],checkpoint['template_id'],
        checkpoint['identity_digest'],int(checkpoint['revision']))
    if (checkpoint['event']=='deleted' or type(row) is not dict or set(row)!=FIELDS
            or type(row.get('contract_version')) is not int or row['contract_version']!=1
            or type(row.get('revision')) not in {int,Int64}
            or any(type(row.get(k)) is not str or row[k]!=v for k,v in (
                ('_id',_id(checkpoint)),('workspace_id',checkpoint['workspace_id']),('template_id',checkpoint['template_id']),
                ('identity_digest',checkpoint['identity_digest']),('review_digest',checkpoint['review_digest']),
                ('checkpoint_id',checkpoint['_id']),('content_kind','template_metadata_v1')))
            or row['revision']!=checkpoint['revision']
            or type(row.get('recorded_by')) is not str or not row['recorded_by'].strip() or len(row['recorded_by'])>200
            or type(row.get('recorded_at')) is not datetime or row['recorded_at'].microsecond%1000
            or row['recorded_at'].utcoffset() not in (None,timezone.utc.utcoffset(None))
            or type(row.get('ciphertext')) is not str or not 1<=len(row['ciphertext'])<=MAX_TOKEN_BYTES
            or not row['ciphertext'].isascii() or len(BSON.encode(row))>MAX_ROW_BYTES):
        _hold()


def seal(source: dict, checkpoint: dict, actor: str, timestamp: datetime) -> dict:
    if (type(source) is not dict or type(source.get('id')) is not str
            or type(source.get('workspace_id')) is not str or source['id']!=checkpoint.get('template_id')
            or source['workspace_id']!=checkpoint.get('workspace_id')):
        _hold()
    review=governance.template_review(source,checkpoint['workspace_id'])
    if (not review['reviewable'] or any(review[k]!=checkpoint[k] for k in ('revision','identity_digest','review_digest'))):
        _hold()
    row={'_id':_id(checkpoint),'contract_version':1,'workspace_id':checkpoint['workspace_id'],
        'template_id':checkpoint['template_id'],'identity_digest':checkpoint['identity_digest'],
        'revision':checkpoint['revision'],'review_digest':checkpoint['review_digest'],'checkpoint_id':checkpoint['_id'],
        'recorded_by':actor,'recorded_at':timestamp,'content_kind':'template_metadata_v1'}
    payload={'context':_context(row),'metadata':_metadata(source)}
    try:row['ciphertext']=encryption.encrypt(_json(payload))
    except Exception:raise HTTPException(503,'Snapshot encryption is unavailable') from None
    _validate(row,checkpoint)
    return row


def open_snapshot(row: dict, checkpoint: dict) -> dict:
    """Private codec, not an authorized public historical-content read service."""
    _validate(row,checkpoint)
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ValueError('Duplicate key')
            result[k]=v
        return result
    try:
        raw=encryption.decrypt_strict(row['ciphertext'])
        payload=json.loads(raw,object_pairs_hook=pairs)
        if (type(payload) is not dict or set(payload)!={'context','metadata'} or _json(payload['context'])!=_json(_context(row))
                or type(payload['metadata']) is not dict or set(payload['metadata'])!={'name','description'}
                or _json(payload)!=raw):
            _hold()
        return _metadata(payload['metadata'])
    except HTTPException:raise
    except Exception:raise HTTPException(409,'Encrypted metadata snapshot is unavailable') from None


def receipt(row):
    return {'contract_version':1,'status':'recorded','snapshot_id':row['_id'],'workspace_id':row['workspace_id'],
        'template_id':row['template_id'],'identity_digest':row['identity_digest'],'revision':int(row['revision']),
        'review_digest':row['review_digest'],'execution_authorized':False}


async def prepare_storage(db: Any) -> dict:
    """Administrative source entry point; no startup/customer index creation."""
    return await storage.prepare_index(db[COLLECTION])


async def _retained(current,workspace,identity):
    pipeline=[{'$match':{**workspace_scope(workspace),'identity_digest':identity}},{'$limit':MAX_SNAPSHOTS+1},
        {'$project':{'_id':0,'bytes':{'$bsonSize':'$$ROOT'},'row':{'$cond':[
            {'$lte':[{'$bsonSize':'$$ROOT'},MAX_ROW_BYTES]},'$$ROOT',None]}}}]
    wrapped=await current.database[COLLECTION].aggregate(pipeline,session=current.session,
        hint=storage.INDEX_NAME,collation={'locale':'simple'},maxTimeMS=2000,batchSize=50).to_list(MAX_SNAPSHOTS+1)
    if len(wrapped)>MAX_SNAPSHOTS:_hold()
    result=[];size=0
    for value in wrapped:
        if (type(value) is not dict or set(value)!={'row','bytes'} or type(value['bytes']) not in {int,Int64}
                or not 0<value['bytes']<=MAX_ROW_BYTES or type(value['row']) is not dict
                or value['bytes']!=len(BSON.encode(value['row']))):_hold()
        size+=int(value['bytes'])
        if size>MAX_TOTAL_BYTES:_hold()
        result.append(value['row'])
    return result,size


async def capture_snapshot(db: Any, workspace: str, actor: str, uid: str, template_id: str, *,
    revision: int, review_digest: str, identity_digest: str, scope_digest: str) -> dict:
    """Capture only current reviewed metadata; no historical-result recovery."""
    if scope_digest!=snapshot_scope(workspace,actor,uid):raise HTTPException(403,'Snapshot account or workspace changed')
    if (type(template_id) is not str or not re.fullmatch(r'tpl_custom_[0-9a-f]{10}',template_id)
            or type(revision) is not int or not 0<=revision<=governance.MAX_REVISION
            or any(type(x) is not str or not re.fullmatch(r'[0-9a-f]{64}',x) for x in (review_digest,identity_digest,scope_digest))):
        raise HTTPException(422,'A current metadata snapshot review is required')
    async def capture(current):
        await governance.authorize_update(current,actor,uid)
        await inspect_access(current.database,workspace,actor,uid,session=current.session)
        source=await unique_resource(current.outreach_templates,workspace,template_id)
        if source is None:raise HTTPException(404,'Current template is unavailable')
        if (type(source.get('_id')) not in {str,ObjectId} or any(type(source.get(k)) is not str for k in ('workspace_id','id','user_id'))):_hold()
        review=governance.template_review(source,workspace)
        if not review['reviewable'] or any(review[k]!=v for k,v in (
            ('revision',revision),('identity_digest',identity_digest),('review_digest',review_digest))):_hold()
        collection=current.database[COLLECTION]
        await storage.require_history_index(collection)
        await storage.require_history_index(current.database.outreach_template_revisions)
        recorded=await history._load_rows(current,workspace,identity_digest)
        ordered,_=history.prepare_history(recorded,workspace,template_id,identity_digest)
        if any(r['event']=='deleted' or int(r['revision'])>revision for r in ordered):_hold()
        parents={int(r['revision']):r for r in ordered};checkpoint=parents.get(revision)
        if checkpoint is None or checkpoint['review_digest']!=review_digest:_hold()
        retained,total=await _retained(current,workspace,identity_digest)
        existing=None
        for row in retained:
            if type(row.get('revision')) not in {int,Int64} or int(row['revision']) not in parents:_hold()
            content=open_snapshot(row,parents[int(row['revision'])])
            if row['_id']==_id(checkpoint):
                if existing is not None or content!=_metadata(source):_hold()
                existing=row
        if existing is None:
            now=datetime.now(timezone.utc);row=seal(source,checkpoint,actor,now.replace(microsecond=now.microsecond//1000*1000))
            if len(retained)+1>MAX_SNAPSHOTS or total+len(BSON.encode(row))>MAX_TOTAL_BYTES:_hold()
            await current[COLLECTION].insert_one(row)
            existing=await current[COLLECTION].find_one({**workspace_scope(workspace),'_id':row['_id']})
            if existing is None or BSON.encode(existing)!=BSON.encode(row) or open_snapshot(existing,checkpoint)!=_metadata(source):_hold()
        await storage.require_history_index(collection)
        await storage.require_history_index(current.database.outreach_template_revisions)
        return receipt(existing)
    try:return await mutate_suppression(db,workspace,capture)
    except HTTPException:raise
    except Exception:raise HTTPException(503,'Could not confirm metadata snapshot; review current source before retrying') from None
