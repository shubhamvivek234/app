import React from 'react';
import { FaYoutube, FaEllipsisV, FaThumbsUp, FaThumbsDown, FaShare, FaDownload } from 'react-icons/fa';

const YouTubePreview = ({ content, media, account, videoTitle }) => {
  const channelName = account?.platform_username || 'Your Channel';
  const avatar      = account?.picture_url;
  const title       = videoTitle || (content ? content.split('\n')[0].slice(0, 80) : 'Your video title');

  // YouTube only shows a single video/thumbnail
  const mediaArray = Array.isArray(media) ? media : (media ? [media] : []);
  const firstItem  = mediaArray[0] || null;
  const hasVideo   = firstItem?.type === 'video';

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
      {/* Thumbnail / Video */}
      <div className="relative aspect-video bg-gray-900 overflow-hidden">
        {firstItem ? (
          firstItem.type === 'video' ? (
            <video src={firstItem.url} className="w-full h-full object-cover" />
          ) : (
            <img src={firstItem.url} alt="" className="w-full h-full object-cover" />
          )
        ) : (
          /* Empty state — prompt to add video */
          <div className="w-full h-full flex flex-col items-center justify-center gap-2 bg-gradient-to-br from-gray-800 to-gray-950">
            <FaYoutube className="text-5xl text-red-500 opacity-40" />
            <p className="text-gray-400 text-xs text-center px-4">
              Add a video to preview your YouTube upload
            </p>
          </div>
        )}

        {/* Play button overlay (only when media present) */}
        {firstItem && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/10">
            <div className="w-14 h-14 rounded-full bg-black/60 flex items-center justify-center hover:bg-black/80 transition-colors cursor-pointer">
              <svg className="w-6 h-6 text-white ml-1" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z" />
              </svg>
            </div>
          </div>
        )}

        {/* Duration badge */}
        {firstItem && (
          <div className="absolute bottom-1.5 right-1.5 bg-black/80 text-white text-[10px] font-medium px-1.5 py-0.5 rounded">
            {hasVideo ? '0:00' : '—'}
          </div>
        )}

        {/* "New" badge for freshly uploaded */}
        {firstItem && (
          <div className="absolute top-2 left-2 bg-red-600 text-white text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wide">
            NEW
          </div>
        )}
      </div>

      {/* Video meta */}
      <div className="p-3 flex gap-2.5">
        {avatar ? (
          <img
            src={avatar}
            alt={channelName}
            className="w-9 h-9 rounded-full object-cover flex-shrink-0 mt-0.5"
          />
        ) : (
          <div className="w-9 h-9 rounded-full bg-red-600 flex items-center justify-center text-white text-sm font-bold flex-shrink-0 mt-0.5">
            {channelName.charAt(0).toUpperCase()}
          </div>
        )}

        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-900 leading-snug line-clamp-2 mb-1">
            {title || <span className="text-gray-300 italic">Add a title…</span>}
          </p>
          <p className="text-xs text-gray-500 hover:text-gray-800 cursor-pointer font-medium">{channelName}</p>
          <p className="text-xs text-gray-400">0 views · Just now</p>
        </div>

        <FaEllipsisV className="text-gray-400 text-sm flex-shrink-0 mt-0.5" />
      </div>

      {/* Action bar (Like / Dislike / Share / Download) */}
      <div className="border-t border-gray-100 px-3 py-2 flex items-center gap-1">
        <div className="flex items-center bg-gray-100 rounded-full overflow-hidden divide-x divide-gray-200">
          <button className="flex items-center gap-1.5 px-3 py-1.5 hover:bg-gray-200 transition-colors text-xs font-medium text-gray-600">
            <FaThumbsUp className="text-sm" />
            <span>0</span>
          </button>
          <button className="flex items-center px-3 py-1.5 hover:bg-gray-200 transition-colors">
            <FaThumbsDown className="text-sm text-gray-500" />
          </button>
        </div>

        <button className="flex items-center gap-1.5 bg-gray-100 hover:bg-gray-200 rounded-full px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors ml-2">
          <FaShare className="text-sm" />
          Share
        </button>

        <button className="flex items-center gap-1.5 bg-gray-100 hover:bg-gray-200 rounded-full px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors">
          <FaDownload className="text-sm" />
          Download
        </button>
      </div>

      {/* Description snippet */}
      {content && (
        <div className="px-3 pb-3">
          <div className="bg-gray-50 rounded-xl px-3 py-2">
            <p className="text-xs text-gray-600 line-clamp-2 leading-relaxed whitespace-pre-wrap">
              {content}
            </p>
            <button className="text-xs font-semibold text-gray-800 mt-0.5">more</button>
          </div>
        </div>
      )}
    </div>
  );
};

export default YouTubePreview;
