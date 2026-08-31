import { format, formatDistance } from 'date-fns';
import {
  formatScheduledCompactDateTime,
  getPostScheduledTimeZone,
} from '@/lib/scheduledTime';

export { getPostScheduledTimeZone };

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

export const formatAbsoluteDate = (value, timeZone = null) => {
  if (!value) return 'Unknown time';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Unknown time';
  if (timeZone) {
    return formatScheduledCompactDateTime(parsed, timeZone, { includeTimeZone: true });
  }
  return format(parsed, 'MMM d, h:mm a');
};

export const formatRelativeDate = (value, now = Date.now()) => {
  if (!value) return 'Unknown';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Unknown';
  return formatDistance(parsed, now, { addSuffix: true });
};

export const countdownLabel = (value, now = Date.now()) => {
  if (!value) return 'No schedule';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'No schedule';
  if (parsed.getTime() <= now) return 'Due now';
  return formatDistance(parsed, now, { addSuffix: true });
};

export const severityPillClass = (severity) => {
  switch (severity) {
    case 'critical':
      return 'bg-red-100 text-red-700 border-red-200 dark:bg-red-950/60 dark:text-red-300 dark:border-red-900/60';
    case 'high':
      return 'bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-900/60';
    case 'medium':
      return 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-900/60';
    default:
      return 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700';
  }
};

export const healthPillClass = (state) => {
  switch (state) {
    case 'restricted':
      return 'bg-red-100 text-red-700 border-red-200 dark:bg-red-950/60 dark:text-red-300 dark:border-red-900/60';
    case 'reconnect_required':
      return 'bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-900/60';
    case 'expiring':
      return 'bg-sky-100 text-sky-700 border-sky-200 dark:bg-sky-950/60 dark:text-sky-300 dark:border-sky-900/60';
    default:
      return 'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-900/60';
  }
};

export const platformPillClass = (platform) => {
  switch (platform) {
    case 'instagram':
      return 'bg-pink-100 text-pink-700 border-pink-200 dark:bg-pink-950/50 dark:text-pink-300 dark:border-pink-900/60';
    case 'youtube':
      return 'bg-red-100 text-red-700 border-red-200 dark:bg-red-950/50 dark:text-red-300 dark:border-red-900/60';
    case 'tiktok':
      return 'bg-slate-900 text-white border-slate-900 dark:bg-slate-800 dark:text-slate-100 dark:border-slate-700';
    case 'linkedin':
      return 'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-900/60';
    case 'twitter':
      return 'bg-slate-100 text-slate-800 border-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:border-slate-700';
    case 'facebook':
      return 'bg-indigo-100 text-indigo-700 border-indigo-200 dark:bg-indigo-950/50 dark:text-indigo-300 dark:border-indigo-900/60';
    default:
      return 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700';
  }
};
