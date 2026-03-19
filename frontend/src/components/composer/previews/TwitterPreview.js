import React from 'react';
import { FaRegComment, FaRetweet, FaRegHeart, FaRegBookmark } from 'react-icons/fa';
import { RiUpload2Line, RiBarChartFill } from 'react-icons/ri';

/* ── Twitter-style media grid ────────────────────────────────────────────── */
const TwitterMediaGrid = ({ mediaArray }) => {
  const video  = mediaArray.find(m => m.type === 'video');
  const images = mediaArray.filter(m => m.type !== 'video').slice(0, 4);

  if (video) {
    return (
      <div className="rounded-2xl overflow-hidden border border-gray-200 mb-2 relative" style={{ maxHeight: '200px' }}>
        <video src={video.url} className="w-full max-h-48 object-cover" />
        {/* Play overlay */}
        <div className="absolute inset-0 flex items-center justify-center bg-black/20">
          <div className="w-12 h-12 rounded-full bg-black/60 flex items-center justify-center">
            <svg className="w-5 h-5 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
          </div>
        </div>
      </div>
    );
  }

  if (images.length === 0) return null;

  if (images.length === 1) {
    return (
      <div className="rounded-2xl overflow-hidden border border-gray-200 mb-2">
        <img src={images[0].url} alt="" className="w-full max-h-56 object-cover" />
      </div>
    );
  }

  if (images.length === 2) {
    return (
      <div className="grid grid-cols-2 gap-0.5 rounded-2xl overflow-hidden mb-2" style={{ height: '180px' }}>
        {images.map((m, i) => (
          <img key={i} src={m.url} alt="" className="w-full h-full object-cover" />
        ))}
      </div>
    );
  }

  if (images.length === 3) {
    return (
      <div
        className="grid gap-0.5 rounded-2xl overflow-hidden mb-2"
        style={{ gridTemplateColumns: '2fr 1fr', height: '180px' }}
      >
        <img src={images[0].url} alt="" className="w-full h-full object-cover" />
        <div className="flex flex-col gap-0.5">
          <img src={images[1].url} alt="" className="w-full object-cover" style={{ height: '89px' }} />
          <img src={images[2].url} alt="" className="w-full object-cover" style={{ height: '89px' }} />
        </div>
      </div>
    );
  }

  // 4 images — 2×2
  return (
    <div className="grid grid-cols-2 gap-0.5 rounded-2xl overflow-hidden mb-2">
      {images.map((m, i) => (
        <img key={i} src={m.url} alt="" className="w-full object-cover" style={{ height: '90px' }} />
      ))}
    </div>
  );
};

/* ── TwitterPreview ──────────────────────────────────────────────────────── */
const TwitterPreview = ({ content, media, account }) => {
  const name   = account?.platform_username || 'YourHandle';
  const avatar = account?.picture_url;
  const LIMIT  = 280;
  const over   = content.length - LIMIT;
  const remaining = LIMIT - content.length;

  // Circular progress ring for character count (like real Twitter/X)
  const radius  = 10;
  const circumf = 2 * Math.PI * radius;
  const filled  = Math.min(content.length / LIMIT, 1);
  const strokeDashoffset = circumf * (1 - filled);
  const ringColor =
    content.length >= LIMIT    ? '#f4212e' :
    content.length >= LIMIT * 0.8 ? '#ffd400' :
    '#1d9bf0';

  const mediaArray = Array.isArray(media) ? media : (media ? [media] : []);

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
      <div className="p-3">
        <div className="flex gap-2.5">
          {/* Avatar */}
          <div className="flex-shrink-0">
            {avatar ? (
              <img src={avatar} alt={name} className="w-9 h-9 rounded-full object-cover" />
            ) : (
              <div className="w-9 h-9 rounded-full bg-black flex items-center justify-center text-white text-sm font-bold">
                {name.charAt(0).toUpperCase()}
              </div>
            )}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1 flex-wrap mb-1">
              <span className="text-sm font-bold text-gray-900 truncate">{name}</span>
              <span className="text-xs text-gray-400 truncate">
                @{name.toLowerCase().replace(/\s+/g, '_')}
              </span>
              <span className="text-gray-300">·</span>
              <span className="text-xs text-gray-400">now</span>
              {/* Verified badge */}
              <svg className="w-4 h-4 text-blue-500 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
                <path d="M22.25 12c0-1.43-.88-2.67-2.19-3.34.46-1.39.2-2.9-.81-3.91s-2.52-1.27-3.91-.81c-.66-1.31-1.91-2.19-3.34-2.19s-2.67.88-3.33 2.19c-1.4-.46-2.91-.2-3.92.81s-1.26 2.52-.8 3.91c-1.31.67-2.2 1.91-2.2 3.34s.89 2.67 2.2 3.34c-.46 1.39-.21 2.9.8 3.91s2.52 1.26 3.91.81c.67 1.31 1.91 2.19 3.34 2.19s2.68-.88 3.34-2.19c1.39.45 2.9.2 3.91-.81s1.27-2.52.81-3.91c1.31-.67 2.19-1.91 2.19-3.34zm-11.71 4.2L6.8 12.46l1.41-1.42 2.26 2.26 4.8-5.23 1.47 1.36-6.2 6.77z" />
              </svg>
            </div>

            {content ? (
              <p className="text-sm text-gray-900 leading-relaxed whitespace-pre-wrap mb-2 break-words">
                {content}
              </p>
            ) : (
              <p className="text-sm text-gray-300 italic mb-2">Start typing to preview…</p>
            )}

            {over > 0 && (
              <p className="text-xs text-red-500 mb-2 font-medium">
                {over} character{over !== 1 ? 's' : ''} over limit
              </p>
            )}

            {mediaArray.length > 0 && <TwitterMediaGrid mediaArray={mediaArray} />}

            {/* Action buttons */}
            <div className="flex items-center justify-between text-gray-400 mt-1">
              {[
                { Icon: FaRegComment,  label: '0' },
                { Icon: FaRetweet,     label: '0' },
                { Icon: FaRegHeart,    label: '0' },
                { Icon: RiBarChartFill, label: '0' },
                { Icon: FaRegBookmark, label: null },
                { Icon: RiUpload2Line, label: null },
              ].map(({ Icon, label }, i) => (
                <button
                  key={i}
                  className="flex items-center gap-1 hover:text-blue-500 transition-colors text-sm"
                >
                  <Icon className="text-base" />
                  {label && <span className="text-xs">{label}</span>}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Character count footer */}
      <div className="border-t border-gray-100 px-3 py-1.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {/* Circular progress ring */}
          <svg width="24" height="24" className="rotate-[-90deg]">
            <circle cx="12" cy="12" r={radius} fill="none" stroke="#e7e7e7" strokeWidth="2" />
            <circle
              cx="12" cy="12" r={radius}
              fill="none"
              stroke={ringColor}
              strokeWidth="2"
              strokeDasharray={circumf}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              style={{ transition: 'stroke-dashoffset 0.2s ease, stroke 0.2s ease' }}
            />
          </svg>
          <span className={`text-xs font-semibold tabular-nums ${over > 0 ? 'text-red-500' : 'text-gray-400'}`}>
            {over > 0 ? `-${over}` : remaining <= 20 ? remaining : ''}
          </span>
        </div>
        <span className="text-xs text-gray-300">X (Twitter)</span>
      </div>
    </div>
  );
};

export default TwitterPreview;
