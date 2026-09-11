import React, { useState, useEffect, useRef } from 'react';
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
  FaAlignLeft,
  FaAlignCenter,
  FaAlignRight,
  FaBolt,
  FaUpload,
  FaExclamationTriangle,
  FaStar,
  FaHeart,
  FaFire,
  FaShoppingBag,
  FaMusic,
  FaVideo,
  FaGlobe,
  FaEnvelope,
  FaCreditCard,
  FaCoins,
  FaCheckCircle,
} from 'react-icons/fa';
import { toast } from 'sonner';

function normalizeImageUrl(url) {
  if (!url || typeof url !== 'string') return '';
  let clean = url.trim();
  // Google Drive share link -> direct thumbnail image
  if (clean.includes('drive.google.com/file/d/')) {
    const match = clean.match(/\/file\/d\/([a-zA-Z0-9_-]+)/);
    if (match && match[1]) {
      return `https://drive.google.com/thumbnail?id=${match[1]}&sz=w1000`;
    }
  }
  // Dropbox link -> raw direct image
  if (clean.includes('dropbox.com')) {
    return clean.replace(/[?&]dl=0/, '?raw=1').replace(/[?&]dl=1/, '?raw=1');
  }
  // Imgur direct image
  if (clean.match(/^https?:\/\/imgur\.com\/([a-zA-Z0-9]+)$/)) {
    const id = clean.split('/').pop();
    return `https://i.imgur.com/${id}.jpg`;
  }
  return clean;
}

const IMAGE_PRESETS = [
  { label: 'Modern Studio', url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=600&q=80' },
  { label: 'Minimal Store', url: 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=600&q=80' },
  { label: 'Abstract 3D', url: 'https://images.unsplash.com/photo-1634017839464-5c339ebe3cb4?auto=format&fit=crop&w=600&q=80' },
  { label: 'Cyber Neon', url: 'https://images.unsplash.com/photo-1550745165-9bc0b252726f?auto=format&fit=crop&w=600&q=80' },
  { label: 'Warm Architecture', url: 'https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=600&q=80' },
  { label: 'Creator Studio', url: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=600&q=80' },
];

const POPULAR_EMOJIS = ['🔥', '🚀', '✨', '💡', '🎉', '💎', '🌟', '⚡', '🎯', '🏷️', '🎧', '🛍️', '💼', '☕', '❤️', '📈'];

const POPULAR_ICONS = [
  { id: 'star', label: 'Star', icon: FaStar },
  { id: 'heart', label: 'Heart', icon: FaHeart },
  { id: 'bolt', label: 'Bolt', icon: FaBolt },
  { id: 'fire', label: 'Fire', icon: FaFire },
  { id: 'shopping', label: 'Shopping', icon: FaShoppingBag },
  { id: 'music', label: 'Music', icon: FaMusic },
  { id: 'video', label: 'Video', icon: FaVideo },
  { id: 'link', label: 'Link', icon: FaLink },
  { id: 'globe', label: 'Globe', icon: FaGlobe },
  { id: 'mail', label: 'Mail', icon: FaEnvelope },
];

export default function BioBlockEditorModal({
  isOpen,
  onClose,
  block,
  onSaveBlock,
  onDeleteBlock,
  theme,
}) {
  const initialMediaUrl = normalizeImageUrl(block?.media_url || block?.image_url || block?.image || block?.thumbnail_url || block?.thumbnail || '');
  const [formData, setFormData] = useState(() => ({
    ...block,
    media_url: initialMediaUrl,
    layout: block?.layout || 'card_left_image',
    media_type: block?.media_type || (initialMediaUrl ? 'image' : 'image'),
    animation: block?.animation || (block?.is_featured ? 'pulse' : 'none'),
    text_align: block?.text_align || 'left',
    size: block?.size || 'large',
    tag: block?.tag || '',
  }));

  const [activeMediaTab, setActiveMediaTab] = useState(() => block?.media_type || (initialMediaUrl ? 'image' : 'image'));
  const [isGeneratingAi, setIsGeneratingAi] = useState(false);
  const [imageError, setImageError] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (block) {
      const mediaUrl = normalizeImageUrl(block?.media_url || block?.image_url || block?.image || block?.thumbnail_url || block?.thumbnail || '');
      setFormData({
        ...block,
        media_url: mediaUrl,
        layout: block?.layout || 'card_left_image',
        media_type: block?.media_type || (mediaUrl ? 'image' : 'image'),
        animation: block?.animation || (block?.is_featured ? 'pulse' : 'none'),
        text_align: block?.text_align || 'left',
        size: block?.size || 'large',
        tag: block?.tag || '',
      });
      setActiveMediaTab(block?.media_type || (mediaUrl ? 'image' : 'image'));
      setImageError(false);
    }
  }, [block]);

  if (!isOpen || !block) return null;

  const handleSave = () => {
    onSaveBlock({
      ...formData,
      media_type: activeMediaTab,
      is_featured: formData.animation === 'pulse',
    });
    onClose();
  };

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      toast.error('Please select an image file (PNG, JPG, WebP, etc.)');
      return;
    }
    const reader = new FileReader();
    reader.onload = (event) => {
      const result = event.target?.result;
      if (result) {
        setFormData((prev) => ({ ...prev, media_url: result }));
        setImageError(false);
        setActiveMediaTab('image');
        toast.success('Image loaded from device');
      }
    };
    reader.readAsDataURL(file);
  };

  const handleImageUrlChange = (val) => {
    const normalized = normalizeImageUrl(val);
    setFormData((prev) => ({ ...prev, media_url: normalized }));
    setImageError(false);
  };

  const handleQuickAiImage = async () => {
    setIsGeneratingAi(true);
    // Pick a diverse curated aesthetic photo
    const randomPreset = IMAGE_PRESETS[Math.floor(Math.random() * IMAGE_PRESETS.length)];
    setTimeout(() => {
      setFormData((prev) => ({ ...prev, media_url: randomPreset.url }));
      setImageError(false);
      setIsGeneratingAi(false);
      toast.success(`Applied ${randomPreset.label} image`);
    }, 400);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-3 sm:p-6 overflow-y-auto animate-in fade-in duration-200">
      <div className="bg-white/95 dark:bg-[#1C1C1E]/95 backdrop-blur-2xl border border-black/[0.08] dark:border-white/[0.1] rounded-[28px] max-w-4xl w-full shadow-[0_25px_70px_rgba(0,0,0,0.35)] overflow-hidden flex flex-col max-h-[90vh]">
        
        {/* Top Header (Apple macOS Sheet Bar) */}
        <div className="p-4 sm:px-6 border-b border-black/[0.06] dark:border-white/[0.08] flex items-center justify-between gap-3 bg-black/[0.02] dark:bg-white/[0.02]">
          <div className="flex items-center gap-2.5">
            <div className="flex items-center gap-1.5 mr-1">
              <span className="w-3 h-3 rounded-full bg-[#FF5F56] border border-[#E0443E]/50 cursor-pointer hover:opacity-80" onClick={onClose} />
              <span className="w-3 h-3 rounded-full bg-[#FFBD2E] border border-[#DEA123]/50" />
              <span className="w-3 h-3 rounded-full bg-[#27C93F] border border-[#1AAB29]/50" />
            </div>
            <h3 className="text-sm font-semibold tracking-tight text-gray-900 dark:text-white">
              Edit Block
            </h3>
            <span className="px-2.5 py-0.5 text-[10px] font-semibold capitalize bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 rounded-full border border-blue-200/50 dark:border-blue-800/40">
              {formData.type?.replace('_', ' ')}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => { onDeleteBlock(block.id); onClose(); }}
              className="p-2 text-gray-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/30 rounded-full transition-colors"
              title="Delete Block"
            >
              <FaTrash className="text-xs" />
            </button>
            <button
              onClick={handleSave}
              className="px-4 py-1.5 text-xs font-semibold bg-[#0071E3] hover:bg-[#0077ED] text-white rounded-full shadow-[0_2px_8px_rgba(0,113,227,0.3)] transition-all flex items-center gap-1.5"
            >
              <FaSave className="text-xs" /> Save Changes
            </button>
            <button
              onClick={onClose}
              className="p-2 text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-black/[0.04] dark:hover:bg-white/[0.08] rounded-full transition-colors"
            >
              <FaTimes className="text-xs" />
            </button>
          </div>
        </div>

        {/* 2-Column Split Editor: Left Content & Media vs Right Block Styles */}
        <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-black/[0.06] dark:divide-white/[0.08] overflow-y-auto flex-1 text-gray-800 dark:text-gray-200">
          
          {/* ── Left Column: Content, URL & Media ── */}
          <div className="p-5 space-y-4">
            
            {/* Button Type */}
            <div>
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                Button Type
              </label>
              <select
                value={formData.type}
                onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                className="w-full px-3 py-2 text-xs bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.06] dark:border-white/[0.08] rounded-xl font-medium text-gray-900 dark:text-white outline-none focus:ring-2 focus:ring-[#0071E3]"
              >
                <option value="link" className="bg-white dark:bg-[#1C1C1E] text-gray-900 dark:text-white">Destination URL</option>
                <option value="folder" className="bg-white dark:bg-[#1C1C1E] text-gray-900 dark:text-white">📁 Folder / Tappable Drawer</option>
                <option value="media_card" className="bg-white dark:bg-[#1C1C1E] text-gray-900 dark:text-white">Media Showcase Card</option>
                <option value="embed" className="bg-white dark:bg-[#1C1C1E] text-gray-900 dark:text-white">Video / Spotify Embed</option>
                <option value="feed_grid" className="bg-white dark:bg-[#1C1C1E] text-gray-900 dark:text-white">Live Instagram Feed Grid</option>
                <option value="lead_capture" className="bg-white dark:bg-[#1C1C1E] text-gray-900 dark:text-white">Newsletter Lead Capture</option>
              </select>
            </div>

            {/* Folder Sub-Links Manager */}
            {formData.type === 'folder' && (
              <div className="space-y-3 pt-2">
                <div className="flex items-center justify-between">
                  <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300">
                    Folder Links ({(formData.folder_items || []).length})
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      const newSub = {
                        id: `sub_${Date.now()}`,
                        title: 'New Sub Link',
                        url: 'https://',
                      };
                      setFormData((prev) => ({
                        ...prev,
                        folder_items: [...(prev.folder_items || []), newSub],
                      }));
                    }}
                    className="px-3 py-1 text-xs font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 rounded-full border border-amber-500/20 flex items-center gap-1 cursor-pointer transition-colors"
                  >
                    + Add Link Inside
                  </button>
                </div>

                <div className="space-y-2 max-h-48 overflow-y-auto custom-scrollbar">
                  {(formData.folder_items || []).length === 0 ? (
                    <p className="text-xs text-gray-400 italic p-3 text-center border border-dashed border-black/[0.08] dark:border-white/[0.1] rounded-2xl">
                      No links inside this folder yet. Click &ldquo;Add Link Inside&rdquo; above.
                    </p>
                  ) : (
                    formData.folder_items.map((sub, sIdx) => (
                      <div key={sub.id || sIdx} className="flex items-center gap-2 p-2 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08]">
                        <input
                          type="text"
                          value={sub.title}
                          onChange={(e) => {
                            const updated = [...(formData.folder_items || [])];
                            updated[sIdx].title = e.target.value;
                            setFormData({ ...formData, folder_items: updated });
                          }}
                          placeholder="Link Title"
                          className="w-1/3 px-2.5 py-1 text-xs bg-white dark:bg-[#2C2C2E] border border-black/[0.06] dark:border-white/[0.08] rounded-xl font-medium text-gray-900 dark:text-white"
                        />
                        <input
                          type="url"
                          value={sub.url}
                          onChange={(e) => {
                            const updated = [...(formData.folder_items || [])];
                            updated[sIdx].url = e.target.value;
                            setFormData({ ...formData, folder_items: updated });
                          }}
                          placeholder="https://..."
                          className="flex-1 px-2.5 py-1 text-xs bg-white dark:bg-[#2C2C2E] border border-black/[0.06] dark:border-white/[0.08] rounded-xl font-mono text-gray-900 dark:text-white"
                        />
                        <button
                          type="button"
                          onClick={() => {
                            const updated = (formData.folder_items || []).filter((_, idx) => idx !== sIdx);
                            setFormData({ ...formData, folder_items: updated });
                          }}
                          className="p-1.5 text-gray-400 hover:text-rose-500 rounded-lg transition-colors"
                        >
                          <FaTrash className="text-xs" />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {/* Destination URL */}
            {formData.type !== 'feed_grid' && formData.type !== 'lead_capture' && formData.type !== 'folder' && (
              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                  Destination URL
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="url"
                    value={formData.url || formData.embed_url || ''}
                    onChange={(e) => setFormData({ ...formData, url: e.target.value, embed_url: e.target.value })}
                    placeholder="https://..."
                    className="flex-1 px-3 py-2 text-xs bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.06] dark:border-white/[0.08] rounded-xl font-mono text-gray-900 dark:text-white outline-none focus:ring-2 focus:ring-[#0071E3]"
                  />
                  {formData.url && (
                    <a
                      href={formData.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-2.5 bg-black/[0.04] hover:bg-black/[0.08] dark:bg-white/[0.06] dark:hover:bg-white/[0.1] rounded-xl text-gray-600 dark:text-gray-300 text-xs transition-colors"
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
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
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
                      className={`p-2.5 rounded-2xl border text-center transition-all ${
                        isSelected
                          ? 'border-[#0071E3] bg-blue-50/60 dark:bg-blue-950/40 text-[#0071E3] dark:text-blue-400 font-semibold shadow-xs'
                          : 'border-black/[0.06] dark:border-white/[0.08] hover:border-black/[0.12] dark:hover:border-white/[0.15] text-gray-600 dark:text-gray-400 bg-white/60 dark:bg-white/[0.04]'
                      }`}
                    >
                      <div className="w-full h-6 rounded-lg bg-black/[0.04] dark:bg-white/[0.08] mb-1.5 flex items-center justify-center text-[10px]">
                        {ly.id === 'card_left_image' && '◧'}
                        {ly.id === 'card_banner_top' && '⬒'}
                        {ly.id === 'compact_pill' && '━'}
                        {ly.id === 'grid_card' && '▦'}
                      </div>
                      <span className="text-[10px] font-semibold block truncate">{ly.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Media Tabs [ Image | Icon | Emoji | 3D ] (Apple Capsule Switcher) */}
            <div>
              <div className="flex p-1 rounded-full bg-black/[0.04] dark:bg-white/[0.06] border border-black/[0.04] dark:border-white/[0.06] mb-3">
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
                    className={`flex-1 py-1 px-2.5 text-xs font-semibold rounded-full transition-all flex items-center justify-center gap-1.5 ${
                      activeMediaTab === m.id
                        ? 'bg-white dark:bg-[#636366] text-gray-900 dark:text-white shadow-[0_2px_6px_rgba(0,0,0,0.08),0_1px_2px_rgba(0,0,0,0.04)]'
                        : 'text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200'
                    }`}
                  >
                    <m.icon className="text-[11px]" />
                    <span>{m.label}</span>
                  </button>
                ))}
              </div>

              {/* 1. Image Media Tab */}
              {activeMediaTab === 'image' && (
                <div className="space-y-3">
                  <div className="flex items-start gap-3">
                    {/* Live Image Box */}
                    <div className="relative w-16 h-16 rounded-2xl bg-black/[0.04] dark:bg-white/[0.06] border border-black/[0.06] dark:border-white/[0.08] overflow-hidden shrink-0 flex items-center justify-center">
                      {formData.media_url && !imageError ? (
                        <img
                          src={formData.media_url}
                          alt="Block Thumbnail"
                          onError={() => setImageError(true)}
                          onLoad={() => setImageError(false)}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="flex flex-col items-center justify-center p-1 text-center text-gray-400">
                          {imageError ? (
                            <FaExclamationTriangle className="text-amber-500 text-base mb-0.5" />
                          ) : (
                            <FaImage className="text-base mb-0.5 opacity-60" />
                          )}
                          <span className="text-[9px] font-semibold leading-tight">
                            {imageError ? 'Invalid' : 'No Image'}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Image URL & Controls */}
                    <div className="flex-1 space-y-2">
                      <input
                        type="url"
                        value={formData.media_url || ''}
                        onChange={(e) => handleImageUrlChange(e.target.value)}
                        placeholder="Paste image link (JPG, PNG, Unsplash, Drive, Dropbox)..."
                        className="w-full px-3 py-1.5 text-xs bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.06] dark:border-white/[0.08] rounded-xl font-mono text-gray-900 dark:text-white placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:bg-white dark:focus:bg-[#2C2C2E] focus:border-[#0071E3] outline-none transition-colors"
                      />

                      {/* Helper Action Pills */}
                      <div className="flex items-center gap-2 flex-wrap">
                        {/* Hidden file input for direct computer uploads */}
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept="image/*"
                          className="hidden"
                          onChange={handleFileUpload}
                        />
                        <button
                          type="button"
                          onClick={() => fileInputRef.current?.click()}
                          className="px-3 py-1 text-[11px] font-semibold bg-black/[0.04] hover:bg-black/[0.08] dark:bg-white/[0.06] dark:hover:bg-white/[0.1] text-gray-700 dark:text-gray-200 border border-black/[0.06] dark:border-white/[0.08] rounded-full transition-colors flex items-center gap-1.5"
                        >
                          <FaUpload className="text-[10px]" /> Upload Image
                        </button>

                        <button
                          type="button"
                          onClick={handleQuickAiImage}
                          disabled={isGeneratingAi}
                          className="px-3 py-1 text-[11px] font-semibold bg-blue-50 hover:bg-blue-100 dark:bg-blue-950/50 dark:hover:bg-blue-900/50 text-blue-600 dark:text-blue-400 border border-blue-200/50 dark:border-blue-800/40 rounded-full transition-colors flex items-center gap-1.5"
                        >
                          <FaMagic className="text-[10px]" /> {isGeneratingAi ? 'Suggesting…' : 'AI Preset'}
                        </button>

                        {formData.media_url && (
                          <button
                            type="button"
                            onClick={() => {
                              setFormData((prev) => ({ ...prev, media_url: '' }));
                              setImageError(false);
                            }}
                            className="px-3 py-1 text-[11px] font-semibold text-rose-500 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/30 rounded-full transition-colors flex items-center gap-1.5"
                          >
                            <FaTrash className="text-[10px]" /> Clear
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Image Error Alert if Link Fails */}
                  {imageError && (
                    <div className="text-[11px] text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/30 px-3 py-2 rounded-2xl flex items-start gap-2 border border-amber-200 dark:border-amber-800/50">
                      <FaExclamationTriangle className="text-amber-500 shrink-0 mt-0.5 text-xs" />
                      <div>
                        <p className="font-semibold">Image failed to display from this link</p>
                        <p className="text-[10px] opacity-80">
                          The link may be protected or not direct. Try clicking <strong>Upload Image</strong> above to load it directly from your device.
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Curated Presets Strip */}
                  <div>
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-1.5 block">
                      Quick Curated Presets
                    </span>
                    <div className="grid grid-cols-3 sm:grid-cols-6 gap-1.5">
                      {IMAGE_PRESETS.map((preset, pIdx) => (
                        <button
                          key={pIdx}
                          type="button"
                          onClick={() => {
                            setFormData((prev) => ({ ...prev, media_url: preset.url }));
                            setImageError(false);
                          }}
                          className="group relative h-11 rounded-xl overflow-hidden border border-black/[0.06] dark:border-white/[0.08] hover:border-[#0071E3] transition-all text-left shadow-2xs"
                        >
                          <img src={preset.url} alt={preset.label} className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-300" />
                          <span className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent flex items-end p-1 text-[8px] font-semibold text-white truncate">
                            {preset.label}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* 2. Icon Media Tab */}
              {activeMediaTab === 'icon' && (
                <div className="space-y-2">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 block">
                    Choose Icon
                  </span>
                  <div className="grid grid-cols-5 gap-2">
                    {POPULAR_ICONS.map((ic) => (
                      <button
                        key={ic.id}
                        type="button"
                        onClick={() => setFormData((prev) => ({ ...prev, icon: ic.id, media_type: 'icon' }))}
                        className={`p-2.5 rounded-2xl border flex flex-col items-center gap-1 transition-all ${
                          formData.icon === ic.id
                            ? 'border-[#0071E3] bg-blue-50/60 dark:bg-blue-950/40 text-[#0071E3] dark:text-blue-400 font-semibold shadow-2xs'
                            : 'border-black/[0.06] dark:border-white/[0.08] hover:border-black/[0.12] dark:hover:border-white/[0.15] text-gray-700 dark:text-gray-300 bg-white/60 dark:bg-white/[0.04]'
                        }`}
                      >
                        <ic.icon className="text-base" />
                        <span className="text-[9px] truncate">{ic.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* 3. Emoji Media Tab */}
              {activeMediaTab === 'emoji' && (
                <div className="space-y-2">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 block">
                    Choose Emoji Badge
                  </span>
                  <div className="flex items-center gap-2 mb-2">
                    <input
                      type="text"
                      maxLength={4}
                      value={formData.emoji || ''}
                      onChange={(e) => setFormData((prev) => ({ ...prev, emoji: e.target.value, media_type: 'emoji' }))}
                      placeholder="✨ Custom Emoji"
                      className="w-36 px-2.5 py-1.5 text-xs bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.06] dark:border-white/[0.08] rounded-xl font-bold text-gray-900 dark:text-white text-center outline-none focus:ring-2 focus:ring-[#0071E3]"
                    />
                    <span className="text-[11px] text-gray-400">or pick below:</span>
                  </div>
                  <div className="grid grid-cols-8 gap-1.5">
                    {POPULAR_EMOJIS.map((em, eIdx) => (
                      <button
                        key={eIdx}
                        type="button"
                        onClick={() => setFormData((prev) => ({ ...prev, emoji: em, media_type: 'emoji' }))}
                        className={`p-2 rounded-xl text-lg border transition-all flex items-center justify-center hover:scale-110 ${
                          formData.emoji === em
                            ? 'border-[#0071E3] bg-blue-50/60 dark:bg-blue-950/40 shadow-xs'
                            : 'border-black/[0.06] dark:border-white/[0.08] bg-white/60 dark:bg-white/[0.04] hover:bg-black/[0.03] dark:hover:bg-white/[0.08]'
                        }`}
                      >
                        {em}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* 4. 3D Art Tab */}
              {activeMediaTab === '3d' && (
                <div className="p-4 bg-black/[0.02] dark:bg-white/[0.03] rounded-2xl border border-dashed border-black/[0.08] dark:border-white/[0.1] text-center space-y-2">
                  <FaCube className="text-2xl text-[#0071E3] mx-auto mb-1" />
                  <p className="text-xs font-semibold text-gray-800 dark:text-gray-200">3D Glassmorphic Art</p>
                  <p className="text-[10px] text-gray-500 dark:text-gray-400 max-w-sm mx-auto">
                    Select 3D stylized rendered badges in the icon options or load translucent 3D assets.
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      setFormData((prev) => ({
                        ...prev,
                        media_url: 'https://images.unsplash.com/photo-1634017839464-5c339ebe3cb4?auto=format&fit=crop&w=600&q=80',
                      }));
                      setImageError(false);
                      setActiveMediaTab('image');
                      toast.success('Applied 3D Holographic art');
                    }}
                    className="mt-1 px-4 py-1.5 text-xs font-semibold bg-blue-50 dark:bg-blue-950/50 text-blue-600 dark:text-blue-400 rounded-full hover:bg-blue-100 dark:hover:bg-blue-900/50 border border-blue-200/50 dark:border-blue-800/40 transition-colors"
                  >
                    Apply 3D Art Sample
                  </button>
                </div>
              )}
            </div>

            {/* Text Inputs: Title, Subtitle, Badge, Tag */}
            <div className="space-y-3 pt-2 border-t border-black/[0.06] dark:border-white/[0.08]">
              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                  Title
                </label>
                <input
                  type="text"
                  value={formData.title || formData.headline || ''}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value, headline: e.target.value })}
                  placeholder="e.g. Spring 2026 Collection"
                  className="w-full px-3 py-2 text-xs font-semibold bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.06] dark:border-white/[0.08] rounded-xl text-gray-900 dark:text-white focus:bg-white dark:focus:bg-[#2C2C2E] focus:border-[#0071E3] outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                  Description / Subtitle
                </label>
                <textarea
                  rows={2}
                  value={formData.subtitle || formData.subheadline || ''}
                  onChange={(e) => setFormData({ ...formData, subtitle: e.target.value, subheadline: e.target.value })}
                  placeholder="Short description under title..."
                  className="w-full px-3 py-1.5 text-xs bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.06] dark:border-white/[0.08] rounded-xl text-gray-800 dark:text-gray-200 resize-none focus:bg-white dark:focus:bg-[#2C2C2E] focus:border-[#0071E3] outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[11px] font-semibold text-gray-600 dark:text-gray-400 mb-1">
                    Badge Highlight
                  </label>
                  <input
                    type="text"
                    value={formData.badge || ''}
                    onChange={(e) => setFormData({ ...formData, badge: e.target.value })}
                    placeholder="e.g. HOT, NEW, SALE"
                    className="w-full px-2.5 py-1.5 text-xs bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.06] dark:border-white/[0.08] rounded-xl text-gray-800 dark:text-gray-200 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-gray-600 dark:text-gray-400 mb-1">
                    Tag Category
                  </label>
                  <input
                    type="text"
                    value={formData.tag || ''}
                    onChange={(e) => setFormData({ ...formData, tag: e.target.value })}
                    placeholder="e.g. Shop, Music"
                    className="w-full px-2.5 py-1.5 text-xs bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.06] dark:border-white/[0.08] rounded-xl text-gray-800 dark:text-gray-200 outline-none"
                  />
                </div>
              </div>
            </div>

          </div>

          {/* ── Right Column: Block Styles & Animation ── */}
          <div className="p-5 space-y-5 bg-black/[0.015] dark:bg-white/[0.02]">
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-3">
                Block Styling & Effects
              </p>

              {/* Block Size Large vs Small */}
              <div className="grid grid-cols-2 gap-2 mb-3">
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, size: 'large' })}
                  className={`py-1.5 text-xs font-semibold rounded-xl border transition-colors ${
                    formData.size === 'large'
                      ? 'border-[#0071E3] bg-blue-50/60 dark:bg-blue-950/40 text-[#0071E3] dark:text-blue-400 shadow-2xs'
                      : 'border-black/[0.06] dark:border-white/[0.08] text-gray-600 dark:text-gray-400 bg-white/60 dark:bg-white/[0.04]'
                  }`}
                >
                  Large Card
                </button>
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, size: 'small' })}
                  className={`py-1.5 text-xs font-semibold rounded-xl border transition-colors ${
                    formData.size === 'small'
                      ? 'border-[#0071E3] bg-blue-50/60 dark:bg-blue-950/40 text-[#0071E3] dark:text-blue-400 shadow-2xs'
                      : 'border-black/[0.06] dark:border-white/[0.08] text-gray-600 dark:text-gray-400 bg-white/60 dark:bg-white/[0.04]'
                  }`}
                >
                  Small Card
                </button>
              </div>

              {/* Text Alignment */}
              <div className="mb-4">
                <label className="block text-[11px] font-semibold text-gray-600 dark:text-gray-400 mb-1.5">
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
                      className={`py-1.5 flex items-center justify-center gap-1.5 rounded-xl border text-xs font-semibold transition-colors ${
                        formData.text_align === al.id
                          ? 'border-[#0071E3] bg-blue-50/60 dark:bg-blue-950/40 text-[#0071E3] dark:text-blue-400 shadow-2xs'
                          : 'border-black/[0.06] dark:border-white/[0.08] text-gray-600 dark:text-gray-400 bg-white/60 dark:bg-white/[0.04]'
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
                <label className="block text-[11px] font-semibold text-gray-600 dark:text-gray-400 mb-1.5">
                  Attention Animation
                </label>
                <select
                  value={formData.animation || 'none'}
                  onChange={(e) => setFormData({ ...formData, animation: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-white dark:bg-[#2C2C2E] border border-black/[0.06] dark:border-white/[0.08] rounded-xl font-medium text-gray-900 dark:text-white outline-none focus:ring-2 focus:ring-[#0071E3]"
                >
                  <option value="none" className="bg-white dark:bg-[#1C1C1E] text-gray-900 dark:text-white">None (Static)</option>
                  <option value="pulse" className="bg-white dark:bg-[#1C1C1E] text-gray-900 dark:text-white">Attention Pulse (Gentle Breathe 3x Clicks)</option>
                  <option value="bounce" className="bg-white dark:bg-[#1C1C1E] text-gray-900 dark:text-white">Bouncy Pop</option>
                  <option value="wiggle" className="bg-white dark:bg-[#1C1C1E] text-gray-900 dark:text-white">Hover Wiggle</option>
                  <option value="glow" className="bg-white dark:bg-[#1C1C1E] text-gray-900 dark:text-white">Cyber Halo Glow</option>
                </select>
              </div>
            </div>

            {/* Live Block Preview */}
            <div className="pt-4 border-t border-black/[0.06] dark:border-white/[0.08]">
              <div className="flex items-center justify-between mb-2">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                  Card Preview
                </p>
                <span className="text-[10px] text-gray-400 dark:text-gray-500 capitalize">
                  {formData.layout?.replace(/_/g, ' ')}
                </span>
              </div>

              <div
                className={`rounded-2xl border shadow-xs transition-all overflow-hidden ${
                  formData.layout === 'card_banner_top'
                    ? 'flex flex-col text-left'
                    : formData.layout === 'compact_pill'
                    ? 'py-2 px-3 flex items-center justify-between text-center'
                    : 'p-3.5 flex items-center justify-between text-left'
                }`}
                style={{
                  background: theme?.card_bg || '#FFFFFF',
                  borderColor: theme?.card_border || 'rgba(0,0,0,0.1)',
                  color: theme?.card_text_color || '#18181B',
                }}
              >
                {/* 1. Hero Banner on Top for card_banner_top */}
                {formData.layout === 'card_banner_top' && formData.media_url && !imageError && (
                  <div className="w-full h-28 overflow-hidden bg-black/5 relative">
                    <img
                      src={formData.media_url}
                      alt=""
                      onError={() => setImageError(true)}
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent pointer-events-none" />
                  </div>
                )}

                {/* 2. Content Row */}
                <div className={`flex items-center gap-3 w-full ${formData.layout === 'card_banner_top' ? 'p-3' : ''}`}>
                  {/* Left Media: only for non-banner and non-pill layouts */}
                  {formData.layout !== 'card_banner_top' && formData.layout !== 'compact_pill' && (
                    <>
                      {formData.media_url && !imageError ? (
                        <img
                          src={formData.media_url}
                          alt=""
                          onError={() => setImageError(true)}
                          className="w-11 h-11 rounded-xl object-cover shrink-0 shadow-2xs border border-black/5 dark:border-white/10"
                        />
                      ) : formData.emoji ? (
                        <div className="w-10 h-10 rounded-xl bg-black/[0.04] dark:bg-white/[0.06] flex items-center justify-center text-lg shrink-0">
                          {formData.emoji}
                        </div>
                      ) : null}
                    </>
                  )}

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {formData.animation === 'pulse' && (
                        <FaBolt className="text-amber-400 text-xs shrink-0 animate-pulse" />
                      )}
                      <p className="text-xs font-semibold truncate">
                        {formData.title || formData.headline || 'Spring 2026 Collection'}
                      </p>
                      {formData.badge && (
                        <span className="px-1.5 py-0.5 text-[8px] font-bold uppercase rounded-full bg-gradient-to-r from-rose-500 to-pink-500 text-white shadow-2xs">
                          {formData.badge}
                        </span>
                      )}
                    </div>
                    {formData.subtitle && (
                      <p className="text-[10px] opacity-75 truncate mt-0.5">
                        {formData.subtitle}
                      </p>
                    )}
                  </div>

                  <div className="w-6 h-6 rounded-full bg-black/5 dark:bg-white/10 flex items-center justify-center opacity-60 shrink-0">
                    <FaExternalLinkAlt className="text-[9px]" />
                  </div>
                </div>
              </div>
            </div>

          </div>

        </div>

      </div>
    </div>
  );
}
