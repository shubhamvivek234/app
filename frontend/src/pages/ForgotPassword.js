import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';

import UnravlerLogo from '@/components/UnravlerLogo';
import TurnstileWidget from '@/components/TurnstileWidget';
import { requestPasswordReset } from '@/services/authService';

const ForgotPassword = () => {
  const [email, setEmail] = useState('');
  const [turnstileToken, setTurnstileToken] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    const link = document.createElement('link');
    link.href = 'https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600&display=swap';
    link.rel = 'stylesheet';
    document.head.appendChild(link);
    return () => {
      document.head.removeChild(link);
    };
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    try {
      const response = await requestPasswordReset(email.trim(), turnstileToken);
      setSubmitted(true);
      toast.success(response?.message || 'If the address is eligible, a reset email will arrive shortly.');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Unable to start password reset right now.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-white px-4 py-8" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
      <div className="mx-auto flex min-h-[80vh] max-w-5xl items-center justify-center">
        <div className="grid w-full overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-[0_30px_80px_rgba(15,23,42,0.08)] lg:grid-cols-[1.05fr_0.95fr]">
          <div className="hidden bg-[radial-gradient(circle_at_top,_rgba(91,110,245,0.2),_transparent_45%),linear-gradient(160deg,#111827_0%,#1e293b_55%,#334155_100%)] p-10 text-white lg:block">
            <UnravlerLogo width={150} height={42} color="white" />
            <div className="mt-20 space-y-6">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-white/60">Password reset</p>
              <h1 className="max-w-md font-['Sora'] text-4xl font-semibold leading-tight">
                Recover access without exposing whether an account exists.
              </h1>
              <p className="max-w-md text-sm leading-7 text-white/75">
                Enter your email and we will send a secure Unravler password reset link if the address is eligible.
              </p>
            </div>
          </div>

          <div className="p-8 sm:p-10 lg:p-12">
            <div className="mb-8 flex items-center justify-between">
              <UnravlerLogo width={120} height={34} />
              <Link to="/login" className="text-sm font-medium text-slate-500 transition hover:text-indigo-600">
                Back to login
              </Link>
            </div>

            <div className="max-w-md">
              <h2 className="font-['Sora'] text-3xl font-semibold text-slate-900">Forgot your password?</h2>
              <p className="mt-3 text-sm leading-6 text-slate-500">
                We will send a reset link if this email can receive password reset messages for an Unravler account.
              </p>

              <form className="mt-8 space-y-5" onSubmit={handleSubmit} method="POST">
                <div>
                  <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="forgot-email">
                    Email address
                  </label>
                  <input
                    id="forgot-email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500 focus:bg-white focus:ring-4 focus:ring-indigo-100"
                    placeholder="you@example.com"
                    required
                  />
                </div>

                <TurnstileWidget
                  onVerify={setTurnstileToken}
                  onExpire={() => setTurnstileToken(null)}
                  onError={() => setTurnstileToken(null)}
                  theme="light"
                />

                <button
                  type="submit"
                  disabled={submitting || !email.trim()}
                  className="w-full rounded-xl bg-[linear-gradient(135deg,#5b6ef5,#8b5cf6)] px-4 py-3 text-sm font-semibold text-white transition hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {submitting ? 'Sending reset link…' : 'Send reset link'}
                </button>
              </form>

              <div className="mt-6 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                {submitted
                  ? 'If the address is eligible, the reset email is on the way. Check your inbox and spam folder.'
                  : 'For security, this form always shows the same response whether or not the email belongs to an account.'}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ForgotPassword;
