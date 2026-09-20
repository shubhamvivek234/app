#!/usr/bin/env node

/**
 * Unravler CLI - Terminal & Agent Toolkit for Social Media Automation
 * Works natively in Node.js 18+ without third-party dependencies.
 */

import fs from 'fs';
import os from 'os';
import path from 'path';

const CONFIG_DIR = path.join(os.homedir(), '.unravler');
const CONFIG_FILE = path.join(CONFIG_DIR, 'config.json');

function loadConfig() {
  try {
    if (fs.existsSync(CONFIG_FILE)) {
      const data = fs.readFileSync(CONFIG_FILE, 'utf8');
      return JSON.parse(data);
    }
  } catch {}
  return {};
}

function saveConfig(cfg) {
  try {
    if (!fs.existsSync(CONFIG_DIR)) {
      fs.mkdirSync(CONFIG_DIR, { recursive: true, mode: 0o700 });
    }
    fs.writeFileSync(CONFIG_FILE, JSON.stringify(cfg, null, 2), { mode: 0o600 });
  } catch (err) {
    console.error(`Error saving config to ${CONFIG_FILE}:`, err.message);
  }
}

function parseArgs(args) {
  const flags = {};
  const positional = [];
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg.startsWith('--')) {
      const key = arg.slice(2);
      if (i + 1 < args.length && !args[i + 1].startsWith('-')) {
        const val = args[++i];
        if (flags[key] !== undefined) {
          flags[key] = Array.isArray(flags[key]) ? [...flags[key], val] : [flags[key], val];
        } else {
          flags[key] = val;
        }
      } else {
        flags[key] = true;
      }
    } else if (arg.startsWith('-')) {
      const key = arg.slice(1);
      if (i + 1 < args.length && !args[i + 1].startsWith('-')) {
        const val = args[++i];
        if (flags[key] !== undefined) {
          flags[key] = Array.isArray(flags[key]) ? [...flags[key], val] : [flags[key], val];
        } else {
          flags[key] = val;
        }
      } else {
        flags[key] = true;
      }
    } else {
      positional.push(arg);
    }
  }
  return { flags, positional };
}

async function request(endpoint, options = {}, flags = {}) {
  const config = loadConfig();
  const baseUrl = (
    flags['api-url'] ||
    process.env.UNRAVLER_API_URL ||
    config.apiUrl ||
    'https://api.unravler.com'
  ).replace(/\/$/, '');

  const apiKey =
    flags['api-key'] ||
    process.env.UNRAVLER_API_KEY ||
    process.env.UNRAVLER_TOKEN ||
    config.apiKey;

  if (!apiKey && !endpoint.includes('/public/ping')) {
    console.error('Authentication required. Run `unravler auth:login <key>` or set UNRAVLER_API_KEY.');
    process.exit(1);
  }

  const url = `${baseUrl}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  const headers = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
    ...(options.headers || {}),
  };

  try {
    const res = await fetch(url, {
      ...options,
      headers,
    });
    const json = await res.json().catch(() => null);
    if (!res.ok) {
      const errDetail = json?.detail || json?.message || res.statusText;
      throw new Error(`API Error (${res.status}): ${typeof errDetail === 'object' ? JSON.stringify(errDetail) : errDetail}`);
    }
    return json;
  } catch (err) {
    if (flags.json) {
      console.log(JSON.stringify({ error: err.message }, null, 2));
    } else {
      console.error(`❌ ${err.message}`);
    }
    process.exit(1);
  }
}

// ── Commands ─────────────────────────────────────────────────────────────────

async function handleAuthLogin(args, flags) {
  const key = args[0] || flags.key;
  if (!key) {
    console.error('Usage: unravler auth:login <api_key> [--api-url <url>]');
    process.exit(1);
  }
  const apiUrl = flags['api-url'] || 'https://api.unravler.com';
  const cfg = loadConfig();
  cfg.apiKey = key;
  cfg.apiUrl = apiUrl;
  saveConfig(cfg);

  if (flags.json) {
    console.log(JSON.stringify({ success: true, message: 'Authenticated successfully', apiUrl }));
  } else {
    console.log('✅ Credentials saved to ~/.unravler/config.json');
    console.log(`🌐 Base URL: ${apiUrl}`);
  }
}

async function handleAuthStatus(flags) {
  const config = loadConfig();
  const apiKey = flags['api-key'] || process.env.UNRAVLER_API_KEY || config.apiKey;
  const apiUrl = flags['api-url'] || process.env.UNRAVLER_API_URL || config.apiUrl || 'https://api.unravler.com';

  if (!apiKey) {
    if (flags.json) {
      console.log(JSON.stringify({ authenticated: false }));
    } else {
      console.log('Not logged in. Run `unravler auth:login <key>`.');
    }
    return;
  }

  const identity = await request('/api/public/me', { method: 'GET' }, flags);
  if (flags.json) {
    console.log(JSON.stringify({ authenticated: true, apiUrl, identity }, null, 2));
  } else {
    console.log('\n🔒 Unravler Authentication Status:');
    console.log(`  • Workspace: ${identity.workspace_id}`);
    console.log(`  • Role:      ${identity.workspace_role || 'member'}`);
    console.log(`  • Token:     ${identity.token_preview || 'active'}`);
    console.log(`  • Scopes:    ${(identity.scopes || []).join(', ')}`);
    console.log(`  • API Host:  ${apiUrl}\n`);
  }
}

async function handleAuthLogout(flags) {
  saveConfig({});
  if (flags.json) {
    console.log(JSON.stringify({ success: true, message: 'Logged out' }));
  } else {
    console.log('👋 Credentials cleared.');
  }
}

async function handleIntegrationsList(flags) {
  const data = await request('/api/public/accounts', { method: 'GET' }, flags);
  const accounts = Array.isArray(data) ? data : data.accounts || [];

  if (flags.json) {
    console.log(JSON.stringify(accounts, null, 2));
    return;
  }

  console.log(`\nConnected Social Accounts (${accounts.length}):`);
  if (accounts.length === 0) {
    console.log('  No accounts connected. Connect accounts in Unravler web app.');
    return;
  }
  for (const acc of accounts) {
    console.log(`  • [${acc.platform}] ${acc.platform_username || acc.account_name} (ID: ${acc.id})`);
  }
  console.log('');
}

async function handlePostsList(flags) {
  const params = new URLSearchParams();
  if (flags.status) params.set('status', flags.status);
  if (flags.limit) params.set('limit', flags.limit);
  const q = params.toString() ? `?${params.toString()}` : '';

  const data = await request(`/api/public/posts${q}`, { method: 'GET' }, flags);
  const posts = Array.isArray(data) ? data : data.posts || [];

  if (flags.json) {
    console.log(JSON.stringify(posts, null, 2));
    return;
  }

  console.log(`\nSocial Media Posts (${posts.length}):`);
  if (posts.length === 0) {
    console.log('  No posts found in this filter.');
    return;
  }
  for (const p of posts) {
    const timeStr = p.scheduled_time ? new Date(p.scheduled_time).toLocaleString() : 'immediate';
    const platforms = (p.platforms || []).join(', ');
    const preview = (p.content || '').replace(/\n/g, ' ').slice(0, 60);
    console.log(`  • [${p.status.toUpperCase()}] ID: ${p.id || p.post_id}`);
    console.log(`    Content: "${preview}..."`);
    console.log(`    Targets: ${platforms} | Time: ${timeStr}\n`);
  }
}

async function handlePostsCreate(flags) {
  let content = flags.content || flags.c;
  if (!content) {
    console.error('Error: --content or -c is required to create a post.');
    process.exit(1);
  }

  let firstComment = null;
  if (Array.isArray(content)) {
    if (content.length > 1) {
      firstComment = content.slice(1).join('\n\n');
    }
    content = content[0];
  }

  const scheduledTime = flags['scheduled-time'] || flags.s || flags.date;
  const publishNow = Boolean(flags['publish-now'] || flags.now);
  const accountIds = flags['account-ids'] || flags.i ? (flags['account-ids'] || flags.i).split(',').map((s) => s.trim()) : [];
  const platforms = flags.platforms ? flags.platforms.split(',').map((s) => s.trim()) : [];
  const mediaUrls = flags['media-urls'] || flags.m ? (flags['media-urls'] || flags.m).split(',').map((s) => s.trim()) : [];

  const body = {
    content,
    account_ids: accountIds,
    platforms,
    scheduled_time: scheduledTime || null,
    publish_now: publishNow,
    media_urls: mediaUrls,
    first_comment: firstComment,
  };

  const res = await request(
    '/api/public/posts',
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
    flags
  );

  if (flags.json) {
    console.log(JSON.stringify(res, null, 2));
  } else {
    console.log('\n✅ Post created successfully:');
    console.log(`  • ID:     ${res.id || res.post_id}`);
    console.log(`  • Status: ${res.status}`);
    if (res.scheduled_time) {
      console.log(`  • Time:   ${new Date(res.scheduled_time).toLocaleString()}`);
    }
    console.log('');
  }
}

async function handlePostsDelete(args, flags) {
  const postId = args[0] || flags.id;
  if (!postId) {
    console.error('Usage: unravler posts:delete <post_id>');
    process.exit(1);
  }
  const res = await request(`/api/public/posts/${postId}`, { method: 'DELETE' }, flags);
  if (flags.json) {
    console.log(JSON.stringify(res, null, 2));
  } else {
    console.log(`🗑️ Post ${postId} deleted successfully.`);
  }
}

async function handlePostsStatus(args, flags) {
  const postId = args[0] || flags.id;
  const statusArg = (flags.status || flags.s || '').toLowerCase();
  if (!postId || !['draft', 'schedule', 'scheduled'].includes(statusArg)) {
    console.error('Usage: unravler posts:status <post_id> --status draft|schedule');
    process.exit(1);
  }
  const targetStatus = statusArg === 'draft' ? 'draft' : 'scheduled';
  const res = await request(
    `/api/public/posts/${postId}`,
    {
      method: 'PATCH',
      body: JSON.stringify({ status: targetStatus }),
    },
    flags
  );

  if (flags.json) {
    console.log(JSON.stringify(res, null, 2));
  } else {
    console.log(`✅ Post ${postId} status changed to [${targetStatus.toUpperCase()}].`);
  }
}

async function handleUpload(args, flags) {
  const targetFile = args[0] || flags.file || flags.f;
  if (!targetFile) {
    console.error('Usage: unravler upload <file_path>');
    process.exit(1);
  }
  const filePath = path.resolve(process.cwd(), targetFile);
  if (!fs.existsSync(filePath)) {
    console.error(`❌ File not found: ${filePath}`);
    process.exit(1);
  }

  const fileBuffer = fs.readFileSync(filePath);
  const fileName = path.basename(filePath);
  const blob = new Blob([fileBuffer]);
  const formData = new FormData();
  formData.append('file', blob, fileName);

  const res = await request(
    '/api/public/media/upload',
    {
      method: 'POST',
      body: formData,
    },
    flags
  );

  if (flags.json) {
    console.log(JSON.stringify(res, null, 2));
  } else {
    console.log('\n✅ Media uploaded successfully:');
    console.log(`  • ID:   ${res.id}`);
    console.log(`  • URL:  ${res.url || res.path}\n`);
  }
}

async function handleAnalyticsPlatform(args, flags) {
  const accountId = args[0] || flags.id || flags['account-id'];
  if (!accountId) {
    console.error('Usage: unravler analytics:platform <account_id> [--days 7]');
    process.exit(1);
  }
  const days = flags.days || flags.d || 7;
  const res = await request(`/api/public/analytics/platform/${accountId}?days=${days}`, { method: 'GET' }, flags);

  if (flags.json) {
    console.log(JSON.stringify(res, null, 2));
    return;
  }

  console.log(`\nPlatform Analytics for Account ${accountId} (Last ${days} days):`);
  for (const m of (Array.isArray(res) ? res : [])) {
    const latest = m.data && m.data.length ? m.data[m.data.length - 1].total : 0;
    const change = m.percentageChange || 0;
    console.log(`  • ${m.label}: ${latest} (Change: ${change > 0 ? '+' : ''}${change}%)`);
  }
  console.log('');
}

async function handleAnalyticsPost(args, flags) {
  const postId = args[0] || flags.id || flags['post-id'];
  if (!postId) {
    console.error('Usage: unravler analytics:post <post_id> [--days 7]');
    process.exit(1);
  }
  const days = flags.days || flags.d || 7;
  const res = await request(`/api/public/analytics/post/${postId}?days=${days}`, { method: 'GET' }, flags);

  if (flags.json) {
    console.log(JSON.stringify(res, null, 2));
    return;
  }

  console.log(`\nPost Analytics for Post ${postId} (Last ${days} days):`);
  for (const m of (Array.isArray(res) ? res : [])) {
    const latest = m.data && m.data.length ? m.data[m.data.length - 1].total : 0;
    const change = m.percentageChange || 0;
    console.log(`  • ${m.label}: ${latest} (Change: ${change > 0 ? '+' : ''}${change}%)`);
  }
  console.log('');
}

function showHelp() {
  console.log(`
Unravler CLI - Official Social Media Automation Tool

USAGE:
  unravler <command> [options]

COMMANDS:
  auth:login <api_key>          Authenticate using a Personal Token or Workspace Key
  auth:status                   Inspect active token, permissions, and workspace
  auth:logout                   Clear stored credentials
  upload <file_path>            Upload a local image/video to storage (alias: media:upload)
  integrations:list             List all connected social accounts
  posts:list                    List scheduled, draft, and published posts
  posts:create                  Create a post draft or scheduled publish job
  posts:status <id> --status <s> Change post status (draft | schedule)
  posts:delete <post_id>        Remove a scheduled post or draft
  analytics:platform <acc_id>   View platform growth & impressions metrics
  analytics:post <post_id>      View published post likes, comments, and shares

OPTIONS:
  --content, -c <text>          Post text content (use multiple for threads)
  --scheduled-time, -s <t>      ISO 8601 schedule timestamp (e.g. 2026-10-15T14:30:00Z)
  --publish-now, --now          Publish immediately instead of queuing
  --account-ids, -i <id1,id2>   Comma-separated target social account IDs
  --platforms <p1,p2>           Comma-separated platform names (e.g. twitter,linkedin)
  --media-urls, -m <u1,u2>      Comma-separated media URLs
  --status <s>                  Filter in posts:list or target in posts:status
  --days, -d <n>                Days to look back for analytics (default: 7)
  --json                        Output pure JSON for AI agents, scripts, and piping
  --api-url <url>               Override backend endpoint URL
  --api-key <key>               Override API key without reading ~/.unravler/config.json
  --help, -h                    Show this manual
`);
}

// ── Entrypoint ───────────────────────────────────────────────────────────────

async function main() {
  const rawArgs = process.argv.slice(2);
  const { flags, positional } = parseArgs(rawArgs);

  if (flags.help || flags.h || positional.length === 0) {
    showHelp();
    return;
  }

  const command = positional[0];
  const commandArgs = positional.slice(1);

  switch (command) {
    case 'auth:login':
      await handleAuthLogin(commandArgs, flags);
      break;
    case 'auth:status':
      await handleAuthStatus(flags);
      break;
    case 'auth:logout':
      await handleAuthLogout(flags);
      break;
    case 'upload':
    case 'media:upload':
      await handleUpload(commandArgs, flags);
      break;
    case 'integrations:list':
      await handleIntegrationsList(flags);
      break;
    case 'posts:list':
      await handlePostsList(flags);
      break;
    case 'posts:create':
      await handlePostsCreate(flags);
      break;
    case 'posts:status':
      await handlePostsStatus(commandArgs, flags);
      break;
    case 'posts:delete':
      await handlePostsDelete(commandArgs, flags);
      break;
    case 'analytics:platform':
      await handleAnalyticsPlatform(commandArgs, flags);
      break;
    case 'analytics:post':
      await handleAnalyticsPost(commandArgs, flags);
      break;
    default:
      console.error(`Unknown command: ${command}`);
      showHelp();
      process.exit(1);
  }
}

main().catch((err) => {
  console.error('Fatal CLI Error:', err);
  process.exit(1);
});

