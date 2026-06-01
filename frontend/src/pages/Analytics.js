import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import {
  getAnalyticsOverview,
  getAnalyticsTimeline,
  getAnalyticsEngagement,
  getAnalyticsDemographics,
  getInstagramAnalyticsReport,
  getBlueskyAnalyticsReport,
  getYoutubeAnalyticsReport,
  getTikTokAnalyticsReport,
  getSocialAccounts,
  getPublishFeed,
} from '@/lib/api';
import { toast } from 'sonner';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, Legend, PieChart, Pie, Line, ComposedChart, Sector,
} from 'recharts';
import { ComposableMap, Geographies, Geography } from 'react-simple-maps';
import {
  FaHeart, FaComment, FaShare, FaEye, FaFileAlt, FaExternalLinkAlt,
  FaInstagram, FaFacebook, FaTwitter, FaLinkedin, FaYoutube, FaTiktok,
  FaDiscord, FaUsers, FaChartLine, FaBullseye,
  FaPinterest, FaReddit, FaSnapchat, FaSortAmountDown, FaChevronDown, FaGripLines, FaReply, FaRetweet, FaQuoteRight, FaInfoCircle,
} from 'react-icons/fa';
import { SiThreads, SiBluesky, SiMastodon } from 'react-icons/si';
import worldGeo from 'world-atlas/countries-110m.json';
import {
  eachDayOfInterval,
  eachMonthOfInterval,
  eachQuarterOfInterval,
  eachWeekOfInterval,
  endOfDay,
  endOfMonth,
  endOfQuarter,
  endOfWeek,
  format,
  isValid,
  parseISO,
  startOfDay,
  startOfMonth,
  startOfQuarter,
  startOfWeek,
  subDays,
} from 'date-fns';

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
  discord:   '#5865F2',
  mastodon:  '#6364FF',
};

const PLATFORM_LABELS = {
  instagram: 'Instagram', twitter: 'Twitter / X', facebook: 'Facebook',
  linkedin: 'LinkedIn', youtube: 'YouTube', tiktok: 'TikTok',
  pinterest: 'Pinterest', threads: 'Threads', bluesky: 'Bluesky',
  reddit: 'Reddit', snapchat: 'Snapchat', discord: 'Discord', mastodon: 'Mastodon',
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
  discord:   FaDiscord,
  mastodon:  SiMastodon,
};

// Metrics that each platform supports (false = not available from API)
const PLATFORM_METRICS = {
  instagram: { likes: true,  comments: true,  shares: false, views: false },
  facebook:  { likes: true,  comments: true,  shares: true,  views: false },
  twitter:   { likes: true,  comments: true,  shares: true,  views: false },
  tiktok:    { likes: true,  comments: true,  shares: true,  views: true  },
  threads:   { likes: true,  comments: true,  shares: true,  views: true  },
  reddit:    { likes: true,  comments: true,  shares: false, views: true  },
  pinterest: { likes: true,  comments: true,  shares: false, views: true  },
  youtube:   { likes: true,  comments: true,  shares: false, views: true  },
  linkedin:  { likes: false, comments: false, shares: false, views: false },
  bluesky:   { likes: true,  comments: true,  shares: true,  views: false },
  snapchat:  { likes: false, comments: false, shares: false, views: false },
  discord:   { likes: false, comments: false, shares: false, views: false },
  mastodon:  { likes: true,  comments: true,  shares: true,  views: false },
};

const ALL_PLATFORMS = [
  'instagram', 'facebook', 'twitter', 'linkedin', 'youtube',
  'tiktok', 'pinterest', 'threads', 'bluesky', 'snapchat', 'reddit', 'discord', 'mastodon',
];

const PLATFORM_ORDER_STORAGE_KEY_PREFIX = 'analytics_platform_order_v1';

const PLATFORM_NOTICES = {
  linkedin: 'LinkedIn can show followers, follower growth, and organization impressions when the connected account has the required analytics scopes and page admin access. Post engagement metrics remain limited.',
  snapchat: "Snapchat's current integration does not expose organic post analytics. Only publishing history can be shown where available.",
  twitter: 'X can show recent posts plus likes, replies, and reposts. View counts are not available from the current API integration.',
  threads: 'Threads can show recent posts plus likes, replies, reposts, and views when Meta returns them.',
  discord: 'Discord uses incoming webhooks for publishing, so analytics can only show posts published from Unravler.',
  tiktok: 'TikTok post analytics depend on the scopes granted when the account was connected. If video list access is unavailable, Unravler falls back to posts published from the app.',
  pinterest: 'Pinterest can show pins with saves, comments, and impressions when the API returns them. Share counts are not available.',
  bluesky: 'Bluesky can show recent posts plus likes, replies, and reposts. View counts are not available from the API.',
  mastodon: 'Mastodon can show recent statuses plus favourites, replies, and boosts. View counts are not available.',
};

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

const BLUESKY_GRANULARITY_OPTIONS = [
  { label: 'Day', value: 'day' },
  { label: 'Week', value: 'week' },
  { label: 'Month', value: 'month' },
  { label: 'Quarter', value: 'quarter' },
];

const COUNTRY_NAME_OVERRIDES = {
  US: 'United States of America',
  GB: 'United Kingdom',
  KR: 'South Korea',
  RU: 'Russia',
  SY: 'Syria',
  LA: 'Laos',
  KP: 'North Korea',
  IR: 'Iran',
  TZ: 'Tanzania',
  VE: 'Venezuela',
  VN: 'Vietnam',
  BO: 'Bolivia',
  MD: 'Moldova',
  TW: 'Taiwan',
};

const regionNames = typeof Intl !== 'undefined' && Intl.DisplayNames
  ? new Intl.DisplayNames(['en'], { type: 'region' })
  : null;

// ── Helpers ────────────────────────────────────────────────────────────────────
const fmt = (n) => {
  if (n == null) return '—';
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000)    return (n / 1000).toFixed(1) + 'K';
  return String(n);
};

const supportedMetricsFor = (platform) => {
  if (!platform) return { likes: true, comments: true, shares: true, views: true };
  return PLATFORM_METRICS[platform] || { likes: false, comments: false, shares: false, views: false };
};

const metricIsSupported = (platform, metric) => !!supportedMetricsFor(platform)?.[metric];

const hasAnyEngagementMetrics = (platform) =>
  ['likes', 'comments', 'shares', 'views'].some((metric) => metricIsSupported(platform, metric));

const parseDate = (val) => {
  if (!val) return null;
  try {
    const dt = parseISO(val.replace('Z', ''));
    return isValid(dt) ? dt : null;
  } catch { return null; }
};

const pctLabel = (value) => {
  if (value == null || Number.isNaN(value)) return null;
  const rounded = Math.round(value * 10) / 10;
  return `${rounded > 0 ? '+' : ''}${rounded}%`;
};

const chartEmptyState = (label = 'No data available currently for this report.') => (
  <div className="h-40 flex items-center justify-center text-sm text-gray-400 text-center px-6">
    {label}
  </div>
);

const normalizePlatformOrder = (order) => {
  const incoming = Array.isArray(order) ? order : [];
  const valid = incoming.filter((platform, index) => ALL_PLATFORMS.includes(platform) && incoming.indexOf(platform) === index);
  const missing = ALL_PLATFORMS.filter((platform) => !valid.includes(platform));
  return [...valid, ...missing];
};

const mergeSeriesByDate = (seriesMap) => {
  const dates = new Set();
  Object.values(seriesMap || {}).forEach((series) => {
    (series || []).forEach((point) => {
      if (point?.date) dates.add(point.date);
    });
  });

  return [...dates]
    .sort()
    .map((date) => {
      const row = { date };
      Object.entries(seriesMap || {}).forEach(([key, series]) => {
        const point = (series || []).find((item) => item.date === date);
        row[key] = point?.count || 0;
      });
      return row;
    });
};

const formatBucketLabel = (date, granularity) => {
  if (!date) return '';
  if (granularity === 'quarter') return format(date, "QQQ ''yy");
  if (granularity === 'month') return format(date, "MMM ''yy");
  if (granularity === 'week') return format(date, 'd MMM');
  return format(date, 'd MMM');
};

const buildTimeBuckets = (days, granularity) => {
  const end = endOfDay(new Date());
  const start = startOfDay(subDays(end, Math.max(days - 1, 0)));

  if (granularity === 'week') {
    return eachWeekOfInterval({ start, end }, { weekStartsOn: 1 }).map((bucketStart) => ({
      key: format(startOfWeek(bucketStart, { weekStartsOn: 1 }), 'yyyy-MM-dd'),
      start: startOfWeek(bucketStart, { weekStartsOn: 1 }),
      end: endOfWeek(bucketStart, { weekStartsOn: 1 }),
      label: formatBucketLabel(startOfWeek(bucketStart, { weekStartsOn: 1 }), 'week'),
    }));
  }

  if (granularity === 'month') {
    return eachMonthOfInterval({ start, end }).map((bucketStart) => ({
      key: format(startOfMonth(bucketStart), 'yyyy-MM-dd'),
      start: startOfMonth(bucketStart),
      end: endOfMonth(bucketStart),
      label: formatBucketLabel(startOfMonth(bucketStart), 'month'),
    }));
  }

  if (granularity === 'quarter') {
    return eachQuarterOfInterval({ start, end }).map((bucketStart) => ({
      key: format(startOfQuarter(bucketStart), 'yyyy-MM-dd'),
      start: startOfQuarter(bucketStart),
      end: endOfQuarter(bucketStart),
      label: formatBucketLabel(startOfQuarter(bucketStart), 'quarter'),
    }));
  }

  return eachDayOfInterval({ start, end }).map((bucketStart) => ({
    key: format(startOfDay(bucketStart), 'yyyy-MM-dd'),
    start: startOfDay(bucketStart),
    end: endOfDay(bucketStart),
    label: formatBucketLabel(startOfDay(bucketStart), 'day'),
  }));
};

const bucketSeriesByGranularity = (series, days, granularity) => {
  const buckets = buildTimeBuckets(days, granularity);
  const normalized = (series || [])
    .map((point) => {
      const parsed = parseDate(point?.date);
      return parsed ? { when: parsed, count: Number(point?.count) || 0 } : null;
    })
    .filter(Boolean);

  return buckets.map((bucket) => ({
    date: bucket.key,
    label: bucket.label,
    count: normalized.reduce((sum, point) => (
      point.when >= bucket.start && point.when <= bucket.end ? sum + point.count : sum
    ), 0),
  }));
};

const mergeBucketedSeries = (seriesMap, days, granularity) => {
  const buckets = buildTimeBuckets(days, granularity);
  const normalizedSeries = Object.fromEntries(
    Object.entries(seriesMap || {}).map(([key, series]) => ([
      key,
      (series || [])
        .map((point) => {
          const parsed = parseDate(point?.date);
          return parsed ? { when: parsed, count: Number(point?.count) || 0 } : null;
        })
        .filter(Boolean),
    ])),
  );

  return buckets.map((bucket) => {
    const row = { date: bucket.key, label: bucket.label };
    Object.entries(normalizedSeries).forEach(([key, series]) => {
      row[key] = series.reduce((sum, point) => (
        point.when >= bucket.start && point.when <= bucket.end ? sum + point.count : sum
      ), 0);
    });
    return row;
  });
};

const chartHasData = (rows, keys) => (
  (rows || []).some((row) => keys.some((key) => Math.abs(Number(row?.[key]) || 0) > 0))
);

const formatReportDate = (date, days) => {
  try { return format(parseISO(date), days <= 7 ? 'EEE' : 'MMM d'); }
  catch { return date; }
};

const formatPreciseMetric = (value) => {
  if (value == null) return '—';
  const num = Number(value) || 0;
  if (Number.isInteger(num)) return fmt(num);
  return num.toFixed(num >= 10 ? 1 : 4).replace(/\.?0+$/, '');
};

const formatDurationSeconds = (value) => {
  const totalSeconds = Math.max(Number(value) || 0, 0);
  if (!totalSeconds) return '0s';
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.round(totalSeconds % 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
};

const formatPercentageMetric = (value) => {
  const num = Number(value) || 0;
  return `${num.toFixed(num >= 10 ? 1 : 2).replace(/\.?0+$/, '')}%`;
};

const formatAnalyticsDate = (value, includeTime = false) => {
  if (!value) return '';
  try {
    return format(parseISO(String(value)), includeTime ? 'MMM d, yyyy h:mm a' : 'MMM d, yyyy');
  } catch {
    return String(value);
  }
};

const formatAutoRefreshInterval = (seconds) => {
  const totalSeconds = Number(seconds) || 0;
  if (!totalSeconds) return '';
  if (totalSeconds % 3600 === 0) {
    const hours = totalSeconds / 3600;
    return `${hours} hour${hours === 1 ? '' : 's'}`;
  }
  if (totalSeconds % 60 === 0) {
    const minutes = totalSeconds / 60;
    return `${minutes} minute${minutes === 1 ? '' : 's'}`;
  }
  return `${totalSeconds} seconds`;
};

const bucketMultiValueSeries = (rows, days, granularity, keys) => mergeBucketedSeries(
  Object.fromEntries(
    keys.map((key) => [
      key,
      (rows || []).map((row) => ({
        date: row.date,
        count: Number(row?.[key]) || 0,
      })),
    ]),
  ),
  days,
  granularity,
);

const bucketYoutubeWatchQualitySeries = (rows, days, granularity) => {
  const buckets = buildTimeBuckets(days, granularity);
  const normalized = (rows || [])
    .map((point) => {
      const when = parseDate(point?.date);
      return when ? {
        when,
        engaged_views: Number(point?.engaged_views) || 0,
        views: Number(point?.views) || 0,
        average_view_duration_seconds: Number(point?.average_view_duration_seconds) || 0,
        average_view_percentage: Number(point?.average_view_percentage) || 0,
      } : null;
    })
    .filter(Boolean);

  return buckets.map((bucket) => {
    const bucketRows = normalized.filter((point) => point.when >= bucket.start && point.when <= bucket.end);
    const totalViews = bucketRows.reduce((sum, point) => sum + point.views, 0);
    const totalEngagedViews = bucketRows.reduce((sum, point) => sum + point.engaged_views, 0);
    const durationWeighted = bucketRows.reduce((sum, point) => sum + (point.average_view_duration_seconds * point.views), 0);
    const percentageWeighted = bucketRows.reduce((sum, point) => sum + (point.average_view_percentage * point.views), 0);

    return {
      date: bucket.key,
      label: bucket.label,
      engaged_views: totalEngagedViews,
      average_view_duration_seconds: totalViews > 0 ? durationWeighted / totalViews : 0,
      average_view_percentage: totalViews > 0 ? percentageWeighted / totalViews : 0,
      views: totalViews,
    };
  });
};

const countryNameForCode = (code) => {
  const normalized = String(code || '').toUpperCase();
  if (!normalized) return '';
  return COUNTRY_NAME_OVERRIDES[normalized] || regionNames?.of(normalized) || normalized;
};

const percentForBreakdown = (value, total) => {
  if (!total) return 0;
  return Math.round(((Number(value) || 0) / total) * 100);
};

const normalizeYoutubeGeographyCard = (payload, fallbackMetricLabel) => {
  if (Array.isArray(payload)) {
    return {
      rows: payload,
      metricLabel: fallbackMetricLabel,
      meta: null,
      emptyLabel: 'No data available currently for this report.',
    };
  }

  const normalizedPayload = payload && typeof payload === 'object' ? payload : {};
  return {
    rows: normalizedPayload.rows || [],
    metricLabel: normalizedPayload.metric_label || fallbackMetricLabel,
    meta: normalizedPayload,
    emptyLabel: normalizedPayload.provider_message || 'YouTube did not return geography data for this channel in the selected period.',
  };
};

const pctPillColor = (value) => (
  value >= 0 ? 'text-emerald-600' : 'text-rose-600'
);

const aggregateAudienceSupport = (accounts) => ({
  followers_total: accounts.some((account) => account?.supports?.followers_total && account?.followers_count != null),
  followers_growth: accounts.some((account) => account?.supports?.followers_growth && account?.followers_growth != null),
  reach: accounts.some((account) => account?.supports?.reach && account?.reach != null),
  impressions: accounts.some((account) => account?.supports?.impressions && account?.impressions != null),
});

const selectedPlatformAudienceSupport = (platform, computedSupport) => {
  if (platform !== 'linkedin') return computedSupport;
  return {
    ...computedSupport,
    followers_total: true,
    followers_growth: true,
    reach: true,
    impressions: true,
  };
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

const AudienceGrowthTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const value = Number(payload[0]?.value) || 0;
  const isNegative = value < 0;
  return (
    <div className="bg-offwhite border border-gray-200 rounded-lg px-3 py-2 shadow-lg text-sm">
      <p className="font-semibold text-gray-700">{label}</p>
      <p className={isNegative ? 'text-rose-600' : 'text-indigo-600'}>
        {fmt(value)} net followers
      </p>
    </div>
  );
};

const InstagramMetricTile = ({ title, value, subtitle, deltaPct, info }) => {
  const numericValue = typeof value === 'number' ? value : Number(value);
  const isNegativeValue = Number.isFinite(numericValue) && numericValue < 0;

  return (
    <div className="bg-offwhite rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-2">
        <p className="text-xs font-bold uppercase tracking-widest text-gray-400">{title}</p>
        {info ? <InfoHint text={info} /> : null}
      </div>
      <div className="mt-3 flex items-end gap-3">
        <p className={`text-5xl font-bold tracking-tight ${isNegativeValue ? 'text-rose-600' : 'text-sky-600'}`}>
          {fmt(value)}
        </p>
        {deltaPct != null && (
          <span className={`text-sm font-semibold ${deltaPct >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
            {pctLabel(deltaPct)}
          </span>
        )}
      </div>
      {subtitle && <p className="mt-3 text-sm text-gray-500">{subtitle}</p>}
    </div>
  );
};

const InstagramDetailCard = ({ title, children, action, info }) => (
  <div className="bg-offwhite rounded-xl border border-gray-200 p-5">
    <div className="flex items-center justify-between gap-3 mb-4">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
        {info ? <InfoHint text={info} /> : null}
      </div>
      {action || null}
    </div>
    {children}
  </div>
);

const ReportMetricTile = ({ title, value, subtitle, deltaPct, accent = 'text-sky-600', valueFormatter = fmt }) => (
  <div className="bg-offwhite rounded-xl border border-gray-200 p-5">
    <p className="text-xs font-bold uppercase tracking-widest text-gray-400">{title}</p>
    <div className="mt-3 flex items-end gap-3">
      <p className={`text-5xl font-bold tracking-tight ${accent}`}>{valueFormatter(value)}</p>
      {deltaPct != null && (
        <span className={`text-sm font-semibold ${pctPillColor(deltaPct)}`}>
          {pctLabel(deltaPct)}
        </span>
      )}
    </div>
    {subtitle && <p className="mt-3 text-sm text-gray-500">{subtitle}</p>}
  </div>
);

const InfoHint = ({ text }) => (
  <div className="group relative inline-flex">
    <span className="inline-flex h-5 w-5 items-center justify-center rounded-full text-gray-400 transition-colors group-hover:text-sky-600">
      <FaInfoCircle className="h-4 w-4" />
    </span>
    <div className="pointer-events-none absolute left-1/2 top-[calc(100%+10px)] z-20 w-64 -translate-x-1/2 rounded-xl border border-gray-200 bg-white px-3 py-2 text-xs font-medium leading-5 text-gray-600 opacity-0 shadow-xl transition-all duration-150 group-hover:opacity-100">
      {text}
    </div>
  </div>
);

const renderActiveDonutShape = (props) => (
  <Sector
    {...props}
    outerRadius={(props.outerRadius || 0) + 10}
    stroke="#ffffff"
    strokeWidth={3}
  />
);

const InteractiveDonutChart = ({
  data,
  dataKey,
  nameKey = 'label',
  colors,
  innerRadius,
  outerRadius,
  paddingAngle = 2,
  centerContent,
  getItemKey = (item) => item.value || item.type || item.label,
  emptyRing,
}) => {
  const [activeIndex, setActiveIndex] = useState(-1);

  if (!data.length) {
    return emptyRing || null;
  }

  return (
    <div className="relative h-full w-full">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            activeIndex={activeIndex >= 0 ? activeIndex : undefined}
            activeShape={renderActiveDonutShape}
            data={data}
            dataKey={dataKey}
            nameKey={nameKey}
            cx="50%"
            cy="50%"
            innerRadius={innerRadius}
            outerRadius={outerRadius}
            paddingAngle={paddingAngle}
            onMouseEnter={(_, index) => setActiveIndex(index)}
            onMouseLeave={() => setActiveIndex(-1)}
          >
            {data.map((item, index) => (
              <Cell
                key={getItemKey(item)}
                fill={colors[index % colors.length]}
                fillOpacity={activeIndex === -1 || activeIndex === index ? 1 : 0.32}
                style={{ cursor: 'pointer', transition: 'fill-opacity 160ms ease' }}
              />
            ))}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
      {centerContent ? (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
          {centerContent}
        </div>
      ) : null}
    </div>
  );
};

const ReportCard = ({ title, children, action, info }) => (
  <div className="bg-offwhite rounded-xl border border-gray-200 p-5">
    <div className="flex items-center justify-between gap-3 mb-4">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
        {info ? <InfoHint text={info} /> : null}
      </div>
      {action || null}
    </div>
    {children}
  </div>
);

const ReportDonutBreakdown = ({
  items,
  valueKey = 'engagement',
  totalValue,
  emptyLabel = 'No data available currently for this report.',
  valueHeader = 'Engagement',
  valueFormatter = fmt,
  totalFormatter = valueFormatter,
  showZeroBreakdown = false,
  showLegend = true,
}) => {
  const palette = ['#2f6690', '#9ca3af', '#8b5cf6', '#22c55e', '#f59e0b'];
  const sourceItems = items || [];
  const positiveItems = sourceItems.filter((item) => Number(item?.[valueKey]) > 0);
  const computedTotal = totalValue ?? positiveItems.reduce((sum, item) => sum + (Number(item?.[valueKey]) || 0), 0);
  const shouldRenderZeroBreakdown = showZeroBreakdown && sourceItems.length > 0;

  if (!positiveItems.length && !shouldRenderZeroBreakdown) return chartEmptyState(emptyLabel);

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[240px_minmax(0,1fr)] xl:items-center">
      <div className="flex flex-col items-center justify-center gap-4">
        <div className="relative h-[220px] w-[220px]">
          <InteractiveDonutChart
            data={positiveItems}
            dataKey={valueKey}
            colors={palette}
            innerRadius={60}
            outerRadius={88}
            paddingAngle={2}
            getItemKey={(item) => item.type || item.label}
            emptyRing={(
              <div className="flex h-full w-full items-center justify-center">
                <div className="h-[176px] w-[176px] rounded-full border-[24px] border-gray-200 bg-white" />
              </div>
            )}
            centerContent={(
              <>
                <span className="text-3xl font-semibold leading-none text-gray-700">{totalFormatter(computedTotal)}</span>
                <span className="mt-2 text-sm font-medium text-gray-500">Total</span>
              </>
            )}
          />
        </div>

        {showLegend && (
          <div className="flex w-full flex-wrap justify-center gap-2">
            {sourceItems.map((item) => {
              const value = Number(item?.[valueKey]) || 0;
              const positiveIndex = positiveItems.findIndex((entry) => (entry.type || entry.label) === (item.type || item.label));
              const color = positiveIndex >= 0 ? palette[positiveIndex % palette.length] : '#d1d5db';
              return (
                <div
                  key={`legend-${item.type || item.label}`}
                  className={`inline-flex max-w-full items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${value > 0 ? 'border-gray-200 bg-white text-gray-700' : 'border-gray-100 bg-gray-50 text-gray-400'}`}
                >
                  <span className="h-2.5 w-2.5 flex-shrink-0 rounded-full" style={{ backgroundColor: color }} />
                  <span className="truncate">{item.label}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="min-w-0">
        <div className="grid grid-cols-[minmax(0,1fr)_88px_52px] gap-x-3 border-b border-gray-200 pb-3 text-[11px] font-bold uppercase tracking-widest text-gray-400 sm:grid-cols-[minmax(0,1.2fr)_108px_64px]">
          <span>Type</span>
          <span className="text-right">{valueHeader}</span>
          <span className="text-right">%</span>
        </div>
        <div className="divide-y divide-gray-100">
          {sourceItems.map((item, index) => {
            const value = Number(item?.[valueKey]) || 0;
            const pct = computedTotal > 0 ? Math.round((value / computedTotal) * 100) : 0;
            const positiveIndex = positiveItems.findIndex((entry) => (entry.type || entry.label) === (item.type || item.label));
            const color = positiveIndex >= 0 ? palette[positiveIndex % palette.length] : '#d1d5db';
            return (
              <div key={item.type || item.label || index} className="grid grid-cols-[minmax(0,1fr)_88px_52px] items-center gap-x-3 py-4 text-sm sm:grid-cols-[minmax(0,1.2fr)_108px_64px]">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="h-3 w-3 flex-shrink-0 rounded-full" style={{ backgroundColor: color }} />
                  <span className={`truncate font-medium ${value > 0 ? 'text-gray-700' : 'text-gray-400'}`}>{item.label}</span>
                </div>
                <span className={`text-right font-medium ${value > 0 ? 'text-gray-700' : 'text-gray-400'}`}>{valueFormatter(value)}</span>
                <span className={`text-right font-medium ${value > 0 ? 'text-gray-700' : 'text-gray-400'}`}>{pct}%</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

const YoutubeMetricBreakdownCard = ({ title, items, emptyLabel = 'No data available currently for this report.', info }) => {
  const normalizedItems = (items || []).map((item) => ({
    ...item,
    views: Number(item?.views) || 0,
    estimatedMinutesWatched: Number(item?.estimatedMinutesWatched) || 0,
  }));
  const hasRows = normalizedItems.length > 0;
  const totalViews = normalizedItems.reduce((sum, item) => sum + item.views, 0);
  const totalMinutes = normalizedItems.reduce((sum, item) => sum + item.estimatedMinutesWatched, 0);
  const chartData = normalizedItems.map((item) => ({
    ...item,
    valueScore: item.views + item.estimatedMinutesWatched,
  }));

  return (
    <ReportCard title={title} info={info}>
      {hasRows ? (
        <div className="space-y-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
              <p className="text-[11px] font-bold uppercase tracking-widest text-gray-400">Total Views</p>
              <p className="mt-2 text-3xl font-bold text-sky-700">{fmt(totalViews)}</p>
            </div>
            <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
              <p className="text-[11px] font-bold uppercase tracking-widest text-gray-400">Estimated Minutes Watched</p>
              <p className="mt-2 text-3xl font-bold text-gray-700">{formatPreciseMetric(totalMinutes)}</p>
            </div>
          </div>

          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} layout="vertical" margin={{ top: 8, right: 16, bottom: 8, left: 16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis type="number" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={120}
                  tick={{ fontSize: 11, fill: '#6b7280' }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  formatter={(value, name) => (
                    name === 'Estimated Minutes Watched'
                      ? formatPreciseMetric(value)
                      : fmt(value)
                  )}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
                <Bar dataKey="views" name="Views" fill="#2f6690" radius={[0, 4, 4, 0]} barSize={14} minPointSize={2} />
                <Bar dataKey="estimatedMinutesWatched" name="Estimated Minutes Watched" fill="#d1d5db" radius={[0, 4, 4, 0]} barSize={14} minPointSize={2} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="divide-y divide-gray-100 rounded-xl border border-gray-100 bg-white">
            <div className="grid grid-cols-[minmax(0,1fr)_100px_160px] gap-x-4 px-4 py-3 text-[11px] font-bold uppercase tracking-widest text-gray-400">
              <span>Type</span>
              <span className="text-right">Views</span>
              <span className="text-right">Estimated Minutes Watched</span>
            </div>
            {normalizedItems.map((item) => (
              <div key={item.value || item.label} className="grid grid-cols-[minmax(0,1fr)_100px_160px] gap-x-4 px-4 py-3 text-sm">
                <span className="truncate font-medium text-gray-700">{item.label}</span>
                <span className="text-right text-gray-700">{fmt(item.views)}</span>
                <span className="text-right text-gray-700">{formatPreciseMetric(item.estimatedMinutesWatched)}</span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        chartEmptyState(emptyLabel)
      )}
    </ReportCard>
  );
};

const YoutubeDeviceTypeCard = ({ items }) => {
  // Distinct categorical colors (not blue shades) to match "Type" identity at a glance.
  const palette = ['#2563eb', '#16a34a', '#f97316', '#a855f7', '#64748b'];
  const positiveItems = (items || []).filter((item) => Number(item?.views) > 0);
  const totalViews = positiveItems.reduce((sum, item) => sum + (Number(item?.views) || 0), 0);

  return (
    <ReportCard title="Views by Device Type" info="Shows which devices your audience used to watch, ranked by share of total views.">
      {positiveItems.length > 0 ? (
        <div className="grid grid-cols-1 gap-6 2xl:grid-cols-[280px_minmax(0,1fr)] 2xl:items-center">
          <div className="flex justify-center">
            <div className="relative h-[220px] w-[220px] lg:h-[240px] lg:w-[240px]">
              <InteractiveDonutChart
                data={positiveItems}
                dataKey="views"
                colors={palette}
                innerRadius={64}
                outerRadius={104}
                paddingAngle={1.5}
                getItemKey={(item) => item.value || item.label}
                centerContent={(
                  <>
                    <span className="text-3xl font-semibold leading-none text-gray-700 lg:text-4xl">{fmt(totalViews)}</span>
                    <span className="mt-2 text-sm font-medium text-gray-500">Total</span>
                  </>
                )}
              />
            </div>
          </div>

          <div className="min-w-0">
            <div className="grid grid-cols-[minmax(0,1fr)_72px_56px] gap-x-3 border-b border-gray-200 pb-4 text-[12px] font-bold uppercase tracking-widest text-gray-500 sm:grid-cols-[minmax(0,1fr)_88px_64px] lg:grid-cols-[minmax(0,1fr)_96px_72px]">
              <span>Type</span>
              <span className="text-right">Views</span>
              <span className="text-right">%</span>
            </div>
            <div className="divide-y divide-gray-100">
              {positiveItems.map((item, index) => (
                <div key={item.value || item.label} className="grid grid-cols-[minmax(0,1fr)_72px_56px] items-center gap-x-3 py-4 text-sm sm:grid-cols-[minmax(0,1fr)_88px_64px] sm:text-base lg:grid-cols-[minmax(0,1fr)_96px_72px]">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="h-3.5 w-3.5 flex-shrink-0 rounded-full" style={{ backgroundColor: palette[index % palette.length] }} />
                    <span className="truncate font-medium text-gray-700">{String(item.label || '').toUpperCase()}</span>
                  </div>
                  <span className="text-right font-medium text-gray-700">{fmt(item.views)}</span>
                  <span className="text-right font-medium text-gray-700">{((Number(item.views) || 0) / Math.max(totalViews, 1) * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        chartEmptyState()
      )}
    </ReportCard>
  );
};

const YoutubeSubscribedStatusCard = ({ items }) => {
  const palette = { SUBSCRIBED: '#cfcfcf', UNSUBSCRIBED: '#2f6690' };
  const labelMap = { SUBSCRIBED: 'Subscribed', UNSUBSCRIBED: 'Non Subscribed' };
  const normalized = ['SUBSCRIBED', 'UNSUBSCRIBED'].map((value) => {
    const match = (items || []).find((item) => String(item?.value || '').toUpperCase() === value);
    return {
      value,
      label: labelMap[value],
      views: Number(match?.views) || 0,
      estimatedMinutesWatched: Number(match?.estimatedMinutesWatched) || 0,
    };
  });
  const totalViews = normalized.reduce((sum, item) => sum + item.views, 0);
  const totalMinutes = normalized.reduce((sum, item) => sum + item.estimatedMinutesWatched, 0);
  const positiveViewRows = normalized.filter((item) => item.views > 0);
  const positiveMinuteRows = normalized.filter((item) => item.estimatedMinutesWatched > 0);
  const primaryViewLabel = positiveViewRows[0]?.label || 'No Data';
  const primaryMinuteLabel = totalMinutes > 0 ? 'mins_watched' : 'mins_watched';

  const renderDonut = (data, dataKey, total, centerValue, centerLabel) => (
    <div className="relative h-[210px] w-[210px] lg:h-[230px] lg:w-[230px]">
      <InteractiveDonutChart
        data={data}
        dataKey={dataKey}
        colors={data.map((item) => palette[item.value])}
        innerRadius={62}
        outerRadius={102}
        paddingAngle={1.5}
        getItemKey={(item) => item.value}
        emptyRing={(
          <div className="flex h-full w-full items-center justify-center">
            <div className="h-[190px] w-[190px] rounded-full border-[28px] border-gray-200 bg-white lg:h-[210px] lg:w-[210px]" />
          </div>
        )}
        centerContent={(
          <>
            <span className="text-3xl font-semibold leading-none text-gray-700 lg:text-4xl">{centerValue}</span>
            <span className="mt-2 text-sm font-medium text-gray-500">{centerLabel}</span>
          </>
        )}
      />
    </div>
  );

  return (
    <ReportCard title="Views and Estimated Minutes Watched by Subscribed Status of Users" info="Compares watch volume from subscribed viewers versus non-subscribed viewers across views and minutes watched.">
      {normalized.length > 0 ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 md:gap-5">
            <div className="flex justify-center">
              {renderDonut(
                positiveViewRows,
                'views',
                totalViews,
                fmt(totalViews),
                primaryViewLabel,
              )}
            </div>
            <div className="flex justify-center">
              {renderDonut(
                positiveMinuteRows,
                'estimatedMinutesWatched',
                totalMinutes,
                totalMinutes > 0 ? `${formatPreciseMetric(totalMinutes)}m` : '0m',
                primaryMinuteLabel,
              )}
            </div>
          </div>

          <div className="mx-auto max-w-3xl overflow-hidden rounded-xl border border-gray-100 bg-white">
            <div className="grid grid-cols-[minmax(0,1fr)_72px_96px] gap-x-3 border-b border-gray-200 px-4 py-4 text-[12px] font-bold uppercase tracking-widest text-gray-500 sm:grid-cols-[minmax(0,1fr)_84px_120px] sm:gap-x-4 sm:px-5">
              <span>Type</span>
              <span className="text-right">Views</span>
              <span className="text-right">Mins_Watched</span>
            </div>
            <div className="divide-y divide-gray-100">
              {normalized.map((item) => (
                <div key={item.value} className="grid grid-cols-[minmax(0,1fr)_72px_96px] items-center gap-x-3 px-4 py-4 text-sm sm:grid-cols-[minmax(0,1fr)_84px_120px] sm:gap-x-4 sm:px-5 sm:text-base">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="h-3.5 w-3.5 flex-shrink-0 rounded-full" style={{ backgroundColor: palette[item.value] }} />
                    <span className={`truncate font-medium ${item.views > 0 || item.estimatedMinutesWatched > 0 ? 'text-gray-700' : 'text-gray-400'}`}>{item.label}</span>
                  </div>
                  <span className={`text-right font-medium ${item.views > 0 ? 'text-gray-700' : 'text-gray-400'}`}>{fmt(item.views)}</span>
                  <span className={`text-right font-medium ${item.estimatedMinutesWatched > 0 ? 'text-gray-700' : 'text-gray-400'}`}>{formatPreciseMetric(item.estimatedMinutesWatched)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        chartEmptyState()
      )}
    </ReportCard>
  );
};

const YoutubeWatchQualityCard = ({ summary, timeline, hasData, action }) => (
  <ReportCard
    title="Watch Quality Summary"
    action={action}
    info="Summarizes how well videos hold attention with engaged views, average watch duration, and average percentage viewed over time."
  >
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      <ReportMetricTile
        title="Engaged Views"
        value={summary?.engaged_views}
        subtitle="Views counted as engaged by YouTube."
        deltaPct={summary?.engaged_views_change_pct}
      />
      <ReportMetricTile
        title="Avg View Duration"
        value={summary?.average_view_duration_seconds}
        subtitle="Average watch duration per view."
        deltaPct={summary?.average_view_duration_change_pct}
        valueFormatter={formatDurationSeconds}
        accent="text-emerald-600"
      />
      <ReportMetricTile
        title="Avg View %"
        value={summary?.average_view_percentage}
        subtitle="Average percentage of video watched."
        deltaPct={summary?.average_view_percentage_change_pct}
        valueFormatter={formatPercentageMetric}
        accent="text-violet-600"
      />
    </div>
    {hasData ? (
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={timeline}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
          <YAxis yAxisId="left" allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
          <YAxis yAxisId="rightDuration" orientation="right" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
          <YAxis yAxisId="rightPct" hide />
          <Tooltip
            formatter={(value, name) => {
              if (name === 'Avg View Duration') return formatDurationSeconds(value);
              if (name === 'Avg View %') return formatPercentageMetric(value);
              return fmt(value);
            }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
          <Bar yAxisId="left" dataKey="engaged_views" name="Engaged Views" fill="#2f6690" radius={[4, 4, 0, 0]} barSize={20} minPointSize={2} />
          <Line yAxisId="rightDuration" type="monotone" dataKey="average_view_duration_seconds" name="Avg View Duration" stroke="#16a34a" strokeWidth={2.5} dot={false} />
          <Line yAxisId="rightPct" type="monotone" dataKey="average_view_percentage" name="Avg View %" stroke="#7c3aed" strokeWidth={2.5} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    ) : (
      chartEmptyState('Watch-quality data is not available for this period.')
    )}
  </ReportCard>
);

const YoutubeDemographicsCard = ({ demographics }) => {
  const ageGroups = demographics?.age_groups || [];
  const genderDistribution = demographics?.gender_distribution || [];
  const matrix = demographics?.age_gender_matrix || [];
  const hasData = ageGroups.length > 0 || genderDistribution.length > 0 || matrix.length > 0;

  return (
    <ReportCard title="Viewer Demographics" info="Breaks down who is watching by age group, gender distribution, and combined age-gender audience mix.">
      {hasData ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.15fr)_380px] gap-5">
            <div className="rounded-xl border border-gray-100 bg-white p-5">
              <div className="grid grid-cols-[minmax(0,1fr)_72px] gap-x-3 border-b border-gray-200 pb-3 text-[11px] font-bold uppercase tracking-widest text-gray-400">
                <span>Age Group</span>
                <span className="text-right">Viewers</span>
              </div>
              <div className="space-y-4 pt-4">
                {ageGroups.map((row) => (
                  <div key={row.value} className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium text-gray-700">{row.label}</span>
                      <span className="text-gray-600">{formatPercentageMetric(row.viewer_percentage)}</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-gray-100">
                      <div className="h-full rounded-full bg-[#2f6690]" style={{ width: `${Math.min(Number(row.viewer_percentage) || 0, 100)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <ReportDonutBreakdown
              items={genderDistribution.map((row) => ({ ...row, engagement: Number(row.viewer_percentage) || 0 }))}
              valueKey="engagement"
              totalValue={genderDistribution.reduce((sum, row) => sum + (Number(row.viewer_percentage) || 0), 0)}
              valueHeader="Viewers"
              valueFormatter={formatPercentageMetric}
              totalFormatter={formatPercentageMetric}
            />
          </div>

          <div className="rounded-xl border border-gray-100 bg-white overflow-hidden">
            <div className="grid grid-cols-[minmax(0,1fr)_110px] gap-x-4 border-b border-gray-200 px-4 py-3 text-[11px] font-bold uppercase tracking-widest text-gray-400 sm:grid-cols-[minmax(0,1fr)_140px]">
              <span>Age / Gender</span>
              <span className="text-right">Viewers</span>
            </div>
            <div className="divide-y divide-gray-100">
              {matrix.map((row) => (
                <div key={row.value} className="grid grid-cols-[minmax(0,1fr)_110px] gap-x-4 px-4 py-3 text-sm sm:grid-cols-[minmax(0,1fr)_140px]">
                  <span className="truncate font-medium text-gray-700">{row.age_group_label} / {row.gender_label}</span>
                  <span className="text-right text-gray-700">{formatPercentageMetric(row.viewer_percentage)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        chartEmptyState('Viewer demographics are not available for this YouTube account right now.')
      )}
    </ReportCard>
  );
};

const YoutubeContentBreakdownCard = ({ title, rows, emptyLabel }) => (
  <div className="rounded-xl border border-gray-100 bg-white overflow-hidden">
    <div className="border-b border-gray-200 px-4 py-3">
      <h4 className="text-sm font-semibold text-gray-700">{title}</h4>
    </div>
    {(rows || []).length > 0 ? (
      <div className="overflow-x-auto">
        <div className="min-w-[760px]">
          <div className="grid grid-cols-[minmax(0,1fr)_92px_146px_116px_126px_98px] gap-x-4 px-4 py-3 text-[11px] font-bold uppercase tracking-widest text-gray-400">
            <span>Type</span>
            <span className="text-right">Views</span>
            <span className="text-right">Minutes Watched</span>
            <span className="text-right">Engaged Views</span>
            <span className="text-right">Avg Duration</span>
            <span className="text-right">Avg View %</span>
          </div>
          <div className="divide-y divide-gray-100">
            {(rows || []).map((row) => (
              <div key={row.value || row.label} className="grid grid-cols-[minmax(0,1fr)_92px_146px_116px_126px_98px] gap-x-4 px-4 py-3 text-sm">
                <span className="truncate font-medium text-gray-700">{row.label}</span>
                <span className="text-right text-gray-700">{fmt(row.views)}</span>
                <span className="text-right text-gray-700">{formatPreciseMetric(row.estimated_minutes_watched)}</span>
                <span className="text-right text-gray-700">{fmt(row.engaged_views)}</span>
                <span className="text-right text-gray-700">{formatDurationSeconds(row.average_view_duration_seconds)}</span>
                <span className="text-right text-gray-700">{formatPercentageMetric(row.average_view_percentage)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    ) : (
      chartEmptyState(emptyLabel)
    )}
  </div>
);

const YoutubeSharingServicesCard = ({ items }) => {
  const hasRows = (items || []).length > 0;
  const showViews = (items || []).some((item) => Number(item?.views) > 0);
  const showMinutes = (items || []).some((item) => Number(item?.estimated_minutes_watched) > 0);
  const columns = showViews && showMinutes
    ? 'grid-cols-[minmax(0,1fr)_90px_90px_170px]'
    : showViews
      ? 'grid-cols-[minmax(0,1fr)_90px_110px]'
      : showMinutes
        ? 'grid-cols-[minmax(0,1fr)_90px_170px]'
        : 'grid-cols-[minmax(0,1fr)_90px]';

  return (
    <ReportCard title="Sharing Services" info="Lists the services viewers used when sharing your videos, along with resulting shares, views, and watch time where available.">
      {hasRows ? (
        <div className="overflow-x-auto">
          <div className={`min-w-[560px]`}>
            <div className={`grid gap-x-4 border-b border-gray-200 pb-3 text-[11px] font-bold uppercase tracking-widest text-gray-400 ${columns}`}>
              <span>Service</span>
              <span className="text-right">Shares</span>
              {showViews && <span className="text-right">Views</span>}
              {showMinutes && <span className="text-right">Estimated Minutes Watched</span>}
            </div>
            <div className="divide-y divide-gray-100">
              {(items || []).map((item) => (
                <div key={item.value || item.label} className={`grid gap-x-4 py-3 text-sm ${columns}`}>
                  <span className="truncate font-medium text-gray-700">{item.label}</span>
                  <span className="text-right text-gray-700">{fmt(item.shares)}</span>
                  {showViews && <span className="text-right text-gray-700">{fmt(item.views)}</span>}
                  {showMinutes && <span className="text-right text-gray-700">{formatPreciseMetric(item.estimated_minutes_watched)}</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        chartEmptyState('Sharing-service data is not available for this period.')
      )}
    </ReportCard>
  );
};

const YoutubeRetentionCard = ({ retention, selectedVideoId, onSelectVideo }) => {
  const videos = retention?.videos || [];
  const currentVideo = videos.find((video) => video.video_id === selectedVideoId) || videos[0];
  const hasSeries = (currentVideo?.series || []).length > 0;

  return (
    <ReportCard
      title="Audience Retention"
      info="Shows how much of a selected video's runtime viewers keep watching, plus how that video performs against YouTube's retention benchmark."
      action={videos.length > 0 ? (
        <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-gray-400">
          <span>Video Compared</span>
          <select
            value={currentVideo?.video_id || ''}
            onChange={(event) => onSelectVideo(event.target.value)}
            className="max-w-[320px] rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-semibold normal-case tracking-normal text-gray-700 shadow-sm"
          >
            {videos.map((video) => (
              <option key={video.video_id} value={video.video_id}>
                {video.title || 'Untitled video'}
              </option>
            ))}
          </select>
        </label>
      ) : null}
    >
      {currentVideo ? (
        <div className="space-y-5">
          <div className="flex flex-col gap-4 rounded-xl border border-gray-100 bg-white p-4 lg:flex-row">
            {currentVideo.thumbnail_url ? (
              <img src={currentVideo.thumbnail_url} alt="" className="h-32 w-full rounded-xl object-cover lg:w-56" />
            ) : (
              <div className="flex h-32 w-full items-center justify-center rounded-xl bg-gray-100 text-sm text-gray-400 lg:w-56">No thumbnail</div>
            )}
            <div className="min-w-0 space-y-2">
              <p className="text-lg font-semibold text-gray-900">{currentVideo.title || '(untitled)'}</p>
              <p className="text-sm text-gray-500">Select any top video from the dropdown to inspect where viewers drop off during playback.</p>
              <p className="text-sm text-gray-500">
                {currentVideo.published_at ? formatAnalyticsDate(currentVideo.published_at, true) : 'Published date unavailable'}
              </p>
              <div className="flex flex-wrap gap-3 text-sm text-gray-600">
                <span className="rounded-full bg-amber-50 px-3 py-1 font-medium text-amber-700">Source: {currentVideo.source_metric === 'estimated_minutes_watched' ? 'Top Minutes Watched' : 'Top Views'}</span>
                <span>Views: {fmt(currentVideo.views)}</span>
                <span>Minutes Watched: {formatPreciseMetric(currentVideo.estimated_minutes_watched)}</span>
              </div>
            </div>
          </div>

          {hasSeries ? (
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={currentVideo.series}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis
                  dataKey="elapsed_video_time_ratio"
                  tick={{ fontSize: 11, fill: '#9ca3af' }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(value) => `${Math.round((Number(value) || 0) * 100)}%`}
                />
                <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                <Tooltip
                  formatter={(value, name) => (
                    name === 'Relative Retention Performance'
                      ? formatPreciseMetric(value)
                      : formatPercentageMetric(value)
                  )}
                  labelFormatter={(value) => `${Math.round((Number(value) || 0) * 100)}% watched`}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
                <Line yAxisId="left" type="monotone" dataKey="audience_watch_ratio" name="Audience Watch Ratio" stroke="#2f6690" strokeWidth={2.5} dot={false} />
                <Line yAxisId="right" type="monotone" dataKey="relative_retention_performance" name="Relative Retention Performance" stroke="#f59e0b" strokeWidth={2.5} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            chartEmptyState('Audience retention is not available for the selected video.')
          )}
        </div>
      ) : (
        chartEmptyState('Audience retention is not available for this period.')
      )}
    </ReportCard>
  );
};

const YoutubeCountryMapCard = ({
  title,
  rows,
  metricLabel,
  meta,
  valueFormatter = formatPreciseMetric,
  action,
  info,
  emptyLabel = 'No data available currently for this report.',
}) => {
  const [hoveredCountryCode, setHoveredCountryCode] = useState(null);
  const positiveRows = (rows || [])
    .filter((row) => Number(row?.count) > 0)
    .map((row) => ({
      ...row,
      countryName: countryNameForCode(row.country_code),
    }))
    .filter((row) => row.countryName);
  const topRows = positiveRows.slice(0, 5);
  const topRowsTotal = topRows.reduce((sum, item) => sum + (Number(item.count) || 0), 0);
  const valueByCountry = Object.fromEntries(positiveRows.map((row) => [row.countryName, Number(row.count) || 0]));
  const countryCodeByName = Object.fromEntries(positiveRows.map((row) => [row.countryName, row.country_code]));
  const maxValue = Math.max(...Object.values(valueByCountry), 0);
  const totalValue = positiveRows.reduce((sum, row) => sum + (Number(row.count) || 0), 0);
  const leadRow = topRows[0] || null;
  const effectiveEndLabel = formatAnalyticsDate(meta?.effective_end_date, false);
  const lastRefreshedLabel = formatAnalyticsDate(meta?.last_refreshed_at, true);
  const autoRefreshLabel = formatAutoRefreshInterval(meta?.auto_refresh_seconds);
  const freshnessLabel = meta?.source === 'snapshot'
    ? (effectiveEndLabel ? `Showing last available geography data from ${effectiveEndLabel}` : 'Showing last available geography snapshot')
    : (effectiveEndLabel ? `Updated through ${effectiveEndLabel}` : '');
  const settledLabel = meta?.is_lag_adjusted ? "Using YouTube's latest settled geography data" : '';
  const showMeta = Boolean(freshnessLabel || settledLabel || lastRefreshedLabel || autoRefreshLabel);

  return (
    <ReportCard title={title} action={action} info={info}>
      {showMeta && (
        <div className="mb-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
          {freshnessLabel && <span>{freshnessLabel}</span>}
          {settledLabel && <span>{settledLabel}</span>}
          {lastRefreshedLabel && <span>Last refreshed {lastRefreshedLabel}</span>}
          {autoRefreshLabel && <span>Auto-refreshes every {autoRefreshLabel}</span>}
        </div>
      )}
      {topRows.length === 0 ? (
        chartEmptyState(emptyLabel)
      ) : (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.45fr)_380px]">
          <div className="space-y-4 rounded-2xl border border-gray-200 bg-gradient-to-br from-slate-50 via-white to-sky-50 p-4 shadow-sm">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-white/80 bg-white/90 p-4">
                <p className="text-[11px] font-bold uppercase tracking-widest text-gray-400">Top Market</p>
                <p className="mt-2 text-xl font-semibold text-gray-900">{leadRow?.countryName || '—'}</p>
                <p className="mt-2 text-sm text-gray-500">{leadRow ? `${valueFormatter(leadRow.count)} ${metricLabel.toLowerCase()}` : 'No data'}</p>
              </div>
              <div className="rounded-2xl border border-white/80 bg-white/90 p-4">
                <p className="text-[11px] font-bold uppercase tracking-widest text-gray-400">Countries in Report</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">{positiveRows.length}</p>
                <p className="mt-2 text-sm text-gray-500">Markets with measurable activity</p>
              </div>
              <div className="rounded-2xl border border-white/80 bg-white/90 p-4">
                <p className="text-[11px] font-bold uppercase tracking-widest text-gray-400">Total {metricLabel}</p>
                <p className="mt-2 text-3xl font-semibold text-gray-900">{valueFormatter(totalValue)}</p>
                <p className="mt-2 text-sm text-gray-500">Across the current geography window</p>
              </div>
            </div>
            <div className="rounded-2xl border border-white/80 bg-white/95 p-3 shadow-inner">
              <div className="mb-3 flex items-center justify-between gap-3 px-2">
                <div>
                  <p className="text-sm font-semibold text-gray-800">Geographic concentration</p>
                  <p className="text-xs text-gray-500">Hover the map or country list to spotlight a market.</p>
                </div>
                <div className="flex items-center gap-2 text-[11px] font-medium text-gray-500">
                  <span>Low</span>
                  <span className="h-2.5 w-20 rounded-full bg-gradient-to-r from-slate-200 via-sky-300 to-[#2f6690]" />
                  <span>High</span>
                </div>
              </div>
              <ComposableMap projectionConfig={{ scale: 152 }} width={800} height={420} style={{ width: '100%', height: 'auto' }}>
              <Geographies geography={worldGeo}>
                {({ geographies }) =>
                  geographies.map((geo) => {
                    const value = valueByCountry[geo.properties?.name] || 0;
                    const intensity = maxValue > 0 ? value / maxValue : 0;
                    const geoCountryCode = countryCodeByName[geo.properties?.name] || null;
                    const isHovered = hoveredCountryCode && geoCountryCode === hoveredCountryCode;
                    const fill = value > 0
                      ? `rgba(47, 102, 144, ${0.2 + (0.65 * intensity)})`
                      : '#f8fafc';
                    return (
                      <Geography
                        key={geo.rsmKey}
                        geography={geo}
                        fill={fill}
                        stroke={isHovered ? '#0f172a' : '#cbd5d1'}
                        strokeWidth={isHovered ? 1.1 : 0.55}
                        onMouseEnter={() => {
                          if (geoCountryCode) setHoveredCountryCode(geoCountryCode);
                        }}
                        onMouseLeave={() => setHoveredCountryCode(null)}
                        style={{
                          default: { outline: 'none' },
                          hover: { outline: 'none', fill: value > 0 ? '#2f6690' : '#e2e8f0' },
                          pressed: { outline: 'none', fill: value > 0 ? '#2f6690' : '#e2e8f0' },
                        }}
                      />
                    );
                  })
                }
              </Geographies>
            </ComposableMap>
          </div>
          </div>
          <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h4 className="text-2xl font-semibold text-gray-900">Top 5 Countries</h4>
                <p className="mt-2 text-sm text-gray-500">The strongest markets for this metric in the selected period.</p>
              </div>
              {leadRow ? (
                <div className="rounded-full bg-sky-50 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-sky-700">
                  Leader: {leadRow.countryName}
                </div>
              ) : null}
            </div>
            <div className="mt-6 grid grid-cols-[minmax(0,1fr)_140px_100px] gap-x-4 border-b border-gray-200 pb-3 text-xs font-bold uppercase tracking-widest text-gray-400">
              <span>Country</span>
              <span className="text-right">{metricLabel}</span>
              <span className="text-right">%</span>
            </div>
            <div className="divide-y divide-gray-100">
              {topRows.map((row) => (
                <div
                  key={row.country_code}
                  className={`grid grid-cols-[minmax(0,1fr)_140px_100px] items-center gap-x-4 rounded-xl px-3 py-4 transition-colors ${hoveredCountryCode === row.country_code ? 'bg-sky-50' : ''}`}
                  onMouseEnter={() => setHoveredCountryCode(row.country_code)}
                  onMouseLeave={() => setHoveredCountryCode(null)}
                >
                  <span className="truncate text-lg font-medium text-gray-800">{row.countryName}</span>
                  <span className="text-right text-lg text-gray-700">{valueFormatter(row.count)}</span>
                  <div className="flex items-center justify-end gap-3">
                    <div className="h-2 w-20 rounded-full bg-gray-200 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-[#2f6690]"
                        style={{ width: `${percentForBreakdown(row.count, topRowsTotal)}%` }}
                      />
                    </div>
                    <span className="w-12 text-right text-lg text-gray-700">
                      {percentForBreakdown(row.count, topRowsTotal)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </ReportCard>
  );
};

const YoutubeTopVideoCard = ({ title, video, metricLabel, primaryMetric, action, info }) => (
  <ReportCard title={title} action={action} info={info}>
    {video ? (
      <div className="max-w-sm rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="px-4 pt-4">
          <p className="text-4xl font-semibold text-gray-900">via YouTube</p>
          <p className="mt-2 text-lg text-gray-500">
            {video.timestamp ? format(parseISO(video.timestamp), 'd MMM yyyy h:mm a') : '—'}
          </p>
        </div>
        {video.thumbnail_url ? (
          <img src={video.thumbnail_url} alt="" className="mt-4 h-48 w-full object-cover" />
        ) : (
          <div className="mt-4 h-48 w-full bg-gray-100 flex items-center justify-center text-sm text-gray-400">No thumbnail</div>
        )}
        <div className="px-4 py-4 text-2xl font-medium text-gray-900 line-clamp-3">{video.title || video.content || '(untitled)'}</div>
        <div className="border-t border-dashed border-gray-200 px-4 py-4 space-y-3 text-xl">
          <div className="flex items-center justify-between">
            <span className="text-gray-700">{metricLabel}</span>
            <span className="font-semibold text-gray-900">
              {primaryMetric === 'estimated_minutes_watched'
                ? formatPreciseMetric(video.estimated_minutes_watched)
                : fmt(video.views)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-gray-700">Views</span>
            <span className="font-semibold text-gray-900">{fmt(video.views)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-gray-700">Minutes Watched</span>
            <span className="font-semibold text-gray-900">{formatPreciseMetric(video.estimated_minutes_watched)}</span>
          </div>
        </div>
      </div>
    ) : (
      chartEmptyState('No YouTube video data is available for this period.')
    )}
  </ReportCard>
);

const YoutubeTopVideosStrip = ({ title, videos, metricLabel, primaryMetric, action, info }) => (
  <ReportCard title={title} action={action} info={info}>
    {(videos || []).length > 0 ? (
      <div className="-mx-1 flex gap-4 overflow-x-auto px-1 pb-2">
        {videos.map((video, index) => (
          <div key={video.id || `${video.title}-${index}`} className="w-[260px] flex-shrink-0 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
              <span className="text-xs font-bold uppercase tracking-widest text-gray-400">#{index + 1}</span>
              <span className="text-xs font-semibold text-gray-500">via YouTube</span>
            </div>
            {video.thumbnail_url ? (
              <img src={video.thumbnail_url} alt="" className="h-36 w-full object-cover" />
            ) : (
              <div className="h-36 w-full bg-gray-100 flex items-center justify-center text-sm text-gray-400">No thumbnail</div>
            )}
            <div className="space-y-3 px-4 py-4">
              <p className="line-clamp-2 text-lg font-semibold text-gray-900">{video.title || video.content || '(untitled)'}</p>
              <p className="text-sm text-gray-500">
                {video.timestamp ? format(parseISO(video.timestamp), 'd MMM yyyy h:mm a') : '—'}
              </p>
              <div className="rounded-xl border border-gray-100 bg-gray-50 px-3 py-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-500">{metricLabel}</span>
                  <span className="font-semibold text-gray-900">
                    {primaryMetric === 'estimated_minutes_watched'
                      ? formatPreciseMetric(video.estimated_minutes_watched)
                      : fmt(video.views)}
                  </span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-lg border border-gray-100 px-3 py-2">
                  <p className="text-gray-400">Views</p>
                  <p className="mt-1 font-semibold text-gray-800">{fmt(video.views)}</p>
                </div>
                <div className="rounded-lg border border-gray-100 px-3 py-2">
                  <p className="text-gray-400">Minutes</p>
                  <p className="mt-1 font-semibold text-gray-800">{formatPreciseMetric(video.estimated_minutes_watched)}</p>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    ) : (
      chartEmptyState('No YouTube video data is available for this period.')
    )}
  </ReportCard>
);

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
  const accountsByPlatform = accounts.reduce((acc, a) => {
    if (!acc[a.platform]) acc[a.platform] = [];
    acc[a.platform].push(a);
    return acc;
  }, {});

  return (
    <nav className="py-2 select-none">
      <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 px-4 py-2">Channels</p>
      <p className="px-4 pb-2 text-[11px] text-gray-400">Drag platforms to arrange this list.</p>

      {/* All Platforms */}
      <button
        onClick={() => onSelect(null)}
        className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors border-r-2
          ${!selectedPlatform
            ? 'bg-indigo-50 text-indigo-700 font-semibold border-indigo-500'
            : 'text-gray-600 hover:bg-gray-50 border-transparent'}`}
      >
        <span className="w-6 h-6 rounded-md bg-gray-100 flex items-center justify-center text-gray-400 shrink-0">
          📊
        </span>
        <span className="flex-1 text-left text-[13px]">All Platforms</span>
      </button>

      {/* Each platform row */}
      {platformOrder.map((plat, index) => {
        const platAccounts = accountsByPlatform[plat] || [];
        const isConnected  = platAccounts.length > 0;
        const isActive     = selectedPlatform === plat;
        const Icon         = PLATFORM_ICONS[plat];
        const color        = PLATFORM_COLORS[plat] || '#6b7280';
        return (
          <button
            key={plat}
            draggable
            title={isConnected ? `${platAccounts.length} connected ${platAccounts.length === 1 ? 'account' : 'accounts'}` : 'No connected accounts'}
            onDragStart={() => onDragStart(index)}
            onDragEnter={() => onDragEnter(index)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              onDragEnd();
            }}
            onDragEnd={onDragEnd}
            onClick={() => onSelect(plat)}
            className={`group relative w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors border-r-2
              ${isActive
                ? 'bg-indigo-50 text-indigo-700 font-semibold border-indigo-500'
                : 'text-gray-600 hover:bg-gray-50 border-transparent'}
              ${!isConnected ? 'opacity-40' : ''}
              ${draggingPlatform === plat ? 'opacity-60 bg-gray-50 scale-[0.995]' : ''}`}
          >
            <span
              className={`w-6 h-6 rounded-md flex items-center justify-center shrink-0 transition-colors
                ${isActive ? 'bg-indigo-100 text-indigo-500' : 'bg-gray-100 text-gray-400 group-hover:text-gray-600'}`}
              aria-hidden="true"
            >
              <FaGripLines className="text-[10px]" />
            </span>
            {Icon && <Icon size={17} style={{ color, flexShrink: 0 }} />}
            <span className="flex-1 text-left text-[13px]">{PLATFORM_LABELS[plat] || plat}</span>
            {isConnected && (
              <span
                className="pointer-events-none absolute left-full top-1/2 z-30 ml-2 -translate-y-1/2 rounded-full px-2 py-1 text-[10px] font-bold whitespace-nowrap opacity-0 shadow-sm transition-all duration-150 translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 group-focus-visible:opacity-100 group-focus-visible:translate-x-0"
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
  const [postsErrors, setPostsErrors] = useState([]);
  const [postsMessage, setPostsMessage] = useState(null);

  const [loadingOverview, setLoadingOverview]       = useState(true);
  const [loadingEngagement, setLoadingEngagement]   = useState(false);
  const [loadingPosts, setLoadingPosts]             = useState(false);
  const [demographics, setDemographics]             = useState(null);
  const [loadingDemos, setLoadingDemos]             = useState(false);
  const [instagramReport, setInstagramReport]       = useState(null);
  const [loadingInstagramReport, setLoadingInstagramReport] = useState(false);
  const [instagramReachGranularity, setInstagramReachGranularity] = useState('day');
  const [blueskyReport, setBlueskyReport]           = useState(null);
  const [loadingBlueskyReport, setLoadingBlueskyReport] = useState(false);
  const [blueskyTopMetric, setBlueskyTopMetric]     = useState('engagement');
  const [blueskyChartGranularity, setBlueskyChartGranularity] = useState('day');
  const [youtubeReport, setYoutubeReport]           = useState(null);
  const [loadingYoutubeReport, setLoadingYoutubeReport] = useState(false);
  const [youtubeChartGranularity, setYoutubeChartGranularity] = useState('day');
  const [youtubeTopVideoMetric, setYoutubeTopVideoMetric] = useState('views');
  const [youtubeRetentionVideoId, setYoutubeRetentionVideoId] = useState('');
  const [tiktokReport, setTikTokReport]             = useState(null);
  const [loadingTikTokReport, setLoadingTikTokReport] = useState(false);
  const [tiktokTopMetric, setTikTokTopMetric]       = useState('views');
  const [platformOrder, setPlatformOrder] = useState(ALL_PLATFORMS);
  const [loadedPlatformOrder, setLoadedPlatformOrder] = useState(false);
  const [draggingPlatform, setDraggingPlatform] = useState(null);
  const dragPlatformIdx = useRef(null);
  const dragOverPlatformIdx = useRef(null);

  const platformOrderStorageKey = `${PLATFORM_ORDER_STORAGE_KEY_PREFIX}_${accounts.find((account) => account?.user_id)?.user_id || 'default'}`;

  // Fetch accounts on load with a quick retry so the platform list is less likely to appear empty.
  useEffect(() => {
    let cancelled = false;

    const loadAccounts = async (retry = false) => {
      try {
        const data = await getSocialAccounts();
        if (!cancelled) setAccounts(data);
      } catch {
        if (!retry && !cancelled) {
          window.setTimeout(() => loadAccounts(true), 500);
        }
      }
    };

    loadAccounts();
    return () => {
      cancelled = true;
    };
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
      setPostsErrors(Array.isArray(data.errors) ? data.errors : []);
      setPostsMessage(data.message || null);
    } catch {
      toast.error('Failed to load posts');
      setPosts([]);
      setPostsErrors([]);
      setPostsMessage(null);
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

  const handleTabClick = useCallback((tabId) => {
    setActiveTab(tabId);

    // The YouTube overview uses the shared overview/timeline payload, which does
    // not automatically refetch when returning from YouTube-specific report tabs.
    // Force a refresh whenever Overview is selected so the cards are rebuilt from
    // fresh data on every click.
    if (selectedPlatform === 'youtube' && tabId === 'overview') {
      fetchOverview();
      fetchEngagement();
    }
  }, [selectedPlatform, fetchOverview, fetchEngagement]);

  const fetchInstagramReport = useCallback(async () => {
    if (selectedPlatform !== 'instagram') {
      setInstagramReport(null);
      return;
    }
    setLoadingInstagramReport(true);
    try {
      const data = await getInstagramAnalyticsReport({
        days,
        accountId: selectedAccount,
      });
      setInstagramReport(data);
    } catch {
      toast.error('Failed to load Instagram report');
      setInstagramReport(null);
    } finally {
      setLoadingInstagramReport(false);
    }
  }, [days, selectedPlatform, selectedAccount]);

  useEffect(() => {
    if (['summary', 'instagram-audience', 'instagram-reach'].includes(activeTab) && selectedPlatform === 'instagram') {
      fetchInstagramReport();
    }
  }, [activeTab, selectedPlatform, fetchInstagramReport]);

  const fetchBlueskyReport = useCallback(async () => {
    if (selectedPlatform !== 'bluesky') {
      setBlueskyReport(null);
      return;
    }
    setLoadingBlueskyReport(true);
    try {
      const data = await getBlueskyAnalyticsReport({
        days,
        accountId: selectedAccount,
      });
      setBlueskyReport(data);
    } catch {
      toast.error('Failed to load Bluesky report');
      setBlueskyReport(null);
    } finally {
      setLoadingBlueskyReport(false);
    }
  }, [days, selectedPlatform, selectedAccount]);

  useEffect(() => {
    if (
      selectedPlatform === 'bluesky'
      && ['bluesky-summary', 'bluesky-audience', 'bluesky-posts-engagement'].includes(activeTab)
    ) {
      fetchBlueskyReport();
    }
  }, [activeTab, selectedPlatform, fetchBlueskyReport]);

  const fetchYoutubeReport = useCallback(async () => {
    if (selectedPlatform !== 'youtube') {
      setYoutubeReport(null);
      return;
    }
    setLoadingYoutubeReport(true);
    try {
      const selectedYoutubeAccount = accounts.find((account) => (
        account.platform === 'youtube' && (
          account.id === selectedAccount
          || account.account_id === selectedAccount
          || account.platform_user_id === selectedAccount
          || account.platform_username === selectedAccount
        )
      ));
      const requestedAccountId =
        selectedYoutubeAccount?.account_id
        || selectedYoutubeAccount?.id
        || selectedAccount
        || null;

      let data = await getYoutubeAnalyticsReport({
        days,
        accountId: requestedAccountId,
        groupBy: youtubeChartGranularity,
      });
      if (requestedAccountId && data && data.supported === false) {
        const fallbackData = await getYoutubeAnalyticsReport({
          days,
          groupBy: youtubeChartGranularity,
        });
        if (fallbackData?.supported) {
          data = fallbackData;
        }
      }
      setYoutubeReport(data);
    } catch {
      toast.error('Failed to load YouTube report');
      setYoutubeReport(null);
    } finally {
      setLoadingYoutubeReport(false);
    }
  }, [accounts, days, selectedPlatform, selectedAccount, youtubeChartGranularity]);

  useEffect(() => {
    if (
      selectedPlatform === 'youtube'
      && ['youtube-summary', 'youtube-audience', 'youtube-video-performance'].includes(activeTab)
    ) {
      fetchYoutubeReport();
    }
  }, [activeTab, selectedPlatform, fetchYoutubeReport]);

  const fetchTikTokReport = useCallback(async () => {
    if (selectedPlatform !== 'tiktok') {
      setTikTokReport(null);
      return;
    }
    setLoadingTikTokReport(true);
    try {
      const data = await getTikTokAnalyticsReport({
        days,
        accountId: selectedAccount,
      });
      setTikTokReport(data);
    } catch {
      toast.error('Failed to load TikTok report');
      setTikTokReport(null);
    } finally {
      setLoadingTikTokReport(false);
    }
  }, [days, selectedPlatform, selectedAccount]);

  useEffect(() => {
    if (
      selectedPlatform === 'tiktok'
      && ['overview', 'tiktok-content', 'tiktok-viewers', 'tiktok-followers'].includes(activeTab)
    ) {
      fetchTikTokReport();
    }
  }, [activeTab, selectedPlatform, fetchTikTokReport]);

  useEffect(() => {
    if (selectedPlatform !== 'instagram' && activeTab === 'summary') {
      setActiveTab('overview');
    }
  }, [selectedPlatform, activeTab]);

  useEffect(() => {
    if (selectedPlatform === 'instagram' && activeTab === 'demographics') {
      setActiveTab('summary');
    }
  }, [selectedPlatform, activeTab]);

  useEffect(() => {
    if (selectedPlatform !== 'bluesky' && ['bluesky-summary', 'bluesky-audience', 'bluesky-posts-engagement'].includes(activeTab)) {
      setActiveTab('overview');
    }
  }, [selectedPlatform, activeTab]);

  useEffect(() => {
    if (selectedPlatform !== 'youtube' && ['youtube-summary', 'youtube-audience', 'youtube-video-performance'].includes(activeTab)) {
      setActiveTab('overview');
    }
  }, [selectedPlatform, activeTab]);

  useEffect(() => {
    if (selectedPlatform !== 'tiktok' && ['tiktok-content', 'tiktok-viewers', 'tiktok-followers'].includes(activeTab)) {
      setActiveTab('overview');
    }
  }, [selectedPlatform, activeTab]);

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

  const handlePlatformDragStart = (index) => {
    dragPlatformIdx.current = index;
    setDraggingPlatform(platformOrder[index] || null);
  };

  const handlePlatformDragEnter = (index) => {
    dragOverPlatformIdx.current = index;
  };

  const handlePlatformDragEnd = () => {
    if (dragPlatformIdx.current == null || dragOverPlatformIdx.current == null) {
      dragPlatformIdx.current = null;
      dragOverPlatformIdx.current = null;
      setDraggingPlatform(null);
      return;
    }
    if (dragPlatformIdx.current === dragOverPlatformIdx.current) {
      dragPlatformIdx.current = null;
      dragOverPlatformIdx.current = null;
      setDraggingPlatform(null);
      return;
    }
    setPlatformOrder((current) => {
      const next = [...current];
      const [moved] = next.splice(dragPlatformIdx.current, 1);
      next.splice(dragOverPlatformIdx.current, 0, moved);
      return normalizePlatformOrder(next);
    });
    dragPlatformIdx.current = null;
    dragOverPlatformIdx.current = null;
    setDraggingPlatform(null);
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
  const showInstagramReportTab = selectedPlatform === 'instagram';
  const showBlueskyReportTabs = selectedPlatform === 'bluesky';
  const showYoutubeReportTabs = selectedPlatform === 'youtube';
  const showTikTokReportTabs = selectedPlatform === 'tiktok';

  const tabs = useMemo(() => ([
    { id: 'overview', label: 'Overview' },
    ...(!showTikTokReportTabs ? [{ id: 'posts', label: 'Posts' }] : []),
    ...(showTikTokReportTabs ? [
      { id: 'tiktok-content', label: 'Content' },
      { id: 'posts', label: 'Posts' },
      { id: 'tiktok-viewers', label: 'Viewers' },
      { id: 'tiktok-followers', label: 'Followers' },
    ] : []),
    ...(showInstagramReportTab ? [
      { id: 'summary', label: 'Summary' },
      { id: 'instagram-audience', label: 'Audience' },
      { id: 'instagram-reach', label: 'Reach' },
    ] : []),
    ...(showBlueskyReportTabs ? [
      { id: 'bluesky-summary', label: 'Summary' },
      { id: 'bluesky-audience', label: 'Audience' },
      { id: 'bluesky-posts-engagement', label: 'Posts & Engagement' },
    ] : []),
    ...(showYoutubeReportTabs ? [
      { id: 'youtube-summary', label: 'Summary' },
      { id: 'youtube-audience', label: 'Audience' },
      { id: 'youtube-video-performance', label: 'Video Performance' },
    ] : []),
    ...(hasDemographics && selectedPlatform !== 'instagram' ? [{ id: 'demographics', label: 'Demographics' }] : []),
  ]), [showTikTokReportTabs, showInstagramReportTab, showBlueskyReportTabs, showYoutubeReportTabs, hasDemographics, selectedPlatform]);

  useEffect(() => {
    if (!tabs.some((tab) => tab.id === activeTab)) {
      setActiveTab('overview');
    }
  }, [activeTab, tabs]);

  // Accounts for the currently selected platform
  const platformAccounts = accounts.filter(
    (a) => !selectedPlatform || a.platform === selectedPlatform
  );
  const selectedConnectedAccount =
    (overview?.connected_accounts || []).find(
      (a) => (a.account_id || a.id) === selectedAccount
    ) ||
    (engagement?.connected_accounts || []).find(
      (a) => (a.account_id || a.id) === selectedAccount
    ) ||
    platformAccounts.find((a) => a.id === selectedAccount);
  const overviewAccounts = overview?.connected_accounts || [];
  const computedAudienceSupport = selectedAccount
    ? (selectedConnectedAccount?.supports || {})
    : aggregateAudienceSupport(overviewAccounts);
  const audienceSupport = selectedPlatformAudienceSupport(selectedPlatform, computedAudienceSupport);
  const audienceSource = selectedAccount
    ? selectedConnectedAccount
    : (overview?.audience_totals || {});
  const reachCardLabel = audienceSupport.reach
    ? 'Reach'
    : (audienceSupport.impressions ? 'Impressions' : null);
  const hasContentOutsideWindow =
    !!selectedPlatform &&
    !!selectedAccount &&
    !loadingOverview &&
    (overview?.published_in_period || 0) === 0 &&
    (selectedConnectedAccount?.posts_count || 0) > 0;
  const isNotConnected = selectedPlatform &&
    accounts.filter((a) => a.platform === selectedPlatform).length === 0;
  const SelectedIcon = selectedPlatform ? PLATFORM_ICONS[selectedPlatform] : null;
  const selectedColor = selectedPlatform ? (PLATFORM_COLORS[selectedPlatform] || '#6b7280') : null;
  const selectedPlatformMetrics = supportedMetricsFor(selectedPlatform);
  const selectedPlatformNotice = selectedPlatform
    ? (engagement?.message || PLATFORM_NOTICES[selectedPlatform] || null)
    : null;
  const showEngagementInsights = !selectedPlatform || hasAnyEngagementMetrics(selectedPlatform);
  const visibleMetricCards = [
    { key: 'likes', label: 'Total Likes', icon: FaHeart, value: engagement?.totals?.total_likes, color: 'bg-rose-500' },
    { key: 'comments', label: 'Comments', icon: FaComment, value: engagement?.totals?.total_comments, color: 'bg-blue-500' },
    { key: 'shares', label: 'Shares', icon: FaShare, value: engagement?.totals?.total_shares, color: 'bg-emerald-500' },
    { key: 'views', label: 'Views', icon: FaEye, value: engagement?.totals?.total_views, color: 'bg-purple-500' },
  ].filter((metric) => !selectedPlatform || selectedPlatformMetrics[metric.key]);
  const audienceMetricCards = [
    {
      key: 'followers_total',
      label: 'Total Followers',
      icon: FaUsers,
      value: audienceSource?.followers_count ?? audienceSource?.followers_total,
      color: 'bg-sky-600',
      visible: audienceSupport.followers_total,
    },
    {
      key: 'followers_growth',
      label: selectedPlatform === 'instagram' ? `Net Follower Change (${days}d)` : `New Followers (${days}d)`,
      icon: FaChartLine,
      value: audienceSource?.followers_growth,
      color: 'bg-emerald-600',
      visible: audienceSupport.followers_growth,
    },
    {
      key: 'reach',
      label: reachCardLabel,
      icon: FaBullseye,
      value: audienceSupport.reach ? audienceSource?.reach : audienceSource?.impressions,
      color: 'bg-amber-500',
      visible: !!reachCardLabel,
    },
  ].filter((metric) => metric.visible);
  const visibleSortOptions = SORT_OPTIONS.filter((opt) => opt.value === 'date' || !selectedPlatform || selectedPlatformMetrics[opt.value]);
  const topPostMetricLabel = selectedPlatformNotice || (!showEngagementInsights ? 'This platform does not expose post engagement metrics through the current integration.' : null);
  const summaryMetricColumns = [
    { key: 'likes', label: 'Likes' },
    { key: 'comments', label: 'Comments' },
    { key: 'shares', label: 'Shares' },
    { key: 'views', label: 'Views' },
  ].filter(({ key }) => {
    if (!overview?.platform_counts) return true;
    return Object.keys(overview.platform_counts).some((plat) => metricIsSupported(plat, key));
  });
  const showEngRateColumn = !!overview?.platform_counts && Object.keys(overview.platform_counts).some((plat) =>
    ['likes', 'comments', 'shares'].some((metric) => metricIsSupported(plat, metric))
  );

  useEffect(() => {
    if (!visibleSortOptions.some((opt) => opt.value === postsSort)) {
      setPostsSort('date');
    }
  }, [postsSort, visibleSortOptions]);

  const instagramSummary = instagramReport?.summary || {};
  const instagramAudience = instagramReport?.audience || {};
  const instagramReach = instagramReport?.reach || {};
  const instagramFollowerTimeline = (instagramAudience.follower_growth || []).map((point) => ({
    ...point,
    label: formatReportDate(point.date, days),
  }));
  const instagramDemographics = instagramAudience.demographics || {};
  const instagramFollowerGrowthUnavailableMessage = (
    instagramAudience.follower_growth_error
    || 'Follower growth data is not available for this Instagram account right now.'
  );
  const instagramDemographicsErrorDetails = (
    instagramAudience.demographics_error_details
    || instagramReport?.demographics_errors
    || []
  );
  const instagramDemographicsUnavailableMessage = (
    instagramAudience.demographics_message
    || (
      instagramDemographicsErrorDetails.length
        ? instagramDemographicsErrorDetails.map((item) => (
          item.metric ? `${item.account} (${item.metric}): ${item.error}` : `${item.account}: ${item.error}`
        )).join(' ')
        : null
    )
    || 'Audience demographics are not available for this Instagram account yet.'
  );
  const instagramFollowerGrowthHasData = chartHasData(instagramFollowerTimeline, ['count']);
  const instagramReachTimeline = bucketSeriesByGranularity(
    instagramReach.reach_series || [],
    days,
    instagramReachGranularity,
  );
  const instagramReachHasData = chartHasData(instagramReachTimeline, ['count']);
  const blueskySummary = blueskyReport?.summary || {};
  const blueskyAudience = blueskyReport?.audience || {};
  const blueskyPostsEngagement = blueskyReport?.posts_engagement || {};
  const blueskyFollowerTimeline = bucketSeriesByGranularity(
    blueskyAudience.follower_growth || [],
    days,
    blueskyChartGranularity,
  );
  const blueskyMessagesMentionsTimeline = mergeBucketedSeries({
    mentions: blueskyAudience.mentions_received || [],
    messages: blueskyAudience.messages_received || [],
  }, days, blueskyChartGranularity);
  const blueskyPostsVsEngagementTimeline = mergeBucketedSeries({
    posts: blueskyPostsEngagement.posts_vs_engagement?.posts || [],
    engagement: blueskyPostsEngagement.posts_vs_engagement?.engagement || [],
  }, days, blueskyChartGranularity);
  const blueskyEngagementActionsTimeline = mergeBucketedSeries({
    likes: blueskyPostsEngagement.engagement_actions?.likes || [],
    replies: blueskyPostsEngagement.engagement_actions?.replies || [],
    reposts: blueskyPostsEngagement.engagement_actions?.reposts || [],
    quotes: blueskyPostsEngagement.engagement_actions?.quotes || [],
  }, days, blueskyChartGranularity);
  const blueskyPostEngagementTimeline = bucketSeriesByGranularity(
    blueskyPostsEngagement.post_engagement || [],
    days,
    blueskyChartGranularity,
  );
  const blueskyFollowerGrowthHasData = chartHasData(blueskyFollowerTimeline, ['count']);
  const blueskyPostsVsEngagementHasData = chartHasData(blueskyPostsVsEngagementTimeline, ['posts', 'engagement']);
  const blueskyPostEngagementHasData = chartHasData(blueskyPostEngagementTimeline, ['count']);
  const blueskyEngagementActionsHasData = chartHasData(blueskyEngagementActionsTimeline, ['likes', 'replies', 'reposts', 'quotes']);
  const blueskyMessagesMentionsHasData = chartHasData(blueskyMessagesMentionsTimeline, ['mentions', 'messages']);
  const blueskyTopPosts = [...(blueskyPostsEngagement.top_posts || [])].sort((a, b) => {
    const metricValue = (post, metric) => {
      if (metric === 'likes') return post.likes || 0;
      if (metric === 'replies') return post.replies || 0;
      if (metric === 'reposts') return post.reposts || 0;
      if (metric === 'quotes') return post.quotes || 0;
      if (metric === 'engagement_rate') return post.engagement_rate || 0;
      return post.engagement || 0;
    };
    return metricValue(b, blueskyTopMetric) - metricValue(a, blueskyTopMetric);
  });
  const blueskyViewSelector = (
    <select
      value={blueskyChartGranularity}
      onChange={(event) => setBlueskyChartGranularity(event.target.value)}
      className="rounded-lg border border-gray-200 bg-offwhite px-3 py-2 text-sm font-semibold text-gray-700"
    >
      {BLUESKY_GRANULARITY_OPTIONS.map((option) => (
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  );
  const instagramReachSelector = (
    <select
      value={instagramReachGranularity}
      onChange={(event) => setInstagramReachGranularity(event.target.value)}
      className="rounded-lg border border-gray-200 bg-offwhite px-3 py-2 text-sm font-semibold text-gray-700"
    >
      {BLUESKY_GRANULARITY_OPTIONS.map((option) => (
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  );
  const youtubeSummary = youtubeReport?.summary || {};
  const youtubeAudience = youtubeReport?.audience || {};
  const youtubeVideoPerformance = youtubeReport?.video_performance || {};
  const youtubeWatchQualitySummary = youtubeSummary.watch_quality_summary || {};
  const youtubeViewsByGeographyCard = normalizeYoutubeGeographyCard(
    youtubeVideoPerformance.views_by_geography,
    'Views',
  );
  const youtubeMinutesByGeographyCard = normalizeYoutubeGeographyCard(
    youtubeVideoPerformance.estimated_minutes_watched_by_geography,
    'Minutes Watched',
  );
  const youtubeSubscriberGrowthTimeline = bucketMultiValueSeries(
    youtubeAudience.subscriber_growth || [],
    days,
    youtubeChartGranularity,
    ['gained', 'lost', 'net'],
  );
  const youtubeViewsMinutesTimeline = mergeBucketedSeries(
    {
      views: youtubeVideoPerformance.views_minutes_series?.views || [],
      estimated_minutes_watched: youtubeVideoPerformance.views_minutes_series?.estimated_minutes_watched || [],
    },
    days,
    youtubeChartGranularity,
  );
  const youtubeWatchQualityTimeline = bucketYoutubeWatchQualitySeries(
    youtubeWatchQualitySummary.series || [],
    days,
    youtubeChartGranularity,
  );
  const youtubeSubscriberGrowthHasData = chartHasData(youtubeSubscriberGrowthTimeline, ['gained', 'lost', 'net']);
  const youtubeViewsMinutesHasData = chartHasData(youtubeViewsMinutesTimeline, ['views', 'estimated_minutes_watched']);
  const youtubeWatchQualityHasData = chartHasData(
    youtubeWatchQualityTimeline,
    ['engaged_views', 'average_view_duration_seconds', 'average_view_percentage'],
  );
  const youtubeTopVideos = youtubeTopVideoMetric === 'estimated_minutes_watched'
    ? (youtubeVideoPerformance.top_videos?.top5_minutes_watched || [])
    : (youtubeVideoPerformance.top_videos?.top5_views || []);
  const youtubeRetention = useMemo(() => youtubeVideoPerformance.retention || {}, [youtubeVideoPerformance.retention]);
  const youtubeAutoRefreshSeconds = Number(
    youtubeViewsByGeographyCard.meta?.auto_refresh_seconds
    || youtubeMinutesByGeographyCard.meta?.auto_refresh_seconds
    || 15 * 60
  );
  useEffect(() => {
    const availableIds = (youtubeRetention.videos || []).map((video) => video.video_id).filter(Boolean);
    if (!availableIds.length) {
      if (youtubeRetentionVideoId) setYoutubeRetentionVideoId('');
      return;
    }
    if (youtubeRetention.selected_video_id && !availableIds.includes(youtubeRetentionVideoId)) {
      setYoutubeRetentionVideoId(youtubeRetention.selected_video_id);
      return;
    }
    if (!youtubeRetentionVideoId || !availableIds.includes(youtubeRetentionVideoId)) {
      setYoutubeRetentionVideoId(availableIds[0]);
    }
  }, [youtubeRetention, youtubeRetentionVideoId]);
  useEffect(() => {
    if (
      selectedPlatform !== 'youtube'
      || !['youtube-summary', 'youtube-audience', 'youtube-video-performance'].includes(activeTab)
    ) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
        return;
      }
      fetchYoutubeReport();
    }, Math.max(youtubeAutoRefreshSeconds, 60) * 1000);

    return () => window.clearInterval(intervalId);
  }, [activeTab, selectedPlatform, fetchYoutubeReport, youtubeAutoRefreshSeconds]);

  const youtubeChartSelector = (
    <select
      value={youtubeChartGranularity}
      onChange={(event) => setYoutubeChartGranularity(event.target.value)}
      className="rounded-lg border border-gray-200 bg-offwhite px-3 py-2 text-sm font-semibold text-gray-700"
    >
      {BLUESKY_GRANULARITY_OPTIONS.map((option) => (
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  );

  const tiktokSummary = tiktokReport?.summary || {};
  const tiktokOverview = tiktokReport?.overview || {};
  const tiktokContent = tiktokReport?.content || {};
  const tiktokViewers = tiktokReport?.viewers || {};
  const tiktokFollowers = tiktokReport?.followers || {};
  const tiktokOverviewSeries = mergeBucketedSeries(
    {
      followers: tiktokOverview.followers_series || [],
      likes: tiktokOverview.likes_series || [],
      videos: tiktokOverview.videos_series || [],
    },
    days,
    'day',
  );
  const tiktokFollowersSeries = bucketSeriesByGranularity(
    tiktokFollowers.followers_series || tiktokOverview.followers_series || [],
    days,
    'day',
  );
  const tiktokViewsSeries = bucketSeriesByGranularity(tiktokContent.post_views_series || [], days, 'day');
  const tiktokEngagementSeries = bucketSeriesByGranularity(tiktokContent.engagement_series || [], days, 'day');
  const tiktokPublishedVideosSeries = bucketSeriesByGranularity(tiktokContent.videos_series || [], days, 'day');
  const tiktokOverviewHasCharts = chartHasData(tiktokOverviewSeries, ['followers', 'likes', 'videos']);
  const tiktokFollowersHasData = chartHasData(tiktokFollowersSeries, ['count']);
  const tiktokContentHasCharts = chartHasData(tiktokViewsSeries, ['count']) || chartHasData(tiktokEngagementSeries, ['count']) || chartHasData(tiktokPublishedVideosSeries, ['count']);
  const tiktokTopPostsByMetric = {
    views: tiktokContent.top_posts_by_views || [],
    likes: tiktokContent.top_posts_by_likes || [],
    comments: tiktokContent.top_posts_by_comments || [],
    shares: tiktokContent.top_posts_by_shares || [],
  };
  const tiktokTopPosts = tiktokTopPostsByMetric[tiktokTopMetric] || [];

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
            platformOrder={platformOrder}
            draggingPlatform={draggingPlatform}
            onDragStart={handlePlatformDragStart}
            onDragEnter={handlePlatformDragEnter}
            onDragEnd={handlePlatformDragEnd}
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
          {platformOrder.filter((plat) => accounts.some((account) => account.platform === plat)).map((plat) => (
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

        {/* ── Platform analytics notice ───────────────────────────── */}
        {selectedPlatformNotice && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <svg className="h-4 w-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
            </svg>
            {selectedPlatformNotice}
          </div>
        )}

        {/* ── Tabs ─────────────────────────────────────────────────── */}
        <div className="flex border-b border-gray-200 mb-6 gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabClick(tab.id)}
              className={`px-4 py-2.5 text-sm font-semibold border-b-2 transition-all -mb-px
                ${activeTab === tab.id
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* ━━━━━━━━━━━━━━━━━ TIKTOK OVERVIEW TAB ━━━━━━━━━━━━━━━━━━━━━ */}
        {activeTab === 'overview' && selectedPlatform === 'tiktok' && (
          <div className="space-y-6">
            {!!tiktokReport?.message && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {tiktokReport.message}
              </div>
            )}

            {!!tiktokReport?.errors?.length && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {tiktokReport.errors.map((item, idx) => (
                  <div key={`${item.account}-${idx}`}>
                    <span className="font-semibold">{item.account}:</span> {item.error}
                  </div>
                ))}
              </div>
            )}

            {loadingTikTokReport ? (
              <div className="space-y-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="bg-offwhite rounded-xl border border-gray-200 h-36 animate-pulse" />
                ))}
              </div>
            ) : !tiktokReport?.supported ? (
              <div className="bg-offwhite rounded-xl border border-gray-200 p-8 text-center">
                <p className="text-gray-500 font-medium">TikTok report not available</p>
                <p className="text-sm text-gray-400 mt-1">
                  {tiktokReport?.message || 'Connect a TikTok account to see this report.'}
                </p>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  <ReportMetricTile title="Total Followers" value={tiktokSummary.followers_total} subtitle="Current TikTok followers" />
                  <ReportMetricTile title="Following" value={tiktokSummary.following_total} subtitle="Accounts this TikTok profile follows" />
                  <ReportMetricTile title="Total Likes" value={tiktokSummary.likes_total} subtitle="Total likes shown by TikTok profile stats" accent="text-rose-600" />
                  <ReportMetricTile title="Total Videos" value={tiktokSummary.videos_total} subtitle="Current TikTok video count" accent="text-violet-600" />
                  <ReportMetricTile title={`Net Followers (${days}d)`} value={tiktokSummary.net_followers} subtitle={tiktokFollowers.history_message || 'Net follower change based on app snapshots in the selected period.'} accent={tiktokSummary.net_followers < 0 ? 'text-rose-600' : 'text-emerald-600'} />
                  <ReportMetricTile title="Videos Published" value={tiktokSummary.videos_published_in_period} subtitle="Videos surfaced in the selected period" accent="text-sky-700" />
                </div>

                <ReportCard title="Account Totals Over Time" info="Tracks TikTok follower totals, profile likes, and total videos across app-owned daily snapshots.">
                  {tiktokOverview.history_message && (
                    <div className="mb-4 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
                      {tiktokOverview.history_message}
                    </div>
                  )}
                  {tiktokOverviewHasCharts ? (
                    <ResponsiveContainer width="100%" height={300}>
                      <ComposedChart data={tiktokOverviewSeries}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                        <YAxis yAxisId="left" allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                        <YAxis yAxisId="right" orientation="right" allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                        <Tooltip />
                        <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
                        <Line yAxisId="left" type="monotone" dataKey="followers" name="Followers" stroke="#2f6690" strokeWidth={2.5} dot={false} />
                        <Line yAxisId="left" type="monotone" dataKey="likes" name="Total Likes" stroke="#ef4444" strokeWidth={2.5} dot={false} />
                        <Bar yAxisId="right" dataKey="videos" name="Total Videos" fill="#8b5cf6" radius={[4, 4, 0, 0]} barSize={18} minPointSize={2} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  ) : (
                    chartEmptyState(tiktokOverview.history_message || 'TikTok historical trend lines will appear after app snapshots accumulate.')
                  )}
                </ReportCard>

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <ReportCard title="Traffic Source" info="TikTok’s app can show where viewers discovered your posts, but the connected developer API does not expose this breakdown to Unravler today.">
                    {chartEmptyState(tiktokOverview.traffic_source_message)}
                  </ReportCard>
                  <ReportCard title="Search Queries" info="TikTok’s app can show search queries that led viewers to your posts, but the connected developer API does not expose them to Unravler today.">
                    {chartEmptyState(tiktokOverview.search_queries_message)}
                  </ReportCard>
                </div>
              </>
            )}
          </div>
        )}

        {/* ━━━━━━━━━━━━━━━━━ OVERVIEW TAB ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
        {activeTab === 'overview' && selectedPlatform !== 'tiktok' && (
          <div className="space-y-6">

            {hasContentOutsideWindow && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                This {PLATFORM_LABELS[selectedPlatform] || selectedPlatform} account has{' '}
                <span className="font-semibold">{fmt(selectedConnectedAccount?.posts_count || 0)}</span>{' '}
                total {selectedPlatform === 'youtube' ? 'videos' : 'posts'}, but none fall within the selected{' '}
                <span className="font-semibold">{days}-day</span> range. The Posts tab can still show recent account content outside this window.
              </div>
            )}

            {!!engagement?.errors?.length && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {engagement.errors.map((item, idx) => (
                  <div key={`${item.account}-${idx}`}>
                    <span className="font-semibold">{item.account}:</span> {item.error}
                  </div>
                ))}
              </div>
            )}

            {!!overview?.errors?.length && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {overview.errors.map((item, idx) => (
                  <div key={`${item.account}-${idx}`}>
                    <span className="font-semibold">{item.account}:</span> {item.error}
                  </div>
                ))}
              </div>
            )}

            {/* Engagement stat cards */}
            <div className={`grid gap-4 ${(audienceMetricCards.length + visibleMetricCards.length + 1) >= 5 ? 'grid-cols-2 md:grid-cols-3 xl:grid-cols-5' : 'grid-cols-2 md:grid-cols-3 xl:grid-cols-4'}`}>
              {audienceMetricCards.map(({ key, label, icon, value, color }) => (
                <EngagementCard
                  key={key}
                  icon={icon}
                  label={label}
                  value={value}
                  color={color}
                  loading={loadingOverview}
                />
              ))}
              <EngagementCard
                icon={FaFileAlt}
                label="Posts Published"
                value={overview?.published_in_period}
                color="bg-indigo-500"
                loading={loadingOverview}
              />
              {visibleMetricCards.map(({ key, label, icon, value, color }) => (
                <EngagementCard
                  key={key}
                  icon={icon}
                  label={label}
                  value={value}
                  color={color}
                  loading={loadingEngagement}
                />
              ))}
            </div>

            {(audienceMetricCards.length > 0 || selectedPlatform) && (
              <div className="rounded-xl border border-gray-200 bg-offwhite px-4 py-3 text-sm text-gray-600">
                Audience metrics come directly from the connected platform API when that platform exposes them. Unsupported metrics stay hidden instead of showing synthetic values.
                {selectedPlatform === 'youtube' && ' YouTube follower growth uses subscriber gained/lost analytics; reach is not exposed as a channel-level metric.'}
                {selectedPlatform === 'tiktok' && ' TikTok follower totals require the account to be connected with stats scopes.'}
              </div>
            )}

            {/* Engagement insights row */}
            {!loadingEngagement && engagement?.totals?.total_posts > 0 && showEngagementInsights && (
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
            <div className={`grid grid-cols-1 gap-4 ${showEngagementInsights ? 'xl:grid-cols-2' : ''}`}>

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

              {showEngagementInsights && (
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
                        {summaryMetricColumns.map(({ key, label }, index) => (
                          <Bar
                            key={key}
                            dataKey={key}
                            name={label}
                            stackId="engagement"
                            fill={
                              key === 'likes' ? '#ef4444'
                                : key === 'comments' ? '#3b82f6'
                                : key === 'shares' ? '#22c55e'
                                : '#f59e0b'
                            }
                            radius={index === summaryMetricColumns.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
                          />
                        ))}
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
              )}
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

            {showEngagementInsights && (
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
                    {topPostMetricLabel || 'No posts with engagement data yet. Connect accounts and publish posts to see results here.'}
                  </div>
                ) : (
                  <div className="space-y-2">
                    {(engagement?.top_posts || []).slice(0, 5).map((post, i) => {
                      const plat = post.platform || 'unknown';
                      const Icon = PLATFORM_ICONS[plat] || FaFileAlt;
                      const color = PLATFORM_COLORS[plat] || '#6b7280';
                      const m = post.metrics || {};
                      const dt = parseDate(post.published_at);
                      const support = PLATFORM_METRICS[plat] || {};
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
                            {support.likes && <span className="flex items-center gap-1"><FaHeart className="text-rose-400" />{fmt(m.likes)}</span>}
                            {support.comments && <span className="flex items-center gap-1"><FaComment className="text-blue-400" />{fmt(m.comments)}</span>}
                            {support.shares && <span className="flex items-center gap-1"><FaShare className="text-green-400" />{fmt(m.shares)}</span>}
                            {support.views && <span className="flex items-center gap-1"><FaEye className="text-purple-400" />{fmt(m.views)}</span>}
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
            )}

            {/* Platform summary table */}
            {overview?.platform_counts && Object.keys(overview.platform_counts).length > 0 && (
              <div className="bg-offwhite rounded-xl border border-gray-200 p-5">
                <h3 className="text-sm font-semibold text-gray-700 mb-4">Platform Summary</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs font-semibold text-gray-400 uppercase tracking-wide border-b border-gray-100">
                        <th className="text-left py-2 pr-4">Platform</th>
                        <th className="text-right py-2 pr-4">Followers</th>
                        <th className="text-right py-2 pr-4">Growth</th>
                        <th className="text-right py-2 pr-4">Reach / Impr.</th>
                        <th className="text-right py-2 pr-4">Posts</th>
                        {summaryMetricColumns.map(({ key, label }) => (
                          <th key={key} className="text-right py-2 pr-4">{label}</th>
                        ))}
                        {showEngRateColumn && <th className="text-right py-2">Eng. Rate</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(overview.platform_counts)
                        .sort((a, b) => b[1] - a[1])
                        .map(([plat, count]) => {
                          const Icon = PLATFORM_ICONS[plat] || FaFileAlt;
                          const color = PLATFORM_COLORS[plat] || '#6b7280';
                          const pd = engagement?.platform_breakdown?.[plat] || {};
                          const accountRows = overviewAccounts.filter((account) => account.platform === plat);
                          const support = aggregateAudienceSupport(accountRows);
                          const followerTotal = support.followers_total
                            ? accountRows.reduce((sum, account) => sum + (account.followers_count || 0), 0)
                            : null;
                          const followerGrowth = support.followers_growth
                            ? accountRows.reduce((sum, account) => sum + (account.followers_growth || 0), 0)
                            : null;
                          const reachOrImpressions = support.reach
                            ? accountRows.reduce((sum, account) => sum + (account.reach || 0), 0)
                            : (support.impressions
                              ? accountRows.reduce((sum, account) => sum + (account.impressions || 0), 0)
                              : null);
                          const sup = PLATFORM_METRICS[plat] || {};
                          return (
                            <tr key={plat} className="border-b border-gray-50 hover:bg-gray-50">
                              <td className="py-2.5 pr-4">
                                <div className="flex items-center gap-2">
                                  <Icon style={{ color }} className="text-base" />
                                  <span className="font-medium text-gray-700">{PLATFORM_LABELS[plat] || plat}</span>
                                </div>
                              </td>
                              <td className="text-right py-2.5 pr-4 text-gray-600">{fmt(followerTotal)}</td>
                              <td className="text-right py-2.5 pr-4 text-gray-600">{fmt(followerGrowth)}</td>
                              <td className="text-right py-2.5 pr-4 text-gray-600">{fmt(reachOrImpressions)}</td>
                              <td className="text-right py-2.5 pr-4 font-semibold text-gray-900">{count}</td>
                              {summaryMetricColumns.map(({ key }) => (
                                <td key={key} className="text-right py-2.5 pr-4 text-gray-600">
                                  {sup[key] ? fmt(pd[key] ?? 0) : '—'}
                                </td>
                              ))}
                              {showEngRateColumn && (
                                <td className="text-right py-2.5 text-gray-600">
                                  {pd.posts > 0 && (sup.likes || sup.comments || sup.shares)
                                    ? (((pd.likes || 0) + (pd.comments || 0) + (pd.shares || 0)) / pd.posts).toFixed(1)
                                    : '—'
                                  }
                                </td>
                              )}
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

        {/* ━━━━━━━━━━━━━━━━━ BLUESKY REPORT TABS ━━━━━━━━━━━━━━━━━━━━━ */}
        {['bluesky-summary', 'bluesky-audience', 'bluesky-posts-engagement'].includes(activeTab) && selectedPlatform === 'bluesky' && (
          <div className="space-y-6">
            {!!blueskyReport?.errors?.length && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {blueskyReport.errors.map((item, idx) => (
                  <div key={`${item.account}-${idx}`}>
                    <span className="font-semibold">{item.account}:</span> {item.error}
                  </div>
                ))}
              </div>
            )}

            {!!blueskyReport?.message_errors?.length && activeTab !== 'bluesky-summary' && (
              <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
                {blueskyReport.message_errors.map((item, idx) => (
                  <div key={`${item.account}-msg-${idx}`}>
                    <span className="font-semibold">{item.account}:</span> {item.error}
                  </div>
                ))}
              </div>
            )}

            {loadingBlueskyReport ? (
              <div className="space-y-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="bg-offwhite rounded-xl border border-gray-200 h-36 animate-pulse" />
                ))}
              </div>
            ) : !blueskyReport?.supported ? (
              <div className="bg-offwhite rounded-xl border border-gray-200 p-8 text-center">
                <p className="text-gray-500 font-medium">Bluesky report not available</p>
                <p className="text-sm text-gray-400 mt-1">
                  {blueskyReport?.message || 'Connect a Bluesky account to see this report.'}
                </p>
              </div>
            ) : (
              <>
                {activeTab === 'bluesky-summary' && (
                  <div className="space-y-6">
                    <ReportCard title="Audience Summary">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Total Followers</p>
                          <p className="mt-2 text-4xl font-bold text-sky-600">{fmt(blueskySummary.followers_total)}</p>
                          <p className="mt-2 text-sm text-gray-500">Total followers for the selected Bluesky account.</p>
                        </div>
                        <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">New Followers</p>
                          <div className="mt-2 flex items-end gap-2">
                            <p className="text-4xl font-bold text-sky-600">{fmt(blueskySummary.new_followers)}</p>
                            {blueskySummary.new_followers_change_pct != null && (
                              <span className={`text-sm font-semibold ${pctPillColor(blueskySummary.new_followers_change_pct)}`}>
                                {pctLabel(blueskySummary.new_followers_change_pct)}
                              </span>
                            )}
                          </div>
                          <p className="mt-2 text-sm text-gray-500">Avg. per day: {blueskySummary.avg_new_followers_per_day ?? 0}</p>
                        </div>
                        <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Following</p>
                          <p className="mt-2 text-4xl font-bold text-sky-600">{fmt(blueskySummary.following_total)}</p>
                          <p className="mt-2 text-sm text-gray-500">Accounts followed by this Bluesky profile.</p>
                        </div>
                      </div>
                    </ReportCard>

                    <ReportCard title="Posts and Engagement Summary">
                      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
                        <div className="space-y-4">
                          <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                            <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Total Posts</p>
                            <div className="mt-2 flex items-end gap-2">
                              <p className="text-4xl font-bold text-sky-600">{fmt(blueskySummary.post_summary?.total_posts)}</p>
                              {blueskySummary.post_summary?.total_posts_change_pct != null && (
                                <span className={`text-sm font-semibold ${pctPillColor(blueskySummary.post_summary.total_posts_change_pct)}`}>
                                  {pctLabel(blueskySummary.post_summary.total_posts_change_pct)}
                                </span>
                              )}
                            </div>
                            <p className="mt-2 text-sm text-gray-500">Avg. per day: {blueskySummary.post_summary?.avg_posts_per_day ?? 0}</p>
                          </div>
                          <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                            <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Total Engagements</p>
                            <div className="mt-2 flex items-end gap-2">
                              <p className="text-4xl font-bold text-sky-600">{fmt(blueskySummary.post_summary?.total_engagement)}</p>
                              {blueskySummary.post_summary?.total_engagement_change_pct != null && (
                                <span className={`text-sm font-semibold ${pctPillColor(blueskySummary.post_summary.total_engagement_change_pct)}`}>
                                  {pctLabel(blueskySummary.post_summary.total_engagement_change_pct)}
                                </span>
                              )}
                            </div>
                            <p className="mt-2 text-sm text-gray-500">Avg. per day: {blueskySummary.post_summary?.avg_engagement_per_day ?? 0}</p>
                          </div>
                        </div>

                        <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-3">Top Post</p>
                          {blueskySummary.post_summary?.top_post ? (
                            <div className="space-y-3">
                              {blueskySummary.post_summary.top_post.media_url ? (
                                <img
                                  src={blueskySummary.post_summary.top_post.media_url}
                                  alt=""
                                  className="w-full h-44 rounded-xl object-cover"
                                  onError={(e) => { e.target.style.display = 'none'; }}
                                />
                              ) : (
                                <div className="w-full h-44 rounded-xl bg-gray-100 flex items-center justify-center text-sm text-gray-400">
                                  No media preview
                                </div>
                              )}
                              <div className="flex items-center gap-2 text-xs text-gray-500">
                                <span className="font-semibold">{blueskySummary.post_summary.top_post.source_app}</span>
                                {blueskySummary.post_summary.top_post.timestamp && (
                                  <span>{formatReportDate(blueskySummary.post_summary.top_post.timestamp, days)}</span>
                                )}
                              </div>
                              <p className="text-sm text-gray-700 line-clamp-4">
                                {blueskySummary.post_summary.top_post.content || '(no caption)'}
                              </p>
                              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-gray-600">
                                <span>Likes</span><span className="text-right font-semibold">{fmt(blueskySummary.post_summary.top_post.likes)}</span>
                                <span>Replies</span><span className="text-right font-semibold">{fmt(blueskySummary.post_summary.top_post.replies)}</span>
                                <span>Reposts</span><span className="text-right font-semibold">{fmt(blueskySummary.post_summary.top_post.reposts)}</span>
                                <span>Quotes</span><span className="text-right font-semibold">{fmt(blueskySummary.post_summary.top_post.quotes)}</span>
                                <span>Engagements</span><span className="text-right font-semibold">{fmt(blueskySummary.post_summary.top_post.engagement)}</span>
                                <span>Engagement Rate</span><span className="text-right font-semibold">{blueskySummary.post_summary.top_post.engagement_rate}%</span>
                              </div>
                              {blueskySummary.post_summary.top_post.permalink && (
                                <a
                                  href={blueskySummary.post_summary.top_post.permalink}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-2 text-sm font-semibold text-indigo-600 hover:text-indigo-700"
                                >
                                  View on Bluesky <FaExternalLinkAlt className="text-xs" />
                                </a>
                              )}
                            </div>
                          ) : (
                            chartEmptyState('No Bluesky post engagement data is available for this period.')
                          )}
                        </div>

                        <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 min-w-0 overflow-hidden">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-3">Engagements by Post Type</p>
                          <ReportDonutBreakdown
                            items={blueskySummary.post_summary?.engagement_by_type || []}
                            valueKey="engagement"
                            totalValue={blueskySummary.post_summary?.total_engagement || 0}
                            emptyLabel="No Bluesky posts were returned for this period."
                          />
                        </div>
                      </div>
                    </ReportCard>
                  </div>
                )}

                {activeTab === 'bluesky-audience' && (
                  <div className="space-y-6">
                    <ReportCard title="Follower Growth" action={blueskyViewSelector}>
                      {blueskyFollowerGrowthHasData ? (
                        <>
                          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
                            <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                              <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Total Followers</p>
                              <p className="mt-2 text-3xl font-bold text-sky-600">{fmt(blueskySummary.followers_total)}</p>
                            </div>
                            <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                              <p className="text-xs font-bold uppercase tracking-widest text-gray-400">New Followers</p>
                              <p className="mt-2 text-3xl font-bold text-sky-600">{fmt(blueskySummary.new_followers)}</p>
                            </div>
                            <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                              <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Follower Change</p>
                              <p className={`mt-2 text-3xl font-bold ${pctPillColor(blueskySummary.new_followers_change_pct ?? 0)}`}>
                                {pctLabel(blueskySummary.new_followers_change_pct) || '0%'}
                              </p>
                            </div>
                            <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                              <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Avg. New Followers / Day</p>
                              <p className="mt-2 text-3xl font-bold text-sky-600">{blueskySummary.avg_new_followers_per_day ?? 0}</p>
                            </div>
                          </div>
                          <ResponsiveContainer width="100%" height={260}>
                            <BarChart data={blueskyFollowerTimeline}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                              <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                              <Tooltip content={<AudienceGrowthTooltip />} />
                              <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
                              <Bar dataKey="count" name="New Followers" fill="#2f6690" radius={[6, 6, 0, 0]} barSize={32} minPointSize={2} />
                            </BarChart>
                          </ResponsiveContainer>
                        </>
                      ) : (
                        chartEmptyState('Follower growth data is not available for this Bluesky account right now.')
                      )}
                    </ReportCard>
                  </div>
                )}

                {activeTab === 'bluesky-posts-engagement' && (
                  <div className="space-y-6">
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                      <ReportCard title="Number of Posts vs Engagement" action={blueskyViewSelector}>
                        {blueskyPostsVsEngagementHasData ? (
                          <ResponsiveContainer width="100%" height={240}>
                            <ComposedChart data={blueskyPostsVsEngagementTimeline}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                              <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                              <YAxis yAxisId="left" allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                              <YAxis yAxisId="right" orientation="right" allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                              <Tooltip />
                              <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
                              <Bar yAxisId="left" dataKey="posts" name="Posts" fill="#2f6690" radius={[4, 4, 0, 0]} barSize={28} minPointSize={2} />
                              <Line yAxisId="right" type="monotone" dataKey="engagement" name="Engagement" stroke="#22c55e" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                            </ComposedChart>
                          </ResponsiveContainer>
                        ) : (
                          chartEmptyState()
                        )}
                      </ReportCard>

                      <ReportCard title="Posts by Type">
                        {(blueskyPostsEngagement.posts_by_type || []).some((item) => item.posts > 0) ? (
                          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-center">
                            <div className="h-[220px]">
                              <InteractiveDonutChart
                                data={(blueskyPostsEngagement.posts_by_type || []).filter((item) => item.posts > 0)}
                                dataKey="posts"
                                colors={['#2f6690', '#9ca3af', '#8b5cf6', '#22c55e', '#f59e0b']}
                                innerRadius={55}
                                outerRadius={85}
                                paddingAngle={2}
                                getItemKey={(item) => item.type}
                                centerContent={(
                                  <>
                                    <span className="text-3xl font-semibold leading-none text-gray-700">{fmt(blueskySummary.post_summary?.total_posts || 0)}</span>
                                    <span className="mt-2 text-sm font-medium text-gray-500">Posts</span>
                                  </>
                                )}
                              />
                            </div>
                            <div className="space-y-3">
                              {(blueskyPostsEngagement.posts_by_type || []).map((item) => {
                                const total = (blueskySummary.post_summary?.total_posts || 1);
                                const pct = Math.round(((item.posts || 0) / total) * 100);
                                return (
                                  <div key={item.type} className="flex items-center justify-between text-sm gap-3">
                                    <span className="font-medium text-gray-700">{item.label}</span>
                                    <span className="text-gray-500">{fmt(item.posts)} • {pct}%</span>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        ) : (
                          chartEmptyState()
                        )}
                      </ReportCard>
                    </div>

                    <ReportCard
                      title="Top Posts By"
                      action={(
                        <select
                          value={blueskyTopMetric}
                          onChange={(event) => setBlueskyTopMetric(event.target.value)}
                          className="rounded-lg border border-gray-200 bg-offwhite px-3 py-2 text-sm font-semibold text-gray-700"
                        >
                          <option value="likes">Likes</option>
                          <option value="replies">Replies</option>
                          <option value="reposts">Reposts</option>
                          <option value="quotes">Quotes</option>
                          <option value="engagement">Engagement</option>
                          <option value="engagement_rate">Engagement Rate</option>
                        </select>
                      )}
                    >
                      {blueskyTopPosts.length > 0 ? (
                        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                          {blueskyTopPosts.slice(0, 6).map((post) => (
                            <div key={post.id} className="rounded-xl border border-gray-100 bg-gray-50 p-4 space-y-3">
                              <div className="flex items-center gap-2 text-xs text-gray-500">
                                <span className="font-semibold">{post.source_app}</span>
                                {post.timestamp && <span>{formatReportDate(post.timestamp, days)}</span>}
                              </div>
                              {post.media_url ? (
                                <img
                                  src={post.media_url}
                                  alt=""
                                  className="w-full h-28 rounded-xl object-cover"
                                  onError={(e) => { e.target.style.display = 'none'; }}
                                />
                              ) : (
                                <div className="w-full h-28 rounded-xl bg-gray-100 flex items-center justify-center text-sm text-gray-400">
                                  No media preview
                                </div>
                              )}
                              <p className="text-sm text-gray-700 line-clamp-3">{post.content || '(no caption)'}</p>
                              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-gray-600">
                                <span>Likes</span><span className="text-right font-semibold">{fmt(post.likes)}</span>
                                <span>Replies</span><span className="text-right font-semibold">{fmt(post.replies)}</span>
                                <span>Reposts</span><span className="text-right font-semibold">{fmt(post.reposts)}</span>
                                <span>Quotes</span><span className="text-right font-semibold">{fmt(post.quotes)}</span>
                                <span>Engagement</span><span className="text-right font-semibold">{fmt(post.engagement)}</span>
                                <span>Engagement Rate</span><span className="text-right font-semibold">{post.engagement_rate}%</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        chartEmptyState()
                      )}
                    </ReportCard>

                    <ReportCard title="Posts by Publishing Apps">
                      {(blueskyPostsEngagement.posts_by_publishing_apps || []).length > 0 ? (
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="text-xs font-semibold text-gray-400 uppercase tracking-wide border-b border-gray-100">
                                <th className="text-left py-2 pr-4">Apps</th>
                                <th className="text-right py-2 pr-4">Posts</th>
                                <th className="text-right py-2 pr-4">Likes</th>
                                <th className="text-right py-2 pr-4">Replies</th>
                                <th className="text-right py-2 pr-4">Reposts</th>
                                <th className="text-right py-2">Quotes</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(blueskyPostsEngagement.posts_by_publishing_apps || []).map((item) => (
                                <tr key={item.app} className="border-b border-gray-50">
                                  <td className="py-2.5 pr-4 font-medium text-gray-700">{item.app}</td>
                                  <td className="text-right py-2.5 pr-4 text-gray-600">{fmt(item.posts)}</td>
                                  <td className="text-right py-2.5 pr-4 text-gray-600">{fmt(item.likes)}</td>
                                  <td className="text-right py-2.5 pr-4 text-gray-600">{fmt(item.replies)}</td>
                                  <td className="text-right py-2.5 pr-4 text-gray-600">{fmt(item.reposts)}</td>
                                  <td className="text-right py-2.5 text-gray-600">{fmt(item.quotes)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        chartEmptyState()
                      )}
                    </ReportCard>

                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                      <ReportCard title="Post Engagement" action={blueskyViewSelector}>
                        {blueskyPostEngagementHasData ? (
                          <ResponsiveContainer width="100%" height={240}>
                            <BarChart data={blueskyPostEngagementTimeline}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                              <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                              <Tooltip />
                              <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
                              <Bar dataKey="count" name="Engagement" fill="#2f6690" radius={[6, 6, 0, 0]} barSize={32} minPointSize={2} />
                            </BarChart>
                          </ResponsiveContainer>
                        ) : (
                          chartEmptyState()
                        )}
                      </ReportCard>

                      <ReportCard title="Engagement by Post Type">
                        <ReportDonutBreakdown
                          items={blueskyPostsEngagement.engagement_by_type || []}
                          valueKey="engagement"
                          totalValue={blueskySummary.post_summary?.total_engagement || 0}
                        />
                      </ReportCard>
                    </div>

                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                      <ReportCard title="Engagement Actions" action={blueskyViewSelector}>
                        {blueskyEngagementActionsHasData ? (
                          <ResponsiveContainer width="100%" height={260}>
                            <BarChart data={blueskyEngagementActionsTimeline}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                              <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                              <Tooltip />
                              <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
                              <Bar dataKey="likes" name="Likes" fill="#2f6690" radius={[4, 4, 0, 0]} barSize={24} minPointSize={2} />
                              <Bar dataKey="replies" name="Replies" fill="#d1d5db" radius={[4, 4, 0, 0]} barSize={24} minPointSize={2} />
                              <Bar dataKey="reposts" name="Reposts" fill="#9ca3af" radius={[4, 4, 0, 0]} barSize={24} minPointSize={2} />
                              <Bar dataKey="quotes" name="Quotes" fill="#f59e0b" radius={[4, 4, 0, 0]} barSize={24} minPointSize={2} />
                            </BarChart>
                          </ResponsiveContainer>
                        ) : (
                          chartEmptyState()
                        )}
                      </ReportCard>

                      <ReportCard title="Messages & Mentions Received" action={blueskyViewSelector}>
                        {blueskyMessagesMentionsHasData ? (
                          <ResponsiveContainer width="100%" height={260}>
                            <BarChart data={blueskyMessagesMentionsTimeline}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                              <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                              <Tooltip />
                              <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
                              <Bar dataKey="mentions" name="Mentions" fill="#2f6690" radius={[4, 4, 0, 0]} barSize={24} minPointSize={2} />
                              <Bar dataKey="messages" name="Messages" fill="#d1d5db" radius={[4, 4, 0, 0]} barSize={24} minPointSize={2} />
                            </BarChart>
                          </ResponsiveContainer>
                        ) : (
                          chartEmptyState(blueskyAudience.messages_message || 'There is no data available currently for this report.')
                        )}
                      </ReportCard>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ━━━━━━━━━━━━━━━━━ YOUTUBE REPORT TABS ━━━━━━━━━━━━━━━━━━━━━━━ */}
        {selectedPlatform === 'youtube' && ['youtube-summary', 'youtube-audience', 'youtube-video-performance'].includes(activeTab) && (
          <div className="space-y-6">
            {!!youtubeReport?.message && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {youtubeReport.message}
              </div>
            )}

            {!!youtubeReport?.errors?.length && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {youtubeReport.errors.map((item, idx) => (
                  <div key={`${item.account}-${idx}`}>
                    <span className="font-semibold">{item.account}:</span> {item.error}
                  </div>
                ))}
              </div>
            )}

            {loadingYoutubeReport ? (
              <div className="space-y-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="bg-offwhite rounded-xl border border-gray-200 h-36 animate-pulse" />
                ))}
              </div>
            ) : !youtubeReport?.supported ? (
              <div className="bg-offwhite rounded-xl border border-gray-200 p-8 text-center">
                <p className="text-gray-500 font-medium">YouTube report not available</p>
                <p className="text-sm text-gray-400 mt-1">
                  {youtubeReport?.message || 'Connect a YouTube account to see this report.'}
                </p>
              </div>
            ) : activeTab === 'youtube-summary' ? (
              <div className="space-y-6">
                <ReportCard title="Audience Summary" info="A quick snapshot of current subscribers, subscribers gained, and subscribers lost during the selected date range.">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <ReportMetricTile
                      title="Subscribers Count"
                      value={youtubeSummary.audience_summary?.subscribers_count}
                      subtitle="Current channel subscribers"
                    />
                    <ReportMetricTile
                      title="Subscribers Gained"
                      value={youtubeSummary.audience_summary?.subscribers_gained}
                      subtitle={`Avg. per day: ${youtubeSummary.audience_summary?.avg_gained_per_day ?? 0}`}
                      deltaPct={youtubeSummary.audience_summary?.gained_change_pct}
                    />
                    <ReportMetricTile
                      title="Subscribers Lost"
                      value={youtubeSummary.audience_summary?.subscribers_lost}
                      subtitle={`Avg. per day: ${youtubeSummary.audience_summary?.avg_lost_per_day ?? 0}`}
                      deltaPct={youtubeSummary.audience_summary?.lost_change_pct}
                    />
                  </div>
                </ReportCard>

                <ReportCard title="Post & Engagement Summary" info="Summarizes how many videos were published, the engagement they generated, and which geography contributed the most views.">
                  <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
                    <div className="space-y-4">
                      <ReportMetricTile
                        title="Videos"
                        value={youtubeSummary.post_summary?.videos}
                        subtitle={`Avg. per day: ${youtubeSummary.post_summary?.avg_videos_per_day ?? 0}`}
                        deltaPct={youtubeSummary.post_summary?.videos_change_pct}
                      />
                      <ReportMetricTile
                        title="Engagement"
                        value={youtubeSummary.post_summary?.engagement}
                        subtitle={`Avg. per day: ${youtubeSummary.post_summary?.avg_engagement_per_day ?? 0}`}
                        deltaPct={youtubeSummary.post_summary?.engagement_change_pct}
                      />
                    </div>
                    <YoutubeTopVideoCard
                      title="Top Video"
                      video={youtubeSummary.post_summary?.top_video}
                      metricLabel="Engagement"
                      primaryMetric="engagement"
                      info="Highlights the single best-performing video in the selected period based on engagement."
                    />
                    <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-3">Top Geography by Views</p>
                      {youtubeSummary.post_summary?.top_geography_by_views ? (
                        <div className="rounded-2xl border border-gray-200 bg-gradient-to-br from-white to-sky-50 p-5 shadow-sm">
                          <p className="text-xs font-bold uppercase tracking-[0.24em] text-sky-600">Leading Market</p>
                          <p className="mt-3 text-4xl font-semibold text-gray-900">
                            {countryNameForCode(youtubeSummary.post_summary.top_geography_by_views.country_code)}
                          </p>
                          <p className="mt-4 text-lg text-gray-500">
                            {fmt(youtubeSummary.post_summary.top_geography_by_views.count)} views in the selected period
                          </p>
                          <div className="mt-5 h-2 overflow-hidden rounded-full bg-sky-100">
                            <div className="h-full w-2/3 rounded-full bg-[#2f6690]" />
                          </div>
                        </div>
                      ) : (
                        chartEmptyState('No geography data is available for this period.')
                      )}
                    </div>
                  </div>
                </ReportCard>

                <ReportCard title="Cards Summary" info="Shows how often YouTube cards and teasers were shown and clicked across the selected reporting window.">
                  {youtubeReport?.supports?.cards ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                      <ReportMetricTile
                        title="Card Impressions"
                        value={youtubeSummary.cards_summary?.card_impressions}
                        subtitle={`Avg. per day: ${youtubeSummary.cards_summary?.avg_card_impressions_per_day ?? 0}`}
                        deltaPct={youtubeSummary.cards_summary?.card_impressions_change_pct}
                      />
                      <ReportMetricTile
                        title="Card Teaser Impressions"
                        value={youtubeSummary.cards_summary?.card_teaser_impressions}
                        deltaPct={youtubeSummary.cards_summary?.card_teaser_impressions_change_pct}
                      />
                      <ReportMetricTile
                        title="Card Clicks"
                        value={youtubeSummary.cards_summary?.card_clicks}
                        subtitle={`Avg. per day: ${youtubeSummary.cards_summary?.avg_card_clicks_per_day ?? 0}`}
                        deltaPct={youtubeSummary.cards_summary?.card_clicks_change_pct}
                      />
                      <ReportMetricTile
                        title="Card Teaser Clicks"
                        value={youtubeSummary.cards_summary?.card_teaser_clicks}
                        deltaPct={youtubeSummary.cards_summary?.card_teaser_clicks_change_pct}
                      />
                    </div>
                  ) : (
                    chartEmptyState('Card metrics are not available for this YouTube account right now.')
                  )}
                </ReportCard>

                <YoutubeWatchQualityCard
                  summary={youtubeWatchQualitySummary}
                  timeline={youtubeWatchQualityTimeline}
                  hasData={youtubeReport?.supports?.watch_quality && youtubeWatchQualityHasData}
                  action={youtubeChartSelector}
                />
              </div>
            ) : activeTab === 'youtube-audience' ? (
              <div className="space-y-6">
                <ReportCard title="Subscriber Growth" action={youtubeChartSelector} info="Tracks subscribers gained, lost, and net growth over time for the connected YouTube channel.">
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                    <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Total Subscribers</p>
                      <p className="mt-2 text-4xl font-bold text-sky-600">{fmt(youtubeAudience.total_subscribers)}</p>
                    </div>
                    <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Subscribers Gained</p>
                      <p className="mt-2 text-4xl font-bold text-sky-600">{fmt(youtubeAudience.subscribers_gained)}</p>
                    </div>
                    <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Subscribers Lost</p>
                      <p className="mt-2 text-4xl font-bold text-sky-600">{fmt(youtubeAudience.subscribers_lost)}</p>
                    </div>
                    <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Net Change</p>
                      <p className="mt-2 text-4xl font-bold text-sky-600">{fmt(youtubeAudience.net_change)}</p>
                      <p className="mt-2 text-sm text-gray-500">Avg. new subscriber per day: {youtubeAudience.avg_new_subscribers_per_day ?? 0}</p>
                    </div>
                  </div>
                  {youtubeSubscriberGrowthHasData ? (
                    <ResponsiveContainer width="100%" height={280}>
                      <ComposedChart data={youtubeSubscriberGrowthTimeline}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                        <Tooltip />
                        <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
                        <Bar dataKey="gained" name="Subscribers Gained" fill="#2f6690" radius={[4, 4, 0, 0]} barSize={22} minPointSize={2} />
                        <Bar dataKey="lost" name="Subscribers Lost" fill="#d1d5db" radius={[4, 4, 0, 0]} barSize={22} minPointSize={2} />
                        <Line dataKey="net" name="Net Change" stroke="#ef4444" strokeWidth={2} dot={false} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  ) : (
                    chartEmptyState('Subscriber growth data is not available for this YouTube account right now.')
                  )}
                </ReportCard>

                <YoutubeCountryMapCard
                  title="Subscriber by Geography"
                  rows={youtubeAudience.subscriber_by_geography || []}
                  metricLabel="Subscribers"
                  action={null}
                  info="Shows where your subscribers are located and how strongly each country contributes to your audience base."
                />

                <YoutubeDemographicsCard demographics={youtubeAudience.viewer_demographics} />
              </div>
            ) : (
              <div className="space-y-6">
                <ReportCard title="Views & Estimated Minutes Watched" action={youtubeChartSelector} info="Compares video view volume with estimated minutes watched so you can see reach versus watch-time quality together.">
                  {youtubeViewsMinutesHasData ? (
                    <div className="space-y-4">
                      <div className="flex flex-wrap justify-end gap-6 text-sm text-gray-500">
                        <span>Avg. Views per day: <strong className="text-emerald-600">{formatPreciseMetric(youtubeVideoPerformance.avg_views_per_day)}</strong></span>
                        <span>Avg. Minutes per day: <strong className="text-rose-500">{formatPreciseMetric(youtubeVideoPerformance.avg_minutes_watched_per_day)}</strong></span>
                      </div>
                      <ResponsiveContainer width="100%" height={280}>
                        <ComposedChart data={youtubeViewsMinutesTimeline}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                          <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                          <YAxis yAxisId="left" allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                          <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                          <Tooltip />
                          <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
                          <Bar yAxisId="left" dataKey="views" name="Views" fill="#2f6690" radius={[4, 4, 0, 0]} barSize={24} minPointSize={2} />
                          <Line yAxisId="right" type="monotone" dataKey="estimated_minutes_watched" name="Estimated Minutes Watched" stroke="#d1d5db" strokeWidth={2.5} dot={false} />
                        </ComposedChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    chartEmptyState('Views and watch-time data are not available for this period.')
                  )}
                </ReportCard>

                <YoutubeTopVideosStrip
                  title="Top Videos By"
                  videos={youtubeTopVideos}
                  metricLabel={youtubeTopVideoMetric === 'estimated_minutes_watched' ? 'Minutes Watched' : 'Views'}
                  primaryMetric={youtubeTopVideoMetric}
                  info="Ranks the channel's strongest videos in the selected period by views or minutes watched."
                  action={(
                    <select
                      value={youtubeTopVideoMetric}
                      onChange={(event) => setYoutubeTopVideoMetric(event.target.value)}
                      className="rounded-lg border border-gray-200 bg-offwhite px-3 py-2 text-sm font-semibold text-gray-700"
                    >
                      <option value="views">Views</option>
                      <option value="estimated_minutes_watched">Minutes Watched</option>
                    </select>
                  )}
                />

                <YoutubeCountryMapCard
                  title="Views by Geography"
                  rows={youtubeViewsByGeographyCard.rows}
                  metricLabel={youtubeViewsByGeographyCard.metricLabel}
                  meta={youtubeViewsByGeographyCard.meta}
                  info="Maps which countries generated the most YouTube views in the selected time window."
                  emptyLabel={youtubeViewsByGeographyCard.emptyLabel}
                />
                <YoutubeCountryMapCard
                  title="Estimated Minutes Watched by Geography"
                  rows={youtubeMinutesByGeographyCard.rows}
                  metricLabel={youtubeMinutesByGeographyCard.metricLabel}
                  meta={youtubeMinutesByGeographyCard.meta}
                  info="Maps where watch time came from, helping you compare high-view markets against high-retention markets."
                  emptyLabel={youtubeMinutesByGeographyCard.emptyLabel}
                  valueFormatter={formatPreciseMetric}
                />

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <YoutubeMetricBreakdownCard
                    title="Playback Location"
                    items={youtubeVideoPerformance.playback_location || []}
                    info="Breaks down where viewers watched your videos, such as watch pages, channel pages, and embedded players."
                    emptyLabel="Playback-location data is not available for this period."
                  />
                  <YoutubeMetricBreakdownCard
                    title="Traffic Source"
                    items={youtubeVideoPerformance.traffic_source || []}
                    info="Shows how viewers discovered your videos across YouTube search, suggested videos, external sources, and more."
                    emptyLabel="Traffic-source data is not available for this period."
                  />
                </div>

                <ReportCard title="Content Type Breakdown" info="Compares results across content formats and live versus on-demand viewing to reveal which content styles perform best.">
                  <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                    <YoutubeContentBreakdownCard
                      title="By Content Format"
                      rows={youtubeVideoPerformance.content_type_breakdown?.creator_content_type || []}
                      emptyLabel="Content-format data is not available for this period."
                    />
                    <YoutubeContentBreakdownCard
                      title="By Live / On Demand"
                      rows={youtubeVideoPerformance.content_type_breakdown?.live_or_on_demand || []}
                      emptyLabel="Live/on-demand data is not available for this period."
                    />
                  </div>
                </ReportCard>

                <ReportCard title="YouTube Search Terms" info="Lists the search queries that brought viewers to your content, with accompanying views and estimated watch time.">
                  {(youtubeVideoPerformance.youtube_search_terms || []).length > 0 ? (
                    <div className="divide-y divide-gray-100">
                      <div className="grid grid-cols-[minmax(0,1fr)_120px_180px] gap-x-4 pb-3 text-[11px] font-bold uppercase tracking-widest text-gray-400">
                        <span>Search Term</span>
                        <span className="text-right">Views</span>
                        <span className="text-right">Estimated Minutes Watched</span>
                      </div>
                      {youtubeVideoPerformance.youtube_search_terms.map((item) => (
                        <div key={item.term} className="grid grid-cols-[minmax(0,1fr)_120px_180px] gap-x-4 py-3 text-sm">
                          <span className="truncate font-medium text-gray-700">{item.term}</span>
                          <span className="text-right text-gray-700">{fmt(item.views)}</span>
                          <span className="text-right text-gray-700">{formatPreciseMetric(item.estimated_minutes_watched)}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    chartEmptyState()
                  )}
                </ReportCard>

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <YoutubeDeviceTypeCard items={youtubeVideoPerformance.views_by_device_type || []} />

                  <YoutubeSubscribedStatusCard items={youtubeVideoPerformance.views_minutes_by_subscribed_status || []} />
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <ReportCard title="Operating System Breakdown" info="Shows which operating systems your viewers used, ranked by share of total views.">
                    <ReportDonutBreakdown
                      items={(youtubeVideoPerformance.operating_system || []).map((item) => ({
                        ...item,
                        engagement: Number(item.views) || 0,
                      }))}
                      valueKey="engagement"
                      totalValue={(youtubeVideoPerformance.operating_system || []).reduce((sum, item) => sum + (Number(item.views) || 0), 0)}
                      valueHeader="Views"
                    />
                  </ReportCard>

                  <YoutubeSharingServicesCard items={youtubeVideoPerformance.sharing_services || []} />
                </div>

                <YoutubeRetentionCard
                  retention={youtubeRetention}
                  selectedVideoId={youtubeRetentionVideoId}
                  onSelectVideo={setYoutubeRetentionVideoId}
                />
              </div>
            )}
          </div>
        )}

        {/* ━━━━━━━━━━━━━━━━━ INSTAGRAM SUMMARY TAB ━━━━━━━━━━━━━━━━━━━━ */}
        {activeTab === 'summary' && selectedPlatform === 'instagram' && (
          <div className="space-y-6">
            {!!instagramReport?.errors?.length && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {instagramReport.errors.map((item, idx) => (
                  <div key={`${item.account}-${idx}`}>
                    <span className="font-semibold">{item.account}:</span> {item.error}
                  </div>
                ))}
              </div>
            )}

            {loadingInstagramReport ? (
              <div className="space-y-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="bg-offwhite rounded-xl border border-gray-200 h-36 animate-pulse" />
                ))}
              </div>
            ) : !instagramReport?.supported ? (
              <div className="bg-offwhite rounded-xl border border-gray-200 p-8 text-center">
                <p className="text-gray-500 font-medium">Instagram report not available</p>
                <p className="text-sm text-gray-400 mt-1">
                  {instagramReport?.message || 'Connect an Instagram Business or Creator account to see this report.'}
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <InstagramMetricTile
                    title="Total Followers"
                    value={instagramSummary.followers_total}
                    subtitle="Current Instagram followers"
                    info="Shows the latest follower total returned for the connected Instagram account."
                  />
                  <InstagramMetricTile
                    title="Net Follower Change"
                    value={instagramSummary.new_followers}
                    subtitle={`Net avg. per day: ${instagramSummary.avg_new_followers_per_day ?? 0}`}
                    info="Shows net follower change for the selected period. Positive values mean the account gained followers overall, and negative values mean it lost followers overall."
                  />
                </div>

                <InstagramDetailCard
                  title="Performance Summary"
                  info="Summarizes profile visits, posting volume, and total engagement generated during the selected date range."
                >
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Profile Views</p>
                      <p className="mt-2 text-3xl font-bold text-gray-900">{fmt(instagramSummary.profile_views)}</p>
                      <p className="mt-2 text-sm text-gray-500">Total profile views in the selected period.</p>
                    </div>
                    <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Posts Published</p>
                      <p className="mt-2 text-3xl font-bold text-gray-900">{fmt(instagramSummary.post_summary?.total_posts)}</p>
                      <p className="mt-2 text-sm text-gray-500">Avg. per day: {instagramSummary.post_summary?.avg_posts_per_day ?? 0}</p>
                    </div>
                    <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Total Engagement</p>
                      <p className="mt-2 text-3xl font-bold text-gray-900">{fmt(instagramSummary.post_summary?.total_engagement)}</p>
                      <p className="mt-2 text-sm text-gray-500">Avg. per post: {instagramSummary.post_summary?.avg_engagement_per_post ?? 0}</p>
                    </div>
                  </div>
                </InstagramDetailCard>

                <InstagramDetailCard
                  title="Reach Summary"
                  info="Compares how many accounts saw your content with the total number of impressions those posts generated."
                >
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <InstagramMetricTile
                      title="Reach"
                      value={instagramSummary.reach}
                      subtitle="Accounts reached in the selected period"
                      info="Unique accounts reached by your content in the selected window."
                    />
                    <InstagramMetricTile
                      title="Impressions"
                      value={instagramSummary.impressions}
                      subtitle="Total content impressions in the selected period"
                      info="Total times your content was displayed, including repeated views from the same accounts."
                    />
                  </div>
                </InstagramDetailCard>

                <InstagramDetailCard
                  title="Post & Engagement Summary"
                  info="Highlights how many posts went out, how much engagement they earned, which post performed best, and which post formats drove results."
                >
                  <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
                    <div className="space-y-4">
                      <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                        <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Total Posts</p>
                        <div className="mt-2 flex items-end gap-2">
                          <p className="text-4xl font-bold text-sky-600">{fmt(instagramSummary.post_summary?.total_posts)}</p>
                          {instagramSummary.post_summary?.total_posts_change_pct != null && (
                            <span className={`text-sm font-semibold ${instagramSummary.post_summary.total_posts_change_pct >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                              {pctLabel(instagramSummary.post_summary.total_posts_change_pct)}
                            </span>
                          )}
                        </div>
                        <p className="mt-2 text-sm text-gray-500">Avg. per day: {instagramSummary.post_summary?.avg_posts_per_day ?? 0}</p>
                      </div>
                      <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                        <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Total Engagement</p>
                        <div className="mt-2 flex items-end gap-2">
                          <p className="text-4xl font-bold text-sky-600">{fmt(instagramSummary.post_summary?.total_engagement)}</p>
                          {instagramSummary.post_summary?.total_engagement_change_pct != null && (
                            <span className={`text-sm font-semibold ${instagramSummary.post_summary.total_engagement_change_pct >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                              {pctLabel(instagramSummary.post_summary.total_engagement_change_pct)}
                            </span>
                          )}
                        </div>
                        <p className="mt-2 text-sm text-gray-500">Avg. per day: {instagramSummary.post_summary?.avg_engagement_per_day ?? 0}</p>
                      </div>
                    </div>

                    <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-3">Top Post</p>
                      {instagramSummary.post_summary?.top_post ? (
                        <div className="space-y-3">
                          {instagramSummary.post_summary.top_post.media_url ? (
                            <img
                              src={instagramSummary.post_summary.top_post.media_url}
                              alt=""
                              className="w-full h-44 rounded-xl object-cover"
                              onError={(e) => { e.target.style.display = 'none'; }}
                            />
                          ) : (
                            <div className="w-full h-44 rounded-xl bg-gray-100 flex items-center justify-center text-sm text-gray-400">
                              No media preview
                            </div>
                          )}
                          <p className="text-sm text-gray-700 line-clamp-4">
                            {instagramSummary.post_summary.top_post.content || '(no caption)'}
                          </p>
                          <div className="flex items-center gap-4 text-xs text-gray-500">
                            <span className="flex items-center gap-1"><FaHeart className="text-rose-400" />{fmt(instagramSummary.post_summary.top_post.likes)}</span>
                            <span className="flex items-center gap-1"><FaComment className="text-blue-400" />{fmt(instagramSummary.post_summary.top_post.comments)}</span>
                            <span className="font-semibold text-gray-700">{fmt(instagramSummary.post_summary.top_post.engagement)} total engagement</span>
                          </div>
                          {instagramSummary.post_summary.top_post.permalink && (
                            <a
                              href={instagramSummary.post_summary.top_post.permalink}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-2 text-sm font-semibold text-indigo-600 hover:text-indigo-700"
                            >
                              View on Instagram <FaExternalLinkAlt className="text-xs" />
                            </a>
                          )}
                        </div>
                      ) : (
                        chartEmptyState('No Instagram post engagement data is available for this period.')
                      )}
                    </div>

                    <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-3">Engagement by Post Type</p>
                      {instagramSummary.post_summary?.engagement_by_type?.length > 0 ? (
                        <div className="space-y-4">
                          {instagramSummary.post_summary.engagement_by_type.map((item) => {
                            const total = instagramSummary.post_summary.total_engagement || 1;
                            const pct = Math.round(((item.engagement || 0) / total) * 100);
                            return (
                              <div key={item.type}>
                                <div className="flex items-center justify-between text-sm mb-1">
                                  <span className="font-medium text-gray-700">{item.label}</span>
                                  <span className="text-gray-500">{fmt(item.engagement)} engagement • {fmt(item.posts)} posts</span>
                                </div>
                                <div className="h-2.5 bg-gray-200 rounded-full overflow-hidden">
                                  <div className="h-full rounded-full bg-indigo-500" style={{ width: `${pct}%` }} />
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        chartEmptyState('No Instagram posts were returned for this period.')
                      )}
                    </div>
                  </div>
                </InstagramDetailCard>

                <InstagramDetailCard
                  title="Reels & Engagement Summary"
                  info="Shows how many reels were published, how much engagement they generated, and which reel led performance for the selected period."
                >
                  <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
                    <div className="space-y-4">
                      <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                        <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Total Reels</p>
                        <div className="mt-2 flex items-end gap-2">
                          <p className="text-4xl font-bold text-sky-600">{fmt(instagramSummary.reels_summary?.total_reels)}</p>
                          {instagramSummary.reels_summary?.total_reels_change_pct != null && (
                            <span className={`text-sm font-semibold ${instagramSummary.reels_summary.total_reels_change_pct >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                              {pctLabel(instagramSummary.reels_summary.total_reels_change_pct)}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                        <p className="text-xs font-bold uppercase tracking-widest text-gray-400">Total Reel Engagement</p>
                        <div className="mt-2 flex items-end gap-2">
                          <p className="text-4xl font-bold text-sky-600">{fmt(instagramSummary.reels_summary?.total_engagement)}</p>
                          {instagramSummary.reels_summary?.total_engagement_change_pct != null && (
                            <span className={`text-sm font-semibold ${instagramSummary.reels_summary.total_engagement_change_pct >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                              {pctLabel(instagramSummary.reels_summary.total_engagement_change_pct)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 xl:col-span-2">
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-3">Top Reel</p>
                      {instagramSummary.reels_summary?.top_reel ? (
                        <div className="flex flex-col md:flex-row gap-4">
                          {instagramSummary.reels_summary.top_reel.media_url ? (
                            <img
                              src={instagramSummary.reels_summary.top_reel.media_url}
                              alt=""
                              className="w-full md:w-56 h-56 rounded-xl object-cover"
                              onError={(e) => { e.target.style.display = 'none'; }}
                            />
                          ) : null}
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-gray-700 line-clamp-6">
                              {instagramSummary.reels_summary.top_reel.content || '(no caption)'}
                            </p>
                            <div className="mt-4 flex flex-wrap items-center gap-4 text-sm text-gray-500">
                              <span className="flex items-center gap-1"><FaHeart className="text-rose-400" />{fmt(instagramSummary.reels_summary.top_reel.likes)}</span>
                              <span className="flex items-center gap-1"><FaComment className="text-blue-400" />{fmt(instagramSummary.reels_summary.top_reel.comments)}</span>
                              <span className="font-semibold text-gray-700">{fmt(instagramSummary.reels_summary.top_reel.engagement)} total engagement</span>
                            </div>
                            {instagramSummary.reels_summary.top_reel.permalink && (
                              <a
                                href={instagramSummary.reels_summary.top_reel.permalink}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-indigo-600 hover:text-indigo-700"
                              >
                                View reel on Instagram <FaExternalLinkAlt className="text-xs" />
                              </a>
                            )}
                          </div>
                        </div>
                      ) : (
                        chartEmptyState('No reels were returned for this period.')
                      )}
                    </div>
                  </div>
                </InstagramDetailCard>
              </div>
            )}
          </div>
        )}

        {activeTab === 'instagram-audience' && selectedPlatform === 'instagram' && (
          <div className="space-y-6">
            {!!instagramReport?.errors?.length && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {instagramReport.errors.map((item, idx) => (
                  <div key={`${item.account}-${idx}`}>
                    <span className="font-semibold">{item.account}:</span> {item.error}
                  </div>
                ))}
              </div>
            )}

            {loadingInstagramReport ? (
              <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="bg-offwhite rounded-xl border border-gray-200 h-36 animate-pulse" />
                ))}
              </div>
            ) : !instagramReport?.supported ? (
              <div className="bg-offwhite rounded-xl border border-gray-200 p-8 text-center">
                <p className="text-gray-500 font-medium">Instagram audience report not available</p>
                <p className="text-sm text-gray-400 mt-1">
                  {instagramReport?.message || 'Connect an Instagram Business or Creator account to see this report.'}
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
                  <strong>Note:</strong> These cards use Instagram {instagramAudience?.demographics_source_label || 'audience'} demographics as the closest available proxy for likes and other interactions.
                  {instagramAudience?.demographics_timeframe && (
                    <span className="ml-1">
                      Instagram returns this data only for recent windows, so this section reflects the latest {instagramAudience.demographics_timeframe === 'this_week' ? 'weekly' : 'monthly'} breakdown rather than the full selected date range.
                    </span>
                  )}
                  {instagramAudience?.accounts_used?.length > 0 && (
                    <span className="ml-1">Showing data from: <strong>{instagramAudience.accounts_used.join(', ')}</strong></span>
                  )}
                </div>

                {!!instagramDemographicsErrorDetails?.length && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                    {instagramDemographicsErrorDetails.map((item, idx) => (
                      <div key={`${item.account}-${idx}`}>
                        <span className="font-semibold">{item.account}:</span> {item.metric ? ` [${item.metric}] ` : ' '}{item.error}
                      </div>
                    ))}
                  </div>
                )}

                <InstagramDetailCard
                  title="Follower Growth"
                  info="Shows daily net follower change across the selected period. Negative values indicate days when the account lost followers."
                >
                  {instagramFollowerGrowthHasData ? (
                    <ResponsiveContainer width="100%" height={220}>
                      <AreaChart data={instagramFollowerTimeline} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
                        <defs>
                          <linearGradient id="colorFollowers" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#2563eb" stopOpacity={0.28} />
                            <stop offset="95%" stopColor="#2563eb" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                        <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} width={40} />
                        <Tooltip content={<AudienceGrowthTooltip />} />
                        <Area type="monotone" dataKey="count" name="Net followers" stroke="#2563eb" strokeWidth={2} fill="url(#colorFollowers)" dot={false} />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    chartEmptyState(instagramFollowerGrowthUnavailableMessage)
                  )}
                </InstagramDetailCard>

                {!instagramAudience.demographics_supported && (
                  <div className="rounded-xl border border-gray-200 bg-offwhite px-4 py-3 text-sm text-gray-500">
                    {instagramAudience.demographics_message || 'Audience demographics are not available for this Instagram account yet.'}
                  </div>
                )}

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <InstagramDetailCard
                    title="Likes by Country"
                    info="Uses Instagram engaged-audience demographics as a proxy for where the accounts interacting with your content came from. Instagram does not expose raw like events split by country."
                  >
                    {instagramDemographics.countries?.length > 0 ? (
                      <ResponsiveContainer width="100%" height={240}>
                        <BarChart data={instagramDemographics.countries} layout="vertical" margin={{ top: 0, right: 10, bottom: 0, left: 50 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                          <XAxis type="number" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                          <YAxis dataKey="name" type="category" tick={{ fontSize: 11, fill: '#6b7280' }} tickLine={false} axisLine={false} width={50} />
                          <Tooltip />
                          <Bar dataKey="count" name="Audience" fill="#f59e0b" radius={[0, 4, 4, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      chartEmptyState(instagramDemographicsUnavailableMessage)
                    )}
                  </InstagramDetailCard>

                  <InstagramDetailCard
                    title="Likes by Gender"
                    info="Uses Instagram engaged-audience demographics as a proxy for the gender breakdown of accounts interacting with your content. Instagram does not expose raw likes by gender."
                  >
                    {instagramDemographics.gender?.length > 0 ? (
                      <div className="space-y-4">
                        {instagramDemographics.gender.map((item) => {
                          const total = instagramDemographics.gender.reduce((sum, current) => sum + current.count, 0) || 1;
                          const pct = Math.round((item.count / total) * 100);
                          return (
                            <div key={item.label}>
                              <div className="flex items-center justify-between text-sm mb-1">
                                <span className="font-medium text-gray-700">{item.label}</span>
                                <span className="text-gray-500">{fmt(item.count)} ({pct}%)</span>
                              </div>
                              <div className="h-2.5 bg-gray-200 rounded-full overflow-hidden">
                                <div className="h-full rounded-full bg-pink-500" style={{ width: `${pct}%` }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      chartEmptyState(instagramDemographicsUnavailableMessage)
                    )}
                  </InstagramDetailCard>

                  <InstagramDetailCard
                    title="Likes by Age Group"
                    info="Uses Instagram engaged-audience demographics as a proxy for which age groups interacted with your content. Instagram does not expose raw likes by age group."
                  >
                    {instagramDemographics.age?.length > 0 ? (
                      <ResponsiveContainer width="100%" height={240}>
                        <BarChart data={instagramDemographics.age} layout="vertical" margin={{ top: 0, right: 10, bottom: 0, left: 40 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                          <XAxis type="number" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                          <YAxis dataKey="range" type="category" tick={{ fontSize: 11, fill: '#6b7280' }} tickLine={false} axisLine={false} width={50} />
                          <Tooltip />
                          <Bar dataKey="count" name="Audience" fill="#6366f1" radius={[0, 4, 4, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      chartEmptyState(instagramDemographicsUnavailableMessage)
                    )}
                  </InstagramDetailCard>

                  <InstagramDetailCard
                    title="Likes by City"
                    info="Uses Instagram engaged-audience demographics as a proxy for the cities of accounts interacting with your content. Instagram does not expose raw likes by city."
                  >
                    {instagramDemographics.cities?.length > 0 ? (
                      <ResponsiveContainer width="100%" height={240}>
                        <BarChart data={instagramDemographics.cities} layout="vertical" margin={{ top: 0, right: 10, bottom: 0, left: 90 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                          <XAxis type="number" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                          <YAxis dataKey="name" type="category" tick={{ fontSize: 10, fill: '#6b7280' }} tickLine={false} axisLine={false} width={90} />
                          <Tooltip />
                          <Bar dataKey="count" name="Audience" fill="#22c55e" radius={[0, 4, 4, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      chartEmptyState(instagramDemographicsUnavailableMessage)
                    )}
                  </InstagramDetailCard>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'instagram-reach' && selectedPlatform === 'instagram' && (
          <div className="space-y-6">
            {!!instagramReport?.errors?.length && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {instagramReport.errors.map((item, idx) => (
                  <div key={`${item.account}-${idx}`}>
                    <span className="font-semibold">{item.account}:</span> {item.error}
                  </div>
                ))}
              </div>
            )}

            {loadingInstagramReport ? (
              <div className="space-y-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="bg-offwhite rounded-xl border border-gray-200 h-36 animate-pulse" />
                ))}
              </div>
            ) : !instagramReport?.supported ? (
              <div className="bg-offwhite rounded-xl border border-gray-200 p-8 text-center">
                <p className="text-gray-500 font-medium">Instagram reach report not available</p>
                <p className="text-sm text-gray-400 mt-1">
                  {instagramReport?.message || 'Connect an Instagram Business or Creator account to see this report.'}
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <InstagramMetricTile
                    title="Reach"
                    value={instagramSummary.reach}
                    subtitle="Unique accounts reached during the selected period"
                    info="Shows how many unique Instagram accounts saw your content across the selected date range."
                  />
                  <InstagramMetricTile
                    title="Impressions"
                    value={instagramSummary.impressions}
                    subtitle="Total content impressions during the selected period"
                    info="Shows how many total times your Instagram content was displayed, including repeat views from the same accounts."
                  />
                  <InstagramMetricTile
                    title="Profile Views"
                    value={instagramSummary.profile_views}
                    subtitle="Instagram profile visits during the selected period"
                    info="Shows how many times people visited your Instagram profile during the selected date range."
                  />
                </div>

                <InstagramDetailCard
                  title="Reach"
                  action={instagramReachSelector}
                  info="Tracks unique accounts reached over time. Change the grouping to compare daily reach with weekly, monthly, or quarterly patterns."
                >
                  {instagramReachHasData ? (
                    <ResponsiveContainer width="100%" height={320}>
                      <BarChart data={instagramReachTimeline} margin={{ top: 8, right: 8, bottom: 0, left: -10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                        <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} width={50} />
                        <Tooltip />
                        <Legend verticalAlign="bottom" height={36} iconType="circle" />
                        <Bar dataKey="count" name="Reach" fill="#2f6690" radius={[6, 6, 0, 0]} maxBarSize={44} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    chartEmptyState('Reach data is not available for this Instagram account right now.')
                  )}
                </InstagramDetailCard>
              </div>
            )}
          </div>
        )}

        {activeTab === 'tiktok-content' && selectedPlatform === 'tiktok' && (
          <div className="space-y-6">
            {!!tiktokReport?.message && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {tiktokReport.message}
              </div>
            )}

            {!!tiktokReport?.errors?.length && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {tiktokReport.errors.map((item, idx) => (
                  <div key={`${item.account}-${idx}`}>
                    <span className="font-semibold">{item.account}:</span> {item.error}
                  </div>
                ))}
              </div>
            )}

            {loadingTikTokReport ? (
              <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="bg-offwhite rounded-xl border border-gray-200 h-36 animate-pulse" />
                ))}
              </div>
            ) : !tiktokReport?.supported ? (
              <div className="bg-offwhite rounded-xl border border-gray-200 p-8 text-center">
                <p className="text-gray-500 font-medium">TikTok content report not available</p>
                <p className="text-sm text-gray-400 mt-1">
                  {tiktokReport?.message || 'Connect a TikTok account to see this report.'}
                </p>
              </div>
            ) : (
              <>
                {tiktokContent.content_source_message && (
                  <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
                    {tiktokContent.content_source_message}
                  </div>
                )}

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <ReportCard title="Content Performance by Publish Date" info="Shows how many views and engagements your TikTok videos have accumulated, grouped by the date they were published.">
                    {tiktokContentHasCharts ? (
                      <ResponsiveContainer width="100%" height={260}>
                        <ComposedChart data={mergeBucketedSeries({ views: tiktokContent.post_views_series || [], engagement: tiktokContent.engagement_series || [] }, days, 'day')}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                          <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                          <YAxis yAxisId="left" allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                          <YAxis yAxisId="right" orientation="right" allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                          <Tooltip />
                          <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
                          <Bar yAxisId="left" dataKey="views" name="Views" fill="#2f6690" radius={[4, 4, 0, 0]} barSize={22} minPointSize={2} />
                          <Line yAxisId="right" type="monotone" dataKey="engagement" name="Engagement" stroke="#22c55e" strokeWidth={2.5} dot={false} />
                        </ComposedChart>
                      </ResponsiveContainer>
                    ) : (
                      chartEmptyState('No TikTok post-performance data is available for the selected period.')
                    )}
                  </ReportCard>

                  <ReportCard title="Videos Published Over Time" info="Shows how many TikTok videos in the selected period were published on each day.">
                    {chartHasData(tiktokPublishedVideosSeries, ['count']) ? (
                      <ResponsiveContainer width="100%" height={260}>
                        <BarChart data={tiktokPublishedVideosSeries}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                          <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                          <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                          <Tooltip />
                          <Bar dataKey="count" name="Videos" fill="#8b5cf6" radius={[6, 6, 0, 0]} maxBarSize={40} minPointSize={2} />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      chartEmptyState('No TikTok videos were returned for the selected period.')
                    )}
                  </ReportCard>
                </div>

                <ReportCard
                  title="Your Top Posts"
                  info="Ranks TikTok videos by the selected metric using the connected TikTok account feed when available, or Unravler fallback posts when TikTok video-list access is unavailable."
                  action={(
                    <div className="flex items-center gap-2 flex-wrap">
                      {[
                        { key: 'views', label: 'Most Views' },
                        { key: 'likes', label: 'Most Likes' },
                        { key: 'comments', label: 'Most Comments' },
                        { key: 'shares', label: 'Most Shares' },
                      ].map((option) => (
                        <button
                          key={option.key}
                          onClick={() => setTikTokTopMetric(option.key)}
                          className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-all ${tiktokTopMetric === option.key ? 'border-indigo-600 bg-indigo-50 text-indigo-600' : 'border-gray-200 bg-offwhite text-gray-600 hover:border-gray-300'}`}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  )}
                >
                  {tiktokTopPosts.length > 0 ? (
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                      {tiktokTopPosts.slice(0, 8).map((post) => (
                        <div key={post.id} className="rounded-xl border border-gray-100 bg-gray-50 p-4 space-y-3">
                          {post.thumbnail_url ? (
                            <img
                              src={post.thumbnail_url}
                              alt=""
                              className="w-full h-40 rounded-xl object-cover"
                              onError={(e) => { e.target.style.display = 'none'; }}
                            />
                          ) : (
                            <div className="w-full h-40 rounded-xl bg-gray-100 flex items-center justify-center text-sm text-gray-400">
                              No media preview
                            </div>
                          )}
                          <div className="flex items-center justify-between gap-3 text-xs text-gray-500">
                            <span className="font-semibold">{post.source_mode === 'db_fallback' ? 'Unravler fallback' : 'TikTok feed'}</span>
                            {post.timestamp && <span>{formatAnalyticsDate(post.timestamp)}</span>}
                          </div>
                          <p className="text-sm text-gray-700 line-clamp-3">{post.title || post.content || '(no caption)'}</p>
                          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-gray-600">
                            <span>Views</span><span className="text-right font-semibold">{fmt(post.views)}</span>
                            <span>Likes</span><span className="text-right font-semibold">{fmt(post.likes)}</span>
                            <span>Comments</span><span className="text-right font-semibold">{fmt(post.comments)}</span>
                            <span>Shares</span><span className="text-right font-semibold">{fmt(post.shares)}</span>
                            <span>Engagement</span><span className="text-right font-semibold">{fmt(post.engagement)}</span>
                          </div>
                          {post.permalink && (
                            <a
                              href={post.permalink}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-2 text-sm font-semibold text-indigo-600 hover:text-indigo-700"
                            >
                              View on TikTok <FaExternalLinkAlt className="text-xs" />
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    chartEmptyState('No top TikTok posts are available for this period yet.')
                  )}
                </ReportCard>
              </>
            )}
          </div>
        )}

        {activeTab === 'tiktok-viewers' && selectedPlatform === 'tiktok' && (
          <div className="space-y-6">
            {loadingTikTokReport ? (
              <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="bg-offwhite rounded-xl border border-gray-200 h-36 animate-pulse" />
                ))}
              </div>
            ) : (
              <>
                <ReportCard title="Key Metrics" info="TikTok’s app can show total, new, and returning viewers, but the connected developer API does not expose those viewer metrics to Unravler today.">
                  {chartEmptyState(tiktokViewers.viewer_metrics_message)}
                </ReportCard>
                <ReportCard title="Viewer Insights" info="TikTok’s app can show viewer gender, age, and locations, but the connected developer API does not expose those demographics to Unravler today.">
                  {chartEmptyState(tiktokViewers.viewer_insights_message)}
                </ReportCard>
                <ReportCard title="Most Active Times" info="TikTok’s app can show when viewers are most active, but the connected developer API does not expose those active-time analytics to Unravler today.">
                  {chartEmptyState(tiktokViewers.active_times_message)}
                </ReportCard>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <ReportCard title="Creators Your Viewers Also Watched" info="TikTok’s app can show related creators, but the connected developer API does not expose this discovery graph to Unravler today.">
                    {chartEmptyState(tiktokViewers.related_creators_message)}
                  </ReportCard>
                  <ReportCard title="Posts Your Viewers Also Viewed" info="TikTok’s app can show related posts, but the connected developer API does not expose this discovery graph to Unravler today.">
                    {chartEmptyState(tiktokViewers.related_posts_message)}
                  </ReportCard>
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === 'tiktok-followers' && selectedPlatform === 'tiktok' && (
          <div className="space-y-6">
            {loadingTikTokReport ? (
              <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="bg-offwhite rounded-xl border border-gray-200 h-36 animate-pulse" />
                ))}
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <ReportMetricTile title="Total Followers" value={tiktokFollowers.followers_total} subtitle="Current TikTok followers" />
                  <ReportMetricTile title={`Net Followers (${days}d)`} value={tiktokFollowers.net_followers} subtitle={tiktokFollowers.history_message || 'Net follower change based on app snapshots.'} accent={tiktokFollowers.net_followers < 0 ? 'text-rose-600' : 'text-emerald-600'} />
                </div>
                <ReportCard title="Follower Growth" info="Tracks TikTok follower totals across app-owned daily snapshots for the selected period.">
                  {tiktokFollowers.history_message && (
                    <div className="mb-4 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
                      {tiktokFollowers.history_message}
                    </div>
                  )}
                  {tiktokFollowersHasData ? (
                    <ResponsiveContainer width="100%" height={280}>
                      <AreaChart data={tiktokFollowersSeries}>
                        <defs>
                          <linearGradient id="colorTikTokFollowers" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#2f6690" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#2f6690" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                        <Tooltip />
                        <Area type="monotone" dataKey="count" name="Followers" stroke="#2f6690" strokeWidth={2.5} fill="url(#colorTikTokFollowers)" dot={false} />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    chartEmptyState(tiktokFollowers.history_message || 'TikTok follower history will appear after app snapshots accumulate.')
                  )}
                </ReportCard>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <ReportCard title="Follower Insights" info="TikTok’s app can show follower gender, age, and locations, but the connected developer API does not expose those demographics to Unravler today.">
                    {chartEmptyState(tiktokFollowers.demographics_message)}
                  </ReportCard>
                  <ReportCard title="Most Active Times" info="TikTok’s app can show when followers are most active, but the connected developer API does not expose those active-time analytics to Unravler today.">
                    {chartEmptyState(tiktokFollowers.active_times_message)}
                  </ReportCard>
                </div>
              </>
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
              {visibleSortOptions.map((opt) => (
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

            {/* Feed errors / notices */}
            {!loadingPosts && (postsMessage || (postsErrors && postsErrors.length > 0)) && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-sm text-amber-900">
                {postsMessage && (
                  <p className="font-semibold">{postsMessage}</p>
                )}
                {postsErrors?.length > 0 && (
                  <div className={postsMessage ? 'mt-2 space-y-1' : 'space-y-1'}>
                    {postsErrors.slice(0, 3).map((item, idx) => (
                      <p key={idx}>
                        <strong>{item.account || 'Account'}:</strong>{' '}
                        {String(item.error || 'Unable to fetch posts').includes('CreditsDepleted')
                          ? 'X API credits are depleted. Showing only posts published from Unravler (if any).'
                          : (item.error || 'Unable to fetch posts')}
                      </p>
                    ))}
                    {postsErrors.length > 3 && (
                      <p className="text-xs text-amber-800">+{postsErrors.length - 3} more…</p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Post summary stats */}
            {!loadingPosts && sortedPosts.length > 0 && (
              <div className={`grid gap-3 ${visibleMetricCards.length > 0 ? 'grid-cols-2 sm:grid-cols-4' : 'grid-cols-1'}`}>
                {visibleMetricCards.map(({ key, label, icon: Icon }) => (
                  <div key={label} className="bg-offwhite rounded-xl border border-gray-200 p-4 flex items-center gap-3">
                    <Icon className={`${
                      key === 'likes' ? 'text-rose-500'
                        : key === 'comments' ? 'text-blue-500'
                        : key === 'shares' ? 'text-green-500'
                        : 'text-purple-500'
                    } text-lg`} />
                    <div>
                      <p className="text-xs text-gray-500">{label}</p>
                      <p className="text-lg font-bold text-gray-900">
                        {fmt(sortedPosts.reduce((sum, post) => sum + (post.metrics?.[key] || 0), 0))}
                      </p>
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
                  {selectedPlatform
                    ? (selectedPlatform === 'twitter' && postsErrors?.some(e => String(e?.error || '').includes('CreditsDepleted'))
                      ? 'X is blocking feed reads due to depleted API credits. Without X credits we can only show posts published from Unravler. None found for this account.'
                      : `No posts from ${PLATFORM_LABELS[selectedPlatform]} yet.`)
                    : 'Connect social accounts and publish posts to see analytics here.'}
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
