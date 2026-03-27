import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { getApiKeys, createApiKey } from '@/lib/api';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'https://api.socialentangler.com';

const tools = [
  {
    name: 'list_connected_accounts',
    desc: 'List all connected social media accounts with their IDs, platform names, and usernames.',
    params: [],
    example: `// Returns
{
  "accounts": [
    { "id": "acc_abc123", "platform": "instagram", "username": "@yourhandle" },
    { "id": "acc_def456", "platform": "twitter",   "username": "@yourhandle" }
  ],
  "total": 2
}`,
  },
  {
    name: 'create_post',
    desc: 'Create a post — publish immediately, schedule for later, or save as draft.',
    params: [
      { name: 'content', type: 'string', required: true, desc: 'Text content of the post' },
      { name: 'account_ids', type: 'string[]', required: true, desc: 'Account IDs from list_connected_accounts' },
      { name: 'scheduled_at', type: 'ISO 8601', required: false, desc: 'Schedule time e.g. "2025-06-01T09:00:00Z"' },
      { name: 'publish_now', type: 'boolean', required: false, desc: 'Set true to publish immediately' },
      { name: 'media_urls', type: 'string[]', required: false, desc: 'Media URLs from upload_media' },
    ],
    example: `{
  "content": "Big news dropping tomorrow 🚀",
  "account_ids": ["acc_abc123", "acc_def456"],
  "scheduled_at": "2025-06-01T09:00:00Z"
}`,
  },
  {
    name: 'list_posts',
    desc: 'List posts filtered by status.',
    params: [
      { name: 'status', type: 'enum', required: false, desc: 'all | draft | scheduled | published | failed' },
      { name: 'limit', type: 'number', required: false, desc: 'Max results (1–50, default 20)' },
    ],
    example: `{ "status": "failed" }`,
  },
  {
    name: 'get_post',
    desc: 'Get full details of a specific post — content, platform results, media, timestamps.',
    params: [
      { name: 'post_id', type: 'string', required: true, desc: 'Post ID to retrieve' },
    ],
    example: `{ "post_id": "post_xyz789" }`,
  },
  {
    name: 'delete_post',
    desc: 'Permanently delete a post. Works on drafts, scheduled, and published posts.',
    params: [
      { name: 'post_id', type: 'string', required: true, desc: 'Post ID to delete' },
    ],
    example: `{ "post_id": "post_xyz789" }`,
  },
  {
    name: 'retry_failed_post',
    desc: 'Retry a post that failed to publish on one or more platforms.',
    params: [
      { name: 'post_id', type: 'string', required: true, desc: 'ID of the failed post' },
    ],
    example: `{ "post_id": "post_xyz789" }`,
  },
  {
    name: 'generate_content',
    desc: 'Use AI to generate platform-optimized captions, tweets, or long-form content.',
    params: [
      { name: 'topic', type: 'string', required: true, desc: 'What the post is about' },
      { name: 'platform', type: 'enum', required: true, desc: 'instagram | twitter | linkedin | facebook | threads | tiktok | youtube | general' },
      { name: 'tone', type: 'enum', required: false, desc: 'professional | casual | excited | funny | inspirational | informative' },
      { name: 'count', type: 'number', required: false, desc: 'Variations to generate (1–5)' },
      { name: 'additional_context', type: 'string', required: false, desc: 'Brand info, hashtags, or extra instructions' },
    ],
    example: `{
  "topic": "Black Friday sale — 50% off everything",
  "platform": "instagram",
  "tone": "excited",
  "count": 3
}`,
  },
  {
    name: 'get_stats',
    desc: 'Fetch your dashboard stats — total posts, connected accounts, queue size, failed posts.',
    params: [],
    example: `// Returns
{
  "total_posts": 142,
  "connected_accounts": 5,
  "scheduled_posts": 8,
  "failed_posts": 1
}`,
  },
  {
    name: 'upload_media',
    desc: 'Upload an image or video from a public URL. Returns a media URL to attach to posts.',
    params: [
      { name: 'url', type: 'string (URL)', required: true, desc: 'Public URL of the image or video' },
      { name: 'filename', type: 'string', required: false, desc: 'Optional filename override' },
    ],
    example: `{
  "url": "https://example.com/banner.jpg"
}
// Returns: { "media_url": "https://cdn.socialentangler.com/..." }`,
  },
];

const examplePrompts = [
  { emoji: '✍️', prompt: '"Write 3 Instagram captions about our product launch with an excited tone, schedule the best one for Friday 9am"' },
  { emoji: '📊', prompt: '"How did my posts perform this week? Show me any failures and retry them"' },
  { emoji: '📅', prompt: '"What\'s in my publishing queue for this week?"' },
  { emoji: '🔄', prompt: '"Repost my latest LinkedIn article as a shorter Twitter thread"' },
  { emoji: '🚀', prompt: '"Post \'Big news tomorrow!\' to all my connected accounts right now"' },
  { emoji: '🗑️', prompt: '"Delete all my draft posts"' },
];

function CopyButton({ text, label = 'Copy' }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={copy}
      className="text-xs text-slate-500 hover:text-slate-700 transition-colors px-2 py-1 rounded border border-slate-300 hover:border-slate-400 bg-white"
    >
      {copied ? 'Copied!' : label}
    </button>
  );
}

function CodeBlock({ children, label }) {
  return (
    <div className="rounded-lg overflow-hidden border border-slate-200 mt-3">
      {label && (
        <div className="bg-slate-100 px-4 py-2 flex items-center justify-between border-b border-slate-200">
          <span className="text-xs text-slate-500 font-mono">{label}</span>
          <CopyButton text={children} />
        </div>
      )}
      <pre className="bg-slate-900 px-4 py-4 text-xs text-slate-300 font-mono overflow-x-auto leading-relaxed whitespace-pre">{children}</pre>
    </div>
  );
}

function StepBadge({ n }) {
  return (
    <span className="w-7 h-7 rounded-full bg-indigo-50 text-indigo-600 text-xs font-bold flex items-center justify-center border border-indigo-200 flex-shrink-0">
      {n}
    </span>
  );
}

// ── Inline API Key Panel ──────────────────────────────────────────────────────

function ApiKeyPanel({ navigate }) {
  const [keys, setKeys] = useState(null);
  const [generatedKey, setGeneratedKey] = useState(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    getApiKeys()
      .then(data => setKeys(Array.isArray(data) ? data : data.keys || []))
      .catch(() => setKeys([]))
      .finally(() => setLoading(false));
  }, []);

  const handleGenerate = async () => {
    setCreating(true);
    setError(null);
    try {
      const result = await createApiKey({ name: 'MCP Key' });
      setGeneratedKey(result.raw_key || result.key || result.api_key || result.value);
      setKeys(prev => [...(prev || []), result]);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Failed to create API key');
    } finally {
      setCreating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-3 text-sm text-slate-400">
        <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
        </svg>
        Loading your keys...
      </div>
    );
  }

  // New key was just generated — show it
  if (generatedKey) {
    return (
      <div className="border border-green-200 bg-green-50 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-green-600 text-lg">✓</span>
          <p className="text-sm font-semibold text-green-800">API key created</p>
        </div>
        <p className="text-xs text-green-700 mb-3">
          Copy this key now — it won't be shown again.
        </p>
        <div className="flex items-center gap-2 bg-white border border-green-300 rounded-lg px-3 py-2">
          <code className="text-xs font-mono text-slate-700 flex-1 break-all">{generatedKey}</code>
          <CopyButton text={generatedKey} label="Copy key" />
        </div>
        <p className="text-xs text-slate-500 mt-3">
          Use this as your <code className="font-mono bg-slate-100 px-1 rounded">SOCIALENTANGLER_API_KEY</code> in Step 3 below.
        </p>
      </div>
    );
  }

  // Already has keys
  if (keys && keys.length > 0) {
    return (
      <div className="border border-slate-200 bg-slate-50 rounded-xl p-5">
        <p className="text-sm font-semibold text-slate-700 mb-3">Your API keys</p>
        <div className="space-y-2 mb-4">
          {keys.map((k, i) => (
            <div key={k.id || i} className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-green-400 flex-shrink-0"></span>
                <span className="text-slate-700 font-medium">{k.name || 'API Key'}</span>
              </div>
              <span className="text-xs text-slate-400 font-mono">{k.key_preview || k.prefix || '••••••••'}</span>
            </div>
          ))}
        </div>
        <button
          onClick={() => navigate('/api-keys')}
          className="text-xs text-indigo-600 hover:text-indigo-500 font-medium underline underline-offset-2"
        >
          Manage API keys →
        </button>
        <p className="text-xs text-slate-500 mt-3">
          Use your key as <code className="font-mono bg-white border border-slate-200 px-1 rounded">SOCIALENTANGLER_API_KEY</code> in Step 3 below.
        </p>
      </div>
    );
  }

  // No keys yet
  return (
    <div className="border border-dashed border-slate-300 rounded-xl p-5">
      <p className="text-sm text-slate-600 mb-4">You don't have any API keys yet. Generate one to use with the MCP server.</p>
      {error && <p className="text-xs text-red-500 mb-3">{error}</p>}
      <button
        onClick={handleGenerate}
        disabled={creating}
        className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-60 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
      >
        {creating ? (
          <>
            <svg className="animate-spin w-3.5 h-3.5" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
            Generating...
          </>
        ) : 'Generate API Key'}
      </button>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function McpDocs() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('claude-desktop');

  const claudeConfig = JSON.stringify({
    mcpServers: {
      socialentangler: {
        command: 'node',
        args: ['/path/to/socialentangler-mcp/index.js'],
        env: {
          SOCIALENTANGLER_API_KEY: 'your_api_key_here',
          SOCIALENTANGLER_BASE_URL: BACKEND_URL,
        },
      },
    },
  }, null, 2);

  const npxConfig = JSON.stringify({
    mcpServers: {
      socialentangler: {
        command: 'npx',
        args: ['socialentangler-mcp'],
        env: {
          SOCIALENTANGLER_API_KEY: 'your_api_key_here',
          SOCIALENTANGLER_BASE_URL: BACKEND_URL,
        },
      },
    },
  }, null, 2);

  const tabs = [
    { id: 'claude-desktop', label: 'Claude Desktop' },
    { id: 'cursor', label: 'Cursor' },
    { id: 'manual', label: 'Manual / CLI' },
  ];

  return (
    <div className="min-h-screen bg-white text-slate-900">

      {/* Nav */}
      <nav className="border-b border-slate-200 sticky top-0 bg-white/90 backdrop-blur z-10">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
          <button onClick={() => navigate('/')} className="text-sm font-semibold text-slate-900 tracking-tight">
            SocialEntangler
          </button>
          <div className="flex items-center gap-4">
            <span className="text-xs text-slate-400 font-mono hidden sm:block">MCP Server v1.0</span>
            {user ? (
              <button
                onClick={() => navigate('/api-keys')}
                className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-md transition-colors font-medium"
              >
                Manage API Keys →
              </button>
            ) : (
              <button
                onClick={() => navigate('/login', { state: { returnTo: '/mcp' } })}
                className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-md transition-colors font-medium"
              >
                Sign in →
              </button>
            )}
          </div>
        </div>
      </nav>

      <div className="max-w-5xl mx-auto px-6 py-16">

        {/* Hero */}
        <div className="mb-20">
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-indigo-50 text-indigo-600 border border-indigo-100 rounded-full text-xs font-medium mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse"></span>
            Model Context Protocol
          </div>
          <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-slate-900 mb-5 leading-tight">
            Control social media<br />from any AI agent
          </h1>
          <p className="text-lg text-slate-500 max-w-2xl leading-relaxed mb-8">
            The SocialEntangler MCP server gives AI assistants like Claude direct access
            to your social accounts — create posts, schedule content, generate captions,
            and check analytics without leaving your conversation.
          </p>
          <div className="flex flex-wrap gap-2">
            {['Claude Desktop', 'Cursor', 'Any MCP Client', '9 tools', '11+ platforms'].map(tag => (
              <span key={tag} className="px-3 py-1 bg-slate-100 text-slate-600 rounded-full text-sm">{tag}</span>
            ))}
          </div>
        </div>

        {/* What you can ask */}
        <section className="mb-20">
          <h2 className="text-xl font-semibold text-slate-900 mb-2">What you can ask</h2>
          <p className="text-slate-500 text-sm mb-6">Once connected, just talk to your AI assistant naturally.</p>
          <div className="grid md:grid-cols-2 gap-3">
            {examplePrompts.map(({ emoji, prompt }, i) => (
              <div key={i} className="flex items-start gap-3 p-4 bg-slate-50 border border-slate-200 rounded-xl">
                <span className="text-lg mt-0.5">{emoji}</span>
                <p className="text-sm text-slate-600 leading-relaxed italic">{prompt}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Setup */}
        <section className="mb-20">
          <h2 className="text-xl font-semibold text-slate-900 mb-2">Setup</h2>
          <p className="text-slate-500 text-sm mb-8">Three steps to connect SocialEntangler to your AI client.</p>

          {/* Step 1 */}
          <div className="mb-10">
            <div className="flex items-center gap-3 mb-4">
              <StepBadge n={1} />
              <h3 className="text-base font-semibold text-slate-900">Get your API key</h3>
            </div>
            <div className="ml-10">
              {user ? (
                <ApiKeyPanel navigate={navigate} />
              ) : (
                <>
                  <p className="text-slate-500 text-sm mb-4">
                    Sign in to SocialEntangler and generate an API key — you can do it right here without navigating away.
                  </p>
                  <button
                    onClick={() => navigate('/login', { state: { returnTo: '/mcp' } })}
                    className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium px-4 py-2.5 rounded-lg transition-colors"
                  >
                    Sign in to get your API key →
                  </button>
                  <p className="text-xs text-slate-400 mt-3">
                    No account?{' '}
                    <button
                      onClick={() => navigate('/signup', { state: { returnTo: '/mcp' } })}
                      className="text-indigo-600 hover:text-indigo-500 underline underline-offset-2"
                    >
                      Create one free →
                    </button>
                  </p>
                </>
              )}
            </div>
          </div>

          {/* Step 2 */}
          <div className="mb-10">
            <div className="flex items-center gap-3 mb-4">
              <StepBadge n={2} />
              <h3 className="text-base font-semibold text-slate-900">Install the MCP server</h3>
            </div>
            <div className="ml-10">
              <p className="text-slate-500 text-sm mb-3">Clone and install dependencies:</p>
              <CodeBlock label="terminal">{`git clone https://github.com/socialentangler/mcp-server
cd mcp-server
npm install`}</CodeBlock>
            </div>
          </div>

          {/* Step 3 */}
          <div className="mb-10">
            <div className="flex items-center gap-3 mb-4">
              <StepBadge n={3} />
              <h3 className="text-base font-semibold text-slate-900">Configure your AI client</h3>
            </div>
            <div className="ml-10">
              <div className="flex gap-1 mb-4 border-b border-slate-200">
                {tabs.map(t => (
                  <button
                    key={t.id}
                    onClick={() => setActiveTab(t.id)}
                    className={`px-4 py-2 text-sm transition-colors border-b-2 -mb-px ${
                      activeTab === t.id
                        ? 'border-indigo-500 text-indigo-600 font-medium'
                        : 'border-transparent text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {activeTab === 'claude-desktop' && (
                <div>
                  <p className="text-slate-500 text-sm mb-3">
                    Edit <code className="text-slate-700 font-mono text-xs bg-slate-100 px-1.5 py-0.5 rounded">~/Library/Application Support/Claude/claude_desktop_config.json</code>:
                  </p>
                  <CodeBlock label="claude_desktop_config.json">{claudeConfig}</CodeBlock>
                  <p className="text-slate-400 text-xs mt-3">Restart Claude Desktop after saving.</p>
                </div>
              )}

              {activeTab === 'cursor' && (
                <div>
                  <p className="text-slate-500 text-sm mb-3">Open Cursor Settings → MCP → Add server:</p>
                  <CodeBlock label="cursor mcp config">{npxConfig}</CodeBlock>
                  <p className="text-slate-400 text-xs mt-3">Reload Cursor after saving.</p>
                </div>
              )}

              {activeTab === 'manual' && (
                <div>
                  <p className="text-slate-500 text-sm mb-3">Run directly with env vars:</p>
                  <CodeBlock label="terminal">{`SOCIALENTANGLER_API_KEY=your_key_here \\
SOCIALENTANGLER_BASE_URL=${BACKEND_URL} \\
node /path/to/socialentangler-mcp/index.js`}</CodeBlock>
                  <p className="text-slate-500 text-sm mt-4">
                    Uses stdio transport — point any MCP-compatible client to this process.
                  </p>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Tools Reference */}
        <section className="mb-20">
          <h2 className="text-xl font-semibold text-slate-900 mb-2">Tools reference</h2>
          <p className="text-slate-500 text-sm mb-8">9 tools available. Your AI assistant can call any of these during a conversation.</p>

          <div className="space-y-2">
            {tools.map((tool) => (
              <details key={tool.name} className="group border border-slate-200 rounded-xl overflow-hidden">
                <summary className="flex items-center justify-between px-5 py-4 cursor-pointer select-none hover:bg-slate-50 transition-colors list-none">
                  <div className="flex items-center gap-3">
                    <code className="text-sm text-indigo-600 font-mono font-semibold">{tool.name}</code>
                    <span className="text-slate-500 text-sm hidden sm:block">{tool.desc}</span>
                  </div>
                  <svg className="w-4 h-4 text-slate-400 group-open:rotate-180 transition-transform flex-shrink-0 ml-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </summary>
                <div className="px-5 pb-5 border-t border-slate-200 pt-4">
                  <p className="text-slate-500 text-sm mb-4 sm:hidden">{tool.desc}</p>

                  {tool.params.length > 0 && (
                    <div className="mb-4">
                      <p className="text-xs text-slate-400 uppercase tracking-wider font-medium mb-3">Parameters</p>
                      <div className="space-y-2">
                        {tool.params.map(p => (
                          <div key={p.name} className="flex flex-wrap items-baseline gap-2 text-sm">
                            <code className="text-amber-700 font-mono text-xs bg-amber-50 px-1 rounded">{p.name}</code>
                            <span className="text-slate-400 font-mono text-xs">{p.type}</span>
                            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${p.required ? 'bg-rose-50 text-rose-500' : 'bg-slate-100 text-slate-400'}`}>
                              {p.required ? 'required' : 'optional'}
                            </span>
                            <span className="text-slate-500 text-xs">{p.desc}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <p className="text-xs text-slate-400 uppercase tracking-wider font-medium mb-2">Example</p>
                  <CodeBlock>{tool.example}</CodeBlock>
                </div>
              </details>
            ))}
          </div>
        </section>

        {/* Supported Platforms */}
        <section className="mb-20">
          <h2 className="text-xl font-semibold text-slate-900 mb-2">Supported platforms</h2>
          <p className="text-slate-500 text-sm mb-6">Connect accounts in SocialEntangler, then reference them by ID in any tool.</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
            {['Instagram', 'Twitter / X', 'Facebook', 'LinkedIn', 'YouTube', 'TikTok', 'Threads', 'Reddit', 'Pinterest', 'Snapchat', 'Bluesky'].map(p => (
              <div key={p} className="px-4 py-3 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-600 text-center">
                {p}
              </div>
            ))}
          </div>
        </section>

        {/* Auth note */}
        <section className="mb-20">
          <h2 className="text-xl font-semibold text-slate-900 mb-2">Authentication</h2>
          <p className="text-slate-500 text-sm mb-4">
            The MCP server sends your SocialEntangler API key via the <code className="text-slate-700 font-mono text-xs bg-slate-100 px-1.5 py-0.5 rounded">X-API-Key</code> header on every request.
            Keys can be created and revoked any time from{' '}
            <button onClick={() => navigate('/api-keys')} className="text-indigo-600 hover:text-indigo-500 underline underline-offset-2">
              Settings → API Keys
            </button>.
          </p>
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
            <p className="text-amber-800 text-sm">
              <span className="font-semibold">Security:</span> Never share your API key or commit it to version control.
              Each key has full account access. Revoke compromised keys immediately from your dashboard.
            </p>
          </div>
        </section>

        {/* CTA */}
        {!user && (
          <section className="border border-slate-200 rounded-2xl p-10 text-center bg-slate-50">
            <h2 className="text-2xl font-semibold text-slate-900 mb-3">Ready to connect?</h2>
            <p className="text-slate-500 text-sm mb-6 max-w-md mx-auto">
              Sign in to get your API key, connect your social accounts, and start managing social media from your AI assistant.
            </p>
            <div className="flex flex-wrap gap-3 justify-center">
              <button
                onClick={() => navigate('/signup', { state: { returnTo: '/mcp' } })}
                className="bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-2.5 rounded-lg text-sm font-semibold transition-colors"
              >
                Create free account →
              </button>
              <button
                onClick={() => navigate('/login', { state: { returnTo: '/mcp' } })}
                className="bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 px-6 py-2.5 rounded-lg text-sm font-medium transition-colors"
              >
                Sign in
              </button>
            </div>
          </section>
        )}

      </div>

      {/* Footer */}
      <footer className="border-t border-slate-200 mt-20 py-8">
        <div className="max-w-5xl mx-auto px-6 flex flex-wrap items-center justify-between gap-4">
          <span className="text-sm text-slate-400">SocialEntangler MCP — Model Context Protocol server</span>
          <div className="flex gap-6">
            <button onClick={() => navigate('/terms')} className="text-xs text-slate-400 hover:text-slate-600 transition-colors">Terms</button>
            <button onClick={() => navigate('/privacy')} className="text-xs text-slate-400 hover:text-slate-600 transition-colors">Privacy</button>
            <button onClick={() => navigate('/')} className="text-xs text-slate-400 hover:text-slate-600 transition-colors">Home</button>
          </div>
        </div>
      </footer>
    </div>
  );
}
