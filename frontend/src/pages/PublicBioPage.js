import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  getPublicBioPage,
  trackBioLinkClick,
  trackBioInteraction,
  subscribeBioNewsletter,
  submitBioPollVote,
  submitBioFeedback,
} from '@/lib/api';
import { toast } from 'sonner';
import {
  FaGlobe,
  FaInstagram,
  FaTwitter,
  FaYoutube,
  FaLinkedin,
  FaTiktok,
  FaSpotify,
  FaGithub,
  FaDiscord,
  FaExternalLinkAlt,
  FaExclamationTriangle,
  FaCheckCircle,
  FaEnvelope,
  FaPlay,
  FaImage,
  FaBolt,
  FaFolder,
  FaChevronUp,
  FaChevronDown,
  FaClock,
  FaStar,
  FaRegStar,
} from 'react-icons/fa';
import {
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
  default: FaGlobe,
};

export default function PublicBioPage() {
  const { handle } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Multi-Page & Folders state
  const [activePageId, setActivePageId] = useState('home');
  const [expandedFolders, setExpandedFolders] = useState({});

  // Newsletter lead state
  const [emailInput, setEmailInput] = useState('');
  const [nameInput, setNameInput] = useState('');
  const [phoneInput, setPhoneInput] = useState('');
  const [subscribing, setSubscribing] = useState(false);
  const [subscribed, setSubscribed] = useState(false);

  // Polls & Feedback state
  const [pollState, setPollState] = useState({});
  const [ratingState, setRatingState] = useState({});
  const [hoverRating, setHoverRating] = useState({});

  const cleanHandle = (handle || '').replace(/^@/, '');

  useEffect(() => {
    const fetchPage = async () => {
      try {
        setLoading(true);
        const res = await getPublicBioPage(cleanHandle);
        setData(res);

        // Check URL query param ?page=
        const searchParams = new URLSearchParams(window.location.search);
        const pageParam = searchParams.get('page');

        if (Array.isArray(res.pages) && res.pages.length > 0) {
          if (pageParam) {
            const cleanParam = pageParam.toLowerCase().trim();
            const matched = res.pages.find(
              (p) => (p.slug && p.slug.toLowerCase() === cleanParam) || p.id === cleanParam
            );
            if (matched) {
              setActivePageId(matched.id);
            } else if (res.active_page_id) {
              setActivePageId(res.active_page_id);
            }
          } else if (res.active_page_id) {
            setActivePageId(res.active_page_id);
          }
        }

        // Update document title & metadata
        if (res.seo?.meta_title || res.title) {
          document.title = res.seo?.meta_title || `${res.title} | Smart Bio`;
        }
      } catch (err) {
        setError(err?.response?.data?.detail || 'Creator page not found.');
      } finally {
        setLoading(false);
      }
    };
    if (cleanHandle) fetchPage();
  }, [cleanHandle]);

  // Load Google Font dynamically based on active page theme
  useEffect(() => {
    if (!data) return;
    const pgList = Array.isArray(data.pages) ? data.pages : [];
    const curPg = pgList.find((p) => p.id === activePageId);
    const activeFont = (activePageId !== 'home' && curPg?.theme?.font_family)
      ? curPg.theme.font_family
      : data.theme?.font_family;
    if (activeFont) {
      loadGoogleFont(activeFont);
    }
  }, [data, activePageId]);

  // Sync document title on page/data change
  useEffect(() => {
    if (!data) return;
    const pgList = Array.isArray(data.pages) ? data.pages : [];
    const curPg = pgList.find((p) => p.id === activePageId);
    if (activePageId !== 'home' && curPg?.title) {
      document.title = `${curPg.title} | ${data.title || data.handle}`;
    } else if (data.seo?.meta_title || data.title) {
      document.title = data.seo?.meta_title || `${data.title} | Smart Bio`;
    }
  }, [data, activePageId]);

  const handleLinkClick = async (block) => {
    try {
      trackBioLinkClick(cleanHandle, block.id);
      trackBioInteraction(cleanHandle, {
        event_type: 'click',
        block_id: block.id,
        target_url: block.url,
      });
    } catch (e) {
      // Non-blocking
    }
    if (block.url) {
      window.open(block.url, '_blank', 'noopener,noreferrer');
    }
  };

  const handleSubscribe = async (e, blockId, leadTag = 'subscriber') => {
    e.preventDefault();
    if (!emailInput || !emailInput.includes('@')) {
      toast.error('Please provide a valid email address');
      return;
    }
    setSubscribing(true);
    try {
      await subscribeBioNewsletter(cleanHandle, {
        email: emailInput,
        name: nameInput,
        phone: phoneInput,
        tag: leadTag,
        source_block_id: blockId,
        variant_id: data?.active_variant_id || null,
      });
      setSubscribed(true);
      setEmailInput('');
      setNameInput('');
      setPhoneInput('');
      toast.success('Thank you for subscribing!');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to subscribe');
    } finally {
      setSubscribing(false);
    }
  };

  const handleVotePoll = async (blockId, optionId) => {
    try {
      const res = await submitBioPollVote(cleanHandle, blockId, {
        option_id: optionId,
        variant_id: data?.active_variant_id || null,
      });
      if (res.success) {
        setPollState((prev) => ({
          ...prev,
          [blockId]: {
            voted: true,
            selected: optionId,
            options: res.options,
            total_votes: res.total_votes,
          },
        }));
        toast.success('Vote recorded!');
      }
    } catch (err) {
      console.error('Failed to vote in poll:', err);
      toast.error('Unable to record vote.');
    }
  };

  const handleRateBio = async (blockId, score, feedbackText = '') => {
    try {
      const res = await submitBioFeedback(cleanHandle, {
        score,
        feedback: feedbackText,
        block_id: blockId,
        variant_id: data?.active_variant_id || null,
      });
      if (res.success) {
        setRatingState((prev) => ({
          ...prev,
          [blockId]: { score, submitted: true, feedback: feedbackText },
        }));
        toast.success(res.message || 'Thank you for your rating!');
      }
    } catch (err) {
      console.error('Failed to submit feedback:', err);
      toast.error('Unable to submit rating.');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
        <div className="w-10 h-10 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error || !data) {
    const errorStr = String(error || '');
    const isScheduled = errorStr.toLowerCase().includes('scheduled') || errorStr.toLowerCase().includes('go live');
    const isExpired = errorStr.toLowerCase().includes('expired');

    return (
      <div className="min-h-screen bg-[#F5F5F7] dark:bg-[#000000] flex items-center justify-center p-4 text-center font-sans">
        <div className="max-w-md w-full bg-white/90 dark:bg-[#1C1C1E]/90 backdrop-blur-2xl rounded-[32px] p-8 border border-black/[0.08] dark:border-white/[0.12] shadow-2xl space-y-5 text-gray-900 dark:text-white animate-in fade-in zoom-in-95 duration-200">
          {isScheduled ? (
            <>
              <div className="w-14 h-14 rounded-2xl bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800/50 flex items-center justify-center text-[#0071E3] text-2xl mx-auto shadow-sm">
                <FaClock />
              </div>
              <div className="space-y-1.5">
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-blue-50 text-[#0071E3] border border-blue-200 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-800/40">
                  Scheduled Launch
                </span>
                <h2 className="text-xl font-bold tracking-tight text-gray-900 dark:text-white pt-1">
                  Coming Soon
                </h2>
                <p className="text-xs text-gray-600 dark:text-gray-400 max-w-xs mx-auto leading-relaxed">
                  {errorStr || `@${cleanHandle}'s Smart Bio is scheduled to go live soon.`}
                </p>
              </div>
              <div className="p-3 rounded-xl bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.05] dark:border-white/[0.06] text-[11px] text-gray-500 dark:text-gray-400">
                Please check back later or contact the creator directly.
              </div>
            </>
          ) : isExpired ? (
            <>
              <div className="w-14 h-14 rounded-2xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/50 flex items-center justify-center text-amber-600 dark:text-amber-400 text-2xl mx-auto shadow-sm">
                <FaClock />
              </div>
              <div className="space-y-1.5">
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-amber-50 text-amber-600 border border-amber-200 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-800/40">
                  Visibility Concluded
                </span>
                <h2 className="text-xl font-bold tracking-tight text-gray-900 dark:text-white pt-1">
                  Page Expired
                </h2>
                <p className="text-xs text-gray-600 dark:text-gray-400 max-w-xs mx-auto leading-relaxed">
                  {errorStr || `The scheduled live window for @${cleanHandle} has ended.`}
                </p>
              </div>
            </>
          ) : (
            <>
              <div className="w-14 h-14 rounded-2xl bg-zinc-100 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700/60 flex items-center justify-center text-zinc-500 text-2xl mx-auto shadow-sm">
                <FaExclamationTriangle className="text-amber-500" />
              </div>
              <div className="space-y-1.5">
                <h2 className="text-xl font-bold tracking-tight text-gray-900 dark:text-white">
                  Page Not Found
                </h2>
                <p className="text-xs text-gray-500 dark:text-gray-400 max-w-xs mx-auto leading-relaxed">
                  @{cleanHandle} does not exist, has been unpublished, or was permanently deleted.
                </p>
              </div>
            </>
          )}

          <div className="pt-2 border-t border-black/[0.06] dark:border-white/[0.08] flex items-center justify-center gap-1 text-[11px] text-gray-400">
            <span>Powered by</span>
            <a
              href="https://unravler.com"
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold text-gray-700 dark:text-gray-300 hover:text-[#0071E3] transition-colors"
            >
              Unravler Smart Bio
            </a>
          </div>
        </div>
      </div>
    );
  }

  const pages = (data.pages && data.pages.length > 0) ? data.pages : [];
  const currentPage = pages.find((p) => p.id === activePageId);
  const isSubPage = activePageId !== 'home' && Boolean(currentPage);
  const theme = (isSubPage && currentPage?.theme) ? { ...data.theme, ...currentPage.theme } : (data.theme || {});
  const displayTitle = (isSubPage && currentPage?.title) ? currentPage.title : (data.title || `@${data.handle}`);
  const displayBio = isSubPage ? (currentPage?.description || '') : (data.bio || '');
  const displayAvatar = (isSubPage && currentPage?.avatar_url) ? currentPage.avatar_url : (data.avatar_url || '');

  const rawPageBlocks = isSubPage ? (currentPage?.blocks || []) : (currentPage?.blocks || data.blocks || []);
  const blocks = (rawPageBlocks || []).filter((b) => b.active !== false);

  const handlePageChange = (pageId) => {
    setActivePageId(pageId);
    const targetPage = pages.find((p) => p.id === pageId);
    const url = new URL(window.location.href);
    if (pageId === 'home' || !targetPage?.slug) {
      url.searchParams.delete('page');
    } else {
      url.searchParams.set('page', targetPage.slug);
    }
    window.history.replaceState({}, '', url.toString());
  };

  const gridPosts = data.grid_posts || [];
  const headerLayout = theme.header_layout || 'classic';
  const bannerUrl = theme.banner_url || data.banner_url;
  const avatarStyles = getProfileAvatarStyles(theme);
  const blockGapPx = getBlockSpacingPx(theme);
  const socialIconPx = getSocialIconSizePx(theme);
  const headerAvatarSizePx = (theme.profile_picture_size !== undefined && Number(theme.profile_picture_size) >= 48)
    ? Number(theme.profile_picture_size)
    : 96;
  const headerTitleClass = headerAvatarSizePx <= 64 ? 'text-lg' : headerAvatarSizePx <= 100 ? 'text-xl' : 'text-2xl';

  const toggleFolder = (blockId) => {
    setExpandedFolders((prev) => ({ ...prev, [blockId]: !prev[blockId] }));
  };

  return (
    <div
      style={{
        background: theme.background_gradient || theme.background_color || '#FDFBF7',
        color: theme.text_color || '#18181B',
        fontFamily: theme.font_family || 'Plus Jakarta Sans, sans-serif',
      }}
      className="min-h-screen relative flex flex-col items-center justify-between pb-12 transition-colors duration-300 overflow-x-hidden"
    >
      {/* Film Grain Texture Overlay */}
      {(theme.background_effect === 'grain' || theme.preset === 'matcha_washi' || theme.preset === 'editorial_cream') && (
        <div
          className="pointer-events-none fixed inset-0 z-0 opacity-[0.04] mix-blend-overlay"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`,
          }}
        />
      )}

      {/* Ambient Glow Orbs */}
      {(theme.background_effect === 'ambient_orbs' || theme.background_effect === 'mesh_glow' || theme.preset === 'liquid_aura' || theme.preset === 'electric_mesh' || theme.preset === 'tokyo_cyber') && (
        <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
          <div
            className="absolute -top-32 -left-32 w-96 h-96 rounded-full blur-3xl opacity-30 animate-pulse"
            style={{ background: theme.accent_color || '#6366F1' }}
          />
          <div
            className="absolute top-1/2 -right-32 w-80 h-80 rounded-full blur-3xl opacity-25"
            style={{ background: theme.card_text_color || '#EC4899' }}
          />
          <div
            className="absolute -bottom-32 left-1/4 w-96 h-96 rounded-full blur-3xl opacity-20"
            style={{ background: theme.accent_color || '#3B82F6' }}
          />
        </div>
      )}

      {/* Top Announcement Banner */}
      {theme.announcement_active && theme.announcement_banner && (
        <div
          onClick={() => theme.announcement_url && window.open(theme.announcement_url, '_blank')}
          className="w-full py-2.5 px-4 text-center text-xs font-bold bg-indigo-600 text-white flex items-center justify-center gap-2 cursor-pointer shadow-sm relative z-20 hover:opacity-95 transition-opacity"
        >
          <span>{theme.announcement_banner}</span>
          {theme.announcement_url && <FaExternalLinkAlt className="text-[10px]" />}
        </div>
      )}

      {/* Banner Layout Cover Image */}
      {headerLayout === 'banner' && (
        <div className="w-full h-44 sm:h-52 relative z-10 overflow-hidden bg-zinc-900/10 dark:bg-white/10">
          {bannerUrl ? (
            <img src={bannerUrl} alt="Cover Banner" className="w-full h-full object-cover" />
          ) : (
            <div
              className="w-full h-full opacity-60"
              style={{
                background: `linear-gradient(135deg, ${theme.accent_color || '#6366F1'}40, ${theme.card_text_color || '#000000'}20)`,
              }}
            />
          )}
        </div>
      )}

      {/* Main Content Container */}
      <div className={`max-w-md w-full relative z-10 flex flex-col items-center px-4 space-y-5 ${headerLayout === 'banner' ? '-mt-14' : 'pt-12'}`}>
        
        {/* HEADER ARCHITECTURE 1: Classic Centered */}
        {(!headerLayout || headerLayout === 'centered' || headerLayout === 'classic') && (
          <div className="flex flex-col items-center text-center space-y-3.5">
            <div
              style={avatarStyles}
              className="rounded-full overflow-hidden flex items-center justify-center shrink-0 bg-black/5 shadow-md"
            >
              {displayAvatar ? (
                <img src={displayAvatar} alt={displayTitle} className="w-full h-full object-cover" />
              ) : (
                <span className="text-2xl font-extrabold uppercase" style={{ color: theme.text_color }}>
                  {displayTitle ? displayTitle[0] : 'U'}
                </span>
              )}
            </div>
            <div className="space-y-1.5 max-w-sm">
              {isSubPage && (
                <span className="inline-block text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-black/5 dark:bg-white/10 mb-0.5 opacity-80">
                  Sub-Page: {currentPage?.title}
                </span>
              )}
              <h1 className={`${headerTitleClass} font-black tracking-tight flex items-center justify-center gap-1.5`} style={{ color: theme.text_color }}>
                {displayTitle}
                {data.verified_badge && <FaCheckCircle className="text-indigo-500 text-sm" />}
              </h1>
              <p className="text-xs font-mono opacity-60" style={{ color: theme.text_color }}>
                @{data.handle}
              </p>
              {displayBio && (
                <p className="text-xs opacity-80 pt-1 leading-relaxed max-w-xs mx-auto" style={{ color: theme.text_color }}>
                  {displayBio}
                </p>
              )}
            </div>
          </div>
        )}

        {/* HEADER ARCHITECTURE 2: Top-Left Stacked */}
        {headerLayout === 'left_stacked' && (
          <div className="w-full flex flex-col items-start text-left space-y-3 px-1">
            <div
              style={avatarStyles}
              className="rounded-full overflow-hidden flex items-center justify-center shrink-0 bg-black/5 shadow-md"
            >
              {displayAvatar ? (
                <img src={displayAvatar} alt={displayTitle} className="w-full h-full object-cover" />
              ) : (
                <span className="text-2xl font-extrabold uppercase" style={{ color: theme.text_color }}>
                  {displayTitle ? displayTitle[0] : 'U'}
                </span>
              )}
            </div>
            <div className="space-y-1 w-full">
              {isSubPage && (
                <span className="inline-block text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-black/5 dark:bg-white/10 mb-0.5 opacity-80">
                  Sub-Page: {currentPage?.title}
                </span>
              )}
              <h1 className={`${headerTitleClass} font-black tracking-tight flex items-center gap-1.5`} style={{ color: theme.text_color }}>
                {displayTitle}
                {data.verified_badge && <FaCheckCircle className="text-indigo-500 text-sm" />}
              </h1>
              <p className="text-xs font-mono opacity-60" style={{ color: theme.text_color }}>
                @{data.handle}
              </p>
              {displayBio && (
                <p className="text-xs opacity-80 pt-1 leading-relaxed" style={{ color: theme.text_color }}>
                  {displayBio}
                </p>
              )}
            </div>
          </div>
        )}

        {/* HEADER ARCHITECTURE 3: Left Row (Inline) */}
        {(headerLayout === 'left_row' || headerLayout === 'minimal_left') && (
          <div className="w-full flex items-center gap-4 text-left px-1">
            <div
              style={avatarStyles}
              className="rounded-full overflow-hidden flex items-center justify-center shrink-0 bg-black/5 shadow-md"
            >
              {displayAvatar ? (
                <img src={displayAvatar} alt={displayTitle} className="w-full h-full object-cover" />
              ) : (
                <span className="text-2xl font-extrabold uppercase" style={{ color: theme.text_color }}>
                  {displayTitle ? displayTitle[0] : 'U'}
                </span>
              )}
            </div>
            <div className="space-y-1 flex-1 min-w-0">
              {isSubPage && (
                <span className="inline-block text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-black/5 dark:bg-white/10 mb-0.5 opacity-80">
                  Sub-Page: {currentPage?.title}
                </span>
              )}
              <h1 className={`${headerTitleClass} font-black tracking-tight flex items-center gap-1.5 truncate`} style={{ color: theme.text_color }}>
                {displayTitle}
                {data.verified_badge && <FaCheckCircle className="text-indigo-500 text-sm shrink-0" />}
              </h1>
              <p className="text-xs font-mono opacity-60" style={{ color: theme.text_color }}>
                @{data.handle}
              </p>
              {displayBio && (
                <p className="text-xs opacity-80 pt-0.5 leading-snug line-clamp-2" style={{ color: theme.text_color }}>
                  {displayBio}
                </p>
              )}
            </div>
          </div>
        )}

        {/* HEADER ARCHITECTURE 4: Top-Right Stacked */}
        {headerLayout === 'right_stacked' && (
          <div className="w-full flex flex-col items-end text-right space-y-3 px-1">
            <div
              style={avatarStyles}
              className="rounded-full overflow-hidden flex items-center justify-center shrink-0 bg-black/5 shadow-md"
            >
              {displayAvatar ? (
                <img src={displayAvatar} alt={displayTitle} className="w-full h-full object-cover" />
              ) : (
                <span className="text-2xl font-extrabold uppercase" style={{ color: theme.text_color }}>
                  {displayTitle ? displayTitle[0] : 'U'}
                </span>
              )}
            </div>
            <div className="space-y-1 w-full">
              {isSubPage && (
                <span className="inline-block text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-black/5 dark:bg-white/10 mb-0.5 opacity-80">
                  Sub-Page: {currentPage?.title}
                </span>
              )}
              <h1 className={`${headerTitleClass} font-black tracking-tight flex items-center justify-end gap-1.5`} style={{ color: theme.text_color }}>
                {data.verified_badge && <FaCheckCircle className="text-indigo-500 text-sm" />}
                {displayTitle}
              </h1>
              <p className="text-xs font-mono opacity-60" style={{ color: theme.text_color }}>
                @{data.handle}
              </p>
              {displayBio && (
                <p className="text-xs opacity-80 pt-1 leading-relaxed" style={{ color: theme.text_color }}>
                  {displayBio}
                </p>
              )}
            </div>
          </div>
        )}

        {/* HEADER ARCHITECTURE 5: Right Row (Inline) */}
        {headerLayout === 'right_row' && (
          <div className="w-full flex items-center justify-between gap-4 text-right px-1">
            <div className="space-y-1 flex-1 min-w-0">
              {isSubPage && (
                <span className="inline-block text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-black/5 dark:bg-white/10 mb-0.5 opacity-80">
                  Sub-Page: {currentPage?.title}
                </span>
              )}
              <h1 className={`${headerTitleClass} font-black tracking-tight flex items-center justify-end gap-1.5 truncate`} style={{ color: theme.text_color }}>
                {data.verified_badge && <FaCheckCircle className="text-indigo-500 text-sm shrink-0" />}
                {displayTitle}
              </h1>
              <p className="text-xs font-mono opacity-60" style={{ color: theme.text_color }}>
                @{data.handle}
              </p>
              {displayBio && (
                <p className="text-xs opacity-80 pt-0.5 leading-snug line-clamp-2" style={{ color: theme.text_color }}>
                  {displayBio}
                </p>
              )}
            </div>
            <div
              style={avatarStyles}
              className="rounded-full overflow-hidden flex items-center justify-center shrink-0 bg-black/5 shadow-md"
            >
              {displayAvatar ? (
                <img src={displayAvatar} alt={displayTitle} className="w-full h-full object-cover" />
              ) : (
                <span className="text-2xl font-extrabold uppercase" style={{ color: theme.text_color }}>
                  {displayTitle ? displayTitle[0] : 'U'}
                </span>
              )}
            </div>
          </div>
        )}

        {/* HEADER ARCHITECTURE 2: Banner Overlap */}
        {headerLayout === 'banner' && (
          <div className="flex flex-col items-center text-center space-y-3">
            <div
              style={avatarStyles}
              className="rounded-full overflow-hidden flex items-center justify-center shrink-0 bg-black/10"
            >
              {displayAvatar ? (
                <img src={displayAvatar} alt={displayTitle} className="w-full h-full object-cover" />
              ) : (
                <span className="text-2xl font-extrabold uppercase" style={{ color: theme.text_color }}>
                  {displayTitle ? displayTitle[0] : 'U'}
                </span>
              )}
            </div>
            <div className="space-y-1 max-w-sm">
              {isSubPage && (
                <span className="inline-block text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-black/5 dark:bg-white/10 mb-0.5 opacity-80">
                  Sub-Page: {currentPage?.title}
                </span>
              )}
              <h1 className="text-xl font-black tracking-tight flex items-center justify-center gap-1.5" style={{ color: theme.text_color }}>
                {displayTitle}
                {data.verified_badge && <FaCheckCircle className="text-indigo-500 text-sm" />}
              </h1>
              <p className="text-xs font-mono opacity-60" style={{ color: theme.text_color }}>
                @{data.handle}
              </p>
              {displayBio && (
                <p className="text-xs opacity-80 pt-1 leading-relaxed max-w-xs mx-auto" style={{ color: theme.text_color }}>
                  {displayBio}
                </p>
              )}
            </div>
          </div>
        )}

        {/* HEADER ARCHITECTURE 3: Editorial Horizontal Split */}
        {headerLayout === 'editorial_split' && (
          <div className="w-full flex items-center gap-4 text-left p-4 rounded-3xl bg-black/5 dark:bg-white/5 border border-black/5 backdrop-blur-md">
            <div
              style={avatarStyles}
              className="rounded-2xl overflow-hidden flex items-center justify-center shrink-0 bg-black/10"
            >
              {displayAvatar ? (
                <img src={displayAvatar} alt={displayTitle} className="w-full h-full object-cover" />
              ) : (
                <span className="text-2xl font-extrabold uppercase" style={{ color: theme.text_color }}>
                  {displayTitle ? displayTitle[0] : 'U'}
                </span>
              )}
            </div>
            <div className="space-y-0.5 flex-1 min-w-0">
              {isSubPage && (
                <span className="inline-block text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-black/5 dark:bg-white/10 mb-0.5 opacity-80">
                  Sub-Page: {currentPage?.title}
                </span>
              )}
              <h1 className="text-lg font-black tracking-tight flex items-center gap-1.5 truncate" style={{ color: theme.text_color }}>
                {displayTitle}
                {data.verified_badge && <FaCheckCircle className="text-indigo-500 text-xs shrink-0" />}
              </h1>
              <p className="text-xs font-mono opacity-60" style={{ color: theme.text_color }}>
                @{data.handle}
              </p>
              {displayBio && (
                <p className="text-xs opacity-80 pt-0.5 leading-snug line-clamp-2" style={{ color: theme.text_color }}>
                  {displayBio}
                </p>
              )}
            </div>
          </div>
        )}

        {/* HEADER ARCHITECTURE 4: Minimalist Monograph */}
        {headerLayout === 'minimal' && (
          <div className="w-full text-center space-y-2 pt-2">
            <div className="flex items-center justify-center gap-2">
              <div className="w-8 h-8 rounded-full border border-black/15 dark:border-white/20 overflow-hidden shrink-0">
                {displayAvatar ? (
                  <img src={displayAvatar} alt={displayTitle} className="w-full h-full object-cover" />
                ) : (
                  <span className="text-xs font-black" style={{ color: theme.text_color }}>
                    {displayTitle ? displayTitle[0] : 'U'}
                  </span>
                )}
              </div>
              <h1 className="text-xl font-serif font-black tracking-tight flex items-center gap-1.5" style={{ color: theme.text_color }}>
                {displayTitle}
                {data.verified_badge && <FaCheckCircle className="text-indigo-500 text-xs" />}
              </h1>
            </div>
            {isSubPage && (
              <span className="inline-block text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-black/5 dark:bg-white/10 mb-0.5 opacity-80">
                Sub-Page: {currentPage?.title}
              </span>
            )}
            <p className="text-xs font-mono opacity-50">@{data.handle}</p>
            {displayBio && (
              <p className="text-xs opacity-75 max-w-sm mx-auto font-serif italic" style={{ color: theme.text_color }}>
                {displayBio}
              </p>
            )}
          </div>
        )}

        {/* Social Icons Bar */}
        {data.social_links && Object.keys(data.social_links).some((k) => data.social_links[k]) && (
          <div className="flex items-center justify-center gap-2.5 pt-1 flex-wrap">
            {Object.entries(data.social_links).map(([plat, url]) => {
              if (!url) return null;
              const Icon = SOCIAL_ICON_MAP[plat] || SOCIAL_ICON_MAP.default;
              return (
                <a
                  key={plat}
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: theme.text_color, width: `${socialIconPx + 16}px`, height: `${socialIconPx + 16}px` }}
                  className="rounded-full bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/20 flex items-center justify-center shadow-xs transition-transform active:scale-95 hover:scale-105"
                >
                  <Icon style={{ fontSize: `${socialIconPx}px` }} />
                </a>
              );
            })}
          </div>
        )}

        {/* Multi-Page Sub-Navigation Pill Dock (as in screenshot) */}
        {pages.length > 1 && (theme.navigation_style || 'pills') === 'pills' && (
          <div className="flex items-center justify-center gap-1.5 p-1 rounded-full bg-black/5 dark:bg-white/10 backdrop-blur-md">
            {pages.map((pg) => {
              const isActive = pg.id === activePageId;
              return (
                <button
                  key={pg.id}
                  onClick={() => handlePageChange(pg.id)}
                  className={`px-4 py-1.5 text-xs font-bold rounded-full transition-all cursor-pointer ${
                    isActive
                      ? 'bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 shadow-sm'
                      : 'opacity-70 hover:opacity-100'
                  }`}
                >
                  {pg.title}
                </button>
              );
            })}
          </div>
        )}

        {/* Dynamic Blocks Stack */}
        <div className="w-full pt-2" style={{ display: 'flex', flexDirection: 'column', gap: `${blockGapPx}px` }}>
          {blocks.map((block) => {
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

            if (isFolder) {
              const isExpanded = expandedFolders[block.id] ?? block.is_expanded;
              return (
                <div
                  key={block.id}
                  style={cardObj.style}
                  className={`w-full font-bold text-sm overflow-hidden transition-all ${cardObj.className}`}
                >
                  <div
                    onClick={() => toggleFolder(block.id)}
                    className="p-4 flex items-center justify-between cursor-pointer"
                  >
                    <div className="flex items-center gap-2.5">
                      <FaFolder className="text-amber-500 text-base" />
                      <span style={{ color: cardObj.style.color }}>{block.title || 'Folder / Group'}</span>
                      {block.folder_items?.length > 0 && (
                        <span className="px-2 py-0.5 rounded-md bg-black/10 dark:bg-white/10 text-[10px] font-mono" style={{ color: cardObj.style.color }}>
                          {block.folder_items.length}
                        </span>
                      )}
                    </div>
                    {isExpanded ? <FaChevronUp className="text-xs" /> : <FaChevronDown className="text-xs" />}
                  </div>

                  {isExpanded && (
                    <div className="p-3 pt-0 space-y-2 border-t border-black/5 dark:border-white/5 mt-1">
                      {(block.folder_items || []).map((subItem, sIdx) => (
                        <button
                          key={subItem.id || sIdx}
                          onClick={() => subItem.url && window.open(subItem.url, '_blank')}
                          className="w-full py-2.5 px-3.5 rounded-xl bg-black/5 dark:bg-white/5 hover:bg-black/10 flex items-center justify-between text-xs font-bold transition-all text-left"
                          style={{ color: cardObj.style.color }}
                        >
                          <span className="truncate">{subItem.title || subItem.url}</span>
                          <FaExternalLinkAlt className="text-[10px] opacity-50" />
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            }

            if (block.type === 'link' || block.type === 'media_card') {
              return (
                <button
                  key={block.id}
                  onClick={() => handleLinkClick(block)}
                  style={cardObj.style}
                  className={`w-full font-bold text-sm transition-all hover:scale-[1.015] active:scale-[0.98] cursor-pointer overflow-hidden ${cardObj.className} ${
                    isBannerTop ? 'flex flex-col text-left' : 'py-3.5 px-4 flex items-center justify-between text-left'
                  }`}
                >
                  {isBannerTop && block.media_url && (
                    <div className="w-full h-40 overflow-hidden bg-black/5">
                      <img src={block.media_url} alt="" className="w-full h-full object-cover" />
                    </div>
                  )}

                  <div className={`flex items-center gap-3 w-full ${isBannerTop ? 'p-4' : ''}`}>
                    {!isBannerTop && block.media_url && (
                      <img src={block.media_url} alt="" className="w-12 h-12 rounded-xl object-cover flex-shrink-0" />
                    )}

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        {block.is_featured && <FaBolt className="text-amber-400 text-xs shrink-0 animate-bounce" />}
                        <span className="truncate" style={{ color: cardObj.style.color }}>
                          {block.title || block.headline || 'View Details'}
                        </span>
                        {block.badge && (
                          <span className="px-2 py-0.5 text-[9px] font-black uppercase tracking-wider bg-rose-500 text-white rounded-full">
                            {block.badge}
                          </span>
                        )}
                      </div>
                      {block.subtitle && (
                        <p className="text-[11px] opacity-70 font-normal mt-0.5 truncate" style={{ color: cardObj.style.color }}>
                          {block.subtitle}
                        </p>
                      )}
                    </div>

                    <FaExternalLinkAlt className="text-xs opacity-40 shrink-0 ml-2" style={{ color: cardObj.style.color }} />
                  </div>
                </button>
              );
            }

            if (block.type === 'embed') {
              const embedUrl = block.embed_url || '';
              const isYouTube = embedUrl.includes('youtube.com') || embedUrl.includes('youtu.be');
              let videoId = '';
              if (isYouTube) {
                const match = embedUrl.match(/(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|watch\?v=|watch\?.+&v=))([\w-]{11})/);
                videoId = match ? match[1] : '';
              }

              return (
                <div
                  key={block.id}
                  style={cardObj.style}
                  className={`w-full p-4 space-y-2 text-left ${cardObj.className}`}
                >
                  <span className="text-xs font-black block">{block.title || 'Featured Media'}</span>
                  {isYouTube && videoId ? (
                    <div className="w-full aspect-video rounded-xl overflow-hidden bg-black">
                      <iframe
                        src={`https://www.youtube.com/embed/${videoId}`}
                        title={block.title}
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                        allowFullScreen
                        className="w-full h-full border-0"
                      />
                    </div>
                  ) : (
                    <a
                      href={embedUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="w-full py-3 bg-black/5 dark:bg-white/10 rounded-xl flex items-center justify-center gap-2 text-xs font-bold"
                    >
                      <FaPlay /> Open Media Player
                    </a>
                  )}
                </div>
              );
            }

            if (block.type === 'lead_capture') {
              return (
                <div
                  key={block.id}
                  style={cardObj.style}
                  className={`w-full p-5 space-y-3 text-center ${cardObj.className}`}
                >
                  <h3 className="text-sm font-black">{block.headline || 'Join Newsletter'}</h3>
                  {block.subheadline && (
                    <p className="text-xs opacity-75">{block.subheadline}</p>
                  )}

                  {subscribed ? (
                    <div className="p-3 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5">
                      <FaCheckCircle /> You&apos;re subscribed!
                    </div>
                  ) : (
                    <form onSubmit={(e) => handleSubscribe(e, block.id, block.lead_tag || 'subscriber')} className="space-y-2 pt-1 text-left">
                      {block.capture_fields?.name && (
                        <input
                          type="text"
                          value={nameInput}
                          onChange={(e) => setNameInput(e.target.value)}
                          placeholder="Your Name (Optional)"
                          className="w-full px-3 py-2 text-xs bg-black/5 dark:bg-white/10 border border-black/10 dark:border-white/10 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
                        />
                      )}
                      {block.capture_fields?.phone && (
                        <input
                          type="tel"
                          value={phoneInput}
                          onChange={(e) => setPhoneInput(e.target.value)}
                          placeholder="Phone Number (Optional)"
                          className="w-full px-3 py-2 text-xs bg-black/5 dark:bg-white/10 border border-black/10 dark:border-white/10 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
                        />
                      )}
                      <div className="flex items-center gap-2">
                        <input
                          type="email"
                          required
                          value={emailInput}
                          onChange={(e) => setEmailInput(e.target.value)}
                          placeholder="Enter your email"
                          className="flex-1 px-3 py-2 text-xs bg-black/5 dark:bg-white/10 border border-black/10 dark:border-white/10 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
                        />
                        <button
                          type="submit"
                          disabled={subscribing}
                          className="px-4 py-2 text-xs font-black bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-xs transition-all active:scale-95 disabled:opacity-50 shrink-0"
                        >
                          {subscribing ? '...' : block.button_label || 'Subscribe'}
                        </button>
                      </div>
                    </form>
                  )}
                </div>
              );
            }

            if (block.type === 'poll') {
              const currentPoll = pollState[block.id] || {};
              const rawOptions = currentPoll.options || block.poll_options || [];
              const options = rawOptions.map((opt, idx) => {
                if (typeof opt === 'string') return { id: `opt_${idx}`, text: opt, votes: 0 };
                return {
                  id: opt.id || `opt_${idx}`,
                  text: opt.text || opt.label || `Option ${idx + 1}`,
                  votes: opt.votes || opt.count || 0,
                };
              });
              const totalVotes = currentPoll.total_votes ?? options.reduce((sum, o) => sum + (o.votes || 0), 0);
              const hasVoted = Boolean(currentPoll.voted);

              return (
                <div
                  key={block.id}
                  style={cardObj.style}
                  className={`w-full p-4.5 space-y-3 text-left ${cardObj.className}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-black tracking-wide flex items-center gap-1.5" style={{ color: cardObj.style.color }}>
                      <FaBolt className="text-amber-500 text-[11px]" />
                      {block.poll_question || block.title || 'Quick Poll'}
                    </span>
                    {totalVotes > 0 && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-black/10 dark:bg-white/10 opacity-70">
                        {totalVotes} {totalVotes === 1 ? 'vote' : 'votes'}
                      </span>
                    )}
                  </div>

                  <div className="space-y-2 pt-0.5">
                    {options.map((option) => {
                      const optVotes = option.votes || 0;
                      const pct = totalVotes > 0 ? Math.round((optVotes / totalVotes) * 100) : 0;
                      const isSelected = currentPoll.selected === option.id;

                      if (hasVoted) {
                        return (
                          <div
                            key={option.id}
                            className={`relative overflow-hidden rounded-xl p-3 border transition-all text-xs font-semibold ${
                              isSelected
                                ? 'border-indigo-500 bg-indigo-500/10'
                                : 'border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5'
                            }`}
                          >
                            <div
                              className="absolute inset-y-0 left-0 bg-indigo-500/20 dark:bg-indigo-500/30 transition-all duration-500"
                              style={{ width: `${pct}%` }}
                            />
                            <div className="relative flex items-center justify-between z-10">
                              <span className="flex items-center gap-1.5 truncate">
                                {isSelected && <FaCheckCircle className="text-indigo-500 text-xs shrink-0" />}
                                <span className={isSelected ? 'font-bold' : ''}>{option.text}</span>
                              </span>
                              <span className="text-[11px] font-bold opacity-80 shrink-0 ml-2">
                                {pct}% ({optVotes})
                              </span>
                            </div>
                          </div>
                        );
                      }

                      return (
                        <button
                          key={option.id}
                          type="button"
                          onClick={() => handleVotePoll(block.id, option.id)}
                          className="w-full text-left p-3 rounded-xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 hover:border-indigo-500 hover:bg-indigo-500/10 transition-all text-xs font-semibold active:scale-[0.99] flex items-center justify-between group"
                          style={{ color: cardObj.style.color }}
                        >
                          <span className="truncate group-hover:text-indigo-600 dark:group-hover:text-indigo-400">
                            {option.text}
                          </span>
                          <span className="text-[10px] opacity-0 group-hover:opacity-100 text-indigo-500 font-bold transition-opacity">
                            Vote ➔
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            }

            if (block.type === 'nps_rating') {
              const currentRating = ratingState[block.id] || {};
              const currentHover = hoverRating[block.id] || 0;
              const isSubmitted = Boolean(currentRating.submitted);
              const isNps10 = block.rating_type === 'nps_10' || block.rating_scale === 10;
              const scale = isNps10 ? 10 : 5;

              return (
                <div
                  key={block.id}
                  style={cardObj.style}
                  className={`w-full p-4.5 space-y-3 text-center ${cardObj.className}`}
                >
                  <h4 className="text-xs font-black tracking-wide" style={{ color: cardObj.style.color }}>
                    {block.rating_prompt || block.title || 'How was your experience?'}
                  </h4>

                  {isSubmitted ? (
                    <div className="p-3 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5">
                      <FaCheckCircle /> Thank you for rating us {currentRating.score}/{scale}!
                    </div>
                  ) : isNps10 ? (
                    <div className="space-y-2">
                      <div className="grid grid-cols-10 gap-1 pt-1">
                        {Array.from({ length: 10 }, (_, i) => i + 1).map((num) => (
                          <button
                            key={num}
                            type="button"
                            onClick={() => handleRateBio(block.id, num)}
                            className="aspect-square flex items-center justify-center rounded-lg border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 hover:bg-indigo-600 hover:text-white hover:border-indigo-600 text-xs font-bold transition-all active:scale-90"
                            style={{ color: cardObj.style.color }}
                          >
                            {num}
                          </button>
                        ))}
                      </div>
                      <div className="flex items-center justify-between text-[10px] opacity-60 font-medium px-1">
                        <span>Not likely</span>
                        <span>Extremely likely</span>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center justify-center gap-2 py-1">
                      {[1, 2, 3, 4, 5].map((star) => {
                        const filled = currentHover ? star <= currentHover : star <= (currentRating.score || 0);
                        return (
                          <button
                            key={star}
                            type="button"
                            onMouseEnter={() => setHoverRating((prev) => ({ ...prev, [block.id]: star }))}
                            onMouseLeave={() => setHoverRating((prev) => ({ ...prev, [block.id]: 0 }))}
                            onClick={() => handleRateBio(block.id, star)}
                            className="p-1.5 text-xl transition-transform hover:scale-125 active:scale-95 text-amber-400 focus:outline-hidden"
                            aria-label={`${star} star`}
                          >
                            {filled ? <FaStar /> : <FaRegStar className="opacity-40" />}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            }

            if (block.type === 'payment_link') {
              const currencySymbol = block.payment_currency === 'USD' ? '$' : block.payment_currency === 'EUR' ? '€' : block.payment_currency === 'GBP' ? '£' : '₹';
              const priceText = block.payment_amount !== undefined && block.payment_amount !== null && Number(block.payment_amount) > 0
                ? `${currencySymbol}${block.payment_amount}`
                : '';
              const ctaText = block.button_text || (priceText ? `Pay ${priceText}` : 'Instant Checkout');

              return (
                <div
                  key={block.id}
                  style={cardObj.style}
                  className={`w-full p-4 space-y-3 text-left overflow-hidden transition-all ${cardObj.className}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      {block.media_url ? (
                        <img src={block.media_url} alt="" className="w-12 h-12 rounded-xl object-cover shrink-0 shadow-xs" />
                      ) : (
                        <div className="w-12 h-12 rounded-xl bg-emerald-500/10 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center text-xl shrink-0 font-black">
                          💳
                        </div>
                      )}
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-extrabold text-sm truncate" style={{ color: cardObj.style.color }}>
                            {block.title || 'Digital Product / Service'}
                          </span>
                          {priceText && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-emerald-500 text-white shadow-xs shrink-0">
                              {priceText}
                            </span>
                          )}
                        </div>
                        {block.subtitle && (
                          <p className="text-xs opacity-75 mt-0.5 leading-relaxed" style={{ color: cardObj.style.color }}>
                            {block.subtitle}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleLinkClick(block)}
                    className="w-full py-2.5 px-4 rounded-xl font-bold text-xs bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm flex items-center justify-center gap-2 transition-all active:scale-[0.98] cursor-pointer"
                  >
                    <span>{ctaText}</span>
                    <FaExternalLinkAlt className="text-[10px] opacity-80" />
                  </button>
                </div>
              );
            }

            if (block.type === 'text_block') {
              return (
                <div
                  key={block.id}
                  style={{ color: theme.text_color }}
                  className="w-full py-3 px-4 text-xs italic opacity-85 text-center leading-relaxed font-serif"
                >
                  {block.content}
                </div>
              );
            }

            return null;
          })}
        </div>
      </div>

      {/* Crafted by Unravler footer */}
      <div className="pt-10 pb-6 text-center text-xs font-medium tracking-wide relative z-10" style={{ color: theme.text_color, opacity: 0.6 }}>
        <a
          href="https://www.unravler.com"
          target="_blank"
          rel="noreferrer"
          className="hover:opacity-100 transition-opacity"
        >
          Crafted by <span className="font-bold">Unravler</span>
        </a>
      </div>
    </div>
  );
}
