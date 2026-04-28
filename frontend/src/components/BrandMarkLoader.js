import React from 'react';
import UnravlerLogo from '@/components/UnravlerLogo';

const BrandMarkLoader = ({ className = '', size = 'xl' }) => (
  <div className={`flex items-center justify-center ${className}`} aria-label="Loading">
    <style>{`
      @keyframes unravlerMarkFloat {
        0%, 100% {
          transform: translateY(0) scale(1);
          filter: drop-shadow(0 8px 18px rgba(12,65,79,0.14));
        }
        50% {
          transform: translateY(-5px) scale(1.025);
          filter: drop-shadow(0 14px 26px rgba(12,65,79,0.22));
        }
      }

      @keyframes unravlerMarkSheen {
        0% { transform: translateX(-130%) skewX(-18deg); opacity: 0; }
        22% { opacity: 0.45; }
        55% { opacity: 0.18; }
        100% { transform: translateX(130%) skewX(-18deg); opacity: 0; }
      }

    `}</style>

    <div className="relative flex items-center justify-center">
      <div
        className="relative overflow-hidden rounded-md px-2 py-2"
        style={{ animation: 'unravlerMarkFloat 2.4s ease-in-out infinite' }}
      >
        <UnravlerLogo showText={false} size={size} darkText />
        <div
          className="pointer-events-none absolute inset-y-1 -left-4 w-8 bg-white/60 blur-sm"
          style={{ animation: 'unravlerMarkSheen 2.6s ease-in-out infinite' }}
        />
      </div>
    </div>
  </div>
);

export default BrandMarkLoader;
