import React, { useState, useEffect } from 'react';
import { Mail, Cookie, ShieldCheck, X, AlertCircle, Loader2, ChevronDown } from 'lucide-react';

export default function ConnectLinkedInModal({ isOpen, onClose, onAccountConnected }) {
  const [authMode, setAuthMode] = useState(null); // 'email' | 'cookie' | null
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [cookieValue, setCookieValue] = useState('');
  const [liAValue, setLiAValue] = useState('');
  const [premiumProduct, setPremiumProduct] = useState('classic');
  const [userAgent, setUserAgent] = useState('');
  const [countryCode, setCountryCode] = useState('US');
  const [twoFactorSession, setTwoFactorSession] = useState(null);
  const [twoFactorCode, setTwoFactorCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (typeof navigator !== 'undefined') {
      setUserAgent(navigator.userAgent || '');
    }
  }, []);

  // Reset internal states when opened
  useEffect(() => {
    if (isOpen) {
      setAuthMode(null);
      setError(null);
      setTwoFactorSession(null);
      setTwoFactorCode('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleConnectCookie = async (e) => {
    e.preventDefault();
    if (!cookieValue.trim()) {
      setError('Please enter your li_at session cookie');
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
          li_a: liAValue.trim(),
          premium_product: premiumProduct,
          user_agent: userAgent.trim(),
          country_code: countryCode,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to connect LinkedIn account');
      }

      if (onAccountConnected) onAccountConnected(data);
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
        if (onAccountConnected) onAccountConnected(data.account);
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

      if (onAccountConnected) onAccountConnected(data.account);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
      <div className="relative w-full max-w-[480px] rounded-2xl bg-white p-7 shadow-2xl border border-gray-100 transition-all">
        {/* Close Button top right */}
        <button
          onClick={onClose}
          className="absolute right-5 top-5 rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 border border-gray-200/80 transition-colors"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>

        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-xl bg-red-50 p-3 text-xs sm:text-sm text-red-600 border border-red-200">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* SCREEN 1: Choose Mode (media_1790020960165.png) */}
        {authMode === null && (
          <div>
            <div className="mb-6 pr-6">
              <h2 className="text-xl font-bold text-gray-900 tracking-tight">Connect LinkedIn</h2>
              <p className="mt-1 text-xs sm:text-sm text-gray-500 leading-relaxed">
                Connect the account you send from. We never store your credentials.
              </p>
            </div>

            <div className="space-y-3.5">
              {/* Email and password */}
              <button
                type="button"
                onClick={() => { setAuthMode('email'); setError(null); }}
                className="w-full text-left flex items-start gap-4 rounded-xl border border-gray-200 p-4 transition-all hover:border-indigo-400 hover:bg-indigo-50/10 group cursor-pointer"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#eeecff] text-[#635bff] group-hover:scale-105 transition-transform">
                  <Mail className="h-5 w-5" />
                </div>
                <div className="flex-1">
                  <h3 className="font-bold text-gray-900 text-sm">Email and password</h3>
                  <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
                    Sign in with your LinkedIn login. We may ask for a 2FA code to keep your account safe.
                  </p>
                </div>
              </button>

              {/* Session Cookie */}
              <button
                type="button"
                onClick={() => { setAuthMode('cookie'); setError(null); }}
                className="w-full text-left flex items-start gap-4 rounded-xl border border-gray-200 p-4 transition-all hover:border-indigo-400 hover:bg-amber-50/10 group cursor-pointer"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#fef7ee] text-[#d97706] group-hover:scale-105 transition-transform">
                  <Cookie className="h-5 w-5" />
                </div>
                <div className="flex-1">
                  <h3 className="font-bold text-gray-900 text-sm">Session Cookie</h3>
                  <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
                    Already signed in? Paste your li_at session cookie instead. Best for Sales Navigator and Recruiter.
                  </p>
                </div>
              </button>
            </div>
          </div>
        )}

        {/* SCREEN 2: Connect with Session Cookie (media_1790104087386.png) */}
        {authMode === 'cookie' && (
          <form onSubmit={handleConnectCookie}>
            <div className="mb-5 pr-6">
              <h2 className="text-xl font-bold text-gray-900 tracking-tight">Connect with session cookie</h2>
              <p className="mt-1 text-xs text-gray-500">
                Paste your cookie from a browser where you are signed in.
              </p>
            </div>

            <div className="space-y-4">
              {/* li_at session cookie */}
              <div>
                <label className="block text-xs font-semibold text-gray-900 mb-1.5">
                  li_at session cookie
                </label>
                <input
                  type="text"
                  value={cookieValue}
                  onChange={(e) => setCookieValue(e.target.value)}
                  placeholder="Value of the li_at cookie"
                  className="w-full rounded-xl border border-gray-200/90 px-3.5 py-2.5 text-xs sm:text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors"
                />
                <p className="mt-1 text-[11px] text-gray-500 leading-normal">
                  From linkedin.com → DevTools → Application → Cookies → copy the <span className="text-gray-700 font-mono">li_at</span> value.
                </p>
              </div>

              {/* li_a cookie (optional, Sales Navigator / Recruiter) */}
              <div>
                <label className="block text-xs font-semibold text-gray-900 mb-1.5">
                  li_a cookie <span className="font-normal text-gray-500">(optional, Sales Navigator / Recruiter)</span>
                </label>
                <input
                  type="text"
                  value={liAValue}
                  onChange={(e) => setLiAValue(e.target.value)}
                  className="w-full rounded-xl border border-gray-200/90 px-3.5 py-2.5 text-xs sm:text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors"
                />
              </div>

              {/* Premium product */}
              <div>
                <label className="block text-xs font-semibold text-gray-900 mb-1.5">
                  Premium product
                </label>
                <div className="relative">
                  <select
                    value={premiumProduct}
                    onChange={(e) => setPremiumProduct(e.target.value)}
                    className="w-full rounded-xl border border-gray-200/90 bg-white px-3.5 py-2.5 text-xs sm:text-sm text-gray-900 appearance-none focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 pr-10 cursor-pointer"
                  >
                    <option value="classic">Classic only</option>
                    <option value="sales_navigator">Sales Navigator</option>
                    <option value="recruiter">Recruiter</option>
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                </div>
                <p className="mt-1 text-[11px] text-gray-500 leading-normal">
                  Choose Sales Navigator or Recruiter only if this account has that product. All other LinkedIn Premium plans use Classic.
                </p>
              </div>

              {/* Browser user agent */}
              <div>
                <label className="block text-xs font-semibold text-gray-900 mb-1.5">
                  Browser user agent
                </label>
                <input
                  type="text"
                  value={userAgent}
                  onChange={(e) => setUserAgent(e.target.value)}
                  className="w-full rounded-xl border border-gray-200/90 px-3.5 py-2.5 text-xs text-gray-700 placeholder:text-gray-400 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono truncate"
                />
                <p className="mt-1 text-[11px] text-gray-500 leading-normal">
                  Prefilled from this browser. Use the same browser you copied the cookie from.
                </p>
              </div>
            </div>

            {/* Bottom Actions */}
            <div className="flex items-center gap-3 pt-6 mt-6">
              <button
                type="button"
                onClick={() => { setAuthMode(null); setError(null); }}
                className="flex-1 rounded-xl border border-gray-200 bg-white py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-colors shadow-2xs"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-[#8280f6] hover:bg-[#7270e6] py-2.5 text-sm font-semibold text-white disabled:opacity-50 transition-colors shadow-2xs"
              >
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                {loading ? 'Connecting...' : 'Continue'}
              </button>
            </div>
          </form>
        )}

        {/* SCREEN 3A: Email & Password Form */}
        {authMode === 'email' && !twoFactorSession && (
          <form onSubmit={handleStartLogin}>
            <div className="mb-5 pr-6">
              <h2 className="text-xl font-bold text-gray-900 tracking-tight">Sign in with email</h2>
              <p className="mt-1 text-xs text-gray-500">
                Enter your credentials to connect your LinkedIn account.
              </p>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-900 mb-1.5">
                  LinkedIn Email *
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@company.com"
                  className="w-full rounded-xl border border-gray-200/90 px-3.5 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-900 mb-1.5">
                  Password *
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full rounded-xl border border-gray-200/90 px-3.5 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>

            {/* Bottom Actions */}
            <div className="flex items-center gap-3 pt-6 mt-6">
              <button
                type="button"
                onClick={() => { setAuthMode(null); setError(null); }}
                className="flex-1 rounded-xl border border-gray-200 bg-white py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-colors shadow-2xs"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-[#8280f6] hover:bg-[#7270e6] py-2.5 text-sm font-semibold text-white disabled:opacity-50 transition-colors shadow-2xs"
              >
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                {loading ? 'Signing in...' : 'Continue'}
              </button>
            </div>
          </form>
        )}

        {/* SCREEN 3B: 2FA Challenge */}
        {authMode === 'email' && twoFactorSession && (
          <form onSubmit={handleVerify2FA}>
            <div className="text-center py-2 mb-4">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-indigo-600 mb-3">
                <ShieldCheck className="h-6 w-6" />
              </div>
              <h3 className="font-bold text-gray-900 text-lg">Two-Factor Authentication</h3>
              <p className="text-xs text-gray-500 mt-1 max-w-xs mx-auto">
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

            <div className="flex items-center gap-3 pt-6 mt-4">
              <button
                type="button"
                onClick={() => { setTwoFactorSession(null); setError(null); }}
                className="flex-1 rounded-xl border border-gray-200 bg-white py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-colors shadow-2xs"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-[#8280f6] hover:bg-[#7270e6] py-2.5 text-sm font-semibold text-white disabled:opacity-50 transition-colors shadow-2xs"
              >
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                {loading ? 'Verifying...' : 'Verify & Connect'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
