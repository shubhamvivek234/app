import React, { useState } from 'react';
import {
  FaTwitter, FaInstagram, FaLinkedin, FaFacebook,
  FaTiktok, FaYoutube, FaPinterest, FaHeart, FaComment,
  FaShare, FaEye, FaBookmark, FaExternalLinkAlt, FaPlay,
  FaReply, FaChevronDown, FaChevronUp,
} from 'react-icons/fa';
import { SiBluesky, SiThreads } from 'react-icons/si';

// ── Platform metadata ─────────────────────────────────────────────────────────
const PLATFORM_META = {
  facebook:  { icon: FaFacebook,  color: 'text-blue-600',  ring: '#1877F2', label: 'Facebook' },
  twitter:   { icon: FaTwitter,   color: 'text-sky-500',   ring: '#1DA1F2', label: 'X (Twitter)' },
  linkedin:  { icon: FaLinkedin,  color: 'text-blue-700',  ring: '#0A66C2', label: 'LinkedIn' },
  instagram: { icon: FaInstagram, color: 'text-pink-500',  ring: '#E1306C', label: 'Instagram' },
  pinterest: { icon: FaPinterest, color: 'text-red-600',   ring: '#E60023', label: 'Pinterest' },
  youtube:   { icon: FaYoutube,   color: 'text-red-500',   ring: '#FF0000', label: 'YouTube' },
  tiktok:    { icon: FaTiktok,    color: 'text-gray-900',  ring: '#010101', label: 'TikTok' },
  bluesky:   { icon: SiBluesky,   color: 'text-blue-500',  ring: '#0085FF', label: 'Bluesky' },
  threads:   { icon: SiThreads,   color: 'text-gray-900',  ring: '#101010', label: 'Threads' },
};

const COMMENT_PLATFORMS = new Set(['instagram', 'facebook', 'youtube', 'threads', 'reddit', 'bluesky']);
const REPLY_PLATFORMS = new Set(['instagram', 'facebook', 'threads', 'reddit', 'bluesky']);

const AVATAR_COLORS = [
  'bg-blue-500', 'bg-green-500', 'bg-yellow-500', 'bg-red-500',
  'bg-purple-500', 'bg-pink-500', 'bg-indigo-500', 'bg-teal-500',
];
const avatarColor = (name = '') =>
  AVATAR_COLORS[(name.charCodeAt(0) || 0) % AVATAR_COLORS.length];

// ── Metric pill ───────────────────────────────────────────────────────────────
const Metric = ({ icon: Icon, value, label }) => {
  if (value === undefined || value === null) return null;
  return (
    <span className="flex items-center gap-1 text-xs text-gray-500">
      <Icon className="text-[11px]" />
      <span className="font-medium text-gray-700">{Number(value).toLocaleString()}</span>
      {label && <span className="hidden sm:inline">{label}</span>}
    </span>
  );
};

// ── Format time helper ────────────────────────────────────────────────────────
const formatTime = (isoString) => {
  if (!isoString) return '';
  try {
    return new Date(isoString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
};

const formatRelative = (isoString) => {
  if (!isoString) return '';
  try {
    return new Date(isoString).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  } catch {
    return '';
  }
};

// ── PostCard ──────────────────────────────────────────────────────────────────
const PostCard = ({ post, onAddComment, onFetchComments, onReplyToComment }) => {
  const [expanded, setExpanded] = useState(false);
  const [commentOpen, setCommentOpen] = useState(false);
  const [commentText, setCommentText] = useState('');
  const [commentLoading, setCommentLoading] = useState(false);
  const [commentSuccess, setCommentSuccess] = useState(false);

  // Comments state
  const [commentsOpen, setCommentsOpen] = useState(false);
  const [comments, setComments] = useState([]);
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [replyingTo, setReplyingTo] = useState(null);
  const [replyText, setReplyText] = useState('');
  const [replySending, setReplySending] = useState(false);

  const {
    platform,
    account_username,
    account_picture,
    content,
    media_url,
    media_type,
    post_url,
    metrics = {},
    published_at,
  } = post;

  const meta = PLATFORM_META[platform] || {};
  const PlatformIcon = meta.icon;
  const ringColor = meta.ring || '#3B82F6';

  const CAPTION_LIMIT = 160;
  const isLong = content && content.length > CAPTION_LIMIT;
  const displayContent = isLong && !expanded ? content.slice(0, CAPTION_LIMIT) + '…' : content;

  const isVideo = media_type === 'VIDEO' || media_type === 'REELS';
  const canFetchComments = COMMENT_PLATFORMS.has(platform) && !!onFetchComments;
  const canReply = REPLY_PLATFORMS.has(platform) && !!onReplyToComment;

  const handleCommentSubmit = async () => {
    if (!commentText.trim() || commentLoading || !onAddComment) return;
    setCommentLoading(true);
    try {
      await onAddComment(post, commentText.trim());
      setCommentText('');
      setCommentOpen(false);
      setCommentSuccess(true);
      setTimeout(() => setCommentSuccess(false), 3000);
    } finally {
      setCommentLoading(false);
    }
  };

  const handleCommentKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      handleCommentSubmit();
    }
  };

  const handleFetchComments = async () => {
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
      // Refresh comments
      if (onFetchComments) {
        const result = await onFetchComments(post);
        setComments(result?.comments || []);
      }
    } finally {
      setReplySending(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow overflow-hidden">
      <div className="flex gap-4 p-4">

        {/* Left: time column */}
        <div className="flex-shrink-0 w-16 text-right pt-0.5">
          <p className="text-xs text-gray-400 font-medium">{formatTime(published_at)}</p>
        </div>

        {/* Center: content */}
        <div className="flex-1 min-w-0">

          {/* Account header */}
          <div className="flex items-center gap-2 mb-2">
            <div className="relative flex-shrink-0">
              {account_picture ? (
                <img
                  src={account_picture}
                  alt={account_username}
                  className="w-9 h-9 rounded-full object-cover"
                  style={{ boxShadow: `0 0 0 2px white, 0 0 0 3.5px ${ringColor}` }}
                />
              ) : (
                <div
                  className={`w-9 h-9 rounded-full ${avatarColor(account_username)} flex items-center justify-center text-white text-sm font-bold`}
                  style={{ boxShadow: `0 0 0 2px white, 0 0 0 3.5px ${ringColor}` }}
                >
                  {(account_username || platform || '?').charAt(0).toUpperCase()}
                </div>
              )}
              {PlatformIcon && (
                <div className="absolute -bottom-0.5 -right-0.5 w-4 h-4 rounded-full bg-white border border-gray-100 flex items-center justify-center shadow-sm">
                  <PlatformIcon className={`text-[9px] ${meta.color}`} />
                </div>
              )}
            </div>

            <div className="min-w-0">
              <p className="text-sm font-semibold text-gray-900 truncate max-w-[160px]">
                {account_username || platform}
              </p>
              <p className="text-[11px] text-gray-400">{meta.label || platform}</p>
            </div>
          </div>

          {/* Caption */}
          {content && (
            <p className="text-sm text-gray-700 leading-relaxed mb-3 whitespace-pre-line">
              {displayContent}
              {isLong && (
                <button
                  onClick={() => setExpanded(!expanded)}
                  className="ml-1 text-green-600 hover:text-green-700 text-xs font-medium"
                >
                  {expanded ? 'less' : 'more'}
                </button>
              )}
            </p>
          )}

          {/* Metrics row */}
          <div className="flex items-center gap-4 flex-wrap">
            {metrics.likes     !== undefined && <Metric icon={FaHeart}    value={metrics.likes}    label="Likes" />}
            {metrics.comments  !== undefined && <Metric icon={FaComment}  value={metrics.comments} label="Comments" />}
            {metrics.shares    !== undefined && <Metric icon={FaShare}    value={metrics.shares}   label="Shares" />}
            {metrics.views     !== undefined && <Metric icon={FaEye}      value={metrics.views}    label="Views" />}
            {metrics.saves     !== undefined && <Metric icon={FaBookmark} value={metrics.saves}    label="Saves" />}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-50">
            <div className="flex items-center gap-3">
              <span className="text-[11px] text-gray-400">
                Published via {meta.label || platform}
              </span>
              {commentSuccess && (
                <span className="text-[11px] text-green-600 font-medium">✓ Comment posted</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {/* View Comments button — only for platforms that support it */}
              {canFetchComments && (
                <button
                  onClick={handleFetchComments}
                  className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border transition-colors ${
                    commentsOpen
                      ? 'border-blue-300 bg-blue-50 text-blue-600'
                      : 'border-gray-200 text-gray-500 hover:text-blue-600 hover:border-blue-200 hover:bg-blue-50/50'
                  }`}
                >
                  <FaComment className="text-[10px]" />
                  {commentsOpen ? <FaChevronUp className="text-[8px]" /> : <FaChevronDown className="text-[8px]" />}
                  Comments{metrics.comments ? ` (${metrics.comments})` : ''}
                </button>
              )}
              {/* Add Comment button */}
              {onAddComment && canReply && (
                <button
                  onClick={() => {
                    setCommentOpen((prev) => !prev);
                    setCommentText('');
                  }}
                  className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border transition-colors ${
                    commentOpen
                      ? 'border-indigo-300 bg-indigo-50 text-indigo-600'
                      : 'border-gray-200 text-gray-500 hover:text-indigo-600 hover:border-indigo-200 hover:bg-indigo-50/50'
                  }`}
                >
                  <FaReply className="text-[10px]" />
                  Comment on Post
                </button>
              )}
              {post_url && (
                <a
                  href={post_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-green-600 hover:text-green-700 font-medium"
                >
                  <FaExternalLinkAlt className="text-[10px]" />
                  View Post
                </a>
              )}
            </div>
          </div>
        </div>

        {/* Right: media thumbnail */}
        {media_url && (
          <div className="flex-shrink-0 self-start">
            <div className="relative w-20 h-20 rounded-lg overflow-hidden bg-gray-100">
              <img
                src={media_url}
                alt="Post media"
                className="w-full h-full object-cover"
                onError={(e) => { e.target.style.display = 'none'; }}
              />
              {isVideo && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/30">
                  <FaPlay className="text-white text-lg drop-shadow" />
                </div>
              )}
            </div>
          </div>
        )}

      </div>

      {/* Inline comment composer */}
      {commentOpen && onAddComment && (
        <div className="border-t border-gray-100 bg-gray-50/60 px-4 py-3">
          <textarea
            value={commentText}
            onChange={(e) => setCommentText(e.target.value)}
            onKeyDown={handleCommentKeyDown}
            placeholder="Write a comment… (⌘↵ to send)"
            rows={3}
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent placeholder-gray-400"
          />
          <div className="flex justify-end gap-2 mt-2">
            <button
              onClick={() => { setCommentOpen(false); setCommentText(''); }}
              className="text-sm text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleCommentSubmit}
              disabled={!commentText.trim() || commentLoading}
              className="flex items-center gap-1.5 text-sm bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-1.5 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {commentLoading ? (
                <>
                  <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                  Posting…
                </>
              ) : (
                'Post Comment'
              )}
            </button>
          </div>
        </div>
      )}

      {/* Comments section */}
      {commentsOpen && (
        <div className="border-t border-gray-100 bg-gray-50/40">
          {commentsLoading ? (
            <div className="p-4 space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="animate-pulse flex gap-3">
                  <div className="w-7 h-7 rounded-full bg-gray-200 flex-shrink-0" />
                  <div className="flex-1 space-y-1.5">
                    <div className="h-3 bg-gray-200 rounded w-24" />
                    <div className="h-3 bg-gray-200 rounded w-full" />
                  </div>
                </div>
              ))}
            </div>
          ) : comments.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-gray-400">
              No comments yet
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {comments.map((comment) => (
                <div key={comment.id} className="px-4 py-3">
                  <div className="flex items-start gap-2.5">
                    {/* Avatar */}
                    {comment.author_avatar ? (
                      <img src={comment.author_avatar} alt="" className="w-7 h-7 rounded-full object-cover flex-shrink-0" />
                    ) : (
                      <div className={`w-7 h-7 rounded-full ${avatarColor(comment.author_name)} flex items-center justify-center text-white text-[10px] font-bold flex-shrink-0`}>
                        {(comment.author_name || '?').charAt(0).toUpperCase()}
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="text-xs font-semibold text-gray-800">{comment.author_name}</span>
                        <span className="text-[10px] text-gray-400">{formatRelative(comment.timestamp)}</span>
                        {comment.likes > 0 && (
                          <span className="flex items-center gap-0.5 text-[10px] text-gray-400">
                            <FaHeart className="text-rose-400" /> {comment.likes}
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-700 whitespace-pre-wrap">{comment.content}</p>

                      {/* Reply button */}
                      {canReply && comment.can_reply && (
                        <button
                          onClick={() => {
                            setReplyingTo(replyingTo === comment.id ? null : comment.id);
                            setReplyText('');
                          }}
                          className="mt-1 text-[11px] text-indigo-500 hover:text-indigo-700 font-medium flex items-center gap-1"
                        >
                          <FaReply className="text-[9px]" />
                          Reply
                        </button>
                      )}

                      {/* Inline reply composer */}
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
                            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-1.5 resize-none bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent placeholder-gray-400"
                          />
                          <div className="flex justify-end gap-2 mt-1.5">
                            <button
                              onClick={() => { setReplyingTo(null); setReplyText(''); }}
                              className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={() => handleReplySubmit(comment)}
                              disabled={!replyText.trim() || replySending}
                              className="flex items-center gap-1 text-xs bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1 rounded-lg disabled:opacity-50"
                            >
                              {replySending ? (
                                <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
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
