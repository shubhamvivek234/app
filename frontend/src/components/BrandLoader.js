import React from 'react';
import UnravlerLogo from '@/components/UnravlerLogo';

const BrandLoader = ({ className = '', size = 'xl' }) => {
  return (
    <div className={`flex items-center justify-center ${className}`}>
      <style>{`
        @keyframes brandLoaderFloat {
          0%, 100% { transform: translateY(0) scale(1); }
          50% { transform: translateY(-6px) scale(1.02); }
        }
        @keyframes brandLoaderGlow {
          0%, 100% { opacity: 0.25; transform: scale(0.92); }
          50% { opacity: 0.42; transform: scale(1.02); }
        }
        @keyframes brandLoaderOrbit {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
      <div className="relative flex items-center justify-center">
        <div
          className="absolute inset-0 rounded-full bg-[rgba(12,65,79,0.18)] blur-2xl"
          style={{ animation: 'brandLoaderGlow 2.2s ease-in-out infinite' }}
        />
        <div
          className="absolute h-20 w-20 rounded-full border border-[rgba(12,65,79,0.14)]"
          style={{ animation: 'brandLoaderOrbit 4.8s linear infinite' }}
        >
          <div className="absolute -top-1 left-1/2 h-2 w-2 -translate-x-1/2 rounded-full bg-[rgb(12,65,79)]" />
        </div>
        <div
          className="relative"
          style={{ animation: 'brandLoaderFloat 2.2s ease-in-out infinite' }}
        >
          <UnravlerLogo showText={false} size={size} darkText />
        </div>
      </div>
    </div>
  );
};

export default BrandLoader;
