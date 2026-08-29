import React, { useState, useEffect } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { getMyBioPage, saveMyBioPage } from '@/lib/api';
import { toast } from 'sonner';
import {
  FaMobileAlt,
  FaPlus,
  FaTrash,
  FaExternalLinkAlt,
  FaCopy,
  FaPalette,
  FaInstagram,
  FaTwitter,
  FaYoutube,
  FaLinkedin,
  FaTiktok,
  FaGlobe,
  FaSave,
} from 'react-icons/fa';

export default function LinkInBio() {
  const [handle, setHandle] = useState('');
  const [title, setTitle] = useState('');
  const [bio, setBio] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [theme, setTheme] = useState({
    background_type: 'solid',
    background_color: '#0f172a',
    card_background: '#1e293b',
    text_color: '#ffffff',
    accent_color: '#6366f1',
    button_style: 'rounded-2xl',
  });
  const [customLinks, setCustomLinks] = useState([]);
  const [socialLinks, setSocialLinks] = useState({});
  const [autoSyncGrid, setAutoSyncGrid] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const loadData = async () => {
    try {
      setLoading(true);
      const data = await getMyBioPage();
      if (data) {
        setHandle(data.handle || '');
        setTitle(data.title || '');
        setBio(data.bio || '');
        setAvatarUrl(data.avatar_url || '');
        if (data.theme) setTheme(data.theme);
        setCustomLinks(data.custom_links || []);
        setSocialLinks(data.social_links || {});
        setAutoSyncGrid(data.auto_sync_instagram_grid ?? true);
      }
    } catch (err) {
      toast.error('Failed to load Bio page settings');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleAddLink = () => {
    const newId = `link_${Date.now()}`;
    setCustomLinks((prev) => [
      ...prev,
      { id: newId, title: 'New Link', url: 'https://', icon: 'globe', is_active: true, clicks: 0 },
    ]);
  };

  const handleUpdateLink = (id, key, val) => {
    setCustomLinks((prev) =>
      prev.map((l) => (l.id === id ? { ...l, [key]: val } : l))
    );
  };

  const handleDeleteLink = (id) => {
    setCustomLinks((prev) => prev.filter((l) => l.id !== id));
  };

  const handleSave = async () => {
    if (!handle) {
      toast.error('Please enter a handle (e.g. yourbrand)');
      return;
    }
    setSaving(true);
    try {
      await saveMyBioPage({
        handle,
        title,
        bio,
        avatar_url: avatarUrl || undefined,
        theme,
        custom_links: customLinks,
        social_links: socialLinks,
        auto_sync_instagram_grid: autoSyncGrid,
        is_published: true,
      });
      toast.success('Link-in-Bio page saved!');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to save bio page');
    } finally {
      setSaving(false);
    }
  };

  const publicUrl = `https://www.unravler.com/@${handle}`;

  const copyPublicUrl = () => {
    navigator.clipboard.writeText(publicUrl);
    toast.success('Public URL copied to clipboard!');
  };

  return (
    <DashboardLayout>
      <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight flex items-center gap-2">
              <FaMobileAlt className="text-indigo-600" /> Link-in-Bio Builder
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Create your branded mobile landing page for Instagram and TikTok with customizable links, colors, and live post grids.
            </p>
          </div>

          <div className="flex items-center gap-3">
            {handle && (
              <button
                onClick={copyPublicUrl}
                className="px-3.5 py-2 text-xs font-semibold bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 rounded-xl shadow-2xs flex items-center gap-1.5"
              >
                <FaCopy /> Copy Link (/@{handle})
              </button>
            )}
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-5 py-2 text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl shadow-xs transition-all active:scale-95 flex items-center gap-1.5 disabled:opacity-50"
            >
              <FaSave /> {saving ? 'Saving...' : 'Save & Publish'}
            </button>
          </div>
        </div>

        {/* Builder Layout: Split Left (Controls) and Right (Live Mobile Phone Frame) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Controls Panel */}
          <div className="lg:col-span-7 space-y-6">
            {/* General Profile Card */}
            <div className="bg-white border border-gray-200 rounded-3xl p-6 shadow-xs space-y-4">
              <h2 className="text-sm font-bold text-gray-900 uppercase tracking-wider">
                1. Profile & Handle
              </h2>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">Handle *</label>
                  <div className="flex items-center bg-gray-50 border border-gray-200 rounded-xl px-3 py-2 text-sm focus-within:ring-2 focus-within:ring-indigo-500">
                    <span className="text-gray-400 font-medium select-none">unravler.com/@</span>
                    <input
                      type="text"
                      value={handle}
                      onChange={(e) => setHandle(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))}
                      className="bg-transparent flex-1 outline-hidden text-gray-900 font-bold ml-0.5"
                      placeholder="yourbrand"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">Display Title *</label>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="Brand Name / Creator"
                    className="w-full px-3 py-2 text-sm border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Bio / Tagline</label>
                <textarea
                  rows={2}
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  placeholder="Welcome to my official links, updates, and featured posts!"
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Avatar Image URL (Optional)</label>
                <input
                  type="url"
                  value={avatarUrl}
                  onChange={(e) => setAvatarUrl(e.target.value)}
                  placeholder="https://.../avatar.jpg"
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
                />
              </div>
            </div>

            {/* Custom Link Buttons */}
            <div className="bg-white border border-gray-200 rounded-3xl p-6 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold text-gray-900 uppercase tracking-wider">
                  2. Custom Link Buttons ({customLinks.length})
                </h2>
                <button
                  onClick={handleAddLink}
                  className="inline-flex items-center gap-1 text-xs font-bold text-indigo-600 hover:text-indigo-700 bg-indigo-50 px-3 py-1.5 rounded-lg"
                >
                  <FaPlus className="text-[10px]" /> Add Link
                </button>
              </div>

              {customLinks.length === 0 ? (
                <p className="text-xs text-gray-400 text-center py-4">No custom links added yet. Click &ldquo;Add Link&rdquo; to begin.</p>
              ) : (
                <div className="space-y-3">
                  {customLinks.map((link) => (
                    <div
                      key={link.id}
                      className="p-4 border border-gray-100 bg-gray-50/70 rounded-2xl space-y-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <input
                          type="text"
                          value={link.title}
                          onChange={(e) => handleUpdateLink(link.id, 'title', e.target.value)}
                          placeholder="Button Title (e.g. Read Our Blog)"
                          className="flex-1 font-semibold text-xs text-gray-900 bg-white border border-gray-200 px-3 py-1.5 rounded-lg outline-hidden focus:ring-1 focus:ring-indigo-500"
                        />
                        <button
                          onClick={() => handleDeleteLink(link.id)}
                          className="text-gray-400 hover:text-red-600 p-1 rounded"
                        >
                          <FaTrash className="text-xs" />
                        </button>
                      </div>

                      <input
                        type="url"
                        value={link.url}
                        onChange={(e) => handleUpdateLink(link.id, 'url', e.target.value)}
                        placeholder="https://yourlink.com"
                        className="w-full text-xs text-gray-600 bg-white border border-gray-200 px-3 py-1.5 rounded-lg outline-hidden focus:ring-1 focus:ring-indigo-500"
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Visual Theme & Instagram Grid */}
            <div className="bg-white border border-gray-200 rounded-3xl p-6 shadow-xs space-y-4">
              <h2 className="text-sm font-bold text-gray-900 uppercase tracking-wider flex items-center gap-2">
                <FaPalette className="text-indigo-600" /> 3. Theme & Media Grid
              </h2>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">Background Color</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      value={theme.background_color}
                      onChange={(e) => setTheme({ ...theme, background_color: e.target.value })}
                      className="w-8 h-8 rounded-lg cursor-pointer border-0"
                    />
                    <span className="text-xs font-mono text-gray-600">{theme.background_color}</span>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">Button Color</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      value={theme.card_background}
                      onChange={(e) => setTheme({ ...theme, card_background: e.target.value })}
                      className="w-8 h-8 rounded-lg cursor-pointer border-0"
                    />
                    <span className="text-xs font-mono text-gray-600">{theme.card_background}</span>
                  </div>
                </div>
              </div>

              <div className="pt-2 border-t border-gray-100">
                <label className="flex items-center gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={autoSyncGrid}
                    onChange={(e) => setAutoSyncGrid(e.target.checked)}
                    className="w-4 h-4 text-indigo-600 rounded-md border-gray-300 focus:ring-indigo-500"
                  />
                  <span className="text-xs font-medium text-gray-800">
                    Auto-sync recent Instagram &amp; published post media thumbnails to grid
                  </span>
                </label>
              </div>
            </div>
          </div>

          {/* Live Mobile Phone Mockup Preview */}
          <div className="lg:col-span-5 flex justify-center sticky top-24">
            <div className="w-[320px] h-[640px] bg-slate-950 rounded-[48px] p-3 shadow-2xl ring-1 ring-slate-800/80 relative flex flex-col">
              {/* Phone Speaker Notch */}
              <div className="w-24 h-4 bg-slate-900 rounded-full mx-auto mb-2 shrink-0 flex items-center justify-center">
                <div className="w-3 h-3 bg-slate-950 rounded-full" />
              </div>

              {/* Live Preview Screen */}
              <div
                style={{ backgroundColor: theme.background_color, color: theme.text_color }}
                className="flex-1 rounded-[36px] overflow-y-auto p-5 space-y-4 no-scrollbar flex flex-col items-center text-center transition-colors duration-200"
              >
                {/* Avatar */}
                <div className="w-20 h-20 rounded-full bg-slate-800 border-2 border-white/20 overflow-hidden flex items-center justify-center shrink-0 shadow-sm">
                  {avatarUrl ? (
                    <img src={avatarUrl} alt="Avatar" className="w-full h-full object-cover" />
                  ) : (
                    <span className="text-xl font-bold uppercase">{title ? title[0] : 'U'}</span>
                  )}
                </div>

                <div>
                  <h3 className="text-base font-bold tracking-tight">{title || 'Your Brand'}</h3>
                  <p className="text-[11px] opacity-75 mt-0.5 max-w-[200px] leading-snug">{bio || 'Official bio & link hub'}</p>
                </div>

                {/* Custom Links */}
                <div className="w-full space-y-2.5 pt-2">
                  {customLinks.map((link) => (
                    <div
                      key={link.id}
                      style={{ backgroundColor: theme.card_background }}
                      className={`w-full py-3 px-4 ${theme.button_style} shadow-xs text-xs font-bold transition-transform active:scale-95 cursor-pointer flex items-center justify-center gap-2`}
                    >
                      <FaGlobe className="text-[11px] opacity-60" />
                      <span>{link.title || 'Untitled Link'}</span>
                    </div>
                  ))}
                </div>

                {/* Auto Grid Mockup placeholder */}
                {autoSyncGrid && (
                  <div className="w-full pt-3 border-t border-white/10">
                    <span className="text-[10px] font-bold uppercase tracking-wider opacity-60 mb-2 block">
                      Recent Posts
                    </span>
                    <div className="grid grid-cols-3 gap-1.5">
                      <div className="aspect-square bg-white/10 rounded-lg" />
                      <div className="aspect-square bg-white/10 rounded-lg" />
                      <div className="aspect-square bg-white/10 rounded-lg" />
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
