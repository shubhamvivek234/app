#!/usr/bin/env node
/**
 * SocialEntangler MCP Server
 * Exposes social media management tools to any MCP-compatible AI client.
 *
 * Usage:
 *   SOCIALENTANGLER_API_KEY=<key> SOCIALENTANGLER_BASE_URL=https://api.socialentangler.com node index.js
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import axios from 'axios';

// ── Config ──────────────────────────────────────────────────────────────────

const API_KEY = process.env.SOCIALENTANGLER_API_KEY;
const BASE_URL = (process.env.SOCIALENTANGLER_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

if (!API_KEY) {
  process.stderr.write('[SocialEntangler MCP] ERROR: SOCIALENTANGLER_API_KEY env var is required\n');
  process.exit(1);
}

const api = axios.create({
  baseURL: `${BASE_URL}/api/public`,
  headers: {
    'X-API-Key': API_KEY,
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

// ── Helpers ──────────────────────────────────────────────────────────────────

function ok(data) {
  return { content: [{ type: 'text', text: JSON.stringify(data, null, 2) }] };
}

function err(message) {
  return { content: [{ type: 'text', text: `Error: ${message}` }], isError: true };
}

async function call(fn) {
  try {
    return ok(await fn());
  } catch (e) {
    const msg = e?.response?.data?.detail || e?.response?.data?.message || e.message;
    return err(msg);
  }
}

// ── Server ───────────────────────────────────────────────────────────────────

const server = new McpServer({
  name: 'socialentangler',
  version: '1.0.0',
});

// ── Tool: list_connected_accounts ────────────────────────────────────────────

server.tool(
  'list_connected_accounts',
  'List all social media accounts connected to your SocialEntangler account (Instagram, Twitter/X, Facebook, LinkedIn, YouTube, TikTok, Threads, Reddit, Pinterest, Bluesky)',
  {},
  async () => call(async () => {
    const { data } = await api.get('/accounts');
    return {
      accounts: (data.accounts || []).map(a => ({
        id: a.id,
        platform: a.platform,
        username: a.username,
        status: a.status || 'active',
      })),
      total: data.total || 0,
    };
  })
);

// ── Tool: list_posts ─────────────────────────────────────────────────────────

server.tool(
  'list_posts',
  'List your posts. Filter by status: draft, scheduled, published, failed, or all.',
  {
    status: z.enum(['all', 'draft', 'scheduled', 'published', 'failed']).optional()
      .describe('Filter posts by status. Defaults to all.'),
    limit: z.number().min(1).max(50).optional()
      .describe('Max number of posts to return (1-50, default 20)'),
  },
  async ({ status, limit = 20 }) => call(async () => {
    const { data } = await api.get('/posts', { params: { limit, page: 1 } });
    let posts = (data.data || []).map(p => ({
      id: p.id,
      status: p.status,
      platforms: p.platforms,
      scheduled_at: p.scheduled_time,
      created_at: p.created_at,
      platform_results: p.platform_results,
    }));
    if (status && status !== 'all') {
      posts = posts.filter(p => p.status === status);
    }
    return { posts, total: data.total };
  })
);

// ── Tool: get_post ────────────────────────────────────────────────────────────

server.tool(
  'get_post',
  'Get full details of a specific post including platform results and media.',
  {
    post_id: z.string().describe('The post ID to retrieve'),
  },
  async ({ post_id }) => call(async () => {
    const { data } = await api.get(`/posts/${post_id}`);
    return data;
  })
);

// ── Tool: create_post ─────────────────────────────────────────────────────────

server.tool(
  'create_post',
  'Create a post — either as a draft, publish immediately, or schedule for a future time. Specify account IDs from list_connected_accounts.',
  {
    content: z.string().min(1).describe('The text content of the post'),
    account_ids: z.array(z.string()).min(1)
      .describe('List of connected account IDs to post to (get IDs from list_connected_accounts)'),
    scheduled_at: z.string().optional()
      .describe('ISO 8601 datetime to schedule the post (e.g. "2025-01-15T10:00:00Z"). Omit to save as draft.'),
    publish_now: z.boolean().optional()
      .describe('Set true to publish immediately. Overrides scheduled_at.'),
    media_urls: z.array(z.string()).optional()
      .describe('List of media URLs to attach (use upload_media first to get URLs)'),
  },
  async ({ content, account_ids, scheduled_at, publish_now, media_urls }) => call(async () => {
    const payload = {
      content,
      account_ids,
      publish_now: publish_now || false,
      ...(scheduled_at ? { scheduled_at } : {}),
      ...(media_urls?.length ? { media_urls } : {}),
    };
    const { data } = await api.post('/posts', payload);
    return data;
  })
);

// ── Tool: delete_post ─────────────────────────────────────────────────────────

server.tool(
  'delete_post',
  'Delete a post (draft, scheduled, or published). This cannot be undone.',
  {
    post_id: z.string().describe('The ID of the post to delete'),
  },
  async ({ post_id }) => call(async () => {
    await api.delete(`/posts/${post_id}`);
    return { deleted: true, post_id };
  })
);

// ── Tool: retry_failed_post ───────────────────────────────────────────────────

server.tool(
  'retry_failed_post',
  'Retry publishing a post that failed on one or more platforms.',
  {
    post_id: z.string().describe('The ID of the failed post to retry'),
  },
  async ({ post_id }) => call(async () => {
    const { data } = await api.post(`/posts/${post_id}/retry`);
    return data;
  })
);

// ── Tool: generate_content ────────────────────────────────────────────────────

server.tool(
  'generate_content',
  'Use AI to generate platform-optimized social media content. Specify the platform and tone to get tailored copy.',
  {
    topic: z.string().min(1).describe('What the post is about (e.g. "product launch", "Black Friday sale")'),
    platform: z.enum(['instagram', 'twitter', 'linkedin', 'facebook', 'threads', 'tiktok', 'youtube', 'general'])
      .describe('Target platform — content will be optimized for platform-specific style and limits'),
    tone: z.enum(['professional', 'casual', 'excited', 'funny', 'inspirational', 'informative']).optional()
      .describe('Tone of the content (default: casual)'),
    count: z.number().min(1).max(5).optional()
      .describe('Number of variations to generate (1-5, default 1)'),
    additional_context: z.string().optional()
      .describe('Extra context, brand info, hashtags to include, or specific instructions'),
  },
  async ({ topic, platform, tone = 'casual', count = 1, additional_context }) => call(async () => {
    const { data } = await api.post('/ai/generate', {
      topic,
      platform,
      tone,
      count,
      additional_context,
    });
    return data;
  })
);

// ── Tool: get_stats ────────────────────────────────────────────────────────────

server.tool(
  'get_stats',
  'Get your SocialEntangler dashboard statistics — post counts, connected accounts, failed posts, etc.',
  {},
  async () => call(async () => {
    const { data } = await api.get('/stats');
    return data;
  })
);

// ── Tool: upload_media ────────────────────────────────────────────────────────

server.tool(
  'upload_media',
  'Upload a media file from a public URL to SocialEntangler. Returns a media URL you can attach to posts using create_post.',
  {
    url: z.string().url().describe('Public URL of the image or video to upload'),
    filename: z.string().optional().describe('Optional filename for the uploaded file'),
  },
  async ({ url, filename }) => {
    // Media upload via public API key is not supported yet.
    // Use the SocialEntangler web app to upload media, then pass the URL to create_post.
    return err('Media upload via API key is not yet supported. Upload media through the SocialEntangler web app and pass the resulting URL to create_post via media_urls.');
  }
);

// ── Start ─────────────────────────────────────────────────────────────────────

const transport = new StdioServerTransport();
await server.connect(transport);
process.stderr.write('[SocialEntangler MCP] Server running\n');
