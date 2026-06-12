"""Shared developer token helpers for REST and MCP surfaces."""
from __future__ import annotations

import hashlib
import secrets
from typing import Iterable

from utils.roles import has_permission

PERSONAL_TOKEN_TYPE = "personal"
WORKSPACE_TOKEN_TYPE = "workspace"

PUBLIC_SCOPES_IN_ORDER: list[str] = [
    "accounts:read",
    "posts:read",
    "posts:write",
    "posts:delete",
    "approval:read",
    "approval:write",
    "stats:read",
    "ai:generate",
]

PUBLIC_READ_SCOPES: list[str] = [
    "accounts:read",
    "posts:read",
    "approval:read",
    "stats:read",
]

LEGACY_SCOPE_ALIASES: dict[str, list[str]] = {
    "read": PUBLIC_READ_SCOPES,
}

PUBLIC_SCOPE_PERMISSIONS: dict[str, str] = {
    "accounts:read": "account:read",
    "posts:read": "post:read",
    "posts:write": "post:update",
    "posts:delete": "post:delete",
    "approval:read": "approval:read",
    "approval:write": "post:update",
    "stats:read": "analytics:read",
    "ai:generate": "post:read",
}


def generate_developer_token() -> str:
    return f"unr_{secrets.token_urlsafe(32)}"


def hash_developer_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def expand_scope_aliases(scopes: Iterable[str] | None) -> list[str]:
    expanded: list[str] = []
    for raw_scope in scopes or []:
        scope = str(raw_scope or "").strip()
        if not scope:
            continue
        if scope == "*":
            if "*" not in expanded:
                expanded.append(scope)
            continue
        for item in LEGACY_SCOPE_ALIASES.get(scope, [scope]):
            if item not in expanded:
                expanded.append(item)
    return expanded


def allowed_public_scopes_for_role(role: str | None) -> list[str]:
    if not role:
        return []
    allowed: list[str] = []
    for scope in PUBLIC_SCOPES_IN_ORDER:
        permission = PUBLIC_SCOPE_PERMISSIONS[scope]
        if has_permission(role, permission):
            allowed.append(scope)
    return allowed


def normalize_requested_scopes(
    requested_scopes: Iterable[str] | None,
    *,
    allowed_scopes: Iterable[str],
    allow_wildcard: bool = False,
) -> list[str]:
    allowed = list(dict.fromkeys(str(scope) for scope in allowed_scopes))
    normalized = expand_scope_aliases(requested_scopes)
    if not normalized:
        return allowed

    if "*" in normalized:
        if not allow_wildcard:
            raise ValueError("Wildcard scope is not allowed for this token type")
        return ["*"]

    invalid = [scope for scope in normalized if scope not in PUBLIC_SCOPES_IN_ORDER]
    if invalid:
        raise ValueError(f"Unknown scopes: {', '.join(invalid)}")

    unauthorized = [scope for scope in normalized if scope not in allowed]
    if unauthorized:
        raise PermissionError(f"Scopes exceed your workspace role: {', '.join(unauthorized)}")

    return normalized


def effective_scopes(doc: dict) -> list[str]:
    scopes = doc.get("scopes") or []
    if "*" in scopes:
        return ["*"]
    return expand_scope_aliases(scopes)


def has_scope(doc: dict, required_scope: str | None) -> bool:
    if not required_scope:
        return True
    scopes = effective_scopes(doc)
    return "*" in scopes or required_scope in scopes
