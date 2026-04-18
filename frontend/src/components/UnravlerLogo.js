import React from 'react';
import { cn } from "@/lib/utils";

const KEYFRAMES = `
@keyframes unravler-float-top {
  0%, 100% { transform: translateY(0px) scale(1); }
  50% { transform: translateY(-1.5px) scale(1.03); }
}
@keyframes unravler-float-bot {
  0%, 100% { transform: translateY(0px) scale(1); }
  50% { transform: translateY(1.5px) scale(1.03); }
}
@keyframes unravler-breathe {
  0%, 100% { filter: drop-shadow(0 4px 6px rgba(168, 85, 247, 0.3)); transform: scale(1); }
  50% { filter: drop-shadow(0 8px 12px rgba(168, 85, 247, 0.5)); transform: scale(1.015); }
}
`;

const UnravlerLogo = ({ size = 'default', showText = true, className = '', darkText = false }) => {
  // Inject keyframes globally
  React.useEffect(() => {
    if (!document.getElementById('urvl-purple-styles')) {
      const style = document.createElement('style');
      style.id = 'urvl-purple-styles';
      style.textContent = KEYFRAMES;
      document.head.appendChild(style);
    }
  }, []);

  // Increased overall sizing to make the logo a little bigger
  const sizes = {
    small:   { icon: 28, fontSize: 'text-[1.1rem]' },
    default: { icon: 40, fontSize: 'text-[1.6rem]' },
    large:   { icon: 56, fontSize: 'text-[2.2rem]' },
    xl:      { icon: 76, fontSize: 'text-[3rem]' },
  };

  const { icon: iconSize, fontSize } = sizes[size] || sizes.default;

  // Text adapts to light/dark themes
  const textClasses = darkText ? 'text-slate-900' : 'text-slate-900 dark:text-white';

  return (
    <div
      className={cn("flex items-center select-none", className)}
      style={{ gap: iconSize * 0.25 }}
    >
      <svg
        width={iconSize}
        height={iconSize}
        viewBox="0 0 44 40"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ flexShrink: 0, overflow: 'visible' }}
      >
        <defs>
          <linearGradient id="unravler-purple" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#c084fc" />   {/* purple-400 */}
            <stop offset="50%" stopColor="#a855f7" />  {/* purple-500 */}
            <stop offset="100%" stopColor="#7e22ce" /> {/* purple-700 */}
          </linearGradient>

          {/* Shadow so white circles are visible on pure white backgrounds */}
          <filter id="circle-shadow-purple" x="-50%" y="-50%" width="200%" height="200%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#000000" floodOpacity="0.12" />
          </filter>
        </defs>

        <g style={{ animation: 'unravler-breathe 4s ease-in-out infinite', transformOrigin: 'center' }}>
          
          {/* Half-Circle / Semi-Circle (Flat edge at X=20) */}
          <path
            d="M 20,8 A 12,12 0 0,0 20,32 Z"
            fill="url(#unravler-purple)"
          />

          {/* Top White Node - Same size (r=6), with a 1.5 unit gap (center X=27.5, left edge=21.5) */}
          <g style={{ animation: 'unravler-float-top 5s ease-in-out infinite', transformOrigin: '27.5px 14px' }}>
            <circle
              cx="27.5"
              cy="14"
              r="6"
              fill="#ffffff"
              filter="url(#circle-shadow-purple)"
            />
          </g>

          {/* Bottom White Node - Same size (r=6), with a 1.5 unit gap */}
          <g style={{ animation: 'unravler-float-bot 5s ease-in-out infinite', transformOrigin: '27.5px 26px' }}>
            <circle
              cx="27.5"
              cy="26"
              r="6"
              fill="#ffffff"
              filter="url(#circle-shadow-purple)"
            />
          </g>

        </g>
      </svg>

      {showText && (
        <span
          className={cn("font-bold tracking-tight", textClasses, fontSize)}
          style={{ 
             letterSpacing: '-0.02em', 
             fontFamily: "'Manrope', 'Inter', sans-serif",
             transform: 'translateY(1px)' // perfectly align with center of logo visual
          }}
        >
          Unravler
        </span>
      )}
    </div>
  );
};

export default UnravlerLogo;
