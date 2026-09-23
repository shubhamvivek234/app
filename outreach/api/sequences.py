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


@router.get("/templates")
async def get_sequence_templates(
    current_user: dict | None = Depends(get_current_user),
    db: AsyncIOMotorDatabase | None = Depends(get_db),
):
    """Returns library of pre-built, high-converting sequence templates + user-saved templates."""
    templates = list(DAGCompiler.get_prebuilt_templates())
    if db is not None and current_user is not None:
        try:
            user_id = str(current_user.get("_id") or current_user.get("id") or current_user.get("user_id") or "")
            ws_id = current_user.get("workspace_id", user_id)
            cursor = db.outreach_templates.find({
                "$or": [
                    {"user_id": user_id},
                    {"workspace_id": ws_id},
                    {"workspace_id": user_id},
                ]
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
    except DAGValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    import uuid
    user_id = str(current_user.get("_id") or current_user.get("id") or current_user.get("user_id") or "")
    ws_id = current_user.get("workspace_id", user_id)
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
    user_id = str(current_user.get("_id") or current_user.get("id") or current_user.get("user_id") or "")
    ws_id = current_user.get("workspace_id", user_id)
    result = await db.outreach_templates.delete_one({
        "id": template_id,
        "$or": [
            {"user_id": user_id},
            {"workspace_id": ws_id},
            {"workspace_id": user_id},
        ],
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
    seq_doc = await db.outreach_sequences.find_one({"campaign_id": campaign_id})
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
    try:
        compiled_dag = DAGCompiler.validate_and_compile(req.nodes, req.edges)
    except DAGValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    doc: dict[str, Any] = {
        "campaign_id": req.campaign_id,
        "nodes": req.nodes,
        "edges": req.edges,
        "compiled_dag": compiled_dag,
        "updated_at": datetime.now(timezone.utc),
    }
    if req.tree is not None:
        doc["tree"] = req.tree

    await db.outreach_sequences.update_one(
        {"campaign_id": req.campaign_id},
        {"$set": doc},
        upsert=True,
    )

    return {"status": "success", "message": "Sequence saved and compiled successfully"}

