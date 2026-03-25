"""
Phase 9 — Feature flag client (Unleash / Flagsmith compatible).
Provides kill-switch capability for TikTok and other risky features.
Falls back to environment variable defaults when Unleash is unavailable.
"""
import logging
import os

logger = logging.getLogger(__name__)

# ── Default flag values (env var overrides) ───────────────────────────────────
_ENV_DEFAULTS: dict[str, bool] = {
    "tiktok_enabled":              os.getenv("TIKTOK_ENABLED", "false").lower() == "true",
    "ai_caption_enabled":          os.getenv("AI_CAPTION_ENABLED", "true").lower() == "true",
    "bulk_import_enabled":         os.getenv("BULK_IMPORT_ENABLED", "true").lower() == "true",
    "recurring_posts_enabled":     os.getenv("RECURRING_POSTS_ENABLED", "true").lower() == "true",
    "public_api_enabled":          os.getenv("PUBLIC_API_ENABLED", "true").lower() == "true",
    "user_webhooks_enabled":       os.getenv("USER_WEBHOOKS_ENABLED", "true").lower() == "true",
    "mfa_enforcement_enabled":     os.getenv("MFA_ENFORCEMENT_ENABLED", "false").lower() == "true",
    "gdpr_export_enabled":         os.getenv("GDPR_EXPORT_ENABLED", "true").lower() == "true",
    "analytics_collection_enabled": os.getenv("ANALYTICS_COLLECTION_ENABLED", "true").lower() == "true",
}


class FeatureFlagClient:
    """
    Thin wrapper over Unleash SDK with env-var fallback.
    If UNLEASH_URL is not set, all flag queries use _ENV_DEFAULTS.
    """

    def __init__(self) -> None:
        self._unleash_client = None
        unleash_url = os.getenv("UNLEASH_URL")
        if unleash_url:
            try:
                from UnleashClient import UnleashClient
                self._unleash_client = UnleashClient(
                    server_url=unleash_url,
                    app_name="socialentangler",
                    custom_headers={
                        "Authorization": os.getenv("UNLEASH_CLIENT_KEY", "")
                    },
                )
                self._unleash_client.initialize_client()
                logger.info("Unleash feature flag client initialized at %s", unleash_url)
            except ImportError:
                logger.warning("UnleashClient not installed — using env var defaults")
            except Exception as exc:
                logger.warning("Unleash init failed — using env var defaults: %s", exc)

    def is_enabled(self, flag_name: str, context: dict | None = None) -> bool:
        """
        Returns True if the feature flag is enabled.
        Checks Unleash first, falls back to environment variable defaults.
        """
        if self._unleash_client:
            try:
                return self._unleash_client.is_enabled(flag_name, context or {})
            except Exception as exc:
                logger.warning("Unleash flag check failed for %s: %s", flag_name, exc)

        return _ENV_DEFAULTS.get(flag_name, False)

    def kill_switch(self, flag_name: str) -> bool:
        """
        Returns True if the feature is DISABLED (kill switch active).
        Use this to gate risky features: if kill_switch("tiktok_enabled"): return early
        """
        return not self.is_enabled(flag_name)


# Module-level singleton — imported once per process
_client: FeatureFlagClient | None = None


def get_flags() -> FeatureFlagClient:
    """Return the module-level feature flag client singleton."""
    global _client
    if _client is None:
        _client = FeatureFlagClient()
    return _client


def is_enabled(flag_name: str, context: dict | None = None) -> bool:
    """Convenience shortcut."""
    return get_flags().is_enabled(flag_name, context)
