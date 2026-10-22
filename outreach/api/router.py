"""
Phase 1: Parent API Router for LinkedIn Outbound & AI Sequence Engine.
Mounted under /api/v1/outreach and /api/outreach. Completely isolated from inbound routes.
"""
from fastapi import APIRouter, Depends
from outreach.core.proxy_manager import JITProxyManager
from outreach.api.accounts import router as accounts_router
from outreach.api.leads import router as leads_router
from outreach.api.lead_lists import router as lead_lists_router
from outreach.api.sequences import router as sequences_router
from outreach.api.campaigns import router as campaigns_router
from outreach.api.voice import router as voice_router
from outreach.api.inbox import router as inbox_router
from outreach.api.billing import router as billing_router
from outreach.api.engage import router as engage_router
from outreach.api.styles import router as styles_router
from outreach.api.swipe import router as swipe_router
from outreach.api.prompts import router as prompts_router
from outreach.api.analytics import router as analytics_router
from outreach.api.mailboxes import router as mailboxes_router
from outreach.api.action_reconciliation import router as action_reconciliation_router
from outreach.api.content_approvals import router as content_approvals_router
from outreach.api.integrations import router as integrations_router, public_router
from db.mongo import get_db
from outreach.api.dependencies import get_outreach_user, workspace_id as resolve_workspace_id
from outreach.core.workspace_scope import workspace_scope
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/outreach", tags=["LinkedIn Outreach Engine"])


async def _open_workspace(current_user: dict = Depends(get_outreach_user)) -> None:
    """Compatibility adapter; mounted handlers own canonical admission now."""
    return None


for child in (accounts_router, leads_router, lead_lists_router, sequences_router, campaigns_router,
        voice_router, inbox_router, billing_router, engage_router, styles_router,
        swipe_router, prompts_router, analytics_router,
        action_reconciliation_router, content_approvals_router):
    router.include_router(child)
router.include_router(mailboxes_router)  # OAuth callback has state/browser binding, not app JWT.
if os.getenv("OUTREACH_INTEGRATIONS_ENABLED", "true").strip().lower() in {"1", "true", "yes"}:
    router.include_router(integrations_router)
    router.include_router(public_router)



def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@router.get("/health")
async def outreach_health():
    """Diagnostic health check for the outbound engine subsystem."""
    proxy_manager = JITProxyManager()
    live_actions = _env_flag("OUTREACH_LIVE_ACTIONS_ENABLED", False)
    voice_enabled = _env_flag("OUTREACH_VOICE_STUDIO_ENABLED", False) and bool(
        (os.getenv("ELEVENLABS_API_KEY") or "").strip()
    )
    integrations_enabled = _env_flag("OUTREACH_INTEGRATIONS_ENABLED", True)
    conditional_auto_launch = _env_flag("OUTREACH_CONDITIONAL_AUTO_LAUNCH_ENABLED", True)
    return {
        "status": "healthy",
        "subsystem": "linkedin_outbound_engine",
        "version": "1.0.0",
        "proxy_provider_mode": proxy_manager.configuration_state,
        "live_actions_enabled": live_actions,
        "runtime_gates": {
            "live_actions_enabled": live_actions,
            "voice_studio_enabled": voice_enabled,
            "integrations_enabled": integrations_enabled,
            "conditional_auto_launch_enabled": conditional_auto_launch,
            "proxy_provider_mode": proxy_manager.configuration_state,
        },
        "features": {
            "hybrid_engine": True,
            "voice_cloner": True,
            "multi_sender_pooling": True,
            "dedicated_proxy_pool": True,
        },
    }


@router.get("/overview")
async def outreach_overview(
    current_user: dict = Depends(get_outreach_user),
    db=Depends(get_db),
):
    """High-level stats for the Outreach dashboard (active campaigns, connected senders, leads)."""
    try:
        ws_id = resolve_workspace_id(current_user)
    except Exception:
        ws_id = current_user.get("default_workspace_id") or current_user.get("workspace_id")
    connected_senders = 0
    active_campaigns = 0
    total_leads = 0
    replies_received = 0
    if ws_id and db is not None and hasattr(db, "outreach_accounts"):
        scope = workspace_scope(ws_id)
        try:
            if hasattr(db.outreach_accounts, "count_documents"):
                connected_senders = int(
                    await db.outreach_accounts.count_documents(
                        {**scope, "is_deleted": {"$ne": True}, "status": "active"}
                    )
                    or 0
                )
            if hasattr(db, "outreach_campaigns") and hasattr(db.outreach_campaigns, "count_documents"):
                active_campaigns = int(
                    await db.outreach_campaigns.count_documents(
                        {**scope, "is_deleted": {"$ne": True}, "status": "active"}
                    )
                    or 0
                )
            if hasattr(db, "outreach_leads") and hasattr(db.outreach_leads, "count_documents"):
                total_leads = int(
                    await db.outreach_leads.count_documents({**scope, "is_deleted": {"$ne": True}}) or 0
                )
                replies_received = int(
                    await db.outreach_leads.count_documents(
                        {**scope, "is_deleted": {"$ne": True}, "has_replied": True}
                    )
                    or 0
                )
        except Exception as exc:
            logger.warning("Outreach overview query degraded (%s)", type(exc).__name__)
    return {
        "user_id": current_user.get("user_id"),
        "workspace_id": ws_id,
        "connected_senders_count": connected_senders,
        "active_campaigns_count": active_campaigns,
        "total_leads_enrolled": total_leads,
        "replies_received": replies_received,
        "system_status": "operational",
    }
