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
} from 'react-icons/fa';
import {
  THEME_PRESETS,
  TACTILE_CARD_STYLES,
  BACKGROUND_EFFECTS,
  HEADER_LAYOUTS,
} from '@/lib/bioThemeUtils';

const FONTS_LIST = [
  { id: 'Plus Jakarta Sans', label: 'Plus Jakarta Sans (Modern Clean)' },
  { id: 'Geist', label: 'Geist (Vercel Precision)' },
  { id: 'Outfit', label: 'Outfit (Geometric Luxury)' },
  { id: 'Playfair Display', label: 'Playfair Display (Editorial Serif)' },
  { id: 'Space Grotesk', label: 'Space Grotesk (Tech Monospace)' },
  { id: 'Inter', label: 'Inter (Standard Sans)' },
];

export default function BioInspectorDrawer({
  theme,
  setTheme,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
  onResetTheme,
}) {
  const [activeCategory, setActiveCategory] = useState('root'); // 'root' | 'templates' | 'general' | 'blocks' | 'fonts' | 'colors' | 'socials' | 'media'
  const [searchQuery, setSearchQuery] = useState('');
  const [showColorPicker, setShowColorPicker] = useState(null); // 'bg' | 'text' | 'accent' | 'card_bg' | 'card_border'

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
    });
  };

  const categories = [
    {
      id: 'templates',
      title: 'Templates',
      badge: '18 Curated',
      isRainbow: true,
      icon: FaPalette,
      desc: 'Instant 1-click designer themes & color stories',
    },
    {
      id: 'general',
      title: 'General Styles',
      badge: '8',
      icon: FaSlidersH,
      desc: 'Header architecture, photo size, background, bio collapse',
    },
    {
      id: 'blocks',
      title: 'Block Styles',
      badge: '8',
      icon: FaLayerGroup,
      desc: 'Tactile 3D physics, corner radius %, shadows %, spacing %',
    },
    {
      id: 'fonts',
      title: 'Fonts',
      badge: '6',
      icon: FaFont,
      desc: 'Typography pairings, font weights & headings',
    },
    {
      id: 'colors',
      title: 'Colors',
      badge: '4',
      icon: FaMagic,
      desc: 'Solid, gradient, liquid mesh, and procedural film grain',
    },
    {
      id: 'socials',
      title: 'Social & Sharing',
      badge: '6',
      icon: FaShareAlt,
      desc: 'Social dock position, icon sizes, and share sheet',
    },
    {
      id: 'navigation',
      title: 'Pages & Navigation',
      badge: '4',
      icon: FaSlidersH,
      desc: 'Pill tabs dock, sticky top bar, or mobile bottom bar',
    },
  ];

  const filteredCategories = categories.filter((c) =>
    c.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    c.desc.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full bg-white dark:bg-zinc-900 border-l border-zinc-200/80 dark:border-zinc-800 text-zinc-800 dark:text-zinc-200 select-none overflow-y-auto custom-scrollbar">
      
      {/* ── Top Inspector Bar: Search & Undo / Redo ── */}
      <div className="p-3 border-b border-zinc-100 dark:border-zinc-800 flex items-center justify-between gap-2">
        {activeCategory === 'root' ? (
          <div className="relative flex-1">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search styles…"
              className="w-full pl-8 pr-2.5 py-1.5 text-xs bg-zinc-50 dark:bg-zinc-800/70 border border-zinc-200/70 dark:border-zinc-700/60 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white placeholder-zinc-400"
            />
            <FaSearch className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400 text-[10px]" />
          </div>
        ) : (
          <button
            onClick={() => setActiveCategory('root')}
            className="flex items-center gap-1.5 text-xs font-bold text-zinc-700 dark:text-zinc-300 hover:text-indigo-600 dark:hover:text-indigo-400 px-2 py-1 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
          >
            <FaChevronLeft className="text-[10px]" />
            <span className="capitalize">{activeCategory} Styles</span>
          </button>
        )}

        <div className="flex items-center gap-1">
          <button
            onClick={onUndo}
            disabled={!canUndo}
            className="p-1.5 rounded-lg border border-zinc-200/70 dark:border-zinc-700/60 bg-zinc-50 dark:bg-zinc-800/70 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-300 disabled:opacity-30 transition-colors"
            title="Undo"
          >
            <FaUndo className="text-[10px]" />
          </button>
          <button
            onClick={onRedo}
            disabled={!canRedo}
            className="p-1.5 rounded-lg border border-zinc-200/70 dark:border-zinc-700/60 bg-zinc-50 dark:bg-zinc-800/70 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-300 disabled:opacity-30 transition-colors"
            title="Redo"
          >
            <FaRedo className="text-[10px]" />
          </button>
        </div>
      </div>

      {/* ── Sub-panel: Main Categories List ── */}
      {activeCategory === 'root' && (
        <div className="p-3.5 space-y-2">
          {filteredCategories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setActiveCategory(cat.id)}
              className="w-full flex items-center justify-between p-3 rounded-2xl border border-zinc-200/80 dark:border-zinc-800/80 hover:border-zinc-300 dark:hover:border-zinc-700 bg-zinc-50/40 dark:bg-zinc-800/30 hover:bg-zinc-50 dark:hover:bg-zinc-800/60 transition-all text-left group shadow-2xs"
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <cat.icon className="text-zinc-500 group-hover:text-indigo-500 text-sm flex-shrink-0 transition-colors" />
                <span className="text-xs font-bold text-zinc-900 dark:text-white truncate">
                  {cat.title}
                </span>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {cat.badge && (
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                      cat.isRainbow
                        ? 'bg-gradient-to-r from-pink-500 via-purple-500 to-indigo-500 text-white shadow-xs'
                        : 'bg-zinc-200/70 dark:bg-zinc-700/60 text-zinc-600 dark:text-zinc-300'
                    }`}
                  >
                    {cat.badge}
                  </span>
                )}
                <FaChevronRight className="text-zinc-400 text-[10px] group-hover:translate-x-0.5 transition-transform" />
              </div>
            </button>
          ))}
        </div>
      )}

      {/* ── Sub-panel: 1. Templates Drawer ── */}
      {activeCategory === 'templates' && (
        <div className="p-3.5 space-y-3">
          <div className="grid grid-cols-2 gap-2.5">
            {THEME_PRESETS.map((p) => {
              const isSelected = theme.preset === p.id || theme.id === p.id;
              return (
                <div
                  key={p.id}
                  onClick={() => handleSelectPreset(p)}
                  className={`relative p-3 rounded-2xl border cursor-pointer transition-all ${
                    isSelected
                      ? 'border-indigo-600 ring-2 ring-indigo-500/20 shadow-md scale-[1.02]'
                      : 'border-zinc-200/80 dark:border-zinc-800 hover:border-zinc-300 hover:shadow-xs'
                  }`}
                  style={{ background: p.background_color }}
                >
                  <div
                    className="h-12 rounded-xl mb-2 flex items-center justify-center p-2 border"
                    style={{
                      background: p.card_bg,
                      borderColor: p.card_border,
                      boxShadow: p.card_style === 'hard_shadow' ? '2px 2px 0px #000' : '0 4px 10px rgba(0,0,0,0.08)',
                    }}
                  >
                    <span className="text-[10px] font-bold truncate" style={{ color: p.card_text_color }}>
                      {p.name}
                    </span>
                  </div>
                  <p className="text-[11px] font-bold truncate" style={{ color: p.text_color }}>
                    {p.name}
                  </p>
                  {isSelected && (
                    <div className="absolute top-2 right-2 w-4 h-4 rounded-full bg-indigo-600 text-white flex items-center justify-center text-[8px]">
                      <FaCheck />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Sub-panel: 2. General Styles (Header, Avatar, Sliders) ── */}
      {activeCategory === 'general' && (
        <div className="p-3.5 space-y-5">
          
          {/* Header Layout Segmented Visual Picker */}
          <div>
            <label className="block text-xs font-bold text-zinc-900 dark:text-white mb-2">
              Header Layout
            </label>
            <div className="grid grid-cols-4 gap-2">
              {[
                { id: 'classic', label: 'Classic', desc: 'Centered' },
                { id: 'banner', label: 'Banner', desc: 'Cover Top' },
                { id: 'editorial_split', label: 'Split', desc: 'Portrait' },
                { id: 'minimal', label: 'Minimal', desc: 'Monograph' },
              ].map((hl) => {
                const isSelected = (theme.header_layout || 'classic') === hl.id;
                return (
                  <button
                    key={hl.id}
                    onClick={() => setTheme({ ...theme, header_layout: hl.id })}
                    className={`flex flex-col items-center justify-center p-2 rounded-xl border text-center transition-all ${
                      isSelected
                        ? 'border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 font-bold shadow-2xs'
                        : 'border-zinc-200 dark:border-zinc-800 hover:border-zinc-300 text-zinc-600 dark:text-zinc-400'
                    }`}
                  >
                    <div className="w-6 h-6 rounded-md bg-zinc-200/80 dark:bg-zinc-700/80 mb-1 flex items-center justify-center text-[10px]">
                      {hl.id === 'classic' && '👤'}
                      {hl.id === 'banner' && '🖼️'}
                      {hl.id === 'editorial_split' && '◧'}
                      {hl.id === 'minimal' && '≡'}
                    </div>
                    <span className="text-[10px] font-bold">{hl.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Background & Text Colors */}
          <div className="space-y-2.5 pt-2 border-t border-zinc-100 dark:border-zinc-800">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">Background</span>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={theme.background_color || '#FDFBF7'}
                  onChange={(e) => setTheme({ ...theme, background_color: e.target.value })}
                  className="w-7 h-7 rounded-lg cursor-pointer border border-zinc-200 dark:border-zinc-700"
                />
                <span className="text-xs font-mono text-zinc-500 uppercase">{theme.background_color || '#FDFBF7'}</span>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">Text Color</span>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={theme.text_color || '#18181B'}
                  onChange={(e) => setTheme({ ...theme, text_color: e.target.value })}
                  className="w-7 h-7 rounded-lg cursor-pointer border border-zinc-200 dark:border-zinc-700"
                />
                <span className="text-xs font-mono text-zinc-500 uppercase">{theme.text_color || '#18181B'}</span>
              </div>
            </div>
          </div>

          {/* Profile Picture Sliders */}
          <div className="space-y-3 pt-2 border-t border-zinc-100 dark:border-zinc-800">
            <div>
              <div className="flex items-center justify-between text-xs font-semibold text-zinc-700 dark:text-zinc-300 mb-1">
                <span>Profile Picture Size</span>
                <span className="text-zinc-400 font-mono">{theme.profile_picture_size ?? 50}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={theme.profile_picture_size ?? 50}
                onChange={(e) => setTheme({ ...theme, profile_picture_size: parseInt(e.target.value, 10) })}
                className="w-full accent-indigo-600"
              />
            </div>

            <div>
              <div className="flex items-center justify-between text-xs font-semibold text-zinc-700 dark:text-zinc-300 mb-1">
                <span>Profile Picture Shadow</span>
                <span className="text-zinc-400 font-mono">{theme.profile_picture_shadow ?? 0}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={theme.profile_picture_shadow ?? 0}
                onChange={(e) => setTheme({ ...theme, profile_picture_shadow: parseInt(e.target.value, 10) })}
                className="w-full accent-indigo-600"
              />
            </div>

            <div>
              <div className="flex items-center justify-between text-xs font-semibold text-zinc-700 dark:text-zinc-300 mb-1">
                <span>Profile Picture Border</span>
                <span className="text-zinc-400 font-mono">{theme.profile_picture_border ?? 0}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={theme.profile_picture_border ?? 0}
                onChange={(e) => setTheme({ ...theme, profile_picture_border: parseInt(e.target.value, 10) })}
                className="w-full accent-indigo-600"
              />
            </div>
          </div>

          {/* Collapse Bio Switch */}
          <div className="flex items-center justify-between pt-2 border-t border-zinc-100 dark:border-zinc-800">
            <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">Collapse Long Bio</span>
            <input
              type="checkbox"
              checked={theme.collapse_long_bio || false}
              onChange={(e) => setTheme({ ...theme, collapse_long_bio: e.target.checked })}
              className="w-4 h-4 text-indigo-600 rounded-sm focus:ring-indigo-500"
            />
          </div>

          {/* Social Icon Size Slider */}
          <div>
            <div className="flex items-center justify-between text-xs font-semibold text-zinc-700 dark:text-zinc-300 mb-1">
              <span>Social Icon Size</span>
              <span className="text-zinc-400 font-mono">{theme.social_icon_size ?? 0}%</span>
            </div>
            <input
              type="range"
              min="0"
              max="100"
              value={theme.social_icon_size ?? 0}
              onChange={(e) => setTheme({ ...theme, social_icon_size: parseInt(e.target.value, 10) })}
              className="w-full accent-indigo-600"
            />
          </div>

        </div>
      )}

      {/* ── Sub-panel: 3. Block Styles (Corner %, Shadow %, Spacing %) ── */}
      {activeCategory === 'blocks' && (
        <div className="p-3.5 space-y-5">
          
          {/* Tactile Toggle */}
          <div className="flex items-center justify-between p-3 rounded-2xl bg-zinc-50 dark:bg-zinc-800/40 border border-zinc-200/80 dark:border-zinc-800">
            <div>
              <p className="text-xs font-bold text-zinc-900 dark:text-white">Tactile Physical Blocks</p>
              <p className="text-[11px] text-zinc-500">Enable 3D convex insets and double-bezel glass</p>
            </div>
            <input
              type="checkbox"
              checked={theme.tactile_blocks ?? true}
              onChange={(e) => setTheme({ ...theme, tactile_blocks: e.target.checked })}
              className="w-4 h-4 text-indigo-600 rounded-sm focus:ring-indigo-500"
            />
          </div>

          {/* Card Colors */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">Card Color</span>
              <input
                type="color"
                value={theme.card_bg?.startsWith('#') ? theme.card_bg : '#FFFFFF'}
                onChange={(e) => setTheme({ ...theme, card_bg: e.target.value })}
                className="w-7 h-7 rounded-lg cursor-pointer border border-zinc-200 dark:border-zinc-700"
              />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">Card Text Color</span>
              <input
                type="color"
                value={theme.card_text_color || '#18181B'}
                onChange={(e) => setTheme({ ...theme, card_text_color: e.target.value })}
                className="w-7 h-7 rounded-lg cursor-pointer border border-zinc-200 dark:border-zinc-700"
              />
            </div>
          </div>

          {/* Sliders: Corner, Border, Shadow, Spacing */}
          <div className="space-y-4 pt-2 border-t border-zinc-100 dark:border-zinc-800">
            <div>
              <div className="flex items-center justify-between text-xs font-semibold text-zinc-700 dark:text-zinc-300 mb-1">
                <span>Corner Radius (Roundness)</span>
                <span className="text-zinc-400 font-mono">{theme.card_corner_radius ?? 20}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={theme.card_corner_radius ?? 20}
                onChange={(e) => setTheme({ ...theme, card_corner_radius: parseInt(e.target.value, 10) })}
                className="w-full accent-indigo-600"
              />
            </div>

            <div>
              <div className="flex items-center justify-between text-xs font-semibold text-zinc-700 dark:text-zinc-300 mb-1">
                <span>Border Width</span>
                <span className="text-zinc-400 font-mono">{theme.card_border_width ?? 0}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={theme.card_border_width ?? 0}
                onChange={(e) => setTheme({ ...theme, card_border_width: parseInt(e.target.value, 10) })}
                className="w-full accent-indigo-600"
              />
            </div>

            <div>
              <div className="flex items-center justify-between text-xs font-semibold text-zinc-700 dark:text-zinc-300 mb-1">
                <span>Shadow Depth</span>
                <span className="text-zinc-400 font-mono">{theme.card_shadow_depth ?? 100}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={theme.card_shadow_depth ?? 100}
                onChange={(e) => setTheme({ ...theme, card_shadow_depth: parseInt(e.target.value, 10) })}
                className="w-full accent-indigo-600"
              />
            </div>

            {/* Soft Shadow vs Solid Hard Shadow Toggle */}
            <div className="grid grid-cols-2 gap-2 pt-1">
              <button
                type="button"
                onClick={() => setTheme({ ...theme, card_shadow_type: 'soft' })}
                className={`py-1.5 text-xs font-bold rounded-xl border transition-colors ${
                  (theme.card_shadow_type || 'soft') === 'soft'
                    ? 'border-indigo-600 bg-indigo-50/60 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400'
                    : 'border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400'
                }`}
              >
                Soft Shadow
              </button>
              <button
                type="button"
                onClick={() => setTheme({ ...theme, card_shadow_type: 'solid' })}
                className={`py-1.5 text-xs font-bold rounded-xl border transition-colors ${
                  theme.card_shadow_type === 'solid'
                    ? 'border-indigo-600 bg-indigo-50/60 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400'
                    : 'border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400'
                }`}
              >
                Solid Shadow
              </button>
            </div>

            <div>
              <div className="flex items-center justify-between text-xs font-semibold text-zinc-700 dark:text-zinc-300 mb-1">
                <span>Card Spacing Gap</span>
                <span className="text-zinc-400 font-mono">{theme.card_spacing ?? 33}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={theme.card_spacing ?? 33}
                onChange={(e) => setTheme({ ...theme, card_spacing: parseInt(e.target.value, 10) })}
                className="w-full accent-indigo-600"
              />
            </div>
          </div>

        </div>
      )}

      {/* ── Sub-panel: 4. Fonts ── */}
      {activeCategory === 'fonts' && (
        <div className="p-3.5 space-y-3">
          <label className="block text-xs font-bold text-zinc-900 dark:text-white mb-1">
            Font Family
          </label>
          <div className="space-y-1.5">
            {FONTS_LIST.map((f) => {
              const isSelected = theme.font_family === f.id;
              return (
                <button
                  key={f.id}
                  onClick={() => setTheme({ ...theme, font_family: f.id })}
                  className={`w-full flex items-center justify-between p-2.5 rounded-xl border text-left transition-all ${
                    isSelected
                      ? 'border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 font-bold'
                      : 'border-zinc-200/80 dark:border-zinc-800 hover:border-zinc-300 text-zinc-700 dark:text-zinc-300'
                  }`}
                  style={{ fontFamily: f.id }}
                >
                  <span className="text-xs">{f.label}</span>
                  {isSelected && <FaCheck className="text-xs" />}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Sub-panel: 5. Colors & Procedural Effects ── */}
      {activeCategory === 'colors' && (
        <div className="p-3.5 space-y-4">
          <div>
            <label className="block text-xs font-bold text-zinc-900 dark:text-white mb-2">
              Background Procedural Effect
            </label>
            <div className="space-y-2">
              {BACKGROUND_EFFECTS.map((eff) => {
                const isSelected = (theme.background_effect || 'none') === eff.id;
                return (
                  <button
                    key={eff.id}
                    onClick={() => setTheme({ ...theme, background_effect: eff.id })}
                    className={`w-full p-2.5 rounded-xl border text-left transition-all ${
                      isSelected
                        ? 'border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 font-bold'
                        : 'border-zinc-200/80 dark:border-zinc-800 hover:border-zinc-300 text-zinc-700 dark:text-zinc-300'
                    }`}
                  >
                    <p className="text-xs font-bold">{eff.label}</p>
                    <p className="text-[10px] text-zinc-400 font-normal mt-0.5">{eff.description}</p>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* ── Sub-panel: 6. Social & Sharing ── */}
      {activeCategory === 'socials' && (
        <div className="p-3.5 space-y-4">
          <div>
            <label className="block text-xs font-bold text-zinc-900 dark:text-white mb-1">
              Social Dock Position
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setTheme({ ...theme, social_position: 'top' })}
                className={`py-2 text-xs font-bold rounded-xl border text-center transition-colors ${
                  (theme.social_position || 'top') === 'top'
                    ? 'border-indigo-600 bg-indigo-50/60 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400'
                    : 'border-zinc-200 dark:border-zinc-800 text-zinc-600 dark:text-zinc-400'
                }`}
              >
                Top Header
              </button>
              <button
                onClick={() => setTheme({ ...theme, social_position: 'bottom' })}
                className={`py-2 text-xs font-bold rounded-xl border text-center transition-colors ${
                  theme.social_position === 'bottom'
                    ? 'border-indigo-600 bg-indigo-50/60 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400'
                    : 'border-zinc-200 dark:border-zinc-800 text-zinc-600 dark:text-zinc-400'
                }`}
              >
                Bottom Footer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Sub-panel: 7. Pages & Navigation Dock ── */}
      {activeCategory === 'navigation' && (
        <div className="p-3.5 space-y-4">
          <div>
            <label className="block text-xs font-bold text-zinc-900 dark:text-white mb-1">
              Site Navigation Style
            </label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { id: 'pills', label: 'Pill Tabs', desc: 'Sub-tabs under header' },
                { id: 'top_bar', label: 'Top Bar', desc: 'Sticky header navigation' },
                { id: 'bottom_bar', label: 'Bottom Dock', desc: 'Mobile app floating dock' },
                { id: 'none', label: 'Hidden', desc: 'Single-page only' },
              ].map((nav) => {
                const isSelected = (theme.navigation_style || 'pills') === nav.id;
                return (
                  <button
                    key={nav.id}
                    onClick={() => setTheme({ ...theme, navigation_style: nav.id })}
                    className={`p-2 rounded-xl border text-center transition-all ${
                      isSelected
                        ? 'border-indigo-600 bg-indigo-50/60 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 font-bold shadow-2xs'
                        : 'border-zinc-200 dark:border-zinc-800 hover:border-zinc-300 text-zinc-600 dark:text-zinc-400'
                    }`}
                  >
                    <p className="text-xs font-bold">{nav.label}</p>
                    <p className="text-[10px] text-zinc-400 mt-0.5">{nav.desc}</p>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
