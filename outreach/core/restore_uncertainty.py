"""Conservative metadata findings for intact restored provider-operation rows.

Labels are not receipts, non-call proofs, or replay authority. Independent
substates remain visible even when a parent job was stopped or reviewed.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

from collections import Counter
from typing import Any

FIELDS = {
    'outreach_mailbox_connection_jobs': ('_id', 'status', 'exchange_state'),
    'outreach_mailbox_oauth_states': ('_id',),
    'outreach_mailboxes': ('_id', 'status', 'refresh_state'),
    'outreach_mailbox_sync_jobs': ('_id', 'status'),
    'outreach_mailbox_sync_reads': ('_id', 'status'),
    'outreach_voice_preparation_jobs': ('_id', 'status', 'generation_result'),
    'outreach_voice_studio_jobs': ('_id', 'status', 'review.outcome_at_review'),
    'outreach_voice_vendor_reads': ('_id', 'status'),
    'outreach_webhook_deliveries': ('_id', 'status'),
}

# All comparisons use tuples: malformed BSON containers must report unproven,
# rather than raising an unhashable-state exception or disappearing silently.
RULES = (
    ('outreach_mailbox_connection_jobs', 'oauth_job', 'status', (
        ('pending_review', ('pending', 'queued')),
        ('unresolved', ('running', 'review_required')),
        ('recorded_result_review', ('connected',)),
        ('stopped_review', ('failed', 'review_stopped')))),
    ('outreach_mailbox_connection_jobs', 'oauth_exchange', 'exchange_state', (
        ('pending_review', ('pending',)), ('preparing_review', ('preparing',)),
        ('unresolved', ('possible', 'unknown')),
        ('recorded_result_review', ('installed', 'rejected')),
        ('stopped_review', ('not_submitted',)))),
    ('outreach_mailboxes', 'mailbox', 'status', (
        ('recorded_state_review', ('active',)),
        ('stopped_review', ('disconnected', 'reauth_required', 'stopped')))),
    ('outreach_mailboxes', 'mailbox_refresh', 'refresh_state', (
        ('preparing_review', ('preparing',)), ('unresolved', ('possible', 'unknown')),
        ('recorded_result_review', ('rejected',)))),
    ('outreach_mailbox_sync_jobs', 'mailbox_sync_job', 'status', (
        ('pending_review', ('queued',)), ('unresolved', ('running',)),
        ('recorded_result_review', ('completed',)), ('stopped_review', ('failed', 'stopped')))),
    ('outreach_mailbox_sync_reads', 'mailbox_sync_read', 'status', (
        ('unresolved', ('possible', 'read_interrupted')), ('recorded_result_review', ('received',)))),
    ('outreach_voice_preparation_jobs', 'voice_preparation', 'status', (
        ('pending_review', ('queued',)), ('preparing_review', ('claimed',)),
        ('unresolved', ('generating', 'held_outcome')), ('recorded_result_review', ('prepared',)),
        ('stopped_review', ('blocked', 'superseded', 'cancelled')))),
    ('outreach_voice_preparation_jobs', 'voice_generation', 'generation_result', (
        ('recorded_result_review', ('received', 'received_discarded')),)),
    ('outreach_voice_studio_jobs', 'voice_studio', 'status', (
        ('pending_review', ('queued',)), ('preparing_review', ('preparing',)),
        ('unresolved', ('possible', 'held_outcome')),
        ('recorded_result_review', ('received', 'held_received', 'completed', 'review_completed')),
        ('stopped_review', ('cancelled', 'stopped', 'review_stopped')))),
    ('outreach_voice_studio_jobs', 'voice_studio_original_outcome', 'review.outcome_at_review', (
        ('unresolved', ('unknown',)), ('recorded_result_review', ('received',)),
        ('stopped_review', ('not_called',)))),
    ('outreach_voice_vendor_reads', 'voice_vendor_read', 'status', (
        ('preparing_review', ('preparing',)), ('unresolved', ('possible', 'read_interrupted')),
        ('recorded_result_review', ('received', 'released')), ('stopped_review', ('stopped',)))),
    ('outreach_webhook_deliveries', 'integration_delivery', 'status', (
        ('pending_review', ('pending', 'retry')), ('preparing_review', ('preparing',)),
        ('unresolved', ('possible', 'review_required')),
        ('recorded_result_review', ('received', 'held_received', 'delivered', 'review_completed')),
        ('stopped_review', ('failed', 'cancelled')))),
)


def findings(records: dict[str, list[dict[str, Any]]]) -> Counter:
    """Consume only the inventory's sanitized, flattened metadata projections."""
    result = Counter()
    result['oauth_browser_state_review'] = len(records['outreach_mailbox_oauth_states'])
    for collection, prefix, field, groups in RULES:
        for row in records[collection]:
            if field not in row:
                if field in ('generation_result', 'review.outcome_at_review'):
                    continue  # Optional evidence; parent state still requires review.
                if field == 'refresh_state':
                    result[prefix + '_unmarked_review'] += 1
                    continue
            state = row.get(field)
            category = next((label for label, states in groups if state in states), 'state_unproven')
            result[prefix + '_' + category] += 1
    return +result
