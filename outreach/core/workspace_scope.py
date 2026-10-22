"""Exact scalar workspace scope for customer-facing resource admission."""
import logging
logger = logging.getLogger(__name__)
from typing import Any


def workspace_scope(workspace_id: str) -> dict[str, Any]:
    """Reject array aliases: Mongo equality otherwise matches their members."""
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise ValueError("A scalar workspace identity is required")
    # An array containing the ID has element zero; a scalar string does not.
    # Empty arrays cannot match the required workspace equality in the first place.
    return {"workspace_id": workspace_id, "workspace_id.0": {"$exists": False}}
