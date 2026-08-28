import React from 'react';

const SIZES = {
  small: 28,
  default: 40,
  large: 56,
  xl: 72,
};

const BrandMarkLoader = ({ 
  className = '', 
  size = 'xl', 
  fullScreen = true,
  overlay = false,
  label = 'Unravler'
}) => {
  const markSize = SIZES[size] || SIZES.xl;
  const isFullScreen = fullScreen || overlay;

  return (
    <div
      className={`${
        isFullScreen
          ? 'fixed inset-0 z-[999999] flex h-screen w-screen min-h-screen min-w-full flex-col items-center justify-center bg-[#fcfbf9] select-none'
          : 'relative flex flex-col items-center justify-center select-none py-6'
      } ${className}`}
      role="status"
      aria-live="polite"
      aria-label="Loading"
    >
      <style>{`
        @keyframes unravlerRibbonWave {
          0%, 100% {
            transform: scaleX(0.92) translateX(-2px);
            opacity: 0.28;
          }
          50% {
            transform: scaleX(1.04) translateX(2px);
            opacity: 1;
          }
        }

        @keyframes unravlerPulseBreath {
          0%, 100% {
            transform: scale(0.98);
            opacity: 0.92;
          }
          50% {
            transform: scale(1.03);
            opacity: 1;
          }
        }

        .unravler-loader-path-1 {
          animation: unravlerRibbonWave 2s cubic-bezier(0.4, 0, 0.2, 1) infinite 0.0s;
          transform-origin: center;
        }
        .unravler-loader-path-2 {
          animation: unravlerRibbonWave 2s cubic-bezier(0.4, 0, 0.2, 1) infinite 0.2s;
          transform-origin: center;
        }
        .unravler-loader-path-3 {
          animation: unravlerRibbonWave 2s cubic-bezier(0.4, 0, 0.2, 1) infinite 0.4s;
          transform-origin: center;
        }
        .unravler-loader-path-4 {
          animation: unravlerRibbonWave 2s cubic-bezier(0.4, 0, 0.2, 1) infinite 0.6s;
          transform-origin: center;
        }

        .unravler-logo-shell {
          animation: unravlerPulseBreath 2.8s ease-in-out infinite;
        }

        @media (prefers-reduced-motion: reduce) {
          .unravler-loader-path-1,
          .unravler-loader-path-2,
          .unravler-loader-path-3,
          .unravler-loader-path-4,
          .unravler-logo-shell {
            animation: none !important;
            transform: none !important;
            opacity: 1 !important;
          }
        }
      `}</style>

      {/* Pure Black Logo Mark without any outer circles or semicircular lines */}
      <div 
        className="unravler-logo-shell flex items-center justify-center"
        style={{ width: markSize, height: markSize }}
      >
        <svg 
          viewBox="0 0 256 256" 
          className="w-full h-full text-black"
          fill="#000000"
          role="img" 
          aria-label="Unravler mark"
        >
          {/* Ribbon 1 */}
          <path 
            className="unravler-loader-path-1"
            d="M30 64c18-13 42-15 72-14h36c32 1 57-4 78-20 6-5 12-1 12 7v22c0 9-7 17-18 21-32 11-68 7-105 4-31-3-56 0-75 15V64Z"
          />
          {/* Ribbon 2 */}
          <path 
            className="unravler-loader-path-2"
            d="M30 106c19-14 44-15 75-13h40c31 0 52-5 72-19 6-4 11-1 11 6v23c0 9-7 17-18 20-32 11-68 7-105 4-31-3-56 0-75 15v-36Z"
          />
          {/* Ribbon 3 */}
          <path 
            className="unravler-loader-path-3"
            d="M30 148c19-14 44-15 75-13h40c31 0 52-5 72-19 6-4 11-1 11 6v23c0 9-7 17-18 20-32 11-68 7-105 4-31-3-56 0-75 15v-36Z"
          />
          {/* Ribbon 4 */}
          <path 
            className="unravler-loader-path-4"
            d="M30 191c19-14 44-15 75-13h40c31 0 52-5 72-19 6-4 11-1 11 6v23c0 10-8 20-21 25-32 13-69 6-105 3-30-3-54 2-72 20v-45Z"
          />
        </svg>
      </div>

      {/* Clean Status indicator */}
      {label && size !== 'small' && (
        <div className="mt-4 flex items-center gap-1.5 text-xs font-medium tracking-wide text-black/75">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-black animate-pulse" />
          <span>{label}</span>
        </div>
      )}
    </div>
  );
};

export default BrandMarkLoader;
