"""
Phase 5.5 — EC8: Content policy pre-publish classification.
EC23: Platform × content-type compatibility matrix.

Runs synchronously before enqueueing to catch policy violations early.
Does not make external API calls — classification is local only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── EC23 — Platform × content-type compatibility matrix ──────────────────────

# Supported (platform → set of content types)
_PLATFORM_CONTENT_TYPES: dict[str, set[str]] = {
    "instagram": {"image", "video", "carousel", "reel", "story"},
    "facebook":  {"image", "video", "carousel", "text", "story"},
    "youtube":   {"video"},
    "twitter":   {"image", "video", "text"},
    "linkedin":  {"image", "video", "text", "article"},
    "tiktok":    {"video"},
}

# Image-only platforms that cannot post text-only
_IMAGE_REQUIRED = {"instagram"}


def validate_platform_content_type(platform: str, content_type: str) -> None:
    """
    EC23 — Raise ValueError if the platform does not support content_type.
    Called before scheduling to prevent impossible publish jobs.
    """
    allowed = _PLATFORM_CONTENT_TYPES.get(platform.lower())
    if allowed is None:
        raise ValueError(f"Unknown platform: {platform}")
    if content_type.lower() not in allowed:
        raise ValueError(
            f"{platform} does not support content type '{content_type}'. "
            f"Allowed: {sorted(allowed)}"
        )
    if platform in _IMAGE_REQUIRED and content_type == "text":
        raise ValueError(f"{platform} requires media — text-only posts are not supported")


# ── EC8 — Content policy classification ──────────────────────────────────────

@dataclass
class PolicyResult:
    approved: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Patterns that are blocked across all platforms
_BLOCKED_PATTERNS = [
    re.compile(r"\b(buy\s+followers|buy\s+likes|guaranteed\s+views)\b", re.IGNORECASE),
    re.compile(r"\b(click\s+here\s+to\s+win|you\s+have\s+been\s+selected)\b", re.IGNORECASE),
    re.compile(r"\b(WhatsApp|Telegram)\s*:\s*\+?\d{7,}", re.IGNORECASE),  # phone spam
]

# Patterns that generate warnings (not blocks)
_WARNING_PATTERNS = [
    re.compile(r"#\w+\s+#\w+\s+#\w+\s+#\w+\s+#\w+\s+#\w+\s+#\w+\s+#\w+\s+#\w+\s+#\w+\s+#\w+\s+#\w+", re.IGNORECASE),  # >12 hashtags
    re.compile(r"(?:follow\s*(?:me|for\s*follow))", re.IGNORECASE),  # follow-for-follow
    re.compile(r"(?:dm\s+for\s+collab|dm\s+for\s+promo)", re.IGNORECASE),
]

# Per-platform character / hashtag limits
_PLATFORM_LIMITS: dict[str, dict] = {
    "twitter":  {"max_chars": 280, "max_hashtags": 3},
    "linkedin": {"max_chars": 3000, "max_hashtags": 5},
    "instagram": {"max_chars": 2200, "max_hashtags": 30},
    "facebook": {"max_chars": 63206, "max_hashtags": 10},
    "tiktok":   {"max_chars": 2200, "max_hashtags": 20},
    "youtube":  {"max_chars": 5000, "max_hashtags": 15},  # description
}


def check_content_policy(text: str, platform: str) -> PolicyResult:
    """
    EC8 — Classify post caption/text against content policy rules.
    Returns PolicyResult with approved flag and list of violations/warnings.
    Fast local check — does not call external moderation APIs.
    """
    violations: list[str] = []
    warnings: list[str] = []

    if not text:
        return PolicyResult(approved=True)

    # Blocked patterns
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(text):
            violations.append(f"Blocked pattern detected: {pattern.pattern[:60]}")

    # Warning patterns
    for pattern in _WARNING_PATTERNS:
        if pattern.search(text):
            warnings.append(f"Low-quality engagement pattern: {pattern.pattern[:60]}")

    # Platform-specific limits
    limits = _PLATFORM_LIMITS.get(platform.lower(), {})
    if limits:
        if len(text) > limits.get("max_chars", 999999):
            violations.append(
                f"{platform} caption exceeds {limits['max_chars']} character limit "
                f"(current: {len(text)})"
            )
        hashtag_count = len(re.findall(r"#\w+", text))
        max_ht = limits.get("max_hashtags", 9999)
        if hashtag_count > max_ht:
            warnings.append(
                f"{platform} recommends ≤{max_ht} hashtags — found {hashtag_count}"
            )

    return PolicyResult(
        approved=len(violations) == 0,
        violations=violations,
        warnings=warnings,
    )
