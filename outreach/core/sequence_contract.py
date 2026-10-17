"""Finite JSON/graph/tree contracts shared by sequence authoring and inspection."""
from __future__ import annotations

import json
import math
import re
from typing import Any
from bson.int64 import Int64

MAX_NODES = 100
MAX_EDGES = 200
MAX_JSON_BYTES = 1_000_000
MAX_DEPTH = 12
MAX_TREE_DEPTH = 32
MAX_DELAY_HOURS = 8760
MAX_RENDER_CHARS = 10000


class DAGValidationError(ValueError):
    """An invalid or ambiguous sequence cannot be published as executable."""


def bounded_json(value: Any, max_depth: int = MAX_DEPTH) -> None:
    stack = [(value, 0)]
    items = size = 0
    while stack:
        current, depth = stack.pop()
        items += 1
        if depth > max_depth or items > 20_000:
            raise DAGValidationError("Sequence data exceeds its depth or item bound.")
        if isinstance(current, dict):
            if items + len(stack) + 2 * len(current) > 20_000:
                raise DAGValidationError("Sequence data exceeds its item bound.")
            if any(not isinstance(key, str) or len(key) > 200 or '\x00' in key for key in current):
                raise DAGValidationError("Sequence objects require bounded string keys.")
            stack.extend((item, depth + 1) for pair in current.items() for item in pair)
        elif isinstance(current, list):
            if items + len(stack) + len(current) > 20_000:
                raise DAGValidationError("Sequence data exceeds its item bound.")
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, str):
            try:
                size += len(current.encode('utf-8'))
            except UnicodeError:
                raise DAGValidationError("Sequence text must be valid UTF-8.") from None
        elif current is None or type(current) in (bool, int, Int64):
            if type(current) in (int, Int64) and not -(2**63) <= current <= 2**63 - 1:
                raise DAGValidationError("Sequence numeric values exceed their bound.")
        elif type(current) is float and math.isfinite(current):
            pass
        else:
            raise DAGValidationError("Sequence data must contain finite JSON values.")
        if size > MAX_JSON_BYTES:
            raise DAGValidationError("Sequence data must be at most 1 MB.")
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')) > MAX_JSON_BYTES:
        raise DAGValidationError("Sequence data must be at most 1 MB.")


def identity(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}', value))


def delay_hours(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= MAX_DELAY_HOURS:
        raise DAGValidationError("Step delays require whole hours from 0 to 8760.")
    return value


_BOOLEAN = {'if_connected', 'if_email_available', 'if_opened_message', 'open_profile_check', 'has_data_in_column'}
_WAIT = {'connection_request', 'if_connected', 'send_message', 'voice_note'}
_COMMON_YES = {'yes', 'true', 'positive'}
_COMMON_NO = {'no', 'false', 'negative'}
_VOCABULARIES = {
    'connection_request': ({'accepted', 'connected'}, {'not accepted', 'not accepted yet', 'not connected', 'rejected', 'declined'}),
    'if_connected': ({'accepted', 'connected'}, {'not accepted', 'not accepted yet', 'not connected', 'rejected', 'declined'}),
    'send_message': ({'replied'}, {'no reply', 'unresponsive'}),
    'voice_note': ({'replied'}, {'no reply', 'unresponsive'}),
    'inmail': ({'replied'}, {'no reply', 'unresponsive'}),
    'if_email_available': ({'email available'}, {'email unavailable'}),
    'if_opened_message': ({'opened'}, {'not opened'}),
    'open_profile_check': ({'open profile'}, {'closed profile'}),
    'has_data_in_column': ({'has data'}, {'missing data'}),
}


def branch_kind(kind: str, label: Any) -> str:
    if label is None or label == '':
        if kind in _BOOLEAN:
            raise DAGValidationError("Condition steps require explicit Yes/No branch labels.")
        return 'default'
    if not isinstance(label, str) or len(label) > 80:
        raise DAGValidationError("Branch labels require bounded text.")
    value = label.strip().lower()
    if not value:
        return branch_kind(kind, None)
    yes, no = _VOCABULARIES.get(kind, (set(), set()))
    if kind in _VOCABULARIES and value in yes | _COMMON_YES:
        return 'positive'
    if kind in _VOCABULARIES and value in no | _COMMON_NO:
        return 'negative'
    raise DAGValidationError(f"Step type {kind} does not support branch label {label!r}.")


def graph_envelope(nodes: Any, edges: Any) -> None:
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES:
        raise DAGValidationError("Sequence must contain 1–100 steps.")
    if not isinstance(edges, list) or len(edges) > MAX_EDGES:
        raise DAGValidationError("Sequence must contain at most 200 connections.")
    bounded_json({'nodes': nodes, 'edges': edges})
    for node in nodes:
        if not isinstance(node, dict) or not identity(node.get('id')) or not isinstance(node.get('type'), str):
            raise DAGValidationError("Every sequence step needs a scalar ID and type.")
        delay_hours(node.get('delay_hours', 0))
        if not isinstance(node.get('config', {}), dict):
            raise DAGValidationError(f"Step {node['id']} config must be an object.")
        if node['type'] == 'has_data_in_column':
            from outreach.core.field_conditions import validate_config
            validate_config(node.get('config', {}))
        if not isinstance(node.get('title', ''), str) or len(node.get('title', '')) > 200:
            raise DAGValidationError("Step titles require bounded text.")
        if node['type'] in _WAIT and 'timeout_days' in node.get('config', {}):
            timeout = node['config']['timeout_days']
            if type(timeout) is not int or not 1 <= timeout <= 30:
                raise DAGValidationError("Condition deadlines require whole days from 1 to 30.")
        if node['type'] == 'like_last_post':
            config = node.get('config', {})
            age = config.get('max_post_age_days', 30)
            if type(age) is not int or not 1 <= age <= 365:
                raise DAGValidationError("Recent-post age requires whole days from 1 to 365.")
            if type(config.get('skip_if_no_posts', True)) is not bool:
                raise DAGValidationError("Skip-if-no-posts requires an explicit boolean.")
    for edge in edges:
        if not isinstance(edge, dict) or not identity(edge.get('source')) or not identity(edge.get('target')):
            raise DAGValidationError("Every connection needs scalar source and target IDs.")


def visual_graph(tree: Any) -> tuple[list[dict], list[dict]]:
    """Bound before recursive traversal; never round or invent IDs/configuration."""
    bounded_json(tree, max_depth=MAX_TREE_DEPTH)
    nodes, edges = [], []

    def visit(steps, parent=None, label=None):
        if not isinstance(steps, list):
            raise DAGValidationError("Visible sequence steps must be a list.")
        previous = parent
        for index, step in enumerate(steps):
            if not isinstance(step, dict) or not identity(step.get('id')) or not isinstance(step.get('type'), str):
                raise DAGValidationError("Every visible step needs a scalar ID and type.")
            if len(nodes) >= MAX_NODES:
                raise DAGValidationError("Visible sequence exceeds 100 steps.")
            hours = step.get('delay_hours', 0)
            if 'delay_days' in step:
                days = step['delay_days']
                if type(days) not in (int, float) or not math.isfinite(days) or not 0 <= days <= 365:
                    raise DAGValidationError("Visible delays require finite numeric days from 0 to 365.")
                product = days * 24
                if not float(product).is_integer():
                    raise DAGValidationError("Visible delays must resolve to whole hours.")
                hours = int(product)
                if 'delay_hours' in step and delay_hours(step['delay_hours']) != hours:
                    raise DAGValidationError("Visible day/hour delays disagree.")
            hours = delay_hours(hours)
            config = step.get('config', {})
            if not isinstance(config, dict):
                raise DAGValidationError("Visible step config must be an object.")
            if 'steps' in step and not isinstance(step['steps'], list):
                raise DAGValidationError("Visible child steps must be a list when present.")
            if step.get('steps'):
                raise DAGValidationError("Nested linear child steps are not displayed by this editor; use the visible step list or branches.")
            if 'endsHere' in step and type(step['endsHere']) is not bool:
                raise DAGValidationError("Visible end markers require booleans.")
            nodes.append({'id': step['id'], 'type': step['type'], 'title': step.get('title', ''), 'delay_hours': hours, 'config': config})
            if previous:
                edges.append({'source': previous, 'target': step['id'], 'label': label if index == 0 and label else ''})
            previous = step['id']
            branches = step.get('branches', {})
            if not isinstance(branches, dict) or set(branches) - {'left', 'right'}:
                raise DAGValidationError("Visible branches must use left/right entries.")
            has_children = bool(step.get('steps')) or any(isinstance(b, dict) and b.get('steps') for b in branches.values())
            if step.get('endsHere') and (has_children or index < len(steps) - 1):
                raise DAGValidationError("An ended visible path cannot contain successor steps.")
            for side, branch in branches.items():
                if not isinstance(branch, dict) or not isinstance(branch.get('steps', []), list):
                    raise DAGValidationError("Visible branch steps must be a list.")
                if 'endsHere' in branch and type(branch['endsHere']) is not bool:
                    raise DAGValidationError("Visible branch end markers require booleans.")
                branch_kind(step['type'], branch.get('condition'))
                if branch.get('endsHere') and branch.get('steps'):
                    raise DAGValidationError("An ended visible branch cannot contain steps.")
                if branch.get('steps'):
                    visit(branch['steps'], step['id'], branch.get('condition'))
            if step.get('steps'):
                visit(step['steps'], step['id'])
    visit(tree)
    return nodes, edges
