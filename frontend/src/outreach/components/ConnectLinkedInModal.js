import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, ChevronDown, ExternalLink, Loader2, LockKeyhole, X } from 'lucide-react';

const PROXY_COUNTRY_CODE = 'US';

const cleanToken = (value, name) => value.trim()
  .replace(new RegExp(`^${name}\\s*=`, 'i'), '')
  .replace(/^["']|["']$/g, '');

export default function ConnectLinkedInModal({ isOpen, onClose, onAccountConnected }) {
  const [cookieValue, setCookieValue] = useState('');
  const [liAValue, setLiAValue] = useState('');
  const [jsessionId, setJsessionId] = useState('');
  const [premiumProduct, setPremiumProduct] = useState('classic');
  const [userAgent, setUserAgent] = useState(() => (
    typeof navigator !== 'undefined' ? navigator.userAgent || '' : ''
  ));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const inFlight = useRef(false);
  const dialogRef = useRef(null);
  const previousFocus = useRef(null);

  useEffect(() => {
    setCookieValue('');
    setLiAValue('');
    setJsessionId('');
    setPremiumProduct('classic');
    setUserAgent(typeof navigator !== 'undefined' ? navigator.userAgent || '' : '');
    setError(null);
    if (isOpen) {
      previousFocus.current = document.activeElement;
      dialogRef.current?.focus();
    } else if (previousFocus.current) {
      previousFocus.current.focus();
      previousFocus.current = null;
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const closeModal = (afterSuccess = false) => {
    if (inFlight.current && !afterSuccess) return;
    setCookieValue('');
    setLiAValue('');
    setJsessionId('');
    setError(null);
    onClose();
  };

  const handleCookieChange = (value) => {
    if (/\bli_at\s*=/i.test(value)) {
      const entries = Object.fromEntries(value.split(';').map((part) => {
        const equalIndex = part.indexOf('=');
        if (equalIndex < 0) return ['', ''];
        return [part.slice(0, equalIndex).trim().toLowerCase(), part.slice(equalIndex + 1).trim()];
      }));
      setCookieValue(cleanToken(entries.li_at || '', 'li_at'));
      if (value.includes(';')) {
        // A newly pasted cookie header replaces the old session as a unit.
        setJsessionId(cleanToken(entries.jsessionid || '', 'JSESSIONID'));
        setLiAValue(cleanToken(entries.li_a || '', 'li_a'));
      }
      return;
    }
    setCookieValue(cleanToken(value, 'li_at'));
  };

  const handleConnectCookie = async (event) => {
    event.preventDefault();
    if (inFlight.current) return;
    if (!cookieValue.trim()) {
      setError('Please enter your li_at session cookie.');
      return;
    }
    if (!jsessionId.trim()) {
      setError('Please enter your JSESSIONID cookie.');
      return;
    }

    inFlight.current = true;
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/v1/outreach/accounts/connect-cookie', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          li_at: cookieValue.trim(),
          jsession_id: jsessionId.trim(),
          li_a: liAValue.trim(),
          premium_product: premiumProduct,
          user_agent: userAgent.trim(),
          country_code: PROXY_COUNTRY_CODE,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(typeof data?.detail === 'string' ? data.detail : 'LinkedIn session verification failed. Please try again.');
      }
      if (!data?.id) throw new Error('LinkedIn account was not confirmed. Please try again.');

      onAccountConnected?.(data);
      closeModal(true);
    } catch (connectionError) {
      setError(connectionError.message || 'LinkedIn session verification failed. Please try again.');
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="linkedin-sender-title"
        aria-describedby="linkedin-sender-description linkedin-platform-notice"
        tabIndex={-1}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            event.stopPropagation();
            closeModal();
          }
        }}
        className="relative max-h-[92vh] w-full max-w-[540px] overflow-y-auto rounded-2xl border border-gray-100 bg-white p-6 shadow-2xl sm:p-8"
      >
        <button
          type="button"
          onClick={() => closeModal()}
          disabled={loading}
          className="absolute right-6 top-6 rounded-md border border-gray-200 p-1 text-gray-400 hover:bg-gray-50 hover:text-gray-600 disabled:opacity-50"
          aria-label="Close connection dialog"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="mb-5 pr-7">
          <h2 id="linkedin-sender-title" className="text-xl font-bold tracking-tight text-gray-900">Connect LinkedIn sender</h2>
          <p id="linkedin-sender-description" className="mt-1.5 text-sm leading-relaxed text-gray-600">
            Advanced session connection for cold outreach. This is separate from official LinkedIn OAuth connections used for supported social features.
          </p>
        </div>

        <div id="linkedin-platform-notice" className="mb-4 flex gap-2.5 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed text-amber-950">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-semibold">Platform and account risk</p>
            <p className="mt-1">
              This is not an official LinkedIn OAuth connection. It uses session cookies and a dedicated residential proxy to access non-public LinkedIn interfaces. LinkedIn restricts unauthorized automation, which can lead to account restriction or suspension. A proxy does not remove that risk.{' '}
              <a href="https://www.linkedin.com/legal/user-agreement" target="_blank" rel="noopener noreferrer" className="font-semibold underline underline-offset-2">Read LinkedIn&apos;s User Agreement</a>.
            </p>
          </div>
        </div>

        <p className="mb-5 rounded-xl border border-indigo-100 bg-indigo-50 px-3 py-2.5 text-xs leading-relaxed text-indigo-950">
          Need to sign in first?{' '}
          <a href="https://www.linkedin.com/login" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold underline underline-offset-2">
            Open LinkedIn in a new tab <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </a>
          . After signing in there, return here and enter your session values manually. Browser security prevents automatic transfer.
        </p>

        {error && (
          <div role="alert" className="mb-4 flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleConnectCookie} autoComplete="off">
          <div className="space-y-4">
            <div>
              <label htmlFor="linkedin-li-at" className="mb-1.5 block text-xs font-semibold text-gray-900">li_at session cookie *</label>
              <input
                id="linkedin-li-at"
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={cookieValue}
                onChange={(event) => handleCookieChange(event.target.value)}
                placeholder="Value of the li_at cookie"
                className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
              />
              <p className="mt-1 text-[11px] text-gray-500">In your signed-in LinkedIn browser: DevTools → Application → Cookies → linkedin.com. You can also paste a full cookie header here.</p>
            </div>

            <div>
              <label htmlFor="linkedin-jsession" className="mb-1.5 block text-xs font-semibold text-gray-900">JSESSIONID cookie *</label>
              <input
                id="linkedin-jsession"
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={jsessionId}
                onChange={(event) => setJsessionId(cleanToken(event.target.value, 'JSESSIONID'))}
                placeholder="Value of the JSESSIONID cookie"
                className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
              />
              <p className="mt-1 text-[11px] text-gray-500">Required to verify the session. Pasting a full cookie header above fills this automatically.</p>
            </div>

            <div>
              <label htmlFor="linkedin-li-a" className="mb-1.5 block text-xs font-semibold text-gray-900">li_a cookie <span className="font-normal text-gray-500">(optional, Sales Navigator / Recruiter)</span></label>
              <input
                id="linkedin-li-a"
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={liAValue}
                onChange={(event) => setLiAValue(cleanToken(event.target.value, 'li_a'))}
                className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
              />
            </div>

            <div>
              <label htmlFor="linkedin-premium-product" className="mb-1.5 block text-xs font-semibold text-gray-900">Premium product</label>
              <div className="relative">
                <select
                  id="linkedin-premium-product"
                  value={premiumProduct}
                  onChange={(event) => setPremiumProduct(event.target.value)}
                  className="w-full appearance-none rounded-lg border border-gray-300 bg-white px-3.5 py-2.5 pr-10 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                >
                  <option value="classic">Classic only</option>
                  <option value="sales_navigator">Sales Navigator</option>
                  <option value="recruiter">Recruiter</option>
                </select>
                <ChevronDown className="pointer-events-none absolute right-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
              </div>
            </div>

            <p className="rounded-lg border border-gray-200 bg-gray-50 px-3.5 py-2.5 text-xs leading-relaxed text-gray-700">
              Proxy routing currently requests the United States (US). Other regions are not selectable until provider availability is verified.
            </p>

            <details className="rounded-lg border border-gray-200 px-3.5 py-2.5 text-xs text-gray-700">
              <summary className="cursor-pointer font-semibold">Connection details</summary>
              <label htmlFor="linkedin-user-agent" className="mb-1.5 mt-3 block font-semibold text-gray-900">Browser user agent</label>
              <input
                id="linkedin-user-agent"
                type="text"
                value={userAgent}
                onChange={(event) => setUserAgent(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3.5 py-2.5 font-mono text-xs text-gray-800 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
              />
              <p className="mt-1 text-[11px] text-gray-500">Prefilled from this browser. Use the same browser you copied the cookies from.</p>
            </details>
          </div>

          <div className="mt-5 flex gap-2.5 rounded-xl border border-gray-200 bg-gray-50 p-3 text-xs leading-relaxed text-gray-700">
            <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <p>Treat session cookies like a password: they can grant access to your account. Values submitted for a new connection are encrypted before storage. We do not ask for your LinkedIn password.</p>
          </div>

          <div className="mt-6 flex items-center gap-3">
            <button
              type="button"
              aria-label="Cancel connection"
              onClick={() => closeModal()}
              disabled={loading}
              className="flex-1 rounded-xl border border-gray-300 bg-white py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-[#8280f6] py-2.5 text-sm font-semibold text-white hover:bg-[#7270e6] disabled:opacity-50"
            >
              {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {loading ? 'Verifying...' : 'Verify & Connect'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
