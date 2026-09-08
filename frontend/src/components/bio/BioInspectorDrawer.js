import React, { useState } from 'react';
import {
  FaUndo,
  FaRedo,
  FaSearch,
  FaChevronRight,
  FaChevronLeft,
  FaTimes,
  FaPalette,
  FaLayerGroup,
  FaFont,
  FaSlidersH,
  FaShareAlt,
  FaImage,
  FaMagic,
  FaCheck,
  FaSun,
  FaMoon,
  FaEyeDropper,
  FaBolt,
  FaCube,
  FaBorderAll,
  FaBullhorn,
} from 'react-icons/fa';
import {
  THEME_PRESETS,
  TACTILE_CARD_STYLES,
  BACKGROUND_EFFECTS,
  HEADER_LAYOUTS,
} from '@/lib/bioThemeUtils';

const FONTS_LIST = [
  { id: 'Plus Jakarta Sans', label: 'Plus Jakarta Sans (Modern Clean)', sample: 'The quick brown fox jumps' },
  { id: 'Geist', label: 'Geist (Vercel Precision)', sample: 'The quick brown fox jumps' },
  { id: 'Outfit', label: 'Outfit (Geometric Luxury)', sample: 'The quick brown fox jumps' },
  { id: 'Playfair Display', label: 'Playfair Display (Editorial Serif)', sample: 'The quick brown fox jumps' },
  { id: 'Space Grotesk', label: 'Space Grotesk (Tech Monospace)', sample: 'The quick brown fox jumps' },
  { id: 'Inter', label: 'Inter (Standard Sans)', sample: 'The quick brown fox jumps' },
];

const COLOR_SWATCHES = [
  '#4F46E5', '#6366F1', '#8B5CF6', '#EC4899', '#F43F5E',
  '#F59E0B', '#10B981', '#06B6D4', '#0EA5E9', '#18181B',
  '#FFFFFF', '#FDFBF7', '#09090B', '#14110E', '#05050A'
];

const GRADIENT_PRESETS = [
  { label: 'Warm Cream', value: 'linear-gradient(135deg, #FDFBF7 0%, #F4EDE2 100%)', bg: '#FDFBF7', text: '#18181B' },
  { label: 'OLED Black', value: 'linear-gradient(180deg, #09090B 0%, #18181B 100%)', bg: '#09090B', text: '#FAFAFA' },
  { label: 'Sunset Aura', value: 'linear-gradient(135deg, #FFE4E6 0%, #EDE9FE 50%, #FEF3C7 100%)', bg: '#FFF1F2', text: '#4C0519' },
  { label: 'Velvet Truffle', value: 'linear-gradient(180deg, #14110E 0%, #201A15 100%)', bg: '#14110E', text: '#FEF3C7' },
  { label: 'Tokyo Cyber', value: 'linear-gradient(135deg, #05050A 0%, #0D081E 50%, #15002A 100%)', bg: '#05050A', text: '#00F0FF' },
  { label: 'Matcha Washi', value: 'linear-gradient(180deg, #F5F7F2 0%, #E8EDE4 100%)', bg: '#F5F7F2', text: '#1E3A2F' },
  { label: 'Electric Indigo', value: 'linear-gradient(135deg, #1E1B4B 0%, #0F172A 50%, #311042 100%)', bg: '#0F172A', text: '#F8FAFC' },
  { label: 'Nordic Aurora', value: 'linear-gradient(135deg, #030D1A 0%, #06243A 60%, #064E3B 100%)', bg: '#030D1A', text: '#E0F2FE' },
];

const CARD_BG_SWATCHES = [
  { label: 'White', val: '#FFFFFF', bg: '#FFFFFF' },
  { label: 'Cream', val: '#FDFBF7', bg: '#FDFBF7' },
  { label: 'Dark Slate', val: '#1E293B', bg: '#1E293B' },
  { label: 'OLED Black', val: '#09090B', bg: '#09090B' },
  { label: 'Glass White', val: 'rgba(255, 255, 255, 0.85)', bg: 'rgba(255, 255, 255, 0.85)' },
  { label: 'Dark Glass', val: 'rgba(24, 24, 27, 0.80)', bg: 'rgba(24, 24, 27, 0.80)' },
  { label: 'Indigo Glass', val: 'rgba(79, 70, 229, 0.15)', bg: '#4F46E5' },
  { label: 'Rose Glass', val: 'rgba(244, 63, 94, 0.15)', bg: '#F43F5E' },
  { label: 'Emerald Glass', val: 'rgba(16, 185, 129, 0.15)', bg: '#10B981' },
  { label: 'Amber Glass', val: 'rgba(245, 158, 11, 0.15)', bg: '#F59E0B' },
];

const rgbaToHex = (colorStr, fallback = '#FFFFFF') => {
  if (!colorStr) return fallback;
  if (colorStr.startsWith('#')) return colorStr.slice(0, 7);
  const match = colorStr.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (match) {
    const r = parseInt(match[1], 10).toString(16).padStart(2, '0');
    const g = parseInt(match[2], 10).toString(16).padStart(2, '0');
    const b = parseInt(match[3], 10).toString(16).padStart(2, '0');
    return `#${r}${g}${b}`;
  }
  return fallback;
};

export default function BioInspectorDrawer({
  theme,
  setTheme,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
  onResetTheme,
}) {
  const [activeCategory, setActiveCategory] = useState('root');
  const [searchQuery, setSearchQuery] = useState('');

  const handleSelectPreset = (preset) => {
    setTheme({
      ...theme,
      ...preset,
      card_corner_radius: theme.card_corner_radius ?? 20,
      card_border_width: theme.card_border_width ?? 0,
      card_shadow_depth: theme.card_shadow_depth ?? 100,
      card_shadow_type: theme.card_shadow_type ?? 'soft',
      card_spacing: theme.card_spacing ?? 33,
      profile_picture_size: theme.profile_picture_size ?? 50,
      profile_picture_shadow: theme.profile_picture_shadow ?? 0,
      profile_picture_border: theme.profile_picture_border ?? 0,
      social_icon_size: theme.social_icon_size ?? 0,
      tactile_blocks: theme.tactile_blocks ?? true,
    });
  };

  const categories = [
    {
      id: 'templates',
      title: 'Templates',
      badge: '18 Presets',
      isRainbow: true,
      icon: FaPalette,
      desc: '1-click designer themes, typography & color stories',
    },
    {
      id: 'blocks',
      title: 'Block Styles',
      badge: 'Cards & 3D',
      icon: FaLayerGroup,
      desc: 'Tactile card styles, background color, borders, corner radius, shadows',
    },
    {
      id: 'colors',
      title: 'Colors & Backdrop',
      badge: 'Palette',
      icon: FaMagic,
      desc: 'Solid, gradient, liquid mesh aura, accent color & film grain',
    },
    {
      id: 'general',
      title: 'General & Profile',
      badge: 'Header',
      icon: FaSlidersH,
      desc: 'Header layout, avatar sizing & borders, collapse long bio',
    },
    {
      id: 'fonts',
      title: 'Fonts & Typography',
      badge: '6 Fonts',
      icon: FaFont,
      desc: 'Font family, weights and text pairings',
    },
    {
      id: 'socials',
      title: 'Social Dock',
      badge: 'Icons',
      icon: FaShareAlt,
      desc: 'Dock position (top/bottom), icon sizes, and tactile glass styles',
    },
    {
      id: 'navigation',
      title: 'Pages & Navigation',
      badge: 'Sub-Sites',
      icon: FaBorderAll,
      desc: 'Pill tabs dock, sticky top bar, or mobile bottom bar',
    },
    {
      id: 'announcement',
      title: 'Announcement Banner',
      badge: 'Marquee',
      icon: FaBullhorn,
      desc: 'Top call-to-action banner for sales, drops, or news',
    },
  ];

  const filteredCategories = categories.filter((c) =>
    c.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    c.desc.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full bg-white/80 dark:bg-[#1C1C1E]/80 backdrop-blur-2xl border-l border-black/[0.06] dark:border-white/[0.08] text-gray-800 dark:text-gray-200 select-none overflow-y-auto custom-scrollbar">
      
      {/* ── Top Inspector Bar: Search & Undo / Redo (Apple Frosted Header) ── */}
      <div className="p-3 border-b border-black/[0.06] dark:border-white/[0.08] flex items-center justify-between gap-2 shrink-0 bg-white/80 dark:bg-[#1C1C1E]/80 backdrop-blur-2xl z-10 sticky top-0">
        {activeCategory === 'root' ? (
          <div className="relative flex-1">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search theme styles…"
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-black/[0.04] dark:bg-white/[0.06] border border-black/[0.06] dark:border-white/[0.08] rounded-full outline-none focus:ring-2 focus:ring-[#0071E3] text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 font-medium"
            />
            <FaSearch className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 text-[10px]" />
          </div>
        ) : (
          <button
            onClick={() => setActiveCategory('root')}
            className="flex items-center gap-1.5 text-xs font-semibold text-gray-700 dark:text-gray-300 hover:text-[#0071E3] dark:hover:text-blue-400 px-2.5 py-1 rounded-full hover:bg-black/[0.04] dark:hover:bg-white/[0.06] transition-colors"
          >
            <FaChevronLeft className="text-[10px]" />
            <span className="capitalize">{categories.find(c => c.id === activeCategory)?.title || 'Styles'}</span>
          </button>
        )}

        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={onUndo}
            disabled={!canUndo}
            className="p-1.5 rounded-full border border-black/[0.06] dark:border-white/[0.08] bg-black/[0.03] dark:bg-white/[0.06] hover:bg-black/[0.06] dark:hover:bg-white/[0.1] text-gray-600 dark:text-gray-300 disabled:opacity-25 transition-colors"
            title="Undo"
          >
            <FaUndo className="text-[10px]" />
          </button>
          <button
            onClick={onRedo}
            disabled={!canRedo}
            className="p-1.5 rounded-full border border-black/[0.06] dark:border-white/[0.08] bg-black/[0.03] dark:bg-white/[0.06] hover:bg-black/[0.06] dark:hover:bg-white/[0.1] text-gray-600 dark:text-gray-300 disabled:opacity-25 transition-colors"
            title="Redo"
          >
            <FaRedo className="text-[10px]" />
          </button>
        </div>
      </div>

      {/* ── Root: Categories Navigation List ── */}
      {activeCategory === 'root' && (
        <div className="p-3.5 space-y-2">
          {filteredCategories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setActiveCategory(cat.id)}
              className="w-full flex items-center justify-between p-3 rounded-2xl border border-black/[0.06] dark:border-white/[0.08] bg-white/70 dark:bg-white/[0.04] hover:bg-white dark:hover:bg-white/[0.08] hover:border-black/[0.12] dark:hover:border-white/[0.15] transition-all text-left group shadow-[0_1px_2px_rgba(0,0,0,0.03)] hover:shadow-xs"
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <div className={`p-2.5 rounded-xl text-sm ${cat.isRainbow ? 'bg-gradient-to-tr from-blue-500 via-indigo-500 to-purple-500 text-white shadow-2xs' : 'bg-black/[0.04] dark:bg-white/[0.08] text-gray-700 dark:text-gray-200 group-hover:text-[#0071E3] dark:group-hover:text-blue-400'}`}>
                  <cat.icon />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <p className="text-xs font-semibold text-gray-900 dark:text-white truncate">{cat.title}</p>
                    {cat.badge && (
                      <span className="px-2 py-0.5 rounded-full text-[9px] font-semibold bg-black/[0.04] dark:bg-white/[0.08] text-gray-600 dark:text-gray-300 border border-black/[0.04] dark:border-white/[0.06]">
                        {cat.badge}
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] text-gray-500 dark:text-gray-400 truncate mt-0.5">{cat.desc}</p>
                </div>
              </div>
              <FaChevronRight className="text-xs text-gray-400 dark:text-gray-500 group-hover:text-gray-600 dark:group-hover:text-gray-300 transition-transform group-hover:translate-x-0.5 shrink-0 ml-2" />
            </button>
          ))}

          <div className="pt-4 text-center">
            <button
              onClick={onResetTheme}
              className="text-[11px] font-semibold text-gray-400 dark:text-gray-500 hover:text-rose-500 dark:hover:text-rose-400 transition-colors"
            >
              Reset to Default Editorial Cream
            </button>
          </div>
        </div>
      )}

      {/* ── Sub-panel 1: Templates (18 Presets) ── */}
      {activeCategory === 'templates' && (
        <div className="p-3.5 space-y-3">
          <p className="text-xs text-gray-500 dark:text-gray-400">Select any template to instantly apply curated styling, colors, and 3D card physics.</p>
          <div className="grid grid-cols-2 gap-2.5">
            {THEME_PRESETS.map((preset) => {
              const isSelected = theme.preset === preset.id || theme.name === preset.name;
              return (
                <button
                  key={preset.id}
                  onClick={() => handleSelectPreset(preset)}
                  className={`p-3 rounded-2xl border text-left transition-all relative overflow-hidden group ${
                    isSelected
                      ? 'border-[#0071E3] ring-2 ring-[#0071E3]/20 bg-blue-50/40 dark:bg-blue-950/20 shadow-xs'
                      : 'border-black/[0.06] dark:border-white/[0.08] hover:border-black/[0.12] dark:hover:border-white/[0.15] bg-white/60 dark:bg-white/[0.03] hover:bg-white dark:hover:bg-white/[0.06]'
                  }`}
                >
                  <div
                    className="w-full h-10 rounded-xl mb-2 flex items-center justify-center p-1.5 shadow-2xs"
                    style={{ background: preset.background_gradient || preset.background_color }}
                  >
                    <div
                      className="w-full h-5 rounded-md flex items-center justify-center text-[9px] font-bold shadow-xs truncate px-1"
                      style={{
                        background: preset.card_bg,
                        color: preset.card_text_color,
                        borderColor: preset.card_border,
                        borderWidth: '1px',
                        borderStyle: 'solid',
                      }}
                    >
                      {preset.name}
                    </div>
                  </div>
                  <p className="text-xs font-semibold text-gray-900 dark:text-white truncate">{preset.name}</p>
                  <p className="text-[10px] text-gray-500 dark:text-gray-400 line-clamp-1 mt-0.5">{preset.subtitle}</p>
                  {isSelected && (
                    <div className="absolute top-2 right-2 w-4 h-4 rounded-full bg-[#0071E3] text-white flex items-center justify-center text-[9px] shadow-2xs">
                      <FaCheck />
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Sub-panel 2: Block Styles (Cards, Physics, Colors, Sliders) ── */}
      {activeCategory === 'blocks' && (
        <div className="p-3.5 space-y-5">
          
          {/* Card Style Archetypes */}
          <div>
            <label className="block text-xs font-semibold text-gray-900 dark:text-white mb-2">
              Tactile Card Style Archetype
            </label>
            <div className="space-y-1.5">
              {TACTILE_CARD_STYLES.map((cs) => {
                const isSelected = (theme.card_style || 'glass_double_bezel') === cs.id;
                return (
                  <button
                    key={cs.id}
                    onClick={() => setTheme((prev) => ({ ...prev, card_style: cs.id }))}
                    className={`w-full p-2.5 rounded-2xl border text-left transition-all flex items-center justify-between ${
                      isSelected
                        ? 'border-[#0071E3] bg-blue-50/60 dark:bg-blue-950/40 text-[#0071E3] dark:text-blue-400 font-semibold shadow-2xs'
                        : 'border-black/[0.06] dark:border-white/[0.08] hover:border-black/[0.12] dark:hover:border-white/[0.15] text-gray-700 dark:text-gray-300 bg-white/60 dark:bg-white/[0.04]'
                    }`}
                  >
                    <div>
                      <p className="text-xs font-semibold">{cs.label}</p>
                      <p className="text-[10px] text-gray-500 dark:text-gray-400 font-normal mt-0.5">{cs.description}</p>
                    </div>
                    {isSelected && <FaCheck className="text-xs shrink-0 ml-2 text-[#0071E3]" />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Tactile 3D Physics Toggle */}
          <div className="flex items-center justify-between p-3 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08]">
            <div>
              <p className="text-xs font-semibold text-gray-900 dark:text-white">Tactile 3D Physics</p>
              <p className="text-[11px] text-gray-400 dark:text-gray-500">Specular highlights & convex tactile insets</p>
            </div>
            <input
              type="checkbox"
              checked={theme.tactile_blocks ?? true}
              onChange={(e) => setTheme((prev) => ({ ...prev, tactile_blocks: e.target.checked }))}
              className="w-4 h-4 text-[#0071E3] rounded-sm focus:ring-[#0071E3] cursor-pointer"
            />
          </div>

          {/* Card Color Controls */}
          <div className="space-y-3.5 pt-2 border-t border-black/[0.06] dark:border-white/[0.08]">
            <label className="block text-xs font-semibold text-gray-900 dark:text-white">
              Card Colors & Surface
            </label>

            {/* Card Background Color */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">Card Background</span>
                  <p className="text-[10px] text-gray-500 dark:text-gray-400">Fill color behind content</p>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={rgbaToHex(theme.card_bg, '#FFFFFF')}
                    onChange={(e) => setTheme((prev) => ({ ...prev, card_bg: e.target.value }))}
                    className="w-8 h-8 rounded-lg cursor-pointer border border-black/[0.06] dark:border-white/[0.08] bg-transparent"
                  />
                  <input
                    type="text"
                    value={theme.card_bg || '#FFFFFF'}
                    onChange={(e) => setTheme((prev) => ({ ...prev, card_bg: e.target.value }))}
                    className="w-24 px-2 py-1 text-xs font-mono bg-black/[0.03] dark:bg-white/[0.06] border border-black/[0.06] dark:border-white/[0.08] rounded-xl text-gray-800 dark:text-gray-200 outline-none"
                  />
                </div>
              </div>

              {/* Quick Card Color Swatches */}
              <div className="flex items-center gap-1.5 flex-wrap">
                {CARD_BG_SWATCHES.map((sw, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setTheme((prev) => ({ ...prev, card_bg: sw.val }))}
                    className="w-6 h-6 rounded-lg border border-black/15 dark:border-white/20 transition-transform hover:scale-110 shadow-2xs relative"
                    style={{ background: sw.bg }}
                    title={sw.label}
                  />
                ))}
              </div>

              {/* Quick Card Opacity Presets */}
              <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
                <span className="text-[10px] font-semibold text-gray-500 dark:text-gray-400 mr-1">Opacity:</span>
                {[
                  { label: 'Solid', val: rgbaToHex(theme.card_bg, '#FFFFFF') },
                  { label: '90%', val: 'rgba(255, 255, 255, 0.90)' },
                  { label: '80% Glass', val: 'rgba(255, 255, 255, 0.80)' },
                  { label: 'Dark Glass', val: 'rgba(24, 24, 27, 0.80)' },
                  { label: 'Frosted', val: 'rgba(255, 255, 255, 0.60)' },
                ].map((op, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setTheme((prev) => ({ ...prev, card_bg: op.val }))}
                    className="px-2.5 py-0.5 text-[10px] font-semibold rounded-full bg-black/[0.04] dark:bg-white/[0.06] hover:bg-black/[0.08] dark:hover:bg-white/[0.1] text-gray-700 dark:text-gray-300 transition-colors"
                  >
                    {op.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Card Text Color */}
            <div className="space-y-1.5 pt-1 border-t border-black/[0.06] dark:border-white/[0.08]">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">Card Text Color</span>
                  <p className="text-[10px] text-gray-500 dark:text-gray-400">Headlines & subtitles inside cards</p>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={rgbaToHex(theme.card_text_color, '#18181B')}
                    onChange={(e) => setTheme((prev) => ({ ...prev, card_text_color: e.target.value }))}
                    className="w-8 h-8 rounded-lg cursor-pointer border border-black/[0.06] dark:border-white/[0.08] bg-transparent"
                  />
                  <input
                    type="text"
                    value={theme.card_text_color || '#18181B'}
                    onChange={(e) => setTheme((prev) => ({ ...prev, card_text_color: e.target.value }))}
                    className="w-24 px-2 py-1 text-xs font-mono bg-black/[0.03] dark:bg-white/[0.06] border border-black/[0.06] dark:border-white/[0.08] rounded-xl text-gray-800 dark:text-gray-200 outline-none"
                  />
                </div>
              </div>
              <div className="flex items-center gap-1.5 flex-wrap">
                {['#18181B', '#FAFAFA', '#FEF3C7', '#4F46E5', '#10B981', '#F43F5E', '#00F0FF'].map((tc) => (
                  <button
                    key={tc}
                    type="button"
                    onClick={() => setTheme((prev) => ({ ...prev, card_text_color: tc }))}
                    className="w-5 h-5 rounded-full border border-black/15 dark:border-white/20 transition-transform hover:scale-110 shadow-2xs"
                    style={{ background: tc }}
                    title={tc}
                  />
                ))}
              </div>
            </div>

            {/* Card Border Color */}
            <div className="space-y-1.5 pt-1 border-t border-black/[0.06] dark:border-white/[0.08]">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">Card Border Color</span>
                  <p className="text-[10px] text-gray-500 dark:text-gray-400">Outer rim highlight</p>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={rgbaToHex(theme.card_border, '#000000')}
                    onChange={(e) => setTheme((prev) => ({ ...prev, card_border: e.target.value }))}
                    className="w-8 h-8 rounded-lg cursor-pointer border border-black/[0.06] dark:border-white/[0.08] bg-transparent"
                  />
                  <input
                    type="text"
                    value={theme.card_border || 'rgba(0,0,0,0.08)'}
                    onChange={(e) => setTheme((prev) => ({ ...prev, card_border: e.target.value }))}
                    className="w-24 px-2 py-1 text-xs font-mono bg-black/[0.03] dark:bg-white/[0.06] border border-black/[0.06] dark:border-white/[0.08] rounded-xl text-gray-800 dark:text-gray-200 outline-none"
                  />
                </div>
              </div>
              <div className="flex items-center gap-1.5 flex-wrap">
                {['rgba(0,0,0,0.08)', 'rgba(255,255,255,0.15)', '#000000', '#FFFFFF', '#6366F1', '#F59E0B', '#00F0FF'].map((bc) => (
                  <button
                    key={bc}
                    type="button"
                    onClick={() => setTheme((prev) => ({ ...prev, card_border: bc }))}
                    className="w-5 h-5 rounded-full border border-black/15 dark:border-white/20 transition-transform hover:scale-110 shadow-2xs"
                    style={{ background: bc }}
                    title={bc}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Sliders: Corner Radius, Border Width, Shadow, Spacing */}
          <div className="space-y-4 pt-2 border-t border-black/[0.06] dark:border-white/[0.08]">
            <div>
              <div className="flex items-center justify-between text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                <span>Corner Radius (Roundness)</span>
                <span className="text-gray-400 dark:text-gray-500 font-mono">{theme.card_corner_radius ?? 20}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={theme.card_corner_radius ?? 20}
                onChange={(e) => setTheme({ ...theme, card_corner_radius: parseInt(e.target.value, 10) })}
                className="w-full accent-[#0071E3] cursor-pointer"
              />
            </div>

            <div>
              <div className="flex items-center justify-between text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                <span>Border Width</span>
                <span className="text-gray-400 dark:text-gray-500 font-mono">{theme.card_border_width ?? 0}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={theme.card_border_width ?? 0}
                onChange={(e) => setTheme({ ...theme, card_border_width: parseInt(e.target.value, 10) })}
                className="w-full accent-[#0071E3] cursor-pointer"
              />
            </div>

            <div>
              <div className="flex items-center justify-between text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                <span>Shadow Depth</span>
                <span className="text-gray-400 dark:text-gray-500 font-mono">{theme.card_shadow_depth ?? 100}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={theme.card_shadow_depth ?? 100}
                onChange={(e) => setTheme({ ...theme, card_shadow_depth: parseInt(e.target.value, 10) })}
                className="w-full accent-[#0071E3] cursor-pointer"
              />
            </div>

            {/* Soft vs Solid Shadow Toggle */}
            <div className="grid grid-cols-2 gap-2 pt-1">
              <button
                type="button"
                onClick={() => setTheme({ ...theme, card_shadow_type: 'soft' })}
                className={`py-1.5 text-xs font-semibold rounded-xl border transition-colors ${
                  (theme.card_shadow_type || 'soft') === 'soft'
                    ? 'border-[#0071E3] bg-blue-50/60 dark:bg-blue-950/40 text-[#0071E3] dark:text-blue-400 shadow-2xs'
                    : 'border-black/[0.06] dark:border-white/[0.08] text-gray-600 dark:text-gray-400 bg-white/60 dark:bg-white/[0.04]'
                }`}
              >
                Soft Ambient Shadow
              </button>
              <button
                type="button"
                onClick={() => setTheme({ ...theme, card_shadow_type: 'solid' })}
                className={`py-1.5 text-xs font-semibold rounded-xl border transition-colors ${
                  theme.card_shadow_type === 'solid'
                    ? 'border-[#0071E3] bg-blue-50/60 dark:bg-blue-950/40 text-[#0071E3] dark:text-blue-400 shadow-2xs'
                    : 'border-black/[0.06] dark:border-white/[0.08] text-gray-600 dark:text-gray-400 bg-white/60 dark:bg-white/[0.04]'
                }`}
              >
                Solid Neobrutalist
              </button>
            </div>

            <div>
              <div className="flex items-center justify-between text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                <span>Card Spacing Gap</span>
                <span className="text-gray-400 dark:text-gray-500 font-mono">{theme.card_spacing ?? 33}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={theme.card_spacing ?? 33}
                onChange={(e) => setTheme({ ...theme, card_spacing: parseInt(e.target.value, 10) })}
                className="w-full accent-[#0071E3] cursor-pointer"
              />
            </div>
          </div>

        </div>
      )}

      {/* ── Sub-panel 3: Colors & Backdrop (Solid, Gradient, Accent, Effects) ── */}
      {activeCategory === 'colors' && (
        <div className="p-3.5 space-y-5">
          
          {/* Accent Color */}
          <div>
            <label className="block text-xs font-semibold text-gray-900 dark:text-white mb-1.5">
              Brand Accent Color
            </label>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-gray-500 dark:text-gray-400">Buttons, verified badges & highlights</span>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={theme.accent_color || '#4F46E5'}
                  onChange={(e) => setTheme({ ...theme, accent_color: e.target.value })}
                  className="w-7 h-7 rounded-lg cursor-pointer border border-black/[0.06] dark:border-white/[0.08] bg-transparent"
                />
                <span className="text-xs font-mono text-gray-400 dark:text-gray-500 uppercase">{theme.accent_color || '#4F46E5'}</span>
              </div>
            </div>

            <div className="flex items-center gap-1.5 flex-wrap">
              {COLOR_SWATCHES.slice(0, 10).map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setTheme({ ...theme, accent_color: c })}
                  className="w-6 h-6 rounded-full border border-black/15 dark:border-white/20 transition-transform hover:scale-110 shadow-2xs"
                  style={{ background: c }}
                  title={c}
                />
              ))}
            </div>
          </div>

          {/* Background Gradient Presets */}
          <div className="pt-2 border-t border-black/[0.06] dark:border-white/[0.08]">
            <label className="block text-xs font-semibold text-gray-900 dark:text-white mb-2">
              Backdrop Gradient Presets
            </label>
            <div className="grid grid-cols-2 gap-2">
              {GRADIENT_PRESETS.map((gp, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setTheme({
                    ...theme,
                    background_gradient: gp.value,
                    background_color: gp.bg,
                    text_color: gp.text,
                  })}
                  className="p-2 rounded-2xl border border-black/[0.06] dark:border-white/[0.08] hover:border-[#0071E3] flex items-center gap-2 text-left transition-all group bg-white/60 dark:bg-white/[0.04]"
                >
                  <div className="w-5 h-5 rounded-md shadow-2xs shrink-0" style={{ background: gp.value }} />
                  <span className="text-[11px] font-semibold text-gray-700 dark:text-gray-300 truncate">{gp.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Custom Background Color & Text Color */}
          <div className="space-y-3 pt-2 border-t border-black/[0.06] dark:border-white/[0.08]">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">Custom Canvas Background</span>
                <p className="text-[10px] text-gray-500 dark:text-gray-400">Solid backdrop color</p>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={rgbaToHex(theme.background_color, '#FDFBF7')}
                  onChange={(e) => setTheme((prev) => ({
                    ...prev,
                    background_color: e.target.value,
                    background_gradient: `linear-gradient(180deg, ${e.target.value} 0%, ${e.target.value} 100%)`,
                  }))}
                  className="w-8 h-8 rounded-lg cursor-pointer border border-black/[0.06] dark:border-white/[0.08] bg-transparent"
                />
                <input
                  type="text"
                  value={theme.background_color || '#FDFBF7'}
                  onChange={(e) => setTheme((prev) => ({
                    ...prev,
                    background_color: e.target.value,
                    background_gradient: `linear-gradient(180deg, ${e.target.value} 0%, ${e.target.value} 100%)`,
                  }))}
                  className="w-24 px-2 py-1 text-xs font-mono bg-black/[0.03] dark:bg-white/[0.06] border border-black/[0.06] dark:border-white/[0.08] rounded-xl text-gray-800 dark:text-gray-200 outline-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">Page Text Color</span>
                <p className="text-[10px] text-gray-500 dark:text-gray-400">Header title, handle & bio</p>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={rgbaToHex(theme.text_color, '#18181B')}
                  onChange={(e) => setTheme((prev) => ({ ...prev, text_color: e.target.value }))}
                  className="w-8 h-8 rounded-lg cursor-pointer border border-black/[0.06] dark:border-white/[0.08] bg-transparent"
                />
                <input
                  type="text"
                  value={theme.text_color || '#18181B'}
                  onChange={(e) => setTheme((prev) => ({ ...prev, text_color: e.target.value }))}
                  className="w-24 px-2 py-1 text-xs font-mono bg-black/[0.03] dark:bg-white/[0.06] border border-black/[0.06] dark:border-white/[0.08] rounded-xl text-gray-800 dark:text-gray-200 outline-none"
                />
              </div>
            </div>
          </div>

          {/* Background Procedural Overlays */}
          <div className="pt-2 border-t border-black/[0.06] dark:border-white/[0.08]">
            <label className="block text-xs font-semibold text-gray-900 dark:text-white mb-2">
              Procedural Background Effects
            </label>
            <div className="space-y-1.5">
              {BACKGROUND_EFFECTS.map((eff) => {
                const isSelected = (theme.background_effect || 'none') === eff.id;
                return (
                  <button
                    key={eff.id}
                    onClick={() => setTheme({ ...theme, background_effect: eff.id })}
                    className={`w-full p-2.5 rounded-2xl border text-left transition-all flex items-center justify-between ${
                      isSelected
                        ? 'border-[#0071E3] bg-blue-50/60 dark:bg-blue-950/40 text-[#0071E3] dark:text-blue-400 font-semibold shadow-2xs'
                        : 'border-black/[0.06] dark:border-white/[0.08] hover:border-black/[0.12] dark:hover:border-white/[0.15] text-gray-700 dark:text-gray-300 bg-white/60 dark:bg-white/[0.04]'
                    }`}
                  >
                    <div>
                      <p className="text-xs font-semibold">{eff.label}</p>
                      <p className="text-[10px] text-gray-500 dark:text-gray-400 font-normal mt-0.5">{eff.description}</p>
                    </div>
                    {isSelected && <FaCheck className="text-xs shrink-0 ml-2 text-[#0071E3]" />}
                  </button>
                );
              })}
            </div>
          </div>

        </div>
      )}

      {/* ── Sub-panel 4: General & Profile (Header Layout, Photo Sliders) ── */}
      {activeCategory === 'general' && (
        <div className="p-3.5 space-y-5">
          
          {/* Header Layout Segmented Visual Picker */}
          <div>
            <label className="block text-xs font-semibold text-gray-900 dark:text-white mb-2">
              Header Layout
            </label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { id: 'classic', label: 'Classic Centered', desc: 'Centered avatar, verified badge & bio' },
                { id: 'banner', label: 'Banner Cover', desc: 'Full-bleed banner with overlapping avatar' },
                { id: 'editorial_split', label: 'Editorial Split', desc: 'Asymmetric portrait on left, bio on right' },
                { id: 'minimal', label: 'Minimal Monograph', desc: 'Compact headline and micro avatar' },
              ].map((hl) => {
                const isSelected = (theme.header_layout || 'classic') === hl.id;
                return (
                  <button
                    key={hl.id}
                    onClick={() => setTheme({ ...theme, header_layout: hl.id })}
                    className={`p-2.5 rounded-2xl border text-left transition-all ${
                      isSelected
                        ? 'border-[#0071E3] bg-blue-50/60 dark:bg-blue-950/40 text-[#0071E3] dark:text-blue-400 font-semibold shadow-2xs'
                        : 'border-black/[0.06] dark:border-white/[0.08] hover:border-black/[0.12] dark:hover:border-white/[0.15] text-gray-600 dark:text-gray-400 bg-white/60 dark:bg-white/[0.04]'
                    }`}
                  >
                    <p className="text-xs font-semibold text-gray-900 dark:text-white">{hl.label}</p>
                    <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">{hl.desc}</p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Profile Picture Sliders */}
          <div className="space-y-3 pt-2 border-t border-black/[0.06] dark:border-white/[0.08]">
            <label className="block text-xs font-semibold text-gray-900 dark:text-white">
              Profile Avatar Sizing & Elevation
            </label>
            <div>
              <div className="flex items-center justify-between text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                <span>Profile Picture Size</span>
                <span className="text-gray-400 dark:text-gray-500 font-mono">{theme.profile_picture_size ?? 50}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={theme.profile_picture_size ?? 50}
                onChange={(e) => setTheme({ ...theme, profile_picture_size: parseInt(e.target.value, 10) })}
                className="w-full accent-[#0071E3] cursor-pointer"
              />
            </div>

            <div>
              <div className="flex items-center justify-between text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                <span>Profile Picture Shadow</span>
                <span className="text-gray-400 dark:text-gray-500 font-mono">{theme.profile_picture_shadow ?? 0}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={theme.profile_picture_shadow ?? 0}
                onChange={(e) => setTheme({ ...theme, profile_picture_shadow: parseInt(e.target.value, 10) })}
                className="w-full accent-[#0071E3] cursor-pointer"
              />
            </div>

            <div>
              <div className="flex items-center justify-between text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                <span>Profile Picture Border Ring</span>
                <span className="text-gray-400 dark:text-gray-500 font-mono">{theme.profile_picture_border ?? 0}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={theme.profile_picture_border ?? 0}
                onChange={(e) => setTheme({ ...theme, profile_picture_border: parseInt(e.target.value, 10) })}
                className="w-full accent-[#0071E3] cursor-pointer"
              />
            </div>
          </div>

          {/* Collapse Long Bio Switch */}
          <div className="flex items-center justify-between p-3 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08]">
            <div>
              <span className="text-xs font-semibold text-gray-900 dark:text-white">Collapse Long Bio</span>
              <p className="text-[11px] text-gray-400 dark:text-gray-500">Truncates long bio text with a 'read more' toggle</p>
            </div>
            <input
              type="checkbox"
              checked={theme.collapse_long_bio || false}
              onChange={(e) => setTheme({ ...theme, collapse_long_bio: e.target.checked })}
              className="w-4 h-4 text-[#0071E3] rounded-sm focus:ring-[#0071E3] cursor-pointer"
            />
          </div>

        </div>
      )}

      {/* ── Sub-panel 5: Fonts ── */}
      {activeCategory === 'fonts' && (
        <div className="p-3.5 space-y-3">
          <label className="block text-xs font-semibold text-gray-900 dark:text-white mb-1">
            Font Family & Pairings
          </label>
          <div className="space-y-2">
            {FONTS_LIST.map((f) => {
              const isSelected = theme.font_family === f.id;
              return (
                <button
                  key={f.id}
                  onClick={() => setTheme({ ...theme, font_family: f.id })}
                  className={`w-full p-3 rounded-2xl border text-left transition-all ${
                    isSelected
                      ? 'border-[#0071E3] bg-blue-50/60 dark:bg-blue-950/40 text-[#0071E3] dark:text-blue-400 font-semibold shadow-2xs'
                      : 'border-black/[0.06] dark:border-white/[0.08] hover:border-black/[0.12] dark:hover:border-white/[0.15] text-gray-700 dark:text-gray-300 bg-white/60 dark:bg-white/[0.04]'
                  }`}
                  style={{ fontFamily: f.id }}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold">{f.label}</span>
                    {isSelected && <FaCheck className="text-xs text-[#0071E3] dark:text-blue-400" />}
                  </div>
                  <p className="text-sm mt-1 opacity-75">{f.sample}</p>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Sub-panel 6: Social Dock ── */}
      {activeCategory === 'socials' && (
        <div className="p-3.5 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-900 dark:text-white mb-2">
              Social Dock Position
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setTheme({ ...theme, social_position: 'top' })}
                className={`py-2 text-xs font-semibold rounded-xl border text-center transition-colors ${
                  (theme.social_position || 'top') === 'top'
                    ? 'border-[#0071E3] bg-blue-50/60 dark:bg-blue-950/40 text-[#0071E3] dark:text-blue-400 shadow-2xs'
                    : 'border-black/[0.06] dark:border-white/[0.08] text-gray-600 dark:text-gray-400 bg-white/60 dark:bg-white/[0.04]'
                }`}
              >
                Top Header
              </button>
              <button
                onClick={() => setTheme({ ...theme, social_position: 'bottom' })}
                className={`py-2 text-xs font-semibold rounded-xl border text-center transition-colors ${
                  theme.social_position === 'bottom'
                    ? 'border-[#0071E3] bg-blue-50/60 dark:bg-blue-950/40 text-[#0071E3] dark:text-blue-400 shadow-2xs'
                    : 'border-black/[0.06] dark:border-white/[0.08] text-gray-600 dark:text-gray-400 bg-white/60 dark:bg-white/[0.04]'
                }`}
              >
                Bottom Footer
              </button>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
              <span>Social Icon Size</span>
              <span className="text-gray-400 dark:text-gray-500 font-mono">{theme.social_icon_size ?? 0}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={theme.social_icon_size ?? 0}
              onChange={(e) => setTheme({ ...theme, social_icon_size: parseInt(e.target.value, 10) })}
              className="w-full accent-[#0071E3] cursor-pointer"
            />
          </div>
        </div>
      )}

      {/* ── Sub-panel 7: Navigation Style ── */}
      {activeCategory === 'navigation' && (
        <div className="p-3.5 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-gray-900 dark:text-white mb-2">
              Multi-Page Navigation Style
            </label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { id: 'pills', label: 'Pill Tabs', desc: 'Floating glass capsule tabs' },
                { id: 'top_bar', label: 'Top Bar', desc: 'Sticky header navigation' },
                { id: 'bottom_bar', label: 'Bottom Dock', desc: 'Mobile floating dock' },
                { id: 'none', label: 'Hidden', desc: 'Single-page only' },
              ].map((nav) => {
                const isSelected = (theme.navigation_style || 'pills') === nav.id;
                return (
                  <button
                    key={nav.id}
                    onClick={() => setTheme({ ...theme, navigation_style: nav.id })}
                    className={`p-2.5 rounded-2xl border text-left transition-all ${
                      isSelected
                        ? 'border-[#0071E3] bg-blue-50/60 dark:bg-blue-950/40 text-[#0071E3] dark:text-blue-400 font-semibold shadow-2xs'
                        : 'border-black/[0.06] dark:border-white/[0.08] hover:border-black/[0.12] dark:hover:border-white/[0.15] text-gray-600 dark:text-gray-400 bg-white/60 dark:bg-white/[0.04]'
                    }`}
                  >
                    <p className="text-xs font-semibold text-gray-900 dark:text-white">{nav.label}</p>
                    <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">{nav.desc}</p>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* ── Sub-panel 8: Announcement Banner ── */}
      {activeCategory === 'announcement' && (
        <div className="p-3.5 space-y-4">
          <div className="flex items-center justify-between p-3 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08]">
            <div>
              <span className="text-xs font-semibold text-gray-900 dark:text-white">Enable Top Announcement</span>
              <p className="text-[11px] text-gray-400 dark:text-gray-500">Show marquee banner at top of your bio</p>
            </div>
            <input
              type="checkbox"
              checked={theme.announcement_active || false}
              onChange={(e) => setTheme({ ...theme, announcement_active: e.target.checked })}
              className="w-4 h-4 text-[#0071E3] rounded-sm focus:ring-[#0071E3] cursor-pointer"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-900 dark:text-white mb-1">
              Banner Text
            </label>
            <input
              type="text"
              value={theme.announcement_banner || ''}
              onChange={(e) => setTheme({ ...theme, announcement_banner: e.target.value })}
              placeholder="🎉 Spring Sale: Use code UNRAVLER for 20% off!"
              className="w-full px-3 py-2 text-xs bg-black/[0.03] dark:bg-white/[0.06] border border-black/[0.06] dark:border-white/[0.08] rounded-xl outline-none focus:ring-2 focus:ring-[#0071E3] text-gray-900 dark:text-white font-medium"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-900 dark:text-white mb-1">
              Banner Target URL (Optional)
            </label>
            <input
              type="text"
              value={theme.announcement_url || ''}
              onChange={(e) => setTheme({ ...theme, announcement_url: e.target.value })}
              placeholder="https://myshop.com/discount"
              className="w-full px-3 py-2 text-xs bg-black/[0.03] dark:bg-white/[0.06] border border-black/[0.06] dark:border-white/[0.08] rounded-xl outline-none focus:ring-2 focus:ring-[#0071E3] text-gray-900 dark:text-white font-medium"
            />
          </div>
        </div>
      )}

    </div>
  );
}
