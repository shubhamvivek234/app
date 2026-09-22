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


@router.get("/templates")
async def get_sequence_templates():
    """Returns library of pre-built, high-converting outreach sequence templates."""
    return DAGCompiler.get_prebuilt_templates()


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

    doc = {
        "campaign_id": req.campaign_id,
        "nodes": req.nodes,
        "edges": req.edges,
        "compiled_dag": compiled_dag,
        "updated_at": datetime.now(timezone.utc),
    }

    await db.outreach_sequences.update_one(
        {"campaign_id": req.campaign_id},
        {"$set": doc},
        upsert=True,
    )

    return {"status": "success", "message": "Sequence saved and compiled successfully"}
