import React, { createContext, useState, useContext, useEffect } from 'react';
import axios from 'axios';
import { auth, googleProvider } from '@/firebase';
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
  const [token, setToken] = useState(null);

  // 1. Listen for Firebase Auth Changes
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
      setLoading(true);
      if (currentUser) {
        setFirebaseUser(currentUser);
        try {
          // Get ID Token
          const idToken = await currentUser.getIdToken();
          setToken(idToken);
          localStorage.setItem('token', idToken);

          // Set Axios Default
          axios.defaults.headers.common['Authorization'] = `Bearer ${idToken}`;

          // Sync with Backend (Get detailed profile)
          await fetchBackendProfile(idToken);
        } catch (error) {
          console.error("Error syncing user:", error);
          toast.error("Failed to sync user profile");
        }
      } else {
        setFirebaseUser(null);
        setToken(null);
        setUser(null);
        localStorage.removeItem('token');
        delete axios.defaults.headers.common['Authorization'];
      }
      setLoading(false);
    });

    return () => unsubscribe();
  }, []);

  // 2. Fetch User Profile from MongoDB (Backend)
  const fetchBackendProfile = async (idToken) => {
    const attempt = async () => {
      const response = await axios.get(`${API}/auth/me`, {
        headers: { Authorization: `Bearer ${idToken}` },
        timeout: 8000,
      });
      setUser(response.data);
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
        if (secondError?.code === 'ERR_NETWORK' || secondError?.code === 'ECONNREFUSED') {
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
      await signInWithPopup(auth, googleProvider);
      return true;
    } catch (error) {
      console.error("Google login error:", error);
      toast.error(error.message);
      throw error;
    }
  };

  const login = async (email, password) => {
    try {
      await signInWithEmailAndPassword(auth, email, password);
      return true;
    } catch (error) {
      console.error("Login error:", error);
      toast.error("Invalid email or password");
      throw error;
    }
  };

  const signup = async (email, password, name) => {
    try {
      // Create user in Firebase
      const result = await createUserWithEmailAndPassword(auth, email, password);

      // Optionally update Firebase Profile Display Name immediately
      // await updateProfile(result.user, { displayName: name });
      // The backend sync will happen automatically on auth state change listener

      return true;
    } catch (error) {
      console.error("Signup error:", error);
      toast.error(error.message);
      throw error;
    }
  };

  const logout = async () => {
    try {
      await signOut(auth);
      // State cleanup handled by onAuthStateChanged
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  // Helper to force token refresh if needed
  const refreshUser = async () => {
    if (firebaseUser) {
      const idToken = await firebaseUser.getIdToken(true);
      setToken(idToken);
      await fetchBackendProfile(idToken);
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