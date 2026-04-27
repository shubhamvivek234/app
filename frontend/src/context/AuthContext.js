import React, { createContext, useState, useContext, useEffect, useCallback } from 'react';
import axios from 'axios';
import { setUserContext } from '../lib/sentry';
import { toast } from 'sonner';
import {
  googleSignIn,
  handleRedirectResult,
  emailSignIn,
  emailSignUp,
  firebaseSignOut,
  getIdToken,
  fetchBackendProfile as fetchProfileService,
  listenToAuthState,
  setAuthToken,
  clearAuthData,
  getSavedToken,
  isRetriableBackendError,
  isFatalAuthSyncError,
} from '@/services/authService';
import env from '@/env';

const AuthContext = createContext();

const BACKEND_URL = env.BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null); // Backend User Profile (MongoDB)
  const [firebaseUser, setFirebaseUser] = useState(null); // Firebase User Object
  const [loading, setLoading] = useState(true);
  const [authIssue, setAuthIssue] = useState(null);
  const [token, setToken] = useState(() => {
    // Initialize from localStorage if available
    return getSavedToken() || null;
  });

  const syncProfile = useCallback(async (idToken, currentUser, { silent = false } = {}) => {
    try {
      const profile = await fetchProfileService(idToken);
      setUser(profile);
      setUserContext(profile);
      setAuthIssue(null);
      return profile;
    } catch (error) {
      const transient = isRetriableBackendError(error);
      const fatal = isFatalAuthSyncError(error);

      if (!silent) {
        console.error('[AuthContext] Error syncing user:', error);
      }

      if (fatal || !transient) {
        throw error;
      }

      setAuthIssue({
        code: 'backend_sync_unavailable',
        message: 'You are signed in, but the app server is taking a moment to catch up.',
      });
      throw error;
    }
  }, []);

  // 1. Check for redirect result on mount (Google sign-in via redirect)
  useEffect(() => {
    const checkRedirectResult = async () => {
      try {
        await handleRedirectResult();
        // handleRedirectResult triggers onAuthStateChanged if successful
      } catch (error) {
        console.error('[AuthContext] Error handling redirect result:', error);
      }
    };
    checkRedirectResult();
  }, []);

  // 2. Listen for Firebase Auth Changes (using isolated authService)
  useEffect(() => {
    const unsubscribe = listenToAuthState(async (currentUser) => {
      // Always set loading=true at the start of an auth state change.
      // This prevents PrivateRoute from seeing (user=null, loading=false)
      // during the async fetchBackendProfile call on a fresh login.
      setLoading(true);
      if (currentUser) {
        setFirebaseUser(currentUser);
        try {
          // Get ID Token
          const idToken = await getIdToken(currentUser);
          setToken(idToken);
          setAuthIssue(null);

          // Sync with Backend (Get detailed profile)
          await syncProfile(idToken, currentUser);
        } catch (error) {
          if (isRetriableBackendError(error) && !isFatalAuthSyncError(error)) {
            toast.error('Signed in, but the server is temporarily unavailable. We will keep trying.');
          } else {
            console.error('[AuthContext] Fatal sync error, signing out:', error);
            try {
              await firebaseSignOut();
            } catch (_) {
              clearAuthData();
            }
            setToken(null);
            setUser(null);
            setFirebaseUser(null);
            setAuthIssue(null);
            toast.error('Login failed. Please try again.');
          }
        }
      } else {
        setFirebaseUser(null);
        setAuthIssue(null);
        // Don't clear token/user here if token exists in localStorage (backend OAuth flow)
        const savedToken = getSavedToken();
        if (!savedToken) {
          setToken(null);
          setUser(null);
          clearAuthData();
        }
      }
      setLoading(false);
    });

    return () => unsubscribe();
  }, [syncProfile]);

  // 3. If token exists but user doesn't, fetch user profile (handles backend OAuth)
  useEffect(() => {
    if (token && !user && !firebaseUser) {
      fetchProfileService(token)
        .then(profile => {
          setUser(profile);
          setUserContext(profile);
          setAuthIssue(null);
        })
        .catch(err => {
          console.warn('[AuthContext] Failed to fetch profile with existing token:', err?.message);
          if (err?.code === 'ERR_NETWORK' || err?.code === 'ECONNREFUSED') {
            toast.error('Cannot reach server. Please make sure the backend is running.');
          } else {
            toast.error('Failed to load your profile. Please refresh the page.');
          }
        });
    }
  }, [token, user, firebaseUser]);

  // 4. Login Actions (delegated to authService)
  const loginWithGoogle = async () => {
    try {
      // Use authService which handles popup + redirect fallback
      // onAuthStateChanged will handle token storage, backend sync, user state
      await googleSignIn();
      return true;
    } catch (error) {
      console.error('[AuthContext] Google login error:', error.code);
      if (error.code !== 'auth/popup-closed-by-user') {
        toast.error(error.message || 'Google login failed');
      }
      throw error;
    }
  };

  const login = async (email, password, cfTurnstileToken = null) => {
    try {
      // Use authService email login which handles Turnstile validation
      await emailSignIn(email, password, cfTurnstileToken);
      return true;
    } catch (error) {
      console.error('[AuthContext] Email login error:', error.code);
      if (error?.response?.status === 403) {
        toast.error("Bot protection check failed. Please refresh and try again.");
      } else {
        toast.error("Invalid email or password");
      }
      throw error;
    }
  };

  const signup = async (email, password, name, cfTurnstileToken = null) => {
    try {
      // Use authService email signup (handles Turnstile validation)
      await emailSignUp(email, password);

      // onAuthStateChanged will handle backend sync automatically
      return true;
    } catch (error) {
      console.error('[AuthContext] Signup error:', error.code);
      if (error?.response?.status === 403) {
        toast.error("Bot protection check failed. Please refresh and try again.");
      } else {
        toast.error(error.message || 'Signup failed');
      }
      throw error;
    }
  };

  const logout = async () => {
    try {
      // Clear state and storage BEFORE signOut so onAuthStateChanged
      // doesn't skip cleanup due to the localStorage token check
      setToken(null);
      setUser(null);
      setFirebaseUser(null);
      // Use authService logout which clears all auth data
      await firebaseSignOut();
    } catch (error) {
      console.error('[AuthContext] Logout error:', error);
      // Even if signOut fails, ensure local state is cleared
      clearAuthData();
      setToken(null);
      setUser(null);
      setFirebaseUser(null);
      setAuthIssue(null);
    }
  };

  const retryProfileSync = useCallback(async ({ silent = false } = {}) => {
    const activeUser = firebaseUser;
    const activeToken = token;
    if (!activeUser && !activeToken) {
      return false;
    }

    setLoading(true);
    try {
      const nextToken = activeUser ? await getIdToken(activeUser) : activeToken;
      if (nextToken) {
        setToken(nextToken);
        await syncProfile(nextToken, activeUser, { silent });
        return true;
      }
      return false;
    } catch (error) {
      if (!silent) {
        toast.error('Still waiting on the server. Please try again in a moment.');
      }
      return false;
    } finally {
      setLoading(false);
    }
  }, [firebaseUser, token, syncProfile]);

  useEffect(() => {
    if (!authIssue || (!firebaseUser && !token)) {
      return undefined;
    }

    const timer = window.setTimeout(() => {
      retryProfileSync({ silent: true });
    }, 4000);

    return () => window.clearTimeout(timer);
  }, [authIssue, firebaseUser, token, retryProfileSync]);

  // Helper to force token refresh if needed.
  // Works for both Firebase users (refreshes Firebase token) and
  // plain JWT users (re-fetches backend profile with the existing token).
  const refreshUser = async () => {
    if (firebaseUser) {
      const idToken = await getIdToken(firebaseUser);
      setToken(idToken);
      const profile = await fetchProfileService(idToken);
      setUser(profile);
      setUserContext(profile);
    } else if (token) {
      const profile = await fetchProfileService(token);
      setUser(profile);
      setUserContext(profile);
    }
  };

  return (
    <AuthContext.Provider value={{
      user, // MongoDB Profile
      firebaseUser, // Firebase User
      loading,
      authIssue,
      login,
      signup,
      loginWithGoogle,
      logout,
      token,
      setToken,
      setUser,
      refreshUser,
      retryProfileSync
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
