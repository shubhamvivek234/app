import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  getPublicBioPage,
  trackBioLinkClick,
  trackBioInteraction,
  subscribeBioNewsletter,
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
} from 'react-icons/fa';
import {
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
  const [subscribing, setSubscribing] = useState(false);
  const [subscribed, setSubscribed] = useState(false);

  const cleanHandle = (handle || '').replace(/^@/, '');

  useEffect(() => {
    const fetchPage = async () => {
      try {
        setLoading(true);
        const res = await getPublicBioPage(cleanHandle);
        setData(res);
        if (res.active_page_id) {
          setActivePageId(res.active_page_id);
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

  const handleSubscribe = async (e, blockId) => {
    e.preventDefault();
    if (!emailInput || !emailInput.includes('@')) {
      toast.error('Please provide a valid email address');
      return;
    }
    setSubscribing(true);
    try {
      await subscribeBioNewsletter(cleanHandle, emailInput, blockId);
      setSubscribed(true);
      setEmailInput('');
      toast.success('Thank you for subscribing!');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to subscribe');
    } finally {
      setSubscribing(false);
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
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4 text-white text-center">
        <div className="max-w-sm w-full bg-zinc-900 rounded-3xl p-8 border border-zinc-800 space-y-3">
          <FaExclamationTriangle className="text-3xl text-amber-400 mx-auto" />
          <h2 className="text-lg font-bold">Page Not Found</h2>
          <p className="text-xs text-zinc-400">@{cleanHandle} does not exist or has been made private.</p>
        </div>
      </div>
    );
  }

  const theme = data.theme || {};
  const pages = (data.pages && data.pages.length > 0) ? data.pages : [];

  const currentPage = pages.find((p) => p.id === activePageId);
  const rawPageBlocks = currentPage ? currentPage.blocks : (data.blocks || []);
  const blocks = (rawPageBlocks || []).filter((b) => b.active !== false);

  const gridPosts = data.grid_posts || [];
  const headerLayout = theme.header_layout || 'classic';
  const bannerUrl = theme.banner_url || data.banner_url;
  const avatarStyles = getProfileAvatarStyles(theme);
  const blockGapPx = getBlockSpacingPx(theme);
  const socialIconPx = getSocialIconSizePx(theme);

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
        {headerLayout === 'classic' && (
          <div className="flex flex-col items-center text-center space-y-3.5">
            <div
              style={avatarStyles}
              className="rounded-full overflow-hidden flex items-center justify-center shrink-0 bg-black/5"
            >
              {data.avatar_url ? (
                <img src={data.avatar_url} alt={data.title} className="w-full h-full object-cover" />
              ) : (
                <span className="text-2xl font-extrabold uppercase" style={{ color: theme.text_color }}>
                  {data.title ? data.title[0] : 'U'}
                </span>
              )}
            </div>
            <div className="space-y-1.5 max-w-sm">
              <h1 className="text-xl font-black tracking-tight flex items-center justify-center gap-1.5" style={{ color: theme.text_color }}>
                {data.title}
                {data.verified_badge && <FaCheckCircle className="text-indigo-500 text-sm" />}
              </h1>
              <p className="text-xs font-mono opacity-60" style={{ color: theme.text_color }}>
                @{data.handle}
              </p>
              {data.bio && (
                <p className="text-xs opacity-80 pt-1 leading-relaxed max-w-xs mx-auto" style={{ color: theme.text_color }}>
                  {data.bio}
                </p>
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
              {data.avatar_url ? (
                <img src={data.avatar_url} alt={data.title} className="w-full h-full object-cover" />
              ) : (
                <span className="text-2xl font-extrabold uppercase" style={{ color: theme.text_color }}>
                  {data.title ? data.title[0] : 'U'}
                </span>
              )}
            </div>
            <div className="space-y-1 max-w-sm">
              <h1 className="text-xl font-black tracking-tight flex items-center justify-center gap-1.5" style={{ color: theme.text_color }}>
                {data.title}
                {data.verified_badge && <FaCheckCircle className="text-indigo-500 text-sm" />}
              </h1>
              <p className="text-xs font-mono opacity-60" style={{ color: theme.text_color }}>
                @{data.handle}
              </p>
              {data.bio && (
                <p className="text-xs opacity-80 pt-1 leading-relaxed max-w-xs mx-auto" style={{ color: theme.text_color }}>
                  {data.bio}
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
              {data.avatar_url ? (
                <img src={data.avatar_url} alt={data.title} className="w-full h-full object-cover" />
              ) : (
                <span className="text-2xl font-extrabold uppercase" style={{ color: theme.text_color }}>
                  {data.title ? data.title[0] : 'U'}
                </span>
              )}
            </div>
            <div className="space-y-0.5 flex-1 min-w-0">
              <h1 className="text-lg font-black tracking-tight flex items-center gap-1.5 truncate" style={{ color: theme.text_color }}>
                {data.title}
                {data.verified_badge && <FaCheckCircle className="text-indigo-500 text-xs shrink-0" />}
              </h1>
              <p className="text-xs font-mono opacity-60" style={{ color: theme.text_color }}>
                @{data.handle}
              </p>
              {data.bio && (
                <p className="text-xs opacity-80 pt-0.5 leading-snug line-clamp-2" style={{ color: theme.text_color }}>
                  {data.bio}
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
                {data.avatar_url ? (
                  <img src={data.avatar_url} alt={data.title} className="w-full h-full object-cover" />
                ) : (
                  <span className="text-xs font-black" style={{ color: theme.text_color }}>
                    {data.title ? data.title[0] : 'U'}
                  </span>
                )}
              </div>
              <h1 className="text-xl font-serif font-black tracking-tight flex items-center gap-1.5" style={{ color: theme.text_color }}>
                {data.title}
                {data.verified_badge && <FaCheckCircle className="text-indigo-500 text-xs" />}
              </h1>
            </div>
            <p className="text-xs font-mono opacity-50">@{data.handle}</p>
            {data.bio && (
              <p className="text-xs opacity-75 max-w-sm mx-auto font-serif italic" style={{ color: theme.text_color }}>
                {data.bio}
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
                  onClick={() => setActivePageId(pg.id)}
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
                      <span>{block.title || 'Folder / Group'}</span>
                      {block.folder_items?.length > 0 && (
                        <span className="px-2 py-0.5 rounded-md bg-black/10 dark:bg-white/10 text-[10px] font-mono">
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
                        <span className="truncate">{block.title || block.headline || 'View Details'}</span>
                        {block.badge && (
                          <span className="px-2 py-0.5 text-[9px] font-black uppercase tracking-wider bg-rose-500 text-white rounded-full">
                            {block.badge}
                          </span>
                        )}
                      </div>
                      {block.subtitle && (
                        <p className="text-[11px] opacity-70 font-normal mt-0.5 truncate">{block.subtitle}</p>
                      )}
                    </div>

                    <FaExternalLinkAlt className="text-xs opacity-40 shrink-0 ml-2" />
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
                  className={`w-full p-5 space-y-2.5 text-center ${cardObj.className}`}
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
                    <form onSubmit={(e) => handleSubscribe(e, block.id)} className="flex items-center gap-2 pt-1">
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
                    </form>
                  )}
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

      {/* Powered by Unravler footer */}
      <div className="pt-12 text-center text-xs opacity-50 hover:opacity-100 transition-opacity relative z-10">
        <a
          href="https://www.unravler.com"
          target="_blank"
          rel="noreferrer"
          style={{ color: theme.text_color }}
          className="font-bold tracking-wider"
        >
          ⚡ Powered by Unravler Smart Bio
        </a>
      </div>
    </div>
  );
}
