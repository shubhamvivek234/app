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
import { SiGoogle } from 'react-icons/si';

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
  google_business: <SiGoogle className="text-blue-500" />,
  google: <SiGoogle className="text-blue-500" />,
  threads: <span className="font-bold text-xs">@</span>,
};

const STATUS_BADGES = {
  published: {
    label: 'Published',
    icon: FaCheckCircle,
    className: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800',
  },
  failed: {
    label: 'Failed',
    icon: FaExclamationCircle,
    className: 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-400 dark:border-red-800',
  },
  permanently_failed: {
    label: 'Failed (Permanent)',
    icon: FaExclamationCircle,
    className: 'bg-red-100 text-red-800 border-red-300 dark:bg-red-950/60 dark:text-red-300 dark:border-red-700',
  },
  retrying: {
    label: 'Retrying…',
    icon: FaSpinner,
    className: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800 animate-pulse',
  },
  queued: {
    label: 'Queued',
    icon: FaClock,
    className: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800',
  },
  processing: {
    label: 'Publishing…',
    icon: FaSpinner,
    className: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800',
  },
  pending: {
    label: 'Pending',
    icon: FaClock,
    className: 'bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700',
  },
};

export default function PostDeliveryInspector({ post, onRetrySuccess, compact = false }) {
  const navigate = useNavigate();
  const [retryingKeys, setRetryingKeys] = useState({});
  const [retryingAll, setRetryingAll] = useState(false);

  if (!post) return null;

  // Extract platform / account entries
  const platformResults = post.platform_results || {};
  const accountResults = post.account_results || {};

  let entries = [];
  if (Object.keys(accountResults).length > 0) {
    entries = Object.entries(accountResults).map(([key, result]) => {
      const platform = (result.platform || key.split(':')[0] || 'social').toLowerCase();
      const accountName = result.account_name || result.account_id || key;
      return {
        key,
        platform,
        accountName,
        result: result || {},
      };
    });
  } else if (Object.keys(platformResults).length > 0) {
    entries = Object.entries(platformResults).map(([platform, result]) => {
      return {
        key: platform,
        platform: platform.toLowerCase(),
        accountName: platform.charAt(0).toUpperCase() + platform.slice(1),
        result: result || {},
      };
    });
  } else if (Array.isArray(post.platforms)) {
    entries = post.platforms.map((platform) => ({
      key: platform,
      platform: platform.toLowerCase(),
      accountName: platform.charAt(0).toUpperCase() + platform.slice(1),
      result: { status: post.status || 'pending' },
    }));
  }

  const failedEntries = entries.filter((e) => {
    const status = String(e.result?.status || '').toLowerCase();
    return status === 'failed' || status === 'permanently_failed' || Boolean(e.result?.error);
  });

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
    <div className="space-y-2 text-xs">
      {/* Header with quick Retry All button if multiple failed */}
      {failedEntries.length > 1 && (
        <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50/70 p-2.5 dark:border-red-900/50 dark:bg-red-950/20">
          <div className="flex items-center gap-2 text-red-800 dark:text-red-300">
            <FaExclamationTriangle className="text-red-600 dark:text-red-400" />
            <span className="font-semibold">{failedEntries.length} platforms failed publishing</span>
          </div>
          <button
            onClick={handleRetryAll}
            disabled={retryingAll}
            className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-1 font-semibold text-white shadow-xs hover:bg-red-700 disabled:opacity-50 transition-colors"
          >
            {retryingAll ? (
              <>
                <FaSpinner className="animate-spin text-[10px]" /> Retrying…
              </>
            ) : (
              <>
                <FaRedo className="text-[10px]" /> Retry All Failed
              </>
            )}
          </button>
        </div>
      )}

      {/* Target platform delivery list */}
      <div className="divide-y divide-slate-100 rounded-lg border border-slate-200/80 bg-white dark:divide-slate-800 dark:border-slate-800 dark:bg-slate-900/60 shadow-xs overflow-hidden">
        {entries.map(({ key, platform, accountName, result }) => {
          const rawStatus = String(result.status || 'pending').toLowerCase();
          const badge = STATUS_BADGES[rawStatus] || STATUS_BADGES.pending;
          const BadgeIcon = badge.icon;
          const isFailed = rawStatus === 'failed' || rawStatus === 'permanently_failed' || Boolean(result.error);
          const isPublished = rawStatus === 'published';
          const diagnostic = isFailed ? parsePlatformError(platform, result) : null;
          const isRetrying = Boolean(retryingKeys[key]) || rawStatus === 'retrying';

          return (
            <div key={key} className="p-3 transition-colors hover:bg-slate-50/50 dark:hover:bg-slate-800/30">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                {/* Platform info and badge */}
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-slate-100 dark:bg-slate-800 text-sm">
                    {PLATFORM_ICONS[platform] || <span className="capitalize">{platform[0]}</span>}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-slate-800 dark:text-slate-200 capitalize">
                      {accountName}
                    </p>
                    <p className="text-[11px] text-slate-400 capitalize">{platform}</p>
                  </div>
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${badge.className}`}
                  >
                    <BadgeIcon className={`text-[9px] ${rawStatus === 'retrying' || rawStatus === 'processing' ? 'animate-spin' : ''}`} />
                    {badge.label}
                  </span>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 self-end sm:self-auto">
                  {isPublished && result.post_url && (
                    <a
                      href={result.post_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 rounded-md border border-indigo-200 bg-indigo-50/60 px-2.5 py-1 text-[11px] font-medium text-indigo-700 hover:bg-indigo-100 dark:border-indigo-800 dark:bg-indigo-950/40 dark:text-indigo-300"
                    >
                      <FaExternalLinkAlt className="text-[9px]" /> View Post
                    </a>
                  )}

                  {isFailed && (
                    <button
                      onClick={() => handleRetryTarget(key, platform)}
                      disabled={isRetrying}
                      className="inline-flex items-center gap-1 rounded-md bg-amber-600 px-2.5 py-1 text-[11px] font-semibold text-white shadow-xs hover:bg-amber-700 disabled:opacity-50 transition-colors"
                    >
                      {isRetrying ? (
                        <>
                          <FaSpinner className="animate-spin text-[9px]" /> Retrying…
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

              {/* Granular Error Diagnostic Card */}
              {isFailed && diagnostic && (
                <div className="mt-2.5 rounded-md border border-red-100 bg-red-50/50 p-2.5 dark:border-red-900/40 dark:bg-red-950/30 text-slate-700 dark:text-slate-300">
                  <div className="flex items-start gap-2">
                    <FaExclamationCircle className="mt-0.5 shrink-0 text-red-500 dark:text-red-400 text-xs" />
                    <div className="space-y-1 min-w-0 flex-1">
                      <p className="font-semibold text-red-900 dark:text-red-200">
                        {diagnostic.title}
                      </p>
                      <p className="text-[11px] text-slate-600 dark:text-slate-300 leading-relaxed">
                        {diagnostic.message}
                      </p>

                      {diagnostic.action && (
                        <div className="mt-1.5 flex flex-wrap items-center gap-2 pt-1 border-t border-red-100 dark:border-red-900/30">
                          <span className="text-[10px] font-semibold text-amber-800 dark:text-amber-300">
                            Action: {diagnostic.action}
                          </span>

                          {diagnostic.actionType === 'reconnect' && (
                            <button
                              onClick={() => navigate('/connected-accounts')}
                              className="inline-flex items-center gap-1 text-[10px] font-bold text-blue-600 hover:underline dark:text-blue-400"
                            >
                              <FaTools className="text-[9px]" /> Open Connected Accounts
                            </button>
                          )}

                          {(diagnostic.actionType === 'edit_post' || diagnostic.actionType === 'crop_media') && (
                            <button
                              onClick={() => navigate(`/create-post?duplicateFrom=${post.id}`)}
                              className="inline-flex items-center gap-1 text-[10px] font-bold text-indigo-600 hover:underline dark:text-indigo-400"
                            >
                              Edit in Composer
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
