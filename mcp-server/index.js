#!/usr/bin/env node
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { resolveBaseUrl, resolveToken } from './lib/apiClient.js';
import { createLocalApiFactory, createUnravlerMcpServer } from './lib/server.js';

const token = resolveToken();
if (!token) {
  process.stderr.write('[Unravler MCP] ERROR: set UNRAVLER_TOKEN (or legacy SOCIALENTANGLER_API_KEY)\n');
  process.exit(1);
}

const baseUrl = resolveBaseUrl();
const server = createUnravlerMcpServer({
  getApi: createLocalApiFactory({ token, baseUrl }),
});

const transport = new StdioServerTransport();
await server.connect(transport);
process.stderr.write(`[Unravler MCP] stdio server running against ${baseUrl}\n`);
