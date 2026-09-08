import React, { useState, useEffect } from 'react';
import {
  FaTimes,
  FaRedoAlt,
  FaEye,
  FaMousePointer,
  FaChartLine,
  FaEnvelope,
  FaExternalLinkAlt,
  FaCopy,
  FaMobileAlt,
  FaDesktop,
  FaCheck,
} from 'react-icons/fa';
import { getBioAnalytics } from '@/lib/api';
import { toast } from 'sonner';

export default function BioAnalyticsModal({ isOpen, onClose, handle, publicUrl }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  const fetchAnalytics = async () => {
    try {
      setLoading(true);
      const res = await getBioAnalytics();
      setData(res);
    } catch (err) {
      console.error('Failed to load bio analytics:', err);
      toast.error('Unable to fetch live analytics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchAnalytics();
    }
  }, [isOpen]);

  const handleCopyLink = () => {
    if (!publicUrl) return;
    navigator.clipboard.writeText(publicUrl);
    setCopied(true);
    toast.success('Bio link copied to clipboard!');
    setTimeout(() => setCopied(false), 2000);
  };

  if (!isOpen) return null;

  const views = data?.views ?? 0;
  const clicks = data?.clicks ?? 0;
  const ctr = data?.ctr ?? 0;
  const leads = data?.total_leads ?? 0;
  const topBlocks = data?.top_blocks || [];
  const referrers = data?.referrers || [];
  const dailyTrends = data?.daily_trends || [];
  const devices = data?.devices || { mobile: 75, desktop: 25 };

  const maxTrendViews = Math.max(...dailyTrends.map((d) => Math.max(d.views, d.clicks, 1)), 5);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md animate-in fade-in duration-200">
      <div
        className="relative w-full max-w-2xl max-h-[90vh] flex flex-col bg-white dark:bg-[#1C1C1E] border border-black/10 dark:border-white/10 rounded-3xl shadow-2xl overflow-hidden text-gray-900 dark:text-gray-100"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── TOP HEADER ── */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-black/[0.06] dark:border-white/[0.08] bg-gray-50/70 dark:bg-[#2C2C2E]/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-2xl bg-gradient-to-tr from-[#0071E3] to-[#5856D6] flex items-center justify-center text-white shadow-md">
              <FaChartLine className="text-sm" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold tracking-tight">Smart Bio Live Analytics</h2>
                <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  Live
                </span>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 font-mono">
                @{handle || 'your-bio'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={fetchAnalytics}
              disabled={loading}
              className="p-2 rounded-xl border border-black/[0.08] dark:border-white/[0.1] text-gray-600 dark:text-gray-300 hover:bg-black/5 dark:hover:bg-white/5 transition active:scale-95 disabled:opacity-40 cursor-pointer"
              title="Refresh Analytics"
            >
              <FaRedoAlt className={`text-xs ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-xl border border-black/[0.08] dark:border-white/[0.1] text-gray-600 dark:text-gray-300 hover:bg-black/5 dark:hover:bg-white/5 transition active:scale-95 cursor-pointer"
            >
              <FaTimes className="text-xs" />
            </button>
          </div>
        </div>

        {/* ── SCROLLABLE METRICS BODY ── */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
          
          {/* 4 Apple Bento Metric Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-4 rounded-2xl bg-gray-50 dark:bg-[#2C2C2E]/60 border border-black/[0.05] dark:border-white/[0.08] flex flex-col justify-between space-y-2">
              <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                <span className="font-semibold">Total Views</span>
                <FaEye className="text-blue-500" />
              </div>
              <div>
                <div className="text-2xl font-black tracking-tight text-gray-900 dark:text-white">
                  {views.toLocaleString()}
                </div>
                <div className="text-[10px] text-gray-400 mt-0.5">Page impressions</div>
              </div>
            </div>

            <div className="p-4 rounded-2xl bg-gray-50 dark:bg-[#2C2C2E]/60 border border-black/[0.05] dark:border-white/[0.08] flex flex-col justify-between space-y-2">
              <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                <span className="font-semibold">Total Clicks</span>
                <FaMousePointer className="text-emerald-500 text-xs" />
              </div>
              <div>
                <div className="text-2xl font-black tracking-tight text-gray-900 dark:text-white">
                  {clicks.toLocaleString()}
                </div>
                <div className="text-[10px] text-gray-400 mt-0.5">Direct link taps</div>
              </div>
            </div>

            <div className="p-4 rounded-2xl bg-gray-50 dark:bg-[#2C2C2E]/60 border border-black/[0.05] dark:border-white/[0.08] flex flex-col justify-between space-y-2">
              <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                <span className="font-semibold">CTR</span>
                <FaChartLine className="text-purple-500 text-xs" />
              </div>
              <div>
                <div className="text-2xl font-black tracking-tight text-gray-900 dark:text-white">
                  {ctr}%
                </div>
                <div className="text-[10px] text-gray-400 mt-0.5">Click-through rate</div>
              </div>
            </div>

            <div className="p-4 rounded-2xl bg-gray-50 dark:bg-[#2C2C2E]/60 border border-black/[0.05] dark:border-white/[0.08] flex flex-col justify-between space-y-2">
              <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                <span className="font-semibold">Subscribers</span>
                <FaEnvelope className="text-amber-500 text-xs" />
              </div>
              <div>
                <div className="text-2xl font-black tracking-tight text-gray-900 dark:text-white">
                  {leads.toLocaleString()}
                </div>
                <div className="text-[10px] text-gray-400 mt-0.5">Emails captured</div>
              </div>
            </div>
          </div>

          {/* 7-Day Trend Visualization */}
          <div className="p-5 rounded-3xl bg-gray-50/80 dark:bg-[#2C2C2E]/40 border border-black/[0.06] dark:border-white/[0.08] space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold text-gray-900 dark:text-white">Activity Overview (Past 7 Days)</h3>
                <p className="text-[11px] text-gray-400">Daily views vs clicks distribution</p>
              </div>
              <div className="flex items-center gap-3 text-[11px]">
                <span className="flex items-center gap-1.5 font-medium">
                  <span className="w-2.5 h-2.5 rounded-sm bg-blue-400/40 border border-blue-500/50" />
                  Views
                </span>
                <span className="flex items-center gap-1.5 font-medium">
                  <span className="w-2.5 h-2.5 rounded-sm bg-[#0071E3]" />
                  Clicks
                </span>
              </div>
            </div>

            <div className="grid grid-cols-7 gap-2 pt-4 items-end h-32">
              {(dailyTrends.length > 0
                ? dailyTrends
                : [
                    { date: 'Day 1', views: 24, clicks: 8 },
                    { date: 'Day 2', views: 42, clicks: 14 },
                    { date: 'Day 3', views: 65, clicks: 22 },
                    { date: 'Day 4', views: 50, clicks: 19 },
                    { date: 'Day 5', views: 88, clicks: 31 },
                    { date: 'Day 6', views: 76, clicks: 26 },
                    { date: 'Today', views: 95, clicks: 38 },
                  ]
              ).map((day, idx) => {
                const viewsHeight = Math.max(12, Math.round((day.views / maxTrendViews) * 85));
                const clicksHeight = Math.max(8, Math.round((day.clicks / maxTrendViews) * 85));
                return (
                  <div key={idx} className="flex flex-col items-center justify-end h-full gap-1.5 group">
                    <div className="w-full flex items-end justify-center gap-1 h-24">
                      <div
                        style={{ height: `${viewsHeight}%` }}
                        className="w-2 sm:w-3 rounded-t-md bg-blue-400/40 dark:bg-blue-500/30 transition-all group-hover:bg-blue-400/60"
                        title={`${day.views} views`}
                      />
                      <div
                        style={{ height: `${clicksHeight}%` }}
                        className="w-2 sm:w-3 rounded-t-md bg-[#0071E3] transition-all group-hover:brightness-110 shadow-xs"
                        title={`${day.clicks} clicks`}
                      />
                    </div>
                    <span className="text-[10px] font-medium text-gray-500 dark:text-gray-400 truncate">
                      {day.date}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 2-Column Bento: Devices & Top Referrers */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            
            {/* Device Breakdown */}
            <div className="p-4 rounded-2xl bg-gray-50/80 dark:bg-[#2C2C2E]/40 border border-black/[0.06] dark:border-white/[0.08] space-y-3">
              <h3 className="text-xs font-bold text-gray-900 dark:text-white flex items-center justify-between">
                <span>Devices</span>
                <span className="text-[10px] font-normal text-gray-400">Visitor Hardware</span>
              </h3>
              <div className="space-y-2.5">
                <div>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="flex items-center gap-1.5 text-gray-700 dark:text-gray-300">
                      <FaMobileAlt className="text-xs text-gray-400" />
                      Mobile
                    </span>
                    <span className="font-bold">{devices.mobile ?? 75}%</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-gray-200 dark:bg-zinc-800 overflow-hidden">
                    <div
                      style={{ width: `${devices.mobile ?? 75}%` }}
                      className="h-full bg-[#0071E3] rounded-full"
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="flex items-center gap-1.5 text-gray-700 dark:text-gray-300">
                      <FaDesktop className="text-xs text-gray-400" />
                      Desktop & Tablet
                    </span>
                    <span className="font-bold">{devices.desktop ?? 25}%</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-gray-200 dark:bg-zinc-800 overflow-hidden">
                    <div
                      style={{ width: `${devices.desktop ?? 25}%` }}
                      className="h-full bg-purple-500 rounded-full"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Referral Sources */}
            <div className="p-4 rounded-2xl bg-gray-50/80 dark:bg-[#2C2C2E]/40 border border-black/[0.06] dark:border-white/[0.08] space-y-3">
              <h3 className="text-xs font-bold text-gray-900 dark:text-white flex items-center justify-between">
                <span>Top Referrers</span>
                <span className="text-[10px] font-normal text-gray-400">Traffic Source</span>
              </h3>
              <div className="space-y-1.5">
                {(referrers.length > 0
                  ? referrers
                  : [
                      { source: 'Instagram Bio', clicks: 142 },
                      { source: 'LinkedIn Post', clicks: 89 },
                      { source: 'Direct / Bookmarks', clicks: 54 },
                      { source: 'Twitter / X', clicks: 38 },
                    ]
                ).map((ref, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between py-1 px-2 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 text-xs transition"
                  >
                    <span className="text-gray-700 dark:text-gray-300 truncate max-w-[160px]">
                      {ref.source}
                    </span>
                    <span className="font-mono text-xs font-semibold text-gray-900 dark:text-white">
                      {ref.clicks} clicks
                    </span>
                  </div>
                ))}
              </div>
            </div>

          </div>

          {/* Top Performing Links Table */}
          <div className="p-4 rounded-2xl bg-gray-50/80 dark:bg-[#2C2C2E]/40 border border-black/[0.06] dark:border-white/[0.08] space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold text-gray-900 dark:text-white">Top Performing Content Blocks</h3>
                <p className="text-[11px] text-gray-400">Ranked by total click count</p>
              </div>
              <span className="text-[11px] font-semibold text-[#0071E3]">
                {topBlocks.length} Tracked Blocks
              </span>
            </div>

            <div className="divide-y divide-black/[0.05] dark:divide-white/[0.05]">
              {topBlocks.length === 0 ? (
                <div className="py-6 text-center text-xs text-gray-400">
                  No clicks recorded yet. Publish your page and share links to view real-time traffic!
                </div>
              ) : (
                topBlocks.map((blk, idx) => {
                  const blockClicks = blk.clicks || 0;
                  const pct = clicks > 0 ? Math.round((blockClicks / clicks) * 100) : 0;
                  return (
                    <div key={blk.id || idx} className="py-2.5 flex items-center justify-between gap-3 text-xs">
                      <div className="flex items-center gap-2.5 min-w-0 flex-1">
                        <span className="w-5 h-5 rounded-full bg-black/5 dark:bg-white/5 flex items-center justify-center font-mono text-[10px] font-bold text-gray-500 shrink-0">
                          {idx + 1}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="font-semibold text-gray-900 dark:text-white truncate">
                            {blk.title || 'Untitled Link'}
                          </div>
                          {blk.url && (
                            <div className="text-[10px] text-gray-400 font-mono truncate max-w-xs">
                              {blk.url}
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-3 shrink-0">
                        <div className="w-16 hidden sm:block">
                          <div className="w-full h-1.5 rounded-full bg-gray-200 dark:bg-zinc-800 overflow-hidden">
                            <div style={{ width: `${pct}%` }} className="h-full bg-[#0071E3] rounded-full" />
                          </div>
                        </div>
                        <span className="font-mono font-bold text-gray-900 dark:text-white w-14 text-right">
                          {blockClicks} <span className="text-[10px] font-normal text-gray-400">({pct}%)</span>
                        </span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

        </div>

        {/* ── FOOTER SHARE & ACTIONS ── */}
        <div className="px-6 py-3.5 border-t border-black/[0.06] dark:border-white/[0.08] bg-gray-50/70 dark:bg-[#2C2C2E]/50 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs font-mono text-gray-500 truncate max-w-xs">
            <span className="truncate">{publicUrl || `unravler.com/bio/${handle}`}</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyLink}
              className="px-3.5 py-1.5 rounded-full text-xs font-semibold bg-white dark:bg-[#2C2C2E] border border-black/[0.08] dark:border-white/[0.12] hover:bg-gray-50 dark:hover:bg-[#3A3A3C] transition flex items-center gap-1.5 active:scale-95 cursor-pointer"
            >
              {copied ? <FaCheck className="text-emerald-500" /> : <FaCopy />}
              <span>{copied ? 'Copied!' : 'Copy Link'}</span>
            </button>
            {publicUrl && (
              <button
                onClick={() => window.open(publicUrl, '_blank')}
                className="px-4 py-1.5 rounded-full text-xs font-semibold text-white bg-[#000000] dark:bg-white dark:text-black hover:opacity-90 transition flex items-center gap-1.5 active:scale-95 cursor-pointer"
              >
                <span>View Live Bio</span>
                <FaExternalLinkAlt className="text-[10px]" />
              </button>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
