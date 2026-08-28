import React from 'react';

const SIZES = {
  small: { mark: 24, stage: 64, ring: 56 },
  default: { mark: 36, stage: 88, ring: 76 },
  large: { mark: 52, stage: 120, ring: 104 },
  xl: { mark: 64, stage: 148, ring: 128 },
};

const BrandMarkLoader = ({ 
  className = '', 
  size = 'xl', 
  overlay = false,
  label = 'Unravler'
}) => {
  const dims = SIZES[size] || SIZES.xl;

  return (
    <div
      className={`relative flex flex-col items-center justify-center select-none ${
        overlay
          ? 'fixed inset-0 z-[120] overflow-hidden bg-offwhite/95 backdrop-blur-[12px] dark:bg-slate-950/95'
          : ''
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

        @keyframes unravlerEchoRipple {
          0% {
            transform: translate(-50%, -50%) scale(0.68);
            opacity: 0.55;
          }
          100% {
            transform: translate(-50%, -50%) scale(1.48);
            opacity: 0;
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

        .unravler-echo-1 {
          animation: unravlerEchoRipple 2.8s cubic-bezier(0, 0.2, 0.8, 1) infinite 0.0s;
        }
        .unravler-echo-2 {
          animation: unravlerEchoRipple 2.8s cubic-bezier(0, 0.2, 0.8, 1) infinite 1.4s;
        }
        .unravler-logo-shell {
          animation: unravlerPulseBreath 2.8s ease-in-out infinite;
        }

        @media (prefers-reduced-motion: reduce) {
          .unravler-loader-path-1,
          .unravler-loader-path-2,
          .unravler-loader-path-3,
          .unravler-loader-path-4,
          .unravler-echo-1,
          .unravler-echo-2,
          .unravler-logo-shell {
            animation: none !important;
            transform: none !important;
            opacity: 1 !important;
          }
        }
      `}</style>

      {/* Stage Container */}
      <div 
        className="relative flex items-center justify-center"
        style={{ width: dims.stage, height: dims.stage }}
      >
        {/* Hairline Echo Wave Rings */}
        <div 
          className="unravler-echo-1 pointer-events-none absolute left-1/2 top-1/2 rounded-full border border-black/15 dark:border-white/15"
          style={{ width: dims.ring * 1.35, height: dims.ring * 1.35 }}
        />
        <div 
          className="unravler-echo-2 pointer-events-none absolute left-1/2 top-1/2 rounded-full border border-black/15 dark:border-white/15"
          style={{ width: dims.ring * 1.35, height: dims.ring * 1.35 }}
        />

        {/* Static Hairline Guide Ring */}
        <div 
          className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-black/8 dark:border-white/10"
          style={{ width: dims.ring, height: dims.ring }}
        />

        {/* Black Unravler Mark with Sequential Ribbon Ripple */}
        <div 
          className="unravler-logo-shell relative z-10 flex items-center justify-center"
          style={{ width: dims.mark, height: dims.mark }}
        >
          <svg 
            viewBox="0 0 256 256" 
            className="w-full h-full text-black dark:text-white"
            fill="currentColor"
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
      </div>

      {/* Subtitle / Status indicator */}
      {label && size !== 'small' && (
        <div className="mt-1 flex items-center gap-1.5 text-xs font-medium tracking-wide text-black/75 dark:text-white/75">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-black dark:bg-white animate-pulse" />
          <span>{label}</span>
        </div>
      )}
    </div>
  );
};

export default BrandMarkLoader;
