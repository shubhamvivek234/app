"""Conservative version admission, not a progress migration or execution grant.

Only an unacted queued root can receive its first current-version binding.
Retained progress must already carry the exact current integer version. These
queries observe current records; older/raw writers and rolled-back data need
separate review. Helpers perform no writes; launch owns conditional rebinding.
"""
import logging
logger = logging.getLogger(__name__)
from bson import Int64

from outreach.core.workspace_scope import workspace_scope

TERMINAL_STATES = ['staged', 'replied', 'finished', 'bounced', 'failed']
PROGRESS_FIELDS = ('last_action_at', 'last_action_taken',
                   'waiting_for_connection_at', 'waiting_for_reply_at')
MAX_VERSION = 2**53 - 1
VERSION_HOLD = ('Outstanding prospects need a review of their saved sequence version '
                'or step before this campaign can resume')


def current_version(sequence: dict) -> int | None:
    value = sequence.get('version', 1)
    return int(value) if type(value) in (int, Int64) and 1 <= value <= MAX_VERSION else None


def outstanding_scope(workspace: str, campaign_id: str) -> dict:
    return {**workspace_scope(workspace), 'campaign_id': campaign_id,
            'campaign_id.0': {'$exists': False}, 'has_replied': {'$ne': True},
            'execution_state': {'$nin': TERMINAL_STATES}}


def binding_candidates(version: int, roots: list[str], nodes: list[str]) -> dict:
    unacted = {'execution_state': 'queued', 'current_node_id': {'$in': [None, *roots]},
             **{field: None for field in PROGRESS_FIELDS},
             '$nor': [{field: {'$type': 'array'}} for field in
                      ('execution_state', 'current_node_id', *PROGRESS_FIELDS)]}
    fresh = {'$and': [unacted, {'sequence_version': None, 'authorized_revision': None,
             '$nor': [{field: {'$type': 'array'}} for field in
                      ('sequence_version', 'authorized_revision')]}]}
    exact = {'sequence_version': version,
             '$or': [{'sequence_version': {'$type': 'int'}},
                     {'sequence_version': {'$type': 'long'}}],
             '$nor': [{'sequence_version': {'$type': 'array'}}]}
    position = {'$or': [unacted, {'current_node_id': {'$in': nodes},
                 'execution_state': {'$type': 'string'},
                 '$nor': [{'current_node_id': {'$type': 'array'}},
                          {'execution_state': {'$type': 'array'}}]}]}
    return {'$or': [fresh, {'$and': [exact, position]}]}


def version_conflicts(workspace: str, campaign_id: str, version: int, roots: list[str], nodes: list[str]) -> dict:
    return {'$and': [outstanding_scope(workspace, campaign_id),
                     {'$nor': [binding_candidates(version, roots, nodes)]}]}
