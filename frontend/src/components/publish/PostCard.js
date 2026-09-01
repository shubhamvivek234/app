import React, { useState } from 'react';
import {
  FaTwitter, FaInstagram, FaLinkedin, FaFacebook,
  FaTiktok, FaYoutube, FaPinterest, FaHeart, FaComment,
  FaShare, FaEye, FaBookmark, FaExternalLinkAlt, FaPlay,
  FaReply, FaChevronDown, FaChevronUp,
} from 'react-icons/fa';
import { SiBluesky, SiThreads } from 'react-icons/si';

const PLATFORM_META = {
  facebook: { icon: FaFacebook, color: 'text-blue-600', ring: '#1877F2', label: 'Facebook' },
  twitter: { icon: FaTwitter, color: 'text-sky-500', ring: '#1DA1F2', label: 'X (Twitter)' },
  linkedin: { icon: FaLinkedin, color: 'text-blue-700', ring: '#0A66C2', label: 'LinkedIn' },
  instagram: { icon: FaInstagram, color: 'text-pink-500', ring: '#E1306C', label: 'Instagram' },
  pinterest: { icon: FaPinterest, color: 'text-red-600', ring: '#E60023', label: 'Pinterest' },
  youtube: { icon: FaYoutube, color: 'text-red-500', ring: '#FF0000', label: 'YouTube' },
  tiktok: { icon: FaTiktok, color: 'text-gray-900', ring: '#010101', label: 'TikTok' },
  bluesky: { icon: SiBluesky, color: 'text-blue-500', ring: '#0085FF', label: 'Bluesky' },
  threads: { icon: SiThreads, color: 'text-gray-900', ring: '#101010', label: 'Threads' },
};

const COMMENT_PLATFORMS = new Set(['instagram', 'facebook', 'youtube', 'reddit', 'bluesky']);
const REPLY_PLATFORMS = new Set(['instagram', 'facebook', 'youtube', 'reddit', 'bluesky']);

const AVATAR_COLORS = [
  'bg-blue-500', 'bg-green-500', 'bg-yellow-500', 'bg-red-500',
  'bg-purple-500', 'bg-pink-500', 'bg-indigo-500', 'bg-teal-500',
];

const avatarColor = (name = '') =>
  AVATAR_COLORS[(name.charCodeAt(0) || 0) % AVATAR_COLORS.length];

const Metric = ({ icon: Icon, value, label }) => (
  <span className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 dark:border-gray-700/80 bg-gray-50 dark:bg-gray-800/80 px-2.5 py-1 text-xs text-gray-600 dark:text-gray-300">
    <Icon className="text-[11px]" />
    <span className="font-semibold text-gray-800 dark:text-gray-100">{Number(value).toLocaleString()}</span>
    <span>{label}</span>
  </span>
);

const formatTime = (isoString) => {
  if (!isoString) return '';
  try {
    return new Date(isoString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
};

const formatAbsoluteDateTime = (isoString) => {
  if (!isoString) return '';
  try {
    return new Date(isoString).toLocaleString([], {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
};

const formatRelativeDate = (isoString) => {
  if (!isoString) return '';
  try {
    return new Date(isoString).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  } catch {
    return '';
  }
};

const prettyPostType = (value) => {
  const normalized = String(value || 'text').replace(/_/g, ' ').trim();
  if (!normalized) return 'Text';
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
};

const PostCard = ({ post, onFetchComments, onReplyToComment }) => {
  const [expanded, setExpanded] = useState(false);
  const [commentsOpen, setCommentsOpen] = useState(false);
  const [comments, setComments] = useState([]);
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [replyingTo, setReplyingTo] = useState(null);
  const [replyText, setReplyText] = useState('');
  const [replySending, setReplySending] = useState(false);

  const {
    platform,
    platform_post_id,
    account_username,
    account_display_name,
    account_picture,
    content,
    media_url,
    media_type,
    post_type,
    post_url,
    metrics = {},
    metric_support = {},
    published_at,
    source_mode,
  } = post;

  const meta = PLATFORM_META[platform] || {};
  const PlatformIcon = meta.icon;
  const ringColor = meta.ring || '#3B82F6';
  const primaryName = account_display_name || account_username || meta.label || platform || 'Account';
  const secondaryHandle = account_username && account_username !== primaryName ? account_username : null;
  const captionLimit = 180;
  const isLong = content && content.length > captionLimit;
  const displayContent = isLong && !expanded ? `${content.slice(0, captionLimit)}…` : content;
  const isVideo = media_type === 'VIDEO' || media_type === 'REELS' || String(post_type || '').toLowerCase() === 'video';
  const canFetchComments = COMMENT_PLATFORMS.has(platform) && !!onFetchComments && !!platform_post_id;
  const canReply = REPLY_PLATFORMS.has(platform) && !!onReplyToComment && !!platform_post_id;
  const sourceBadge = source_mode === 'db_fallback' ? 'Unravler Fallback' : 'Platform Feed';
  const publishedLabel = formatAbsoluteDateTime(published_at);

  const visibleMetrics = [
    { key: 'likes', label: 'Likes', icon: FaHeart, value: metrics.likes },
    { key: 'comments', label: 'Comments', icon: FaComment, value: metrics.comments },
    { key: 'shares', label: 'Shares', icon: FaShare, value: metrics.shares },
    { key: 'views', label: 'Views', icon: FaEye, value: metrics.views },
    { key: 'saves', label: 'Saves', icon: FaBookmark, value: metrics.saves },
  ].filter((metric) => {
    if (metric.key === 'saves') return metric.value !== undefined && metric.value !== null;
    const support = metric_support?.[metric.key];
    if (support?.supported === false) return false;
    return metric.value !== undefined && metric.value !== null;
  });

  const engagementUnavailable = source_mode === 'db_fallback' || (
    ['likes', 'comments', 'shares', 'views'].every((key) => metric_support?.[key]?.supported === false)
  );

  const handleFetchComments = async () => {
    if (!canFetchComments) return;
    if (commentsOpen) {
      setCommentsOpen(false);
      return;
    }
    setCommentsLoading(true);
    setCommentsOpen(true);
    try {
      const result = await onFetchComments(post);
      setComments(result?.comments || []);
    } catch {
      setComments([]);
    } finally {
      setCommentsLoading(false);
    }
  };

  const handleReplySubmit = async (comment) => {
    if (!replyText.trim() || replySending || !onReplyToComment) return;
    setReplySending(true);
    try {
      await onReplyToComment(post, comment, replyText.trim());
      setReplyText('');
      setReplyingTo(null);
      if (onFetchComments) {
        const result = await onFetchComments(post);
        setComments(result?.comments || []);
      }
    } finally {
      setReplySending(false);
    }
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-gray-200 dark:border-gray-800 bg-offwhite dark:bg-gray-900/90 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex flex-col gap-4 p-4 md:flex-row md:items-start">
        <div className="order-1 flex items-start justify-between gap-3 md:w-44 md:flex-shrink-0 md:flex-col md:justify-start">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{formatTime(published_at) || 'Unknown time'}</p>
            <p className="mt-1 text-sm font-medium text-gray-700 dark:text-gray-200">{formatRelativeDate(published_at) || 'Unknown date'}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 md:mt-2">
            <span className="inline-flex items-center gap-1 rounded-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 px-2.5 py-1 text-[11px] font-semibold text-gray-700 dark:text-gray-300">
              {PlatformIcon && <PlatformIcon className={meta.color} />}
              {meta.label || platform}
            </span>
            <span className="rounded-full border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 px-2.5 py-1 text-[11px] font-semibold text-gray-600 dark:text-gray-300">
              {prettyPostType(post_type || media_type)}
            </span>
            <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
              source_mode === 'db_fallback'
                ? 'border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300'
                : 'border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300'
            }`}>
              {sourceBadge}
            </span>
          </div>
        </div>

        <div className="order-2 min-w-0 flex-1">
          <div className="mb-3 flex items-start gap-3">
            <div className="relative flex-shrink-0">
              {account_picture ? (
                <img
                  src={account_picture}
                  alt={primaryName}
                  className="h-10 w-10 rounded-full object-cover"
                  style={{ boxShadow: `0 0 0 2px white, 0 0 0 3.5px ${ringColor}` }}
                />
              ) : (
                <div
                  className={`flex h-10 w-10 items-center justify-center rounded-full text-sm font-bold text-white ${avatarColor(primaryName)}`}
                  style={{ boxShadow: `0 0 0 2px white, 0 0 0 3.5px ${ringColor}` }}
                >
                  {primaryName.charAt(0).toUpperCase()}
                </div>
              )}
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-gray-900 dark:text-white">{primaryName}</p>
              <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                {secondaryHandle && <span className="truncate">@{secondaryHandle}</span>}
                {publishedLabel && <span title={publishedLabel}>{publishedLabel}</span>}
              </div>
            </div>
          </div>

          {content ? (
            <p className="mb-3 whitespace-pre-line text-sm leading-relaxed text-gray-700 dark:text-gray-200">
              {displayContent}
              {isLong && (
                <button
                  onClick={() => setExpanded(!expanded)}
                  className="ml-1 text-xs font-medium text-green-600 dark:text-green-400 hover:text-green-700"
                >
                  {expanded ? 'less' : 'more'}
                </button>
              )}
            </p>
          ) : (
            <p className="mb-3 text-sm italic text-gray-400 dark:text-gray-500">No caption provided</p>
          )}

          {visibleMetrics.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-2">
              {visibleMetrics.map((metric) => (
                <Metric key={metric.key} icon={metric.icon} value={metric.value} label={metric.label} />
              ))}
            </div>
          )}

          {engagementUnavailable && (
            <div className="mb-3 rounded-xl border border-amber-200 dark:border-amber-800/60 bg-amber-50 dark:bg-amber-950/40 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
              Live engagement is unavailable for this post, so this card is showing publish history without platform metrics.
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 dark:border-gray-800 pt-3">
            <div className="text-[11px] text-gray-400 dark:text-gray-500">
              {platform_post_id ? `Platform post ID: ${platform_post_id}` : 'Platform post ID unavailable for this record'}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {canFetchComments && (
                <button
                  onClick={handleFetchComments}
                  className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition-colors ${
                    commentsOpen
                      ? 'border-blue-300 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/50 text-blue-600 dark:text-blue-300'
                      : 'border-gray-200 dark:border-gray-700 bg-offwhite dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:border-blue-200 hover:bg-blue-50/50 hover:text-blue-600'
                  }`}
                >
                  <FaComment className="text-[10px]" />
                  {commentsOpen ? <FaChevronUp className="text-[8px]" /> : <FaChevronDown className="text-[8px]" />}
                  Comments{metrics.comments ? ` (${metrics.comments})` : ''}
                </button>
              )}
              {post_url && (
                <a
                  href={post_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs font-medium text-green-600 dark:text-green-400 hover:text-green-700"
                >
                  <FaExternalLinkAlt className="text-[10px]" />
                  View Post
                </a>
              )}
            </div>
          </div>
        </div>

        {media_url && (
          <div className="order-3 md:w-32 md:flex-shrink-0">
            <div className="relative h-40 overflow-hidden rounded-xl bg-gray-100 dark:bg-gray-800 md:h-32 md:w-32">
              <img
                src={media_url}
                alt="Post media"
                className="h-full w-full object-cover"
                onError={(e) => { e.target.style.display = 'none'; }}
              />
              {isVideo && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/25">
                  <FaPlay className="text-lg text-white drop-shadow" />
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {commentsOpen && (
        <div className="border-t border-gray-100 dark:border-gray-800 bg-gray-50/40 dark:bg-gray-950/50">
          {commentsLoading ? (
            <div className="space-y-3 p-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="flex animate-pulse gap-3">
                  <div className="h-7 w-7 flex-shrink-0 rounded-full bg-gray-200 dark:bg-gray-800" />
                  <div className="flex-1 space-y-1.5">
                    <div className="h-3 w-24 rounded bg-gray-200 dark:bg-gray-800" />
                    <div className="h-3 w-full rounded bg-gray-200 dark:bg-gray-800" />
                  </div>
                </div>
              ))}
            </div>
          ) : comments.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-gray-400 dark:text-gray-500">No comments yet</div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-800">
              {comments.map((comment) => (
                <div key={comment.id} className="px-4 py-3">
                  <div className="flex items-start gap-2.5">
                    {comment.author_avatar ? (
                      <img src={comment.author_avatar} alt="" className="h-7 w-7 flex-shrink-0 rounded-full object-cover" />
                    ) : (
                      <div className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white ${avatarColor(comment.author_name)}`}>
                        {(comment.author_name || '?').charAt(0).toUpperCase()}
                      </div>
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="mb-0.5 flex items-center gap-2">
                        <span className="text-xs font-semibold text-gray-800 dark:text-gray-100">{comment.author_name}</span>
                        <span className="text-[10px] text-gray-400 dark:text-gray-500">{formatRelativeDate(comment.timestamp)}</span>
                        {comment.likes > 0 && (
                          <span className="flex items-center gap-0.5 text-[10px] text-gray-400 dark:text-gray-500">
                            <FaHeart className="text-rose-400" /> {comment.likes}
                          </span>
                        )}
                      </div>
                      <p className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300">{comment.content}</p>

                      {canReply && comment.can_reply && (
                        <button
                          onClick={() => {
                            setReplyingTo(replyingTo === comment.id ? null : comment.id);
                            setReplyText('');
                          }}
                          className="mt-1 flex items-center gap-1 text-[11px] font-medium text-indigo-500 hover:text-indigo-700"
                        >
                          <FaReply className="text-[9px]" />
                          Reply
                        </button>
                      )}

                      {replyingTo === comment.id && (
                        <div className="mt-2">
                          <textarea
                            value={replyText}
                            onChange={(e) => setReplyText(e.target.value)}
                            onKeyDown={(e) => {
                              if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') handleReplySubmit(comment);
                            }}
                            placeholder={`Reply to ${comment.author_name}… (⌘↵)`}
                            rows={2}
                            className="w-full resize-none rounded-lg border border-gray-200 dark:border-gray-700 bg-offwhite dark:bg-gray-800 text-gray-800 dark:text-gray-100 px-3 py-1.5 text-sm placeholder-gray-400 dark:placeholder-gray-500 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-400"
                          />
                          <div className="mt-1.5 flex justify-end gap-2">
                            <button
                              onClick={() => { setReplyingTo(null); setReplyText(''); }}
                              className="rounded px-2 py-1 text-xs text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={() => handleReplySubmit(comment)}
                              disabled={!replyText.trim() || replySending}
                              className="flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1 text-xs text-white disabled:opacity-50 hover:bg-indigo-700"
                            >
                              {replySending ? (
                                <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                              ) : (
                                <FaReply className="text-[9px]" />
                              )}
                              Reply
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default PostCard;
