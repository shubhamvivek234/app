import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getCampaigns,
  createCampaign,
  updateCampaign,
  deleteCampaign,
  getCampaign,
  generateCampaignBlueprint,
  createShortLink,
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
  FaMagic,
  FaLink,
  FaCopy,
  FaCheck,
  FaDownload,
  FaExternalLinkAlt,
  FaClock,
  FaCheckCircle,
  FaRegClock,
  FaFileAlt,
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

// Helper to compute visual campaign timeline & pacing
const getCampaignTimeline = (camp) => {
  if (!camp.start_date && !camp.end_date) {
    return { label: 'Ongoing', percent: 100, daysLeft: null, isOverdue: false, text: 'Continuous Pace' };
  }
  const now = new Date();
  const start = camp.start_date ? new Date(camp.start_date) : new Date(camp.created_at);
  const end = camp.end_date ? new Date(camp.end_date) : null;

  if (!end) {
    return { label: 'Active', percent: 100, daysLeft: null, isOverdue: false, text: 'No end date set' };
  }

  const totalDays = Math.max(1, Math.ceil((end - start) / (1000 * 60 * 60 * 24)));
  const elapsedDays = Math.max(0, Math.ceil((now - start) / (1000 * 60 * 60 * 24)));
  const daysRemaining = Math.ceil((end - now) / (1000 * 60 * 60 * 24));
  const percent = Math.min(100, Math.max(0, Math.round((elapsedDays / totalDays) * 100)));

  if (daysRemaining < 0) {
    return {
      label: 'Ended',
      percent: 100,
      daysLeft: 0,
      isOverdue: true,
      text: `Concluded ${Math.abs(daysRemaining)}d ago`,
    };
  }

  return {
    label: `Day ${Math.min(elapsedDays, totalDays)} of ${totalDays}`,
    percent,
    daysLeft: daysRemaining,
    isOverdue: false,
    text: `${daysRemaining}d remaining (${percent}%)`,
  };
};

// Helper to export CSV performance reports
const exportCampaignCsv = (campaignDetail) => {
  const camp = campaignDetail.campaign || campaignDetail;
  const posts = campaignDetail.posts || [];
  const links = campaignDetail.short_links || [];
  const metrics = campaignDetail.metrics || {};

  const rows = [
    ['CAMPAIGN PERFORMANCE REPORT'],
    ['Generated At', new Date().toISOString()],
    ['Campaign Name', camp.name],
    ['Status', camp.status],
    ['Color', camp.color],
    ['Budget ($)', camp.budget || 0],
    ['Start Date', camp.start_date || 'N/A'],
    ['End Date', camp.end_date || 'N/A'],
    ['Target Platforms', (camp.target_platforms || []).join('; ')],
    ['Tags', (camp.tags || []).join('; ')],
    ['Total Posts', camp.post_count || posts.length],
    ['Total Impressions', metrics.total_impressions || camp.total_impressions || 0],
    ['Total Engagements', metrics.total_engagements || camp.total_engagements || 0],
    ['Total Clicks', metrics.total_clicks || camp.total_clicks || 0],
    ['Cost Per Click (CPC)', metrics.cpc || camp.cpc || 0],
    ['Cost Per Engagement (CPE)', metrics.cpe || camp.cpe || 0],
    [],
    ['POSTS BREAKDOWN'],
    ['Post ID', 'Status', 'Platforms', 'Scheduled/Created', 'Content'],
    ...posts.map((p) => [
      p.id,
      p.status,
      (p.platforms || []).join('; '),
      p.scheduled_time || p.created_at,
      `"${(p.content || '').replace(/"/g, '""')}"`,
    ]),
    [],
    ['TRACKED SHORT LINKS'],
    ['Code', 'Clicks', 'Original URL', 'Final URL'],
    ...links.map((l) => [
      l.code,
      l.clicks_count || l.clicks || 0,
      l.original_url,
      l.final_url,
    ]),
  ];

  const csvContent = 'data:text/csv;charset=utf-8,' + rows.map((e) => e.join(',')).join('\n');
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement('a');
  link.setAttribute('href', encodedUri);
  link.setAttribute('download', `${camp.name.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_report.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  toast.success('Campaign report exported as CSV');
};

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
  const [drawerPostFilter, setDrawerPostFilter] = useState('all');

  // UTM Short Link Builder state
  const [utmUrl, setUtmUrl] = useState('');
  const [utmSource, setUtmSource] = useState('twitter');
  const [utmMedium, setUtmMedium] = useState('social');
  const [creatingLink, setCreatingLink] = useState(false);
  const [copiedLink, setCopiedLink] = useState(null);

  // AI Content Blueprint Modal state
  const [blueprintModalOpen, setBlueprintModalOpen] = useState(false);
  const [blueprintCampaign, setBlueprintCampaign] = useState(null);
  const [blueprintPosts, setBlueprintPosts] = useState([]);
  const [generatingBlueprint, setGeneratingBlueprint] = useState(false);
  const [blueprintFocus, setBlueprintFocus] = useState('');

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
      setDrawerPostFilter('all');
      setUtmUrl('');
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

  // UTM Link Builder Handlers
  const generatedUtmPreview = useMemo(() => {
    if (!utmUrl || !selectedCampaignDetail?.campaign) return '';
    try {
      const u = new URL(utmUrl.startsWith('http') ? utmUrl : `https://${utmUrl}`);
      u.searchParams.set('utm_source', utmSource);
      u.searchParams.set('utm_medium', utmMedium);
      u.searchParams.set('utm_campaign', selectedCampaignDetail.campaign.name);
      return u.toString();
    } catch {
      return '';
    }
  }, [utmUrl, utmSource, utmMedium, selectedCampaignDetail]);

  const handleCreateShortLink = async (e) => {
    e.preventDefault();
    if (!utmUrl.trim() || !selectedCampaignDetail?.campaign) return;
    try {
      setCreatingLink(true);
      await createShortLink({
        original_url: utmUrl.trim(),
        campaign_id: selectedCampaignDetail.campaign.id,
        utm_campaign: selectedCampaignDetail.campaign.name,
        utm_source: utmSource,
        utm_medium: utmMedium,
      });
      toast.success('Short link generated and tagged to campaign!');
      setUtmUrl('');
      // Reload detail
      const updated = await getCampaign(selectedCampaignDetail.campaign.id);
      setSelectedCampaignDetail(updated);
      fetchCampaigns();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to create short link');
    } finally {
      setCreatingLink(false);
    }
  };

  const handleCopyLink = (text, key) => {
    navigator.clipboard.writeText(text);
    setCopiedLink(key);
    toast.success('Link copied to clipboard!');
    setTimeout(() => setCopiedLink(null), 2000);
  };

  // AI Content Blueprint Handlers
  const handleOpenBlueprint = (camp) => {
    setBlueprintCampaign(camp);
    setBlueprintPosts([]);
    setBlueprintFocus('');
    setBlueprintModalOpen(true);
    handleGenerateBlueprint(camp);
  };

  const handleGenerateBlueprint = async (camp) => {
    const target = camp || blueprintCampaign;
    if (!target) return;
    try {
      setGeneratingBlueprint(true);
      const res = await generateCampaignBlueprint(target.id, {
        custom_prompt: blueprintFocus.trim() || undefined,
      });
      setBlueprintPosts(res.posts || []);
      toast.success(`Generated 5-stage blueprint via ${res.provider}`);
    } catch (err) {
      toast.error('Failed to generate blueprint. Please try again.');
    } finally {
      setGeneratingBlueprint(false);
    }
  };

  const handleSendToComposer = (content, camp) => {
    setBlueprintModalOpen(false);
    setSelectedCampaignDetail(null);
    navigate('/create-post', {
      state: {
        initialContent: content,
        campaignId: camp?.id,
      },
    });
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

  // Drawer filtered posts
  const drawerFilteredPosts = useMemo(() => {
    if (!selectedCampaignDetail?.posts) return [];
    if (drawerPostFilter === 'all') return selectedCampaignDetail.posts;
    return selectedCampaignDetail.posts.filter((p) => p.status === drawerPostFilter);
  }, [selectedCampaignDetail, drawerPostFilter]);

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
                Organize multi-channel launches, track UTM links, generate AI blueprints, and monitor cross-platform ROI.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate('/calendar')}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold text-slate-700 dark:text-zinc-200 bg-white dark:bg-zinc-800 border border-slate-200 dark:border-zinc-700 hover:bg-slate-50 dark:hover:bg-zinc-700 shadow-2xs transition-all active:scale-95"
          >
            <FaCalendarAlt className="text-indigo-500" /> Master Calendar
          </button>

          <button
            onClick={openCreateModal}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-sm transition-all active:scale-95"
          >
            <FaPlus /> New Campaign
          </button>
        </div>
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
          {filteredCampaigns.map((camp) => {
            const timeline = getCampaignTimeline(camp);
            return (
              <div
                key={camp.id}
                className="group relative bg-white dark:bg-zinc-900 border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-5 shadow-xs hover:shadow-md transition-all flex flex-col justify-between space-y-4"
              >
                {/* Top Accent Strip */}
                <div
                  className="absolute top-0 left-0 right-0 h-1.5 rounded-t-2xl"
                  style={{ backgroundColor: camp.color || '#6366f1' }}
                />

                <div className="space-y-3 pt-1">
                  {/* Status + Action Shortcuts */}
                  <div className="flex items-center justify-between">
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
                        onClick={() => handleOpenBlueprint(camp)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-amber-500 hover:bg-slate-100 dark:hover:bg-zinc-800 text-xs transition-colors"
                        title="✨ AI Campaign Blueprint"
                      >
                        <FaMagic />
                      </button>
                      <button
                        onClick={() => navigate(`/calendar?campaign=${camp.id}`)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-slate-100 dark:hover:bg-zinc-800 text-xs transition-colors"
                        title="View in Master Calendar"
                      >
                        <FaCalendarAlt />
                      </button>
                      <button
                        onClick={() => navigate(`/create-post?campaign=${camp.id}`)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-slate-100 dark:hover:bg-zinc-800 text-xs transition-colors"
                        title="Compose Post for Campaign"
                      >
                        <FaPen />
                      </button>
                      <button
                        onClick={() => openEditModal(camp)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-slate-100 dark:hover:bg-zinc-800 text-xs transition-colors"
                        title="Edit Campaign"
                      >
                        <FaEdit />
                      </button>
                      <button
                        onClick={() => handleDelete(camp.id, camp.name)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-slate-100 dark:hover:bg-zinc-800 text-xs transition-colors"
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

                  {/* Visual Campaign Timeline Bar */}
                  <div className="space-y-1.5 pt-1">
                    <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500 dark:text-zinc-400">
                      <span className="flex items-center gap-1">
                        <FaClock className="text-[10px] text-slate-400" />
                        {timeline.label}
                      </span>
                      <span className="text-[10px] font-mono text-slate-400">
                        {timeline.text}
                      </span>
                    </div>
                    <div className="w-full bg-slate-100 dark:bg-zinc-800 h-1.5 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${timeline.percent}%`,
                          backgroundColor: camp.color || '#6366f1',
                        }}
                      />
                    </div>
                  </div>

                  {/* Post Status Delivery Breakdown Pills */}
                  <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-medium text-slate-500 dark:text-zinc-400 pt-0.5">
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-400">
                      <FaCheckCircle className="text-[9px]" /> {camp.published_count || 0} Pub
                    </span>
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-indigo-50 dark:bg-indigo-950/30 text-indigo-700 dark:text-indigo-400">
                      <FaRegClock className="text-[9px]" /> {camp.scheduled_count || 0} Sched
                    </span>
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-100 dark:bg-zinc-800 text-slate-600 dark:text-zinc-300">
                      <FaFileAlt className="text-[9px]" /> {camp.draft_count || 0} Draft
                    </span>

                    {/* Budget & ROI Pills */}
                    {camp.budget && (
                      <span className="ml-auto inline-flex items-center gap-0.5 px-2 py-0.5 rounded-md bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400 font-bold font-mono">
                        ${camp.budget.toLocaleString()}
                        {camp.cpc > 0 && <span className="text-[9px] opacity-80 ml-1">(${camp.cpc} CPC)</span>}
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
                <div className="pt-3 border-t border-slate-100 dark:border-zinc-800 grid grid-cols-3 gap-2 text-center">
                  <div
                    onClick={() => viewCampaignDetail(camp)}
                    className="bg-slate-50 dark:bg-zinc-800/50 hover:bg-slate-100 dark:hover:bg-zinc-800 rounded-xl py-1.5 px-2 cursor-pointer transition-colors"
                  >
                    <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Posts</div>
                    <div className="text-xs font-bold text-slate-800 dark:text-white mt-0.5">{camp.post_count}</div>
                  </div>
                  <div
                    onClick={() => viewCampaignDetail(camp)}
                    className="bg-slate-50 dark:bg-zinc-800/50 hover:bg-slate-100 dark:hover:bg-zinc-800 rounded-xl py-1.5 px-2 cursor-pointer transition-colors"
                  >
                    <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Clicks</div>
                    <div className="text-xs font-bold text-slate-800 dark:text-white mt-0.5">{camp.total_clicks}</div>
                  </div>
                  <div
                    onClick={() => viewCampaignDetail(camp)}
                    className="bg-slate-50 dark:bg-zinc-800/50 hover:bg-slate-100 dark:hover:bg-zinc-800 rounded-xl py-1.5 px-2 cursor-pointer transition-colors"
                  >
                    <div className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Engage</div>
                    <div className="text-xs font-bold text-slate-800 dark:text-white mt-0.5">{camp.total_engagements}</div>
                  </div>
                </div>
              </div>
            );
          })}
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

      {/* Campaign Detail Drawer */}
      {selectedCampaignDetail && (
        <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/60 backdrop-blur-xs">
          <div className="bg-white dark:bg-zinc-900 border-l border-slate-200 dark:border-zinc-800 w-full max-w-2xl h-full p-6 sm:p-8 shadow-2xl overflow-y-auto space-y-6">
            {/* Header */}
            <div className="flex items-start justify-between border-b border-slate-100 dark:border-zinc-800 pb-4">
              <div className="flex items-center gap-3">
                <span
                  className="h-4 w-4 rounded-full ring-2 ring-offset-2 ring-slate-200 dark:ring-zinc-800 shrink-0"
                  style={{ backgroundColor: selectedCampaignDetail.campaign.color }}
                />
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                      {selectedCampaignDetail.campaign.name}
                    </h2>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                        selectedCampaignDetail.campaign.status === 'active'
                          ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400'
                          : selectedCampaignDetail.campaign.status === 'completed'
                          ? 'bg-blue-100 dark:bg-blue-950/60 text-blue-700 dark:text-blue-400'
                          : selectedCampaignDetail.campaign.status === 'draft'
                          ? 'bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400'
                          : 'bg-slate-100 dark:bg-zinc-800 text-slate-600 dark:text-zinc-400'
                      }`}
                    >
                      {selectedCampaignDetail.campaign.status}
                    </span>
                  </div>
                  {selectedCampaignDetail.campaign.description && (
                    <p className="text-xs text-slate-500 dark:text-zinc-400 mt-1 line-clamp-2">
                      {selectedCampaignDetail.campaign.description}
                    </p>
                  )}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-1.5 shrink-0 ml-4">
                <button
                  onClick={() => navigate(`/calendar?campaign=${selectedCampaignDetail.campaign.id}`)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 hover:bg-slate-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-slate-700 dark:text-zinc-200 transition-colors"
                  title="View in Master Calendar"
                >
                  <FaCalendarAlt className="text-indigo-500" />
                  <span className="hidden sm:inline">Calendar</span>
                </button>
                <button
                  onClick={() => handleOpenBlueprint(selectedCampaignDetail.campaign)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-semibold bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-950/50 dark:hover:bg-indigo-900/50 text-indigo-600 dark:text-indigo-400 transition-colors border border-indigo-200/60 dark:border-indigo-800/60"
                  title="Generate AI Content Blueprint"
                >
                  <FaMagic className="text-indigo-500" />
                  <span className="hidden sm:inline">AI Blueprint</span>
                </button>
                <button
                  onClick={() => exportCampaignCsv(selectedCampaignDetail)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 hover:bg-slate-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-slate-700 dark:text-zinc-200 transition-colors"
                  title="Export Performance CSV"
                >
                  <FaDownload className="text-emerald-500" />
                  <span className="hidden sm:inline">Export</span>
                </button>
                <button
                  onClick={() => setSelectedCampaignDetail(null)}
                  className="p-2 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors"
                >
                  <FaTimes />
                </button>
              </div>
            </div>

            {/* Campaign Pacing & Timeline Progress */}
            {(() => {
              const timeline = getCampaignTimeline(selectedCampaignDetail.campaign);
              return (
                <div className="bg-slate-50 dark:bg-zinc-800/50 border border-slate-200/70 dark:border-zinc-700/70 rounded-2xl p-4 space-y-2.5">
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <FaClock className="text-slate-400 dark:text-zinc-400 text-xs" />
                      <span className="font-semibold text-slate-800 dark:text-zinc-200">
                        {timeline.label}
                      </span>
                    </div>
                    <span className={`text-[11px] font-bold ${
                      timeline.isOverdue ? 'text-rose-500' : 'text-slate-500 dark:text-zinc-400'
                    }`}>
                      {timeline.text}
                    </span>
                  </div>

                  {/* Dual-Track Pacing Progress Bar */}
                  <div className="w-full bg-slate-200 dark:bg-zinc-700 rounded-full h-2.5 overflow-hidden">
                    <div
                      className="h-2.5 rounded-full transition-all duration-500"
                      style={{
                        width: `${timeline.percent}%`,
                        backgroundColor: selectedCampaignDetail.campaign.color || '#6366f1',
                      }}
                    />
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-slate-500 dark:text-zinc-400 pt-1">
                    <span>
                      Start: {selectedCampaignDetail.campaign.start_date ? new Date(selectedCampaignDetail.campaign.start_date).toLocaleDateString() : 'Immediate'}
                    </span>
                    <span>
                      End: {selectedCampaignDetail.campaign.end_date ? new Date(selectedCampaignDetail.campaign.end_date).toLocaleDateString() : 'Open Ended'}
                    </span>
                  </div>
                </div>
              );
            })()}

            {/* Performance Metrics Bento */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-slate-50 dark:bg-zinc-800/60 border border-slate-100 dark:border-zinc-800 p-3.5 rounded-2xl">
                <div className="flex items-center gap-1.5 text-slate-500 dark:text-zinc-400 text-xs font-semibold mb-1">
                  <FaEye className="text-xs text-blue-500" />
                  <span>Impressions</span>
                </div>
                <div className="text-lg font-bold text-slate-900 dark:text-white">
                  {(selectedCampaignDetail.metrics?.total_impressions || 0).toLocaleString()}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  ER: {selectedCampaignDetail.metrics?.engagement_rate || 0}%
                </div>
              </div>

              <div className="bg-slate-50 dark:bg-zinc-800/60 border border-slate-100 dark:border-zinc-800 p-3.5 rounded-2xl">
                <div className="flex items-center gap-1.5 text-slate-500 dark:text-zinc-400 text-xs font-semibold mb-1">
                  <FaShareAlt className="text-xs text-indigo-500" />
                  <span>Engagements</span>
                </div>
                <div className="text-lg font-bold text-slate-900 dark:text-white">
                  {(selectedCampaignDetail.metrics?.total_engagements || 0).toLocaleString()}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  {selectedCampaignDetail.campaign.budget && selectedCampaignDetail.metrics?.cpe
                    ? `$${selectedCampaignDetail.metrics.cpe} CPE`
                    : 'Organic'}
                </div>
              </div>

              <div className="bg-slate-50 dark:bg-zinc-800/60 border border-slate-100 dark:border-zinc-800 p-3.5 rounded-2xl">
                <div className="flex items-center gap-1.5 text-slate-500 dark:text-zinc-400 text-xs font-semibold mb-1">
                  <FaMousePointer className="text-xs text-amber-500" />
                  <span>Link Clicks</span>
                </div>
                <div className="text-lg font-bold text-slate-900 dark:text-white">
                  {(selectedCampaignDetail.metrics?.total_clicks || 0).toLocaleString()}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  {selectedCampaignDetail.campaign.budget && selectedCampaignDetail.metrics?.cpc
                    ? `$${selectedCampaignDetail.metrics.cpc} CPC`
                    : 'Tracked'}
                </div>
              </div>

              <div className="bg-slate-50 dark:bg-zinc-800/60 border border-slate-100 dark:border-zinc-800 p-3.5 rounded-2xl">
                <div className="flex items-center gap-1.5 text-slate-500 dark:text-zinc-400 text-xs font-semibold mb-1">
                  <FaDollarSign className="text-xs text-emerald-500" />
                  <span>Budget</span>
                </div>
                <div className="text-lg font-bold text-slate-900 dark:text-white">
                  {selectedCampaignDetail.campaign.budget !== null && selectedCampaignDetail.campaign.budget !== undefined
                    ? `$${Number(selectedCampaignDetail.campaign.budget).toLocaleString()}`
                    : 'None'}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5">
                  Allocated
                </div>
              </div>
            </div>

            {/* Target Channels & Platform Breakdown */}
            {selectedCampaignDetail.campaign.target_platforms?.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-zinc-400">
                  Target Channels & Distribution
                </h4>
                <div className="flex flex-wrap gap-2">
                  {selectedCampaignDetail.campaign.target_platforms.map((p) => {
                    const iconConfig = PLATFORM_ICONS[p] || { icon: FaBullhorn, color: '#6366f1', label: p };
                    const IconComp = iconConfig.icon;
                    const postCountOnPlatform = selectedCampaignDetail.platform_breakdown?.[p] || 0;
                    return (
                      <div
                        key={p}
                        className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50 dark:bg-zinc-800/70 border border-slate-200/80 dark:border-zinc-700 text-xs font-medium text-slate-700 dark:text-zinc-300"
                      >
                        <IconComp style={{ color: iconConfig.color }} />
                        <span>{iconConfig.label}</span>
                        <span className="px-1.5 py-0.5 rounded-md bg-slate-200/80 dark:bg-zinc-700 text-[10px] font-bold text-slate-600 dark:text-zinc-300">
                          {postCountOnPlatform} posts
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Campaign UTM & Short Link Generator */}
            <div className="bg-slate-50/80 dark:bg-zinc-800/40 border border-slate-200/80 dark:border-zinc-700/80 rounded-2xl p-4 sm:p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-lg bg-indigo-100 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
                    <FaLink className="text-xs" />
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider">
                      UTM & Short Link Generator
                    </h3>
                    <p className="text-[11px] text-slate-500 dark:text-zinc-400">
                      Track clicks and conversion attribution directly linked to this campaign.
                    </p>
                  </div>
                </div>
              </div>

              <form onSubmit={handleCreateShortLink} className="space-y-3">
                <div>
                  <label className="block text-[11px] font-bold text-slate-700 dark:text-zinc-300 uppercase tracking-wider mb-1">
                    Destination URL *
                  </label>
                  <input
                    type="url"
                    placeholder="https://yourbrand.com/landing-page"
                    value={utmUrl}
                    onChange={(e) => setUtmUrl(e.target.value)}
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                    required
                  />
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 dark:text-zinc-300 uppercase tracking-wider mb-1">
                      UTM Source
                    </label>
                    <select
                      value={utmSource}
                      onChange={(e) => setUtmSource(e.target.value)}
                      className="w-full px-2.5 py-1.5 rounded-xl border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                    >
                      <option value="twitter">Twitter / X</option>
                      <option value="linkedin">LinkedIn</option>
                      <option value="facebook">Facebook</option>
                      <option value="instagram">Instagram</option>
                      <option value="youtube">YouTube</option>
                      <option value="tiktok">TikTok</option>
                      <option value="newsletter">Newsletter</option>
                      <option value="direct">Direct / Link in Bio</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 dark:text-zinc-300 uppercase tracking-wider mb-1">
                      UTM Medium
                    </label>
                    <select
                      value={utmMedium}
                      onChange={(e) => setUtmMedium(e.target.value)}
                      className="w-full px-2.5 py-1.5 rounded-xl border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
                    >
                      <option value="social">Social (organic)</option>
                      <option value="cpc">CPC / Paid Ad</option>
                      <option value="email">Email</option>
                      <option value="bio">Bio Link</option>
                      <option value="referral">Referral</option>
                    </select>
                  </div>
                </div>

                {generatedUtmPreview && (
                  <div className="p-2.5 rounded-xl bg-indigo-50/60 dark:bg-indigo-950/30 border border-indigo-100 dark:border-indigo-900/50 text-[11px] font-mono break-all text-indigo-700 dark:text-indigo-300">
                    <span className="font-bold text-slate-600 dark:text-zinc-400 not-font-mono text-[10px] uppercase block mb-0.5">
                      Preview with UTM Tagging:
                    </span>
                    {generatedUtmPreview}
                  </div>
                )}

                <div className="flex justify-end">
                  <button
                    type="submit"
                    disabled={creatingLink || !utmUrl.trim()}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-sm disabled:opacity-50 transition-colors"
                  >
                    <FaLink className="text-[11px]" />
                    {creatingLink ? 'Creating Short Link...' : 'Shorten & Track Link'}
                  </button>
                </div>
              </form>

              {/* Active Short Links List */}
              {selectedCampaignDetail.short_links?.length > 0 && (
                <div className="pt-3 border-t border-slate-200 dark:border-zinc-700/60 space-y-2">
                  <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-600 dark:text-zinc-400">
                    Tracked Links ({selectedCampaignDetail.short_links.length})
                  </h4>
                  <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                    {selectedCampaignDetail.short_links.map((link) => {
                      const shortHref = `${window.location.origin}/r/${link.code}`;
                      return (
                        <div
                          key={link.code}
                          className="flex items-center justify-between p-2.5 bg-white dark:bg-zinc-900 border border-slate-200/80 dark:border-zinc-700 rounded-xl text-xs"
                        >
                          <div className="min-w-0 pr-3">
                            <div className="flex items-center gap-2">
                              <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400">
                                /r/{link.code}
                              </span>
                              <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400">
                                {link.clicks_count || link.clicks || 0} clicks
                              </span>
                              {link.utm_source && (
                                <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-100 dark:bg-zinc-800 text-slate-600 dark:text-zinc-400">
                                  {link.utm_source}
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-slate-400 truncate mt-0.5">
                              {link.original_url}
                            </p>
                          </div>

                          <div className="flex items-center gap-1 shrink-0">
                            <button
                              type="button"
                              onClick={() => handleCopyLink(shortHref, link.code)}
                              className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 dark:text-zinc-400 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors"
                              title="Copy Short Link"
                            >
                              {copiedLink === link.code ? (
                                <FaCheck className="text-emerald-500 text-xs" />
                              ) : (
                                <FaCopy className="text-xs" />
                              )}
                            </button>
                            <a
                              href={shortHref}
                              target="_blank"
                              rel="noreferrer"
                              className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 dark:text-zinc-400 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors"
                              title="Test Link"
                            >
                              <FaExternalLinkAlt className="text-[10px]" />
                            </a>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* Linked Posts Section with Filter Tabs */}
            <div className="space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-zinc-200">
                    Assigned Posts ({selectedCampaignDetail.posts.length})
                  </h3>
                </div>
                <button
                  onClick={() => navigate(`/create-post?campaign=${selectedCampaignDetail.campaign.id}`)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-xs transition-colors self-start sm:self-auto"
                >
                  <FaPen className="text-[10px]" />
                  New Post for Campaign
                </button>
              </div>

              {/* Status Filter Tabs */}
              <div className="flex items-center gap-1.5 border-b border-slate-100 dark:border-zinc-800 pb-2 text-xs">
                {[
                  { key: 'all', label: `All (${selectedCampaignDetail.posts.length})` },
                  { key: 'published', label: `Published (${selectedCampaignDetail.status_breakdown?.published || 0})` },
                  { key: 'scheduled', label: `Scheduled (${selectedCampaignDetail.status_breakdown?.scheduled || 0})` },
                  { key: 'draft', label: `Drafts (${selectedCampaignDetail.status_breakdown?.draft || 0})` },
                ].map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => setDrawerPostFilter(tab.key)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                      drawerPostFilter === tab.key
                        ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900 shadow-xs'
                        : 'text-slate-600 dark:text-zinc-400 hover:bg-slate-100 dark:hover:bg-zinc-800'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {drawerFilteredPosts.length === 0 ? (
                <div className="text-center py-8 text-xs text-slate-400 border border-dashed border-slate-200 dark:border-zinc-800 rounded-2xl space-y-2">
                  <FaBullhorn className="mx-auto text-xl opacity-40 text-indigo-500" />
                  <p>No posts match this filter.</p>
                  <button
                    onClick={() => navigate(`/create-post?campaign=${selectedCampaignDetail.campaign.id}`)}
                    className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline"
                  >
                    Compose a new post for this campaign
                  </button>
                </div>
              ) : (
                <div className="space-y-2.5 max-h-80 overflow-y-auto pr-1">
                  {drawerFilteredPosts.map((post) => {
                    const statusColor =
                      post.status === 'published'
                        ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400'
                        : post.status === 'scheduled'
                        ? 'bg-blue-100 dark:bg-blue-950/60 text-blue-700 dark:text-blue-400'
                        : 'bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400';

                    return (
                      <div
                        key={post.id}
                        className="p-3.5 bg-slate-50/60 dark:bg-zinc-800/60 border border-slate-200/70 dark:border-zinc-700/60 rounded-2xl text-xs space-y-2 hover:border-indigo-300 dark:hover:border-indigo-700 transition-colors"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${statusColor}`}>
                              {post.status}
                            </span>
                            {post.platforms?.map((p) => {
                              const iconConfig = PLATFORM_ICONS[p];
                              if (!iconConfig) return null;
                              const IconComp = iconConfig.icon;
                              return (
                                <span key={p} style={{ color: iconConfig.color }} title={iconConfig.label}>
                                  <IconComp className="text-xs" />
                                </span>
                              );
                            })}
                          </div>
                          <span className="text-[11px] text-slate-400 flex items-center gap-1">
                            <FaClock className="text-[10px]" />
                            {post.scheduled_time
                              ? new Date(post.scheduled_time).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
                              : new Date(post.created_at).toLocaleDateString()}
                          </span>
                        </div>
                        <p className="text-slate-800 dark:text-zinc-200 line-clamp-3 leading-relaxed">
                          {post.content}
                        </p>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* AI Campaign Content Blueprint Modal */}
      {blueprintModalOpen && blueprintCampaign && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className="bg-white dark:bg-zinc-900 border border-slate-200 dark:border-zinc-800 rounded-3xl max-w-2xl w-full max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="p-5 border-b border-slate-100 dark:border-zinc-800 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-2xl bg-indigo-600/10 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400">
                  <FaMagic className="text-lg" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    AI Campaign Content Blueprint
                    <span
                      className="px-2 py-0.5 rounded-full text-[11px] font-semibold text-white"
                      style={{ backgroundColor: blueprintCampaign.color || '#6366f1' }}
                    >
                      {blueprintCampaign.name}
                    </span>
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-zinc-400">
                    A multi-stage sequential storytelling narrative engineered for maximum reach and conversions.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setBlueprintModalOpen(false)}
                className="p-1.5 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-white"
              >
                <FaTimes />
              </button>
            </div>

            {/* Custom Guidance Prompt Bar */}
            <div className="p-4 bg-slate-50 dark:bg-zinc-800/50 border-b border-slate-100 dark:border-zinc-800 flex flex-col sm:flex-row gap-2">
              <input
                type="text"
                placeholder="Optional focus: e.g. Emphasize limited-time coupon or customer testimonial..."
                value={blueprintFocus}
                onChange={(e) => setBlueprintFocus(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleGenerateBlueprint(blueprintCampaign);
                }}
                className="flex-1 px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white"
              />
              <button
                type="button"
                disabled={generatingBlueprint}
                onClick={() => handleGenerateBlueprint(blueprintCampaign)}
                className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-sm disabled:opacity-50 transition-colors shrink-0"
              >
                <FaMagic className="text-xs" />
                {generatingBlueprint ? 'Generating...' : 'Regenerate'}
              </button>
            </div>

            {/* Blueprint Stages Content Area */}
            <div className="p-5 overflow-y-auto space-y-4 flex-1">
              {generatingBlueprint ? (
                <div className="text-center py-16 space-y-3">
                  <div className="inline-block animate-spin text-2xl text-indigo-600">
                    <FaMagic />
                  </div>
                  <p className="text-xs font-semibold text-slate-700 dark:text-zinc-300">
                    Designing your 5-stage campaign narrative...
                  </p>
                  <p className="text-[11px] text-slate-400">
                    Crafting hooks, story arc, hashtags, and CTAs across your target platforms.
                  </p>
                </div>
              ) : blueprintPosts.length === 0 ? (
                <div className="text-center py-12 text-xs text-slate-400">
                  No blueprint generated yet. Click Regenerate to generate your campaign strategy!
                </div>
              ) : (
                blueprintPosts.map((post, idx) => (
                  <div
                    key={idx}
                    className="p-4 rounded-2xl border border-slate-200 dark:border-zinc-800 bg-slate-50/50 dark:bg-zinc-800/40 space-y-3 hover:border-indigo-300 dark:hover:border-indigo-700 transition-colors"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-100 dark:bg-indigo-950/80 text-indigo-700 dark:text-indigo-300">
                          {post.stage}
                        </span>
                        <span className="text-[11px] font-semibold text-slate-500 dark:text-zinc-400">
                          Day +{post.day_offset}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        {post.suggested_platforms?.map((p) => {
                          const iconConfig = PLATFORM_ICONS[p.toLowerCase()] || { icon: FaBullhorn, color: '#6366f1', label: p };
                          const IconComp = iconConfig.icon;
                          return (
                            <span key={p} className="p-1 rounded bg-white dark:bg-zinc-800 border border-slate-200 dark:border-zinc-700 text-xs" style={{ color: iconConfig.color }} title={iconConfig.label}>
                              <IconComp />
                            </span>
                          );
                        })}
                      </div>
                    </div>

                    {post.hook && (
                      <div className="text-xs font-bold text-slate-900 dark:text-white">
                        🎯 Hook: <span className="font-normal text-slate-700 dark:text-zinc-300">{post.hook}</span>
                      </div>
                    )}

                    <div className="p-3 bg-white dark:bg-zinc-900 border border-slate-100 dark:border-zinc-800 rounded-xl text-xs text-slate-800 dark:text-zinc-200 whitespace-pre-line leading-relaxed font-sans">
                      {post.content}
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-1 text-[11px]">
                      <div className="flex flex-wrap gap-1 text-indigo-600 dark:text-indigo-400">
                        {post.hashtags?.map((tag) => (
                          <span key={tag} className="font-medium">{tag}</span>
                        ))}
                      </div>

                      <button
                        type="button"
                        onClick={() => handleSendToComposer(post.content, blueprintCampaign)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-xs transition-colors self-start sm:self-auto shrink-0"
                      >
                        <FaPen className="text-[10px]" />
                        Send to Composer
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-100 dark:border-zinc-800 flex justify-end gap-2 bg-slate-50 dark:bg-zinc-900">
              <button
                type="button"
                onClick={() => setBlueprintModalOpen(false)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 dark:text-zinc-300 hover:bg-slate-200 dark:hover:bg-zinc-800 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
