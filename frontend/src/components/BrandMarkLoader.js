import React from 'react';
import UnravlerLogo from '@/components/UnravlerLogo';

const LOGO_HEIGHTS = {
  small: 20,
  default: 28,
  large: 42,
  xl: 56,
};

const BrandMarkLoader = ({ className = '', size = 'xl', overlay = false }) => {
  const markHeight = LOGO_HEIGHTS[size] || LOGO_HEIGHTS.xl;
  const stageSize = Math.round(markHeight * 3.1);
  const orbitSize = stageSize + Math.round(markHeight * 1.3);
  const haloSize = stageSize + Math.round(markHeight * 2.1);
  const spotlightSize = haloSize + Math.round(markHeight * 2.6);

  return (
    <div
      className={`relative flex items-center justify-center ${
        overlay
          ? 'fixed inset-0 z-[120] overflow-hidden bg-offwhite/92 backdrop-blur-[14px] dark:bg-slate-950/94'
          : ''
      } ${className}`}
      role="status"
      aria-live="polite"
      aria-label="Loading"
    >
      <style>{`
        @keyframes unravlerLoaderDrift {
          0% {
            transform: translate3d(-2px, 2px, 0) scale(0.992) rotate(-0.8deg);
          }
          28% {
            transform: translate3d(3px, -6px, 0) scale(1.018) rotate(0deg);
          }
          62% {
            transform: translate3d(-1px, -3px, 0) scale(1.01) rotate(0.7deg);
          }
          100% {
            transform: translate3d(-2px, 2px, 0) scale(0.992) rotate(-0.8deg);
          }
        }

        @keyframes unravlerLoaderGlow {
          0%, 100% {
            transform: translate(-50%, -50%) scale(0.95);
            opacity: 0.74;
          }
          50% {
            transform: translate(-50%, -50%) scale(1.08);
            opacity: 0.98;
          }
        }

        @keyframes unravlerLoaderAura {
          0%, 100% {
            transform: translate(-44%, -42%) scale(0.96);
            opacity: 0.44;
          }
          50% {
            transform: translate(-56%, -58%) scale(1.1);
            opacity: 0.72;
          }
        }

        @keyframes unravlerLoaderOrbit {
          0% {
            transform: translate(-50%, -50%) rotate(0deg);
            opacity: 0.42;
          }
          50% {
            opacity: 0.72;
          }
          100% {
            transform: translate(-50%, -50%) rotate(360deg);
            opacity: 0.42;
          }
        }

        @keyframes unravlerLoaderOrbitReverse {
          0% {
            transform: translate(-50%, -50%) rotate(360deg) scale(0.985);
          }
          50% {
            transform: translate(-50%, -50%) rotate(180deg) scale(1.02);
          }
          100% {
            transform: translate(-50%, -50%) rotate(0deg) scale(0.985);
          }
        }

        @keyframes unravlerLoaderSheen {
          0% {
            transform: translateX(-160%) skewX(-18deg);
            opacity: 0;
          }
          18% {
            opacity: 0.18;
          }
          40% {
            opacity: 0.5;
          }
          62% {
            opacity: 0.12;
          }
          100% {
            transform: translateX(220%) skewX(-18deg);
            opacity: 0;
          }
        }

        @keyframes unravlerLoaderSpotlight {
          0%, 100% {
            transform: translate(-50%, -50%) scale(0.94);
            opacity: 0.5;
          }
          50% {
            transform: translate(-50%, -50%) scale(1.08);
            opacity: 0.72;
          }
        }

        @keyframes unravlerLoaderPulseRing {
          0% {
            transform: translate(-50%, -50%) scale(0.92);
            opacity: 0;
          }
          18% {
            opacity: 0.16;
          }
          62% {
            opacity: 0.08;
          }
          100% {
            transform: translate(-50%, -50%) scale(1.08);
            opacity: 0;
          }
        }

        @keyframes unravlerLoaderArcSweep {
          0% {
            transform: translate(-50%, -50%) rotate(0deg);
            opacity: 0.22;
          }
          50% {
            opacity: 0.42;
          }
          100% {
            transform: translate(-50%, -50%) rotate(360deg);
            opacity: 0.22;
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .unravler-loader__spotlight,
          .unravler-loader__halo-primary,
          .unravler-loader__halo-secondary,
          .unravler-loader__pulse,
          .unravler-loader__arc,
          .unravler-loader__orbit,
          .unravler-loader__orbit-accent,
          .unravler-loader__mark-shell,
          .unravler-loader__sheen {
            animation: none !important;
            transform: translate(-50%, -50%) scale(1) !important;
          }

          .unravler-loader__mark-shell {
            transform: none !important;
          }

          .unravler-loader__orbit,
          .unravler-loader__orbit-accent {
            opacity: 0.24 !important;
          }

          .unravler-loader__sheen {
            opacity: 0.1 !important;
          }
        }
      `}</style>

      {overlay ? (
        <div className="pointer-events-none absolute inset-0">
          <div
            className="unravler-loader__spotlight absolute left-1/2 top-1/2 rounded-full opacity-80 blur-3xl dark:hidden"
            style={{
              width: spotlightSize,
              height: spotlightSize,
              transform: 'translate(-50%, -50%)',
              background:
                'radial-gradient(circle, rgba(255,255,255,0.94) 0%, rgba(234,242,239,0.72) 34%, rgba(244,247,243,0.18) 60%, rgba(244,247,243,0) 80%)',
              animation: 'unravlerLoaderSpotlight 5.6s ease-in-out infinite',
            }}
          />
          <div
            className="unravler-loader__spotlight absolute left-1/2 top-1/2 hidden rounded-full opacity-80 blur-3xl dark:block"
            style={{
              width: spotlightSize,
              height: spotlightSize,
              transform: 'translate(-50%, -50%)',
              background:
                'radial-gradient(circle, rgba(161,190,183,0.34) 0%, rgba(87,110,107,0.18) 36%, rgba(15,23,42,0) 76%)',
              animation: 'unravlerLoaderSpotlight 5.6s ease-in-out infinite',
            }}
          />
        </div>
      ) : null}

      <div
        className="relative flex items-center justify-center"
        style={{ width: stageSize, height: stageSize }}
      >
        <div
          className="unravler-loader__halo-primary pointer-events-none absolute left-1/2 top-1/2 rounded-full blur-3xl dark:hidden"
          style={{
            width: haloSize,
            height: haloSize,
            transform: 'translate(-50%, -50%)',
            background:
              'radial-gradient(circle, rgba(223,236,232,0.96) 0%, rgba(195,214,209,0.52) 38%, rgba(195,214,209,0.16) 56%, rgba(195,214,209,0) 76%)',
            animation: 'unravlerLoaderGlow 4.8s cubic-bezier(0.37, 0, 0.22, 1) infinite',
          }}
        />
        <div
          className="unravler-loader__halo-primary pointer-events-none absolute left-1/2 top-1/2 hidden rounded-full blur-3xl dark:block"
          style={{
            width: haloSize,
            height: haloSize,
            transform: 'translate(-50%, -50%)',
            background:
              'radial-gradient(circle, rgba(143,175,168,0.34) 0%, rgba(82,104,101,0.2) 38%, rgba(15,23,42,0.02) 60%, rgba(15,23,42,0) 76%)',
            animation: 'unravlerLoaderGlow 4.8s cubic-bezier(0.37, 0, 0.22, 1) infinite',
          }}
        />
        <div
          className="unravler-loader__halo-secondary pointer-events-none absolute left-1/2 top-1/2 rounded-full blur-2xl dark:hidden"
          style={{
            width: Math.round(haloSize * 0.72),
            height: Math.round(haloSize * 0.72),
            transform: 'translate(-44%, -42%)',
            background:
              'radial-gradient(circle, rgba(246,240,223,0.88) 0%, rgba(246,240,223,0.28) 48%, rgba(246,240,223,0) 72%)',
            animation: 'unravlerLoaderAura 4.6s cubic-bezier(0.37, 0, 0.22, 1) infinite',
          }}
        />
        <div
          className="unravler-loader__halo-secondary pointer-events-none absolute left-1/2 top-1/2 hidden rounded-full blur-2xl dark:block"
          style={{
            width: Math.round(haloSize * 0.7),
            height: Math.round(haloSize * 0.7),
            transform: 'translate(-44%, -42%)',
            background:
              'radial-gradient(circle, rgba(229,236,231,0.18) 0%, rgba(229,236,231,0.08) 48%, rgba(15,23,42,0) 72%)',
            animation: 'unravlerLoaderAura 4.6s cubic-bezier(0.37, 0, 0.22, 1) infinite',
          }}
        />
        <div
          className="unravler-loader__pulse pointer-events-none absolute left-1/2 top-1/2 rounded-full border border-slate-300/30 dark:border-slate-500/25"
          style={{
            width: Math.round(stageSize * 1.24),
            height: Math.round(stageSize * 1.24),
            transform: 'translate(-50%, -50%)',
            animation: 'unravlerLoaderPulseRing 4.9s cubic-bezier(0.16, 1, 0.3, 1) infinite',
          }}
        />
        <div
          className="unravler-loader__arc pointer-events-none absolute left-1/2 top-1/2 rounded-full"
          style={{
            width: orbitSize + 10,
            height: orbitSize + 10,
            transform: 'translate(-50%, -50%)',
            background:
              'conic-gradient(from 150deg, rgba(86,116,110,0.38) 0deg, rgba(86,116,110,0.12) 34deg, rgba(86,116,110,0) 74deg, rgba(86,116,110,0) 360deg)',
            WebkitMask:
              'radial-gradient(farthest-side, transparent calc(100% - 1.5px), #000 calc(100% - 1.5px))',
            mask:
              'radial-gradient(farthest-side, transparent calc(100% - 1.5px), #000 calc(100% - 1.5px))',
            animation: 'unravlerLoaderArcSweep 8.6s linear infinite',
          }}
        />

        <div
          className="unravler-loader__orbit pointer-events-none absolute left-1/2 top-1/2 rounded-full border border-slate-300/60 dark:border-slate-600/55"
          style={{
            width: orbitSize,
            height: orbitSize,
            transform: 'translate(-50%, -50%)',
            animation: 'unravlerLoaderOrbit 7.5s linear infinite',
          }}
        />
        <div
          className="unravler-loader__orbit-accent pointer-events-none absolute left-1/2 top-1/2 rounded-full"
          style={{
            width: orbitSize,
            height: orbitSize,
            transform: 'translate(-50%, -50%)',
            animation: 'unravlerLoaderOrbitReverse 5.8s cubic-bezier(0.37, 0, 0.22, 1) infinite',
          }}
        >
          <span className="absolute left-1/2 top-0 block h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[rgba(72,110,104,0.88)] shadow-[0_0_0_6px_rgba(72,110,104,0.12),0_0_20px_rgba(72,110,104,0.28)] dark:bg-[rgba(229,236,231,0.82)] dark:shadow-[0_0_0_6px_rgba(229,236,231,0.08),0_0_22px_rgba(229,236,231,0.18)]" />
        </div>

        <div
          className="unravler-loader__mark-shell relative flex items-center justify-center transform-gpu"
          style={{
            width: stageSize,
            height: stageSize,
            animation: 'unravlerLoaderDrift 4.2s cubic-bezier(0.37, 0, 0.22, 1) infinite',
          }}
        >
          <div className="relative overflow-hidden rounded-[22px] border border-white/55 bg-white/60 px-3 py-3 shadow-[0_20px_48px_-26px_rgba(45,73,76,0.32),inset_0_1px_0_rgba(255,255,255,0.76)] backdrop-blur-md dark:border-white/10 dark:bg-white/5 dark:shadow-[0_24px_60px_-30px_rgba(0,0,0,0.7),inset_0_1px_0_rgba(255,255,255,0.08)]">
            <div className="pointer-events-none absolute inset-0 rounded-[22px] bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.5),transparent_60%)] dark:bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.08),transparent_60%)]" />

            <div
              className="relative transform-gpu"
              style={{
                filter: 'drop-shadow(0 14px 24px rgba(23,58,58,0.12))',
              }}
            >
              <UnravlerLogo showText={false} size={size} darkText />
            </div>

            <div
              className="unravler-loader__sheen pointer-events-none absolute inset-y-2 -left-10 w-10 rounded-full bg-white/70 blur-md dark:bg-white/12"
              style={{
                animation: 'unravlerLoaderSheen 3.8s cubic-bezier(0.37, 0, 0.22, 1) infinite',
              }}
            />
          </div>
        </div>

        <span className="sr-only">Loading</span>
      </div>
    </div>
  );
};

export default BrandMarkLoader;
