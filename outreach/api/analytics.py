"""
Phase 3 & Prosp AI Parity: Outreach Campaign & Account Analytics API.
Powers KPI summary metric cards and daily Sent vs Accepted bar chart.
Matches Prosp campaign analytics (prosp_campaign_analytics.jpg).
"""
import csv
import io
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["LinkedIn Outreach Analytics"])


@router.get("")
async def get_outreach_analytics(
    campaign_id: str | None = None,
    sender_account_id: str | None = None,
    timeframe: str = Query("30d", description="'7d' | '14d' | '30d'"),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns aggregated outreach KPIs (Requests, Messages, Engagement, Email)
    and daily Sent vs Accepted timeline for bar chart visualization.
    """
    if timeframe not in {"7d", "14d", "30d"}:
        raise HTTPException(status_code=422, detail="Invalid analytics timeframe")
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    scope = {"workspace_id": workspace_id}
    if campaign_id and campaign_id != "all":
        campaign = await db.outreach_campaigns.find_one({"id": campaign_id, **scope})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

    num_days = {"7d": 7, "14d": 14, "30d": 30}[timeframe]
    now = datetime.now(timezone.utc)
    period_start = (now - timedelta(days=num_days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)

    lead_clauses: list[dict[str, Any]] = [
        scope
    ]
    if campaign_id and campaign_id != "all":
        lead_clauses.append({"campaign_id": campaign_id})

    # Aggregate actual executed queue items if any
    queue_clauses: list[dict[str, Any]] = [
        scope
    ]
    if campaign_id and campaign_id != "all":
        queue_clauses.append({"campaign_id": campaign_id})

    if sender_account_id and sender_account_id != "all":
        sender = await db.outreach_accounts.find_one({"id": sender_account_id, **scope})
        if not sender:
            raise HTTPException(status_code=404, detail="Sender account not found")
        lead_clauses.append({"assigned_account_id": sender_account_id})
        queue_clauses.append({"account_id": sender_account_id})

    lead_query = {"$and": lead_clauses} if len(lead_clauses) > 1 else lead_clauses[0]
    queue_query = {"$and": queue_clauses} if len(queue_clauses) > 1 else queue_clauses[0]

    # Aggregate counts from leads
    total_leads = await db.outreach_leads.count_documents(lead_query)
    replied_leads = await db.outreach_leads.count_documents({"$and": [lead_query, {"pipeline_stage": "replied"}]})
    booked_leads = await db.outreach_leads.count_documents({"$and": [lead_query, {"pipeline_stage": "call_booked"}]})
    in_campaign = await db.outreach_leads.count_documents({"$and": [lead_query, {"pipeline_stage": {"$in": ["in_campaign", "contacted"]}}]})

    # Check for connected accounts safely
    acc_count = 0
    if hasattr(db, "outreach_accounts"):
        acc_count = await db.outreach_accounts.count_documents({
            **scope,
            "status": "active",
        })
    has_connected_account = acc_count > 0

    def task_filter(task_type: str | dict, date_filter: dict | None = None) -> dict:
        return {"$and": [queue_query, {"task_type": task_type, "status": "completed", **(date_filter or {"updated_at": {"$gte": period_start}})}]}

    def lead_filter(fields: dict) -> dict:
        return {"$and": [lead_query, fields]}

    # Only recorded actions count; CRM stage changes must not fabricate sends.
    requests_sent = await db.outreach_tasks.count_documents(task_filter("connection_request"))
    requests_accepted = await db.outreach_leads.count_documents(lead_filter({"is_connected": True, "accepted_at": {"$gte": period_start}}))

    # Messages metrics
    messages_sent = await db.outreach_tasks.count_documents(task_filter("send_message"))
    messages_replied = await db.outreach_leads.count_documents(lead_filter({"has_replied": True, "replied_at": {"$gte": period_start}}))

    # Email metrics (only confirmed sends and deliveries from recorded events)
    email_sent = await db.outreach_tasks.count_documents(task_filter("send_email"))
    email_delivered = 0
    deliverability_rate = None
    if email_sent > 0:
        bounces = 0
        if hasattr(db, "outreach_email_inbound_events") and hasattr(db.outreach_email_inbound_events, "count_documents"):
            bounce_filter = {**scope, "kind": "bounce", "created_at": {"$gte": period_start}}
            if sender_account_id and sender_account_id != "all":
                bounce_filter["sender_account_id"] = sender_account_id
            bounce_res = db.outreach_email_inbound_events.count_documents(bounce_filter)
            if hasattr(bounce_res, "__await__"):
                bounces = await bounce_res
            elif isinstance(bounce_res, (int, float)):
                bounces = int(bounce_res)
        email_delivered = max(0, email_sent - bounces)
        deliverability_rate = round(email_delivered / email_sent * 100, 1)

    # Engagement metrics (pre-warming visits, likes, comments)
    profile_visits = await db.outreach_tasks.count_documents(task_filter("visit_profile"))
    post_engagements = await db.outreach_tasks.count_documents(task_filter({"$in": ["like_last_post", "comment_last_post"]}))
    if hasattr(db, "outreach_engage_posts"):
        engage_filter: dict[str, Any] = {"workspace_id": workspace_id}
        if campaign_id and campaign_id != "all":
            linked_list_ids = await db.outreach_engage_lists.distinct("id", {"workspace_id": workspace_id, "campaign_id": campaign_id})
            engage_filter["list_id"] = {"$in": linked_list_ids}
        if sender_account_id and sender_account_id != "all":
            engage_filter["$or"] = [
                {"liked_by_account_id": sender_account_id},
                {"commented_by_account_id": sender_account_id},
            ]
        post_engagements += await db.outreach_engage_posts.count_documents({**engage_filter, "liked_at": {"$gte": period_start}})
        post_engagements += await db.outreach_engage_posts.count_documents({**engage_filter, "commented_at": {"$gte": period_start}})
    total_engagement = profile_visits + post_engagements

    # Days breakdown
    count_slots = asyncio.Semaphore(8)

    async def count_for_day(collection, query: dict) -> int:
        async with count_slots:
            return await collection.count_documents(query)

    async def day_summary(d: int) -> dict:
        day_date = now - timedelta(days=d)
        label = day_date.strftime("%d %b")
        day_start = day_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_range = {"$gte": day_start, "$lt": day_end}
        sent, messages_day, accepted, replied, visits_day, post_eng_day = await asyncio.gather(
            count_for_day(db.outreach_tasks, task_filter("connection_request", {"updated_at": day_range})),
            count_for_day(db.outreach_tasks, task_filter("send_message", {"updated_at": day_range})),
            count_for_day(db.outreach_leads, lead_filter({"is_connected": True, "accepted_at": day_range})),
            count_for_day(db.outreach_leads, lead_filter({"has_replied": True, "replied_at": day_range})),
            count_for_day(db.outreach_tasks, task_filter("visit_profile", {"updated_at": day_range})),
            count_for_day(db.outreach_tasks, task_filter({"$in": ["like_last_post", "comment_last_post"]}, {"updated_at": day_range})),
        )
        return {
            "date": label,
            "timestamp": day_date.isoformat(),
            "sent": sent,
            "messages_sent": messages_day,
            "accepted": accepted,
            "replied": replied,
            "profile_visits": visits_day,
            "post_engagements": post_eng_day,
        }

    daily_chart = await asyncio.gather(*(day_summary(d) for d in range(num_days - 1, -1, -1)))

    return {
        "has_connected_account": has_connected_account,
        "kpis": {
            "requests": {
                "sent": requests_sent,
                "accepted": requests_accepted,
                "acceptance_rate": round(requests_accepted / requests_sent * 100, 1) if requests_sent > 0 else None,
                "denominator": requests_sent,
            },
            "messages": {
                "sent": messages_sent,
                "replied": messages_replied,
                "reply_rate": round(messages_replied / messages_sent * 100, 1) if messages_sent > 0 else None,
                "denominator": messages_sent,
            },
            "engagement": {
                "total_actions": total_engagement,
                "profile_visits": profile_visits,
                "post_engagements": post_engagements,
            },
            "email": {
                "sent": email_sent,
                "delivered": email_delivered,
                "deliverability_rate": deliverability_rate,
                "denominator": email_sent,
            },
            "pipeline": {
                "total_leads": total_leads,
                "in_campaign": in_campaign,
                "replied": replied_leads,
                "call_booked": booked_leads,
            },
        },
        "daily_chart": daily_chart,
        "timeframe": timeframe,
        "campaign_id": campaign_id or "all",
        "sender_account_id": sender_account_id or "all",
    }


@router.get("/export")
async def export_outreach_analytics(
    campaign_id: str | None = None,
    sender_account_id: str | None = None,
    timeframe: str = Query("30d", description="'7d' | '14d' | '30d'"),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Exports daily outreach metrics as CSV.
    Headers: date,requests_sent,requests_accepted,messages_sent,messages_replied,profile_visits,post_engagements
    """
    analytics_data = await get_outreach_analytics(
        campaign_id=campaign_id,
        sender_account_id=sender_account_id,
        timeframe=timeframe,
        current_user=current_user,
        db=db,
    )
    daily_chart = analytics_data.get("daily_chart", [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "date",
        "requests_sent",
        "requests_accepted",
        "messages_sent",
        "messages_replied",
        "profile_visits",
        "post_engagements",
    ])
    for day in daily_chart:
        raw_date = day.get("timestamp", day.get("date"))
        date_str = raw_date[:10] if "T" in raw_date else raw_date
        writer.writerow([
            date_str,
            day.get("sent", 0),
            day.get("accepted", 0),
            day.get("messages_sent", 0),
            day.get("replied", 0),
            day.get("profile_visits", 0),
            day.get("post_engagements", 0),
        ])

    csv_bytes = output.getvalue().encode("utf-8")
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=outreach-analytics-{timeframe}.csv",
        },
    )


@router.get("/live-feed")
async def live_activity_feed(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Real-time Server-Sent Events (SSE) stream for live outreach touchpoints and activity.
    Broadcasts completed tasks, invitations, replies, and heartbeats at $0 infra cost.
    """
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")

    async def event_generator():
        # Initial greeting event
        init_payload = {
            "type": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "online",
        }
        yield f"event: connected\ndata: {json.dumps(init_payload)}\n\n"

        last_check = datetime.now(timezone.utc) - timedelta(minutes=10)
        try:
            while True:
                now = datetime.now(timezone.utc)
                # Check for tasks completed since last check
                recent_tasks = await db.outreach_tasks.find({
                    "workspace_id": workspace_id,
                    "status": "completed",
                    "updated_at": {"$gt": last_check, "$lte": now},
                }).sort("updated_at", -1).to_list(length=10)

                for t in recent_tasks:
                    payload = {
                        "id": t.get("id"),
                        "task_type": t.get("task_type"),
                        "campaign_id": t.get("campaign_id"),
                        "lead_id": t.get("lead_id"),
                        "account_id": t.get("account_id"),
                        "timestamp": (
                            t["updated_at"].isoformat()
                            if isinstance(t.get("updated_at"), datetime)
                            else str(t.get("updated_at", now.isoformat()))
                        ),
                    }
                    yield f"event: task_completed\ndata: {json.dumps(payload)}\n\n"

                last_check = now
                heartbeat = {
                    "type": "heartbeat",
                    "timestamp": now.isoformat(),
                }
                yield f"event: heartbeat\ndata: {json.dumps(heartbeat)}\n\n"
                await asyncio.sleep(15)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
