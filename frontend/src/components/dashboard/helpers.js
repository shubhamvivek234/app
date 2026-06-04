import { format, formatDistanceToNow } from 'date-fns';

export const PLATFORM_LABELS = {
  instagram: 'Instagram',
  facebook: 'Facebook',
  youtube: 'YouTube',
  twitter: 'X',
  linkedin: 'LinkedIn',
  tiktok: 'TikTok',
  threads: 'Threads',
  bluesky: 'Bluesky',
  pinterest: 'Pinterest',
  mastodon: 'Mastodon',
  discord: 'Discord',
  snapchat: 'Snapchat',
};

const numberFormatter = new Intl.NumberFormat('en', {
  notation: 'compact',
  maximumFractionDigits: 1,
});

export const platformLabel = (platform) => PLATFORM_LABELS[platform] || (platform ? platform[0].toUpperCase() + platform.slice(1) : 'Platform');

export const compactNumber = (value) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 'Unavailable';
  return numberFormatter.format(numeric);
};

export const primaryPostTitle = (post) => {
  const title = post?.title?.trim();
  if (title) return title;
  const content = post?.content?.trim();
  if (!content) return 'Untitled post';
  return content.length > 84 ? `${content.slice(0, 84).trim()}…` : content;
};

export const secondaryPostPreview = (post) => {
  const content = post?.content?.trim() || '';
  if (!content) return 'No caption added.';
  return content.length > 140 ? `${content.slice(0, 140).trim()}…` : content;
};

export const primaryThumbnail = (post) => (
  post?.thumbnail_urls?.[0]
  || post?.published_card_thumbnail_url
  || null
);

export const formatAbsoluteDate = (value) => {
  if (!value) return 'Unknown time';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Unknown time';
  return format(parsed, 'MMM d, h:mm a');
};

export const formatRelativeDate = (value) => {
  if (!value) return 'Unknown';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Unknown';
  return formatDistanceToNow(parsed, { addSuffix: true });
};

export const countdownLabel = (value) => {
  if (!value) return 'No schedule';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'No schedule';
  const now = Date.now();
  if (parsed.getTime() <= now) return 'Due now';
  return formatDistanceToNow(parsed, { addSuffix: true });
};

export const severityPillClass = (severity) => {
  switch (severity) {
    case 'critical':
      return 'bg-red-100 text-red-700 border-red-200';
    case 'high':
      return 'bg-amber-100 text-amber-800 border-amber-200';
    case 'medium':
      return 'bg-blue-100 text-blue-700 border-blue-200';
    default:
      return 'bg-slate-100 text-slate-700 border-slate-200';
  }
};

export const healthPillClass = (state) => {
  switch (state) {
    case 'restricted':
      return 'bg-red-100 text-red-700 border-red-200';
    case 'reconnect_required':
      return 'bg-amber-100 text-amber-800 border-amber-200';
    case 'expiring':
      return 'bg-sky-100 text-sky-700 border-sky-200';
    default:
      return 'bg-emerald-100 text-emerald-700 border-emerald-200';
  }
};

export const platformPillClass = (platform) => {
  switch (platform) {
    case 'instagram':
      return 'bg-pink-100 text-pink-700 border-pink-200';
    case 'youtube':
      return 'bg-red-100 text-red-700 border-red-200';
    case 'tiktok':
      return 'bg-slate-900 text-white border-slate-900';
    case 'linkedin':
      return 'bg-blue-100 text-blue-800 border-blue-200';
    case 'twitter':
      return 'bg-slate-100 text-slate-800 border-slate-200';
    case 'facebook':
      return 'bg-indigo-100 text-indigo-700 border-indigo-200';
    default:
      return 'bg-slate-100 text-slate-700 border-slate-200';
  }
};
