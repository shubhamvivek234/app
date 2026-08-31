import React, { useState, useEffect } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import {
  getMyBioPage,
  saveMyBioPage,
  getBioAnalytics,
  getBioLeads,
  exportBioLeadsCsv,
} from '@/lib/api';
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
  FaSpotify,
  FaGithub,
  FaDiscord,
  FaGlobe,
  FaSave,
  FaChartLine,
  FaEnvelope,
  FaDownload,
  FaQrcode,
  FaEye,
  FaMousePointer,
  FaPercentage,
  FaCheckCircle,
  FaClock,
  FaSlidersH,
  FaShareAlt,
  FaLayerGroup,
  FaImage,
  FaPlay,
  FaQuoteLeft,
  FaTimes,
  FaShieldAlt,
  FaChevronDown,
  FaChevronUp,
} from 'react-icons/fa';

const THEME_PRESETS = [
  {
    id: 'editorial_cream',
    name: 'Editorial Cream',
    subtitle: 'Warm parchment & luxury typography',
    background_type: 'gradient',
    background_color: '#FDFBF7',
    background_gradient: 'linear-gradient(135deg, #fdfbf7 0%, #f4ede2 100%)',
    text_color: '#18181B',
    card_style: 'glass_double_bezel',
    card_bg: 'rgba(255, 255, 255, 0.85)',
    card_border: 'rgba(0, 0, 0, 0.08)',
    card_text_color: '#18181B',
    button_radius: 'rounded-2xl',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#4F46E5',
  },
  {
    id: 'vantablack',
    name: 'OLED Vantablack',
    subtitle: 'Ultra-dark glass & pure white lines',
    background_type: 'dark',
    background_color: '#09090B',
    background_gradient: 'linear-gradient(180deg, #09090B 0%, #18181B 100%)',
    text_color: '#FAFAFA',
    card_style: 'glass_double_bezel',
    card_bg: 'rgba(24, 24, 27, 0.75)',
    card_border: 'rgba(255, 255, 255, 0.12)',
    card_text_color: '#FAFAFA',
    button_radius: 'rounded-2xl',
    font_family: 'Geist',
    accent_color: '#6366F1',
  },
  {
    id: 'electric_mesh',
    name: 'Electric Indigo',
    subtitle: 'Vibrant mesh glow & high contrast',
    background_type: 'gradient',
    background_color: '#0F172A',
    background_gradient: 'linear-gradient(135deg, #1E1B4B 0%, #0F172A 50%, #311042 100%)',
    text_color: '#F8FAFC',
    card_style: 'soft_pill',
    card_bg: 'rgba(30, 27, 75, 0.8)',
    card_border: 'rgba(129, 140, 248, 0.25)',
    card_text_color: '#F8FAFC',
    button_radius: 'rounded-full',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#818CF8',
  },
  {
    id: 'emerald_glass',
    name: 'Emerald Forest',
    subtitle: 'Deep botanical jade & frosted glass',
    background_type: 'gradient',
    background_color: '#022C22',
    background_gradient: 'linear-gradient(135deg, #064E3B 0%, #022C22 100%)',
    text_color: '#ECFDF5',
    card_style: 'glass_double_bezel',
    card_bg: 'rgba(6, 78, 59, 0.75)',
    card_border: 'rgba(52, 211, 153, 0.2)',
    card_text_color: '#ECFDF5',
    button_radius: 'rounded-2xl',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#10B981',
  },
  {
    id: 'sunset_coral',
    name: 'Sunset Rose',
    subtitle: 'Warm coral blush & crimson accents',
    background_type: 'gradient',
    background_color: '#FFF1F2',
    background_gradient: 'linear-gradient(135deg, #FFF1F2 0%, #FFE4E6 50%, #FEE2E2 100%)',
    text_color: '#881337',
    card_style: 'soft_pill',
    card_bg: 'rgba(255, 255, 255, 0.9)',
    card_border: 'rgba(225, 29, 72, 0.15)',
    card_text_color: '#881337',
    button_radius: 'rounded-full',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#E11D48',
  },
  {
    id: 'obsidian_luxury',
    name: 'Obsidian Gold',
    subtitle: 'Espresso charcoal & champagne gold',
    background_type: 'dark',
    background_color: '#1C1917',
    background_gradient: 'linear-gradient(180deg, #1C1917 0%, #292524 100%)',
    text_color: '#FEF3C7',
    card_style: 'minimal_outline',
    card_bg: 'rgba(41, 37, 36, 0.85)',
    card_border: 'rgba(245, 158, 11, 0.3)',
    card_text_color: '#FEF3C7',
    button_radius: 'rounded-xl',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#F59E0B',
  },
  {
    id: 'nordic_slate',
    name: 'Nordic Slate',
    subtitle: 'Clean Scandinavian monochrome',
    background_type: 'gradient',
    background_color: '#F8FAFC',
    background_gradient: 'linear-gradient(180deg, #F8FAFC 0%, #E2E8F0 100%)',
    text_color: '#0F172A',
    card_style: 'solid_flat',
    card_bg: '#FFFFFF',
    card_border: 'rgba(15, 23, 42, 0.08)',
    card_text_color: '#0F172A',
    button_radius: 'rounded-2xl',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#0EA5E9',
  },
  {
    id: 'cyberpunk_neon',
    name: 'Cyberpunk Neon',
    subtitle: 'High energy cyan & electric purple',
    background_type: 'dark',
    background_color: '#05050A',
    background_gradient: 'linear-gradient(135deg, #05050A 0%, #15002A 100%)',
    text_color: '#00F0FF',
    card_style: 'hard_shadow',
    card_bg: 'rgba(20, 0, 40, 0.85)',
    card_border: 'rgba(0, 240, 255, 0.4)',
    card_text_color: '#00F0FF',
    button_radius: 'rounded-xl',
    font_family: 'Geist',
    accent_color: '#FF0055',
  },
];

const SOCIAL_PLATFORMS = [
  { key: 'instagram', name: 'Instagram', icon: FaInstagram, placeholder: 'https://instagram.com/username' },
  { key: 'tiktok', name: 'TikTok', icon: FaTiktok, placeholder: 'https://tiktok.com/@username' },
  { key: 'youtube', name: 'YouTube', icon: FaYoutube, placeholder: 'https://youtube.com/@channel' },
  { key: 'twitter', name: 'X / Twitter', icon: FaTwitter, placeholder: 'https://x.com/username' },
  { key: 'linkedin', name: 'LinkedIn', icon: FaLinkedin, placeholder: 'https://linkedin.com/in/username' },
  { key: 'spotify', name: 'Spotify', icon: FaSpotify, placeholder: 'https://open.spotify.com/artist/...' },
  { key: 'github', name: 'GitHub', icon: FaGithub, placeholder: 'https://github.com/username' },
  { key: 'discord', name: 'Discord', icon: FaDiscord, placeholder: 'https://discord.gg/invite' },
];

export default function LinkInBio() {
  const [activeTab, setActiveTab] = useState('blocks'); // 'blocks' | 'themes' | 'socials' | 'analytics' | 'settings'
  const [handle, setHandle] = useState('');
  const [title, setTitle] = useState('');
  const [bio, setBio] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [verifiedBadge, setVerifiedBadge] = useState(false);
  const [theme, setTheme] = useState(THEME_PRESETS[0]);
  const [blocks, setBlocks] = useState([]);
  const [socialLinks, setSocialLinks] = useState({});
  const [customDomain, setCustomDomain] = useState('');
  const [seo, setSeo] = useState({ meta_title: '', meta_description: '' });
  const [autoSyncGrid, setAutoSyncGrid] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Analytics & Leads state
  const [analytics, setAnalytics] = useState(null);
  const [leads, setLeads] = useState([]);
  const [showQrModal, setShowQrModal] = useState(false);
  const [addBlockModalOpen, setAddBlockModalOpen] = useState(false);

  const loadData = async () => {
    try {
      setLoading(true);
      const data = await getMyBioPage();
      if (data) {
        setHandle(data.handle || '');
        setTitle(data.title || '');
        setBio(data.bio || '');
        setAvatarUrl(data.avatar_url || '');
        setVerifiedBadge(data.verified_badge ?? false);
        if (data.theme) setTheme(data.theme);
        setBlocks(data.blocks || []);
        setSocialLinks(data.social_links || {});
        setCustomDomain(data.custom_domain || '');
        setSeo(data.seo || { meta_title: '', meta_description: '' });
        setAutoSyncGrid(data.auto_sync_instagram_grid ?? true);
      }
      
      // Load Analytics
      try {
        const stats = await getBioAnalytics();
        setAnalytics(stats);
      } catch (e) {
        // non-blocking
      }

      // Load Leads
      try {
        const leadList = await getBioLeads();
        setLeads(leadList || []);
      } catch (e) {
        // non-blocking
      }
    } catch (err) {
      toast.error('Failed to load Bio Page data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSave = async () => {
    if (!handle) {
      toast.error('Please specify a unique handle');
      return;
    }
    setSaving(true);
    try {
      await saveMyBioPage({
        handle,
        title,
        bio,
        avatar_url: avatarUrl || undefined,
        verified_badge: verifiedBadge,
        theme,
        blocks,
        social_links: socialLinks,
        custom_domain: customDomain,
        seo,
        auto_sync_instagram_grid: autoSyncGrid,
        is_published: true,
      });
      toast.success('Smart Bio published successfully!');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to save bio page');
    } finally {
      setSaving(false);
    }
  };

  const handleAddBlock = (type) => {
    const newId = `blk_${Date.now()}`;
    let newBlock = { id: newId, type, active: true, click_count: 0 };

    if (type === 'link') {
      newBlock = {
        ...newBlock,
        title: 'New Featured Link',
        subtitle: 'Add a brief caption or description',
        url: 'https://',
        icon: 'globe',
        badge: '',
      };
    } else if (type === 'feed_grid') {
      newBlock = {
        ...newBlock,
        title: 'Recent Social Highlights',
        limit: 6,
        show_caption: true,
      };
    } else if (type === 'embed') {
      newBlock = {
        ...newBlock,
        title: 'Featured Media',
        provider: 'youtube',
        embed_url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
      };
    } else if (type === 'lead_capture') {
      newBlock = {
        ...newBlock,
        headline: 'Join My VIP Community 💌',
        subheadline: 'Exclusive drops & updates delivered weekly.',
        button_label: 'Subscribe',
      };
    } else if (type === 'media_card') {
      newBlock = {
        ...newBlock,
        title: 'Special Announcement',
        media_url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=800&q=80',
        url: 'https://',
        button_label: 'Learn More',
      };
    } else if (type === 'text_block') {
      newBlock = {
        ...newBlock,
        content: '“Quality is not an act, it is a habit.” ✨ Welcome to my official social hub.',
      };
    }

    setBlocks((prev) => [...prev, newBlock]);
    setAddBlockModalOpen(false);
    toast.success(`Added new ${type.replace('_', ' ')} block!`);
  };

  const handleUpdateBlock = (id, key, val) => {
    setBlocks((prev) => prev.map((b) => (b.id === id ? { ...b, [key]: val } : b)));
  };

  const handleDeleteBlock = (id) => {
    setBlocks((prev) => prev.filter((b) => b.id !== id));
  };

  const handleMoveBlock = (index, direction) => {
    const targetIndex = direction === 'up' ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= blocks.length) return;
    const newBlocks = [...blocks];
    const temp = newBlocks[index];
    newBlocks[index] = newBlocks[targetIndex];
    newBlocks[targetIndex] = temp;
    setBlocks(newBlocks);
  };

  const handleExportLeads = async () => {
    try {
      const blob = await exportBioLeadsCsv();
      const url = window.URL.createObjectURL(new Blob([blob]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `bio_leads_${handle || 'unravler'}.csv`);
      document.body.appendChild(link);
      link.click();
      link.parentNode.removeChild(link);
      toast.success('Leads CSV downloaded!');
    } catch (err) {
      toast.error('Failed to export leads CSV');
    }
  };

  const publicUrl = `https://www.unravler.com/@${handle}`;

  const copyPublicUrl = () => {
    navigator.clipboard.writeText(publicUrl);
    toast.success('Public URL copied to clipboard!');
  };

  return (
    <DashboardLayout>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        {/* Top Floating Glass Header */}
        <div className="bg-white/80 dark:bg-zinc-900/80 backdrop-blur-xl border border-zinc-200/80 dark:border-zinc-800 rounded-3xl p-5 sm:p-6 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-2xl bg-indigo-600/10 dark:bg-indigo-400/10 text-indigo-600 dark:text-indigo-400 flex items-center justify-center text-xl shadow-inner">
              <FaMobileAlt />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl sm:text-2xl font-black text-zinc-900 dark:text-white tracking-tight">
                  Smart Bio Studio
                </h1>
                <span className="px-2 py-0.5 text-[10px] font-black uppercase tracking-widest bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 rounded-full">
                  Live Sync
                </span>
              </div>
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
                Editorial Link-in-Bio & Dynamic Social Feed Mirroring
              </p>
            </div>
          </div>

          <div className="flex items-center flex-wrap gap-2.5">
            {handle && (
              <>
                <button
                  onClick={copyPublicUrl}
                  className="px-3.5 py-2 text-xs font-bold bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-zinc-800 dark:text-zinc-200 rounded-xl transition-all flex items-center gap-1.5 active:scale-95"
                >
                  <FaCopy /> Copy Link
                </button>
                <button
                  onClick={() => setShowQrModal(true)}
                  className="p-2.5 text-xs font-bold bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-zinc-800 dark:text-zinc-200 rounded-xl transition-all active:scale-95"
                  title="Show QR Code"
                >
                  <FaQrcode />
                </button>
                <a
                  href={publicUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="px-3.5 py-2 text-xs font-bold bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-zinc-800 dark:text-zinc-200 rounded-xl transition-all flex items-center gap-1.5 active:scale-95"
                >
                  <FaEye /> View Live
                </a>
              </>
            )}
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-5 py-2.5 text-xs font-black bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-md shadow-indigo-500/20 transition-all flex items-center gap-2 active:scale-95 disabled:opacity-50"
            >
              <FaSave /> {saving ? 'Publishing...' : 'Save & Publish'}
            </button>
          </div>
        </div>

        {/* Tab Navigation Pill Bar */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
          {[
            { id: 'blocks', label: 'Blocks & Content', icon: FaLayerGroup, count: blocks.length },
            { id: 'themes', label: 'Design & Themes', icon: FaPalette },
            { id: 'socials', label: 'Social Dock', icon: FaShareAlt, count: Object.keys(socialLinks).filter((k) => socialLinks[k]).length },
            { id: 'analytics', label: 'Analytics & Leads', icon: FaChartLine, count: leads.length },
            { id: 'settings', label: 'Settings & SEO', icon: FaSlidersH },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2.5 rounded-2xl text-xs font-bold transition-all flex items-center gap-2 shrink-0 ${
                  isActive
                    ? 'bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 shadow-sm'
                    : 'bg-white/60 dark:bg-zinc-900/60 text-zinc-600 dark:text-zinc-400 hover:bg-white dark:hover:bg-zinc-800 border border-zinc-200/60 dark:border-zinc-800/60'
                }`}
              >
                <Icon className={isActive ? 'text-indigo-400 dark:text-indigo-600' : 'opacity-60'} />
                <span>{tab.label}</span>
                {tab.count !== undefined && (
                  <span
                    className={`px-1.5 py-0.2 rounded-full text-[10px] font-black ${
                      isActive
                        ? 'bg-zinc-800 dark:bg-zinc-200 text-zinc-200 dark:text-zinc-800'
                        : 'bg-zinc-200 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400'
                    }`}
                  >
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Main Grid: Left Controls (7 cols) + Right Phone Simulator (5 cols) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Controls Column */}
          <div className="lg:col-span-7 space-y-6">
            {/* TAB 1: BLOCKS */}
            {activeTab === 'blocks' && (
              <div className="space-y-6">
                {/* Profile Header Quick Edit */}
                <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-6 shadow-xs space-y-4">
                  <h2 className="text-xs font-black uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
                    Header Profile
                  </h2>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-bold text-zinc-700 dark:text-zinc-300 mb-1">
                        Handle (@username)
                      </label>
                      <div className="flex items-center bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-2xl px-3 py-2 text-sm focus-within:ring-2 focus-within:ring-indigo-500">
                        <span className="text-zinc-400 font-medium select-none text-xs">unravler.com/@</span>
                        <input
                          type="text"
                          value={handle}
                          onChange={(e) => setHandle(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))}
                          className="bg-transparent flex-1 outline-hidden text-zinc-900 dark:text-white font-bold ml-1 text-sm"
                          placeholder="yourbrand"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs font-bold text-zinc-700 dark:text-zinc-300 mb-1">
                        Display Name
                      </label>
                      <input
                        type="text"
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        placeholder="Sarah Jenkins"
                        className="w-full px-3 py-2 text-sm font-bold bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-2xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-zinc-700 dark:text-zinc-300 mb-1">
                      Bio Tagline
                    </label>
                    <textarea
                      rows={2}
                      value={bio}
                      onChange={(e) => setBio(e.target.value)}
                      placeholder="Product Designer & Creator ✨ Exploring interfaces, sound, and design systems."
                      className="w-full px-3 py-2 text-xs bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-2xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center">
                    <div>
                      <label className="block text-xs font-bold text-zinc-700 dark:text-zinc-300 mb-1">
                        Avatar URL
                      </label>
                      <input
                        type="url"
                        value={avatarUrl}
                        onChange={(e) => setAvatarUrl(e.target.value)}
                        placeholder="https://.../avatar.jpg"
                        className="w-full px-3 py-2 text-xs bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-2xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                      />
                    </div>

                    <div className="flex items-center gap-3 pt-4">
                      <input
                        type="checkbox"
                        id="verified_badge"
                        checked={verifiedBadge}
                        onChange={(e) => setVerifiedBadge(e.target.checked)}
                        className="w-4 h-4 text-indigo-600 rounded-sm focus:ring-indigo-500 dark:bg-zinc-800"
                      />
                      <label htmlFor="verified_badge" className="text-xs font-bold text-zinc-700 dark:text-zinc-300 flex items-center gap-1.5 cursor-pointer">
                        <FaShieldAlt className="text-indigo-500" /> Show Verified Creator Badge
                      </label>
                    </div>
                  </div>
                </div>

                {/* Blocks Stack Header */}
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-base font-black text-zinc-900 dark:text-white tracking-tight">
                      Content Blocks ({blocks.length})
                    </h2>
                    <p className="text-xs text-zinc-500">
                      Reorder, schedule, and customize your buttons, feed, and widgets.
                    </p>
                  </div>
                  <button
                    onClick={() => setAddBlockModalOpen(true)}
                    className="px-4 py-2 text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-xs transition-all flex items-center gap-1.5 active:scale-95"
                  >
                    <FaPlus /> Add Block
                  </button>
                </div>

                {/* Block Items List */}
                {blocks.length === 0 ? (
                  <div className="bg-white dark:bg-zinc-900 border border-dashed border-zinc-300 dark:border-zinc-800 rounded-3xl p-12 text-center space-y-3">
                    <FaLayerGroup className="text-3xl text-zinc-400 mx-auto" />
                    <p className="text-sm font-bold text-zinc-700 dark:text-zinc-300">No content blocks yet</p>
                    <p className="text-xs text-zinc-500 max-w-sm mx-auto">
                      Add custom link buttons, your live Instagram/social feed grid, video players, or newsletter signup forms.
                    </p>
                    <button
                      onClick={() => setAddBlockModalOpen(true)}
                      className="px-4 py-2 text-xs font-bold bg-indigo-600 text-white rounded-xl hover:bg-indigo-500 inline-flex items-center gap-1.5"
                    >
                      <FaPlus /> Add Your First Block
                    </button>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {blocks.map((block, idx) => (
                      <div
                        key={block.id}
                        className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-5 shadow-xs space-y-4 relative group"
                      >
                        {/* Top Block Bar: Type, Order, Toggle, Delete */}
                        <div className="flex items-center justify-between gap-2 border-b border-zinc-100 dark:border-zinc-800/80 pb-3">
                          <div className="flex items-center gap-2">
                            <span className="w-6 h-6 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex items-center justify-center text-xs font-black">
                              {idx + 1}
                            </span>
                            <span className="px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 rounded-lg">
                              {block.type.replace('_', ' ')}
                            </span>
                            {block.click_count !== undefined && block.click_count > 0 && (
                              <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 px-2 py-0.5 rounded-full flex items-center gap-1">
                                <FaMousePointer className="text-[8px]" /> {block.click_count} clicks
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => handleMoveBlock(idx, 'up')}
                              disabled={idx === 0}
                              className="p-1.5 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 disabled:opacity-20"
                              title="Move Up"
                            >
                              <FaChevronUp className="text-xs" />
                            </button>
                            <button
                              onClick={() => handleMoveBlock(idx, 'down')}
                              disabled={idx === blocks.length - 1}
                              className="p-1.5 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 disabled:opacity-20"
                              title="Move Down"
                            >
                              <FaChevronDown className="text-xs" />
                            </button>
                            <button
                              onClick={() => handleDeleteBlock(block.id)}
                              className="p-1.5 text-zinc-400 hover:text-rose-600 rounded-lg transition-colors ml-2"
                              title="Delete Block"
                            >
                              <FaTrash className="text-xs" />
                            </button>
                          </div>
                        </div>

                        {/* BLOCK SPECIFIC CONTROLS */}
                        {block.type === 'link' && (
                          <div className="space-y-3">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                              <div>
                                <label className="block text-[11px] font-bold text-zinc-600 dark:text-zinc-400 mb-1">
                                  Button Label
                                </label>
                                <input
                                  type="text"
                                  value={block.title}
                                  onChange={(e) => handleUpdateBlock(block.id, 'title', e.target.value)}
                                  placeholder="My Portfolio & Projects"
                                  className="w-full px-3 py-1.5 text-xs font-bold bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                                />
                              </div>
                              <div>
                                <label className="block text-[11px] font-bold text-zinc-600 dark:text-zinc-400 mb-1">
                                  Highlight Badge (Optional)
                                </label>
                                <input
                                  type="text"
                                  value={block.badge || ''}
                                  onChange={(e) => handleUpdateBlock(block.id, 'badge', e.target.value)}
                                  placeholder="e.g. 50% OFF, NEW, HOT"
                                  className="w-full px-3 py-1.5 text-xs font-bold bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                                />
                              </div>
                            </div>

                            <div>
                              <label className="block text-[11px] font-bold text-zinc-600 dark:text-zinc-400 mb-1">
                                Destination URL
                              </label>
                              <input
                                type="url"
                                value={block.url}
                                onChange={(e) => handleUpdateBlock(block.id, 'url', e.target.value)}
                                placeholder="https://mywebsite.com/summer-sale"
                                className="w-full px-3 py-1.5 text-xs bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white font-mono"
                              />
                            </div>

                            <div>
                              <label className="block text-[11px] font-bold text-zinc-600 dark:text-zinc-400 mb-1">
                                Subtitle Caption (Optional)
                              </label>
                              <input
                                type="text"
                                value={block.subtitle || ''}
                                onChange={(e) => handleUpdateBlock(block.id, 'subtitle', e.target.value)}
                                placeholder="Instant digital download available worldwide"
                                className="w-full px-3 py-1.5 text-xs bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                              />
                            </div>
                          </div>
                        )}

                        {block.type === 'feed_grid' && (
                          <div className="space-y-3 bg-zinc-50 dark:bg-zinc-800/40 p-4 rounded-2xl border border-zinc-100 dark:border-zinc-800">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-bold text-zinc-800 dark:text-zinc-200">
                                Live Social Feed Mirroring
                              </span>
                              <span className="text-[10px] font-black uppercase text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full">
                                Auto-Populated
                              </span>
                            </div>
                            <p className="text-xs text-zinc-500">
                              Automatically renders recent published social posts from your Unravler publishing queue. When followers click a post image, they get redirected to your destination link.
                            </p>
                            <div className="flex items-center gap-4 pt-1">
                              <div className="flex items-center gap-2">
                                <label className="text-xs font-bold text-zinc-700 dark:text-zinc-300">Display Limit:</label>
                                <select
                                  value={block.limit || 6}
                                  onChange={(e) => handleUpdateBlock(block.id, 'limit', parseInt(e.target.value, 10))}
                                  className="text-xs font-bold bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-lg px-2 py-1"
                                >
                                  <option value={3}>3 Posts</option>
                                  <option value={6}>6 Posts</option>
                                  <option value={9}>9 Posts</option>
                                  <option value={12}>12 Posts</option>
                                </select>
                              </div>
                            </div>
                          </div>
                        )}

                        {block.type === 'embed' && (
                          <div className="space-y-3">
                            <div>
                              <label className="block text-[11px] font-bold text-zinc-600 dark:text-zinc-400 mb-1">
                                Media Player Title
                              </label>
                              <input
                                type="text"
                                value={block.title}
                                onChange={(e) => handleUpdateBlock(block.id, 'title', e.target.value)}
                                placeholder="Latest YouTube Video / Spotify Episode"
                                className="w-full px-3 py-1.5 text-xs font-bold bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                              />
                            </div>
                            <div>
                              <label className="block text-[11px] font-bold text-zinc-600 dark:text-zinc-400 mb-1">
                                Video or Spotify URL
                              </label>
                              <input
                                type="url"
                                value={block.embed_url}
                                onChange={(e) => handleUpdateBlock(block.id, 'embed_url', e.target.value)}
                                placeholder="https://www.youtube.com/watch?v=... or Spotify link"
                                className="w-full px-3 py-1.5 text-xs font-mono bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                              />
                            </div>
                          </div>
                        )}

                        {block.type === 'lead_capture' && (
                          <div className="space-y-3">
                            <div>
                              <label className="block text-[11px] font-bold text-zinc-600 dark:text-zinc-400 mb-1">
                                Headline
                              </label>
                              <input
                                type="text"
                                value={block.headline}
                                onChange={(e) => handleUpdateBlock(block.id, 'headline', e.target.value)}
                                placeholder="Join My VIP Newsletter 💌"
                                className="w-full px-3 py-1.5 text-xs font-bold bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                              />
                            </div>
                            <div>
                              <label className="block text-[11px] font-bold text-zinc-600 dark:text-zinc-400 mb-1">
                                Subheadline
                              </label>
                              <input
                                type="text"
                                value={block.subheadline}
                                onChange={(e) => handleUpdateBlock(block.id, 'subheadline', e.target.value)}
                                placeholder="Get behind-the-scenes insights & free resource drops."
                                className="w-full px-3 py-1.5 text-xs bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                              />
                            </div>
                          </div>
                        )}

                        {block.type === 'text_block' && (
                          <div>
                            <label className="block text-[11px] font-bold text-zinc-600 dark:text-zinc-400 mb-1">
                              Note / Quote Content
                            </label>
                            <textarea
                              rows={2}
                              value={block.content}
                              onChange={(e) => handleUpdateBlock(block.id, 'content', e.target.value)}
                              placeholder="Type an announcement or inspirational message..."
                              className="w-full px-3 py-2 text-xs bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                            />
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: THEMES */}
            {activeTab === 'themes' && (
              <div className="space-y-6">
                <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-6 shadow-xs space-y-4">
                  <h2 className="text-base font-black text-zinc-900 dark:text-white tracking-tight">
                    Curated Agency Themes
                  </h2>
                  <p className="text-xs text-zinc-500">
                    Pick a handcrafted luxury aesthetic inspired by editorial publications and modern design studios.
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                    {THEME_PRESETS.map((preset) => {
                      const isSelected = theme.preset === preset.id;
                      return (
                        <div
                          key={preset.id}
                          onClick={() => setTheme(preset)}
                          style={{ background: preset.background_gradient }}
                          className={`p-5 rounded-3xl cursor-pointer border-2 transition-all relative overflow-hidden flex flex-col justify-between h-36 ${
                            isSelected
                              ? 'border-indigo-600 ring-4 ring-indigo-500/20 shadow-lg scale-[1.02]'
                              : 'border-black/5 hover:border-black/20 hover:scale-[1.01]'
                          }`}
                        >
                          <div className="flex items-start justify-between">
                            <div>
                              <h3 style={{ color: preset.text_color }} className="font-extrabold text-sm tracking-tight">
                                {preset.name}
                              </h3>
                              <p style={{ color: preset.text_color }} className="text-[11px] opacity-70 mt-0.5">
                                {preset.subtitle}
                              </p>
                            </div>
                            {isSelected && (
                              <FaCheckCircle className="text-indigo-600 bg-white rounded-full text-base shrink-0" />
                            )}
                          </div>

                          <div
                            style={{
                              backgroundColor: preset.card_bg,
                              borderColor: preset.card_border,
                              color: preset.card_text_color,
                            }}
                            className={`px-3 py-2 text-center text-[11px] font-bold border shadow-xs ${preset.button_radius}`}
                          >
                            Sample Button
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Fine-Tuning Controls */}
                <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-6 shadow-xs space-y-4">
                  <h2 className="text-sm font-bold text-zinc-900 dark:text-white uppercase tracking-wider">
                    Custom Theme Fine-Tuning
                  </h2>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs font-bold text-zinc-700 dark:text-zinc-300 mb-1">
                        Button Shape
                      </label>
                      <select
                        value={theme.button_radius}
                        onChange={(e) => setTheme({ ...theme, button_radius: e.target.value })}
                        className="w-full px-3 py-2 text-xs font-bold bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl"
                      >
                        <option value="rounded-none">Sharp Rectangle</option>
                        <option value="rounded-xl">Subtle Radius (12px)</option>
                        <option value="rounded-2xl">Modern Soft (16px)</option>
                        <option value="rounded-full">Fully Rounded Pill</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-bold text-zinc-700 dark:text-zinc-300 mb-1">
                        Card Style
                      </label>
                      <select
                        value={theme.card_style}
                        onChange={(e) => setTheme({ ...theme, card_style: e.target.value })}
                        className="w-full px-3 py-2 text-xs font-bold bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl"
                      >
                        <option value="glass_double_bezel">Glass Double-Bezel</option>
                        <option value="solid_flat">Solid Flat</option>
                        <option value="hard_shadow">Hard Brutalist Shadow</option>
                        <option value="minimal_outline">Minimal Outline</option>
                        <option value="soft_pill">Soft Pill</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-bold text-zinc-700 dark:text-zinc-300 mb-1">
                        Typography
                      </label>
                      <select
                        value={theme.font_family}
                        onChange={(e) => setTheme({ ...theme, font_family: e.target.value })}
                        className="w-full px-3 py-2 text-xs font-bold bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl"
                      >
                        <option value="Plus Jakarta Sans">Plus Jakarta Sans</option>
                        <option value="Geist">Geist Monospace / Modern</option>
                        <option value="PP Editorial New">Editorial Serif</option>
                        <option value="Clash Display">Clash Grotesk</option>
                      </select>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 3: SOCIALS */}
            {activeTab === 'socials' && (
              <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-6 shadow-xs space-y-4">
                <div>
                  <h2 className="text-base font-black text-zinc-900 dark:text-white tracking-tight">
                    Social Accounts Dock
                  </h2>
                  <p className="text-xs text-zinc-500 mt-0.5">
                    Add direct links to your social channels. These render as sleek circular icons directly under your profile bio.
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                  {SOCIAL_PLATFORMS.map((plat) => {
                    const Icon = plat.icon;
                    return (
                      <div key={plat.key} className="space-y-1">
                        <label className="text-xs font-bold text-zinc-700 dark:text-zinc-300 flex items-center gap-1.5">
                          <Icon className="text-indigo-600 dark:text-indigo-400" /> {plat.name}
                        </label>
                        <input
                          type="url"
                          value={socialLinks[plat.key] || ''}
                          onChange={(e) => setSocialLinks({ ...socialLinks, [plat.key]: e.target.value })}
                          placeholder={plat.placeholder}
                          className="w-full px-3 py-2 text-xs bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-2xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                        />
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* TAB 4: ANALYTICS & LEADS */}
            {activeTab === 'analytics' && (
              <div className="space-y-6">
                {/* Stats Metric Cards */}
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-5 shadow-xs">
                    <div className="flex items-center justify-between text-zinc-400 text-xs font-bold">
                      <span>Total Views</span>
                      <FaEye className="text-indigo-500" />
                    </div>
                    <p className="text-2xl sm:text-3xl font-black text-zinc-900 dark:text-white mt-2">
                      {analytics?.views || 0}
                    </p>
                    <span className="text-[10px] text-zinc-400 font-medium">All-time page impressions</span>
                  </div>

                  <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-5 shadow-xs">
                    <div className="flex items-center justify-between text-zinc-400 text-xs font-bold">
                      <span>Total Clicks</span>
                      <FaMousePointer className="text-emerald-500" />
                    </div>
                    <p className="text-2xl sm:text-3xl font-black text-zinc-900 dark:text-white mt-2">
                      {analytics?.clicks || 0}
                    </p>
                    <span className="text-[10px] text-zinc-400 font-medium">Outbound link interactions</span>
                  </div>

                  <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-5 shadow-xs">
                    <div className="flex items-center justify-between text-zinc-400 text-xs font-bold">
                      <span>CTR %</span>
                      <FaPercentage className="text-amber-500" />
                    </div>
                    <p className="text-2xl sm:text-3xl font-black text-zinc-900 dark:text-white mt-2">
                      {analytics?.ctr || 0}%
                    </p>
                    <span className="text-[10px] text-zinc-400 font-medium">Click-through conversion rate</span>
                  </div>
                </div>

                {/* Top Referrers & Per-Link Breakdown */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-5 shadow-xs space-y-3">
                    <h3 className="text-xs font-black uppercase tracking-wider text-zinc-500">
                      Top Traffic Referrers
                    </h3>
                    {analytics?.referrers && analytics.referrers.length > 0 ? (
                      <div className="space-y-2">
                        {analytics.referrers.map((ref, idx) => (
                          <div key={idx} className="flex items-center justify-between text-xs py-1.5 border-b border-zinc-100 dark:border-zinc-800">
                            <span className="font-bold text-zinc-800 dark:text-zinc-200">{ref.source}</span>
                            <span className="font-mono text-indigo-600 dark:text-indigo-400 font-bold">{ref.clicks} clicks</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-zinc-400 py-3 text-center">No referrer data recorded yet.</p>
                    )}
                  </div>

                  <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-5 shadow-xs space-y-3">
                    <h3 className="text-xs font-black uppercase tracking-wider text-zinc-500">
                      Top Performing Links
                    </h3>
                    {analytics?.top_blocks && analytics.top_blocks.length > 0 ? (
                      <div className="space-y-2">
                        {analytics.top_blocks.map((blk, idx) => (
                          <div key={idx} className="flex items-center justify-between text-xs py-1.5 border-b border-zinc-100 dark:border-zinc-800">
                            <span className="font-bold text-zinc-800 dark:text-zinc-200 truncate max-w-[160px]">{blk.title}</span>
                            <span className="font-mono text-emerald-600 dark:text-emerald-400 font-bold">{blk.clicks} clicks</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-zinc-400 py-3 text-center">No clicks recorded on links yet.</p>
                    )}
                  </div>
                </div>

                {/* Newsletter Leads Capture Table */}
                <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-6 shadow-xs space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-black text-zinc-900 dark:text-white flex items-center gap-2">
                        <FaEnvelope className="text-indigo-500" /> Captured Newsletter Leads ({leads.length})
                      </h3>
                      <p className="text-xs text-zinc-500 mt-0.5">
                        Followers who subscribed through your Smart Bio lead capture form.
                      </p>
                    </div>
                    {leads.length > 0 && (
                      <button
                        onClick={handleExportLeads}
                        className="px-3.5 py-2 text-xs font-bold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-100 rounded-xl flex items-center gap-1.5"
                      >
                        <FaDownload /> Export CSV
                      </button>
                    )}
                  </div>

                  {leads.length === 0 ? (
                    <p className="text-xs text-zinc-400 py-4 text-center">
                      No email leads collected yet. Add a &ldquo;Lead Capture Form&rdquo; block to start growing your list!
                    </p>
                  ) : (
                    <div className="divide-y divide-zinc-100 dark:divide-zinc-800 max-h-56 overflow-y-auto">
                      {leads.map((lead) => (
                        <div key={lead.id} className="py-2.5 flex items-center justify-between text-xs">
                          <span className="font-bold text-zinc-800 dark:text-zinc-200">{lead.email}</span>
                          <span className="text-zinc-400 text-[11px] font-mono">
                            {new Date(lead.created_at).toLocaleDateString()}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* TAB 5: SETTINGS & SEO */}
            {activeTab === 'settings' && (
              <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl p-6 shadow-xs space-y-6">
                <div>
                  <h2 className="text-base font-black text-zinc-900 dark:text-white tracking-tight">
                    Custom Domain & SEO
                  </h2>
                  <p className="text-xs text-zinc-500 mt-0.5">
                    Connect your own domain (e.g. links.yourbrand.com) and configure rich OpenGraph social share previews.
                  </p>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-bold text-zinc-700 dark:text-zinc-300 mb-1">
                      Custom Subdomain (CNAME)
                    </label>
                    <input
                      type="text"
                      value={customDomain}
                      onChange={(e) => setCustomDomain(e.target.value)}
                      placeholder="links.mybrand.com"
                      className="w-full px-3 py-2 text-xs font-mono bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-2xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                    />
                    <p className="text-[11px] text-zinc-400 mt-1">
                      Add a CNAME record pointing your subdomain to <code className="text-indigo-500 font-bold">cname.unravler.bio</code>.
                    </p>
                  </div>

                  <div className="border-t border-zinc-100 dark:border-zinc-800 pt-4 space-y-3">
                    <h3 className="text-xs font-black uppercase tracking-wider text-zinc-500">
                      SEO & Social Previews
                    </h3>
                    <div>
                      <label className="block text-xs font-bold text-zinc-700 dark:text-zinc-300 mb-1">
                        Meta Page Title
                      </label>
                      <input
                        type="text"
                        value={seo.meta_title || ''}
                        onChange={(e) => setSeo({ ...seo, meta_title: e.target.value })}
                        placeholder={`${title || 'My Brand'} | Official Links & Social Hub`}
                        className="w-full px-3 py-2 text-xs bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-2xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-zinc-700 dark:text-zinc-300 mb-1">
                        Meta Description
                      </label>
                      <textarea
                        rows={2}
                        value={seo.meta_description || ''}
                        onChange={(e) => setSeo({ ...seo, meta_description: e.target.value })}
                        placeholder="Explore the latest templates, social media drops, and projects."
                        className="w-full px-3 py-2 text-xs bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-2xl outline-hidden focus:ring-2 focus:ring-indigo-500 text-zinc-900 dark:text-white"
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Right Live Device Simulator (5 cols) */}
          <div className="lg:col-span-5 sticky top-6">
            <div className="flex flex-col items-center">
              {/* Top Device Bar */}
              <div className="flex items-center gap-2 mb-3">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-[11px] font-black uppercase tracking-widest text-zinc-500">
                  Live Device Simulator
                </span>
              </div>

              {/* Machined iPhone Frame */}
              <div className="w-[340px] sm:w-[360px] h-[720px] bg-zinc-950 rounded-[48px] p-3 ring-12 ring-zinc-900 shadow-2xl relative flex flex-col justify-between overflow-hidden">
                {/* Dynamic Island / Camera Notch */}
                <div className="absolute top-4 left-1/2 -translate-x-1/2 w-28 h-6 bg-black rounded-full z-30 flex items-center justify-between px-3">
                  <span className="w-2 h-2 rounded-full bg-indigo-900/60" />
                  <span className="w-2.5 h-2.5 rounded-full bg-zinc-900 border border-zinc-800" />
                </div>

                {/* Inner Screen Canvas */}
                <div
                  style={{ background: theme.background_gradient || theme.background_color }}
                  className="w-full h-full rounded-[38px] overflow-y-auto pt-14 pb-8 px-4 text-center flex flex-col items-center justify-between scrollbar-none transition-all duration-300"
                >
                  <div className="w-full flex flex-col items-center space-y-4">
                    {/* Avatar */}
                    <div className="w-20 h-20 rounded-full border-2 border-white/40 overflow-hidden bg-black/10 flex items-center justify-center shadow-md shrink-0">
                      {avatarUrl ? (
                        <img src={avatarUrl} alt={title} className="w-full h-full object-cover" />
                      ) : (
                        <span style={{ color: theme.text_color }} className="text-2xl font-black uppercase">
                          {title ? title[0] : 'U'}
                        </span>
                      )}
                    </div>

                    {/* Title & Bio */}
                    <div className="space-y-1 max-w-[280px]">
                      <h2
                        style={{ color: theme.text_color }}
                        className="text-base font-extrabold tracking-tight flex items-center justify-center gap-1.5"
                      >
                        {title || 'Your Brand'}
                        {verifiedBadge && <FaCheckCircle className="text-indigo-500 text-xs" />}
                      </h2>
                      <p style={{ color: theme.text_color }} className="text-[11px] font-mono opacity-60">
                        @{handle || 'handle'}
                      </p>
                      {bio && (
                        <p style={{ color: theme.text_color }} className="text-[11px] opacity-80 pt-1 leading-relaxed line-clamp-3">
                          {bio}
                        </p>
                      )}
                    </div>

                    {/* Social Dock Bar */}
                    {Object.keys(socialLinks).some((k) => socialLinks[k]) && (
                      <div className="flex items-center justify-center gap-2 pt-1 flex-wrap">
                        {Object.entries(socialLinks).map(([plat, url]) => {
                          if (!url) return null;
                          return (
                            <span
                              key={plat}
                              className="w-8 h-8 rounded-full bg-black/10 dark:bg-white/10 flex items-center justify-center text-xs shadow-2xs hover:scale-105 transition-transform"
                              style={{ color: theme.text_color }}
                            >
                              <FaGlobe />
                            </span>
                          );
                        })}
                      </div>
                    )}

                    {/* Active Blocks Stack */}
                    <div className="w-full space-y-2.5 pt-2">
                      {blocks.map((block) => {
                        if (!block.active) return null;

                        if (block.type === 'link') {
                          return (
                            <div
                              key={block.id}
                              style={{
                                backgroundColor: theme.card_bg,
                                borderColor: theme.card_border,
                                color: theme.card_text_color,
                              }}
                              className={`w-full py-3 px-4 ${theme.button_radius} border shadow-xs text-xs font-bold flex items-center justify-between transition-all hover:scale-[1.01]`}
                            >
                              <div className="text-left">
                                <div className="flex items-center gap-1.5">
                                  <span>{block.title || 'Untitled Link'}</span>
                                  {block.badge && (
                                    <span className="px-1.5 py-0.2 text-[8px] font-black uppercase bg-rose-500 text-white rounded-full">
                                      {block.badge}
                                    </span>
                                  )}
                                </div>
                                {block.subtitle && (
                                  <p className="text-[9px] opacity-70 font-normal mt-0.5">{block.subtitle}</p>
                                )}
                              </div>
                              <FaExternalLinkAlt className="text-[10px] opacity-40 shrink-0" />
                            </div>
                          );
                        }

                        if (block.type === 'feed_grid') {
                          return (
                            <div key={block.id} className="w-full pt-2 space-y-1.5">
                              <span style={{ color: theme.text_color }} className="text-[10px] font-black uppercase tracking-wider opacity-60 block text-left">
                                {block.title || 'Recent Highlights'}
                              </span>
                              <div className="grid grid-cols-3 gap-1.5">
                                {[1, 2, 3, 4, 5, 6].slice(0, block.limit || 6).map((num) => (
                                  <div
                                    key={num}
                                    className="aspect-square bg-black/10 dark:bg-white/10 rounded-xl flex items-center justify-center text-[10px] font-bold opacity-70 border border-black/5"
                                  >
                                    <FaImage className="opacity-40" />
                                  </div>
                                ))}
                              </div>
                            </div>
                          );
                        }

                        if (block.type === 'embed') {
                          return (
                            <div
                              key={block.id}
                              style={{
                                backgroundColor: theme.card_bg,
                                borderColor: theme.card_border,
                                color: theme.card_text_color,
                              }}
                              className={`w-full p-3 ${theme.button_radius} border shadow-xs space-y-1.5 text-left`}
                            >
                              <span className="text-[10px] font-bold block">{block.title || 'Featured Media'}</span>
                              <div className="w-full h-24 bg-black/20 rounded-xl flex items-center justify-center">
                                <FaPlay className="text-base text-white/80" />
                              </div>
                            </div>
                          );
                        }

                        if (block.type === 'lead_capture') {
                          return (
                            <div
                              key={block.id}
                              style={{
                                backgroundColor: theme.card_bg,
                                borderColor: theme.card_border,
                                color: theme.card_text_color,
                              }}
                              className={`w-full p-3.5 ${theme.button_radius} border shadow-xs space-y-2 text-center`}
                            >
                              <p className="text-[11px] font-black">{block.headline || 'Join Newsletter'}</p>
                              <div className="flex items-center gap-1">
                                <input
                                  disabled
                                  placeholder="your@email.com"
                                  className="w-full px-2 py-1 text-[10px] bg-white/50 border border-black/10 rounded-lg"
                                />
                                <button
                                  disabled
                                  className="px-2.5 py-1 text-[10px] font-black bg-indigo-600 text-white rounded-lg"
                                >
                                  {block.button_label || 'Join'}
                                </button>
                              </div>
                            </div>
                          );
                        }

                        if (block.type === 'text_block') {
                          return (
                            <div
                              key={block.id}
                              style={{ color: theme.text_color }}
                              className="w-full py-2 px-3 text-[10px] italic opacity-80"
                            >
                              {block.content}
                            </div>
                          );
                        }

                        return null;
                      })}
                    </div>
                  </div>

                  {/* Footer Tag */}
                  <div className="pt-6">
                    <span style={{ color: theme.text_color }} className="text-[9px] font-bold opacity-40">
                      ⚡ Powered by Unravler Smart Bio
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ADD BLOCK MODAL */}
        {addBlockModalOpen && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl max-w-md w-full p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-black text-zinc-900 dark:text-white">
                  Add Content Block
                </h3>
                <button onClick={() => setAddBlockModalOpen(false)} className="text-zinc-400 hover:text-zinc-600">
                  <FaTimes />
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                {[
                  { type: 'link', label: 'Custom Link Button', desc: 'Direct link with badge & subtitle', icon: FaExternalLinkAlt },
                  { type: 'feed_grid', label: 'Social Feed Grid', desc: 'Live visual feed mirroring', icon: FaImage },
                  { type: 'embed', label: 'Media Player Embed', desc: 'YouTube video or Spotify player', icon: FaPlay },
                  { type: 'lead_capture', label: 'Newsletter Lead Box', desc: 'Collect emails into database', icon: FaEnvelope },
                  { type: 'text_block', label: 'Editorial Quote / Note', desc: 'Rich text announcement', icon: FaQuoteLeft },
                ].map((item) => {
                  const Icon = item.icon;
                  return (
                    <div
                      key={item.type}
                      onClick={() => handleAddBlock(item.type)}
                      className="p-3.5 bg-zinc-50 dark:bg-zinc-800/60 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 border border-zinc-200 dark:border-zinc-700 rounded-2xl cursor-pointer transition-all hover:scale-[1.02] space-y-1"
                    >
                      <div className="w-7 h-7 rounded-lg bg-indigo-600/10 text-indigo-600 dark:text-indigo-400 flex items-center justify-center text-xs">
                        <Icon />
                      </div>
                      <h4 className="text-xs font-bold text-zinc-900 dark:text-white">{item.label}</h4>
                      <p className="text-[10px] text-zinc-500">{item.desc}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* QR CODE MODAL */}
        {showQrModal && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl max-w-sm w-full p-6 shadow-2xl text-center space-y-4">
              <h3 className="text-base font-black text-zinc-900 dark:text-white">
                Scan Your Smart Bio
              </h3>
              <p className="text-xs text-zinc-500">
                Place this QR code on business cards, brochures, or packaging.
              </p>

              <div className="bg-white p-4 rounded-2xl shadow-inner inline-block border border-zinc-200">
                <img
                  src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(publicUrl)}`}
                  alt="QR Code"
                  className="w-44 h-44 mx-auto"
                />
              </div>

              <p className="text-xs font-mono font-bold text-indigo-600 dark:text-indigo-400">
                unravler.com/@{handle}
              </p>

              <button
                onClick={() => setShowQrModal(false)}
                className="w-full py-2 text-xs font-bold bg-zinc-900 text-white rounded-xl hover:bg-zinc-800"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
