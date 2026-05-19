import axios from 'axios';

let initialized = false;
function generateTraceId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function initHttpInterceptors() {
  if (initialized) return;
  initialized = true;

  axios.interceptors.request.use((config) => {
    const nextConfig = { ...config };
    nextConfig.headers = nextConfig.headers || {};
    if (!nextConfig.headers['X-Trace-ID']) {
      nextConfig.headers['X-Trace-ID'] = generateTraceId();
    }
    return nextConfig;
  });

  axios.interceptors.response.use(
    (response) => response,
    (error) => {
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
