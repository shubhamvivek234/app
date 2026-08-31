import React from 'react';
import {
  FaFacebook,
  FaInstagram,
  FaLinkedin,
  FaPinterest,
  FaRegClock,
  FaRegStickyNote,
  FaTiktok,
  FaYoutube,
} from 'react-icons/fa';
import { SiBluesky, SiThreads, SiX } from 'react-icons/si';

import { cn } from '@/lib/utils';

import {
  accountAvatarTone,
  formatPostLabel,
  formatPostPreview,
  formatScheduledTime,
  getPostScheduledTimeZone,
  getAccountInitials,
  getAccountLabel,
  getPostMediaMeta,
  getPostPlatforms,
  getPostPrimaryThumbnail,
  statusBadgeClasses,
} from './calendarHelpers';

const PLATFORM_META = {
  facebook: { icon: FaFacebook, color: 'text-blue-600', label: 'Facebook' },
  twitter: { icon: SiX, color: 'text-slate-900', label: 'X' },
  linkedin: { icon: FaLinkedin, color: 'text-blue-700', label: 'LinkedIn' },
  instagram: { icon: FaInstagram, color: 'text-pink-500', label: 'Instagram' },
  pinterest: { icon: FaPinterest, color: 'text-red-600', label: 'Pinterest' },
  youtube: { icon: FaYoutube, color: 'text-red-500', label: 'YouTube' },
  tiktok: { icon: FaTiktok, color: 'text-slate-900', label: 'TikTok' },
  bluesky: { icon: SiBluesky, color: 'text-sky-500', label: 'Bluesky' },
  threads: { icon: SiThreads, color: 'text-slate-900', label: 'Threads' },
};

const AccountAvatar = ({ account, size = 'sm' }) => {
  const sizeClass = size === 'xs' ? 'h-5 w-5 text-[9px]' : 'h-7 w-7 text-[10px]';

  if (account?.picture_url) {
    return (
      <img
        src={account.picture_url}
        alt=""
        className={`${sizeClass} rounded-full border border-white object-cover shadow-sm`}
      />
    );
  }

  const tone = accountAvatarTone[(account?.id || account?.account_id || '').length % accountAvatarTone.length];
  return (
    <div className={`${sizeClass} ${tone} flex items-center justify-center rounded-full border border-white font-bold shadow-sm`}>
      {getAccountInitials(account)}
    </div>
  );
};

const PlatformBadges = ({ platforms = [], compact = true }) => {
  const visiblePlatforms = compact ? platforms.slice(0, 1) : platforms.slice(0, 3);
  const extraPlatforms = Math.max(platforms.length - visiblePlatforms.length, 0);

  return (
    <div className="flex shrink-0 items-center gap-1">
      {visiblePlatforms.map((platform) => {
        const meta = PLATFORM_META[platform];
        const Icon = meta?.icon;
        if (!Icon) return null;

        return (
          <span
            key={platform}
            className="flex h-5 w-5 items-center justify-center rounded-full border border-slate-200 bg-white text-[10px] shadow-sm"
            title={meta.label}
          >
            <Icon className={meta.color} />
          </span>
        );
      })}
      {extraPlatforms > 0 ? (
        <span className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-slate-100 px-1 text-[9px] font-bold text-slate-600">
          +{extraPlatforms}
        </span>
      ) : null}
    </div>
  );
};

const CalendarPostChip = ({
  post,
  accounts = [],
  compact = true,
  expandedVariant = 'week',
  today = false,
  noteCount = 0,
  onClick,
}) => {
  const isAgenda = !compact && expandedVariant === 'agenda';
  const visibleAccounts = accounts.slice(0, compact ? 2 : 3);
  const extraAccounts = Math.max(accounts.length - visibleAccounts.length, 0);
  const status = String(post?.status || 'scheduled').toLowerCase();
  const statusClass = statusBadgeClasses[status] || statusBadgeClasses.scheduled;
  const label = formatPostLabel(post);
  const preview = formatPostPreview(post, compact ? 84 : 160);
  const scheduledTimeZone = getPostScheduledTimeZone(post);
  const timeValue = formatScheduledTime(post?.scheduled_time, scheduledTimeZone);
  const platforms = getPostPlatforms(post);
  const primaryAccountLabel = accounts.length > 0 ? getAccountLabel(accounts[0]) : 'No account info';
  const media = getPostMediaMeta(post);
  const thumbnail = compact ? null : getPostPrimaryThumbnail(post);

  const containerClass = compact
    ? 'rounded-2xl border border-slate-200/90 bg-white p-2 shadow-[0_10px_20px_-16px_rgba(15,23,42,0.35)] dark:border-slate-800 dark:bg-slate-900 dark:shadow-none'
    : isAgenda
      ? 'rounded-[24px] border border-slate-200 bg-white px-4 py-3.5 shadow-[0_22px_36px_-30px_rgba(15,23,42,0.34)] dark:border-slate-800 dark:bg-slate-900 dark:shadow-none'
      : 'rounded-2xl border border-slate-200 bg-white p-3 shadow-[0_20px_35px_-28px_rgba(15,23,42,0.35)] dark:border-slate-800 dark:bg-slate-900 dark:shadow-none';

  const todayAccent = today ? 'ring-1 ring-emerald-300/80 dark:ring-emerald-700/80' : '';

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full text-left transition-all duration-200 hover:-translate-y-[1px] hover:border-slate-300 dark:hover:border-slate-700 active:translate-y-0 active:scale-[0.995]',
        containerClass,
        todayAccent,
      )}
      title={label}
      data-testid={`post-${post.id}`}
    >
      <div className={cn('flex items-start gap-3', compact ? 'flex-col' : 'flex-row')}>
        {!compact && thumbnail ? (
          <div className={cn(
            'shrink-0 overflow-hidden border border-slate-200 bg-slate-100 dark:border-slate-800 dark:bg-slate-800',
            isAgenda ? 'h-14 w-14 rounded-2xl' : 'h-16 w-16 rounded-xl',
          )}>
            <img src={thumbnail} alt="" className="h-full w-full object-cover" />
          </div>
        ) : null}

        <div className={cn('min-w-0 flex-1', isAgenda ? 'space-y-2.5' : 'space-y-2')}>
          <div className={cn('flex justify-between gap-2', isAgenda ? 'items-center' : 'items-start')}>
            <div className="flex min-w-0 items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
              <FaRegClock className="shrink-0 text-slate-400 dark:text-slate-500" />
              <span className="truncate">{timeValue}</span>
            </div>
            <span className={cn('inline-flex shrink-0 rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide', statusClass)}>
              {status}
            </span>
          </div>

          <div className={cn('flex gap-2', isAgenda ? 'flex-wrap items-center justify-start' : 'items-center justify-between')}>
            <PlatformBadges platforms={platforms} compact={compact} />
            <div className="flex items-center gap-2">
              <div className="flex items-center -space-x-1.5">
                {visibleAccounts.map((account) => (
                  <AccountAvatar key={account.account_id || account.id} account={account} size="xs" />
                ))}
              </div>
              {extraAccounts > 0 ? (
                <div className="flex h-5 min-w-[20px] items-center justify-center rounded-full border border-white dark:border-slate-800 bg-slate-100 dark:bg-slate-800 px-1 text-[9px] font-bold text-slate-600 dark:text-slate-300 shadow-sm">
                  +{extraAccounts}
                </div>
              ) : null}
            </div>
          </div>

          <div className={cn('space-y-1', isAgenda ? 'text-left' : '')}>
            <span className={cn('block min-w-0 font-semibold text-slate-900 dark:text-slate-100', isAgenda ? 'text-[13px] leading-5' : 'text-[12px] leading-4')}>
              {compact ? label : isAgenda ? label : preview}
            </span>
            {isAgenda && preview !== label ? (
              <span className="block min-w-0 text-[12px] leading-5 text-slate-600 dark:text-slate-400">
                {preview}
              </span>
            ) : null}
            {!compact ? (
              <span className={cn('block min-w-0 leading-5 text-slate-500 dark:text-slate-400', isAgenda ? 'text-[11px]' : 'text-[11px]')}>
                {primaryAccountLabel}
                {extraAccounts > 0 ? ` +${extraAccounts} account${extraAccounts > 1 ? 's' : ''}` : ''}
              </span>
            ) : null}
          </div>

          <div className={cn('flex flex-wrap items-center text-[10px] font-medium text-slate-500 dark:text-slate-400', isAgenda ? 'gap-2.5' : 'gap-2')}>
            <span className="inline-flex items-center rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5">
              {media.label}
            </span>
            {noteCount > 0 ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 dark:bg-emerald-950/40 px-2 py-0.5 text-emerald-700 dark:text-emerald-300">
                <FaRegStickyNote className="text-[9px]" />
                {noteCount} note{noteCount > 1 ? 's' : ''}
              </span>
            ) : null}
          </div>
        </div>
      </div>
    </button>
  );
};

export default CalendarPostChip;
