import React, { useState } from 'react';
import {
  FaUndo,
  FaRedo,
  FaCheck,
  FaLayerGroup,
  FaPalette,
  FaSlidersH,
  FaFont,
  FaTimes,
} from 'react-icons/fa';
import {
  TACTILE_CARD_STYLES,
  HEADER_LAYOUTS,
} from '@/lib/bioThemeUtils';

export const MODERN_THEME_PRESETS = [
  {
    id: 'cosmic',
    name: 'Cosmic Indigo',
    subtitle: 'Deep Space',
    bg: 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%)',
    textColor: '#FFFFFF',
    accentColor: '#818CF8',
    cardBg: 'rgba(255, 255, 255, 0.12)',
    cardBorder: 'rgba(255, 255, 255, 0.20)',
    cardTextColor: '#FFFFFF',
    cardStyle: 'glass_double_bezel',
  },
  {
    id: 'titanium',
    name: 'Natural Titanium',
    subtitle: 'Brushed Metal',
    bg: 'linear-gradient(135deg, #27272a 0%, #18181b 100%)',
    textColor: '#F5F5F7',
    accentColor: '#E2DDD6',
    cardBg: 'rgba(255, 255, 255, 0.08)',
    cardBorder: 'rgba(255, 255, 255, 0.14)',
    cardTextColor: '#FFFFFF',
    cardStyle: 'glass_double_bezel',
  },
  {
    id: 'alpine',
    name: 'Alpine Pine',
    subtitle: 'Forest Glass',
    bg: 'linear-gradient(135deg, #064e3b 0%, #065f46 50%, #047857 100%)',
    textColor: '#FFFFFF',
    accentColor: '#34D399',
    cardBg: 'rgba(255, 255, 255, 0.12)',
    cardBorder: 'rgba(52, 211, 153, 0.25)',
    cardTextColor: '#FFFFFF',
    cardStyle: 'glass_double_bezel',
  },
  {
    id: 'desert',
    name: 'Desert Gold',
    subtitle: 'Warm Amber',
    bg: 'linear-gradient(135deg, #451a03 0%, #78350f 50%, #b45309 100%)',
    textColor: '#FFFFFF',
    accentColor: '#FBBF24',
    cardBg: 'rgba(255, 255, 255, 0.12)',
    cardBorder: 'rgba(251, 191, 36, 0.25)',
    cardTextColor: '#FFFFFF',
    cardStyle: 'glass_double_bezel',
  },
  {
    id: 'cashmere',
    name: 'Editorial Cashmere',
    subtitle: 'Luxury Cream',
    bg: 'linear-gradient(135deg, #FAF8F5 0%, #F3EDE2 100%)',
    textColor: '#1D1D1F',
    accentColor: '#0071E3',
    cardBg: '#FFFFFF',
    cardBorder: 'rgba(0, 0, 0, 0.08)',
    cardTextColor: '#1D1D1F',
    cardStyle: 'solid_flat',
  },
  {
    id: 'obsidian',
    name: 'Pure Obsidian',
    subtitle: 'Midnight Noir',
    bg: 'linear-gradient(180deg, #000000 0%, #09090B 100%)',
    textColor: '#FAFAFA',
    accentColor: '#FFFFFF',
    cardBg: 'rgba(255, 255, 255, 0.08)',
    cardBorder: 'rgba(255, 255, 255, 0.14)',
    cardTextColor: '#FAFAFA',
    cardStyle: 'glass_double_bezel',
  },
  {
    id: 'lavender',
    name: 'Lavender Silk',
    subtitle: 'Pastel Violet',
    bg: 'linear-gradient(135deg, #F5F3FF 0%, #EDE9FE 50%, #DDD6FE 100%)',
    textColor: '#4C1D95',
    accentColor: '#7C3AED',
    cardBg: 'rgba(255, 255, 255, 0.90)',
    cardBorder: 'rgba(124, 58, 237, 0.15)',
    cardTextColor: '#4C1D95',
    cardStyle: 'soft_pill',
  },
  {
    id: 'sunset',
    name: 'Sunset Aura',
    subtitle: 'Coral Peach',
    bg: 'linear-gradient(135deg, #FFE4E6 0%, #EDE9FE 50%, #FEF3C7 100%)',
    textColor: '#4C0519',
    accentColor: '#E11D48',
    cardBg: 'rgba(255, 255, 255, 0.85)',
    cardBorder: 'rgba(225, 29, 72, 0.15)',
    cardTextColor: '#4C0519',
    cardStyle: 'tactile_convex',
  },
  {
    id: 'cyber',
    name: 'Tokyo Cyber',
    subtitle: 'Neon Midnight',
    bg: 'linear-gradient(135deg, #05050A 0%, #0D081E 50%, #15002A 100%)',
    textColor: '#00F0FF',
    accentColor: '#EC4899',
    cardBg: 'rgba(255, 255, 255, 0.06)',
    cardBorder: 'rgba(0, 240, 255, 0.3)',
    cardTextColor: '#00F0FF',
    cardStyle: 'neon_glow',
  },
  {
    id: 'champagne',
    name: 'Champagne Luxe',
    subtitle: 'Ivory Gold',
    bg: 'linear-gradient(135deg, #FBF9F4 0%, #F5EDE0 100%)',
    textColor: '#451A03',
    accentColor: '#D97706',
    cardBg: 'rgba(255, 255, 255, 0.95)',
    cardBorder: 'rgba(217, 119, 6, 0.2)',
    cardTextColor: '#451A03',
    cardStyle: 'tactile_convex',
  },
  {
    id: 'arctic',
    name: 'Nordic Arctic',
    subtitle: 'Glacier Slate',
    bg: 'linear-gradient(135deg, #030D1A 0%, #0F172A 60%, #1E293B 100%)',
    textColor: '#E0F2FE',
    accentColor: '#38BDF8',
    cardBg: 'rgba(255, 255, 255, 0.08)',
    cardBorder: 'rgba(56, 189, 248, 0.25)',
    cardTextColor: '#E0F2FE',
    cardStyle: 'glass_double_bezel',
  },
  {
    id: 'matcha',
    name: 'Matcha Botanical',
    subtitle: 'Zen Sage',
    bg: 'linear-gradient(135deg, #F4F7F4 0%, #E8EFE8 100%)',
    textColor: '#1E3A2F',
    accentColor: '#059669',
    cardBg: 'rgba(255, 255, 255, 0.92)',
    cardBorder: 'rgba(5, 150, 105, 0.2)',
    cardTextColor: '#1E3A2F',
    cardStyle: 'glass_double_bezel',
  },
  {
    id: 'espresso',
    name: 'Velvet Espresso',
    subtitle: 'Dark Caramel',
    bg: 'linear-gradient(135deg, #1C120C 0%, #2A1B12 100%)',
    textColor: '#FED7AA',
    accentColor: '#F97316',
    cardBg: 'rgba(255, 255, 255, 0.08)',
    cardBorder: 'rgba(249, 115, 22, 0.25)',
    cardTextColor: '#FED7AA',
    cardStyle: 'glass_double_bezel',
  },
  {
    id: 'rosequartz',
    name: 'Rose Quartz',
    subtitle: 'Blush Pearl',
    bg: 'linear-gradient(135deg, #FFF1F2 0%, #FFE4E6 100%)',
    textColor: '#881337',
    accentColor: '#F43F5E',
    cardBg: 'rgba(255, 255, 255, 0.90)',
    cardBorder: 'rgba(244, 63, 94, 0.2)',
    cardTextColor: '#881337',
    cardStyle: 'soft_pill',
  },
];

const FONTS_LIST = [
  { id: 'Plus Jakarta Sans', label: 'Plus Jakarta Sans', sample: 'Modern Luxury' },
  { id: 'Geist', label: 'Geist', sample: 'Minimal Tech' },
  { id: 'Outfit', label: 'Outfit', sample: 'Geometric Chic' },
  { id: 'Playfair Display', label: 'Playfair Display', sample: 'Editorial Serif' },
  { id: 'Space Grotesk', label: 'Space Grotesk', sample: 'Monospace Edge' },
  { id: 'Inter', label: 'Inter', sample: 'Classic Clean' },
];

const ACCENT_SWATCHES = [
  '#0071E3', '#34C759', '#5856D6', '#AF52DE', '#FF2D55',
  '#FF9500', '#FFCC00', '#5AC8FA', '#10B981', '#F43F5E',
  '#6366F1', '#D97706', '#059669', '#0284C7', '#FAFAFA',
];

const CARD_BG_SWATCHES = [
  { label: 'White', val: '#FFFFFF', bg: '#FFFFFF' },
  { label: 'Cream', val: '#FAF8F5', bg: '#FAF8F5' },
  { label: 'Glass White', val: 'rgba(255, 255, 255, 0.85)', bg: 'rgba(255, 255, 255, 0.85)' },
  { label: 'Dark Glass', val: 'rgba(24, 24, 27, 0.80)', bg: 'rgba(24, 24, 27, 0.80)' },
  { label: 'Indigo Glass', val: 'rgba(79, 70, 229, 0.15)', bg: '#4F46E5' },
  { label: 'Rose Glass', val: 'rgba(244, 63, 94, 0.15)', bg: '#F43F5E' },
  { label: 'Emerald Glass', val: 'rgba(16, 185, 129, 0.15)', bg: '#10B981' },
  { label: 'Dark Slate', val: '#1E293B', bg: '#1E293B' },
  { label: 'OLED Black', val: '#09090B', bg: '#09090B' },
];

const CARD_TEXT_SWATCHES = [
  { label: 'Auto/Default', val: '' },
  { label: 'White', val: '#FFFFFF' },
  { label: 'Charcoal', val: '#1D1D1F' },
  { label: 'Muted Slate', val: '#64748B' },
  { label: 'Gold', val: '#FBBF24' },
  { label: 'Rose', val: '#F43F5E' },
];

const SOCIAL_PLATFORMS = [
  { id: 'instagram', label: 'Instagram', placeholder: 'https://instagram.com/username' },
  { id: 'twitter', label: 'Twitter / X', placeholder: 'https://x.com/username' },
  { id: 'youtube', label: 'YouTube', placeholder: 'https://youtube.com/@channel' },
  { id: 'linkedin', label: 'LinkedIn', placeholder: 'https://linkedin.com/in/username' },
  { id: 'tiktok', label: 'TikTok', placeholder: 'https://tiktok.com/@username' },
  { id: 'github', label: 'GitHub', placeholder: 'https://github.com/username' },
  { id: 'spotify', label: 'Spotify', placeholder: 'https://open.spotify.com/artist/...' },
  { id: 'discord', label: 'Discord', placeholder: 'https://discord.gg/invite' },
];

export default function BioInspectorDrawer({
  theme = {},
  setTheme,
  socialLinks = {},
  setSocialLinks,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
  onResetTheme,
}) {
  const [activeTab, setActiveTab] = useState('style'); // 'style' | 'cards' | 'settings'

  const applyThemePreset = (preset) => {
    setTheme((prev) => ({
      ...prev,
      preset: preset.id,
      background_type: 'gradient',
      background_gradient: preset.bg,
      background_color: preset.bg.includes('#') ? preset.bg.slice(preset.bg.indexOf('#'), preset.bg.indexOf('#') + 7) : '#000000',
      text_color: preset.textColor,
      accent_color: preset.accentColor,
      card_bg: preset.cardBg,
      card_border: preset.cardBorder,
      card_text_color: preset.cardTextColor,
      card_style: preset.cardStyle,
      card_corner_radius: prev.card_corner_radius ?? 16,
      card_spacing: prev.card_spacing ?? 12,
    }));
  };

  const handleCardShape = (shape) => {
    if (shape === 'sharp') {
      setTheme((prev) => ({ ...prev, card_corner_radius: 4 }));
    } else if (shape === 'squircle') {
      setTheme((prev) => ({ ...prev, card_corner_radius: 16 }));
    } else if (shape === 'pill') {
      setTheme((prev) => ({ ...prev, card_corner_radius: 9999 }));
    }
  };

  const currentShape =
    (theme.card_corner_radius ?? 16) >= 40
      ? 'pill'
      : (theme.card_corner_radius ?? 16) <= 6
      ? 'sharp'
      : 'squircle';

  return (
    <div className="flex flex-col h-full bg-white/80 dark:bg-[#1C1C1E]/80 backdrop-blur-2xl border-l border-black/[0.06] dark:border-white/[0.08] text-gray-800 dark:text-gray-200 select-none overflow-hidden">
      
      {/* ── TOP HEADER WITH APPLE SEGMENTED CONTROL & UNDO/REDO ── */}
      <div className="p-3 border-b border-black/[0.04] dark:border-white/[0.06] flex items-center justify-between gap-2 shrink-0">
        <div className="apple-segment-wrapper flex-1 justify-between">
          <button
            onClick={() => setActiveTab('style')}
            className={`apple-segment-btn flex-1 text-center ${activeTab === 'style' ? 'active' : ''}`}
          >
            Style
          </button>
          <button
            onClick={() => setActiveTab('cards')}
            className={`apple-segment-btn flex-1 text-center ${activeTab === 'cards' ? 'active' : ''}`}
          >
            Cards
          </button>
          <button
            onClick={() => setActiveTab('settings')}
            className={`apple-segment-btn flex-1 text-center ${activeTab === 'settings' ? 'active' : ''}`}
          >
            Settings
          </button>
        </div>

        {/* Undo / Redo Actions */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={onUndo}
            disabled={!canUndo}
            className="p-2 rounded-full hover:bg-black/[0.05] dark:hover:bg-white/[0.08] text-gray-600 dark:text-gray-300 disabled:opacity-30 transition-all"
            title="Undo"
          >
            <FaUndo className="text-xs" />
          </button>
          <button
            onClick={onRedo}
            disabled={!canRedo}
            className="p-2 rounded-full hover:bg-black/[0.05] dark:hover:bg-white/[0.08] text-gray-600 dark:text-gray-300 disabled:opacity-30 transition-all"
            title="Redo"
          >
            <FaRedo className="text-xs" />
          </button>
        </div>
      </div>

      {/* ── TAB CONTENT SCROLLABLE BODY ── */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5 custom-scrollbar">
        
        {/* ══════════ 1. STYLE TAB ══════════ */}
        {activeTab === 'style' && (
          <div className="space-y-5 animate-in fade-in duration-200">
            
            {/* Modern & Elegant Theme Presets */}
            <div>
              <div className="flex items-center justify-between mb-2.5">
                <label className="text-[11px] font-bold tracking-wider uppercase text-gray-400 dark:text-gray-500">
                  Modern & Elegant Themes
                </label>
                <span className="text-[10px] font-semibold text-[#0071E3] dark:text-blue-400">14 Presets</span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {MODERN_THEME_PRESETS.map((preset) => {
                  const isSelected = theme.background_gradient === preset.bg || theme.preset === preset.id;
                  return (
                    <button
                      key={preset.id}
                      onClick={() => applyThemePreset(preset)}
                      className={`p-2.5 rounded-xl border text-left transition-all relative ${
                        isSelected
                          ? 'border-[#0071E3] ring-2 ring-[#0071E3]/20 bg-blue-50/20 dark:bg-blue-950/20'
                          : 'border-black/[0.08] dark:border-white/[0.12] bg-black/[0.02] dark:bg-white/[0.04] hover:border-[#0071E3]/50'
                      }`}
                    >
                      <div
                        className="h-10 rounded-lg mb-1.5 shadow-inner relative overflow-hidden"
                        style={{ background: preset.bg }}
                      >
                        {isSelected && (
                          <div className="absolute top-1 right-1 w-4 h-4 rounded-full bg-[#0071E3] text-white flex items-center justify-center text-[9px] shadow-sm">
                            <FaCheck />
                          </div>
                        )}
                      </div>
                      <div className="text-xs font-semibold text-gray-900 dark:text-white truncate">
                        {preset.name}
                      </div>
                      <div className="text-[10px] text-gray-400 dark:text-gray-500 truncate">
                        {preset.subtitle}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Sliders: Glass Blur & Corner Radius */}
            <div className="p-3.5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] space-y-3.5">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-gray-700 dark:text-gray-300">Glass Blur Intensity</span>
                  <span className="font-mono text-[11px] text-gray-500">{theme.glass_blur ?? 16}px</span>
                </div>
                <input
                  type="range"
                  className="apple-slider"
                  min="0"
                  max="40"
                  value={theme.glass_blur ?? 16}
                  onChange={(e) => setTheme((prev) => ({ ...prev, glass_blur: Number(e.target.value) }))}
                />
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-gray-700 dark:text-gray-300">Squircle Corner Radius</span>
                  <span className="font-mono text-[11px] text-gray-500">{theme.card_corner_radius ?? 16}px</span>
                </div>
                <input
                  type="range"
                  className="apple-slider"
                  min="0"
                  max="32"
                  value={theme.card_corner_radius ?? 16}
                  onChange={(e) => setTheme((prev) => ({ ...prev, card_corner_radius: Number(e.target.value) }))}
                />
              </div>
            </div>

            {/* Accent Tint Color Swatches + Custom Picker */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-[11px] font-bold tracking-wider uppercase text-gray-400 dark:text-gray-500">
                  Accent Tint Color
                </label>
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-gray-400 font-mono">{theme.accent_color || '#0071E3'}</span>
                  <input
                    type="color"
                    value={theme.accent_color || '#0071E3'}
                    onChange={(e) => setTheme((prev) => ({ ...prev, accent_color: e.target.value }))}
                    className="w-5 h-5 rounded-full cursor-pointer border-0 bg-transparent p-0"
                    title="Custom Accent Color"
                  />
                </div>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                {ACCENT_SWATCHES.map((hex) => {
                  const isMatch = (theme.accent_color || '').toLowerCase() === hex.toLowerCase();
                  return (
                    <button
                      key={hex}
                      onClick={() => setTheme((prev) => ({ ...prev, accent_color: hex }))}
                      style={{ background: hex }}
                      className={`w-7 h-7 rounded-full transition-transform border border-black/10 dark:border-white/15 flex items-center justify-center ${
                        isMatch ? 'scale-110 ring-2 ring-[#0071E3] ring-offset-2' : 'hover:scale-105'
                      }`}
                    >
                      {isMatch && <FaCheck className={`text-[10px] ${hex === '#FFFFFF' || hex === '#FAFAFA' || hex === '#FFCC00' ? 'text-black' : 'text-white'}`} />}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Custom Background Color Picker */}
            <div className="p-3.5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] flex items-center justify-between">
              <div>
                <span className="text-xs font-semibold text-gray-800 dark:text-gray-200">Custom Solid Background</span>
                <p className="text-[10px] text-gray-400">Override background with exact hex color</p>
              </div>
              <input
                type="color"
                value={theme.background_color && theme.background_color.startsWith('#') ? theme.background_color : '#0f172a'}
                onChange={(e) =>
                  setTheme((prev) => ({
                    ...prev,
                    background_type: 'solid',
                    background_color: e.target.value,
                    background_gradient: '',
                  }))
                }
                className="w-8 h-8 rounded-xl cursor-pointer border border-black/10 dark:border-white/15 p-0 bg-transparent"
              />
            </div>

            {/* Fonts & Typography */}
            <div>
              <label className="text-[11px] font-bold tracking-wider uppercase text-gray-400 dark:text-gray-500 block mb-2">
                Font Family
              </label>
              <div className="space-y-1.5">
                {FONTS_LIST.map((f) => {
                  const isCurrent = (theme.font_family || 'Plus Jakarta Sans').includes(f.id);
                  return (
                    <button
                      key={f.id}
                      onClick={() => setTheme((prev) => ({ ...prev, font_family: `${f.id}, sans-serif` }))}
                      className={`w-full p-2.5 rounded-xl border text-left flex items-center justify-between transition-all ${
                        isCurrent
                          ? 'border-[#0071E3] bg-blue-50/30 dark:bg-blue-950/30 font-bold'
                          : 'border-black/[0.06] dark:border-white/[0.08] hover:bg-black/[0.02] dark:hover:bg-white/[0.04]'
                      }`}
                      style={{ fontFamily: `${f.id}, sans-serif` }}
                    >
                      <div>
                        <div className="text-xs font-semibold text-gray-900 dark:text-white">{f.label}</div>
                        <div className="text-[10px] text-gray-400">{f.sample}</div>
                      </div>
                      {isCurrent && <FaCheck className="text-xs text-[#0071E3]" />}
                    </button>
                  );
                })}
              </div>
            </div>

          </div>
        )}

        {/* ══════════ 2. CARDS TAB ══════════ */}
        {activeTab === 'cards' && (
          <div className="space-y-5 animate-in fade-in duration-200">
            
            {/* Button Shape Style */}
            <div>
              <label className="text-[11px] font-bold tracking-wider uppercase text-gray-400 dark:text-gray-500 block mb-2">
                Card Geometry
              </label>
              <div className="grid grid-cols-3 gap-2">
                <button
                  onClick={() => handleCardShape('sharp')}
                  className={`py-2 text-xs font-semibold rounded-lg border transition-all ${
                    currentShape === 'sharp'
                      ? 'border-[#0071E3] bg-blue-50/50 dark:bg-blue-950/40 text-[#0071E3] ring-1 ring-[#0071E3]'
                      : 'border-black/[0.08] dark:border-white/[0.12] hover:border-[#0071E3]'
                  }`}
                >
                  Sharp
                </button>
                <button
                  onClick={() => handleCardShape('squircle')}
                  className={`py-2 text-xs font-semibold rounded-2xl border transition-all ${
                    currentShape === 'squircle'
                      ? 'border-[#0071E3] bg-blue-50/50 dark:bg-blue-950/40 text-[#0071E3] ring-1 ring-[#0071E3]'
                      : 'border-black/[0.08] dark:border-white/[0.12] hover:border-[#0071E3]'
                  }`}
                >
                  Squircle
                </button>
                <button
                  onClick={() => handleCardShape('pill')}
                  className={`py-2 text-xs font-semibold rounded-full border transition-all ${
                    currentShape === 'pill'
                      ? 'border-[#0071E3] bg-blue-50/50 dark:bg-blue-950/40 text-[#0071E3] ring-1 ring-[#0071E3]'
                      : 'border-black/[0.08] dark:border-white/[0.12] hover:border-[#0071E3]'
                  }`}
                >
                  Pill
                </button>
              </div>
            </div>

            {/* Tactile 3D Card Style Presets */}
            <div>
              <label className="text-[11px] font-bold tracking-wider uppercase text-gray-400 dark:text-gray-500 block mb-2">
                Tactile Card Physics
              </label>
              <div className="grid grid-cols-2 gap-2">
                {TACTILE_CARD_STYLES.map((st) => {
                  const isCurrent = (theme.card_style || 'glass_double_bezel') === st.id;
                  return (
                    <button
                      key={st.id}
                      onClick={() => setTheme((prev) => ({ ...prev, card_style: st.id }))}
                      className={`p-2.5 rounded-xl border text-left transition-all ${
                        isCurrent
                          ? 'border-[#0071E3] bg-blue-50/30 dark:bg-blue-950/30 text-[#0071E3]'
                          : 'border-black/[0.06] dark:border-white/[0.08] hover:border-[#0071E3]'
                      }`}
                    >
                      <div className="text-xs font-bold truncate text-gray-900 dark:text-white">{st.label}</div>
                      <div className="text-[10px] text-gray-400 dark:text-gray-500 truncate">{st.description}</div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Card Background Swatches + Custom Hex */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-[11px] font-bold tracking-wider uppercase text-gray-400 dark:text-gray-500">
                  Card Backdrop Tint
                </label>
                <input
                  type="color"
                  value={theme.card_bg && theme.card_bg.startsWith('#') ? theme.card_bg : '#FFFFFF'}
                  onChange={(e) => setTheme((prev) => ({ ...prev, card_bg: e.target.value }))}
                  className="w-5 h-5 rounded-full cursor-pointer border-0 bg-transparent p-0"
                  title="Custom Card Background"
                />
              </div>
              <div className="grid grid-cols-3 gap-2">
                {CARD_BG_SWATCHES.map((sw) => {
                  const isCurrent = theme.card_bg === sw.val;
                  return (
                    <button
                      key={sw.label}
                      onClick={() => setTheme((prev) => ({ ...prev, card_bg: sw.val }))}
                      className={`p-2 rounded-xl border flex items-center gap-2 text-left transition-all ${
                        isCurrent
                          ? 'border-[#0071E3] ring-1 ring-[#0071E3]'
                          : 'border-black/[0.08] dark:border-white/[0.12] hover:border-[#0071E3]'
                      }`}
                    >
                      <span
                        className="w-4 h-4 rounded-full border border-black/10 shrink-0 shadow-inner"
                        style={{ background: sw.bg }}
                      />
                      <span className="text-[11px] font-medium truncate text-gray-800 dark:text-gray-200">
                        {sw.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Card Text Color */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-[11px] font-bold tracking-wider uppercase text-gray-400 dark:text-gray-500">
                  Card Text Color
                </label>
                <input
                  type="color"
                  value={theme.card_text_color || '#FFFFFF'}
                  onChange={(e) => setTheme((prev) => ({ ...prev, card_text_color: e.target.value }))}
                  className="w-5 h-5 rounded-full cursor-pointer border-0 bg-transparent p-0"
                  title="Custom Card Text Color"
                />
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                {CARD_TEXT_SWATCHES.map((tx) => {
                  const isCurrent = (theme.card_text_color || '') === tx.val;
                  return (
                    <button
                      key={tx.label}
                      onClick={() => setTheme((prev) => ({ ...prev, card_text_color: tx.val }))}
                      className={`px-3 py-1 rounded-lg text-xs font-medium border transition-all ${
                        isCurrent
                          ? 'border-[#0071E3] bg-blue-50/50 dark:bg-blue-950/40 text-[#0071E3]'
                          : 'border-black/[0.08] dark:border-white/[0.12] hover:border-[#0071E3]'
                      }`}
                    >
                      {tx.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Card Spacing, Shadow Depth & Border Width Sliders */}
            <div className="p-3.5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] space-y-3.5">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-gray-700 dark:text-gray-300">Card Vertical Gap</span>
                  <span className="font-mono text-[11px] text-gray-500">{theme.card_spacing ?? 12}px</span>
                </div>
                <input
                  type="range"
                  className="apple-slider"
                  min="6"
                  max="32"
                  value={theme.card_spacing ?? 12}
                  onChange={(e) => setTheme((prev) => ({ ...prev, card_spacing: Number(e.target.value) }))}
                />
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-gray-700 dark:text-gray-300">Tactile Shadow Depth</span>
                  <span className="font-mono text-[11px] text-gray-500">{theme.card_shadow_depth ?? 50}%</span>
                </div>
                <input
                  type="range"
                  className="apple-slider"
                  min="0"
                  max="100"
                  value={theme.card_shadow_depth ?? 50}
                  onChange={(e) => setTheme((prev) => ({ ...prev, card_shadow_depth: Number(e.target.value) }))}
                />
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-gray-700 dark:text-gray-300">Card Border Width</span>
                  <span className="font-mono text-[11px] text-gray-500">{theme.card_border_width ?? 1}px</span>
                </div>
                <input
                  type="range"
                  className="apple-slider"
                  min="0"
                  max="4"
                  value={theme.card_border_width ?? 1}
                  onChange={(e) => setTheme((prev) => ({ ...prev, card_border_width: Number(e.target.value) }))}
                />
              </div>
            </div>

          </div>
        )}

        {/* ══════════ 3. SETTINGS TAB ══════════ */}
        {activeTab === 'settings' && (
          <div className="space-y-5 animate-in fade-in duration-200">
            
            {/* Header Layout */}
            <div>
              <label className="text-[11px] font-bold tracking-wider uppercase text-gray-400 dark:text-gray-500 block mb-2">
                Header Layout
              </label>
              <div className="grid grid-cols-2 gap-2">
                {HEADER_LAYOUTS.map((hl) => {
                  const isCurrent = (theme.header_layout || 'classic') === hl.id;
                  return (
                    <button
                      key={hl.id}
                      onClick={() => setTheme((prev) => ({ ...prev, header_layout: hl.id }))}
                      className={`p-2.5 rounded-xl border text-left transition-all ${
                        isCurrent
                          ? 'border-[#0071E3] bg-blue-50/30 dark:bg-blue-950/30 text-[#0071E3] font-bold'
                          : 'border-black/[0.06] dark:border-white/[0.08] hover:border-[#0071E3]'
                      }`}
                    >
                      <div className="text-xs font-semibold text-gray-900 dark:text-white truncate">{hl.label}</div>
                      <div className="text-[10px] text-gray-400 dark:text-gray-500 truncate">{hl.description}</div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Profile Avatar Sizing */}
            <div className="p-3.5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-gray-700 dark:text-gray-300">Avatar Diameter</span>
                <span className="font-mono text-[11px] text-gray-500">{theme.profile_picture_size ?? 96}px</span>
              </div>
              <input
                type="range"
                className="apple-slider"
                min="48"
                max="128"
                value={theme.profile_picture_size ?? 96}
                onChange={(e) => setTheme((prev) => ({ ...prev, profile_picture_size: Number(e.target.value) }))}
              />
            </div>

            {/* Connected Social Dock Toggles */}
            <div>
              <label className="text-[11px] font-bold tracking-wider uppercase text-gray-400 dark:text-gray-500 block mb-2">
                Connected Social Dock
              </label>
              <div className="space-y-2">
                {SOCIAL_PLATFORMS.map((sp) => {
                  const currentVal = socialLinks[sp.id] || '';
                  return (
                    <div
                      key={sp.id}
                      className="p-2.5 rounded-xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] space-y-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-gray-800 dark:text-gray-200">{sp.label}</span>
                        {currentVal && (
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-50 text-emerald-600 border border-emerald-200">
                            Active
                          </span>
                        )}
                      </div>
                      <input
                        type="url"
                        value={currentVal}
                        onChange={(e) =>
                          setSocialLinks?.((prev) => ({ ...prev, [sp.id]: e.target.value }))
                        }
                        placeholder={sp.placeholder}
                        className="w-full px-2.5 py-1 text-xs rounded-lg bg-white dark:bg-[#2C2C2E] border border-black/[0.08] dark:border-white/[0.1] text-gray-900 dark:text-white outline-none focus:border-[#0071E3] transition"
                      />
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Announcement Top Banner */}
            <div className="p-3.5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-800 dark:text-gray-200">Announcement Banner</span>
                <label className="apple-switch">
                  <input
                    type="checkbox"
                    checked={Boolean(theme.announcement_active)}
                    onChange={(e) => setTheme((prev) => ({ ...prev, announcement_active: e.target.checked }))}
                  />
                  <span className="apple-switch-slider"></span>
                </label>
              </div>
              {theme.announcement_active && (
                <input
                  type="text"
                  value={theme.announcement_banner || ''}
                  onChange={(e) => setTheme((prev) => ({ ...prev, announcement_banner: e.target.value }))}
                  placeholder="e.g. 🚀 Check out our latest project launch!"
                  className="w-full px-3 py-1.5 text-xs rounded-lg bg-white dark:bg-[#2C2C2E] border border-black/[0.08] dark:border-white/[0.1] text-gray-900 dark:text-white outline-none focus:border-[#0071E3] transition"
                />
              )}
            </div>

            {/* Reset Theme Button */}
            <button
              onClick={onResetTheme}
              className="w-full py-2 rounded-xl border border-rose-200 dark:border-rose-900/40 text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/20 text-xs font-semibold transition-colors"
            >
              Reset Theme to Default
            </button>

          </div>
        )}

      </div>
    </div>
  );
}
