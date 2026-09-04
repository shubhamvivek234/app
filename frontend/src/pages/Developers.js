import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import {
  FaBolt,
  FaBook,
  FaCloud,
  FaCode,
  FaCopy,
  FaGlobe,
  FaHistory,
  FaKey,
  FaLaptopCode,
  FaPlug,
  FaPlus,
  FaServer,
  FaShieldAlt,
  FaSpinner,
  FaTrash,
  FaRobot,
  FaTerminal,
} from 'react-icons/fa';

import DashboardLayout from '@/components/DashboardLayout';
import UnravlerLogo from '@/components/UnravlerLogo';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/context/AuthContext';
import {
  createApiKey,
  createPersonalToken,
  createWebhookEndpoint,
  deleteApiKey,
  deletePersonalToken,
  deleteWebhookEndpoint,
  getApiKeys,
  getDeveloperScopes,
  getPersonalTokens,
  getWebhookDeliveries,
  getWebhookEndpoints,
  testWebhookEndpoint,
} from '@/lib/api';
import { hasWorkspacePermission } from '@/lib/workspacePermissions';

const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || 'https://api.unravler.com').replace(/\/$/, '');
const PUBLIC_API_BASE = `${BACKEND_URL}/api/public`;
const MCP_HTTP_ENDPOINT = `${BACKEND_URL}/mcp`;

const SUPPORTED_WEBHOOK_EVENTS = [
  { key: 'post.published', label: 'post.published', desc: 'Fires when a post successfully goes live on connected channels' },
  { key: 'post.failed', label: 'post.failed', desc: 'Fires when publishing fails with platform error details' },
  { key: 'post.partial_failed', label: 'post.partial_failed', desc: 'Fires when some platform targets publish but others fail' },
  { key: 'post.scheduled', label: 'post.scheduled', desc: 'Fires when a new draft is scheduled into the queue' },
  { key: 'post.cancelled', label: 'post.cancelled', desc: 'Fires when a scheduled post is removed or cancelled' },
  { key: 'account.disconnected', label: 'account.disconnected', desc: 'Fires when an OAuth token expires or permissions are lost' },
  { key: 'post.approval_requested', label: 'post.approval_requested', desc: 'Fires when a draft is submitted for team approval' },
];

const REST_GROUPS = [
  {
    title: 'Identity',
    items: [
      { method: 'GET', path: '/me', scope: 'any valid token', description: 'Inspect the active workspace, actor, token type, and granted scopes.' },
    ],
  },
  {
    title: 'Posts',
    items: [
      { method: 'GET', path: '/posts', scope: 'posts:read', description: 'List posts with status, page, and limit filters.' },
      { method: 'GET', path: '/posts/{post_id}', scope: 'posts:read', description: 'Fetch a single post including media and per-platform results.' },
      { method: 'POST', path: '/posts', scope: 'posts:write', description: 'Create a draft, scheduled post, or immediate publish job.' },
      { method: 'PATCH', path: '/posts/{post_id}', scope: 'posts:write', description: 'Update draft or scheduled posts through the main app pipeline.' },
      { method: 'DELETE', path: '/posts/{post_id}', scope: 'posts:delete', description: 'Delete a post with safe queued-work and media cleanup semantics.' },
      { method: 'POST', path: '/posts/{post_id}/retry', scope: 'posts:write', description: 'Retry failed or partial publishes.' },
    ],
  },
  {
    title: 'Timeslots & Auto-Queue',
    items: [
      { method: 'GET', path: '/timeslots', scope: 'accounts:read', description: 'List recurring weekly timeslot schedules by account and category.' },
      { method: 'GET', path: '/timeslots/next-slot', scope: 'accounts:read', description: 'Find the next available auto-scheduling timeslot in your timezone.' },
    ],
  },
  {
    title: 'Approvals',
    items: [
      { method: 'GET', path: '/approvals', scope: 'approval:read', description: 'Read awaiting, expired, and changes-requested review buckets.' },
      { method: 'POST', path: '/posts/{post_id}/submit-review', scope: 'posts:write', description: 'Submit a future-scheduled draft for approval.' },
      { method: 'POST', path: '/posts/{post_id}/approve', scope: 'approval:write', description: 'Approve a pending item back into scheduled status.' },
      { method: 'POST', path: '/posts/{post_id}/reject', scope: 'approval:write', description: 'Reject a pending item back to draft with a reason.' },
      { method: 'POST', path: '/posts/{post_id}/return-to-draft', scope: 'approval:write', description: 'Recover expired approval items into draft status.' },
      { method: 'POST', path: '/posts/{post_id}/resubmit', scope: 'posts:write', description: 'Resubmit a creator-owned draft after changes and rescheduling.' },
    ],
  },
  {
    title: 'Webhooks & Automation Suite',
    items: [
      { method: 'POST', path: '/api/v1/webhooks/inbound/post', scope: 'posts:write', description: 'Inbound automation webhook for n8n, Make.com, and Zapier to create or schedule posts.' },
      { method: 'GET', path: '/api/v1/webhooks/endpoints', scope: 'webhooks:manage', description: 'List registered outbound HTTPS webhooks.' },
      { method: 'POST', path: '/api/v1/webhooks/endpoints', scope: 'webhooks:manage', description: 'Register an HTTPS endpoint with HMAC SHA-256 signature verification.' },
      { method: 'DELETE', path: '/api/v1/webhooks/endpoints/{id}', scope: 'webhooks:manage', description: 'Revoke and delete a registered outbound webhook.' },
      { method: 'POST', path: '/api/v1/webhooks/endpoints/{id}/test', scope: 'webhooks:manage', description: 'Send a test event payload to verify delivery to your server.' },
    ],
  },
  {
    title: 'Workspace & AI',
    items: [
      { method: 'GET', path: '/accounts', scope: 'accounts:read', description: 'List connected social accounts available to the active workspace.' },
      { method: 'GET', path: '/stats', scope: 'stats:read', description: 'Fetch high-level operational stats used by dashboards and automations.' },
      { method: 'POST', path: '/ai/generate', scope: 'ai:generate', description: 'Generate copy variants with platform-aware prompts.' },
    ],
  },
];

const METHOD_STYLES = {
  GET: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-800',
  POST: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800',
  PATCH: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800',
  DELETE: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/60 dark:text-rose-300 dark:border-rose-800',
};

function CopyButton({ text, label = 'Copy' }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:border-gray-300 hover:bg-gray-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
    >
      <FaCopy className="text-[10px]" />
      {copied ? 'Copied' : label}
    </button>
  );
}

function CodeBlock({ label, children }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-gray-200 bg-slate-950 dark:border-slate-800">
      <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900 px-4 py-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</span>
        <CopyButton text={children} />
      </div>
      <pre className="overflow-x-auto px-4 py-4 text-xs leading-6 text-slate-200">{children}</pre>
    </div>
  );
}

function ScopePicker({ scopes, selectedScopes, onToggle, title }) {
  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-medium text-gray-900 dark:text-slate-100">{title}</p>
        <p className="text-xs text-gray-500 dark:text-slate-400">Choose the exact capabilities this credential should be allowed to use.</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {scopes.map((scope) => {
          const checked = selectedScopes.includes(scope);
          return (
            <label
              key={scope}
              className={`flex cursor-pointer items-center justify-between rounded-2xl border px-3 py-2 text-sm transition ${
                checked
                  ? 'border-green-300 bg-green-50 text-green-900 dark:border-green-800 dark:bg-green-950/60 dark:text-green-200'
                  : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-slate-600'
              }`}
            >
              <span className="font-mono text-xs">{scope}</span>
              <input
                type="checkbox"
                className="sr-only"
                checked={checked}
                onChange={() => onToggle(scope)}
              />
              <span className={`h-4 w-4 rounded-full border flex items-center justify-center text-[10px] ${
                checked ? 'border-green-600 bg-green-600 text-white' : 'border-gray-300 dark:border-slate-600'
              }`}>
                {checked ? '✓' : ''}
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

function CredentialList({ items, onDelete, emptyLabel }) {
  if (items.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-gray-200 bg-white px-4 py-8 text-center text-sm text-gray-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
        {emptyLabel}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div
          key={item.id}
          className="flex flex-col gap-4 rounded-2xl border border-gray-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 lg:flex-row lg:items-center lg:justify-between"
        >
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-gray-900 dark:text-slate-100">{item.name}</span>
              <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-600 dark:bg-slate-800 dark:text-slate-300">
                {item.masked_key || 'Personal token'}
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {(item.scopes || []).map((scope) => (
                <span
                  key={scope}
                  className="rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 font-mono text-[11px] text-gray-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
                >
                  {scope}
                </span>
              ))}
            </div>
            <div className="flex flex-wrap gap-4 text-xs text-gray-500 dark:text-slate-400">
              <span>Created {new Date(item.created_at).toLocaleString()}</span>
              <span>
                {item.last_used_at
                  ? `Last used ${new Date(item.last_used_at).toLocaleString()}`
                  : 'Not used yet'}
              </span>
            </div>
          </div>
          <Button
            type="button"
            variant="outline"
            className="border-rose-200 text-rose-600 hover:bg-rose-50 hover:text-rose-700 dark:border-rose-900/60 dark:text-rose-400 dark:hover:bg-rose-950/60"
            onClick={() => onDelete(item.id)}
          >
            <FaTrash className="mr-2 text-xs" />
            Revoke
          </Button>
        </div>
      ))}
    </div>
  );
}

function CredentialSection({
  title,
  icon: Icon,
  copy,
  createLabel,
  name,
  setName,
  scopes,
  setScopes,
  allowedScopes,
  items,
  onCreate,
  onDelete,
  busy,
  generatedToken,
}) {
  return (
    <section className="space-y-5 rounded-[28px] border border-gray-200 bg-offwhite px-5 py-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/80 lg:px-7">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-gray-600 shadow-sm dark:bg-slate-800 dark:text-slate-300">
            <Icon className="text-[11px]" />
            {title}
          </div>
          <p className="max-w-2xl text-sm text-gray-600 dark:text-slate-400">{copy}</p>
        </div>
      </div>

      {generatedToken ? (
        <div className="rounded-2xl border border-green-200 bg-green-50 p-4 dark:border-green-900/60 dark:bg-green-950/40">
          <p className="text-sm font-semibold text-green-900 dark:text-green-200">Copy this token now</p>
          <p className="mt-1 text-xs text-green-700 dark:text-green-300">
            Raw tokens are only shown once. Save it in your client config or secret manager immediately.
          </p>
          <div className="mt-3 flex flex-col gap-3 rounded-2xl border border-green-200 bg-white p-3 dark:border-green-800 dark:bg-slate-900 lg:flex-row lg:items-center lg:justify-between">
            <code className="break-all text-xs text-slate-800 dark:text-slate-100">{generatedToken}</code>
            <CopyButton text={generatedToken} label="Copy token" />
          </div>
        </div>
      ) : null}

      <form
        className="space-y-4 rounded-2xl border border-gray-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
        onSubmit={(event) => {
          event.preventDefault();
          onCreate();
        }}
      >
        <div className="space-y-2">
          <label className="text-sm font-medium text-gray-900 dark:text-slate-100" htmlFor={`${title}-name`}>
            Credential name
          </label>
          <Input
            id={`${title}-name`}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={title === 'Personal Tokens' ? 'Claude personal token' : 'Zapier workspace key'}
            className="dark:border-slate-700 dark:bg-slate-800 dark:text-white"
          />
        </div>
        <ScopePicker
          title="Scopes"
          scopes={allowedScopes}
          selectedScopes={scopes}
          onToggle={(scope) => (
            setScopes((current) => (
              current.includes(scope)
                ? current.filter((value) => value !== scope)
                : [...current, scope]
            ))
          )}
        />
        <div className="flex flex-wrap gap-3">
          <Button type="submit" disabled={busy || !name.trim() || scopes.length === 0}>
            <FaKey className="mr-2 text-xs" />
            {busy ? 'Creating...' : createLabel}
          </Button>
        </div>
      </form>

      <CredentialList items={items} onDelete={onDelete} emptyLabel={`No ${title.toLowerCase()} yet.`} />
    </section>
  );
}

function WebhookSection({
  endpoints,
  onRegister,
  onDelete,
  onTest,
  onViewDeliveries,
  testingEndpointId,
  busyRegister,
  generatedSecret,
  setGeneratedSecret,
}) {
  const [url, setUrl] = useState('');
  const [description, setDescription] = useState('');
  const [selectedEvents, setSelectedEvents] = useState(['post.published', 'post.failed']);

  const handleToggleEvent = (evtKey) => {
    setSelectedEvents((prev) =>
      prev.includes(evtKey) ? prev.filter((e) => e !== evtKey) : [...prev, evtKey]
    );
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!url.startsWith('https://')) {
      toast.error('Webhook URL must use HTTPS');
      return;
    }
    if (selectedEvents.length === 0) {
      toast.error('Select at least one event');
      return;
    }
    onRegister({ url, events: selectedEvents, description }, () => {
      setUrl('');
      setDescription('');
      setSelectedEvents(['post.published', 'post.failed']);
    });
  };

  const isSlackUrl = url.includes('hooks.slack.com');
  const isDiscordUrl = url.includes('discord.com/api/webhooks');

  return (
    <section className="space-y-6 rounded-[28px] border border-gray-200 bg-offwhite px-5 py-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/80 lg:px-7">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-indigo-600 shadow-sm dark:bg-slate-800 dark:text-indigo-400">
            <FaPlug className="text-[11px]" />
            Outbound Webhooks & Integrations
          </div>
          <p className="max-w-3xl text-sm text-gray-600 dark:text-slate-400">
            Receive real-time signed HMAC HTTP POST requests when posts publish, fail, or need approval. Slack and Discord URLs are automatically detected and delivered as rich interactive message cards.
          </p>
        </div>
      </div>

      {generatedSecret && (
        <div className="rounded-2xl border border-indigo-200 bg-indigo-50/80 p-4 dark:border-indigo-900/60 dark:bg-indigo-950/50">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-indigo-950 dark:text-indigo-200 flex items-center gap-2">
              <FaShieldAlt className="text-indigo-600" />
              Save your Webhook Signing Secret
            </p>
            <button
              type="button"
              onClick={() => setGeneratedSecret('')}
              className="text-xs text-indigo-700 hover:text-indigo-900 dark:text-indigo-300"
            >
              Dismiss
            </button>
          </div>
          <p className="mt-1 text-xs text-indigo-800 dark:text-indigo-300/90">
            Verify <code className="font-mono text-indigo-900 dark:text-indigo-200">X-Unravler-Signature</code> headers on incoming payloads with this secret. This secret is shown only once.
          </p>
          <div className="mt-3 flex flex-col gap-3 rounded-xl border border-indigo-200 bg-white p-3 dark:border-indigo-800 dark:bg-slate-900 lg:flex-row lg:items-center lg:justify-between">
            <code className="break-all font-mono text-xs font-bold text-slate-900 dark:text-white">{generatedSecret}</code>
            <CopyButton text={generatedSecret} label="Copy secret" />
          </div>
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className="space-y-4 rounded-2xl border border-gray-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex flex-wrap items-center gap-2 pb-2 border-b border-gray-100 dark:border-slate-800">
          <span className="text-[11px] font-semibold text-gray-500 dark:text-slate-400">Quick Presets:</span>
          <button
            type="button"
            onClick={() => {
              setDescription('Slack Channel Alerts');
              setSelectedEvents(['post.published', 'post.failed', 'post.partial_failed']);
              toast.info('Slack preset selected! Paste your incoming webhook URL below.');
            }}
            className="rounded-lg border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 dark:border-indigo-800 dark:bg-indigo-950 dark:text-indigo-300 transition-colors"
          >
            🚀 Slack Channel Alerts
          </button>
          <button
            type="button"
            onClick={() => {
              setDescription('Discord Social Feed');
              setSelectedEvents(['post.published', 'post.failed']);
              toast.info('Discord preset selected! Paste your discord webhook URL below.');
            }}
            className="rounded-lg border border-purple-200 bg-purple-50 px-2.5 py-1 text-xs font-semibold text-purple-700 hover:bg-purple-100 dark:border-purple-800 dark:bg-purple-950 dark:text-purple-300 transition-colors"
          >
            🎮 Discord Channel Alerts
          </button>
          <button
            type="button"
            onClick={() => {
              setDescription('Zapier Automation Trigger');
              setSelectedEvents(SUPPORTED_WEBHOOK_EVENTS.map((e) => e.key));
              toast.info('Zapier/Make preset selected! Subscribed to all events.');
            }}
            className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700 hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300 transition-colors"
          >
            ⚡ Zapier / Make / n8n
          </button>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300">
              Target HTTPS Endpoint URL
            </label>
            <Input
              type="url"
              required
              placeholder="https://api.yourdomain.com/webhooks or https://hooks.slack.com/services/..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            />
            {isSlackUrl && (
              <p className="text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                ✨ Slack webhook detected: Payloads will be formatted as rich Slack Blocks with headers and buttons.
              </p>
            )}
            {isDiscordUrl && (
              <p className="text-[11px] font-medium text-indigo-600 dark:text-indigo-400">
                ✨ Discord webhook detected: Payloads will be formatted as color-coded Discord Embeds.
              </p>
            )}
          </div>

          <div className="space-y-1.5 sm:col-span-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300">
              Description / Label (Optional)
            </label>
            <Input
              placeholder="e.g. Slack #social-alerts channel, Production CRM Sync"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            />
          </div>
        </div>

        <div className="space-y-2 pt-1">
          <label className="text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300">
            Subscribed Events
          </label>
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
            {SUPPORTED_WEBHOOK_EVENTS.map((evt) => {
              const checked = selectedEvents.includes(evt.key);
              return (
                <div
                  key={evt.key}
                  onClick={() => handleToggleEvent(evt.key)}
                  className={`cursor-pointer rounded-xl border p-3 transition-all ${
                    checked
                      ? 'border-indigo-500 bg-indigo-50/70 text-indigo-950 dark:border-indigo-500 dark:bg-indigo-950/40 dark:text-indigo-200'
                      : 'border-slate-200 bg-slate-50/60 text-slate-700 hover:border-slate-300 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-bold">{evt.label}</span>
                    <span className={`h-4 w-4 rounded-full border flex items-center justify-center text-[10px] ${
                      checked ? 'border-indigo-600 bg-indigo-600 text-white' : 'border-slate-300 dark:border-slate-600'
                    }`}>
                      {checked ? '✓' : ''}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] leading-tight text-slate-500 dark:text-slate-400">{evt.desc}</p>
                </div>
              );
            })}
          </div>
        </div>

        <div className="pt-2">
          <Button type="submit" disabled={busyRegister || !url.trim() || selectedEvents.length === 0} className="bg-indigo-600 text-white hover:bg-indigo-700 font-bold">
            {busyRegister ? <FaSpinner className="animate-spin mr-2" /> : <FaPlus className="mr-2 text-xs" />}
            Register Webhook Endpoint
          </Button>
        </div>
      </form>

      {endpoints.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-gray-200 bg-white p-8 text-center text-sm text-gray-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
          No webhook endpoints registered yet. Add your first HTTPS URL above to start streaming real-time events.
        </div>
      ) : (
        <div className="space-y-3">
          {endpoints.map((ep) => (
            <div
              key={ep.id}
              className="flex flex-col gap-4 rounded-2xl border border-gray-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 lg:flex-row lg:items-center lg:justify-between"
            >
              <div className="space-y-2 min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs font-bold text-slate-900 dark:text-slate-100 truncate max-w-md">
                    {ep.url}
                  </span>
                  {ep.description ? (
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                      {ep.description}
                    </span>
                  ) : null}
                  {ep.last_delivery_status ? (
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                      ep.last_delivery_status < 400
                        ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
                        : 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300'
                    }`}>
                      {ep.last_delivery_status < 400 ? `HTTP ${ep.last_delivery_status} OK` : `HTTP ${ep.last_delivery_status} Err`}
                    </span>
                  ) : null}
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {(ep.events || []).map((evt) => (
                    <span
                      key={evt}
                      className="rounded-full border border-indigo-100 bg-indigo-50 px-2 py-0.5 font-mono text-[10px] font-medium text-indigo-700 dark:border-indigo-900/60 dark:bg-indigo-950/60 dark:text-indigo-300"
                    >
                      {evt}
                    </span>
                  ))}
                </div>

                <div className="flex flex-wrap gap-4 text-xs text-gray-500 dark:text-slate-400">
                  <span>Registered {new Date(ep.created_at).toLocaleDateString()}</span>
                  {ep.last_delivery_at && (
                    <span>Last fired {new Date(ep.last_delivery_at).toLocaleTimeString()}</span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={testingEndpointId === ep.id}
                  onClick={() => onTest(ep.id)}
                  className="border-slate-300 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  {testingEndpointId === ep.id ? (
                    <FaSpinner className="animate-spin text-xs" />
                  ) : (
                    <>
                      <FaBolt className="mr-1.5 text-xs text-amber-500" />
                      Test Ping
                    </>
                  )}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => onViewDeliveries(ep)}
                  className="border-slate-300 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  <FaHistory className="mr-1.5 text-xs text-slate-400" />
                  Logs
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => onDelete(ep.id)}
                  className="border-rose-200 text-rose-600 hover:bg-rose-50 hover:text-rose-700 dark:border-rose-900/60 dark:text-rose-400 dark:hover:bg-rose-950/60"
                >
                  <FaTrash className="text-xs" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function DeliveriesModal({ endpoint, deliveries, open, onClose, loading }) {
  if (!open) return null;

  return (
    <Dialog open={open} onOpenChange={(val) => !val && onClose()}>
      <DialogContent className="max-w-2xl rounded-3xl border-slate-200 dark:border-slate-800 dark:bg-slate-900">
        <DialogHeader className="text-left">
          <DialogTitle className="flex items-center gap-2 text-slate-900 dark:text-white text-lg">
            <FaHistory className="text-sky-500" />
            Webhook Delivery History
          </DialogTitle>
          <DialogDescription className="dark:text-slate-400 truncate">
            Target: <code className="font-mono text-xs">{endpoint?.url}</code>
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="p-8 text-center text-sm text-slate-500 dark:text-slate-400">
            <FaSpinner className="animate-spin inline mr-2" /> Loading delivery logs...
          </div>
        ) : deliveries.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500 dark:text-slate-400">
            No delivery events recorded yet for this endpoint.
          </div>
        ) : (
          <div className="max-h-80 overflow-y-auto space-y-2 pr-1">
            {deliveries.map((deliv) => (
              <div
                key={deliv.id}
                className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50/70 p-3 text-xs dark:border-slate-800 dark:bg-slate-800/60"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-slate-900 dark:text-slate-100">{deliv.event}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                      deliv.success
                        ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
                        : 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300'
                    }`}>
                      {deliv.status_code ? `HTTP ${deliv.status_code}` : 'Failed'}
                    </span>
                  </div>
                  <p className="text-slate-500 dark:text-slate-400">
                    {new Date(deliv.timestamp).toLocaleString()}
                    {deliv.error && <span className="text-rose-500 ml-2">({deliv.error})</span>}
                  </p>
                </div>
                <span className="font-mono font-semibold text-slate-600 dark:text-slate-300">
                  {deliv.latency_ms}ms
                </span>
              </div>
            ))}
          </div>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AiAgentMcpHub({ personalTokens = [], generatedToken = '', backendUrl = '', mcpEndpoint = '' }) {
  const [activeClient, setActiveClient] = useState('cursor');
  const [transport, setTransport] = useState('remote');

  const effectiveToken =
    generatedToken ||
    (personalTokens?.[0]?.token_preview
      ? `unrv_${personalTokens[0].token_preview.replace(/\*/g, 'x')}`
      : 'YOUR_PERSONAL_TOKEN');

  const CLIENT_CONFIGS = {
    cursor: {
      label: 'Cursor IDE',
      filename: '.cursor/mcp.json',
      hint: 'Place in your project root at .cursor/mcp.json or configure in Cursor Settings > Features > MCP.',
      remoteSnippet: `{
  "mcpServers": {
    "unravler": {
      "url": "${mcpEndpoint}",
      "headers": {
        "Authorization": "Bearer ${effectiveToken}"
      }
    }
  }
}`,
      stdioSnippet: `{
  "mcpServers": {
    "unravler": {
      "command": "node",
      "args": ["/absolute/path/to/unravler/app/mcp-server/index.js"],
      "env": {
        "UNRAVLER_TOKEN": "${effectiveToken}",
        "UNRAVLER_BASE_URL": "${backendUrl}"
      }
    }
  }
}`,
    },
    claude: {
      label: 'Claude Desktop',
      filename: 'claude_desktop_config.json',
      hint: 'Add to ~/Library/Application Support/Claude/claude_desktop_config.json (macOS) or %APPDATA%/Claude (Windows).',
      remoteSnippet: `{
  "mcpServers": {
    "unravler": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "${mcpEndpoint}", "--header", "Authorization: Bearer ${effectiveToken}"]
    }
  }
}`,
      stdioSnippet: `{
  "mcpServers": {
    "unravler": {
      "command": "node",
      "args": ["/absolute/path/to/unravler/app/mcp-server/index.js"],
      "env": {
        "UNRAVLER_TOKEN": "${effectiveToken}",
        "UNRAVLER_BASE_URL": "${backendUrl}"
      }
    }
  }
}`,
    },
    windsurf: {
      label: 'Windsurf (Codeium)',
      filename: '~/.codeium/windsurf/mcp_config.json',
      hint: 'Configure in Cascade Settings > MCP or add to ~/.codeium/windsurf/mcp_config.json.',
      remoteSnippet: `{
  "mcpServers": {
    "unravler": {
      "serverUrl": "${mcpEndpoint}",
      "headers": {
        "Authorization": "Bearer ${effectiveToken}"
      }
    }
  }
}`,
      stdioSnippet: `{
  "mcpServers": {
    "unravler": {
      "command": "node",
      "args": ["/absolute/path/to/unravler/app/mcp-server/index.js"],
      "env": {
        "UNRAVLER_TOKEN": "${effectiveToken}",
        "UNRAVLER_BASE_URL": "${backendUrl}"
      }
    }
  }
}`,
    },
    http: {
      label: 'cURL / Direct HTTP',
      filename: 'Terminal Probe',
      hint: 'Probe the hosted JSON-RPC 2.0 endpoint directly over HTTPS.',
      remoteSnippet: `curl -X POST "${mcpEndpoint}" \\
  -H "Authorization: Bearer ${effectiveToken}" \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'`,
      stdioSnippet: `curl -X POST "${mcpEndpoint}" \\
  -H "Authorization: Bearer ${effectiveToken}" \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'`,
    },
  };

  const activeConf = CLIENT_CONFIGS[activeClient] || CLIENT_CONFIGS.cursor;
  const currentSnippet = transport === 'remote' ? activeConf.remoteSnippet : activeConf.stdioSnippet;

  return (
    <section className="space-y-6 rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 lg:p-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
            <FaRobot className="text-[11px]" />
            Unravler MCP Server for AI Agents
          </div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            Supercharge Claude Desktop, Cursor, and Windsurf
          </h2>
          <p className="max-w-3xl text-sm leading-relaxed text-gray-600 dark:text-slate-400">
            Enable autonomous AI agents to list accounts, schedule and publish posts, retry failed platforms, inspect campaigns, query master calendar schedules, and generate copy using standard Model Context Protocol tools.
          </p>
        </div>

        <div className="flex items-center gap-1 rounded-xl border border-gray-200 bg-offwhite p-1 dark:border-slate-800 dark:bg-slate-800/80 self-start">
          <button
            type="button"
            onClick={() => setTransport('remote')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              transport === 'remote'
                ? 'bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-xs'
                : 'text-gray-500 hover:text-gray-900 dark:text-slate-400 dark:hover:text-white'
            }`}
          >
            🌐 Hosted Remote (HTTPS)
          </button>
          <button
            type="button"
            onClick={() => setTransport('stdio')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              transport === 'stdio'
                ? 'bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-xs'
                : 'text-gray-500 hover:text-gray-900 dark:text-slate-400 dark:hover:text-white'
            }`}
          >
            💻 Local Stdio
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-gray-100 dark:border-slate-800 pb-3">
        {Object.entries(CLIENT_CONFIGS).map(([key, conf]) => (
          <button
            key={key}
            type="button"
            onClick={() => setActiveClient(key)}
            className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all flex items-center gap-1.5 ${
              activeClient === key
                ? 'bg-indigo-600 text-white shadow-xs'
                : 'bg-offwhite text-gray-600 hover:bg-gray-100 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
            }`}
          >
            {key === 'cursor' && '⚡'}
            {key === 'claude' && '🧠'}
            {key === 'windsurf' && '🏄'}
            {key === 'http' && '🔌'}
            {conf.label}
          </button>
        ))}
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-50 dark:bg-slate-800/50 p-3.5 rounded-2xl border border-slate-100 dark:border-slate-800 text-xs">
        <div className="flex items-center gap-2 text-slate-700 dark:text-slate-300">
          <FaTerminal className="text-indigo-500 shrink-0" />
          <span>Config path: <strong className="font-mono text-slate-900 dark:text-white">{activeConf.filename}</strong></span>
        </div>
        <div className="text-[11px] text-slate-500 dark:text-slate-400">
          {activeConf.hint}
        </div>
      </div>

      <div className="relative">
        <CodeBlock label={`${activeConf.label} Configuration (${transport === 'remote' ? 'Hosted' : 'Local'})`}>
          {currentSnippet}
        </CodeBlock>
      </div>

      <div className="space-y-3 pt-2">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-slate-400">
            19 Exposed Model Context Protocol Tools
          </h3>
          <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold">
            Ready for Claude 3.7 / Claude 3.5 Sonnet / Cursor Agent / Windsurf Cascade
          </span>
        </div>

        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4 text-xs">
          <div className="p-3 rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-850 space-y-1.5">
            <p className="font-bold text-slate-800 dark:text-slate-200">Posts & Publishing</p>
            <div className="flex flex-wrap gap-1">
              {['posts.create', 'posts.update', 'posts.list', 'posts.get', 'posts.delete', 'posts.retry'].map((t) => (
                <span key={t} className="px-1.5 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 font-mono text-[10px] text-slate-700 dark:text-slate-300">
                  {t}
                </span>
              ))}
            </div>
          </div>

          <div className="p-3 rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-850 space-y-1.5">
            <p className="font-bold text-slate-800 dark:text-slate-200">Campaigns & Calendar</p>
            <div className="flex flex-wrap gap-1">
              {['campaigns.list', 'campaigns.get', 'calendar.get'].map((t) => (
                <span key={t} className="px-1.5 py-0.5 rounded-md bg-indigo-50 dark:bg-indigo-950/60 font-mono text-[10px] text-indigo-700 dark:text-indigo-300">
                  {t}
                </span>
              ))}
            </div>
          </div>

          <div className="p-3 rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-850 space-y-1.5">
            <p className="font-bold text-slate-800 dark:text-slate-200">Team Governance</p>
            <div className="flex flex-wrap gap-1">
              {['approvals.list', 'approvals.submit', 'approvals.approve', 'approvals.reject', 'approvals.return_to_draft'].map((t) => (
                <span key={t} className="px-1.5 py-0.5 rounded-md bg-amber-50 dark:bg-amber-950/60 font-mono text-[10px] text-amber-700 dark:text-amber-300">
                  {t}
                </span>
              ))}
            </div>
          </div>

          <div className="p-3 rounded-xl border border-slate-200/80 bg-white dark:border-slate-800 dark:bg-slate-850 space-y-1.5">
            <p className="font-bold text-slate-800 dark:text-slate-200">Intelligence & Stats</p>
            <div className="flex flex-wrap gap-1">
              {['accounts.list', 'stats.get', 'ai.generate', 'analytics.summary'].map((t) => (
                <span key={t} className="px-1.5 py-0.5 rounded-md bg-emerald-50 dark:bg-emerald-950/60 font-mono text-[10px] text-emerald-700 dark:text-emerald-300">
                  {t}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function DevelopersContent({ user, navigate }) {
  const [scopeMeta, setScopeMeta] = useState(null);
  const [personalTokens, setPersonalTokens] = useState([]);
  const [workspaceKeys, setWorkspaceKeys] = useState([]);
  const [webhookEndpoints, setWebhookEndpoints] = useState([]);
  const [loading, setLoading] = useState(Boolean(user));
  const [personalName, setPersonalName] = useState('Claude personal token');
  const [workspaceName, setWorkspaceName] = useState('Workspace integration key');
  const [personalScopes, setPersonalScopes] = useState([]);
  const [workspaceScopes, setWorkspaceScopes] = useState([]);
  const [generatedPersonalToken, setGeneratedPersonalToken] = useState('');
  const [generatedWorkspaceKey, setGeneratedWorkspaceKey] = useState('');
  const [generatedWebhookSecret, setGeneratedWebhookSecret] = useState('');
  const [creatingPersonal, setCreatingPersonal] = useState(false);
  const [creatingWorkspace, setCreatingWorkspace] = useState(false);
  const [creatingWebhook, setCreatingWebhook] = useState(false);
  const [testingEndpointId, setTestingEndpointId] = useState(null);
  const [selectedLogsEndpoint, setSelectedLogsEndpoint] = useState(null);
  const [deliveryLogs, setDeliveryLogs] = useState([]);
  const [loadingLogs, setLoadingLogs] = useState(false);

  const canManageWorkspaceKeys = hasWorkspacePermission(user, 'api_key:manage');
  const canManageWebhooks = hasWorkspacePermission(user, 'webhook:manage');

  useEffect(() => {
    if (!user) {
      setLoading(false);
      return undefined;
    }

    let active = true;
    const load = async () => {
      try {
        const [scopesResponse, personalResponse, workspaceResponse, webhooksResponse] = await Promise.all([
          getDeveloperScopes(),
          getPersonalTokens(),
          canManageWorkspaceKeys ? getApiKeys() : Promise.resolve([]),
          canManageWebhooks ? getWebhookEndpoints().catch(() => []) : Promise.resolve([]),
        ]);

        if (!active) return;

        setScopeMeta(scopesResponse);
        setPersonalTokens(Array.isArray(personalResponse) ? personalResponse : []);
        setWorkspaceKeys(Array.isArray(workspaceResponse) ? workspaceResponse : []);
        setWebhookEndpoints(Array.isArray(webhooksResponse) ? webhooksResponse : []);
        setPersonalScopes(scopesResponse.default_personal_scopes || []);
        setWorkspaceScopes(scopesResponse.default_workspace_scopes || []);
      } catch (error) {
        if (active) {
          toast.error(error?.response?.data?.detail || 'Failed to load developer credentials');
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    load();
    return () => {
      active = false;
    };
  }, [canManageWorkspaceKeys, canManageWebhooks, user]);

  const createPersonal = async () => {
    setCreatingPersonal(true);
    try {
      const result = await createPersonalToken({
        name: personalName,
        scopes: personalScopes,
      });
      setGeneratedPersonalToken(result.raw_key || '');
      setPersonalTokens((current) => [{ ...result, raw_key: undefined }, ...current]);
      toast.success('Personal token created');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to create personal token');
    } finally {
      setCreatingPersonal(false);
    }
  };

  const createWorkspace = async () => {
    setCreatingWorkspace(true);
    try {
      const result = await createApiKey({
        name: workspaceName,
        scopes: workspaceScopes,
      });
      setGeneratedWorkspaceKey(result.raw_key || '');
      setWorkspaceKeys((current) => [{ ...result, raw_key: undefined }, ...current]);
      toast.success('Workspace API key created');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to create workspace API key');
    } finally {
      setCreatingWorkspace(false);
    }
  };

  const registerWebhook = async (data, onSuccess) => {
    setCreatingWebhook(true);
    try {
      const result = await createWebhookEndpoint(data);
      if (result.signing_secret) {
        setGeneratedWebhookSecret(result.signing_secret);
      }
      setWebhookEndpoints((prev) => [result, ...prev]);
      toast.success('Webhook endpoint registered successfully');
      onSuccess?.();
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to register webhook endpoint');
    } finally {
      setCreatingWebhook(false);
    }
  };

  const revokePersonal = async (tokenId) => {
    try {
      await deletePersonalToken(tokenId);
      setPersonalTokens((current) => current.filter((item) => item.id !== tokenId));
      toast.success('Personal token revoked');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to revoke personal token');
    }
  };

  const revokeWorkspace = async (keyId) => {
    try {
      await deleteApiKey(keyId);
      setWorkspaceKeys((current) => current.filter((item) => item.id !== keyId));
      toast.success('Workspace API key revoked');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to revoke workspace API key');
    }
  };

  const revokeWebhook = async (endpointId) => {
    try {
      await deleteWebhookEndpoint(endpointId);
      setWebhookEndpoints((prev) => prev.filter((item) => item.id !== endpointId));
      toast.success('Webhook endpoint deleted');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to delete webhook endpoint');
    }
  };

  const handleTestWebhook = async (endpointId) => {
    setTestingEndpointId(endpointId);
    try {
      const res = await testWebhookEndpoint(endpointId);
      if (res.success) {
        toast.success(`Test ping succeeded (${res.status_code} OK in ${res.latency_ms}ms)`);
      } else {
        toast.error(`Test ping failed: ${res.error || `HTTP ${res.status_code}`}`);
      }
      const updated = await getWebhookEndpoints();
      setWebhookEndpoints(updated);
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to send test payload');
    } finally {
      setTestingEndpointId(null);
    }
  };

  const handleOpenDeliveries = async (endpoint) => {
    setSelectedLogsEndpoint(endpoint);
    setLoadingLogs(true);
    try {
      const logs = await getWebhookDeliveries(endpoint.id);
      setDeliveryLogs(logs);
    } catch {
      setDeliveryLogs([]);
    } finally {
      setLoadingLogs(false);
    }
  };

  const inboundPostSnippet = `curl -X POST "${BACKEND_URL}/api/v1/webhooks/inbound/post" \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "content": "Exciting product update from our CMS! 🚀",
    "platforms": ["twitter", "linkedin", "instagram"],
    "media_urls": ["https://assets.mybrand.com/update.png"],
    "scheduled_time": "2026-09-05T14:30:00Z",
    "publish_now": false
  }'`;

  const localConfigSnippet = `{
  "mcpServers": {
    "unravler": {
      "command": "node",
      "args": ["/absolute/path/to/unravler/app/mcp-server/index.js"],
      "env": {
        "UNRAVLER_TOKEN": "paste_personal_token_here",
        "UNRAVLER_BASE_URL": "${BACKEND_URL}"
      }
    }
  }
}`;

  const hostedCurlSnippet = `curl -X POST "${MCP_HTTP_ENDPOINT}" \\
  -H "Authorization: Bearer YOUR_PERSONAL_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'`;

  const postCreateSnippet = `curl -X POST "${PUBLIC_API_BASE}/posts" \\
  -H "Authorization: Bearer YOUR_PERSONAL_TOKEN" \\
  -H "Content-Type: application/json" \\
  -H "Idempotency-Key: create-campaign-42" \\
  -d '{
    "content": "Launch day is here.",
    "account_ids": ["acc_123"],
    "scheduled_time": "2026-06-15T09:30:00Z",
    "timeslot_category": "Category 1",
    "media_urls": ["https://example.com/banner.png"]
  }'`;

  return (
    <div className="space-y-8">
      <section className="rounded-[32px] border border-gray-200 bg-white px-6 py-7 shadow-sm dark:border-slate-800 dark:bg-slate-900 lg:px-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-4">
            <div className="inline-flex items-center gap-2 rounded-full bg-green-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-green-700 dark:bg-green-950/60 dark:text-green-300">
              <FaPlug className="text-[11px]" />
              Developers & Integrations
            </div>
            <div className="space-y-2">
              <h1 className="text-3xl font-semibold tracking-tight text-gray-900 dark:text-white">Build & automate with Unravler</h1>
              <p className="max-w-3xl text-sm leading-6 text-gray-600 dark:text-slate-400">
                Personal tokens for agents & IDEs, Workspace API keys for backend servers, Outbound webhooks for real-time Slack/Discord alerts, and Inbound webhooks for low-code Zapier & Make workflows.
              </p>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border border-gray-200 bg-offwhite px-4 py-4 dark:border-slate-800 dark:bg-slate-800/60">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500 dark:text-slate-400">REST Base</p>
              <p className="mt-2 break-all text-sm font-medium text-gray-900 dark:text-white">{PUBLIC_API_BASE}</p>
            </div>
            <div className="rounded-2xl border border-gray-200 bg-offwhite px-4 py-4 dark:border-slate-800 dark:bg-slate-800/60">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500 dark:text-slate-400">Hosted MCP</p>
              <p className="mt-2 break-all text-sm font-medium text-gray-900 dark:text-white">{MCP_HTTP_ENDPOINT}</p>
            </div>
            <div className="rounded-2xl border border-gray-200 bg-offwhite px-4 py-4 dark:border-slate-800 dark:bg-slate-800/60">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500 dark:text-slate-400">Webhooks</p>
              <p className="mt-2 text-sm font-medium text-gray-900 dark:text-white">HMAC SHA-256 + Slack/Discord</p>
            </div>
          </div>
        </div>
      </section>

      {user ? (
        <section className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-[28px] border border-gray-200 bg-white px-5 py-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 lg:px-7">
            <div className="flex items-start gap-3">
              <FaBook className="mt-1 text-gray-400" />
              <div className="space-y-2">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Active workspace context</h2>
                <p className="text-sm text-gray-600 dark:text-slate-400">
                  Tokens are bound to your current workspace and capped by your role there. Switch workspace before generating a credential if you need a different target.
                </p>
              </div>
            </div>
          </div>
          <div className="rounded-[28px] border border-gray-200 bg-white px-5 py-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 lg:px-7">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500 dark:text-slate-400">Current role</p>
            <p className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">{scopeMeta?.workspace_role || user.workspace_role || 'member'}</p>
            <p className="mt-2 text-sm text-gray-600 dark:text-slate-400">
              Allowed scopes: {(scopeMeta?.allowed_scopes || []).join(', ') || 'Loading...'}
            </p>
          </div>
        </section>
      ) : null}

      {user ? (
        loading ? (
          <section className="rounded-[28px] border border-gray-200 bg-white px-6 py-10 text-sm text-gray-500 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            Loading developer credentials...
          </section>
        ) : (
          <div className="space-y-8">
            {canManageWebhooks ? (
              <WebhookSection
                endpoints={webhookEndpoints}
                onRegister={registerWebhook}
                onDelete={revokeWebhook}
                onTest={handleTestWebhook}
                onViewDeliveries={handleOpenDeliveries}
                testingEndpointId={testingEndpointId}
                busyRegister={creatingWebhook}
                generatedSecret={generatedWebhookSecret}
                setGeneratedSecret={setGeneratedWebhookSecret}
              />
            ) : null}

            <section className="space-y-4 rounded-[28px] border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-start gap-3">
                <FaBolt className="mt-1 text-amber-500" />
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Inbound Automation Webhook (Zapier, Make, n8n, Airtable)</h2>
                  <p className="text-sm text-gray-600 dark:text-slate-400">
                    Trigger automatic social scheduling from external tools without writing SDK code. Point your Notion, Airtable, or WordPress automation to this endpoint:
                  </p>
                </div>
              </div>
              <CodeBlock label="Inbound Webhook Payload Example">{inboundPostSnippet}</CodeBlock>
            </section>

            <CredentialSection
              title="Personal Tokens"
              icon={FaLaptopCode}
              copy="Use personal tokens for Claude Desktop, Cursor, local MCP clients, scripts, and direct REST calls. These inherit only the capabilities your workspace role already has."
              createLabel="Create personal token"
              name={personalName}
              setName={setPersonalName}
              scopes={personalScopes}
              setScopes={setPersonalScopes}
              allowedScopes={scopeMeta?.allowed_scopes || []}
              items={personalTokens}
              onCreate={createPersonal}
              onDelete={revokePersonal}
              busy={creatingPersonal}
              generatedToken={generatedPersonalToken}
            />

            {canManageWorkspaceKeys ? (
              <CredentialSection
                title="Workspace API Keys"
                icon={FaServer}
                copy="Use workspace API keys for admin-owned service integrations such as internal automation jobs or server-side orchestration. These keys are still scoped to the active workspace."
                createLabel="Create workspace key"
                name={workspaceName}
                setName={setWorkspaceName}
                scopes={workspaceScopes}
                setScopes={setWorkspaceScopes}
                allowedScopes={scopeMeta?.allowed_scopes || []}
                items={workspaceKeys}
                onCreate={createWorkspace}
                onDelete={revokeWorkspace}
                busy={creatingWorkspace}
                generatedToken={generatedWorkspaceKey}
              />
            ) : (
              <section className="rounded-[28px] border border-gray-200 bg-white px-6 py-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Workspace API Keys</h2>
                <p className="mt-2 text-sm text-gray-600 dark:text-slate-400">
                  Admin or owner access is required to create shared workspace API keys. Personal tokens are still available above for your own agent and REST workflows.
                </p>
              </section>
            )}
          </div>
        )
      ) : null}

      <AiAgentMcpHub
        personalTokens={personalTokens}
        generatedToken={generatedPersonalToken}
        backendUrl={BACKEND_URL}
        mcpEndpoint={MCP_HTTP_ENDPOINT}
      />

      <section className="space-y-6 rounded-[28px] border border-gray-200 bg-white px-6 py-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-start gap-3">
          <FaGlobe className="mt-1 text-gray-400" />
          <div className="space-y-2">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">REST reference</h2>
            <p className="text-sm text-gray-600 dark:text-slate-400">
              All write routes support <code className="rounded bg-gray-100 px-1 dark:bg-slate-800">Idempotency-Key</code>. Public media URLs are validated with the same SSRF and content rules as the main composer flow.
            </p>
          </div>
        </div>
        <CodeBlock label="Create a scheduled post">{postCreateSnippet}</CodeBlock>
        <div className="grid gap-4 xl:grid-cols-2">
          {REST_GROUPS.map((group) => (
            <div key={group.title} className="rounded-2xl border border-gray-200 bg-offwhite p-4 dark:border-slate-800 dark:bg-slate-800/60">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{group.title}</h3>
              <div className="mt-4 space-y-3">
                {group.items.map((item) => (
                  <div key={`${group.title}-${item.method}-${item.path}`} className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${METHOD_STYLES[item.method]}`}>
                        {item.method}
                      </span>
                      <code className="text-xs text-gray-700 dark:text-slate-300">{item.path}</code>
                    </div>
                    <p className="mt-2 text-sm text-gray-700 dark:text-slate-300">{item.description}</p>
                    <p className="mt-2 text-xs text-gray-500 dark:text-slate-400">Required scope: {item.scope}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <DeliveriesModal
        endpoint={selectedLogsEndpoint}
        deliveries={deliveryLogs}
        open={Boolean(selectedLogsEndpoint)}
        onClose={() => setSelectedLogsEndpoint(null)}
        loading={loadingLogs}
      />

      {!user ? (
        <section className="rounded-[28px] border border-gray-200 bg-white px-6 py-7 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="space-y-2">
              <h2 className="text-xl font-semibold text-gray-900">Sign in to create tokens</h2>
              <p className="text-sm text-gray-600">
                Developers docs are public, but token creation and workspace-scoped credentials require an authenticated Unravler account.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => navigate('/login', { state: { returnTo: '/developers' } })}>
                Login
              </Button>
              <Button variant="outline" onClick={() => navigate('/signup', { state: { returnTo: '/developers' } })}>
                Create account
              </Button>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function PublicShell({ children, navigate }) {
  return (
    <div className="min-h-screen bg-offwhite">
      <header className="border-b border-gray-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <button type="button" onClick={() => navigate('/')} className="rounded-md">
            <UnravlerLogo />
          </button>
          <div className="flex flex-wrap gap-3">
            <Button variant="ghost" onClick={() => navigate('/login', { state: { returnTo: '/developers' } })}>
              Login
            </Button>
            <Button onClick={() => navigate('/signup', { state: { returnTo: '/developers' } })}>
              Start building
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {children}
      </main>
    </div>
  );
}

export default function Developers() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-sm text-muted-foreground">
        Loading developers surface...
      </div>
    );
  }

  const content = <DevelopersContent user={user} navigate={navigate} />;

  if (user) {
    return (
      <DashboardLayout>
        {content}
      </DashboardLayout>
    );
  }

  return (
    <PublicShell navigate={navigate}>
      {content}
    </PublicShell>
  );
}
