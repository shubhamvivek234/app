import React, { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';

const AuthCallback = () => {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const processCallback = async () => {
      const sessionId = searchParams.get('session_id');
      const tokenParam = searchParams.get('token');

      if (tokenParam) {
        // Direct OAuth Flow — token stored, let Firebase onAuthStateChanged handle the rest
        try {
          localStorage.setItem('token', tokenParam);
          toast.success('Successfully logged in!');
          navigate('/dashboard');
        } catch (error) {
          console.error('Auth callback error:', error);
          toast.error('Authentication failed');
          navigate('/login');
        }
        return;
      }

      if (!sessionId) {
        toast.error('Invalid authentication response');
        navigate('/login');
        return;
      }

      // Legacy session-based flow — just refresh and redirect
      try {
        await refreshUser();
        toast.success('Welcome back!');
        navigate('/dashboard');
      } catch (error) {
        console.error('Auth callback error:', error);
        toast.error('Authentication failed');
        navigate('/login');
      }
    };

    processCallback();
  }, [searchParams, navigate, refreshUser]);

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