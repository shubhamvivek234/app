import React from 'react';
import { FaHeart, FaRegComment, FaShare, FaMusic, FaPlus } from 'react-icons/fa';
import { FaTiktok } from 'react-icons/fa';
import { RiSendPlaneLine } from 'react-icons/ri';

const TikTokPreview = ({ content, media, account }) => {
  const name   = account?.platform_username || 'your_account';
  const avatar = account?.picture_url;

  // TikTok is single-video / single-image (vertical)
  const mediaArray = Array.isArray(media) ? media : (media ? [media] : []);
  const firstItem  = mediaArray[0] || null;

  return (
    <div
      className="rounded-xl overflow-hidden relative bg-black shadow-sm w-full"
      style={{ aspectRatio: '9/16', maxHeight: '480px' }}
    >
      {/* Background media */}
      {firstItem ? (
        <div className="absolute inset-0">
          {firstItem.type === 'video' ? (
            <video src={firstItem.url} className="w-full h-full object-cover" />
          ) : (
            <img src={firstItem.url} alt="" className="w-full h-full object-cover" />
          )}
          {/* Gradient overlays for readability */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-b from-black/20 via-transparent to-transparent" />
        </div>
      ) : (
        /* Empty state */
        <div className="absolute inset-0 bg-gradient-to-br from-gray-900 via-black to-gray-900 flex flex-col items-center justify-center gap-3">
          <FaTiktok className="text-5xl text-white opacity-10" />
          <p className="text-white/30 text-xs">Add a video for TikTok</p>
        </div>
      )}

      {/* Top bar */}
      <div className="absolute top-3 left-0 right-0 flex items-center justify-between px-4 z-10">
        <span className="text-white/70 text-sm">Following</span>
        <span className="text-white text-sm font-semibold border-b-2 border-white pb-0.5">For You</span>
        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </div>

      {/* Right action bar */}
      <div className="absolute right-3 bottom-24 flex flex-col items-center gap-5 z-10">
        {/* Avatar with follow */}
        <div className="relative mb-1">
          {avatar ? (
            <img
              src={avatar}
              alt={name}
              className="w-11 h-11 rounded-full object-cover border-2 border-white"
            />
          ) : (
            <div className="w-11 h-11 rounded-full bg-gray-600 border-2 border-white flex items-center justify-center text-white font-bold">
              {name.charAt(0).toUpperCase()}
            </div>
          )}
          <div className="absolute -bottom-2.5 left-1/2 -translate-x-1/2 w-5 h-5 rounded-full bg-[#FE2C55] flex items-center justify-center shadow-md">
            <FaPlus className="text-white text-[9px]" />
          </div>
        </div>

        {/* Like */}
        <div className="flex flex-col items-center gap-0.5">
          <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center">
            <FaHeart className="text-white text-xl" />
          </div>
          <span className="text-white text-[11px] font-medium">0</span>
        </div>

        {/* Comment */}
        <div className="flex flex-col items-center gap-0.5">
          <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center">
            <FaRegComment className="text-white text-xl" />
          </div>
          <span className="text-white text-[11px] font-medium">0</span>
        </div>

        {/* Share */}
        <div className="flex flex-col items-center gap-0.5">
          <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center">
            <RiSendPlaneLine className="text-white text-xl" />
          </div>
          <span className="text-white text-[11px] font-medium">0</span>
        </div>

        {/* Spinning music disc */}
        <div
          className="w-9 h-9 rounded-full border-[3px] border-gray-500 overflow-hidden flex items-center justify-center"
          style={{
            background: 'radial-gradient(circle at center, #555 30%, #222 100%)',
            animation: 'spin 4s linear infinite',
          }}
        >
          <FaMusic className="text-white text-xs" />
        </div>
      </div>

      {/* Bottom info overlay */}
      <div className="absolute bottom-0 left-0 right-14 px-3 pb-5 z-10">
        <p className="text-white text-sm font-bold mb-1 drop-shadow">@{name}</p>
        {content ? (
          <p className="text-white text-xs leading-relaxed line-clamp-3 opacity-90 whitespace-pre-wrap drop-shadow">
            {content}
          </p>
        ) : (
          <p className="text-white/40 text-xs italic">Start typing to preview…</p>
        )}
        <div className="flex items-center gap-1.5 mt-2">
          <FaMusic className="text-white text-[10px]" />
          <p className="text-white/80 text-[10px] truncate drop-shadow">
            Original audio · {name}
          </p>
        </div>
      </div>
    </div>
  );
};

export default TikTokPreview;
