import React from 'react';

// SocialSync Logo Component
const SocialSyncLogo = ({ size = 'default', showText = true, className = '' }) => {
  const sizes = {
    small: { icon: 'w-5 h-5', text: 'text-sm' },
    default: { icon: 'w-6 h-6', text: 'text-lg' },
    large: { icon: 'w-8 h-8', text: 'text-xl' },
    xl: { icon: 'w-10 h-10', text: 'text-2xl' }
  };

  const currentSize = sizes[size] || sizes.default;

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {/* Logo Icon - Abstract S shape with sync arrows */}
      <div className={`${currentSize.icon} relative`}>
        <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
          {/* Background circle with gradient */}
          <defs>
            <linearGradient id="socialSyncGradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#10B981" />
              <stop offset="100%" stopColor="#059669" />
            </linearGradient>
          </defs>
          <circle cx="16" cy="16" r="16" fill="url(#socialSyncGradient)" />
          
          {/* Sync arrows forming an S */}
          <path 
            d="M10 12C10 12 12 10 16 10C20 10 22 12 22 14C22 16 20 18 16 18" 
            stroke="white" 
            strokeWidth="2.5" 
            strokeLinecap="round"
            fill="none"
          />
          <path 
            d="M22 20C22 20 20 22 16 22C12 22 10 20 10 18C10 16 12 14 16 14" 
            stroke="white" 
            strokeWidth="2.5" 
            strokeLinecap="round"
            fill="none"
          />
          {/* Arrow heads */}
          <path 
            d="M19 10L22 10L22 13" 
            stroke="white" 
            strokeWidth="2" 
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
          <path 
            d="M13 22L10 22L10 19" 
            stroke="white" 
            strokeWidth="2" 
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
        </svg>
      </div>
      
      {showText && (
        <span className={`font-semibold text-gray-900 ${currentSize.text}`}>
          SocialSync
        </span>
      )}
    </div>
  );
};

export default SocialSyncLogo;
