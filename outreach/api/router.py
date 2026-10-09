"""
Phase 1: Parent API Router for LinkedIn Outbound & AI Sequence Engine.
Mounted under /api/v1/outreach and /api/outreach. Completely isolated from inbound routes.
"""
from fastapi import APIRouter, Depends
from outreach.core.proxy_manager import JITProxyManager
from outreach.api.accounts import router as accounts_router
from outreach.api.leads import router as leads_router
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
from api.deps import get_current_user, CurrentUser, DB
import os

router = APIRouter(prefix="/outreach", tags=["LinkedIn Outreach Engine"])


async def _open_workspace(current_user: CurrentUser, db: DB) -> None:
    from outreach.core.erasure import require_open_workspace
    await require_open_workspace(current_user, db)


for child in (accounts_router, leads_router, sequences_router, campaigns_router,
        voice_router, inbox_router, billing_router, engage_router, styles_router,
        swipe_router, prompts_router, analytics_router,
        action_reconciliation_router, content_approvals_router):
    router.include_router(child, dependencies=[Depends(_open_workspace)])
router.include_router(mailboxes_router)  # OAuth callback has state/browser binding, not app JWT.
if os.getenv("OUTREACH_INTEGRATIONS_ENABLED", "false").strip().lower() in {"1", "true"}:
    # The experimental public API/webhook surface is not part of the email
    # pilot. Keep it inaccessible until its security and event delivery path
    # have been verified end to end.
    router.include_router(integrations_router, dependencies=[Depends(_open_workspace)])
    router.include_router(public_router)



@router.get("/health")
async def outreach_health():
    """Diagnostic health check for the outbound engine subsystem."""
    proxy_manager = JITProxyManager()
    return {
        "status": "healthy",
        "subsystem": "linkedin_outbound_engine",
        "version": "1.0.0",
        "proxy_provider_mode": proxy_manager.configuration_state,
        "features": {
            "hybrid_engine": True,
            "voice_cloner": True,
            "multi_sender_pooling": True,
            "dedicated_proxy_pool": True,
        },
    }


@router.get("/overview")
async def outreach_overview(current_user: dict = Depends(get_current_user)):
    """High-level stats for the Outreach dashboard (active campaigns, connected senders, leads)."""
    return {
        "user_id": current_user.get("user_id"),
        "connected_senders_count": 0,
        "active_campaigns_count": 0,
        "total_leads_enrolled": 0,
        "replies_received": 0,
        "system_status": "operational",
    }
