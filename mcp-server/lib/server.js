import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';

import { buildIdempotencyHeaders, createPublicApiClient, getErrorMessage } from './apiClient.js';

function ok(data) {
  const safeData = data ?? {};
  return {
    content: [{ type: 'text', text: JSON.stringify(safeData, null, 2) }],
    structuredContent: safeData,
  };
}

function err(message) {
  return {
    content: [{ type: 'text', text: `Error: ${message}` }],
    isError: true,
  };
}

async function call(getApi, extra, fn) {
  try {
    const api = getApi(extra);
    return ok(await fn(api, extra));
  } catch (error) {
    return err(getErrorMessage(error));
  }
}

function idempotencyConfig(extra, action) {
  const headers = buildIdempotencyHeaders(extra, action);
  return Object.keys(headers).length > 0 ? { headers } : undefined;
}

function registerToolAliases(server, tool) {
  for (const alias of tool.aliases || []) {
    server.tool(
      alias,
      `${tool.description} Deprecated alias for ${tool.name}.`,
      tool.inputSchema,
      async (args, extra) => tool.handler(args, extra),
    );
  }
}

function registerTool(server, tool) {
  server.tool(
    tool.name,
    tool.description,
    tool.inputSchema,
    async (args, extra) => tool.handler(args, extra),
  );
  registerToolAliases(server, tool);
}

export function createUnravlerMcpServer({ getApi }) {
  const server = new McpServer(
    {
      name: 'unravler',
      version: '1.1.0',
    },
    {
      capabilities: {
        logging: {},
      },
      instructions: 'Use Unravler to inspect accounts, manage posts, and review approvals. Public media URLs are supported on post create/update. Direct binary uploads are not exposed in this MCP server.',
    },
  );

  const tools = [
    {
      name: 'accounts.list',
      aliases: ['list_connected_accounts'],
      description: 'List connected social accounts for the active Unravler workspace.',
      inputSchema: {},
      handler: async (_args, extra) => call(getApi, extra, async (api) => {
        const { data } = await api.get('/accounts');
        return data;
      }),
    },
    {
      name: 'posts.list',
      aliases: ['list_posts'],
      description: 'List posts in the active workspace. Filter by status and page through results.',
      inputSchema: {
        status: z.enum(['all', 'draft', 'scheduled', 'pending_approval', 'published', 'failed']).optional()
          .describe('Optional post status filter. Use "all" to include every status.'),
        page: z.number().int().min(1).optional().describe('Page number, default 1.'),
        limit: z.number().int().min(1).max(100).optional().describe('Page size, default 20.'),
      },
      handler: async ({ status = 'all', page = 1, limit = 20 }, extra) => call(getApi, extra, async (api) => {
        const params = { page, limit };
        if (status !== 'all') {
          params.status = status;
        }
        const { data } = await api.get('/posts', { params });
        return data;
      }),
    },
    {
      name: 'posts.get',
      aliases: ['get_post'],
      description: 'Fetch one post with full metadata, media, platforms, and publishing results.',
      inputSchema: {
        post_id: z.string().min(1).describe('The Unravler post ID.'),
      },
      handler: async ({ post_id }, extra) => call(getApi, extra, async (api) => {
        const { data } = await api.get(`/posts/${post_id}`);
        return data;
      }),
    },
    {
      name: 'posts.create',
      aliases: ['create_post'],
      description: 'Create a draft, schedule a post, or publish immediately. Media URLs must already be safe public URLs.',
      inputSchema: {
        content: z.string().min(1).describe('Post caption or text body.'),
        account_ids: z.array(z.string().min(1)).min(1).describe('Target social account IDs from accounts.list.'),
        platforms: z.array(z.string().min(1)).optional().describe('Optional explicit platform list. If omitted, Unravler resolves platforms from account_ids.'),
        scheduled_at: z.string().optional().describe('Optional ISO 8601 schedule timestamp. Omit to save as draft unless publish_now is true.'),
        publish_now: z.boolean().optional().describe('Set true to publish immediately.'),
        first_comment: z.string().optional().describe('Optional first comment / link in first comment to post automatically.'),
        media_urls: z.array(z.string().url()).optional().describe('Optional list of safe public media URLs.'),
        thumbnail_urls: z.array(z.string().url()).optional().describe('Optional thumbnails, usually omitted because Unravler derives them when possible.'),
        post_type: z.string().optional().describe('Optional content type such as text, image, video, or mixed.'),
      },
      handler: async (args, extra) => call(getApi, extra, async (api) => {
        const { data } = await api.post('/posts', args, idempotencyConfig(extra, 'posts.create'));
        return data;
      }),
    },
    {
      name: 'posts.update',
      aliases: ['update_post'],
      description: 'Update a draft or scheduled post. If version is omitted, Unravler resolves the latest version automatically.',
      inputSchema: {
        post_id: z.string().min(1).describe('The post ID to update.'),
        content: z.string().optional().describe('Updated caption or text body.'),
        first_comment: z.string().optional().describe('Optional updated first comment.'),
        scheduled_at: z.union([z.string(), z.null()]).optional().describe('ISO 8601 scheduled time, or null to clear the schedule.'),
        platforms: z.array(z.string().min(1)).optional().describe('Optional replacement platform list.'),
        account_ids: z.array(z.string().min(1)).optional().describe('Optional replacement account list.'),
        media_urls: z.array(z.string().url()).optional().describe('Optional replacement media URLs. Use an empty array to clear media.'),
        post_type: z.string().optional().describe('Optional replacement post type.'),
        version: z.number().int().min(1).optional().describe('Optional optimistic-lock version override.'),
      },
      handler: async ({ post_id, ...body }, extra) => call(getApi, extra, async (api) => {
        const { data } = await api.patch(`/posts/${post_id}`, body, idempotencyConfig(extra, 'posts.update'));
        return data;
      }),
    },
    {
      name: 'posts.delete',
      aliases: ['delete_post'],
      description: 'Delete a post. Unravler will revoke queued publishing work and orphan-cleanup media when safe.',
      inputSchema: {
        post_id: z.string().min(1).describe('The post ID to delete.'),
      },
      handler: async ({ post_id }, extra) => call(getApi, extra, async (api) => {
        await api.delete(`/posts/${post_id}`, idempotencyConfig(extra, 'posts.delete'));
        return { deleted: true, post_id };
      }),
    },
    {
      name: 'posts.retry',
      aliases: ['retry_failed_post'],
      description: 'Retry a failed or partially failed post, optionally for a single platform.',
      inputSchema: {
        post_id: z.string().min(1).describe('The failed post ID.'),
        platform: z.string().optional().describe('Optional platform to retry, such as instagram or youtube.'),
      },
      handler: async ({ post_id, platform }, extra) => call(getApi, extra, async (api) => {
        const config = {
          ...(idempotencyConfig(extra, 'posts.retry') || {}),
          params: platform ? { platform } : undefined,
        };
        const { data } = await api.post(`/posts/${post_id}/retry`, {}, config);
        return data;
      }),
    },
    {
      name: 'approvals.list',
      aliases: ['list_approvals'],
      description: 'List approval queue buckets for the active workspace, including awaiting, expired, and changes-requested items.',
      inputSchema: {
        limit: z.number().int().min(1).max(100).optional().describe('Per-bucket page size, default 25.'),
      },
      handler: async ({ limit = 25 }, extra) => call(getApi, extra, async (api) => {
        const { data } = await api.get('/approvals', { params: { limit } });
        return data;
      }),
    },
    {
      name: 'approvals.submit',
      aliases: ['submit_post_for_review'],
      description: 'Submit a scheduled draft for review. The draft must have a future scheduled time.',
      inputSchema: {
        post_id: z.string().min(1).describe('Draft post ID.'),
        content: z.string().optional().describe('Optional updated content to save before submitting for review.'),
      },
      handler: async ({ post_id, content }, extra) => call(getApi, extra, async (api) => {
        const { data } = await api.post(
          `/posts/${post_id}/submit-review`,
          content ? { content } : {},
          idempotencyConfig(extra, 'approvals.submit'),
        );
        return data;
      }),
    },
    {
      name: 'approvals.approve',
      aliases: ['approve_post'],
      description: 'Approve a pending approval item so it can move back to scheduled status.',
      inputSchema: {
        post_id: z.string().min(1).describe('Pending approval post ID.'),
      },
      handler: async ({ post_id }, extra) => call(getApi, extra, async (api) => {
        const { data } = await api.post(
          `/posts/${post_id}/approve`,
          {},
          idempotencyConfig(extra, 'approvals.approve'),
        );
        return data;
      }),
    },
    {
      name: 'approvals.reject',
      aliases: ['reject_post'],
      description: 'Reject a pending approval item and send it back to draft with a reason.',
      inputSchema: {
        post_id: z.string().min(1).describe('Pending approval post ID.'),
        reason: z.string().optional().describe('Optional rejection reason.'),
      },
      handler: async ({ post_id, reason }, extra) => call(getApi, extra, async (api) => {
        const { data } = await api.post(
          `/posts/${post_id}/reject`,
          reason ? { reason } : {},
          idempotencyConfig(extra, 'approvals.reject'),
        );
        return data;
      }),
    },
    {
      name: 'approvals.return_to_draft',
      aliases: ['return_post_to_draft'],
      description: 'Return an expired approval item to draft so it can be rescheduled.',
      inputSchema: {
        post_id: z.string().min(1).describe('Expired approval post ID.'),
      },
      handler: async ({ post_id }, extra) => call(getApi, extra, async (api) => {
        const { data } = await api.post(
          `/posts/${post_id}/return-to-draft`,
          {},
          idempotencyConfig(extra, 'approvals.return_to_draft'),
        );
        return data;
      }),
    },
    {
      name: 'approvals.resubmit',
      aliases: ['resubmit_post'],
      description: 'Resubmit a returned draft for review after it has been updated and rescheduled.',
      inputSchema: {
        post_id: z.string().min(1).describe('Draft post ID.'),
        content: z.string().optional().describe('Optional updated content before resubmitting.'),
      },
      handler: async ({ post_id, content }, extra) => call(getApi, extra, async (api) => {
        const { data } = await api.post(
          `/posts/${post_id}/resubmit`,
          content ? { content } : {},
          idempotencyConfig(extra, 'approvals.resubmit'),
        );
        return data;
      }),
    },
    {
      name: 'stats.get',
      aliases: ['get_stats'],
      description: 'Fetch high-level workspace stats such as posts by status and connected account counts.',
      inputSchema: {},
      handler: async (_args, extra) => call(getApi, extra, async (api) => {
        const { data } = await api.get('/stats');
        return data;
      }),
    },
    {
      name: 'ai.generate',
      aliases: ['generate_content'],
      description: 'Generate platform-aware copy variants using Unravler AI.',
      inputSchema: {
        topic: z.string().min(1).describe('What the content should be about.'),
        platform: z.enum(['instagram', 'twitter', 'linkedin', 'facebook', 'threads', 'tiktok', 'youtube', 'general'])
          .describe('Platform hint for generation.'),
        tone: z.enum(['professional', 'casual', 'excited', 'funny', 'inspirational', 'informative']).optional()
          .describe('Optional tone.'),
        count: z.number().int().min(1).max(5).optional().describe('Number of variations, default 1.'),
        additional_context: z.string().optional().describe('Optional extra instructions or brand context.'),
      },
      handler: async ({ topic, platform, tone = 'casual', count = 1, additional_context }, extra) => call(getApi, extra, async (api) => {
        const { data } = await api.post(
          '/ai/generate',
          { topic, platform, tone, count, additional_context },
          idempotencyConfig(extra, 'ai.generate'),
        );
        return data;
      }),
    },
    {
      name: 'analytics.summary',
      aliases: ['get_analytics_summary'],
      description: 'Get executive performance and growth analytics summary for social platforms.',
      inputSchema: {
        days: z.number().int().min(1).max(90).optional().describe('Number of trailing days, default 30.'),
      },
      handler: async ({ days = 30 }, extra) => call(getApi, extra, async (api) => {
        const { data } = await api.get('/analytics/dashboard', { params: { days } });
        return data;
      }),
    },
  ];

  for (const tool of tools) {
    registerTool(server, tool);
  }

  return server;
}

export function createLocalApiFactory({ token, baseUrl }) {
  const api = createPublicApiClient({ token, baseUrl });
  return () => api;
}
