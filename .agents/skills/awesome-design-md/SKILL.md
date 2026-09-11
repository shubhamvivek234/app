---
name: awesome-design-md
description: Comprehensive collection of 74+ production DESIGN.md specifications (Linear, Cursor, Vercel, Stripe, Raycast, Resend, Supabase, Claude, Apple, etc.) based on the Google Stitch DESIGN.md standard. Use when designing, styling, or redesigning web interfaces to match iconic developer-tool, B2B, AI, or consumer brand aesthetics.
---

# Awesome DESIGN.md — Production Design System Library

## Overview

`awesome-design-md` is a curated collection of **74 analyzed DESIGN.md specifications** extracted from industry-defining developer tools, AI platforms, and high-craft consumer websites.

Each profile defines the exact:
1. **Color Tokens**: Primary brand voltage, ink/body text, muted accents, canvas tones, hairline borders, and semantic indicators.
2. **Typography Architecture**: Font pairings, display weights, letter-spacing tracking, and heading line-heights.
3. **Component Behaviors**: Button hierarchy, card elevation, border radiuses, interactive hover/active states, and glow effects.
4. **Layout Principles**: Grid rhythm, section spacing, visual density, and whitespace rules.
5. **Brand Personality**: Tone, voice, and unique visual signatures (e.g., Cursor's pastel AI pipeline steps, Linear's monochromatic speed aesthetic, Vercel's precision monochrome geometry).

---

## Supported Design Systems (74 Curated Brands)

### 1. Developer Tools & Terminal Native
- **`cursor`**: Editorial warm-cream canvas (`#f7f7f4`), near-black warm ink (`#26251e`), Cursor Orange (`#f54e00`), and pastel AI stage timeline indicators.
- **`linear.app`**: Void-black speed aesthetic, crisp micro-borders (`1px solid rgba(255,255,255,0.08)`), keyboard-first shortcuts, ultra-subtle purple/indigo illumination.
- **`raycast`**: Deep OLED dark mode, vibrant gradient accents, tactile launcher dialogs, keyboard navigation indicators.
- **`warp`**: Modern rust/terminal dark IDE blocks with status pills and code block syntax highlighting.
- **`expo`**: Deep developer dark theme, tight tracking, monospace numeric telemetry.
- **`vercel`**: Absolute monochrome geometric precision (`Geist` font, stark black & white contrast, zero decorative fluff).

### 2. AI & Frontier LLM Platforms
- **`claude`**: Anthropic's warm terracotta accent (`#D97757`), ivory reading canvas, editorial book-serif styling, calm academic tone.
- **`elevenlabs`**: Dark cinematic interface with audio-waveform visualizations and purple-cyan spectrum tints.
- **`mistral.ai`**: French-engineered minimalism, deep obsidian canvas, fiery amber/orange gradient accents.
- **`ollama`**: Terminal-first, stark monochrome ASCII simplicity.
- **`runwayml`**: High-fashion film-festival aesthetic, cinematic full-bleed dark heroes, paper-white reading bands, pure black pill CTAs.
- **`together.ai`**: Technical blueprint grid lines, monospace schematics, electric blue accents.
- **`voltagent`**: Void-black terminal canvas, emerald green accents (`#10B981`), high-velocity dev experience.
- **`x.ai`**: Stark futuristic monochrome minimalism.

### 3. High-Conversion FinTech & B2B SaaS
- **`stripe`**: High-chroma saturated gradient mesh, refined tabular typography, crisp payment badge styling.
- **`resend`**: Ultra-minimalist email developer aesthetic, dark canvas with laser-sharp white typography and crisp SVG iconography.
- **`supabase`**: Emerald dark mode (`#3ECF8E`), database table schemas, developer documentation elegance.
- **`posthog`**: Playful hedgehogs, retro-yellow highlights, high-density analytics telemetry without feeling corporate.
- **`revolut`**: Ultra-fast neobank glassmorphism, fluorescent gradients, micro-motion badges.
- **`wise`**: High-contrast electric lime accents, currency ticker cards, bold sans-serif display type.

---

## How to Apply a Design System to Any Page

When designing or redesigning a component or page:

1. **Locate the profile**:
   Examine `.agents/skills/awesome-design-md/design-md/<brand-name>/DESIGN.md`.
2. **Extract tokens**:
   - Extract the `colors:` map (canvas, primary, ink, hairline, surface-card).
   - Extract the `typography:` rules (headline font, body font, tracking, line-height).
   - Extract the `components:` styling (button radius, card borders, shadow rules).
3. **Map to Tailwind / CSS**:
   Convert hex codes and tokens into Tailwind utility classes or CSS custom properties.
4. **Enforce anti-patterns**:
   Adhere to the brand's unique constraints (e.g. Cursor forbids dark IDE hero backgrounds; Vercel forbids rounded pill buttons; Linear forbids saturated gradient blobs).

---

## File Location

All 74 design specifications are located at:
`/.agents/skills/awesome-design-md/design-md/<brand-name>/DESIGN.md`
