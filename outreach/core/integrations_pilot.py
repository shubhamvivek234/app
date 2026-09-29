"""Workspace-level allowlisting and release gates for Outreach Integrations."""
from __future__ import annotations

import os


def integrations_enabled() -> bool:
    """Checks whether outreach integrations are enabled globally."""
    return os.getenv("OUTREACH_INTEGRATIONS_ENABLED", "false").strip().lower() in {"1", "true", "yes"}


def is_integrations_pilot_allowed(workspace_id: str | None = None) -> bool:
    """Checks whether integrations are enabled globally and for this specific pilot workspace."""
    if not integrations_enabled():
        return False
    allowlist = os.getenv("OUTREACH_INTEGRATIONS_PILOT_WORKSPACES", "").strip()
    if not allowlist or allowlist == "*":
        return True
    allowed_ids = {ws.strip() for ws in allowlist.split(",") if ws.strip()}
    return bool(workspace_id and workspace_id in allowed_ids)
