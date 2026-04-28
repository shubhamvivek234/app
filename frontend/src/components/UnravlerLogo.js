import React from 'react';
import { cn } from "@/lib/utils";

import logoDark from "@/assets/brand/unravler-logo-dark.png";
import logoWhite from "@/assets/brand/unravler-logo-white.png";
import markDark from "@/assets/brand/unravler-mark-clean-dark.svg";
import markWhite from "@/assets/brand/unravler-mark-clean-white.svg";

const UnravlerLogo = ({ 
  size = 'default', 
  showText = true, 
  className = '', 
  darkText = false 
}) => {
  // Sizing is based on logo height.
  const sizes = {
    small:  20,
    default: 28,
    large:  42,
    xl:     56,
  };

  const height = sizes[size] || sizes.default;
  const preferDark = !!darkText;

  return (
    <div
      className={cn("flex items-center select-none", className)}
    >
      {/* Brand mark + wordmark image (exact). */}
      {preferDark ? (
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
