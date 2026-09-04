import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getCampaigns,
  createCampaign,
  updateCampaign,
  deleteCampaign,
  getCampaign,
} from '@/lib/api';
import { toast } from 'sonner';
import {
  FaBullhorn,
  FaPlus,
  FaSearch,
  FaCalendarAlt,
  FaDollarSign,
  FaEye,
  FaMousePointer,
  FaShareAlt,
  FaTrash,
  FaEdit,
  FaPen,
  FaLayerGroup,
  FaTimes,
} from 'react-icons/fa';
import {
  FaTwitter,
  FaLinkedin,
  FaFacebook,
  FaInstagram,
  FaYoutube,
  FaTiktok,
} from 'react-icons/fa';

const PLATFORM_ICONS = {
  twitter: { icon: FaTwitter, color: '#1DA1F2', label: 'Twitter' },
  linkedin: { icon: FaLinkedin, color: '#0A66C2', label: 'LinkedIn' },
  facebook: { icon: FaFacebook, color: '#1877F2', label: 'Facebook' },
  instagram: { icon: FaInstagram, color: '#E1306C', label: 'Instagram' },
  youtube: { icon: FaYoutube, color: '#FF0000', label: 'YouTube' },
  tiktok: { icon: FaTiktok, color: '#000000', label: 'TikTok' },
};

const COLOR_PRESETS = [
  '#6366f1', // Indigo
  '#3b82f6', // Blue
  '#06b6d4', // Cyan
  '#10b981', // Emerald
  '#f59e0b', // Amber
  '#ef4444', // Rose
  '#ec4899', // Pink
  '#8b5cf6', // Violet
];

export default function Campaigns() {
  const navigate = useNavigate();
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  
  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingCampaign, setEditingCampaign] = useState(null);
  const [saving, setSaving] = useState(false);

  // Detail drawer
  const [selectedCampaignDetail, setSelectedCampaignDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Form fields
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [color, setColor] = useState('#6366f1');
  const [status, setStatus] = useState('active');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [budget, setBudget] = useState('');
  const [targetPlatforms, setTargetPlatforms] = useState([]);
  const [tags, setTags] = useState('');

  const fetchCampaigns = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getCampaigns(statusFilter === 'all' ? null : statusFilter);
      setCampaigns(data || []);
    } catch (err) {
      toast.error('Failed to load campaigns');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchCampaigns();
  }, [fetchCampaigns]);

  const openCreateModal = () => {
    setEditingCampaign(null);
    setName('');
    setDescription('');
    setColor('#6366f1');
    setStatus('active');
    setStartDate('');
    setEndDate('');
    setBudget('');
    setTargetPlatforms(['twitter', 'linkedin']);
    setTags('');
    setIsModalOpen(true);
  };

  const openEditModal = (camp) => {
    setEditingCampaign(camp);
    setName(camp.name || '');
    setDescription(camp.description || '');
    setColor(camp.color || '#6366f1');
    setStatus(camp.status || 'active');
    setStartDate(camp.start_date ? camp.start_date.split('T')[0] : '');
    setEndDate(camp.end_date ? camp.end_date.split('T')[0] : '');
    setBudget(camp.budget !== null && camp.budget !== undefined ? camp.budget : '');
    setTargetPlatforms(camp.target_platforms || []);
    setTags((camp.tags || []).join(', '));
    setIsModalOpen(true);
  };

  const handleSaveCampaign = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      toast.error('Campaign name is required');
      return;
    }

    setSaving(true);
    const parsedTags = tags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const payload = {
      name: name.trim(),
      description: description.trim() || null,
      color,
      status,
      start_date: startDate ? new Date(startDate).toISOString() : null,
      end_date: endDate ? new Date(endDate).toISOString() : null,
      budget: budget ? parseFloat(budget) : null,
      target_platforms: targetPlatforms,
      tags: parsedTags,
    };

    try {
      if (editingCampaign) {
        await updateCampaign(editingCampaign.id, payload);
        toast.success('Campaign updated successfully');
      } else {
        await createCampaign(payload);
        toast.success('Campaign created successfully');
      }
      setIsModalOpen(false);
      fetchCampaigns();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to save campaign');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (campaignId, campaignName) => {
    if (!window.confirm(`Are you sure you want to delete "${campaignName}"? Posts will not be deleted, but will be unlinked.`)) {
      return;
    }
    try {
      await deleteCampaign(campaignId);
      toast.success('Campaign deleted');
      if (selectedCampaignDetail?.campaign?.id === campaignId) {
        setSelectedCampaignDetail(null);
      }
      fetchCampaigns();
    } catch (err) {
      toast.error('Failed to delete campaign');
    }
  };

  const viewCampaignDetail = async (camp) => {
    try {
      setLoadingDetail(true);
      const detail = await getCampaign(camp.id);
      setSelectedCampaignDetail(detail);
    } catch (err) {
      toast.error('Failed to fetch campaign details');
    } finally {
      setLoadingDetail(false);
    }
  };

  const togglePlatform = (p) => {
    setTargetPlatforms((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
    );
  };

  // Filtered campaigns
  const filteredCampaigns = useMemo(() => {
    return campaigns.filter((c) => {
      const q = searchQuery.toLowerCase();
      const matchesSearch =
        !q ||
        c.name.toLowerCase().includes(q) ||
        (c.description && c.description.toLowerCase().includes(q)) ||
        (c.tags && c.tags.some((t) => t.toLowerCase().includes(q)));
      return matchesSearch;
    });
  }, [campaigns, searchQuery]);

  // High-level aggregates
  const aggregateStats = useMemo(() => {
    let posts = 0;
    let clicks = 0;
    let impressions = 0;
    let engagements = 0;
    campaigns.forEach((c) => {
      posts += c.post_count || 0;
      clicks += c.total_clicks || 0;
      impressions += c.total_impressions || 0;
      engagements += c.total_engagements || 0;
    });
    return { posts, clicks, impressions, engagements };
  }, [campaigns]);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-zinc-950 p-6 md:p-8 space-y-6">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-indigo-600/10 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400">
              <FaBullhorn className="text-xl" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
                Campaigns Hub
              </h1>
              <p className="text-xs text-slate-500 dark:text-zinc-400 mt-0.5">
                Organize multi-channel launches, track UTM link clicks, and aggregate cross-platform ROI.
              </p>
            </div>
          </div>
        </div>

        <button
          onClick={openCreateModal}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-sm transition-all active:scale-95"
        >
          <FaPlus /> New Campaign
        </button>
      </div>

      {/* Aggregate Metrics Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-zinc-900 border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 dark:text-zinc-400 uppercase tracking-wider">
            <FaLayerGroup className="text-indigo-500" /> Total Campaigns
          </div>
          <div className="text-2xl font-black text-slate-900 dark:text-white mt-1">
            {campaigns.length}
          </div>
          <p className="text-[11px] text-slate-400 dark:text-zinc-500 mt-0.5">
            {campaigns.filter((c) => c.status === 'active').length} active now
          </p>
        </div>

        <div className="bg-white dark:bg-zinc-900 border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 dark:text-zinc-400 uppercase tracking-wider">
            <FaShareAlt className="text-blue-500" /> Linked Posts
          </div>
          <div className="text-2xl font-black text-slate-900 dark:text-white mt-1">
            {aggregateStats.posts}
          </div>
          <p className="text-[11px] text-slate-400 dark:text-zinc-500 mt-0.5">
            Cross-channel content
          </p>
        </div>

        <div className="bg-white dark:bg-zinc-900 border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 dark:text-zinc-400 uppercase tracking-wider">
            <FaMousePointer className="text-emerald-500" /> Tracked Clicks
          </div>
          <div className="text-2xl font-black text-slate-900 dark:text-white mt-1">
            {aggregateStats.clicks.toLocaleString()}
          </div>
          <p className="text-[11px] text-slate-400 dark:text-zinc-500 mt-0.5">
            Short link &amp; UTM attribution
          </p>
        </div>

        <div className="bg-white dark:bg-zinc-900 border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 dark:text-zinc-400 uppercase tracking-wider">
            <FaEye className="text-purple-500" /> Total Impressions
          </div>
          <div className="text-2xl font-black text-slate-900 dark:text-white mt-1">
            {aggregateStats.impressions.toLocaleString()}
          </div>
          <p className="text-[11px] text-slate-400 dark:text-zinc-500 mt-0.5">
            Reach across networks
          </p>
        </div>
      </div>

      {/* Filter & Search Toolbar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white dark:bg-zinc-900 border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-3 shadow-xs">
        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto">
          {['all', 'active', 'draft', 'completed', 'archived'].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold capitalize transition-colors ${
                statusFilter === st
                  ? 'bg-indigo-600 text-white shadow-xs'
                  : 'text-slate-600 dark:text-zinc-400 hover:bg-slate-100 dark:hover:bg-zinc-800'
              }`}
            >
              {st}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-64">
          <FaSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-slate-400" />
          <input
            type="text"
            placeholder="Search campaigns..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
          />
        </div>
      </div>

      {/* Campaigns Bento Grid */}
      {loading ? (
        <div className="py-20 text-center text-xs text-slate-400">Loading campaigns...</div>
      ) : filteredCampaigns.length === 0 ? (
        <div className="py-20 text-center bg-white dark:bg-zinc-900 border border-dashed border-slate-200 dark:border-zinc-800 rounded-3xl p-8">
          <FaBullhorn className="mx-auto text-3xl text-slate-300 dark:text-zinc-600 mb-3" />
          <h3 className="text-sm font-bold text-slate-800 dark:text-zinc-200">No campaigns found</h3>
          <p className="text-xs text-slate-500 dark:text-zinc-400 mt-1 max-w-sm mx-auto">
            {searchQuery
              ? 'No campaigns match your search query.'
              : 'Create your first marketing campaign to organize multi-platform posts and monitor analytics.'}
          </p>
          <button
            onClick={openCreateModal}
            className="mt-4 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-sm"
          >
            Create First Campaign
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredCampaigns.map((camp) => (
            <div
              key={camp.id}
              className="group relative bg-white dark:bg-zinc-900 border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-5 shadow-xs hover:shadow-md transition-all flex flex-col justify-between"
            >
              {/* Top Accent Strip */}
              <div
                className="absolute top-0 left-0 right-0 h-1.5 rounded-t-2xl"
                style={{ backgroundColor: camp.color || '#6366f1' }}
              />

              <div className="space-y-3">
                {/* Status + Actions */}
                <div className="flex items-center justify-between pt-1">
                  <span
                    className={`inline-flex items-center gap-1.5 text-[11px] font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wider ${
                      camp.status === 'active'
                        ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 border border-emerald-200/50'
                        : camp.status === 'draft'
                        ? 'bg-slate-100 text-slate-600 dark:bg-zinc-800 dark:text-zinc-300'
                        : 'bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400'
                    }`}
                  >
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        camp.status === 'active' ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'
                      }`}
                    />
                    {camp.status}
                  </span>

                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => navigate(`/create-post?campaign=${camp.id}`)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-slate-100 dark:hover:bg-zinc-800 text-xs"
                      title="Create Post for this Campaign"
                    >
                      <FaPen />
                    </button>
                    <button
                      onClick={() => openEditModal(camp)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-slate-100 dark:hover:bg-zinc-800 text-xs"
                      title="Edit Campaign"
                    >
                      <FaEdit />
                    </button>
                    <button
                      onClick={() => handleDelete(camp.id, camp.name)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-slate-100 dark:hover:bg-zinc-800 text-xs"
                      title="Delete Campaign"
                    >
                      <FaTrash />
                    </button>
                  </div>
                </div>

                {/* Title & Description */}
                <div>
                  <h3
                    onClick={() => viewCampaignDetail(camp)}
                    className="text-base font-bold text-slate-900 dark:text-white hover:text-indigo-600 dark:hover:text-indigo-400 cursor-pointer transition-colors"
                  >
                    {camp.name}
                  </h3>
                  {camp.description && (
                    <p className="text-xs text-slate-500 dark:text-zinc-400 mt-1 line-clamp-2">
                      {camp.description}
                    </p>
                  )}
                </div>

                {/* Date & Platforms */}
                <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500 dark:text-zinc-400 pt-1">
                  {(camp.start_date || camp.end_date) && (
                    <span className="flex items-center gap-1">
                      <FaCalendarAlt className="text-slate-400" />
                      {camp.start_date ? new Date(camp.start_date).toLocaleDateString() : 'Now'}
                      {' → '}
                      {camp.end_date ? new Date(camp.end_date).toLocaleDateString() : 'Ongoing'}
                    </span>
                  )}
                  {camp.budget !== null && camp.budget !== undefined && (
                    <span className="flex items-center gap-0.5 font-semibold text-slate-700 dark:text-zinc-200">
                      <FaDollarSign className="text-emerald-500" />
                      {camp.budget.toLocaleString()}
                    </span>
                  )}
                </div>

                {/* Target Platforms */}
                {camp.target_platforms && camp.target_platforms.length > 0 && (
                  <div className="flex items-center gap-1.5 pt-1">
                    {camp.target_platforms.map((p) => {
                      const iconConfig = PLATFORM_ICONS[p];
                      if (!iconConfig) return null;
                      const IconComp = iconConfig.icon;
                      return (
                        <span
                          key={p}
                          className="p-1.5 rounded-lg bg-slate-100 dark:bg-zinc-800"
                          style={{ color: iconConfig.color }}
                          title={iconConfig.label}
                        >
                          <IconComp className="text-xs" />
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Bento Metrics Bar */}
              <div className="mt-4 pt-3 border-t border-slate-100 dark:border-zinc-800 grid grid-cols-3 gap-2 text-center">
                <div className="bg-slate-50 dark:bg-zinc-800/50 rounded-xl py-1.5 px-2">
                  <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Posts</div>
                  <div className="text-xs font-bold text-slate-800 dark:text-white mt-0.5">{camp.post_count}</div>
                </div>
                <div className="bg-slate-50 dark:bg-zinc-800/50 rounded-xl py-1.5 px-2">
                  <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Clicks</div>
                  <div className="text-xs font-bold text-slate-800 dark:text-white mt-0.5">{camp.total_clicks}</div>
                </div>
                <div className="bg-slate-50 dark:bg-zinc-800/50 rounded-xl py-1.5 px-2">
                  <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Engage</div>
                  <div className="text-xs font-bold text-slate-800 dark:text-white mt-0.5">{camp.total_engagements}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create / Edit Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className="bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-3xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-zinc-800 pb-3">
              <h2 className="text-base font-bold text-slate-900 dark:text-white">
                {editingCampaign ? 'Edit Campaign' : 'Create New Campaign'}
              </h2>
              <button
                onClick={() => setIsModalOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-white"
              >
                <FaTimes />
              </button>
            </div>

            <form onSubmit={handleSaveCampaign} className="space-y-4 text-xs">
              <div>
                <label className="block font-bold text-slate-700 dark:text-zinc-300 uppercase tracking-wider mb-1">
                  Campaign Name *
                </label>
                <input
                  type="text"
                  placeholder="e.g. Q3 Product Launch or Black Friday 2026"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                  required
                />
              </div>

              <div>
                <label className="block font-bold text-slate-700 dark:text-zinc-300 uppercase tracking-wider mb-1">
                  Description
                </label>
                <textarea
                  rows={2}
                  placeholder="Goals, target audience, and key messaging..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-slate-700 dark:text-zinc-300 uppercase tracking-wider mb-1">
                    Start Date
                  </label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                  />
                </div>
                <div>
                  <label className="block font-bold text-slate-700 dark:text-zinc-300 uppercase tracking-wider mb-1">
                    End Date
                  </label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-slate-700 dark:text-zinc-300 uppercase tracking-wider mb-1">
                    Status
                  </label>
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                  >
                    <option value="active">Active</option>
                    <option value="draft">Draft</option>
                    <option value="completed">Completed</option>
                    <option value="archived">Archived</option>
                  </select>
                </div>
                <div>
                  <label className="block font-bold text-slate-700 dark:text-zinc-300 uppercase tracking-wider mb-1">
                    Budget ($)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    placeholder="e.g. 5000"
                    value={budget}
                    onChange={(e) => setBudget(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                  />
                </div>
              </div>

              {/* Color Presets */}
              <div>
                <label className="block font-bold text-slate-700 dark:text-zinc-300 uppercase tracking-wider mb-1.5">
                  Theme Accent
                </label>
                <div className="flex items-center gap-2">
                  {COLOR_PRESETS.map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setColor(c)}
                      className={`h-6 w-6 rounded-full transition-transform ${
                        color === c ? 'scale-125 ring-2 ring-offset-2 ring-indigo-500' : 'hover:scale-110'
                      }`}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                </div>
              </div>

              {/* Target Platforms */}
              <div>
                <label className="block font-bold text-slate-700 dark:text-zinc-300 uppercase tracking-wider mb-1.5">
                  Target Channels
                </label>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(PLATFORM_ICONS).map(([key, config]) => {
                    const isSelected = targetPlatforms.includes(key);
                    const IconComp = config.icon;
                    return (
                      <button
                        key={key}
                        type="button"
                        onClick={() => togglePlatform(key)}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all ${
                          isSelected
                            ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900 border-transparent shadow-xs'
                            : 'border-slate-200 dark:border-zinc-700 text-slate-600 dark:text-zinc-400 hover:bg-slate-50 dark:hover:bg-zinc-800'
                        }`}
                      >
                        <IconComp style={{ color: isSelected ? undefined : config.color }} />
                        {config.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="pt-3 border-t border-slate-100 dark:border-zinc-800 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-5 py-2 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-sm disabled:opacity-50"
                >
                  {saving ? 'Saving...' : editingCampaign ? 'Update Campaign' : 'Create Campaign'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Campaign Detail Drawer / Modal */}
      {selectedCampaignDetail && (
        <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/50 backdrop-blur-xs">
          <div className="bg-white dark:bg-zinc-900 border-l border-slate-200 dark:border-zinc-800 w-full max-w-md h-full p-6 shadow-2xl overflow-y-auto space-y-6">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-zinc-800 pb-3">
              <div className="flex items-center gap-2">
                <span
                  className="h-3 w-3 rounded-full"
                  style={{ backgroundColor: selectedCampaignDetail.campaign.color }}
                />
                <h2 className="text-base font-bold text-slate-900 dark:text-white">
                  {selectedCampaignDetail.campaign.name}
                </h2>
              </div>
              <button
                onClick={() => setSelectedCampaignDetail(null)}
                className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-white"
              >
                <FaTimes />
              </button>
            </div>

            {/* Campaign Summary */}
            <div className="bg-slate-50 dark:bg-zinc-800/60 rounded-2xl p-4 text-xs space-y-2">
              <div className="flex justify-between">
                <span className="text-slate-500 dark:text-zinc-400">Status:</span>
                <span className="font-bold capitalize text-slate-900 dark:text-white">
                  {selectedCampaignDetail.campaign.status}
                </span>
              </div>
              {selectedCampaignDetail.campaign.budget !== null && (
                <div className="flex justify-between">
                  <span className="text-slate-500 dark:text-zinc-400">Budget:</span>
                  <span className="font-bold text-slate-900 dark:text-white">
                    ${selectedCampaignDetail.campaign.budget?.toLocaleString()}
                  </span>
                </div>
              )}
              {selectedCampaignDetail.campaign.description && (
                <p className="text-slate-600 dark:text-zinc-300 pt-1 border-t border-slate-200/60 dark:border-zinc-700/60">
                  {selectedCampaignDetail.campaign.description}
                </p>
              )}
            </div>

            {/* Linked Posts */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-zinc-300">
                  Assigned Posts ({selectedCampaignDetail.posts.length})
                </h3>
                <button
                  onClick={() => navigate(`/create-post?campaign=${selectedCampaignDetail.campaign.id}`)}
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-xs transition-colors"
                >
                  <FaPen className="text-[10px]" />
                  New Post for Campaign
                </button>
              </div>
              {selectedCampaignDetail.posts.length === 0 ? (
                <div className="text-center py-8 text-xs text-slate-400 border border-dashed border-slate-200 dark:border-zinc-800 rounded-xl">
                  No posts linked to this campaign yet. Select this campaign when composing a new post!
                </div>
              ) : (
                <div className="space-y-2">
                  {selectedCampaignDetail.posts.map((post) => (
                    <div
                      key={post.id}
                      className="p-3 bg-white dark:bg-zinc-800/80 border border-slate-200 dark:border-zinc-700/80 rounded-xl text-xs space-y-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold capitalize text-indigo-600 dark:text-indigo-400">
                          {post.status}
                        </span>
                        <span className="text-[10px] text-slate-400">
                          {post.scheduled_time
                            ? new Date(post.scheduled_time).toLocaleString()
                            : new Date(post.created_at).toLocaleDateString()}
                        </span>
                      </div>
                      <p className="text-slate-800 dark:text-zinc-200 line-clamp-2">{post.content}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
