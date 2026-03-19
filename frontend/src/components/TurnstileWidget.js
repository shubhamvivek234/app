import React, { useEffect, useRef } from 'react';

/**
 * TurnstileWidget — renders a Cloudflare Turnstile challenge widget.
 *
 * Props:
 *   onVerify(token: string) — called with the cf-turnstile-response token
 *                             when the challenge is successfully solved.
 *   onError()               — optional, called on widget error.
 *   onExpire()              — optional, called when the token expires.
 *   theme                   — "light" | "dark" | "auto"  (default: "auto")
 *
 * The Cloudflare Turnstile script is loaded lazily on first mount and
 * shared across all widget instances on the page.
 *
 * Site key is read from the REACT_APP_TURNSTILE_SITE_KEY env var.
 */
const SITE_KEY = process.env.REACT_APP_TURNSTILE_SITE_KEY || '';
const SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
const SCRIPT_ID = 'cf-turnstile-script';

let scriptPromise = null;

function loadTurnstileScript() {
  if (scriptPromise) return scriptPromise;

  scriptPromise = new Promise((resolve, reject) => {
    if (document.getElementById(SCRIPT_ID)) {
      // Script tag already present — wait for turnstile object
      const poll = setInterval(() => {
        if (window.turnstile) {
          clearInterval(poll);
          resolve(window.turnstile);
        }
      }, 50);
      return;
    }

    const script = document.createElement('script');
    script.id = SCRIPT_ID;
    script.src = SCRIPT_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => {
      const poll = setInterval(() => {
        if (window.turnstile) {
          clearInterval(poll);
          resolve(window.turnstile);
        }
      }, 50);
    };
    script.onerror = () => {
      scriptPromise = null;
      reject(new Error('Failed to load Cloudflare Turnstile script'));
    };
    document.head.appendChild(script);
  });

  return scriptPromise;
}

const TurnstileWidget = ({
  onVerify,
  onError,
  onExpire,
  theme = 'auto',
}) => {
  const containerRef = useRef(null);
  const widgetIdRef = useRef(null);

  useEffect(() => {
    if (!SITE_KEY) {
      console.warn('TurnstileWidget: REACT_APP_TURNSTILE_SITE_KEY is not set');
      return;
    }

    let mounted = true;

    loadTurnstileScript()
      .then((turnstile) => {
        if (!mounted || !containerRef.current) return;

        widgetIdRef.current = turnstile.render(containerRef.current, {
          sitekey: SITE_KEY,
          theme,
          callback: (token) => {
            if (onVerify) onVerify(token);
          },
          'error-callback': () => {
            if (onError) onError();
          },
          'expired-callback': () => {
            if (onExpire) onExpire();
          },
        });
      })
      .catch((err) => {
        console.error('TurnstileWidget: failed to initialise widget', err);
        if (onError) onError();
      });

    return () => {
      mounted = false;
      if (widgetIdRef.current !== null && window.turnstile) {
        try {
          window.turnstile.remove(widgetIdRef.current);
        } catch (_) {
          // Ignore cleanup errors
        }
        widgetIdRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      ref={containerRef}
      style={{ margin: '12px 0' }}
    />
  );
};

export default TurnstileWidget;
