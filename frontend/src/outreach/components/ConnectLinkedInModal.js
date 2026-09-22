import React, { useState } from 'react';
import { Mail, Cookie, ShieldCheck, ArrowRight, X, AlertCircle, Loader2 } from 'lucide-react';

export default function ConnectLinkedInModal({ isOpen, onClose, onAccountConnected }) {
  const [authMode, setAuthMode] = useState(null); // 'email' | 'cookie' | null
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [cookieValue, setCookieValue] = useState('');
  const [jsessionId, setJsessionId] = useState('');
  const [countryCode, setCountryCode] = useState('US');
  const [twoFactorSession, setTwoFactorSession] = useState(null);
  const [twoFactorCode, setTwoFactorCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleConnectCookie = async (e) => {
    e.preventDefault();
    if (!cookieValue.trim()) {
      setError('Please paste your li_at session cookie');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/accounts/connect-cookie', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          li_at: cookieValue.trim(),
          jsession_id: jsessionId.trim(),
          country_code: countryCode,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to connect LinkedIn account');
      }

      onAccountConnected(data);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleStartLogin = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please enter both email and password');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/accounts/login-start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          email: email.trim(),
          password,
          country_code: countryCode,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Login failed');
      }

      if (data.status === '2fa_required') {
        setTwoFactorSession(data.session_id);
      } else if (data.status === 'authenticated') {
        onAccountConnected(data.account);
        onClose();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleVerify2FA = async (e) => {
    e.preventDefault();
    if (!twoFactorCode.trim()) {
      setError('Please enter the 6-digit code');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/accounts/login-verify-2fa', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          session_id: twoFactorSession,
          code: twoFactorCode.trim(),
          country_code: countryCode,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Verification code failed');
      }

      onAccountConnected(data.account);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl border border-gray-100 transition-all">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 rounded-full p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
        >
          <X className="h-5 w-5" />
        </button>

        {/* Modal Header */}
        <div className="mb-6">
          <h2 className="text-xl font-bold text-gray-900">Connect LinkedIn</h2>
          <p className="mt-1 text-sm text-gray-500">
            Connect the account you send from. We never store your credentials in plain text.
          </p>
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-600 border border-red-200">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Screen 1: Choose Mode */}
        {authMode === null && (
          <div className="space-y-3">
            {/* Email & Password Card */}
            <button
              type="button"
              onClick={() => { setAuthMode('email'); setError(null); }}
              className="w-full text-left flex items-start gap-4 rounded-xl border border-gray-200 p-4 transition-all hover:border-indigo-500 hover:bg-indigo-50/20 group"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                <Mail className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-gray-900 group-hover:text-indigo-600">Email and password</h3>
                <p className="text-xs text-gray-500 mt-0.5">
                  Sign in with your LinkedIn login. We may ask for a 2FA code to keep your account safe.
                </p>
              </div>
              <ArrowRight className="h-4 w-4 text-gray-400 group-hover:text-indigo-600 mt-1" />
            </button>

            {/* Session Cookie Card */}
            <button
              type="button"
              onClick={() => { setAuthMode('cookie'); setError(null); }}
              className="w-full text-left flex items-start gap-4 rounded-xl border border-gray-200 p-4 transition-all hover:border-indigo-500 hover:bg-indigo-50/20 group"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-600 group-hover:bg-amber-600 group-hover:text-white transition-colors">
                <Cookie className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-gray-900 group-hover:text-amber-600">Session Cookie</h3>
                <p className="text-xs text-gray-500 mt-0.5">
                  Already signed in? Paste your li_at session cookie instead. Best for Sales Navigator and Recruiter.
                </p>
              </div>
              <ArrowRight className="h-4 w-4 text-gray-400 group-hover:text-amber-600 mt-1" />
            </button>
          </div>
        )}

        {/* Screen 2A: Session Cookie Form */}
        {authMode === 'cookie' && (
          <form onSubmit={handleConnectCookie} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-gray-700">
                li_at Cookie Value *
              </label>
              <input
                type="password"
                value={cookieValue}
                onChange={(e) => setCookieValue(e.target.value)}
                placeholder="AQEDAT..."
                className="mt-1.5 w-full rounded-xl border border-gray-300 px-3.5 py-2.5 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 font-mono"
              />
              <p className="mt-1 text-xs text-gray-400">
                Found in Chrome DevTools: Application → Cookies → linkedin.com → li_at.
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-gray-700">
                Country for Residential Proxy
              </label>
              <select
                value={countryCode}
                onChange={(e) => setCountryCode(e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-gray-300 px-3.5 py-2.5 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 bg-white"
              >
                <option value="US">United States</option>
                <option value="GB">United Kingdom</option>
                <option value="CA">Canada</option>
                <option value="DE">Germany</option>
                <option value="FR">France</option>
                <option value="IN">India</option>
                <option value="AU">Australia</option>
              </select>
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={() => { setAuthMode(null); setError(null); }}
                className="text-xs font-medium text-gray-500 hover:text-gray-800"
              >
                Back
              </button>
              <button
                type="submit"
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-sm"
              >
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                Connect Account
              </button>
            </div>
          </form>
        )}

        {/* Screen 2B: Email/Password Form (or 2FA) */}
        {authMode === 'email' && !twoFactorSession && (
          <form onSubmit={handleStartLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-gray-700">
                LinkedIn Email *
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
                className="mt-1.5 w-full rounded-xl border border-gray-300 px-3.5 py-2.5 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-gray-700">
                Password *
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="mt-1.5 w-full rounded-xl border border-gray-300 px-3.5 py-2.5 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-gray-700">
                Country for Residential Proxy
              </label>
              <select
                value={countryCode}
                onChange={(e) => setCountryCode(e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-gray-300 px-3.5 py-2.5 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 bg-white"
              >
                <option value="US">United States</option>
                <option value="GB">United Kingdom</option>
                <option value="CA">Canada</option>
                <option value="DE">Germany</option>
                <option value="FR">France</option>
                <option value="IN">India</option>
                <option value="AU">Australia</option>
              </select>
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={() => { setAuthMode(null); setError(null); }}
                className="text-xs font-medium text-gray-500 hover:text-gray-800"
              >
                Back
              </button>
              <button
                type="submit"
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-sm"
              >
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                Continue
              </button>
            </div>
          </form>
        )}

        {/* Screen 2C: 2FA Verification Challenge */}
        {authMode === 'email' && twoFactorSession && (
          <form onSubmit={handleVerify2FA} className="space-y-4">
            <div className="text-center py-2">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 text-indigo-600 mb-3">
                <ShieldCheck className="h-6 w-6" />
              </div>
              <h3 className="font-bold text-gray-900">Two-Factor Authentication</h3>
              <p className="text-xs text-gray-500 mt-1">
                Enter the 6-digit verification code sent to your phone or authenticator app.
              </p>
            </div>

            <div>
              <input
                type="text"
                maxLength={6}
                value={twoFactorCode}
                onChange={(e) => setTwoFactorCode(e.target.value)}
                placeholder="123456"
                className="w-full text-center tracking-widest text-2xl font-bold rounded-xl border border-gray-300 py-3 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={() => { setTwoFactorSession(null); setError(null); }}
                className="text-xs font-medium text-gray-500 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-sm"
              >
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                Verify & Connect
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
