---
name: unravler
description: Manage and publish social media content across Twitter, LinkedIn, Instagram, TikTok, YouTube, Threads, Facebook, and Bluesky using the Unravler CLI and Public API.
---

# Unravler Agent Skill

This skill allows AI coding assistants (Antigravity, Cursor, Claude Code, Windsurf) to manage connected social accounts, draft posts, upload media, trigger video clipping, inspect analytics, and schedule content queues using the Unravler platform.

## Prerequisites

1. Generate a Personal Token or Workspace API Key in Unravler at **Settings > Developers** (`/developers`).
2. Set the environment variable:
   ```bash
   export UNRAVLER_API_KEY="unrv_pat_..."
   # Optional custom endpoint:
   export UNRAVLER_API_URL="https://api.unravler.com"
   ```

## CLI Usage

The Unravler CLI is located in `cli/bin/unravler.js`:

```bash
# Check status and active workspace
node cli/bin/unravler.js auth:status

# Upload local media file and get URL
node cli/bin/unravler.js upload ./assets/banner.png --json

# List connected accounts
node cli/bin/unravler.js integrations:list

# Schedule a post across Twitter and LinkedIn with media
node cli/bin/unravler.js posts:create \
  --content "Exciting launch day! Check out our new platform 🚀 https://unravler.com" \
  --platforms twitter,linkedin \
  --media-urls "https://cdn.unravler.com/media/.../banner.png" \
  --scheduled-time "2026-10-15T14:30:00Z"

# Shift post between draft and schedule
node cli/bin/unravler.js posts:status <post_id> --status schedule

# View platform & post analytics
node cli/bin/unravler.js analytics:platform <account_id> --days 30
node cli/bin/unravler.js analytics:post <post_id> --days 7

# List scheduled queue as JSON
node cli/bin/unravler.js posts:list --status scheduled --json

# Delete a scheduled draft
node cli/bin/unravler.js posts:delete <post_id>
```

## REST Endpoints Reference

All endpoints are mounted under `${UNRAVLER_API_URL}/api/public` and authenticate via `Authorization: Bearer <API_KEY>`:

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/me` | Inspect token identity, permissions, and workspace role |
| `GET` | `/accounts` | List connected social accounts with platform IDs |
| `POST` | `/media/upload` | Upload a local image or video file to storage |
| `POST` | `/ai/generate-image` | Generate a high-resolution 16:9 social visual banner |
| `POST` | `/clipping/jobs` | Submit YouTube video for automated 9:16 vertical shorts clipping |
| `GET` | `/clipping/jobs/{id}` | Inspect progress and get rendered clips |
| `GET` | `/posts` | List posts with status, limit, and pagination filters |
| `POST` | `/posts` | Create draft, immediate publish, or future scheduled item |
| `GET` | `/posts/{id}` | Inspect post details and per-platform publish outcomes |
| `PATCH`| `/posts/{id}` | Update draft/scheduled post or change status |
| `DELETE`| `/posts/{id}` | Safely remove a post and clean up scheduled jobs |
| `GET` | `/analytics/platform/{id}` | Channel growth, impressions, and follower trend |
| `GET` | `/analytics/post/{id}` | Published post likes, comments, and shares metrics |

## MCP Server Integration

For direct Model Context Protocol integration, Unravler hosts an MCP endpoint:
- **Streamable HTTP Endpoint**: `https://api.unravler.com/mcp` (with `Authorization: Bearer <TOKEN>`) OR `https://api.unravler.com/mcp/<TOKEN>`
- **Tools Available**:
  - `posts.create`, `posts.list`, `posts.get`, `posts.update`, `posts.delete`, `posts.retry`
  - `clipping.create` (alias: `clippingTool`), `clipping.status` (alias: `clippingStatusTool`)
  - `image.generate` (alias: `generateImageTool`)
  - `analytics.platform`, `analytics.post`, `analytics.summary`
  - `approvals.list`, `approvals.approve`, `approvals.reject`
  - `campaigns.list`, `campaigns.get`, `calendar.get`

