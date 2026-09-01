from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl


class BlockSchedule(BaseModel):
    start_at: datetime | None = None
    end_at: datetime | None = None


class BioBlockItem(BaseModel):
    id: str
    type: Literal["link", "feed_grid", "embed", "lead_capture", "text_block", "media_card", "folder", "tab_group"]
    title: str = ""
    subtitle: str = ""
    url: str = ""
    icon: str = ""
    badge: str = ""
    is_featured: bool = False
    provider: str = ""
    embed_url: str = ""
    media_url: str = ""
    media_type: str = "image"
    layout: str = "card_left_image"
    animation: str = "none"
    tag: str = ""
    text_align: str = "left"
    size: str = "large"
    custom_styles: dict = Field(default_factory=dict)
    headline: str = ""
    subheadline: str = ""
    button_label: str = "Subscribe"
    limit: int = 6
    show_caption: bool = True
    active: bool = True
    schedule: BlockSchedule | None = None
    click_count: int = 0
    folder_items: list[dict] = Field(default_factory=list)
    is_expanded: bool = False


class SocialLinkItem(BaseModel):
    platform: str
    url: str


class ThemeConfig(BaseModel):
    preset: str = "editorial_cream"
    background_type: str = "gradient"
    background_color: str = "#FDFBF7"
    background_gradient: str = "linear-gradient(135deg, #fdfbf7 0%, #f4ede2 100%)"
    background_effect: str = "none"
    header_layout: str = "classic"
    banner_url: str = ""
    text_color: str = "#18181B"
    card_style: str = "glass_double_bezel"
    card_bg: str = "rgba(255, 255, 255, 0.85)"
    card_border: str = "rgba(0, 0, 0, 0.07)"
    card_text_color: str = "#18181B"
    card_shadow: str = ""
    button_radius: str = "rounded-2xl"
    font_family: str = "Plus Jakarta Sans"
    accent_color: str = "#4F46E5"
    card_corner_radius: int = 20
    card_border_width: int = 0
    card_shadow_depth: int = 100
    card_shadow_type: str = "soft"
    card_spacing: int = 33
    profile_picture_size: int = 50
    profile_picture_shadow: int = 0
    profile_picture_border: int = 0
    collapse_long_bio: bool = False
    social_icon_size: int = 0
    announcement_banner: str = ""
    announcement_url: str = ""
    announcement_active: bool = False
    navigation_style: str = "pills"


class SeoConfig(BaseModel):
    meta_title: str = ""
    meta_description: str = ""
    meta_image_url: str = ""


class BioSubPage(BaseModel):
    id: str
    slug: str
    title: str
    description: str = ""
    blocks: list[BioBlockItem] = Field(default_factory=list)
    seo: SeoConfig | None = None


class BioPageUpdate(BaseModel):
    handle: str
    title: str
    bio: str = ""
    avatar_url: str = ""
    verified_badge: bool = False
    theme: ThemeConfig
    social_links: list[SocialLinkItem] = Field(default_factory=list)
    blocks: list[BioBlockItem] = Field(default_factory=list)
    pages: list[BioSubPage] = Field(default_factory=list)
    active_page_id: str = "home"
    navigation_style: str = "pills"
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
