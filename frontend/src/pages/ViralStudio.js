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
} from 'react-icons/fa';
import { SiTiktok, SiInstagram, SiYoutube } from 'react-icons/si';

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
    navigate('/create', { state: { initialCaption: text } });
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
    navigate('/create', { state: { initialCaption: finalPost } });
  };

  return (
    <DashboardLayout>
      <div className="min-h-screen bg-[#FDFBF7] dark:bg-[#09090B] text-zinc-900 dark:text-zinc-100 py-8 px-4 sm:px-6 lg:px-10 transition-colors">
        {/* Top Header */}
        <div className="max-w-7xl mx-auto mb-8">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-zinc-200/80 dark:border-zinc-800">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-50 dark:bg-amber-950/40 border border-amber-200/60 dark:border-amber-800/40 text-amber-800 dark:text-amber-300 text-xs font-semibold uppercase tracking-wider mb-2">
                <FaBolt className="text-amber-500 text-[10px]" />
                Short-Form Intelligence & Viral Hooks
              </div>
              <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-zinc-900 dark:text-white font-sans">
                Viral Studio
              </h1>
              <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1 max-w-2xl">
                Curated library of 120+ battle-tested short-form hooks and automated 9:16 video script generator for TikTok, Reels & Shorts.
              </p>
            </div>

            {/* Navigation Tabs */}
            <div className="flex items-center bg-zinc-200/60 dark:bg-zinc-800/60 p-1 rounded-xl border border-zinc-300/40 dark:border-zinc-700/50">
              <button
                onClick={() => setActiveTab('vault')}
                className={`flex items-center gap-2 px-4 py-2 text-xs sm:text-sm font-medium rounded-lg transition-all cursor-pointer ${
                  activeTab === 'vault'
                    ? 'bg-white dark:bg-zinc-900 text-zinc-900 dark:text-white shadow-sm'
                    : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white'
                }`}
              >
                <FaBolt className="text-amber-500 text-xs" />
                Hook Vault ({hooks.length})
              </button>
              <button
                onClick={() => setActiveTab('scriptwriter')}
                className={`flex items-center gap-2 px-4 py-2 text-xs sm:text-sm font-medium rounded-lg transition-all cursor-pointer ${
                  activeTab === 'scriptwriter'
                    ? 'bg-white dark:bg-zinc-900 text-zinc-900 dark:text-white shadow-sm'
                    : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white'
                }`}
              >
                <FaVideo className="text-indigo-500 text-xs" />
                AI Video Scriptwriter
              </button>
              <button
                onClick={() => setActiveTab('bookmarks')}
                className={`flex items-center gap-2 px-4 py-2 text-xs sm:text-sm font-medium rounded-lg transition-all cursor-pointer ${
                  activeTab === 'bookmarks'
                    ? 'bg-white dark:bg-zinc-900 text-zinc-900 dark:text-white shadow-sm'
                    : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white'
                }`}
              >
                <FaBookmark className="text-rose-500 text-xs" />
                Saved ({bookmarkedIds.size})
              </button>
            </div>
          </div>
        </div>

        {/* ── TAB 1: VIRAL HOOK VAULT ── */}
        {activeTab === 'vault' && (
          <div className="max-w-7xl mx-auto space-y-6">
            {/* Filter Bar */}
            <div className="bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md p-4 sm:p-5 rounded-2xl border border-zinc-200/80 dark:border-zinc-800/80 shadow-sm space-y-4">
              <div className="flex flex-col md:flex-row md:items-center gap-3">
                {/* Search */}
                <div className="relative flex-1">
                  <FaSearch className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-400 text-xs" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search hooks (e.g. 'Stop doing', 'mistake', 'secret tool', 'framework')..."
                    className="w-full pl-9 pr-4 py-2.5 bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500 text-zinc-900 dark:text-white placeholder-zinc-400"
                  />
                </div>

                {/* Niche Dropdown */}
                <div className="flex items-center gap-2">
                  <label className="text-xs font-semibold text-zinc-500 uppercase tracking-wider whitespace-nowrap">
                    Niche:
                  </label>
                  <select
                    value={selectedNiche}
                    onChange={(e) => setSelectedNiche(e.target.value)}
                    className="px-3 py-2 bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700 rounded-xl text-xs font-medium focus:outline-none focus:border-amber-500 text-zinc-800 dark:text-zinc-200 cursor-pointer"
                  >
                    {niches.map((n) => (
                      <option key={n.id} value={n.id}>
                        {n.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Category Pills */}
              <div className="flex items-center gap-1.5 overflow-x-auto pb-1 no-scrollbar">
                {categories.map((cat) => (
                  <button
                    key={cat.id}
                    onClick={() => setSelectedCategory(cat.id)}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-all cursor-pointer ${
                      selectedCategory === cat.id
                        ? 'bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 shadow-sm'
                        : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-700'
                    }`}
                  >
                    {cat.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Hook Cards Grid */}
            {loadingHooks ? (
              <div className="py-20 text-center text-zinc-400">
                <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <p className="text-sm font-medium">Loading viral templates...</p>
              </div>
            ) : hooks.length === 0 ? (
              <div className="py-16 text-center bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 p-8">
                <FaBolt className="text-zinc-300 text-3xl mx-auto mb-3" />
                <p className="text-base font-semibold text-zinc-700 dark:text-zinc-300">No matching hooks found</p>
                <p className="text-xs text-zinc-400 mt-1">Try clearing your search query or selecting a different category.</p>
                <button
                  onClick={() => {
                    setSelectedCategory('all');
                    setSelectedNiche('all');
                    setSearchQuery('');
                  }}
                  className="mt-4 px-4 py-2 bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 text-xs font-medium rounded-xl cursor-pointer"
                >
                  Reset Filters
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
                {hooks.map((hook) => (
                  <div
                    key={hook.id}
                    className="group relative bg-white dark:bg-zinc-900/90 rounded-2xl border border-zinc-200/80 dark:border-zinc-800 p-5 shadow-sm hover:shadow-md hover:border-amber-400/40 transition-all flex flex-col justify-between"
                  >
                    <div>
                      {/* Top Badges */}
                      <div className="flex items-center justify-between gap-2 mb-3">
                        <div className="flex items-center gap-2">
                          <span className="px-2.5 py-0.5 rounded-full bg-amber-50 dark:bg-amber-950/50 text-amber-700 dark:text-amber-300 text-[10px] font-bold uppercase tracking-wider border border-amber-200/50 dark:border-amber-800/30">
                            {hook.category}
                          </span>
                          <span className="px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300 text-[10px] font-semibold">
                            🔥 {hook.virality_score}% Virality
                          </span>
                        </div>

                        <button
                          onClick={() => handleToggleBookmark(hook.id)}
                          className="text-zinc-400 hover:text-rose-500 transition-colors p-1 cursor-pointer"
                          title="Save to bookmarks"
                        >
                          {bookmarkedIds.has(hook.id) ? (
                            <FaBookmark className="text-rose-500 text-sm" />
                          ) : (
                            <FaRegBookmark className="text-sm" />
                          )}
                        </button>
                      </div>

                      {/* Hook Title & Template */}
                      <h3 className="text-sm font-bold text-zinc-900 dark:text-white mb-2">{hook.title}</h3>
                      <div className="p-3 bg-zinc-50 dark:bg-zinc-800/40 rounded-xl border border-zinc-100 dark:border-zinc-800 text-xs font-mono text-zinc-800 dark:text-zinc-200 leading-relaxed mb-3">
                        "{hook.template}"
                      </div>

                      {/* Real Example */}
                      <div className="text-xs text-zinc-500 dark:text-zinc-400 mb-4">
                        <span className="font-semibold text-zinc-700 dark:text-zinc-300">Live Example:</span> "{hook.example}"
                      </div>
                    </div>

                    {/* Footer Actions */}
                    <div className="pt-3 border-t border-zinc-100 dark:border-zinc-800 flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 text-zinc-400 text-xs">
                        <FaClock className="text-[10px]" />
                        <span>{hook.recommended_duration || '30s'}</span>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleOpenAutoFill(hook)}
                          className="px-3 py-1.5 bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 hover:bg-amber-100 text-xs font-semibold rounded-lg border border-amber-200/60 dark:border-amber-800/40 flex items-center gap-1.5 transition-colors cursor-pointer"
                        >
                          <FaMagic className="text-[10px]" />
                          Personalize
                        </button>
                        <button
                          onClick={() => handleCopyText(hook.template, hook.id)}
                          className="px-3 py-1.5 bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 text-xs font-medium rounded-lg flex items-center gap-1.5 transition-colors cursor-pointer"
                        >
                          {copiedId === hook.id ? <FaCheck className="text-emerald-500" /> : <FaCopy className="text-xs" />}
                          {copiedId === hook.id ? 'Copied' : 'Copy'}
                        </button>
                        <button
                          onClick={() => handleUseInComposer(hook.example)}
                          className="px-3 py-1.5 bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 hover:bg-zinc-800 text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors shadow-sm cursor-pointer"
                        >
                          Use <FaArrowRight className="text-[10px]" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── TAB 2: AI SHORT-FORM SCRIPTWRITER ── */}
        {activeTab === 'scriptwriter' && (
          <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8">
            {/* Left Column: Creator Configuration */}
            <div className="lg:col-span-5 space-y-6">
              <div className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200/80 dark:border-zinc-800 p-6 shadow-sm space-y-5">
                <div>
                  <h2 className="text-base font-bold text-zinc-900 dark:text-white flex items-center gap-2">
                    <FaVideo className="text-indigo-500" />
                    Short-Form Storyboard Generator
                  </h2>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
                    Turns any topic or concept into a timed 9:16 visual storyboard and teleprompter script.
                  </p>
                </div>

                {/* Topic Input */}
                <div className="space-y-1.5">
                  <label className="text-xs font-bold uppercase tracking-wider text-zinc-700 dark:text-zinc-300">
                    What is the video about?
                  </label>
                  <textarea
                    rows={3}
                    value={scriptTopic}
                    onChange={(e) => setScriptTopic(e.target.value)}
                    placeholder="e.g. 3 reasons your social posts are getting 0 views and how our automation tool fixes it in 2 minutes."
                    className="w-full p-3 bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 resize-none text-zinc-900 dark:text-white"
                  />
                </div>

                {/* Platform Target */}
                <div className="space-y-1.5">
                  <label className="text-xs font-bold uppercase tracking-wider text-zinc-700 dark:text-zinc-300">
                    Target Network
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { id: 'tiktok', label: 'TikTok', icon: SiTiktok },
                      { id: 'reels', label: 'IG Reels', icon: SiInstagram },
                      { id: 'shorts', label: 'YT Shorts', icon: SiYoutube },
                    ].map((p) => {
                      const Icon = p.icon;
                      return (
                        <button
                          key={p.id}
                          type="button"
                          onClick={() => setScriptPlatform(p.id)}
                          className={`flex items-center justify-center gap-2 py-2 px-3 rounded-xl border text-xs font-semibold transition-all cursor-pointer ${
                            scriptPlatform === p.id
                              ? 'bg-indigo-50 dark:bg-indigo-950/50 border-indigo-500 text-indigo-600 dark:text-indigo-300 shadow-sm'
                              : 'bg-zinc-50 dark:bg-zinc-800/40 border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400'
                          }`}
                        >
                          <Icon /> {p.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Duration & Hook Style */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-xs font-bold uppercase tracking-wider text-zinc-700 dark:text-zinc-300">
                      Duration
                    </label>
                    <div className="flex gap-1.5">
                      {['15s', '30s', '60s'].map((dur) => (
                        <button
                          key={dur}
                          type="button"
                          onClick={() => setScriptDuration(dur)}
                          className={`flex-1 py-1.5 text-xs font-semibold rounded-lg border transition-all cursor-pointer ${
                            scriptDuration === dur
                              ? 'bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 border-transparent shadow-sm'
                              : 'bg-zinc-50 dark:bg-zinc-800 border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400'
                          }`}
                        >
                          {dur}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-bold uppercase tracking-wider text-zinc-700 dark:text-zinc-300">
                      Hook Style
                    </label>
                    <select
                      value={scriptHookStyle}
                      onChange={(e) => setScriptHookStyle(e.target.value)}
                      className="w-full py-1.5 px-2.5 bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-lg text-xs font-medium text-zinc-800 dark:text-zinc-200 focus:outline-none cursor-pointer"
                    >
                      <option value="contrarian">Contrarian / Myth</option>
                      <option value="mistake">Mistake / Warning</option>
                      <option value="curiosity">Curiosity / Secret</option>
                      <option value="how_to">Step-by-Step Blueprint</option>
                      <option value="roi_numbers">Numbers & Proof</option>
                    </select>
                  </div>
                </div>

                {/* Generate Button */}
                <button
                  onClick={handleGenerateScript}
                  disabled={generatingScript || !scriptTopic.trim()}
                  className="w-full py-3 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 disabled:opacity-50 text-white text-sm font-bold rounded-xl flex items-center justify-center gap-2 shadow-md transition-all cursor-pointer"
                >
                  {generatingScript ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Generating Storyboard...
                    </>
                  ) : (
                    <>
                      <FaMagic /> Generate Viral Script
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Right Column: Output Viewer */}
            <div className="lg:col-span-7 space-y-6">
              {!scriptResult ? (
                <div className="h-full min-h-[420px] bg-white/60 dark:bg-zinc-900/60 rounded-2xl border border-dashed border-zinc-300 dark:border-zinc-800 flex flex-col items-center justify-center p-8 text-center">
                  <div className="w-14 h-14 rounded-2xl bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-100 dark:border-indigo-800/40 flex items-center justify-center text-indigo-500 mb-4 text-xl">
                    <FaVideo />
                  </div>
                  <h3 className="text-base font-bold text-zinc-800 dark:text-zinc-200">No Script Generated Yet</h3>
                  <p className="text-xs text-zinc-500 max-w-md mt-1">
                    Enter your video idea on the left and choose your target duration to generate a 3-second hook, visual storyboard, and teleprompter transcript.
                  </p>
                </div>
              ) : (
                <div className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200/80 dark:border-zinc-800 p-6 shadow-sm space-y-6">
                  {/* Header & Send Button */}
                  <div className="flex items-center justify-between pb-4 border-b border-zinc-100 dark:border-zinc-800">
                    <div>
                      <span className="text-[10px] font-bold text-indigo-600 uppercase tracking-wider">
                        {scriptResult.provider ? `Engine: ${scriptResult.provider}` : 'Viral Blueprint'}
                      </span>
                      <h2 className="text-lg font-bold text-zinc-900 dark:text-white">{scriptResult.title}</h2>
                    </div>

                    <button
                      onClick={handleSendScriptToComposer}
                      className="px-4 py-2 bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 text-xs font-bold rounded-xl flex items-center gap-1.5 hover:scale-[1.02] transition-all shadow-sm cursor-pointer"
                    >
                      Schedule in Composer <FaArrowRight className="text-[10px]" />
                    </button>
                  </div>

                  {/* 3 Hook Options */}
                  {scriptResult.hooks && scriptResult.hooks.length > 0 && (
                    <div className="space-y-2">
                      <label className="text-xs font-bold uppercase tracking-wider text-zinc-600 dark:text-zinc-400">
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
                            className={`p-3 rounded-xl border text-xs font-medium cursor-pointer transition-all flex items-center justify-between ${
                              selectedHookIndex === i
                                ? 'bg-amber-50 dark:bg-amber-950/40 border-amber-400/60 text-amber-900 dark:text-amber-200 shadow-sm'
                                : 'bg-zinc-50 dark:bg-zinc-800/40 border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300 hover:border-amber-300'
                            }`}
                          >
                            <span>"{h}"</span>
                            {selectedHookIndex === i && <FaCheck className="text-amber-600 flex-shrink-0" />}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Timed Storyboard Beats */}
                  <div className="space-y-3">
                    <label className="text-xs font-bold uppercase tracking-wider text-zinc-600 dark:text-zinc-400">
                      Visual Storyboard & Shot Breakdown
                    </label>
                    <div className="space-y-3">
                      {scriptResult.storyboard.map((beat, idx) => (
                        <div
                          key={idx}
                          className="p-4 bg-zinc-50/80 dark:bg-zinc-800/50 rounded-xl border border-zinc-200/70 dark:border-zinc-700/60 space-y-2"
                        >
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400 flex items-center gap-1.5">
                              <FaClock className="text-[10px]" /> {beat.timestamp}
                            </span>
                            <span className="px-2 py-0.5 bg-zinc-200 dark:bg-zinc-700 rounded text-[10px] font-bold text-zinc-700 dark:text-zinc-300 uppercase">
                              {beat.stage}
                            </span>
                          </div>

                          <div className="text-xs text-zinc-600 dark:text-zinc-300">
                            <strong className="text-zinc-900 dark:text-white">🎥 Action:</strong> {beat.visual_cue}
                          </div>

                          {beat.on_screen_text && (
                            <div className="text-xs text-zinc-600 dark:text-zinc-300">
                              <strong className="text-zinc-900 dark:text-white">📱 Text Overlay:</strong>{' '}
                              <span className="font-mono bg-zinc-200/80 dark:bg-zinc-700 px-1.5 py-0.5 rounded text-[11px]">
                                {beat.on_screen_text}
                              </span>
                            </div>
                          )}

                          <div className="p-2.5 bg-white dark:bg-zinc-900 rounded-lg border border-zinc-200/60 dark:border-zinc-800 text-xs font-medium text-zinc-800 dark:text-zinc-200">
                            💬 "{beat.spoken_dialogue}"
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Teleprompter Script */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold uppercase tracking-wider text-zinc-600 dark:text-zinc-400">
                        Full Teleprompter Transcript
                      </label>
                      <button
                        onClick={() => handleCopyText(scriptResult.full_script, 'full_script')}
                        className="text-xs text-indigo-600 dark:text-indigo-400 font-semibold hover:underline flex items-center gap-1 cursor-pointer"
                      >
                        <FaCopy /> Copy Script
                      </button>
                    </div>
                    <div className="p-4 bg-zinc-900 text-zinc-100 rounded-xl font-mono text-xs leading-relaxed max-h-48 overflow-y-auto">
                      {scriptResult.full_script}
                    </div>
                  </div>

                  {/* Hashtags */}
                  {scriptResult.recommended_hashtags && (
                    <div className="flex flex-wrap gap-1.5 pt-2">
                      {scriptResult.recommended_hashtags.map((tag, i) => (
                        <span
                          key={i}
                          className="px-2 py-1 bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 rounded-lg text-xs font-mono"
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

        {/* ── TAB 3: BOOKMARKS ── */}
        {activeTab === 'bookmarks' && (
          <div className="max-w-7xl mx-auto">
            {bookmarkedIds.size === 0 ? (
              <div className="py-20 text-center bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 p-8">
                <FaRegBookmark className="text-zinc-300 text-3xl mx-auto mb-3" />
                <h3 className="text-base font-semibold text-zinc-800 dark:text-zinc-200">No Saved Bookmarks Yet</h3>
                <p className="text-xs text-zinc-400 mt-1 max-w-sm mx-auto">
                  Click the bookmark icon on any viral hook card in the Hook Vault to save your favorites here.
                </p>
                <button
                  onClick={() => setActiveTab('vault')}
                  className="mt-4 px-4 py-2 bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 text-xs font-semibold rounded-xl cursor-pointer"
                >
                  Browse Hook Vault
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {hooks
                  .filter((h) => bookmarkedIds.has(h.id))
                  .map((hook) => (
                    <div
                      key={hook.id}
                      className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 p-5 shadow-sm space-y-3"
                    >
                      <div className="flex items-center justify-between">
                        <span className="px-2.5 py-0.5 rounded-full bg-amber-50 dark:bg-amber-950/50 text-amber-700 dark:text-amber-300 text-[10px] font-bold uppercase">
                          {hook.category}
                        </span>
                        <button onClick={() => handleToggleBookmark(hook.id)} className="text-rose-500 cursor-pointer">
                          <FaBookmark />
                        </button>
                      </div>
                      <h4 className="text-sm font-bold text-zinc-900 dark:text-white">{hook.title}</h4>
                      <p className="text-xs font-mono bg-zinc-50 dark:bg-zinc-800 p-3 rounded-xl text-zinc-800 dark:text-zinc-200">
                        "{hook.template}"
                      </p>
                      <div className="flex justify-end gap-2 pt-2">
                        <button
                          onClick={() => handleCopyText(hook.template, hook.id)}
                          className="px-3 py-1.5 bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 text-xs font-medium rounded-lg cursor-pointer"
                        >
                          Copy
                        </button>
                        <button
                          onClick={() => handleUseInComposer(hook.example)}
                          className="px-3 py-1.5 bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 text-xs font-semibold rounded-lg flex items-center gap-1.5 cursor-pointer"
                        >
                          Use in Post <FaArrowRight className="text-[10px]" />
                        </button>
                      </div>
                    </div>
                  ))}
              </div>
            )}
          </div>
        )}

        {/* ── MODAL: AUTO-FILL HOOK ── */}
        {autoFillModal.open && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
            <div className="w-full max-w-lg bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-zinc-100 dark:border-zinc-800">
                <h3 className="text-sm font-bold text-zinc-900 dark:text-white flex items-center gap-2">
                  <FaMagic className="text-amber-500" /> Personalize Viral Hook
                </h3>
                <button
                  onClick={() => setAutoFillModal({ open: false, hook: null, topic: '', results: [], loading: false })}
                  className="text-zinc-400 hover:text-zinc-600 text-sm font-bold cursor-pointer"
                >
                  ✕
                </button>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-zinc-500 uppercase">Template:</label>
                <div className="p-3 bg-zinc-50 dark:bg-zinc-800 rounded-xl text-xs font-mono text-zinc-800 dark:text-zinc-200">
                  "{autoFillModal.hook?.template}"
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-bold text-zinc-700 dark:text-zinc-300">
                  Your Specific Topic or Brand Name:
                </label>
                <input
                  type="text"
                  value={autoFillModal.topic}
                  onChange={(e) => setAutoFillModal((prev) => ({ ...prev, topic: e.target.value }))}
                  placeholder="e.g. B2B LinkedIn prospecting, Shopify dropshipping, morning workouts..."
                  className="w-full p-2.5 bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl text-sm focus:outline-none focus:border-amber-500 text-zinc-900 dark:text-white"
                />
              </div>

              <button
                onClick={handleRunAutoFill}
                disabled={autoFillModal.loading || !autoFillModal.topic.trim()}
                className="w-full py-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-bold text-xs rounded-xl flex items-center justify-center gap-2 cursor-pointer"
              >
                {autoFillModal.loading ? 'Generating Variations...' : '✨ Generate 3 Custom Hooks'}
              </button>

              {autoFillModal.results.length > 0 && (
                <div className="space-y-2 pt-2 border-t border-zinc-100 dark:border-zinc-800">
                  <label className="text-xs font-bold text-zinc-600 dark:text-zinc-400">Custom Variations:</label>
                  {autoFillModal.results.map((varText, idx) => (
                    <div
                      key={idx}
                      className="p-3 bg-zinc-50 dark:bg-zinc-800/60 rounded-xl border border-zinc-200 dark:border-zinc-700 text-xs font-medium text-zinc-800 dark:text-zinc-200 flex items-center justify-between gap-3"
                    >
                      <span>"{varText}"</span>
                      <button
                        onClick={() => {
                          handleUseInComposer(varText);
                        }}
                        className="px-2.5 py-1 bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 text-[11px] font-bold rounded-lg whitespace-nowrap cursor-pointer"
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
    </DashboardLayout>
  );
}
