import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import {
  FaBook,
  FaCloud,
  FaCode,
  FaCopy,
  FaGlobe,
  FaKey,
  FaLaptopCode,
  FaPlug,
  FaServer,
  FaTrash,
} from 'react-icons/fa';

import DashboardLayout from '@/components/DashboardLayout';
import UnravlerLogo from '@/components/UnravlerLogo';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/context/AuthContext';
import {
  createApiKey,
  createPersonalToken,
  deleteApiKey,
  deletePersonalToken,
  getApiKeys,
  getDeveloperScopes,
  getPersonalTokens,
} from '@/lib/api';
import { hasWorkspacePermission } from '@/lib/workspacePermissions';

const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || 'https://api.unravler.com').replace(/\/$/, '');
const PUBLIC_API_BASE = `${BACKEND_URL}/api/public`;
const MCP_HTTP_ENDPOINT = `${BACKEND_URL}/mcp`;

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
    title: 'Approvals',
    items: [
      { method: 'GET', path: '/approvals', scope: 'approval:read', description: 'Read awaiting, expired, and changes-requested review buckets.' },
      { method: 'POST', path: '/posts/{post_id}/submit-review', scope: 'approval:write', description: 'Submit a future-scheduled draft for approval.' },
      { method: 'POST', path: '/posts/{post_id}/approve', scope: 'approval:write', description: 'Approve a pending item back into scheduled status.' },
      { method: 'POST', path: '/posts/{post_id}/reject', scope: 'approval:write', description: 'Reject a pending item back to draft with a reason.' },
      { method: 'POST', path: '/posts/{post_id}/return-to-draft', scope: 'approval:write', description: 'Recover expired approval items into draft status.' },
      { method: 'POST', path: '/posts/{post_id}/resubmit', scope: 'approval:write', description: 'Resubmit a creator-owned draft after changes and rescheduling.' },
    ],
  },
  {
    title: 'Workspace',
    items: [
      { method: 'GET', path: '/accounts', scope: 'accounts:read', description: 'List connected social accounts available to the active workspace.' },
      { method: 'GET', path: '/stats', scope: 'stats:read', description: 'Fetch high-level operational stats used by dashboards and automations.' },
      { method: 'POST', path: '/ai/generate', scope: 'ai:generate', description: 'Generate copy variants with platform-aware prompts.' },
    ],
  },
];

const METHOD_STYLES = {
  GET: 'bg-blue-50 text-blue-700 border-blue-200',
  POST: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  PATCH: 'bg-amber-50 text-amber-700 border-amber-200',
  DELETE: 'bg-rose-50 text-rose-700 border-rose-200',
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
      className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:border-gray-300 hover:bg-gray-50"
    >
      <FaCopy className="text-[10px]" />
      {copied ? 'Copied' : label}
    </button>
  );
}

function CodeBlock({ label, children }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-gray-200 bg-slate-950">
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
        <p className="text-sm font-medium text-gray-900">{title}</p>
        <p className="text-xs text-gray-500">Choose the exact capabilities this credential should be allowed to use.</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {scopes.map((scope) => {
          const checked = selectedScopes.includes(scope);
          return (
            <label
              key={scope}
              className={`flex cursor-pointer items-center justify-between rounded-2xl border px-3 py-2 text-sm transition ${
                checked
                  ? 'border-green-300 bg-green-50 text-green-900'
                  : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300'
              }`}
            >
              <span className="font-medium">{scope}</span>
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-gray-300"
                checked={checked}
                onChange={() => onToggle(scope)}
              />
            </label>
          );
        })}
      </div>
    </div>
  );
}

function CredentialList({ items, onDelete, emptyLabel }) {
  if (!items.length) {
    return (
      <div className="rounded-2xl border border-dashed border-gray-300 bg-gray-50 px-4 py-6 text-sm text-gray-500">
        {emptyLabel}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div
          key={item.id}
          className="rounded-2xl border border-gray-200 bg-white px-4 py-4 shadow-sm"
        >
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <h4 className="text-sm font-semibold text-gray-900">{item.name}</h4>
                <span className="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-gray-600">
                  {item.token_type}
                </span>
                <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-mono text-slate-600">
                  {item.key_prefix}
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {(item.scopes || []).map((scope) => (
                  <span key={scope} className="rounded-full border border-gray-200 bg-white px-2.5 py-1 text-[11px] font-medium text-gray-600">
                    {scope}
                  </span>
                ))}
              </div>
              <div className="flex flex-wrap gap-4 text-xs text-gray-500">
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
              className="border-rose-200 text-rose-600 hover:bg-rose-50 hover:text-rose-700"
              onClick={() => onDelete(item.id)}
            >
              <FaTrash className="mr-2 text-xs" />
              Revoke
            </Button>
          </div>
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
    <section className="space-y-5 rounded-[28px] border border-gray-200 bg-offwhite px-5 py-6 shadow-sm lg:px-7">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-gray-600 shadow-sm">
            <Icon className="text-[11px]" />
            {title}
          </div>
          <p className="max-w-2xl text-sm text-gray-600">{copy}</p>
        </div>
      </div>

      {generatedToken ? (
        <div className="rounded-2xl border border-green-200 bg-green-50 p-4">
          <p className="text-sm font-semibold text-green-900">Copy this token now</p>
          <p className="mt-1 text-xs text-green-700">
            Raw tokens are only shown once. Save it in your client config or secret manager immediately.
          </p>
          <div className="mt-3 flex flex-col gap-3 rounded-2xl border border-green-200 bg-white p-3 lg:flex-row lg:items-center lg:justify-between">
            <code className="break-all text-xs text-slate-800">{generatedToken}</code>
            <CopyButton text={generatedToken} label="Copy token" />
          </div>
        </div>
      ) : null}

      <form
        className="space-y-4 rounded-2xl border border-gray-200 bg-white p-4"
        onSubmit={(event) => {
          event.preventDefault();
          onCreate();
        }}
      >
        <div className="space-y-2">
          <label className="text-sm font-medium text-gray-900" htmlFor={`${title}-name`}>
            Credential name
          </label>
          <Input
            id={`${title}-name`}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={title === 'Personal Tokens' ? 'Claude personal token' : 'Zapier workspace key'}
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

function DevelopersContent({ user, navigate }) {
  const [scopeMeta, setScopeMeta] = useState(null);
  const [personalTokens, setPersonalTokens] = useState([]);
  const [workspaceKeys, setWorkspaceKeys] = useState([]);
  const [loading, setLoading] = useState(Boolean(user));
  const [personalName, setPersonalName] = useState('Claude personal token');
  const [workspaceName, setWorkspaceName] = useState('Workspace integration key');
  const [personalScopes, setPersonalScopes] = useState([]);
  const [workspaceScopes, setWorkspaceScopes] = useState([]);
  const [generatedPersonalToken, setGeneratedPersonalToken] = useState('');
  const [generatedWorkspaceKey, setGeneratedWorkspaceKey] = useState('');
  const [creatingPersonal, setCreatingPersonal] = useState(false);
  const [creatingWorkspace, setCreatingWorkspace] = useState(false);

  const canManageWorkspaceKeys = hasWorkspacePermission(user, 'api_key:manage');

  useEffect(() => {
    if (!user) {
      setLoading(false);
      return undefined;
    }

    let active = true;
    const load = async () => {
      try {
        const [scopesResponse, personalResponse, workspaceResponse] = await Promise.all([
          getDeveloperScopes(),
          getPersonalTokens(),
          canManageWorkspaceKeys ? getApiKeys() : Promise.resolve([]),
        ]);

        if (!active) {
          return;
        }

        setScopeMeta(scopesResponse);
        setPersonalTokens(Array.isArray(personalResponse) ? personalResponse : []);
        setWorkspaceKeys(Array.isArray(workspaceResponse) ? workspaceResponse : []);
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
  }, [canManageWorkspaceKeys, user]);

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
    "scheduled_at": "2026-06-15T09:30:00Z",
    "media_urls": ["https://example.com/banner.png"]
  }'`;

  return (
    <div className="space-y-8">
      <section className="rounded-[32px] border border-gray-200 bg-white px-6 py-7 shadow-sm lg:px-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-4">
            <div className="inline-flex items-center gap-2 rounded-full bg-green-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-green-700">
              <FaPlug className="text-[11px]" />
              Developers
            </div>
            <div className="space-y-2">
              <h1 className="text-3xl font-semibold tracking-tight text-gray-900">Build against Unravler without bypassing the product rules</h1>
              <p className="max-w-3xl text-sm leading-6 text-gray-600">
                Personal tokens are the recommended path for Claude, Cursor, and local agent workflows. Workspace API keys remain available for admin-owned service integrations. Both route into the same approval, scheduling, and media validation logic as the app.
              </p>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border border-gray-200 bg-offwhite px-4 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">REST Base</p>
              <p className="mt-2 break-all text-sm font-medium text-gray-900">{PUBLIC_API_BASE}</p>
            </div>
            <div className="rounded-2xl border border-gray-200 bg-offwhite px-4 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">Hosted MCP</p>
              <p className="mt-2 break-all text-sm font-medium text-gray-900">{MCP_HTTP_ENDPOINT}</p>
            </div>
            <div className="rounded-2xl border border-gray-200 bg-offwhite px-4 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">Recommended Token</p>
              <p className="mt-2 text-sm font-medium text-gray-900">Personal, workspace-bound</p>
            </div>
          </div>
        </div>
      </section>

      {user ? (
        <section className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-[28px] border border-gray-200 bg-white px-5 py-6 shadow-sm lg:px-7">
            <div className="flex items-start gap-3">
              <FaBook className="mt-1 text-gray-400" />
              <div className="space-y-2">
                <h2 className="text-lg font-semibold text-gray-900">Active workspace context</h2>
                <p className="text-sm text-gray-600">
                  Tokens are bound to your current workspace and capped by your role there. Switch workspace before generating a credential if you need a different target.
                </p>
              </div>
            </div>
          </div>
          <div className="rounded-[28px] border border-gray-200 bg-white px-5 py-6 shadow-sm lg:px-7">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-500">Current role</p>
            <p className="mt-2 text-2xl font-semibold text-gray-900">{scopeMeta?.workspace_role || user.workspace_role || 'member'}</p>
            <p className="mt-2 text-sm text-gray-600">
              Allowed scopes: {(scopeMeta?.allowed_scopes || []).join(', ') || 'Loading...'}
            </p>
          </div>
        </section>
      ) : null}

      {user ? (
        loading ? (
          <section className="rounded-[28px] border border-gray-200 bg-white px-6 py-10 text-sm text-gray-500 shadow-sm">
            Loading developer credentials...
          </section>
        ) : (
          <div className="space-y-8">
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
              <section className="rounded-[28px] border border-gray-200 bg-white px-6 py-6 shadow-sm">
                <h2 className="text-lg font-semibold text-gray-900">Workspace API Keys</h2>
                <p className="mt-2 text-sm text-gray-600">
                  Admin or owner access is required to create shared workspace API keys. Personal tokens are still available above for your own agent and REST workflows.
                </p>
              </section>
            )}
          </div>
        )
      ) : null}

      <section className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
        <div className="space-y-6 rounded-[28px] border border-gray-200 bg-white px-6 py-6 shadow-sm">
          <div className="flex items-start gap-3">
            <FaCloud className="mt-1 text-gray-400" />
            <div className="space-y-2">
              <h2 className="text-lg font-semibold text-gray-900">Hosted MCP setup</h2>
              <p className="text-sm text-gray-600">
                Use the hosted HTTP MCP endpoint when your client supports remote MCP calls over HTTPS. Authenticate with a personal token in the bearer header.
              </p>
            </div>
          </div>
          <CodeBlock label="HTTP MCP probe">{hostedCurlSnippet}</CodeBlock>
        </div>
        <div className="space-y-6 rounded-[28px] border border-gray-200 bg-white px-6 py-6 shadow-sm">
          <div className="flex items-start gap-3">
            <FaCode className="mt-1 text-gray-400" />
            <div className="space-y-2">
              <h2 className="text-lg font-semibold text-gray-900">Local stdio MCP setup</h2>
              <p className="text-sm text-gray-600">
                Use the bundled local package when your client prefers stdio transport. Legacy <code className="rounded bg-gray-100 px-1">SOCIALENTANGLER_API_KEY</code> still works, but <code className="rounded bg-gray-100 px-1">UNRAVLER_TOKEN</code> is the preferred env var now.
              </p>
            </div>
          </div>
          <CodeBlock label="Claude or Cursor config">{localConfigSnippet}</CodeBlock>
        </div>
      </section>

      <section className="space-y-6 rounded-[28px] border border-gray-200 bg-white px-6 py-6 shadow-sm">
        <div className="flex items-start gap-3">
          <FaGlobe className="mt-1 text-gray-400" />
          <div className="space-y-2">
            <h2 className="text-lg font-semibold text-gray-900">REST reference</h2>
            <p className="text-sm text-gray-600">
              All write routes support <code className="rounded bg-gray-100 px-1">Idempotency-Key</code>. Public media URLs are validated with the same SSRF and content rules as the main composer flow.
            </p>
          </div>
        </div>
        <CodeBlock label="Create a scheduled post">{postCreateSnippet}</CodeBlock>
        <div className="grid gap-4 xl:grid-cols-2">
          {REST_GROUPS.map((group) => (
            <div key={group.title} className="rounded-2xl border border-gray-200 bg-offwhite p-4">
              <h3 className="text-sm font-semibold text-gray-900">{group.title}</h3>
              <div className="mt-4 space-y-3">
                {group.items.map((item) => (
                  <div key={`${group.title}-${item.method}-${item.path}`} className="rounded-2xl border border-gray-200 bg-white p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${METHOD_STYLES[item.method]}`}>
                        {item.method}
                      </span>
                      <code className="text-xs text-gray-700">{item.path}</code>
                    </div>
                    <p className="mt-2 text-sm text-gray-700">{item.description}</p>
                    <p className="mt-2 text-xs text-gray-500">Required scope: {item.scope}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

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
