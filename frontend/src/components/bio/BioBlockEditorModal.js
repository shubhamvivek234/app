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
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6 overflow-y-auto animate-in fade-in duration-150">
      <div className="bg-white border border-gray-200 rounded-3xl max-w-4xl w-full shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        
        {/* Top Header */}
        <div className="p-4 border-b border-gray-100 flex items-center justify-between gap-3 bg-gray-50/50">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-bold text-gray-900">
              Edit Block
            </h3>
            <span className="px-2 py-0.5 text-[10px] font-black uppercase tracking-wider bg-blue-50 text-blue-600 rounded-md">
              {formData.type?.replace('_', ' ')}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => { onDeleteBlock(block.id); onClose(); }}
              className="p-2 text-gray-500 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition-colors"
              title="Delete Block"
            >
              <FaTrash className="text-xs" />
            </button>
            <button
              onClick={handleSave}
              className="px-4 py-1.5 text-xs font-bold bg-blue-500 hover:bg-blue-400 text-white rounded-xl shadow-xs transition-colors flex items-center gap-1.5"
            >
              <FaSave className="text-xs" /> Save Changes
            </button>
            <button
              onClick={onClose}
              className="p-2 text-gray-500 hover:text-gray-600 rounded-xl"
            >
              <FaTimes className="text-xs" />
            </button>
          </div>
        </div>

        {/* 2-Column Split Editor: Left Content & Media vs Right Block Styles */}
        <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-gray-100 overflow-y-auto flex-1">
          
          {/* ── Left Column: Content, URL & Media ── */}
          <div className="p-5 space-y-4">
            
            {/* Button Type */}
            <div>
              <label className="block text-xs font-bold text-gray-700 mb-1">
                Button Type
              </label>
              <select
                value={formData.type}
                onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                className="w-full px-3 py-2 text-xs bg-gray-50 border border-gray-200 rounded-xl font-semibold text-gray-900"
              >
                <option value="link">Destination URL</option>
                <option value="folder">📁 Folder / Tappable Drawer</option>
                <option value="media_card">Media Showcase Card</option>
                <option value="embed">Video / Spotify Embed</option>
                <option value="feed_grid">Live Instagram Feed Grid</option>
                <option value="lead_capture">Newsletter Lead Capture</option>
              </select>
            </div>

            {/* Folder Sub-Links Manager */}
            {formData.type === 'folder' && (
              <div className="space-y-3 pt-2">
                <div className="flex items-center justify-between">
                  <label className="block text-xs font-bold text-gray-700">
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
                    className="px-2.5 py-1 text-xs font-bold bg-amber-500/10 text-amber-600 hover:bg-amber-500/20 rounded-lg flex items-center gap-1 cursor-pointer"
                  >
                    + Add Link Inside
                  </button>
                </div>

                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {(formData.folder_items || []).length === 0 ? (
                    <p className="text-xs text-gray-500 italic p-3 text-center border border-dashed border-gray-200 rounded-xl">
                      No links inside this folder yet. Click &ldquo;Add Link Inside&rdquo; above.
                    </p>
                  ) : (
                    formData.folder_items.map((sub, sIdx) => (
                      <div key={sub.id || sIdx} className="flex items-center gap-2 p-2 rounded-xl bg-gray-50 border border-gray-200">
                        <input
                          type="text"
                          value={sub.title}
                          onChange={(e) => {
                            const updated = [...(formData.folder_items || [])];
                            updated[sIdx].title = e.target.value;
                            setFormData({ ...formData, folder_items: updated });
                          }}
                          placeholder="Link Title"
                          className="w-1/3 px-2 py-1 text-xs bg-white border border-gray-200 rounded-lg font-semibold text-gray-900"
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
                          className="flex-1 px-2 py-1 text-xs bg-white border border-gray-200 rounded-lg font-mono text-gray-900"
                        />
                        <button
                          type="button"
                          onClick={() => {
                            const updated = (formData.folder_items || []).filter((_, idx) => idx !== sIdx);
                            setFormData({ ...formData, folder_items: updated });
                          }}
                          className="p-1.5 text-gray-500 hover:text-rose-600 rounded-lg"
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
                <label className="block text-xs font-bold text-gray-700 mb-1">
                  Destination URL
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="url"
                    value={formData.url || formData.embed_url || ''}
                    onChange={(e) => setFormData({ ...formData, url: e.target.value, embed_url: e.target.value })}
                    placeholder="https://..."
                    className="flex-1 px-3 py-2 text-xs bg-gray-50 border border-gray-200 rounded-xl font-mono text-gray-900 outline-hidden focus:ring-2 focus:ring-blue-500"
                  />
                  {formData.url && (
                    <a
                      href={formData.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-2.5 bg-gray-100 hover:bg-gray-200 rounded-xl text-gray-600 text-xs"
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
              <label className="block text-xs font-bold text-gray-700 mb-2">
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
                          ? 'border-blue-600 bg-blue-50/60 text-blue-600 font-bold shadow-2xs'
                          : 'border-gray-200 hover:border-gray-300 text-gray-600'
                      }`}
                    >
                      <div className="w-full h-6 rounded bg-gray-200/80 mb-1 flex items-center justify-center text-[10px]">
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
              <div className="flex border-b border-gray-100 mb-3">
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
                        ? 'border-blue-600 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-600'
                    }`}
                  >
                    <m.icon className="text-xs" />
                    {m.label}
                  </button>
                ))}
              </div>

              {/* 1. Image Media Tab */}
              {activeMediaTab === 'image' && (
                <div className="space-y-3">
                  <div className="flex items-start gap-3">
                    {/* Live Image Box */}
                    <div className="relative w-16 h-16 rounded-2xl bg-gray-100 border border-gray-200 overflow-hidden flex-shrink-0 flex items-center justify-center">
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
                          <span className="text-[9px] font-bold leading-tight">
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
                        className="w-full px-3 py-1.5 text-xs bg-gray-50 border border-gray-200 rounded-xl font-mono text-gray-900 placeholder:text-gray-400 focus:bg-white focus:border-blue-500 outline-hidden transition-colors"
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
                          className="px-2.5 py-1 text-[11px] font-bold bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-colors flex items-center gap-1"
                        >
                          <FaUpload className="text-[10px]" /> Upload Image
                        </button>

                        <button
                          type="button"
                          onClick={handleQuickAiImage}
                          disabled={isGeneratingAi}
                          className="px-2.5 py-1 text-[11px] font-bold bg-blue-50 hover:bg-blue-100 text-blue-600 rounded-lg transition-colors flex items-center gap-1"
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
                            className="px-2.5 py-1 text-[11px] font-bold text-rose-500 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors flex items-center gap-1"
                          >
                            <FaTrash className="text-[10px]" /> Clear
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Image Error Alert if Link Fails */}
                  {imageError && (
                    <div className="text-[11px] text-amber-700 bg-amber-50 px-3 py-2 rounded-xl flex items-start gap-2 border border-amber-200">
                      <FaExclamationTriangle className="text-amber-500 shrink-0 mt-0.5 text-xs" />
                      <div>
                        <p className="font-bold">Image failed to display from this link</p>
                        <p className="text-[10px] text-amber-600">
                          The link may be protected or not direct. Try clicking <strong>Upload Image</strong> above to load it directly from your device.
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Curated Presets Strip */}
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1.5 block">
                      Quick Royalty-Free Presets
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
                          className="group relative h-10 rounded-lg overflow-hidden border border-gray-200 hover:border-blue-500 transition-all text-left"
                        >
                          <img src={preset.url} alt={preset.label} className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-200" />
                          <span className="absolute inset-0 bg-black/40 flex items-end p-1 text-[8px] font-bold text-white truncate">
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
                  <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                    Choose Icon
                  </span>
                  <div className="grid grid-cols-5 gap-2">
                    {POPULAR_ICONS.map((ic) => (
                      <button
                        key={ic.id}
                        type="button"
                        onClick={() => setFormData((prev) => ({ ...prev, icon: ic.id, media_type: 'icon' }))}
                        className={`p-2.5 rounded-xl border flex flex-col items-center gap-1 transition-all ${
                          formData.icon === ic.id
                            ? 'border-blue-500 bg-blue-50/70 text-blue-600 font-bold'
                            : 'border-gray-200 hover:border-gray-300 text-gray-700 bg-white'
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
                  <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                    Choose Emoji Badge
                  </span>
                  <div className="flex items-center gap-2 mb-2">
                    <input
                      type="text"
                      maxLength={4}
                      value={formData.emoji || ''}
                      onChange={(e) => setFormData((prev) => ({ ...prev, emoji: e.target.value, media_type: 'emoji' }))}
                      placeholder="✨ Custom Emoji"
                      className="w-36 px-2.5 py-1.5 text-xs bg-gray-50 border border-gray-200 rounded-xl font-bold text-gray-900 text-center"
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
                            ? 'border-blue-500 bg-blue-50 shadow-2xs'
                            : 'border-gray-200 bg-white hover:bg-gray-50'
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
                <div className="p-3 bg-gray-50 rounded-2xl border border-dashed border-gray-200 text-center space-y-1.5">
                  <FaCube className="text-xl text-blue-500 mx-auto mb-1" />
                  <p className="text-xs font-bold text-gray-800">3D Glassmorphic Icon Pack</p>
                  <p className="text-[10px] text-gray-500">
                    Select from 3D stylized rendered badges in the icon options or upload custom 3D PNG transparent assets.
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
                    className="mt-1 px-3 py-1 text-xs font-bold bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100"
                  >
                    Apply 3D Art Sample
                  </button>
                </div>
              )}
            </div>

            {/* Text Inputs: Title, Subtitle, Badge, Tag */}
            <div className="space-y-3 pt-2 border-t border-gray-100">
              <div>
                <label className="block text-xs font-bold text-gray-700 mb-1">
                  Title
                </label>
                <input
                  type="text"
                  value={formData.title || formData.headline || ''}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value, headline: e.target.value })}
                  placeholder="e.g. Spring 2026 Collection"
                  className="w-full px-3 py-2 text-xs font-bold bg-gray-50 border border-gray-200 rounded-xl text-gray-900"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-700 mb-1">
                  Description / Subtitle
                </label>
                <textarea
                  rows={2}
                  value={formData.subtitle || formData.subheadline || ''}
                  onChange={(e) => setFormData({ ...formData, subtitle: e.target.value, subheadline: e.target.value })}
                  placeholder="Short description under title..."
                  className="w-full px-3 py-1.5 text-xs bg-gray-50 border border-gray-200 rounded-xl text-gray-800 resize-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[11px] font-bold text-gray-600 mb-1">
                    Badge Highlight
                  </label>
                  <input
                    type="text"
                    value={formData.badge || ''}
                    onChange={(e) => setFormData({ ...formData, badge: e.target.value })}
                    placeholder="e.g. HOT, NEW, SALE"
                    className="w-full px-2.5 py-1.5 text-xs bg-gray-50 border border-gray-200 rounded-xl text-gray-800"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-bold text-gray-600 mb-1">
                    Tag Category
                  </label>
                  <input
                    type="text"
                    value={formData.tag || ''}
                    onChange={(e) => setFormData({ ...formData, tag: e.target.value })}
                    placeholder="e.g. Shop, Music"
                    className="w-full px-2.5 py-1.5 text-xs bg-gray-50 border border-gray-200 rounded-xl text-gray-800"
                  />
                </div>
              </div>
            </div>

          </div>

          {/* ── Right Column: Block Styles & Animation ── */}
          <div className="p-5 space-y-5 bg-gray-50/40">
            <div>
              <p className="text-xs font-bold text-gray-900 mb-2">
                THIS BLOCK STYLES
              </p>

              {/* Block Size Large vs Small */}
              <div className="grid grid-cols-2 gap-2 mb-3">
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, size: 'large' })}
                  className={`py-1.5 text-xs font-bold rounded-xl border transition-colors ${
                    formData.size === 'large'
                      ? 'border-blue-600 bg-blue-50/60 text-blue-600'
                      : 'border-gray-200 text-gray-600'
                  }`}
                >
                  Large Card
                </button>
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, size: 'small' })}
                  className={`py-1.5 text-xs font-bold rounded-xl border transition-colors ${
                    formData.size === 'small'
                      ? 'border-blue-600 bg-blue-50/60 text-blue-600'
                      : 'border-gray-200 text-gray-600'
                  }`}
                >
                  Small Card
                </button>
              </div>

              {/* Text Alignment */}
              <div className="mb-4">
                <label className="block text-[11px] font-bold text-gray-600 mb-1.5">
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
                          ? 'border-blue-600 bg-blue-50/60 text-blue-600'
                          : 'border-gray-200 text-gray-600'
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
                <label className="block text-[11px] font-bold text-gray-600 mb-1.5">
                  Attention Animation
                </label>
                <select
                  value={formData.animation || 'none'}
                  onChange={(e) => setFormData({ ...formData, animation: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-white border border-gray-200 rounded-xl font-bold text-gray-900"
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
            <div className="pt-4 border-t border-gray-100">
              <div className="flex items-center justify-between mb-2">
                <p className="text-[11px] font-bold uppercase tracking-wider text-gray-500">
                  Card Preview
                </p>
                <span className="text-[10px] text-gray-400 capitalize">
                  {formData.layout?.replace(/_/g, ' ')}
                </span>
              </div>

              <div
                className={`rounded-2xl border shadow-sm transition-all overflow-hidden ${
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
                          className="w-11 h-11 rounded-xl object-cover flex-shrink-0 shadow-xs border border-gray-100"
                        />
                      ) : formData.emoji ? (
                        <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center text-lg flex-shrink-0">
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
                      <p className="text-xs font-bold truncate">
                        {formData.title || formData.headline || 'Spring 2026 Collection'}
                      </p>
                      {formData.badge && (
                        <span className="px-1.5 py-0.5 text-[8px] font-black uppercase rounded-full bg-gradient-to-r from-rose-500 to-pink-500 text-white shadow-xs">
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

                  <div className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center text-gray-500 opacity-60 flex-shrink-0">
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
