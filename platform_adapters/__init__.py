"""Platform adapter registry."""
from platform_adapters.base import PlatformAdapter


def get_adapter(platform: str) -> PlatformAdapter:
    from platform_adapters.instagram import InstagramAdapter
    from platform_adapters.facebook import FacebookAdapter
    from platform_adapters.youtube import YouTubeAdapter
    from platform_adapters.twitter import TwitterAdapter
    from platform_adapters.linkedin import LinkedInAdapter
    from platform_adapters.tiktok import TikTokAdapter

    registry: dict[str, type[PlatformAdapter]] = {
        "instagram": InstagramAdapter,
        "facebook": FacebookAdapter,
        "youtube": YouTubeAdapter,
        "twitter": TwitterAdapter,
        "linkedin": LinkedInAdapter,
        "tiktok": TikTokAdapter,
    }
    adapter_class = registry.get(platform.lower())
    if adapter_class is None:
        raise ValueError(f"Unknown platform: {platform}")
    return adapter_class()
