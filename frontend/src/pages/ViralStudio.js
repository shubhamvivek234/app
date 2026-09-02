import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import { getViralHooks, generateShortFormScript, autoFillViralHook, toggleHookBookmark } from '@/lib/api';
import { toast } from 'sonner';
import {
  FaBolt,
  FaVideo,
  FaSearch,
  FaCopy,
  FaBookmark,
  FaRegBookmark,
  FaMagic,
  FaArrowRight,
  FaCheck,
  FaClock,
  FaFire,
  FaCommentDots,
  FaFont,
  FaQuoteLeft,
  FaTimes,
  FaChevronDown,
  FaFilter,
} from 'react-icons/fa';
import { SiTiktok, SiInstagram, SiYoutube } from 'react-icons/si';

const NICHE_ICONS = {
  all: '🌐',
  saas_tech: '💻',
  ecommerce: '🛍️',
  marketing: '📈',
  fitness: '💪',
  real_estate: '🏡',
  finance: '💰',
  creator: '🎬',
  productivity: '⚡',
  beauty_fashion: '💄',
  food_cooking: '🍳',
  career_jobs: '💼',
  coaching_consulting: '🧠',
  travel_lifestyle: '✈️',
  legal_tax: '⚖️',
  gaming_gear: '🎮',
  parenting_home: '👶',
};

export default function ViralStudio() {
  const navigate = useNavigate();

  // Active Main Tab
  const [activeTab, setActiveTab] = useState('vault'); // 'vault' | 'scriptwriter' | 'bookmarks'

  // Hook Vault States
  const [hooks, setHooks] = useState([]);
  const [categories, setCategories] = useState([]);
  const [niches, setNiches] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedNiche, setSelectedNiche] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [loadingHooks, setLoadingHooks] = useState(true);
  const [visibleCount, setVisibleCount] = useState(24);
  const [bookmarkedIds, setBookmarkedIds] = useState(new Set());
  const [copiedId, setCopiedId] = useState(null);

  // Auto-fill Modal State
  const [autoFillModal, setAutoFillModal] = useState({ open: false, hook: null, topic: '', results: [], loading: false });

  // Scriptwriter States
  const [scriptTopic, setScriptTopic] = useState('');
  const [scriptNiche, setScriptNiche] = useState('saas_tech');
  const [scriptPlatform, setScriptPlatform] = useState('tiktok');
  const [scriptDuration, setScriptDuration] = useState('30s');
  const [scriptHookStyle, setScriptHookStyle] = useState('contrarian');
  const [scriptResult, setScriptResult] = useState(null);
  const [generatingScript, setGeneratingScript] = useState(false);
  const [selectedHookIndex, setSelectedHookIndex] = useState(0);

  // Load hooks catalog
  const fetchCatalog = useCallback(async () => {
    setLoadingHooks(true);
    try {
      const data = await getViralHooks({
        category: selectedCategory,
        niche: selectedNiche,
        search: searchQuery,
      });
      setHooks(data.hooks || []);
      setVisibleCount(24);
      if (data.categories) setCategories(data.categories);
      if (data.niches) setNiches(data.niches);
    } catch (err) {
      toast.error('Failed to load viral hooks catalog.');
    } finally {
      setLoadingHooks(false);
    }
  }, [selectedCategory, selectedNiche, searchQuery]);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  const handleCopyText = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    toast.success('Copied hook to clipboard!');
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleUseInComposer = (text) => {
    navigate('/create-post', { state: { initialContent: text, initialCaption: text } });
  };

  const handleToggleBookmark = async (hookId) => {
    try {
      const res = await toggleHookBookmark(hookId);
      setBookmarkedIds((prev) => {
        const next = new Set(prev);
        if (res.bookmarked) next.add(hookId);
        else next.delete(hookId);
        return next;
      });
      toast.success(res.bookmarked ? 'Saved to bookmarks' : 'Removed from bookmarks');
    } catch {
      // Local optimistic toggle fallback
      setBookmarkedIds((prev) => {
        const next = new Set(prev);
        if (next.has(hookId)) next.delete(hookId);
        else next.add(hookId);
        return next;
      });
    }
  };

  const handleOpenAutoFill = (hook) => {
    setAutoFillModal({
      open: true,
      hook,
      topic: '',
      results: [],
      loading: false,
    });
  };

  const handleRunAutoFill = async () => {
    if (!autoFillModal.topic.trim() || !autoFillModal.hook) return;
    setAutoFillModal((prev) => ({ ...prev, loading: true }));
    try {
      const res = await autoFillViralHook({
        hook_template: autoFillModal.hook.template,
        topic_or_brand: autoFillModal.topic.trim(),
        niche: selectedNiche !== 'all' ? selectedNiche : 'creator',
      });
      setAutoFillModal((prev) => ({ ...prev, results: res.variations || [], loading: false }));
    } catch {
      toast.error('Failed to personalize hook.');
      setAutoFillModal((prev) => ({ ...prev, loading: false }));
    }
  };

  const handleGenerateScript = async () => {
    if (!scriptTopic.trim()) {
      toast.error('Please enter a video topic or concept.');
      return;
    }
    setGeneratingScript(true);
    try {
      const data = await generateShortFormScript({
        topic: scriptTopic.trim(),
        niche: scriptNiche,
        platform: scriptPlatform,
        target_duration: scriptDuration,
        hook_style: scriptHookStyle,
        use_brand_voice: true,
      });
      setScriptResult(data);
      setSelectedHookIndex(0);
      toast.success('Viral video script generated!');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Generation failed. Check your API settings.');
    } finally {
      setGeneratingScript(false);
    }
  };

  const handleSendScriptToComposer = () => {
    if (!scriptResult) return;
    const finalPost = `${scriptResult.selected_hook}\n\n${scriptResult.full_script}\n\n${scriptResult.call_to_action}\n\n${scriptResult.recommended_hashtags?.join(' ')}`;
    navigate('/create-post', { state: { initialContent: finalPost, initialCaption: finalPost } });
  };

  return (
    <DashboardLayout>
      <div className="min-h-[100dvh] bg-[#FAF9F6] dark:bg-[#0C0A09] text-gray-900 dark:text-gray-100 py-8 px-4 sm:px-6 lg:px-10 transition-colors relative font-sans">
        {/* Subtle Ambient Grid Backdrop */}
        <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] dark:bg-[radial-gradient(#27272a_1px,transparent_1px)] [background-size:24px_24px] opacity-40" />

        <div className="max-w-7xl mx-auto relative z-10 space-y-8">
          {/* Top Studio Header */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 pb-6 border-b border-gray-200/80 dark:border-zinc-800/80">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-800 dark:text-amber-300 text-xs font-semibold tracking-wide mb-2.5">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                Short-Form Intelligence & Viral Hooks
              </div>
              <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-gray-900 dark:text-white">
                Viral Studio
              </h1>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5 max-w-2xl leading-relaxed">
                Curated library of 1,700+ battle-tested short-form hooks and automated 9:16 video storyboard studio for TikTok, Instagram Reels & YouTube Shorts.
              </p>
            </div>

            {/* Segmented Navigation Dock */}
            <div className="inline-flex p-1 bg-white/90 dark:bg-zinc-900/90 backdrop-blur-md rounded-2xl border border-gray-200/80 dark:border-zinc-800 shadow-2xs self-start md:self-auto">
              <button
                onClick={() => setActiveTab('vault')}
                className={`flex items-center gap-2 px-4 py-2 text-xs sm:text-sm font-semibold rounded-xl transition-all cursor-pointer ${
                  activeTab === 'vault'
                    ? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-zinc-800/60'
                }`}
              >
                <FaBolt className={activeTab === 'vault' ? 'text-amber-400 dark:text-amber-500 text-xs' : 'text-amber-500 text-xs'} />
                <span>Hook Vault</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-mono font-bold ${
                  activeTab === 'vault'
                    ? 'bg-white/20 text-white dark:bg-black/10 dark:text-gray-900'
                    : 'bg-gray-100 dark:bg-zinc-800 text-gray-600 dark:text-gray-400'
                }`}>
                  {hooks.length}
                </span>
              </button>

              <button
                onClick={() => setActiveTab('scriptwriter')}
                className={`flex items-center gap-2 px-4 py-2 text-xs sm:text-sm font-semibold rounded-xl transition-all cursor-pointer ${
                  activeTab === 'scriptwriter'
                    ? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-zinc-800/60'
                }`}
              >
                <FaVideo className={activeTab === 'scriptwriter' ? 'text-blue-400 dark:text-blue-500 text-xs' : 'text-blue-500 text-xs'} />
                <span>AI Scriptwriter</span>
              </button>

              <button
                onClick={() => setActiveTab('bookmarks')}
                className={`flex items-center gap-2 px-4 py-2 text-xs sm:text-sm font-semibold rounded-xl transition-all cursor-pointer ${
                  activeTab === 'bookmarks'
                    ? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-zinc-800/60'
                }`}
              >
                <FaBookmark className={activeTab === 'bookmarks' ? 'text-rose-400 dark:text-rose-500 text-xs' : 'text-rose-500 text-xs'} />
                <span>Saved</span>
                {bookmarkedIds.size > 0 && (
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-mono font-bold ${
                    activeTab === 'bookmarks'
                      ? 'bg-white/20 text-white dark:bg-black/10 dark:text-gray-900'
                      : 'bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-300'
                  }`}>
                    {bookmarkedIds.size}
                  </span>
                )}
              </button>
            </div>
          </div>

        {/* ── TAB 1: VIRAL HOOK VAULT ── */}
        {activeTab === 'vault' && (
          <div className="space-y-6">
            {/* Filter & Search Bar */}
            <div className="bg-white/95 dark:bg-zinc-900/90 backdrop-blur-md p-4 sm:p-5 rounded-2xl border border-gray-200/80 dark:border-zinc-800/80 shadow-2xs space-y-4">
              <div className="flex flex-col md:flex-row md:items-center gap-3">
                {/* Search Input */}
                <div className="relative flex-1">
                  <FaSearch className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400 dark:text-zinc-500 text-xs" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search viral formulas (e.g. 'Stop doing', 'secret tool', '3 mistakes', 'blueprint')..."
                    className="w-full pl-9 pr-9 py-2.5 bg-gray-50/70 dark:bg-zinc-800/50 border border-gray-200 dark:border-zinc-700/80 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-zinc-500 transition-all"
                  />
                  {searchQuery && (
                    <button
                      onClick={() => setSearchQuery('')}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 cursor-pointer p-1"
                    >
                      <FaTimes className="text-xs" />
                    </button>
                  )}
                </div>

                {/* Niche Dropdown */}
                <div className="relative flex items-center gap-2 shrink-0">
                  <div className="relative">
                    <select
                      value={selectedNiche}
                      onChange={(e) => setSelectedNiche(e.target.value)}
                      className="appearance-none pl-9 pr-8 py-2.5 bg-gray-50/70 dark:bg-zinc-800/50 border border-gray-200 dark:border-zinc-700/80 rounded-xl text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 text-gray-800 dark:text-zinc-200 cursor-pointer transition-all"
                    >
                      {niches.map((n) => (
                        <option key={n.id} value={n.id}>
                          {NICHE_ICONS[n.id] ? `${NICHE_ICONS[n.id]} ${n.label}` : n.label}
                        </option>
                      ))}
                    </select>
                    <FaFilter className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-zinc-500 text-[10px] pointer-events-none" />
                    <FaChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-zinc-500 text-[10px] pointer-events-none" />
                  </div>
                </div>
              </div>

              {/* Category Pills Strip */}
              <div className="flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar pt-1">
                {categories.map((cat) => (
                  <button
                    key={cat.id}
                    onClick={() => setSelectedCategory(cat.id)}
                    className={`px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
                      selectedCategory === cat.id
                        ? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900 shadow-sm'
                        : 'bg-gray-100 dark:bg-zinc-800/80 text-gray-600 dark:text-gray-400 hover:bg-gray-200/80 dark:hover:bg-zinc-700/80 hover:text-gray-900 dark:hover:text-white'
                    }`}
                  >
                    {cat.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Hook Cards Grid */}
            {loadingHooks ? (
              <div className="py-24 text-center text-gray-400 dark:text-zinc-500">
                <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-3.5" />
                <p className="text-sm font-medium">Loading high-converting hook catalog...</p>
              </div>
            ) : hooks.length === 0 ? (
              <div className="py-20 text-center bg-white dark:bg-zinc-900/90 rounded-2xl border border-gray-200/80 dark:border-zinc-800 p-8 shadow-2xs">
                <div className="w-12 h-12 rounded-2xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200/60 dark:border-amber-800/40 flex items-center justify-center text-amber-500 mx-auto mb-3">
                  <FaBolt className="text-xl" />
                </div>
                <h3 className="text-base font-bold text-gray-900 dark:text-white">No matching hooks found</h3>
                <p className="text-xs text-gray-500 dark:text-zinc-400 mt-1 max-w-sm mx-auto">
                  Try refining your search keyword, changing the niche filter, or selecting "All Archetypes".
                </p>
                <button
                  onClick={() => {
                    setSelectedCategory('all');
                    setSelectedNiche('all');
                    setSearchQuery('');
                  }}
                  className="mt-5 px-4 py-2 bg-gray-900 hover:bg-gray-800 dark:bg-white dark:hover:bg-gray-100 text-white dark:text-gray-900 text-xs font-semibold rounded-xl cursor-pointer shadow-xs transition-all active:scale-95"
                >
                  Reset All Filters
                </button>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-5">
                  {hooks.slice(0, visibleCount).map((hook) => (
                    <div
                      key={hook.id}
                      className="group relative bg-white dark:bg-zinc-900/90 rounded-2xl border border-gray-200/80 dark:border-zinc-800/90 p-5 sm:p-6 shadow-2xs hover:shadow-md hover:border-amber-400/40 dark:hover:border-amber-500/30 transition-all duration-200 flex flex-col justify-between"
                    >
                      <div>
                        {/* Top Badges */}
                        <div className="flex items-center justify-between gap-2 mb-3.5">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="px-2.5 py-1 rounded-lg bg-gray-100 dark:bg-zinc-800 text-gray-600 dark:text-gray-300 text-[10px] font-bold uppercase tracking-wider">
                              {hook.category}
                            </span>
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 text-[10px] font-bold border border-amber-200/60 dark:border-amber-800/40">
                              <FaFire className="text-amber-500 text-[11px]" />
                              {hook.virality_score}% Virality
                            </span>
                          </div>

                          <button
                            onClick={() => handleToggleBookmark(hook.id)}
                            className="text-gray-400 hover:text-rose-500 dark:text-zinc-500 dark:hover:text-rose-400 transition-colors p-1.5 rounded-lg hover:bg-gray-50 dark:hover:bg-zinc-800 cursor-pointer"
                            title={bookmarkedIds.has(hook.id) ? 'Remove bookmark' : 'Save to bookmarks'}
                          >
                            {bookmarkedIds.has(hook.id) ? (
                              <FaBookmark className="text-rose-500 text-sm" />
                            ) : (
                              <FaRegBookmark className="text-sm" />
                            )}
                          </button>
                        </div>

                        {/* Hook Title */}
                        <h3 className="text-sm sm:text-base font-bold text-gray-900 dark:text-white mb-2.5 group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors">
                          {hook.title}
                        </h3>

                        {/* Formula / Template Box */}
                        <div className="relative p-3.5 bg-[#F8F8F6] dark:bg-zinc-800/40 rounded-xl border border-gray-200/70 dark:border-zinc-800 text-xs sm:text-sm font-mono text-gray-800 dark:text-gray-200 leading-relaxed mb-3 group-hover:border-amber-300/60 dark:group-hover:border-zinc-700 transition-colors">
                          <FaQuoteLeft className="text-gray-300 dark:text-zinc-700 text-xs mb-1.5" />
                          "{hook.template}"
                        </div>

                        {/* Live Example Box */}
                        <div className="text-xs text-gray-600 dark:text-gray-400 mb-4 bg-gray-50/60 dark:bg-zinc-800/20 p-2.5 rounded-lg border border-dashed border-gray-200/80 dark:border-zinc-800">
                          <span className="font-semibold text-gray-800 dark:text-gray-200">Live Example:</span> "{hook.example}"
                        </div>
                      </div>

                      {/* Footer Actions */}
                      <div className="pt-3.5 border-t border-gray-100 dark:border-zinc-800/80 flex items-center justify-between gap-2 flex-wrap">
                        <div className="flex items-center gap-1.5 text-gray-400 dark:text-zinc-500 text-xs font-mono">
                          <FaClock className="text-[10px]" />
                          <span>{hook.recommended_duration || '30s'}</span>
                        </div>

                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => handleOpenAutoFill(hook)}
                            className="px-2.5 py-1.5 bg-amber-50 hover:bg-amber-100/80 dark:bg-amber-950/40 dark:hover:bg-amber-900/50 text-amber-800 dark:text-amber-300 text-xs font-semibold rounded-xl border border-amber-200/60 dark:border-amber-800/40 flex items-center gap-1.5 transition-all cursor-pointer active:scale-95"
                            title="Personalize template with your topic"
                          >
                            <FaMagic className="text-[10px]" />
                            Personalize
                          </button>

                          <button
                            onClick={() => handleCopyText(hook.template, hook.id)}
                            className="px-2.5 py-1.5 bg-gray-100 hover:bg-gray-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-gray-700 dark:text-gray-300 text-xs font-medium rounded-xl flex items-center gap-1.5 transition-all cursor-pointer active:scale-95"
                            title="Copy template text"
                          >
                            {copiedId === hook.id ? (
                              <FaCheck className="text-emerald-500 text-xs" />
                            ) : (
                              <FaCopy className="text-xs" />
                            )}
                            {copiedId === hook.id ? 'Copied' : 'Copy'}
                          </button>

                          <button
                            onClick={() => handleUseInComposer(hook.example)}
                            className="px-3 py-1.5 bg-gray-900 hover:bg-gray-800 dark:bg-white dark:hover:bg-gray-100 text-white dark:text-gray-900 text-xs font-semibold rounded-xl flex items-center gap-1.5 transition-all shadow-xs cursor-pointer active:scale-95"
                            title="Send to Post Composer"
                          >
                            <span>Use</span>
                            <FaArrowRight className="text-[9px]" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Load More Trigger */}
                {hooks.length > visibleCount && (
                  <div className="text-center pt-6 pb-4">
                    <button
                      onClick={() => setVisibleCount((prev) => prev + 24)}
                      className="px-6 py-3 bg-white dark:bg-zinc-900 hover:bg-gray-50 dark:hover:bg-zinc-800 border border-gray-200 dark:border-zinc-700 text-gray-800 dark:text-gray-200 font-semibold text-xs rounded-xl shadow-xs transition-all cursor-pointer inline-flex items-center gap-2 active:scale-95"
                    >
                      <span>Load More Viral Hooks</span>
                      <span className="px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-950/50 text-amber-700 dark:text-amber-300 text-[10px] font-bold">
                        Showing {Math.min(visibleCount, hooks.length)} of {hooks.length}
                      </span>
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── TAB 2: AI SHORT-FORM SCRIPTWRITER ── */}
        {activeTab === 'scriptwriter' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            {/* Left Column: Storyboard Configurator */}
            <div className="lg:col-span-5 space-y-6">
              <div className="bg-white dark:bg-zinc-900/90 rounded-2xl border border-gray-200/80 dark:border-zinc-800 p-6 shadow-2xs space-y-5">
                <div>
                  <h2 className="text-base font-bold text-gray-900 dark:text-white flex items-center gap-2">
                    <FaVideo className="text-blue-500 text-sm" />
                    Short-Form Storyboard Generator
                  </h2>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 leading-relaxed">
                    Turns any idea into a timed 9:16 vertical video storyboard, 3 viral hooks, and teleprompter transcript.
                  </p>
                </div>

                {/* Topic Input */}
                <div className="space-y-1.5">
                  <label className="text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-300">
                    What is the video about?
                  </label>
                  <textarea
                    rows={3}
                    value={scriptTopic}
                    onChange={(e) => setScriptTopic(e.target.value)}
                    placeholder="e.g. 3 reasons your social posts are getting 0 views and how our automation tool fixes it in 2 minutes."
                    className="w-full p-3 bg-gray-50/70 dark:bg-zinc-800/60 border border-gray-200 dark:border-zinc-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-none text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-zinc-500 transition-all"
                  />
                </div>

                {/* Network Switcher */}
                <div className="space-y-1.5">
                  <label className="text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-300">
                    Target Network
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { id: 'tiktok', label: 'TikTok', icon: SiTiktok },
                      { id: 'reels', label: 'IG Reels', icon: SiInstagram },
                      { id: 'shorts', label: 'YT Shorts', icon: SiYoutube },
                    ].map((p) => {
                      const Icon = p.icon;
                      const isSelected = scriptPlatform === p.id;
                      return (
                        <button
                          key={p.id}
                          type="button"
                          onClick={() => setScriptPlatform(p.id)}
                          className={`flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl border text-xs font-semibold transition-all cursor-pointer ${
                            isSelected
                              ? 'bg-blue-50 dark:bg-blue-950/40 border-blue-500 text-blue-600 dark:text-blue-300 shadow-xs'
                              : 'bg-gray-50/70 dark:bg-zinc-800/40 border-gray-200 dark:border-zinc-700/80 text-gray-600 dark:text-gray-400 hover:border-gray-300 dark:hover:border-zinc-600'
                          }`}
                        >
                          <Icon className="text-xs" /> {p.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Niche Target */}
                <div className="space-y-1.5">
                  <label className="text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-300">
                    Content Niche & Visual Cues
                  </label>
                  <div className="relative">
                    <select
                      value={scriptNiche}
                      onChange={(e) => setScriptNiche(e.target.value)}
                      className="w-full appearance-none pl-3 pr-8 py-2.5 bg-gray-50/70 dark:bg-zinc-800/60 border border-gray-200 dark:border-zinc-700/80 rounded-xl text-xs font-semibold text-gray-800 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 cursor-pointer transition-all"
                    >
                      {niches
                        .filter((n) => n.id !== 'all')
                        .map((n) => (
                          <option key={n.id} value={n.id}>
                            {NICHE_ICONS[n.id] ? `${NICHE_ICONS[n.id]} ${n.label}` : n.label}
                          </option>
                        ))}
                    </select>
                    <FaChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-zinc-500 text-[10px] pointer-events-none" />
                  </div>
                </div>

                {/* Duration & Hook Style */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-300">
                      Duration
                    </label>
                    <div className="flex gap-1.5">
                      {['15s', '30s', '60s'].map((dur) => (
                        <button
                          key={dur}
                          type="button"
                          onClick={() => setScriptDuration(dur)}
                          className={`flex-1 py-1.5 text-xs font-semibold rounded-xl border transition-all cursor-pointer ${
                            scriptDuration === dur
                              ? 'bg-gray-900 dark:bg-white text-white dark:text-gray-900 border-transparent shadow-xs'
                              : 'bg-gray-50/70 dark:bg-zinc-800/60 border-gray-200 dark:border-zinc-700/80 text-gray-600 dark:text-gray-400 hover:border-gray-300'
                          }`}
                        >
                          {dur}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-300">
                      Hook Style
                    </label>
                    <div className="relative">
                      <select
                        value={scriptHookStyle}
                        onChange={(e) => setScriptHookStyle(e.target.value)}
                        className="w-full appearance-none pl-3 pr-7 py-1.5 bg-gray-50/70 dark:bg-zinc-800/60 border border-gray-200 dark:border-zinc-700/80 rounded-xl text-xs font-semibold text-gray-800 dark:text-zinc-200 focus:outline-none focus:border-blue-500 cursor-pointer"
                      >
                        <option value="contrarian">Contrarian / Myth</option>
                        <option value="mistake">Mistake / Warning</option>
                        <option value="curiosity">Curiosity / Secret</option>
                        <option value="how_to">Step-by-Step</option>
                        <option value="roi_numbers">Numbers & Proof</option>
                      </select>
                      <FaChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 dark:text-zinc-500 text-[10px] pointer-events-none" />
                    </div>
                  </div>
                </div>

                {/* Generate Button */}
                <button
                  onClick={handleGenerateScript}
                  disabled={generatingScript || !scriptTopic.trim()}
                  className="w-full py-3 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 text-white text-sm font-bold rounded-xl flex items-center justify-center gap-2 shadow-md shadow-blue-500/20 transition-all cursor-pointer active:scale-95"
                >
                  {generatingScript ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      <span>Crafting Storyboard & Script...</span>
                    </>
                  ) : (
                    <>
                      <FaMagic className="text-xs" />
                      <span>Generate Viral Storyboard</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Right Column: Output Viewer */}
            <div className="lg:col-span-7 space-y-6">
              {!scriptResult ? (
                <div className="h-full min-h-[440px] bg-white/70 dark:bg-zinc-900/60 rounded-2xl border border-dashed border-gray-300 dark:border-zinc-800 flex flex-col items-center justify-center p-8 text-center">
                  <div className="w-14 h-14 rounded-2xl bg-blue-50 dark:bg-blue-950/40 border border-blue-200/60 dark:border-blue-800/40 flex items-center justify-center text-blue-500 mb-4 text-xl">
                    <FaVideo />
                  </div>
                  <h3 className="text-base font-bold text-gray-800 dark:text-zinc-200">No Script Generated Yet</h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400 max-w-md mt-1.5 leading-relaxed">
                    Enter your topic on the left and select your duration to build a complete 9:16 short-form storyboard, audio cues, and teleprompter transcript.
                  </p>
                </div>
              ) : (
                <div className="bg-white dark:bg-zinc-900/90 rounded-2xl border border-gray-200/80 dark:border-zinc-800 p-6 shadow-2xs space-y-6">
                  {/* Header & Send Button */}
                  <div className="flex items-center justify-between pb-4 border-b border-gray-100 dark:border-zinc-800/80 gap-3">
                    <div>
                      <span className="text-[10px] font-bold text-blue-600 dark:text-blue-400 uppercase tracking-wider">
                        {scriptResult.provider ? `Engine: ${scriptResult.provider}` : 'Viral Short-Form Blueprint'}
                      </span>
                      <h2 className="text-lg font-bold text-gray-900 dark:text-white mt-0.5">{scriptResult.title}</h2>
                    </div>

                    <button
                      onClick={handleSendScriptToComposer}
                      className="px-4 py-2 bg-gray-900 hover:bg-gray-800 dark:bg-white dark:hover:bg-gray-100 text-white dark:text-gray-900 text-xs font-bold rounded-xl flex items-center gap-1.5 shadow-sm transition-all cursor-pointer active:scale-95 shrink-0"
                    >
                      <span>Schedule in Composer</span>
                      <FaArrowRight className="text-[10px]" />
                    </button>
                  </div>

                  {/* 3 Hook Options */}
                  {scriptResult.hooks && scriptResult.hooks.length > 0 && (
                    <div className="space-y-2">
                      <label className="text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-400">
                        Select Primary Hook (0:00 - 0:03)
                      </label>
                      <div className="space-y-2">
                        {scriptResult.hooks.map((h, i) => (
                          <div
                            key={i}
                            onClick={() => {
                              setSelectedHookIndex(i);
                              setScriptResult((prev) => ({ ...prev, selected_hook: h }));
                            }}
                            className={`p-3 rounded-xl border text-xs font-medium cursor-pointer transition-all flex items-center justify-between gap-2 ${
                              selectedHookIndex === i
                                ? 'bg-amber-50 dark:bg-amber-950/40 border-amber-400 text-amber-900 dark:text-amber-200 shadow-2xs'
                                : 'bg-gray-50/70 dark:bg-zinc-800/40 border-gray-200 dark:border-zinc-700/80 text-gray-700 dark:text-gray-300 hover:border-amber-300'
                            }`}
                          >
                            <span>"{h}"</span>
                            {selectedHookIndex === i && <FaCheck className="text-amber-600 shrink-0" />}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Timed Storyboard Beats */}
                  <div className="space-y-3">
                    <label className="text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-400">
                      Visual Storyboard & Shot Breakdown
                    </label>
                    <div className="space-y-3">
                      {scriptResult.storyboard.map((beat, idx) => (
                        <div
                          key={idx}
                          className="p-4 bg-[#F8F8F6] dark:bg-zinc-800/40 rounded-xl border border-gray-200/80 dark:border-zinc-700/80 space-y-2.5"
                        >
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-mono font-bold text-blue-600 dark:text-blue-400 flex items-center gap-1.5">
                              <FaClock className="text-[10px]" /> {beat.timestamp}
                            </span>
                            <span className="px-2 py-0.5 bg-gray-200/80 dark:bg-zinc-700 rounded-md text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                              {beat.stage}
                            </span>
                          </div>

                          <div className="text-xs text-gray-700 dark:text-gray-300 flex items-start gap-1.5">
                            <FaVideo className="text-blue-500 text-[11px] mt-0.5 shrink-0" />
                            <div>
                              <strong className="text-gray-900 dark:text-white">Visual Action:</strong> {beat.visual_cue}
                            </div>
                          </div>

                          {beat.on_screen_text && (
                            <div className="text-xs text-gray-700 dark:text-gray-300 flex items-start gap-1.5">
                              <FaFont className="text-amber-500 text-[11px] mt-0.5 shrink-0" />
                              <div>
                                <strong className="text-gray-900 dark:text-white">Text Overlay:</strong>{' '}
                                <span className="font-mono bg-gray-200/70 dark:bg-zinc-700 px-1.5 py-0.5 rounded text-[11px] text-gray-800 dark:text-gray-200">
                                  {beat.on_screen_text}
                                </span>
                              </div>
                            </div>
                          )}

                          <div className="p-3 bg-white dark:bg-zinc-900 rounded-lg border border-gray-200/60 dark:border-zinc-800 text-xs font-medium text-gray-800 dark:text-gray-200 flex items-start gap-2">
                            <FaCommentDots className="text-gray-400 text-xs mt-0.5 shrink-0" />
                            <span>"{beat.spoken_dialogue}"</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Teleprompter Script */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-400">
                        Full Teleprompter Transcript
                      </label>
                      <button
                        onClick={() => handleCopyText(scriptResult.full_script, 'full_script')}
                        className="text-xs text-blue-600 dark:text-blue-400 font-semibold hover:underline flex items-center gap-1 cursor-pointer"
                      >
                        <FaCopy className="text-[10px]" /> Copy Script
                      </button>
                    </div>
                    <div className="p-4 bg-gray-900 text-gray-100 rounded-xl font-mono text-xs leading-relaxed max-h-48 overflow-y-auto border border-gray-800 shadow-inner">
                      {scriptResult.full_script}
                    </div>
                  </div>

                  {/* Hashtags */}
                  {scriptResult.recommended_hashtags && (
                    <div className="flex flex-wrap gap-1.5 pt-2">
                      {scriptResult.recommended_hashtags.map((tag, i) => (
                        <span
                          key={i}
                          className="px-2.5 py-1 bg-gray-100 dark:bg-zinc-800 text-gray-600 dark:text-gray-400 rounded-lg text-xs font-mono font-medium"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── TAB 3: SAVED BOOKMARKS ── */}
        {activeTab === 'bookmarks' && (
          <div className="space-y-6">
            {bookmarkedIds.size === 0 ? (
              <div className="py-20 text-center bg-white dark:bg-zinc-900/90 rounded-2xl border border-gray-200/80 dark:border-zinc-800 p-8 shadow-2xs">
                <div className="w-12 h-12 rounded-2xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200/60 dark:border-rose-800/40 flex items-center justify-center text-rose-500 mx-auto mb-3">
                  <FaRegBookmark className="text-xl" />
                </div>
                <h3 className="text-base font-bold text-gray-900 dark:text-white">No Saved Bookmarks Yet</h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-sm mx-auto leading-relaxed">
                  Click the bookmark icon on any viral hook card in the Hook Vault to save your top performing formulas here.
                </p>
                <button
                  onClick={() => setActiveTab('vault')}
                  className="mt-5 px-4 py-2 bg-gray-900 hover:bg-gray-800 dark:bg-white dark:hover:bg-gray-100 text-white dark:text-gray-900 text-xs font-semibold rounded-xl cursor-pointer shadow-xs transition-all active:scale-95"
                >
                  Browse Hook Vault
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-5">
                {hooks
                  .filter((h) => bookmarkedIds.has(h.id))
                  .map((hook) => (
                    <div
                      key={hook.id}
                      className="bg-white dark:bg-zinc-900/90 rounded-2xl border border-gray-200/80 dark:border-zinc-800 p-5 sm:p-6 shadow-2xs space-y-3.5"
                    >
                      <div className="flex items-center justify-between">
                        <span className="px-2.5 py-1 rounded-lg bg-gray-100 dark:bg-zinc-800 text-gray-600 dark:text-gray-300 text-[10px] font-bold uppercase tracking-wider">
                          {hook.category}
                        </span>
                        <button
                          onClick={() => handleToggleBookmark(hook.id)}
                          className="text-rose-500 hover:text-rose-600 p-1 cursor-pointer transition-transform active:scale-90"
                          title="Remove from saved"
                        >
                          <FaBookmark className="text-sm" />
                        </button>
                      </div>
                      <h4 className="text-sm sm:text-base font-bold text-gray-900 dark:text-white">{hook.title}</h4>
                      <p className="text-xs sm:text-sm font-mono bg-[#F8F8F6] dark:bg-zinc-800/50 p-3.5 rounded-xl text-gray-800 dark:text-zinc-200 border border-gray-200/70 dark:border-zinc-800 leading-relaxed">
                        "{hook.template}"
                      </p>
                      <div className="flex justify-end gap-2 pt-2">
                        <button
                          onClick={() => handleCopyText(hook.template, hook.id)}
                          className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 text-gray-700 dark:text-gray-300 text-xs font-medium rounded-xl transition-all cursor-pointer active:scale-95"
                        >
                          {copiedId === hook.id ? 'Copied' : 'Copy'}
                        </button>
                        <button
                          onClick={() => handleUseInComposer(hook.example)}
                          className="px-3.5 py-1.5 bg-gray-900 hover:bg-gray-800 dark:bg-white dark:hover:bg-gray-100 text-white dark:text-gray-900 text-xs font-semibold rounded-xl flex items-center gap-1.5 shadow-xs transition-all cursor-pointer active:scale-95"
                        >
                          <span>Use in Post</span>
                          <FaArrowRight className="text-[10px]" />
                        </button>
                      </div>
                    </div>
                  ))}
              </div>
            )}
          </div>
        )}

        {/* ── MODAL: AUTO-FILL / PERSONALIZE HOOK ── */}
        {autoFillModal.open && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-fade-in">
            <div className="w-full max-w-lg bg-white dark:bg-zinc-900 rounded-3xl border border-gray-200 dark:border-zinc-800 p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-gray-100 dark:border-zinc-800">
                <h3 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-2">
                  <FaMagic className="text-amber-500 text-xs" /> Personalize Viral Hook
                </h3>
                <button
                  onClick={() => setAutoFillModal({ open: false, hook: null, topic: '', results: [], loading: false })}
                  className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors cursor-pointer"
                >
                  <FaTimes className="text-xs" />
                </button>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Template Formula:</label>
                <div className="p-3 bg-[#F8F8F6] dark:bg-zinc-800/50 rounded-xl text-xs font-mono text-gray-800 dark:text-zinc-200 border border-gray-200/80 dark:border-zinc-700/80 leading-relaxed">
                  "{autoFillModal.hook?.template}"
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-bold text-gray-700 dark:text-gray-300">
                  Your Specific Topic, Niche, or Brand:
                </label>
                <input
                  type="text"
                  value={autoFillModal.topic}
                  onChange={(e) => setAutoFillModal((prev) => ({ ...prev, topic: e.target.value }))}
                  placeholder="e.g. B2B LinkedIn prospecting, Shopify dropshipping, morning workouts..."
                  className="w-full p-2.5 bg-gray-50/70 dark:bg-zinc-800/60 border border-gray-200 dark:border-zinc-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 text-gray-900 dark:text-white placeholder-gray-400 transition-all"
                />
              </div>

              <button
                onClick={handleRunAutoFill}
                disabled={autoFillModal.loading || !autoFillModal.topic.trim()}
                className="w-full py-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-bold text-xs rounded-xl flex items-center justify-center gap-2 shadow-sm transition-all cursor-pointer active:scale-95"
              >
                {autoFillModal.loading ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>Generating Variations...</span>
                  </>
                ) : (
                  <>
                    <FaMagic className="text-xs" />
                    <span>Generate 3 Custom Hooks</span>
                  </>
                )}
              </button>

              {autoFillModal.results.length > 0 && (
                <div className="space-y-2 pt-3 border-t border-gray-100 dark:border-zinc-800">
                  <label className="text-xs font-bold text-gray-600 dark:text-gray-400">Custom Variations:</label>
                  {autoFillModal.results.map((varText, idx) => (
                    <div
                      key={idx}
                      className="p-3 bg-[#F8F8F6] dark:bg-zinc-800/60 rounded-xl border border-gray-200 dark:border-zinc-700 text-xs font-medium text-gray-800 dark:text-zinc-200 flex items-center justify-between gap-3"
                    >
                      <span>"{varText}"</span>
                      <button
                        onClick={() => {
                          handleUseInComposer(varText);
                        }}
                        className="px-2.5 py-1.5 bg-gray-900 hover:bg-gray-800 dark:bg-white dark:hover:bg-gray-100 text-white dark:text-gray-900 text-[11px] font-bold rounded-lg whitespace-nowrap cursor-pointer shadow-2xs active:scale-95 transition-all"
                      >
                        Use in Post →
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
        </div>
      </div>
    </DashboardLayout>
  );
}
