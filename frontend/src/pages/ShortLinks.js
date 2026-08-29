import React, { useState, useEffect } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import {
  createShortLink,
  getShortLinks,
  getShortLinkStats,
  deleteShortLink,
  getUTMPresets,
  saveUTMPreset,
  deleteUTMPreset,
} from '@/lib/api';
import { toast } from 'sonner';
import {
  FaLink,
  FaPlus,
  FaCopy,
  FaTrash,
  FaChartBar,
  FaExternalLinkAlt,
  FaTimes,
  FaTag,
  FaGlobe,
  FaMobileAlt,
  FaDesktop,
} from 'react-icons/fa';

export default function ShortLinks() {
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedStats, setSelectedStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [presets, setPresets] = useState([]);

  // Form state
  const [originalUrl, setOriginalUrl] = useState('');
  const [title, setTitle] = useState('');
  const [customSlug, setCustomSlug] = useState('');
  const [utmSource, setUtmSource] = useState('');
  const [utmMedium, setUtmMedium] = useState('social');
  const [utmCampaign, setUtmCampaign] = useState('');
  const [creating, setCreating] = useState(false);

  const fetchLinks = async () => {
    try {
      setLoading(true);
      const data = await getShortLinks();
      setLinks(data || []);
    } catch (err) {
      toast.error('Failed to load short links');
    } finally {
      setLoading(false);
    }
  };

  const fetchPresets = async () => {
    try {
      const p = await getUTMPresets();
      setPresets(p || []);
    } catch (err) {
      // Non-blocking
    }
  };

  useEffect(() => {
    fetchLinks();
    fetchPresets();
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!originalUrl) {
      toast.error('Please enter a target destination URL');
      return;
    }
    setCreating(true);
    try {
      const created = await createShortLink({
        original_url: originalUrl,
        title: title || undefined,
        custom_slug: customSlug || undefined,
        utm_source: utmSource || undefined,
        utm_medium: utmMedium || undefined,
        utm_campaign: utmCampaign || undefined,
      });
      toast.success('Short link generated successfully!');
      setShowCreateModal(false);
      setOriginalUrl('');
      setTitle('');
      setCustomSlug('');
      setUtmSource('');
      setUtmCampaign('');
      fetchLinks();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to create short link');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (code) => {
    if (!window.confirm('Delete this short link? Previous links will stop redirecting.')) return;
    try {
      await deleteShortLink(code);
      toast.success('Short link deleted');
      setLinks((prev) => prev.filter((l) => l.code !== code));
      if (selectedStats?.code === code) setSelectedStats(null);
    } catch (err) {
      toast.error('Failed to delete short link');
    }
  };

  const handleCopy = (url) => {
    navigator.clipboard.writeText(url);
    toast.success('Short link copied to clipboard!');
  };

  const handleViewStats = async (code) => {
    setStatsLoading(true);
    try {
      const stats = await getShortLinkStats(code);
      setSelectedStats(stats);
    } catch (err) {
      toast.error('Failed to load click analytics');
    } finally {
      setStatsLoading(false);
    }
  };

  const applyPreset = (p) => {
    setUtmSource(p.utm_source || '');
    setUtmMedium(p.utm_medium || '');
    setUtmCampaign(p.utm_campaign || '');
    toast.info(`Applied preset: ${p.name}`);
  };

  return (
    <DashboardLayout>
      <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight flex items-center gap-2">
              <FaLink className="text-indigo-600" /> Auto-UTM & Link Shortener
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Shorten links, automatically attach Google Analytics UTM campaign tags, and monitor real-time clicks.
            </p>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-all active:scale-95"
          >
            <FaPlus className="text-xs" /> Shorten New Link
          </button>
        </div>

        {/* Stats Preview Drawer if open */}
        {selectedStats && (
          <div className="bg-white border border-indigo-100 rounded-2xl p-6 shadow-sm relative">
            <button
              onClick={() => setSelectedStats(null)}
              className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 p-1.5 rounded-lg hover:bg-gray-100"
            >
              <FaTimes />
            </button>
            <div className="flex items-center gap-2 mb-4">
              <FaChartBar className="text-indigo-600" />
              <h2 className="text-lg font-bold text-gray-900">
                Click Performance: <span className="font-mono text-indigo-600">/r/{selectedStats.code}</span>
              </h2>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
              <div className="bg-indigo-50/50 rounded-xl p-4 border border-indigo-100/50">
                <span className="text-xs font-semibold text-indigo-700 uppercase tracking-wider">Total Clicks</span>
                <p className="text-3xl font-extrabold text-indigo-900 mt-1">{selectedStats.total_clicks}</p>
              </div>
              <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Top Referrer</span>
                <p className="text-xl font-bold text-gray-800 mt-1 capitalize truncate">
                  {Object.keys(selectedStats.referrers || {})[0] || 'Direct / Email'}
                </p>
              </div>
              <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Primary Device</span>
                <p className="text-xl font-bold text-gray-800 mt-1 capitalize">
                  {selectedStats.devices?.mobile > selectedStats.devices?.desktop ? 'Mobile' : 'Desktop'}
                </p>
              </div>
            </div>
            <div className="text-xs text-gray-500 truncate">
              <strong>Destination:</strong>{' '}
              <a href={selectedStats.final_url} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">
                {selectedStats.final_url}
              </a>
            </div>
          </div>
        )}

        {/* Links Table */}
        <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
          {loading ? (
            <div className="p-12 text-center text-gray-400">Loading your shortened links...</div>
          ) : links.length === 0 ? (
            <div className="p-12 text-center">
              <div className="w-12 h-12 bg-indigo-50 text-indigo-600 rounded-2xl flex items-center justify-center mx-auto mb-3">
                <FaLink className="text-xl" />
              </div>
              <h3 className="text-base font-semibold text-gray-900">No short links created yet</h3>
              <p className="text-sm text-gray-500 mt-1 max-w-sm mx-auto">
                Shorten your blog posts, product pages, or campaign URLs with automated UTM tracking tags.
              </p>
              <button
                onClick={() => setShowCreateModal(true)}
                className="mt-4 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg"
              >
                Create Your First Link
              </button>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {links.map((link) => (
                <div key={link.id} className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-gray-50/50 transition-colors">
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-gray-900 text-sm truncate">{link.title || 'Untitled Link'}</span>
                      {link.utm_params?.utm_campaign && (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-md">
                          <FaTag className="text-[9px]" /> {link.utm_params.utm_campaign}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="font-mono font-medium text-indigo-600">{link.short_url}</span>
                      <span className="text-gray-300">•</span>
                      <span className="text-gray-400 truncate max-w-md">{link.original_url}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    <div className="text-right">
                      <div className="text-sm font-bold text-gray-900">{link.clicks_count}</div>
                      <div className="text-[10px] text-gray-400 uppercase tracking-wider">Clicks</div>
                    </div>

                    <button
                      onClick={() => handleCopy(link.short_url)}
                      title="Copy short link"
                      className="p-2 text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                    >
                      <FaCopy className="text-sm" />
                    </button>

                    <button
                      onClick={() => handleViewStats(link.code)}
                      title="View Click Analytics"
                      className="p-2 text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                    >
                      <FaChartBar className="text-sm" />
                    </button>

                    <button
                      onClick={() => handleDelete(link.code)}
                      title="Delete link"
                      className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                    >
                      <FaTrash className="text-sm" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Create Modal */}
        {showCreateModal && (
          <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl border border-gray-100 animate-in fade-in zoom-in-95 duration-150">
              <div className="flex items-center justify-between mb-5">
                <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                  <FaLink className="text-indigo-600" /> Shorten Link & Build UTMs
                </h3>
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="text-gray-400 hover:text-gray-600 p-1 rounded-lg"
                >
                  <FaTimes />
                </button>
              </div>

              <form onSubmit={handleCreate} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                    Destination URL *
                  </label>
                  <input
                    type="url"
                    required
                    placeholder="https://yourbrand.com/new-product"
                    value={originalUrl}
                    onChange={(e) => setOriginalUrl(e.target.value)}
                    className="w-full px-3.5 py-2.5 text-sm border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-hidden"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                      Title (Optional)
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Summer Promo"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="w-full px-3.5 py-2.5 text-sm border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 outline-hidden"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                      Custom Slug (Optional)
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. summer26"
                      value={customSlug}
                      onChange={(e) => setCustomSlug(e.target.value)}
                      className="w-full px-3.5 py-2.5 text-sm border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 outline-hidden"
                    />
                  </div>
                </div>

                {/* UTM Controls */}
                <div className="bg-gray-50/70 p-4 rounded-xl border border-gray-100 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-gray-700 flex items-center gap-1.5">
                      <FaTag className="text-indigo-600 text-xs" /> Google Analytics UTM Tags
                    </span>
                    {presets.length > 0 && (
                      <div className="flex items-center gap-1">
                        {presets.map((p) => (
                          <button
                            key={p.id}
                            type="button"
                            onClick={() => applyPreset(p)}
                            className="text-[11px] bg-white border border-gray-200 px-2 py-0.5 rounded text-gray-600 hover:text-indigo-600"
                          >
                            {p.name}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="grid grid-cols-3 gap-2">
                    <div>
                      <label className="block text-[11px] font-medium text-gray-500 mb-0.5">utm_source</label>
                      <input
                        type="text"
                        placeholder="twitter / linkedin"
                        value={utmSource}
                        onChange={(e) => setUtmSource(e.target.value)}
                        className="w-full px-2.5 py-1.5 text-xs bg-white border border-gray-200 rounded-lg outline-hidden"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-gray-500 mb-0.5">utm_medium</label>
                      <input
                        type="text"
                        placeholder="social"
                        value={utmMedium}
                        onChange={(e) => setUtmMedium(e.target.value)}
                        className="w-full px-2.5 py-1.5 text-xs bg-white border border-gray-200 rounded-lg outline-hidden"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-gray-500 mb-0.5">utm_campaign</label>
                      <input
                        type="text"
                        placeholder="launch26"
                        value={utmCampaign}
                        onChange={(e) => setUtmCampaign(e.target.value)}
                        className="w-full px-2.5 py-1.5 text-xs bg-white border border-gray-200 rounded-lg outline-hidden"
                      />
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(false)}
                    className="px-4 py-2 text-xs font-semibold text-gray-600 hover:bg-gray-100 rounded-xl"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={creating}
                    className="px-5 py-2 text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl shadow-sm transition-all disabled:opacity-50"
                  >
                    {creating ? 'Shortening...' : 'Generate Short Link'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
