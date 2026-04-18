import React, { useEffect, useRef } from 'react';

const KEYFRAMES = `
@keyframes unravler-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50%       { transform: scale(1.08); opacity: 0.85; }
}
@keyframes unravler-glow {
  0%, 100% { filter: drop-shadow(0 0 4px rgba(16,185,129,0.5)) drop-shadow(0 0 8px rgba(16,185,129,0.2)); }
  50%       { filter: drop-shadow(0 0 8px rgba(16,185,129,0.9)) drop-shadow(0 0 16px rgba(16,185,129,0.4)); }
}
@keyframes unravler-orbit-top {
  0%   { transform: translate(0px, 0px); }
  25%  { transform: translate(1.5px, -1.5px); }
  50%  { transform: translate(0px, -2px); }
  75%  { transform: translate(-1.5px, -1.5px); }
  100% { transform: translate(0px, 0px); }
}
@keyframes unravler-orbit-bottom {
  0%   { transform: translate(0px, 0px); }
  25%  { transform: translate(-1.5px, 1.5px); }
  50%  { transform: translate(0px, 2px); }
  75%  { transform: translate(1.5px, 1.5px); }
  100% { transform: translate(0px, 0px); }
}
@keyframes unravler-shimmer {
  0%   { background-position: -200% center; }
  100% { background-position:  200% center; }
}
`;

const UnravlerLogo = ({ size = 'default', showText = true, className = '', darkText = false }) => {
  const styleRef = useRef(null);

  useEffect(() => {
    if (!document.getElementById('unravler-logo-styles')) {
      const style = document.createElement('style');
      style.id = 'unravler-logo-styles';
      style.textContent = KEYFRAMES;
      document.head.appendChild(style);
      styleRef.current = style;
    }
    return () => {
      // keep the style tag alive globally – multiple logos may exist
    };
  }, []);

  const scales = {
    small:   { icon: 28, fontSize: 14 },
    default: { icon: 38, fontSize: 20 },
    large:   { icon: 54, fontSize: 28 },
    xl:      { icon: 72, fontSize: 38 },
  };
  const { icon: iconSize, fontSize } = scales[size] || scales.default;

  // ── colours ──────────────────────────────────────────────────────────────
  const greenDark  = '#059669';
  const greenLight = '#34d399';
  const nodeColor  = darkText ? '#059669' : '#ffffff';
  const nodeStroke = darkText ? '#059669' : 'rgba(255,255,255,0.3)';
  const textColor  = darkText ? '#111827' : '#ffffff';

  return (
    <div
      className={`flex items-center ${className}`}
      style={{ display: 'flex', alignItems: 'center', gap: iconSize * 0.22 }}
    >
      {/* ── Icon ──────────────────────────────────────────────────────────── */}
      <svg
        width={iconSize}
        height={iconSize}
        viewBox="0 0 40 40"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{
          flexShrink: 0,
          animation: 'unravler-glow 3s ease-in-out infinite',
        }}
      >
        <defs>
          <linearGradient id="urvl-half" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%"   stopColor={greenLight} />
            <stop offset="100%" stopColor={greenDark}  />
          </linearGradient>
          <radialGradient id="urvl-node-top" cx="40%" cy="35%" r="60%">
            <stop offset="0%"   stopColor="#ffffff" stopOpacity="1" />
            <stop offset="100%" stopColor="#d1fae5" stopOpacity="0.85" />
          </radialGradient>
          <radialGradient id="urvl-node-bot" cx="40%" cy="35%" r="60%">
            <stop offset="0%"   stopColor="#ffffff" stopOpacity="1" />
            <stop offset="100%" stopColor="#a7f3d0" stopOpacity="0.85" />
          </radialGradient>
          <filter id="urvl-shadow">
            <feDropShadow dx="0" dy="1" stdDeviation="1.5" floodColor="#059669" floodOpacity="0.4" />
          </filter>
        </defs>

        {/* Half-circle (left half of a 26-px circle centred at 14,20) */}
        <path
          d="M14,6 A14,14 0 0,1 14,34 Z"
          fill="url(#urvl-half)"
          style={{ animation: 'unravler-pulse 4s ease-in-out infinite' }}
        />

        {/* Top node */}
        <g style={{ animation: 'unravler-orbit-top 5s ease-in-out infinite', transformOrigin: '28px 13px' }}>
          <circle
            cx="28" cy="13" r="6.5"
            fill={darkText ? 'none' : 'url(#urvl-node-top)'}
            stroke={darkText ? greenDark : 'rgba(255,255,255,0.2)'}
            strokeWidth={darkText ? 2 : 0.5}
            filter="url(#urvl-shadow)"
          />
        </g>

        {/* Bottom node (smaller) */}
        <g style={{ animation: 'unravler-orbit-bottom 5s ease-in-out infinite', transformOrigin: '27px 28px' }}>
          <circle
            cx="27" cy="28" r="5"
            fill={darkText ? 'none' : 'url(#urvl-node-bot)'}
            stroke={darkText ? greenLight : 'rgba(255,255,255,0.2)'}
            strokeWidth={darkText ? 2 : 0.5}
            filter="url(#urvl-shadow)"
          />
        </g>
      </svg>

      {/* ── Text ──────────────────────────────────────────────────────────── */}
      {showText && (
        <span
          style={{
            fontSize,
            fontWeight: 800,
            letterSpacing: '-0.03em',
            lineHeight: 1,
            color: textColor,
            background: darkText
              ? 'linear-gradient(90deg, #059669 0%, #10b981 40%, #059669 100%)'
              : 'linear-gradient(90deg, #ffffff 0%, #d1fae5 40%, #ffffff 60%, #d1fae5 80%, #ffffff 100%)',
            backgroundSize: '200% auto',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            animation: 'unravler-shimmer 4s linear infinite',
          }}
        >
          Unravler
        </span>
      )}
    </div>
  );
};

export default UnravlerLogo;
