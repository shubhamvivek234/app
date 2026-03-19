import React, { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import axios from 'axios';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * AuthCallback — handles backend OAuth redirect flow.
 *
 * Used when the backend (e.g. /api/auth/google/login) completes an OAuth
 * exchange and redirects to /auth/callback?token=JWT.
 *
 * Primary Google login now uses Firebase signInWithPopup (no redirect needed).
 * This component handles fallback/legacy backend OAuth flows only.
 */
const AuthCallback = () => {
  const navigate = useNavigate();
  const { setUser, setToken } = useAuth();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const processCallback = async () => {
      const tokenParam = searchParams.get('token');
      const errorParam = searchParams.get('error');

      // Handle backend error redirect (e.g. /auth/callback?error=auth_failed)
      if (errorParam) {
        toast.error('Authentication failed. Please try again.');
        navigate('/login');
        return;
      }

      if (!tokenParam) {
        toast.error('Invalid authentication response');
        navigate('/login');
        return;
      }

      try {
        // Store token and set axios header
        localStorage.setItem('token', tokenParam);
        setToken(tokenParam);
        axios.defaults.headers.common['Authorization'] = `Bearer ${tokenParam}`;

        // Fetch backend profile with the new token
        const response = await axios.get(`${BACKEND_URL}/api/auth/me`, {
          headers: { Authorization: `Bearer ${tokenParam}` },
          timeout: 8000,
        });
        const user = response.data;
        setUser(user);

        // Redirect based on user state
        if (user.subscription_status === 'active' || user.onboarding_completed) {
          toast.success('Welcome back!');
          navigate('/dashboard');
        } else {
          toast.success("Welcome! Let's get you set up.");
          navigate('/onboarding');
        }
      } catch (error) {
        console.error('Auth callback error:', error);
        // Clear any partial state
        localStorage.removeItem('token');
        delete axios.defaults.headers.common['Authorization'];
        toast.error('Authentication failed. Please try again.');
        navigate('/login');
      }
    };

    processCallback();
  }, [searchParams, navigate, setUser, setToken]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-offwhite">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
        <p className="text-slate-600">Completing sign in...</p>
      </div>
    </div>
  );
};

export default AuthCallback;
