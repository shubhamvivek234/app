"""Single source of truth for sequence editor and launch capabilities.

Code support is deliberately separate from operator-enabled live execution.
This catalog is sender-independent so the editor can render before a sender is
selected; launch and workers must still verify entitlement and sender health.
"""
import os

from outreach.models import SequenceNodeType


_LINKEDIN_SUPPORTED = {
    SequenceNodeType.VISIT_PROFILE.value,
    SequenceNodeType.CONNECTION_REQUEST.value,
    SequenceNodeType.SEND_MESSAGE.value,
    SequenceNodeType.VOICE_NOTE.value,
    SequenceNodeType.LIKE_LAST_POST.value,
    SequenceNodeType.IF_CONNECTED.value,
}
_EMAIL_SUPPORTED = {
    SequenceNodeType.FIND_EMAIL.value,
    SequenceNodeType.SEND_EMAIL.value,
    SequenceNodeType.IF_EMAIL_AVAILABLE.value,
}
_CONDITIONS = {
    SequenceNodeType.IF_CONNECTED.value,
    SequenceNodeType.IF_OPENED_MESSAGE.value,
    SequenceNodeType.OPEN_PROFILE_CHECK.value,
    SequenceNodeType.HAS_DATA_IN_COLUMN.value,
    SequenceNodeType.IF_EMAIL_AVAILABLE.value,
}


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").lower() in {"1", "true"}


def sequence_capabilities() -> list[dict[str, object]]:
    """Describe capability without assuming a selected sender or mailbox."""
    linkedin_live = _enabled("OUTREACH_LIVE_ACTIONS_ENABLED")
    catalog = []
    for node_type in SequenceNodeType:
        type_name = node_type.value
        email = type_name in _EMAIL_SUPPORTED
        supported = type_name in _LINKEDIN_SUPPORTED or email
        feature_enabled = True
        if type_name == SequenceNodeType.FIND_EMAIL.value:
            feature_enabled = _enabled("OUTREACH_HUNTER_ENABLED")
        elif type_name == SequenceNodeType.SEND_EMAIL.value:
            feature_enabled = _enabled("OUTREACH_EMAIL_SEND_ENABLED") and _enabled("OUTREACH_EMAIL_SYNC_ENABLED")
        elif type_name == SequenceNodeType.IF_EMAIL_AVAILABLE.value:
            feature_enabled = sequence_dispatch_enabled()
        live_enabled = supported and feature_enabled and (email or linkedin_live)
        reason = ""
        if not supported:
            reason = "This step has no verified campaign runner yet."
        elif not email and not linkedin_live:
            reason = "Live outreach is disabled for this deployment."
        elif not feature_enabled:
            reason = "This email capability is not enabled for this deployment."
        catalog.append({
            "type": type_name,
            "supported": supported,
            "builder_available": supported,
            "live_enabled": live_enabled,
            "reason": reason,
            "release_state": "implemented" if supported else "unavailable",
            "channel": "email" if email else "linkedin",
            "kind": "condition" if type_name in _CONDITIONS else "action",
        })
    return catalog


def sequence_dispatch_enabled() -> bool:
    """Email workers can run while unofficial LinkedIn actions remain disabled."""
    return (
        _enabled("OUTREACH_LIVE_ACTIONS_ENABLED")
        or (_enabled("OUTREACH_EMAIL_SEND_ENABLED") and _enabled("OUTREACH_EMAIL_SYNC_ENABLED"))
        or _enabled("OUTREACH_HUNTER_ENABLED")
    )


def sequence_capability_map() -> dict[str, dict[str, object]]:
    return {item["type"]: item for item in sequence_capabilities()}
