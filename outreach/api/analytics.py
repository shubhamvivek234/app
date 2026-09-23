"""
Phase 3 & Prosp AI Parity: Outreach Campaign & Account Analytics API.
Powers KPI summary metric cards and daily Sent vs Accepted bar chart.
Matches Prosp campaign analytics (prosp_campaign_analytics.jpg).
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["LinkedIn Outreach Analytics"])


@router.get("")
async def get_outreach_analytics(
    campaign_id: str | None = None,
    timeframe: str = Query("30d", description="'7d' | '14d' | '30d' | 'all'"),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns aggregated outreach KPIs (Requests, Messages, Engagement, Email)
    and daily Sent vs Accepted timeline for bar chart visualization.
    """
    workspace_id = current_user.get("default_workspace_id") or "default_ws"
    user_id = current_user.get("user_id")

    lead_clauses: list[dict[str, Any]] = [
        {"$or": [{"workspace_id": workspace_id}, {"workspace_id": user_id}, {"user_id": user_id}]}
    ]
    if campaign_id and campaign_id != "all":
        lead_clauses.append({"campaign_id": campaign_id})

    lead_query = {"$and": lead_clauses} if len(lead_clauses) > 1 else lead_clauses[0]

    # Aggregate counts from leads
    total_leads = await db.outreach_leads.count_documents(lead_query)
    contacted_leads = await db.outreach_leads.count_documents({**lead_query, "pipeline_stage": {"$in": ["contacted", "replied", "call_booked"]}})
    replied_leads = await db.outreach_leads.count_documents({**lead_query, "pipeline_stage": {"$in": ["replied", "call_booked"]}})
    booked_leads = await db.outreach_leads.count_documents({**lead_query, "pipeline_stage": "call_booked"})

    # Aggregate actual executed queue items if any
    queue_clauses: list[dict[str, Any]] = [
        {"$or": [{"workspace_id": workspace_id}, {"workspace_id": user_id}, {"user_id": user_id}]}
    ]
    if campaign_id and campaign_id != "all":
        queue_clauses.append({"campaign_id": campaign_id})
    queue_query = {"$and": queue_clauses} if len(queue_clauses) > 1 else queue_clauses[0]

    # Check for connected accounts safely
    acc_count = 0
    if hasattr(db, "outreach_accounts"):
        acc_count = await db.outreach_accounts.count_documents({
            "$or": [{"user_id": user_id}, {"workspace_id": user_id}, {"workspace_id": workspace_id}],
            "status": {"$ne": "disconnected"},
        })
    social_acc_count = 0
    if hasattr(db, "social_accounts"):
        social_acc_count = await db.social_accounts.count_documents({
            "user_id": user_id,
            "platform": {"$in": ["linkedin", "linkedin_page"]},
            "is_active": True,
        })
    has_connected_account = (acc_count + social_acc_count) > 0

    total_tasks = await db.outreach_tasks.count_documents(queue_query)
    completed_tasks = await db.outreach_tasks.count_documents({**queue_query, "status": "completed"})

    # Requests metrics (real values, zero if no activity)
    task_reqs = await db.outreach_tasks.count_documents({**queue_query, "task_type": "connection_request", "status": "completed"})
    requests_sent = task_reqs if task_reqs > 0 else contacted_leads

    lead_accepted = await db.outreach_leads.count_documents({**lead_query, "is_connected": True})
    requests_accepted = lead_accepted if lead_accepted > 0 else (replied_leads if contacted_leads > 0 else 0)
    acceptance_rate = round((requests_accepted / requests_sent) * 100, 1) if requests_sent > 0 else 0.0

    # Messages metrics
    task_msgs = await db.outreach_tasks.count_documents({**queue_query, "task_type": "send_message", "status": "completed"})
    messages_sent = task_msgs if task_msgs > 0 else (requests_accepted if requests_accepted > 0 else 0)
    messages_replied = replied_leads
    reply_rate = round((messages_replied / messages_sent) * 100, 1) if messages_sent > 0 else 0.0

    # Engagement metrics (pre-warming visits, likes, comments)
    profile_visits = await db.outreach_tasks.count_documents({**queue_query, "task_type": "visit_profile", "status": "completed"})
    post_engagements = await db.outreach_tasks.count_documents({**queue_query, "task_type": {"$in": ["like_last_post", "comment_last_post"]}, "status": "completed"})
    total_engagement = profile_visits + post_engagements

    # Days breakdown
    num_days = 14 if timeframe == "14d" else (7 if timeframe == "7d" else 30)
    now = datetime.now(timezone.utc)
    daily_chart = []

    # Daily distribution (only populate if actual activity exists)
    has_activity = (requests_sent > 0 or messages_sent > 0 or total_engagement > 0)
    for d in range(num_days - 1, -1, -1):
        day_date = now - timedelta(days=d)
        label = day_date.strftime("%d %b")
        sent = 0
        accepted = 0
        replied = 0

        if has_activity:
            # Query actual tasks for that day
            day_start = day_date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            date_filter = {"updated_at": {"$gte": day_start, "$lte": day_end}}
            sent = await db.outreach_tasks.count_documents({**queue_query, **date_filter, "status": "completed"})
            accepted = await db.outreach_leads.count_documents({**lead_query, "is_connected": True, "created_at": {"$gte": day_start, "$lte": day_end}})
            replied = await db.outreach_leads.count_documents({**lead_query, "pipeline_stage": {"$in": ["replied", "call_booked"]}, "created_at": {"$gte": day_start, "$lte": day_end}})

        daily_chart.append({
            "date": label,
            "timestamp": day_date.isoformat(),
            "sent": sent,
            "accepted": accepted,
            "replied": replied,
        })

    return {
        "has_connected_account": has_connected_account,
        "kpis": {
            "requests": {
                "sent": requests_sent,
                "accepted": requests_accepted,
                "acceptance_rate": acceptance_rate,
            },
            "messages": {
                "sent": messages_sent,
                "replied": messages_replied,
                "reply_rate": reply_rate,
            },
            "engagement": {
                "total_actions": total_engagement,
                "profile_visits": profile_visits,
                "post_engagements": post_engagements,
            },
            "email": {
                "delivered": 0,
                "deliverability_rate": 0.0,
            },
            "pipeline": {
                "total_leads": total_leads,
                "in_campaign": max(total_leads - booked_leads - replied_leads, 0),
                "replied": replied_leads,
                "call_booked": booked_leads,
            }
        },
        "daily_chart": daily_chart,
        "timeframe": timeframe,
        "campaign_id": campaign_id or "all",
    }
