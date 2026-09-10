import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import {
  FaYoutube,
  FaInstagram,
  FaFacebook,
  FaTiktok,
  FaLinkedin,
  FaExternalLinkAlt,
  FaRedo,
  FaCheckCircle,
  FaExclamationCircle,
  FaExclamationTriangle,
  FaSpinner,
  FaClock,
  FaTools,
} from 'react-icons/fa';
import { FaXTwitter } from 'react-icons/fa6';
import GoogleBusinessIcon from '@/components/icons/GoogleBusinessIcon';

import { retryFailedPost } from '@/lib/api';
import { parsePlatformError } from '@/lib/publishFailures';

const PLATFORM_ICONS = {
  youtube: <FaYoutube className="text-red-500" />,
  instagram: <FaInstagram className="text-pink-500" />,
  facebook: <FaFacebook className="text-blue-600" />,
  tiktok: <FaTiktok className="text-black dark:text-white" />,
  twitter: <FaXTwitter className="text-black dark:text-white" />,
  x: <FaXTwitter className="text-black dark:text-white" />,
  linkedin: <FaLinkedin className="text-blue-700" />,
  google_business: <GoogleBusinessIcon className="w-4 h-4" />,
  google: <GoogleBusinessIcon className="w-4 h-4" />,
  threads: <span className="font-bold text-xs">@</span>,
};

const STATUS_BADGES = {
  published: {
    label: 'Published',
    icon: FaCheckCircle,
    className: 'bg-emerald-50 text-emerald-700 border-emerald-200/80 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800',
  },
  failed: {
    label: 'Failed',
    icon: FaExclamationCircle,
    className: 'bg-rose-50 text-rose-700 border-rose-200/80 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800',
  },
  permanently_failed: {
    label: 'Failed (Permanent)',
    icon: FaExclamationCircle,
    className: 'bg-rose-100/70 text-rose-800 border-rose-300 dark:bg-rose-950/60 dark:text-rose-300 dark:border-rose-700',
  },
  retrying: {
    label: 'Retrying…',
    icon: FaSpinner,
    className: 'bg-amber-50 text-amber-700 border-amber-200/80 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800 animate-pulse',
  },
  queued: {
    label: 'Queued',
    icon: FaClock,
    className: 'bg-blue-50 text-blue-700 border-blue-200/80 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-800',
  },
  processing: {
    label: 'Publishing…',
    icon: FaSpinner,
    className: 'bg-blue-50 text-blue-700 border-blue-200/80 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-800',
  },
  pending: {
    label: 'Pending',
    icon: FaClock,
    className: 'bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700',
  },
};

const KNOWN_PLATFORMS = [
  'twitter', 'x', 'linkedin', 'instagram', 'facebook', 'youtube',
  'tiktok', 'threads', 'google_business', 'google', 'gbp', 'bluesky', 'pinterest'
];

function isRawInternalId(str) {
  if (!str) return false;
  const s = String(str).toLowerCase().trim();
  if (s.startsWith('usr_') || s.startsWith('acc_') || s.startsWith('user_') || s.includes('usr_c7') || s.includes('account_')) return true;
  if (/^[a-f0-9]{24}$/.test(s)) return true;
  if (/^[a-f0-9-]{32,}$/.test(s)) return true;
  return false;
}

function resolvePlatform(rawKey = '', result = {}, post = {}) {
  const candidates = [
    result.platform,
    result.platform_name,
    result.provider,
    rawKey,
  ].filter(Boolean).map(s => String(s).toLowerCase().trim());

  for (const candidate of candidates) {
    for (const p of KNOWN_PLATFORMS) {
      if (candidate === p || candidate.startsWith(`${p}_`) || candidate.startsWith(`${p}:`) || candidate.startsWith(`${p}-`)) {
        if (p === 'x') return 'twitter';
        if (p === 'gbp' || p === 'google') return 'google_business';
        return p;
      }
    }
  }

  if (Array.isArray(post.platforms) && post.platforms.length === 1) {
    const p = String(post.platforms[0]).toLowerCase();
    return p === 'x' ? 'twitter' : p;
  }
  return 'social';
}

function resolveAccountDisplay(rawKey = '', result = {}, accountMap = {}, platform = 'social', post = {}) {
  // 1. Result fields
  if (result.account_name && !isRawInternalId(result.account_name)) {
    return result.account_name;
  }
  if (result.platform_username && !isRawInternalId(result.platform_username)) {
    return result.platform_username.startsWith('@') || platform !== 'twitter'
      ? result.platform_username
      : `@${result.platform_username}`;
  }

  // 2. Extract account ID
  const accountId = result.account_id || rawKey.split(':')[1] || (rawKey.startsWith(`${platform}_`) ? rawKey.slice(platform.length + 1) : rawKey);

  // 3. Direct accountMap lookup
  const matched = (accountMap && (accountMap[accountId] || accountMap[rawKey])) || null;
  if (matched) {
    const name = matched.platform_username || matched.display_name || matched.name;
    if (name && !isRawInternalId(name)) {
      return name.startsWith('@') || platform !== 'twitter' ? name : `@${name}`;
    }
  }

  // 4. Look into post.publish_targets or post.accounts
  const postTargets = post.publish_targets || post.accounts || [];
  if (Array.isArray(postTargets)) {
    const matchedTarget = postTargets.find(
      (t) => t && (t.account_id === accountId || t.target_key === rawKey || t.id === accountId)
    );
    if (matchedTarget) {
      const name = matchedTarget.platform_username || matchedTarget.display_name || matchedTarget.account_name || matchedTarget.username;
      if (name && !isRawInternalId(name)) {
        return name.startsWith('@') || platform !== 'twitter' ? name : `@${name}`;
      }
    }
  }

  // 5. Look for any connected account matching the same platform in accountMap
  if (accountMap && typeof accountMap === 'object') {
    const samePlatformAccount = Object.values(accountMap).find(
      (a) => a && (a.platform === platform || (platform === 'twitter' && (a.platform === 'x' || a.platform === 'twitter')))
    );
    if (samePlatformAccount) {
      const name = samePlatformAccount.platform_username || samePlatformAccount.display_name || samePlatformAccount.name;
      if (name && !isRawInternalId(name)) {
        return name.startsWith('@') || platform !== 'twitter' ? name : `@${name}`;
      }
    }
  }

  // 6. Clean fallback
  const platformLabel = platform === 'twitter' ? 'Twitter' : platform.charAt(0).toUpperCase() + platform.slice(1).replace('_', ' ');
  return `${platformLabel} Account`;
}

export default function PostDeliveryInspector({ post, accountMap = {}, onRetrySuccess, compact = false }) {
  const navigate = useNavigate();
  const [retryingKeys, setRetryingKeys] = useState({});
  const [retryingAll, setRetryingAll] = useState(false);

  if (!post) return null;

  // Extract platform / account entries with robust humanized mapping
  const platformResults = post.platform_results || {};
  const accountResults = post.account_results || {};

  let entries = [];
  if (Object.keys(accountResults).length > 0) {
    entries = Object.entries(accountResults).map(([key, result]) => {
      const platform = resolvePlatform(key, result, post);
      const accountName = resolveAccountDisplay(key, result, accountMap, platform, post);
      return {
        key,
        platform,
        accountName,
        result: result || {},
      };
    });
  } else if (Object.keys(platformResults).length > 0) {
    entries = Object.entries(platformResults).map(([platformKey, result]) => {
      const platform = resolvePlatform(platformKey, result, post);
      const accountName = resolveAccountDisplay(platformKey, result, accountMap, platform, post);
      return {
        key: platformKey,
        platform,
        accountName,
        result: result || {},
      };
    });
  } else if (Array.isArray(post.platforms)) {
    entries = post.platforms.map((platformKey) => {
      const platform = resolvePlatform(platformKey, {}, post);
      const accountName = resolveAccountDisplay(platformKey, {}, accountMap, platform, post);
      return {
        key: platformKey,
        platform,
        accountName,
        result: { status: post.status || 'pending' },
      };
    });
  }

  const failedEntries = entries.filter((e) => {
    const status = String(e.result?.status || '').toLowerCase();
    const isRetrying = Boolean(retryingKeys[e.key]) || status === 'retrying';
    const isProcessing = status === 'processing';
    return (status === 'failed' || status === 'permanently_failed') && !isRetrying && !isProcessing;
  });

  const hasMedia = Boolean(
    (post?.media_ids && post.media_ids.length > 0) ||
    (post?.media_urls && post.media_urls.length > 0) ||
    (post?.thumbnail_urls && post.thumbnail_urls.length > 0)
  );

  const isMediaExpired = Boolean(
    hasMedia && (
      post?.media_expired ||
      post?.media_cleaned_at ||
      (post?.failed_media_expires_at && new Date(post.failed_media_expires_at) <= new Date())
    )
  );

  const remainingHours = (hasMedia && !isMediaExpired && post?.failed_media_expires_at)
    ? Math.max(0, Math.round((new Date(post.failed_media_expires_at) - new Date()) / (1000 * 60 * 60)))
    : null;

  const handleRetryTarget = async (entryKey, platformName) => {
    setRetryingKeys((prev) => ({ ...prev, [entryKey]: true }));
    try {
      const res = await retryFailedPost(post.id, platformName);
      toast.success(`Queued retry for ${platformName.toUpperCase()}`);
      if (onRetrySuccess) {
        onRetrySuccess(post.id, platformName, res);
      }
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || `Failed to retry ${platformName}`;
      toast.error(msg);
    } finally {
      setRetryingKeys((prev) => ({ ...prev, [entryKey]: false }));
    }
  };

  const handleRetryAll = async () => {
    setRetryingAll(true);
    try {
      const res = await retryFailedPost(post.id);
      toast.success('Queued retry for all failed platforms');
      if (onRetrySuccess) {
        onRetrySuccess(post.id, null, res);
      }
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || 'Failed to retry failed platforms';
      toast.error(msg);
    } finally {
      setRetryingAll(false);
    }
  };

  if (!entries.length) {
    return null;
  }

  return (
    <div className={`text-xs ${compact ? 'space-y-1.5' : 'space-y-2'}`}>
      {/* Header with quick Retry All button if multiple failed */}
      {failedEntries.length > 1 && (
        <div className="flex flex-col sm:flex-row gap-2 sm:items-center justify-between rounded-lg border border-rose-200/80 bg-rose-50/60 p-2.5 dark:border-rose-900/50 dark:bg-rose-950/20">
          <div className="flex items-center gap-1.5 text-rose-800 dark:text-rose-300 text-[11px] min-w-0 flex-wrap">
            <FaExclamationTriangle className="text-rose-600 dark:text-rose-400 text-xs shrink-0" />
            <span className="font-semibold">{failedEntries.length} platforms failed</span>
            {isMediaExpired ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-[9px] font-medium text-slate-500" title="Media expired after 48-hour grace period">
                Expired
              </span>
            ) : remainingHours !== null ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-amber-300 dark:border-amber-800 bg-amber-100/70 dark:bg-amber-950/40 px-1.5 py-0.5 text-[9px] font-medium text-amber-800 dark:text-amber-300" title="Media will be automatically purged 48 hours after failure">
                <FaClock className="text-[8px]" /> {remainingHours}h left
              </span>
            ) : null}
          </div>
          <button
            onClick={handleRetryAll}
            disabled={retryingAll || isMediaExpired}
            title={isMediaExpired ? 'Media expired after 48 hours. Please duplicate or re-upload the post.' : 'Retry publishing to all failed platforms'}
            className={`inline-flex items-center justify-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-medium text-white shadow-2xs transition-colors shrink-0 ${
              isMediaExpired
                ? 'bg-slate-300 dark:bg-slate-700 text-slate-500 cursor-not-allowed'
                : 'bg-rose-600 hover:bg-rose-700 disabled:opacity-50'
            }`}
          >
            {retryingAll ? (
              <>
                <FaSpinner className="animate-spin text-[9px]" /> Retrying…
              </>
            ) : (
              <>
                <FaRedo className="text-[9px]" /> {isMediaExpired ? 'Expired' : 'Retry All'}
              </>
            )}
          </button>
        </div>
      )}

      {/* Target platform delivery list */}
      <div className="divide-y divide-slate-100 rounded-lg border border-slate-200/80 bg-slate-50/40 dark:divide-slate-800/80 dark:border-slate-800 dark:bg-slate-900/40 shadow-2xs overflow-hidden">
        {entries.map(({ key, platform, accountName, result }) => {
          const rawStatus = String(result.status || 'pending').toLowerCase();
          const isRetrying = Boolean(retryingKeys[key]) || rawStatus === 'retrying';
          const isProcessing = rawStatus === 'processing';
          const isPublished = rawStatus === 'published';
          const isFailed = (rawStatus === 'failed' || rawStatus === 'permanently_failed' || (Boolean(result.error) && !isRetrying && !isProcessing)) && !isRetrying && !isProcessing;

          const currentStatusKey = isRetrying ? 'retrying' : (isProcessing ? 'processing' : rawStatus);
          const badge = STATUS_BADGES[currentStatusKey] || STATUS_BADGES.pending;
          const BadgeIcon = badge.icon;
          const diagnostic = isFailed ? parsePlatformError(platform, result) : null;
          const platformLabel = platform === 'twitter' ? 'Twitter' : platform.charAt(0).toUpperCase() + platform.slice(1).replace('_', ' ');

          return (
            <div key={key} className={`${compact ? 'p-2.5' : 'p-3'} transition-colors hover:bg-slate-50/80 dark:hover:bg-slate-800/30`}>
              {/* Line 1: Identity on left, Status badge on right */}
              <div className="flex items-center justify-between gap-2 min-w-0">
                <div className="flex items-center gap-2 min-w-0 flex-1 overflow-hidden">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white dark:bg-slate-800 text-xs text-slate-700 dark:text-slate-300 border border-slate-200/80 dark:border-slate-700 shadow-2xs">
                    {PLATFORM_ICONS[platform] || <span className="capitalize text-[10px] font-bold">{platform[0]}</span>}
                  </div>
                  <div className="min-w-0 flex-1 overflow-hidden">
                    <p className="truncate font-semibold text-slate-800 dark:text-slate-200 text-xs capitalize leading-tight" title={accountName}>
                      {accountName}
                    </p>
                    <p className="truncate text-[10px] text-slate-400 capitalize leading-tight" title={platformLabel}>
                      {platformLabel}
                    </p>
                  </div>
                </div>

                {/* Status Badge */}
                <span
                  className={`shrink-0 inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[10px] font-medium shadow-2xs ${badge.className}`}
                >
                  <BadgeIcon className={`text-[9px] ${currentStatusKey === 'retrying' || currentStatusKey === 'processing' ? 'animate-spin' : ''}`} />
                  {badge.label}
                </span>
              </div>

              {/* Line 2: Actions & Grace Info / Active Retry indicator */}
              {isRetrying ? (
                <div className="mt-2 flex items-center justify-between gap-2 pt-1.5 border-t border-slate-100 dark:border-slate-800/80">
                  <div className="flex items-center gap-1.5 text-[11px] text-amber-600 dark:text-amber-400 font-medium py-0.5">
                    <FaSpinner className="animate-spin text-[10px]" />
                    <span>Publishing retry in progress…</span>
                  </div>
                </div>
              ) : (isFailed || (isPublished && result.post_url)) ? (
                <div className="mt-2 flex items-center justify-between gap-2 pt-1.5 border-t border-slate-100 dark:border-slate-800/80">
                  {/* Left: Grace period or delivery info */}
                  <div className="min-w-0 flex-1 overflow-hidden">
                    {isFailed && !isMediaExpired && remainingHours !== null ? (
                      <span className="inline-flex items-center gap-1 text-[10px] text-amber-600 dark:text-amber-400 font-medium" title="Media retained in Cloudflare R2 for 48 hours">
                        <FaClock className="text-[9px]" /> {remainingHours}h grace left
                      </span>
                    ) : isFailed && isMediaExpired ? (
                      <span className="inline-flex items-center gap-1 text-[10px] text-slate-400 dark:text-slate-500 font-medium" title="Grace period expired. Media removed from R2.">
                        <FaExclamationTriangle className="text-[9px]" /> Media expired
                      </span>
                    ) : isPublished ? (
                      <span className="text-[10px] text-slate-400 dark:text-slate-500 font-normal">
                        Delivered successfully
                      </span>
                    ) : null}
                  </div>

                  {/* Right: Action Button */}
                  <div className="shrink-0 flex items-center gap-1.5">
                    {isPublished && result.post_url && (
                      <a
                        href={result.post_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 py-0.5 text-[10px] font-medium text-slate-700 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 hover:border-indigo-200 shadow-2xs transition-colors"
                      >
                        <FaExternalLinkAlt className="text-[8px]" /> View Post
                      </a>
                    )}

                    {isFailed && (
                      <button
                        onClick={() => handleRetryTarget(key, platform)}
                        disabled={isMediaExpired}
                        title={isMediaExpired ? 'Media expired after 48 hours. Duplicate this post to re-upload.' : `Retry publishing to ${platformLabel}`}
                        className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-medium shadow-2xs transition-colors ${
                          isMediaExpired
                            ? 'bg-slate-100 text-slate-400 border border-slate-200 dark:bg-slate-800 dark:text-slate-600 dark:border-slate-700 cursor-not-allowed'
                            : 'bg-rose-600 hover:bg-rose-700 text-white disabled:opacity-50'
                        }`}
                      >
                        {isMediaExpired ? (
                          <>
                            <FaRedo className="text-[9px] opacity-40" /> Expired
                          </>
                        ) : (
                          <>
                            <FaRedo className="text-[9px]" /> Retry Platform
                          </>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              ) : null}

              {/* Line 3: Granular Error Diagnostic Card (only shown when failed, never while retrying) */}
              {isFailed && diagnostic && (
                <div className="mt-2 rounded-md border border-rose-200/70 bg-rose-50/50 p-2.5 dark:border-rose-900/40 dark:bg-rose-950/20 text-slate-700 dark:text-slate-300">
                  <div className="flex items-start gap-2">
                    <FaExclamationCircle className="mt-0.5 shrink-0 text-rose-500 dark:text-rose-400 text-xs" />
                    <div className="space-y-1 min-w-0 flex-1">
                      <p className="font-semibold text-rose-900 dark:text-rose-200 text-xs leading-snug">
                        {diagnostic.title}
                      </p>
                      <p className="text-[11px] text-slate-600 dark:text-slate-300 leading-relaxed break-words">
                        {diagnostic.message}
                      </p>

                      {diagnostic.action && (
                        <div className="mt-1.5 flex flex-wrap items-center gap-2 pt-1 border-t border-rose-200/60 dark:border-rose-900/30">
                          <span className="text-[10px] font-medium text-rose-700 dark:text-rose-300">
                            Action: {diagnostic.action}
                          </span>

                          {diagnostic.actionType === 'external_link' && diagnostic.actionUrl && (
                            <a
                              href={diagnostic.actionUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-[10px] font-semibold text-blue-600 hover:underline dark:text-blue-400"
                            >
                              <FaExternalLinkAlt className="text-[8px]" /> {diagnostic.actionLabel || 'Open Portal'}
                            </a>
                          )}

                          {diagnostic.actionType === 'reconnect' && (
                            <button
                              onClick={() => navigate('/connected-accounts')}
                              className="inline-flex items-center gap-1 text-[10px] font-semibold text-blue-600 hover:underline dark:text-blue-400"
                            >
                              <FaTools className="text-[9px]" /> Open Connected Accounts
                            </button>
                          )}

                          {(diagnostic.actionType === 'edit_post' || diagnostic.actionType === 'crop_media') && (
                            <button
                              onClick={() => navigate(`/create-post?duplicateFrom=${post.id}`)}
                              className="inline-flex items-center gap-1 text-[10px] font-semibold text-indigo-600 hover:underline dark:text-indigo-400"
                            >
                              Edit in Composer →
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
