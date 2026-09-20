"""AI Agent Hub Routes for conversational social media management and autonomous operations."""
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUser, DB, VerifiedUser
from api.models.agent import (
    AgentActionCard,
    AgentChatRequest,
    AgentChatResponse,
    AgentMessage,
    AgentSessionCreate,
    AgentSessionResponse,
)
from utils.ai_image_service import generate_banner_image
from utils.content_repurposer import extract_youtube_video_id
from utils.free_llm_router import free_llm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["ai-agent"])


@router.get("/sessions", response_model=List[AgentSessionResponse])
async def list_agent_sessions(
    current_user: CurrentUser,
    db: DB,
):
    """List all AI agent chat threads for the active workspace."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    cursor = db.agent_sessions.find(
        {"workspace_id": workspace_id},
        {"_id": 0},
    ).sort("updated_at", -1).limit(30)
    sessions = await cursor.to_list(None)

    for s in sessions:
        count = await db.agent_messages.count_documents({"session_id": s["id"]})
        s["message_count"] = count
    return sessions


@router.post("/sessions", response_model=AgentSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_session(
    request: AgentSessionCreate,
    current_user: VerifiedUser,
    db: DB,
):
    """Create a new conversational agent session."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    session_doc = {
        "id": session_id,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "title": request.title or "New Strategy Thread",
        "channel_ids": request.channel_ids,
        "created_at": now,
        "updated_at": now,
    }
    await db.agent_sessions.insert_one(session_doc)

    # Insert default greeting message
    greeting_id = str(uuid.uuid4())
    greeting_doc = {
        "id": greeting_id,
        "session_id": session_id,
        "sender": "assistant",
        "text": (
            "Hey! I'm your Unravler AI Operator. I can draft multi-platform campaigns, "
            "propose optimal calendar timeslots, generate visuals, or turn YouTube videos into vertical shorts. "
            "What are we working on today?"
        ),
        "cards": [],
        "created_at": now,
    }
    await db.agent_messages.insert_one(greeting_doc)

    session_doc.pop("_id", None)
    session_doc["message_count"] = 1
    return session_doc


@router.get("/sessions/{session_id}")
async def get_agent_session(
    session_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Retrieve full message history for a specific thread."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    session = await db.agent_sessions.find_one({"id": session_id, "workspace_id": workspace_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    cursor = db.agent_messages.find({"session_id": session_id}, {"_id": 0}).sort("created_at", 1)
    messages = await cursor.to_list(100)

    return {
        "session": session,
        "messages": messages,
    }


@router.delete("/sessions/{session_id}", status_code=status.HTTP_200_OK)
async def delete_agent_session(
    session_id: str,
    current_user: VerifiedUser,
    db: DB,
):
    """Delete an AI agent chat thread and its messages."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    res = await db.agent_sessions.delete_one({"id": session_id, "workspace_id": workspace_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.agent_messages.delete_many({"session_id": session_id})
    return {"success": True, "message": "Thread deleted"}


@router.post("/sessions/{session_id}/chat", response_model=AgentChatResponse)
async def send_agent_message(
    session_id: str,
    request: AgentChatRequest,
    current_user: VerifiedUser,
    db: DB,
):
    """Send a user message to the AI agent and receive conversational actions."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id

    session = await db.agent_sessions.find_one({"id": session_id, "workspace_id": workspace_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    now = datetime.now(timezone.utc)

    # 1. Record user message
    user_msg_id = str(uuid.uuid4())
    user_msg_doc = {
        "id": user_msg_id,
        "session_id": session_id,
        "sender": "user",
        "text": request.message.strip(),
        "cards": [],
        "created_at": now,
    }
    await db.agent_messages.insert_one(user_msg_doc)

    # 2. Resolve available channels guardrail
    effective_channel_ids = request.channel_ids or session.get("channel_ids") or []
    acc_filter = {"workspace_id": workspace_id, "status": {"$ne": "deleted"}}
    if effective_channel_ids:
        acc_filter["id"] = {"$in": effective_channel_ids}

    accounts = await db.social_accounts.find(acc_filter, {"_id": 0, "id": 1, "platform": 1, "platform_username": 1}).to_list(20)
    channels_summary = ", ".join([f"{a['platform']} (@{a.get('platform_username', a['id'])})" for a in accounts]) or "No channels selected (Global draft)"

    # 3. Formulate Agent Prompt & Detect Intent
    cards: List[AgentActionCard] = []
    user_text = request.message.strip()

    # Check if YouTube link provided for video clipping
    yt_id = None
    yt_url = user_text
    yt_match = re.search(r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=[a-zA-Z0-9_-]+|youtu\.be/[a-zA-Z0-9_-]+|youtube\.com/shorts/[a-zA-Z0-9_-]+))', user_text)
    if yt_match:
        yt_url = yt_match.group(1)
        yt_id = extract_youtube_video_id(yt_url)
    else:
        yt_id = extract_youtube_video_id(user_text)

    if yt_id:
        cards.append(
            AgentActionCard(
                card_type="clipping_job",
                title=f"YouTube Video Detected ({yt_id})",
                summary="Extract viral 9:16 vertical shorts with bold subtitles",
                payload={"youtube_url": yt_url, "num_clips": 3, "fit_mode": "blur"},
                actions=[{"label": "Start Clipping Job", "action": "clip_video"}],
            )
        )

    # System instruction
    system_prompt = (
        "You are the Unravler AI Agent, an autonomous, highly experienced executive social media director. "
        "You help users craft compelling multi-channel copy, schedule drafts, plan content calendars, "
        "and repurpose assets.\n\n"
        f"Active Workspace Channels Guardrail: [{channels_summary}].\n\n"
        "Guidelines:\n"
        "- When asked to draft a post or announce something, write a polished post adapted for the selected channels.\n"
        "- Keep copy punchy, high-engagement, and formatted with clean linebreaks.\n"
        "- If the user asks for an image, propose a visual concept.\n"
        "- Maintain an energetic, confident, and professional tone."
    )

    try:
        reply_text, _, _ = await free_llm.generate_text(system_prompt, user_text)
        reply_text = reply_text.strip()
    except Exception as exc:
        logger.warning("Agent LLM call failed: %s", exc)
        reply_text = f"I'm on it! Here is a recommended draft for your channels based on: {user_text}"

    # If the user asked for a post or announcement, create a draft_post card
    post_trigger_keywords = ["post", "tweet", "announce", "draft", "write", "publish", "share", "content"]
    if any(k in user_text.lower() for k in post_trigger_keywords) and not yt_id:
        platforms = list(set([a["platform"] for a in accounts])) if accounts else ["twitter", "linkedin"]
        cards.append(
            AgentActionCard(
                card_type="draft_post",
                title="Proposed Social Draft",
                summary="Ready to open in Composer or schedule directly to your queue",
                payload={
                    "content": reply_text,
                    "platforms": platforms,
                    "account_ids": [a["id"] for a in accounts],
                },
                actions=[
                    {"label": "Open in Composer", "action": "open_composer"},
                    {"label": "Schedule to Next Timeslot", "action": "schedule_slot"},
                ],
            )
        )

    # Check for image generation intent
    if "image" in user_text.lower() or "banner" in user_text.lower() or "picture" in user_text.lower():
        img_url = generate_banner_image(user_text)
        cards.append(
            AgentActionCard(
                card_type="image_generation",
                title="Generated AI Visual Banner",
                summary="16:9 high-resolution banner created for this post",
                payload={"image_url": img_url},
                actions=[{"label": "Attach to Composer", "action": "attach_image"}],
            )
        )

    # 4. Save assistant reply
    assistant_msg_id = str(uuid.uuid4())
    assistant_msg_doc = {
        "id": assistant_msg_id,
        "session_id": session_id,
        "sender": "assistant",
        "text": reply_text,
        "cards": [c.model_dump() for c in cards],
        "created_at": datetime.now(timezone.utc),
    }
    await db.agent_messages.insert_one(assistant_msg_doc)

    # 5. Update thread title if first user message
    msg_count = await db.agent_messages.count_documents({"session_id": session_id})
    if msg_count <= 3 and session.get("title") == "New Strategy Thread":
        new_title = user_text[:35] + ("..." if len(user_text) > 35 else "")
        await db.agent_sessions.update_one(
            {"id": session_id},
            {"$set": {"title": new_title, "updated_at": datetime.now(timezone.utc)}},
        )
    else:
        await db.agent_sessions.update_one(
            {"id": session_id},
            {"$set": {"updated_at": datetime.now(timezone.utc)}},
        )

    return AgentChatResponse(
        session_id=session_id,
        reply=reply_text,
        cards=cards,
    )
