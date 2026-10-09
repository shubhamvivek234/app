"""Private drained strict-Fernet to scoped storage conversion; no provider calls."""
from __future__ import annotations
from copy import deepcopy
from typing import Any
import uuid
from outreach.core import erasure, integration_control as ctl, integration_custody as custody, session_custody
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import PREFIX
from outreach.core.integration_delivery import now
from utils.encryption import decrypt_strict


class IntegrationMigration:
    def __init__(self, db: Any) -> None:
        self.db = db

    @staticmethod
    def _blockers(view: dict) -> list[str]:
        reasons = ctl.blockers(view); row = view['source'] or {}
        if not view['workspace_open']: reasons.append('workspace_closed')
        if session_custody.custody_mode() != 'kms_v1': reasons.append('scoped_destination_required')
        if not row or not ctl.material(row, view['workspace_id'], view['kind']): reasons.append('resource_binding_unproven')
        value = row.get(custody.FIELDS[view['kind']])
        if not isinstance(value,str) or not value or value.startswith(PREFIX): reasons.append('original_strict_fernet_required')
        if row.get('custody_workspace_id') not in {None,view['workspace_id']}: reasons.append('original_scope_unproven')
        if any(row.get('status') not in {'pending','retry'} for row in view['jobs']): reasons.append('original_delivery_outcome_unresolved')
        return sorted(set(reasons))

    async def inspect(self, workspace: str, kind: str, resource: str) -> dict:
        view = await ctl.snapshot(self.db,workspace,kind,resource)
        return {'workspace_id':workspace,'kind':kind,'resource_id':resource,'review_digest':canonical_hash(view),
            'blockers':self._blockers(view),'activation_allowed':False}

    async def migrate(self, workspace: str, kind: str, resource: str, operator: str, evidence: str,
                      expected_digest: str, *, workers_drained: bool = False) -> dict:
        ctl.require_review(operator,evidence,expected_digest,workers_drained)
        ctl.reference(workspace); custody.resource_scope(workspace,kind,resource)
        key=canonical_hash(['integration_custody_migration',workspace,kind,resource,expected_digest])
        journal_scope={'workspace_id':workspace,'_id':key}
        async def saved(current: Any, receipt: dict) -> dict:
            if (receipt.get('operator_digest')!=canonical_hash(operator.strip())
                    or receipt.get('evidence_digest')!=canonical_hash(evidence.strip())):
                raise ValueError('A different integration migration is already saved')
            row=await custody.collection(current,kind).find_one(custody.resource_scope(workspace,kind,resource))
            return {'status':'completed','migration_id':key,
                'current_matches':ctl.material(row,workspace,kind)==receipt['after_digest'],
                'configuration_matches':custody.policy_digest()==receipt['target_policy_digest'],'activation_allowed':False}
        existing=await self.db.outreach_credential_migrations.find_one(journal_scope)
        if existing:return await saved(self.db,existing)
        if not await erasure.workspace_is_open(self.db,workspace):
            raise ValueError('Workspace is closed for credential installation')
        async def verify(current: Any) -> dict:
            view=await ctl.snapshot(ctl.fenced(current),workspace,kind,resource)
            if canonical_hash(view)!=expected_digest or self._blockers(view):raise ValueError('Drained integration inspection changed')
            return view
        async def preflight(current: Any) -> dict:
            # Another exact migration can commit between the unguarded receipt
            # lookup and this snapshot. Its permanent receipt must win before
            # comparing the old source digest or opening the original key.
            receipt=await current.outreach_credential_migrations.find_one(journal_scope)
            if receipt:return {'completed':await saved(current,receipt)}
            return {'view':await verify(current)}
        inspected=await ctl.control(self.db,workspace,preflight)
        if 'completed' in inspected:return inspected['completed']
        view=inspected['view']
        row=deepcopy(view['source'])
        try:raw=decrypt_strict(row[custody.FIELDS[kind]]);custody._validate(raw,kind)
        except (ValueError,OSError,TypeError):raise ValueError('Original encrypted integration credential is unavailable') from None
        generation=row.get('credential_generation') or uuid.uuid4().hex
        scoped={**row,'credential_generation':generation,'custody_workspace_id':workspace}
        encrypted=await session_custody.configured_custody().seal(raw,custody._context(scoped,workspace,kind))
        del raw
        if not ctl.flags_off() or view['policy']!=custody.policy_digest():raise ValueError('Integration custody configuration changed')
        async def apply(current: Any) -> dict:
            receipt=await current.outreach_credential_migrations.find_one(journal_scope)
            if receipt:return await saved(current,receipt)
            fresh=await verify(current)
            await ctl.stop(current,fresh,operator.strip(),'integration_credential_migration')
            updates={custody.FIELDS[kind]:encrypted,'credential_generation':generation,'custody_workspace_id':workspace}
            changed=await custody.collection(current,kind).update_one({**custody.resource_scope(workspace,kind,resource),
                '_id':row['_id'],custody.FIELDS[kind]:row[custody.FIELDS[kind]]},{'$set':updates})
            if changed.matched_count!=1:raise ValueError('Original integration credential changed')
            after=await custody.collection(current,kind).find_one(custody.resource_scope(workspace,kind,resource))
            receipt={**journal_scope,'kind':'integration','resource_kind':kind,'resource_id':resource,'status':'completed',
                'before_digest':expected_digest,'after_digest':ctl.material(after,workspace,kind),
                'operator_digest':canonical_hash(operator.strip()),'evidence_digest':canonical_hash(evidence.strip()),
                'target_policy_digest':view['policy'],'generation_digest':canonical_hash(generation),
                'at':now(),'workers_drained':True,'activation_allowed':False,'provenance':'strict_fernet_storage_conversion'}
            await current.outreach_credential_migrations.insert_one(receipt)
            if not ctl.flags_off() or view['policy']!=custody.policy_digest():raise ValueError('Integration custody configuration changed')
            return await saved(current,receipt)
        return await ctl.control(self.db,workspace,apply)
