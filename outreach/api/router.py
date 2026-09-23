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
from api.deps import get_current_user
import os

router = APIRouter(prefix="/outreach", tags=["LinkedIn Outreach Engine"])
router.include_router(accounts_router)
router.include_router(leads_router)
router.include_router(sequences_router)
router.include_router(campaigns_router)
router.include_router(voice_router)
router.include_router(inbox_router)
router.include_router(billing_router)
router.include_router(engage_router)
router.include_router(styles_router)
router.include_router(swipe_router)
router.include_router(prompts_router)
router.include_router(analytics_router)



@router.get("/health")
async def outreach_health():
    """Diagnostic health check for the outbound engine subsystem."""
    proxy_manager = JITProxyManager()
    return {
        "status": "healthy",
        "subsystem": "linkedin_outbound_engine",
        "version": "1.0.0",
        "proxy_provider_mode": "mock" if proxy_manager.is_mock else "live",
        "features": {
            "hybrid_engine": True,
            "voice_cloner": True,
            "multi_sender_pooling": True,
            "jit_zero_idle_cost": True,
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
