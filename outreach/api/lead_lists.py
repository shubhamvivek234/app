"""Scoped campaign audience-list metadata; collection and launch remain separate."""
from typing import Any, Literal, Annotated
import logging

from fastapi import APIRouter, Depends, Query, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints

from db.mongo import get_db
from outreach.api.dependencies import require_outreach_permission, workspace_id
from outreach.core import lead_lists, lead_list_imports

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lead-lists", tags=["Outreach audience lists"])


class CreateList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=60)
    request_id: str = Field(min_length=36, max_length=36)


class ListRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: StrictInt = Field(ge=1)
    review_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class RenameList(ListRevision):
    name: str = Field(min_length=1, max_length=60)


class MembershipChange(ListRevision):
    lead_ids: list[str] = Field(min_length=1, max_length=100)
    operation: str


class AdoptExisting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_id: str = Field(min_length=1, max_length=200)
    revision: StrictInt = Field(ge=0)
    writers_drained: StrictBool


def actor(user: dict) -> str:
    return str(user.get("user_id") or user.get("id") or user.get("_id") or "")


@router.get("")
async def list_audiences(campaign_id: str, include_archived: bool = False,
        current_user: dict = require_outreach_permission("lead:read"),
        db: AsyncIOMotorDatabase = Depends(get_db)) -> dict[str, Any]:
    return await lead_lists.inventory(db, workspace_id(current_user), campaign_id, include_archived)


@router.post("")
async def create_audience(req: CreateList, current_user: dict = require_outreach_permission("lead:create"),
        db: AsyncIOMotorDatabase = Depends(get_db)) -> dict[str, Any]:
    return await lead_lists.create_list(db, workspace_id(current_user), actor(current_user), req.campaign_id, req.name, req.request_id)


@router.post("/adopt-existing")
async def adopt_existing_audience(req: AdoptExisting,
        current_user: dict = require_outreach_permission("workspace:update"),
        db: AsyncIOMotorDatabase = Depends(get_db)) -> dict[str, Any]:
    return await lead_lists.adopt_existing(db, workspace_id(current_user), actor(current_user),
        req.campaign_id, req.revision, req.writers_drained)


@router.patch("/{list_id}")
async def rename_audience(list_id: str, req: RenameList,
        current_user: dict = require_outreach_permission("lead:update"),
        db: AsyncIOMotorDatabase = Depends(get_db)) -> dict[str, Any]:
    return await lead_lists.edit_list(db, workspace_id(current_user), list_id, req.revision, name=req.name,
        expected_review=req.review_digest)


@router.post("/{list_id}/archive")
async def archive_audience(list_id: str, req: ListRevision,
        current_user: dict = require_outreach_permission("lead:delete"),
        db: AsyncIOMotorDatabase = Depends(get_db)) -> dict[str, Any]:
    return await lead_lists.edit_list(db, workspace_id(current_user), list_id, req.revision, archive=True,
        expected_review=req.review_digest)


@router.post("/{list_id}/members")
async def change_audience_members(list_id: str, req: MembershipChange,
        current_user: dict = require_outreach_permission("lead:update"),
        db: AsyncIOMotorDatabase = Depends(get_db)) -> dict[str, Any]:
    return await lead_lists.change_members(db, workspace_id(current_user), actor(current_user),
        list_id, req.revision, req.lead_ids, req.operation, expected_review=req.review_digest)


@router.get("/{list_id}/members")
async def read_audience_members(list_id: str, after: str | None = None, limit: int = Query(50, ge=1, le=100),
        current_user: dict = require_outreach_permission("lead:read"),
        db: AsyncIOMotorDatabase = Depends(get_db)) -> dict[str, Any]:
    return await lead_lists.members(db, workspace_id(current_user), list_id, after=after, limit=limit)


class ImportPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: Literal["csv", "pasted_urls"]
    raw_text: str = Field(min_length=1, max_length=2_000_000)
    quantity: StrictInt = Field(ge=1, le=100)
    require_name: StrictBool = True
    skip_already_contacted: StrictBool = True
    default_first_name: str | None = Field(default=None, max_length=100)
    default_company_name: str | None = Field(default=None, max_length=200)
    name_overrides: dict[Annotated[str, StringConstraints(pattern=r"^(?:[1-9]|[1-9][0-9]|100)$", max_length=3)], Annotated[str, StringConstraints(max_length=100)]] = Field(default_factory=dict, max_length=100)


class ImportRequest(ImportPreview):
    request_id: str = Field(min_length=36, max_length=36)
    request_scope: str = Field(pattern=r"^[0-9a-f]{64}$")
    campaign_id: str = Field(min_length=1, max_length=200)
    revision: StrictInt = Field(ge=1)
    review_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ImportScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_scope: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.get("/import-context")
async def import_context(current_user: dict = require_outreach_permission("lead:read")):
    return {"request_scope": lead_list_imports.request_scope(workspace_id(current_user), actor(current_user))}


@router.get("/imports/{request_id}")
async def inspect_audience_import(request_id: str, request_scope: str = Query(pattern=r"^[0-9a-f]{64}$"),
        current_user: dict = require_outreach_permission("lead:read"), db: AsyncIOMotorDatabase = Depends(get_db)):
    return await lead_list_imports.inspect_import(db, workspace_id(current_user), actor(current_user), request_id, request_scope)


@router.post("/imports/{request_id}/cancel")
async def cancel_audience_import(request_id: str, req: ImportScope,
        current_user: dict = require_outreach_permission("lead:create"), db: AsyncIOMotorDatabase = Depends(get_db)):
    return await lead_list_imports.cancel_import(db, workspace_id(current_user), actor(current_user), request_id, req.request_scope)


@router.post("/{list_id}/import-preview")
async def preview_audience_import(list_id: str, req: ImportPreview,
        current_user: dict = require_outreach_permission("lead:create"), db: AsyncIOMotorDatabase = Depends(get_db)):
    return await lead_list_imports.preview_import(db, workspace_id(current_user), actor(current_user), list_id, req.model_dump())


@router.post("/{list_id}/import")
async def import_audience_contacts(list_id: str, req: ImportRequest,
        current_user: dict = require_outreach_permission("lead:create"),
        editor: dict = require_outreach_permission("lead:update"), db: AsyncIOMotorDatabase = Depends(get_db)):
    if workspace_id(current_user) != workspace_id(editor) or actor(current_user) != actor(editor):
        raise HTTPException(403, "Import permission context changed")
    return await lead_list_imports.import_contacts(db, workspace_id(current_user), actor(current_user), list_id, req.model_dump())
