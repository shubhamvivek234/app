import React from 'react';
import { cn } from "@/lib/utils";

const KEYFRAMES = `
@keyframes unravler-brand-spin {
  0%   { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
@keyframes unravler-brand-pulse {
  0%, 100% { transform: scale(1); filter: drop-shadow(0 4px 12px rgba(168, 85, 247, 0.4)); opacity: 1; }
  50%      { transform: scale(1.05); filter: drop-shadow(0 8px 24px rgba(168, 85, 247, 0.7)); opacity: 0.9; }
}
`;

const UnravlerLogo = ({ 
  size = 'default', 
  showText = true, 
  className = '', 
  darkText = false 
}) => {
  // Inject subtle keyframes once
  React.useEffect(() => {
    if (!document.getElementById('urvl-elegant-styles')) {
      const style = document.createElement('style');
      style.id = 'urvl-elegant-styles';
      style.textContent = KEYFRAMES;
      document.head.appendChild(style);
    }
  }, []);

  // Reduced sizing as requested
  const sizes = {
    small:   { icon: 20, fontSize: 'text-[1.1rem]' },
    default: { icon: 28, fontSize: 'text-[1.5rem]' },
    large:   { icon: 42, fontSize: 'text-[2.2rem]' },
    xl:      { icon: 56, fontSize: 'text-[3rem]'   },
  };

  const { icon: iconSize, fontSize } = sizes[size] || sizes.default;
  const textClasses = darkText ? 'text-slate-800' : 'text-slate-800 dark:text-white';

  return (
    <div
      className={cn("flex items-center select-none", className)}
      style={{ gap: iconSize * 0.35 }}
    >
      {/* ── New Abstract Design: The Dynamic "Untangled Nexus" ── */}
      <svg
        width={iconSize}
        height={iconSize}
        viewBox="0 0 100 100"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ flexShrink: 0, overflow: 'visible' }}
        className="group"
      >
        <defs>
          <linearGradient id="nexusGrad1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#a855f7" />  {/* purple-500 */}
            <stop offset="100%" stopColor="#d946ef" /> {/* fuchsia-500 */}
          </linearGradient>
          <linearGradient id="nexusGrad2" x1="100%" y1="100%" x2="0%" y2="0%">
            <stop offset="0%" stopColor="#7e22ce" />  {/* purple-700 */}
            <stop offset="100%" stopColor="#ec4899" /> {/* pink-500 */}
          </linearGradient>
          <linearGradient id="nexusGrad3" x1="100%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#c084fc" />   {/* purple-400 */}
            <stop offset="100%" stopColor="#4f46e5" /> {/* indigo-600 */}
          </linearGradient>

          <filter id="nexusShadow">
            <feDropShadow dx="0" dy="4" stdDeviation="4" floodColor="#a855f7" floodOpacity="0.3" />
          </filter>
        </defs>

        <g style={{ transformOrigin: '50% 50%', animation: 'unravler-brand-pulse 6s ease-in-out infinite' }}>
          
          {/* A majestic intertwining abstract shape representing an unraveling thread or nexus */}
          
          {/* Top Left Sweeping Arc */}
          <path 
            d="M 50 15 C 30 15, 15 30, 25 50 C 35 70, 70 30, 80 50 C 85 60, 75 80, 50 85" 
            fill="none" 
            stroke="url(#nexusGrad1)" 
            strokeWidth="12" 
            strokeLinecap="round" 
            filter="url(#nexusShadow)"
          />

          {/* Overlapping connecting ring/loop */}
          <circle 
            cx="40" 
            cy="45" 
            r="20" 
            fill="none" 
            stroke="url(#nexusGrad2)" 
            strokeWidth="10" 
            opacity="0.8"
            style={{ transformOrigin: '40px 45px', animation: 'unravler-brand-spin 12s linear infinite' }}
          />

          {/* Central floating node / spark */}
          <circle 
            cx="65" 
            cy="60" 
            r="8" 
            fill="url(#nexusGrad3)" 
            filter="url(#nexusShadow)"
          />
        </g>
      </svg>

      {/* ── Text remains identical to your previous strict tracking setup ── */}
      {showText && (
        <span
          className={cn("font-black tracking-tight", textClasses, fontSize)}
          style={{ 
             letterSpacing: '-0.04em',
             fontFamily: "'Inter', sans-serif"
          }}
        >
          Unravler
        </span>
      )}
    </div>
  );
};

export default UnravlerLogo;
