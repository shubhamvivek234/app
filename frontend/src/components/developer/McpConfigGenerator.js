import React, { useState } from 'react';
import { FaCopy, FaCheck, FaRobot, FaTerminal, FaCode, FaLaptopCode } from 'react-icons/fa6';
import { SiClaude } from 'react-icons/si';

const CLIENTS = [
  {
    id: 'cursor',
    name: 'Cursor',
    icon: FaCode,
    file: '~/.cursor/mcp.json or project .cursor/mcp.json',
    format: 'json',
  },
  {
    id: 'claude_desktop',
    name: 'Claude Desktop',
    icon: SiClaude,
    file: 'claude_desktop_config.json',
    format: 'json',
  },
  {
    id: 'claude_code',
    name: 'Claude Code CLI',
    icon: FaTerminal,
    file: 'Run directly in your terminal',
    format: 'bash',
  },
  {
    id: 'remote_http',
    name: 'Remote HTTP / ChatGPT',
    icon: FaRobot,
    file: 'Direct SSE / Streamable HTTP endpoint',
    format: 'json',
  },
];

export default function McpConfigGenerator({ availableTokens = [], backendUrl }) {
  const [selectedClient, setSelectedClient] = useState('cursor');
  const [selectedToken, setSelectedToken] = useState(
    availableTokens[0]?.key_prefix ? `${availableTokens[0].key_prefix}...` : 'YOUR_UNRAVLER_TOKEN'
  );
  const [copied, setCopied] = useState(false);

  const mcpHttpUrl = `${backendUrl || 'https://api.unravler.com'}/mcp`;

  const generateSnippet = () => {
    const tokenPlaceholder = selectedToken || 'YOUR_UNRAVLER_TOKEN';
    const mcpUrlWithKey = `${backendUrl || 'https://api.unravler.com'}/mcp/${tokenPlaceholder}`;

    switch (selectedClient) {
      case 'cursor':
        return JSON.stringify(
          {
            mcpServers: {
              unravler: {
                url: mcpUrlWithKey,
              },
            },
          },
          null,
          2
        );

      case 'claude_desktop':
        return JSON.stringify(
          {
            mcpServers: {
              unravler: {
                url: mcpUrlWithKey,
              },
            },
          },
          null,
          2
        );

      case 'claude_code':
        return `claude mcp add unravler --transport http --url "${mcpUrlWithKey}"`;

      case 'remote_http':
        return JSON.stringify(
          {
            endpoint: mcpUrlWithKey,
            transport: 'streamable-http',
            headers: {
              'Content-Type': 'application/json',
            },
          },
          null,
          2
        );

      default:
        return '';
    }
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(generateSnippet());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const activeClientInfo = CLIENTS.find((c) => c.id === selectedClient);

  return (
    <div className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-6 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 dark:border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-xl bg-violet-50 dark:bg-violet-950/60 text-violet-600 dark:text-violet-400">
              <FaRobot className="text-base" />
            </span>
            <h3 className="text-base font-bold text-slate-900 dark:text-white">
              MCP Client Configuration
            </h3>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Connect AI assistants like Claude, Cursor, or ChatGPT to automate your social schedule via Model Context Protocol.
          </p>
        </div>

        {/* Token Selector */}
        {availableTokens.length > 0 && (
          <div className="flex items-center gap-2">
            <label className="text-xs font-semibold text-slate-600 dark:text-slate-400 shrink-0">
              Inject Token:
            </label>
            <select
              value={selectedToken}
              onChange={(e) => setSelectedToken(e.target.value)}
              className="text-xs font-mono rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-1.5 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500"
            >
              {availableTokens.map((t) => (
                <option key={t.id} value={`${t.key_prefix || t.name}...`}>
                  {t.name} ({t.key_prefix || 'token'})
                </option>
              ))}
              <option value="YOUR_UNRAVLER_TOKEN">Placeholder token</option>
            </select>
          </div>
        )}
      </div>

      {/* Client selector tabs */}
      <div className="flex flex-wrap gap-2">
        {CLIENTS.map((client) => {
          const Icon = client.icon;
          const isActive = selectedClient === client.id;
          return (
            <button
              key={client.id}
              type="button"
              onClick={() => setSelectedClient(client.id)}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all ${
                isActive
                  ? 'bg-violet-600 text-white shadow-md shadow-violet-500/20'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
            >
              <Icon className="text-xs" />
              {client.name}
            </button>
          );
        })}
      </div>

      {/* Code snippet display */}
      <div className="relative rounded-2xl bg-slate-950 border border-slate-800 overflow-hidden group">
        <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-red-500/80" />
            <span className="h-2.5 w-2.5 rounded-full bg-amber-500/80" />
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-500/80" />
            <span className="text-[11px] font-mono text-slate-400 ml-2">
              {activeClientInfo?.file}
            </span>
          </div>
          <button
            type="button"
            onClick={handleCopy}
            className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold text-slate-200 bg-slate-800 hover:bg-slate-700 transition-colors"
          >
            {copied ? <FaCheck className="text-emerald-400" /> : <FaCopy className="text-xs" />}
            <span>{copied ? 'Copied!' : 'Copy Config'}</span>
          </button>
        </div>
        <pre className="p-4 text-xs font-mono text-emerald-400/90 overflow-x-auto leading-relaxed">
          {generateSnippet()}
        </pre>
      </div>
    </div>
  );
}
