"""Due-action original-recipient observation using existing physical controls."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from outreach.core.authorization import authorization_snapshot
from outreach.core.connection_waits import (admission, one, scope_guard, read_operation, read_context,
    apply_observation, ConnectionWaitUnavailable)
from outreach.core.inbox_freshness import credential_generation
from outreach.core.request_guard import RequestEnvelope, RequestDenied
from outreach.core.restore_epoch import EpochUnavailable
from outreach.core.session_custody import account_session
from outreach.core.proxy_custody import prepare_proxy
from outreach.engine.voyager_client import VoyagerClient


async def recheck_connection(db: Any, lead: dict, campaign: dict, sequence: dict,
                             account: dict, node_type: str) -> dict | None:
    """No background monitor: only an original wait or due negative-path step."""
    if not lead.get('connection_wait_required') and not lead.get('connection_wait_id'):
        return None
    blocked = await scope_guard(db, lead, campaign, sequence, account, for_observation=True)
    if blocked:
        return {'status': blocked, 'not_submitted': True}
    scope = await one(db, 'outreach_connection_waits', lead['workspace_id'], {'_id': lead['connection_wait_id']})
    if not (scope['status'] == 'waiting' and lead.get('current_node_id') == scope['origin_node_id']
            or scope['status'] == 'negative_active' and lead.get('current_node_id') in scope['negative_nodes']):
        return None
    from outreach.tasks.sequence_executor import _preflight_dispatch
    workspace = lead['workspace_id']
    expected = authorization_snapshot(campaign, account, sequence)
    try:
        await admission(db, workspace, account, datetime.now(timezone.utc))
        async def validate(current: Any) -> str | None:
            reason = await _preflight_dispatch(current, lead, expected, node_type, observing_connection=True)
            if reason:
                return reason
            from outreach.core.inbox_freshness import require_fresh_inbox
            from outreach.tasks.sequence_executor import _recipient_has_reply
            current_sender = await one(current, 'outreach_accounts', workspace, {'id': account['id']})
            reason = await require_fresh_inbox(current, workspace, current_sender)
            if reason or await _recipient_has_reply(current, workspace, account['id'], lead):
                return reason or 'lead_suppressed'
            return None
        reason = await validate(db)
        if reason:
            return {'status': reason, 'not_submitted': True}
        from outreach.core.connection_observations import saved_positive
        recovered = await saved_positive(db, scope, lead, datetime.now(timezone.utc))
        if recovered:
            return await apply_observation(db, workspace, lead['id'], scope['_id'], recovered)
        prepared = await prepare_proxy(account['proxy'], workspace) if account.get('proxy') else None
        if not prepared:
            return {'status': 'connection_recheck_required', 'not_submitted': True}
        envelope = RequestEnvelope(db, workspace, account['id'], credential_generation(account), 'sequence', prepared.url,
            prepared_proxy=prepared, campaign_limits=campaign.get('limits') or {}, operation_id=read_operation(scope, lead),
            authority_validator=lambda: validate(db), transaction_validator=validate, connection_context=read_context(scope, lead))
        voyager = VoyagerClient(**(await account_session(account)), proxy_url=prepared.url, request_envelope=envelope)
        observation = await voyager.observe_original_connection(scope['recipient_urn'])
        request_id = observation.get('request_id') if isinstance(observation, dict) else None
        result = await apply_observation(db, workspace, lead['id'], scope['_id'], request_id)
        return None if result['status'] == 'connection_negative_confirmed' else result
    except (ConnectionWaitUnavailable, EpochUnavailable, RequestDenied):
        return {'status': 'connection_recheck_required', 'not_submitted': True}
