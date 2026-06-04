import { format } from 'date-fns';

export const NOTE_COLORS = ['green', 'blue', 'yellow', 'red'];

export const noteColorClasses = {
  green: {
    chip: 'bg-emerald-100 text-emerald-700',
    form: 'bg-emerald-50 text-emerald-800',
    dot: 'bg-emerald-400',
    border: 'border-emerald-200',
  },
  blue: {
    chip: 'bg-sky-100 text-sky-700',
    form: 'bg-sky-50 text-sky-800',
    dot: 'bg-sky-400',
    border: 'border-sky-200',
  },
  yellow: {
    chip: 'bg-amber-100 text-amber-700',
    form: 'bg-amber-50 text-amber-800',
    dot: 'bg-amber-400',
    border: 'border-amber-200',
  },
  red: {
    chip: 'bg-rose-100 text-rose-700',
    form: 'bg-rose-50 text-rose-800',
    dot: 'bg-rose-400',
    border: 'border-rose-200',
  },
};

export const statusBadgeClasses = {
  draft: 'bg-slate-100 text-slate-600',
  scheduled: 'bg-sky-100 text-sky-700',
  queued: 'bg-amber-100 text-amber-700',
  processing: 'bg-violet-100 text-violet-700',
  published: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-rose-100 text-rose-700',
  partial: 'bg-orange-100 text-orange-700',
  cancelled: 'bg-slate-100 text-slate-600',
};

export const accountAvatarTone = [
  'bg-sky-100 text-sky-700',
  'bg-emerald-100 text-emerald-700',
  'bg-amber-100 text-amber-700',
  'bg-fuchsia-100 text-fuchsia-700',
];

export const PLATFORM_LABELS = {
  facebook: 'Facebook',
  twitter: 'X',
  linkedin: 'LinkedIn',
  instagram: 'Instagram',
  pinterest: 'Pinterest',
  youtube: 'YouTube',
  tiktok: 'TikTok',
  bluesky: 'Bluesky',
  threads: 'Threads',
};

export const getAccountInitials = (account) => {
  const label = account?.platform_username || account?.display_name || account?.platform_user_id || account?.platform || '?';
  return String(label).slice(0, 2).toUpperCase();
};

export const getAccountLabel = (account) =>
  account?.display_name
  || account?.username
  || account?.handle
  || account?.platform_username
  || account?.platform_user_id
  || account?.platform
  || 'Unknown account';

export const formatPostLabel = (post) => {
  const raw = post?.title || post?.content || 'Scheduled post';
  return String(raw).replace(/\s+/g, ' ').trim() || 'Scheduled post';
};

export const formatPostPreview = (post, maxLength = 120) => {
  const raw = post?.content || post?.title || 'No caption';
  const normalized = String(raw).replace(/\s+/g, ' ').trim() || 'No caption';
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength).trim()}…` : normalized;
};

export const getPostPlatforms = (post) => {
  const directPlatforms = Array.isArray(post?.platforms) ? post.platforms : [];
  const targetPlatforms = Array.isArray(post?.publish_targets)
    ? post.publish_targets.map((target) => target?.platform).filter(Boolean)
    : [];
  const singlePlatform = post?.platform ? [post.platform] : [];

  return [...new Set([...directPlatforms, ...targetPlatforms, ...singlePlatform].map((platform) => String(platform).toLowerCase()))];
};

export const getPostAccountIds = (post) => {
  if (Array.isArray(post?.account_ids) && post.account_ids.length > 0) return post.account_ids;
  if (Array.isArray(post?.social_account_ids) && post.social_account_ids.length > 0) return post.social_account_ids;
  if (Array.isArray(post?.platform_account_ids) && post.platform_account_ids.length > 0) return post.platform_account_ids;
  if (post?.social_account_id) return [post.social_account_id];
  if (Array.isArray(post?.publish_targets) && post.publish_targets.length > 0) {
    return post.publish_targets.map((target) => target?.account_id).filter(Boolean);
  }
  return [];
};

export const getPostPrimaryThumbnail = (post) => (
  post?.thumbnail_urls?.[0]
  || post?.published_card_thumbnail_url
  || post?.media_urls?.[0]
  || null
);

export const getPostMediaMeta = (post) => {
  const normalizedType = String(post?.post_type || '').toLowerCase();
  const mediaCount = Math.max(
    Array.isArray(post?.media_ids) ? post.media_ids.length : 0,
    Array.isArray(post?.media_urls) ? post.media_urls.length : 0,
    Array.isArray(post?.thumbnail_urls) ? post.thumbnail_urls.length : 0,
    0,
  );

  if (['mixed', 'carousel', 'album'].includes(normalizedType)) {
    return {
      kind: 'mixed',
      label: mediaCount > 1 ? `${mediaCount} assets` : 'Mixed media',
    };
  }

  if (normalizedType.includes('video') || normalizedType === 'reel' || normalizedType === 'story') {
    return {
      kind: 'video',
      label: mediaCount > 1 ? `${mediaCount} videos` : 'Video',
    };
  }

  if (normalizedType.includes('image') || normalizedType.includes('photo')) {
    return {
      kind: 'image',
      label: mediaCount > 1 ? `${mediaCount} images` : 'Image',
    };
  }

  if (mediaCount > 1) {
    return {
      kind: 'mixed',
      label: `${mediaCount} assets`,
    };
  }

  if (mediaCount === 1) {
    return {
      kind: 'image',
      label: 'Media',
    };
  }

  return {
    kind: 'text',
    label: 'Text',
  };
};

export const formatScheduledTime = (value) => {
  if (!value) return 'No time';
  return format(new Date(value), 'h:mm a');
};

export const formatScheduledDateTime = (value) => {
  if (!value) return 'No scheduled time';
  return format(new Date(value), 'MMMM d, yyyy h:mm a');
};

export const getDaySummaryLabel = (postCount, noteCount) => {
  const segments = [];
  if (postCount > 0) segments.push(`${postCount} post${postCount === 1 ? '' : 's'}`);
  if (noteCount > 0) segments.push(`${noteCount} note${noteCount === 1 ? '' : 's'}`);
  return segments.join(' · ');
};
