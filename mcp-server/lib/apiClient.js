import axios from 'axios';

const DEFAULT_BASE_URL = 'http://localhost:8001';
const TEN_YEARS_IN_SECONDS = 60 * 60 * 24 * 365 * 10;

export function resolveBaseUrl(
  rawBaseUrl = process.env.UNRAVLER_BACKEND_BASE_URL
    || process.env.UNRAVLER_BASE_URL
    || process.env.SOCIALENTANGLER_BASE_URL
    || DEFAULT_BASE_URL,
) {
  return String(rawBaseUrl || DEFAULT_BASE_URL).replace(/\/$/, '');
}

export function resolveToken(rawToken = process.env.UNRAVLER_TOKEN || process.env.SOCIALENTANGLER_API_KEY) {
  return typeof rawToken === 'string' ? rawToken.trim() : '';
}

export function createPublicApiClient({ token, baseUrl = resolveBaseUrl(), userAgent = 'unravler-mcp/1.1.0' }) {
  if (!token) {
    throw new Error('Missing Unravler developer token');
  }

  return axios.create({
    baseURL: `${baseUrl}/api/public`,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'User-Agent': userAgent,
    },
    timeout: 30000,
  });
}

export async function verifyDeveloperToken({ token, baseUrl = resolveBaseUrl() }) {
  const api = createPublicApiClient({
    token,
    baseUrl,
    userAgent: 'unravler-mcp-auth/1.1.0',
  });
  const { data } = await api.get('/me');
  const scopes = Array.isArray(data?.scopes)
    ? data.scopes
    : (Array.isArray(data?.token_scopes) ? data.token_scopes : []);
  return {
    token,
    clientId: String(data?.token_id || data?.user_id || 'unravler-client'),
    scopes,
    expiresAt: Math.floor(Date.now() / 1000) + TEN_YEARS_IN_SECONDS,
    extra: data,
  };
}

export function buildIdempotencyHeaders(extra, action) {
  if (!extra?.requestId) {
    return {};
  }
  return {
    'Idempotency-Key': `mcp:${action}:${String(extra.requestId)}`,
  };
}

export function getErrorMessage(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim();
  }
  const message = error?.response?.data?.message;
  if (typeof message === 'string' && message.trim()) {
    return message.trim();
  }
  if (typeof error?.message === 'string' && error.message.trim()) {
    return error.message.trim();
  }
  return 'Unexpected MCP error';
}
