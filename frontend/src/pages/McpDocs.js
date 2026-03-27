import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

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
    desc: 'Create a post — publish immediately, schedule for later, or save as draft. Attach media with upload_media first.',
    params: [
      { name: 'content', type: 'string', required: true, desc: 'Text content of the post' },
      { name: 'account_ids', type: 'string[]', required: true, desc: 'Account IDs from list_connected_accounts' },
      { name: 'scheduled_at', type: 'ISO 8601', required: false, desc: 'Schedule time e.g. "2025-06-01T09:00:00Z"' },
      { name: 'publish_now', type: 'boolean', required: false, desc: 'Set true to publish immediately' },
      { name: 'media_urls', type: 'string[]', required: false, desc: 'Media URLs from upload_media' },
    ],
    example: `// Schedule a post to Instagram + Twitter
{
  "content": "Big news dropping tomorrow 🚀",
  "account_ids": ["acc_abc123", "acc_def456"],
  "scheduled_at": "2025-06-01T09:00:00Z"
}`,
  },
  {
    name: 'list_posts',
    desc: 'List posts filtered by status. Use this to audit your queue or find failed posts.',
    params: [
      { name: 'status', type: 'enum', required: false, desc: 'all | draft | scheduled | published | failed' },
      { name: 'limit', type: 'number', required: false, desc: 'Max results (1–50, default 20)' },
    ],
    example: `// List failed posts
{ "status": "failed" }

// List next 10 scheduled posts
{ "status": "scheduled", "limit": 10 }`,
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
    desc: 'Use AI to generate platform-optimized captions, tweets, or long-form content. Specify tone and get multiple variations.',
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
  "count": 3,
  "additional_context": "Include #BlackFriday and a countdown feel"
}`,
  },
  {
    name: 'get_stats',
    desc: 'Fetch your dashboard stats — total posts, connected accounts, scheduled queue size, failed posts.',
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
  "url": "https://example.com/banner.jpg",
  "filename": "launch-banner.jpg"
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

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={copy}
      className="text-xs text-slate-400 hover:text-slate-200 transition-colors px-2 py-1 rounded border border-slate-700 hover:border-slate-500"
    >
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

function CodeBlock({ children, label }) {
  return (
    <div className="rounded-lg overflow-hidden border border-slate-800 mt-3">
      {label && (
        <div className="bg-slate-800/60 px-4 py-2 flex items-center justify-between border-b border-slate-800">
          <span className="text-xs text-slate-400 font-mono">{label}</span>
          <CopyButton text={children} />
        </div>
      )}
      <pre className="bg-slate-900 px-4 py-4 text-xs text-slate-300 font-mono overflow-x-auto leading-relaxed whitespace-pre">{children}</pre>
    </div>
  );
}

export default function McpDocs() {
  const navigate = useNavigate();
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
    <div className="min-h-screen bg-slate-950 text-slate-100">

      {/* Nav */}
      <nav className="border-b border-slate-800/60 sticky top-0 bg-slate-950/90 backdrop-blur z-10">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
          <button onClick={() => navigate('/')} className="text-sm font-semibold text-white tracking-tight">
            SocialEntangler
          </button>
          <div className="flex items-center gap-4">
            <span className="text-xs text-slate-500 font-mono">MCP Server v1.0</span>
            <button
              onClick={() => navigate('/login')}
              className="text-xs bg-indigo-500 hover:bg-indigo-400 text-white px-3 py-1.5 rounded-md transition-colors font-medium"
            >
              Get API Key →
            </button>
          </div>
        </div>
      </nav>

      <div className="max-w-5xl mx-auto px-6 py-16">

        {/* Hero */}
        <div className="mb-20">
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-full text-xs font-medium mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse"></span>
            Model Context Protocol
          </div>
          <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-white mb-5 leading-tight">
            Control social media<br />from any AI agent
          </h1>
          <p className="text-lg text-slate-400 max-w-2xl leading-relaxed mb-8">
            The SocialEntangler MCP server gives AI assistants like Claude direct access
            to your social accounts — create posts, schedule content, generate captions,
            and check analytics without leaving your conversation.
          </p>
          <div className="flex flex-wrap gap-3">
            <span className="px-3 py-1 bg-slate-800 text-slate-300 rounded-full text-sm">Claude Desktop</span>
            <span className="px-3 py-1 bg-slate-800 text-slate-300 rounded-full text-sm">Cursor</span>
            <span className="px-3 py-1 bg-slate-800 text-slate-300 rounded-full text-sm">Any MCP Client</span>
            <span className="px-3 py-1 bg-slate-800 text-slate-300 rounded-full text-sm">9 tools</span>
            <span className="px-3 py-1 bg-slate-800 text-slate-300 rounded-full text-sm">11+ platforms</span>
          </div>
        </div>

        {/* What you can ask */}
        <section className="mb-20">
          <h2 className="text-xl font-semibold text-white mb-2">What you can ask</h2>
          <p className="text-slate-400 text-sm mb-6">Once connected, just talk to your AI assistant naturally.</p>
          <div className="grid md:grid-cols-2 gap-3">
            {examplePrompts.map(({ emoji, prompt }, i) => (
              <div key={i} className="flex items-start gap-3 p-4 bg-slate-900 border border-slate-800 rounded-xl">
                <span className="text-lg mt-0.5">{emoji}</span>
                <p className="text-sm text-slate-300 leading-relaxed italic">{prompt}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Setup */}
        <section className="mb-20">
          <h2 className="text-xl font-semibold text-white mb-2">Setup</h2>
          <p className="text-slate-400 text-sm mb-8">Three steps to connect SocialEntangler to your AI client.</p>

          {/* Step 1 */}
          <div className="mb-10">
            <div className="flex items-center gap-3 mb-4">
              <span className="w-7 h-7 rounded-full bg-indigo-500/20 text-indigo-400 text-xs font-bold flex items-center justify-center border border-indigo-500/30">1</span>
              <h3 className="text-base font-semibold text-white">Get your API key</h3>
            </div>
            <p className="text-slate-400 text-sm mb-3 ml-10">
              Sign in to SocialEntangler, go to <span className="text-slate-200 font-medium">Settings → API Keys</span>, and create a new key.
              Keep it safe — it grants full access to your account.
            </p>
            <div className="ml-10">
              <button
                onClick={() => navigate('/login')}
                className="text-sm text-indigo-400 hover:text-indigo-300 underline underline-offset-2 transition-colors"
              >
                Open Settings → API Keys →
              </button>
            </div>
          </div>

          {/* Step 2 */}
          <div className="mb-10">
            <div className="flex items-center gap-3 mb-4">
              <span className="w-7 h-7 rounded-full bg-indigo-500/20 text-indigo-400 text-xs font-bold flex items-center justify-center border border-indigo-500/30">2</span>
              <h3 className="text-base font-semibold text-white">Install the MCP server</h3>
            </div>
            <div className="ml-10">
              <p className="text-slate-400 text-sm mb-3">Clone and install dependencies:</p>
              <CodeBlock label="terminal">{`git clone https://github.com/socialentangler/mcp-server
cd mcp-server
npm install`}</CodeBlock>
              <p className="text-slate-400 text-sm mt-4 mb-3">Or install globally via npm (coming soon):</p>
              <CodeBlock label="terminal">{`npm install -g socialentangler-mcp`}</CodeBlock>
            </div>
          </div>

          {/* Step 3 */}
          <div className="mb-10">
            <div className="flex items-center gap-3 mb-4">
              <span className="w-7 h-7 rounded-full bg-indigo-500/20 text-indigo-400 text-xs font-bold flex items-center justify-center border border-indigo-500/30">3</span>
              <h3 className="text-base font-semibold text-white">Configure your AI client</h3>
            </div>
            <div className="ml-10">
              {/* Tabs */}
              <div className="flex gap-1 mb-4 border-b border-slate-800">
                {tabs.map(t => (
                  <button
                    key={t.id}
                    onClick={() => setActiveTab(t.id)}
                    className={`px-4 py-2 text-sm transition-colors border-b-2 -mb-px ${
                      activeTab === t.id
                        ? 'border-indigo-400 text-white font-medium'
                        : 'border-transparent text-slate-400 hover:text-slate-300'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {activeTab === 'claude-desktop' && (
                <div>
                  <p className="text-slate-400 text-sm mb-3">
                    Edit <span className="text-slate-200 font-mono text-xs">~/Library/Application Support/Claude/claude_desktop_config.json</span>:
                  </p>
                  <CodeBlock label="claude_desktop_config.json">{claudeConfig}</CodeBlock>
                  <p className="text-slate-500 text-xs mt-3">Restart Claude Desktop after saving.</p>
                </div>
              )}

              {activeTab === 'cursor' && (
                <div>
                  <p className="text-slate-400 text-sm mb-3">
                    Open Cursor Settings → MCP → Add new server, then paste:
                  </p>
                  <CodeBlock label="cursor mcp config">{npxConfig}</CodeBlock>
                  <p className="text-slate-500 text-xs mt-3">Reload Cursor after saving.</p>
                </div>
              )}

              {activeTab === 'manual' && (
                <div>
                  <p className="text-slate-400 text-sm mb-3">Run the server directly with env vars:</p>
                  <CodeBlock label="terminal">{`SOCIALENTANGLER_API_KEY=your_key_here \\
SOCIALENTANGLER_BASE_URL=${BACKEND_URL} \\
node /path/to/socialentangler-mcp/index.js`}</CodeBlock>
                  <p className="text-slate-400 text-sm mt-4 mb-3">
                    The server communicates via <span className="text-slate-200">stdio</span> (standard MCP transport).
                    Point any MCP-compatible client to this process.
                  </p>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Tools Reference */}
        <section className="mb-20">
          <h2 className="text-xl font-semibold text-white mb-2">Tools reference</h2>
          <p className="text-slate-400 text-sm mb-8">9 tools available. Your AI assistant can call any of these during a conversation.</p>

          <div className="space-y-4">
            {tools.map((tool) => (
              <details key={tool.name} className="group border border-slate-800 rounded-xl overflow-hidden">
                <summary className="flex items-center justify-between px-5 py-4 cursor-pointer select-none hover:bg-slate-900/50 transition-colors list-none">
                  <div className="flex items-center gap-3">
                    <code className="text-sm text-indigo-300 font-mono font-semibold">{tool.name}</code>
                    <span className="text-slate-400 text-sm hidden sm:block">{tool.desc}</span>
                  </div>
                  <svg className="w-4 h-4 text-slate-500 group-open:rotate-180 transition-transform flex-shrink-0 ml-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </summary>
                <div className="px-5 pb-5 border-t border-slate-800 pt-4">
                  <p className="text-slate-400 text-sm mb-4 sm:hidden">{tool.desc}</p>

                  {tool.params.length > 0 && (
                    <div className="mb-4">
                      <p className="text-xs text-slate-500 uppercase tracking-wider font-medium mb-3">Parameters</p>
                      <div className="space-y-2">
                        {tool.params.map(p => (
                          <div key={p.name} className="flex flex-wrap items-baseline gap-2 text-sm">
                            <code className="text-yellow-300/80 font-mono text-xs">{p.name}</code>
                            <span className="text-slate-600 font-mono text-xs">{p.type}</span>
                            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${p.required ? 'bg-rose-500/10 text-rose-400' : 'bg-slate-700/50 text-slate-400'}`}>
                              {p.required ? 'required' : 'optional'}
                            </span>
                            <span className="text-slate-400 text-xs">{p.desc}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <p className="text-xs text-slate-500 uppercase tracking-wider font-medium mb-2">Example</p>
                  <CodeBlock>{tool.example}</CodeBlock>
                </div>
              </details>
            ))}
          </div>
        </section>

        {/* Supported Platforms */}
        <section className="mb-20">
          <h2 className="text-xl font-semibold text-white mb-2">Supported platforms</h2>
          <p className="text-slate-400 text-sm mb-6">Connect accounts in SocialEntangler, then reference them by ID in any tool.</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {['Instagram', 'Twitter / X', 'Facebook', 'LinkedIn', 'YouTube', 'TikTok', 'Threads', 'Reddit', 'Pinterest', 'Snapchat', 'Bluesky'].map(p => (
              <div key={p} className="px-4 py-3 bg-slate-900 border border-slate-800 rounded-lg text-sm text-slate-300 text-center">
                {p}
              </div>
            ))}
          </div>
        </section>

        {/* Auth note */}
        <section className="mb-20">
          <h2 className="text-xl font-semibold text-white mb-2">Authentication</h2>
          <p className="text-slate-400 text-sm mb-4">
            The MCP server uses your SocialEntangler API key as a Bearer token on every request.
            Keys can be created and revoked any time from Settings → API Keys.
          </p>
          <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-4">
            <p className="text-amber-300/80 text-sm">
              <span className="font-semibold">Security:</span> Never share your API key or commit it to version control.
              Each key has full account access. Revoke compromised keys immediately from your dashboard.
            </p>
          </div>
        </section>

        {/* CTA */}
        <section className="border border-slate-800 rounded-2xl p-10 text-center bg-slate-900/30">
          <h2 className="text-2xl font-semibold text-white mb-3">Ready to connect?</h2>
          <p className="text-slate-400 text-sm mb-6 max-w-md mx-auto">
            Sign in to get your API key, connect your social accounts, and start managing social media from your AI assistant.
          </p>
          <div className="flex flex-wrap gap-3 justify-center">
            <button
              onClick={() => navigate('/signup')}
              className="bg-indigo-500 hover:bg-indigo-400 text-white px-6 py-2.5 rounded-lg text-sm font-semibold transition-colors"
            >
              Create free account →
            </button>
            <button
              onClick={() => navigate('/login')}
              className="bg-slate-800 hover:bg-slate-700 text-white px-6 py-2.5 rounded-lg text-sm font-medium transition-colors"
            >
              Sign in
            </button>
          </div>
        </section>

      </div>

      {/* Footer */}
      <footer className="border-t border-slate-800/60 mt-20 py-8">
        <div className="max-w-5xl mx-auto px-6 flex flex-wrap items-center justify-between gap-4">
          <span className="text-sm text-slate-500">SocialEntangler MCP — Model Context Protocol server</span>
          <div className="flex gap-6">
            <button onClick={() => navigate('/terms')} className="text-xs text-slate-500 hover:text-slate-400 transition-colors">Terms</button>
            <button onClick={() => navigate('/privacy')} className="text-xs text-slate-500 hover:text-slate-400 transition-colors">Privacy</button>
            <button onClick={() => navigate('/')} className="text-xs text-slate-500 hover:text-slate-400 transition-colors">Home</button>
          </div>
        </div>
      </footer>
    </div>
  );
}
