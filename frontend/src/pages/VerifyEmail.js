import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { applyActionCode, checkActionCode, reload } from 'firebase/auth';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import UnravlerLogo from '@/components/UnravlerLogo';
import { auth } from '@/firebase';
import { resendVerificationEmail, getIdToken, exchangeSession } from '@/services/authService';
import { useAuth } from '@/context/AuthContext';

const VerifyEmail = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { firebaseUser, user, setUser, setToken } = useAuth();
  const [status, setStatus] = useState('idle');
  const [resending, setResending] = useState(false);

  const mode = searchParams.get('mode');
  const oobCode = searchParams.get('oobCode');
  const continueTarget = searchParams.get('returnTo');
  const sent = searchParams.get('sent') === '1';

  const nextHref = useMemo(() => {
    if (continueTarget) return continueTarget;
    if (!user) return '/login';
    if (!user.onboarding_completed) return '/onboarding';
    if (user.subscription_status === 'free') return '/onboarding/pricing';
    return '/dashboard';
  }, [continueTarget, user]);

  useEffect(() => {
    const syncVerifiedSession = async () => {
      if (!firebaseUser) return;
      await reload(firebaseUser);
      const freshToken = await getIdToken(firebaseUser);
      setToken(freshToken);
      const profile = await exchangeSession(freshToken);
      setUser(profile);
      sessionStorage.removeItem('post_signup_verify_email');
      return profile;
    };

    const verifyEmail = async () => {
      if (mode !== 'verifyEmail' || !oobCode) {
        setStatus(sent ? 'pending' : user?.email_verified ? 'verified' : 'pending');
        return;
      }

      setStatus('verifying');

      try {
        await checkActionCode(auth, oobCode);
        await applyActionCode(auth, oobCode);
        await syncVerifiedSession();
        setStatus('success');
        toast.success('Email verified successfully.');
      } catch (error) {
        console.error('[VerifyEmail] Verification failed', error);
        setStatus('error');
        toast.error('The verification link is invalid or has expired.');
      }
    };

    verifyEmail();
  }, [firebaseUser, mode, oobCode, sent, setToken, setUser, user?.email_verified]);

  const handleResend = async () => {
    if (!firebaseUser) {
      toast.error('Please sign in again to resend the verification email.');
      return;
    }
    setResending(true);
    try {
      await resendVerificationEmail(firebaseUser);
      toast.success('Verification email sent. Check your inbox.');
      setStatus('pending');
    } catch (error) {
      console.error('[VerifyEmail] Resend failed', error);
      toast.error(error?.message || 'Could not resend verification email.');
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="min-h-screen bg-white px-4 py-8">
      <div className="mx-auto flex min-h-[80vh] max-w-3xl items-center justify-center">
        <div className="w-full rounded-[28px] border border-slate-200 bg-white p-8 shadow-[0_30px_80px_rgba(15,23,42,0.08)] sm:p-10">
          <div className="mb-8 flex items-center justify-between">
            <UnravlerLogo width={140} height={38} />
            <Link to="/login" className="text-sm font-medium text-slate-500 transition hover:text-indigo-600">
              Back to login
            </Link>
          </div>

          {status === 'verifying' && (
            <div className="text-center">
              <div className="mx-auto mb-5 h-12 w-12 animate-spin rounded-full border-b-2 border-indigo-600" />
              <h2 className="text-2xl font-semibold text-slate-900">Verifying your email…</h2>
              <p className="mt-3 text-sm text-slate-500">Please wait while we confirm your address.</p>
            </div>
          )}

          {status === 'success' && (
            <div className="text-center">
              <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-full bg-green-100">
                <svg className="h-6 w-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h2 className="text-2xl font-semibold text-slate-900">Email verified</h2>
              <p className="mt-3 text-sm text-slate-500">
                Your email is confirmed. You can now connect accounts, publish, schedule posts, and invite teammates.
              </p>
              <Button onClick={() => navigate(nextHref)} className="mt-6 w-full">
                Continue
              </Button>
            </div>
          )}

          {status === 'pending' && (
            <div>
              <h2 className="text-2xl font-semibold text-slate-900">Verify your email</h2>
              <p className="mt-3 text-sm leading-6 text-slate-500">
                {sent
                  ? 'We sent a verification email. Open the link in that message to unlock account connections, publishing, scheduling, and team invites.'
                  : 'Your account is signed in, but sensitive actions stay locked until your email is verified.'}
              </p>
              <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                Once you verify, refreshing the app will sync your session automatically.
              </div>
              <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                <Button onClick={handleResend} disabled={resending} className="w-full sm:w-auto">
                  {resending ? 'Sending…' : 'Resend verification email'}
                </Button>
                <Button variant="outline" onClick={() => navigate(nextHref)} className="w-full sm:w-auto">
                  Continue anyway
                </Button>
              </div>
            </div>
          )}

          {status === 'verified' && (
            <div className="text-center">
              <h2 className="text-2xl font-semibold text-slate-900">Your email is already verified</h2>
              <p className="mt-3 text-sm text-slate-500">You already have full access to sensitive publishing and team features.</p>
              <Button onClick={() => navigate(nextHref)} className="mt-6 w-full">
                Continue
              </Button>
            </div>
          )}

          {status === 'error' && (
            <div className="text-center">
              <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
                <svg className="h-6 w-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <h2 className="text-2xl font-semibold text-slate-900">Verification failed</h2>
              <p className="mt-3 text-sm text-slate-500">
                The verification link is invalid or has expired. Request a fresh email and try again.
              </p>
              <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                <Button onClick={handleResend} disabled={resending} className="w-full sm:w-auto">
                  {resending ? 'Sending…' : 'Resend verification email'}
                </Button>
                <Button variant="outline" onClick={() => navigate('/login')} className="w-full sm:w-auto">
                  Back to login
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default VerifyEmail;
