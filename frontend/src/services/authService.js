/**
 * Isolated Authentication Service
 *
 * This service handles all authentication logic independently from UI.
 * It encapsulates Google login, email/password auth, and token management.
 *
 * IMPORTANT: This file should NEVER be modified during UI changes.
 * All authentication logic is isolated here to prevent UI updates from breaking auth.
 */

import axios from 'axios';
import { auth, googleProvider } from '@/firebase';
import {
  onAuthStateChanged,
  signInWithPopup,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut,
  signInWithRedirect,
  getRedirectResult,
} from 'firebase/auth';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

/**
 * Configure axios with auth token
 */
export const setAuthToken = (token) => {
  if (token) {
    axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    localStorage.setItem('token', token);
  } else {
    delete axios.defaults.headers.common['Authorization'];
    localStorage.removeItem('token');
  }
};

/**
 * Get saved auth token from localStorage
 */
export const getSavedToken = () => {
  return localStorage.getItem('token');
};

/**
 * Clear all auth data
 */
export const clearAuthData = () => {
  localStorage.removeItem('token');
  delete axios.defaults.headers.common['Authorization'];
};

/**
 * Google Sign-In with popup fallback to redirect
 *
 * - First tries popup (modern, better UX)
 * - If popup blocked, falls back to redirect flow
 * - Both flows handled by onAuthStateChanged listener
 */
export const googleSignIn = async () => {
  try {
    console.log('[AuthService] Starting Google sign-in with popup...');
    await signInWithPopup(auth, googleProvider);
    return true;
  } catch (error) {
    console.error('[AuthService] Google popup error:', error.code, error.message);

    // Popup was blocked - fall back to redirect flow
    if (error.code === 'auth/popup-blocked' || error.code === 'auth/operation-not-supported-in-this-environment') {
      console.log('[AuthService] Popup blocked, falling back to redirect flow...');
      try {
        await signInWithRedirect(auth, googleProvider);
        return true;
      } catch (redirectError) {
        console.error('[AuthService] Redirect flow error:', redirectError);
        throw redirectError;
      }
    }

    // User cancelled popup
    if (error.code === 'auth/popup-closed-by-user') {
      console.log('[AuthService] User closed popup');
      return false;
    }

    throw error;
  }
};

/**
 * Handle redirect result from Google sign-in
 * Called after page load if user signed in via redirect
 */
export const handleRedirectResult = async () => {
  try {
    console.log('[AuthService] Checking for redirect result...');
    const result = await getRedirectResult(auth);
    if (result && result.user) {
      console.log('[AuthService] Redirect login successful:', result.user.email);
      return result.user;
    }
  } catch (error) {
    console.error('[AuthService] Error handling redirect result:', error);
    throw error;
  }
};

/**
 * Email/Password Sign-In
 */
export const emailSignIn = async (email, password, cfTurnstileToken = null) => {
  try {
    console.log('[AuthService] Starting email sign-in...');
    const credential = await signInWithEmailAndPassword(auth, email, password);

    // If Turnstile token provided, notify backend
    if (cfTurnstileToken) {
      try {
        const idToken = await credential.user.getIdToken();
        await axios.post(
          `${API}/auth/login`,
          { cf_turnstile_token: cfTurnstileToken },
          { headers: { Authorization: `Bearer ${idToken}` } }
        );
      } catch (backendErr) {
        console.warn('[AuthService] Turnstile validation error:', backendErr?.response?.data);
        if (backendErr?.response?.status === 403) throw backendErr;
      }
    }

    return credential.user;
  } catch (error) {
    console.error('[AuthService] Email sign-in error:', error.code);
    throw error;
  }
};

/**
 * Email/Password Sign-Up
 */
export const emailSignUp = async (email, password) => {
  try {
    console.log('[AuthService] Starting email sign-up...');
    const credential = await createUserWithEmailAndPassword(auth, email, password);
    return credential.user;
  } catch (error) {
    console.error('[AuthService] Email sign-up error:', error.code);
    throw error;
  }
};

/**
 * Sign Out
 * Clears Firebase auth and local auth data
 */
export const firebaseSignOut = async () => {
  try {
    console.log('[AuthService] Signing out...');
    await signOut(auth);
    clearAuthData();
    return true;
  } catch (error) {
    console.error('[AuthService] Sign-out error:', error);
    throw error;
  }
};

/**
 * Get Firebase ID Token
 */
export const getIdToken = async (user) => {
  try {
    if (!user) throw new Error('No user logged in');
    const token = await user.getIdToken();
    setAuthToken(token);
    return token;
  } catch (error) {
    console.error('[AuthService] Error getting ID token:', error);
    throw error;
  }
};

/**
 * Fetch User Profile from Backend
 * Retries once after 2 seconds if first attempt fails
 */
export const fetchBackendProfile = async (idToken) => {
  const attempt = async () => {
    const response = await axios.get(`${API}/auth/me`, {
      headers: { Authorization: `Bearer ${idToken}` },
      timeout: 8000,
    });
    return response.data;
  };

  try {
    console.log('[AuthService] Fetching backend profile...');
    return await attempt();
  } catch (firstError) {
    console.warn('[AuthService] First profile fetch failed, retrying in 2s...', firstError?.message);

    // Retry once after 2 seconds
    await new Promise(r => setTimeout(r, 2000));
    try {
      return await attempt();
    } catch (secondError) {
      console.error('[AuthService] Profile fetch failed after retry:', secondError?.message);
      throw secondError;
    }
  }
};

/**
 * Listen for Firebase Auth State Changes
 * Returns unsubscribe function
 */
export const listenToAuthState = (callback) => {
  console.log('[AuthService] Setting up auth state listener...');
  return onAuthStateChanged(auth, callback);
};
