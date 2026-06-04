import axios from 'axios';
import env from '@/env';

let initialized = false;
const BACKEND_URL = (env.BACKEND_URL || '').replace(/\/+$/, '');
let originalFetch = null;

function generateTraceId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function isBackendRequest(config) {
  const url = config?.url;
  if (typeof url !== 'string' || !url) return false;
  return url.startsWith('/api/') || (BACKEND_URL && url.startsWith(BACKEND_URL));
}

function isBackendFetchTarget(input) {
  if (typeof input === 'string') {
    return input.startsWith('/api/') || (BACKEND_URL && input.startsWith(BACKEND_URL));
  }
  if (input instanceof Request) {
    return input.url.startsWith('/api/') || (BACKEND_URL && input.url.startsWith(BACKEND_URL));
  }
  return false;
}

function sanitizeFetchHeaders(headersLike) {
  const headers = new Headers(headersLike || {});
  const authorization = headers.get('Authorization') || headers.get('authorization');
  if (
    authorization === 'Bearer null'
    || authorization === 'Bearer undefined'
    || authorization === 'Bearer '
  ) {
    headers.delete('Authorization');
    headers.delete('authorization');
  }
  if (!headers.get('X-Trace-ID') && !headers.get('x-trace-id')) {
    headers.set('X-Trace-ID', generateTraceId());
  }
  return headers;
}

export function initHttpInterceptors() {
  if (initialized) return;
  initialized = true;

  axios.interceptors.request.use(async (config) => {
    const nextConfig = { ...config };
    nextConfig.headers = nextConfig.headers || {};
    if (isBackendRequest(nextConfig)) {
      nextConfig.withCredentials = true;
      if (!nextConfig.headers['X-Trace-ID']) {
        nextConfig.headers['X-Trace-ID'] = generateTraceId();
      }
      const authHeader = nextConfig.headers.Authorization || nextConfig.headers.authorization;
      if (
        authHeader === 'Bearer null'
        || authHeader === 'Bearer undefined'
        || authHeader === 'Bearer '
      ) {
        delete nextConfig.headers.Authorization;
        delete nextConfig.headers.authorization;
      }
    } else {
      delete nextConfig.headers.Authorization;
      delete nextConfig.headers.authorization;
      delete nextConfig.headers['X-Trace-ID'];
      delete nextConfig.headers['x-trace-id'];
    }
    return nextConfig;
  });

  axios.interceptors.response.use(
    (response) => response,
    async (error) => {
      const traceId = error?.response?.headers?.['x-trace-id'];
      if (traceId) {
        error.traceId = traceId;
        if (typeof error.message === 'string' && !error.message.includes(traceId)) {
          error.message = `${error.message} [Ref: ${traceId}]`;
        }
        if (error.response?.data && typeof error.response.data === 'object' && !error.response.data.trace_id) {
          error.response.data.trace_id = traceId;
        }
      }
      return Promise.reject(error);
    }
  );

  if (typeof window !== 'undefined' && typeof window.fetch === 'function' && !originalFetch) {
    originalFetch = window.fetch.bind(window);
    window.fetch = (input, init = {}) => {
      if (!isBackendFetchTarget(input)) {
        return originalFetch(input, init);
      }

      if (input instanceof Request) {
        const nextRequest = new Request(input, {
          credentials: 'include',
          headers: sanitizeFetchHeaders(input.headers),
        });
        return originalFetch(nextRequest, init);
      }

      return originalFetch(input, {
        ...init,
        credentials: 'include',
        headers: sanitizeFetchHeaders(init.headers),
      });
    };
  }
}
