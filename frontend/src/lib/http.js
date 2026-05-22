import axios from 'axios';
import { auth } from '@/firebase';
import env from '@/env';

let initialized = false;
const BACKEND_URL = (env.BACKEND_URL || '').replace(/\/+$/, '');

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

async function getFreshFirebaseToken(forceRefresh = false) {
  const currentUser = auth.currentUser;
  if (!currentUser) return null;
  try {
    const token = await currentUser.getIdToken(forceRefresh);
    if (typeof window !== 'undefined') {
      localStorage.setItem('token', token);
    }
    axios.defaults.headers.common.Authorization = `Bearer ${token}`;
    return token;
  } catch (error) {
    console.warn('[http] Unable to refresh Firebase ID token', error);
    return null;
  }
}

export function initHttpInterceptors() {
  if (initialized) return;
  initialized = true;

  axios.interceptors.request.use(async (config) => {
    const nextConfig = { ...config };
    nextConfig.headers = nextConfig.headers || {};
    if (!nextConfig.headers['X-Trace-ID']) {
      nextConfig.headers['X-Trace-ID'] = generateTraceId();
    }
    if (isBackendRequest(nextConfig)) {
      const token = await getFreshFirebaseToken(false);
      if (token) {
        nextConfig.headers.Authorization = `Bearer ${token}`;
      }
    }
    return nextConfig;
  });

  axios.interceptors.response.use(
    (response) => response,
    async (error) => {
      const originalRequest = error?.config;
      if (
        error?.response?.status === 401
        && originalRequest
        && !originalRequest._authRetried
        && isBackendRequest(originalRequest)
      ) {
        const refreshedToken = await getFreshFirebaseToken(true);
        if (refreshedToken) {
          const retryConfig = {
            ...originalRequest,
            _authRetried: true,
            headers: {
              ...(originalRequest.headers || {}),
              Authorization: `Bearer ${refreshedToken}`,
            },
          };
          return axios(retryConfig);
        }
      }

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
}
