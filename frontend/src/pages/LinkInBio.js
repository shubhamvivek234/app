import React, { useState, useEffect, useRef } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import UnravlerLogo from '@/components/UnravlerLogo';
import { useTheme } from '@/context/ThemeContext';
import {
  getMyBioPage,
  saveMyBioPage,
  deleteMyBioPage,
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
  FaChartLine,
  FaClock,
  FaTrashAlt,
  FaExclamationTriangle,
} from 'react-icons/fa';
import { SiThreads, SiBluesky } from 'react-icons/si';

import BioOutlineTree from '@/components/bio/BioOutlineTree';
import BioInspectorDrawer from '@/components/bio/BioInspectorDrawer';
import BioBlockEditorModal from '@/components/bio/BioBlockEditorModal';
import BioAnalyticsModal from '@/components/bio/BioAnalyticsModal';
import BioScheduleModal from '@/components/bio/BioScheduleModal';
import {
  THEME_PRESETS,
  loadGoogleFont,
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
  const [analyticsModalOpen, setAnalyticsModalOpen] = useState(false);
  const [scheduleModalOpen, setScheduleModalOpen] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);
  const [deletedBlocks, setDeletedBlocks] = useState([]);
  const [activeFolders, setActiveFolders] = useState({});

  // History for Undo / Redo
  const [history, setHistory] = useState([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const isUndoRedoAction = useRef(false);
  const historyIdxRef = useRef(-1);
  historyIdxRef.current = historyIdx;

  // Scheduling & Visibility state
  const [pageSchedule, setPageSchedule] = useState({
    enabled: false,
    start_at: '',
    end_at: '',
  });
  const [isPublished, setIsPublished] = useState(true);

  // Permanent Delete Modal state
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);

  // Format ISO strings to datetime-local input value (YYYY-MM-DDTHH:mm)
  const formatIsoToLocalInput = (isoStr) => {
    if (!isoStr) return '';
    try {
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return '';
      const pad = (n) => String(n).padStart(2, '0');
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch {
      return '';
    }
  };

  // Convert datetime-local input to ISO string for API
  const formatLocalToIso = (localStr) => {
    if (!localStr) return null;
    try {
      const d = new Date(localStr);
      if (isNaN(d.getTime())) return null;
      return d.toISOString();
    } catch {
      return null;
    }
  };

  // Compute live schedule status badge
  const getScheduleStatus = () => {
    if (!isPublished) {
      return {
        label: 'Unpublished',
        dot: 'bg-zinc-400',
        color: 'bg-zinc-100 text-zinc-600 border-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:border-zinc-700',
      };
    }
    if (!pageSchedule?.enabled) {
      return {
        label: 'Live',
        dot: 'bg-emerald-500',
        color: 'bg-emerald-50 text-emerald-600 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-800/40',
      };
    }
    const now = new Date();
    const start = pageSchedule.start_at ? new Date(pageSchedule.start_at) : null;
    const end = pageSchedule.end_at ? new Date(pageSchedule.end_at) : null;

    if (start && !isNaN(start.getTime()) && now < start) {
      return {
        label: 'Scheduled',
        dot: 'bg-blue-500',
        color: 'bg-blue-50 text-[#0071E3] border-blue-200 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-800/40',
      };
    }
    if (end && !isNaN(end.getTime()) && now > end) {
      return {
        label: 'Expired',
        dot: 'bg-amber-500',
        color: 'bg-amber-50 text-amber-600 border-amber-200 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-800/40',
      };
    }
    return {
      label: 'Live (Timed)',
      dot: 'bg-emerald-500',
      color: 'bg-emerald-50 text-emerald-600 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-800/40',
    };
  };

  const publicUrl = handle
    ? `${window.location.origin}/bio/${handle}${activePageId !== 'home' ? `?page=${pages.find((p) => p.id === activePageId)?.slug || activePageId}` : ''}`
    : '';

  // Dynamically load Google Font
  useEffect(() => {
    if (theme?.font_family) {
      loadGoogleFont(theme.font_family);
    }
  }, [theme?.font_family]);

  // Initial Load
  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const res = await getMyBioPage();
        const d = res?.data || res;
        if (d && (d.handle || d.title || d.blocks)) {
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

          if (d.page_schedule) {
            setPageSchedule({
              enabled: Boolean(d.page_schedule.enabled),
              start_at: formatIsoToLocalInput(d.page_schedule.start_at),
              end_at: formatIsoToLocalInput(d.page_schedule.end_at),
            });
          }

          if (d.is_published !== undefined) {
            setIsPublished(Boolean(d.is_published));
          }

          if (d.theme) {
            setTheme((prev) => ({ ...prev, ...d.theme }));
          }

          let initialPages = [];
          if (Array.isArray(d.pages) && d.pages.length > 0) {
            initialPages = d.pages.map((p) => ({
              ...p,
              blocks: Array.isArray(p.blocks) ? p.blocks : [],
              description: p.description || '',
            }));
            const hasHome = initialPages.some((p) => p.id === 'home');
            if (!hasHome) {
              initialPages.unshift({
                id: 'home',
                title: d.title || 'Home',
                slug: 'home',
                description: d.bio || '',
                blocks: Array.isArray(d.blocks) ? d.blocks : [],
              });
            }
          } else {
            initialPages = [
              {
                id: 'home',
                title: d.title || 'Home',
                slug: 'home',
                description: d.bio || '',
                blocks: Array.isArray(d.blocks) ? d.blocks : [],
              },
            ];
          }
          setPages(initialPages);
          const initialActive = d.active_page_id || 'home';
          const activePageObj = initialPages.find((p) => p.id === initialActive) || initialPages[0];
          setActivePageId(activePageObj ? activePageObj.id : 'home');
          setBlocks(activePageObj && Array.isArray(activePageObj.blocks) ? activePageObj.blocks : []);
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

  // Atomic block state updater: guarantees current active page and blocks are in sync
  const updateCurrentPageBlocks = (updaterOrNewBlocks) => {
    setBlocks((prevBlocks) => {
      const nextBlocks = typeof updaterOrNewBlocks === 'function' ? updaterOrNewBlocks(prevBlocks) : updaterOrNewBlocks;
      setPages((prevPages) => {
        const pageExists = prevPages.some((p) => p.id === activePageId);
        if (pageExists) {
          return prevPages.map((p) => (p.id === activePageId ? { ...p, blocks: nextBlocks } : p));
        }
        return [
          ...prevPages,
          {
            id: activePageId,
            title: activePageId === 'home' ? 'Home' : 'Sub Page',
            slug: activePageId,
            description: '',
            blocks: nextBlocks,
          },
        ];
      });
      return nextBlocks;
    });
  };

  // Page Management Handlers
  const handleSelectPage = (pageId) => {
    if (pageId === activePageId) return;
    setPages((prev) => {
      // Commit active blocks to current page in pages
      const updated = prev.map((p) => (p.id === activePageId ? { ...p, blocks } : p));
      const targetPage = updated.find((p) => p.id === pageId);
      setBlocks(targetPage && Array.isArray(targetPage.blocks) ? targetPage.blocks : []);
      return updated;
    });
    setActivePageId(pageId);
  };

  const handleAddPage = (pageTitle, slug) => {
    const cleanTitle = (pageTitle || '').trim();
    if (!cleanTitle) return;
    const cleanSlug = (slug || cleanTitle).toLowerCase().replace(/[^a-z0-9_-]/g, '-');
    const newPage = {
      id: `page_${Date.now()}`,
      title: cleanTitle,
      slug: cleanSlug,
      description: '',
      blocks: [],
    };
    setPages((prev) => {
      const updated = prev.map((p) => (p.id === activePageId ? { ...p, blocks } : p));
      return [...updated, newPage];
    });
    setActivePageId(newPage.id);
    setBlocks([]);
    toast.success(`Created sub-page "${cleanTitle}"`);
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
        setBlocks(homePage && Array.isArray(homePage.blocks) ? homePage.blocks : []);
      }
      return filtered;
    });
    toast.success('Deleted sub-page');
  };

  const handleUpdateSubPage = (field, value) => {
    if (activePageId === 'home') {
      if (field === 'title') setTitle(value);
      if (field === 'description' || field === 'bio') setBio(value);
      return;
    }
    setPages((prev) =>
      prev.map((p) => {
        if (p.id === activePageId) {
          return { ...p, [field]: value };
        }
        return p;
      })
    );
  };

  const handleSaveCurrentPage = () => {
    const currentPageObj = pages.find((p) => p.id === activePageId);
    const pageLabel = activePageId === 'home' ? 'Home' : (currentPageObj?.title || 'Sub-Page');
    return handleSaveAll(null, `Saved "${pageLabel}" changes successfully!`);
  };

  // Save changes to backend
  const handleSaveAll = async (overrideState = null, customSuccessMsg = null) => {
    setSaving(true);
    try {
      // Synchronize current active page blocks into updatedPages
      const updatedPages = pages.map((p) => (p.id === activePageId ? { ...p, blocks } : p));
      const homeIdx = updatedPages.findIndex((p) => p.id === 'home');
      const homeBlocks = activePageId === 'home'
        ? blocks
        : (homeIdx !== -1 && Array.isArray(updatedPages[homeIdx].blocks) ? updatedPages[homeIdx].blocks : []);

      if (homeIdx !== -1) {
        updatedPages[homeIdx] = {
          ...updatedPages[homeIdx],
          title: title || 'Home',
          slug: 'home',
          description: bio || '',
          blocks: homeBlocks,
        };
      } else {
        updatedPages.unshift({
          id: 'home',
          title: title || 'Home',
          slug: 'home',
          description: bio || '',
          blocks: homeBlocks,
        });
      }

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
        blocks: homeBlocks,
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
        is_published: Boolean(isPublished),
        page_schedule: {
          enabled: Boolean(pageSchedule?.enabled),
          start_at: formatLocalToIso(pageSchedule?.start_at),
          end_at: formatLocalToIso(pageSchedule?.end_at),
        },
      };
      const res = await saveMyBioPage(payload);
      const savedHandle = res?.handle || safeHandle;
      if (res && res.handle) {
        setHandle(res.handle);
      }
      toast.success(customSuccessMsg || (isPublished ? '✨ Smart Bio saved live!' : 'Smart Bio saved in draft mode.'));

      // If user clicked the main header Publish button (no customSuccessMsg) and is published, open preview
      if (isPublished && !customSuccessMsg) {
        const targetUrl = `${window.location.origin}/bio/${savedHandle}${activePageId !== 'home' ? `?page=${pages.find((p) => p.id === activePageId)?.slug || activePageId}` : ''}`;
        window.open(targetUrl, '_blank', 'noopener,noreferrer');
      }
    } catch (err) {
      console.error('Save bio error:', err);
      const errMsg = err?.response?.data?.detail || err?.message || 'Failed to save Smart Bio';
      toast.error(errMsg);
    } finally {
      setSaving(false);
    }
  };

  // Permanent Deletion Handler
  const handlePermanentDelete = async () => {
    if (deleteConfirmText.trim().toLowerCase() !== handle.trim().toLowerCase()) {
      toast.error(`Please type "${handle}" exactly to confirm deletion.`);
      return;
    }
    setIsDeleting(true);
    try {
      await deleteMyBioPage();
      toast.success('Your Smart Bio page has been permanently deleted.');
      setDeleteModalOpen(false);
      setDeleteConfirmText('');
      // Reset state to initial defaults
      const freshHandle = `user_${Math.random().toString(36).slice(2, 7)}`;
      setHandle(freshHandle);
      setTitle('My Bio');
      setBio('');
      setAvatarUrl('');
      setBannerUrl('');
      setBlocks([]);
      setPages([{ id: 'home', title: 'Home', slug: 'home', blocks: [] }]);
      setPageSchedule({ enabled: false, start_at: '', end_at: '' });
      setIsPublished(false);
      setSocialLinks({
        instagram: '',
        twitter: '',
        youtube: '',
        linkedin: '',
        tiktok: '',
        spotify: '',
        github: '',
        discord: '',
      });
    } catch (err) {
      console.error('Delete bio error:', err);
      const errMsg = err?.response?.data?.detail || err?.message || 'Failed to delete Smart Bio page';
      toast.error(errMsg);
    } finally {
      setIsDeleting(false);
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

  // Block Actions (strictly confined to active page)
  const handleSaveBlock = (updatedBlock) => {
    updateCurrentPageBlocks((prev) => prev.map((b) => (b.id === updatedBlock.id ? updatedBlock : b)));
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
      updateCurrentPageBlocks((prev) => [...prev, newBlock]);
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
    updateCurrentPageBlocks((prev) => [...prev, duplicated]);
    toast.success('Block duplicated');
  };

  const handleToggleBlockActive = (blockId) => {
    updateCurrentPageBlocks((prev) =>
      prev.map((b) => (b.id === blockId ? { ...b, active: b.active === false ? true : false } : b))
    );
  };

  const handleDeleteBlock = (blockId) => {
    const target = blocks.find((b) => b.id === blockId);
    if (target) {
      setDeletedBlocks((prev) => [target, ...prev]);
      updateCurrentPageBlocks((prev) => prev.filter((b) => b.id !== blockId));
      setEditingBlock(null);
      toast.success('Moved block to trash bin');
    }
  };

  const handleRestoreBlock = (blockId) => {
    const target = deletedBlocks.find((b) => b.id === blockId);
    if (target) {
      setDeletedBlocks((prev) => prev.filter((b) => b.id !== blockId));
      updateCurrentPageBlocks((prev) => [...prev, target]);
      toast.success('Restored block');
    }
  };

  const handleClearDeletedBlocks = () => {
    setDeletedBlocks([]);
    toast.success('Emptied trash bin');
  };

  const handleReorderBlocks = (newBlocks) => {
    updateCurrentPageBlocks(newBlocks);
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
  const activePageObj = pages.find((p) => p.id === activePageId);
  const isSubPage = activePageId !== 'home' && Boolean(activePageObj);
  const previewTitle = isSubPage && activePageObj?.title ? activePageObj.title : (title || 'Your Name');
  const previewBio = isSubPage ? (activePageObj?.description || activePageObj?.bio || '') : (bio || '');
  const avatarStyles = getProfileAvatarStyles(theme);
  const blockGapPx = getBlockSpacingPx(theme);
  const socialIconPx = getSocialIconSizePx(theme);
  const headerAvatarSizePx = (theme.profile_picture_size !== undefined && Number(theme.profile_picture_size) >= 48)
    ? Number(theme.profile_picture_size)
    : 96;
  const headerTitleClass = headerAvatarSizePx <= 64 ? 'text-lg' : headerAvatarSizePx <= 100 ? 'text-xl' : 'text-2xl';

  return (
    <DashboardLayout noPadding={true}>
      <div className="h-[calc(100vh-3.5rem)] flex flex-col bg-[#F5F5F7] dark:bg-[#000000] overflow-hidden font-sans select-none transition-colors duration-300">
        
        {/* ── TOP STUDIO CONTROL HEADER ── */}
        <header className="relative z-30 px-4 sm:px-6 py-3 border-b border-black/[0.06] dark:border-white/[0.08] apple-glass-panel flex items-center justify-between gap-4 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            {/* Unravler Logo + Studio Title & Bio Link */}
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-8 h-8 rounded-[10px] bg-black dark:bg-white flex items-center justify-center p-1.5 shadow-sm shrink-0">
                <UnravlerLogo size="small" showText={false} darkText={isDarkMode} />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-xs text-gray-900 dark:text-white tracking-tight">
                    Smart Bio Studio
                  </span>
                  {(() => {
                    const st = getScheduleStatus();
                    return (
                      <button
                        type="button"
                        onClick={() => setScheduleModalOpen(true)}
                        className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border flex items-center gap-1.5 cursor-pointer hover:opacity-85 transition active:scale-95 ${st.color}`}
                        title="Click to configure Scheduled Live Window"
                      >
                        <span className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />
                        <span>{st.label}</span>
                      </button>
                    );
                  })()}
                </div>
                <div className="flex items-center text-[11px] text-gray-500 dark:text-gray-400 font-mono truncate">
                  <span>unravler.com/bio/</span>
                  <input
                    type="text"
                    value={handle}
                    onChange={(e) => setHandle(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))}
                    className="font-bold text-gray-900 dark:text-white bg-transparent outline-none w-24 sm:w-32 focus:text-[#0071E3] transition-colors ml-0.5"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Center: Segmented Device Switcher (Preserved exact labels: Mobile, Tablet, Desktop) */}
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

          {/* Right: Actions, Dark Mode, QR, Zoom & Publish CTA */}
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

            {/* Live Analytics Modal Trigger */}
            <button
              onClick={() => setAnalyticsModalOpen(true)}
              className="px-3 py-1.5 rounded-full text-xs font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-[#2C2C2E] border border-black/[0.08] dark:border-white/[0.12] hover:bg-gray-50 dark:hover:bg-[#3A3A3C] shadow-xs transition flex items-center gap-1.5 cursor-pointer active:scale-95"
              title="View Live Analytics"
            >
              <FaChartLine className="text-[#0071E3] text-xs" />
              <span>Analytics</span>
            </button>

            {/* Scheduled Live Window Modal Trigger */}
            <button
              onClick={() => setScheduleModalOpen(true)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium border shadow-xs transition flex items-center gap-1.5 cursor-pointer active:scale-95 ${
                pageSchedule?.enabled
                  ? 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-700 font-semibold'
                  : 'text-gray-700 dark:text-gray-200 bg-white dark:bg-[#2C2C2E] border-black/[0.08] dark:border-white/[0.12] hover:bg-gray-50 dark:hover:bg-[#3A3A3C]'
              }`}
              title="Set Start Time & End Time (Scheduled Live Window)"
            >
              <FaClock className={`text-xs ${pageSchedule?.enabled ? 'text-amber-600 dark:text-amber-400' : 'text-gray-400'}`} />
              <span>{pageSchedule?.enabled ? 'Scheduled' : 'Schedule'}</span>
            </button>

            {publicUrl && (
              <button
                onClick={() => setQrModalOpen(true)}
                className="px-3 py-1.5 rounded-full text-xs font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-[#2C2C2E] border border-black/[0.08] dark:border-white/[0.12] hover:bg-gray-50 dark:hover:bg-[#3A3A3C] shadow-xs transition hidden sm:inline-block"
              >
                Share QR
              </button>
            )}

            {/* Publish Changes CTA */}
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
          
          {/* 1. LEFT COLUMN: Content Tree Navigator (~320px) */}
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
              onUpdateSubPage={handleUpdateSubPage}
              onSavePage={handleSaveCurrentPage}
              saving={saving}
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

          {/* 2. CENTER CANVAS: Ambient Mesh Stage & Phone Viewport */}
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

            {/* ── THE HARDWARE CHASSIS ── */}
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
                  className="iphone-screen flex-1 flex flex-col overflow-y-auto relative transition-colors duration-300"
                  style={{
                    background: theme.background_gradient || theme.background_color || 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%)',
                    borderRadius: deviceMode === 'mobile' ? '42px' : deviceMode === 'tablet' ? '26px' : '16px',
                    fontFamily: theme.font_family || 'Plus Jakarta Sans, sans-serif',
                    color: theme.text_color || '#FFFFFF',
                  }}
                >
                  {/* Top Dynamic Island Status Bar (Mobile Mode) */}
                  {deviceMode === 'mobile' && (
                    <div className="sticky top-0 z-30 pt-3 px-7 pb-2 flex items-center justify-between text-[11px] font-semibold tracking-tight backdrop-blur-md bg-black/10 select-none" style={{ color: theme.text_color || '#FFFFFF' }}>
                      <span>9:41</span>
                      <div className="w-24 h-6 rounded-full bg-black flex items-center justify-between px-2.5 shadow-md">
                        <span className="w-2 h-2 rounded-full animate-ping" style={{ backgroundColor: theme.accent_color || '#818CF8' }} />
                        <div className="flex items-center gap-1">
                          <span className="w-2 h-2 rounded-full bg-[#34C759]" />
                          <span className="w-2.5 h-2.5 rounded-full bg-zinc-800" />
                        </div>
                      </div>
                      <div className="flex items-center gap-1 opacity-90">
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
                  <div className="px-5 pt-6 pb-10 flex flex-col items-center text-center space-y-4 flex-1 relative z-10 custom-scrollbar">
                    
                    {/* Announcement Banner */}
                    {theme.announcement_active && theme.announcement_banner && (
                      <div
                        className="w-full py-2 px-3 text-center text-[11px] font-bold text-white rounded-xl shadow-md flex items-center justify-center gap-1.5 animate-in fade-in duration-200"
                        style={{ backgroundColor: theme.accent_color || '#0071E3' }}
                      >
                        <span className="truncate">{theme.announcement_banner}</span>
                        <FaExternalLinkAlt className="text-[9px]" />
                      </div>
                    )}

                    {/* Profile & Avatar Header Layout (5 Layout Architectures) */}
                    {/* 1. Centered */}
                    {(!theme.header_layout || theme.header_layout === 'centered' || theme.header_layout === 'classic') && (
                      <div className="space-y-2.5 text-center mb-2 flex flex-col items-center">
                        <div
                          style={avatarStyles}
                          className="rounded-full p-[2px] bg-white/25 backdrop-blur-xl shadow-lg flex items-center justify-center overflow-hidden transition-all duration-300 mx-auto"
                        >
                          {avatarUrl ? (
                            <img src={avatarUrl} alt="" className="w-full h-full object-cover rounded-full" />
                          ) : (
                            <div className="w-full h-full rounded-full bg-gradient-to-tr from-amber-400 via-rose-500 to-indigo-600 flex items-center justify-center text-2xl font-black text-white">
                              {previewTitle ? previewTitle[0] : 'U'}
                            </div>
                          )}
                        </div>
                        <div className="space-y-1 text-center">
                          {isSubPage && (
                            <div className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-white/20 text-white backdrop-blur-md border border-white/20 mb-0.5">
                              <span>Sub-Page: {activePageObj?.title}</span>
                            </div>
                          )}
                          <div className="flex items-center justify-center gap-1.5">
                            <h2 className={`${headerTitleClass} font-bold tracking-tight`} style={{ color: theme.text_color || '#FFFFFF' }}>
                              {previewTitle}
                            </h2>
                            {verifiedBadge && <span className="font-bold text-sm" style={{ color: theme.accent_color || '#0071E3' }}>✓</span>}
                          </div>
                          {previewBio && (
                            <p className="text-xs max-w-[260px] leading-relaxed mx-auto opacity-80" style={{ color: theme.text_color || '#FFFFFF' }}>
                              {previewBio}
                            </p>
                          )}
                        </div>
                      </div>
                    )}

                    {/* 2. Left Stacked */}
                    {theme.header_layout === 'left_stacked' && (
                      <div className="w-full flex flex-col items-start text-left mb-2 px-1 space-y-2">
                        <div
                          style={avatarStyles}
                          className="rounded-full overflow-hidden shrink-0 shadow-lg flex items-center justify-center"
                        >
                          {avatarUrl ? (
                            <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full rounded-full bg-gradient-to-tr from-amber-400 via-rose-500 to-indigo-600 flex items-center justify-center text-xl font-black text-white">
                              {previewTitle ? previewTitle[0] : 'U'}
                            </div>
                          )}
                        </div>
                        <div className="min-w-0 w-full">
                          {isSubPage && (
                            <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-white/20 text-white backdrop-blur-md border border-white/20 mb-0.5">
                              <span>Sub-Page: {activePageObj?.title}</span>
                            </div>
                          )}
                          <div className="flex items-center gap-1.5">
                            <h2 className={`${headerTitleClass} font-bold tracking-tight truncate`} style={{ color: theme.text_color || '#FFFFFF' }}>
                              {previewTitle}
                            </h2>
                            {verifiedBadge && <span className="font-bold text-sm" style={{ color: theme.accent_color || '#0071E3' }}>✓</span>}
                          </div>
                          {previewBio && (
                            <p className="text-xs leading-relaxed opacity-80 mt-0.5" style={{ color: theme.text_color || '#FFFFFF' }}>
                              {previewBio}
                            </p>
                          )}
                        </div>
                      </div>
                    )}

                    {/* 3. Left Row (Inline) */}
                    {(theme.header_layout === 'left_row' || theme.header_layout === 'minimal_left') && (
                      <div className="w-full flex items-center gap-3.5 text-left mb-2 px-1">
                        <div
                          style={avatarStyles}
                          className="rounded-full overflow-hidden shrink-0 shadow-lg flex items-center justify-center"
                        >
                          {avatarUrl ? (
                            <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full rounded-full bg-gradient-to-tr from-amber-400 via-rose-500 to-indigo-600 flex items-center justify-center text-xl font-black text-white">
                              {previewTitle ? previewTitle[0] : 'U'}
                            </div>
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          {isSubPage && (
                            <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-white/20 text-white backdrop-blur-md border border-white/20 mb-0.5">
                              <span>Sub-Page: {activePageObj?.title}</span>
                            </div>
                          )}
                          <div className="flex items-center gap-1.5">
                            <h2 className={`${headerTitleClass} font-bold tracking-tight truncate`} style={{ color: theme.text_color || '#FFFFFF' }}>
                              {previewTitle}
                            </h2>
                            {verifiedBadge && <span className="font-bold text-sm" style={{ color: theme.accent_color || '#0071E3' }}>✓</span>}
                          </div>
                          {previewBio && (
                            <p className="text-xs leading-relaxed opacity-80 mt-0.5 line-clamp-2" style={{ color: theme.text_color || '#FFFFFF' }}>
                              {previewBio}
                            </p>
                          )}
                        </div>
                      </div>
                    )}

                    {/* 4. Right Stacked */}
                    {theme.header_layout === 'right_stacked' && (
                      <div className="w-full flex flex-col items-end text-right mb-2 px-1 space-y-2">
                        <div
                          style={avatarStyles}
                          className="rounded-full overflow-hidden shrink-0 shadow-lg flex items-center justify-center"
                        >
                          {avatarUrl ? (
                            <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full rounded-full bg-gradient-to-tr from-amber-400 via-rose-500 to-indigo-600 flex items-center justify-center text-xl font-black text-white">
                              {previewTitle ? previewTitle[0] : 'U'}
                            </div>
                          )}
                        </div>
                        <div className="min-w-0 w-full">
                          {isSubPage && (
                            <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-white/20 text-white backdrop-blur-md border border-white/20 mb-0.5">
                              <span>Sub-Page: {activePageObj?.title}</span>
                            </div>
                          )}
                          <div className="flex items-center justify-end gap-1.5">
                            {verifiedBadge && <span className="font-bold text-sm" style={{ color: theme.accent_color || '#0071E3' }}>✓</span>}
                            <h2 className={`${headerTitleClass} font-bold tracking-tight truncate`} style={{ color: theme.text_color || '#FFFFFF' }}>
                              {previewTitle}
                            </h2>
                          </div>
                          {previewBio && (
                            <p className="text-xs leading-relaxed opacity-80 mt-0.5" style={{ color: theme.text_color || '#FFFFFF' }}>
                              {previewBio}
                            </p>
                          )}
                        </div>
                      </div>
                    )}

                    {/* 5. Right Row (Inline) */}
                    {theme.header_layout === 'right_row' && (
                      <div className="w-full flex items-center justify-between gap-3.5 text-right mb-2 px-1">
                        <div className="min-w-0 flex-1">
                          {isSubPage && (
                            <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-white/20 text-white backdrop-blur-md border border-white/20 mb-0.5">
                              <span>Sub-Page: {activePageObj?.title}</span>
                            </div>
                          )}
                          <div className="flex items-center justify-end gap-1.5">
                            {verifiedBadge && <span className="font-bold text-sm" style={{ color: theme.accent_color || '#0071E3' }}>✓</span>}
                            <h2 className={`${headerTitleClass} font-bold tracking-tight truncate`} style={{ color: theme.text_color || '#FFFFFF' }}>
                              {previewTitle}
                            </h2>
                          </div>
                          {previewBio && (
                            <p className="text-xs leading-relaxed opacity-80 mt-0.5 line-clamp-2" style={{ color: theme.text_color || '#FFFFFF' }}>
                              {previewBio}
                            </p>
                          )}
                        </div>
                        <div
                          style={avatarStyles}
                          className="rounded-full overflow-hidden shrink-0 shadow-lg flex items-center justify-center"
                        >
                          {avatarUrl ? (
                            <img src={avatarUrl} alt="" className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full rounded-full bg-gradient-to-tr from-amber-400 via-rose-500 to-indigo-600 flex items-center justify-center text-xl font-black text-white">
                              {previewTitle ? previewTitle[0] : 'U'}
                            </div>
                          )}
                        </div>
                      </div>
                    )}

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
                              style={{ color: theme.text_color || '#FFFFFF' }}
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
                        <div className="w-full space-y-3">
                          {/* Interactive Sample Cards — Always React Live to Geometry, Tint & Text Color */}
                          {[
                            {
                              id: 'sample_suite',
                              title: 'The Unravler AI Architecture',
                              subtitle: 'Next-gen multi-channel social engine',
                              icon: '⚡',
                              is_featured: true,
                            },
                            {
                              id: 'sample_newsletter',
                              title: 'VIP Founder Letter & Drops',
                              subtitle: 'Join 10,000+ top founders & creators',
                              icon: '✉️',
                              is_featured: false,
                            },
                            {
                              id: 'sample_consult',
                              title: 'Book 1:1 Strategy Session',
                              subtitle: 'Private advisory & roadmap consultation',
                              icon: '🔗',
                              is_featured: false,
                            },
                          ].map((sample) => {
                            const cardObj = getTactileCardStyles(theme.card_style, theme, sample.is_featured);
                            return (
                              <div
                                key={sample.id}
                                style={cardObj.style}
                                className={`w-full p-3.5 text-left flex items-center justify-between cursor-pointer hover:opacity-90 active:scale-[0.98] transition-all group overflow-hidden ${cardObj.className}`}
                              >
                                <div className="flex items-center gap-3 min-w-0">
                                  <div
                                    className="w-10 h-10 rounded-xl flex items-center justify-center text-lg shrink-0 shadow-xs"
                                    style={{
                                      backgroundColor: 'rgba(255, 255, 255, 0.14)',
                                      color: cardObj.style.color,
                                    }}
                                  >
                                    {sample.icon}
                                  </div>
                                  <div className="min-w-0">
                                    <div className="text-sm font-bold truncate" style={{ color: cardObj.style.color }}>
                                      {sample.title}
                                    </div>
                                    <div className="text-[11px] truncate opacity-70" style={{ color: cardObj.style.color }}>
                                      {sample.subtitle}
                                    </div>
                                  </div>
                                </div>
                                <span
                                  className="text-sm shrink-0 ml-2 group-hover:translate-x-0.5 transition-transform opacity-70 group-hover:opacity-100"
                                  style={{ color: cardObj.style.color }}
                                >
                                  →
                                </span>
                              </div>
                            );
                          })}
                          <div
                            className="py-2.5 px-3 text-center text-[11px] font-medium border border-dashed rounded-xl opacity-75 mt-2"
                            style={{
                              borderColor: theme.card_border || 'rgba(255, 255, 255, 0.2)',
                              color: theme.text_color || '#FFFFFF',
                            }}
                          >
                            Sample preview cards • Add real links from the left panel
                          </div>
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
                              className={`w-full p-3.5 text-left flex items-center justify-between cursor-pointer hover:opacity-90 active:scale-[0.98] transition-all group overflow-hidden ${cardObj.className}`}
                            >
                              <div className="flex items-center gap-3 min-w-0">
                                {block.media_url ? (
                                  <img
                                    src={block.media_url}
                                    alt=""
                                    className="w-10 h-10 rounded-xl object-cover shrink-0 shadow-xs"
                                  />
                                ) : (
                                  <div
                                    className="w-10 h-10 rounded-xl flex items-center justify-center text-lg shrink-0 shadow-xs"
                                    style={{
                                      backgroundColor: 'rgba(255, 255, 255, 0.14)',
                                      color: cardObj.style.color,
                                    }}
                                  >
                                    {block.is_featured ? '⚡' : block.type === 'video' ? '▶' : block.type === 'newsletter' ? '✉️' : '🔗'}
                                  </div>
                                )}
                                <div className="min-w-0">
                                  <div className="text-sm font-bold truncate" style={{ color: cardObj.style.color }}>
                                    {block.title || block.headline || 'View Link'}
                                  </div>
                                  <div className="text-[11px] truncate opacity-70" style={{ color: cardObj.style.color }}>
                                    {block.subtitle || block.url || ''}
                                  </div>
                                </div>
                              </div>
                              <span
                                className="text-sm shrink-0 ml-2 group-hover:translate-x-0.5 transition-transform opacity-70 group-hover:opacity-100"
                                style={{ color: cardObj.style.color }}
                              >
                                →
                              </span>
                            </div>
                          );
                        })
                      )}
                    </div>

                    {/* Watermark: Crafted by Unravler */}
                    <div className="pt-8 pb-4 text-center text-xs font-medium tracking-wide relative z-10" style={{ color: theme.text_color || '#FFFFFF', opacity: 0.6 }}>
                      <a
                        href="https://www.unravler.com"
                        target="_blank"
                        rel="noreferrer"
                        className="hover:opacity-100 transition-opacity"
                      >
                        Crafted by <span className="font-bold">Unravler</span>
                      </a>
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
              pageSchedule={pageSchedule}
              setPageSchedule={setPageSchedule}
              isPublished={isPublished}
              setIsPublished={setIsPublished}
              onOpenScheduleModal={() => setScheduleModalOpen(true)}
              onDeletePage={() => {
                setDeleteConfirmText('');
                setDeleteModalOpen(true);
              }}
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
                      updateCurrentPageBlocks((prev) => [...prev, newBlock]);
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

        {/* 4. Live Analytics Modal */}
        <BioAnalyticsModal
          isOpen={analyticsModalOpen}
          onClose={() => setAnalyticsModalOpen(false)}
          handle={handle}
          publicUrl={publicUrl}
        />

        {/* 5. Scheduled Live Window Modal */}
        <BioScheduleModal
          isOpen={scheduleModalOpen}
          onClose={() => setScheduleModalOpen(false)}
          pageSchedule={pageSchedule}
          setPageSchedule={setPageSchedule}
          handle={handle}
        />

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

        {/* 5. Apple-Inspired Permanent Delete Confirmation Modal */}
        {deleteModalOpen && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-4 animate-in fade-in duration-200">
            <div className="bg-white/95 dark:bg-[#1C1C1E]/95 backdrop-blur-2xl border border-rose-200 dark:border-rose-900/40 rounded-[28px] max-w-md w-full p-6 shadow-2xl space-y-4 text-gray-900 dark:text-white">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-2xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800/50 flex items-center justify-center text-rose-600 dark:text-rose-400 text-lg shadow-sm">
                    <FaTrashAlt />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-gray-900 dark:text-white">
                      Delete Smart Bio Page?
                    </h3>
                    <p className="text-xs text-rose-600 dark:text-rose-400 font-medium">
                      This action cannot be undone
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setDeleteModalOpen(false)}
                  className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 p-2 rounded-full hover:bg-black/[0.05] dark:hover:bg-white/[0.08] transition-colors"
                >
                  <FaTimes />
                </button>
              </div>

              <div className="p-3.5 rounded-2xl bg-rose-50/60 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-900/40 text-xs text-gray-700 dark:text-gray-300 leading-relaxed space-y-2">
                <p>
                  You are about to permanently delete your public page <strong className="font-mono text-gray-900 dark:text-white">unravler.com/bio/{handle}</strong>.
                </p>
                <ul className="list-disc list-inside text-[11px] text-gray-600 dark:text-gray-400 space-y-1">
                  <li>Your custom blocks, design presets, and themes will be wiped</li>
                  <li>Visitor clicks and impression analytics will be deleted</li>
                  <li>All captured subscriber email leads will be permanently erased</li>
                  <li>The handle <span className="font-mono font-semibold text-gray-900 dark:text-white">@{handle}</span> will be released immediately</li>
                </ul>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-gray-700 dark:text-gray-300 block">
                  To confirm deletion, type your handle <span className="font-mono font-bold text-rose-600 dark:text-rose-400">"{handle}"</span> below:
                </label>
                <input
                  type="text"
                  value={deleteConfirmText}
                  onChange={(e) => setDeleteConfirmText(e.target.value)}
                  placeholder={`Type "${handle}" to confirm`}
                  className="w-full px-3 py-2 text-xs rounded-xl bg-white dark:bg-[#2C2C2E] border border-black/[0.1] dark:border-white/[0.12] text-gray-900 dark:text-white outline-none focus:border-rose-500 transition font-mono"
                  autoFocus
                />
              </div>

              <div className="flex items-center justify-end gap-2.5 pt-2">
                <button
                  type="button"
                  onClick={() => setDeleteModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-gray-700 dark:text-gray-300 hover:bg-black/[0.05] dark:hover:bg-white/[0.08] transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={deleteConfirmText.trim().toLowerCase() !== handle.trim().toLowerCase() || isDeleting}
                  onClick={handlePermanentDelete}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 disabled:opacity-40 disabled:cursor-not-allowed shadow-sm transition-all flex items-center gap-2 cursor-pointer active:scale-[0.98]"
                >
                  {isDeleting ? (
                    <>
                      <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      <span>Deleting…</span>
                    </>
                  ) : (
                    <>
                      <FaTrashAlt className="text-[11px]" />
                      <span>Permanently Delete Page</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </DashboardLayout>
  );
}
