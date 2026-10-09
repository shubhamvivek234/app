"""Passive verified-evidence monitor and bounded operator-authorized renewal.

No probing, key opening, campaign activation or automatic latch release.
Status labels and generic HTTP success alone are not positive health proof.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import logging
from typing import Any

from outreach.core import erasure, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.execution_permission import ExecutionPermission, MAX_PERMISSION_SECONDS
from outreach.core.integration_control import reference, stable
from outreach.core.paid_access import get_active_entitlement, live_actions_enabled, _utc
from outreach.core.proxy_custody import proxy_digest
from outreach.core.proxy_migration import HEX
from outreach.core.voice_artifact_custody import policy

SOURCES = frozenset({'sequence', 'sync', 'search', 'inbox_reply', 'engage'})
FRESHNESS = timedelta(seconds=90)
INTERVAL = timedelta(seconds=30)
MAX_WINDOW_SECONDS = 900
LIMIT = 100
logger = logging.getLogger(__name__)


def now() -> datetime:
    stamp = datetime.now(timezone.utc)
    return stamp.replace(microsecond=stamp.microsecond//1000*1000)


def enabled() -> bool:
    return os.getenv('OUTREACH_HEALTH_MONITOR_ENABLED', 'false').lower() in {'true', '1'}


def runtime_enabled() -> bool:
    return enabled() and live_actions_enabled() and os.getenv('OUTREACH_MOCK_AUTH','false').lower() not in {'true','1'}


def binding(account: dict) -> str:
    return canonical_hash(stable([account.get(field) for field in ('workspace_id','id','credential_generation',
        'linkedin_urn','session_cookie_enc','jsession_id','li_a_enc')]
        + [proxy_digest(account.get('proxy') or {})]))


def connection_evidence(job_id: str, generation: str, account: dict, observed_at: datetime) -> dict:
    """Called only after existing identity parsing; monitor rechecks original proof."""
    return {'version':1, 'provenance':'verified_connection_profile', 'job_id':job_id,
        'credential_generation':generation, 'observed_at':observed_at,
        'binding_digest':binding({**account,'credential_generation':generation})}


def instant(value: Any) -> datetime | None:
    return _utc(value) if isinstance(value, datetime) and value.microsecond % 1000 == 0 else None


def evidence_valid(view: dict, stamp: datetime) -> bool:
    account, job, reads = view['account'], view['job'], view['verification_reads']
    try:
        evidence = account['execution_health']; observed = instant(evidence.get('observed_at'))
        fence = account.get('connection_finalization') or {}
        from outreach.core.connection_repair import installed_digest
        return bool(set(evidence)=={'version','provenance','job_id','credential_generation','observed_at','binding_digest'}
            and type(evidence['version']) is int and evidence['version']==1
            and evidence['provenance']=='verified_connection_profile' and observed and observed<=stamp<observed+FRESHNESS
            and evidence['credential_generation']==account['credential_generation']
            and evidence['binding_digest']==binding(account) and job and job.get('status')=='completed'
            and not job.get('repair') and job.get('id')==evidence['job_id'] and job.get('sender_id')==account['id']
            and job.get('credential_generation')==account['credential_generation']
            and job.get('expected_linkedin_urn')==account.get('linkedin_urn')
            and fence.get('job_id')==job['id'] and fence.get('generation')==account['credential_generation']
            and fence.get('state')=='closed' and fence.get('completion')=='verified_install'
            and fence.get('ever_installed') is True
            and fence.get('expected_linkedin_urn')==account.get('linkedin_urn')
            and fence.get('installed_credential_digest')==installed_digest(account)
            and account.get('session_cookie_enc') and account.get('jsession_id')
            and any(type(row.get('http_status')) is int and row['http_status']==200
                and (row.get('dispatch_authorization') or {}).get('mode')=='transaction'
                and (completed:=instant(row.get('completed_at'))) and completed<=observed<=completed+timedelta(seconds=10)
                for row in reads))
    except (KeyError, TypeError, AttributeError, ValueError):
        return False


async def controlled_permission_allowed(db: Any, authority: dict, permission: dict, stamp: datetime) -> bool:
    """Flag/control revocation denies without waiting for a scheduled tick."""
    if not runtime_enabled(): return False
    captured_policy = canonical_hash(policy())
    row = await db.outreach_health_controls.find_one({'workspace_id':authority['workspace_id'],
        'sender_id':authority['sender_id'], '_id':permission['health_control_id']})
    allowed = bool(runtime_enabled() and captured_policy==canonical_hash(policy())
        and row and row.get('status')=='armed' and instant(row.get('expires_at')) and _utc(row['expires_at'])>stamp
        and row.get('generation')==permission.get('credential_generation')
        and row.get('sources')==permission.get('sources')
        and row.get('expected_permission_revision')==authority.get('permission_revision')
        and row.get('policy_digest')==captured_policy)
    if allowed and isinstance(db, AuthorityDatabase):
        deadline = _utc(row['expires_at'])
        db.checks.append(lambda current: runtime_enabled() and canonical_hash(policy())==captured_policy and current<deadline)
    return allowed


class HealthMonitor:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def _snapshot(self, current: Any, workspace: str, sender: str) -> dict:
        account = await current.outreach_accounts.find_one({'workspace_id':workspace,'id':sender})
        asset = ((account or {}).get('proxy') or {}).get('proxy_id')
        evidence = (account or {}).get('execution_health') or {}
        state = await current.outreach_sender_execution.find_one(ExecutionPermission.scope(workspace,sender))
        inventory = await current.outreach_proxy_inventory.find_one({'workspace_id':workspace,'_id':asset})
        view = {'account':account,'state':state,'inventory':inventory,
            'job':await current.outreach_connection_jobs.find_one({'workspace_id':workspace,'id':evidence.get('job_id'),'sender_id':sender}),
            'paid':await get_active_entitlement(current,workspace),
            'lease':await current.outreach_proxy_leases.find_one({'workspace_id':workspace,'_id':asset,'sender_id':sender}),
            'slot':await current.outreach_sender_slots.find_one({'workspace_id':workspace,'sender_id':sender}),
            'lock':await current.outreach_connection_locks.find_one({'workspace_id':workspace,'_id':sender}),
            'workspace_open':await erasure.workspace_is_open(current,workspace),
            'runtime_enabled':runtime_enabled(),'policy_digest':canonical_hash(policy())}
        for key, collection, query in (
            ('verification_reads','outreach_physical_requests',{'sender_id':sender,'source':'verify',
                'credential_generation':'pending:'+str(evidence.get('job_id')),'action':'read','mutation':False,'status':'response_received'}),
            ('unknown','outreach_physical_requests',{'sender_id':sender,'status':{'$in':['in_flight','unknown_outcome']}}),
            ('intents','outreach_intents',{'sender_id':sender,'status':{'$in':['uncertain','unknown_outcome','held_outcome']}}),
            ('tasks','outreach_tasks',{'account_id':sender,'status':{'$in':['uncertain','unknown_outcome','held_outcome']}}),
            ('connections','outreach_connection_jobs',{'sender_id':sender,'status':{'$in':['queued','running','finalizing','repairing']}}),
            ('manual','outreach_manual_actions',{'account_id':sender,'$or':[{'status':{'$in':['unknown_outcome','resolving']}},
                {'status':'resolved','cleanup_complete':{'$ne':True}}]}),
            ('active_controls','outreach_health_controls',{'sender_id':sender,'status':'armed'}),
            ('campaigns','outreach_campaigns',{'sender_account_ids':sender,'status':{'$in':['active','warming_up']}})):
            view[key] = await getattr(current,collection).find({'workspace_id':workspace,**query}).sort('_id',1).limit(LIMIT+1).to_list(length=LIMIT+1)
        view['asset_proven'] = True
        if inventory and inventory.get('provider')=='webshare_plan':
            from outreach.core.webshare_provisioning import managed_webshare_valid
            view['asset_proven']=await managed_webshare_valid(current,inventory,workspace)
        return stable(view)

    @staticmethod
    def _blockers(view: dict, stamp: datetime, *, arm: bool = False) -> list[str]:
        reasons=[]; account=view['account'] or {}; state=view['state'] or {}; permission=state.get('permission') or {}
        if not view['runtime_enabled']: reasons.append('monitor_or_live_gate_disabled')
        if not view['workspace_open']: reasons.append('workspace_closed')
        if account.get('status')!='active' or account.get('is_deleted') or account.get('stop_reason'):
            reasons.append('sender_stopped')
        if not evidence_valid(view,stamp): reasons.append('fresh_original_health_evidence_required')
        if not view['paid']: reasons.append('paid_access_unavailable')
        inventory=view['inventory'] or {}; lease=view['lease'] or {}
        if (not view['asset_proven'] or inventory.get('status')!='available' or not instant(inventory.get('expires_at'))
                or _utc(inventory['expires_at'])<=stamp or inventory.get('last_workspace_id')!=account.get('workspace_id')
                or inventory.get('country_code')!=account.get('country_code')
                or inventory.get('provider') not in {'iproyal_static','webshare_plan'}
                or proxy_digest(inventory)!=proxy_digest(account.get('proxy') or {})
                or not lease or lease.get('country_code')!=account.get('country_code')
                or not view['slot']): reasons.append('assigned_proxy_unavailable_or_changed')
        sources=permission.get('sources')
        issued, expiry=instant(permission.get('issued_at')),instant(permission.get('expires_at'))
        if (permission.get('latched') is not False or permission.get('stop_reason')
                or permission.get('credential_generation')!=account.get('credential_generation')
                or not isinstance(sources,list) or not sources or any(not isinstance(value,str) or value not in SOURCES for value in sources)
                or not issued or not expiry or not issued<=stamp or not 0<(expiry-issued).total_seconds()<=60
                or arm and expiry<=stamp or type(state.get('permission_revision')) is not int): reasons.append('original_permission_unproven_or_stopped')
        live_owner = bool(instant(state.get('expires_at')) and _utc(state['expires_at'])>stamp)
        unresolved = any(row.get('status')=='unknown_outcome' or not (live_owner
            and row.get('_id')==state.get('physical_request_token') and row.get('owner_token')==state.get('owner_token'))
            for row in view['unknown'])
        if unresolved or view['intents'] or view['tasks'] or view['manual'] or view['connections'] or view['lock']:
            reasons.append('unresolved_work_requires_review')
        if any(len(view[name])>LIMIT for name in ('verification_reads','unknown','intents','tasks','manual','connections','active_controls','campaigns')):
            reasons.append('authority_capacity_exceeded')
        if state.get('status')!='idle' or state.get('owner_token') or state.get('physical_request_token'):
            reasons.append('sender_owned')
        if arm and view['active_controls']: reasons.append('health_control_already_armed')
        return sorted(set(reasons))

    async def inspect(self, workspace: str, sender: str) -> dict:
        reference(workspace);reference(sender)
        view=await self._snapshot(self.db,workspace,sender)
        return {'workspace_id':workspace,'sender_id':sender,'digest':canonical_hash(view),
            'blockers':self._blockers(view,now(),arm=True),'campaigns_resumed':False}

    async def arm(self, workspace: str, sender: str, operator: str, evidence: str, expected: str,
                  *, window_seconds: int = 300) -> dict:
        for value in (workspace,sender,operator):reference(value)
        if (not runtime_enabled() or type(window_seconds) is not int or not 1<=window_seconds<=MAX_WINDOW_SECONDS
                or any(not isinstance(value,str) or not HEX.fullmatch(value) for value in (evidence,expected))):
            raise ValueError('Exact bounded health renewal authorization is required')
        key=canonical_hash(['health-control-v1',workspace,sender,expected]); scope={'workspace_id':workspace,'_id':key}
        request=canonical_hash([workspace,sender,operator,evidence,expected,window_seconds])
        def saved(row):
            if row.get('request_digest')!=request:raise ValueError('A different health authorization is saved')
            return {'control_id':key,'status':row['status'],'campaigns_resumed':False}
        row=await self.db.outreach_health_controls.find_one(scope)
        if row:return saved(row)
        async def apply(current):
            from outreach.core.restore_epoch import positive
            epoch = await positive(current, workspace)
            row=await current.outreach_health_controls.find_one(scope)
            if row:return saved(row)
            fenced=AuthorityDatabase(current.database,current.session,key) if isinstance(current,suppression.SuppressionDatabase) else current
            view=await self._snapshot(fenced,workspace,sender); stamp=now()
            if canonical_hash(view)!=expected or self._blockers(view,stamp,arm=True):raise ValueError('Health inspection changed or is unavailable')
            state=view['state']; account=view['account']
            row={**scope,'sender_id':sender,'status':'armed','request_digest':request,'arm_digest':expected,
                'generation':account['credential_generation'],'sources':state['permission']['sources'],
                'expected_permission_revision':state['permission_revision'],'policy_digest':view['policy_digest'],
                'operator':operator,'operator_digest':canonical_hash(operator),'evidence_digest':evidence,
                'created_at':stamp,'expires_at':stamp+timedelta(seconds=window_seconds),'next_check_at':stamp,
                'renewals':0,'provenance':'bounded_operator_health_renewal'}
            await current.outreach_health_controls.insert_one(row)
            self._final(view, min(row['expires_at'], _utc(account['execution_health']['observed_at'])+FRESHNESS,
                _utc(state['permission']['expires_at']), _utc(view['paid']['paid_through']), _utc(view['inventory']['expires_at'])))
            epoch.assert_live()
            return saved(row)
        return await suppression.mutate_suppression(self.db,workspace,apply)

    @staticmethod
    def _final(view: dict, deadline: datetime) -> None:
        if not runtime_enabled() or canonical_hash(policy())!=view['policy_digest'] or now()>=deadline:
            raise ValueError('Health renewal configuration or deadline changed')

    async def _stop(self, current: Any, row: dict, state: dict, reason: str, stamp: datetime, campaigns: list) -> dict:
        scope={'workspace_id':row['workspace_id'],'_id':row['_id'],'status':'armed'}
        changed=await current.outreach_sender_execution.update_one({**ExecutionPermission.scope(row['workspace_id'],row['sender_id']),
            'permission_revision':row['expected_permission_revision'],'permission':state['permission']},
            {'$set':{'permission.latched':True,'permission.expires_at':stamp,'permission.stop_reason':reason},'$inc':{'permission_revision':1}})
        if changed.matched_count!=1:raise ValueError('Health stop authority changed')
        for campaign in campaigns:
            await current.outreach_campaigns.update_one({'workspace_id':row['workspace_id'],'_id':campaign['_id'],
                'status':campaign['status'],'authorization_revision':campaign.get('authorization_revision',0)},
                {'$set':{'status':'paused','auto_launch_enabled':False},'$inc':{'authorization_revision':1},
                 '$addToSet':{'pause_reasons':'health_monitor'}})
        await current.outreach_execution_permissions.update_one(ExecutionPermission.scope(row['workspace_id'],row['sender_id']),
            {'$set':{'latched':True,'expires_at':stamp,'stop_reason':reason}},upsert=True)
        await current.outreach_health_controls.update_one(scope,{'$set':{'status':'stopped','stop_reason':reason,'stopped_at':stamp}})
        return {'control_id':row['_id'],'status':'stopped','campaigns_resumed':False,
            'campaign_pause_scan_complete':len(campaigns)<=LIMIT}

    async def tick(self, workspace: str, control_id: str) -> dict:
        reference(workspace)
        if not isinstance(control_id,str) or not HEX.fullmatch(control_id):raise ValueError('An exact health control is required')
        async def apply(current):
            row=await current.outreach_health_controls.find_one({'workspace_id':workspace,'_id':control_id})
            if not row:return {'status':'absent','campaigns_resumed':False}
            if row['status']!='armed':return {'status':row['status'],'campaigns_resumed':False}
            stamp=now(); fenced=AuthorityDatabase(current.database,current.session,control_id) if isinstance(current,suppression.SuppressionDatabase) else current
            view=await self._snapshot(fenced,workspace,row['sender_id']); state=view['state'] or {}; account=view['account'] or {}
            scope={'workspace_id':workspace,'_id':control_id,'status':'armed'}
            if (account.get('credential_generation')!=row['generation'] or state.get('permission_revision')!=row['expected_permission_revision']
                    or (state.get('permission') or {}).get('credential_generation')!=row['generation']
                    or (state.get('permission') or {}).get('sources')!=row['sources']):
                await current.outreach_health_controls.update_one(scope,{'$set':{'status':'obsolete','stopped_at':stamp}})
                return {'status':'obsolete','campaigns_resumed':False}
            reasons=self._blockers(view,stamp)
            if not instant(row.get('expires_at')) or _utc(row['expires_at'])<=stamp:reasons.append('control_expired')
            if canonical_hash(policy())!=row['policy_digest']:reasons.append('configuration_changed')
            if reasons==['sender_owned'] and instant(state.get('expires_at')) and _utc(state['expires_at'])>stamp:
                await current.outreach_health_controls.update_one(scope,{'$set':{'next_check_at':stamp+INTERVAL}})
                return {'status':'busy','campaigns_resumed':False}
            if reasons:return await self._stop(current,row,state,sorted(reasons)[0],stamp,view['campaigns'])
            if instant(row.get('next_check_at')) and _utc(row['next_check_at'])>stamp:return {'status':'not_due','campaigns_resumed':False}
            deadline=min(stamp+timedelta(seconds=MAX_PERMISSION_SECONDS),_utc(row['expires_at']),
                _utc(account['execution_health']['observed_at'])+FRESHNESS,_utc(view['paid']['paid_through']),_utc(view['inventory']['expires_at']))
            if deadline<=stamp:return await self._stop(current,row,state,'health_deadline_expired',stamp,view['campaigns'])
            from outreach.core.restore_epoch import positive
            epoch = await positive(current, workspace)
            permission={'credential_generation':row['generation'],'sources':row['sources'],'latched':False,'stop_reason':None,
                'issued_at':stamp,'expires_at':deadline,'operator':row['operator'],'health_control_id':control_id}
            changed=await current.outreach_sender_execution.update_one({**ExecutionPermission.scope(workspace,row['sender_id']),
                'permission_revision':row['expected_permission_revision'],'permission':state['permission'],'status':'idle',
                'physical_request_token':{'$exists':False},'owner_token':{'$exists':False}},
                {'$set':{'permission':permission},'$inc':{'permission_revision':1},'$push':{'permission_history':{
                    'event':'health_renewal','control_id':control_id,'at':stamp,'expires_at':deadline}}})
            if changed.matched_count!=1:raise ValueError('Health renewal owner changed')
            await current.outreach_execution_permissions.update_one(ExecutionPermission.scope(workspace,row['sender_id']),
                {'$set':{**permission,'revision':row['expected_permission_revision']+1}},upsert=True)
            await current.outreach_health_controls.update_one(scope,{'$set':{'expected_permission_revision':row['expected_permission_revision']+1,
                'next_check_at':stamp+INTERVAL,'last_checked_at':stamp},'$inc':{'renewals':1}})
            self._final(view,deadline)
            if not epoch.live():raise ValueError('Restore epoch changed during renewal')
            return {'status':'renewed','expires_at':deadline.isoformat(),'campaigns_resumed':False}
        return await suppression.mutate_suppression(self.db,workspace,apply)

    async def stop(self, workspace: str, control_id: str, operator: str, evidence: str) -> dict:
        for value in (workspace,operator):reference(value)
        if any(not isinstance(value,str) or not HEX.fullmatch(value) for value in (control_id,evidence)):
            raise ValueError('Exact health stop evidence is required')
        async def apply(current):
            row=await current.outreach_health_controls.find_one({'workspace_id':workspace,'_id':control_id})
            if not row or row.get('status')!='armed':return {'status':(row or {}).get('status','absent'),'campaigns_resumed':False}
            fenced=AuthorityDatabase(current.database,current.session,control_id) if isinstance(current,suppression.SuppressionDatabase) else current
            view=await self._snapshot(fenced,workspace,row['sender_id']); state=view['state'] or {}
            if (state.get('permission_revision')!=row['expected_permission_revision']
                    or (view['account'] or {}).get('credential_generation')!=row['generation']
                    or (state.get('permission') or {}).get('credential_generation')!=row['generation']
                    or (state.get('permission') or {}).get('sources')!=row['sources']):
                await current.outreach_health_controls.update_one({'workspace_id':workspace,'_id':control_id},{'$set':{'status':'obsolete'}})
                return {'status':'obsolete','campaigns_resumed':False}
            result=await self._stop(current,row,state,'operator_health_stop',now(),view['campaigns'])
            await current.outreach_health_controls.update_one({'workspace_id':workspace,'_id':control_id},
                {'$set':{'stop_operator_digest':canonical_hash(operator),'stop_evidence_digest':evidence}})
            return result
        return await suppression.mutate_suppression(self.db,workspace,apply)

    async def sweep(self, *, limit: int = 100) -> dict:
        if type(limit) is not int or not 1<=limit<=100:raise ValueError('Bounded health scan required')
        rows=await self.db.outreach_health_controls.find({'status':'armed','next_check_at':{'$lte':now()}}).sort([('next_check_at',1),('_id',1)]).limit(limit).to_list(length=limit)
        counts={'processed':0,'failed':0}
        for row in rows:
            try:await self.tick(row['workspace_id'],row['_id']);counts['processed']+=1
            except Exception:
                counts['failed']+=1
                logger.warning('Sender health control needs review; renewal denied')
                # Back off only this still-due root, never a concurrent renewal/stop.
                await self.db.outreach_health_controls.update_one({'workspace_id':row['workspace_id'],
                    '_id':row['_id'],'status':'armed','next_check_at':row['next_check_at']},
                    {'$set':{'next_check_at':now()+INTERVAL,'scan_error':'review_required'}})
        return counts
