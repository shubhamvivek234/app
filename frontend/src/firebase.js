import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider } from "firebase/auth";
import { getStorage } from "firebase/storage";
import { getAnalytics, isSupported } from "firebase/analytics";
import env from "./env";

/**
 * Firebase config is loaded exclusively from environment variables.
 * Set these in frontend/.env (already in .gitignore — never commit real values).
 *
 * Required vars:
 *   REACT_APP_FIREBASE_API_KEY
 *   REACT_APP_FIREBASE_AUTH_DOMAIN
 *   REACT_APP_FIREBASE_PROJECT_ID
 *   REACT_APP_FIREBASE_STORAGE_BUCKET
 *   REACT_APP_FIREBASE_MESSAGING_SENDER_ID
 *   REACT_APP_FIREBASE_APP_ID
 *   REACT_APP_FIREBASE_MEASUREMENT_ID  (optional — for Analytics)
 */
const firebaseConfig = {
    apiKey:            env.FIREBASE_API_KEY,
    authDomain:        env.FIREBASE_AUTH_DOMAIN,
    projectId:         env.FIREBASE_PROJECT_ID,
    storageBucket:     env.FIREBASE_STORAGE_BUCKET,
    messagingSenderId: env.FIREBASE_MESSAGING_SENDER_ID,
    appId:             env.FIREBASE_APP_ID,
    measurementId:     import.meta.env.VITE_FIREBASE_MEASUREMENT_ID
      || import.meta.env.REACT_APP_FIREBASE_MEASUREMENT_ID
      || process.env.REACT_APP_FIREBASE_MEASUREMENT_ID,
};

const requiredFirebaseFields = [
    ['REACT_APP_FIREBASE_API_KEY', env.FIREBASE_API_KEY],
    ['REACT_APP_FIREBASE_AUTH_DOMAIN', env.FIREBASE_AUTH_DOMAIN],
    ['REACT_APP_FIREBASE_PROJECT_ID', env.FIREBASE_PROJECT_ID],
    ['REACT_APP_FIREBASE_APP_ID', env.FIREBASE_APP_ID],
];

export const getMissingFirebaseConfig = () => (
    requiredFirebaseFields
        .filter(([, value]) => !value)
        .map(([key]) => key)
);

export const assertFirebaseAuthConfig = () => {
    const missing = getMissingFirebaseConfig();
    if (missing.length) {
        throw new Error(
            `Firebase auth is not configured for this deployment. Missing: ${missing.join(', ')}`
        );
    }
};

// Guard: warn loudly in dev if any required key is missing
if (process.env.NODE_ENV === 'development') {
    requiredFirebaseFields.forEach(([key, value]) => {
        if (!value) {
            console.warn(`[Firebase] Missing env var: ${key}. Check your frontend/.env file.`);
        }
    });
}

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Analytics is optional — only initialise if the browser supports it
// (blocked in some browsers / extensions — this prevents a crash)
isSupported().then((supported) => {
    if (supported) getAnalytics(app);
});

export const auth = getAuth(app);
export const storage = getStorage(app);

export const googleProvider = new GoogleAuthProvider();
googleProvider.addScope('email');
googleProvider.addScope('profile');
googleProvider.setCustomParameters({ prompt: 'select_account' });

export default app;
