import React, { useState, useEffect } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { getApiKeys, createApiKey, deleteApiKey } from '@/lib/api';
import { toast } from 'sonner';
import { FaKey, FaTrash, FaCopy, FaCheckCircle, FaBook } from 'react-icons/fa';

// ─── Inline docs data ──────────────────────────────────────────────────────────
const BASE_URL = `${process.env.REACT_APP_BACKEND_URL}/api/public`;

const ENDPOINTS = [
  {
    group: 'Accounts',
    items: [
      {
        method: 'GET',
        path: '/accounts',
        description: 'List all connected and active social media accounts.',
        request: null,
        response: `{
  "accounts": [
    { "id": "acc_abc123", "platform": "instagram", "username": "@yourhandle", "status": "active" },
    { "id": "acc_def456", "platform": "twitter",   "username": "@yourhandle", "status": "active" }
  ],
  "total": 2
}`,
      },
    ],
  },
  {
    group: 'Posts',
    items: [
      {
        method: 'GET',
        path: '/posts',
        description: 'List posts (paginated). Returns draft, scheduled, published, and failed posts.',
        params: [
          { name: 'page',  type: 'query', required: false, desc: 'Page number (default: 1)' },
          { name: 'limit', type: 'query', required: false, desc: 'Results per page, max 100 (default: 20)' },
        ],
        request: null,
        response: `{
  "data": [
    {
      "id": "post-uuid",
      "status": "scheduled",
      "platforms": ["instagram", "twitter"],
      "scheduled_time": "2025-06-01T09:00:00Z",
      "created_at": "2025-05-28T12:00:00Z",
      "platform_results": {}
    }
  ],
  "total": 42,
  "page": 1,
  "limit": 20
}`,
      },
      {
        method: 'GET',
        path: '/posts/{post_id}',
        description: 'Get full details of a single post.',
        params: [
          { name: 'post_id', type: 'path', required: true, desc: 'The post ID' },
        ],
        request: null,
        response: `{
  "id": "post-uuid",
  "status": "published",
  "platforms": ["instagram"],
  "scheduled_time": "2025-06-01T09:00:00Z",
  "created_at": "2025-05-28T12:00:00Z",
  "platform_results": { "instagram": { "post_id": "18023...", "url": "https://..." } }
}`,
      },
      {
        method: 'POST',
        path: '/posts',
        description: 'Create a post — save as draft, schedule for later, or publish immediately.',
        request: `{
  "content": "Hello from the SocialEntangler API!",
  "account_ids": ["acc_abc123", "acc_def456"],
  "scheduled_at": "2025-06-01T09:00:00Z",
  "publish_now": false,
  "media_urls": []
}`,
        response: `{
  "id": "post-uuid",
  "status": "scheduled",
  "scheduled_at": "2025-06-01T09:00:00Z",
  "message": "Post scheduled for 2025-06-01T09:00:00Z."
}`,
        notes: 'Set publish_now: true to publish immediately. Omit scheduled_at to save as draft.',
      },
      {
        method: 'DELETE',
        path: '/posts/{post_id}',
        description: 'Soft-delete a post.',
        params: [
          { name: 'post_id', type: 'path', required: true, desc: 'The post ID to delete' },
        ],
        request: null,
        response: `204 No Content`,
      },
      {
        method: 'POST',
        path: '/posts/{post_id}/retry',
        description: 'Retry a failed or partially-published post.',
        params: [
          { name: 'post_id', type: 'path', required: true, desc: 'The failed post ID' },
        ],
        request: null,
        response: `{
  "post_id": "post-uuid",
  "status": "scheduled",
  "message": "Post queued for retry."
}`,
      },
    ],
  },
  {
    group: 'AI Content',
    items: [
      {
        method: 'POST',
        path: '/ai/generate',
        description: 'Generate platform-optimized social media content using AI.',
        request: `{
  "topic": "Black Friday sale — 50% off everything",
  "platform": "instagram",
  "tone": "excited",
  "count": 3,
  "additional_context": "Include emoji and hashtags"
}`,
        response: `{
  "variations": ["Caption 1...", "Caption 2...", "Caption 3..."],
  "platform": "instagram",
  "count": 3
}`,
        notes: 'platform: instagram | twitter | linkedin | facebook | tiktok | youtube. tone: professional | casual | excited | funny | inspirational | informative. count: 1–5.',
      },
    ],
  },
  {
    group: 'Stats',
    items: [
      {
        method: 'GET',
        path: '/stats',
        description: 'Dashboard statistics — post counts by status, connected accounts.',
        request: null,
        response: `{
  "total_posts": 142,
  "scheduled_posts": 8,
  "published_posts": 130,
  "failed_posts": 4,
  "connected_accounts": 5
}`,
      },
    ],
  },
];

// Post state colors
const STATE_COLORS = {
  QUEUE: 'bg-yellow-100 text-yellow-800',
  SCHEDULED: 'bg-blue-100 text-blue-800',
  PUBLISHED: 'bg-green-100 text-green-800',
  ERROR: 'bg-red-100 text-red-800',
  DRAFT: 'bg-gray-100 text-gray-700',
};

const METHOD_COLORS = {
  GET: 'bg-blue-100 text-blue-700',
  POST: 'bg-green-100 text-green-700',
  DELETE: 'bg-red-100 text-red-700',
  PUT: 'bg-orange-100 text-orange-700',
  PATCH: 'bg-purple-100 text-purple-700',
};

// ─── Reusable tiny components ──────────────────────────────────────────────────
const MethodBadge = ({ method }) => (
  <span className={`inline-block px-2 py-0.5 rounded text-xs font-mono font-semibold ${METHOD_COLORS[method] || 'bg-gray-100 text-gray-700'}`}>
    {method}
  </span>
);

const CodeBlock = ({ children }) => {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };
  return (
    <div className="relative group">
      <pre className="bg-slate-900 text-slate-100 text-xs rounded-lg p-4 overflow-x-auto font-mono leading-relaxed">
        {children}
      </pre>
      <button
        onClick={copy}
        className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-700 hover:bg-slate-600 text-slate-200 rounded px-2 py-1 text-xs flex items-center gap-1"
      >
        {copied ? <FaCheckCircle className="text-green-400" /> : <FaCopy />}
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  );
};

// ─── Keys Tab ─────────────────────────────────────────────────────────────────
const KeysTab = () => {
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newKeyName, setNewKeyName] = useState('');
  const [generating, setGenerating] = useState(false);
  const [generatedKey, setGeneratedKey] = useState(null);

  useEffect(() => { fetchKeys(); }, []);

  const fetchKeys = async () => {
    try {
      const data = await getApiKeys();
      setKeys(data);
    } catch {
      toast.error('Failed to fetch API keys');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newKeyName.trim()) return;
    setGenerating(true);
    try {
      const data = await createApiKey({ name: newKeyName });
      setGeneratedKey(data.raw_key);
      setNewKeyName('');
      fetchKeys();
      toast.success('API Key generated successfully');
    } catch {
      toast.error('Failed to generate API key');
    } finally {
      setGenerating(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Revoke this API key? Any integration using it will lose access.')) return;
    try {
      await deleteApiKey(id);
      setKeys(keys.filter(k => k.id !== id));
      toast.success('API Key revoked');
    } catch {
      toast.error('Failed to revoke API key');
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast.success('Copied to clipboard');
  };

  return (
    <div className="space-y-6">
      {/* New key alert */}
      {generatedKey && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-6 space-y-4">
          <h2 className="text-lg font-semibold text-green-900">New API Key Generated</h2>
          <p className="text-sm text-green-700">
            Copy this key and store it safely. <strong>It will never be shown again.</strong>
          </p>
          <div className="flex gap-2">
            <code className="flex-1 bg-offwhite border border-green-200 p-2 rounded text-sm font-mono truncate lg:whitespace-normal">
              {generatedKey}
            </code>
            <Button onClick={() => copyToClipboard(generatedKey)} variant="outline" size="sm" className="bg-offwhite">
              <FaCopy className="mr-2" /> Copy
            </Button>
          </div>
          <Button onClick={() => setGeneratedKey(null)} variant="link" className="text-green-700 p-0 h-auto font-medium">
            I've saved the key
          </Button>
        </div>
      )}

      {/* Generate form */}
      <div className="bg-offwhite rounded-lg border border-border p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900 mb-6">Generate New Key</h2>
        <form onSubmit={handleCreate} className="flex gap-4 items-end">
          <div className="flex-1 space-y-2">
            <Label htmlFor="keyName">Key Name</Label>
            <Input
              id="keyName"
              placeholder="e.g. My Agent, n8n Workflow…"
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={generating || !newKeyName.trim()}>
            {generating ? 'Generating…' : 'Generate Key'}
          </Button>
        </form>
      </div>

      {/* Keys table */}
      <div className="bg-offwhite rounded-lg border border-border overflow-hidden shadow-sm">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-offwhite border-b border-border">
              <th className="px-6 py-4 text-sm font-semibold text-slate-900">Name</th>
              <th className="px-6 py-4 text-sm font-semibold text-slate-900">Created</th>
              <th className="px-6 py-4 text-sm font-semibold text-slate-900">Last Used</th>
              <th className="px-6 py-4 text-sm font-semibold text-slate-900 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {loading ? (
              <tr><td colSpan="4" className="px-6 py-8 text-center text-slate-500">Loading keys…</td></tr>
            ) : keys.length === 0 ? (
              <tr><td colSpan="4" className="px-6 py-8 text-center text-slate-500">No API keys yet.</td></tr>
            ) : keys.map((key) => (
              <tr key={key.id} className="hover:bg-slate-50/50 transition-colors">
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-offwhite border border-slate-200 rounded text-slate-600">
                      <FaKey size={12} />
                    </div>
                    <span className="font-medium text-slate-900">{key.name}</span>
                  </div>
                </td>
                <td className="px-6 py-4 text-sm text-slate-600">
                  {new Date(key.created_at).toLocaleDateString()}
                </td>
                <td className="px-6 py-4 text-sm text-slate-600">
                  {key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'Never'}
                </td>
                <td className="px-6 py-4 text-right">
                  <Button onClick={() => handleDelete(key.id)} variant="ghost" size="icon" className="text-slate-400 hover:text-red-600">
                    <FaTrash />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ─── Reference Tab ─────────────────────────────────────────────────────────────
const ReferenceTab = () => {
  const [openEndpoint, setOpenEndpoint] = useState(null);

  const toggle = (key) => setOpenEndpoint(prev => prev === key ? null : key);

  return (
    <div className="space-y-8">
      {/* Base URL + Auth */}
      <div className="bg-offwhite rounded-lg border border-border p-6 shadow-sm space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 mb-2">Base URL</h2>
          <CodeBlock>{BASE_URL}</CodeBlock>
        </div>
        <div>
          <h2 className="text-lg font-semibold text-slate-900 mb-1">Authentication</h2>
          <p className="text-sm text-slate-600 mb-2">
            All endpoints require your API key in the <code className="bg-slate-100 px-1 py-0.5 rounded text-xs font-mono">X-API-Key</code> request header.
          </p>
          <CodeBlock>{`X-API-Key: your-api-key`}</CodeBlock>
        </div>
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
          <strong>Rate limit:</strong> 30 requests / hour per key.
        </div>
      </div>

      {/* Endpoint groups */}
      {ENDPOINTS.map((group) => (
        <div key={group.group} className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-400 px-1">{group.group}</h3>
          <div className="bg-offwhite rounded-lg border border-border shadow-sm overflow-hidden divide-y divide-border">
            {group.items.map((ep) => {
              const key = `${ep.method}-${ep.path}`;
              const isOpen = openEndpoint === key;
              return (
                <div key={key}>
                  {/* Row header */}
                  <button
                    className="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-slate-50 transition-colors"
                    onClick={() => toggle(key)}
                  >
                    <MethodBadge method={ep.method} />
                    <code className="text-sm font-mono text-slate-800 flex-1">{ep.path}</code>
                    <span className="text-sm text-slate-500 hidden sm:block">{ep.description}</span>
                    <span className={`ml-2 text-slate-400 text-xs transition-transform ${isOpen ? 'rotate-180' : ''}`}>▼</span>
                  </button>

                  {/* Expanded detail */}
                  {isOpen && (
                    <div className="px-5 pb-5 pt-2 bg-slate-50 border-t border-border space-y-4">
                      <p className="text-sm text-slate-700">{ep.description}</p>

                      {ep.params && (
                        <div>
                          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Parameters</p>
                          <table className="w-full text-sm border border-border rounded overflow-hidden">
                            <thead>
                              <tr className="bg-offwhite border-b border-border">
                                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600">Name</th>
                                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600">In</th>
                                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600">Required</th>
                                <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600">Description</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border bg-offwhite">
                              {ep.params.map(p => (
                                <tr key={p.name}>
                                  <td className="px-3 py-2 font-mono text-xs text-slate-800">{p.name}</td>
                                  <td className="px-3 py-2 text-xs text-slate-500">{p.type}</td>
                                  <td className="px-3 py-2 text-xs">
                                    {p.required
                                      ? <span className="text-red-600 font-semibold">yes</span>
                                      : <span className="text-slate-400">no</span>}
                                  </td>
                                  <td className="px-3 py-2 text-xs text-slate-600">{p.desc}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {ep.request && (
                        <div>
                          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Request Body</p>
                          <CodeBlock>{ep.request}</CodeBlock>
                        </div>
                      )}

                      <div>
                        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Response — 200 OK</p>
                        <CodeBlock>{ep.response}</CodeBlock>
                      </div>

                      {ep.notes && (
                        <p className="text-xs text-slate-500 italic">{ep.notes}</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* Auth note */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
        <strong>Authentication:</strong> Pass your API key in every request as <code className="font-mono bg-amber-100 px-1 rounded">X-API-Key: se_your_key</code>. Keys can be created and revoked from the Keys tab. Never share your key or commit it to version control.
      </div>
    </div>
  );
};

// ─── Page ──────────────────────────────────────────────────────────────────────
const ApiKeys = () => {
  const [tab, setTab] = useState('keys');

  return (
    <DashboardLayout>
      <div className="max-w-4xl space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">API</h1>
          <p className="text-base text-slate-600 mt-1">
            Manage API keys and explore the public REST API for external integrations and AI agents.
          </p>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-border">
          {[
            { id: 'keys',      label: 'Keys',          icon: FaKey },
            { id: 'reference', label: 'API Reference',  icon: FaBook },
          ].map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
                tab === id
                  ? 'border-green-600 text-green-700'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              <Icon className="text-xs" />
              {label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {tab === 'keys'      && <KeysTab />}
        {tab === 'reference' && <ReferenceTab />}
      </div>
    </DashboardLayout>
  );
};

export default ApiKeys;
