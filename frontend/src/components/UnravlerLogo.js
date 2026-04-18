import React from 'react';
import { cn } from "@/lib/utils";

const KEYFRAMES = `
@keyframes unravler-layer-breathe {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}
@keyframes unravler-layer-breathe-mid {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-1.5px); }
}
`;

const UnravlerLogo = ({ 
  size = 'default', 
  showText = true, 
  className = '', 
  darkText = false 
}) => {
  // Inject subtle keyframes for a premium 3D hover/breathe effect
  React.useEffect(() => {
    if (!document.getElementById('urvl-buffer-styles')) {
      const style = document.createElement('style');
      style.id = 'urvl-buffer-styles';
      style.textContent = KEYFRAMES;
      document.head.appendChild(style);
    }
  }, []);

  // Proportional sizing mapped exactly to the elegant Buffer-style layout
  const sizes = {
    small:   { icon: 24, fontSize: 'text-[1.25rem]' },
    default: { icon: 38, fontSize: 'text-[2.1rem]'  },
    large:   { icon: 52, fontSize: 'text-[2.8rem]'  },
    xl:      { icon: 72, fontSize: 'text-[4rem]'    },
  };

  const { icon: iconSize, fontSize } = sizes[size] || sizes.default;

  // Adaptive text color for light/dark mode
  const textClasses = darkText ? 'text-slate-800' : 'text-slate-800 dark:text-white';

  return (
    <div
      className={cn("flex items-center select-none", className)}
      style={{ gap: iconSize * 0.35 }}
    >
      <svg
        width={iconSize}
        height={iconSize * 1.05} // Slightly taller viewbox to fit the stack gracefully
        viewBox="0 0 100 100"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ flexShrink: 0, overflow: 'visible' }}
        className="group" // allows hover effects if you want them
      >
        <defs>
          {/* Deep premium purple gradient to match your app's branding but with the Buffer structure */}
          <linearGradient id="buffer-purple-grad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#9333ea" />  {/* purple-600 */}
            <stop offset="100%" stopColor="#6b21a8" /> {/* purple-800 */}
          </linearGradient>
          
          <linearGradient id="buffer-purple-light" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#a855f7" />  {/* purple-500 */}
            <stop offset="100%" stopColor="#7e22ce" /> {/* purple-700 */}
          </linearGradient>

          {/* Optional soft shadow for depth */}
          <filter id="stack-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="8" stdDeviation="6" floodColor="#9333ea" floodOpacity="0.15" />
          </filter>
        </defs>

        <g filter="url(#stack-shadow)">
          {/* TOP LAYER (Solid Rhombus) 
              Center X=50. Y spans from 8 to 48.
          */}
          <path
            d="M 50 8 L 90 28 L 50 48 L 10 28 Z"
            fill="url(#buffer-purple-light)"
            stroke="url(#buffer-purple-light)"
            strokeWidth="3"
            strokeLinejoin="round"
            style={{ animation: 'unravler-layer-breathe 4s ease-in-out infinite' }}
          />

          {/* MIDDLE LAYER (Chevron) 
              Shifted down. Gap = 8. Thickness = 14.
          */}
          <path
            d="M 10 36 L 50 56 L 90 36 L 90 50 L 50 70 L 10 50 Z"
            fill="url(#buffer-purple-grad)"
            stroke="url(#buffer-purple-grad)"
            strokeWidth="3"
            strokeLinejoin="round"
            style={{ animation: 'unravler-layer-breathe-mid 4s ease-in-out infinite' }}
          />

          {/* BOTTOM LAYER (Chevron) 
              Shifted down again.
          */}
          <path
            d="M 10 58 L 50 78 L 90 58 L 90 72 L 50 92 L 10 72 Z"
            fill="url(#buffer-purple-grad)"
            stroke="url(#buffer-purple-grad)"
            strokeWidth="3"
            strokeLinejoin="round"
          />
        </g>
      </svg>

      {showText && (
        <span
          className={cn("font-black tracking-tight", textClasses, fontSize)}
          style={{ 
             letterSpacing: '-0.04em', // super tight tracking like the Buffer text
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
