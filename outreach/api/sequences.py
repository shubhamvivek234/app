"""
Phase 4: Sequences API router.
Supports sequence graph validation, compiling, saving, and template retrieval.
"""
import logging
from typing import Any, Literal
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict, StrictBool, StrictInt, StrictStr
from motor.motor_asyncio import AsyncIOMotorDatabase

from db.mongo import get_db
from outreach.api.dependencies import get_outreach_user, require_outreach_permission
from outreach.core.dag_compiler import DAGCompiler, DAGValidationError
from outreach.core.sequence_versions import load_sequence, publish_sequence
from outreach.core.sequence_contract import bounded_json, visual_graph
from outreach.core.sequence_preview import analyze_sequence, same_execution_graph, simulate_sequence
from outreach.core.authorization import canonical_hash
from outreach.core.template_governance import MAX_REVISION, scoped_review, delete_template, create_template
from outreach.core.workspace_scope import workspace_scope
from outreach.core import template_saves, template_metadata, template_graphs, template_metadata_updates

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


class SaveTemplateRequest(ValidateSequenceRequest):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default="", max_length=1000)


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
    templates = list(DAGCompiler.get_prebuilt_templates())
    if db is not None and current_user is not None:
        try:
            ws_id = _workspace_id(current_user)
            cursor = db.outreach_templates.find(workspace_scope(ws_id)).sort("created_at", -1)
            custom_templates = await cursor.to_list(length=100)
            for doc in custom_templates:
                templates.append({**{key: value for key, value in doc.items() if key != "_id"},
                    "deletion_review": scoped_review(doc, ws_id, current_user.get("user_id"), current_user.get("firebase_uid")),
                    "metadata_review": template_metadata.metadata_review(doc, ws_id, current_user.get("user_id"), current_user.get("firebase_uid")),
                    "graph_review": template_graphs.graph_review(doc, ws_id, current_user.get("user_id"), current_user.get("firebase_uid"))})
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
