# LinkedIn Outbound & AI Sequence Engine: Production Architecture Document

**Author / Architect:** Antigravity Systems Architect  
**Target System:** Unravler Core Platform (`SocialEntangler`)  
**Domain:** Enterprise LinkedIn Cold Outreach, Multi-Account Pooling & Voice AI Automation  
**Target Concurrency:** 3,000 – 4,000+ Active LinkedIn Accounts (~240,000 daily actions)  
**Status:** Architecture Specification & Blueprint  

---

## 1. Executive Summary & Design Principles

This document defines the production architecture for the **LinkedIn Outbound Automation & AI Sequence Engine**, built as a completely decoupled, high-throughput subsystem within Unravler. 

### Core Architectural Mandates:
1. **Zero Coupling with Core Inbound Schedulers:** The outbound engine lives in its own domain namespace (`outreach/`), with independent database tables, dedicated Celery task queues, and isolated API routes. Failure in an outbound campaign cannot degrade standard social scheduling.
2. **Zero Cost When Idle (Just-In-Time Provisioning):** Hardware and proxy resources scale with paying users. No static residential proxy is provisioned until a customer's Stripe payment or trial authorization succeeds.
3. **Option A Hybrid Engine (Voyager API + Stealth Playwright):** 80% of lightweight network events (message sync, connection checks, profile reads) execute via LinkedIn's private Voyager REST endpoints; 20% of high-risk / DOM-specific events (login 2FA, voice note uploads, complex invites) execute via an isolated, stealth-patched Playwright headless browser pool.
4. **4,000-Account Scale Math:**
   * 4,000 accounts $\times$ 60 actions/day = 240,000 daily events.
   * Staggered across an 8-hour working day = ~8.3 actions/second average across the cluster.
   * By utilizing the Voyager API for lightweight requests (200ms) and Playwright only for DOM actions (10s), the entire 4,000-account cluster requires only **20 to 30 concurrent headless browser instances**, fitting comfortably on modest cloud infrastructure.

---

## 2. High-Level System Architecture

```
                                  SYSTEM TOPOLOGY
                                         │
 ┌───────────────────────────────────────┼───────────────────────────────────────┐
 │                                       │                                       │
 ▼                                       ▼                                       ▼
[ FRONTEND SPA: /outreach ]    [ STRIPE BILLING & WEBHOOK ]     [ EXTERNAL AI APIS ]
 • Prosp Minimalist UI          • JIT Proxy Trigger              • ElevenLabs Voice Cloning
 • React Flow DAG Canvas        • Seat Tier Scaling              • Dynamic Audio Synthesizer
 • Unified Multi-Inbox          • Subscription Lifecycle         • Free LLM Router Fallback
 └───────────────────┬───────────────────┴───────────────────────────────────────┘
                     │ REST & WebSocket
                     ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│               UNRAVLER FASTAPI GATEWAY: /api/v1/outreach/*                     │
├───────────────────┬───────────────────┬───────────────────┬────────────────────┤
│ Account Controller│ Campaign Engine   │ Lead CRM API      │ Unified Inbox API  │
│ • Cookie / 2FA    │ • DAG Compiler    │ • CSV / Sales Nav │ • Thread Aggregator│
│ • Proxy Mappings  │ • Timezone Sched  │ • Deduplication   │ • Real-time Sync   │
└───────────────────┴─────────┬─────────┴───────────────────┴────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
    [ POSTGRESQL DATABASE ]           [ REDIS 7 CLUSTER ]
    • outreach_accounts               • celery:outreach_queue
    • outreach_campaigns              • account_rate_limits (Token Bucket)
    • outreach_leads                  • proxy_health_cache
    • outreach_sequences (DAGs)       • human_delay_jitter_locks
    • outreach_inbox_threads          • real-time websocket pub/sub
              │                               │
              └───────────────┬───────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                   CELERY DISTRIBUTED OUTREACH WORKER POOL                      │
├───────────────────────────────────────────────┬────────────────────────────────┤
│           VOYAGER CLIENT WORKERS (80%)        │     STEALTH PLAYWRIGHT (20%)   │
│ • Connection Status Polling                   │ • Session 2FA Challenge Relay  │
│ • Incoming Message Sync                       │ • Voice Note Binary Upload     │
│ • Profile Data Extraction                     │ • Complex DOM Invite Injection │
│ • Account Warmup Logic                        │ • Checkpoint Detection         │
└───────────────────────┬───────────────────────┴────────────────┬───────────────┘
                        │                                        │
                        └───────────────────┬────────────────────┘
                                            ▼
                           [ DEDICATED RESIDENTIAL PROXIES ]
                           • 1:1 Sticky Static ISP/Residential IP
                           • Geographically matched to user account
                           • Automated health verification
                                            │
                                            ▼
                             [ LINKEDIN WEB & VOYAGER API ]
```

---

## 3. Database Schema & Data Models

All models reside in `outreach/models/` using SQLAlchemy Declarative Base.

### 3.1. Account & Infrastructure Mapping
```python
# outreach_accounts
id                  = Column(UUID, primary_key=True)
workspace_id        = Column(UUID, ForeignKey("workspaces.id"), index=True)
linkedin_urn        = Column(String, unique=True, index=True)
account_name        = Column(String)
avatar_url          = Column(String)
auth_mode           = Column(Enum("COOKIE", "CREDENTIALS"))
session_cookie_enc  = Column(Text)  # AES-256 encrypted li_at
jsession_id         = Column(String)
status              = Column(Enum("ACTIVE", "CHECKPOINT", "WARMING", "PAUSED", "DISCONNECTED"))
country_code        = Column(String(2)) # For geo-proxy matching

# 1:1 Static Residential Proxy Assignment
proxy_id            = Column(String)    # Webshare / Smartproxy provider ID
proxy_host          = Column(String)
proxy_port          = Column(Integer)
proxy_user          = Column(String)
proxy_pass_enc      = Column(Text)      # AES-256 encrypted
proxy_status        = Column(Enum("HEALTHY", "FAILED", "ROTATING"))

# Safety & Daily Counters (Reset daily at local midnight)
daily_invites_sent  = Column(Integer, default=0)
daily_messages_sent = Column(Integer, default=0)
daily_profile_views = Column(Integer, default=0)
warmup_level        = Column(Integer, default=1)  # 1 to 5 (e.g. 5, 10, 15, 20/day)
```

### 3.2. Campaigns & Sequence Graphs
```python
# outreach_campaigns
id                  = Column(UUID, primary_key=True)
workspace_id        = Column(UUID, ForeignKey("workspaces.id"), index=True)
name                = Column(String, nullable=False)
status              = Column(Enum("DRAFT", "ACTIVE", "PAUSED", "COMPLETED"))
sender_account_ids  = Column(ARRAY(UUID))  # Multi-account pooling pool
timezone            = Column(String, default="UTC")
working_hours_start = Column(Time, default="09:00:00")
working_hours_end   = Column(Time, default="17:00:00")
working_days        = Column(ARRAY(Integer)) # [0, 1, 2, 3, 4] (Mon-Fri)

# outreach_sequences (The DAG graph definition)
id                  = Column(UUID, primary_key=True)
campaign_id         = Column(UUID, ForeignKey("outreach_campaigns.id"), index=True)
graph_json          = Column(JSONB) # Raw React Flow nodes & edges
compiled_nodes      = Column(JSONB) # Adjacency list with execution states
```

### 3.3. Leads, CRM & Execution State
```python
# outreach_leads
id                  = Column(UUID, primary_key=True)
campaign_id         = Column(UUID, ForeignKey("outreach_campaigns.id"), index=True)
assigned_account_id = Column(UUID, ForeignKey("outreach_accounts.id"), nullable=True)
linkedin_profile_url= Column(String, nullable=False)
first_name          = Column(String)
last_name           = Column(String)
company_name        = Column(String)
job_title           = Column(String)
location            = Column(String)
email               = Column(String, nullable=True)
phone               = Column(String, nullable=True)

# Sequence Execution Pointer
current_node_id     = Column(String) # Current step in DAG
execution_state     = Column(Enum("QUEUED", "WAITING_DELAY", "WAITING_TRIGGER", "REPLIED", "ACCEPTED", "FINISHED", "BOUNCED"))
next_action_due_at  = Column(DateTime, index=True) # Earliest timestamp to fire next step
last_action_taken   = Column(String)
last_action_at      = Column(DateTime)
```

### 3.4. AI Voice Cloning & Audio Cache
```python
# outreach_voices
id                  = Column(UUID, primary_key=True)
workspace_id        = Column(UUID, ForeignKey("workspaces.id"), index=True)
name                = Column(String)
elevenlabs_voice_id = Column(String, nullable=False)
sample_audio_url    = Column(String) # Stored in Cloudflare R2
assigned_account_ids= Column(ARRAY(UUID)) # Senders using this voice

# outreach_generated_audios (Dynamic Cache)
id                  = Column(UUID, primary_key=True)
lead_id             = Column(UUID, ForeignKey("outreach_leads.id"), index=True)
voice_id            = Column(UUID, ForeignKey("outreach_voices.id"))
audio_url           = Column(String) # R2 bucket URL
duration_seconds    = Column(Float)
file_size_bytes     = Column(Integer)
```

---

## 4. High-Throughput Execution Mechanics (The Hybrid Engine)

### 4.1. Voyager Client Engine (80% of Operations)
LinkedIn's web frontend talks to internal private REST endpoints prefixed with `https://www.linkedin.com/voyager/api/`. By utilizing authenticated HTTP requests with the correct browser headers (`csrf-token`, `x-restli-protocol-version`, User-Agent) routed through the dedicated residential proxy:
* **Connection Check:** `GET /voyager/api/relationships/invitations` returns pending status without DOM overhead.
* **Inbox Poll:** `GET /voyager/api/messaging/conversations` returns real-time threads in ~180ms using only ~2KB of bandwidth.
* **Profile Extraction:** `GET /voyager/api/identity/profiles/{vanity_name}` returns structured JSON with employment history, skills, and contact data.

### 4.2. Stealth Playwright Browser Pool (20% of Operations)
When an action requires strict human simulation or binary file attachments:
* **Stealth Evasion:** Uses `playwright-extra` with `puppeteer-extra-plugin-stealth` to mask `navigator.webdriver`, patch WebGL vendor fingerprints, and randomize audio contexts.
* **Human Jitter:** Mouse paths are calculated using cubic Bezier curves (`humanize-mouse`). Keystrokes have Gaussian delays (80ms to 240ms between characters).
* **Native Voice Note Upload:** Automates the LinkedIn messaging composer to click the voice attachment button, upload the dynamic `.mp3`/`.aac` generated from ElevenLabs, and trigger the native waveform card.

---

## 5. Just-In-Time (JIT) Zero-Idle-Cost Lifecycle

```
[ Customer signs up ]
      │
      ▼
Total Cost = $0.00 (No proxy purchased, no workers allocated)
      │
      ▼
[ Customer starts 4-Day Trial / Subscribes ($79/mo) ]
      │
      ├── 1. Stripe Webhook: `invoice.payment_succeeded` / `trial_started`
      │
      ├── 2. Backend calls Webshare API:
      │      POST https://proxy.webshare.io/api/v2/proxy/order/
      │      Body: {"proxy_type": "residential", "country": user_country, "count": 1}
      │
      ├── 3. Assign static IP:port:user:pass to `outreach_accounts.proxy_id`
      │
      └── 4. Register account queue in Redis & Celery
            (Total Cost = $1.80/mo; covered by $79.00 payment)
      │
      ▼
[ Customer Cancels Subscription ]
      │
      ├── 1. Stripe Webhook: `customer.subscription.deleted`
      ├── 2. Pause all running outreach campaigns
      ├── 3. Backend calls Webshare API: `DELETE /v2/proxy/{proxy_id}/`
      └── 4. System cost immediately returns to $0.00
```

---

## 6. Safety Shield & Anti-Ban Architecture

To protect customer LinkedIn accounts from temporary restrictions or bans:
1. **Gradual Warm-Up Ramp:**
   * Day 1–4: Max 5 connection invites / 5 messages / day
   * Day 5–8: Max 10 connection invites / 10 messages / day
   * Day 9–14: Max 15 connection invites / 15 messages / day
   * Day 15+: Standard limit of 20 invites / 20 messages / day
2. **Account Pooling Distribution:**
   * If a campaign contains 600 leads and 3 senders are assigned, the campaign engine assigns 200 leads to each sender.
   * Work is executed in parallel, cutting campaign completion time by 66% while keeping each individual account well under safety thresholds.
3. **Automatic Pending Invite Withdrawal:**
   * If an account accumulates >500 pending invitations, LinkedIn's spam filters flag the account.
   * A nightly Celery cron automatically withdraws any invitation older than 21 days.
4. **Checkpoint Auto-Circuit-Breaker:**
   * If LinkedIn issues a PIN verification, CAPTCHA, or temporary restriction header (`429 Too Many Requests` or `checkpoint` redirect), the worker immediately halts all tasks for that account, updates status to `CHECKPOINT`, and sends an instant email alert to the user.

---

## 7. Value-Add Features Over Competitors (Prosp+)

1. **AI Reply Intent Classifier:** In the Unified Inbox, an incoming lead response is automatically tagged:
   * 🟢 `Interested / Meeting Request`
   * 🟡 `Objection / Pricing Question`
   * ⚪ `Information Requested`
   * 🔴 `Not Interested / Unsubscribe`
2. **One-Click AI Reply Generator:** SDRs can click a suggested response crafted from their campaign value proposition to book calls in seconds.
3. **LinkedIn Post Engager Harvester:** Directly scrape all users who liked or commented on any public thought leadership post (either the user's own post or a competitor's viral post) and auto-enroll them into a warm sequence.
4. **CRM Bi-Directional Webhooks:** Send booked leads directly to HubSpot, Salesforce, or Zapier when an acceptance or positive reply occurs.
