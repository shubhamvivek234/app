"""
Phase 4: Sequences API router.
Supports sequence graph validation, compiling, saving, and template retrieval.
"""
import logging
import re
from typing import Any, Literal
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field, ConfigDict, StrictBool, StrictInt, StrictStr
from motor.motor_asyncio import AsyncIOMotorDatabase

from db.mongo import get_db
from api.deps import get_current_user
from outreach.api.dependencies import get_outreach_user, require_outreach_permission, workspace_id
from outreach.core.dag_compiler import DAGCompiler, DAGValidationError
from outreach.core.sequence_versions import load_sequence, publish_sequence
from outreach.core.sequence_contract import bounded_json, visual_graph
from outreach.core.sequence_preview import analyze_sequence, same_execution_graph, simulate_sequence
from outreach.core.authorization import canonical_hash
from outreach.core.template_governance import MAX_REVISION, scoped_review, delete_template, create_template
from outreach.core.workspace_scope import workspace_scope
from outreach.core.template_access import inspect_access, describe_access
from outreach.core import template_saves, template_metadata, template_graphs, template_metadata_updates, template_graph_updates, template_deletions
from outreach.core import template_history, template_snapshot_reads

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sequences", tags=["LinkedIn Outreach Sequences"])


def _user_id(current_user: dict) -> str:
    return str(current_user.get("user_id") or current_user.get("id") or current_user.get("_id") or "")


def _workspace_id(current_user: dict) -> str:
    return str(
        current_user.get("default_workspace_id")
        or current_user.get("current_workspace_id")
        or current_user.get("workspace_id")
        or _user_id(current_user)
    )


def _campaign_filter(campaign_id: str, current_user: dict) -> dict[str, Any]:
    return {
        "id": campaign_id,
        "is_deleted": {"$ne": True},
        "workspace_id": _workspace_id(current_user),
    }


class ValidateSequenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodes: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    edges: list[dict[str, Any]] = Field(max_length=200)
    tree: list[dict[str, Any]] | None = Field(default=None, max_length=100)


class SaveSequenceRequest(ValidateSequenceRequest):
    campaign_id: str = Field(min_length=1, max_length=200)


class LiveEditSequenceRequest(SaveSequenceRequest):
    reengage_completed_leads: StrictBool = True
    resume_failed_on_deleted_steps: StrictBool = True
    node_mapping: dict[str, str] | None = Field(default=None)
    sender_mapping: dict[str, str] | None = Field(default=None)


class SaveTemplateRequest(ValidateSequenceRequest):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default="", max_length=1000)
    add_to_team_templates: bool = Field(default=True, description="Share template across all workspace team members")


class DeleteTemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: StrictInt = Field(ge=1, le=1)
    workspace_id: StrictStr = Field(min_length=1, max_length=200)
    revision: StrictInt = Field(ge=0, le=MAX_REVISION)
    review_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    identity_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    scope_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class RecoverableTemplateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    contract_version: StrictInt = Field(ge=1, le=1)
    workspace_id: StrictStr = Field(min_length=1, max_length=200)
    scope_digest: StrictStr = Field(pattern=r'^[0-9a-f]{64}$')
    request_id: StrictStr = Field(pattern='^'+template_saves.UUID_PATTERN+'$')
    input_digest: StrictStr = Field(pattern=r'^[0-9a-f]{64}$')
    content_json: StrictStr = Field(min_length=1, max_length=template_saves.MAX_INPUT_BYTES)


class EditTemplateMetadataRequest(DeleteTemplateRequest):
    revision: StrictInt = Field(ge=0, lt=MAX_REVISION)
    name: StrictStr = Field(min_length=1, max_length=100)
    description: StrictStr = Field(max_length=1000)


class RecoverableMetadataUpdateRequest(RecoverableTemplateRequest):
    content_json: StrictStr = Field(min_length=1, max_length=template_metadata_updates.MAX_INPUT_BYTES)


class RecoverableDeletionRequest(RecoverableTemplateRequest):
    content_json: StrictStr = Field(min_length=1, max_length=template_deletions.MAX_INPUT_BYTES)


class EditTemplateGraphRequest(DeleteTemplateRequest):
    revision: StrictInt = Field(ge=0, lt=MAX_REVISION)
    graph_json: StrictStr = Field(min_length=1, max_length=template_graphs.MAX_INPUT_BYTES)
    input_digest: StrictStr = Field(pattern=r'^[0-9a-f]{64}$')


class PreviewSequenceRequest(ValidateSequenceRequest):
    request_scope: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    sample: dict[str, Any] = Field(default_factory=dict, max_length=50)
    condition_values: dict[str, Any] = Field(default_factory=dict, max_length=9)
    observations: dict[str, Literal['yes', 'no', 'unknown', 'deadline_no', 'deadline_unknown']] = Field(default_factory=dict, max_length=100)
    initial_connected: Literal['yes', 'no', 'unknown'] = 'unknown'
    initial_email_available: Literal['yes', 'no', 'unknown'] = 'unknown'
    assume_action_completion: StrictBool = False


def _compile_visual_tree(tree: list[dict[str, Any]]) -> dict[str, Any]:
    nodes, edges = visual_graph(tree)
    return DAGCompiler.validate_and_compile(nodes, edges)


_same_execution_graph = same_execution_graph


def _authoring_graph(req: ValidateSequenceRequest) -> tuple[dict, dict]:
    bounded_json(req.model_dump())
    compiled = DAGCompiler.validate_and_compile(req.nodes, req.edges)
    if req.tree is not None and not same_execution_graph(_compile_visual_tree(req.tree), compiled):
        raise DAGValidationError("Visible sequence does not match its execution steps. Save the editor again.")
    return compiled, analyze_sequence(compiled)


def _require_executable_analysis(analysis: dict) -> None:
    if not analysis['valid']:
        raise DAGValidationError(next(item['message'] for item in analysis['issues'] if item['severity'] == 'error'))


@router.get("/templates")
async def get_sequence_templates(
    current_user: dict | None = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase | None = Depends(get_db),
):
    """Inspect starter and workspace templates without granting execution."""
    if db is None or current_user is None:
        raise HTTPException(503, "Sequence templates are unavailable. Please retry.")
    try:
        access = await inspect_access(db, _workspace_id(current_user), current_user.get('user_id'), current_user.get('firebase_uid'))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'Sequence templates are unavailable. Please retry.') from None
    templates = [{**row, 'workspace_access': describe_access(access, row, custom=False, actor=current_user['user_id'])}
                 for row in DAGCompiler.get_prebuilt_templates()]
    if db is not None and current_user is not None:
        try:
            ws_id = _workspace_id(current_user)
            cursor = db.outreach_templates.find(workspace_scope(ws_id)).sort("created_at", -1)
            custom_templates = await cursor.to_list(length=100)
            for doc in custom_templates:
                templates.append({**{key: value for key, value in doc.items() if key != "_id"},
                    "deletion_review": scoped_review(doc, ws_id, current_user.get("user_id"), current_user.get("firebase_uid")),
                    "metadata_review": template_metadata.metadata_review(doc, ws_id, current_user.get("user_id"), current_user.get("firebase_uid")),
                    "graph_review": template_graphs.graph_review(doc, ws_id, current_user.get("user_id"), current_user.get("firebase_uid")),
                    'workspace_access': describe_access(access, doc, custom=True, actor=current_user['user_id'])})
        except Exception:
            logger.warning("Could not load workspace sequence templates")
            raise HTTPException(503, "Sequence templates are unavailable. Please retry.") from None

    inspected = []
    for template in templates:
        try:
            _, compatibility = _authoring_graph(ValidateSequenceRequest(
                nodes=template.get('nodes'), edges=template.get('edges'), tree=template.get('tree')))
            compatibility['configuration_available'] = compatibility['valid'] and bool(template.get('tree'))
            if not template.get('tree'):
                compatibility['error'] = 'Saved template has no editable visual sequence. Review it before use.'
        except (ValueError, TypeError, AttributeError):
            compatibility = {'contract_version': 1, 'valid': False, 'issues': [],
                'error': 'Saved template structure needs review.', 'execution_authorized': False,
                'configuration_available': False}
        inspected.append({**template, 'compatibility': compatibility})
    return inspected


@router.get('/templates/{template_id}/revision-checkpoints')
async def get_template_history(template_id: str, request: Request, identity_digest: str = Query(...),
    page_size: str = Query('20'), cursor: str | None = Query(None),
    current_user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    # Permission and open-workspace checks belong to the guarded snapshot below.
    allowed = {'identity_digest', 'page_size', 'cursor'}
    pairs = list(request.query_params.multi_items())
    if (any(key not in allowed for key, _ in pairs) or len(pairs) != len({key for key, _ in pairs})
            or not re.fullmatch(r'(?:[1-9]|1[0-9]|2[0-5])', page_size)):
        raise HTTPException(422, 'Invalid template history query')
    result = await template_history.read_history(db, workspace_id(current_user), current_user.get('user_id'),
        current_user.get('firebase_uid'), template_id, identity_digest, page_size=int(page_size), cursor=cursor)
    return JSONResponse(result, headers={'Cache-Control': 'no-store'})


class _SnapshotContentRoute(APIRoute):
    """Keep dependency, validation and handler responses private on this route."""
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def dispatch(request):
            try:
                response = await handler(request)
            except RequestValidationError as error:
                response = await request_validation_exception_handler(request, error)
            except StarletteHTTPException as error:
                raise StarletteHTTPException(error.status_code, error.detail,
                    headers={**(error.headers or {}), **template_snapshot_reads.RESPONSE_HEADERS}) from None
            except Exception:
                response = JSONResponse({'detail': 'Recorded template content is unavailable'}, status_code=503)
            response.headers.update(template_snapshot_reads.RESPONSE_HEADERS)
            return response
        return dispatch


async def get_template_snapshot_content(template_id: str, checkpoint_id: str, request: Request,
    identity_digest: str = Query(...), history_digest: str = Query(...),
    current_user: dict = Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    # Current permission/UID/erasure admission belongs to the owning snapshot.
    pairs = list(request.query_params.multi_items())
    if (any(key not in {'identity_digest', 'history_digest'} for key, _ in pairs)
            or len(pairs) != len({key for key, _ in pairs})):
        raise HTTPException(422, 'Invalid recorded content query')
    result = await template_snapshot_reads.read_content(db, workspace_id(current_user),
        current_user.get('user_id'), current_user.get('firebase_uid'), template_id,
        identity_digest, checkpoint_id, history_digest)
    return JSONResponse(result, headers=template_snapshot_reads.RESPONSE_HEADERS)


router.add_api_route('/templates/{template_id}/revision-checkpoints/{checkpoint_id}/content',
    get_template_snapshot_content, methods=['GET'], route_class_override=_SnapshotContentRoute)


@router.post("/templates")
async def save_custom_template(
    req: SaveTemplateRequest,
    current_user: dict = require_outreach_permission('sequence:create'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Saves an outreach sequence graph as a reusable custom template."""
    try:
        compiled_dag, analysis = _authoring_graph(req)
        _require_executable_analysis(analysis)
    except DAGValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    import uuid
    user_id = _user_id(current_user)
    ws_id = _workspace_id(current_user)
    template_id = f"tpl_custom_{uuid.uuid4().hex[:10]}"

    doc = {
        "id": template_id,
        "name": req.name,
        "description": req.description or f"Custom template saved from {req.name}",
        "user_id": user_id,
        "workspace_id": ws_id,
        "uses": "—",
        "acceptance": "—",
        "reply": "—",
        "is_custom": True,
        "nodes": req.nodes,
        "edges": req.edges,
        "tree": req.tree,
        "compiled_dag": compiled_dag,
        "compiler_contract_version": 1,
        "created_at": datetime.now(timezone.utc),
    }
    saved = await create_template(db, ws_id, current_user.get("user_id"), doc,
                                  authenticated_uid=current_user.get("firebase_uid"))
    return {"status": "success", "template": saved}


@router.delete("/templates/{template_id}")
@router.delete("/templates/{template_id}/reviewed")
async def delete_custom_template(
    template_id: str,
    req: DeleteTemplateRequest,
    current_user: dict = require_outreach_permission('sequence:delete'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Delete only the native template reviewed under current authority."""
    ws_id = _workspace_id(current_user)
    if req.workspace_id != ws_id:
        raise HTTPException(403, "Template review workspace changed; reload before deleting")
    return await delete_template(db, ws_id, current_user.get("user_id"), template_id,
        req.revision, req.review_digest, req.identity_digest,
        authenticated_uid=current_user.get("firebase_uid"), scope_digest=req.scope_digest)


@router.patch('/templates/{template_id}/metadata-reviewed')
async def edit_custom_template_metadata(template_id: str, req: EditTemplateMetadataRequest,
    current_user: dict = require_outreach_permission('sequence:update'),
    db: AsyncIOMotorDatabase = Depends(get_db)):
    """Change only reviewed metadata; original graphs and campaign copies remain."""
    workspace = _workspace_id(current_user)
    if req.workspace_id != workspace:
        raise HTTPException(403, 'Template review workspace changed; reload before editing')
    return await template_metadata.update_metadata(db, workspace, current_user.get('user_id'), template_id,
        req.revision, req.review_digest, req.identity_digest, req.name, req.description,
        authenticated_uid=current_user.get('firebase_uid'), scope_digest=req.scope_digest)


@router.patch('/templates/{template_id}/graph-reviewed')
async def edit_custom_template_graph(template_id: str, req: EditTemplateGraphRequest,
    current_user: dict = require_outreach_permission('sequence:update'),
    db: AsyncIOMotorDatabase = Depends(get_db)):
    """Update only one original reviewed template graph under current authority."""
    workspace = _workspace_id(current_user)
    if req.workspace_id != workspace:
        raise HTTPException(403, 'Template graph review workspace changed')
    return await template_graphs.update_graph(db, workspace, current_user.get('user_id'), template_id,
        req.revision, req.review_digest, req.identity_digest, req.graph_json, req.input_digest,
        authenticated_uid=current_user.get('firebase_uid'), scope_digest=req.scope_digest)


@router.get('/template-deletions/context')
async def template_deletion_context(current_user: dict = require_outreach_permission('sequence:delete')):
    return template_deletions.deletion_context(_workspace_id(current_user),
        current_user.get('user_id'), current_user.get('firebase_uid'))


@router.get('/template-deletions/{request_id}')
async def inspect_template_deletion(request_id: str,
    workspace_id: str = Query(min_length=1, max_length=200),
    scope_digest: str = Query(pattern=r'^[0-9a-f]{64}$'),
    input_digest: str = Query(pattern=r'^[0-9a-f]{64}$'),
    current_user: dict = require_outreach_permission('sequence:delete'),
    db: AsyncIOMotorDatabase = Depends(get_db)):
    workspace = _workspace_id(current_user)
    if workspace != workspace_id:
        raise HTTPException(403, 'Original template deletion workspace changed')
    return await template_deletions.inspect_deletion(db, workspace, current_user.get('user_id'),
        current_user.get('firebase_uid'), request_id, scope_digest, input_digest)


@router.post('/template-deletions')
async def save_template_deletion(req: RecoverableDeletionRequest,
    current_user: dict = require_outreach_permission('sequence:delete'),
    db: AsyncIOMotorDatabase = Depends(get_db)):
    workspace = _workspace_id(current_user)
    if workspace != req.workspace_id:
        raise HTTPException(403, 'Original template deletion workspace changed')
    return await template_deletions.save_deletion(db, workspace, current_user.get('user_id'),
        current_user.get('firebase_uid'), req.request_id, req.scope_digest, req.content_json, req.input_digest)


@router.get('/template-graph-updates/context')
async def template_graph_update_context(current_user: dict = require_outreach_permission('sequence:update')):
    return template_graph_updates.update_context(_workspace_id(current_user),
        current_user.get('user_id'), current_user.get('firebase_uid'))


@router.get('/template-graph-updates/{request_id}')
async def inspect_template_graph_update(request_id: str,
    workspace_id: str = Query(min_length=1, max_length=200),
    scope_digest: str = Query(pattern=r'^[0-9a-f]{64}$'),
    input_digest: str = Query(pattern=r'^[0-9a-f]{64}$'),
    current_user: dict = require_outreach_permission('sequence:update'),
    db: AsyncIOMotorDatabase = Depends(get_db)):
    workspace = _workspace_id(current_user)
    if workspace_id != workspace:
        raise HTTPException(403, 'Template update workspace changed')
    return await template_graph_updates.inspect_update(db, workspace, current_user.get('user_id'),
        current_user.get('firebase_uid'), request_id, scope_digest, input_digest)


@router.post('/template-graph-updates')
async def save_template_graph_update(req: RecoverableTemplateRequest,
    current_user: dict = require_outreach_permission('sequence:update'),
    db: AsyncIOMotorDatabase = Depends(get_db)):
    workspace = _workspace_id(current_user)
    if req.workspace_id != workspace:
        raise HTTPException(403, 'Template update workspace changed')
    return await template_graph_updates.save_update(db, workspace, current_user.get('user_id'),
        current_user.get('firebase_uid'), req.request_id, req.scope_digest, req.content_json, req.input_digest)


@router.get('/template-metadata-updates/context')
async def template_metadata_update_context(current_user: dict = require_outreach_permission('sequence:update')):
    return template_metadata_updates.update_context(_workspace_id(current_user),
        current_user.get('user_id'), current_user.get('firebase_uid'))


@router.get('/template-metadata-updates/{request_id}')
async def inspect_template_metadata_update(request_id: str,
    workspace_id: str = Query(min_length=1, max_length=200),
    scope_digest: str = Query(pattern=r'^[0-9a-f]{64}$'),
    input_digest: str = Query(pattern=r'^[0-9a-f]{64}$'),
    current_user: dict = require_outreach_permission('sequence:update'),
    db: AsyncIOMotorDatabase = Depends(get_db)):
    workspace = _workspace_id(current_user)
    if workspace_id != workspace:
        raise HTTPException(403, 'Template update workspace changed')
    return await template_metadata_updates.inspect_update(db, workspace, current_user.get('user_id'),
        current_user.get('firebase_uid'), request_id, scope_digest, input_digest)


@router.post('/template-metadata-updates')
async def save_template_metadata_update(req: RecoverableMetadataUpdateRequest,
    current_user: dict = require_outreach_permission('sequence:update'),
    db: AsyncIOMotorDatabase = Depends(get_db)):
    workspace = _workspace_id(current_user)
    if req.workspace_id != workspace:
        raise HTTPException(403, 'Template update workspace changed')
    return await template_metadata_updates.save_update(db, workspace, current_user.get('user_id'),
        current_user.get('firebase_uid'), req.request_id, req.scope_digest, req.content_json, req.input_digest)


@router.get('/template-saves/context')
async def template_save_context(current_user: dict = require_outreach_permission('sequence:create')):
    return template_saves.save_context(_workspace_id(current_user), current_user.get('user_id'), current_user.get('firebase_uid'))


@router.get('/template-saves/{request_id}')
async def inspect_template_save(request_id: str,
    workspace_id: str = Query(min_length=1, max_length=200),
    scope_digest: str = Query(pattern=r'^[0-9a-f]{64}$'),
    current_user: dict = require_outreach_permission('sequence:create'),
    db: AsyncIOMotorDatabase = Depends(get_db)):
    ws = _workspace_id(current_user)
    if workspace_id != ws:
        raise HTTPException(403, 'Template save workspace changed')
    return await template_saves.inspect_save(db, ws, current_user.get('user_id'),
        current_user.get('firebase_uid'), request_id, scope_digest)


@router.post('/template-saves')
async def save_recoverable_template(req: RecoverableTemplateRequest,
    current_user: dict = require_outreach_permission('sequence:create'),
    db: AsyncIOMotorDatabase = Depends(get_db)):
    ws = _workspace_id(current_user)
    if req.workspace_id != ws:
        raise HTTPException(403, 'Template save workspace changed')

    def build():
        # Parsing/compilation is deliberately inside the new-request branch;
        # completed original receipts remain readable across compiler changes.
        try:
            original = SaveTemplateRequest.model_validate_json(req.content_json)
            compiled, analysis = _authoring_graph(original)
            _require_executable_analysis(analysis)
        except (ValueError, TypeError, RecursionError) as exc:
            raise HTTPException(400, 'Template structure needs review before saving') from exc
        import uuid
        return {'id': 'tpl_custom_'+uuid.uuid4().hex[:10], 'name': original.name,
            'description': original.description or '', 'user_id': current_user.get('user_id'),
            'workspace_id': ws, 'is_custom': True, 'uses': '—', 'acceptance': '—', 'reply': '—',
            'nodes': original.nodes, 'edges': original.edges, 'tree': original.tree,
            'compiled_dag': compiled, 'compiler_contract_version': 1, 'created_at': datetime.now(timezone.utc)}

    return await template_saves.save_template(db, ws, current_user.get('user_id'),
        current_user.get('firebase_uid'), req.request_id, req.scope_digest,
        req.content_json, req.input_digest, build)


@router.post("/validate", dependencies=[require_outreach_permission("sequence:update")])
async def validate_sequence(req: ValidateSequenceRequest):
    """
    Validates a sequence topology before launching.
    Detects cycles, invalid branching, or disconnected nodes.
    """
    try:
        compiled, analysis = _authoring_graph(req)
        return {**analysis, "compiled": compiled}
    except DAGValidationError as exc:
        return {"valid": False, "contract_version": 1, "execution_authorized": False, "error": str(exc)}


def preview_scope(user: dict) -> str:
    return canonical_hash(['sequence-preview-v1', _workspace_id(user), _user_id(user)])


@router.get("/preview-context")
async def preview_context(current_user: dict = require_outreach_permission('sequence:update')):
    return {"contract_version": 1, "request_scope": preview_scope(current_user)}


@router.post("/preview")
async def preview_sequence(req: PreviewSequenceRequest,
        current_user: dict = require_outreach_permission('sequence:update')):
    """Pure supplied-data simulation after resolved role/workspace admission."""
    if req.request_scope != preview_scope(current_user):
        raise HTTPException(403, 'Preview account or workspace changed; reopen the sequence review.')
    try:
        compiled, _ = _authoring_graph(req)
        report = simulate_sequence(compiled, sample=req.sample, observations=req.observations, condition_values=req.condition_values,
            initial_connected=req.initial_connected, initial_email_available=req.initial_email_available,
            assume_action_completion=req.assume_action_completion)
        return {**report, "request_id": req.request_id, "request_scope": req.request_scope,
            "input_digest": canonical_hash(req.model_dump()), "graph_digest": canonical_hash(compiled),
            "provider_outcomes_verified": False, "execution_authorized": False}
    except DAGValidationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{campaign_id}")
async def get_campaign_sequence(
    campaign_id: str,
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Retrieves the sequence graph for a specific campaign."""
    campaign = await db.outreach_campaigns.find_one(_campaign_filter(campaign_id, current_user))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    seq_doc = await load_sequence(db, _workspace_id(current_user), campaign_id)
    if not seq_doc:
        # Return default template
        templates = DAGCompiler.get_prebuilt_templates()
        return {
            "campaign_id": campaign_id,
            "nodes": templates[0]["nodes"],
            "edges": templates[0]["edges"],
            "tree": templates[0].get("tree"),
            "is_default": True,
        }

    try:
        if not isinstance(seq_doc.get('tree'), list) or not seq_doc['tree']:
            raise DAGValidationError('Saved sequence has no faithful visual tree; review its original graph before editing.')
        candidate, _ = _authoring_graph(ValidateSequenceRequest(
            nodes=seq_doc.get('nodes'), edges=seq_doc.get('edges'), tree=seq_doc['tree']))
        if 'compiled_dag' in seq_doc and not same_execution_graph(candidate, seq_doc['compiled_dag']):
            raise DAGValidationError('Saved source and execution graph differ; review the original revision before editing.')
    except (ValueError, TypeError, AttributeError) as exc:
        return {'campaign_id': campaign_id, 'nodes': [], 'edges': [], 'tree': None,
                'editor_error': str(exc) if isinstance(exc, DAGValidationError) else 'Saved sequence structure needs review before editing.'}
    seq_doc.pop("_id", None)
    return seq_doc


@router.post("")
async def save_campaign_sequence(
    req: SaveSequenceRequest,
    current_user: dict = require_outreach_permission('sequence:update'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Validates and saves an outreach sequence graph for a campaign.
    """
    campaign = await db.outreach_campaigns.find_one(_campaign_filter(req.campaign_id, current_user))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if campaign.get("status") in {"active", "warming_up"}:
        raise HTTPException(status_code=409, detail="Pause the campaign before editing its sequence")

    try:
        compiled_dag, analysis = _authoring_graph(req)
        _require_executable_analysis(analysis)
    except DAGValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    doc: dict[str, Any] = {
        "campaign_id": req.campaign_id,
        "user_id": _user_id(current_user),
        "workspace_id": _workspace_id(current_user),
        "nodes": req.nodes,
        "edges": req.edges,
        "compiled_dag": compiled_dag,
        "compiler_contract_version": 1,
        "updated_at": datetime.now(timezone.utc),
    }
    if req.tree is not None:
        doc["tree"] = req.tree

    if not await publish_sequence(db, _workspace_id(current_user), req.campaign_id, doc,
                                  expected_revision=campaign.get("authorization_revision", 0)):
        raise HTTPException(status_code=409, detail="Campaign changed while saving the sequence")

    return {"status": "success", "message": "Sequence saved and compiled successfully"}


@router.post("/migration-preview")
async def preview_campaign_sequence_migration(
    req: LiveEditSequenceRequest,
    current_user: dict = require_outreach_permission('sequence:read'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Previews a sequence or sender migration without mutating campaign state.
    Reports which leads move safely (preserving waiting timestamps and history)
    and which leads sit on deleted steps or removed senders that need explicit mapping.
    """
    ws_id = _workspace_id(current_user)
    campaign = await db.outreach_campaigns.find_one(_campaign_filter(req.campaign_id, current_user))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    try:
        compiled_dag, analysis = _authoring_graph(req)
        _require_executable_analysis(analysis)
    except DAGValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    prior_seq = await load_sequence(db, ws_id, req.campaign_id, campaign=campaign)
    prior_dag = (prior_seq or {}).get("compiled_dag") or {}
    prior_nodes = prior_dag.get("nodes") or {}
    new_nodes = compiled_dag.get("nodes") or {}
    deleted_node_ids = sorted(set(prior_nodes.keys()) - set(new_nodes.keys()))
    node_mapping = req.node_mapping or {}
    sender_mapping = req.sender_mapping or {}

    leads_cursor = db.outreach_leads.find({
        "workspace_id": ws_id,
        "campaign_id": req.campaign_id,
        "execution_state": {"$ne": "staged"},
    })
    leads = await leads_cursor.to_list(length=5000) if hasattr(leads_cursor, "to_list") else list(leads_cursor)

    active_senders = set(campaign.get("sender_account_ids") or [])
    safe_leads_count = 0
    preserved_waiting_count = 0
    needs_node_mapping: list[dict[str, Any]] = []
    needs_sender_mapping: list[dict[str, Any]] = []
    mapped_nodes_count = 0
    mapped_senders_count = 0

    for lead in leads:
        if lead.get("has_replied") or lead.get("execution_state") in ("replied", "finished", "bounced", "failed"):
            continue
        cur_node = lead.get("current_node_id")
        assigned_sender = lead.get("assigned_account_id")
        is_waiting = bool(
            lead.get("waiting_for_connection_at")
            or lead.get("waiting_for_reply_at")
            or lead.get("execution_state") in ("waiting_trigger", "waiting_delay", "accepted")
        )
        node_ok = cur_node is None or cur_node in new_nodes
        if not node_ok and cur_node in node_mapping and node_mapping[cur_node] in new_nodes:
            node_ok = True
            mapped_nodes_count += 1
        elif not node_ok:
            old_node = prior_nodes.get(cur_node) or {}
            default_succ = old_node.get("next_default")
            if not is_waiting and default_succ and default_succ in new_nodes:
                node_ok = True
                mapped_nodes_count += 1
            else:
                needs_node_mapping.append({
                    "lead_id": lead.get("id"),
                    "first_name": lead.get("first_name"),
                    "current_node_id": cur_node,
                    "execution_state": lead.get("execution_state"),
                    "waiting_for_connection_at": lead.get("waiting_for_connection_at"),
                    "waiting_for_reply_at": lead.get("waiting_for_reply_at"),
                })

        sender_ok = assigned_sender is None or assigned_sender in active_senders
        if not sender_ok and assigned_sender in sender_mapping:
            sender_ok = True
            mapped_senders_count += 1
        elif not sender_ok:
            needs_sender_mapping.append({
                "lead_id": lead.get("id"),
                "first_name": lead.get("first_name"),
                "assigned_account_id": assigned_sender,
                "execution_state": lead.get("execution_state"),
            })

        if node_ok and sender_ok:
            safe_leads_count += 1
            if is_waiting:
                preserved_waiting_count += 1

    return {
        "campaign_id": req.campaign_id,
        "can_migrate_safely": len(needs_node_mapping) == 0 and len(needs_sender_mapping) == 0,
        "safe_leads_count": safe_leads_count,
        "preserved_waiting_count": preserved_waiting_count,
        "mapped_nodes_count": mapped_nodes_count,
        "mapped_senders_count": mapped_senders_count,
        "deleted_node_ids": deleted_node_ids,
        "needs_node_mapping": needs_node_mapping[:100],
        "needs_sender_mapping": needs_sender_mapping[:100],
    }


@router.post("/live-edit")
async def live_edit_campaign_sequence(
    req: LiveEditSequenceRequest,
    current_user: dict = require_outreach_permission('sequence:update'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Edits an active, paused, or draft campaign sequence in place without rebuilding the campaign.
    Supports extending past the end of sequence to pull completed leads back into newly appended steps,
    and advancing leads sitting on deleted non-branching steps.
    """
    ws_id = _workspace_id(current_user)
    campaign = await db.outreach_campaigns.find_one(_campaign_filter(req.campaign_id, current_user))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    try:
        compiled_dag, analysis = _authoring_graph(req)
        _require_executable_analysis(analysis)
    except DAGValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    prior_seq = await load_sequence(db, ws_id, req.campaign_id, campaign=campaign)
    prior_dag = (prior_seq or {}).get("compiled_dag") or {}
    prior_nodes = prior_dag.get("nodes") or {}
    new_nodes = compiled_dag.get("nodes") or {}

    import uuid
    now = datetime.now(timezone.utc)
    current_version = int((prior_seq or {}).get("version", 0) or 0)
    new_version = current_version + 1
    pointer = str(uuid.uuid4())
    expected_revision = int(campaign.get("authorization_revision", 0) or 0)
    new_revision = expected_revision + 1

    doc: dict[str, Any] = {
        "campaign_id": req.campaign_id,
        "user_id": _user_id(current_user),
        "workspace_id": ws_id,
        "nodes": req.nodes,
        "edges": req.edges,
        "compiled_dag": compiled_dag,
        "compiler_contract_version": 1,
        "version": new_version,
        "updated_at": now,
        "is_deleted": False,
    }
    if req.tree is not None:
        doc["tree"] = req.tree

    await db.outreach_sequence_versions.insert_one({**doc, "_id": pointer})
    rev_filter = expected_revision if "authorization_revision" in campaign else {"$exists": False}
    updated_camp = await db.outreach_campaigns.update_one(
        {"id": req.campaign_id, "workspace_id": ws_id, "is_deleted": {"$ne": True}, "authorization_revision": rev_filter},
        {"$set": {"sequence_version_id": pointer, "updated_at": now}, "$inc": {"authorization_revision": 1}},
    )
    if getattr(updated_camp, "matched_count", 0) == 0:
        raise HTTPException(status_code=409, detail="Campaign changed while saving the live sequence")

    await db.outreach_sequences.update_one(
        {"workspace_id": ws_id, "campaign_id": req.campaign_id},
        {"$set": doc},
        upsert=True,
    )

    reengaged_count = 0
    migrated_deleted_count = 0
    migrated_senders_count = 0

    # 0. Apply explicit sender replacement mapping while preserving waiting timestamps/history
    if req.sender_mapping:
        for old_sender_id, new_sender_id in req.sender_mapping.items():
            if not old_sender_id or not new_sender_id or old_sender_id == new_sender_id:
                continue
            s_res = await db.outreach_leads.update_many(
                {
                    "workspace_id": ws_id,
                    "campaign_id": req.campaign_id,
                    "assigned_account_id": old_sender_id,
                    "has_replied": {"$ne": True},
                },
                {
                    "$set": {
                        "assigned_account_id": new_sender_id,
                        "previous_assigned_account_id": old_sender_id,
                        "updated_at": now,
                    }
                },
            )
            migrated_senders_count += int(getattr(s_res, "modified_count", 0) or 0)

    # 1. Detect previously terminal steps that now have a new successor step (`next_default`)
    extended_successors: list[str] = []
    for node_id, old_node in prior_nodes.items():
        if not isinstance(old_node, dict):
            continue
        was_terminal = old_node.get("next_default") is None and not any((old_node.get("branches") or {}).values())
        new_node = new_nodes.get(node_id)
        if was_terminal and isinstance(new_node, dict):
            next_step_id = new_node.get("next_default")
            if isinstance(next_step_id, str) and next_step_id in new_nodes:
                extended_successors.append(next_step_id)

    if req.reengage_completed_leads and extended_successors:
        target_step_id = extended_successors[0]
        target_node = new_nodes.get(target_step_id, {})
        delay_h = int(target_node.get("delay_hours", 0) or 0)
        reengage_res = await db.outreach_leads.update_many(
            {
                "workspace_id": ws_id,
                "campaign_id": req.campaign_id,
                "execution_state": "finished",
                "has_replied": {"$ne": True},
                "do_not_contact": {"$ne": True},
            },
            {
                "$set": {
                    "current_node_id": target_step_id,
                    "execution_state": "waiting_delay" if delay_h > 0 else "queued",
                    "next_action_due_at": now + timedelta(hours=delay_h),
                    "sequence_version": new_version,
                    "authorized_revision": new_revision,
                    "updated_at": now,
                }
            },
        )
        reengaged_count = int(getattr(reengage_res, "modified_count", 0) or 0)

    # 2. Migrate leads sitting on deleted or explicitly mapped steps while preserving waiting periods
    deleted_node_ids = set(prior_nodes.keys()) - set(new_nodes.keys())
    explicit_node_map = req.node_mapping or {}
    fallback_root = (compiled_dag.get("root_node_ids") or [None])[0]
    for del_id in sorted(deleted_node_ids | set(explicit_node_map.keys())):
        old_node = prior_nodes.get(del_id) or {}
        next_target = explicit_node_map.get(del_id) or old_node.get("next_default")
        if next_target not in new_nodes:
            next_target = fallback_root
        if next_target and next_target in new_nodes:
            states_to_move = ["queued", "waiting_delay", "waiting_trigger", "accepted", "in_progress"]
            if req.resume_failed_on_deleted_steps:
                states_to_move.append("failed")
            # For leads in waiting_trigger / accepted / waiting_delay mapped explicitly, preserve their state and waiting timestamps
            if del_id in explicit_node_map:
                wait_res = await db.outreach_leads.update_many(
                    {
                        "workspace_id": ws_id,
                        "campaign_id": req.campaign_id,
                        "current_node_id": del_id,
                        "execution_state": {"$in": ["waiting_trigger", "waiting_delay", "accepted"]},
                        "has_replied": {"$ne": True},
                    },
                    {
                        "$set": {
                            "current_node_id": next_target,
                            "sequence_version": new_version,
                            "authorized_revision": new_revision,
                            "updated_at": now,
                        }
                    },
                )
                migrated_deleted_count += int(getattr(wait_res, "modified_count", 0) or 0)
                states_to_move = [s for s in states_to_move if s not in ("waiting_trigger", "waiting_delay", "accepted")]
            mig_res = await db.outreach_leads.update_many(
                {
                    "workspace_id": ws_id,
                    "campaign_id": req.campaign_id,
                    "current_node_id": del_id,
                    "execution_state": {"$in": states_to_move},
                    "has_replied": {"$ne": True},
                },
                {
                    "$set": {
                        "current_node_id": next_target,
                        "execution_state": "queued",
                        "failure_reason": None,
                        "sequence_version": new_version,
                        "authorized_revision": new_revision,
                        "updated_at": now,
                    }
                },
            )
            migrated_deleted_count += int(getattr(mig_res, "modified_count", 0) or 0)

    # 3. Sync remaining active leads (including waiting_trigger and accepted) onto the new sequence version & revision
    await db.outreach_leads.update_many(
        {
            "workspace_id": ws_id,
            "campaign_id": req.campaign_id,
            "current_node_id": {"$in": list(new_nodes.keys())},
            "execution_state": {"$in": ["queued", "waiting_delay", "waiting_trigger", "accepted", "in_progress"]},
            "has_replied": {"$ne": True},
        },
        {"$set": {"sequence_version": new_version, "authorized_revision": new_revision, "updated_at": now}},
    )

    return {
        "status": "success",
        "message": "Live sequence updated successfully",
        "version": new_version,
        "authorization_revision": new_revision,
        "reengaged_completed_leads": reengaged_count,
        "migrated_deleted_step_leads": migrated_deleted_count,
        "migrated_sender_leads": migrated_senders_count,
    }
