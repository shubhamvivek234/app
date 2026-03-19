import React, { useState, useEffect, useCallback } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import {
  getAnalyticsOverview,
  getAnalyticsTimeline,
  getAnalyticsEngagement,
  getAnalyticsDemographics,
  getSocialAccounts,
  getPublishFeed,
} from '@/lib/api';
import { toast } from 'sonner';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, Legend,
} from 'recharts';
import {
  FaHeart, FaComment, FaShare, FaEye, FaFileAlt, FaExternalLinkAlt,
  FaInstagram, FaFacebook, FaTwitter, FaLinkedin, FaYoutube, FaTiktok,
  FaPinterest, FaReddit, FaSnapchat, FaSortAmountDown, FaChevronDown,
} from 'react-icons/fa';
import { SiThreads, SiBluesky } from 'react-icons/si';
import { format, parseISO, isValid } from 'date-fns';

// ── Platform config ────────────────────────────────────────────────────────────
const PLATFORM_COLORS = {
  instagram: '#E1306C',
  twitter:   '#1DA1F2',
  facebook:  '#1877F2',
  linkedin:  '#0A66C2',
  youtube:   '#FF0000',
  tiktok:    '#010101',
  pinterest: '#E60023',
  threads:   '#101010',
  bluesky:   '#0085FF',
  reddit:    '#FF4500',
  snapchat:  '#FFFC00',
};

const PLATFORM_LABELS = {
  instagram: 'Instagram', twitter: 'Twitter / X', facebook: 'Facebook',
  linkedin: 'LinkedIn', youtube: 'YouTube', tiktok: 'TikTok',
  pinterest: 'Pinterest', threads: 'Threads', bluesky: 'Bluesky',
  reddit: 'Reddit', snapchat: 'Snapchat',
};

const PLATFORM_ICONS = {
  instagram: FaInstagram,
  facebook:  FaFacebook,
  twitter:   FaTwitter,
  linkedin:  FaLinkedin,
  youtube:   FaYoutube,
  tiktok:    FaTiktok,
  pinterest: FaPinterest,
  threads:   SiThreads,
  bluesky:   SiBluesky,
  reddit:    FaReddit,
  snapchat:  FaSnapchat,
};

// Metrics that each platform supports (false = not available from API)
const PLATFORM_METRICS = {
  instagram: { likes: true,  comments: true,  shares: false, views: false },
  facebook:  { likes: true,  comments: true,  shares: true,  views: false },
  twitter:   { likes: true,  comments: true,  shares: true,  views: true  },
  tiktok:    { likes: true,  comments: true,  shares: true,  views: true  },
  threads:   { likes: true,  comments: true,  shares: true,  views: true  },
  reddit:    { likes: true,  comments: true,  shares: false, views: true  },
  pinterest: { likes: true,  comments: true,  shares: false, views: true  },
  youtube:   { likes: true,  comments: true,  shares: false, views: true  },
  linkedin:  { likes: false, comments: false, shares: false, views: false },
  bluesky:   { likes: true,  comments: true,  shares: true,  views: false },
  snapchat:  { likes: false, comments: false, shares: false, views: false },
};

const ALL_PLATFORMS = [
  'instagram', 'facebook', 'twitter', 'linkedin', 'youtube',
  'tiktok', 'pinterest', 'threads', 'bluesky', 'snapchat', 'reddit',
];

const DAYS_OPTIONS = [
  { label: '7d',  value: 7  },
  { label: '30d', value: 30 },
  { label: '90d', value: 90 },
];

const SORT_OPTIONS = [
  { label: 'Date',     value: 'date'     },
  { label: 'Likes',    value: 'likes'    },
  { label: 'Comments', value: 'comments' },
  { label: 'Shares',   value: 'shares'   },
  { label: 'Views',    value: 'views'    },
];

// ── Helpers ────────────────────────────────────────────────────────────────────
const fmt = (n) => {
  if (n == null) return '—';
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000)    return (n / 1000).toFixed(1) + 'K';
  return String(n);
};

const parseDate = (val) => {
  if (!val) return null;
  try {
    const dt = parseISO(val.replace('Z', ''));
    return isValid(dt) ? dt : null;
  } catch { return null; }
};

// ── Sub-components ─────────────────────────────────────────────────────────────

// Engagement summary card
const EngagementCard = ({ icon: Icon, label, value, color, loading }) => (
  <div className="bg-offwhite rounded-xl border border-gray-200 p-5 flex items-center gap-4">
    <div className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 ${color}`}>
      <Icon className="text-white text-lg" />
    </div>
    <div className="min-w-0">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{label}</p>
      {loading
        ? <div className="h-7 w-16 bg-gray-200 animate-pulse rounded mt-1" />
        : <p className="text-2xl font-bold text-gray-900 mt-0.5">{fmt(value)}</p>
      }
    </div>
  </div>
);

// Platform icon pill
const PlatformPill = ({ platform, active, onClick }) => {
  const Icon = PLATFORM_ICONS[platform];
  const color = PLATFORM_COLORS[platform] || '#6366f1';
  return (
    <button
      onClick={onClick}
      style={active ? { background: color, borderColor: color, color: '#fff' } : {}}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border transition-all
        ${active ? '' : 'border-gray-200 text-gray-600 bg-offwhite hover:border-gray-300 hover:bg-gray-50'}`}
    >
      {Icon && <Icon className="text-sm" style={active ? {} : { color }} />}
      {PLATFORM_LABELS[platform] || platform}
    </button>
  );
};

// Custom tooltip for AreaChart
const TimelineTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-offwhite border border-gray-200 rounded-lg px-3 py-2 shadow-lg text-sm">
      <p className="font-semibold text-gray-700">{label}</p>
      <p className="text-indigo-600">{payload[0]?.value} posts</p>
    </div>
  );
};

// Custom tooltip for Bar chart
const EngagementTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-offwhite border border-gray-200 rounded-lg px-3 py-2 shadow-lg text-sm">
      <p className="font-semibold text-gray-700 mb-1">{PLATFORM_LABELS[label] || label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.fill || p.color }} className="capitalize">
          {p.name}: {fmt(p.value)}
        </p>
      ))}
    </div>
  );
};

// Post card for the Posts tab
const PostCard = ({ post }) => {
  const plat = post.platform || 'unknown';
  const Icon = PLATFORM_ICONS[plat] || FaFileAlt;
  const color = PLATFORM_COLORS[plat] || '#6b7280';
  const metrics = post.metrics || {};
  const support = PLATFORM_METRICS[plat] || {};
  const dt = parseDate(post.published_at);

  return (
    <div className="bg-offwhite rounded-xl border border-gray-200 p-4 flex gap-4 hover:shadow-sm transition-shadow">
      {/* Thumbnail */}
      {post.media_url ? (
        <div className="w-20 h-20 rounded-lg overflow-hidden flex-shrink-0 bg-gray-100">
          <img
            src={post.media_url}
            alt=""
            className="w-full h-full object-cover"
            onError={(e) => { e.target.style.display = 'none'; }}
          />
        </div>
      ) : (
        <div className="w-20 h-20 rounded-lg flex-shrink-0 bg-gray-100 flex items-center justify-center">
          <FaFileAlt className="text-gray-400 text-2xl" />
        </div>
      )}

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Header */}
        <div className="flex items-center gap-2 mb-1">
          <Icon style={{ color }} className="text-sm flex-shrink-0" />
          <span className="text-xs font-semibold text-gray-600">{post.account_username || PLATFORM_LABELS[plat]}</span>
          {dt && <span className="text-xs text-gray-400 ml-auto">{format(dt, 'MMM d, yyyy')}</span>}
        </div>
        {/* Caption */}
        <p className="text-sm text-gray-700 line-clamp-2 mb-2">
          {post.content || '(no caption)'}
        </p>
        {/* Metrics row */}
        <div className="flex items-center gap-4 flex-wrap">
          {support.likes !== false && (
            <span className="flex items-center gap-1 text-xs text-gray-500">
              <FaHeart className="text-rose-400" /> {support.likes ? fmt(metrics.likes ?? 0) : '—'}
            </span>
          )}
          {support.comments !== false && (
            <span className="flex items-center gap-1 text-xs text-gray-500">
              <FaComment className="text-blue-400" /> {support.comments ? fmt(metrics.comments ?? 0) : '—'}
            </span>
          )}
          {support.shares !== false && (
            <span className="flex items-center gap-1 text-xs text-gray-500">
              <FaShare className="text-green-400" /> {support.shares ? fmt(metrics.shares ?? 0) : '—'}
            </span>
          )}
          {support.views !== false && (
            <span className="flex items-center gap-1 text-xs text-gray-500">
              <FaEye className="text-purple-400" /> {support.views ? fmt(metrics.views ?? 0) : '—'}
            </span>
          )}
          {post.post_url && (
            <a
              href={post.post_url}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto flex items-center gap-1 text-xs text-indigo-500 hover:text-indigo-700"
            >
              View post <FaExternalLinkAlt className="text-[10px]" />
            </a>
          )}
        </div>
      </div>
    </div>
  );
};

// Demographic placeholder card
const DemoCard = ({ title }) => (
  <div className="bg-offwhite rounded-xl border border-gray-200 p-5">
    <p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-3">{title}</p>
    <div className="h-32 flex items-center justify-center bg-gray-50 rounded-lg">
      <p className="text-sm text-gray-400">No data available</p>
    </div>
  </div>
);

// ── Account avatar helper ───────────────────────────────────────────────────
const AccountAvatar = ({ account, size = 'sm' }) => {
  const sz = size === 'sm' ? 'w-6 h-6 text-[10px]' : 'w-8 h-8 text-xs';
  const initials = (account.platform_username || account.platform_user_id || '?')
    .replace('@', '').slice(0, 2).toUpperCase();
  const color = PLATFORM_COLORS[account.platform] || '#6b7280';

  if (account.picture_url) {
    return (
      <img
        src={account.picture_url}
        alt={initials}
        className={`${sz} rounded-full object-cover border border-white shadow-sm flex-shrink-0`}
        onError={(e) => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex'; }}
      />
    );
  }
  return (
    <div
      className={`${sz} rounded-full flex items-center justify-center font-bold text-white flex-shrink-0`}
      style={{ background: color }}
    >
      {initials}
    </div>
  );
};

// ── Custom account dropdown with avatars ────────────────────────────────────
const AccountDropdown = ({ accounts, selectedId, onSelect, platformLabel, showAll }) => {
  const [open, setOpen] = useState(false);
  const selected = accounts.find((a) => a.id === selectedId) || null;
  const displayName = (a) => a.platform_username || a.platform_user_id || a.id;

  // Close when clicking outside
  const ref = React.useRef(null);
  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      {/* Trigger button */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 border border-gray-200 rounded-xl px-3 py-2 bg-offwhite hover:bg-gray-50 transition-colors min-w-[180px] shadow-sm"
      >
        {selected ? (
          <>
            <AccountAvatar account={selected} size="sm" />
            <span className="flex-1 text-left text-sm font-semibold text-gray-800 truncate">
              {displayName(selected)}
            </span>
          </>
        ) : (
          <span className="flex-1 text-left text-sm font-semibold text-gray-600">
            All {platformLabel} Accounts
          </span>
        )}
        <FaChevronDown className={`text-gray-400 text-xs flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown panel */}
      {open && (
        <div className="absolute top-full left-0 mt-1 w-64 bg-offwhite rounded-xl border border-gray-200 shadow-xl z-50 overflow-hidden">
          {/* "All accounts" option */}
          {showAll && (
            <button
              onClick={() => { onSelect(null); setOpen(false); }}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-gray-50 transition-colors
                ${!selectedId ? 'bg-indigo-50 text-indigo-700 font-semibold' : 'text-gray-700'}`}
            >
              <div className="w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
                <span className="text-[10px] font-bold text-gray-500">All</span>
              </div>
              <span>All {platformLabel} Accounts</span>
            </button>
          )}
          {/* Each account */}
          {accounts.map((a) => (
            <button
              key={a.id}
              onClick={() => { onSelect(a.id); setOpen(false); }}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-gray-50 transition-colors
                ${selectedId === a.id ? 'bg-indigo-50 text-indigo-700 font-semibold' : 'text-gray-700'}`}
            >
              <AccountAvatar account={a} size="sm" />
              <div className="flex-1 text-left min-w-0">
                <p className="font-semibold truncate">{displayName(a)}</p>
              </div>
              {selectedId === a.id && (
                <span className="w-2 h-2 rounded-full bg-indigo-500 flex-shrink-0" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

// Platform sidebar listing ALL platforms
const PlatformSidebar = ({ accounts, selectedPlatform, onSelect }) => {
  const accountsByPlatform = accounts.reduce((acc, a) => {
    if (!acc[a.platform]) acc[a.platform] = [];
    acc[a.platform].push(a);
    return acc;
  }, {});

  return (
    <nav className="py-2 select-none">
      <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 px-4 py-2">Channels</p>

      {/* All Platforms */}
      <button
        onClick={() => onSelect(null)}
        className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors border-r-2
          ${!selectedPlatform
            ? 'bg-indigo-50 text-indigo-700 font-semibold border-indigo-500'
            : 'text-gray-600 hover:bg-gray-50 border-transparent'}`}
      >
        <span className="w-[18px] text-center">📊</span>
        <span className="flex-1 text-left text-[13px]">All Platforms</span>
      </button>

      {/* Each platform row */}
      {ALL_PLATFORMS.map((plat) => {
        const platAccounts = accountsByPlatform[plat] || [];
        const isConnected  = platAccounts.length > 0;
        const isActive     = selectedPlatform === plat;
        const Icon         = PLATFORM_ICONS[plat];
        const color        = PLATFORM_COLORS[plat] || '#6b7280';
        return (
          <button
            key={plat}
            onClick={() => onSelect(plat)}
            className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors border-r-2
              ${isActive
                ? 'bg-indigo-50 text-indigo-700 font-semibold border-indigo-500'
                : 'text-gray-600 hover:bg-gray-50 border-transparent'}
              ${!isConnected ? 'opacity-40' : ''}`}
          >
            {Icon && <Icon size={17} style={{ color, flexShrink: 0 }} />}
            <span className="flex-1 text-left text-[13px]">{PLATFORM_LABELS[plat] || plat}</span>
            {isConnected && (
              <span
                className="text-[10px] font-bold px-1.5 py-0.5 rounded-full whitespace-nowrap"
                style={{ background: color + '22', color }}
              >
                {platAccounts.length} {platAccounts.length === 1 ? 'Account' : 'Accounts'}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
};

// ── Main Analytics component ───────────────────────────────────────────────────
const Analytics = () => {
  const [activeTab, setActiveTab]           = useState('overview');
  const [days, setDays]                     = useState(30);
  const [selectedPlatform, setSelectedPlatform] = useState(null);
  const [selectedAccount, setSelectedAccount]   = useState(null);

  const [accounts, setAccounts]       = useState([]);
  const [overview, setOverview]       = useState(null);
  const [timeline, setTimeline]       = useState([]);
  const [engagement, setEngagement]   = useState(null);
  const [posts, setPosts]             = useState([]);
  const [postsSort, setPostsSort]     = useState('date');

  const [loadingOverview, setLoadingOverview]       = useState(true);
  const [loadingEngagement, setLoadingEngagement]   = useState(false);
  const [loadingPosts, setLoadingPosts]             = useState(false);
  const [demographics, setDemographics]             = useState(null);
  const [loadingDemos, setLoadingDemos]             = useState(false);

  // Unique platforms from connected accounts
  const connectedPlatforms = [...new Set(accounts.map((a) => a.platform))];

  // Fetch accounts once
  useEffect(() => {
    getSocialAccounts()
      .then(setAccounts)
      .catch(() => {});
  }, []);

  // Fetch overview + timeline whenever filters change
  const fetchOverview = useCallback(async () => {
    setLoadingOverview(true);
    try {
      const params = { days, platform: selectedPlatform, accountId: selectedAccount };
      const [ov, tl] = await Promise.all([
        getAnalyticsOverview(params),
        getAnalyticsTimeline(params),
      ]);
      setOverview(ov);
      setTimeline(tl);
    } catch {
      toast.error('Failed to load analytics overview');
    } finally {
      setLoadingOverview(false);
    }
  }, [days, selectedPlatform, selectedAccount]);

  useEffect(() => {
    fetchOverview();
  }, [fetchOverview]);

  // Fetch engagement when on Overview tab
  const fetchEngagement = useCallback(async () => {
    setLoadingEngagement(true);
    try {
      const data = await getAnalyticsEngagement({
        days,
        platform: selectedPlatform,
        accountId: selectedAccount,
      });
      setEngagement(data);
    } catch {
      toast.error('Failed to load engagement data');
    } finally {
      setLoadingEngagement(false);
    }
  }, [days, selectedPlatform, selectedAccount]);

  useEffect(() => {
    if (activeTab === 'overview') {
      fetchEngagement();
    }
  }, [activeTab, fetchEngagement]);

  // Fetch posts when Posts tab is active
  const fetchPosts = useCallback(async () => {
    setLoadingPosts(true);
    try {
      const data = await getPublishFeed({
        platform: selectedPlatform,
        accountId: selectedAccount,
        limit: 50,
      });
      setPosts(data.posts || []);
    } catch {
      toast.error('Failed to load posts');
    } finally {
      setLoadingPosts(false);
    }
  }, [selectedPlatform, selectedAccount]);

  useEffect(() => {
    if (activeTab === 'posts') {
      fetchPosts();
    }
  }, [activeTab, fetchPosts]);

  // Fetch demographics when tab is active
  const fetchDemographics = useCallback(async () => {
    setLoadingDemos(true);
    try {
      const data = await getAnalyticsDemographics({
        platform: selectedPlatform,
        accountId: selectedAccount,
      });
      setDemographics(data);
    } catch {
      toast.error('Failed to load demographics');
    } finally {
      setLoadingDemos(false);
    }
  }, [selectedPlatform, selectedAccount]);

  useEffect(() => {
    if (activeTab === 'demographics') {
      fetchDemographics();
    }
  }, [activeTab, fetchDemographics]);

  // Platform sidebar selection — auto-select account if only one exists
  const handlePlatformSelect = (plat) => {
    setSelectedPlatform(plat);
    if (plat) {
      const platAccounts = accounts.filter((a) => a.platform === plat);
      setSelectedAccount(platAccounts.length === 1 ? platAccounts[0].id : null);
    } else {
      setSelectedAccount(null);
    }
  };

  // Account dropdown selection
  const handleAccountChange = (accountId) => {
    setSelectedAccount(accountId || null);
  };

  // Sort posts
  const sortedPosts = [...posts].sort((a, b) => {
    const ma = a.metrics || {};
    const mb = b.metrics || {};
    if (postsSort === 'date') {
      const da = parseDate(a.published_at);
      const db = parseDate(b.published_at);
      return (db?.getTime() ?? 0) - (da?.getTime() ?? 0);
    }
    return (mb[postsSort] ?? 0) - (ma[postsSort] ?? 0);
  });

  // Platform engagement chart data
  const platformEngData = Object.entries(engagement?.platform_breakdown || {}).map(([plat, d]) => ({
    platform: plat,
    likes:    d.likes    || 0,
    comments: d.comments || 0,
    shares:   d.shares   || 0,
    views:    d.views    || 0,
  }));

  // Format timeline dates for display
  const timelineFormatted = timeline.map((t) => ({
    ...t,
    label: (() => {
      try { return format(parseISO(t.date), days <= 7 ? 'EEE' : 'MMM d'); }
      catch { return t.date; }
    })(),
  }));

  // Demographics only available for Instagram and Facebook
  const DEMOGRAPHICS_PLATFORMS = ['instagram', 'facebook'];
  const hasDemographics = !selectedPlatform
    ? accounts.some((a) => DEMOGRAPHICS_PLATFORMS.includes(a.platform))
    : DEMOGRAPHICS_PLATFORMS.includes(selectedPlatform);

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'posts',    label: 'Posts'    },
    ...(hasDemographics ? [{ id: 'demographics', label: 'Demographics' }] : []),
  ];

  // Accounts for the currently selected platform
  const platformAccounts = accounts.filter(
    (a) => !selectedPlatform || a.platform === selectedPlatform
  );
  const isNotConnected = selectedPlatform &&
    accounts.filter((a) => a.platform === selectedPlatform).length === 0;
  const SelectedIcon = selectedPlatform ? PLATFORM_ICONS[selectedPlatform] : null;
  const selectedColor = selectedPlatform ? (PLATFORM_COLORS[selectedPlatform] || '#6b7280') : null;

  return (
    <DashboardLayout hideSidebar>
      {/* ── Two-column layout: platform sidebar + content ─────────────── */}
      <div className="flex h-full overflow-hidden">

        {/* ── Left Platform Sidebar ──────────────────────────────────── */}
        <aside className="w-52 shrink-0 border-r border-gray-200 bg-offwhite overflow-y-auto hidden md:block">
          <PlatformSidebar
            accounts={accounts}
            selectedPlatform={selectedPlatform}
            onSelect={handlePlatformSelect}
          />
        </aside>

        {/* ── Right Content Area ─────────────────────────────────────── */}
        <div className="flex-1 min-w-0 overflow-y-auto">
          <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6">

        {/* ── Content header: account selector + date range ────────── */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
          {/* Left: platform icon + account selector */}
          <div className="flex items-center gap-3">
            {SelectedIcon && (
              <SelectedIcon size={22} style={{ color: selectedColor }} />
            )}
            {selectedPlatform && platformAccounts.length > 0 ? (
              /* Platform selected + has accounts → custom dropdown with avatars */
              <AccountDropdown
                accounts={platformAccounts}
                selectedId={selectedAccount}
                onSelect={handleAccountChange}
                platformLabel={PLATFORM_LABELS[selectedPlatform] || selectedPlatform}
                showAll={platformAccounts.length > 1}
              />
            ) : (
              /* No platform selected → show Analytics title */
              <h1 className="text-xl font-bold text-gray-900">Analytics</h1>
            )}
          </div>

          {/* Right: date range selector */}
          <div className="flex bg-gray-100 rounded-lg p-1">
            {DAYS_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setDays(opt.value)}
                className={`px-3 py-1.5 rounded-md text-sm font-semibold transition-all
                  ${days === opt.value
                    ? 'bg-offwhite text-indigo-600 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'}`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* ── Mobile platform pills (hidden on md+, shown on small screens) */}
        <div className="flex items-center gap-2 flex-wrap mb-5 md:hidden">
          <button
            onClick={() => handlePlatformSelect(null)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-all
              ${!selectedPlatform
                ? 'bg-indigo-600 border-indigo-600 text-white'
                : 'border-gray-200 text-gray-600 bg-offwhite hover:border-gray-300'}`}
          >
            All
          </button>
          {accounts.length > 0 && [...new Set(accounts.map((a) => a.platform))].map((plat) => (
            <PlatformPill
              key={plat}
              platform={plat}
              active={selectedPlatform === plat}
              onClick={() => handlePlatformSelect(plat)}
            />
          ))}
        </div>

        {/* ── Not connected state ──────────────────────────────────── */}
        {isNotConnected ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            {SelectedIcon && (
              <SelectedIcon size={48} style={{ color: selectedColor }} className="mb-4 opacity-30" />
            )}
            <p className="text-lg font-semibold text-gray-700">
              No {PLATFORM_LABELS[selectedPlatform] || selectedPlatform} account connected
            </p>
            <p className="text-sm text-gray-400 mt-1 mb-4">
              Connect your {PLATFORM_LABELS[selectedPlatform] || selectedPlatform} account to view analytics here.
            </p>
            <a
              href="/accounts"
              className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition-colors"
            >
              Connect Account →
            </a>
          </div>
        ) : (
          <>

        {/* ── LinkedIn API limitation notice ──────────────────────── */}
        {selectedPlatform === 'linkedin' && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <svg className="h-4 w-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
            </svg>
            LinkedIn's API does not provide engagement metrics (likes, comments, shares) for organic posts. Post counts and publishing data are available.
          </div>
        )}

        {/* ── Snapchat API limitation notice ──────────────────────── */}
        {selectedPlatform === 'snapchat' && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <svg className="h-4 w-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
            </svg>
            Snapchat's API does not support fetching organic post analytics. Only Snap Ads metrics are available through their Marketing API.
          </div>
        )}

        {/* ── Tabs ─────────────────────────────────────────────────── */}
        <div className="flex border-b border-gray-200 mb-6 gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2.5 text-sm font-semibold border-b-2 transition-all -mb-px
                ${activeTab === tab.id
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* ━━━━━━━━━━━━━━━━━ OVERVIEW TAB ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
        {activeTab === 'overview' && (
          <div className="space-y-6">

            {/* Engagement stat cards */}
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
              <EngagementCard
                icon={FaFileAlt}
                label="Posts Published"
                value={overview?.published_in_period}
                color="bg-indigo-500"
                loading={loadingOverview}
              />
              <EngagementCard
                icon={FaHeart}
                label="Total Likes"
                value={engagement?.totals?.total_likes}
                color="bg-rose-500"
                loading={loadingEngagement}
              />
              <EngagementCard
                icon={FaComment}
                label="Comments"
                value={engagement?.totals?.total_comments}
                color="bg-blue-500"
                loading={loadingEngagement}
              />
              <EngagementCard
                icon={FaShare}
                label="Shares"
                value={engagement?.totals?.total_shares}
                color="bg-emerald-500"
                loading={loadingEngagement}
              />
              <EngagementCard
                icon={FaEye}
                label="Views"
                value={engagement?.totals?.total_views}
                color="bg-purple-500"
                loading={loadingEngagement}
              />
            </div>

            {/* Engagement insights row */}
            {!loadingEngagement && engagement?.totals?.total_posts > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {/* Average engagement per post */}
                <div className="bg-offwhite rounded-xl border border-gray-200 p-4">
                  <p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-1">Avg. Engagement / Post</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {fmt(Math.round(
                      ((engagement.totals.total_likes || 0) + (engagement.totals.total_comments || 0) + (engagement.totals.total_shares || 0))
                      / (engagement.totals.total_posts || 1)
                    ))}
                  </p>
                  <p className="text-xs text-gray-400 mt-1">Likes + Comments + Shares per post</p>
                </div>

                {/* Best performing platform */}
                {(() => {
                  const breakdown = engagement?.platform_breakdown || {};
                  const best = Object.entries(breakdown).sort((a, b) => {
                    const engA = (a[1].likes || 0) + (a[1].comments || 0) + (a[1].shares || 0);
                    const engB = (b[1].likes || 0) + (b[1].comments || 0) + (b[1].shares || 0);
                    return engB - engA;
                  })[0];
                  if (!best) return null;
                  const [plat, data] = best;
                  const Icon = PLATFORM_ICONS[plat] || FaFileAlt;
                  const totalEng = (data.likes || 0) + (data.comments || 0) + (data.shares || 0);
                  return (
                    <div className="bg-offwhite rounded-xl border border-gray-200 p-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-1">Best Platform</p>
                      <div className="flex items-center gap-2">
                        <Icon style={{ color: PLATFORM_COLORS[plat] }} className="text-xl" />
                        <span className="text-2xl font-bold text-gray-900">{PLATFORM_LABELS[plat] || plat}</span>
                      </div>
                      <p className="text-xs text-gray-400 mt-1">{fmt(totalEng)} total engagement from {data.posts || 0} posts</p>
                    </div>
                  );
                })()}

                {/* Most viewed platform */}
                {(() => {
                  const breakdown = engagement?.platform_breakdown || {};
                  const best = Object.entries(breakdown).filter(([, d]) => (d.views || 0) > 0).sort((a, b) => (b[1].views || 0) - (a[1].views || 0))[0];
                  if (!best) return null;
                  const [plat, data] = best;
                  const Icon = PLATFORM_ICONS[plat] || FaFileAlt;
                  return (
                    <div className="bg-offwhite rounded-xl border border-gray-200 p-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-1">Most Viewed</p>
                      <div className="flex items-center gap-2">
                        <Icon style={{ color: PLATFORM_COLORS[plat] }} className="text-xl" />
                        <span className="text-2xl font-bold text-gray-900">{fmt(data.views)}</span>
                      </div>
                      <p className="text-xs text-gray-400 mt-1">Views on {PLATFORM_LABELS[plat] || plat}</p>
                    </div>
                  );
                })()}
              </div>
            )}

            {/* Charts row */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">

              {/* Posts Over Time */}
              <div className="bg-offwhite rounded-xl border border-gray-200 p-5">
                <h3 className="text-sm font-semibold text-gray-700 mb-4">Posts Published Over Time</h3>
                {loadingOverview ? (
                  <div className="h-48 bg-gray-100 animate-pulse rounded-lg" />
                ) : timeline.length === 0 ? (
                  <div className="h-48 flex items-center justify-center text-sm text-gray-400">No data</div>
                ) : (
                  <ResponsiveContainer width="100%" height={180}>
                    <AreaChart data={timelineFormatted} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
                      <defs>
                        <linearGradient id="colorPosts" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} width={28} />
                      <Tooltip content={<TimelineTooltip />} />
                      <Area type="monotone" dataKey="count" name="Posts" stroke="#6366f1" strokeWidth={2} fill="url(#colorPosts)" dot={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </div>

              {/* Platform Engagement Breakdown */}
              <div className="bg-offwhite rounded-xl border border-gray-200 p-5">
                <h3 className="text-sm font-semibold text-gray-700 mb-4">Engagement by Platform</h3>
                {loadingEngagement ? (
                  <div className="h-48 bg-gray-100 animate-pulse rounded-lg" />
                ) : platformEngData.length === 0 ? (
                  <div className="h-48 flex items-center justify-center text-sm text-gray-400">No engagement data</div>
                ) : (
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={platformEngData} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis
                        dataKey="platform"
                        tick={{ fontSize: 11, fill: '#9ca3af' }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v) => PLATFORM_LABELS[v]?.split(' ')[0] || v}
                      />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} width={40} />
                      <Tooltip content={<EngagementTooltip />} />
                      <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
                      <Bar dataKey="likes" name="Likes" stackId="engagement" fill="#ef4444" radius={[0, 0, 0, 0]} />
                      <Bar dataKey="comments" name="Comments" stackId="engagement" fill="#3b82f6" />
                      <Bar dataKey="shares" name="Shares" stackId="engagement" fill="#22c55e" />
                      <Bar dataKey="views" name="Views" stackId="engagement" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>

            {/* Post type breakdown */}
            {overview && (
              <div className="bg-offwhite rounded-xl border border-gray-200 p-5">
                <h3 className="text-sm font-semibold text-gray-700 mb-4">Posts by Type</h3>
                {loadingOverview ? (
                  <div className="h-10 bg-gray-100 animate-pulse rounded-lg" />
                ) : (
                  <div className="space-y-3">
                    {[
                      { key: 'text',  label: 'Text',  color: '#6366f1' },
                      { key: 'image', label: 'Image', color: '#22c55e' },
                      { key: 'video', label: 'Video', color: '#f59e0b' },
                    ].map(({ key, label, color }) => {
                      const count = overview.type_counts?.[key] || 0;
                      const total = overview.published_in_period || 1;
                      const pct = Math.round((count / total) * 100);
                      return (
                        <div key={key} className="flex items-center gap-3">
                          <span className="text-sm text-gray-600 w-12">{label}</span>
                          <div className="flex-1 h-2.5 bg-gray-100 rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full transition-all"
                              style={{ width: `${pct}%`, background: color }}
                            />
                          </div>
                          <span className="text-sm text-gray-500 w-16 text-right">{count} ({pct}%)</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* Top performing posts */}
            <div className="bg-offwhite rounded-xl border border-gray-200 p-5">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">Top Performing Posts</h3>
              {loadingEngagement ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-14 bg-gray-100 animate-pulse rounded-lg" />
                  ))}
                </div>
              ) : !engagement?.top_posts?.length ? (
                <div className="py-8 text-center text-sm text-gray-400">
                  No posts with engagement data yet. Connect accounts and publish posts to see results here.
                </div>
              ) : (
                <div className="space-y-2">
                  {(engagement?.top_posts || []).slice(0, 5).map((post, i) => {
                    const plat = post.platform || 'unknown';
                    const Icon = PLATFORM_ICONS[plat] || FaFileAlt;
                    const color = PLATFORM_COLORS[plat] || '#6b7280';
                    const m = post.metrics || {};
                    const dt = parseDate(post.published_at);
                    return (
                      <div key={i} className="flex items-center gap-3 p-3 rounded-lg hover:bg-gray-50 transition-colors">
                        <span className="w-5 text-center text-xs font-bold text-gray-400">{i + 1}</span>
                        <Icon style={{ color, flexShrink: 0 }} className="text-base" />
                        {post.media_url && (
                          <img
                            src={post.media_url}
                            alt=""
                            className="w-10 h-10 rounded-lg object-cover flex-shrink-0"
                            onError={(e) => { e.target.style.display = 'none'; }}
                          />
                        )}
                        <p className="flex-1 text-sm text-gray-700 truncate min-w-0">
                          {post.content || '(no caption)'}
                        </p>
                        <div className="flex items-center gap-3 flex-shrink-0 text-xs text-gray-500">
                          {m.likes != null && <span className="flex items-center gap-1"><FaHeart className="text-rose-400" />{fmt(m.likes)}</span>}
                          {m.comments != null && <span className="flex items-center gap-1"><FaComment className="text-blue-400" />{fmt(m.comments)}</span>}
                          {m.shares != null && <span className="flex items-center gap-1"><FaShare className="text-green-400" />{fmt(m.shares)}</span>}
                          {m.views != null && <span className="flex items-center gap-1"><FaEye className="text-purple-400" />{fmt(m.views)}</span>}
                          {dt && <span className="text-gray-400 hidden sm:block">{format(dt, 'MMM d')}</span>}
                          {post.post_url && (
                            <a href={post.post_url} target="_blank" rel="noopener noreferrer" className="text-indigo-500 hover:text-indigo-700">
                              <FaExternalLinkAlt />
                            </a>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Platform summary table */}
            {overview?.platform_counts && Object.keys(overview.platform_counts).length > 0 && (
              <div className="bg-offwhite rounded-xl border border-gray-200 p-5">
                <h3 className="text-sm font-semibold text-gray-700 mb-4">Platform Summary</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs font-semibold text-gray-400 uppercase tracking-wide border-b border-gray-100">
                        <th className="text-left py-2 pr-4">Platform</th>
                        <th className="text-right py-2 pr-4">Posts</th>
                        <th className="text-right py-2 pr-4">Likes</th>
                        <th className="text-right py-2 pr-4">Comments</th>
                        <th className="text-right py-2 pr-4">Shares</th>
                        <th className="text-right py-2 pr-4">Views</th>
                        <th className="text-right py-2">Eng. Rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(overview.platform_counts)
                        .sort((a, b) => b[1] - a[1])
                        .map(([plat, count]) => {
                          const Icon = PLATFORM_ICONS[plat] || FaFileAlt;
                          const color = PLATFORM_COLORS[plat] || '#6b7280';
                          const pd = engagement?.platform_breakdown?.[plat] || {};
                          const sup = PLATFORM_METRICS[plat] || {};
                          return (
                            <tr key={plat} className="border-b border-gray-50 hover:bg-gray-50">
                              <td className="py-2.5 pr-4">
                                <div className="flex items-center gap-2">
                                  <Icon style={{ color }} className="text-base" />
                                  <span className="font-medium text-gray-700">{PLATFORM_LABELS[plat] || plat}</span>
                                </div>
                              </td>
                              <td className="text-right py-2.5 pr-4 font-semibold text-gray-900">{count}</td>
                              <td className="text-right py-2.5 pr-4 text-gray-600">{sup.likes ? fmt(pd.likes ?? 0) : '—'}</td>
                              <td className="text-right py-2.5 pr-4 text-gray-600">{sup.comments ? fmt(pd.comments ?? 0) : '—'}</td>
                              <td className="text-right py-2.5 pr-4 text-gray-600">{sup.shares ? fmt(pd.shares ?? 0) : '—'}</td>
                              <td className="text-right py-2.5 pr-4 text-gray-600">{sup.views ? fmt(pd.views ?? 0) : '—'}</td>
                              <td className="text-right py-2.5 text-gray-600">
                                {pd.posts > 0 && (sup.likes || sup.comments || sup.shares)
                                  ? (((pd.likes || 0) + (pd.comments || 0) + (pd.shares || 0)) / pd.posts).toFixed(1)
                                  : '—'
                                }
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

          </div>
        )}

        {/* ━━━━━━━━━━━━━━━━━ POSTS TAB ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
        {activeTab === 'posts' && (
          <div className="space-y-4">

            {/* Controls row */}
            <div className="flex items-center gap-2 flex-wrap">
              <FaSortAmountDown className="text-gray-400 text-sm" />
              <span className="text-sm text-gray-500 mr-1">Sort by:</span>
              {SORT_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setPostsSort(opt.value)}
                  className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-all
                    ${postsSort === opt.value
                      ? 'bg-indigo-600 border-indigo-600 text-white'
                      : 'border-gray-200 text-gray-600 bg-offwhite hover:border-gray-300'}`}
                >
                  {opt.label}
                </button>
              ))}
              {loadingPosts && (
                <span className="text-xs text-gray-400 ml-auto animate-pulse">Loading...</span>
              )}
              {!loadingPosts && (
                <span className="text-xs text-gray-400 ml-auto">{sortedPosts.length} posts</span>
              )}
            </div>

            {/* Post summary stats */}
            {!loadingPosts && sortedPosts.length > 0 && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { label: 'Total Likes',    val: sortedPosts.reduce((s, p) => s + (p.metrics?.likes || 0), 0),    icon: FaHeart,   color: 'text-rose-500'   },
                  { label: 'Total Comments', val: sortedPosts.reduce((s, p) => s + (p.metrics?.comments || 0), 0), icon: FaComment, color: 'text-blue-500'   },
                  { label: 'Total Shares',   val: sortedPosts.reduce((s, p) => s + (p.metrics?.shares || 0), 0),   icon: FaShare,   color: 'text-green-500'  },
                  { label: 'Total Views',    val: sortedPosts.reduce((s, p) => s + (p.metrics?.views || 0), 0),    icon: FaEye,     color: 'text-purple-500' },
                ].map(({ label, val, icon: Icon, color }) => (
                  <div key={label} className="bg-offwhite rounded-xl border border-gray-200 p-4 flex items-center gap-3">
                    <Icon className={`${color} text-lg`} />
                    <div>
                      <p className="text-xs text-gray-500">{label}</p>
                      <p className="text-lg font-bold text-gray-900">{fmt(val)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Post list */}
            {loadingPosts ? (
              <div className="space-y-3">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="bg-offwhite rounded-xl border border-gray-200 p-4 flex gap-4">
                    <div className="w-20 h-20 bg-gray-100 animate-pulse rounded-lg flex-shrink-0" />
                    <div className="flex-1 space-y-2">
                      <div className="h-3 bg-gray-100 animate-pulse rounded w-1/3" />
                      <div className="h-3 bg-gray-100 animate-pulse rounded w-2/3" />
                      <div className="h-3 bg-gray-100 animate-pulse rounded w-1/2" />
                    </div>
                  </div>
                ))}
              </div>
            ) : sortedPosts.length === 0 ? (
              <div className="bg-offwhite rounded-xl border border-gray-200 py-16 text-center">
                <FaFileAlt className="text-4xl text-gray-300 mx-auto mb-3" />
                <p className="text-gray-500 font-medium">No published posts found</p>
                <p className="text-sm text-gray-400 mt-1">
                  {selectedPlatform ? `No posts from ${PLATFORM_LABELS[selectedPlatform]} yet.` : 'Connect social accounts and publish posts to see analytics here.'}
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {sortedPosts.map((post, i) => (
                  <PostCard key={post.platform_post_id || i} post={post} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* ━━━━━━━━━━━━━━━━━ DEMOGRAPHICS TAB ━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
        {activeTab === 'demographics' && (
          <div className="space-y-6">
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
              <strong>Note:</strong> Follower demographics are available for Instagram Business/Creator accounts (100+ followers) and Facebook Pages.
              {demographics?.accounts_used?.length > 0 && (
                <span className="ml-1">Showing data from: <strong>{demographics.accounts_used.join(', ')}</strong></span>
              )}
            </div>

            {demographics?.errors?.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-sm text-amber-800">
                {demographics.errors.map((e, i) => (
                  <p key={i}><strong>{e.account}:</strong> {e.error}</p>
                ))}
              </div>
            )}

            {loadingDemos ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="bg-offwhite rounded-xl border border-gray-200 p-5">
                    <div className="h-4 bg-gray-100 animate-pulse rounded w-1/3 mb-4" />
                    <div className="h-40 bg-gray-100 animate-pulse rounded-lg" />
                  </div>
                ))}
              </div>
            ) : !demographics?.supported ? (
              <div className="bg-offwhite rounded-xl border border-gray-200 p-8 text-center">
                <p className="text-gray-500 font-medium">Demographics not available</p>
                <p className="text-sm text-gray-400 mt-1">{demographics?.message || 'Connect an Instagram Business or Facebook Page account to see demographics.'}</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Age Distribution */}
                <div className="bg-offwhite rounded-xl border border-gray-200 p-5">
                  <h4 className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-4">Age Distribution</h4>
                  {demographics?.demographics?.age?.length > 0 ? (
                    <ResponsiveContainer width="100%" height={200}>
                      <BarChart data={demographics.demographics.age} layout="vertical" margin={{ top: 0, right: 10, bottom: 0, left: 40 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis type="number" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                        <YAxis dataKey="range" type="category" tick={{ fontSize: 11, fill: '#6b7280' }} tickLine={false} axisLine={false} width={50} />
                        <Tooltip />
                        <Bar dataKey="count" name="Followers" fill="#6366f1" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-40 flex items-center justify-center text-sm text-gray-400">No age data</div>
                  )}
                </div>

                {/* Gender Breakdown */}
                <div className="bg-offwhite rounded-xl border border-gray-200 p-5">
                  <h4 className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-4">Gender Breakdown</h4>
                  {demographics?.demographics?.gender?.length > 0 ? (
                    <div className="space-y-3 mt-2">
                      {demographics.demographics.gender.map((g) => {
                        const total = demographics.demographics.gender.reduce((s, x) => s + x.count, 0) || 1;
                        const pct = Math.round((g.count / total) * 100);
                        const colors = { Male: '#3b82f6', Female: '#ec4899', Other: '#8b5cf6' };
                        return (
                          <div key={g.label}>
                            <div className="flex justify-between text-sm mb-1">
                              <span className="text-gray-700 font-medium">{g.label}</span>
                              <span className="text-gray-500">{fmt(g.count)} ({pct}%)</span>
                            </div>
                            <div className="h-3 bg-gray-100 rounded-full overflow-hidden">
                              <div className="h-full rounded-full" style={{ width: `${pct}%`, background: colors[g.label] || '#6b7280' }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="h-40 flex items-center justify-center text-sm text-gray-400">No gender data</div>
                  )}
                </div>

                {/* Top Cities */}
                <div className="bg-offwhite rounded-xl border border-gray-200 p-5">
                  <h4 className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-4">Top Cities</h4>
                  {demographics?.demographics?.cities?.length > 0 ? (
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={demographics.demographics.cities.slice(0, 10)} layout="vertical" margin={{ top: 0, right: 10, bottom: 0, left: 80 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis type="number" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                        <YAxis dataKey="name" type="category" tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} axisLine={false} width={80} />
                        <Tooltip />
                        <Bar dataKey="count" name="Followers" fill="#22c55e" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-40 flex items-center justify-center text-sm text-gray-400">No city data</div>
                  )}
                </div>

                {/* Top Countries */}
                <div className="bg-offwhite rounded-xl border border-gray-200 p-5">
                  <h4 className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-4">Top Countries</h4>
                  {demographics?.demographics?.countries?.length > 0 ? (
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={demographics.demographics.countries.slice(0, 10)} layout="vertical" margin={{ top: 0, right: 10, bottom: 0, left: 40 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis type="number" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                        <YAxis dataKey="name" type="category" tick={{ fontSize: 11, fill: '#6b7280' }} tickLine={false} axisLine={false} width={40} />
                        <Tooltip />
                        <Bar dataKey="count" name="Followers" fill="#f59e0b" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-40 flex items-center justify-center text-sm text-gray-400">No country data</div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

          </>
        )}
          </div>{/* closes max-w-5xl */}
        </div>{/* closes flex-1 overflow-y-auto */}
      </div>{/* closes flex h-full */}
    </DashboardLayout>
  );
};

export default Analytics;
