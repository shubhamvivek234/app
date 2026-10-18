"""Reviewed template graph replacement under current workspace authority.

The shared transaction writes native authority counters and one template row.
Current audit fields are not immutable history or durable outcome receipts;
unknown commits must not be automatically replayed with a newer review.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import re
from typing import Any

from bson import BSON, Int64, ObjectId
from fastapi import HTTPException

from outreach.core import template_governance as governance
from outreach.core.authorization import canonical_hash
from outreach.core.dag_compiler import DAGCompiler
from outreach.core.lead_tags import unique_resource
from outreach.core.sequence_contract import bounded_json, visual_graph, DAGValidationError
from outreach.core.sequence_preview import analyze_sequence, same_execution_graph, checked_compiled
from outreach.core.suppression import SuppressionUnavailable, mutate_suppression
from outreach.core.template_saves import input_digest, MAX_INPUT_BYTES
from outreach.core.workspace_scope import workspace_scope


def _require_browser_values(value: Any) -> None:
    """Require plain JSON values within the bounded browser numeric range."""
    pending = [value]
    while pending:
        current = pending.pop()
        if type(current) is dict:
            pending.extend(current.values())
        elif type(current) is list:
            pending.extend(current)
        elif type(current) in {int, Int64, float}:
            if abs(current) > governance.MAX_REVISION:
                raise DAGValidationError('Template numeric value is not browser-safe')
        elif current is not None and type(current) not in {str, bool}:
            raise DAGValidationError('Template values require plain JSON types')


def compile_graph(graph: dict) -> dict:
    """Use the existing compiler/semantic/visual contract, with mandatory tree."""
    try:
        if (type(graph) is not dict or set(graph) != {'nodes', 'edges', 'tree'}
                or type(graph['tree']) is not list or not 1 <= len(graph['tree']) <= 100):
            raise DAGValidationError('A complete visible graph is required')
        bounded_json(graph)
        # Template authoring passes through JavaScript JSON. Reject values it
        # cannot represent faithfully rather than silently rounding originals.
        _require_browser_values(graph)
        compiled = DAGCompiler.validate_and_compile(graph['nodes'], graph['edges'])
        nodes, edges = visual_graph(graph['tree'])
        visible = DAGCompiler.validate_and_compile(nodes, edges)
        if not same_execution_graph(compiled, visible):
            raise DAGValidationError('Visible and execution graphs disagree')
        analysis = analyze_sequence(compiled)
        if not analysis['valid']:
            raise DAGValidationError('Sequence semantics need review')
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
        raise HTTPException(422, 'Template graph needs a complete valid visible sequence') from None
    return {**deepcopy(graph), 'compiled_dag': compiled, 'compiler_contract_version': 1}


def prepare_graph(content: str) -> dict:
    """Bind exact UTF-8 JSON, rejecting duplicate object keys before compilation."""
    if type(content) is not str:
        raise HTTPException(422, 'Template graph input must be frozen JSON text')
    digest = input_digest(content)

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate graph key')
            result[key] = value
        return result

    try:
        graph = json.loads(content, object_pairs_hook=pairs)
    except (ValueError, RecursionError):
        raise HTTPException(422, 'Template graph input is invalid') from None
    prepared = compile_graph(graph)
    return {'document': prepared, 'input_digest': digest, 'graph_digest': canonical_hash(prepared['compiled_dag'])}


def graph_scope(workspace: str, actor: str, uid: str) -> str:
    """Correlate a graph review with its admitted original actor/UID/scope."""
    if any(type(value) is not str or not value.strip() or not 1 <= len(value) <= 200
           for value in (workspace, actor, uid)):
        raise HTTPException(403, 'Template graph access is unavailable')
    return canonical_hash(['template-graph-scope-v1', workspace, actor, uid])


def graph_review(row: dict, workspace: str, actor: str, uid: str) -> dict:
    """Pure full-original review; current write authority is checked separately."""
    unavailable = {'contract_version': 1, 'reviewable': False, 'workspace_id': workspace,
        'revision': None, 'identity_digest': None, 'review_digest': None, 'scope_digest': None,
        'update_authorized': False, 'execution_authorized': False}
    try:
        scope = graph_scope(workspace, actor, uid)
        review = governance.template_review(row, workspace)
        if (not review['reviewable'] or review['revision'] >= governance.MAX_REVISION
                or any(type(row.get(key)) is not str for key in ('id', 'workspace_id', 'user_id'))
                or not (type(row.get('_id')) is str or isinstance(row.get('_id'), ObjectId))):
            return unavailable
        original = compile_graph({key: row.get(key) for key in ('nodes','edges','tree')})
        if ('compiled_dag' in row) != ('compiler_contract_version' in row):
            return unavailable
        if 'compiled_dag' in row:
            if type(row.get('compiler_contract_version')) is not int or row['compiler_contract_version'] != 1:
                return unavailable
            checked_compiled(row['compiled_dag'])
            _require_browser_values(row['compiled_dag'])
            if canonical_hash(original['compiled_dag']) != canonical_hash(row['compiled_dag']):
                return unavailable
    except (HTTPException, ValueError, AttributeError, TypeError):
        return unavailable
    return {**unavailable, 'reviewable': True, 'revision': review['revision'],
        'identity_digest': review['identity_digest'], 'review_digest': review['review_digest'], 'scope_digest': scope}


def prepare_graph_operation(workspace: str, actor: str, authenticated_uid: str, template_id: str,
                            revision: int, review_digest: str, identity_digest: str, scope_digest: str) -> dict:
    """Validate the original graph review without compiling new graph content."""
    if (type(template_id) is not str or not re.fullmatch(r'tpl_custom_[0-9a-f]{10}', template_id)
            or type(revision) is not int or not 0 <= revision < governance.MAX_REVISION
            or any(type(value) is not str or not re.fullmatch(r'[0-9a-f]{64}', value)
                   for value in (review_digest, identity_digest, scope_digest))):
        raise HTTPException(422, 'A current template graph review is required')
    if scope_digest != graph_scope(workspace, actor, authenticated_uid):
        raise HTTPException(403, 'Template graph account or workspace changed')
    return {'contract_version': 1, 'workspace_id': workspace, 'template_id': template_id,
        'revision': revision, 'review_digest': review_digest, 'identity_digest': identity_digest, 'scope_digest': scope_digest}


async def _replace_graph(current: Any, workspace: str, actor: str, authenticated_uid: str,
                         operation: dict, prepared: dict, timestamp: datetime) -> dict:
    """Apply only within the caller's shared guard and current authority fence.

    Both callers validate the operation and prepared graph before this helper.
    Its exceptions propagate through the owning transaction, including a later
    receipt failure. prepared.input_digest belongs to that caller's contract:
    graph-only JSON for legacy PATCH, whole-operation JSON for recoverable POST.
    """
    template_id = operation['template_id']
    captured = {key: operation[key] for key in ('contract_version', 'workspace_id',
        'revision', 'review_digest', 'identity_digest', 'scope_digest')}
    row = await unique_resource(current.outreach_templates, workspace, template_id)
    if row is None:
        raise HTTPException(404, 'Reviewed template is unavailable; reload before editing')
    reviewed = graph_review(row, workspace, actor, authenticated_uid)
    if not reviewed['reviewable'] or any(reviewed[key] != value for key,value in captured.items()):
        raise HTTPException(409, 'Template changed; reload before editing its graph')
    fields = {**deepcopy(prepared['document']), 'template_revision': operation['revision'] + 1,
        'graph_updated_at': timestamp, 'graph_updated_by': actor}
    expected = {**deepcopy(row), **fields}
    result_review = governance.template_review(expected, workspace)
    if not result_review['reviewable']:
        raise HTTPException(422, 'Updated template exceeds the supported full-record bound')
    query = {**workspace_scope(workspace), 'id': template_id, '_id': row['_id'],
        '$expr': {'$eq': ['$$ROOT', {'$literal': deepcopy(row)}]}}
    result = await current.outreach_templates.replace_one(query, deepcopy(expected))
    if result.matched_count != 1:
        raise HTTPException(409, 'Template changed; reload before editing its graph')
    saved = await current.outreach_templates.find_one({**workspace_scope(workspace), '_id': row['_id']})
    if saved is None or BSON.encode(saved) != BSON.encode(expected):
        raise HTTPException(409, 'Could not verify updated template graph')
    return {**captured, 'status': 'updated', 'template_id': template_id,
        'input_digest': prepared['input_digest'], 'graph_digest': prepared['graph_digest'],
        'new_revision': operation['revision'] + 1, 'new_review_digest': result_review['review_digest']}


async def update_graph(db: Any, workspace: str, actor: str, template_id: str,
                       revision: int, review_digest: str, identity_digest: str,
                       graph_json: str, input_digest: str, *, authenticated_uid: str, scope_digest: str) -> dict:
    """Retain the legacy reviewed PATCH's graph-only input and receipt semantics."""
    if type(input_digest) is not str or not re.fullmatch(r'[0-9a-f]{64}', input_digest):
        raise HTTPException(422, 'A current template graph review is required')
    operation = prepare_graph_operation(workspace, actor, authenticated_uid, template_id,
        revision, review_digest, identity_digest, scope_digest)
    prepared = prepare_graph(graph_json)
    if prepared['input_digest'] != input_digest:
        raise HTTPException(422, 'Template graph input changed')
    now = datetime.now(timezone.utc)
    timestamp = now.replace(microsecond=now.microsecond // 1000 * 1000)
    async def update(current):
        await governance.authorize_update(current, actor, authenticated_uid)
        return await _replace_graph(current, workspace, actor, authenticated_uid, operation, prepared, timestamp)
    try:
        return await mutate_suppression(db, workspace, update)
    except SuppressionUnavailable:
        raise HTTPException(503, 'Template graph update is unconfirmed. Reload and review before another edit.') from None
