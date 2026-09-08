import React, { useState, useMemo } from 'react';
import {
  FaUndo,
  FaRedo,
  FaCheck,
  FaSearch,
  FaTimes,
  FaExternalLinkAlt,
  FaClock,
  FaTrashAlt,
  FaCalendarAlt,
  FaExclamationTriangle,
} from 'react-icons/fa';
import {
  THEME_PRESETS,
  HEADER_LAYOUTS,
  BUTTON_STYLES,
  BUTTON_SHAPES,
  FONTS_LIST,
  loadGoogleFont,
} from '@/lib/bioThemeUtils';

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
  { label: 'Indigo Glass', val: 'rgba(79, 70, 229, 0.40)', bg: '#4F46E5' },
  { label: 'Rose Glass', val: 'rgba(244, 63, 94, 0.35)', bg: '#F43F5E' },
  { label: 'Emerald Glass', val: 'rgba(16, 185, 129, 0.35)', bg: '#10B981' },
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
  { label: 'Emerald', val: '#10B981' },
  { label: 'Indigo', val: '#818CF8' },
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
  pageSchedule = { enabled: false, start_at: '', end_at: '' },
  setPageSchedule,
  isPublished = true,
  setIsPublished,
  onOpenScheduleModal,
  onDeletePage,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
  onResetTheme,
}) {
  const [activeTab, setActiveTab] = useState('themes'); // 'themes' | 'styles' | 'fonts' | 'settings'
  const [fontSearch, setFontSearch] = useState('');

  // Filter fonts
  const filteredFonts = useMemo(() => {
    if (!fontSearch.trim()) return FONTS_LIST;
    const q = fontSearch.toLowerCase();
    return FONTS_LIST.filter(
      (f) => f.label.toLowerCase().includes(q) || f.sample.toLowerCase().includes(q)
    );
  }, [fontSearch]);

  const applyThemePreset = (preset) => {
    loadGoogleFont(preset.font_family);
    setTheme((prev) => ({
      ...prev,
      preset: preset.id,
      background_type: preset.background_type || 'gradient',
      background_gradient: preset.background_gradient || preset.bg,
      background_color: preset.background_color || (preset.bg?.includes('#') ? preset.bg.slice(preset.bg.indexOf('#'), preset.bg.indexOf('#') + 7) : '#000000'),
      text_color: preset.text_color || preset.textColor || '#18181B',
      accent_color: preset.accent_color || preset.accentColor || '#0071E3',
      card_bg: preset.card_bg || preset.cardBg || '#FFFFFF',
      card_border: preset.card_border || preset.cardBorder || 'rgba(0,0,0,0.08)',
      card_text_color: preset.card_text_color || preset.cardTextColor || '#18181B',
      card_style: preset.card_style || 'solid_flat',
      font_family: preset.font_family || prev.font_family || 'Plus Jakarta Sans',
      card_corner_radius: prev.card_corner_radius ?? 16,
      card_spacing: prev.card_spacing ?? 12,
      button_style: prev.button_style || 'solid',
      button_shape: prev.button_shape || 'standard',
    }));
  };

  const handleSelectFont = (fontId) => {
    loadGoogleFont(fontId);
    setTheme((prev) => ({ ...prev, font_family: fontId }));
  };

  const currentShape = theme.button_shape || (
    (theme.card_corner_radius ?? 16) >= 40
      ? 'pill'
      : (theme.card_corner_radius ?? 16) <= 4
      ? 'sharp'
      : 'standard'
  );

  const currentButtonStyle = theme.button_style || 'solid';
  const currentHeaderLayout = theme.header_layout || 'centered';

  return (
    <div className="flex flex-col h-full bg-white/80 dark:bg-[#1C1C1E]/80 backdrop-blur-2xl border-l border-black/[0.06] dark:border-white/[0.08] text-gray-800 dark:text-gray-200 select-none overflow-hidden">
      
      {/* ── TOP HEADER WITH APPLE SEGMENTED CONTROL & UNDO/REDO ── */}
      <div className="p-3 border-b border-black/[0.04] dark:border-white/[0.06] flex items-center justify-between gap-2 shrink-0">
        <div className="apple-segment-wrapper flex-1 justify-between text-xs">
          <button
            onClick={() => setActiveTab('themes')}
            className={`apple-segment-btn flex-1 text-center py-1.5 text-xs ${activeTab === 'themes' ? 'active' : ''}`}
          >
            Themes
          </button>
          <button
            onClick={() => setActiveTab('styles')}
            className={`apple-segment-btn flex-1 text-center py-1.5 text-xs ${activeTab === 'styles' ? 'active' : ''}`}
          >
            Styles
          </button>
          <button
            onClick={() => setActiveTab('fonts')}
            className={`apple-segment-btn flex-1 text-center py-1.5 text-xs ${activeTab === 'fonts' ? 'active' : ''}`}
          >
            Fonts
          </button>
          <button
            onClick={() => setActiveTab('settings')}
            className={`apple-segment-btn flex-1 text-center py-1.5 text-xs ${activeTab === 'settings' ? 'active' : ''}`}
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
        
        {/* ══════════ 1. THEMES TAB (Screenshot 1 Reference) ══════════ */}
        {activeTab === 'themes' && (
          <div className="space-y-4 animate-in fade-in duration-200">
            <div className="flex items-center justify-between mb-1">
              <div>
                <h3 className="text-xs font-bold text-gray-900 dark:text-white">Default themes</h3>
                <p className="text-[11px] text-gray-500">Pick a handcrafted palette for your bio</p>
              </div>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#0071E3]/10 text-[#0071E3]">
                {THEME_PRESETS.length} Themes
              </span>
            </div>

            {/* Themes Grid */}
            <div className="grid grid-cols-2 gap-3">
              {THEME_PRESETS.map((preset) => {
                const isSelected = theme.preset === preset.id;
                return (
                  <button
                    key={preset.id}
                    onClick={() => applyThemePreset(preset)}
                    className={`group relative flex flex-col p-2.5 rounded-2xl border transition-all text-left overflow-hidden ${
                      isSelected
                        ? 'border-[#0071E3] ring-2 ring-[#0071E3]/30 bg-blue-50/20 dark:bg-blue-950/20 shadow-md scale-[1.02]'
                        : 'border-black/[0.07] dark:border-white/[0.08] hover:border-black/[0.2] dark:hover:border-white/[0.2] bg-white/70 dark:bg-zinc-900/70 hover:shadow-sm'
                    }`}
                  >
                    {/* Mini Visual Preview Card (Inspired by Screenshot 1) */}
                    <div
                      className="w-full h-24 rounded-xl p-2 flex flex-col items-center justify-between relative overflow-hidden shadow-inner mb-2 border border-black/5"
                      style={{
                        background: preset.background_gradient || preset.background_color,
                      }}
                    >
                      {/* Avatar Circle */}
                      <div
                        className="w-5 h-5 rounded-full bg-white/80 shadow-xs flex items-center justify-center text-[9px] font-black"
                        style={{ color: preset.accent_color || preset.text_color }}
                      >
                        ●
                      </div>

                      {/* Title Line */}
                      <div
                        className="w-10 h-1 rounded-full opacity-70"
                        style={{ backgroundColor: preset.text_color || '#FFFFFF' }}
                      />

                      {/* Card Preview Bar */}
                      <div
                        className="w-full h-7 rounded-lg shadow-sm border border-black/5 flex items-center justify-center px-1.5"
                        style={{
                          backgroundColor: preset.card_bg || '#FFFFFF',
                          borderColor: preset.card_border || 'transparent',
                        }}
                      >
                        <div
                          className="w-8 h-1 rounded-full opacity-60"
                          style={{ backgroundColor: preset.card_text_color || preset.accent_color }}
                        />
                      </div>
                    </div>

                    {/* Theme Label */}
                    <div className="flex items-center justify-between w-full">
                      <span className="text-[11px] font-bold text-gray-900 dark:text-gray-100 truncate">
                        {preset.name}
                      </span>
                      {isSelected && (
                        <span className="w-3.5 h-3.5 rounded-full bg-[#0071E3] text-white flex items-center justify-center text-[8px]">
                          <FaCheck />
                        </span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* ══════════ 2. STYLES TAB (Screenshot 2 Reference) ══════════ */}
        {activeTab === 'styles' && (
          <div className="space-y-6 animate-in fade-in duration-200">
            
            {/* Header Layout (5 Layouts as shown in Screenshot 2) */}
            <div>
              <div className="flex items-center justify-between mb-2.5">
                <label className="text-xs font-bold text-gray-900 dark:text-white">
                  Header Layout
                </label>
                <span className="text-[10px] text-gray-400 capitalize">{currentHeaderLayout.replace('_', ' ')}</span>
              </div>
              <div className="grid grid-cols-5 gap-2">
                
                {/* 1. Centered */}
                <button
                  onClick={() => setTheme((prev) => ({ ...prev, header_layout: 'centered' }))}
                  className={`p-2 rounded-xl border flex flex-col items-center justify-center h-16 transition-all ${
                    currentHeaderLayout === 'centered'
                      ? 'border-[#0071E3] bg-blue-50/40 dark:bg-blue-950/40 ring-1 ring-[#0071E3]'
                      : 'border-black/[0.08] dark:border-white/[0.08] hover:border-gray-400 bg-white/50 dark:bg-zinc-900/50'
                  }`}
                  title="Centered (Classic)"
                >
                  <div className="w-4 h-4 rounded-full bg-gray-300 dark:bg-gray-600 mb-1.5" />
                  <div className="w-6 h-1 rounded-full bg-gray-300 dark:bg-gray-600 mb-1" />
                  <div className="w-4 h-0.5 rounded-full bg-gray-200 dark:bg-gray-700" />
                </button>

                {/* 2. Top-Left Stacked */}
                <button
                  onClick={() => setTheme((prev) => ({ ...prev, header_layout: 'left_stacked' }))}
                  className={`p-2 rounded-xl border flex flex-col items-start justify-center h-16 pl-2.5 transition-all ${
                    currentHeaderLayout === 'left_stacked'
                      ? 'border-[#0071E3] bg-blue-50/40 dark:bg-blue-950/40 ring-1 ring-[#0071E3]'
                      : 'border-black/[0.08] dark:border-white/[0.08] hover:border-gray-400 bg-white/50 dark:bg-zinc-900/50'
                  }`}
                  title="Top-Left Stacked"
                >
                  <div className="w-4 h-4 rounded-full bg-gray-300 dark:bg-gray-600 mb-1.5" />
                  <div className="w-6 h-1 rounded-full bg-gray-300 dark:bg-gray-600 mb-1" />
                  <div className="w-4 h-0.5 rounded-full bg-gray-200 dark:bg-gray-700" />
                </button>

                {/* 3. Left Row (Inline) */}
                <button
                  onClick={() => setTheme((prev) => ({ ...prev, header_layout: 'left_row' }))}
                  className={`p-2 rounded-xl border flex items-center gap-1.5 justify-center h-16 transition-all ${
                    currentHeaderLayout === 'left_row'
                      ? 'border-[#0071E3] bg-blue-50/40 dark:bg-blue-950/40 ring-1 ring-[#0071E3]'
                      : 'border-black/[0.08] dark:border-white/[0.08] hover:border-gray-400 bg-white/50 dark:bg-zinc-900/50'
                  }`}
                  title="Left Row Inline"
                >
                  <div className="w-4 h-4 rounded-full bg-gray-300 dark:bg-gray-600 shrink-0" />
                  <div className="flex flex-col gap-1">
                    <div className="w-5 h-1 rounded-full bg-gray-300 dark:bg-gray-600" />
                    <div className="w-3.5 h-0.5 rounded-full bg-gray-200 dark:bg-gray-700" />
                  </div>
                </button>

                {/* 4. Top-Right Stacked */}
                <button
                  onClick={() => setTheme((prev) => ({ ...prev, header_layout: 'right_stacked' }))}
                  className={`p-2 rounded-xl border flex flex-col items-end justify-center h-16 pr-2.5 transition-all ${
                    currentHeaderLayout === 'right_stacked'
                      ? 'border-[#0071E3] bg-blue-50/40 dark:bg-blue-950/40 ring-1 ring-[#0071E3]'
                      : 'border-black/[0.08] dark:border-white/[0.08] hover:border-gray-400 bg-white/50 dark:bg-zinc-900/50'
                  }`}
                  title="Top-Right Stacked"
                >
                  <div className="w-4 h-4 rounded-full bg-gray-300 dark:bg-gray-600 mb-1.5" />
                  <div className="w-6 h-1 rounded-full bg-gray-300 dark:bg-gray-600 mb-1" />
                  <div className="w-4 h-0.5 rounded-full bg-gray-200 dark:bg-gray-700" />
                </button>

                {/* 5. Right Row (Inline) */}
                <button
                  onClick={() => setTheme((prev) => ({ ...prev, header_layout: 'right_row' }))}
                  className={`p-2 rounded-xl border flex items-center gap-1.5 justify-center h-16 transition-all ${
                    currentHeaderLayout === 'right_row'
                      ? 'border-[#0071E3] bg-blue-50/40 dark:bg-blue-950/40 ring-1 ring-[#0071E3]'
                      : 'border-black/[0.08] dark:border-white/[0.08] hover:border-gray-400 bg-white/50 dark:bg-zinc-900/50'
                  }`}
                  title="Right Row Inline"
                >
                  <div className="flex flex-col gap-1 items-end">
                    <div className="w-5 h-1 rounded-full bg-gray-300 dark:bg-gray-600" />
                    <div className="w-3.5 h-0.5 rounded-full bg-gray-200 dark:bg-gray-700" />
                  </div>
                  <div className="w-4 h-4 rounded-full bg-gray-300 dark:bg-gray-600 shrink-0" />
                </button>
              </div>

              {/* Header & Avatar Size Slider */}
              <div className="mt-3.5 p-3 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-gray-800 dark:text-gray-200">
                    Header & Avatar Size
                  </span>
                  <span className="font-mono text-[11px] font-bold text-[#0071E3]">
                    {theme.profile_picture_size ?? 96}px
                  </span>
                </div>
                <input
                  type="range"
                  className="apple-slider w-full"
                  min="48"
                  max="140"
                  step="4"
                  value={theme.profile_picture_size ?? 96}
                  onChange={(e) =>
                    setTheme((prev) => ({ ...prev, profile_picture_size: Number(e.target.value) }))
                  }
                />
                <div className="flex justify-between items-center text-[10px] text-gray-400 font-medium pt-0.5">
                  <button
                    type="button"
                    onClick={() => setTheme((prev) => ({ ...prev, profile_picture_size: 64 }))}
                    className={`px-1.5 py-0.5 rounded hover:text-gray-700 dark:hover:text-gray-300 transition ${
                      (theme.profile_picture_size ?? 96) === 64 ? 'font-bold text-[#0071E3]' : ''
                    }`}
                  >
                    Compact (64px)
                  </button>
                  <button
                    type="button"
                    onClick={() => setTheme((prev) => ({ ...prev, profile_picture_size: 96 }))}
                    className={`px-1.5 py-0.5 rounded hover:text-gray-700 dark:hover:text-gray-300 transition ${
                      (theme.profile_picture_size ?? 96) === 96 ? 'font-bold text-[#0071E3]' : ''
                    }`}
                  >
                    Standard (96px)
                  </button>
                  <button
                    type="button"
                    onClick={() => setTheme((prev) => ({ ...prev, profile_picture_size: 128 }))}
                    className={`px-1.5 py-0.5 rounded hover:text-gray-700 dark:hover:text-gray-300 transition ${
                      (theme.profile_picture_size ?? 96) === 128 ? 'font-bold text-[#0071E3]' : ''
                    }`}
                  >
                    Large (128px)
                  </button>
                </div>
              </div>
            </div>

            {/* Button Style (Solid vs Outline as shown in Screenshot 2) */}
            <div>
              <label className="text-xs font-bold text-gray-900 dark:text-white block mb-2.5">
                Button Style
              </label>
              <div className="grid grid-cols-2 gap-2.5">
                <button
                  onClick={() => setTheme((prev) => ({ ...prev, button_style: 'solid' }))}
                  className={`p-3 rounded-xl border flex items-center justify-center transition-all ${
                    currentButtonStyle === 'solid'
                      ? 'border-[#0071E3] ring-1 ring-[#0071E3] bg-blue-50/30 dark:bg-blue-950/30'
                      : 'border-black/[0.08] dark:border-white/[0.08] hover:border-gray-400 bg-white/50 dark:bg-zinc-900/50'
                  }`}
                >
                  <div className="w-20 py-1.5 rounded-lg bg-gray-200 dark:bg-gray-700 text-center text-xs font-bold text-gray-800 dark:text-gray-200">
                    Aa
                  </div>
                </button>

                <button
                  onClick={() => setTheme((prev) => ({ ...prev, button_style: 'outline' }))}
                  className={`p-3 rounded-xl border flex items-center justify-center transition-all ${
                    currentButtonStyle === 'outline'
                      ? 'border-[#0071E3] ring-1 ring-[#0071E3] bg-blue-50/30 dark:bg-blue-950/30'
                      : 'border-black/[0.08] dark:border-white/[0.08] hover:border-gray-400 bg-white/50 dark:bg-zinc-900/50'
                  }`}
                >
                  <div className="w-20 py-1.5 rounded-lg border border-gray-400 dark:border-gray-500 bg-transparent text-center text-xs font-bold text-gray-800 dark:text-gray-200">
                    Aa
                  </div>
                </button>
              </div>
            </div>

            {/* Button Shape (Standard, Pill, Sharp as shown in Screenshot 2) */}
            <div>
              <label className="text-xs font-bold text-gray-900 dark:text-white block mb-2.5">
                Button Shape
              </label>
              <div className="grid grid-cols-3 gap-2.5">
                {/* Standard (Squircle / Rounded) */}
                <button
                  onClick={() =>
                    setTheme((prev) => ({ ...prev, button_shape: 'standard', card_corner_radius: 16 }))
                  }
                  className={`p-3 rounded-xl border flex items-center justify-center transition-all ${
                    currentShape === 'standard'
                      ? 'border-[#0071E3] ring-1 ring-[#0071E3] bg-blue-50/30 dark:bg-blue-950/30'
                      : 'border-black/[0.08] dark:border-white/[0.08] hover:border-gray-400 bg-white/50 dark:bg-zinc-900/50'
                  }`}
                  title="Standard Squircle"
                >
                  <div className="w-14 h-5 rounded-lg bg-gray-200 dark:bg-gray-700" />
                </button>

                {/* Pill (Full Rounded) */}
                <button
                  onClick={() =>
                    setTheme((prev) => ({ ...prev, button_shape: 'pill', card_corner_radius: 9999 }))
                  }
                  className={`p-3 rounded-xl border flex items-center justify-center transition-all ${
                    currentShape === 'pill'
                      ? 'border-[#0071E3] ring-1 ring-[#0071E3] bg-blue-50/30 dark:bg-blue-950/30'
                      : 'border-black/[0.08] dark:border-white/[0.08] hover:border-gray-400 bg-white/50 dark:bg-zinc-900/50'
                  }`}
                  title="Full Pill"
                >
                  <div className="w-14 h-5 rounded-full bg-gray-200 dark:bg-gray-700" />
                </button>

                {/* Sharp (Rectangle) */}
                <button
                  onClick={() =>
                    setTheme((prev) => ({ ...prev, button_shape: 'sharp', card_corner_radius: 0 }))
                  }
                  className={`p-3 rounded-xl border flex items-center justify-center transition-all ${
                    currentShape === 'sharp'
                      ? 'border-[#0071E3] ring-1 ring-[#0071E3] bg-blue-50/30 dark:bg-blue-950/30'
                      : 'border-black/[0.08] dark:border-white/[0.08] hover:border-gray-400 bg-white/50 dark:bg-zinc-900/50'
                  }`}
                  title="Sharp Rectangle"
                >
                  <div className="w-14 h-5 rounded-none bg-gray-200 dark:bg-gray-700" />
                </button>
              </div>
            </div>

            {/* Accent Color Swatches */}
            <div>
              <label className="text-xs font-bold text-gray-900 dark:text-white block mb-2.5">
                Accent Brand Color
              </label>
              <div className="flex flex-wrap gap-2">
                {ACCENT_SWATCHES.map((hex) => (
                  <button
                    key={hex}
                    onClick={() => setTheme((prev) => ({ ...prev, accent_color: hex }))}
                    className={`w-6 h-6 rounded-full border border-black/10 transition-transform ${
                      theme.accent_color === hex ? 'scale-125 ring-2 ring-[#0071E3]' : 'hover:scale-110'
                    }`}
                    style={{ backgroundColor: hex }}
                  />
                ))}
              </div>
            </div>

            {/* Fine-Tuning Sliders */}
            <div className="space-y-4 p-3.5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08]">
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

        {/* ══════════ 3. FONTS TAB (Screenshot 3 Reference) ══════════ */}
        {activeTab === 'fonts' && (
          <div className="space-y-4 animate-in fade-in duration-200">
            <div>
              <h3 className="text-xs font-bold text-gray-900 dark:text-white">Choose a font</h3>
              <p className="text-[11px] text-gray-500">Pick typography that matches your brand voice</p>
            </div>

            {/* Search for a Font Input */}
            <div className="relative">
              <FaSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs" />
              <input
                type="text"
                value={fontSearch}
                onChange={(e) => setFontSearch(e.target.value)}
                placeholder="Search for a font..."
                className="w-full pl-8 pr-8 py-2 text-xs rounded-xl bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.08] dark:border-white/[0.1] text-gray-900 dark:text-white placeholder-gray-400 outline-none focus:border-[#0071E3] transition"
              />
              {fontSearch && (
                <button
                  onClick={() => setFontSearch('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xs"
                >
                  <FaTimes />
                </button>
              )}
            </div>

            {/* Font Cards Grid */}
            <div className="grid grid-cols-2 gap-2.5">
              {filteredFonts.map((font) => {
                const isSelected = (theme.font_family || 'Plus Jakarta Sans') === font.id;
                return (
                  <button
                    key={font.id}
                    onClick={() => handleSelectFont(font.id)}
                    className={`p-3.5 rounded-2xl border text-center flex flex-col items-center justify-between min-h-[82px] transition-all ${
                      isSelected
                        ? 'border-[#0071E3] ring-2 ring-[#0071E3]/30 bg-blue-50/40 dark:bg-blue-950/40 scale-[1.02] shadow-sm'
                        : 'border-black/[0.07] dark:border-white/[0.08] hover:border-gray-400 bg-white/70 dark:bg-zinc-900/70 hover:shadow-xs'
                    }`}
                  >
                    {/* Font Preview Specimen */}
                    <div
                      className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white mb-1"
                      style={{ fontFamily: font.id }}
                    >
                      AaBb
                    </div>
                    {/* Font Name */}
                    <div className="text-[11px] font-medium text-gray-600 dark:text-gray-400 truncate w-full">
                      {font.label}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* ══════════ 4. SETTINGS TAB ══════════ */}
        {activeTab === 'settings' && (
          <div className="space-y-5 animate-in fade-in duration-200">
            
            {/* Profile Avatar Diameter */}
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
              <label className="text-xs font-bold text-gray-900 dark:text-white block mb-2">
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

            {/* Page Visibility & Scheduling Window */}
            <div className="p-3.5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-lg bg-blue-50 dark:bg-blue-900/30 text-[#0071E3] flex items-center justify-center text-xs">
                    <FaClock />
                  </div>
                  <div>
                    <span className="text-xs font-semibold text-gray-800 dark:text-gray-200 block">
                      Scheduled Live Window
                    </span>
                    <span className="text-[10px] text-gray-500 block">
                      Optional start & expiry times
                    </span>
                  </div>
                </div>
                <label className="apple-switch">
                  <input
                    type="checkbox"
                    checked={Boolean(pageSchedule?.enabled)}
                    onChange={(e) =>
                      setPageSchedule?.((prev) => ({ ...prev, enabled: e.target.checked }))
                    }
                  />
                  <span className="apple-switch-slider"></span>
                </label>
              </div>

              {pageSchedule?.enabled && (
                <div className="space-y-2.5 pt-1 animate-in fade-in duration-150 border-t border-black/[0.05] dark:border-white/[0.05]">
                  <p className="text-[11px] text-gray-500 leading-relaxed">
                    Your Smart Bio URL will only be live during this window. Before start or after expiry, visitors see a scheduled card.
                  </p>
                  <div>
                    <label className="text-[11px] font-medium text-gray-600 dark:text-gray-400 block mb-1">
                      Start Time (Go-Live)
                    </label>
                    <input
                      type="datetime-local"
                      value={pageSchedule?.start_at || ''}
                      onChange={(e) =>
                        setPageSchedule?.((prev) => ({ ...prev, start_at: e.target.value }))
                      }
                      className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-white dark:bg-[#2C2C2E] border border-black/[0.08] dark:border-white/[0.1] text-gray-900 dark:text-white outline-none focus:border-[#0071E3] transition"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-gray-600 dark:text-gray-400 block mb-1">
                      End Time (Expiry)
                    </label>
                    <input
                      type="datetime-local"
                      value={pageSchedule?.end_at || ''}
                      onChange={(e) =>
                        setPageSchedule?.((prev) => ({ ...prev, end_at: e.target.value }))
                      }
                      className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-white dark:bg-[#2C2C2E] border border-black/[0.08] dark:border-white/[0.1] text-gray-900 dark:text-white outline-none focus:border-[#0071E3] transition"
                    />
                  </div>
                  {(pageSchedule?.start_at || pageSchedule?.end_at) && (
                    <button
                      type="button"
                      onClick={() => setPageSchedule?.((prev) => ({ ...prev, start_at: '', end_at: '' }))}
                      className="text-[10px] text-rose-500 hover:text-rose-600 underline font-medium block"
                    >
                      Clear schedule times
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={() => onOpenScheduleModal?.()}
                    className="w-full py-1.5 px-3 rounded-xl border border-black/[0.08] dark:border-white/[0.1] bg-white dark:bg-[#2C2C2E] text-xs font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-[#3A3A3C] transition flex items-center justify-center gap-1.5 shadow-xs cursor-pointer active:scale-98"
                  >
                    <FaCalendarAlt className="text-[10px] text-[#0071E3]" />
                    <span>Open Schedule Window Manager</span>
                  </button>
                </div>
              )}
            </div>

            {/* Public Availability Toggle */}
            <div className="p-3.5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] space-y-1.5">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-gray-800 dark:text-gray-200 block">
                    Page Published
                  </span>
                  <span className="text-[10px] text-gray-500 block">
                    {isPublished ? 'Public URL is active & reachable' : 'Page is in private draft mode'}
                  </span>
                </div>
                <label className="apple-switch">
                  <input
                    type="checkbox"
                    checked={Boolean(isPublished)}
                    onChange={(e) => setIsPublished?.(e.target.checked)}
                  />
                  <span className="apple-switch-slider"></span>
                </label>
              </div>
            </div>

            {/* Reset Theme Button */}
            <button
              onClick={onResetTheme}
              className="w-full py-2.5 rounded-xl border border-gray-200 dark:border-white/[0.1] text-gray-700 dark:text-gray-300 hover:bg-black/[0.02] dark:hover:bg-white/[0.05] text-xs font-semibold transition-colors"
            >
              Reset Theme to Default
            </button>

            {/* Danger Zone: Permanent Deletion */}
            <div className="p-3.5 rounded-2xl bg-rose-50/60 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-900/40 space-y-2.5 mt-4">
              <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
                <FaExclamationTriangle className="text-xs" />
                <span className="text-[11px] font-bold uppercase tracking-wider">Danger Zone</span>
              </div>
              <p className="text-[11px] text-gray-600 dark:text-gray-400 leading-relaxed">
                Permanently delete your Smart Bio page, release your handle, and erase all blocks, visitor analytics, and subscriber leads.
              </p>
              <button
                type="button"
                onClick={onDeletePage}
                className="w-full py-2 px-3 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold shadow-xs flex items-center justify-center gap-2 transition-colors active:scale-[0.99]"
              >
                <FaTrashAlt className="text-[11px]" />
                Delete Published Page Permanently
              </button>
            </div>

          </div>
        )}

      </div>
    </div>
  );
}
