import React, { useState } from 'react';
import { FaGlobeAmericas, FaThumbsUp, FaRegComment, FaShare, FaEllipsisH, FaVideo } from 'react-icons/fa';

/* Colored backgrounds for short text-only posts (like real Facebook) */
const TEXT_BG_STYLES = [
  { bg: 'from-blue-500 to-blue-700',       text: 'text-white' },
  { bg: 'from-purple-500 to-purple-800',    text: 'text-white' },
  { bg: 'from-orange-400 to-rose-500',      text: 'text-white' },
  { bg: 'from-green-500 to-emerald-700',    text: 'text-white' },
  { bg: 'from-pink-500 to-fuchsia-600',     text: 'text-white' },
  { bg: 'from-amber-400 to-orange-500',     text: 'text-white' },
];

/* ── Multi-image grid helper ─────────────────────────────────────────────── */
const MediaGrid = ({ mediaArray }) => {
  const images = mediaArray.filter(m => m.type !== 'video');
  const video  = mediaArray.find(m => m.type === 'video');

  if (video) {
    return (
      <div className="relative aspect-video flex items-center justify-center bg-gray-900">
        <video src={video.url} className="w-full h-full object-contain" />
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-14 h-14 rounded-full bg-black/50 flex items-center justify-center">
            <svg className="w-6 h-6 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
          </div>
        </div>
        {/* Video duration badge */}
        <div className="absolute bottom-2 right-2 bg-black/70 text-white text-[10px] font-medium px-1.5 py-0.5 rounded flex items-center gap-1">
          <FaVideo className="text-[9px]" />
          <span>0:00</span>
        </div>
      </div>
    );
  }

  if (images.length === 0) return null;

  if (images.length === 1) {
    return <img src={images[0].url} alt="" className="w-full object-cover max-h-72" />;
  }

  if (images.length === 2) {
    return (
      <div className="grid grid-cols-2 gap-0.5" style={{ maxHeight: '220px' }}>
        {images.map((m, i) => (
          <img key={i} src={m.url} alt="" className="w-full object-cover" style={{ height: '220px' }} />
        ))}
      </div>
    );
  }

  if (images.length === 3) {
    return (
      <div className="flex flex-col gap-0.5">
        <img src={images[0].url} alt="" className="w-full object-cover" style={{ height: '160px' }} />
        <div className="grid grid-cols-2 gap-0.5">
          <img src={images[1].url} alt="" className="w-full object-cover" style={{ height: '100px' }} />
          <img src={images[2].url} alt="" className="w-full object-cover" style={{ height: '100px' }} />
        </div>
      </div>
    );
  }

  // 4+ images: 2×2 grid with "+N" overlay
  const show  = images.slice(0, 4);
  const extra = images.length - 4;
  return (
    <div className="grid grid-cols-2 gap-0.5">
      {show.map((m, i) => (
        <div key={i} className="relative" style={{ height: '110px' }}>
          <img src={m.url} alt="" className="w-full h-full object-cover" />
          {i === 3 && extra > 0 && (
            <div className="absolute inset-0 bg-black/55 flex items-center justify-center text-white font-bold text-xl">
              +{extra}
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

/* ── FacebookPreview ─────────────────────────────────────────────────────── */
const FacebookPreview = ({ content, media, account }) => {
  const [expanded, setExpanded] = useState(false);
  const name   = account?.platform_username || 'Your Page';
  const avatar = account?.picture_url;
  const MAX    = 180;
  const shouldTruncate = content.length > MAX && !expanded;
  const displayText    = shouldTruncate ? content.slice(0, MAX) + '…' : content;

  const mediaArray = Array.isArray(media) ? media : (media ? [media] : []);

  // Short text-only posts get a colored background (Facebook feature)
  const isTextOnly   = mediaArray.length === 0 && content.length > 0;
  const isShortText  = isTextOnly && content.length <= 130;
  const bgStyle      = TEXT_BG_STYLES[(name.charCodeAt(0) || 0) % TEXT_BG_STYLES.length];

  return (
    <div className="bg-offwhite rounded-xl border border-gray-200 overflow-hidden shadow-sm">
      {/* Header */}
      <div className="flex items-start justify-between p-3">
        <div className="flex items-center gap-2.5">
          {avatar ? (
            <img src={avatar} alt={name} className="w-9 h-9 rounded-full object-cover" />
          ) : (
            <div className="w-9 h-9 rounded-full bg-blue-600 flex items-center justify-center text-white text-sm font-bold">
              {name.charAt(0).toUpperCase()}
            </div>
          )}
          <div>
            <p className="text-sm font-semibold text-gray-900 leading-tight">{name}</p>
            <div className="flex items-center gap-1 text-xs text-gray-400">
              <span>Just now</span>
              <span>·</span>
              <FaGlobeAmericas className="text-[10px]" />
            </div>
          </div>
        </div>
        <FaEllipsisH className="text-gray-400 text-sm mt-1" />
      </div>

      {/* Text — short text-only → colored background block */}
      {isShortText ? (
        <div className={`mx-0 bg-gradient-to-br ${bgStyle.bg} flex items-center justify-center py-8 px-6 mb-0`}
          style={{ minHeight: '140px' }}>
          <p className={`${bgStyle.text} text-xl font-bold text-center leading-snug`}>
            {content}
          </p>
        </div>
      ) : (
        content && (
          <div className="px-3 pb-2 text-sm text-gray-800 leading-relaxed">
            <span className="whitespace-pre-wrap">{displayText}</span>
            {shouldTruncate && (
              <button
                onClick={() => setExpanded(true)}
                className="text-blue-600 hover:underline ml-1 text-sm font-medium"
              >
                See more
              </button>
            )}
          </div>
        )
      )}

      {!content && mediaArray.length === 0 && (
        <div className="px-3 pb-2 text-sm text-gray-300 italic">
          Start typing to preview…
        </div>
      )}

      {/* Media */}
      {mediaArray.length > 0 && (
        <div className="bg-black overflow-hidden">
          <MediaGrid mediaArray={mediaArray} />
        </div>
      )}

      {/* Reaction counts row */}
      <div className="px-3 pt-2.5 pb-0">
        <div className="flex items-center justify-between text-xs text-gray-400 pb-2 border-b border-gray-100">
          <div className="flex items-center gap-1">
            <span className="flex">
              <span className="w-4 h-4 rounded-full bg-blue-500 flex items-center justify-center text-[8px] z-10">👍</span>
              <span className="w-4 h-4 rounded-full bg-red-500 flex items-center justify-center text-[8px] -ml-1 z-0">❤️</span>
              <span className="w-4 h-4 rounded-full bg-yellow-400 flex items-center justify-center text-[8px] -ml-1 z-0">😮</span>
            </span>
            <span className="ml-1">Be the first to react</span>
          </div>
          <span>0 comments</span>
        </div>
      </div>

      {/* Action buttons */}
      <div className="px-3 pb-2">
        <div className="flex items-center justify-around pt-1.5">
          {[
            { icon: FaThumbsUp,   label: 'Like'    },
            { icon: FaRegComment, label: 'Comment' },
            { icon: FaShare,      label: 'Share'   },
          ].map(({ icon: Icon, label }) => (
            <button
              key={label}
              className="flex items-center gap-1.5 text-xs font-semibold text-gray-500 hover:text-gray-700 py-1.5 px-3 rounded-lg hover:bg-gray-100 transition-colors"
            >
              <Icon className="text-base" />
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default FacebookPreview;
