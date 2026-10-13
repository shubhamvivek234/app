"""Bounded, read-only reporting of stored email evidence, never delivery proof."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any

from outreach.core.workspace_scope import workspace_scope

logger = logging.getLogger(__name__)
MAX_OPERATIONS = 10_000
MAX_EVENTS = 20_000
MAX_TASKS = 10_000
READ_SECONDS = 10
COUNTS = ('sent', 'provider_accepted', 'bounced', 'possible_bounced', 'delivery_unknown',
          'pending_or_unknown_operations', 'human_reported', 'unverified_operations',
          'unverified_task_records', 'unverified_bounce_events')


def _date(value: Any) -> datetime | None:
    # BSON's default naive codec represents UTC; strings are unproven dates.
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _identity(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 200


def _scope(workspace: str, campaign: str | None, sender: str | None, sender_field: str) -> dict:
    query = workspace_scope(workspace)
    for field, value in (('campaign_id', campaign), (sender_field, sender)):
        if value and value != 'all':
            query.update({field: value, field + '.0': {'$exists': False}})
    return query


async def _rows(collection, query: dict, projection: dict, maximum: int) -> list[dict]:
    rows = await collection.find(query, projection).limit(maximum + 1).to_list(length=maximum + 1)
    if not isinstance(rows, list) or len(rows) > maximum or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Email reporting capacity or source contract exceeded')
    return rows


def _result(start: datetime, as_of: datetime, available: bool) -> dict:
    email = {key: 0 if available else None for key in COUNTS}
    email.update({'submitted': None, 'submission_status': 'unavailable',
        'delivered': None, 'deliverability_rate': None, 'denominator': 0 if available else None,
        'delivery_status': 'unavailable', 'evidence_status': 'recorded' if available else 'unavailable',
        'cohort_basis': 'provider_accepted_at_utc', 'period_start': start.isoformat(),
        'as_of': as_of.isoformat(), 'bounce_basis': 'stored_message_reference_classification',
        'message': ('Provider acceptance is not delivery. Reference bounces are stored classifications; '
                    'thread/address matches are possible bounces. Submission and delivery coverage are unavailable.'
                    if available else 'Email evidence could not be fully read. Counts are unavailable; retry or narrow the filters.')})
    return {'kpis': email, 'daily': {}}


async def _build(db, workspace: str, campaign: str | None, sender: str | None,
                 start: datetime, as_of: datetime) -> dict:
    operations = await _rows(db.outreach_email_operations,
        _scope(workspace, campaign, sender, 'sender_account_id'),
        {key: 1 for key in ('_id', 'workspace_id', 'campaign_id', 'sender_account_id',
            'logical_operation_id', 'source', 'provider', 'provider_message_id', 'credential_generation', 'status',
            'accepted_at', 'created_at', 'acceptance_source', 'resolution.source')}, MAX_OPERATIONS)
    result = _result(start, as_of, True)
    email, daily = result['kpis'], result['daily']
    accepted: dict[str, dict] = {}
    task_bindings: set[tuple[str, str, str]] = set()

    def add_day(date: datetime, field: str) -> None:
        slot = daily.setdefault(date.date().isoformat(), {'email_provider_accepted': 0, 'email_bounced': 0})
        slot[field] += 1

    for op in operations:
        logical = op.get('logical_operation_id')
        valid = (op.get('workspace_id') == workspace and _identity(op.get('campaign_id'))
            and _identity(op.get('sender_account_id')) and _identity(logical)
            and op.get('_id') == f'email:{workspace}:{logical}' and op.get('source') == 'email_send'
            and isinstance(op.get('provider'), str) and op['provider'] in {'gmail', 'microsoft'}
            and _identity(op.get('credential_generation')))
        if not valid:
            email['unverified_operations'] += 1
            continue
        created, at = _date(op.get('created_at')), _date(op.get('accepted_at'))
        resolution = op.get('resolution')
        human = (op.get('acceptance_source') == 'human_assertion'
                 or isinstance(resolution, dict) and resolution.get('source') == 'human_assertion')
        if human:
            if at and at <= as_of:
                if start <= at:
                    email['human_reported'] += 1
            else:
                email['unverified_operations'] += 1
            continue
        if op.get('status') == 'accepted':
            if (not at or not created or not created <= at <= as_of or resolution
                    or op.get('acceptance_source') not in (None, 'provider_response', 'transport_response_recovery')
                    or op['provider'] == 'gmail' and (not isinstance(op.get('provider_message_id'), str)
                        or not op['provider_message_id'].strip())):
                email['unverified_operations'] += 1
            else:
                # A repaired old acceptance can explain its task without moving into this cohort.
                task_bindings.add((op['campaign_id'], op['sender_account_id'], logical))
                if start <= at:
                    accepted[op['_id']] = {**op, 'accepted_at': at}
                    add_day(at, 'email_provider_accepted')
        elif op.get('status') in ('dispatching', 'uncertain'):
            if created and start <= created <= as_of:
                email['pending_or_unknown_operations'] += 1
            elif not created or created > as_of:
                email['unverified_operations'] += 1
        elif op.get('status') not in ('not_submitted', 'failed', 'not_sent_stopped'):
            email['unverified_operations'] += 1

    # Old task projections have no independent acceptance/delivery authority.
    tasks = await _rows(db.outreach_tasks, {**_scope(workspace, campaign, sender, 'account_id'),
        'task_type': 'send_email', 'status': {'$in': ['completed', 'accepted']},
        'updated_at': {'$gte': start, '$lte': as_of}},
        {key: 1 for key in ('id', 'campaign_id', 'account_id')}, MAX_TASKS)
    for task in tasks:
        binding = tuple(task.get(key) for key in ('campaign_id', 'account_id', 'id'))
        if not all(_identity(value) for value in binding) or binding not in task_bindings:
            email['unverified_task_records'] += 1

    bounced: dict[str, datetime] = {}
    possible: set[str] = set()
    if accepted:
        query = {**workspace_scope(workspace), 'operation_id': {'$in': list(accepted)}, 'kind': 'bounce'}
        events = await _rows(db.outreach_email_inbound_events, query,
            {key: 1 for key in ('operation_id', 'workspace_id', 'sender_account_id',
                'kind', 'received_at', 'attribution')}, MAX_EVENTS)
        for event in events:
            operation_id = event.get('operation_id')
            op = accepted.get(operation_id) if isinstance(operation_id, str) else None
            at = _date(event.get('received_at'))
            if (not op or event.get('workspace_id') != workspace
                    or event.get('sender_account_id') != op['sender_account_id']):
                continue
            if event.get('kind') != 'bounce':
                email['unverified_bounce_events'] += 1
                continue
            if not at or not op['accepted_at'] <= at <= as_of:
                email['unverified_bounce_events'] += 1
                continue
            if event.get('attribution') == 'message_reference':
                bounced[operation_id] = min(at, bounced.get(operation_id, at))
            else:
                # A conversation, address or old unproven label is not a unique message reference.
                possible.add(operation_id)
    for at in bounced.values():
        add_day(at, 'email_bounced')
    email.update({'sent': len(accepted), 'provider_accepted': len(accepted),
        'denominator': len(accepted), 'bounced': len(bounced),
        'possible_bounced': len(possible - bounced.keys()), 'delivery_unknown': len(accepted) - len(bounced)})
    if any(email[key] for key in ('unverified_operations', 'unverified_task_records', 'unverified_bounce_events')):
        email['evidence_status'] = 'partial'
        email['message'] += ' Some selected records lack usable evidence; known counts are not a complete history.'
    return result


async def email_report(db, *, workspace: str, campaign: str | None, sender: str | None,
                       start: datetime, as_of: datetime) -> dict:
    """Observe a selected acceptance cohort without writes, HTTP, secrets or repair."""
    try:
        return await asyncio.wait_for(_build(db, workspace, campaign, sender, start, as_of), READ_SECONDS)
    except Exception as exc:
        logger.warning('Email reporting unavailable (%s)', type(exc).__name__)
        return _result(start, as_of, False)
