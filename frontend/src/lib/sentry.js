/**
 * Sentry frontend error tracking — Stage 4
 * Initialize once in index.js before rendering.
 * REACT_APP_SENTRY_DSN must be set in .env
 */
import * as Sentry from '@sentry/react';

const SENTRY_DSN = process.env.REACT_APP_SENTRY_DSN;

export function initSentry() {
  if (!SENTRY_DSN) {
    console.debug('Sentry DSN not configured — error tracking disabled');
    return;
  }
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: process.env.NODE_ENV,
    tracesSampleRate: 0.1,
    replaysSessionSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,
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
