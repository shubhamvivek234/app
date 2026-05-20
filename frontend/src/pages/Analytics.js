import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { format, isValid, parseISO } from 'date-fns';
import DashboardLayout from '@/components/DashboardLayout';
import { getAnalyticsBrandHealth, getSocialAccounts } from '@/lib/api';
import { toast } from 'sonner';
import {
  FaChevronDown,
  FaExclamationCircle,
  FaExternalLinkAlt,
  FaFacebook,
  FaGripLines,
  FaInstagram,
  FaLinkedin,
  FaPinterest,
  FaReddit,
  FaSnapchat,
  FaTiktok,
  FaTwitter,
  FaYoutube,
} from 'react-icons/fa';
import { SiBluesky, SiDiscord, SiMastodon, SiThreads } from 'react-icons/si';

const PLATFORM_COLORS = {
  instagram: '#E1306C',
  twitter: '#1DA1F2',
  facebook: '#1877F2',
  linkedin: '#0A66C2',
  youtube: '#FF0000',
  tiktok: '#010101',
  pinterest: '#E60023',
  threads: '#101010',
  bluesky: '#0085FF',
  reddit: '#FF4500',
  snapchat: '#FFFC00',
  discord: '#5865F2',
  mastodon: '#6364FF',
};

const PLATFORM_LABELS = {
  instagram: 'Instagram',
  twitter: 'Twitter / X',
  facebook: 'Facebook',
  linkedin: 'LinkedIn',
  youtube: 'YouTube',
  tiktok: 'TikTok',
  pinterest: 'Pinterest',
  threads: 'Threads',
  bluesky: 'Bluesky',
  reddit: 'Reddit',
  snapchat: 'Snapchat',
  discord: 'Discord',
  mastodon: 'Mastodon',
};

const PLATFORM_SOURCE_LABELS = {
  instagram: 'Instagram',
  twitter: 'X',
  facebook: 'Facebook',
  linkedin: 'LinkedIn',
  youtube: 'YouTube',
  tiktok: 'TikTok',
  pinterest: 'Pinterest',
  threads: 'Threads',
  bluesky: 'Bluesky',
  reddit: 'Reddit',
  snapchat: 'Snapchat',
  discord: 'Discord',
  mastodon: 'Mastodon',
};

const PLATFORM_ICONS = {
  instagram: FaInstagram,
  facebook: FaFacebook,
  twitter: FaTwitter,
  linkedin: FaLinkedin,
  youtube: FaYoutube,
  tiktok: FaTiktok,
  pinterest: FaPinterest,
  threads: SiThreads,
  bluesky: SiBluesky,
  reddit: FaReddit,
  snapchat: FaSnapchat,
  discord: SiDiscord,
  mastodon: SiMastodon,
};

const ALL_PLATFORMS = [
  'instagram',
  'facebook',
  'twitter',
  'linkedin',
  'youtube',
  'tiktok',
  'pinterest',
  'threads',
  'bluesky',
  'snapchat',
  'reddit',
  'discord',
  'mastodon',
];

const DAYS_OPTIONS = [
  { label: '7d', value: 7 },
  { label: '30d', value: 30 },
  { label: '90d', value: 90 },
];

const PLATFORM_ORDER_STORAGE_KEY_PREFIX = 'analytics_platform_order_v1';

const fmt = (n) => {
  if (n == null) return 'NA';
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
};

const normalizePlatformOrder = (order) => {
  const incoming = Array.isArray(order) ? order : [];
  const valid = incoming.filter(
    (platform, index) => ALL_PLATFORMS.includes(platform) && incoming.indexOf(platform) === index,
  );
  const missing = ALL_PLATFORMS.filter((platform) => !valid.includes(platform));
  return [...valid, ...missing];
};

const parseDate = (value) => {
  if (!value || typeof value !== 'string') return null;
  try {
    const parsed = parseISO(value.replace('Z', '+00:00'));
    return isValid(parsed) ? parsed : null;
  } catch {
    return null;
  }
};

const formatPublishedAt = (value) => {
  const parsed = parseDate(value);
  if (!parsed) return null;
  return format(parsed, 'd MMM');
};

const changeLabel = (value) => {
  if (value == null) return null;
  const formatted = `${Math.abs(value).toFixed(value % 1 === 0 ? 0 : 1)}%`;
  if (value > 0) return { text: `↑ ${formatted}`, color: 'text-emerald-600' };
  if (value < 0) return { text: `↓ ${formatted}`, color: 'text-rose-600' };
  return { text: '0.0%', color: 'text-gray-400' };
};

const recentPostMetricRows = (post) => {
  const platform = post.platform;
  const metrics = post.metrics || {};
  const rows = [];
  const primaryReactionLabel = platform === 'facebook' ? 'Reactions' : 'Likes';
  const commentsLabel = ['twitter', 'threads', 'bluesky', 'mastodon', 'reddit'].includes(platform) ? 'Replies' : 'Comments';
  const sharesLabel = ['twitter', 'threads', 'bluesky', 'mastodon'].includes(platform) ? 'Reposts' : 'Shares';

  rows.push({ label: primaryReactionLabel, value: metrics.likes ?? 0 });
  rows.push({ label: commentsLabel, value: metrics.comments ?? 0 });
  if (platform !== 'linkedin' && platform !== 'discord' && platform !== 'snapchat') {
    rows.push({ label: sharesLabel, value: metrics.shares ?? 0 });
  }
  if ((metrics.views ?? 0) > 0) {
    rows.push({ label: 'Views', value: metrics.views ?? 0 });
  }
  rows.push({ label: 'Engagement', value: post.total_engagement ?? 0 });
  return rows;
};

const getAnalyticsUserKey = (accounts) => {
  const first = Array.isArray(accounts) ? accounts.find((account) => account?.user_id) : null;
  return first?.user_id || 'default';
};

const SkeletonBlock = ({ className }) => (
  <div className={`animate-pulse rounded-xl bg-gray-100 ${className}`} />
);

const AccountAvatar = ({ account, size = 'sm' }) => {
  const classes = size === 'sm' ? 'h-6 w-6 text-[10px]' : 'h-9 w-9 text-xs';
  const seed = account?.platform_username || account?.display_name || account?.account_id || '?';
  const initials = seed.replace('@', '').slice(0, 2).toUpperCase();
  const color = PLATFORM_COLORS[account?.platform] || '#6b7280';

  if (account?.picture_url) {
    return (
      <div className={`${classes} relative`}>
        <img
          src={account.picture_url}
          alt={initials}
          className="h-full w-full rounded-full border border-white object-cover shadow-sm"
          onError={(event) => {
            event.currentTarget.style.display = 'none';
            const fallback = event.currentTarget.nextSibling;
            if (fallback) fallback.style.display = 'flex';
          }}
        />
        <div
          className="hidden h-full w-full items-center justify-center rounded-full font-bold text-white shadow-sm"
          style={{ background: color }}
        >
          {initials}
        </div>
      </div>
    );
  }

  return (
    <div
      className={`${classes} flex items-center justify-center rounded-full font-bold text-white shadow-sm`}
      style={{ background: color }}
    >
      {initials}
    </div>
  );
};

const AccountDropdown = ({ accounts, selectedId, onSelect, platformLabel }) => {
  const [open, setOpen] = useState(false);
  const selected = accounts.find((account) => account.id === selectedId) || null;
  const ref = useRef(null);

  useEffect(() => {
    const handleClick = (event) => {
      if (ref.current && !ref.current.contains(event.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((value) => !value)}
        className="flex min-w-[220px] items-center gap-3 rounded-xl border border-gray-200 bg-offwhite px-3 py-2 shadow-sm transition-colors hover:bg-gray-50"
      >
        {selected ? (
          <>
            <AccountAvatar account={selected} size="sm" />
            <span className="flex-1 truncate text-left text-sm font-semibold text-gray-800">
              {selected.platform_username || selected.display_name || selected.id}
            </span>
          </>
        ) : (
          <span className="flex-1 text-left text-sm font-semibold text-gray-600">
            All {platformLabel} Accounts
          </span>
        )}
        <FaChevronDown className={`text-xs text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-50 mt-1 w-72 overflow-hidden rounded-xl border border-gray-200 bg-offwhite shadow-xl">
          <button
            onClick={() => {
              onSelect(null);
              setOpen(false);
            }}
            className={`flex w-full items-center gap-3 px-4 py-2.5 text-sm transition-colors hover:bg-gray-50 ${
              !selectedId ? 'bg-indigo-50 font-semibold text-indigo-700' : 'text-gray-700'
            }`}
          >
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-gray-200 text-[10px] font-bold text-gray-500">
              All
            </div>
            <span>All {platformLabel} Accounts</span>
          </button>
          {accounts.map((account) => (
            <button
              key={account.id}
              onClick={() => {
                onSelect(account.id);
                setOpen(false);
              }}
              className={`flex w-full items-center gap-3 px-4 py-2.5 text-sm transition-colors hover:bg-gray-50 ${
                selectedId === account.id ? 'bg-indigo-50 font-semibold text-indigo-700' : 'text-gray-700'
              }`}
            >
              <AccountAvatar account={account} size="sm" />
              <span className="flex-1 truncate text-left">
                {account.platform_username || account.display_name || account.id}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

const PlatformSidebar = ({
  accounts,
  selectedPlatform,
  onSelect,
  platformOrder,
  draggingPlatform,
  onDragStart,
  onDragEnter,
  onDragEnd,
}) => {
  const accountsByPlatform = accounts.reduce((acc, account) => {
    if (!acc[account.platform]) acc[account.platform] = [];
    acc[account.platform].push(account);
    return acc;
  }, {});

  return (
    <nav className="py-2 select-none">
      <p className="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-gray-400">Channels</p>
      <p className="px-4 pb-2 text-[11px] text-gray-400">Drag platforms to arrange this list.</p>

      <button
        onClick={() => onSelect(null)}
        className={`flex w-full items-center gap-3 border-r-2 px-4 py-2.5 text-sm transition-colors ${
          !selectedPlatform
            ? 'border-indigo-500 bg-indigo-50 font-semibold text-indigo-700'
            : 'border-transparent text-gray-600 hover:bg-gray-50'
        }`}
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-gray-100 text-gray-400">📊</span>
        <span className="flex-1 text-left text-[13px]">All Platforms</span>
      </button>

      {platformOrder.map((platform, index) => {
        const platformAccounts = accountsByPlatform[platform] || [];
        const isConnected = platformAccounts.length > 0;
        const isActive = selectedPlatform === platform;
        const Icon = PLATFORM_ICONS[platform];
        const color = PLATFORM_COLORS[platform] || '#6b7280';

        return (
          <button
            key={platform}
            draggable
            title={isConnected ? `${platformAccounts.length} connected ${platformAccounts.length === 1 ? 'account' : 'accounts'}` : 'No connected accounts'}
            onDragStart={() => onDragStart(index)}
            onDragEnter={() => onDragEnter(index)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              onDragEnd();
            }}
            onDragEnd={onDragEnd}
            onClick={() => onSelect(platform)}
            className={`group relative flex w-full items-center gap-3 border-r-2 px-4 py-2.5 text-sm transition-colors ${
              isActive
                ? 'border-indigo-500 bg-indigo-50 font-semibold text-indigo-700'
                : 'border-transparent text-gray-600 hover:bg-gray-50'
            } ${!isConnected ? 'opacity-40' : ''} ${draggingPlatform === platform ? 'scale-[0.995] bg-gray-50 opacity-60' : ''}`}
          >
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-md transition-colors ${
                isActive ? 'bg-indigo-100 text-indigo-500' : 'bg-gray-100 text-gray-400 group-hover:text-gray-600'
              }`}
            >
              <FaGripLines className="text-[10px]" />
            </span>
            {Icon && <Icon size={17} style={{ color, flexShrink: 0 }} />}
            <span className="flex-1 text-left text-[13px]">{PLATFORM_LABELS[platform] || platform}</span>
            {isConnected && (
              <span
                className="pointer-events-none absolute left-full top-1/2 z-30 ml-2 -translate-y-1/2 translate-x-1 whitespace-nowrap rounded-full px-2 py-1 text-[10px] font-bold opacity-0 shadow-sm transition-all duration-150 group-hover:translate-x-0 group-hover:opacity-100"
                style={{ background: `${color}22`, color }}
              >
                {platformAccounts.length} {platformAccounts.length === 1 ? 'Account' : 'Accounts'}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
};

const MetricCell = ({ value, delta }) => {
  const change = changeLabel(delta);
  if (value == null) return <span className="text-sm font-medium text-gray-400">NA</span>;

  return (
    <div className="flex items-center gap-2">
      <span className="text-lg font-semibold text-gray-900">{fmt(value)}</span>
      {change && <span className={`text-sm font-semibold ${change.color}`}>{change.text}</span>}
    </div>
  );
};

const BrandHealthTable = ({ rows, platformOrder }) => {
  const platformRank = new Map(platformOrder.map((platform, index) => [platform, index]));
  const sortedRows = [...rows].sort((a, b) => {
    const rankA = platformRank.get(a.platform) ?? 999;
    const rankB = platformRank.get(b.platform) ?? 999;
    if (rankA !== rankB) return rankA - rankB;
    return (a.display_name || a.platform_username || '').localeCompare(b.display_name || b.platform_username || '');
  });

  if (!sortedRows.length) {
    return (
      <div className="rounded-2xl border border-gray-200 bg-offwhite p-10 text-center">
        <p className="text-base font-semibold text-gray-600">No connected accounts for this filter.</p>
        <p className="mt-2 text-sm text-gray-400">Connect accounts or switch platforms to see channel health.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left">
        <thead>
          <tr className="border-b border-gray-200 text-[11px] font-bold uppercase tracking-widest text-gray-400">
            <th className="w-[320px] px-4 py-4">Channels</th>
            <th className="min-w-[180px] px-4 py-4">Total Followers / Subscribers</th>
            <th className="min-w-[180px] px-4 py-4">New Followers / Subscribers Gained</th>
            <th className="min-w-[160px] px-4 py-4">No. of Posts / Videos</th>
            <th className="min-w-[140px] px-4 py-4">Reach</th>
            <th className="min-w-[160px] px-4 py-4">Engagements</th>
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row) => {
            const accountLabel = row.display_name || row.platform_username || row.account_id;
            const note = row.error || row.notice;
            return (
              <tr key={row.account_id} className="border-b border-gray-100 last:border-b-0">
                <td className="px-4 py-5 align-top">
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5">
                      <AccountAvatar account={row} size="md" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="truncate text-base font-semibold text-gray-900">{accountLabel}</p>
                        {note && (
                          <span title={note}>
                            <FaExclamationCircle className={`text-sm ${row.error ? 'text-amber-500' : 'text-gray-400'}`} />
                          </span>
                        )}
                      </div>
                      <p className="mt-0.5 text-sm text-gray-500">{PLATFORM_LABELS[row.platform] || row.platform}</p>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-5 align-top"><MetricCell value={row.followers_total} delta={row.followers_total_change_pct} /></td>
                <td className="px-4 py-5 align-top"><MetricCell value={row.new_followers} delta={null} /></td>
                <td className="px-4 py-5 align-top"><MetricCell value={row.posts_count} delta={row.posts_change_pct} /></td>
                <td className="px-4 py-5 align-top"><MetricCell value={row.reach} delta={null} /></td>
                <td className="px-4 py-5 align-top"><MetricCell value={row.engagements} delta={row.engagements_change_pct} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

const RecentPostCard = ({ post }) => {
  const rows = recentPostMetricRows(post);

  return (
    <article className="w-[300px] flex-shrink-0 rounded-2xl border border-gray-200 bg-offwhite p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <AccountAvatar
          account={{
            platform: post.platform,
            picture_url: post.picture_url,
            platform_username: post.account_username,
            display_name: post.account_label,
            account_id: post.account_id,
          }}
          size="md"
        />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-gray-900">{post.account_label || post.account_username || 'Connected account'}</p>
          <p className="truncate text-xs text-gray-500">directly via {PLATFORM_SOURCE_LABELS[post.platform] || PLATFORM_LABELS[post.platform] || post.platform}</p>
          {post.published_at && (
            <p className="mt-1 text-xs text-gray-400">{formatPublishedAt(post.published_at)}</p>
          )}
        </div>
      </div>

      <div className="mt-4 overflow-hidden rounded-xl border border-gray-100 bg-gray-50">
        {post.media_url ? (
          <img
            src={post.media_url}
            alt=""
            className="h-44 w-full object-cover"
            onError={(event) => {
              event.currentTarget.style.display = 'none';
              const fallback = event.currentTarget.parentElement?.querySelector('[data-fallback]');
              if (fallback) fallback.classList.remove('hidden');
            }}
          />
        ) : null}
        <div
          data-fallback
          className={`flex h-44 items-center justify-center px-6 text-center text-sm text-gray-400 ${post.media_url ? 'hidden' : ''}`}
        >
          {post.content || 'No media preview available'}
        </div>
      </div>

      <p className="mt-4 line-clamp-3 text-sm text-gray-800">{post.content || '(no caption)'}</p>

      <div className="mt-4 space-y-2 border-t border-dashed border-gray-200 pt-4">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between text-sm">
            <span className="text-gray-600">{row.label}</span>
            <span className="font-semibold text-gray-900">{fmt(row.value)}</span>
          </div>
        ))}
      </div>

      <div className="mt-4 flex items-center justify-between">
        {post.row_error ? (
          <span className="text-xs text-amber-600" title={post.row_error}>Feed fallback used</span>
        ) : <span />}
        {post.post_url && (
          <a
            href={post.post_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700"
          >
            View post <FaExternalLinkAlt className="text-[10px]" />
          </a>
        )}
      </div>
    </article>
  );
};

const Analytics = () => {
  const [days, setDays] = useState(30);
  const [selectedPlatform, setSelectedPlatform] = useState(null);
  const [selectedAccount, setSelectedAccount] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [brandHealth, setBrandHealth] = useState(null);
  const [loadingAccounts, setLoadingAccounts] = useState(true);
  const [loadingBrandHealth, setLoadingBrandHealth] = useState(true);
  const [platformOrder, setPlatformOrder] = useState(ALL_PLATFORMS);
  const [loadedPlatformOrder, setLoadedPlatformOrder] = useState(false);
  const [draggingPlatform, setDraggingPlatform] = useState(null);
  const dragPlatformIdx = useRef(null);
  const dragOverPlatformIdx = useRef(null);

  const platformOrderStorageKey = `${PLATFORM_ORDER_STORAGE_KEY_PREFIX}_${getAnalyticsUserKey(accounts)}`;

  useEffect(() => {
    let cancelled = false;

    const loadAccounts = async (retry = false) => {
      setLoadingAccounts(true);
      try {
        const data = await getSocialAccounts();
        if (!cancelled) setAccounts(data);
      } catch {
        if (!retry && !cancelled) {
          window.setTimeout(() => loadAccounts(true), 500);
        } else if (!cancelled) {
          toast.error('Failed to load connected accounts');
        }
      } finally {
        if (!cancelled) setLoadingAccounts(false);
      }
    };

    loadAccounts();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(platformOrderStorageKey);
      const saved = raw ? JSON.parse(raw) : null;
      setPlatformOrder(normalizePlatformOrder(saved));
    } catch {
      setPlatformOrder(ALL_PLATFORMS);
    } finally {
      setLoadedPlatformOrder(true);
    }
  }, [platformOrderStorageKey]);

  useEffect(() => {
    if (!loadedPlatformOrder) return;
    try {
      window.localStorage.setItem(platformOrderStorageKey, JSON.stringify(normalizePlatformOrder(platformOrder)));
    } catch {}
  }, [loadedPlatformOrder, platformOrderStorageKey, platformOrder]);

  useEffect(() => {
    if (!selectedPlatform) {
      setSelectedAccount(null);
      return;
    }
    const platformAccounts = accounts.filter((account) => account.platform === selectedPlatform);
    if (selectedAccount && !platformAccounts.some((account) => account.id === selectedAccount)) {
      setSelectedAccount(null);
    }
  }, [accounts, selectedPlatform, selectedAccount]);

  const fetchBrandHealth = useCallback(async () => {
    setLoadingBrandHealth(true);
    try {
      const data = await getAnalyticsBrandHealth({
        days,
        platform: selectedPlatform,
        accountId: selectedAccount,
      });
      setBrandHealth(data);
    } catch {
      toast.error('Failed to load analytics');
      setBrandHealth(null);
    } finally {
      setLoadingBrandHealth(false);
    }
  }, [days, selectedPlatform, selectedAccount]);

  useEffect(() => {
    fetchBrandHealth();
  }, [fetchBrandHealth]);

  const filteredPlatformAccounts = useMemo(
    () => accounts.filter((account) => !selectedPlatform || account.platform === selectedPlatform),
    [accounts, selectedPlatform],
  );

  const selectedPlatformAccounts = useMemo(
    () => accounts.filter((account) => account.platform === selectedPlatform),
    [accounts, selectedPlatform],
  );

  const platformTitle = selectedPlatform ? PLATFORM_LABELS[selectedPlatform] || selectedPlatform : 'All Platforms';
  const selectedIcon = selectedPlatform ? PLATFORM_ICONS[selectedPlatform] : null;
  const selectedColor = selectedPlatform ? (PLATFORM_COLORS[selectedPlatform] || '#6b7280') : '#6b7280';

  const sortedRows = useMemo(() => {
    const rows = brandHealth?.rows || [];
    const rank = new Map(platformOrder.map((platform, index) => [platform, index]));
    return [...rows].sort((a, b) => {
      const rankA = rank.get(a.platform) ?? 999;
      const rankB = rank.get(b.platform) ?? 999;
      if (rankA !== rankB) return rankA - rankB;
      return (a.display_name || a.platform_username || a.account_id || '').localeCompare(
        b.display_name || b.platform_username || b.account_id || '',
      );
    });
  }, [brandHealth?.rows, platformOrder]);

  const sortedRecentPosts = useMemo(() => {
    const posts = brandHealth?.recent_posts || [];
    const order = new Map(sortedRows.map((row, index) => [row.account_id, index]));
    return [...posts].sort((a, b) => {
      const rankA = order.get(a.account_id) ?? 999;
      const rankB = order.get(b.account_id) ?? 999;
      return rankA - rankB;
    });
  }, [brandHealth?.recent_posts, sortedRows]);

  const handleDragStart = (index) => {
    dragPlatformIdx.current = index;
    setDraggingPlatform(platformOrder[index] || null);
  };

  const handleDragEnter = (index) => {
    dragOverPlatformIdx.current = index;
  };

  const handleDragEnd = () => {
    const fromIndex = dragPlatformIdx.current;
    const toIndex = dragOverPlatformIdx.current;
    if (fromIndex == null || toIndex == null || fromIndex === toIndex) {
      dragPlatformIdx.current = null;
      dragOverPlatformIdx.current = null;
      setDraggingPlatform(null);
      return;
    }

    setPlatformOrder((current) => {
      const next = [...current];
      const [moved] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, moved);
      return next;
    });

    dragPlatformIdx.current = null;
    dragOverPlatformIdx.current = null;
    setDraggingPlatform(null);
  };

  const renderLoadingState = () => (
    <div className="space-y-6">
      <div className="rounded-2xl border border-gray-200 bg-offwhite p-6">
        <SkeletonBlock className="mb-4 h-6 w-64" />
        <SkeletonBlock className="h-64 w-full" />
      </div>
      <div className="rounded-2xl border border-gray-200 bg-offwhite p-6">
        <SkeletonBlock className="mb-4 h-6 w-40" />
        <div className="flex gap-4 overflow-hidden">
          {[1, 2, 3].map((item) => (
            <div key={item} className="w-[300px] flex-shrink-0 space-y-3">
              <SkeletonBlock className="h-5 w-40" />
              <SkeletonBlock className="h-44 w-full" />
              <SkeletonBlock className="h-16 w-full" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  return (
    <DashboardLayout>
      <div className="min-h-screen bg-white">
        <div className="mx-auto max-w-[1600px] px-6 py-6">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
            <aside className="self-start rounded-2xl border border-gray-200 bg-offwhite">
              <PlatformSidebar
                accounts={accounts}
                selectedPlatform={selectedPlatform}
                onSelect={setSelectedPlatform}
                platformOrder={platformOrder}
                draggingPlatform={draggingPlatform}
                onDragStart={handleDragStart}
                onDragEnter={handleDragEnter}
                onDragEnd={handleDragEnd}
              />
            </aside>

            <main className="min-w-0 space-y-6">
              <div className="flex flex-col gap-4 rounded-2xl border border-gray-200 bg-offwhite p-6 xl:flex-row xl:items-center xl:justify-between">
                <div className="flex flex-wrap items-center gap-4">
                  {selectedPlatform && selectedIcon ? (
                    <div className="flex items-center gap-3">
                      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-white shadow-sm">
                        {React.createElement(selectedIcon, { style: { color: selectedColor }, className: 'text-xl' })}
                      </div>
                      <div>
                        <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Analytics</p>
                        <p className="text-xl font-semibold text-gray-900">{platformTitle}</p>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Analytics</p>
                      <p className="text-xl font-semibold text-gray-900">All Platforms</p>
                    </div>
                  )}

                  {selectedPlatform && selectedPlatformAccounts.length > 0 && (
                    <AccountDropdown
                      accounts={selectedPlatformAccounts}
                      selectedId={selectedAccount}
                      onSelect={setSelectedAccount}
                      platformLabel={platformTitle}
                    />
                  )}
                </div>

                <div className="flex items-center gap-2 self-start rounded-2xl border border-gray-200 bg-white p-1 shadow-sm">
                  {DAYS_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      onClick={() => setDays(option.value)}
                      className={`rounded-xl px-4 py-2 text-sm font-semibold transition-colors ${
                        days === option.value ? 'bg-indigo-50 text-indigo-600' : 'text-gray-500 hover:text-gray-700'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              {selectedPlatform && !loadingAccounts && filteredPlatformAccounts.length === 0 ? (
                <div className="rounded-2xl border border-gray-200 bg-offwhite p-10 text-center">
                  <p className="text-base font-semibold text-gray-600">
                    No {platformTitle} account connected
                  </p>
                  <p className="mt-2 text-sm text-gray-400">
                    Connect your {platformTitle} account to see analytics here.
                  </p>
                </div>
              ) : loadingBrandHealth || loadingAccounts ? (
                renderLoadingState()
              ) : (
                <>
                  <section className="rounded-2xl border border-gray-200 bg-offwhite p-6">
                    <div className="mb-5 flex flex-wrap items-center gap-3">
                      <h2 className="text-2xl font-semibold text-gray-900">Brand Health</h2>
                      <span className="rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-500">
                        Channels overview for the past {days} days
                      </span>
                    </div>

                    {brandHealth?.message ? (
                      <div className="rounded-xl border border-gray-200 bg-white p-10 text-center">
                        <p className="text-base font-semibold text-gray-600">{brandHealth.message}</p>
                      </div>
                    ) : (
                      <BrandHealthTable rows={sortedRows} platformOrder={platformOrder} />
                    )}
                  </section>

                  <section className="rounded-2xl border border-gray-200 bg-offwhite p-6">
                    <div className="mb-5 flex items-center justify-between gap-3">
                      <h2 className="text-2xl font-semibold text-gray-900">Recent Posts</h2>
                      {!!sortedRecentPosts.length && (
                        <span className="text-sm text-gray-400">{sortedRecentPosts.length} accounts with posts in range</span>
                      )}
                    </div>

                    {sortedRecentPosts.length > 0 ? (
                      <div className="overflow-x-auto">
                        <div className="flex gap-4 pb-2">
                          {sortedRecentPosts.map((post) => (
                            <RecentPostCard key={`${post.account_id}-${post.id}`} post={post} />
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="rounded-xl border border-gray-200 bg-white p-10 text-center">
                        <p className="text-base font-semibold text-gray-600">No recent posts in this date range.</p>
                        <p className="mt-2 text-sm text-gray-400">
                          Connected accounts remain visible in Brand Health even when they have no post in the selected window.
                        </p>
                      </div>
                    )}
                  </section>
                </>
              )}
            </main>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Analytics;
