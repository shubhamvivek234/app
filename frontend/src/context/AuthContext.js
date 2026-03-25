import React, { createContext, useState, useContext, useEffect } from 'react';
import axios from 'axios';
import { auth, googleProvider } from '@/firebase';
import { setUserContext } from '../lib/sentry';
import {
  onAuthStateChanged,
  signInWithPopup,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut
} from 'firebase/auth';
import { toast } from 'sonner';

const AuthContext = createContext();

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null); // Backend User Profile (MongoDB)
  const [firebaseUser, setFirebaseUser] = useState(null); // Firebase User Object
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState(() => {
    // Initialize from localStorage if available
    const savedToken = localStorage.getItem('token');
    return savedToken || null;
  });

  // 1. Listen for Firebase Auth Changes
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
      // Always set loading=true at the start of an auth state change.
      // This prevents PrivateRoute from seeing (user=null, loading=false)
      // during the async fetchBackendProfile call on a fresh login.
      setLoading(true);
      if (currentUser) {
        console.log("[Auth] Firebase auth state changed: user logged in", currentUser.email);
        setFirebaseUser(currentUser);
        try {
          // Get ID Token
          console.log("[Auth] Getting Firebase ID token...");
          const idToken = await currentUser.getIdToken();
          console.log("[Auth] Got ID token, length:", idToken.length);
          setToken(idToken);
          localStorage.setItem('token', idToken);

          // Set Axios Default
          axios.defaults.headers.common['Authorization'] = `Bearer ${idToken}`;

          // Sync with Backend (Get detailed profile)
          console.log("[Auth] Fetching backend profile...");
          await fetchBackendProfile(idToken);
        } catch (error) {
          console.error("[Auth] Error syncing user:", error);
          toast.error("Failed to sync user profile");
        }
      } else {
        console.log("[Auth] Firebase auth state changed: user logged out");
        setFirebaseUser(null);
        // Don't clear token/user here if token exists in localStorage (backend OAuth flow)
        if (!localStorage.getItem('token')) {
          setToken(null);
          setUser(null);
          localStorage.removeItem('token');
          delete axios.defaults.headers.common['Authorization'];
        }
      }
      setLoading(false);
    });

    return () => unsubscribe();
  }, []);

  // 2. If token exists but user doesn't, fetch user profile (handles backend OAuth)
  useEffect(() => {
    if (token && !user && !firebaseUser) {
      fetchBackendProfile(token).catch(err => {
        console.warn('Failed to fetch profile with existing token:', err);
      });
    }
  }, [token, user, firebaseUser]);

  // 2. Fetch User Profile from MongoDB (Backend)
  const fetchBackendProfile = async (idToken) => {
    const attempt = async () => {
      const response = await axios.get(`${API}/auth/me`, {
        headers: { Authorization: `Bearer ${idToken}` },
        timeout: 8000,
      });
      setUser(response.data);
      setUserContext(response.data);
    };

    try {
      await attempt();
    } catch (firstError) {
      console.warn('Backend profile fetch failed, retrying in 2s...', firstError?.message);
      // Retry once after 2 seconds (backend may still be warming up)
      await new Promise(r => setTimeout(r, 2000));
      try {
        await attempt();
      } catch (secondError) {
        console.error('Failed to fetch backend profile after retry:', secondError);
        if (secondError?.response?.status === 401) {
          // Stale or expired token — clear it so the user can log in fresh
          localStorage.removeItem('token');
          delete axios.defaults.headers.common['Authorization'];
          setToken(null);
          setUser(null);
          console.warn('Cleared stale token — user must log in again');
        } else if (secondError?.code === 'ERR_NETWORK' || secondError?.code === 'ECONNREFUSED') {
          toast.error('Cannot reach server. Please make sure the backend is running.');
        } else {
          toast.error('Failed to load your profile. Please refresh the page.');
        }
        // Don't setUser — force PrivateRoute to show clear feedback
      }
    }
  };

  // 3. Login Actions
  const loginWithGoogle = async () => {
    try {
      console.log("[Auth] Starting Google Sign-In...");
      // Use Firebase signInWithPopup — onAuthStateChanged will handle the rest
      // (token storage, backend sync, user state)
      const result = await signInWithPopup(auth, googleProvider);
      console.log("[Auth] Google Sign-In successful, user:", result.user.email);
      return true;
    } catch (error) {
      console.error("[Auth] Google login failed:", error.code, error.message);
      if (error.code === 'auth/popup-blocked') {
        toast.error("Popup was blocked. Please allow popups and try again.");
      } else if (error.code === 'auth/popup-closed-by-user') {
        // User closed the popup, don't show error
        console.log("[Auth] User closed Google Sign-In popup");
      } else if (error.code === 'auth/network-request-failed') {
        toast.error("Network error. Please check your internet connection.");
      } else {
        toast.error(`Google login failed: ${error.message}`);
      }
      throw error;
    }
  };

  const login = async (email, password, cfTurnstileToken = null) => {
    try {
      const credential = await signInWithEmailAndPassword(auth, email, password);
      // If Turnstile token is present, notify the backend so it can validate it
      // (backend enforces this only when TURNSTILE_ENABLED=true)
      if (cfTurnstileToken) {
        try {
          const idToken = await credential.user.getIdToken();
          await axios.post(
            `${API}/auth/login`,
            { cf_turnstile_token: cfTurnstileToken },
            { headers: { Authorization: `Bearer ${idToken}` } },
          );
        } catch (backendErr) {
          console.warn('Turnstile backend validation error:', backendErr?.response?.data);
          // Re-throw only if backend explicitly rejected the Turnstile check (403)
          if (backendErr?.response?.status === 403) throw backendErr;
        }
      }
      return true;
    } catch (error) {
      console.error("Login error:", error);
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
      // Create user in Firebase
      const credential = await createUserWithEmailAndPassword(auth, email, password);

      // Notify backend of signup (includes Turnstile token when provided)
      // Backend enforces Turnstile only when TURNSTILE_ENABLED=true
      if (cfTurnstileToken) {
        try {
          const idToken = await credential.user.getIdToken();
          await axios.post(
            `${API}/auth/signup`,
            { cf_turnstile_token: cfTurnstileToken },
            { headers: { Authorization: `Bearer ${idToken}` } },
          );
        } catch (backendErr) {
          console.warn('Signup Turnstile backend error:', backendErr?.response?.data);
          if (backendErr?.response?.status === 403) throw backendErr;
        }
      }

      // onAuthStateChanged will handle backend sync automatically
      return true;
    } catch (error) {
      console.error("Signup error:", error);
      if (error?.response?.status === 403) {
        toast.error("Bot protection check failed. Please refresh and try again.");
      } else {
        toast.error(error.message);
      }
      throw error;
    }
  };

  const logout = async () => {
    try {
      // Clear state and storage BEFORE signOut so onAuthStateChanged
      // doesn't skip cleanup due to the localStorage token check
      localStorage.removeItem('token');
      delete axios.defaults.headers.common['Authorization'];
      setToken(null);
      setUser(null);
      setFirebaseUser(null);
      await signOut(auth);
    } catch (error) {
      console.error('Logout error:', error);
      // Even if signOut fails, ensure local state is cleared
      localStorage.removeItem('token');
      delete axios.defaults.headers.common['Authorization'];
      setToken(null);
      setUser(null);
      setFirebaseUser(null);
    }
  };

  // Helper to force token refresh if needed.
  // Works for both Firebase users (refreshes Firebase token) and
  // plain JWT users (re-fetches backend profile with the existing token).
  const refreshUser = async () => {
    if (firebaseUser) {
      const idToken = await firebaseUser.getIdToken(true);
      setToken(idToken);
      localStorage.setItem('token', idToken);
      await fetchBackendProfile(idToken);
    } else if (token) {
      await fetchBackendProfile(token);
    }
  };

  return (
    <AuthContext.Provider value={{
      user, // MongoDB Profile
      firebaseUser, // Firebase User
      loading,
      login,
      signup,
      loginWithGoogle,
      logout,
      token,
      setToken,
      setUser,
      refreshUser
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