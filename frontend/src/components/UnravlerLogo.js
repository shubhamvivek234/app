import React from 'react';

// Unravler Logo Component — glowing spiral nodes icon
const UnravlerLogo = ({ size = 'default', showText = true, className = '' }) => {
  const iconSizes = {
    small: { box: 24, text: 'text-base' },
    default: { box: 32, text: 'text-xl' },
    large: { box: 48, text: 'text-3xl' },
    xl: { box: 64, text: 'text-4xl' },
  };

  const { box, text: textClass } = iconSizes[size] || iconSizes.default;

  return (
    <div className={`flex items-center gap-2 ${className}`} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      {/* SVG Icon with glow effect */}
      <svg
        width={box}
        height={box}
        viewBox="0 0 40 40"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ flexShrink: 0 }}
      >
        <defs>
          {/* Outer glow filter */}
          <filter id="unravler-glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          {/* Strong glow for nodes */}
          <filter id="node-glow" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="1.5" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          {/* Gradient for the spirals */}
          <linearGradient id="spiralGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#7c3aed" />
            <stop offset="50%" stopColor="#a855f7" />
            <stop offset="100%" stopColor="#c084fc" />
          </linearGradient>
          {/* Gradient for nodes */}
          <radialGradient id="nodeGrad" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#e9d5ff" />
            <stop offset="100%" stopColor="#a855f7" />
          </radialGradient>
        </defs>

        {/* Outer arc — main unravel loop */}
        <path
          d="M20 4 C10 4, 4 11, 4 20 C4 29, 11 36, 20 36"
          stroke="url(#spiralGrad)"
          strokeWidth="2.5"
          strokeLinecap="round"
          fill="none"
          filter="url(#unravler-glow)"
          opacity="0.9"
        />
        {/* Middle arc */}
        <path
          d="M20 9 C13 9, 9 14, 9 20 C9 26, 13 31, 20 31"
          stroke="url(#spiralGrad)"
          strokeWidth="2"
          strokeLinecap="round"
          fill="none"
          filter="url(#unravler-glow)"
          opacity="0.75"
        />
        {/* Inner arc */}
        <path
          d="M20 14 C16 14, 14 17, 14 20 C14 23, 16 26, 20 26"
          stroke="url(#spiralGrad)"
          strokeWidth="1.5"
          strokeLinecap="round"
          fill="none"
          filter="url(#unravler-glow)"
          opacity="0.6"
        />

        {/* Connection lines from center outward */}
        <line x1="20" y1="9" x2="32" y2="6" stroke="#a855f7" strokeWidth="1.5" strokeLinecap="round" opacity="0.8" filter="url(#unravler-glow)" />
        <line x1="20" y1="31" x2="32" y2="34" stroke="#a855f7" strokeWidth="1.5" strokeLinecap="round" opacity="0.8" filter="url(#unravler-glow)" />

        {/* Floating nodes */}
        <circle cx="20" cy="20" r="2.5" fill="url(#nodeGrad)" filter="url(#node-glow)" />
        <circle cx="32" cy="6" r="3" fill="url(#nodeGrad)" filter="url(#node-glow)" />
        <circle cx="32" cy="34" r="3" fill="url(#nodeGrad)" filter="url(#node-glow)" />
        <circle cx="20" cy="36" r="2" fill="#c084fc" opacity="0.7" filter="url(#node-glow)" />
      </svg>

      {showText && (
        <span
          className={`font-bold ${textClass}`}
          style={{
            background: 'linear-gradient(135deg, #7c3aed 0%, #a855f7 50%, #c084fc 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            letterSpacing: '-0.02em',
          }}
        >
          Unravler
        </span>
      )}
    </div>
  );
};

export default UnravlerLogo;
