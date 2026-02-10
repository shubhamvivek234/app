import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import axios from 'axios';

const OAuthCallback = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState('processing');

  useEffect(() => {
    const handleOAuthCallback = async () => {
      const code = searchParams.get('code');
      const state = searchParams.get('state');
      const error = searchParams.get('error');

      if (error) {
        setStatus('error');
        toast.error(`OAuth error: ${error}`);
        setTimeout(() => navigate('/onboarding/connect'), 2000);
        return;
      }

      if (!code || !state) {
        setStatus('error');
        toast.error('Invalid OAuth callback');
        setTimeout(() => navigate('/onboarding/connect'), 2000);
        return;
      }

      try {
        const token = localStorage.getItem('token');
        const apiUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';
        const platform = sessionStorage.getItem('oauth_platform');
        const returnTo = sessionStorage.getItem('oauth_return_to');

        if (!platform) {
          throw new Error('Platform information not found');
        }

        // Prepare callback data
        const callbackData = { code };

        // For Twitter, include code_verifier
        if (platform === 'twitter') {
          const codeVerifier = sessionStorage.getItem('twitter_code_verifier');
          if (codeVerifier) {
            callbackData.code_verifier = codeVerifier;
            sessionStorage.removeItem('twitter_code_verifier');
          }
        }

        // Send callback to backend
        const response = await axios.post(
          `${apiUrl}/api/oauth/${platform}/callback`,
          callbackData,
          {
            headers: { Authorization: `Bearer ${token}` },
            withCredentials: true,
          }
        );

        if (response.data.success) {
          setStatus('success');
          toast.success(`${response.data.platform} connected successfully!`);
          
          // Clean up session storage
          sessionStorage.removeItem('oauth_platform');
          sessionStorage.removeItem('oauth_return_to');

          // Redirect based on return destination
          setTimeout(() => {
            if (returnTo === 'onboarding') {
              navigate('/onboarding/connect');
            } else {
              navigate('/accounts');
            }
          }, 1500);
        }
      } catch (error) {
        console.error('OAuth callback error:', error);
        setStatus('error');
        
        if (error.response?.status === 500 && error.response?.data?.detail?.includes('not configured')) {
          toast.error('API credentials not configured. Please contact administrator.');
        } else {
          toast.error(error.response?.data?.detail || 'Failed to connect account');
        }
        
        setTimeout(() => navigate('/onboarding/connect'), 2000);
      }
    };

    handleOAuthCallback();
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-white rounded-xl shadow-sm border border-border p-8 text-center">
        {status === 'processing' && (
          <>
            <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-green-500 mx-auto mb-4"></div>
            <h2 className="text-2xl font-bold text-slate-900 mb-2">Connecting your account...</h2>
            <p className="text-slate-600">Please wait while we complete the connection.</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-slate-900 mb-2">Successfully Connected!</h2>
            <p className="text-slate-600">Redirecting you back...</p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-slate-900 mb-2">Connection Failed</h2>
            <p className="text-slate-600">Redirecting you back...</p>
          </>
        )}
      </div>
    </div>
  );
};

export default OAuthCallback;
