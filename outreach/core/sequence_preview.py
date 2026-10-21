"""Bounded authoring analysis and illustrative paths. Never an execution grant."""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Any

from outreach.core.dag_compiler import DAGCompiler, contains_ai_prompt_token, interpolate_template
from outreach.core.sequence_capabilities import sequence_capability_map
from outreach.core.sequence_contract import DAGValidationError, bounded_json, delay_hours, MAX_RENDER_CHARS

CONTRACT_VERSION = 1
WAIT_KINDS = {'connection_request', 'if_connected', 'send_message', 'voice_note'}
STANDARD_VARIABLES = {
    'first_name', 'last_name', 'full_name', 'headline', 'company_name', 'company',
    'job_title', 'position', 'industry', 'location_raw', 'location', 'country',
    'connections_count', 'number_of_connections', 'top_skill', 'company_location',
    'summary', 'school', 'years_in_company', 'years_in_role', 'mutual_connections',
}
_FIELDS = {
    'connection_request': ('note',),
    'send_message': ('body',),
    'voice_note': ('script',),
    'send_email': ('subject', 'body'),
    'comment_last_post': ('comment',),
    'inmail': ('subject', 'body'),
}
_TOKEN = re.compile(r'\{\{\s*([A-Za-z_][A-Za-z0-9_]{0,99})(?:\s*\|\s*(?:\"[^\"{}]{0,200}\"|' + r"'[^'{}]{0,200}'|[^|{}]{1,200}?))?\s*\}\}")


def same_execution_graph(one: dict, two: dict) -> bool:
    if not isinstance(one, dict) or not isinstance(two, dict) or not isinstance(one.get('nodes'), dict) or not isinstance(two.get('nodes'), dict):
        return False
    if one.get('root_node_ids') != two.get('root_node_ids') or one.get('nodes', {}).keys() != two.get('nodes', {}).keys():
        return False
    fields = ('type', 'delay_hours', 'config', 'next_default', 'branches')
    return all(isinstance(one['nodes'][key], dict) and isinstance(two['nodes'][key], dict)
               and all(one['nodes'][key].get(field) == two['nodes'][key].get(field) for field in fields)
               for key in one['nodes'])


def checked_compiled(compiled: dict) -> dict:
    """Validate the frozen graph without changing its stored execution authority."""
    bounded_json(compiled)
    rows = compiled.get('nodes') if isinstance(compiled, dict) else None
    if not isinstance(rows, dict) or not 1 <= len(rows) <= 100:
        raise DAGValidationError('Saved execution graph needs review.')
    nodes, edges = [], []
    for identity, row in rows.items():
        if not isinstance(row, dict) or row.get('id', identity) != identity:
            raise DAGValidationError('Saved execution node identity needs review.')
        # Historical roots started immediately, successors defaulted to 24h.
        # Inspection preserves those defaults; new authored graphs store an int.
        roots = compiled.get('root_node_ids')
        old_default = 0 if isinstance(roots, list) and roots == [identity] else 24
        nodes.append({'id': identity, 'delay_hours': row.get('delay_hours', old_default),
                      **{key: row[key] for key in ('type', 'config') if key in row}})
        branches = row.get('branches', {})
        if not isinstance(branches, dict) or set(branches) - {'positive', 'negative'}:
            raise DAGValidationError('Saved execution branch needs review.')
        for branch, target in branches.items():
            if target is None:
                continue  # Historical explicit terminal, never a target/action.
            edges.append({'source': identity, 'target': target, 'label': branch})
        if row.get('next_default') is not None:
            edges.append({'source': identity, 'target': row['next_default']})
    canonical = DAGCompiler.validate_and_compile(nodes, edges)
    if canonical['root_node_ids'] != compiled.get('root_node_ids'):
        raise DAGValidationError('Saved execution root needs review.')
    return canonical


def timeout_days(node: dict) -> int:
    return node['config'].get('timeout_days', 3 if node['type'] == 'if_connected' else 7)


def content_templates(node: dict, lead: dict | None = None) -> dict[str, str]:
    from outreach.core.dag_compiler import select_step_variant
    defaults = {
        'note': '',
        'body': 'Hi {{first_name}}',
        'script': 'Hey {{first_name}}, saw your work at {{company_name}} and wanted to send a quick voice note!',
        'comment': 'Great insights on this, {{first_name}}!',
        'subject': 'Quick question, {{first_name}}',
    }
    _, effective_config = select_step_variant(node, lead)
    def _resolve_field(cfg: dict, field: str) -> Any:
        if field in cfg:
            return cfg[field]
        if node['type'] == 'inmail' and field == 'body' and 'message' in cfg:
            return cfg['message']
        if node['type'] == 'comment_last_post' and field == 'comment' and 'comment_template' in cfg:
            return cfg['comment_template']
        return '' if node['type'] in {'send_email', 'inmail'} else defaults.get(field, '')
    return {field: _resolve_field(effective_config, field) for field in _FIELDS.get(node['type'], ())}


def all_variant_templates(node: dict) -> list[tuple[str | None, dict[str, str]]]:
    defaults = {
        'note': '',
        'body': 'Hi {{first_name}}',
        'script': 'Hey {{first_name}}, saw your work at {{company_name}} and wanted to send a quick voice note!',
        'comment': 'Great insights on this, {{first_name}}!',
        'subject': 'Quick question, {{first_name}}',
    }
    fields = _FIELDS.get(node['type'], ())
    config = node.get('config') or {}
    variants = config.get('variants')
    if isinstance(variants, list) and variants:
        result = []
        for v in variants:
            if isinstance(v, dict):
                merged = {**config, **v}
                result.append((v.get('id'), {
                    field: (merged[field] if field in merged else (
                        merged['message'] if node['type'] == 'inmail' and field == 'body' and 'message' in merged else (
                        merged['comment_template'] if node['type'] == 'comment_last_post' and field == 'comment' and 'comment_template' in merged else
                        ('' if node['type'] in {'send_email', 'inmail'} else defaults.get(field, ''))
                    )))
                    for field in fields
                }))
        if result:
            return result
    return [(None, content_templates(node))]


def analyze_sequence(compiled: dict) -> dict:
    compiled = checked_compiled(compiled)
    catalog = sequence_capability_map()
    issues, seen = [], set()
    states = {key: {} for key in compiled['nodes']}
    states[compiled['root_node_ids'][0]][('unknown', 'unknown')] = ()

    def issue(code, identity, message, severity, path=()):
        key = (code, identity, severity)
        if key in seen:
            return
        if len(issues) >= 100:
            raise DAGValidationError('Sequence analysis exceeds its issue bound; simplify this graph.')
        seen.add(key)
        issues.append({'code': code, 'node_id': identity, 'message': message, 'severity': severity,
                       'path': list(path[-16:]), 'path_truncated': len(path) > 16})

    for identity in compiled['execution_order']:
        node = compiled['nodes'][identity]
        kind, config = node['type'], node['config']
        if not catalog.get(kind, {}).get('supported'):
            issue('unsupported_step', identity, 'This step has no supported campaign runner.', 'error')
        if contains_ai_prompt_token(config):
            issue('unfinished_ai_prompt', identity, 'Replace the AI prompt marker with reviewed message copy.', 'error')
        for variant_id, copies in all_variant_templates(node):
            if sum(len(value) for value in copies.values() if isinstance(value, str)) > MAX_RENDER_CHARS:
                issue('message_copy_too_large', identity, 'Message copy exceeds the 10,000-character review bound.', 'error')
            for field, text in copies.items():
                if not isinstance(text, str) or field != 'note' and not text.strip():
                    issue('invalid_message_copy', identity, f'{field} needs nonempty text.', 'error')
                    continue
                residue = _TOKEN.sub('', text)
                if '{{' in residue or '}}' in residue:
                    issue('invalid_template_token', identity, 'Use complete supported {{variable_name}} tokens.', 'error')
                if _TOKEN.search(text):
                    issue('sample_fields_required', identity, 'Review variable values and generic/empty fallbacks for your audience.', 'warning')
        if kind in {'send_message', 'voice_note'} and node['branches'].get('positive'):
            issue('work_after_reply_stop', identity, 'Replies stop outreach; a Replied path cannot promise successor work.', 'error')
        for (connected, email), witness in states[identity].items():
            path = (*witness, identity)
            if kind in {'send_message', 'voice_note'}:
                if connected in {'no', 'invited', 'withdrawn'}:
                    issue('message_without_connection_guard', identity, 'Add a positive connection check before messaging this path.', 'error', path)
                elif connected == 'unknown':
                    issue('connection_required_at_execution', identity, 'This path requires a usable existing connection at execution.', 'warning', path)
            if kind == 'connection_request' and connected == 'yes':
                issue('invite_on_connected_path', identity, 'Do not invite a connection on a known connected path.', 'error', path)
            if kind == 'connection_request' and connected == 'invited':
                issue('invite_already_requested_on_path', identity, 'This path already requested a connection; wait for an observation instead of inviting again.', 'error', path)
            if kind == 'connection_request' and connected == 'withdrawn' and node.get('delay_hours', 0) < 504:
                issue('reconnect_before_21_days', identity, 'Withdrawing an invitation and reconnecting requires at least a 21-day (504h) delay.', 'error', path)
            if kind == 'withdraw_invite' and connected == 'yes':
                issue('withdraw_on_connected_path', identity, 'Do not withdraw a connection request on a known connected path.', 'error', path)
            if kind == 'send_email':
                if email == 'no':
                    issue('email_without_availability_guard', identity, 'A negative email path needs new usable-email evidence before sending.', 'error', path)
                elif email == 'unknown':
                    issue('usable_email_required_at_execution', identity, 'This path requires a valid, unsuppressed email at execution.', 'warning', path)
            outgoing = [('default', node['next_default'])] if node['next_default'] else list(node['branches'].items())
            for branch, target in outgoing:
                next_connected, next_email = connected, email
                if kind in {'connection_request', 'if_connected'}:
                    next_connected = ('yes' if branch == 'positive' else
                                      'invited' if kind == 'connection_request' or connected == 'invited' else
                                      'no' if branch == 'negative' else connected)
                elif kind == 'withdraw_invite':
                    next_connected = 'withdrawn'
                if kind == 'if_email_available':
                    next_email = 'yes' if branch == 'positive' else 'no'
                if kind == 'find_email':
                    next_email = 'unknown'
                states[target].setdefault((next_connected, next_email), path)
    return {'contract_version': CONTRACT_VERSION, 'valid': not any(item['severity'] == 'error' for item in issues),
            'issues': issues, 'authority': 'offline_graph_analysis', 'execution_authorized': False}


def validate_pinned_sequence(sequence: dict) -> dict:
    if not isinstance(sequence, dict):
        raise DAGValidationError('Saved sequence needs review.')
    compiled = checked_compiled(sequence.get('compiled_dag'))
    if 'nodes' in sequence or 'edges' in sequence:
        raw = DAGCompiler.validate_and_compile(sequence.get('nodes'), sequence.get('edges'))
        if not same_execution_graph(raw, sequence['compiled_dag']):
            raise DAGValidationError('Saved source and pinned execution graph differ; review a new sequence revision.')
    assessment = analyze_sequence(compiled)
    if not assessment['valid']:
        raise DAGValidationError(next(item['message'] for item in assessment['issues'] if item['severity'] == 'error'))
    return compiled


def due_block_reason(lead: dict, now: datetime) -> str | None:
    due = lead.get('next_action_due_at')
    if due is None:
        return None
    if not isinstance(due, datetime):
        return 'sequence_timing_review_required'
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return 'not_due' if due > now else None


def successor_fields(compiled: dict, next_id: str | None, now: datetime) -> dict:
    if next_id is None:
        return {'current_node_id': None, 'execution_state': 'finished', 'next_action_due_at': None}
    node = compiled.get('nodes', {}).get(next_id)
    if not isinstance(node, dict):
        raise DAGValidationError('Next execution step is missing; review this sequence.')
    delay = delay_hours(node.get('delay_hours', 24))
    return {'current_node_id': next_id, 'execution_state': 'waiting_delay' if delay else 'queued',
            'next_action_due_at': now + timedelta(hours=delay)}


def waiting_start(lead: dict, kind: str, now: datetime) -> datetime | None:
    field = 'waiting_for_connection_at' if kind in {'connection_request', 'if_connected'} else 'waiting_for_reply_at' if kind in {'send_message', 'voice_note'} else None
    value = lead.get(field) if field else None
    if value is None:
        return None
    if isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', value):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            raise DAGValidationError('Saved condition start needs review.') from None
    if not isinstance(value, datetime):
        raise DAGValidationError('Saved condition start needs review.')
    try:
        value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise DAGValidationError('Saved condition start needs review.') from None
    if value > now:
        raise DAGValidationError('Saved condition start is in the future; review its timing.')
    return value


def simulate_sequence(compiled: dict, *, sample: dict | None = None, observations: dict | None = None,
                      condition_values: dict | None = None,
                      initial_connected: str = 'unknown', initial_email_available: str = 'unknown', assume_action_completion: bool = False) -> dict:
    sample = {} if sample is None else sample
    observations = {} if observations is None else observations
    from outreach.core.field_conditions import evaluate, validate_samples
    condition_values = {} if condition_values is None else condition_values
    bounded_json({'sample': sample, 'observations': observations, 'condition_values': condition_values})
    validate_samples(condition_values)
    if (not isinstance(sample, dict) or not isinstance(observations, dict) or len(observations) > 100
            or initial_connected not in ('yes', 'no', 'unknown') or initial_email_available not in ('yes', 'no', 'unknown')
            or type(assume_action_completion) is not bool):
        raise DAGValidationError('Preview requires bounded sample data and explicit typed assumptions.')
    allowed = STANDARD_VARIABLES | {'email', 'custom_variables'}
    if set(sample) - allowed or any(value is not None and not isinstance(value, str) for key, value in sample.items() if key != 'custom_variables'):
        raise DAGValidationError('Sample fields must be text and use the supported variable names.')
    custom = sample.get('custom_variables', {})
    if not isinstance(custom, dict) or len(custom) > 50 or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,99}', k) for k, v in custom.items()):
        raise DAGValidationError('Sample custom variables require bounded text keys and values.')
    compiled = checked_compiled(compiled)
    for identity, observation in observations.items():
        node = compiled['nodes'].get(identity)
        if not node or node['type'] not in WAIT_KINDS | {'if_email_available'} or observation not in ('yes', 'no', 'unknown', 'deadline_no', 'deadline_unknown'):
            raise DAGValidationError('An observation refers to an invalid step or value.')
        if node['type'] == 'if_email_available' and observation not in ('yes', 'no', 'unknown'):
            raise DAGValidationError('Email availability is an immediate usable-email policy observation.')
    analysis = analyze_sequence(compiled)
    steps, assumptions = [], []
    connected, email = initial_connected, initial_email_available
    identity = compiled['root_node_ids'][0]
    configured_hours = wait_hours = 0
    ending = 'finished'
    if not analysis['valid']:
        return {**analysis, 'steps': [], 'ending': 'invalid_graph', 'assumptions': [], 'configured_delay_hours': 0, 'assumed_wait_hours': 0}
    while identity:
        node = compiled['nodes'][identity]
        kind = node['type']
        configured_hours += node['delay_hours']
        step = {'node_id': identity, 'type': kind, 'configured_delay_hours': node['delay_hours'], 'status': 'would_attempt'}
        steps.append(step)
        if kind == 'has_data_in_column':
            decision = evaluate(node['config'], condition_values)
            step['condition_reason'] = decision['reason']
            if decision['condition_met'] is None:
                step['status'] = ending = 'needs_review'
                break
            branch = 'positive' if decision['condition_met'] else 'negative'
            step['status'] = 'evaluated_branch'
            step['branch'] = branch
            identity = node['branches'].get(branch)
            continue
        if kind == 'if_connected' and not node['branches']:
            step['status'] = 'terminal_condition'
            break  # No saved path to choose, matching the existing terminal runner.
        if kind in {'send_message', 'voice_note'} and connected != 'yes':
            step['status'] = ending = 'connection_required'
            break
        if kind == 'connection_request' and connected == 'yes':
            step['status'] = ending = 'already_connected'
            break
        if kind == 'send_email' and email != 'yes':
            step['status'] = ending = 'usable_email_required'
            break
        rendered = {}
        missing = []
        for field, template in content_templates(node).items():
            text = interpolate_template(template, sample)
            if _TOKEN.search(text):
                missing.extend(_TOKEN.findall(text))
            rendered[field] = {'text': text[:2000], 'truncated': len(text) > 2000}
        if rendered:
            step['content'] = rendered
        if missing:
            step['status'] = ending = 'sample_variables_missing'; step['missing_variables'] = sorted(set(missing))
            break
        if kind not in {'if_connected', 'if_email_available'}:
            if not assume_action_completion:
                ending = 'await_action_outcome'
                break
            assumptions.append({'node_id': identity, 'kind': 'action_completes_successfully'})
            step['assumed_completion'] = True
            if kind == 'find_email':
                email = 'unknown'
            if kind == 'connection_request':
                connected = 'invited'
        branches = node['branches']
        if kind == 'if_email_available' or kind in WAIT_KINDS and branches:
            observed = observations.get(identity, 'unknown')
            step['assumed_observation'] = observed
            if observed in {'unknown', 'deadline_unknown'}:
                step['status'] = ending = 'needs_review' if observed == 'deadline_unknown' else 'waiting_for_observation'
                break
            if kind != 'if_email_available' and observed == 'no':
                step['status'] = ending = 'waiting_for_deadline'
                break
            if kind in {'send_message', 'voice_note'} and observed == 'yes':
                step['status'] = ending = 'stopped_on_reply'
                break
            branch = 'positive' if observed == 'yes' else 'negative'
            if observed == 'deadline_no':
                elapsed = timeout_days(node) * 24
                wait_hours += elapsed; step['assumed_wait_hours'] = elapsed
            if kind in {'connection_request', 'if_connected'}:
                connected = 'yes' if branch == 'positive' else 'invited' if connected == 'invited' else 'no'
            if kind == 'if_email_available':
                email = 'yes' if branch == 'positive' else 'no'
            step['status'] = 'assumed_branch'; step['branch'] = branch
            identity = branches.get(branch)
        else:
            identity = node['next_default']
    return {**analysis, 'steps': steps, 'ending': ending, 'assumptions': assumptions,
            'configured_delay_hours': configured_hours, 'assumed_wait_hours': wait_hours,
            'timing_basis': 'configured_delays_and_supplied_assumptions_not_live_schedule', 'provider_outcomes_verified': False}
