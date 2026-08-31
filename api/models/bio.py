from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl


class BlockSchedule(BaseModel):
    start_at: datetime | None = None
    end_at: datetime | None = None


class BioBlockItem(BaseModel):
    id: str
    type: Literal["link", "feed_grid", "embed", "lead_capture", "text_block", "media_card"]
    title: str = ""
    subtitle: str = ""
    url: str = ""
    icon: str = ""
    badge: str = ""
    provider: str = ""
    embed_url: str = ""
    media_url: str = ""
    headline: str = ""
    subheadline: str = ""
    button_label: str = "Subscribe"
    limit: int = 6
    show_caption: bool = True
    active: bool = True
    schedule: BlockSchedule | None = None
    click_count: int = 0


class SocialLinkItem(BaseModel):
    platform: str
    url: str


class ThemeConfig(BaseModel):
    preset: str = "editorial_cream"
    background_type: Literal["solid", "gradient", "mesh", "dark"] = "gradient"
    background_color: str = "#FDFBF7"
    background_gradient: str = "linear-gradient(135deg, #fdfbf7 0%, #f4ede2 100%)"
    text_color: str = "#18181B"
    card_style: Literal["glass_double_bezel", "solid_flat", "hard_shadow", "minimal_outline", "soft_pill"] = "glass_double_bezel"
    card_bg: str = "rgba(255, 255, 255, 0.85)"
    card_border: str = "rgba(0, 0, 0, 0.07)"
    card_text_color: str = "#18181B"
    button_radius: str = "rounded-2xl"
    font_family: str = "Plus Jakarta Sans"
    accent_color: str = "#4F46E5"


class SeoConfig(BaseModel):
    meta_title: str = ""
    meta_description: str = ""
    meta_image_url: str = ""


class BioPageUpdate(BaseModel):
    handle: str
    title: str
    bio: str = ""
    avatar_url: str = ""
    verified_badge: bool = False
    theme: ThemeConfig
    social_links: list[SocialLinkItem] = Field(default_factory=list)
    blocks: list[BioBlockItem] = Field(default_factory=list)
    custom_domain: str = ""
    seo: SeoConfig | None = None
    published: bool = True


class BioPageResponse(BaseModel):
    id: str
    workspace_id: str
    handle: str
    title: str
    bio: str
    avatar_url: str
    verified_badge: bool
    theme: ThemeConfig
    social_links: list[SocialLinkItem]
    blocks: list[BioBlockItem]
    custom_domain: str
    seo: SeoConfig
    published: bool
    total_views: int = 0
    total_clicks: int = 0
    created_at: datetime
    updated_at: datetime


class PublicBioResponse(BaseModel):
    handle: str
    title: str
    bio: str
    avatar_url: str
    verified_badge: bool
    theme: ThemeConfig
    social_links: list[SocialLinkItem]
    blocks: list[BioBlockItem]
    feed_posts: list[dict] = Field(default_factory=list)
    seo: SeoConfig


class BioTrackRequest(BaseModel):
    event_type: Literal["impression", "click"]
    block_id: str | None = None
    target_url: str | None = None
    referrer: str | None = None


class BioLeadSubscribeRequest(BaseModel):
    email: str
    source_block_id: str | None = None
