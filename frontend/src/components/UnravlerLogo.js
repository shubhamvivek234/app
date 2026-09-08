import React from 'react';
import { cn } from "@/lib/utils";

import logoDark from "@/assets/brand/unravler-logo-dark.png";
import logoWhite from "@/assets/brand/unravler-logo-white.png";
import markDark from "@/assets/brand/unravler-mark-upload-dark.png";
import markWhite from "@/assets/brand/unravler-mark-upload-white.png";

const UnravlerLogo = ({ 
  size = 'default', 
  showText = true, 
  className = '', 
  darkText = false,
  color = null,
  forceWhite = false,
  height: customHeight = null,
}) => {
  // Sizing is based on logo height.
  const sizes = {
    xs:     16,
    small:  20,
    default: 28,
    large:  42,
    xl:     56,
  };

  const height = customHeight || sizes[size] || sizes.default;
  const isWhite = forceWhite || color === 'white';
  const preferDark = !isWhite && !!darkText;

  return (
    <div
      className={cn("flex items-center select-none", className)}
    >
      {/* Brand mark + wordmark image (exact). */}
      {isWhite ? (
        <img
          src={showText ? logoWhite : markWhite}
          alt="Unravler"
          style={{ height, width: "auto" }}
          className="block"
          draggable={false}
        />
      ) : preferDark ? (
        <img
          src={showText ? logoDark : markDark}
          alt="Unravler"
          style={{ height, width: "auto" }}
          className="block"
          draggable={false}
        />
      ) : (
        <>
          <img
            src={showText ? logoDark : markDark}
            alt="Unravler"
            style={{ height, width: "auto" }}
            className="block dark:hidden"
            draggable={false}
          />
          <img
            src={showText ? logoWhite : markWhite}
            alt="Unravler"
            style={{ height, width: "auto" }}
            className="hidden dark:block"
            draggable={false}
          />
        </>
      )}
    </div>
  );
};

export default UnravlerLogo;
