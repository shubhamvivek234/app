import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { FaRobot, FaDownload, FaKey } from 'react-icons/fa';
import SocialEntanglerLogo from '@/components/SocialEntanglerLogo';

const METHOD_STYLES = {
  GET: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  POST: 'bg-blue-100 text-blue-700 border-blue-200',
  DELETE: 'bg-red-100 text-red-700 border-red-200',
};

const AgentDocs = () => {
  const navigate = useNavigate();
  const [copiedId, setCopiedId] = useState(null);

  const baseUrl = window.location.origin;

  const copy = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const endpoints = [
    {
      id: 'is-connected',
      method: 'GET',
      path: '/api/public/v1/is-connected',
      description: 'Check if your API key is valid and the account is properly connected.',
      body: null,
      response: `{ "connected": true, "user": "you@example.com" }`,
    },
    {
      id: 'integrations',
      method: 'GET',
      path: '/api/public/v1/integrations',
      description: 'List all social media channels connected to your SocialEntangler account.',
      body: null,
      response: `[
  {
    "id": "abc123",
    "name": "My Twitter Account",
    "platform": "twitter",
    "username": "@myhandle"
  }
]`,
    },
    {
      id: 'upload',
      method: 'POST',
      path: '/api/public/v1/upload',
      description: 'Upload an image or video file (multipart/form-data). Returns a URL you can pass to posts.',
      body: 'Multipart form-data — field name: file\nSupported types: JPEG, PNG, GIF, WebP, MP4',
      response: `{ "url": "https://your-domain.com/uploads/media_abc123.jpg" }`,
    },
    {
      id: 'posts-create',
      method: 'POST',
      path: '/api/public/v1/posts',
      description: 'Create and optionally schedule a post across one or more platforms.',
      body: `{
  "content": "Your post text here",
  "integrationIds": ["abc123", "def456"],
  "mediaUrls": ["https://..."],
  "scheduledAt": "2025-01-15T10:00:00Z"
}

Required: content, integrationIds
Optional: mediaUrls, scheduledAt`,
      response: `{ "id": "post_xyz789", "status": "scheduled" }`,
    },
    {
      id: 'posts-list',
      method: 'GET',
      path: '/api/public/v1/posts',
      description: 'List all posts created via the API for your account.',
      body: null,
      response: `[
  {
    "id": "post_xyz789",
    "content": "Your post text here",
    "status": "scheduled",
    "scheduledAt": "2025-01-15T10:00:00Z"
  }
]`,
    },
    {
      id: 'posts-delete',
      method: 'DELETE',
      path: '/api/public/v1/posts/{post_id}',
      description: 'Delete a post by its ID.',
      body: null,
      response: `{ "success": true }`,
    },
  ];

  const skillJson = {
    name: 'SocialEntangler',
    description: 'Manage social media posts across 11+ platforms via REST API',
    base_url: `${baseUrl}/api/public/v1`,
    auth: {
      type: 'bearer',
      header: 'Authorization',
      env: 'SOCIALENTANGLER_API_KEY',
    },
    tools: [
      {
        name: 'integrations:list',
        description: 'List all connected social media channels',
        endpoint: '/api/public/v1/integrations',
        method: 'GET',
      },
      {
        name: 'media:upload',
        description: 'Upload an image or video file — returns a URL to attach to posts',
        endpoint: '/api/public/v1/upload',
        method: 'POST',
        content_type: 'multipart/form-data',
        parameters: { file: 'FormFile' },
      },
      {
        name: 'posts:create',
        description: 'Create and optionally schedule a post across platforms',
        endpoint: '/api/public/v1/posts',
        method: 'POST',
        body: {
          content: 'string (required)',
          integrationIds: 'string[] (required)',
          mediaUrls: 'string[] (optional)',
          scheduledAt: 'ISO-8601 string (optional)',
        },
      },
      {
        name: 'posts:list',
        description: 'List all posts created via the API',
        endpoint: '/api/public/v1/posts',
        method: 'GET',
      },
      {
        name: 'posts:delete',
        description: 'Delete a post by its ID',
        endpoint: '/api/public/v1/posts/{post_id}',
        method: 'DELETE',
      },
    ],
  };

  const buildCurl = (ep) => {
    const url = `${baseUrl}${ep.path.replace('{post_id}', 'YOUR_POST_ID')}`;
    const auth = `-H "Authorization: Bearer $SOCIALENTANGLER_API_KEY"`;
    if (ep.id === 'upload') {
      return `curl -X POST ${auth} \\\n  -F "file=@photo.jpg" \\\n  "${url}"`;
    }
    if (ep.id === 'posts-create') {
      return `curl -X POST ${auth} \\\n  -H "Content-Type: application/json" \\\n  -d '{"content":"Hello!","integrationIds":["abc123"]}' \\\n  "${url}"`;
    }
    const method = ep.method !== 'GET' ? `-X ${ep.method} ` : '';
    return `curl ${method}${auth} \\\n  "${url}"`;
  };

  return (
    <div className="min-h-screen bg-offwhite">
      {/* Header */}
      <nav className="bg-offwhite border-b border-gray-100 py-4 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex justify-between items-center">
          <div className="cursor-pointer" onClick={() => navigate('/')}>
            <SocialEntanglerLogo />
          </div>
          <div className="flex gap-3 items-center">
            <Button variant="ghost" className="text-gray-600 text-sm" onClick={() => navigate('/')}>
              ← Back to Home
            </Button>
            <Button onClick={() => navigate('/api-keys')} className="bg-indigo-600 hover:bg-indigo-700">
              <FaKey className="mr-2 text-xs" /> Get API Key
            </Button>
          </div>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 py-12 space-y-14">
        {/* Hero */}
        <div className="space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-indigo-50 text-indigo-700 rounded-full text-xs font-semibold uppercase tracking-wider">
            <FaRobot /> REST API for AI Agents
          </div>
          <h1 className="text-4xl font-bold text-slate-900 tracking-tight">
            SocialEntangler API Reference
          </h1>
          <p className="text-lg text-slate-600 leading-relaxed max-w-2xl">
            A production-ready REST API for AI agents to post, schedule, and manage social media across 11+ platforms. Compatible with LangChain, AutoGPT, OpenClaw, and any HTTP client.
          </p>
          <div className="inline-flex items-center gap-2 bg-slate-100 rounded-lg px-4 py-2">
            <span className="text-xs text-slate-500 font-medium uppercase tracking-wide">Base URL</span>
            <code className="font-mono text-sm text-slate-800 font-semibold">{baseUrl}/api/public/v1/</code>
          </div>
        </div>

        {/* Step 1: Auth */}
        <section className="space-y-5">
          <h2 className="text-2xl font-semibold text-slate-900 flex items-center gap-3">
            <span className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-900 text-white text-sm font-bold shrink-0">1</span>
            Authentication
          </h2>
          <div className="bg-offwhite rounded-xl p-6 border border-slate-200 space-y-4">
            <p className="text-slate-700">
              All requests require a Bearer token in the{' '}
              <code className="bg-slate-100 px-1.5 py-0.5 rounded text-sm font-mono text-slate-800">Authorization</code>{' '}
              header. Generate your key from the dashboard.
            </p>
            <div className="bg-slate-900 rounded-lg p-4 font-mono text-sm text-indigo-300">
              Authorization: Bearer {'<YOUR_API_KEY>'}
            </div>
            <Button onClick={() => navigate('/api-keys')} className="bg-indigo-600 hover:bg-indigo-700">
              <FaKey className="mr-2 text-xs" /> Go to API Keys
            </Button>
          </div>
        </section>

        {/* Step 2: Env Setup */}
        <section className="space-y-5">
          <h2 className="text-2xl font-semibold text-slate-900 flex items-center gap-3">
            <span className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-900 text-white text-sm font-bold shrink-0">2</span>
            Environment Setup
          </h2>
          <p className="text-slate-600">
            Export these variables in your agent's runtime environment:
          </p>
          <div className="relative group">
            <pre className="bg-slate-900 text-indigo-300 p-5 rounded-xl font-mono text-sm overflow-x-auto shadow-lg border border-slate-800">
              <code>{`export SOCIALENTANGLER_API_KEY="your_api_key_here"\nexport SOCIALENTANGLER_BASE_URL="${baseUrl}"`}</code>
            </pre>
            <button
              onClick={() => copy(`export SOCIALENTANGLER_API_KEY="your_api_key_here"\nexport SOCIALENTANGLER_BASE_URL="${baseUrl}"`, 'env')}
              className="absolute top-3 right-3 text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 px-2 py-1 rounded transition-colors opacity-0 group-hover:opacity-100"
            >
              {copiedId === 'env' ? '✓ Copied' : 'Copy'}
            </button>
          </div>
        </section>

        {/* Step 3: API Reference */}
        <section className="space-y-6">
          <h2 className="text-2xl font-semibold text-slate-900 flex items-center gap-3">
            <span className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-900 text-white text-sm font-bold shrink-0">3</span>
            API Reference
          </h2>

          <div className="space-y-4">
            {endpoints.map((ep) => (
              <div key={ep.id} className="border border-slate-200 rounded-xl overflow-hidden">
                {/* Endpoint Header */}
                <div className="bg-slate-50 px-5 py-4 flex items-start gap-3 border-b border-slate-200">
                  <span className={`shrink-0 text-xs font-bold px-2.5 py-1 rounded border ${METHOD_STYLES[ep.method]}`}>
                    {ep.method}
                  </span>
                  <div className="flex-1 min-w-0">
                    <code className="font-mono text-sm text-slate-800 break-all">{ep.path}</code>
                    <p className="text-sm text-slate-500 mt-1">{ep.description}</p>
                  </div>
                </div>

                {/* Endpoint Body */}
                <div className="p-5 space-y-5 bg-offwhite">
                  {/* Request Body */}
                  {ep.body && (
                    <div>
                      <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-2">Request Body</p>
                      <pre className="bg-slate-50 border border-slate-100 rounded-lg p-4 text-xs font-mono text-slate-700 overflow-x-auto whitespace-pre-wrap leading-relaxed">
                        {ep.body}
                      </pre>
                    </div>
                  )}

                  {/* Response */}
                  <div>
                    <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-2">Response</p>
                    <pre className="bg-slate-50 border border-slate-100 rounded-lg p-4 text-xs font-mono text-slate-700 overflow-x-auto whitespace-pre leading-relaxed">
                      {ep.response}
                    </pre>
                  </div>

                  {/* cURL */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest">cURL Example</p>
                      <button
                        onClick={() => copy(buildCurl(ep), ep.id)}
                        className="text-xs text-indigo-600 hover:text-indigo-800 font-medium transition-colors"
                      >
                        {copiedId === ep.id ? '✓ Copied' : 'Copy'}
                      </button>
                    </div>
                    <pre className="bg-slate-900 rounded-lg p-4 text-xs font-mono text-slate-300 overflow-x-auto whitespace-pre leading-relaxed">
                      {buildCurl(ep)}
                    </pre>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Step 4: Skill Manifest */}
        <section className="space-y-5">
          <h2 className="text-2xl font-semibold text-slate-900 flex items-center gap-3">
            <span className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-900 text-white text-sm font-bold shrink-0">4</span>
            Agent Skill Manifest
          </h2>
          <p className="text-slate-600 leading-relaxed">
            For OpenClaw, LangChain tool-use, or any skill-based agent, register SocialEntangler using this JSON manifest:
          </p>
          <div className="bg-offwhite border border-slate-200 rounded-xl overflow-hidden shadow-sm">
            <div className="bg-slate-50 px-4 py-3 border-b border-slate-200 flex justify-between items-center">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-widest font-mono">skill.json</span>
              <button
                onClick={() => copy(JSON.stringify(skillJson, null, 2), 'skill-json')}
                className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center gap-1.5 font-medium"
              >
                <FaDownload className="text-xs" />
                {copiedId === 'skill-json' ? '✓ Copied!' : 'Copy JSON'}
              </button>
            </div>
            <pre className="p-5 text-sm text-slate-800 font-mono overflow-auto max-h-96 bg-offwhite leading-relaxed">
              {JSON.stringify(skillJson, null, 2)}
            </pre>
          </div>
        </section>

        {/* CTA */}
        <section className="py-4 border-t border-slate-100">
          <div className="bg-indigo-600 rounded-2xl p-8 text-center text-white shadow-xl shadow-indigo-100">
            <h3 className="text-xl font-bold mb-2">Need help with integration?</h3>
            <p className="text-indigo-100 mb-6 max-w-md mx-auto leading-relaxed">
              Our team is ready to help with custom agent configurations or advanced automation workflows.
            </p>
            <div className="flex gap-3 justify-center flex-wrap">
              <Button
                className="bg-offwhite text-indigo-600 hover:bg-slate-100 px-6 font-semibold"
                onClick={() => navigate('/api-keys')}
              >
                Get API Key
              </Button>
              <Button
                variant="outline"
                className="border-white/40 text-white hover:bg-white/10 px-6"
                onClick={() => navigate('/support')}
              >
                Contact Support
              </Button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default AgentDocs;
