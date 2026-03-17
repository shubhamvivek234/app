import React, { useEffect, useState, useCallback } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { getAnalyticsEngagement, getAnalyticsFeed, getAnalyticsDemographics, getSocialAccounts } from '@/lib/api';
import { toast } from 'sonner';
import { format } from 'date-fns';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts';
import {
  FaInstagram, FaFacebook, FaTwitter, FaLinkedin, FaYoutube, FaTiktok, FaPinterest, FaSnapchat, FaGlobe
} from 'react-icons/fa';
import { SiThreads, SiBluesky, SiReddit } from 'react-icons/si';

const PLATFORM_ICONS = {
  instagram: FaInstagram,
  facebook: FaFacebook,
  twitter: FaTwitter,
  linkedin: FaLinkedin,
  youtube: FaYoutube,
  tiktok: FaTiktok,
  threads: SiThreads,
  reddit: SiReddit,
  pinterest: FaPinterest,
  bluesky: SiBluesky,
  snapchat: FaSnapchat,
};

const PLATFORM_COLORS = {
  instagram: '#E4405F',
  facebook: '#1877F2',
  twitter: '#1DA1F2',
  linkedin: '#0A66C2',
  youtube: '#FF0000',
  tiktok: '#000000',
  threads: '#000000',
  reddit: '#FF4500',
  pinterest: '#E60023',
  bluesky: '#0085FF',
  snapchat: '#FFFC00',
};

const DEMOGRAPHICS_PLATFORMS = new Set(['instagram', 'facebook']);
const CHART_COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#f97316'];

const Analytics = () => {
  const [accounts, setAccounts] = useState([]);
  const [selectedPlatform, setSelectedPlatform] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [engagement, setEngagement] = useState([]);
  const [feed, setFeed] = useState([]);
  const [demographics, setDemographics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingFeed, setLoadingFeed] = useState(false);
  const [loadingDemos, setLoadingDemos] = useState(false);

  useEffect(() => {
    const fetchAccounts = async () => {
      try {
        const data = await getSocialAccounts();
        setAccounts(data);
      } catch {
        // ignore
      }
    };
    fetchAccounts();
  }, []);

  const platforms = [...new Set(accounts.map(a => a.platform))];

  const showDemographicsTab = selectedPlatform
    ? DEMOGRAPHICS_PLATFORMS.has(selectedPlatform)
    : platforms.some(p => DEMOGRAPHICS_PLATFORMS.has(p));

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'posts', label: 'Posts' },
    ...(showDemographicsTab ? [{ id: 'demographics', label: 'Demographics' }] : []),
  ];

  const fetchEngagement = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAnalyticsEngagement(selectedPlatform);
      setEngagement(data.engagement || []);
    } catch {
      toast.error('Failed to load engagement data');
    } finally {
      setLoading(false);
    }
  }, [selectedPlatform]);

  const fetchFeed = useCallback(async () => {
    setLoadingFeed(true);
    try {
      const data = await getAnalyticsFeed(selectedPlatform, 50);
      setFeed(data.posts || []);
    } catch {
      toast.error('Failed to load posts');
    } finally {
      setLoadingFeed(false);
    }
  }, [selectedPlatform]);

  const fetchDemographics = useCallback(async () => {
    setLoadingDemos(true);
    try {
      const data = await getAnalyticsDemographics(selectedPlatform);
      setDemographics(data);
    } catch {
      toast.error('Failed to load demographics');
    } finally {
      setLoadingDemos(false);
    }
  }, [selectedPlatform]);

  useEffect(() => {
    if (activeTab === 'overview') fetchEngagement();
    else if (activeTab === 'posts') fetchFeed();
    else if (activeTab === 'demographics') fetchDemographics();
  }, [activeTab, fetchEngagement, fetchFeed, fetchDemographics]);

  useEffect(() => {
    // Reset tab if demographics not available for selected platform
    if (activeTab === 'demographics' && !showDemographicsTab) {
      setActiveTab('overview');
    }
  }, [selectedPlatform, activeTab, showDemographicsTab]);

  const renderSkeleton = (count = 4) => (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="bg-white rounded-lg border p-6 animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-1/2 mb-3" />
          <div className="h-8 bg-gray-200 rounded w-2/3" />
        </div>
      ))}
    </div>
  );

  const renderOverview = () => {
    if (loading) return renderSkeleton();
    if (!engagement.length) {
      return (
        <div className="text-center py-12 text-gray-500">
          <p>No analytics data available. Connect social accounts to see engagement metrics.</p>
        </div>
      );
    }

    return (
      <div className="space-y-6">
        {engagement.map((eng, idx) => {
          const Icon = PLATFORM_ICONS[eng.platform] || FaGlobe;
          const color = PLATFORM_COLORS[eng.platform] || '#6b7280';
          const metrics = Object.entries(eng).filter(
            ([k]) => !['platform', 'account_id', 'account_name', 'note'].includes(k)
          );

          return (
            <div key={idx} className="bg-white rounded-lg border p-6">
              <div className="flex items-center gap-3 mb-4">
                <Icon style={{ color }} className="text-xl" />
                <h3 className="font-semibold text-gray-900">{eng.account_name || eng.platform}</h3>
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full capitalize">{eng.platform}</span>
              </div>
              {eng.note && (
                <p className="text-sm text-amber-600 mb-3">{eng.note}</p>
              )}
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                {metrics.map(([key, value]) => (
                  <div key={key} className="p-3 bg-gray-50 rounded-lg">
                    <p className="text-xs text-gray-500 capitalize">{key.replace(/_/g, ' ')}</p>
                    <p className="text-xl font-semibold text-gray-900 mt-1">
                      {typeof value === 'number' ? value.toLocaleString() : value}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const renderPosts = () => {
    if (loadingFeed) return renderSkeleton(6);
    if (!feed.length) {
      return (
        <div className="text-center py-12 text-gray-500">
          <p>No posts found. Posts will appear here once fetched from connected platforms.</p>
        </div>
      );
    }

    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {feed.map((post, idx) => {
          const Icon = PLATFORM_ICONS[post.platform] || FaGlobe;
          return (
            <div key={post.id || idx} className="bg-white rounded-lg border overflow-hidden">
              {post.media_url && (
                <div className="aspect-video bg-gray-100 overflow-hidden">
                  <img
                    src={post.media_url}
                    alt=""
                    className="w-full h-full object-cover"
                    onError={(e) => { e.target.style.display = 'none'; }}
                  />
                </div>
              )}
              <div className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Icon className="text-sm" style={{ color: PLATFORM_COLORS[post.platform] }} />
                  <span className="text-xs text-gray-500 capitalize">{post.platform}</span>
                  {post.account_name && (
                    <span className="text-xs text-gray-400">@{post.account_name}</span>
                  )}
                </div>
                <p className="text-sm text-gray-800 line-clamp-3 mb-3">{post.content || '(No caption)'}</p>
                <div className="flex items-center gap-4 text-xs text-gray-500">
                  <span>{post.likes || 0} likes</span>
                  <span>{post.comments_count || 0} comments</span>
                  {post.views !== undefined && <span>{post.views.toLocaleString()} views</span>}
                  {post.shares !== undefined && <span>{post.shares} shares</span>}
                </div>
                {post.timestamp && (
                  <p className="text-xs text-gray-400 mt-2">
                    {format(new Date(post.timestamp), 'MMM d, yyyy h:mm a')}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const renderDemographics = () => {
    if (loadingDemos) return renderSkeleton();
    if (!demographics || !demographics.supported) {
      return (
        <div className="text-center py-12 text-gray-500">
          <p>Demographics data not available. This feature requires Instagram or Facebook accounts with sufficient followers.</p>
        </div>
      );
    }

    const { age = [], gender = [], cities = [], countries = [] } = demographics.demographics || {};

    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Age Distribution */}
        <div className="bg-white rounded-lg border p-6">
          <h3 className="font-semibold text-gray-900 mb-4">Age Distribution</h3>
          {age.length ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={age}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="range" fontSize={12} />
                <YAxis fontSize={12} />
                <Tooltip />
                <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="text-sm text-gray-400">No data</p>}
        </div>

        {/* Gender Breakdown */}
        <div className="bg-white rounded-lg border p-6">
          <h3 className="font-semibold text-gray-900 mb-4">Gender Breakdown</h3>
          {gender.length ? (
            <div className="space-y-3">
              {gender.map((g, i) => {
                const total = gender.reduce((s, x) => s + x.count, 0);
                const pct = total > 0 ? ((g.count / total) * 100).toFixed(1) : 0;
                return (
                  <div key={g.label}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="capitalize">{g.label}</span>
                      <span className="text-gray-500">{pct}% ({g.count.toLocaleString()})</span>
                    </div>
                    <div className="h-3 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${pct}%`, backgroundColor: CHART_COLORS[i % CHART_COLORS.length] }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : <p className="text-sm text-gray-400">No data</p>}
        </div>

        {/* Top Cities */}
        <div className="bg-white rounded-lg border p-6">
          <h3 className="font-semibold text-gray-900 mb-4">Top Cities</h3>
          {cities.length ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={cities} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" fontSize={12} />
                <YAxis type="category" dataKey="name" width={120} fontSize={11} />
                <Tooltip />
                <Bar dataKey="count" fill="#22c55e" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="text-sm text-gray-400">No data</p>}
        </div>

        {/* Top Countries */}
        <div className="bg-white rounded-lg border p-6">
          <h3 className="font-semibold text-gray-900 mb-4">Top Countries</h3>
          {countries.length ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={countries} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" fontSize={12} />
                <YAxis type="category" dataKey="name" width={80} fontSize={11} />
                <Tooltip />
                <Bar dataKey="count" fill="#f59e0b" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="text-sm text-gray-400">No data</p>}
        </div>

        {/* Accounts used */}
        {demographics.accounts_used?.length > 0 && (
          <div className="lg:col-span-2 text-xs text-gray-400">
            Data from: {demographics.accounts_used.map(a => `${a.platform}/${a.name}`).join(', ')}
          </div>
        )}
      </div>
    );
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Analytics</h1>
          <p className="text-base text-slate-600 mt-1">Track performance across your connected platforms.</p>
        </div>

        {/* Platform Filter */}
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setSelectedPlatform(null)}
            className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
              !selectedPlatform ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            All Platforms
          </button>
          {platforms.map((p) => {
            const Icon = PLATFORM_ICONS[p] || FaGlobe;
            return (
              <button
                key={p}
                onClick={() => setSelectedPlatform(p)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  selectedPlatform === p ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                <Icon className="text-xs" />
                <span className="capitalize">{p}</span>
              </button>
            );
          })}
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200">
          <nav className="flex gap-6">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? 'border-green-600 text-green-700'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        {/* Tab Content */}
        {activeTab === 'overview' && renderOverview()}
        {activeTab === 'posts' && renderPosts()}
        {activeTab === 'demographics' && renderDemographics()}
      </div>
    </DashboardLayout>
  );
};

export default Analytics;
