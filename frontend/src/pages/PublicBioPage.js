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
} from 'react-icons/fa';

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
  const blocks = data.blocks || [];
  const gridPosts = data.grid_posts || [];

  return (
    <div
      style={{
        background: theme.background_gradient || theme.background_color || '#FDFBF7',
        color: theme.text_color || '#18181B',
        fontFamily: theme.font_family || 'Plus Jakarta Sans, sans-serif',
      }}
      className="min-h-screen flex flex-col items-center justify-between py-12 px-4 transition-colors duration-300"
    >
      <div className="max-w-md w-full flex flex-col items-center text-center space-y-6">
        {/* Avatar */}
        <div className="w-24 h-24 rounded-full border-3 border-black/10 dark:border-white/20 overflow-hidden flex items-center justify-center shadow-xl shrink-0 bg-black/5">
          {data.avatar_url ? (
            <img src={data.avatar_url} alt={data.title} className="w-full h-full object-cover" />
          ) : (
            <span className="text-3xl font-extrabold uppercase" style={{ color: theme.text_color }}>
              {data.title ? data.title[0] : 'U'}
            </span>
          )}
        </div>

        {/* Title & Bio */}
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
                  style={{ color: theme.text_color }}
                  className="w-10 h-10 rounded-full bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/20 flex items-center justify-center text-sm shadow-xs transition-transform active:scale-95 hover:scale-105"
                >
                  <Icon />
                </a>
              );
            })}
          </div>
        )}

        {/* Dynamic Blocks Stack */}
        <div className="w-full space-y-3 pt-2">
          {blocks.map((block) => {
            if (block.type === 'link') {
              return (
                <button
                  key={block.id}
                  onClick={() => handleLinkClick(block)}
                  style={{
                    backgroundColor: theme.card_bg || 'rgba(255, 255, 255, 0.85)',
                    borderColor: theme.card_border || 'rgba(0, 0, 0, 0.08)',
                    color: theme.card_text_color || theme.text_color,
                  }}
                  className={`w-full py-4 px-5 ${theme.button_radius || 'rounded-2xl'} border shadow-md font-bold text-sm flex items-center justify-between transition-all hover:scale-[1.01] active:scale-[0.98] cursor-pointer`}
                >
                  <div className="text-left">
                    <div className="flex items-center gap-2">
                      <span>{block.title}</span>
                      {block.badge && (
                        <span className="px-2 py-0.5 text-[9px] font-black uppercase tracking-wider bg-rose-500 text-white rounded-full">
                          {block.badge}
                        </span>
                      )}
                    </div>
                    {block.subtitle && (
                      <p className="text-[11px] opacity-70 font-normal mt-0.5">{block.subtitle}</p>
                    )}
                  </div>
                  <FaExternalLinkAlt className="text-xs opacity-40 shrink-0 ml-2" />
                </button>
              );
            }

            if (block.type === 'feed_grid') {
              if (gridPosts.length === 0) return null;
              return (
                <div key={block.id} className="w-full pt-4 space-y-2 text-left">
                  <span
                    style={{ color: theme.text_color }}
                    className="text-xs font-black uppercase tracking-wider opacity-60 block px-1"
                  >
                    {block.title || 'Recent Highlights'}
                  </span>
                  <div className="grid grid-cols-3 gap-2">
                    {gridPosts.slice(0, block.limit || 6).map((post) => (
                      <div
                        key={post.id}
                        onClick={() => post.post_url && window.open(post.post_url, '_blank')}
                        className="aspect-square bg-black/10 dark:bg-white/10 rounded-2xl overflow-hidden group relative cursor-pointer border border-black/5"
                      >
                        <img
                          src={post.media_url}
                          alt={post.title}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                        />
                        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white text-xs p-2 text-center font-bold">
                          <span className="line-clamp-2">{post.title}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
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
                  style={{
                    backgroundColor: theme.card_bg || 'rgba(255, 255, 255, 0.85)',
                    borderColor: theme.card_border || 'rgba(0, 0, 0, 0.08)',
                    color: theme.card_text_color || theme.text_color,
                  }}
                  className={`w-full p-4 ${theme.button_radius || 'rounded-2xl'} border shadow-md space-y-2 text-left`}
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
                  style={{
                    backgroundColor: theme.card_bg || 'rgba(255, 255, 255, 0.85)',
                    borderColor: theme.card_border || 'rgba(0, 0, 0, 0.08)',
                    color: theme.card_text_color || theme.text_color,
                  }}
                  className={`w-full p-5 ${theme.button_radius || 'rounded-2xl'} border shadow-md space-y-2.5 text-center`}
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
      <div className="pt-12 text-center text-xs opacity-50 hover:opacity-100 transition-opacity">
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
