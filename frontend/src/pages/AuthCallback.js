import React, { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import axios from 'axios';
import { toast } from 'sonner';
import Cookies from 'js-cookie';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const AuthCallback = () => {
  const navigate = useNavigate();
  const { setUser, setToken } = useAuth();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const processCallback = async () => {
      const sessionId = searchParams.get('session_id');
      const tokenParam = searchParams.get('token');

      if (tokenParam) {
        // Direct OAuth Flow
        try {
          // Set cookie and localStorage
          Cookies.set('session_token', tokenParam, { expires: 7 });
          localStorage.setItem('token', tokenParam);

          // Update auth context
          // This will trigger the AuthContext to fetch the user profile
          setToken(tokenParam);

          // Navigate to dashboard - PrivateRoute will redirect to /onboarding if needed
          // based on the user's fetched profile (onboarding_completed status)
          toast.success('Successfully logged in!');
          navigate('/dashboard');
        } catch (error) {
          console.error('Auth callback error:', error);
          toast.error('Authentication failed');
          navigate('/login');
        }
        return;
      }

      // Legacy Proxy Flow (Fallback)
      if (!sessionId) {
        toast.error('Invalid authentication response');
        navigate('/login');
        return;
      }

      try {
        const response = await axios.post(`${BACKEND_URL}/api/auth/google/callback`, {
          session_id: sessionId
        });

        const { session_token, user } = response.data;

        // Set cookie
        Cookies.set('session_token', session_token, { expires: 7 });

        // Update auth context
        setToken(session_token);
        setUser(user);

        // Check if onboarding is completed
        if (user.onboarding_completed) {
          toast.success('Welcome back!');
          navigate('/dashboard');
        } else {
          toast.success('Welcome! Let\'s get you set up.');
          navigate('/onboarding');
        }
      } catch (error) {
        console.error('Auth callback error:', error);
        toast.error('Authentication failed');
        navigate('/login');
      }
    };

    processCallback();
  }, [searchParams, navigate, setUser, setToken]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
        <p className="text-slate-600">Completing sign in...</p>
      </div>
    </div>
  );
};

export default AuthCallback;