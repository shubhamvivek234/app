"""Recover original recorded observations before issuing another charged read."""
import logging
logger = logging.getLogger(__name__)
from datetime import datetime, timedelta
from typing import Any

from outreach.core.authorization import canonical_hash
from outreach.core.connection_waits import ConnectionWaitUnavailable, MAX_ROWS, READ_SECONDS, utc


def validate_observation(receipt: dict, scope: dict, lead: dict, now: datetime) -> bool | None:
    fact = receipt.get('connection_fact')
    context = receipt.get('connection_wait_context')
    at = utc(receipt.get('completed_at'))
    positive = isinstance(fact, dict) and fact.get('connected') is True
    if (not isinstance(receipt.get('_id'), str) or not 1 <= len(receipt['_id']) <= 200
            or not isinstance(fact, dict) or type(fact.get('version')) is not int or fact['version'] != 1
            or fact.get('kind') != 'observed_connection' or fact.get('recipient_urn') != scope['recipient_urn']
            or fact.get('connected') is not None and type(fact['connected']) is not bool
            or not at or utc(fact.get('observed_at')) != at or not timedelta(0) <= now - at <= timedelta(seconds=READ_SECONDS)
            or not isinstance(context, dict) or set(context) != {'scope_id', 'scope_revision', 'lead_native', 'node_id', 'dispatch_key', 'operation_id'}
            or context.get('scope_id') != scope['_id'] or type(context.get('scope_revision')) is not int
            or not 1 <= context['scope_revision'] <= scope['revision']
            or not positive and context['scope_revision'] != scope['revision']
            or context.get('lead_native') != scope['lead_native'] or not isinstance(context.get('node_id'), str)
            or context['node_id'] not in [scope['origin_node_id'], *scope['negative_nodes']]
            or not positive and context['node_id'] != lead.get('current_node_id')
            or not isinstance(context.get('dispatch_key'), str) or not 1 <= len(context['dispatch_key']) <= 200
            or context.get('operation_id') != canonical_hash(['connection-recheck-v1', scope['_id'], context['scope_revision'], context['node_id'], context['dispatch_key']])
            or receipt.get('logical_operation_id') != context['operation_id'] or receipt.get('source') != 'sequence'
            or receipt.get('sender_id') != scope['sender_id'] or receipt.get('credential_generation') != scope['credential_generation']
            or receipt.get('status') != 'response_received' or receipt.get('action') != 'read' or receipt.get('mutation') is not False
            or type(receipt.get('http_status')) is not int or receipt['http_status'] != 200
            or not isinstance(receipt.get('owner_token'), str) or not receipt['owner_token']
            or not isinstance(receipt.get('dispatch_authorization'), dict) or receipt['dispatch_authorization'].get('mode') != 'transaction'
            or receipt.get('endpoint_digest') != canonical_hash(['GET', '/voyager/api/relationships/connections'])):
        raise ConnectionWaitUnavailable('connection_observation_unavailable')
    return fact['connected']


async def saved_positive(db: Any, scope: dict, lead: dict, now: datetime) -> str | None:
    # Fact publication shares the workspace guard with final action authorization.
    # A stale or malformed saved positive holds; a later negative cannot erase it.
    rows = await db.outreach_physical_requests.find({'workspace_id': scope['workspace_id'],
        'connection_wait_context.scope_id': scope['_id'], 'connection_fact.connected': True,
        }).limit(MAX_ROWS + 1).to_list(length=MAX_ROWS + 1)
    if len(rows) > MAX_ROWS:
        raise ConnectionWaitUnavailable('connection_observation_overflow')
    for row in rows:
        if validate_observation(row, scope, lead, now) is not True:
            raise ConnectionWaitUnavailable('connection_observation_unavailable')
    if not rows:
        return None
    return min(rows, key=lambda row: (utc(row['completed_at']), str(row['_id'])))['_id']
