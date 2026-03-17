import React from 'react';

// SocialEntangler Logo Component
const SocialEntanglerLogo = ({ size = 'default', showText = true, className = '' }) => {
  const sizeClasses = {
    small: 'w-6 h-6',
    default: 'w-8 h-8',
    large: 'w-12 h-12',
    xl: 'w-16 h-16'
  };

  const textClasses = {
    small: 'text-lg',
    default: 'text-xl',
    large: 'text-3xl',
    xl: 'text-4xl'
  };

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className={`relative flex items-center justify-center ${sizeClasses[size] || sizeClasses.default} bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 rounded-lg shadow-lg`}>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-white w-[70%] h-[70%]"
        >
          {/* Interconnected nodes representing social entanglement */}
          <circle cx="18" cy="5" r="3"></circle>
          <circle cx="6" cy="12" r="3"></circle>
          <circle cx="18" cy="19" r="3"></circle>
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line>
          <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line>
        </svg>
      </div>
      {showText && (
        <span className={`font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 ${textClasses[size] || textClasses.default}`}>
          SocialEntangler
        </span>
      )}
    </div>
  );
};

export default SocialEntanglerLogo;
