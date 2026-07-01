import React, { useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '@/context/AuthContext';
import { exchangeMagicLink } from '@/lib/api';

const MagicLogin = () => {
  const { token } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user, loginWithCustomToken, loading: authLoading } = useAuth();
  
  const [status, setStatus] = useState('authenticating'); // authenticating | success | error
  const [errorMsg, setErrorMsg] = useState('');
  
  const postId = searchParams.get('post_id');

  useEffect(() => {
    // If user is already logged in, skip token verification and redirect immediately
    if (user && !authLoading) {
      const destination = postId ? `/approvals?post_id=${encodeURIComponent(postId)}` : '/approvals';
      navigate(destination);
      return;
    }

    if (!token) {
      setStatus('error');
      setErrorMsg('No login token was provided in the link.');
      return;
    }

    const processLogin = async () => {
      try {
        setStatus('authenticating');
        const data = await exchangeMagicLink(token);
        
        if (data.custom_token) {
          await loginWithCustomToken(data.custom_token);
          setStatus('success');
          
          const destination = postId ? `/approvals?post_id=${encodeURIComponent(postId)}` : '/approvals';
          setTimeout(() => {
            navigate(destination);
          }, 800);
        } else {
          throw new Error('No custom login token returned from server.');
        }
      } catch (err) {
        console.error('Magic link exchange failed:', err);
        setStatus('error');
        setErrorMsg(err.response?.data?.detail || 'This login link is invalid, expired, or has already been used.');
        toast.error('Failed to log in via Magic Link');
      }
    };

    processLogin();
  }, [token, user, authLoading, loginWithCustomToken, navigate, postId]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="text-center">
          <span className="text-xl font-bold tracking-tight text-slate-900">Unravler</span>
        </div>

        <div className="mt-8 flex flex-col items-center text-center">
          {status === 'authenticating' && (
            <>
              <div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-indigo-600" />
              <h2 className="mt-6 text-lg font-semibold text-slate-900">Logging you in...</h2>
              <p className="mt-2 text-sm text-slate-500">Securing your session. Please hold on.</p>
            </>
          )}

          {status === 'success' && (
            <>
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h2 className="mt-6 text-lg font-semibold text-slate-900">Success!</h2>
              <p className="mt-2 text-sm text-slate-500">Redirecting to your approvals dashboard.</p>
            </>
          )}

          {status === 'error' && (
            <>
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-100 text-rose-600">
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <h2 className="mt-6 text-lg font-semibold text-slate-900">Login Link Expired</h2>
              <p className="mt-2 text-sm text-slate-500">{errorMsg}</p>
              <button
                onClick={() => navigate('/login')}
                className="mt-6 w-full rounded-xl bg-slate-900 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
              >
                Go to Login
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default MagicLogin;
