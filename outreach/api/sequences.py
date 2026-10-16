"""
Phase 4: Sequences API router.
Supports sequence graph validation, compiling, saving, and template retrieval.
"""
import logging
from typing import Any, Literal
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict, StrictBool
from motor.motor_asyncio import AsyncIOMotorDatabase

from db.mongo import get_db
from outreach.api.dependencies import get_outreach_user, require_outreach_permission
from outreach.core.dag_compiler import DAGCompiler, DAGValidationError
from outreach.core.sequence_versions import load_sequence, publish_sequence
from outreach.core.sequence_contract import bounded_json, visual_graph
from outreach.core.sequence_preview import analyze_sequence, same_execution_graph, simulate_sequence
from outreach.core.authorization import canonical_hash

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
    """Returns library of pre-built, high-converting sequence templates + user-saved templates."""
    templates = list(DAGCompiler.get_prebuilt_templates())
    if db is not None and current_user is not None:
        try:
            ws_id = _workspace_id(current_user)
            cursor = db.outreach_templates.find({
                "workspace_id": ws_id,
            }).sort("created_at", -1)
            custom_templates = await cursor.to_list(length=100)
            for doc in custom_templates:
                doc.pop("_id", None)
                templates.append(doc)
        except Exception as exc:
            logger.warning(f"Could not load custom templates from db: {exc}")

    inspected = []
    for template in templates:
        try:
            _, compatibility = _authoring_graph(ValidateSequenceRequest(
                nodes=template.get('nodes'), edges=template.get('edges'), tree=template.get('tree')))
        except (ValueError, TypeError, AttributeError):
            compatibility = {'contract_version': 1, 'valid': False, 'issues': [],
                'error': 'Saved template structure needs review.', 'execution_authorized': False}
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
    await db.outreach_templates.insert_one(doc)
    doc.pop("_id", None)
    return {"status": "success", "template": doc}


@router.delete("/templates/{template_id}")
async def delete_custom_template(
    template_id: str,
    current_user: dict = require_outreach_permission('sequence:delete'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Deletes a user-saved custom template."""
    ws_id = _workspace_id(current_user)
    result = await db.outreach_templates.delete_one({
        "id": template_id,
        "workspace_id": ws_id,
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found or cannot delete prebuilt template")
    return {"status": "success", "message": "Template deleted"}


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
