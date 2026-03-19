import React, { useState } from 'react';
import {
  FaThumbsUp, FaRegComment, FaRetweet, FaRegPaperPlane,
  FaEllipsisH, FaGlobeAmericas, FaLock,
} from 'react-icons/fa';

/* Highlight #hashtags and @mentions in text */
const RichText = ({ text }) => {
  if (!text) return null;
  const parts = text.split(/([@#]\w+)/g);
  return (
    <>
      {parts.map((part, i) =>
        /^[@#]\w+/.test(part) ? (
          <span key={i} className="text-blue-600 hover:underline cursor-pointer">
            {part}
          </span>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  );
};

/* ── Media grid ──────────────────────────────────────────────────────────── */
const MediaGrid = ({ mediaArray }) => {
  const images = mediaArray.filter(m => m.type !== 'video');
  const video  = mediaArray.find(m => m.type === 'video');

  if (video) {
    return (
      <div className="relative aspect-video bg-gray-900 overflow-hidden">
        <video src={video.url} className="w-full h-full object-cover" />
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-14 h-14 rounded-full bg-black/50 flex items-center justify-center">
            <svg className="w-5 h-5 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
          </div>
        </div>
      </div>
    );
  }

  if (images.length === 0) return null;
  if (images.length === 1) return <img src={images[0].url} alt="" className="w-full max-h-72 object-cover" />;

  if (images.length === 2) {
    return (
      <div className="grid grid-cols-2 gap-0.5" style={{ maxHeight: '200px' }}>
        {images.map((m, i) => (
          <img key={i} src={m.url} alt="" className="w-full object-cover" style={{ height: '200px' }} />
        ))}
      </div>
    );
  }

  const show  = images.slice(0, 4);
  const extra = images.length - 4;
  return (
    <div className="grid grid-cols-2 gap-0.5">
      {show.map((m, i) => (
        <div key={i} className="relative" style={{ height: '100px' }}>
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

/* ── LinkedInPreview ─────────────────────────────────────────────────────── */
const LinkedInPreview = ({ content, media, account }) => {
  const [expanded, setExpanded] = useState(false);
  const name   = account?.platform_username || 'Your Name';
  const avatar = account?.picture_url;
  const MAX    = 210;
  const shouldTruncate = content.length > MAX && !expanded;
  const displayText    = shouldTruncate ? content.slice(0, MAX) + '…' : content;

  const mediaArray = Array.isArray(media) ? media : (media ? [media] : []);

  return (
    <div className="bg-offwhite rounded-xl border border-gray-200 overflow-hidden shadow-sm">
      {/* Header */}
      <div className="p-3 flex items-start justify-between">
        <div className="flex items-start gap-2.5">
          {avatar ? (
            <img src={avatar} alt={name} className="w-10 h-10 rounded-full object-cover flex-shrink-0" />
          ) : (
            <div className="w-10 h-10 rounded-full bg-blue-700 flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
              {name.charAt(0).toUpperCase()}
            </div>
          )}
          <div>
            <div className="flex items-center gap-1.5">
              <p className="text-sm font-semibold text-gray-900 leading-tight">{name}</p>
              {/* LinkedIn blue badge */}
              <svg className="w-3.5 h-3.5 text-blue-600 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
                <path d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
              </svg>
            </div>
            <p className="text-xs text-gray-500 leading-tight">Social Media Manager · 1st</p>
            <div className="flex items-center gap-1 text-[10px] text-gray-400 mt-0.5">
              <span>Just now</span>
              <span>·</span>
              <FaGlobeAmericas className="text-[9px]" />
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button className="text-xs text-blue-600 font-semibold border border-blue-500 rounded-full px-3 py-0.5 hover:bg-blue-50 transition-colors">
            + Follow
          </button>
          <FaEllipsisH className="text-gray-400 text-sm" />
        </div>
      </div>

      {/* Content */}
      <div className="px-3 pb-2">
        {content ? (
          <div className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap break-words">
            <RichText text={displayText} />
            {shouldTruncate && (
              <button
                onClick={() => setExpanded(true)}
                className="text-gray-500 hover:text-gray-800 font-semibold ml-1 text-sm"
              >
                …see more
              </button>
            )}
          </div>
        ) : (
          <p className="text-sm text-gray-300 italic">Start typing to preview…</p>
        )}
      </div>

      {/* Media */}
      {mediaArray.length > 0 && (
        <div className="overflow-hidden mb-0.5">
          <MediaGrid mediaArray={mediaArray} />
        </div>
      )}

      {/* Reaction summary */}
      <div className="px-3 pt-2 pb-0 flex items-center justify-between text-xs text-gray-400">
        <div className="flex items-center gap-1">
          <span className="flex">
            <span className="text-base">👍</span>
            <span className="text-base -ml-1">❤️</span>
            <span className="text-base -ml-1">💡</span>
          </span>
          <span>Be the first to react</span>
        </div>
        <span>0 comments · 0 reposts</span>
      </div>

      {/* Divider */}
      <div className="mx-3 border-t border-gray-100 mt-2" />

      {/* Action buttons */}
      <div className="px-1 pb-1">
        <div className="flex items-center justify-around">
          {[
            { icon: FaThumbsUp,      label: 'Like'    },
            { icon: FaRegComment,    label: 'Comment' },
            { icon: FaRetweet,       label: 'Repost'  },
            { icon: FaRegPaperPlane, label: 'Send'    },
          ].map(({ icon: Icon, label }) => (
            <button
              key={label}
              className="flex items-center gap-1.5 text-xs font-semibold text-gray-500 hover:text-blue-600 hover:bg-blue-50 py-2 px-2 rounded-lg transition-colors"
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

export default LinkedInPreview;
