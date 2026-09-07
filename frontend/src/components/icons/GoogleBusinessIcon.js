import React from 'react';

/**
 * Official Google Business Profile (formerly Google My Business) Icon
 * Renders the iconic storefront building with blue awning canopy stripes and the white Google 'G'.
 */
export default function GoogleBusinessIcon({ className = 'w-5 h-5', size, style, ...props }) {
  const inlineStyle = {
    display: 'inline-block',
    verticalAlign: 'middle',
    flexShrink: 0,
    ...(size ? { width: size, height: size } : {}),
    ...style,
  };

  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      style={inlineStyle}
      aria-hidden="true"
      {...props}
    >
      {/* Storefront base building */}
      <path
        d="M4 10.5V20C4 20.5523 4.44772 21 5 21H19C19.5523 21 20 20.5523 20 20V10.5"
        fill="#1A73E8"
      />
      {/* Canopy Roof Flaps / Awning Stripes */}
      {/* Left canopy stripe */}
      <path
        d="M4.5 4H7.5L6.5 10.5H2L3.5 5.5C3.7 4.6 4 4 4.5 4Z"
        fill="#4285F4"
      />
      {/* Middle-left canopy stripe */}
      <path
        d="M7.5 4H12V10.5H6.5L7.5 4Z"
        fill="#1967D2"
      />
      {/* Middle-right canopy stripe */}
      <path
        d="M12 4H16.5L17.5 10.5H12V4Z"
        fill="#4285F4"
      />
      {/* Right canopy stripe */}
      <path
        d="M16.5 4H19.5C20 4 20.3 4.6 20.5 5.5L22 10.5H17.5L16.5 4Z"
        fill="#1967D2"
      />
      {/* Awning scallop valances along the bottom */}
      <path
        d="M2 10.5C2 11.88 3.12 13 4.5 13C5.88 13 7 11.88 7 10.5H2Z"
        fill="#4285F4"
      />
      <path
        d="M7 10.5C7 11.88 8.12 13 9.5 13C10.88 13 12 11.88 12 10.5H7Z"
        fill="#1967D2"
      />
      <path
        d="M12 10.5C12 11.88 13.12 13 14.5 13C15.88 13 17 11.88 17 10.5H12Z"
        fill="#4285F4"
      />
      <path
        d="M17 10.5C17 11.88 18.12 13 19.5 13C20.88 13 22 11.88 22 10.5H17Z"
        fill="#1967D2"
      />
      {/* Centered White Google 'G' Mark */}
      <path
        d="M15.5 16.5H12V18.2H14.1C13.8 19.1 13 19.8 12 19.8C10.62 19.8 9.5 18.68 9.5 17.3C9.5 15.92 10.62 14.8 12 14.8C12.65 14.8 13.25 15.05 13.7 15.48L14.95 14.23C14.18 13.5 13.15 13.05 12 13.05C9.65 13.05 7.75 14.95 7.75 17.3C7.75 19.65 9.65 21.55 12 21.55C14.45 21.55 16.05 19.8 16.05 17.4C16.05 17.08 16 16.78 15.9 16.5H15.5Z"
        fill="#FFFFFF"
      />
    </svg>
  );
}

export { GoogleBusinessIcon };
