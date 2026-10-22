"""Reusable prompt guidance library and illustrative sequence preview."""
import uuid
from copy import deepcopy
import logging
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from outreach.core.workspace_scope import workspace_scope
from db.mongo import get_db
from outreach.api.dependencies import get_outreach_user, require_outreach_permission, workspace_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["LinkedIn Outreach AI Prompts"])


# ── Request / Response DTOs ────────────────────────────────────────────────

class CreateAIPromptRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    prompt_text: str = Field(..., min_length=5)
    description: str = Field(default="")
    author_name: str = Field(default="You")


class PromptPreviewRequest(BaseModel):
    template: str = Field(..., description="Message text with contact variables and optional prompt guidance tokens")
    alternative_message: str | None = None
    subject: str | None = None
    lead_id: str | None = None
    campaign_id: str | None = None
    evaluate_ai: bool = False
    improve_copy: bool = False
    custom_lead_data: dict[str, Any] | None = None


# Server-owned guidance: database rows cannot declare themselves global.
# Stable reserved IDs let clients identify curated templates without seeding.

DEFAULT_PROMPTS = [
    {
        "name": "Saw you're doing X (3-5 words)",
        "prompt_text": "Analyze the lead's current role, company tagline, or recent LinkedIn post. Extract a concise phrase (3-5 words) describing what they are actively scaling or building. Do not include punctuation. Example: 'scaling high-volume outbound pipelines'",
        "description": "Short 3-5 word activity snippet extracted from headline or post.",
        "author_name": "Unravler Curated",
        "id": "curated_activity-snippet",
        "runs_count": 0,
        "is_system": True,
    },
    {
        "name": "Website designer personalised first line",
        "prompt_text": "Write a 1-sentence genuine compliment about their company's UI aesthetic, brand clarity, or modern design velocity.",
        "description": "High-converting opening line focused on product design & branding.",
        "author_name": "Unravler Curated",
        "id": "curated_design-first-line",
        "runs_count": 0,
        "is_system": True,
    },
    {
        "name": "Recent post observation",
        "prompt_text": "Synthesize their most recent post into a thoughtful one-sentence insight showing you actually read and digested their thesis.",
        "description": "Engaging hook referencing their latest LinkedIn post topic.",
        "author_name": "Unravler Curated",
        "id": "curated_recent-post",
        "runs_count": 0,
        "is_system": True,
    },
    {
        "name": "Company milestone congratulations",
        "prompt_text": "Acknowledge recent growth, hiring surge, or product launch at their company with zero flattery and direct tone.",
        "description": "Professional acknowledgment of company traction.",
        "author_name": "Unravler Curated",
        "id": "curated_company-milestone",
        "runs_count": 0,
        "is_system": True,
    },
    {
        "name": "Mutual niche connection",
        "prompt_text": "Highlight shared focus in their specific niche and why their approach to outbound/automation stood out.",
        "description": "Niche peer-to-peer connection icebreaker.",
        "author_name": "Unravler Curated",
        "id": "curated_niche-connection",
        "runs_count": 0,
        "is_system": True,
    },
    {
        "name": "Casual role-based value insights",
        "prompt_text": "Based on the following information from the LinkedIn profile, write a very short sentence starting with 'Most [role] like you are trying to [goal]' tailored to their headline, biography, and company overview.",
        "description": "Role-based insight hook starting with 'Most [role] like you are trying to...'",
        "author_name": "Unravler Curated",
        "id": "curated_role-value-insights",
        "runs_count": 0,
        "is_system": True,
    },
    {
        "name": "Profile observation",
        "prompt_text": "Analyze the prospect's LinkedIn headline, summary, and company overview to write a concise observation starting with 'I noticed that...' about what their company builds or offers.",
        "description": "Personalized company & profile observation icebreaker.",
        "author_name": "Unravler Curated",
        "id": "curated_profile-observation",
        "runs_count": 0,
        "is_system": True,
    },
    {
        "name": "Skill & experience compliment",
        "prompt_text": "Write a genuine 1-sentence compliment referencing their specific technical or leadership skills, years of experience, or notable projects from their LinkedIn profile.",
        "description": "Specific compliment on tenure, projects, and top skills.",
        "author_name": "Unravler Curated",
        "id": "curated_skill-compliment",
        "runs_count": 0,
        "is_system": True,
    },
]


async def _fetch_cursor_docs(cursor, length: int = 100) -> list[dict]:
    docs = []
    async for doc in cursor:
        docs.append(doc)
        if len(docs) >= length:
            break
    return docs


@router.get("")
async def list_prompts(
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return curated guidance and current-workspace custom prompts; never seed."""
    cursor = db.outreach_ai_prompts.find({
        **workspace_scope(workspace_id(current_user)),
        "is_system": {"$ne": True},
        "id": {"$nin": [item["id"] for item in DEFAULT_PROMPTS]},
    }, {"_id": 0}).sort("runs_count", -1)
    items = await _fetch_cursor_docs(cursor, length=100)
    for item in items:
        item.pop("_id", None)
        item["is_system"] = False
    return deepcopy(DEFAULT_PROMPTS) + items


@router.post("")
async def create_prompt(
    req: CreateAIPromptRequest,
    current_user: dict = require_outreach_permission('content:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Creates a custom reusable AI prompt."""
    user_id = current_user.get("user_id")
    ws_id = workspace_id(current_user)

    doc = {
        "id": f"prm_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "workspace_id": ws_id,
        "name": req.name.strip(),
        "prompt_text": req.prompt_text.strip(),
        "description": req.description.strip(),
        "author_name": req.author_name.strip() or "User",
        "runs_count": 0,
        "is_system": False,
        "created_at": datetime.now(timezone.utc),
    }

    await db.outreach_ai_prompts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/{prompt_id}")
async def delete_prompt(
    prompt_id: str,
    current_user: dict = require_outreach_permission('content:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Deletes a custom AI prompt (system prompts protected)."""
    if prompt_id in {item["id"] for item in DEFAULT_PROMPTS}:
        raise HTTPException(status_code=404, detail="Cannot delete built-in system prompt")
    res = await db.outreach_ai_prompts.delete_one({
        "id": prompt_id,
        **workspace_scope(workspace_id(current_user)),
        "is_system": {"$ne": True},
    })
    if res.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not found or cannot delete built-in system prompt",
        )
    return {"status": "deleted", "prompt_id": prompt_id}


def _synthesize_prompt_output(prompt_name: str, prompt_text: str, lead_data: dict[str, Any]) -> str:
    """Synthesize personalized copy from real lead profile context (headline, role, company, summary, recent_post)."""
    first_name = (lead_data.get("first_name") or "there").strip()
    company = (lead_data.get("company_name") or "your team").strip()
    job_title = (lead_data.get("job_title") or "leader").strip()
    industry = (lead_data.get("industry") or "your space").strip()
    headline = (lead_data.get("headline") or "").strip()
    summary = (lead_data.get("summary") or "").strip()
    recent_post = (lead_data.get("recent_post") or "").strip()
    name_lower = prompt_name.lower()
    text_lower = prompt_text.lower()

    if "3-5 words" in name_lower or "doing x" in name_lower or "concise phrase" in text_lower:
        if "|" in headline:
            segment = headline.split("|")[-1].strip().rstrip(".")
            words = segment.split()
            if 2 <= len(words) <= 7:
                return segment[0].lower() + segment[1:] if segment else f"leading {job_title.lower()} initiatives at {company}"
        if recent_post:
            words = recent_post.split()[:5]
            return " ".join(words).rstrip(".,!?:;").lower()
        if summary:
            words = summary.split()[:5]
            return " ".join(words).rstrip(".,!?:;").lower()
        return f"scaling {industry.lower()} initiatives at {company}"

    if "website" in name_lower or "designer" in name_lower or "ui aesthetic" in text_lower:
        return f"Noticed {company}'s focus on {industry} and wanted to connect around your work as {job_title}."

    if "recent post" in name_lower or "latest linkedin post" in text_lower:
        if recent_post:
            snippet = recent_post[:90].rstrip("., ") + ("..." if len(recent_post) > 90 else "")
            return f"Your recent post on \"{snippet}\" really resonated with what we're seeing in {industry}."
        return f"Would love to hear your perspective as {job_title} at {company} on where {industry} is heading."

    if "milestone" in name_lower or "congratulations" in name_lower or "hiring" in text_lower:
        return f"Congrats on the momentum at {company}—exciting to see how you're leading the {job_title} charter."

    if "niche" in name_lower or "mutual" in name_lower:
        return f"Always great connecting with fellow leaders focused on {industry} and modern growth workflows at {company}."

    if "role-based" in name_lower or "value insights" in name_lower or "most [" in text_lower:
        role_plural = f"{job_title}s" if not job_title.lower().endswith("s") else job_title
        goal = f"scale {industry.lower()} pipelines without sacrificing personalization"
        if "|" in headline:
            tail = headline.split("|")[-1].strip().rstrip(".")
            if len(tail.split()) >= 2:
                goal = tail[0].lower() + tail[1:]
        return f"Most {role_plural} like you at {company} are trying to {goal}."

    if "profile observation" in name_lower or "i noticed that" in text_lower:
        if summary:
            obs = summary[:80].rstrip("., ") + ("..." if len(summary) > 80 else "")
            return f"I noticed that at {company} ({obs}), you're focused on high-impact {industry.lower()} outcomes."
        if "|" in headline:
            obs = headline.split("|")[-1].strip().rstrip(".")
            return f"I noticed that at {company} you're {obs[0].lower() + obs[1:] if obs else f'leading {industry.lower()} initiatives'}."
        return f"I noticed that {company} is building strong momentum in {industry} under your leadership as {job_title}."

    if "skill" in name_lower or "experience" in name_lower or "compliment" in name_lower:
        top_skill = (lead_data.get("top_skill") or industry).strip()
        years = (lead_data.get("years_in_role") or lead_data.get("years_in_company") or "").strip()
        tenure_clause = f"—{years} in {top_skill} shows real dedication" if years else f" and your focus on {top_skill} at {company} really stands out"
        return f"Solid work on the {company} initiatives, {first_name}{tenure_clause}."

    if "?" in prompt_text or "question" in name_lower or "ask" in text_lower:
        return f"How is your team at {company} approaching {industry.lower()} automation as {job_title} this quarter?"

    if recent_post:
        return f"Loved your recent perspective at {company} ({job_title})—especially your point on {recent_post[:60].rstrip()}."
    if summary:
        snippet = summary[:75].rstrip("., ") + ("..." if len(summary) > 75 else "")
        return f"Noticed from your profile ({snippet}) how you're driving {industry.lower()} growth at {company}."
    if headline:
        return f"Noticed your work as {headline} and how you're driving growth at {company}."
    return f"Impressed by your work as {job_title} at {company}, {first_name}."


@router.post("/preview")
async def preview_evaluated_message(
    req: PromptPreviewRequest,
    current_user: dict = require_outreach_permission('sequence:read'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Renders contact variables and prompt tokens against a real or sample lead.
    """
    ws_scope = workspace_scope(workspace_id(current_user))
    lead_data: dict[str, Any] = {
        "first_name": "Elena",
        "last_name": "Rostova",
        "full_name": "Elena Rostova",
        "company_name": "CognitiveFlow",
        "company": "CognitiveFlow",
        "job_title": "Founder & CEO",
        "position": "Founder & CEO",
        "location": "London, United Kingdom",
        "location_raw": "London, United Kingdom",
        "country": "United Kingdom",
        "company_location": "London, UK",
        "industry": "Artificial Intelligence",
        "headline": "Founder & CEO at CognitiveFlow | Building autonomous reasoning systems",
        "summary": "Building autonomous reasoning systems for B2B revenue teams.",
        "school": "Imperial College London",
        "university_name": "Imperial College London",
        "university": "Imperial College London",
        "top_skill": "Enterprise AI & Outbound GTM",
        "company_followed": "OpenAI",
        "connections_count": "2,450",
        "number_of_connections": "2,450",
        "years_in_company": "4 years",
        "years_in_role": "3 years",
        "mutual_connections": "14 mutual connections",
        "profile_type": "Open Profile",
        "recent_post": "AI agents are fundamentally restructuring how outbound SDR workflows operate. Speed and contextual relevance win.",
    }
    resolved_lead_id: str | None = None
    available_leads: list[dict[str, Any]] = []

    def _hydrate_lead_doc(lead_doc: dict[str, Any]) -> dict[str, Any]:
        custom_vars = lead_doc.get("custom_variables") or {}
        first = (lead_doc.get("first_name") or "").strip()
        last = (lead_doc.get("last_name") or "").strip()
        company = (lead_doc.get("company_name") or "").strip()
        title = (lead_doc.get("job_title") or "").strip()
        school_val = (
            lead_doc.get("university_name")
            or lead_doc.get("school")
            or custom_vars.get("university_name")
            or custom_vars.get("school")
            or ""
        )
        raw_conns = lead_doc.get("connections_count") or custom_vars.get("connections_count")
        conns_val = str(raw_conns) if raw_conns is not None and str(raw_conns).strip() else ""
        profile_type_val = (
            "Open Profile"
            if lead_doc.get("is_open_profile") is True
            else "Premium"
            if lead_doc.get("is_premium") is True
            else (lead_doc.get("profile_type") or custom_vars.get("profile_type") or "")
        )
        loc_val = (lead_doc.get("location") or custom_vars.get("location") or "").strip()
        headline_val = (lead_doc.get("headline") or custom_vars.get("headline") or "").strip()
        if not headline_val and title and company:
            headline_val = f"{title} at {company}"
        hydrated = {
            "id": lead_doc.get("id"),
            "first_name": first,
            "last_name": last,
            "full_name": f"{first} {last}".strip(),
            "company_name": company,
            "company": company,
            "job_title": title,
            "position": title,
            "location": loc_val,
            "location_raw": loc_val,
            "country": lead_doc.get("country") or custom_vars.get("country") or "",
            "company_location": lead_doc.get("company_location") or custom_vars.get("company_location") or loc_val,
            "industry": lead_doc.get("industry") or custom_vars.get("industry") or "",
            "headline": headline_val,
            "summary": lead_doc.get("summary") or custom_vars.get("summary") or "",
            "school": school_val,
            "university_name": school_val,
            "university": school_val,
            "top_skill": lead_doc.get("top_skill") or custom_vars.get("top_skill") or "",
            "company_followed": lead_doc.get("company_followed") or custom_vars.get("company_followed") or "",
            "connections_count": conns_val,
            "number_of_connections": conns_val,
            "years_in_company": lead_doc.get("years_in_company") or custom_vars.get("years_in_company") or "",
            "years_in_role": lead_doc.get("years_in_role") or custom_vars.get("years_in_role") or "",
            "mutual_connections": lead_doc.get("mutual_connections") or custom_vars.get("mutual_connections") or "",
            "profile_type": profile_type_val,
            "recent_post": custom_vars.get("recent_post") or lead_doc.get("summary") or "",
            "linkedin_url": lead_doc.get("linkedin_url") or "",
        }
        hydrated.update(custom_vars)
        return hydrated

    # Fetch available leads for the campaign/workspace switcher if outreach_leads exists
    leads_col = getattr(db, "outreach_leads", None)
    if leads_col is not None and hasattr(leads_col, "find"):
        try:
            query: dict[str, Any] = {**ws_scope}
            if req.campaign_id and req.campaign_id != "new":
                query["campaign_id"] = req.campaign_id
            cursor = leads_col.find(query)
            docs = await _fetch_cursor_docs(cursor, length=25)
            if not docs and req.campaign_id:
                cursor = leads_col.find({**ws_scope})
                docs = await _fetch_cursor_docs(cursor, length=25)
            for d in docs:
                if d.get("id") and (d.get("first_name") or d.get("last_name") or d.get("company_name")):
                    available_leads.append({
                        "id": d.get("id"),
                        "first_name": d.get("first_name") or "Lead",
                        "last_name": d.get("last_name") or "",
                        "company_name": d.get("company_name") or "",
                        "job_title": d.get("job_title") or "",
                        "location": d.get("location") or "",
                    })
        except Exception as exc:
            logger.debug("Available leads preview query skipped (%s)", type(exc).__name__)
            available_leads = []

    if req.lead_id:
        lead_doc = await db.outreach_leads.find_one({
            "id": req.lead_id,
            **ws_scope,
        })
        if not lead_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        lead_data = _hydrate_lead_doc(lead_doc)
        resolved_lead_id = lead_doc.get("id")
    elif req.custom_lead_data:
        lead_data.update(req.custom_lead_data)
        if "company_name" in req.custom_lead_data and "company" not in req.custom_lead_data:
            lead_data["company"] = req.custom_lead_data["company_name"]
        elif "company" in req.custom_lead_data and "company_name" not in req.custom_lead_data:
            lead_data["company_name"] = req.custom_lead_data["company"]
        if "job_title" in req.custom_lead_data and "position" not in req.custom_lead_data:
            lead_data["position"] = req.custom_lead_data["job_title"]
        elif "position" in req.custom_lead_data and "job_title" not in req.custom_lead_data:
            lead_data["job_title"] = req.custom_lead_data["position"]
        if "university_name" in req.custom_lead_data and "school" not in req.custom_lead_data:
            lead_data["school"] = req.custom_lead_data["university_name"]
            lead_data["university"] = req.custom_lead_data["university_name"]
        if "location" in req.custom_lead_data and "location_raw" not in req.custom_lead_data:
            lead_data["location_raw"] = req.custom_lead_data["location"]
    elif available_leads:
        first_lead_doc = await db.outreach_leads.find_one({
            "id": available_leads[0]["id"],
            **ws_scope,
        })
        if first_lead_doc:
            lead_data = _hydrate_lead_doc(first_lead_doc)
            resolved_lead_id = first_lead_doc.get("id")

    from outreach.core.dag_compiler import find_missing_profile_variables

    missing_primary_vars = find_missing_profile_variables(req.template, lead_data)
    used_alternative_message = False
    active_template = req.template
    if missing_primary_vars and req.alternative_message and req.alternative_message.strip():
        active_template = req.alternative_message.strip()
        used_alternative_message = True

    rendered_text = active_template
    rendered_subject = req.subject or ""

    # 1. Replace static variables
    for var, val in lead_data.items():
        rendered_text = rendered_text.replace(f"{{{{{var}}}}}", str(val))
        rendered_text = rendered_text.replace(f"{{{var}}}", str(val))
        if rendered_subject:
            rendered_subject = rendered_subject.replace(f"{{{{{var}}}}}", str(val))
            rendered_subject = rendered_subject.replace(f"{{{var}}}", str(val))

    # Fallback replacements
    rendered_text = rendered_text.replace("{{first_name}}", str(lead_data.get("first_name", "")))
    rendered_text = rendered_text.replace("{{company_name}}", str(lead_data.get("company_name", "")))
    rendered_text = rendered_text.replace("{{job_title}}", str(lead_data.get("job_title", "")))
    if rendered_subject:
        rendered_subject = rendered_subject.replace("{{first_name}}", str(lead_data.get("first_name", "")))
        rendered_subject = rendered_subject.replace("{{company_name}}", str(lead_data.get("company_name", "")))
        rendered_subject = rendered_subject.replace("{{job_title}}", str(lead_data.get("job_title", "")))

    import re
    token_pattern = re.compile(r"✨\s*\[([^\]]+)\]")

    # Also build an AI-evaluated version resolving ✨ [Prompt Name] against the lead's profile
    catalog_by_name = {p["name"].lower(): p for p in DEFAULT_PROMPTS}
    prompts_col = getattr(db, "outreach_ai_prompts", None)
    if prompts_col is not None and hasattr(prompts_col, "find"):
        try:
            custom_docs = await _fetch_cursor_docs(
                prompts_col.find({**ws_scope, "is_system": {"$ne": True}}),
                length=100,
            )
            for cd in custom_docs:
                if cd.get("name"):
                    catalog_by_name[cd["name"].lower()] = cd
        except Exception as exc:
            logger.debug("Custom AI prompts lookup skipped (%s)", type(exc).__name__)

    def _resolve_ai_match(match: re.Match) -> str:
        p_name = match.group(1).strip()
        p_doc = catalog_by_name.get(p_name.lower(), {})
        p_text = p_doc.get("prompt_text", p_name)
        return _synthesize_prompt_output(p_name, p_text, lead_data)

    ai_generated_text = token_pattern.sub(_resolve_ai_match, rendered_text)

    if req.evaluate_ai:
        rendered_text = ai_generated_text
        # Increment runs_count on custom prompts used
        if prompts_col is not None and hasattr(prompts_col, "update_one"):
            for m in token_pattern.finditer(active_template):
                p_name = m.group(1).strip().lower()
                p_doc = catalog_by_name.get(p_name)
                if p_doc and not p_doc.get("is_system") and p_doc.get("id"):
                    try:
                        await prompts_col.update_one(
                            {"id": p_doc["id"], **ws_scope},
                            {"$inc": {"runs_count": 1}},
                        )
                    except Exception as exc:
                        logger.debug("Prompt runs_count increment skipped for prompt=%s (%s)", p_doc.get("id"), type(exc).__name__)
    else:
        # Prompt instructions are not executed by the live runner unless resolved.
        rendered_text = token_pattern.sub(
            lambda match: f"[Prompt guidance not generated: {match.group(1).strip()}]",
            rendered_text,
        )

    sender_name = current_user.get("name") or "You"
    improved_template = req.template
    if req.improve_copy and isinstance(req.template, str) and req.template.strip():
        improved_template = req.template.strip()
        # Replace common bracketed example placeholders with specific B2B phrasing while preserving {{variables}}
        bracket_replacements = {
            "pain point": "scaling predictable outbound pipeline without manual busywork",
            "benefit": "booking 3x more qualified conversations each week",
            "goal": "hitting your next revenue milestone",
            "industry": "{{industry}}",
            "topic": "modern revenue automation",
            "solution": "personalized multi-touch sequences",
            "value prop": "automating repetitive prospecting while keeping every touch human",
        }
        def _replace_bracket(m: re.Match) -> str:
            inner = m.group(1).strip().lower()
            return bracket_replacements.get(inner, f"streamlining {inner} workflows")
        improved_template = re.sub(r"(?<!✨\s)(?<!✨)\[([A-Za-z][A-Za-z0-9_\s/-]{1,39})\]", _replace_bracket, improved_template)
        if not improved_template.endswith(("?", ".", "!")):
            improved_template += "."
        if "worth a quick chat" not in improved_template.lower() and "open to" not in improved_template.lower() and len(improved_template) < 240:
            improved_template = f"{improved_template}\n\nOpen to a quick exchange on how you're approaching this at {{{{company_name}}}}?"

    return {
        "evaluated_text": rendered_text,
        "evaluated_subject": rendered_subject if req.subject is not None else None,
        "ai_generated_text": ai_generated_text,
        "improved_template": improved_template if req.improve_copy else None,
        "generation_mode": "heuristic_preview",
        "has_ai_tokens": bool(token_pattern.search(active_template)),
        "used_alternative_message": used_alternative_message,
        "missing_variables": missing_primary_vars,
        "is_illustrative_preview": not bool(resolved_lead_id),
        "selected_lead_id": resolved_lead_id,
        "available_leads": available_leads,
        "notice": (
            f"Alternative message used because profile variable(s) {', '.join(missing_primary_vars)} were missing on this lead."
            if used_alternative_message
            else (
                "AI prompt personalized against lead profile. Click 'Apply AI Copy to Step' to save finished copy for campaign launch."
                if req.evaluate_ai
                else "Prompt guidance is shown as a placeholder, not AI-generated copy. Replace it with finished message text before launching."
            )
        ),
        "lead_preview": lead_data,
        "sender_preview": {
            "name": sender_name,
            "avatar": current_user.get("avatar_url") or "",
        }
    }
