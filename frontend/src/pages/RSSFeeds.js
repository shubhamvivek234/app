import React, { useState, useEffect, useMemo } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import {
  getRssFeeds,
  validateRssFeed,
  createRssFeed,
  updateRssFeed,
  deleteRssFeed,
  syncRssFeed,
  getRssItems,
  shareRssItem,
  getSocialAccounts,
} from '@/lib/api';
import { toast } from 'sonner';
import {
  FaRss,
  FaPlus,
  FaRotate,
  FaTrash,
  FaGear,
  FaCircleCheck,
  FaClock,
  FaShareNodes,
  FaNewspaper,
  FaBolt,
  FaSpinner,
  FaGlobe,
  FaFilter,
  FaWandMagicSparkles,
  FaArrowUpRightFromSquare,
  FaCircleExclamation,
  FaXmark,
  FaPlay,
  FaPause,
} from 'react-icons/fa6';
import {
  SiX,
  SiLinkedin,
  SiFacebook,
  SiInstagram,
  SiYoutube,
  SiTiktok,
  SiThreads,
  SiBluesky,
} from 'react-icons/si';

const PLATFORM_ICONS = {
  twitter: { Icon: SiX, color: 'text-slate-900', label: 'X (Twitter)' },
  linkedin: { Icon: SiLinkedin, color: 'text-blue-600', label: 'LinkedIn' },
  facebook: { Icon: SiFacebook, color: 'text-blue-600', label: 'Facebook' },
  instagram: { Icon: SiInstagram, color: 'text-pink-600', label: 'Instagram' },
  youtube: { Icon: SiYoutube, color: 'text-red-600', label: 'YouTube' },
  tiktok: { Icon: SiTiktok, color: 'text-slate-900', label: 'TikTok' },
  threads: { Icon: SiThreads, color: 'text-slate-900', label: 'Threads' },
  bluesky: { Icon: SiBluesky, color: 'text-blue-500', label: 'Bluesky' },
};

const DEFAULT_POST_TEMPLATE = '{title}\n\n{link}\n\n#updates';

export default function RSSFeeds() {
  const [activeTab, setActiveTab] = useState('feeds'); // 'feeds' | 'articles'
  const [feeds, setFeeds] = useState([]);
  const [items, setItems] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncingFeedId, setSyncingFeedId] = useState(null);
  const [syncingAll, setSyncingAll] = useState(false);

  // Modal State
  const [showAddModal, setShowAddModal] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validatedData, setValidatedData] = useState(null);
  const [feedUrl, setFeedUrl] = useState('');
  const [feedTitle, setFeedTitle] = useState('');
  const [selectedAccounts, setSelectedAccounts] = useState([]);
  const [autoPublish, setAutoPublish] = useState(true);
  const [postStatus, setPostStatus] = useState('scheduled');
  const [postTemplate, setPostTemplate] = useState(DEFAULT_POST_TEMPLATE);
  const [useTimeslot, setUseTimeslot] = useState(true);
  const [timeslotCategory, setTimeslotCategory] = useState('Category 1');
  const [useAi, setUseAi] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Share Item Modal State
  const [sharingItem, setSharingItem] = useState(null);
  const [shareCustomContent, setShareCustomContent] = useState('');
  const [shareAccounts, setShareAccounts] = useState([]);
  const [sharingLoading, setSharingLoading] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [feedsRes, accountsRes, itemsRes] = await Promise.all([
        getRssFeeds(),
        getSocialAccounts(),
        getRssItems({ limit: 40 }),
      ]);
      setFeeds(feedsRes.feeds || []);
      const accList = Array.isArray(accountsRes) ? accountsRes : accountsRes.accounts || [];
      setAccounts(accList);
      setItems(itemsRes.items || []);
    } catch (err) {
      toast.error('Failed to load RSS feeds');
    } finally {
      setLoading(false);
    }
  };

  const handleValidateUrl = async () => {
    if (!feedUrl.trim()) {
      toast.error('Please enter a feed URL');
      return;
    }
    setValidating(true);
    setValidatedData(null);
    try {
      const res = await validateRssFeed(feedUrl.trim());
      setValidatedData(res);
      if (!feedTitle && res.title) {
        setFeedTitle(res.title);
      }
      toast.success(`Valid feed detected: ${res.title}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Invalid RSS/Atom feed URL');
    } finally {
      setValidating(false);
    }
  };

  const handleCreateFeed = async (e) => {
    e.preventDefault();
    if (!feedUrl.trim()) {
      toast.error('Feed URL is required');
      return;
    }
    if (autoPublish && selectedAccounts.length === 0) {
      toast.error('Please select at least one social account for auto-publishing');
      return;
    }

    setSubmitting(true);
    try {
      const targetPlatforms = Array.from(
        new Set(
          accounts
            .filter((a) => selectedAccounts.includes(a.id))
            .map((a) => (a.platform || '').toLowerCase())
            .filter(Boolean)
        )
      );

      const payload = {
        feed_url: feedUrl.trim(),
        title: feedTitle.trim() || undefined,
        target_account_ids: selectedAccounts,
        target_platforms: targetPlatforms,
        auto_publish: autoPublish,
        post_status: postStatus,
        post_template: postTemplate,
        use_timeslot: useTimeslot,
        timeslot_category: timeslotCategory,
        use_ai_enhancement: useAi,
      };

      await createRssFeed(payload);
      toast.success('RSS Feed connected & automated successfully');
      setShowAddModal(false);
      resetModal();
      loadData();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to connect RSS feed');
    } finally {
      setSubmitting(false);
    }
  };

  const resetModal = () => {
    setFeedUrl('');
    setFeedTitle('');
    setValidatedData(null);
    setSelectedAccounts([]);
    setAutoPublish(true);
    setPostStatus('scheduled');
    setPostTemplate(DEFAULT_POST_TEMPLATE);
    setUseTimeslot(true);
    setTimeslotCategory('Category 1');
    setUseAi(false);
  };

  const handleSyncFeed = async (feedId) => {
    setSyncingFeedId(feedId);
    try {
      const res = await syncRssFeed(feedId);
      const stats = res.stats || {};
      toast.success(
        `Synced feed: ${stats.discovered || 0} discovered, ${stats.scheduled || 0} scheduled`
      );
      loadData();
    } catch (err) {
      toast.error('Failed to sync feed');
    } finally {
      setSyncingFeedId(null);
    }
  };

  const handleSyncAll = async () => {
    setSyncingAll(true);
    try {
      for (const feed of feeds) {
        await syncRssFeed(feed.id);
      }
      toast.success('All active feeds synced successfully');
      loadData();
    } catch (err) {
      toast.error('Failed to sync some feeds');
    } finally {
      setSyncingAll(false);
    }
  };

  const handleToggleFeedStatus = async (feed) => {
    const nextStatus = feed.status === 'active' ? 'paused' : 'active';
    try {
      await updateRssFeed(feed.id, { status: nextStatus });
      setFeeds((prev) =>
        prev.map((f) => (f.id === feed.id ? { ...f, status: nextStatus } : f))
      );
      toast.success(`Feed ${nextStatus === 'active' ? 'resumed' : 'paused'}`);
    } catch (err) {
      toast.error('Failed to update feed status');
    }
  };

  const handleDeleteFeed = async (feedId) => {
    if (!window.confirm('Are you sure you want to disconnect this RSS feed?')) return;
    try {
      await deleteRssFeed(feedId);
      setFeeds((prev) => prev.filter((f) => f.id !== feedId));
      toast.success('Feed removed successfully');
    } catch (err) {
      toast.error('Failed to delete feed');
    }
  };

  const handleOpenShare = (item) => {
    setSharingItem(item);
    const feed = feeds.find((f) => f.id === item.feed_id);
    const tpl = feed?.post_template || DEFAULT_POST_TEMPLATE;
    const formatted = tpl
      .replace('{title}', item.title || '')
      .replace('{link}', item.url || '')
      .replace('{summary}', (item.summary || '').slice(0, 200))
      .replace('{author}', item.author || '');
    setShareCustomContent(formatted.trim());
    setShareAccounts(feed?.target_account_ids || (accounts[0] ? [accounts[0].id] : []));
  };

  const handleExecuteShare = async () => {
    if (!sharingItem) return;
    if (shareAccounts.length === 0) {
      toast.error('Please select at least one account');
      return;
    }
    setSharingLoading(true);
    try {
      await shareRssItem(sharingItem.id, {
        target_account_ids: shareAccounts,
        custom_content: shareCustomContent,
        use_timeslot: true,
        timeslot_category: 'Category 1',
      });
      toast.success('Article scheduled to social media successfully!');
      setSharingItem(null);
      loadData();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to share article');
    } finally {
      setSharingLoading(false);
    }
  };

  const totalAutoScheduled = useMemo(() => {
    return feeds.reduce((acc, f) => acc + (f.scheduled_items || 0), 0);
  }, [feeds]);

  return (
    <DashboardLayout>
      <div className="max-w-7xl mx-auto pb-16 px-4 sm:px-6">
        {/* Top Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8 pt-2">
          <div>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center text-lg border border-emerald-100 shadow-2xs">
                <FaRss />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                  RSS Feeds & Automations
                </h1>
                <p className="text-xs text-slate-500 mt-0.5">
                  Autopilot blog posts, YouTube releases, and news directly into your queue
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleSyncAll}
              disabled={syncingAll || feeds.length === 0}
              className="inline-flex items-center gap-2 text-xs font-semibold text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 px-3.5 py-2.5 rounded-xl transition-all shadow-2xs disabled:opacity-50"
            >
              <FaRotate className={syncingAll ? 'animate-spin' : ''} />
              {syncingAll ? 'Syncing...' : 'Sync All Feeds'}
            </button>
            <button
              onClick={() => setShowAddModal(true)}
              className="inline-flex items-center gap-2 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 px-4 py-2.5 rounded-xl transition-all shadow-sm shadow-emerald-600/20"
            >
              <FaPlus /> Connect New Feed
            </button>
          </div>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-2xs">
            <div className="flex items-center justify-between text-slate-400 mb-2">
              <span className="text-xs font-semibold">Active Feeds</span>
              <FaRss className="text-emerald-500" />
            </div>
            <div className="text-2xl font-bold text-slate-900">
              {feeds.filter((f) => f.status === 'active').length}
            </div>
            <div className="text-[11px] text-emerald-600 font-medium mt-1">
              ● Polled automatically every 30m
            </div>
          </div>

          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-2xs">
            <div className="flex items-center justify-between text-slate-400 mb-2">
              <span className="text-xs font-semibold">Auto-Scheduled Posts</span>
              <FaBolt className="text-amber-500" />
            </div>
            <div className="text-2xl font-bold text-slate-900">{totalAutoScheduled}</div>
            <div className="text-[11px] text-slate-500 mt-1">Queued via timeslots</div>
          </div>

          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-2xs">
            <div className="flex items-center justify-between text-slate-400 mb-2">
              <span className="text-xs font-semibold">Discovered Articles</span>
              <FaNewspaper className="text-blue-500" />
            </div>
            <div className="text-2xl font-bold text-slate-900">{items.length}</div>
            <div className="text-[11px] text-slate-500 mt-1">Available for 1-click sharing</div>
          </div>

          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-2xs">
            <div className="flex items-center justify-between text-slate-400 mb-2">
              <span className="text-xs font-semibold">Connected Channels</span>
              <FaShareNodes className="text-purple-500" />
            </div>
            <div className="text-2xl font-bold text-slate-900">{accounts.length}</div>
            <div className="text-[11px] text-purple-600 font-medium mt-1">Social destinations</div>
          </div>
        </div>

        {/* Tab Selection */}
        <div className="flex items-center justify-between border-b border-slate-200 mb-6">
          <div className="flex items-center gap-6 text-sm font-semibold">
            <button
              onClick={() => setActiveTab('feeds')}
              className={`pb-3 flex items-center gap-2 border-b-2 transition-colors ${
                activeTab === 'feeds'
                  ? 'text-emerald-600 border-emerald-600'
                  : 'text-slate-500 border-transparent hover:text-slate-800'
              }`}
            >
              <FaRss /> Connected Feeds ({feeds.length})
            </button>
            <button
              onClick={() => setActiveTab('articles')}
              className={`pb-3 flex items-center gap-2 border-b-2 transition-colors ${
                activeTab === 'articles'
                  ? 'text-emerald-600 border-emerald-600'
                  : 'text-slate-500 border-transparent hover:text-slate-800'
              }`}
            >
              <FaNewspaper /> Discovered Stream ({items.length})
            </button>
          </div>
        </div>

        {/* ── TAB 1: CONNECTED FEEDS ─────────────────────────────────────────── */}
        {activeTab === 'feeds' && (
          <div>
            {loading ? (
              <div className="py-16 text-center text-slate-400 text-sm">
                <FaSpinner className="animate-spin text-2xl mx-auto mb-2 text-emerald-500" />
                Loading connected feeds...
              </div>
            ) : feeds.length === 0 ? (
              <div className="bg-white border-2 border-dashed border-slate-200 rounded-2xl p-12 text-center max-w-xl mx-auto my-6">
                <div className="w-14 h-14 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center text-2xl mx-auto mb-4 border border-emerald-100">
                  <FaRss />
                </div>
                <h3 className="text-base font-bold text-slate-900 mb-1">No RSS Feeds Connected</h3>
                <p className="text-xs text-slate-500 mb-6 max-w-md mx-auto leading-relaxed">
                  Connect your WordPress blog, YouTube channel, Substack, or Medium feed to start
                  automating your social media distribution.
                </p>
                <button
                  onClick={() => setShowAddModal(true)}
                  className="inline-flex items-center gap-2 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 px-5 py-2.5 rounded-xl transition-all shadow-sm shadow-emerald-600/20"
                >
                  <FaPlus /> Connect Your First Feed
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                {feeds.map((feed) => {
                  const isSyncing = syncingFeedId === feed.id;
                  const targetAccs = accounts.filter((a) =>
                    (feed.target_account_ids || []).includes(a.id)
                  );

                  return (
                    <div
                      key={feed.id}
                      className="bg-white border border-slate-200 rounded-2xl p-6 shadow-2xs hover:shadow-xs transition-all flex flex-col md:flex-row md:items-center justify-between gap-6"
                    >
                      <div className="flex items-start gap-4">
                        <div className="w-12 h-12 rounded-xl bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-600 text-xl flex-shrink-0">
                          {feed.icon_url ? (
                            <img
                              src={feed.icon_url}
                              alt=""
                              className="w-7 h-7 rounded object-cover"
                              onError={(e) => {
                                e.target.style.display = 'none';
                              }}
                            />
                          ) : (
                            <FaGlobe />
                          )}
                        </div>

                        <div>
                          <div className="flex items-center gap-2.5 mb-1">
                            <h3 className="font-bold text-base text-slate-900">{feed.title}</h3>
                            <span
                              className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md border ${
                                feed.status === 'active'
                                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                  : 'bg-slate-100 text-slate-600 border-slate-200'
                              }`}
                            >
                              {feed.status === 'active' ? 'Active' : 'Paused'}
                            </span>
                            {feed.auto_publish ? (
                              <span className="text-[10px] font-bold uppercase tracking-wider bg-blue-50 text-blue-700 px-2 py-0.5 rounded-md border border-blue-200">
                                ⚡ Autopilot
                              </span>
                            ) : (
                              <span className="text-[10px] font-bold uppercase tracking-wider bg-slate-100 text-slate-600 px-2 py-0.5 rounded-md border border-slate-200">
                                📰 Curation Feed
                              </span>
                            )}
                            {feed.use_ai_enhancement && (
                              <span className="text-[10px] font-bold uppercase tracking-wider bg-purple-50 text-purple-700 px-2 py-0.5 rounded-md border border-purple-200 flex items-center gap-1">
                                <FaWandMagicSparkles /> AI Hooks
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-2 text-xs font-mono text-slate-500 mb-3">
                            <a
                              href={feed.feed_url}
                              target="_blank"
                              rel="noreferrer"
                              className="hover:underline flex items-center gap-1 text-slate-600"
                            >
                              {feed.feed_url} <FaArrowUpRightFromSquare className="text-[9px]" />
                            </a>
                          </div>

                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-xs text-slate-400 font-medium mr-1">Target channels:</span>
                            {targetAccs.length === 0 ? (
                              <span className="text-xs text-slate-400 italic">No channels assigned</span>
                            ) : (
                              targetAccs.map((acc) => {
                                const pCfg = PLATFORM_ICONS[acc.platform?.toLowerCase()] || {};
                                const PIcon = pCfg.Icon || FaGlobe;
                                return (
                                  <span
                                    key={acc.id}
                                    className="inline-flex items-center gap-1.5 text-xs font-medium bg-slate-50 text-slate-700 px-2.5 py-1 rounded-lg border border-slate-200"
                                  >
                                    <PIcon className={pCfg.color || ''} />
                                    {acc.username || acc.display_name}
                                  </span>
                                );
                              })
                            )}
                            {feed.auto_publish && feed.use_timeslot && (
                              <span className="inline-flex items-center gap-1 text-xs font-medium bg-amber-50 text-amber-800 border border-amber-200 px-2.5 py-1 rounded-lg">
                                <FaClock className="text-[10px]" /> {feed.timeslot_category || 'Category 1'}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 border-t md:border-t-0 pt-4 md:pt-0 border-slate-100">
                        <button
                          onClick={() => handleSyncFeed(feed.id)}
                          disabled={isSyncing}
                          className="p-2.5 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-xl transition-colors"
                          title="Sync Feed Now"
                        >
                          <FaRotate className={isSyncing ? 'animate-spin' : ''} />
                        </button>
                        <button
                          onClick={() => handleToggleFeedStatus(feed)}
                          className="p-2.5 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-xl transition-colors"
                          title={feed.status === 'active' ? 'Pause Feed' : 'Resume Feed'}
                        >
                          {feed.status === 'active' ? <FaPause /> : <FaPlay />}
                        </button>
                        <button
                          onClick={() => handleDeleteFeed(feed.id)}
                          className="p-2.5 text-red-500 hover:text-red-700 hover:bg-red-50 rounded-xl transition-colors"
                          title="Delete Feed"
                        >
                          <FaTrash />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ── TAB 2: DISCOVERED ARTICLES ──────────────────────────────────────── */}
        {activeTab === 'articles' && (
          <div>
            {items.length === 0 ? (
              <div className="bg-white border-2 border-dashed border-slate-200 rounded-2xl p-12 text-center max-w-xl mx-auto my-6">
                <FaNewspaper className="text-3xl text-slate-300 mx-auto mb-3" />
                <h3 className="text-base font-bold text-slate-900 mb-1">No Articles Discovered Yet</h3>
                <p className="text-xs text-slate-500 mb-4">
                  Once your connected feeds sync, incoming articles and videos will appear here.
                </p>
                <button
                  onClick={handleSyncAll}
                  className="text-xs font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 px-4 py-2 rounded-xl transition-colors"
                >
                  <FaRotate className="mr-1 inline" /> Check for New Content
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {items.map((item) => {
                  const hasImage = item.media_urls && item.media_urls.length > 0;
                  const isScheduled = item.status === 'scheduled' || item.status === 'published';

                  return (
                    <div
                      key={item.id}
                      className="bg-white border border-slate-200 rounded-2xl p-5 hover:border-slate-300 transition-all flex flex-col justify-between space-y-4 shadow-2xs"
                    >
                      <div className="space-y-2.5">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-semibold text-emerald-700 bg-emerald-50 border border-emerald-100 px-2 py-0.5 rounded-md">
                            {item.feed_title || 'RSS Source'}
                          </span>
                          <span className="text-slate-400 text-[11px]">
                            {item.pub_date ? new Date(item.pub_date).toLocaleDateString() : ''}
                          </span>
                        </div>

                        {hasImage && (
                          <div className="w-full h-36 rounded-xl bg-slate-100 overflow-hidden relative">
                            <img
                              src={item.media_urls[0]}
                              alt=""
                              className="w-full h-full object-cover"
                              onError={(e) => {
                                e.target.style.display = 'none';
                              }}
                            />
                          </div>
                        )}

                        <h4 className="font-bold text-sm text-slate-900 line-clamp-2 leading-snug">
                          {item.title}
                        </h4>
                        <p className="text-xs text-slate-500 line-clamp-2 leading-relaxed">
                          {item.summary}
                        </p>
                      </div>

                      <div className="pt-3 border-t border-slate-100 flex items-center justify-between">
                        {isScheduled ? (
                          <div className="flex items-center gap-1.5 text-emerald-600 text-xs font-semibold">
                            <FaCircleCheck className="text-[11px]" /> Scheduled to Queue
                          </div>
                        ) : (
                          <span className="text-xs text-slate-400">Not scheduled</span>
                        )}

                        <div className="flex items-center gap-2">
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-slate-400 hover:text-slate-700 p-1.5 text-xs"
                            title="Read original article"
                          >
                            <FaArrowUpRightFromSquare />
                          </a>
                          <button
                            onClick={() => handleOpenShare(item)}
                            className="text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 px-3.5 py-1.5 rounded-xl transition-all shadow-2xs flex items-center gap-1.5"
                          >
                            <FaShareNodes /> Share to Social
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ── CONNECT NEW FEED MODAL ────────────────────────────────────────── */}
        {showAddModal && (
          <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
            <div className="bg-white border border-slate-200 rounded-2xl max-w-2xl w-full overflow-hidden shadow-2xl animate-in fade-in zoom-in-95 duration-150">
              <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center text-lg">
                    <FaRss />
                  </div>
                  <div>
                    <h3 className="font-bold text-slate-900 text-base">Connect RSS / Atom Feed</h3>
                    <p className="text-xs text-slate-500">
                      Auto-publish new blog posts, videos, or podcasts to your social channels
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setShowAddModal(false)}
                  className="text-slate-400 hover:text-slate-600 p-2"
                >
                  <FaXmark className="text-lg" />
                </button>
              </div>

              <form onSubmit={handleCreateFeed}>
                <div className="p-6 space-y-5 max-h-[70vh] overflow-y-auto">
                  {/* Feed URL & Live Validator */}
                  <div className="space-y-1.5">
                    <label className="text-xs font-bold text-slate-700">
                      RSS / Atom Feed URL <span className="text-red-500">*</span>
                    </label>
                    <div className="flex gap-2">
                      <div className="relative flex-1">
                        <FaGlobe className="absolute left-3 top-3 text-slate-400 text-xs" />
                        <input
                          type="url"
                          required
                          value={feedUrl}
                          onChange={(e) => setFeedUrl(e.target.value)}
                          placeholder="e.g. https://myblog.com/feed or YouTube channel URL"
                          className="w-full text-xs font-mono pl-8 pr-3 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:border-emerald-500 text-slate-800"
                        />
                      </div>
                      <button
                        type="button"
                        onClick={handleValidateUrl}
                        disabled={validating || !feedUrl.trim()}
                        className="text-xs font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 px-4 py-2.5 rounded-xl transition-colors disabled:opacity-50"
                      >
                        {validating ? <FaSpinner className="animate-spin" /> : 'Validate'}
                      </button>
                    </div>

                    {validatedData && (
                      <div className="flex items-center gap-1.5 text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 p-2 rounded-lg font-medium">
                        <FaCircleCheck /> Feed Verified: <strong>{validatedData.title}</strong> (
                        {validatedData.items_count} items detected)
                      </div>
                    )}
                  </div>

                  {/* Feed Title (Optional Custom Name) */}
                  <div className="space-y-1.5">
                    <label className="text-xs font-bold text-slate-700">Feed Display Name</label>
                    <input
                      type="text"
                      value={feedTitle}
                      onChange={(e) => setFeedTitle(e.target.value)}
                      placeholder="e.g. Company Blog"
                      className="w-full text-xs px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:border-emerald-500 text-slate-800"
                    />
                  </div>

                  {/* Target Social Accounts */}
                  <div className="space-y-1.5">
                    <label className="text-xs font-bold text-slate-700">
                      Destination Social Accounts
                    </label>
                    {accounts.length === 0 ? (
                      <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 p-3 rounded-xl">
                        No connected accounts found. Please connect accounts in Connections first.
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {accounts.map((acc) => {
                          const isChecked = selectedAccounts.includes(acc.id);
                          const pCfg = PLATFORM_ICONS[acc.platform?.toLowerCase()] || {};
                          const PIcon = pCfg.Icon || FaGlobe;

                          return (
                            <label
                              key={acc.id}
                              className={`flex items-center gap-2 p-2.5 border rounded-xl cursor-pointer transition-all ${
                                isChecked
                                  ? 'border-emerald-500 bg-emerald-50/50'
                                  : 'border-slate-200 hover:border-slate-300'
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={isChecked}
                                onChange={(e) => {
                                  if (e.target.checked) {
                                    setSelectedAccounts([...selectedAccounts, acc.id]);
                                  } else {
                                    setSelectedAccounts(selectedAccounts.filter((id) => id !== acc.id));
                                  }
                                }}
                                className="rounded text-emerald-600 focus:ring-emerald-500"
                              />
                              <PIcon className={pCfg.color || 'text-slate-600'} />
                              <span className="text-xs font-semibold text-slate-800 truncate">
                                {acc.username || acc.display_name}
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  {/* Automation Settings */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <label className="text-xs font-bold text-slate-700">Automation Mode</label>
                      <select
                        value={postStatus}
                        onChange={(e) => setPostStatus(e.target.value)}
                        className="w-full text-xs bg-slate-50 border border-slate-200 rounded-xl px-3 py-2.5 focus:outline-none focus:border-emerald-500 text-slate-800 font-medium"
                      >
                        <option value="scheduled">⚡ Auto-Schedule to Queue</option>
                        <option value="draft">📝 Save as Draft for Review</option>
                        <option value="pending_approval">⏳ Send to Team Approvals</option>
                      </select>
                    </div>

                    <div className="space-y-1.5">
                      <label className="text-xs font-bold text-slate-700">Timeslot Category</label>
                      <select
                        value={timeslotCategory}
                        onChange={(e) => setTimeslotCategory(e.target.value)}
                        className="w-full text-xs bg-slate-50 border border-slate-200 rounded-xl px-3 py-2.5 focus:outline-none focus:border-emerald-500 text-slate-800 font-medium"
                      >
                        <option value="Category 1">Category 1 (Primary)</option>
                        <option value="Category 2">Category 2</option>
                        <option value="Category 3">Category 3</option>
                      </select>
                    </div>
                  </div>

                  {/* Caption Template */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-slate-700">Caption Template</label>
                      <label className="flex items-center gap-1.5 text-xs text-purple-700 font-semibold cursor-pointer">
                        <input
                          type="checkbox"
                          checked={useAi}
                          onChange={(e) => setUseAi(e.target.checked)}
                          className="rounded text-purple-600"
                        />
                        <FaWandMagicSparkles /> AI Hook Generator
                      </label>
                    </div>
                    <textarea
                      rows={3}
                      value={postTemplate}
                      onChange={(e) => setPostTemplate(e.target.value)}
                      className="w-full text-xs font-mono bg-slate-50 border border-slate-200 rounded-xl p-3 focus:outline-none focus:border-emerald-500 text-slate-800 leading-relaxed"
                    />
                    <div className="flex gap-1.5 text-[10px] text-slate-400">
                      <span>Placeholders:</span>
                      <span className="bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded font-mono">
                        {'{title}'}
                      </span>
                      <span className="bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded font-mono">
                        {'{link}'}
                      </span>
                      <span className="bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded font-mono">
                        {'{summary}'}
                      </span>
                      <span className="bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded font-mono">
                        {'{author}'}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="px-6 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setShowAddModal(false)}
                    className="text-xs font-semibold text-slate-600 hover:text-slate-800 px-4 py-2 rounded-xl transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submitting}
                    className="text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 px-5 py-2.5 rounded-xl transition-all shadow-sm shadow-emerald-600/20 disabled:opacity-50 flex items-center gap-2"
                  >
                    {submitting ? <FaSpinner className="animate-spin" /> : 'Connect & Automate'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* ── SHARE ARTICLE MODAL ───────────────────────────────────────────── */}
        {sharingItem && (
          <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
            <div className="bg-white border border-slate-200 rounded-2xl max-w-xl w-full overflow-hidden shadow-2xl animate-in fade-in zoom-in-95 duration-150">
              <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between">
                <h3 className="font-bold text-slate-900 text-base">Share Article to Social</h3>
                <button onClick={() => setSharingItem(null)} className="text-slate-400 hover:text-slate-600 p-2">
                  <FaXmark className="text-lg" />
                </button>
              </div>

              <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
                <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                  <div className="text-xs font-bold text-slate-900 mb-1">{sharingItem.title}</div>
                  <div className="text-[11px] text-slate-500 font-mono truncate">{sharingItem.url}</div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-700">Target Accounts</label>
                  <div className="grid grid-cols-2 gap-2">
                    {accounts.map((acc) => {
                      const isChecked = shareAccounts.includes(acc.id);
                      const pCfg = PLATFORM_ICONS[acc.platform?.toLowerCase()] || {};
                      const PIcon = pCfg.Icon || FaGlobe;

                      return (
                        <label
                          key={acc.id}
                          className={`flex items-center gap-2 p-2 border rounded-xl cursor-pointer text-xs ${
                            isChecked ? 'border-emerald-500 bg-emerald-50/50' : 'border-slate-200'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setShareAccounts([...shareAccounts, acc.id]);
                              } else {
                                setShareAccounts(shareAccounts.filter((id) => id !== acc.id));
                              }
                            }}
                            className="rounded text-emerald-600"
                          />
                          <PIcon className={pCfg.color || ''} />
                          <span className="truncate">{acc.username || acc.display_name}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-700">Post Caption</label>
                  <textarea
                    rows={4}
                    value={shareCustomContent}
                    onChange={(e) => setShareCustomContent(e.target.value)}
                    className="w-full text-xs font-sans bg-slate-50 border border-slate-200 rounded-xl p-3 focus:outline-none focus:border-emerald-500 text-slate-800 leading-relaxed"
                  />
                </div>
              </div>

              <div className="px-6 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-3">
                <button
                  onClick={() => setSharingItem(null)}
                  className="text-xs font-semibold text-slate-600 px-4 py-2"
                >
                  Cancel
                </button>
                <button
                  onClick={handleExecuteShare}
                  disabled={sharingLoading}
                  className="text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 px-5 py-2.5 rounded-xl flex items-center gap-2"
                >
                  {sharingLoading ? <FaSpinner className="animate-spin" /> : 'Schedule to Timeslot'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
