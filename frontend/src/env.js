/**
 * Environment variable compatibility shim.
 * Supports both REACT_APP_ (CRA/Webpack) and VITE_ (Vite) prefixes safely.
 */
const safeMetaEnv = (() => {
  try {
    return (typeof import.meta !== 'undefined' && import.meta && import.meta.env) ? import.meta.env : {};
  } catch (_) {
    return {};
  }
})();

const safeProcEnv = (() => {
  try {
    return (typeof process !== 'undefined' && process && process.env) ? process.env : {};
  } catch (_) {
    return {};
  }
})();

const getEnvVar = (name, fallback = '') => {
  return safeMetaEnv[`VITE_${name}`]
    || safeMetaEnv[`REACT_APP_${name}`]
    || safeMetaEnv[name]
    || safeProcEnv[`REACT_APP_${name}`]
    || safeProcEnv[`VITE_${name}`]
    || safeProcEnv[name]
    || fallback;
};

const env = {
  BACKEND_URL: getEnvVar('BACKEND_URL', 'http://localhost:8001'),
  FIREBASE_API_KEY: getEnvVar('FIREBASE_API_KEY', ''),
  FIREBASE_AUTH_DOMAIN: getEnvVar('FIREBASE_AUTH_DOMAIN', ''),
  FIREBASE_USE_FIRST_PARTY_AUTH_DOMAIN: getEnvVar('FIREBASE_USE_FIRST_PARTY_AUTH_DOMAIN', 'false').toLowerCase(),
  FIREBASE_PROJECT_ID: getEnvVar('FIREBASE_PROJECT_ID', ''),
  FIREBASE_STORAGE_BUCKET: getEnvVar('FIREBASE_STORAGE_BUCKET', ''),
  FIREBASE_MESSAGING_SENDER_ID: getEnvVar('FIREBASE_MESSAGING_SENDER_ID', ''),
  FIREBASE_APP_ID: getEnvVar('FIREBASE_APP_ID', ''),
  FIREBASE_MEASUREMENT_ID: getEnvVar('FIREBASE_MEASUREMENT_ID', ''),
  SENTRY_DSN: getEnvVar('SENTRY_DSN', ''),
  RAZORPAY_KEY_ID: getEnvVar('RAZORPAY_KEY_ID', ''),
  TENOR_API_KEY: getEnvVar('TENOR_API_KEY', ''),
  UNSPLASH_ACCESS_KEY: getEnvVar('UNSPLASH_ACCESS_KEY', 'GUPs8JkjqQaNg1SSdFM5LtHGjzhXszV5wM-mVL1mQQs'),
  DROPBOX_APP_KEY: getEnvVar('DROPBOX_APP_KEY', '12r9kfe7r3xewc2'),
  GOOGLE_PICKER_API_KEY: getEnvVar('GOOGLE_PICKER_API_KEY', 'AIzaSyComimUXiPgXOdyXaztwSNp6GRxquxVzdU'),
  GOOGLE_CLIENT_ID: getEnvVar('GOOGLE_CLIENT_ID', '973333038336-fjic3rr6ug35kgr2s2k4f2jock5vo4o8.apps.googleusercontent.com'),
  GOOGLE_PHOTOS_CLIENT_ID: getEnvVar('GOOGLE_PHOTOS_CLIENT_ID', '973333038336-fjic3rr6ug35kgr2s2k4f2jock5vo4o8.apps.googleusercontent.com'),
  ONEDRIVE_APP_ID: getEnvVar('ONEDRIVE_APP_ID', ''),
  ONEDRIVE_REDIRECT_URI: getEnvVar('ONEDRIVE_REDIRECT_URI', ''),
  CANVA_IMPORT_ENABLED: getEnvVar('CANVA_IMPORT_ENABLED', 'true').toLowerCase(),
  AUDIO_PROVIDER_ENABLED: getEnvVar('AUDIO_PROVIDER_ENABLED', 'false').toLowerCase(),
  AUDIO_PROVIDER_NAME: getEnvVar('AUDIO_PROVIDER_NAME', ''),
};

export default env;
