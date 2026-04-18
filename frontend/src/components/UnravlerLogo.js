import React from 'react';

const KEYFRAMES = `
@keyframes unravler-float-top {
  0%, 100% { transform: translateY(0px) scale(1); }
  50% { transform: translateY(-2px) scale(1.05); }
}
@keyframes unravler-float-bot {
  0%, 100% { transform: translateY(0px) scale(1); }
  50% { transform: translateY(2px) scale(1.05); }
}
@keyframes unravler-breathe {
  0%, 100% { filter: drop-shadow(0 4px 6px rgba(34,197,94,0.3)); transform: scale(1); }
  50% { filter: drop-shadow(0 8px 12px rgba(34,197,94,0.5)); transform: scale(1.02); }
}
`;

const UnravlerLogo = ({ size = 'default', showText = true, className = '', darkText = false }) => {
  // Inject keyframes globally
  React.useEffect(() => {
    if (!document.getElementById('urvl-exact-styles')) {
      const style = document.createElement('style');
      style.id = 'urvl-exact-styles';
      style.textContent = KEYFRAMES;
      document.head.appendChild(style);
    }
  }, []);

  const sizes = {
    small: { icon: 24, fontSize: 'text-base' },
    default: { icon: 32, fontSize: 'text-xl' },
    large: { icon: 48, fontSize: 'text-3xl' },
    xl: { icon: 64, fontSize: 'text-4xl' },
  };

  const { icon: iconSize, fontSize } = sizes[size] || sizes.default;

  // Base text color logic.
  // Tailwind "text-slate-900 dark:text-white" handles global dark mode automatically!
  // If 'darkText' is explicitly passed as true, we force dark. Otherwise, let Tailwind handle it.
  const textClasses = darkText ? 'text-slate-900' : 'text-slate-900 dark:text-white';

  return (
    <div
      className={`flex items-center select-none ${className}`}
      style={{ display: 'flex', alignItems: 'center', gap: iconSize * 0.25 }}
    >
      <svg
        width={iconSize}
        height={iconSize}
        viewBox="0 0 40 40"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ flexShrink: 0, overflow: 'visible' }}
      >
        <defs>
          <linearGradient id="shodwe-green" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#22c55e" /> {/* bright green */}
            <stop offset="100%" stopColor="#15803d" /> {/* deeper green */}
          </linearGradient>

          {/* Shadow for circles so they show up on white backgrounds */}
          <filter id="circle-shadow" x="-50%" y="-50%" width="200%" height="200%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#000000" floodOpacity="0.15" />
          </filter>
        </defs>

        {/* Group with breathing glow animation */}
        <g style={{ animation: 'unravler-breathe 4s ease-in-out infinite', transformOrigin: 'center' }}>
          
          {/* Half-Circle / Semi-Circle */}
          <path
            d="M 21,8 A 12,12 0 0,0 21,32 Z"
            fill="url(#shodwe-green)"
          />

          {/* Top White Circle */}
          <g style={{ animation: 'unravler-float-top 5s ease-in-out infinite', transformOrigin: '27px 14px' }}>
            <circle
              cx="27"
              cy="14"
              r="6"
              fill="#ffffff"
              filter="url(#circle-shadow)"
            />
          </g>

          {/* Bottom White Circle */}
          <g style={{ animation: 'unravler-float-bot 5s ease-in-out infinite', transformOrigin: '27px 26px' }}>
            <circle
              cx="27"
              cy="26"
              r="6"
              fill="#ffffff"
              filter="url(#circle-shadow)"
            />
          </g>

        </g>
      </svg>

      {showText && (
        <span
          className={`font-extrabold tracking-tight ${textClasses}`}
          style={{ letterSpacing: '-0.035em' }}
        >
          Unravler
        </span>
      )}
    </div>
  );
};

export default UnravlerLogo;
