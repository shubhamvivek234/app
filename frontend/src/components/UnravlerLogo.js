"use client"
import React from "react"
import { cn } from "@/lib/utils"

export default function UnravlerLogo({ 
  text = "Unravler", 
  letterToReplace = "a", 
  className = "", 
  size = 'default',
  showText = true, // To maintain backward compatibility with any places that hide text
  darkText = false // Maintain compatibility
}) {
  const sizeMap = {
    small: 'text-2xl',
    default: 'text-4xl',
    large: 'text-6xl',
    xl: 'text-[5rem]'
  };
  const sizeClass = sizeMap[size] || sizeMap.default;

  // Since this component's whole point is animating a letter in the text, if showText is false, just render the diamond isolated.
  if (!showText) {
    return (
      <span
        className={cn("relative inline-flex items-center justify-center", sizeClass, className)}
        style={{ filter: "drop-shadow(0 4px 8px rgba(0,0,0,0.25)) drop-shadow(0 2px 4px rgba(0,0,0,0.15))" }}
      >
        <UnravlerDiamondGlow />
      </span>
    );
  }

  const parts = [];
  let keyIndex = 0;

  const lowerText = text.toLowerCase();
  const lowerLetter = letterToReplace.toLowerCase();
  const replaceIndex = lowerText.indexOf(lowerLetter);

  if (replaceIndex === -1) {
    return <span className={cn("font-black tracking-tight text-foreground", sizeClass, className)}>{text}</span>;
  }

  const before = text.slice(0, replaceIndex);
  const after = text.slice(replaceIndex + 1);

  return (
    <span className={cn("inline-flex items-center font-black tracking-tight", darkText ? "text-slate-900" : "text-slate-900 dark:text-white", sizeClass, className)}>
      {before && <span key={keyIndex++}>{before}</span>}

      {/* Animated visual replacing the letter */}
      <span
        className="relative inline-flex items-center justify-center mx-[0.02em]"
        style={{
          filter: "drop-shadow(0 4px 8px rgba(0,0,0,0.25)) drop-shadow(0 2px 4px rgba(0,0,0,0.15))",
        }}
      >
        <UnravlerDiamondGlow />
      </span>

      {after && <span key={keyIndex++}>{after}</span>}
    </span>
  );
}

const UnravlerDiamondGlow = () => (
  <>
    {/* SVG filters for realistic effects */}
    <svg className="absolute w-0 h-0" aria-hidden="true">
      <defs>
        {/* Inner shadow filter for the outer shape */}
        <filter id="innerShadowAnimated" x="-50%" y="-50%" width="200%" height="200%">
          <feComponentTransfer in="SourceAlpha">
            <feFuncA type="table" tableValues="1 0" />
          </feComponentTransfer>
          <feGaussianBlur stdDeviation="3" />
          <feOffset dx="0" dy="2" result="offsetblur" />
          <feFlood floodColor="rgba(255,255,255,0.15)" result="color" />
          <feComposite in2="offsetblur" operator="in" />
          <feComposite in2="SourceAlpha" operator="in" />
          <feMerge>
            <feMergeNode in="SourceGraphic" />
            <feMergeNode />
          </feMerge>
        </filter>

        <filter id="diamondGlowAnimated" x="-150%" y="-150%" width="400%" height="400%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="1.5" result="blur" />
          <feFlood floodColor="#d4ff4a" floodOpacity="0.3" />
          <feComposite in2="blur" operator="in" />
          <feMerge>
            <feMergeNode />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        <linearGradient id="diamondGradientAnimated" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#e2ff6a" />
          <stop offset="40%" stopColor="#d4ff4a" />
          <stop offset="60%" stopColor="#c4f934" />
          <stop offset="100%" stopColor="#b8ed28" />
        </linearGradient>

        <linearGradient id="diamondShineAnimated" x1="0%" y1="0%" x2="50%" y2="50%">
          <stop offset="0%" stopColor="rgba(255,255,255,0.6)" />
          <stop offset="100%" stopColor="rgba(255,255,255,0)" />
        </linearGradient>

        <radialGradient id="outerShapeGradientAnimated" cx="30%" cy="30%" r="70%">
          <stop offset="0%" stopColor="#2a2a2a" />
          <stop offset="100%" stopColor="#0f0f0f" />
        </radialGradient>
      </defs>
    </svg>

    {/* Scalloped/flower outer shape with depth */}
    <svg viewBox="0 0 100 100" className="w-[0.75em] h-[0.75em]">
      <path
        d="M50 0
           C55 15, 65 15, 75 10
           C70 25, 75 35, 90 35
           C80 45, 80 55, 90 65
           C75 65, 70 75, 75 90
           C65 85, 55 85, 50 100
           C45 85, 35 85, 25 90
           C30 75, 25 65, 10 65
           C20 55, 20 45, 10 35
           C25 35, 30 25, 25 10
           C35 15, 45 15, 50 0Z"
        fill="url(#outerShapeGradientAnimated)"
        filter="url(#innerShadowAnimated)"
      />
      <path
        d="M50 0
           C55 15, 65 15, 75 10
           C70 25, 75 35, 90 35
           C80 45, 80 55, 90 65
           C75 65, 70 75, 75 90
           C65 85, 55 85, 50 100
           C45 85, 35 85, 25 90
           C30 75, 25 65, 10 65
           C20 55, 20 45, 10 35
           C25 35, 30 25, 25 10
           C35 15, 45 15, 50 0Z"
        fill="none"
        stroke="rgba(255,255,255,0.05)"
        strokeWidth="1"
      />
    </svg>

    <span className="absolute inset-0 flex items-center justify-center">
      <svg
        viewBox="0 0 100 100"
        className="w-[0.32em] h-[0.32em] animate-diamond-rotate"
        filter="url(#diamondGlowAnimated)"
      >
        {/* Main diamond shape with clean gradient */}
        <path d="M50 8 L92 50 L50 92 L8 50 Z" fill="url(#diamondGradientAnimated)" />
        {/* Top-left shine facet for 3D polish */}
        <path d="M50 8 L8 50 L50 50 Z" fill="url(#diamondShineAnimated)" />
        {/* Subtle inner edge highlight */}
        <path d="M50 18 L82 50 L50 82 L18 50 Z" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" />
      </svg>
    </span>
  </>
);
