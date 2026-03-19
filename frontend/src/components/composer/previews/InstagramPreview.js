import React, { useState } from 'react';
import {
  FaHeart, FaRegComment, FaRegBookmark, FaEllipsisH,
  FaChevronRight, FaChevronLeft, FaMusic, FaVolumeUp,
} from 'react-icons/fa';
import { RiSendPlaneLine } from 'react-icons/ri';

/* ─────────────────────────────────────────────────────────────────────────
   REEL — full-screen 9:16 dark overlay, right-side action bar, TikTok-ish
───────────────────────────────────────────────────────────────────────── */
const ReelPost = ({ mediaArray, content, name, avatar }) => {
  const firstItem = mediaArray[0] || null;

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
          <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-transparent to-black/25" />
        </div>
      ) : (
        <div className="absolute inset-0 bg-gradient-to-br from-gray-900 via-black to-gray-900 flex items-center justify-center">
          <div className="text-center">
            <div className="text-5xl mb-2 opacity-20">🎬</div>
            <p className="text-white/30 text-xs">Add a video for your Reel</p>
          </div>
        </div>
      )}

      {/* Top bar: "Reels" label + mute + more */}
      <div className="absolute top-3 left-0 right-0 flex items-center justify-between px-3 z-10">
        <p className="text-white text-sm font-bold tracking-wide">Reels</p>
        <div className="flex items-center gap-4">
          <FaVolumeUp className="text-white text-base" />
          <FaEllipsisH className="text-white text-base" />
        </div>
      </div>

      {/* Right action bar */}
      <div className="absolute right-3 bottom-20 flex flex-col items-center gap-4 z-10">
        {/* Follow avatar */}
        <div className="relative mb-1">
          {avatar ? (
            <img src={avatar} alt={name} className="w-9 h-9 rounded-full object-cover border-2 border-white" />
          ) : (
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-purple-500 via-pink-500 to-orange-400 flex items-center justify-center text-white text-xs font-bold border-2 border-white">
              {name.charAt(0).toUpperCase()}
            </div>
          )}
          <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 w-4 h-4 rounded-full bg-red-500 flex items-center justify-center shadow">
            <span className="text-white text-[9px] font-bold leading-none">+</span>
          </div>
        </div>

        {[
          { icon: FaHeart,          label: '0' },
          { icon: FaRegComment,     label: '0' },
          { icon: RiSendPlaneLine,  label: '0' },
        ].map(({ icon: Icon, label }, i) => (
          <div key={i} className="flex flex-col items-center gap-0.5">
            <Icon className="text-white text-2xl drop-shadow" />
            <span className="text-white text-[10px] font-medium">{label}</span>
          </div>
        ))}

        <FaEllipsisH className="text-white text-lg mt-1" />

        {/* Spinning music disc */}
        <div
          className="w-8 h-8 rounded-full border-2 border-gray-400 overflow-hidden flex items-center justify-center bg-gray-800"
          style={{ animation: 'spin 4s linear infinite' }}
        >
          <FaMusic className="text-white text-xs" />
        </div>
      </div>

      {/* Bottom info */}
      <div className="absolute bottom-0 left-0 right-12 px-3 pb-5 z-10">
        <div className="flex items-center gap-2 mb-1">
          <p className="text-white text-sm font-bold">@{name}</p>
          <button className="text-white text-xs border border-white/70 rounded px-2 py-0.5 font-medium">
            Follow
          </button>
        </div>
        {content ? (
          <p className="text-white text-xs leading-relaxed line-clamp-2 opacity-90 whitespace-pre-wrap">
            {content}
          </p>
        ) : (
          <p className="text-white/40 text-xs italic">Caption for your reel…</p>
        )}
        <div className="flex items-center gap-1.5 mt-2">
          <FaMusic className="text-white text-[10px]" />
          <p className="text-white/80 text-[10px] truncate">Original audio · {name}</p>
        </div>
      </div>
    </div>
  );
};

/* ─────────────────────────────────────────────────────────────────────────
   STORY — 9:16, progress bars at top, user overlay, colored bg, send bar
───────────────────────────────────────────────────────────────────────── */
const BG_GRADIENTS = [
  'from-purple-600 via-pink-600 to-red-500',
  'from-blue-600 via-cyan-500 to-teal-400',
  'from-orange-500 via-amber-500 to-yellow-400',
  'from-green-600 via-emerald-500 to-teal-500',
];

const StoryPost = ({ mediaArray, content, name, avatar }) => {
  const firstItem = mediaArray[0] || null;
  const bgGradient = BG_GRADIENTS[(name.charCodeAt(0) || 0) % BG_GRADIENTS.length];

  return (
    <div
      className="rounded-xl overflow-hidden relative bg-black shadow-sm w-full"
      style={{ aspectRatio: '9/16', maxHeight: '480px' }}
    >
      {/* Background */}
      {firstItem ? (
        <div className="absolute inset-0">
          {firstItem.type === 'video' ? (
            <video src={firstItem.url} className="w-full h-full object-cover" />
          ) : (
            <img src={firstItem.url} alt="" className="w-full h-full object-cover" />
          )}
          {/* Subtle darkening at top/bottom for readability */}
          <div className="absolute inset-0 bg-gradient-to-b from-black/40 via-transparent to-black/30" />
        </div>
      ) : (
        /* Text-only story: gradient background with large text */
        <div className={`absolute inset-0 bg-gradient-to-br ${bgGradient} flex items-center justify-center px-6`}>
          {content ? (
            <p className="text-white text-2xl font-bold text-center leading-snug drop-shadow-lg">
              {content.slice(0, 100)}
            </p>
          ) : (
            <p className="text-white/50 text-sm italic text-center">
              Add text or upload an image / video
            </p>
          )}
        </div>
      )}

      {/* Story progress bars (top) */}
      <div className="absolute top-2 left-2 right-2 flex gap-0.5 z-10">
        {[0.55, 0, 0].map((fill, i) => (
          <div key={i} className="flex-1 h-0.5 bg-white/40 rounded-full overflow-hidden">
            {fill > 0 && (
              <div className="h-full bg-offwhite rounded-full" style={{ width: `${fill * 100}%` }} />
            )}
          </div>
        ))}
      </div>

      {/* Top: user info */}
      <div className="absolute top-5 left-0 right-0 flex items-center justify-between px-3 z-10">
        <div className="flex items-center gap-2">
          {avatar ? (
            <img
              src={avatar}
              alt={name}
              className="w-8 h-8 rounded-full object-cover border-2 border-white"
            />
          ) : (
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 via-pink-500 to-orange-400 flex items-center justify-center text-white text-xs font-bold border-2 border-white">
              {name.charAt(0).toUpperCase()}
            </div>
          )}
          <div>
            <p className="text-white text-xs font-semibold drop-shadow">{name}</p>
            <p className="text-white/70 text-[10px]">Just now</p>
          </div>
          <p className="text-white/60 text-xs ml-1">· · ·</p>
        </div>
        <div className="flex items-center gap-3">
          <FaEllipsisH className="text-white text-sm drop-shadow" />
          <span className="text-white text-base font-light leading-none drop-shadow">✕</span>
        </div>
      </div>

      {/* Text overlay when media present + content */}
      {firstItem && content && (
        <div className="absolute inset-x-4 bottom-28 z-10">
          <div className="bg-black/50 backdrop-blur-sm rounded-xl px-4 py-2.5 text-center">
            <p className="text-white text-sm font-semibold leading-snug">
              {content.slice(0, 80)}
            </p>
          </div>
        </div>
      )}

      {/* Bottom: send message bar (no like/comment buttons — stories don't have them) */}
      <div className="absolute bottom-0 left-0 right-0 px-3 pb-5 z-10">
        <div className="flex items-center gap-2">
          <div className="flex-1 border border-white/60 rounded-full px-4 py-2 backdrop-blur-sm bg-black/10">
            <p className="text-white/70 text-xs">Send message</p>
          </div>
          <RiSendPlaneLine className="text-white text-lg flex-shrink-0 drop-shadow" />
          <FaHeart className="text-white text-lg flex-shrink-0 drop-shadow" />
        </div>
      </div>
    </div>
  );
};

/* ─────────────────────────────────────────────────────────────────────────
   FEED POST — white card, square/portrait, carousel support
───────────────────────────────────────────────────────────────────────── */
const FeedPost = ({
  mediaArray, isCarousel, activeSlide, setActiveSlide,
  content, name, avatar, expanded, setExpanded, displayText, shouldTruncate,
}) => {
  const currentItem = mediaArray[activeSlide] || null;

  return (
    <div className="bg-offwhite rounded-xl border border-gray-200 overflow-hidden shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between p-3">
        <div className="flex items-center gap-2.5">
          {avatar ? (
            <img
              src={avatar}
              alt={name}
              className="w-8 h-8 rounded-full object-cover"
              style={{
                padding: '2px',
                background: 'linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888)',
              }}
            />
          ) : (
            /* Gradient ring avatar */
            <div
              className="w-8 h-8 rounded-full p-0.5 flex-shrink-0"
              style={{ background: 'linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888)' }}
            >
              <div className="w-full h-full rounded-full bg-offwhite flex items-center justify-center text-xs font-bold text-gray-700">
                {name.charAt(0).toUpperCase()}
              </div>
            </div>
          )}
          <p className="text-xs font-semibold text-gray-900">{name}</p>
        </div>
        <FaEllipsisH className="text-gray-400 text-sm" />
      </div>

      {/* Media (square) */}
      {currentItem ? (
        <div className="aspect-square bg-black overflow-hidden relative">
          {currentItem.type === 'video' ? (
            <>
              <video src={currentItem.url} className="w-full h-full object-cover" />
              {/* Video play indicator */}
              <div className="absolute top-2 left-2 bg-black/60 rounded px-1.5 py-0.5 flex items-center gap-1">
                <svg className="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8 5v14l11-7z" />
                </svg>
                <span className="text-white text-[9px] font-medium">VIDEO</span>
              </div>
            </>
          ) : (
            <img src={currentItem.url} alt="" className="w-full h-full object-cover" />
          )}

          {/* Carousel counter */}
          {isCarousel && (
            <div className="absolute top-2 right-2 bg-black/60 text-white text-[10px] font-medium px-1.5 py-0.5 rounded-full">
              {activeSlide + 1}/{mediaArray.length}
            </div>
          )}
          {/* Prev arrow */}
          {isCarousel && activeSlide > 0 && (
            <button
              onClick={() => setActiveSlide(i => Math.max(i - 1, 0))}
              className="absolute left-1.5 top-1/2 -translate-y-1/2 w-7 h-7 rounded-full bg-white/80 flex items-center justify-center shadow"
            >
              <FaChevronLeft className="text-gray-700 text-xs" />
            </button>
          )}
          {/* Next arrow */}
          {isCarousel && activeSlide < mediaArray.length - 1 && (
            <button
              onClick={() => setActiveSlide(i => Math.min(i + 1, mediaArray.length - 1))}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 w-7 h-7 rounded-full bg-white/80 flex items-center justify-center shadow"
            >
              <FaChevronRight className="text-gray-700 text-xs" />
            </button>
          )}
        </div>
      ) : (
        /* No media placeholder */
        <div className="aspect-square bg-gradient-to-br from-gray-100 to-gray-200 flex items-center justify-center">
          <div className="text-center">
            <div className="text-4xl mb-2">🖼️</div>
            <p className="text-xs text-gray-400">No media</p>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="px-3 pt-2.5 pb-1">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-3.5">
            <FaHeart className="text-xl text-gray-300" />
            <FaRegComment className="text-xl text-gray-300" />
            <RiSendPlaneLine className="text-xl text-gray-300" />
          </div>
          <FaRegBookmark className="text-xl text-gray-300" />
        </div>

        {/* Carousel dots below actions (Instagram style) */}
        {isCarousel && (
          <div className="flex gap-1 mb-2">
            {mediaArray.map((_, i) => (
              <button
                key={i}
                onClick={() => setActiveSlide(i)}
                className={`rounded-full h-1.5 transition-all ${
                  i === activeSlide ? 'w-4 bg-blue-500' : 'w-1.5 bg-gray-300'
                }`}
              />
            ))}
          </div>
        )}

        {/* Caption */}
        <div className="text-xs text-gray-800 leading-relaxed">
          {content ? (
            <>
              <span className="font-semibold mr-1">{name}</span>
              <span className="whitespace-pre-wrap">{displayText}</span>
              {shouldTruncate && (
                <button onClick={() => setExpanded(true)} className="text-gray-400 ml-1">
                  more
                </button>
              )}
            </>
          ) : (
            <span className="text-gray-300 italic">Start typing to preview…</span>
          )}
        </div>
        <p className="text-[10px] text-gray-300 mt-1.5 mb-2">Add a comment…</p>
      </div>
    </div>
  );
};

/* ─────────────────────────────────────────────────────────────────────────
   Main component — routes to the right sub-preview
───────────────────────────────────────────────────────────────────────── */
const InstagramPreview = ({ content, media, account, postFormat }) => {
  const [expanded, setExpanded] = useState(false);
  const [activeSlide, setActiveSlide] = useState(0);

  const name   = account?.platform_username || 'your_account';
  const avatar = account?.picture_url;
  const MAX    = 100;
  const shouldTruncate = content.length > MAX && !expanded;
  const displayText    = shouldTruncate ? content.slice(0, MAX) + '…' : content;

  const mediaArray = Array.isArray(media) ? media : (media ? [media] : []);
  const isCarousel = mediaArray.length > 1;

  if (postFormat === 'Reel') {
    return <ReelPost mediaArray={mediaArray} content={content} name={name} avatar={avatar} />;
  }

  if (postFormat === 'Story') {
    return <StoryPost mediaArray={mediaArray} content={content} name={name} avatar={avatar} />;
  }

  return (
    <FeedPost
      mediaArray={mediaArray}
      isCarousel={isCarousel}
      activeSlide={activeSlide}
      setActiveSlide={setActiveSlide}
      content={content}
      name={name}
      avatar={avatar}
      expanded={expanded}
      setExpanded={setExpanded}
      displayText={displayText}
      shouldTruncate={shouldTruncate}
    />
  );
};

export default InstagramPreview;
