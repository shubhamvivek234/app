import React, { useState, useEffect, useRef } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import {
  getMyBioPage,
  saveMyBioPage,
  getBioAnalytics,
  getBioLeads,
} from '@/lib/api';
import { toast } from 'sonner';
import {
  FaMobileAlt,
  FaDesktop,
  FaExternalLinkAlt,
  FaCopy,
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
  FaCheckCircle,
  FaShareAlt,
  FaLayerGroup,
  FaImage,
  FaPlay,
  FaTimes,
  FaBolt,
  FaFolder,
  FaChevronDown,
  FaChevronUp,
} from 'react-icons/fa';
import {
  THEME_PRESETS,
  getTactileCardStyles,
  getProfileAvatarStyles,
  getBlockSpacingPx,
  getSocialIconSizePx,
} from '@/lib/bioThemeUtils';
import BioOutlineTree from '@/components/bio/BioOutlineTree';
import BioInspectorDrawer from '@/components/bio/BioInspectorDrawer';
import BioBlockEditorModal from '@/components/bio/BioBlockEditorModal';

const SOCIAL_ICON_MAP = {
  instagram: FaInstagram,
  twitter: FaTwitter,
  youtube: FaYoutube,
  linkedin: FaLinkedin,
  tiktok: FaTiktok,
  spotify: FaSpotify,
  github: FaGithub,
  discord: FaDiscord,
  default: FaGlobe,
};

export default function LinkInBio() {
  const [handle, setHandle] = useState('');
  const [title, setTitle] = useState('');
  const [bio, setBio] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [bannerUrl, setBannerUrl] = useState('');
  const [verifiedBadge, setVerifiedBadge] = useState(false);
  const [theme, setTheme] = useState(THEME_PRESETS[0]);
  
  // Multi-Page State
  const [pages, setPages] = useState([{ id: 'home', title: 'Home', slug: 'home', blocks: [] }]);
  const [activePageId, setActivePageId] = useState('home');
  const [blocks, setBlocks] = useState([]);
  const [deletedBlocks, setDeletedBlocks] = useState([]);

  const [socialLinks, setSocialLinks] = useState({});
  const [customDomain, setCustomDomain] = useState('');
  const [seo, setSeo] = useState({ meta_title: '', meta_description: '' });
  const [autoSyncGrid, setAutoSyncGrid] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Undo / Redo History Stack
  const [history, setHistory] = useState([]);
  const [historyIdx, setHistoryIdx] = useState(-1);

  // UI Studio State
  const [deviceMode, setDeviceMode] = useState('mobile'); // 'mobile' | 'desktop'
  const [editingBlock, setEditingBlock] = useState(null);
  const [addBlockModalOpen, setAddBlockModalOpen] = useState(false);

  // Load Initial Data
  const loadData = async () => {
    try {
      setLoading(true);
      const data = await getMyBioPage();
      if (data) {
        setHandle(data.handle || '');
        setTitle(data.title || '');
        setBio(data.bio || '');
        setAvatarUrl(data.avatar_url || '');
        setBannerUrl(data.theme?.banner_url || data.banner_url || '');
        setVerifiedBadge(data.verified_badge ?? false);
        if (data.theme) setTheme({ ...THEME_PRESETS[0], ...data.theme });
        
        // Multi-page initialization
        const initialPages = (data.pages && data.pages.length > 0)
          ? data.pages
          : [{ id: 'home', title: 'Home', slug: 'home', blocks: data.blocks || [] }];
        
        setPages(initialPages);
        setActivePageId(data.active_page_id || 'home');
        
        const currentPg = initialPages.find((p) => p.id === (data.active_page_id || 'home')) || initialPages[0];
        setBlocks(currentPg?.blocks || data.blocks || []);

        setSocialLinks(data.social_links || {});
        setCustomDomain(data.custom_domain || '');
        setSeo(data.seo || { meta_title: '', meta_description: '' });
        setAutoSyncGrid(data.auto_sync_instagram_grid ?? true);
      }
    } catch (err) {
      toast.error('Failed to load Bio page details');
    } finally {
      setLoading(false);
    }
  };

  const isInitialMount = useRef(true);
  const isUndoRedoAction = useRef(false);
  const historyIdxRef = useRef(historyIdx);
  historyIdxRef.current = historyIdx;

  useEffect(() => {
    loadData();
  }, []);

  // Sync active page's blocks whenever blocks change
  useEffect(() => {
    if (loading) return;
    setPages((prev) =>
      prev.map((p) => (p.id === activePageId ? { ...p, blocks } : p))
    );
  }, [blocks, activePageId, loading]);

  useEffect(() => {
    if (loading) return;
    if (isInitialMount.current) {
      setHistory([{ theme, blocks, pages }]);
      setHistoryIdx(0);
      isInitialMount.current = false;
      return;
    }
    if (isUndoRedoAction.current) {
      isUndoRedoAction.current = false;
      return;
    }
    const timeout = setTimeout(() => {
      setHistory((prev) => {
        const sliced = prev.slice(0, historyIdxRef.current + 1);
        return [...sliced, { theme, blocks, pages }];
      });
      setHistoryIdx((prev) => prev + 1);
    }, 400);
    return () => clearTimeout(timeout);
  }, [theme, blocks, pages, loading]);

  // Page Management Handlers
  const handleSelectPage = (pageId) => {
    // Save current blocks to pages first
    setPages((prev) => {
      const updated = prev.map((p) => (p.id === activePageId ? { ...p, blocks } : p));
      const targetPage = updated.find((p) => p.id === pageId);
      if (targetPage) {
        setBlocks(targetPage.blocks || []);
      }
      return updated;
    });
    setActivePageId(pageId);
  };

  const handleAddPage = (pageTitle, slug) => {
    const newPage = {
      id: `page_${Date.now()}`,
      title: pageTitle,
      slug: slug || pageTitle.toLowerCase().replace(/[^a-z0-9]/g, '-'),
      blocks: [],
    };
    setPages((prev) => [...prev, newPage]);
    setActivePageId(newPage.id);
    setBlocks([]);
    toast.success(`Created page "${pageTitle}"`);
  };

  const handleDeletePage = (pageId) => {
    if (pageId === 'home') {
      toast.error('Cannot delete the primary Home page');
      return;
    }
    setPages((prev) => {
      const filtered = prev.filter((p) => p.id !== pageId);
      if (activePageId === pageId) {
        setActivePageId('home');
        const homePage = filtered.find((p) => p.id === 'home');
        setBlocks(homePage?.blocks || []);
      }
      return filtered;
    });
    toast.success('Deleted page');
  };

  // Save changes to backend
  const handleSaveAll = async (overrideState = null) => {
    setSaving(true);
    try {
      const updatedPages = pages.map((p) => (p.id === activePageId ? { ...p, blocks } : p));
      const homePage = updatedPages.find((p) => p.id === 'home');

      const payload = {
        handle: handle.trim(),
        title: title.trim(),
        bio,
        avatar_url: avatarUrl,
        banner_url: bannerUrl,
        verified_badge: verifiedBadge,
        theme: overrideState?.theme || theme,
        blocks: homePage?.blocks || blocks,
        pages: updatedPages,
        active_page_id: activePageId,
        navigation_style: theme.navigation_style || 'pills',
        social_links: overrideState?.socialLinks || socialLinks,
        custom_domain: customDomain,
        seo,
        auto_sync_instagram_grid: autoSyncGrid,
        is_published: true,
      };
      await saveMyBioPage(payload);
      toast.success('Smart Bio & Multi-Page site published live!');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to save Smart Bio');
    } finally {
      setSaving(false);
    }
  };

  // Undo / Redo Handlers
  const handleUndo = () => {
    if (historyIdx > 0) {
      isUndoRedoAction.current = true;
      const prev = history[historyIdx - 1];
      setTheme(prev.theme);
      setBlocks(prev.blocks);
      if (prev.pages) setPages(prev.pages);
      setHistoryIdx(historyIdx - 1);
    }
  };

  const handleRedo = () => {
    if (historyIdx < history.length - 1) {
      isUndoRedoAction.current = true;
      const next = history[historyIdx + 1];
      setTheme(next.theme);
      setBlocks(next.blocks);
      if (next.pages) setPages(next.pages);
      setHistoryIdx(historyIdx + 1);
    }
  };

  // Quick link creation
  const handleQuickAddLink = (url) => {
    let rawTitle = 'My Link';
    try {
      const parsed = new URL(url.startsWith('http') ? url : `https://${url}`);
      rawTitle = parsed.hostname.replace('www.', '').split('.')[0];
      rawTitle = rawTitle.charAt(0).toUpperCase() + rawTitle.slice(1);
    } catch (e) {
      rawTitle = 'New Link';
    }

    const newBlock = {
      id: `block_${Date.now()}`,
      type: 'link',
      title: rawTitle,
      subtitle: '',
      url: url.startsWith('http') ? url : `https://${url}`,
      icon: 'globe',
      badge: '',
      is_featured: false,
      layout: 'card_left_image',
      media_type: 'image',
      media_url: '',
      active: true,
      click_count: 0,
    };
    setBlocks((prev) => [newBlock, ...prev]);
    toast.success(`Created link for ${rawTitle}`);
  };

  // Block handlers
  const handleSaveBlock = (updatedBlock) => {
    setBlocks((prev) => prev.map((b) => (b.id === updatedBlock.id ? updatedBlock : b)));
    toast.success('Block updated');
  };

  const handleDeleteBlock = (blockId) => {
    const toDelete = blocks.find((b) => b.id === blockId);
    if (toDelete) {
      setDeletedBlocks((prev) => [toDelete, ...prev]);
      setBlocks((prev) => prev.filter((b) => b.id !== blockId));
      toast.success('Block moved to Deleted Blocks');
    }
  };

  const handleToggleBlockActive = (blockId) => {
    setBlocks((prev) =>
      prev.map((b) => (b.id === blockId ? { ...b, active: b.active === false ? true : false } : b))
    );
  };

  const handleDuplicateBlock = (block) => {
    const dup = {
      ...block,
      id: `block_${Date.now()}`,
      title: `${block.title || 'Link'} (Copy)`,
    };
    setBlocks((prev) => [...prev, dup]);
    toast.success('Duplicated block');
  };

  const handleRestoreBlock = (delBlock) => {
    setBlocks((prev) => [...prev, delBlock]);
    setDeletedBlocks((prev) => prev.filter((b) => b.id !== delBlock.id));
    toast.success('Block restored');
  };

  const handleClearDeletedBlocks = () => {
    setDeletedBlocks([]);
    toast.success('Deleted blocks cleared permanently');
  };

  const handleReorderBlocks = (newOrder) => {
    setBlocks(newOrder);
  };

  const toggleFolderPreview = (blockId) => {
    setBlocks((prev) =>
      prev.map((b) => (b.id === blockId ? { ...b, is_expanded: !b.is_expanded } : b))
    );
  };

  const publicUrl = handle ? `${window.location.origin}/bio/${handle}` : '';

  const copyPublicUrl = () => {
    if (!publicUrl) return;
    navigator.clipboard.writeText(publicUrl);
    toast.success('Public Smart Bio link copied to clipboard!');
  };

  // Dynamic style calculations for live preview
  const activeBlocks = blocks.filter((b) => b.active !== false);
  const avatarStyles = getProfileAvatarStyles(theme);
  const blockGapPx = getBlockSpacingPx(theme);
  const socialIconPx = getSocialIconSizePx(theme);

  return (
    <DashboardLayout>
      <div className="h-[calc(100vh-3.5rem)] flex flex-col bg-zinc-100 dark:bg-zinc-950 overflow-hidden font-sans">
        
        {/* ── TOP STUDIO CONTROL HEADER ── */}
        <div className="h-13 bg-white dark:bg-zinc-900 border-b border-zinc-200/80 dark:border-zinc-800 px-4 flex items-center justify-between z-20 shrink-0">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-xs font-bold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                Smart Bio Studio
              </span>
            </div>
            <div className="h-4 w-[1px] bg-zinc-200 dark:bg-zinc-800" />
            <div className="flex items-center gap-1.5 text-xs text-zinc-700 dark:text-zinc-300 font-mono bg-zinc-50 dark:bg-zinc-800 px-2.5 py-1 rounded-lg border border-zinc-200/60 dark:border-zinc-700/60">
              <span>unravler.bio/</span>
              <input
                type="text"
                value={handle}
                onChange={(e) => setHandle(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))}
                placeholder="username"
                className="bg-transparent font-bold text-zinc-900 dark:text-white outline-hidden w-24 sm:w-32"
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Device Switcher (Mobile vs Desktop) */}
            <div className="hidden sm:flex items-center p-0.5 rounded-xl bg-zinc-100 dark:bg-zinc-800 border border-zinc-200/80 dark:border-zinc-700">
              <button
                onClick={() => setDeviceMode('mobile')}
                className={`p-1.5 rounded-lg text-xs font-bold transition-all ${
                  deviceMode === 'mobile'
                    ? 'bg-white dark:bg-zinc-900 text-indigo-600 dark:text-indigo-400 shadow-xs'
                    : 'text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200'
                }`}
                title="Mobile Viewport"
              >
                <FaMobileAlt />
              </button>
              <button
                onClick={() => setDeviceMode('desktop')}
                className={`p-1.5 rounded-lg text-xs font-bold transition-all ${
                  deviceMode === 'desktop'
                    ? 'bg-white dark:bg-zinc-900 text-indigo-600 dark:text-indigo-400 shadow-xs'
                    : 'text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200'
                }`}
                title="Desktop Viewport"
              >
                <FaDesktop />
              </button>
            </div>

            {publicUrl && (
              <button
                onClick={copyPublicUrl}
                className="px-3 py-1.5 text-xs font-bold text-zinc-700 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 border border-zinc-200/80 dark:border-zinc-700/80 rounded-xl transition-colors hidden md:flex items-center gap-1.5"
              >
                <FaCopy className="text-zinc-400 text-[10px]" /> Copy Link
              </button>
            )}

            {publicUrl && (
              <a
                href={publicUrl}
                target="_blank"
                rel="noreferrer"
                className="px-3 py-1.5 text-xs font-bold text-zinc-700 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 border border-zinc-200/80 dark:border-zinc-700/80 rounded-xl transition-colors hidden md:flex items-center gap-1.5"
              >
                <FaExternalLinkAlt className="text-zinc-400 text-[10px]" /> View Live
              </a>
            )}

            <button
              onClick={() => handleSaveAll()}
              disabled={saving}
              className="px-4 py-1.5 text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-xs transition-colors flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
            >
              <FaSave className="text-xs" /> {saving ? 'Publishing…' : 'Publish Bio'}
            </button>
          </div>
        </div>

        {/* ── 3-COLUMN STUDIO WORKSPACE ── */}
        <div className="flex-1 flex overflow-hidden">
          
          {/* 1. LEFT COLUMN: Outline & Content Tree (~330px) */}
          <div className="w-80 sm:w-88 shrink-0 h-full overflow-hidden flex flex-col">
            <BioOutlineTree
              title={title}
              setTitle={setTitle}
              bio={bio}
              setBio={setBio}
              avatarUrl={avatarUrl}
              setAvatarUrl={setAvatarUrl}
              socialLinks={socialLinks}
              setSocialLinks={setSocialLinks}
              theme={theme}
              setTheme={setTheme}
              blocks={blocks}
              setBlocks={setBlocks}
              pages={pages}
              activePageId={activePageId}
              onSelectPage={handleSelectPage}
              onAddPage={handleAddPage}
              onDeletePage={handleDeletePage}
              onOpenBlockEditor={(blk) => setEditingBlock(blk)}
              onOpenAddModal={() => setAddBlockModalOpen(true)}
              onQuickAddLink={handleQuickAddLink}
              onDuplicateBlock={handleDuplicateBlock}
              onToggleBlockActive={handleToggleBlockActive}
              onDeleteBlock={handleDeleteBlock}
              deletedBlocks={deletedBlocks}
              onRestoreBlock={handleRestoreBlock}
              onClearDeletedBlocks={handleClearDeletedBlocks}
              onReorderBlocks={handleReorderBlocks}
            />
          </div>

          {/* 2. CENTER CANVAS: Live Interactive Device Preview Viewport */}
          <div className="flex-1 bg-zinc-100/70 dark:bg-zinc-950 flex flex-col items-center justify-center p-4 sm:p-6 overflow-y-auto relative">
            
            {/* Device Viewport Frame */}
            <div
              className={`transition-all duration-300 shadow-2xl rounded-[3rem] border-8 border-zinc-900 dark:border-zinc-800 bg-white overflow-hidden relative flex flex-col ${
                deviceMode === 'mobile'
                  ? 'w-[360px] h-[680px] max-h-[85vh]'
                  : 'w-[540px] h-[720px] max-h-[88vh]'
              }`}
            >
              {/* Simulated Mobile Notch / Browser Header */}
              <div className="bg-zinc-900 text-white px-4 py-2 flex items-center justify-between text-[11px] shrink-0 z-30">
                <span className="font-mono truncate max-w-[180px] text-zinc-400">
                  {handle ? `unravler.bio/${handle}` : 'unravler.bio/preview'}
                </span>
                <button onClick={copyPublicUrl} className="hover:text-white text-zinc-400">
                  <FaShareAlt className="text-xs" />
                </button>
              </div>

              {/* Live Canvas Content Frame */}
              <div
                style={{
                  background: theme.background_gradient || theme.background_color || '#FDFBF7',
                  color: theme.text_color || '#18181B',
                  fontFamily: theme.font_family || 'Plus Jakarta Sans, sans-serif',
                }}
                className="flex-1 overflow-y-auto p-4 flex flex-col items-center relative custom-scrollbar select-none"
              >
                {/* Film Grain Texture Overlay */}
                {(theme.background_effect === 'grain' || theme.preset === 'matcha_washi' || theme.preset === 'editorial_cream') && (
                  <div
                    className="pointer-events-none absolute inset-0 z-0 opacity-[0.04] mix-blend-overlay"
                    style={{
                      backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`,
                    }}
                  />
                )}

                {/* Ambient Defocused Orbs */}
                {(theme.background_effect === 'ambient_orbs' || theme.background_effect === 'mesh_glow' || theme.preset === 'liquid_aura' || theme.preset === 'tokyo_cyber') && (
                  <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
                    <div
                      className="absolute -top-16 -left-16 w-48 h-48 rounded-full blur-2xl opacity-40 animate-pulse"
                      style={{ background: theme.accent_color || '#6366F1' }}
                    />
                    <div
                      className="absolute top-1/2 -right-16 w-44 h-44 rounded-full blur-2xl opacity-30"
                      style={{ background: theme.card_text_color || '#EC4899' }}
                    />
                  </div>
                )}

                {/* Top Announcement Banner */}
                {theme.announcement_active && theme.announcement_banner && (
                  <div
                    className="w-full -mx-4 -mt-4 mb-3 py-2 px-3 text-center text-[10px] font-bold bg-indigo-600 text-white flex items-center justify-center gap-1.5 shadow-xs relative z-20"
                  >
                    <span className="truncate">{theme.announcement_banner}</span>
                    <FaExternalLinkAlt className="text-[8px]" />
                  </div>
                )}

                {/* Header Layout Mockup */}
                <div className="w-full flex flex-col items-center text-center mb-4 relative z-10">
                  <div
                    style={avatarStyles}
                    className="rounded-full overflow-hidden flex items-center justify-center mb-2 bg-black/10 shrink-0"
                  >
                    {avatarUrl ? (
                      <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-xl font-extrabold uppercase" style={{ color: theme.text_color }}>
                        {title ? title[0] : 'U'}
                      </span>
                    )}
                  </div>
                  <h2 className="text-sm font-black tracking-tight flex items-center justify-center gap-1" style={{ color: theme.text_color }}>
                    {title || 'Your Name'}
                    {verifiedBadge && <FaCheckCircle className="text-indigo-500 text-xs" />}
                  </h2>
                  <p className="text-[10px] font-mono opacity-60" style={{ color: theme.text_color }}>
                    @{handle || 'handle'}
                  </p>
                  {bio && (
                    <p className="text-[11px] opacity-80 pt-1 leading-snug max-w-xs" style={{ color: theme.text_color }}>
                      {bio}
                    </p>
                  )}
                </div>

                {/* Social Dock Bar */}
                {socialLinks && Object.keys(socialLinks).some((k) => socialLinks[k]) && (
                  <div className="flex items-center justify-center gap-2 mb-3 flex-wrap relative z-10">
                    {Object.entries(socialLinks).map(([plat, url]) => {
                      if (!url) return null;
                      const Icon = SOCIAL_ICON_MAP[plat] || SOCIAL_ICON_MAP.default;
                      return (
                        <div
                          key={plat}
                          style={{
                            color: theme.text_color,
                            width: `${socialIconPx + 12}px`,
                            height: `${socialIconPx + 12}px`,
                          }}
                          className="rounded-full bg-black/5 dark:bg-white/10 flex items-center justify-center shadow-2xs"
                        >
                          <Icon style={{ fontSize: `${socialIconPx}px` }} />
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Multi-Page Sub-Navigation Pill Dock (as in screenshot) */}
                {pages.length > 1 && (theme.navigation_style || 'pills') === 'pills' && (
                  <div className="flex items-center justify-center gap-1.5 mb-4 p-1 rounded-full bg-black/5 dark:bg-white/10 backdrop-blur-md relative z-10">
                    {pages.map((pg) => {
                      const isActive = pg.id === activePageId;
                      return (
                        <button
                          key={pg.id}
                          onClick={() => handleSelectPage(pg.id)}
                          className={`px-3.5 py-1 text-xs font-bold rounded-full transition-all ${
                            isActive
                              ? 'bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 shadow-sm'
                              : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white'
                          }`}
                        >
                          {pg.title}
                        </button>
                      );
                    })}
                  </div>
                )}

                {/* Blocks Stack in Live Preview */}
                <div
                  className="w-full relative z-10"
                  style={{ display: 'flex', flexDirection: 'column', gap: `${blockGapPx}px` }}
                >
                  {activeBlocks.length === 0 ? (
                    <div className="py-12 text-center text-xs opacity-50 border border-dashed rounded-2xl p-4">
                      No blocks on this page. Add blocks from the left panel.
                    </div>
                  ) : (
                    activeBlocks.map((block) => {
                      const cardObj = getTactileCardStyles(theme.card_style, theme, block.is_featured, {
                        animation: block.animation,
                      });

                      const isFolder = block.type === 'folder' || block.type === 'tab_group';
                      const isBannerTop = block.layout === 'card_banner_top';

                      if (isFolder) {
                        return (
                          <div
                            key={block.id}
                            style={cardObj.style}
                            className={`w-full font-bold text-xs overflow-hidden transition-all ${cardObj.className}`}
                          >
                            <div
                              onClick={() => toggleFolderPreview(block.id)}
                              className="p-3.5 flex items-center justify-between cursor-pointer"
                            >
                              <div className="flex items-center gap-2">
                                <FaFolder className="text-amber-500 text-sm" />
                                <span>{block.title || 'Folder / Group'}</span>
                                {block.folder_items?.length > 0 && (
                                  <span className="px-1.5 py-0.2 rounded-md bg-black/10 dark:bg-white/10 text-[9px] font-mono">
                                    {block.folder_items.length} links
                                  </span>
                                )}
                              </div>
                              <div className="flex items-center gap-2">
                                {block.is_expanded ? <FaChevronUp className="text-[10px]" /> : <FaChevronDown className="text-[10px]" />}
                              </div>
                            </div>

                            {/* Folder Nested Links */}
                            {block.is_expanded && (
                              <div className="p-3 pt-0 space-y-2 border-t border-black/5 dark:border-white/5 mt-1">
                                {(block.folder_items || []).length === 0 ? (
                                  <p className="text-[10px] opacity-60 text-center py-2">
                                    Folder is empty. Click edit to add sub-links.
                                  </p>
                                ) : (
                                  block.folder_items.map((subItem, sIdx) => (
                                    <div
                                      key={subItem.id || sIdx}
                                      className="py-2 px-3 rounded-xl bg-black/5 dark:bg-white/5 flex items-center justify-between text-xs font-semibold"
                                    >
                                      <div className="flex items-center gap-2 truncate">
                                        <FaExternalLinkAlt className="text-[9px] opacity-60 flex-shrink-0" />
                                        <span className="truncate">{subItem.title || subItem.url}</span>
                                      </div>
                                    </div>
                                  ))
                                )}
                              </div>
                            )}
                          </div>
                        );
                      }

                      return (
                        <div
                          key={block.id}
                          onClick={() => setEditingBlock(block)}
                          style={cardObj.style}
                          className={`w-full font-bold text-xs cursor-pointer transition-transform hover:scale-[1.01] active:scale-[0.99] overflow-hidden ${cardObj.className} ${
                            isBannerTop ? 'flex flex-col text-left' : 'py-3 px-3.5 flex items-center justify-between text-left'
                          }`}
                        >
                          {isBannerTop && block.media_url && (
                            <div className="w-full h-28 overflow-hidden bg-black/5">
                              <img src={block.media_url} alt="" className="w-full h-full object-cover" />
                            </div>
                          )}

                          <div className={`flex items-center gap-2.5 w-full ${isBannerTop ? 'p-3' : ''}`}>
                            {!isBannerTop && block.media_url && (
                              <img src={block.media_url} alt="" className="w-9 h-9 rounded-lg object-cover flex-shrink-0" />
                            )}

                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-1.5">
                                {block.is_featured && <FaBolt className="text-amber-400 text-[10px] shrink-0" />}
                                <span className="truncate">{block.title || block.headline || 'View Link'}</span>
                                {block.badge && (
                                  <span className="px-1.5 py-0.5 text-[8px] font-black uppercase rounded-full bg-rose-500 text-white">
                                    {block.badge}
                                  </span>
                                )}
                              </div>
                              {block.subtitle && (
                                <p className="text-[10px] opacity-70 font-normal truncate mt-0.5">{block.subtitle}</p>
                              )}
                            </div>

                            <FaExternalLinkAlt className="text-[9px] opacity-40 shrink-0" />
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>

              </div>
            </div>

          </div>

          {/* 3. RIGHT COLUMN: Inspector Drawer (~360px) */}
          <div className="w-88 sm:w-96 shrink-0 h-full overflow-hidden flex flex-col">
            <BioInspectorDrawer
              theme={theme}
              setTheme={setTheme}
              onUndo={handleUndo}
              onRedo={handleRedo}
              canUndo={historyIdx > 0}
              canRedo={historyIdx < history.length - 1}
              onResetTheme={() => setTheme(THEME_PRESETS[0])}
            />
          </div>

        </div>

        {/* ── MODALS ── */}
        
        {/* 1. Deep Block Layout & Content Editor Modal */}
        <BioBlockEditorModal
          isOpen={Boolean(editingBlock)}
          onClose={() => setEditingBlock(null)}
          block={editingBlock}
          onSaveBlock={handleSaveBlock}
          onDeleteBlock={handleDeleteBlock}
          theme={theme}
        />

        {/* 2. Add New Block Modal */}
        {addBlockModalOpen && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-3xl max-w-md w-full p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-bold text-zinc-900 dark:text-white">Add Content Block</h3>
                <button onClick={() => setAddBlockModalOpen(false)} className="text-zinc-400 hover:text-zinc-600">
                  <FaTimes />
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2.5">
                {[
                  { id: 'link', label: 'Custom Link', desc: 'Direct URL with badge & subtitle', icon: FaExternalLinkAlt, color: 'text-indigo-500' },
                  { id: 'folder', label: 'Folder / Group', desc: 'Group related links into a tidy drawer', icon: FaFolder, color: 'text-amber-500' },
                  { id: 'media_card', label: 'Media Card', desc: 'Hero photo card with subtitle & link', icon: FaImage, color: 'text-rose-500' },
                  { id: 'embed', label: 'YouTube / Spotify', desc: 'Embedded video & podcast player', icon: FaPlay, color: 'text-purple-500' },
                  { id: 'feed_grid', label: 'Instagram Feed', desc: 'Live mirror of recent social posts', icon: FaLayerGroup, color: 'text-amber-500' },
                ].map((typeItem) => (
                  <button
                    key={typeItem.id}
                    onClick={() => {
                      const newBlock = {
                        id: `block_${Date.now()}`,
                        type: typeItem.id,
                        title: `New ${typeItem.label}`,
                        subtitle: '',
                        url: '',
                        embed_url: '',
                        media_url: '',
                        layout: typeItem.id === 'media_card' ? 'card_banner_top' : 'card_left_image',
                        media_type: 'image',
                        active: true,
                        click_count: 0,
                        folder_items: typeItem.id === 'folder' ? [] : undefined,
                        is_expanded: false,
                      };
                      setBlocks((prev) => [...prev, newBlock]);
                      setAddBlockModalOpen(false);
                      setEditingBlock(newBlock);
                    }}
                    className="p-3 rounded-2xl border border-zinc-200/80 dark:border-zinc-800 hover:border-indigo-500 bg-zinc-50/50 dark:bg-zinc-800/40 text-left transition-all hover:scale-[1.02]"
                  >
                    <typeItem.icon className={`text-base mb-1.5 ${typeItem.color}`} />
                    <p className="text-xs font-bold text-zinc-900 dark:text-white">{typeItem.label}</p>
                    <p className="text-[10px] text-zinc-400 leading-tight mt-0.5">{typeItem.desc}</p>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

      </div>
    </DashboardLayout>
  );
}
