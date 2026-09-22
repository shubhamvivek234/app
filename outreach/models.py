"""
Phase 1: Isolated Data Schemas & Models for LinkedIn Outbound & AI Sequence Engine.
All schemas are strict Pydantic v2 models decoupled from core inbound logic.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── Account Enums & Sub-models ─────────────────────────────────────────────

class AccountAuthMode(str, Enum):
    COOKIE = "cookie"
    CREDENTIALS = "credentials"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    CHECKPOINT = "checkpoint"
    WARMING = "warming"
    PAUSED = "paused"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class ProxyStatus(str, Enum):
    HEALTHY = "healthy"
    FAILED = "failed"
    ROTATING = "rotating"
    UNASSIGNED = "unassigned"


class ProxyConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    proxy_id: str = Field(default_factory=generate_uuid)
    provider: str = "webshare"
    host: str
    port: int
    username: str
    password_enc: str  # Fernet encrypted password
    country_code: str = "US"
    status: ProxyStatus = ProxyStatus.HEALTHY
    assigned_at: datetime = Field(default_factory=utc_now)
    last_health_check: datetime = Field(default_factory=utc_now)


class DailyLimits(BaseModel):
    """Configured daily caps per sender to guarantee account safety."""
    connection_invites: int = 20
    messages: int = 20
    voice_notes: int = 20
    inmails: int = 20
    profile_visits: int = 20
    follows: int = 20
    post_likes: int = 20
    comments: int = 20


class DailyCounters(BaseModel):
    """Running tally for the current 24-hour cycle. Resets daily."""
    date: str = ""  # YYYY-MM-DD
    connection_invites: int = 0
    messages: int = 0
    voice_notes: int = 0
    inmails: int = 0
    profile_visits: int = 0
    follows: int = 0
    post_likes: int = 0
    comments: int = 0


class OutreachAccount(BaseModel):
    """A connected LinkedIn sender account mapped 1:1 to a static residential proxy."""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=generate_uuid)
    workspace_id: str
    user_id: str
    account_name: str
    avatar_url: str | None = None
    linkedin_urn: str | None = None
    vanity_name: str | None = None
    auth_mode: AccountAuthMode = AccountAuthMode.COOKIE
    session_cookie_enc: str = ""  # Encrypted li_at
    jsession_id: str = ""
    status: AccountStatus = AccountStatus.ACTIVE
    country_code: str = "US"
    proxy: ProxyConfig | None = None
    limits: DailyLimits = Field(default_factory=DailyLimits)
    counters: DailyCounters = Field(default_factory=DailyCounters)
    warmup_level: int = 1  # 1 (5/day) to 4 (20/day)
    warmup_started_at: datetime = Field(default_factory=utc_now)
    last_active_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


# ── Campaign & Schedule Models ─────────────────────────────────────────────

class CampaignStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class WorkingSchedule(BaseModel):
    """Defines the active time window in the prospect's/sender's timezone."""
    timezone: str = "UTC"
    start_time: str = "09:00"  # HH:MM 24h
    end_time: str = "17:00"    # HH:MM 24h
    days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])  # Mon=0, Fri=4


class OutreachCampaign(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=generate_uuid)
    workspace_id: str
    user_id: str
    name: str
    status: CampaignStatus = CampaignStatus.DRAFT
    sender_account_ids: list[str] = Field(default_factory=list)  # Sender pooling
    schedule: WorkingSchedule = Field(default_factory=WorkingSchedule)
    limits: DailyLimits = Field(default_factory=DailyLimits)
    leads_count: int = 0
    leads_contacted: int = 0
    replies_count: int = 0
    acceptances_count: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


# ── Sequence DAG Nodes & Edges ──────────────────────────────────────────────

class SequenceNodeType(str, Enum):
    # LinkedIn Actions
    VISIT_PROFILE = "visit_profile"
    CONNECTION_REQUEST = "connection_request"
    SEND_MESSAGE = "send_message"
    VOICE_NOTE = "voice_note"
    INMAIL = "inmail"
    FOLLOW = "follow"
    LIKE_LAST_POST = "like_last_post"
    COMMENT_LAST_POST = "comment_last_post"
    REPLY_TO_COMMENT = "reply_to_comment"
    ENDORSE_SKILLS = "endorse_skills"
    # Conditions & Triggers
    IF_CONNECTED = "if_connected"
    IF_OPENED_MESSAGE = "if_opened_message"
    OPEN_PROFILE_CHECK = "open_profile_check"
    HAS_DATA_IN_COLUMN = "has_data_in_column"


class SequenceNode(BaseModel):
    id: str
    type: SequenceNodeType
    title: str = ""
    delay_hours: int = 0  # Hours to wait before executing this step
    config: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})


class SequenceEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str | None = None  # e.g., "accepted", "not accepted yet", "replied", "no reply"


class OutreachSequence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=generate_uuid)
    campaign_id: str
    nodes: list[SequenceNode] = Field(default_factory=list)
    edges: list[SequenceEdge] = Field(default_factory=list)
    compiled_dag: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utc_now)


# ── Leads & Execution State ────────────────────────────────────────────────

class LeadExecutionState(str, Enum):
    QUEUED = "queued"
    WAITING_DELAY = "waiting_delay"
    WAITING_TRIGGER = "waiting_trigger"
    ACCEPTED = "accepted"
    REPLIED = "replied"
    FINISHED = "finished"
    BOUNCED = "bounced"
    FAILED = "failed"


class OutreachLead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=generate_uuid)
    campaign_id: str
    workspace_id: str
    assigned_account_id: str | None = None
    linkedin_url: str
    first_name: str = ""
    last_name: str = ""
    company_name: str = ""
    job_title: str = ""
    location: str = ""
    email: str | None = None
    phone: str | None = None
    custom_variables: dict[str, str] = Field(default_factory=dict)
    
    # State tracking
    current_node_id: str | None = None
    execution_state: LeadExecutionState = LeadExecutionState.QUEUED
    next_action_due_at: datetime | None = None
    last_action_taken: str | None = None
    last_action_at: datetime | None = None
    is_connected: bool = False
    has_replied: bool = False
    created_at: datetime = Field(default_factory=utc_now)


# ── AI Voice Cloning Models ────────────────────────────────────────────────

class OutreachVoice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=generate_uuid)
    workspace_id: str
    name: str
    elevenlabs_voice_id: str
    sample_audio_url: str = ""
    assigned_account_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


# ── Unified Inbox & Messages ───────────────────────────────────────────────

class MessageSenderType(str, Enum):
    LEAD = "lead"
    USER = "user"


class OutreachInboxMessage(BaseModel):
    id: str = Field(default_factory=generate_uuid)
    sender_type: MessageSenderType
    sender_name: str
    sender_urn: str = ""
    body: str
    audio_url: str | None = None
    is_voice_note: bool = False
    timestamp: datetime = Field(default_factory=utc_now)


class OutreachInboxThread(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=generate_uuid)
    workspace_id: str
    account_id: str  # Connected sender account that received it
    lead_id: str | None = None
    lead_name: str
    lead_avatar: str | None = None
    lead_headline: str | None = None
    lead_urn: str
    last_message_snippet: str = ""
    last_message_at: datetime = Field(default_factory=utc_now)
    unread_count: int = 0
    intent_tag: str | None = None  # "interested", "objection", "not_interested"
    messages: list[OutreachInboxMessage] = Field(default_factory=list)
