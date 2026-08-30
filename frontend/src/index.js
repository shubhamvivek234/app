import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { initSentry } from './lib/sentry';
import { initHttpInterceptors } from './lib/http';
import posthog from 'posthog-js';
import { PostHogProvider } from 'posthog-js/react';

try {
  initSentry();
} catch (err) {
  console.warn('[Sentry] Init error:', err);
}

try {
  initHttpInterceptors();
} catch (err) {
  console.warn('[Http] Init error:', err);
}

const posthogKey = process.env.REACT_APP_POSTHOG_KEY;
const isPostHogConfigured = Boolean(posthogKey && posthogKey !== 'YOUR_POSTHOG_KEY');

if (isPostHogConfigured) {
  try {
    posthog.init(posthogKey, {
      api_host: process.env.REACT_APP_POSTHOG_HOST || 'https://app.posthog.com',
      autocapture: true,
      capture_pageview: true,
      capture_pageleave: true,
    });
  } catch (err) {
    console.warn('[PostHog] Init error:', err);
  }
}

const root = ReactDOM.createRoot(document.getElementById("root"));

const Content = isPostHogConfigured ? (
  <PostHogProvider client={posthog}>
    <App />
  </PostHogProvider>
) : (
  <App />
);

root.render(
  <React.StrictMode>
    {Content}
  </React.StrictMode>,
);
