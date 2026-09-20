---
name: unravler
description: Manage and publish social media content across Twitter, LinkedIn, Instagram, TikTok, YouTube, Threads, Facebook, and Bluesky using the Unravler CLI and Public API.
---

# Unravler Agent Skill

This skill allows AI coding assistants (Antigravity, Cursor, Claude Code, Windsurf) to manage connected social accounts, draft posts, schedule content queues, and inspect publish statuses using the Unravler platform.

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

# List connected accounts
node cli/bin/unravler.js integrations:list

# Schedule a post across Twitter and LinkedIn
node cli/bin/unravler.js posts:create \
  --content "Exciting launch day! Check out our new platform 🚀 https://unravler.com" \
  --platforms twitter,linkedin \
  --scheduled-time "2026-10-15T14:30:00Z"

# Publish immediately
node cli/bin/unravler.js posts:create \
  --content "Breaking announcement live now!" \
  --platforms twitter \
  --publish-now

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
| `GET` | `/posts` | List posts with status, limit, and pagination filters |
| `POST` | `/posts` | Create draft, immediate publish, or future scheduled item |
| `GET` | `/posts/{id}` | Inspect post details and per-platform publish outcomes |
| `DELETE` | `/posts/{id}` | Safely remove a post and clean up scheduled jobs |
| `POST` | `/posts/{id}/retry` | Retry failed or partially failed publish attempts |

## MCP Server Integration

For direct Model Context Protocol integration, Unravler hosts an MCP endpoint:
- **HTTP SSE Endpoint**: `https://api.unravler.com/mcp`
- **Headers**: `Authorization: Bearer <PERSONAL_TOKEN>`
- **Tools Available**: `posts.create`, `posts.list`, `posts.update`, `campaigns.list`, `approvals.approve`, `stats.get`, `ai.generate`.
