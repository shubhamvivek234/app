#!/usr/bin/env node

import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { requireBearerAuth } from '@modelcontextprotocol/sdk/server/auth/middleware/bearerAuth.js';
import { InvalidTokenError, ServerError } from '@modelcontextprotocol/sdk/server/auth/errors.js';
import { createMcpExpressApp } from '@modelcontextprotocol/sdk/server/express.js';

import { createPublicApiClient, getErrorMessage, resolveBaseUrl, verifyDeveloperToken } from './lib/apiClient.js';
import { createUnravlerMcpServer } from './lib/server.js';

const PORT = Number.parseInt(process.env.PORT || process.env.MCP_PORT || '3001', 10);
const HOST = process.env.HOST || '0.0.0.0';
const BASE_URL = resolveBaseUrl();
const allowedHosts = String(
  process.env.MCP_ALLOWED_HOSTS || 'localhost,127.0.0.1,api.unravler.com',
)
  .split(',')
  .map((host) => host.trim())
  .filter(Boolean);

const verifier = {
  async verifyAccessToken(token) {
    try {
      return await verifyDeveloperToken({ token, baseUrl: BASE_URL });
    } catch (error) {
      const statusCode = error?.response?.status;
      if (statusCode === 401 || statusCode === 403) {
        throw new InvalidTokenError(getErrorMessage(error));
      }
      throw new ServerError(getErrorMessage(error));
    }
  },
};

const app = createMcpExpressApp({
  host: HOST,
  allowedHosts,
});

const authMiddleware = requireBearerAuth({ verifier });

app.get('/health', (_req, res) => {
  res.json({
    ok: true,
    service: 'unravler-mcp-http',
    baseUrl: BASE_URL,
  });
});

app.post('/mcp', authMiddleware, async (req, res) => {
  const server = createUnravlerMcpServer({
    getApi: (extra) => {
      const token = extra?.authInfo?.token || req.auth?.token;
      return createPublicApiClient({ token, baseUrl: BASE_URL });
    },
  });

  try {
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
    });
    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
    res.on('close', () => {
      transport.close();
      server.close();
    });
  } catch (error) {
    console.error('[Unravler MCP] request failed', error);
    if (!res.headersSent) {
      res.status(500).json({
        jsonrpc: '2.0',
        error: {
          code: -32603,
          message: getErrorMessage(error),
        },
        id: null,
      });
    }
  }
});

for (const method of ['get', 'delete']) {
  app[method]('/mcp', (_req, res) => {
    res.status(405).json({
      jsonrpc: '2.0',
      error: {
        code: -32000,
        message: 'Method not allowed.',
      },
      id: null,
    });
  });
}

app.listen(PORT, (error) => {
  if (error) {
    console.error('[Unravler MCP] failed to start', error);
    process.exit(1);
  }
  console.log(`[Unravler MCP] HTTP server listening on ${HOST}:${PORT} (backend ${BASE_URL})`);
});
