"""
Phase 4: Sequences API router.
Supports sequence graph validation, compiling, saving, and template retrieval.
"""
import logging
from typing import Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db
from outreach.core.dag_compiler import DAGCompiler, DAGValidationError
from outreach.models import OutreachSequence, SequenceNode, SequenceEdge

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
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class SaveSequenceRequest(BaseModel):
    campaign_id: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    tree: list[dict[str, Any]] | None = None


class SaveTemplateRequest(BaseModel):
    name: str
    description: str | None = ""
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    tree: list[dict[str, Any]] | None = None


def _compile_visual_tree(tree: list[dict[str, Any]]) -> dict[str, Any]:
    """Compile the editor's visible tree so it cannot diverge from saved execution nodes."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def visit(steps: list[dict[str, Any]], parent_id: str | None = None, branch_label: str | None = None) -> None:
        if not isinstance(steps, list):
            raise DAGValidationError("Sequence tree contains invalid steps")
        previous_id = parent_id
        for index, step in enumerate(steps):
            if not isinstance(step, dict) or not step.get("id") or not step.get("type"):
                raise DAGValidationError("Every visible sequence step needs an ID and type")
            delay_hours = round(float(step.get("delay_days", 0)) * 24) if "delay_days" in step else round(float(step.get("delay_hours", 0)))
            nodes.append({
                "id": step["id"], "type": step["type"], "delay_hours": delay_hours,
                "config": step.get("config") or {},
            })
            if previous_id:
                edges.append({
                    "source": previous_id, "target": step["id"],
                    "label": branch_label if index == 0 and branch_label else "",
                })
            previous_id = step["id"]
            branches = step.get("branches") or {}
            for side in ("left", "right"):
                branch = branches.get(side) or {}
                if branch.get("steps"):
                    visit(branch["steps"], step["id"], branch.get("condition"))
            if step.get("steps"):
                visit(step["steps"], step["id"])

    try:
        visit(tree)
    except (TypeError, ValueError) as exc:
        raise DAGValidationError("Sequence tree contains an invalid delay") from exc
    return DAGCompiler.validate_and_compile(nodes, edges)


def _same_execution_graph(visible: dict[str, Any], saved: dict[str, Any]) -> bool:
    if visible.get("root_node_ids") != saved.get("root_node_ids"):
        return False
    visible_nodes = visible.get("nodes", {})
    saved_nodes = saved.get("nodes", {})
    if visible_nodes.keys() != saved_nodes.keys():
        return False
    fields = ("type", "delay_hours", "config", "next_default", "branches")
    return all(all(visible_nodes[node_id].get(field) == saved_nodes[node_id].get(field) for field in fields) for node_id in visible_nodes)


@router.get("/templates")
async def get_sequence_templates(
    current_user: dict | None = Depends(get_current_user),
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

    return templates


@router.post("/templates")
async def save_custom_template(
    req: SaveTemplateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Saves an outreach sequence graph as a reusable custom template."""
    try:
        compiled_dag = DAGCompiler.validate_and_compile(req.nodes, req.edges)
        if req.tree is not None and not _same_execution_graph(_compile_visual_tree(req.tree), compiled_dag):
            raise DAGValidationError("Visible sequence does not match its execution steps. Save the editor again.")
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
        "created_at": datetime.now(timezone.utc),
    }
    await db.outreach_templates.insert_one(doc)
    doc.pop("_id", None)
    return {"status": "success", "template": doc}


@router.delete("/templates/{template_id}")
async def delete_custom_template(
    template_id: str,
    current_user: dict = Depends(get_current_user),
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


@router.post("/validate")
async def validate_sequence(req: ValidateSequenceRequest):
    """
    Validates a sequence topology before launching.
    Detects cycles, invalid branching, or disconnected nodes.
    """
    try:
        compiled = DAGCompiler.validate_and_compile(req.nodes, req.edges)
        return {"valid": True, "compiled": compiled}
    except DAGValidationError as exc:
        return {"valid": False, "error": str(exc)}


@router.get("/{campaign_id}")
async def get_campaign_sequence(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Retrieves the sequence graph for a specific campaign."""
    campaign = await db.outreach_campaigns.find_one(_campaign_filter(campaign_id, current_user))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    seq_doc = await db.outreach_sequences.find_one({"campaign_id": campaign_id, "workspace_id": _workspace_id(current_user), "is_deleted": {"$ne": True}})
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

    seq_doc.pop("_id", None)
    return seq_doc


@router.post("")
async def save_campaign_sequence(
    req: SaveSequenceRequest,
    current_user: dict = Depends(get_current_user),
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
        compiled_dag = DAGCompiler.validate_and_compile(req.nodes, req.edges)
        if req.tree is not None and not _same_execution_graph(_compile_visual_tree(req.tree), compiled_dag):
            raise DAGValidationError("Visible sequence does not match its execution steps. Save the editor again.")
    except DAGValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    doc: dict[str, Any] = {
        "campaign_id": req.campaign_id,
        "user_id": _user_id(current_user),
        "workspace_id": _workspace_id(current_user),
        "nodes": req.nodes,
        "edges": req.edges,
        "compiled_dag": compiled_dag,
        "updated_at": datetime.now(timezone.utc),
    }
    if req.tree is not None:
        doc["tree"] = req.tree

    await db.outreach_sequences.update_one(
        {"campaign_id": req.campaign_id, "workspace_id": _workspace_id(current_user)},
        {"$set": {**doc, "is_deleted": False}},
        upsert=True,
    )

    return {"status": "success", "message": "Sequence saved and compiled successfully"}
