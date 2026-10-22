"""
Phase 3 & Prosp AI Parity: Outreach Campaign & Account Analytics API.
Powers KPI summary metric cards and daily Sent vs Accepted bar chart.
Matches Prosp campaign analytics (prosp_campaign_analytics.jpg).
"""
import csv
import io
import json
import asyncio
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from db.mongo import get_db
from outreach.api.dependencies import get_outreach_user, workspace_id
from outreach.core.activity_stream import StreamAccess, activity_events, STREAM_LIFETIME_SECONDS
from outreach.core.email_reporting import email_report
from outreach.core.linkedin_reporting import linkedin_cohort_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["LinkedIn Outreach Analytics"])


@router.get("")
async def get_outreach_analytics(
    campaign_id: str | None = None,
    sender_account_id: str | None = None,
    timeframe: str = Query("30d", description="'7d' | '14d' | '30d' | '90d'"),
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns aggregated outreach KPIs (Requests, Messages, Engagement, Email)
    and daily Sent vs Accepted timeline for bar chart visualization.
    """
    if timeframe not in {"7d", "14d", "30d", "90d"}:
        raise HTTPException(status_code=422, detail="Invalid analytics timeframe")
    workspace_id = current_user.get("default_workspace_id") or current_user.get("user_id")
    scope = {"workspace_id": workspace_id}
    if campaign_id and campaign_id != "all":
        campaign = await db.outreach_campaigns.find_one({"id": campaign_id, **scope})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

    num_days = {"7d": 7, "14d": 14, "30d": 30, "90d": 90}[timeframe]
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
        return {"$and": [queue_query, {"task_type": task_type, "status": "completed", **(date_filter or {"updated_at": {"$gte": period_start, "$lte": now}})}]}

    def lead_filter(fields: dict) -> dict:
        return {"$and": [lead_query, fields]}

    # Only recorded actions count; CRM stage changes must not fabricate sends.
    requests_sent = await db.outreach_tasks.count_documents(task_filter("connection_request"))
    requests_accepted = await db.outreach_leads.count_documents(lead_filter({"is_connected": True, "accepted_at": {"$gte": period_start, "$lte": now}}))

    # Messages metrics
    messages_sent = await db.outreach_tasks.count_documents(task_filter("send_message"))
    messages_replied = await db.outreach_leads.count_documents(lead_filter({"has_replied": True, "replied_at": {"$gte": period_start, "$lte": now}}))

    # Provider acceptance, stored bounce classification and delivery are distinct.
    email_evidence = await email_report(db, workspace=workspace_id, campaign=campaign_id,
        sender=sender_account_id, start=period_start, as_of=now)
    linkedin_cohorts = await linkedin_cohort_report(
        db, workspace=workspace_id, campaign=campaign_id, sender=sender_account_id,
        start=period_start, as_of=now)

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
        day_range = {"$gte": day_start, "$lt": day_end, "$lte": now}
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
    for day in daily_chart:
        evidence = email_evidence['daily'].get(day['timestamp'][:10], {})
        available = email_evidence['kpis']['evidence_status'] != 'unavailable'
        day.update({key: evidence.get(key, 0) if available else None
                    for key in ('email_provider_accepted', 'email_bounced')})
        day.update({'email_delivered': None, 'email_delivery_status': 'unavailable',
                    'email_evidence_status': email_evidence['kpis']['evidence_status'],
                    'email_period_start_utc': email_evidence['kpis']['period_start'],
                    'email_as_of_utc': email_evidence['kpis']['as_of'],
                    'email_cohort_basis': email_evidence['kpis']['cohort_basis'],
                    'email_bounce_basis': email_evidence['kpis']['bounce_basis']})

    # Team / Per-Sender Performance & Daily Quota Usage
    team_performance: list[dict[str, Any]] = []
    today_str = now.strftime("%Y-%m-%d")
    if hasattr(db, "outreach_accounts") and hasattr(db.outreach_accounts, "find"):
        from outreach.core.safety_shield import WarmUpGovernor
        try:
            acc_cursor = db.outreach_accounts.find({**scope, "is_deleted": {"$ne": True}})
            sender_docs = await acc_cursor.to_list(length=50) if hasattr(acc_cursor, "to_list") else []
            if not isinstance(sender_docs, list):
                sender_docs = []
        except Exception as exc:
            logger.warning("Analytics sender list query degraded for workspace=%s (%s)", workspace_id, type(exc).__name__)
            sender_docs = []

        # Preload active campaigns in this workspace for team queue health calculation
        active_campaign_ids_by_sender: dict[str, list[str]] = {}
        if hasattr(db, "outreach_campaigns") and hasattr(db.outreach_campaigns, "find"):
            try:
                active_c_cursor = db.outreach_campaigns.find({**scope, "status": "active", "is_deleted": {"$ne": True}})
                active_c_docs = await active_c_cursor.to_list(length=200) if hasattr(active_c_cursor, "to_list") else []
                if isinstance(active_c_docs, list):
                    for cdoc in active_c_docs:
                        if isinstance(cdoc, dict) and cdoc.get("id"):
                            for c_sid in (cdoc.get("sender_account_ids") or []):
                                active_campaign_ids_by_sender.setdefault(str(c_sid), []).append(str(cdoc["id"]))
            except Exception as exc:
                logger.debug("Active campaign sender map lookup skipped for workspace=%s (%s)", workspace_id, type(exc).__name__)
                active_campaign_ids_by_sender = {}

        for sdoc in sender_docs:
            if not isinstance(sdoc, dict) or not sdoc.get("id"):
                continue
            sid = sdoc["id"]
            s_task_base = {**scope, "account_id": sid, "status": "completed", "updated_at": {"$gte": period_start, "$lte": now}}
            if campaign_id and campaign_id != "all":
                s_task_base["campaign_id"] = campaign_id
            s_lead_base = {**scope, "assigned_account_id": sid}
            if campaign_id and campaign_id != "all":
                s_lead_base["campaign_id"] = campaign_id

            s_req_sent, s_req_acc, s_msg_sent, s_msg_rep, s_visits, s_inmails, s_follows, s_pending_inv = await asyncio.gather(
                db.outreach_tasks.count_documents({**s_task_base, "task_type": "connection_request"}),
                db.outreach_leads.count_documents({**s_lead_base, "is_connected": True, "accepted_at": {"$gte": period_start, "$lte": now}}),
                db.outreach_tasks.count_documents({**s_task_base, "task_type": "send_message"}),
                db.outreach_leads.count_documents({**s_lead_base, "has_replied": True, "replied_at": {"$gte": period_start, "$lte": now}}),
                db.outreach_tasks.count_documents({**s_task_base, "task_type": "visit_profile"}),
                db.outreach_tasks.count_documents({**s_task_base, "task_type": "inmail"}),
                db.outreach_tasks.count_documents({**s_task_base, "task_type": "follow"}),
                db.outreach_leads.count_documents({**scope, "assigned_account_id": sid, "execution_state": "invited", "is_connected": {"$ne": True}}),
            )
            sender_active_campaigns = active_campaign_ids_by_sender.get(sid, [])
            active_campaigns_count = len(sender_active_campaigns)
            queued_leads_count = 0
            if active_campaigns_count > 0:
                try:
                    q_cnt = await db.outreach_leads.count_documents({
                        **scope,
                        "campaign_id": {"$in": sender_active_campaigns},
                        "$or": [{"assigned_account_id": sid}, {"assigned_account_id": None}],
                        "execution_state": "queued",
                    })
                    if isinstance(q_cnt, int):
                        queued_leads_count = q_cnt
                except Exception as exc:
                    logger.debug("Queued leads count skipped for sender=%s (%s)", sid, type(exc).__name__)
                    queued_leads_count = 0
            if active_campaigns_count == 0:
                queue_health_status = "no_active_campaigns"
            elif queued_leads_count == 0:
                queue_health_status = "empty_queue"
            elif queued_leads_count < 20:
                queue_health_status = "low_queue"
            else:
                queue_health_status = "healthy"

            unread_messages_count = 0
            if hasattr(db, "outreach_inbox_threads") and hasattr(db.outreach_inbox_threads, "count_documents"):
                try:
                    u_cnt = await db.outreach_inbox_threads.count_documents({
                        **scope,
                        "account_id": sid,
                        "unread_count": {"$gt": 0},
                    })
                    if isinstance(u_cnt, int):
                        unread_messages_count = u_cnt
                except Exception as exc:
                    logger.debug("Unread inbox count skipped for sender=%s (%s)", sid, type(exc).__name__)
                    unread_messages_count = 0

            stored_pending = sdoc.get("pending_invitations_count")
            effective_pending_inv = (
                stored_pending
                if isinstance(stored_pending, int) and not isinstance(stored_pending, bool)
                else (s_pending_inv if isinstance(s_pending_inv, int) else 0)
            )
            last_active_raw = sdoc.get("last_active_at") or sdoc.get("updated_at") or sdoc.get("created_at")
            last_active_str = last_active_raw.isoformat() if isinstance(last_active_raw, datetime) else str(last_active_raw or "")

            ac_summary = WarmUpGovernor.compute_activity_control_summary(sdoc, now=now)
            counters = sdoc.get("counters") or {}
            is_today = counters.get("date") == today_str
            budget_actions: dict[str, int] = {}
            if hasattr(db, "outreach_request_budgets") and hasattr(db.outreach_request_budgets, "find_one"):
                try:
                    bdoc = await db.outreach_request_budgets.find_one({"workspace_id": workspace_id, "sender_id": sid})
                    if isinstance(bdoc, dict) and bdoc.get("day") == now.strftime("%Y%m%d") and isinstance(bdoc.get("actions"), dict):
                        budget_actions = bdoc["actions"]
                except Exception as exc:
                    logger.debug("Daily request budget lookup skipped for sender=%s (%s)", sid, type(exc).__name__)
                    budget_actions = {}
            eff_limits = ac_summary["effective_limits"]
            weekly_limit_reached = bool(sdoc.get("weekly_invite_limit_reached", False))
            weekly_reset_at = sdoc.get("weekly_invite_reset_at")
            if isinstance(weekly_reset_at, datetime) and weekly_reset_at.tzinfo is None:
                weekly_reset_at = weekly_reset_at.replace(tzinfo=timezone.utc)
            if weekly_limit_reached and isinstance(weekly_reset_at, datetime) and now >= weekly_reset_at:
                weekly_limit_reached = False
            team_performance.append({
                "account_id": sid,
                "user_id": sdoc.get("user_id") or "",
                "account_name": sdoc.get("account_name") or "LinkedIn Sender",
                "vanity_name": sdoc.get("vanity_name") or "",
                "status": sdoc.get("status") or "active",
                "premium_product": sdoc.get("premium_product") or "classic",
                "activity_control_enabled": ac_summary["activity_control_enabled"],
                "safety_status": ac_summary.get("safety_status", "manual"),
                "warmup_level": sdoc.get("warmup_level", 1),
                "connections_count": sdoc.get("connections_count"),
                "pending_invitations_count": effective_pending_inv,
                "active_campaigns_count": active_campaigns_count,
                "queued_leads_count": queued_leads_count,
                "queue_health_status": queue_health_status,
                "unread_messages_count": unread_messages_count,
                "last_active_at": last_active_str,
                "weekly_invite_limit_reached": weekly_limit_reached,
                "weekly_invite_reset_at": weekly_reset_at.isoformat() if isinstance(weekly_reset_at, datetime) else weekly_reset_at,
                "daily_usage_today": {
                    "connection_invites": max(int(counters.get("connection_invites", 0)) if is_today else 0, int(budget_actions.get("invite", 0) or 0)),
                    "messages": max(int(counters.get("messages", 0)) if is_today else 0, int(budget_actions.get("message", 0) or 0)),
                    "profile_visits": max(int(counters.get("profile_visits", 0)) if is_today else 0, int(budget_actions.get("visit", 0) or 0)),
                },
                "effective_limits": {
                    "connection_invites": eff_limits.get("connection_invites", 20),
                    "messages": eff_limits.get("messages", 20),
                    "profile_visits": eff_limits.get("profile_visits", 20),
                },
                "period_stats": {
                    "requests_sent": s_req_sent,
                    "requests_accepted": s_req_acc,
                    "acceptance_rate": round((s_req_acc / s_req_sent) * 100, 1) if s_req_sent > 0 else None,
                    "messages_sent": s_msg_sent,
                    "inmails_sent": s_inmails if isinstance(s_inmails, int) else 0,
                    "messages_replied": s_msg_rep,
                    "reply_rate": round((s_msg_rep / s_msg_sent) * 100, 1) if s_msg_sent > 0 else None,
                    "profile_visits": s_visits,
                    "follows_count": s_follows if isinstance(s_follows, int) else 0,
                },
            })

    # A/B Testing Variant Breakdown (A, B, C)
    ab_variants_breakdown: dict[str, dict[str, Any]] = {}
    if hasattr(db, "outreach_tasks") and hasattr(db.outreach_tasks, "find"):
        try:
            for vid in ("A", "B", "C"):
                v_req_sent, v_msg_sent = await asyncio.gather(
                    db.outreach_tasks.count_documents(task_filter("connection_request", {"variant_id": vid, "updated_at": {"$gte": period_start, "$lte": now}})),
                    db.outreach_tasks.count_documents(task_filter("send_message", {"variant_id": vid, "updated_at": {"$gte": period_start, "$lte": now}})),
                )
                if isinstance(v_req_sent, int) and isinstance(v_msg_sent, int) and (v_req_sent > 0 or v_msg_sent > 0):
                    ab_variants_breakdown[vid] = {
                        "variant_id": vid,
                        "requests_sent": v_req_sent,
                        "messages_sent": v_msg_sent,
                        "total_sent": v_req_sent + v_msg_sent,
                    }
        except (StopAsyncIteration, Exception) as exc:
            logger.debug("A/B variant breakdown query skipped for workspace=%s (%s)", workspace_id, type(exc).__name__)

    sequence_funnel = {
        "total_leads": total_leads,
        "profile_visits": profile_visits,
        "requests_sent": requests_sent,
        "requests_accepted": requests_accepted,
        "acceptance_rate": linkedin_cohorts["requests"]["acceptance_rate"],
        "messages_sent": messages_sent,
        "messages_replied": messages_replied,
        "reply_rate": linkedin_cohorts["messages"]["reply_rate"],
        "calls_booked": booked_leads,
        "variants_breakdown": ab_variants_breakdown,
    }

    # Prosp Parity: Peer Benchmarks ("Benchmarks against teams like yours")
    acc_rate = linkedin_cohorts["requests"]["acceptance_rate"]
    rep_rate = linkedin_cohorts["messages"]["reply_rate"]
    benchmarks = {
        "acceptance_rate": {
            "your_rate": acc_rate,
            "peer_median": 28.0,
            "top_quartile": 42.0,
            "status": (
                "insufficient_data" if acc_rate is None or linkedin_cohorts["requests"]["denominator"] < 5
                else "top_tier" if acc_rate >= 42.0
                else "above_average" if acc_rate >= 28.0
                else "below_average"
            ),
        },
        "reply_rate": {
            "your_rate": rep_rate,
            "peer_median": 12.0,
            "top_quartile": 24.0,
            "status": (
                "insufficient_data" if rep_rate is None or linkedin_cohorts["messages"]["denominator"] < 5
                else "top_tier" if rep_rate >= 24.0
                else "above_average" if rep_rate >= 12.0
                else "below_average"
            ),
        },
    }

    # Prosp Parity: "What to Fix: AI recommendations on what to change next"
    recommendations: list[dict[str, str]] = []
    if not has_connected_account:
        recommendations.append({
            "id": "connect_sender",
            "severity": "high",
            "title": "Connect an active LinkedIn sender account",
            "action": "Go to Settings → Accounts to connect a sender and dedicated residential/ISP proxy so sequences can run.",
        })
    if any(m.get("weekly_invite_limit_reached") for m in team_performance):
        recommendations.append({
            "id": "weekly_invite_cap",
            "severity": "medium",
            "title": "Weekly invitation limit reached on at least one sender",
            "action": "Invites are automatically isolated until Monday UTC while direct messages and warm-up visits continue. Add a second sender slot to distribute invite volume.",
        })
    if acc_rate is not None and linkedin_cohorts["requests"]["denominator"] >= 5 and acc_rate < 25.0:
        recommendations.append({
            "id": "low_acceptance_rate",
            "severity": "high",
            "title": f"Acceptance rate ({acc_rate}%) is below the 28% peer benchmark",
            "action": "Add a 'Visit profile' and 'Like last post' warm-up step before your Connection Request, or test a blank connection note.",
        })
    if rep_rate is not None and linkedin_cohorts["messages"]["denominator"] >= 5 and rep_rate < 10.0:
        recommendations.append({
            "id": "low_reply_rate",
            "severity": "high",
            "title": f"Message reply rate ({rep_rate}%) is below the 12% peer benchmark",
            "action": "Enable A/B/C message variants in your sequence or add a personalized AI Voice Note follow-up to lift response rates.",
        })
    if requests_sent >= 10 and profile_visits == 0 and post_engagements == 0:
        recommendations.append({
            "id": "missing_pre_warming",
            "severity": "medium",
            "title": "Zero pre-warming actions recorded before connection invites",
            "action": "Sequences that view profiles or engage with a post prior to connecting convert 18–25% better. Add pre-warm steps to your sequence.",
        })
    if messages_sent >= 10 and len(ab_variants_breakdown) <= 1:
        recommendations.append({
            "id": "enable_ab_testing",
            "severity": "low",
            "title": "No active A/B message split detected",
            "action": "Add Variant B in the Sequence Builder to test a shorter question-led opener against your current copy.",
        })
    if not recommendations:
        recommendations.append({
            "id": "healthy_funnel",
            "severity": "healthy",
            "title": "Campaign metrics are tracking at or above peer benchmarks",
            "action": "Continue monitoring sender Activity Control levels and scale daily limits gradually.",
        })

    # Dripify Account Stats & Recent Activity Feed (Videos #10 & #11)
    pending_invitations_count = 0
    try:
        pending_res = db.outreach_leads.count_documents(lead_filter({
            "execution_state": {"$in": ["invited", "waiting_delay"]},
            "is_connected": {"$ne": True},
        }))
        if hasattr(pending_res, "__await__"):
            pending_res = await pending_res
        if isinstance(pending_res, (int, float)):
            pending_invitations_count = int(pending_res)
    except Exception as exc:
        logger.debug("Pending invitations count skipped for workspace=%s (%s)", workspace_id, type(exc).__name__)
        pending_invitations_count = 0

    unread_inbox_count = 0
    if hasattr(db, "outreach_inbox_threads") and hasattr(db.outreach_inbox_threads, "count_documents"):
        try:
            unread_res = db.outreach_inbox_threads.count_documents({**scope, "unread_count": {"$gt": 0}})
            if hasattr(unread_res, "__await__"):
                unread_res = await unread_res
            if isinstance(unread_res, (int, float)):
                unread_inbox_count = int(unread_res)
        except Exception as exc:
            logger.debug("Unread inbox count skipped for workspace=%s (%s)", workspace_id, type(exc).__name__)
            unread_inbox_count = 0

    account_stats = {
        "pending_invitations_count": pending_invitations_count,
        "excessive_pending_invites_warning": pending_invitations_count >= 100,
        "unread_inbox_count": unread_inbox_count,
        "profile_views_count": profile_visits,
    }

    recent_activity: list[dict[str, Any]] = []
    if hasattr(db, "outreach_tasks") and hasattr(db.outreach_tasks, "find"):
        try:
            task_cursor = db.outreach_tasks.find(queue_query)
            raw_tasks = await task_cursor.to_list(length=50) if hasattr(task_cursor, "to_list") else []
            if isinstance(raw_tasks, list):
                def _ts_str(item: dict[str, Any]) -> str:
                    v = item.get("completed_at") or item.get("updated_at") or item.get("created_at") or ""
                    return v.isoformat() if isinstance(v, datetime) else str(v or "")

                sorted_tasks = sorted(
                    [t for t in raw_tasks if isinstance(t, dict) and t.get("status") in ("completed", "accepted", "skipped", "failed")],
                    key=_ts_str,
                    reverse=True,
                )[:25]
                lead_ids = list({str(t.get("lead_id")) for t in sorted_tasks if t.get("lead_id")})
                camp_ids = list({str(t.get("campaign_id")) for t in sorted_tasks if t.get("campaign_id")})
                lead_map: dict[str, dict[str, Any]] = {}
                camp_map: dict[str, str] = {}
                if lead_ids and hasattr(db, "outreach_leads") and hasattr(db.outreach_leads, "find"):
                    l_cur = db.outreach_leads.find({**scope, "id": {"$in": lead_ids}})
                    l_docs = await l_cur.to_list(length=50) if hasattr(l_cur, "to_list") else []
                    if isinstance(l_docs, list):
                        lead_map = {str(d.get("id")): d for d in l_docs if isinstance(d, dict) and d.get("id")}
                if camp_ids and hasattr(db, "outreach_campaigns") and hasattr(db.outreach_campaigns, "find"):
                    c_cur = db.outreach_campaigns.find({**scope, "id": {"$in": camp_ids}})
                    c_docs = await c_cur.to_list(length=50) if hasattr(c_cur, "to_list") else []
                    if isinstance(c_docs, list):
                        camp_map = {str(d.get("id")): str(d.get("name") or "Campaign") for d in c_docs if isinstance(d, dict) and d.get("id")}
                for t in sorted_tasks:
                    lid = str(t.get("lead_id") or "")
                    cid = str(t.get("campaign_id") or "")
                    ld = lead_map.get(lid, {})
                    lname = f"{ld.get('first_name', '')} {ld.get('last_name', '')}".strip() or ld.get("vanity_name") or "Lead"
                    recent_activity.append({
                        "id": str(t.get("id") or ""),
                        "task_type": str(t.get("task_type") or "action"),
                        "status": str(t.get("status") or "completed"),
                        "lead_id": lid,
                        "lead_name": lname,
                        "lead_company": ld.get("company_name") or "",
                        "lead_linkedin_url": ld.get("linkedin_url") or "",
                        "campaign_id": cid,
                        "campaign_name": camp_map.get(cid, "Campaign"),
                        "timestamp": _ts_str(t),
                    })
        except Exception as exc:
            logger.debug("Recent activity feed query skipped for workspace=%s (%s)", workspace_id, type(exc).__name__)
            recent_activity = []

    return {
        "has_connected_account": has_connected_account,
        "account_stats": account_stats,
        "recent_activity": recent_activity,
        "kpis": {
            "requests": {
                "sent": linkedin_cohorts["requests"]["denominator"],
                "accepted": linkedin_cohorts["requests"]["accepted"],
                "acceptance_rate": linkedin_cohorts["requests"]["acceptance_rate"],
                "denominator": linkedin_cohorts["requests"]["denominator"],
                "period_activity": {"sent": requests_sent, "accepted": requests_accepted},
                "cohort": linkedin_cohorts["requests"],
            },
            "messages": {
                "sent": linkedin_cohorts["messages"]["denominator"],
                "replied": linkedin_cohorts["messages"]["replied"],
                "reply_rate": linkedin_cohorts["messages"]["reply_rate"],
                "denominator": linkedin_cohorts["messages"]["denominator"],
                "period_activity": {"sent": messages_sent, "replied": messages_replied},
                "cohort": linkedin_cohorts["messages"],
            },
            "engagement": {
                "total_actions": total_engagement,
                "profile_visits": profile_visits,
                "post_engagements": post_engagements,
            },
            "email": email_evidence['kpis'],
            "pipeline": {
                "total_leads": total_leads,
                "in_campaign": in_campaign,
                "replied": replied_leads,
                "call_booked": booked_leads,
            },
        },
        "daily_chart": daily_chart,
        "linkedin_cohorts": linkedin_cohorts,
        "team_performance": team_performance,
        "sequence_funnel": sequence_funnel,
        "benchmarks": benchmarks,
        "recommendations": recommendations,
        "timeframe": timeframe,
        "campaign_id": campaign_id or "all",
        "sender_account_id": sender_account_id or "all",
    }


@router.get("/export")
async def export_outreach_analytics(
    campaign_id: str | None = None,
    sender_account_id: str | None = None,
    timeframe: str = Query("30d", description="'7d' | '14d' | '30d' | '90d'"),
    current_user: dict = Depends(get_outreach_user),
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
        "email_provider_accepted",
        "email_bounced",
        "email_delivered",
        "email_delivery_status",
        "email_evidence_status",
        "email_period_start_utc",
        "email_as_of_utc",
        "email_cohort_basis",
        "email_bounce_basis",
        "linkedin_cohort_basis",
        "linkedin_attribution_window_days",
        "linkedin_request_cohort_denominator",
        "linkedin_request_cohort_accepted",
        "linkedin_request_cohort_rate",
        "linkedin_message_cohort_denominator",
        "linkedin_message_cohort_replied",
        "linkedin_message_cohort_rate",
        "linkedin_cohort_status",
        "linkedin_outcome_basis",
        "linkedin_period_start_utc",
        "linkedin_as_of_utc",
        "linkedin_summary_scope",
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
            day.get("email_provider_accepted"),
            day.get("email_bounced"),
            day.get("email_delivered"),
            day.get("email_delivery_status"),
            day.get("email_evidence_status"),
            day.get("email_period_start_utc"),
            day.get("email_as_of_utc"),
            day.get("email_cohort_basis"),
            day.get("email_bounce_basis"),
            analytics_data.get("linkedin_cohorts", {}).get("basis"),
            analytics_data.get("linkedin_cohorts", {}).get("attribution_window_days"),
            analytics_data.get("linkedin_cohorts", {}).get("requests", {}).get("denominator"),
            analytics_data.get("linkedin_cohorts", {}).get("requests", {}).get("accepted"),
            analytics_data.get("linkedin_cohorts", {}).get("requests", {}).get("acceptance_rate"),
            analytics_data.get("linkedin_cohorts", {}).get("messages", {}).get("denominator"),
            analytics_data.get("linkedin_cohorts", {}).get("messages", {}).get("replied"),
            analytics_data.get("linkedin_cohorts", {}).get("messages", {}).get("reply_rate"),
            analytics_data.get("linkedin_cohorts", {}).get("status"),
            analytics_data.get("linkedin_cohorts", {}).get("outcome_basis"),
            analytics_data.get("linkedin_cohorts", {}).get("period_start"),
            analytics_data.get("linkedin_cohorts", {}).get("as_of"),
            "selected_period_summary_repeated_on_each_daily_row",
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
    request: Request = None,
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Completed-task observations with bounded, original-workspace access."""
    try:
        access = StreamAccess(current_user.get("user_id"), workspace_id(current_user),
                              current_user.get("firebase_uid"))
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid stream context") from None
    # Start before returning the response: backpressure cannot reset the lifetime.
    deadline = time.monotonic() + STREAM_LIFETIME_SECONDS

    return StreamingResponse(
        activity_events(db, access, deadline, request.headers.get('last-event-id') if request else None),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
