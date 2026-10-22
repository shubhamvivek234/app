/**
 * Secret-safe structured logger for the Outreach frontend subsystem.
 *
 * - Redacts tokens, cookies (li_at, JSESSIONID), proxy credentials, and passwords.
 * - Suppresses `debug` and `info` logs during automated test runs (`NODE_ENV === 'test'`)
 *   unless `REACT_APP_OUTREACH_DEBUG_LOGS=true` is explicitly set.
 */

const SENSITIVE_KEY_PATTERN = /(token|secret|password|cookie|li_at|li_a|jsessionid|authorization|api_key|proxy_url|session_cookie)/i;
const PROXY_URL_CRED_PATTERN = /(https?:\/\/)([^/\s:@]+:[^/\s@]+@)/gi;
const COOKIE_VALUE_PATTERN = /\b(li_at|li_a|JSESSIONID)\s*=\s*[^\s;&"']+/gi;

export function scrubLogValue(value, depth = 0) {
  if (depth > 4 || value == null) {
    return value;
  }
  if (typeof value === 'string') {
    return value
      .replace(PROXY_URL_CRED_PATTERN, '$1[REDACTED]@')
      .replace(COOKIE_VALUE_PATTERN, '$1=[REDACTED]');
  }
  if (value instanceof Error) {
    return {
      name: value.name || 'Error',
      message: scrubLogValue(value.message || '', depth + 1),
      status: value.response?.status,
    };
  }
  if (Array.isArray(value)) {
    return value.map((item) => scrubLogValue(item, depth + 1));
  }
  if (typeof value === 'object') {
    const scrubbed = {};
    for (const [k, v] of Object.entries(value)) {
      if (SENSITIVE_KEY_PATTERN.test(k)) {
        scrubbed[k] = '[REDACTED]';
      } else {
        scrubbed[k] = scrubLogValue(v, depth + 1);
      }
    }
    return scrubbed;
  }
  return value;
}

function isQuietTestEnv() {
  return (
    typeof process !== 'undefined' &&
    process.env &&
    process.env.NODE_ENV === 'test' &&
    process.env.REACT_APP_OUTREACH_DEBUG_LOGS !== 'true'
  );
}

export const outreachLogger = {
  debug(event, meta = {}) {
    if (isQuietTestEnv()) return;
    if (typeof console !== 'undefined' && typeof console.debug === 'function') {
      console.debug(`[Outreach] ${event}`, scrubLogValue(meta));
    }
  },
  info(event, meta = {}) {
    if (isQuietTestEnv()) return;
    if (typeof console !== 'undefined' && typeof console.info === 'function') {
      console.info(`[Outreach] ${event}`, scrubLogValue(meta));
    }
  },
  warn(event, meta = {}) {
    if (isQuietTestEnv()) return;
    if (typeof console !== 'undefined' && typeof console.warn === 'function') {
      console.warn(`[Outreach] ${event}`, scrubLogValue(meta));
    }
  },
  error(event, meta = {}) {
    if (typeof console !== 'undefined' && typeof console.error === 'function') {
      console.error(`[Outreach] ${event}`, scrubLogValue(meta));
    }
  },
};

export default outreachLogger;
