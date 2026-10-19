"""Explicit encrypted graph capture, with no HTTP/UI/automatic mutation hook.

Only version-one known graph fields are copied. Existing source documents
remain plaintext, and this codec is not a public historical-content reader.
"""
from datetime import datetime,timezone
import json
from typing import Any

from bson import BSON,Int64
from fastapi import HTTPException

from utils import encryption
from outreach.core import template_governance as governance,template_history_storage as storage
from outreach.core.authorization import canonical_hash
from outreach.core.suppression import mutate_suppression
from outreach.core.template_graph_content import project_graph
from outreach.core.template_revision_checkpoints import validate_checkpoint
from outreach.core.template_snapshot_capture import CapturePolicy,capture_reviewed,canonical_json
from outreach.core.workspace_scope import workspace_scope

COLLECTION='outreach_template_graph_snapshots'
MAX_SNAPSHOTS=100
MAX_ROW_BYTES=256*1024
MAX_TOKEN_BYTES=190000
MAX_TOTAL_BYTES=8*1024*1024
FIELDS=frozenset({'_id','contract_version','workspace_id','template_id','identity_digest','revision',
    'review_digest','checkpoint_id','recorded_by','recorded_at','content_kind','ciphertext'})


def _hold():
    raise HTTPException(409,'Template graph snapshots need review')


def snapshot_scope(workspace: str,actor: str,uid: str) -> str:
    if any(type(x) is not str for x in (workspace,actor,uid)):raise HTTPException(403,'Snapshot account or workspace changed')
    governance.review_scope(workspace,actor,uid)
    return canonical_hash(['template-graph-snapshot-scope-v1',workspace,actor,uid])


def _id(checkpoint):
    return canonical_hash(['template-graph-snapshot-v1',checkpoint['workspace_id'],checkpoint['identity_digest'],int(checkpoint['revision'])])


def _context(row):
    value={k:v for k,v in row.items() if k!='ciphertext'};value['revision']=int(value['revision'])
    value['recorded_at']=value['recorded_at'].replace(tzinfo=timezone.utc).isoformat(timespec='milliseconds')
    return value


def _validate(row,checkpoint):
    validate_checkpoint(checkpoint,checkpoint['workspace_id'],checkpoint['template_id'],checkpoint['identity_digest'],int(checkpoint['revision']))
    if (checkpoint['event']=='deleted' or type(row) is not dict or set(row)!=FIELDS
            or type(row.get('contract_version')) is not int or row['contract_version']!=1
            or type(row.get('revision')) not in {int,Int64}
            or any(type(row.get(k)) is not str or row[k]!=v for k,v in (
                ('_id',_id(checkpoint)),('workspace_id',checkpoint['workspace_id']),('template_id',checkpoint['template_id']),
                ('identity_digest',checkpoint['identity_digest']),('review_digest',checkpoint['review_digest']),
                ('checkpoint_id',checkpoint['_id']),('content_kind','template_graph_v1')))
            or row['revision']!=checkpoint['revision']
            or type(row.get('recorded_by')) is not str or not row['recorded_by'].strip() or len(row['recorded_by'])>200
            or type(row.get('recorded_at')) is not datetime or row['recorded_at'].microsecond%1000
            or row['recorded_at'].utcoffset() not in (None,timezone.utc.utcoffset(None))
            or type(row.get('ciphertext')) is not str or not 1<=len(row['ciphertext'])<=MAX_TOKEN_BYTES
            or not row['ciphertext'].isascii() or len(BSON.encode(row))>MAX_ROW_BYTES):_hold()


def seal(source: dict,checkpoint: dict,actor: str,timestamp: datetime) -> dict:
    if (type(source) is not dict or type(source.get('id')) is not str or type(source.get('workspace_id')) is not str
            or source['id']!=checkpoint.get('template_id') or source['workspace_id']!=checkpoint.get('workspace_id')):_hold()
    review=governance.template_review(source,checkpoint['workspace_id'])
    if not review['reviewable'] or any(review[k]!=checkpoint[k] for k in ('revision','identity_digest','review_digest')):_hold()
    row={'_id':_id(checkpoint),'contract_version':1,'workspace_id':checkpoint['workspace_id'],
        'template_id':checkpoint['template_id'],'identity_digest':checkpoint['identity_digest'],
        'revision':checkpoint['revision'],'review_digest':checkpoint['review_digest'],'checkpoint_id':checkpoint['_id'],
        'recorded_by':actor,'recorded_at':timestamp,'content_kind':'template_graph_v1'}
    payload={'context':_context(row),'graph':project_graph(source)}
    try:row['ciphertext']=encryption.encrypt(canonical_json(payload))
    except Exception:raise HTTPException(503,'Snapshot encryption is unavailable') from None
    _validate(row,checkpoint);return row


def open_snapshot(row: dict,checkpoint: dict) -> dict:
    """Private authenticated codec; current authority is the caller's duty."""
    _validate(row,checkpoint)
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ValueError('Duplicate key')
            result[k]=v
        return result
    try:
        raw=encryption.decrypt_strict(row['ciphertext']);payload=json.loads(raw,object_pairs_hook=pairs)
        if (type(payload) is not dict or set(payload)!={'context','graph'}
                or canonical_json(payload['context'])!=canonical_json(_context(row))
                or type(payload['graph']) is not dict or set(payload['graph'])!={'nodes','edges','tree'}
                or canonical_json(payload)!=raw):_hold()
        return project_graph(payload['graph'])
    except HTTPException:raise
    except Exception:raise HTTPException(409,'Encrypted graph snapshot is unavailable') from None


def receipt(row):
    return {'contract_version':1,'status':'recorded','snapshot_id':row['_id'],'workspace_id':row['workspace_id'],
        'template_id':row['template_id'],'identity_digest':row['identity_digest'],'revision':int(row['revision']),
        'review_digest':row['review_digest'],'execution_authorized':False}


async def prepare_storage(db: Any) -> dict:
    return await storage.prepare_index(db[COLLECTION])


async def _retained(current,workspace,identity):
    pipeline=[{'$match':{**workspace_scope(workspace),'identity_digest':identity}},{'$limit':MAX_SNAPSHOTS+1},
        {'$project':{'_id':0,'bytes':{'$bsonSize':'$$ROOT'},'row':{'$cond':[
            {'$lte':[{'$bsonSize':'$$ROOT'},MAX_ROW_BYTES]},'$$ROOT',None]}}}]
    wrapped=await current.database[COLLECTION].aggregate(pipeline,session=current.session,
        hint=storage.INDEX_NAME,collation={'locale':'simple'},maxTimeMS=2000,batchSize=25).to_list(MAX_SNAPSHOTS+1)
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


async def capture_snapshot(db: Any,workspace: str,actor: str,uid: str,template_id: str,*,
    revision: int,review_digest: str,identity_digest: str,scope_digest: str) -> dict:
    policy=CapturePolicy(COLLECTION,MAX_SNAPSHOTS,MAX_TOTAL_BYTES,snapshot_scope,_id,project_graph,
        seal,open_snapshot,receipt,_retained,'graph')
    return await capture_reviewed(policy,db,workspace,actor,uid,template_id,revision=revision,
        review_digest=review_digest,identity_digest=identity_digest,scope_digest=scope_digest,transaction=mutate_suppression)
