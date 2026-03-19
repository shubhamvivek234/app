/**
 * Environment variable compatibility shim.
 * Supports both REACT_APP_ (CRA legacy) and VITE_ prefixes.
 * Import this instead of using process.env directly where possible.
 *
 * Note: process.env.REACT_APP_* still works everywhere because vite.config.js
 * injects all REACT_APP_ vars via the `define` option. This shim is an
 * explicit, testable alternative that prefers VITE_ prefix for new code.
 */
const env = {
  BACKEND_URL: import.meta.env.VITE_BACKEND_URL
    || import.meta.env.REACT_APP_BACKEND_URL
    || process.env.REACT_APP_BACKEND_URL
    || 'http://localhost:8001',

  FIREBASE_API_KEY: import.meta.env.VITE_FIREBASE_API_KEY
    || import.meta.env.REACT_APP_FIREBASE_API_KEY
    || process.env.REACT_APP_FIREBASE_API_KEY,

  FIREBASE_AUTH_DOMAIN: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN
    || import.meta.env.REACT_APP_FIREBASE_AUTH_DOMAIN
    || process.env.REACT_APP_FIREBASE_AUTH_DOMAIN,

  FIREBASE_PROJECT_ID: import.meta.env.VITE_FIREBASE_PROJECT_ID
    || import.meta.env.REACT_APP_FIREBASE_PROJECT_ID
    || process.env.REACT_APP_FIREBASE_PROJECT_ID,

  FIREBASE_STORAGE_BUCKET: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET
    || import.meta.env.REACT_APP_FIREBASE_STORAGE_BUCKET
    || process.env.REACT_APP_FIREBASE_STORAGE_BUCKET,

  FIREBASE_MESSAGING_SENDER_ID: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID
    || import.meta.env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID
    || process.env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID,

  FIREBASE_APP_ID: import.meta.env.VITE_FIREBASE_APP_ID
    || import.meta.env.REACT_APP_FIREBASE_APP_ID
    || process.env.REACT_APP_FIREBASE_APP_ID,

  SENTRY_DSN: import.meta.env.VITE_SENTRY_DSN
    || import.meta.env.REACT_APP_SENTRY_DSN
    || process.env.REACT_APP_SENTRY_DSN,

  RAZORPAY_KEY_ID: import.meta.env.VITE_RAZORPAY_KEY_ID
    || import.meta.env.REACT_APP_RAZORPAY_KEY_ID
    || process.env.REACT_APP_RAZORPAY_KEY_ID,

  TENOR_API_KEY: import.meta.env.VITE_TENOR_API_KEY
    || import.meta.env.REACT_APP_TENOR_API_KEY
    || process.env.REACT_APP_TENOR_API_KEY,

  UNSPLASH_ACCESS_KEY: import.meta.env.VITE_UNSPLASH_ACCESS_KEY
    || import.meta.env.REACT_APP_UNSPLASH_ACCESS_KEY
    || process.env.REACT_APP_UNSPLASH_ACCESS_KEY,

  DROPBOX_APP_KEY: import.meta.env.VITE_DROPBOX_APP_KEY
    || import.meta.env.REACT_APP_DROPBOX_APP_KEY
    || process.env.REACT_APP_DROPBOX_APP_KEY,

  GOOGLE_PICKER_API_KEY: import.meta.env.VITE_GOOGLE_PICKER_API_KEY
    || import.meta.env.REACT_APP_GOOGLE_PICKER_API_KEY
    || process.env.REACT_APP_GOOGLE_PICKER_API_KEY,

  GOOGLE_CLIENT_ID: import.meta.env.VITE_GOOGLE_CLIENT_ID
    || import.meta.env.REACT_APP_GOOGLE_CLIENT_ID
    || process.env.REACT_APP_GOOGLE_CLIENT_ID,
};

export default env;
