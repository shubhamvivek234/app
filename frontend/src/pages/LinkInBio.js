import React, { useState, useEffect, useRef } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { useTheme } from '@/context/ThemeContext';
import {
  getMyBioPage,
  saveMyBioPage,
} from '@/lib/api';
import { toast } from 'sonner';
import {
  FaMobileAlt,
  FaDesktop,
  FaTabletAlt,
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
  FaPlus,
  FaFolder,
  FaChevronDown,
  FaChevronUp,
  FaBolt,
  FaQrcode,
  FaRedoAlt,
  FaSearchPlus,
  FaSearchMinus,
  FaWifi,
  FaBatteryFull,
  FaSignal,
} from 'react-icons/fa';
import { SiThreads, SiBluesky } from 'react-icons/si';

import BioOutlineTree from '@/components/bio/BioOutlineTree';
import BioInspectorDrawer from '@/components/bio/BioInspectorDrawer';
import BioBlockEditorModal from '@/components/bio/BioBlockEditorModal';
import {
  THEME_PRESETS,
  getTactileCardStyles,
  getProfileAvatarStyles,
  getBlockSpacingPx,
  getSocialIconSizePx,
} from '@/lib/bioThemeUtils';

const SOCIAL_ICON_MAP = {
  instagram: FaInstagram,
  twitter: FaTwitter,
  youtube: FaYoutube,
  linkedin: FaLinkedin,
  tiktok: FaTiktok,
  spotify: FaSpotify,
  github: FaGithub,
  discord: FaDiscord,
  threads: SiThreads,
  bluesky: SiBluesky,
  website: FaGlobe,
  default: FaGlobe,
};

export default function LinkInBio() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { isDarkMode, toggleDarkMode } = useTheme();

  // Core Bio Identity
  const [handle, setHandle] = useState('');
  const [title, setTitle] = useState('');
  const [bio, setBio] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [bannerUrl, setBannerUrl] = useState('');
  const [verifiedBadge, setVerifiedBadge] = useState(false);
  const [socialLinks, setSocialLinks] = useState({
    instagram: '',
    twitter: '',
    youtube: '',
    linkedin: '',
    tiktok: '',
    spotify: '',
    github: '',
    discord: '',
  });

  // Multi-Page & Content Blocks
  const [pages, setPages] = useState([
    { id: 'home', title: 'Home', slug: 'home', blocks: [] },
  ]);
  const [activePageId, setActivePageId] = useState('home');
  const [blocks, setBlocks] = useState([]);

  // Theme & Tactile Engine
  const [theme, setTheme] = useState(THEME_PRESETS[0]);
  const [customDomain, setCustomDomain] = useState('');
  const [seo, setSeo] = useState({ title: '', description: '', og_image: '' });
  const [autoSyncGrid, setAutoSyncGrid] = useState(false);

  // Studio UI state
  const [deviceMode, setDeviceMode] = useState('mobile'); // 'mobile' | 'tablet' | 'desktop'
  const [zoomScale, setZoomScale] = useState(1); // 0.8 to 1.15
  const [editingBlock, setEditingBlock] = useState(null);
  const [addBlockModalOpen, setAddBlockModalOpen] = useState(false);
  const [qrModalOpen, setQrModalOpen] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);
  const [deletedBlocks, setDeletedBlocks] = useState([]);
  const [activeFolders, setActiveFolders] = useState({});

  // History for Undo / Redo
  const [history, setHistory] = useState([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const isUndoRedoAction = useRef(false);
  const historyIdxRef = useRef(-1);
  historyIdxRef.current = historyIdx;

  const publicUrl = handle
    ? `${window.location.origin}/bio/${handle}${activePageId !== 'home' ? `?page=${pages.find((p) => p.id === activePageId)?.slug || activePageId}` : ''}`
    : '';

  // Initial Load
  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const res = await getMyBioPage();
        if (res && res.data) {
          const d = res.data;
          setHandle(d.handle || '');
          setTitle(d.title || '');
          setBio(d.bio || '');
          setAvatarUrl(d.avatar_url || '');
          setBannerUrl(d.banner_url || '');
          setVerifiedBadge(Boolean(d.verified_badge));
          if (d.social_links) setSocialLinks(d.social_links);
          if (d.custom_domain) setCustomDomain(d.custom_domain);
          if (d.seo) setSeo(d.seo);
          if (d.auto_sync_instagram_grid !== undefined) setAutoSyncGrid(d.auto_sync_instagram_grid);

          if (d.theme) {
            setTheme((prev) => ({ ...prev, ...d.theme }));
          }

          if (Array.isArray(d.pages) && d.pages.length > 0) {
            setPages(d.pages);
            const initialActive = d.active_page_id || 'home';
            setActivePageId(initialActive);
            const activePageObj = d.pages.find((p) => p.id === initialActive) || d.pages[0];
            setBlocks(activePageObj.blocks || d.blocks || []);
          } else if (Array.isArray(d.blocks)) {
            setBlocks(d.blocks);
            setPages([{ id: 'home', title: 'Home', slug: 'home', blocks: d.blocks }]);
          }
        }
      } catch (err) {
        console.error('Failed to load bio data:', err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  // Track History for Undo/Redo
  useEffect(() => {
    if (loading) return;
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

      const safeHandle = (handle || '').trim() || 'user';
      const safeTitle = (title || '').trim() || safeHandle;

      const payload = {
        handle: safeHandle,
        title: safeTitle,
        bio: bio || '',
        avatar_url: avatarUrl || null,
        banner_url: bannerUrl || null,
        verified_badge: Boolean(verifiedBadge),
        theme: overrideState?.theme || theme,
        blocks: homePage?.blocks || blocks,
        pages: updatedPages,
        active_page_id: activePageId || 'home',
        navigation_style: theme.navigation_style || 'pills',
        social_links: overrideState?.socialLinks || socialLinks || {},
        custom_domain: customDomain || '',
        seo: {
          meta_title: seo?.meta_title || seo?.title || `${safeTitle} | Smart Bio`,
          meta_description: seo?.meta_description || seo?.description || bio || '',
          meta_image_url: seo?.meta_image_url || seo?.og_image || avatarUrl || '',
        },
        auto_sync_instagram_grid: autoSyncGrid,
        is_published: true,
      };
      const res = await saveMyBioPage(payload);
      const savedHandle = res?.handle || safeHandle;
      if (res && res.handle) {
        setHandle(res.handle);
      }
      toast.success('✨ Smart Bio published live! Opening in new tab…');

      // Automatically open the published public bio in a new tab
      const targetUrl = `${window.location.origin}/bio/${savedHandle}`;
      window.open(targetUrl, '_blank', 'noopener,noreferrer');
    } catch (err) {
      console.error('Save bio error:', err);
      const errMsg = err?.response?.data?.detail || err?.message || 'Failed to save Smart Bio';
      toast.error(errMsg);
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
      setPages(prev.pages);
      setHistoryIdx((i) => i - 1);
      toast.info('Undo applied');
    }
  };

  const handleRedo = () => {
    if (historyIdx < history.length - 1) {
      isUndoRedoAction.current = true;
      const next = history[historyIdx + 1];
      setTheme(next.theme);
      setBlocks(next.blocks);
      setPages(next.pages);
      setHistoryIdx((i) => i + 1);
      toast.info('Redo applied');
    }
  };

  // Block Actions
  const handleSaveBlock = (updatedBlock) => {
    setBlocks((prev) => prev.map((b) => (b.id === updatedBlock.id ? updatedBlock : b)));
    setEditingBlock(null);
    toast.success('Block updated');
  };

  const handleQuickAddLink = (url) => {
    try {
      let hostname = url;
      try {
        const parsed = new URL(url.startsWith('http') ? url : `https://${url}`);
        hostname = parsed.hostname.replace('www.', '');
      } catch (e) {}

      const cleanTitle = hostname.charAt(0).toUpperCase() + hostname.slice(1);
      const newBlock = {
        id: `block_${Date.now()}`,
        type: 'link',
        title: cleanTitle,
        subtitle: url,
        url: url.startsWith('http') ? url : `https://${url}`,
        active: true,
        click_count: 0,
        layout: 'card_left_image',
      };
      setBlocks((prev) => [...prev, newBlock]);
      toast.success('Quick link added to outline');
    } catch (err) {
      toast.error('Invalid URL format');
    }
  };

  const handleDuplicateBlock = (block) => {
    const duplicated = {
      ...block,
      id: `block_${Date.now()}`,
      title: `${block.title || 'Block'} (Copy)`,
      click_count: 0,
    };
    setBlocks((prev) => [...prev, duplicated]);
    toast.success('Block duplicated');
  };

  const handleToggleBlockActive = (blockId) => {
    setBlocks((prev) =>
      prev.map((b) => (b.id === blockId ? { ...b, active: b.active === false ? true : false } : b))
    );
  };

  const handleDeleteBlock = (blockId) => {
    const target = blocks.find((b) => b.id === blockId);
    if (target) {
      setDeletedBlocks((prev) => [target, ...prev]);
      setBlocks((prev) => prev.filter((b) => b.id !== blockId));
      setEditingBlock(null);
      toast.success('Moved block to trash bin');
    }
  };

  const handleRestoreBlock = (blockId) => {
    const target = deletedBlocks.find((b) => b.id === blockId);
    if (target) {
      setDeletedBlocks((prev) => prev.filter((b) => b.id !== blockId));
      setBlocks((prev) => [...prev, target]);
      toast.success('Restored block');
    }
  };

  const handleClearDeletedBlocks = () => {
    setDeletedBlocks([]);
    toast.success('Emptied trash bin');
  };

  const handleReorderBlocks = (newBlocks) => {
    setBlocks(newBlocks);
  };

  const toggleFolderPreview = (folderId) => {
    setActiveFolders((prev) => ({ ...prev, [folderId]: !prev[folderId] }));
  };

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
    <DashboardLayout noPadding={true}>
      <div className="h-[calc(100vh-3.5rem)] flex flex-col bg-[#F5F5F7] dark:bg-[#000000] overflow-hidden font-sans select-none transition-colors duration-300">
        
        {/* ── TOP STUDIO CONTROL HEADER (Apple macOS Sequoia Glass Bar) ── */}
        <header className="relative z-30 px-4 sm:px-6 py-3 border-b border-black/[0.06] dark:border-white/[0.08] apple-glass-panel flex items-center justify-between gap-4 shrink-0">
          <div className="flex items-center gap-3 sm:gap-4 min-w-0">
            {/* macOS Window Traffic Lights */}
            <div className="flex items-center gap-2 mr-1">
              <span className="w-3 h-3 rounded-full bg-[#FF5F56] border border-[#E0443E]/50 cursor-pointer hover:opacity-80" />
              <span className="w-3 h-3 rounded-full bg-[#FFBD2E] border border-[#DEA123]/50 cursor-pointer hover:opacity-80" />
              <span className="w-3 h-3 rounded-full bg-[#27C93F] border border-[#1AAB29]/50 cursor-pointer hover:opacity-80" />
            </div>

            <div className="h-4 w-px bg-black/[0.08] dark:bg-white/[0.1] hidden sm:block" />

            {/* Apple Logo + Studio Branding & Bio Link */}
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-7 h-7 rounded-[8px] bg-gradient-to-br from-[#090D16] to-[#1E293B] text-white flex items-center justify-center font-bold text-xs shadow-sm shrink-0">
                
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-xs text-gray-800 dark:text-gray-100 hidden md:inline-block">
                    Smart Bio Studio
                  </span>
                  <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 dark:bg-blue-950/60 text-[#0071E3] dark:text-blue-400 border border-blue-200/50 dark:border-blue-800/40 hidden lg:inline-block">
                    Apple Edition
                  </span>
                </div>
                <div className="flex items-center gap-1.5 text-[11px] text-gray-500 dark:text-gray-400 font-mono truncate">
                  <span>unravler.com/bio/</span>
                  <input
                    type="text"
                    value={handle}
                    onChange={(e) => setHandle(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))}
                    className="font-bold text-gray-900 dark:text-white bg-transparent outline-none w-20 sm:w-28 focus:text-[#0071E3] transition-colors"
                  />
                  <button onClick={copyPublicUrl} className="p-0.5 hover:text-[#0071E3] transition" title="Copy Bio Link">
                    📋
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Center: Apple Segmented Device Switcher (Preserved exact labels: Mobile, Tablet, Desktop) */}
          <div className="hidden md:flex items-center justify-center">
            <div className="apple-segment-wrapper">
              <button
                onClick={() => { setDeviceMode('mobile'); setZoomScale(1); }}
                className={`apple-segment-btn flex items-center gap-1.5 ${deviceMode === 'mobile' ? 'active' : ''}`}
                title="Mobile"
              >
                <FaMobileAlt className="text-xs" />
                <span>Mobile</span>
              </button>
              <button
                onClick={() => { setDeviceMode('tablet'); setZoomScale(0.95); }}
                className={`apple-segment-btn flex items-center gap-1.5 ${deviceMode === 'tablet' ? 'active' : ''}`}
                title="Tablet"
              >
                <FaTabletAlt className="text-xs" />
                <span>Tablet</span>
              </button>
              <button
                onClick={() => { setDeviceMode('desktop'); setZoomScale(0.9); }}
                className={`apple-segment-btn flex items-center gap-1.5 ${deviceMode === 'desktop' ? 'active' : ''}`}
                title="Desktop"
              >
                <FaDesktop className="text-xs" />
                <span>Desktop</span>
              </button>
            </div>
          </div>

          {/* Right: Actions, Dark Mode, QR, Zoom & Apple Obsidian CTA */}
          <div className="flex items-center gap-2 sm:gap-2.5 shrink-0">
            {/* Dark Mode Toggle */}
            <button
              onClick={toggleDarkMode}
              className="w-8 h-8 rounded-full flex items-center justify-center text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white bg-black/[0.04] dark:bg-white/[0.08] hover:bg-black/[0.08] transition"
              title="Toggle Light/Dark Theme"
            >
              🌓
            </button>

            {/* Zoom Controls */}
            <div className="hidden lg:flex items-center gap-1 bg-black/[0.04] dark:bg-white/[0.06] rounded-full px-2.5 py-1 text-xs text-gray-600 dark:text-gray-300 font-mono">
              <button
                onClick={() => setZoomScale((z) => Math.max(0.7, +(z - 0.05).toFixed(2)))}
                className="hover:text-blue-600 font-bold px-1"
                title="Zoom Out"
              >
                −
              </button>
              <span className="px-1 text-[11px]">{Math.round(zoomScale * 100)}%</span>
              <button
                onClick={() => setZoomScale((z) => Math.min(1.3, +(z + 0.05).toFixed(2)))}
                className="hover:text-blue-600 font-bold px-1"
                title="Zoom In"
              >
                +
              </button>
            </div>

            {publicUrl && (
              <button
                onClick={() => setQrModalOpen(true)}
                className="px-3 py-1.5 rounded-full text-xs font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-[#2C2C2E] border border-black/[0.08] dark:border-white/[0.12] hover:bg-gray-50 dark:hover:bg-[#3A3A3C] shadow-xs transition hidden sm:inline-block"
              >
                Share QR
              </button>
            )}

            {/* Publish Changes CTA (Apple Obsidian Pill) */}
            <button
              onClick={() => handleSaveAll()}
              disabled={saving}
              className="px-5 py-1.5 rounded-full text-xs font-semibold text-white bg-[#000000] dark:bg-[#FFFFFF] dark:text-[#000000] shadow-[0_2px_8px_rgba(0,0,0,0.2),inset_0_1px_1px_rgba(255,255,255,0.4)] hover:opacity-90 active:scale-[0.98] transition-all flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
            >
              <span className="w-2 h-2 rounded-full bg-[#34C759] animate-pulse" />
              <span>{saving ? 'Publishing…' : 'Publish Changes'}</span>
            </button>
          </div>
        </header>

        {/* ── 3-COLUMN STUDIO WORKSPACE ── */}
        <div className="flex-1 flex overflow-hidden">
          
          {/* 1. LEFT COLUMN: Outline & Content Tree (~320px) */}
          <div className="w-72 md:w-80 lg:w-84 shrink-0 h-full overflow-hidden flex flex-col border-r border-black/[0.06] dark:border-white/[0.08] apple-glass-panel relative z-20 shadow-xs">
            <BioOutlineTree
              title={title}
              setTitle={setTitle}
              bio={bio}
              setBio={setBio}
              avatarUrl={avatarUrl}
              setAvatarUrl={setAvatarUrl}
              handle={handle}
              setHandle={setHandle}
              verifiedBadge={verifiedBadge}
              setVerifiedBadge={setVerifiedBadge}
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

          {/* 2. CENTER CANVAS: Ambient Mesh Stage & iPhone 16 Pro Viewport */}
          <div className="flex-1 min-w-0 h-full bg-[#F5F5F7] dark:bg-[#000000] flex flex-col items-center justify-start p-4 md:p-8 overflow-x-hidden overflow-y-auto relative custom-scrollbar z-10 transition-colors">
            
            {/* Ambient Mesh Glow */}
            <div className="ambient-mesh pointer-events-none" />

            {/* Stage Quick Replay Pill */}
            <div className="relative z-20 mb-3 flex items-center justify-center">
              <button
                onClick={() => setPreviewKey((k) => k + 1)}
                className="px-3.5 py-1 rounded-full bg-white/80 dark:bg-[#2C2C2E]/80 backdrop-blur-md hover:bg-white dark:hover:bg-[#3A3A3C] border border-black/[0.06] dark:border-white/[0.08] text-[11px] font-semibold text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-all flex items-center gap-1.5 shadow-xs"
                title="Replay Entrance Animations"
              >
                <FaRedoAlt className="text-[10px]" /> Replay Animations
              </button>
            </div>

            {/* ── THE IPHONE 16 PRO / HARDWARE CHASSIS ── */}
            <div
              style={{ transform: `scale(${zoomScale})`, transformOrigin: 'top center' }}
              className="transition-transform duration-300 flex items-center justify-center my-auto relative z-20 max-w-full"
            >
              <div
                className="iphone-chassis flex flex-col transition-all duration-500 relative"
                style={{
                  width: deviceMode === 'mobile' ? '385px' : deviceMode === 'tablet' ? '540px' : '720px',
                  height: deviceMode === 'mobile' ? '780px' : deviceMode === 'tablet' ? '740px' : '680px',
                  borderRadius: deviceMode === 'mobile' ? '52px' : deviceMode === 'tablet' ? '36px' : '24px',
                }}
              >
                {/* Hardware Screen */}
                <div
                  className="iphone-screen flex-1 flex flex-col overflow-y-auto relative text-white"
                  style={{
                    background: theme.background_gradient || theme.background_color || 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%)',
                    borderRadius: deviceMode === 'mobile' ? '42px' : deviceMode === 'tablet' ? '26px' : '16px',
                    fontFamily: theme.font_family || 'Plus Jakarta Sans, sans-serif',
                  }}
                >
                  {/* Top Dynamic Island Status Bar (Mobile Mode) */}
                  {deviceMode === 'mobile' && (
                    <div className="sticky top-0 z-30 pt-3 px-7 pb-2 flex items-center justify-between text-[11px] font-semibold tracking-tight text-white/90 backdrop-blur-md bg-black/10 select-none">
                      <span>9:41</span>
                      <div className="w-24 h-6 rounded-full bg-black flex items-center justify-between px-2.5 shadow-md">
                        <span className="w-2 h-2 rounded-full bg-indigo-400 animate-ping" />
                        <div className="flex items-center gap-1">
                          <span className="w-2 h-2 rounded-full bg-[#34C759]" />
                          <span className="w-2.5 h-2.5 rounded-full bg-zinc-800" />
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <span>5G</span>
                        <span>100%</span>
                      </div>
                    </div>
                  )}

                  {/* Safari Window Header (Tablet & Desktop Mode) */}
                  {deviceMode !== 'mobile' && (
                    <div className="bg-[#2C2C2E] border-b border-white/[0.08] px-3.5 py-1.5 flex items-center justify-between text-xs shrink-0 z-30 select-none">
                      <div className="flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#FF5F56] border border-[#E0443E]/50" />
                        <span className="w-2.5 h-2.5 rounded-full bg-[#FFBD2E] border border-[#DEA123]/50" />
                        <span className="w-2.5 h-2.5 rounded-full bg-[#27C93F] border border-[#1AAB29]/50" />
                      </div>
                      <div className="bg-[#1C1C1E] text-gray-300 font-mono text-[11px] px-3.5 py-0.5 rounded-full border border-white/[0.1] truncate max-w-xs shadow-inner">
                        {handle ? `https://unravler.bio/${handle}` : 'https://unravler.bio/preview'}
                      </div>
                      <button onClick={copyPublicUrl} className="text-gray-400 hover:text-white transition-colors" title="Copy URL">
                        <FaShareAlt className="text-xs" />
                      </button>
                    </div>
                  )}

                  {/* Bio Page Body */}
                  <div className="px-5 pt-8 pb-12 flex flex-col items-center text-center space-y-5 flex-1 relative z-10 custom-scrollbar">
                    
                    {/* Announcement Banner */}
                    {theme.announcement_active && theme.announcement_banner && (
                      <div className="w-full py-2 px-3 text-center text-[11px] font-bold bg-[#0071E3] text-white rounded-xl shadow-md flex items-center justify-center gap-1.5">
                        <span className="truncate">{theme.announcement_banner}</span>
                        <FaExternalLinkAlt className="text-[9px]" />
                      </div>
                    )}

                    {/* Avatar */}
                    <div className="relative">
                      <div className="w-24 h-24 rounded-full p-[2px] bg-white/25 backdrop-blur-xl shadow-lg flex items-center justify-center overflow-hidden">
                        {avatarUrl ? (
                          <img src={avatarUrl} alt="" className="w-full h-full object-cover rounded-full" />
                        ) : (
                          <div className="w-full h-full rounded-full bg-gradient-to-tr from-amber-400 via-rose-500 to-indigo-600 flex items-center justify-center text-2xl font-black text-white">
                            {title ? title[0] : 'U'}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Display Name & Verified Badge */}
                    <div className="space-y-1 text-center">
                      <div className="flex items-center justify-center gap-1.5">
                        <h2 className="text-xl font-bold tracking-tight text-white">
                          {title || 'Your Name'}
                        </h2>
                        {verifiedBadge && <span className="text-blue-400 font-bold">✓</span>}
                      </div>
                      {bio && (
                        <p className="text-xs text-white/80 max-w-[260px] leading-relaxed mx-auto">
                          {bio}
                        </p>
                      )}
                    </div>

                    {/* Social Dock Pills */}
                    {socialLinks && Object.values(socialLinks).some(Boolean) && (
                      <div className="flex items-center justify-center gap-3 py-1.5 px-4 rounded-full bg-white/10 backdrop-blur-xl border border-white/15 text-xs text-white">
                        {Object.entries(socialLinks).map(([plat, url]) => {
                          if (!url) return null;
                          const Icon = SOCIAL_ICON_MAP[plat] || SOCIAL_ICON_MAP.default;
                          return (
                            <a
                              key={plat}
                              href={url}
                              target="_blank"
                              rel="noreferrer"
                              className="hover:opacity-80 transition cursor-pointer"
                            >
                              <Icon className="text-sm" />
                            </a>
                          );
                        })}
                      </div>
                    )}

                    {/* Multi-Page Navigation Pills */}
                    {pages.length > 1 && (
                      <div className="flex items-center justify-center gap-1.5 p-1 rounded-full bg-white/10 backdrop-blur-xl border border-white/15">
                        {pages.map((pg) => (
                          <button
                            key={pg.id}
                            onClick={() => handleSelectPage(pg.id)}
                            className={`px-3 py-1 text-xs font-semibold rounded-full transition-all ${
                              activePageId === pg.id
                                ? 'bg-white text-black shadow-sm'
                                : 'text-white/70 hover:text-white'
                            }`}
                          >
                            {pg.title}
                          </button>
                        ))}
                      </div>
                    )}

                    {/* Cards Stack */}
                    <div
                      className="w-full pt-1"
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: `${theme.card_spacing ?? 12}px`,
                      }}
                    >
                      {activeBlocks.length === 0 ? (
                        <div className="py-10 text-center text-xs text-white/50 border border-dashed border-white/20 rounded-2xl p-4">
                          No blocks on this page. Add links from the left panel.
                        </div>
                      ) : (
                        activeBlocks.map((block) => {
                          const cardObj = getTactileCardStyles(theme.card_style, theme, block.is_featured, {
                            animation: block.animation,
                            has_custom_bg: Boolean(block.has_custom_bg),
                            card_bg: block.card_bg,
                            has_custom_border: Boolean(block.has_custom_border),
                            card_border: block.card_border,
                            has_custom_text_color: Boolean(block.has_custom_text_color),
                            card_text_color: block.card_text_color,
                          });

                          return (
                            <div
                              key={block.id}
                              onClick={() => setEditingBlock(block)}
                              style={cardObj.style}
                              className={`w-full p-4 rounded-2xl bg-white/15 backdrop-blur-xl border border-white/20 shadow-lg text-left flex items-center justify-between cursor-pointer hover:bg-white/25 transition group ${cardObj.className}`}
                            >
                              <div className="flex items-center gap-3 min-w-0">
                                {block.media_url ? (
                                  <img
                                    src={block.media_url}
                                    alt=""
                                    className="w-10 h-10 rounded-xl object-cover shrink-0 shadow-xs"
                                  />
                                ) : (
                                  <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center text-lg shrink-0">
                                    {block.is_featured ? '⚡' : block.type === 'video' ? '▶' : block.type === 'newsletter' ? '✉️' : '🔗'}
                                  </div>
                                )}
                                <div className="min-w-0">
                                  <div className="text-sm font-semibold text-white truncate">
                                    {block.title || block.headline || 'View Link'}
                                  </div>
                                  <div className="text-[11px] text-white/70 truncate">
                                    {block.subtitle || block.url || ''}
                                  </div>
                                </div>
                              </div>
                              <span className="text-white/60 group-hover:text-white group-hover:translate-x-0.5 transition-all text-sm shrink-0 ml-2">
                                →
                              </span>
                            </div>
                          );
                        })
                      )}
                    </div>

                    {/* Watermark */}
                    <div className="pt-6 pb-2 text-[11px] font-medium text-white/50 select-none">
                      Crafted with <span className="font-bold text-white/80">Unravler</span>
                    </div>

                    {/* Bottom Home Bar (Mobile Mode) */}
                    {deviceMode === 'mobile' && (
                      <div className="w-32 h-1 bg-white/40 rounded-full mx-auto mb-2 mt-auto shrink-0" />
                    )}

                  </div>
                </div>
              </div>
            </div>

          </div>

          {/* 3. RIGHT COLUMN: Inspector Drawer (~340px) */}
          <div className="w-80 md:w-84 shrink-0 h-full overflow-hidden flex flex-col border-l border-black/[0.06] dark:border-white/[0.08] apple-glass-panel relative z-20 shadow-xs">
            <BioInspectorDrawer
              theme={theme}
              setTheme={setTheme}
              socialLinks={socialLinks}
              setSocialLinks={setSocialLinks}
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

        {/* 2. Add New Block Modal (Apple Sheet Style) */}
        {addBlockModalOpen && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-4">
            <div className="bg-white/95 dark:bg-[#1C1C1E]/95 backdrop-blur-2xl border border-black/[0.08] dark:border-white/[0.12] rounded-[28px] max-w-md w-full p-6 shadow-2xl space-y-4 text-gray-900 dark:text-white">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-gray-900 dark:text-white">Add Content Block</h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Choose a high-converting block archetype</p>
                </div>
                <button onClick={() => setAddBlockModalOpen(false)} className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 p-2 rounded-full hover:bg-black/[0.05] dark:hover:bg-white/[0.08] transition-colors">
                  <FaTimes />
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2.5">
                {[
                  { id: 'link', label: 'Custom Link', desc: 'Direct URL with badge & subtitle', icon: FaExternalLinkAlt, color: 'text-blue-500' },
                  { id: 'folder', label: 'Folder / Group', desc: 'Group links into a sleek accordion', icon: FaFolder, color: 'text-amber-500' },
                  { id: 'media_card', label: 'Media Card', desc: 'Hero photo banner with subtitle & link', icon: FaImage, color: 'text-rose-500' },
                  { id: 'embed', label: 'YouTube / Spotify', desc: 'Embedded video & podcast player', icon: FaPlay, color: 'text-purple-500' },
                  { id: 'feed_grid', label: 'Instagram Feed', desc: 'Live mirror of recent social posts', icon: FaLayerGroup, color: 'text-emerald-500' },
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
                    className="p-3.5 rounded-2xl border border-black/[0.06] dark:border-white/[0.08] hover:border-blue-500/50 bg-black/[0.02] dark:bg-white/[0.04] hover:bg-black/[0.04] dark:hover:bg-white/[0.06] text-left transition-all hover:scale-[1.02] cursor-pointer group"
                  >
                    <typeItem.icon className={`text-lg mb-2 ${typeItem.color} group-hover:scale-110 transition-transform`} />
                    <p className="text-xs font-bold text-gray-900 dark:text-white">{typeItem.label}</p>
                    <p className="text-[10px] text-gray-500 dark:text-gray-400 leading-tight mt-0.5">{typeItem.desc}</p>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* 3. QR Code Live Testing Modal (Apple Style) */}
        {qrModalOpen && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-4">
            <div className="bg-white/95 dark:bg-[#1C1C1E]/95 backdrop-blur-2xl border border-black/[0.08] dark:border-white/[0.12] rounded-[28px] max-w-sm w-full p-6 shadow-2xl text-center space-y-4 text-gray-900 dark:text-white">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-bold text-gray-900 dark:text-white">Scan on Mobile</h3>
                <button onClick={() => setQrModalOpen(false)} className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 p-2 rounded-full hover:bg-black/[0.05] dark:hover:bg-white/[0.08]">
                  <FaTimes />
                </button>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Point your iPhone or Android camera at the QR code to view your Smart Bio live in real-time.
              </p>
              <div className="bg-white p-4 rounded-2xl inline-block shadow-lg mx-auto">
                <img
                  src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(publicUrl)}`}
                  alt="QR Code"
                  className="w-44 h-44 mx-auto rounded-lg"
                />
              </div>
              <div className="p-2.5 rounded-xl bg-black/[0.04] dark:bg-white/[0.06] font-mono text-xs text-blue-600 dark:text-blue-400 truncate border border-black/[0.06] dark:border-white/[0.08]">
                {publicUrl}
              </div>
            </div>
          </div>
        )}

      </div>
    </DashboardLayout>
  );
}
