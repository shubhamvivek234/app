import React, { useState, useEffect, useRef } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
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
      <div className="h-[calc(100vh-3.5rem)] flex flex-col bg-zinc-950 overflow-hidden font-sans select-none">
        
        {/* ── TOP STUDIO CONTROL HEADER (Flush & High-Density) ── */}
        <div className="h-12 sm:h-13 bg-zinc-900/95 border-b border-zinc-800/90 px-3 sm:px-5 flex items-center justify-between z-30 shrink-0 backdrop-blur-md">
          {/* Left: Branding & Handle Pill */}
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex items-center gap-2 shrink-0">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse ring-4 ring-emerald-500/20" />
              <span className="text-xs font-black uppercase tracking-widest text-zinc-300 hidden lg:inline-block">
                Smart Bio Studio
              </span>
            </div>
            <div className="h-4 w-[1px] bg-zinc-800 hidden lg:block" />
            <div className="flex items-center gap-1 text-xs text-zinc-300 font-mono bg-zinc-950/90 px-2.5 py-1 rounded-xl border border-zinc-800/80 shadow-inner truncate">
              <span className="text-zinc-500 font-normal">bio/</span>
              <input
                type="text"
                value={handle}
                onChange={(e) => setHandle(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))}
                placeholder="handle"
                className="bg-transparent font-bold text-emerald-400 outline-none w-20 sm:w-28 focus:text-white transition-colors"
              />
            </div>
          </div>

          {/* Center: Device Mode Switcher */}
          <div className="flex items-center gap-1 p-0.5 rounded-xl bg-zinc-950/90 border border-zinc-800/70 shadow-xs">
            <button
              onClick={() => { setDeviceMode('mobile'); setZoomScale(1); }}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                deviceMode === 'mobile'
                  ? 'bg-zinc-800 text-white shadow-xs'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
              title="iPhone 16 Pro (Mobile)"
            >
              <FaMobileAlt className="text-xs" />
              <span className="hidden md:inline">Mobile</span>
            </button>
            <button
              onClick={() => { setDeviceMode('tablet'); setZoomScale(0.95); }}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                deviceMode === 'tablet'
                  ? 'bg-zinc-800 text-white shadow-xs'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
              title="iPad / Tablet"
            >
              <FaTabletAlt className="text-xs" />
              <span className="hidden md:inline">Tablet</span>
            </button>
            <button
              onClick={() => { setDeviceMode('desktop'); setZoomScale(0.9); }}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                deviceMode === 'desktop'
                  ? 'bg-zinc-800 text-white shadow-xs'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
              title="Desktop Browser"
            >
              <FaDesktop className="text-xs" />
              <span className="hidden md:inline">Desktop</span>
            </button>
          </div>

          {/* Right: Actions, QR, Zoom & Publish CTA */}
          <div className="flex items-center gap-2 shrink-0">
            {/* Zoom Controls */}
            <div className="hidden xl:flex items-center gap-1 px-2 border-r border-zinc-800 text-xs font-mono text-zinc-400">
              <button
                onClick={() => setZoomScale((z) => Math.max(0.75, +(z - 0.05).toFixed(2)))}
                className="p-1 hover:text-white rounded-md hover:bg-zinc-800 transition-colors"
                title="Zoom Out"
              >
                <FaSearchMinus />
              </button>
              <span className="w-10 text-center font-bold text-zinc-300">{Math.round(zoomScale * 100)}%</span>
              <button
                onClick={() => setZoomScale((z) => Math.min(1.15, +(z + 0.05).toFixed(2)))}
                className="p-1 hover:text-white rounded-md hover:bg-zinc-800 transition-colors"
                title="Zoom In"
              >
                <FaSearchPlus />
              </button>
            </div>

            {publicUrl && (
              <button
                onClick={() => setQrModalOpen(true)}
                className="p-1.5 text-zinc-400 hover:text-white bg-zinc-800/60 hover:bg-zinc-800 border border-zinc-700/60 rounded-xl transition-all"
                title="Scan QR Code on Phone"
              >
                <FaQrcode className="text-xs" />
              </button>
            )}

            {publicUrl && (
              <button
                onClick={copyPublicUrl}
                className="px-2.5 py-1.5 text-xs font-bold text-zinc-300 hover:text-white bg-zinc-800/60 hover:bg-zinc-800 border border-zinc-700/60 rounded-xl transition-all hidden sm:flex items-center gap-1.5"
                title="Copy Public Link"
              >
                <FaCopy className="text-zinc-400 text-[10px]" /> Copy
              </button>
            )}

            {publicUrl && (
              <a
                href={publicUrl}
                target="_blank"
                rel="noreferrer"
                className="px-2.5 py-1.5 text-xs font-bold text-zinc-300 hover:text-white bg-zinc-800/60 hover:bg-zinc-800 border border-zinc-700/60 rounded-xl transition-all hidden sm:flex items-center gap-1.5"
                title="View Live Public Page"
              >
                <FaExternalLinkAlt className="text-zinc-400 text-[9px]" /> Live
              </a>
            )}

            <button
              onClick={() => handleSaveAll()}
              disabled={saving}
              className="px-4 py-1.5 text-xs font-black bg-gradient-to-r from-indigo-500 to-violet-600 hover:from-indigo-600 hover:to-violet-700 text-white rounded-xl shadow-md shadow-indigo-500/25 transition-all flex items-center gap-1.5 disabled:opacity-50 cursor-pointer active:scale-95"
            >
              <FaSave className="text-xs" /> {saving ? 'Publishing…' : 'Publish Bio'}
            </button>
          </div>
        </div>

        {/* ── 3-COLUMN STUDIO WORKSPACE ── */}
        <div className="flex-1 flex overflow-hidden">
          
          {/* 1. LEFT COLUMN: Outline & Content Tree (~320px) */}
          <div className="w-72 md:w-80 lg:w-84 xl:w-88 shrink-0 h-full overflow-hidden flex flex-col border-r border-zinc-800/90 bg-zinc-900/50 relative z-20 shadow-lg">
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

          {/* 2. CENTER CANVAS: Contained & Responsive Machined Hardware Viewport */}
          <div className="flex-1 min-w-0 h-full bg-zinc-950 flex flex-col items-center justify-start p-3 sm:p-4 md:p-6 overflow-x-hidden overflow-y-auto relative custom-scrollbar z-10">
            
            {/* Background Studio Grid & Stage Spotlight */}
            <div className="absolute inset-0 bg-[radial-gradient(#27272a_1px,transparent_1px)] [background-size:24px_24px] pointer-events-none opacity-50" />
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-gradient-to-tr from-indigo-500/10 via-purple-500/10 to-pink-500/10 blur-[100px] rounded-full pointer-events-none" />

            {/* Stage Quick Replay Pill */}
            <div className="relative z-20 mb-2 flex items-center justify-center">
              <button
                onClick={() => setPreviewKey((k) => k + 1)}
                className="px-3 py-1 rounded-full bg-zinc-900/80 hover:bg-zinc-900 border border-zinc-800 text-[11px] font-bold text-zinc-400 hover:text-white transition-all flex items-center gap-1.5 shadow-xs"
                title="Replay Entrance Animations"
              >
                <FaRedoAlt className="text-[10px]" /> Replay Animations
              </button>
            </div>

            {/* ── THE MACHINED HARDWARE DEVICE CHASSIS (Contained & Centered) ── */}
            <div
              style={{ transform: `scale(${zoomScale})`, transformOrigin: 'top center' }}
              className="transition-transform duration-300 flex items-center justify-center my-auto relative z-20 max-w-full"
            >
              {/* Outer Metallic Titanium Chassis */}
              <div
                className={`relative transition-all duration-300 ${
                  deviceMode === 'mobile'
                    ? 'w-[360px] sm:w-[380px] h-[750px] sm:h-[770px] rounded-[50px] p-[10px] bg-gradient-to-b from-zinc-700 via-zinc-800 to-zinc-950 shadow-[0_25px_80px_-15px_rgba(0,0,0,0.6),0_0_0_1px_rgba(255,255,255,0.18)_inset]'
                    : deviceMode === 'tablet'
                    ? 'w-[440px] sm:w-[480px] md:w-[500px] h-[680px] sm:h-[720px] rounded-[36px] p-[10px] bg-gradient-to-b from-zinc-700 via-zinc-800 to-zinc-950 shadow-[0_25px_80px_-15px_rgba(0,0,0,0.6),0_0_0_1px_rgba(255,255,255,0.18)_inset]'
                    : 'w-[480px] sm:w-[540px] md:w-[580px] xl:w-[620px] h-[680px] sm:h-[720px] rounded-[24px] p-[8px] bg-gradient-to-b from-zinc-700 via-zinc-800 to-zinc-900 shadow-[0_25px_80px_-15px_rgba(0,0,0,0.6),0_0_0_1px_rgba(255,255,255,0.15)_inset]'
                }`}
              >
                {/* Physical Hardware Buttons (Mobile Mode) */}
                {deviceMode === 'mobile' && (
                  <>
                    <div className="absolute -left-[4px] top-28 w-[4px] h-7 bg-zinc-600 rounded-l-md shadow-inner" />
                    <div className="absolute -left-[4px] top-40 w-[4px] h-12 bg-zinc-600 rounded-l-md shadow-inner" />
                    <div className="absolute -left-[4px] top-56 w-[4px] h-12 bg-zinc-600 rounded-l-md shadow-inner" />
                    <div className="absolute -right-[4px] top-44 w-[4px] h-16 bg-zinc-600 rounded-r-md shadow-inner" />
                  </>
                )}

                {/* Inner Display Enclosure */}
                <div
                  className={`w-full h-full bg-black overflow-hidden relative flex flex-col shadow-inner ${
                    deviceMode === 'mobile'
                      ? 'rounded-[40px]'
                      : deviceMode === 'tablet'
                      ? 'rounded-[28px]'
                      : 'rounded-[18px]'
                  }`}
                >
                  {/* Specular Diagonal Glass Gloss Reflection */}
                  <div className="pointer-events-none absolute inset-0 z-40 bg-gradient-to-tr from-transparent via-white/[0.02] to-white/[0.08]" />

                  {/* Top iOS Status Bar + Dynamic Island (Mobile Mode) */}
                  {deviceMode === 'mobile' && (
                    <div className="relative w-full h-10 shrink-0 px-6 pt-1.5 flex items-center justify-between z-30 select-none bg-transparent">
                      <span className="text-[12px] font-semibold tracking-tight text-white/90">9:41</span>

                      {/* Centered Dynamic Island Pill */}
                      <div className="absolute left-1/2 -translate-x-1/2 top-2 w-28 h-6 bg-black rounded-full flex items-center justify-between px-2.5 shadow-[0_0_0_1px_rgba(255,255,255,0.15)] z-40">
                        <div className="w-2.5 h-2.5 rounded-full bg-zinc-900 ring-1 ring-zinc-800 flex items-center justify-center">
                          <span className="w-1 h-1 rounded-full bg-blue-500/80 blur-[0.5px]" />
                        </div>
                        <div className="w-2 h-2 rounded-full bg-zinc-950" />
                      </div>

                      <div className="flex items-center gap-1.5 text-white/90 text-[10px]">
                        <FaSignal className="text-[9px]" />
                        <span className="text-[8px] font-bold">5G</span>
                        <FaWifi className="text-[10px]" />
                        <FaBatteryFull className="text-xs text-emerald-400" />
                      </div>
                    </div>
                  )}

                  {/* Desktop / Browser Header (Desktop & Tablet Mode) */}
                  {deviceMode !== 'mobile' && (
                    <div className="bg-zinc-900 border-b border-zinc-800 px-3.5 py-1.5 flex items-center justify-between text-xs shrink-0 z-30">
                      <div className="flex items-center gap-1.5">
                        <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80" />
                        <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
                        <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
                      </div>
                      <div className="bg-zinc-950/90 text-zinc-400 font-mono text-[11px] px-3.5 py-0.5 rounded-full border border-zinc-800/80 truncate max-w-xs">
                        {handle ? `https://unravler.bio/${handle}` : 'https://unravler.bio/preview'}
                      </div>
                      <button onClick={copyPublicUrl} className="text-zinc-400 hover:text-white">
                        <FaShareAlt className="text-xs" />
                      </button>
                    </div>
                  )}

                  {/* ── LIVE BIO CANVAS VIEWPORT ── */}
                  <div
                    key={previewKey}
                    style={{
                      background: theme.background_gradient || theme.background_color || '#FDFBF7',
                      color: theme.text_color || '#18181B',
                      fontFamily: theme.font_family || 'Plus Jakarta Sans, sans-serif',
                    }}
                    className="flex-1 overflow-y-auto p-4 sm:p-5 flex flex-col items-center relative custom-scrollbar select-none"
                  >
                    {/* Procedural Film Grain Overlay */}
                    {(theme.background_effect === 'grain' || theme.preset === 'matcha_washi' || theme.preset === 'editorial_cream') && (
                      <div
                        className="pointer-events-none absolute inset-0 z-0 opacity-[0.04] mix-blend-overlay"
                        style={{
                          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`,
                        }}
                      />
                    )}

                    {/* Radiant Defocused Ambient Mesh Orbs */}
                    {(theme.background_effect === 'ambient_orbs' || theme.background_effect === 'mesh_glow' || theme.preset === 'liquid_aura' || theme.preset === 'tokyo_cyber') && (
                      <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
                        <div
                          className="absolute -top-16 -left-16 w-52 h-52 rounded-full blur-3xl opacity-40 animate-pulse"
                          style={{ background: theme.accent_color || '#6366F1' }}
                        />
                        <div
                          className="absolute top-1/2 -right-16 w-48 h-48 rounded-full blur-3xl opacity-35"
                          style={{ background: theme.card_text_color || '#EC4899' }}
                        />
                      </div>
                    )}

                    {/* Announcement Top Banner */}
                    {theme.announcement_active && theme.announcement_banner && (
                      <div
                        className="w-full -mx-4 -mt-4 mb-4 py-2 px-3 text-center text-[11px] font-bold bg-indigo-600 text-white flex items-center justify-center gap-1.5 shadow-md relative z-20 animate-fade-in"
                      >
                        <span className="truncate">{theme.announcement_banner}</span>
                        <FaExternalLinkAlt className="text-[9px]" />
                      </div>
                    )}

                    {/* Header Layout & Profile Hero */}
                    <div className="w-full flex flex-col items-center text-center mb-4 relative z-10">
                      {/* Avatar with Custom Styling */}
                      <div
                        style={avatarStyles}
                        className="rounded-full overflow-hidden flex items-center justify-center mb-2.5 bg-black/10 shrink-0 ring-4 ring-black/5 dark:ring-white/10 shadow-lg relative group transition-transform hover:scale-105"
                      >
                        {avatarUrl ? (
                          <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
                        ) : (
                          <span className="text-2xl font-black uppercase tracking-wider" style={{ color: theme.text_color }}>
                            {title ? title[0] : 'U'}
                          </span>
                        )}
                      </div>

                      {/* Display Name with Verified Badge */}
                      <h2 className="text-base font-black tracking-tight flex items-center justify-center gap-1.5" style={{ color: theme.text_color }}>
                        {title || 'Your Name'}
                        {verifiedBadge && (
                          <span className="inline-flex items-center justify-center text-indigo-500 bg-indigo-500/10 rounded-full p-0.5" title="Verified Creator">
                            <FaCheckCircle className="text-xs text-indigo-500" />
                          </span>
                        )}
                      </h2>

                      {/* Handle / Slug */}
                      <p className="text-[11px] font-mono opacity-60 tracking-tight" style={{ color: theme.text_color }}>
                        @{handle || 'handle'}
                      </p>

                      {/* Bio Copy */}
                      {bio && (
                        <p className="text-xs opacity-85 pt-1.5 leading-relaxed max-w-xs font-normal" style={{ color: theme.text_color }}>
                          {bio}
                        </p>
                      )}
                    </div>

                    {/* Social Dock Bar */}
                    {socialLinks && Object.keys(socialLinks).some((k) => socialLinks[k]) && (
                      <div className="flex items-center justify-center gap-2 mb-4 flex-wrap relative z-10">
                        {Object.entries(socialLinks).map(([plat, url]) => {
                          if (!url) return null;
                          const Icon = SOCIAL_ICON_MAP[plat] || SOCIAL_ICON_MAP.default;
                          return (
                            <div
                              key={plat}
                              style={{
                                color: theme.text_color,
                                width: `${socialIconPx + 14}px`,
                                height: `${socialIconPx + 14}px`,
                              }}
                              className="rounded-full bg-black/5 dark:bg-white/10 border border-black/5 dark:border-white/10 backdrop-blur-md flex items-center justify-center shadow-xs transition-transform hover:scale-110 active:scale-95 cursor-pointer"
                            >
                              <Icon style={{ fontSize: `${socialIconPx}px` }} />
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* Multi-Page Sub-Navigation Pill Strip */}
                    {pages.length > 1 && (theme.navigation_style || 'pills') === 'pills' && (
                      <div className="flex items-center justify-center gap-1.5 mb-5 p-1 rounded-full bg-black/5 dark:bg-white/10 backdrop-blur-md border border-black/5 dark:border-white/10 relative z-10 shadow-xs">
                        {pages.map((pg) => {
                          const isActive = pg.id === activePageId;
                          return (
                            <button
                              key={pg.id}
                              onClick={() => handleSelectPage(pg.id)}
                              className={`px-4 py-1 text-xs font-bold rounded-full transition-all duration-200 ${
                                isActive
                                  ? 'bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 shadow-sm scale-100'
                                  : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white'
                              }`}
                            >
                              {pg.title}
                            </button>
                          );
                        })}
                      </div>
                    )}

                    {/* ── Content Blocks Stack in Live Preview ── */}
                    <div
                      className="w-full relative z-10"
                      style={{ display: 'flex', flexDirection: 'column', gap: `${blockGapPx}px` }}
                    >
                      {activeBlocks.length === 0 ? (
                        <div className="py-14 text-center text-xs opacity-50 border-2 border-dashed border-black/10 dark:border-white/10 rounded-3xl p-6 flex flex-col items-center gap-2">
                          <FaPlus className="text-lg opacity-40" />
                          <span>No blocks on this page.</span>
                          <span className="text-[10px] opacity-70">Add custom links, hero cards, or media from the left outline tree.</span>
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

                          const isFolder = block.type === 'folder' || block.type === 'tab_group';
                          const isBannerTop = block.layout === 'card_banner_top';
                          const isFolderOpen = Boolean(activeFolders[block.id]);

                          if (isFolder) {
                            return (
                              <div
                                key={block.id}
                                style={cardObj.style}
                                className={`w-full font-bold text-xs overflow-hidden transition-all shadow-sm ${cardObj.className}`}
                              >
                                <div
                                  onClick={() => toggleFolderPreview(block.id)}
                                  className="p-3.5 flex items-center justify-between cursor-pointer hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                                >
                                  <div className="flex items-center gap-2.5">
                                    <div className="p-2 rounded-xl bg-amber-500/10 text-amber-500">
                                      <FaFolder className="text-sm" />
                                    </div>
                                    <div>
                                      <p className="text-xs font-bold leading-tight" style={{ color: cardObj.style.color }}>
                                        {block.title || 'Folder / Group'}
                                      </p>
                                      {block.folder_items?.length > 0 && (
                                        <p className="text-[10px] opacity-60 font-normal mt-0.5" style={{ color: cardObj.style.color }}>
                                          {block.folder_items.length} sub-links
                                        </p>
                                      )}
                                    </div>
                                  </div>
                                  <div className="p-1 rounded-full text-zinc-400">
                                    {isFolderOpen ? <FaChevronUp className="text-xs" /> : <FaChevronDown className="text-xs" />}
                                  </div>
                                </div>

                                {/* Expandable Folder Nested Sub-Links */}
                                {isFolderOpen && (
                                  <div className="p-3 pt-0 space-y-2 border-t border-black/5 dark:border-white/5 mt-1 animate-fade-in">
                                    {(block.folder_items || []).length === 0 ? (
                                      <p className="text-[10px] opacity-60 text-center py-2" style={{ color: cardObj.style.color }}>
                                        Folder is empty. Click edit on left tree to add sub-links.
                                      </p>
                                    ) : (
                                      block.folder_items.map((subItem, sIdx) => (
                                        <div
                                          key={subItem.id || sIdx}
                                          className="py-2.5 px-3 rounded-xl bg-black/5 dark:bg-white/5 flex items-center justify-between text-xs font-semibold hover:bg-black/10 transition-colors"
                                          style={{ color: cardObj.style.color }}
                                        >
                                          <div className="flex items-center gap-2 truncate">
                                            <FaExternalLinkAlt className="text-[9px] opacity-50 flex-shrink-0" />
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
                              className={`w-full font-bold text-xs cursor-pointer transition-all hover:scale-[1.02] active:scale-[0.98] overflow-hidden group shadow-sm ${cardObj.className} ${
                                isBannerTop ? 'flex flex-col text-left' : 'py-3 px-3.5 flex items-center justify-between text-left'
                              }`}
                            >
                              {isBannerTop && block.media_url && (
                                <div className="w-full h-32 overflow-hidden bg-black/10 relative">
                                  <img src={block.media_url} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
                                  <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent pointer-events-none" />
                                </div>
                              )}

                              <div className={`flex items-center gap-3 w-full ${isBannerTop ? 'p-3.5' : ''}`}>
                                {!isBannerTop && block.media_url && (
                                  <img src={block.media_url} alt="" className="w-10 h-10 rounded-xl object-cover flex-shrink-0 shadow-xs" />
                                )}

                                <div className="min-w-0 flex-1">
                                  <div className="flex items-center gap-1.5 flex-wrap">
                                    {block.is_featured && <FaBolt className="text-amber-400 text-xs shrink-0 animate-pulse" />}
                                    <span className="truncate font-black" style={{ color: cardObj.style.color }}>
                                      {block.title || block.headline || 'View Link'}
                                    </span>
                                    {block.badge && (
                                      <span className="px-2 py-0.5 text-[8px] font-black uppercase tracking-wider rounded-full bg-gradient-to-r from-rose-500 to-pink-500 text-white shadow-xs">
                                        {block.badge}
                                      </span>
                                    )}
                                  </div>
                                  {block.subtitle && (
                                    <p className="text-[10px] opacity-75 font-normal truncate mt-0.5" style={{ color: cardObj.style.color }}>
                                      {block.subtitle}
                                    </p>
                                  )}
                                </div>

                                <div
                                  className="w-6 h-6 rounded-full bg-black/5 dark:bg-white/10 flex items-center justify-center opacity-60 group-hover:opacity-100 group-hover:scale-110 transition-all shrink-0"
                                  style={{ color: cardObj.style.color }}
                                >
                                  <FaExternalLinkAlt className="text-[9px]" />
                                </div>
                              </div>
                            </div>
                          );
                        })
                      )}
                    </div>

                    {/* Bottom Floating iOS Home Bar (Mobile Mode) */}
                    {deviceMode === 'mobile' && (
                      <div className="w-32 h-1 bg-current opacity-25 rounded-full mx-auto mt-6 mb-1 shrink-0" />
                    )}

                  </div>
                </div>
              </div>
            </div>

          </div>

          {/* 3. RIGHT COLUMN: Inspector Drawer (~340px) */}
          <div className="w-80 md:w-84 lg:w-88 xl:w-92 shrink-0 h-full overflow-hidden flex flex-col border-l border-zinc-800/90 bg-zinc-900/50 relative z-20 shadow-lg">
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
          <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-zinc-900 border border-zinc-800 rounded-3xl max-w-md w-full p-6 shadow-2xl space-y-4 text-white">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-black text-white">Add Content Block</h3>
                  <p className="text-xs text-zinc-400">Choose a high-converting block archetype</p>
                </div>
                <button onClick={() => setAddBlockModalOpen(false)} className="text-zinc-400 hover:text-white p-2 rounded-xl hover:bg-zinc-800 transition-colors">
                  <FaTimes />
                </button>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {[
                  { id: 'link', label: 'Custom Link', desc: 'Direct URL with badge & subtitle', icon: FaExternalLinkAlt, color: 'text-indigo-400' },
                  { id: 'folder', label: 'Folder / Group', desc: 'Group links into a sleek accordion', icon: FaFolder, color: 'text-amber-400' },
                  { id: 'media_card', label: 'Media Card', desc: 'Hero photo banner with subtitle & link', icon: FaImage, color: 'text-rose-400' },
                  { id: 'embed', label: 'YouTube / Spotify', desc: 'Embedded video & podcast player', icon: FaPlay, color: 'text-purple-400' },
                  { id: 'feed_grid', label: 'Instagram Feed', desc: 'Live mirror of recent social posts', icon: FaLayerGroup, color: 'text-emerald-400' },
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
                    className="p-3.5 rounded-2xl border border-zinc-800 hover:border-indigo-500 bg-zinc-950/60 text-left transition-all hover:scale-[1.02] cursor-pointer group"
                  >
                    <typeItem.icon className={`text-lg mb-2 ${typeItem.color} group-hover:scale-110 transition-transform`} />
                    <p className="text-xs font-bold text-white">{typeItem.label}</p>
                    <p className="text-[10px] text-zinc-400 leading-tight mt-0.5">{typeItem.desc}</p>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* 3. QR Code Live Testing Modal */}
        {qrModalOpen && (
          <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-zinc-900 border border-zinc-800 rounded-3xl max-w-sm w-full p-6 shadow-2xl text-center space-y-4 text-white">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-black">Scan on Mobile</h3>
                <button onClick={() => setQrModalOpen(false)} className="text-zinc-400 hover:text-white">
                  <FaTimes />
                </button>
              </div>
              <p className="text-xs text-zinc-400">
                Point your iPhone or Android camera at the QR code to view your Smart Bio live in real-time.
              </p>
              <div className="bg-white p-4 rounded-2xl inline-block shadow-lg mx-auto">
                <img
                  src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(publicUrl)}`}
                  alt="QR Code"
                  className="w-44 h-44 mx-auto rounded-lg"
                />
              </div>
              <div className="p-2.5 rounded-xl bg-zinc-950 font-mono text-xs text-emerald-400 truncate border border-zinc-800">
                {publicUrl}
              </div>
            </div>
          </div>
        )}

      </div>
    </DashboardLayout>
  );
}
