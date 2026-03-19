import React, { useState, useEffect } from 'react';

const CONSENT_KEY = 'se_cookie_consent';

const CookieConsent = () => {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const consent = localStorage.getItem(CONSENT_KEY);
    if (!consent) {
      // Show after a short delay
      const timer = setTimeout(() => setShow(true), 1500);
      return () => clearTimeout(timer);
    }
  }, []);

  const acceptAll = () => {
    localStorage.setItem(CONSENT_KEY, JSON.stringify({
      essential: true, analytics: true, marketing: false,
      timestamp: new Date().toISOString(),
    }));
    setShow(false);
  };

  const acceptEssential = () => {
    localStorage.setItem(CONSENT_KEY, JSON.stringify({
      essential: true, analytics: false, marketing: false,
      timestamp: new Date().toISOString(),
    }));
    setShow(false);
  };

  if (!show) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 p-4 bg-slate-900 text-white shadow-2xl border-t border-slate-700">
      <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-start sm:items-center gap-4">
        <div className="flex-1">
          <p className="text-sm font-medium mb-1">We use cookies</p>
          <p className="text-xs text-slate-300">
            We use essential cookies to make our site work and analytics cookies to understand how you use it.
            See our{' '}
            <a href="/privacy" className="underline hover:text-white">Privacy Policy</a>.
          </p>
        </div>
        <div className="flex gap-2 flex-shrink-0">
          <button
            onClick={acceptEssential}
            className="px-4 py-2 text-xs bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
          >
            Essential Only
          </button>
          <button
            onClick={acceptAll}
            className="px-4 py-2 text-xs bg-indigo-600 hover:bg-indigo-500 rounded-lg font-medium transition-colors"
          >
            Accept All
          </button>
        </div>
      </div>
    </div>
  );
};

export default CookieConsent;
