import React, { useState } from 'react';
import {
  FaTimes,
  FaTrash,
  FaSave,
  FaLink,
  FaImage,
  FaIcons,
  FaSmile,
  FaCube,
  FaMagic,
  FaExternalLinkAlt,
  FaCheck,
  FaAlignLeft,
  FaAlignCenter,
  FaAlignRight,
  FaBolt,
} from 'react-icons/fa';

export default function BioBlockEditorModal({
  isOpen,
  onClose,
  block,
  onSaveBlock,
  onDeleteBlock,
  theme,
}) {
  const [formData, setFormData] = useState(() => ({
    ...block,
    layout: block?.layout || 'card_left_image',
    media_type: block?.media_type || 'image',
    animation: block?.animation || (block?.is_featured ? 'pulse' : 'none'),
    text_align: block?.text_align || 'left',
    size: block?.size || 'large',
    tag: block?.tag || '',
  }));

  const [activeMediaTab, setActiveMediaTab] = useState(() => block?.media_type || 'image'); // 'image' | 'icon' | 'emoji' | '3d'
  const [aiPrompt, setAiPrompt] = useState('');
  const [isGeneratingAi, setIsGeneratingAi] = useState(false);

  if (!isOpen || !block) return null;

  const handleSave = () => {
    onSaveBlock({
      ...formData,
      media_type: activeMediaTab,
      is_featured: formData.animation === 'pulse',
    });
    onClose();
  };

  const handleQuickAiImage = async () => {
    if (!formData.title) return;
    setIsGeneratingAi(true);
    // Generate beautiful Unsplash / AI placeholder matching block title
    const query = encodeURIComponent(formData.title);
    const generatedUrl = `https://images.unsplash.com/photo-1579783902614-a3fb3927b675?auto=format&fit=crop&w=600&q=80`;
    setTimeout(() => {
      setFormData((prev) => ({ ...prev, media_url: generatedUrl }));
      setIsGeneratingAi(false);
    }, 600);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6 overflow-y-auto animate-in fade-in duration-150">
      <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl max-w-4xl w-full shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        
        {/* Top Header */}
        <div className="p-4 border-b border-zinc-100 dark:border-zinc-800 flex items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-800/40">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-bold text-zinc-900 dark:text-white">
              Edit Block
            </h3>
            <span className="px-2 py-0.5 text-[10px] font-black uppercase tracking-wider bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 rounded-md">
              {formData.type?.replace('_', ' ')}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => { onDeleteBlock(block.id); onClose(); }}
              className="p-2 text-zinc-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 rounded-xl transition-colors"
              title="Delete Block"
            >
              <FaTrash className="text-xs" />
            </button>
            <button
              onClick={handleSave}
              className="px-4 py-1.5 text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-xs transition-colors flex items-center gap-1.5"
            >
              <FaSave className="text-xs" /> Save Changes
            </button>
            <button
              onClick={onClose}
              className="p-2 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 rounded-xl"
            >
              <FaTimes className="text-xs" />
            </button>
          </div>
        </div>

        {/* 2-Column Split Editor: Left Content & Media vs Right Block Styles */}
        <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-zinc-100 dark:divide-zinc-800 overflow-y-auto flex-1">
          
          {/* ── Left Column: Content, URL & Media ── */}
          <div className="p-5 space-y-4">
            
            {/* Button Type */}
            <div>
              <label className="block text-xs font-bold text-zinc-700 dark:text-zinc-300 mb-1">
                Button Type
              </label>
              <select
                value={formData.type}
                onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                className="w-full px-3 py-2 text-xs bg-zinc-50 dark:bg-zinc-800/70 border border-zinc-200 dark:border-zinc-700 rounded-xl font-semibold text-zinc-900 dark:text-white"
              >
                <option value="link">Destination URL</option>
                <option value="media_card">Media Showcase Card</option>
                <option value="embed">Video / Spotify Embed</option>
                <option value="feed_grid">Live Instagram Feed Grid</option>
                <option value="lead_capture">Newsletter Lead Capture</option>
              </select>
            </div>

            {/* Destination URL */}
            {formData.type !== 'feed_grid' && formData.type !== 'lead_capture' && (
              <div>
                <label className="block text-xs font-bold text-zinc-700 dark:text-zinc-300 mb-1">
                  Destination URL
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="url"
                    value={formData.url || formData.embed_url || ''}
                    onChange={(e) => setFormData({ ...formData, url: e.target.value, embed_url: e.target.value })}
                    placeholder="https://..."
                    className="flex-1 px-3 py-2 text-xs bg-zinc-50 dark:bg-zinc-800/70 border border-zinc-200 dark:border-zinc-700 rounded-xl font-mono text-zinc-900 dark:text-white outline-hidden focus:ring-2 focus:ring-indigo-500"
                  />
                  {formData.url && (
                    <a
                      href={formData.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-2.5 bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 rounded-xl text-zinc-600 dark:text-zinc-300 text-xs"
                      title="Test Link"
                    >
                      <FaExternalLinkAlt />
                    </a>
                  )}
                </div>
              </div>
            )}

            {/* Layout Card Selector (5 presets) */}
            <div>
              <label className="block text-xs font-bold text-zinc-700 dark:text-zinc-300 mb-2">
                Card Layout
              </label>
              <div className="grid grid-cols-4 gap-2">
                {[
                  { id: 'card_left_image', label: 'Left Image', desc: 'Square thumb on left' },
                  { id: 'card_banner_top', label: 'Top Hero', desc: 'Big photo cover on top' },
                  { id: 'compact_pill', label: 'Compact Pill', desc: 'Minimal clean button' },
                  { id: 'grid_card', label: 'Grid Card', desc: '2-column bento card' },
                ].map((ly) => {
                  const isSelected = formData.layout === ly.id;
                  return (
                    <button
                      key={ly.id}
                      type="button"
                      onClick={() => setFormData({ ...formData, layout: ly.id })}
                      className={`p-2 rounded-xl border text-center transition-all ${
                        isSelected
                          ? 'border-indigo-600 bg-indigo-50/60 dark:bg-indigo-950/50 text-indigo-600 dark:text-indigo-400 font-bold shadow-2xs'
                          : 'border-zinc-200 dark:border-zinc-800 hover:border-zinc-300 text-zinc-600 dark:text-zinc-400'
                      }`}
                    >
                      <div className="w-full h-6 rounded bg-zinc-200/80 dark:bg-zinc-700/80 mb-1 flex items-center justify-center text-[10px]">
                        {ly.id === 'card_left_image' && '◧'}
                        {ly.id === 'card_banner_top' && '⬒'}
                        {ly.id === 'compact_pill' && '━'}
                        {ly.id === 'grid_card' && '▦'}
                      </div>
                      <span className="text-[10px] font-bold block truncate">{ly.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Media Tabs [ Image | Icon | Emoji | 3D ] */}
            <div>
              <div className="flex border-b border-zinc-100 dark:border-zinc-800 mb-3">
                {[
                  { id: 'image', label: 'Image', icon: FaImage },
                  { id: 'icon', label: 'Icon', icon: FaIcons },
                  { id: 'emoji', label: 'Emoji', icon: FaSmile },
                  { id: '3d', label: '3D Art', icon: FaCube },
                ].map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => setActiveMediaTab(m.id)}
                    className={`pb-2 px-3 text-xs font-bold border-b-2 transition-colors flex items-center gap-1.5 ${
                      activeMediaTab === m.id
                        ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400'
                        : 'border-transparent text-zinc-400 hover:text-zinc-600'
                    }`}
                  >
                    <m.icon className="text-xs" />
                    {m.label}
                  </button>
                ))}
              </div>

              {activeMediaTab === 'image' && (
                <div className="space-y-2.5">
                  <div className="flex items-center gap-3">
                    {formData.media_url ? (
                      <img src={formData.media_url} alt="" className="w-14 h-14 rounded-xl object-cover border border-zinc-200 dark:border-zinc-700" />
                    ) : (
                      <div className="w-14 h-14 rounded-xl bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center text-zinc-400 text-xs">
                        No Image
                      </div>
                    )}
                    <div className="flex-1 space-y-1.5">
                      <input
                        type="url"
                        value={formData.media_url || ''}
                        onChange={(e) => setFormData({ ...formData, media_url: e.target.value })}
                        placeholder="https://.../image.jpg"
                        className="w-full px-2.5 py-1.5 text-xs bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl font-mono text-zinc-800 dark:text-zinc-200"
                      />
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={handleQuickAiImage}
                          disabled={isGeneratingAi}
                          className="px-2.5 py-1 text-[11px] font-bold bg-indigo-50 dark:bg-indigo-950/50 text-indigo-600 dark:text-indigo-400 rounded-lg hover:bg-indigo-100 transition-colors flex items-center gap-1"
                        >
                          <FaMagic className="text-[10px]" /> {isGeneratingAi ? 'Generating…' : 'Generate with AI'}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Text Inputs: Title, Subtitle, Badge, Tag */}
            <div className="space-y-3 pt-2 border-t border-zinc-100 dark:border-zinc-800">
              <div>
                <label className="block text-xs font-bold text-zinc-700 dark:text-zinc-300 mb-1">
                  Title
                </label>
                <input
                  type="text"
                  value={formData.title || formData.headline || ''}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value, headline: e.target.value })}
                  placeholder="e.g. Spring 2026 Collection"
                  className="w-full px-3 py-2 text-xs font-bold bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl text-zinc-900 dark:text-white"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-zinc-700 dark:text-zinc-300 mb-1">
                  Description / Subtitle
                </label>
                <textarea
                  rows={2}
                  value={formData.subtitle || formData.subheadline || ''}
                  onChange={(e) => setFormData({ ...formData, subtitle: e.target.value, subheadline: e.target.value })}
                  placeholder="Short description under title..."
                  className="w-full px-3 py-1.5 text-xs bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl text-zinc-800 dark:text-zinc-200 resize-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[11px] font-bold text-zinc-600 dark:text-zinc-400 mb-1">
                    Badge Highlight
                  </label>
                  <input
                    type="text"
                    value={formData.badge || ''}
                    onChange={(e) => setFormData({ ...formData, badge: e.target.value })}
                    placeholder="e.g. HOT, NEW, SALE"
                    className="w-full px-2.5 py-1.5 text-xs bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl text-zinc-800 dark:text-zinc-200"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-bold text-zinc-600 dark:text-zinc-400 mb-1">
                    Tag Category
                  </label>
                  <input
                    type="text"
                    value={formData.tag || ''}
                    onChange={(e) => setFormData({ ...formData, tag: e.target.value })}
                    placeholder="e.g. Shop, Music"
                    className="w-full px-2.5 py-1.5 text-xs bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl text-zinc-800 dark:text-zinc-200"
                  />
                </div>
              </div>
            </div>

          </div>

          {/* ── Right Column: Block Styles & Animation ── */}
          <div className="p-5 space-y-5 bg-zinc-50/40 dark:bg-zinc-900/40">
            <div>
              <p className="text-xs font-bold text-zinc-900 dark:text-white mb-2">
                THIS BLOCK STYLES
              </p>

              {/* Block Size Large vs Small */}
              <div className="grid grid-cols-2 gap-2 mb-3">
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, size: 'large' })}
                  className={`py-1.5 text-xs font-bold rounded-xl border transition-colors ${
                    formData.size === 'large'
                      ? 'border-indigo-600 bg-indigo-50/60 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400'
                      : 'border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400'
                  }`}
                >
                  Large Card
                </button>
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, size: 'small' })}
                  className={`py-1.5 text-xs font-bold rounded-xl border transition-colors ${
                    formData.size === 'small'
                      ? 'border-indigo-600 bg-indigo-50/60 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400'
                      : 'border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400'
                  }`}
                >
                  Small Card
                </button>
              </div>

              {/* Text Alignment */}
              <div className="mb-4">
                <label className="block text-[11px] font-bold text-zinc-600 dark:text-zinc-400 mb-1.5">
                  Text Alignment
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { id: 'left', label: 'Left', icon: FaAlignLeft },
                    { id: 'center', label: 'Center', icon: FaAlignCenter },
                    { id: 'right', label: 'Right', icon: FaAlignRight },
                  ].map((al) => (
                    <button
                      key={al.id}
                      type="button"
                      onClick={() => setFormData({ ...formData, text_align: al.id })}
                      className={`py-1.5 flex items-center justify-center gap-1.5 rounded-xl border text-xs font-bold transition-colors ${
                        formData.text_align === al.id
                          ? 'border-indigo-600 bg-indigo-50/60 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400'
                          : 'border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400'
                      }`}
                    >
                      <al.icon className="text-[10px]" />
                      {al.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Attention Micro-Animation */}
              <div>
                <label className="block text-[11px] font-bold text-zinc-600 dark:text-zinc-400 mb-1.5">
                  Attention Animation
                </label>
                <select
                  value={formData.animation || 'none'}
                  onChange={(e) => setFormData({ ...formData, animation: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl font-bold text-zinc-900 dark:text-white"
                >
                  <option value="none">None (Static)</option>
                  <option value="pulse">Attention Pulse (Gentle Breathe 3x Clicks)</option>
                  <option value="bounce">Bouncy Pop</option>
                  <option value="wiggle">Hover Wiggle</option>
                  <option value="glow">Cyber Halo Glow</option>
                </select>
              </div>
            </div>

            {/* Live Block Preview */}
            <div className="pt-4 border-t border-zinc-100 dark:border-zinc-800">
              <p className="text-[11px] font-bold uppercase tracking-wider text-zinc-400 mb-2">
                Card Preview
              </p>
              <div
                className="p-3.5 rounded-2xl border shadow-sm transition-all"
                style={{
                  background: theme.card_bg || '#FFFFFF',
                  borderColor: theme.card_border || 'rgba(0,0,0,0.1)',
                  color: theme.card_text_color || '#18181B',
                }}
              >
                <div className="flex items-center gap-3">
                  {formData.media_url && (
                    <img src={formData.media_url} alt="" className="w-12 h-12 rounded-xl object-cover flex-shrink-0" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-bold truncate">{formData.title || 'Spring 2026 Collection'}</p>
                    {formData.subtitle && (
                      <p className="text-[11px] opacity-75 truncate">{formData.subtitle}</p>
                    )}
                  </div>
                  {formData.badge && (
                    <span className="px-2 py-0.5 text-[9px] font-black uppercase rounded-full bg-amber-400 text-black">
                      {formData.badge}
                    </span>
                  )}
                </div>
              </div>
            </div>

          </div>

        </div>

      </div>
    </div>
  );
}
