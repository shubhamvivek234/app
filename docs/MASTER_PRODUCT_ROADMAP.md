# Unravler — Master Product Roadmap & Feature Blueprint

This master roadmap outlines the end-to-end technical specifications, data schemas, API contracts, and user flows for expanding **Unravler** into a market-leading social media management platform.

---

## 1. Executive Summary & Brand Identity

> [!IMPORTANT]
> **Brand Name Alignment**: The platform brand name is **Unravler** (`unravler.com`, `app.unravler.com`, `api.unravler.com`). All user-facing strings, page titles, notifications, emails, and API headers are being standardized to **Unravler**.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     UNRAVLER SAAS PLATFORM                                   │
├───────────────────────────────┬───────────────────────────────┬─────────────────────────────┤
│      PUBLISHING & QUEUE       │       CLIENT & TEAM SUITE     │      GROWTH & ANALYTICS     │
│  • Multi-network Dispatch     │  • No-login Client Links      │  • Auto-UTM Campaign Engine │
│  • Weekly Timeslots Engine    │  • Inline Draft Comments      │  • Built-in Link Shortener  │
│  • Bulk CSV & Video Scheduler │  • Role Permissions (Client)  │  • Link-in-Bio Page Builder │
│  • RSS Feeds & Automations    │  • Approval Decisions         │  • Branded PDF Reports      │
│  • Evergreen Content Queues   │  • Activity Logs & Audits     │  • Best-Time Heatmaps       │
└───────────────────────────────┴───────────────────────────────┴─────────────────────────────┘
```

---

## 2. Feature Specification: Tier 1 (High-Impact Game Changers)

### Feature 1: Automated UTM Campaign Builder & Link Shortener
- **Problem**: Marketing teams manually append UTM parameters to track conversions in Google Analytics, leading to human errors and long, messy links.
- **Solution**:
  - Automatically append UTM parameters upon post scheduling:
    `?utm_source={platform}&utm_medium=social&utm_campaign={category}&utm_content={post_id}`
  - Integrated Link Shortener generating short URLs (e.g. `unrav.link/x7b9` or custom domain CNAME).
  - Track real-time click counts, country breakdown, and referrers in Unravler Analytics.

#### Database Schema (`db.short_links`):
```json
{
  "id": "link_uuid",
  "workspace_id": "ws_123",
  "short_code": "x7b9a",
  "original_url": "https://company.com/blog/growth",
  "utm_params": {
    "utm_source": "twitter",
    "utm_medium": "social",
    "utm_campaign": "Category 1",
    "utm_content": "post_uuid"
  },
  "final_url": "https://company.com/blog/growth?utm_source=twitter&utm_medium=social&utm_campaign=Category%201",
  "clicks_total": 342,
  "created_at": "2026-08-29T10:00:00Z"
}
```

---

### Feature 2: Link-in-Bio / "Start Page" Builder
- **Problem**: Instagram, TikTok, and Twitter only allow one clickable link in user bios.
- **Solution**:
  - Host a responsive, lightning-fast mobile landing page at `unravler.com/@yourusername`.
  - Grid mode: Auto-syncs scheduled/published Instagram posts so clicking any image opens its destination URL.
  - Custom buttons: Newsletter signup, YouTube embeds, WhatsApp/Telegram buttons, product catalog links.
  - Full theme customization (fonts, colors, avatars, social icon bar).

#### Database Schema (`db.bio_pages`):
```json
{
  "id": "bio_uuid",
  "workspace_id": "ws_123",
  "handle": "techbrand",
  "title": "TechBrand Official",
  "bio_description": "Building the future of developer tools 🚀",
  "avatar_url": "https://r2.unravler.com/avatars/techbrand.png",
  "theme": {
    "background_color": "#ffffff",
    "card_background": "#f8fafc",
    "text_color": "#0f172a",
    "accent_color": "#10b981",
    "button_style": "rounded-xl"
  },
  "custom_links": [
    {"id": "btn_1", "title": "Join Our Discord", "url": "https://discord.gg/...", "icon": "discord", "clicks": 128},
    {"id": "btn_2", "title": "Read Latest Blog Post", "url": "https://blog.techbrand.com", "icon": "globe", "clicks": 450}
  ],
  "social_links": {
    "twitter": "https://x.com/techbrand",
    "instagram": "https://instagram.com/techbrand",
    "youtube": "https://youtube.com/@techbrand"
  },
  "auto_sync_instagram_grid": true,
  "created_at": "2026-08-29T10:00:00Z"
}
```

---

### Feature 3: Shareable Client Review Magic Links (No-Login Approval)
- **Problem**: Clients frequently delay post approvals because logging into a full SaaS platform creates friction.
- **Solution**:
  - Workspace owners can generate a password-protected or expiring Magic Link (e.g. `app.unravler.com/review/sec_98f12...`).
  - The client opens the link on mobile or desktop without signing in.
  - Shows an interactive carousel/card stream of all posts in `pending_approval` for that client.
  - Client can 1-click **Approve All**, approve individual posts, or leave inline feedback comments.

#### Backend Endpoints:
- `POST /api/v1/approvals/share-link`: Generates a signed review token.
- `GET /api/v1/approvals/public/{token}`: Returns list of pending posts with sanitized client-visible metadata.
- `POST /api/v1/approvals/public/{token}/decision`: Submits approval or change request.

---

### Feature 4: Inline Draft Comments & Editorial Activity Thread
- **Problem**: Team members and clients have to communicate revisions in external Slack/WhatsApp chats.
- **Solution**:
  - Dedicated comment drawer on every post card (`/content-library`, `/approvals`, and Composer).
  - Supports @mentions (e.g., `@sarah please replace the second image`), timestamps, and resolved checkboxes.

#### Database Structure inside `db.posts` (`comments` array):
```json
"comments": [
  {
    "id": "comment_uuid",
    "user_id": "user_123",
    "author_name": "Sarah Connor",
    "author_avatar": "https://...",
    "text": "Great copy! Let's swap the thumbnail with the high-res Canva asset.",
    "created_at": "2026-08-29T14:30:00Z",
    "resolved": false
  }
]
```

---

## 3. Feature Specification: Tier 2 (Analytics & Power Automation)

### Feature 5: Automated Branded PDF Executive Reports
- **1-Click PDF Generation**: Client-ready report with workspace logo, date range, reach, engagement rate, top 5 posts, follower growth, and channel breakdown.
- **Automated Monthly Email Dispatch**: Celery Beat task sends reports to client emails on the 1st of every month.

### Feature 6: Evergreen Content Pools (Content Recycling)
- Organize posts into dynamic evergreen buckets (e.g. "Customer Reviews", "Product Tips").
- When a timeslot is empty, the scheduler automatically pulls the least-recently published post from the assigned evergreen pool.

### Feature 7: AI Brand Voice & Style Vault
- Define workspace-wide custom guidelines:
  - Tone (e.g. "Direct, authoritative, humorous, no buzzwords").
  - Target audience ("Founders, developers").
  - Formatting rules ("Always include bullet points and max 2 hashtags").
- Automatically applied to all AI caption generations and RSS rewrites.

---

## 4. Systematic "SocialEntangler" $\rightarrow$ "Unravler" Rebranding Plan

| Scope | Current Reference | Target Update | Action Required |
|---|---|---|---|
| **Page Titles & Meta** | `SocialEntangler` | `Unravler` | Update `public/index.html`, `<title>` tags, OpenGraph meta tags, and `manifest.json`. |
| **UI Logo & Headers** | `SocialEntangler` text | `Unravler` | Ensure `UnravlerLogo` component is used everywhere consistently. |
| **API Docs & OpenAPI** | `title="SocialEntangler API"` | `title="Unravler API"` | Update `api/main.py`. |
| **Bot User-Agents** | `SocialEntangler-Bot/1.0` | `Unravler-Bot/1.0` | Update `utils/rss_parser.py` and HTTP client headers. |
| **CSV Download Templates** | `socialentangler_bulk_template.csv` | `unravler_bulk_template.csv` | Update `api/routes/bulk_upload.py`. |
| **System Documentation** | `SocialEntangler` | `Unravler` | Update `AGENTS.md`, `README.md`, and developer guides. |
| **Internal Safety Note** | `DB_NAME`, Firebase project ID | Keep internal IDs intact | Preserve `socialentangler-b92a8` in Firebase config so production database links remain unbroken. |

---

## 5. Execution Timeline & Phases

```
Phase 1: Brand & Identity Normalization
  ├── Replace all user-facing "SocialEntangler" strings with "Unravler"
  └── Update CSV templates, page titles, and FastAPI metadata

Phase 2: Client Magic Links & Inline Draft Comments
  ├── Public tokenized approval review interface (no login required)
  └── Post draft revision comment drawer & activity threads

Phase 3: Auto-UTM Engine & Built-in Link Shortener
  ├── Automated campaign tracking parameters in Composer
  └── Analytics click tracker & redirection engine

Phase 4: Link-in-Bio Page Builder
  ├── Mobile landing page at unravler.com/@handle
  └── Drag-and-drop links & Instagram post sync
```
