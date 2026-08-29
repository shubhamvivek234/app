import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { getPublicBioPage, trackBioLinkClick } from '@/lib/api';
import {
  FaGlobe,
  FaInstagram,
  FaTwitter,
  FaYoutube,
  FaLinkedin,
  FaTiktok,
  FaExternalLinkAlt,
  FaExclamationTriangle,
} from 'react-icons/fa';

export default function PublicBioPage() {
  const { handle } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Strip leading @ if provided in route param
  const cleanHandle = (handle || '').replace(/^@/, '');

  useEffect(() => {
    const fetchPage = async () => {
      try {
        setLoading(true);
        const res = await getPublicBioPage(cleanHandle);
        setData(res);
      } catch (err) {
        setError(err?.response?.data?.detail || 'Creator page not found.');
      } finally {
        setLoading(false);
      }
    };
    if (cleanHandle) fetchPage();
  }, [cleanHandle]);

  const handleLinkClick = async (link) => {
    try {
      trackBioLinkClick(cleanHandle, link.id);
    } catch (e) {
      // Non-blocking
    }
    window.open(link.url, '_blank', 'noopener,noreferrer');
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
        <div className="w-10 h-10 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4 text-white text-center">
        <div className="max-w-sm w-full bg-slate-900 rounded-3xl p-8 border border-slate-800 space-y-3">
          <FaExclamationTriangle className="text-3xl text-amber-400 mx-auto" />
          <h2 className="text-lg font-bold">Page Not Found</h2>
          <p className="text-xs text-slate-400">@{cleanHandle} does not exist or has been made private.</p>
        </div>
      </div>
    );
  }

  const theme = data.theme || {};
  const links = data.custom_links || [];
  const gridPosts = data.grid_posts || [];

  return (
    <div
      style={{
        backgroundColor: theme.background_color || '#0f172a',
        color: theme.text_color || '#ffffff',
      }}
      className="min-h-screen flex flex-col items-center py-12 px-4 transition-colors duration-200"
    >
      <div className="max-w-md w-full flex flex-col items-center text-center space-y-5">
        {/* Avatar */}
        <div className="w-24 h-24 rounded-full bg-slate-800 border-3 border-white/20 overflow-hidden flex items-center justify-center shadow-lg shrink-0">
          {data.avatar_url ? (
            <img src={data.avatar_url} alt={data.title} className="w-full h-full object-cover" />
          ) : (
            <span className="text-3xl font-extrabold uppercase">{data.title ? data.title[0] : 'U'}</span>
          )}
        </div>

        {/* Title & Bio */}
        <div className="space-y-1">
          <h1 className="text-xl font-extrabold tracking-tight">{data.title}</h1>
          <p className="text-xs font-mono opacity-60">@{data.handle}</p>
          {data.bio && <p className="text-xs opacity-80 max-w-xs mx-auto pt-1 leading-relaxed">{data.bio}</p>}
        </div>

        {/* Social Icons Bar */}
        {data.social_links && Object.keys(data.social_links).length > 0 && (
          <div className="flex items-center justify-center gap-3 pt-1">
            {Object.entries(data.social_links).map(([plat, url]) => (
              <a
                key={plat}
                href={url}
                target="_blank"
                rel="noreferrer"
                className="w-9 h-9 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-sm transition-transform active:scale-95"
              >
                <FaGlobe />
              </a>
            ))}
          </div>
        )}

        {/* Custom Links Stack */}
        <div className="w-full space-y-3 pt-2">
          {links.map((link) => (
            <button
              key={link.id}
              onClick={() => handleLinkClick(link)}
              style={{ backgroundColor: theme.card_background || '#1e293b' }}
              className={`w-full py-3.5 px-5 ${theme.button_style || 'rounded-2xl'} shadow-md font-bold text-sm flex items-center justify-between transition-all hover:opacity-95 active:scale-[0.98]`}
            >
              <span className="w-5" />
              <span>{link.title}</span>
              <FaExternalLinkAlt className="text-xs opacity-50" />
            </button>
          ))}
        </div>

        {/* Media Grid */}
        {gridPosts.length > 0 && (
          <div className="w-full pt-6 border-t border-white/10 space-y-3">
            <span className="text-xs font-bold uppercase tracking-wider opacity-60 block">Recent Posts</span>
            <div className="grid grid-cols-3 gap-2">
              {gridPosts.map((p) => (
                <div key={p.id} className="aspect-square bg-white/10 rounded-xl overflow-hidden group relative">
                  <img src={p.media_url} alt={p.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform" />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Powered by Unravler footer */}
        <div className="pt-8 text-[11px] opacity-40 hover:opacity-100 transition-opacity">
          <a href="https://www.unravler.com" target="_blank" rel="noreferrer" className="font-semibold tracking-wide">
            Powered by Unravler
          </a>
        </div>
      </div>
    </div>
  );
}
