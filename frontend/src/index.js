import { initSentry } from './lib/sentry';
initSentry();

import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import posthog from 'posthog-js';
import { PostHogProvider } from 'posthog-js/react';

posthog.init(
  process.env.REACT_APP_POSTHOG_KEY || 'YOUR_POSTHOG_KEY', 
  { api_host: process.env.REACT_APP_POSTHOG_HOST || 'https://app.posthog.com' }
);

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <PostHogProvider client={posthog}>
      <App />
    </PostHogProvider>
  </React.StrictMode>,
);
