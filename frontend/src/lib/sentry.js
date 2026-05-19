/**
 * Sentry frontend error tracking — Stage 4
 * Initialize once in index.js before rendering.
 * REACT_APP_SENTRY_DSN must be set in .env
 */
import * as Sentry from '@sentry/react';

const SENTRY_DSN = process.env.REACT_APP_SENTRY_DSN;
const SENTRY_ENVIRONMENT = process.env.REACT_APP_SENTRY_ENVIRONMENT || process.env.NODE_ENV;
const SENTRY_RELEASE = process.env.REACT_APP_SENTRY_RELEASE;
const SENTRY_TRACES_SAMPLE_RATE = Number(process.env.REACT_APP_SENTRY_TRACES_SAMPLE_RATE || 0.1);
const SENTRY_REPLAYS_SESSION_SAMPLE_RATE = Number(process.env.REACT_APP_SENTRY_REPLAYS_SESSION_SAMPLE_RATE || 0.1);
const SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE = Number(process.env.REACT_APP_SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE || 1.0);

export function initSentry() {
  if (!SENTRY_DSN) {
    console.debug('Sentry DSN not configured — error tracking disabled');
    return;
  }
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: SENTRY_ENVIRONMENT,
    release: SENTRY_RELEASE,
    tracesSampleRate: SENTRY_TRACES_SAMPLE_RATE,
    replaysSessionSampleRate: SENTRY_REPLAYS_SESSION_SAMPLE_RATE,
    replaysOnErrorSampleRate: SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE,
    beforeSend(event) {
      // Don't send events in development
      if (process.env.NODE_ENV !== 'production') return null;
      return event;
    },
  });
}

export function captureError(error, context = {}) {
  if (!SENTRY_DSN) return;
  Sentry.withScope((scope) => {
    Object.entries(context).forEach(([key, value]) => {
      scope.setExtra(key, value);
    });
    Sentry.captureException(error);
  });
}

export function setUserContext(user) {
  if (!SENTRY_DSN || !user) return;
  Sentry.setUser({
    id: user.user_id,
    email: user.email,
    subscription: user.subscription_status,
  });
}
