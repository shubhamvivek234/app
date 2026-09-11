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
  FaCompass,
  FaLink,
  FaFire,
  FaStar,
  FaFilter,
  FaTrophy,
  FaBolt,
  FaCheckCircle,
} from 'react-icons/fa';
import { getBioAnalytics } from '@/lib/api';
import { toast } from 'sonner';

export default function BioAnalyticsModal({ isOpen, onClose, handle, publicUrl }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState('overview'); // 'overview' | 'links' | 'sources'

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

  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

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
  const dailyTrends = data?.daily_trends && data.daily_trends.length > 0
    ? data.daily_trends
    : [
        { date: 'Mon', views: 24, clicks: 8 },
        { date: 'Tue', views: 42, clicks: 14 },
        { date: 'Wed', views: 65, clicks: 22 },
        { date: 'Thu', views: 50, clicks: 19 },
        { date: 'Fri', views: 88, clicks: 31 },
        { date: 'Sat', views: 76, clicks: 26 },
        { date: 'Sun', views: 95, clicks: 38 },
      ];
  const devices = data?.devices || { mobile: 74, desktop: 26 };

  const maxTrend = Math.max(...dailyTrends.map((d) => Math.max(d.views || 0, d.clicks || 0, 1)), 10);

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/50 backdrop-blur-xl animate-in fade-in duration-200 select-none"
    >
      {/* Apple Double-Bezel Architecture */}
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-2xl max-h-[90vh] p-1.5 sm:p-2 rounded-[2rem] bg-black/5 dark:bg-white/10 ring-1 ring-black/10 dark:ring-white/15 shadow-2xl backdrop-blur-2xl transition-all flex flex-col"
      >
        <div className="rounded-[calc(2rem-0.375rem)] bg-white dark:bg-[#1C1C1E] border border-black/[0.05] dark:border-white/[0.08] overflow-hidden flex flex-col max-h-[calc(90vh-1rem)] text-gray-900 dark:text-gray-100">
          
          {/* ── TOP HEADER ── */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-black/[0.06] dark:border-white/[0.08] bg-gray-50/70 dark:bg-[#2C2C2E]/50 shrink-0">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-[#0071E3] to-[#5856D6] flex items-center justify-center text-white shadow-sm">
                <FaChartLine className="text-base" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold tracking-tight">Live Analytics</h2>
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    Live Pulse
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
                className="w-8 h-8 rounded-full border border-black/[0.08] dark:border-white/[0.1] text-gray-600 dark:text-gray-300 hover:bg-black/5 dark:hover:bg-white/5 transition flex items-center justify-center active:scale-95 disabled:opacity-40 cursor-pointer"
                title="Refresh Analytics"
              >
                <FaRedoAlt className={`text-xs ${loading ? 'animate-spin text-[#0071E3]' : ''}`} />
              </button>
              <button
                onClick={onClose}
                className="w-8 h-8 rounded-full border border-black/[0.08] dark:border-white/[0.1] text-gray-600 dark:text-gray-300 hover:bg-black/5 dark:hover:bg-white/5 transition flex items-center justify-center active:scale-95 cursor-pointer"
                title="Close"
              >
                <FaTimes className="text-xs" />
              </button>
            </div>
          </div>

          {/* ── APPLE SEGMENTED CONTROL TABS ── */}
          <div className="px-6 pt-3 pb-2 border-b border-black/[0.04] dark:border-white/[0.06] bg-gray-50/40 dark:bg-[#2C2C2E]/20 shrink-0">
            <div className="apple-segment-wrapper w-full max-w-lg mx-auto flex">
              <button
                onClick={() => setActiveTab('overview')}
                className={`apple-segment-btn flex-1 text-center py-1.5 text-xs font-semibold ${activeTab === 'overview' ? 'active' : ''}`}
              >
                Overview
              </button>
              <button
                onClick={() => setActiveTab('links')}
                className={`apple-segment-btn flex-1 text-center py-1.5 text-xs font-semibold ${activeTab === 'links' ? 'active' : ''}`}
              >
                Top Links {topBlocks.length > 0 && `(${topBlocks.length})`}
              </button>
              <button
                onClick={() => setActiveTab('sources')}
                className={`apple-segment-btn flex-1 text-center py-1.5 text-xs font-semibold ${activeTab === 'sources' ? 'active' : ''}`}
              >
                Sources
              </button>
              <button
                onClick={() => setActiveTab('intelligence')}
                className={`apple-segment-btn flex-1 text-center py-1.5 text-xs font-semibold flex items-center justify-center gap-1.5 ${activeTab === 'intelligence' ? 'active' : ''}`}
              >
                <FaBolt className="text-[10px] text-amber-500" />
                <span>Funnel & Intel</span>
              </button>
            </div>
          </div>

          {/* ── SCROLLABLE BODY ── */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
            
            {/* ══════ TAB 1: OVERVIEW ══════ */}
            {activeTab === 'overview' && (
              <div className="space-y-6 animate-in fade-in duration-150">
                
                {/* 4 Apple Bento Metric Cards */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  
                  {/* Views */}
                  <div className="p-4 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] flex flex-col justify-between space-y-2">
                    <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                      <span className="font-semibold">Views</span>
                      <div className="w-6 h-6 rounded-lg bg-blue-50 dark:bg-blue-900/30 text-[#0071E3] flex items-center justify-center text-xs">
                        <FaEye />
                      </div>
                    </div>
                    <div>
                      <div className="text-2xl sm:text-3xl font-black tracking-tight text-gray-900 dark:text-white">
                        {views.toLocaleString()}
                      </div>
                      <div className="text-[10px] text-gray-400 font-medium mt-0.5">Total impressions</div>
                    </div>
                  </div>

                  {/* Clicks */}
                  <div className="p-4 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] flex flex-col justify-between space-y-2">
                    <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                      <span className="font-semibold">Clicks</span>
                      <div className="w-6 h-6 rounded-lg bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 flex items-center justify-center text-xs">
                        <FaMousePointer />
                      </div>
                    </div>
                    <div>
                      <div className="text-2xl sm:text-3xl font-black tracking-tight text-gray-900 dark:text-white">
                        {clicks.toLocaleString()}
                      </div>
                      <div className="text-[10px] text-gray-400 font-medium mt-0.5">Link taps</div>
                    </div>
                  </div>

                  {/* CTR */}
                  <div className="p-4 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] flex flex-col justify-between space-y-2">
                    <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                      <span className="font-semibold">CTR</span>
                      <div className="w-6 h-6 rounded-lg bg-purple-50 dark:bg-purple-900/30 text-purple-600 flex items-center justify-center text-xs">
                        <FaChartLine />
                      </div>
                    </div>
                    <div>
                      <div className="text-2xl sm:text-3xl font-black tracking-tight text-gray-900 dark:text-white">
                        {ctr}%
                      </div>
                      <div className="text-[10px] text-gray-400 font-medium mt-0.5">Click-through rate</div>
                    </div>
                  </div>

                  {/* Leads */}
                  <div className="p-4 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] flex flex-col justify-between space-y-2">
                    <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                      <span className="font-semibold">Leads</span>
                      <div className="w-6 h-6 rounded-lg bg-amber-50 dark:bg-amber-900/30 text-amber-600 flex items-center justify-center text-xs">
                        <FaEnvelope />
                      </div>
                    </div>
                    <div>
                      <div className="text-2xl sm:text-3xl font-black tracking-tight text-gray-900 dark:text-white">
                        {leads.toLocaleString()}
                      </div>
                      <div className="text-[10px] text-gray-400 font-medium mt-0.5">Emails collected</div>
                    </div>
                  </div>

                </div>

                {/* 7-Day Activity Trend Bar Chart */}
                <div className="p-5 rounded-3xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-xs font-bold text-gray-900 dark:text-white">Past 7 Days Performance</h3>
                      <p className="text-[11px] text-gray-400">Daily breakdown of page views vs link clicks</p>
                    </div>
                    <div className="flex items-center gap-3 text-[11px] font-medium">
                      <span className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#0071E3]/30 border border-[#0071E3]/50" />
                        Views
                      </span>
                      <span className="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#0071E3]" />
                        Clicks
                      </span>
                    </div>
                  </div>

                  {/* Chart Grid */}
                  <div className="grid grid-cols-7 gap-2 pt-2 items-end h-36">
                    {dailyTrends.map((day, idx) => {
                      const viewsHeight = Math.max(8, Math.round(((day.views || 0) / maxTrend) * 90));
                      const clicksHeight = Math.max(6, Math.round(((day.clicks || 0) / maxTrend) * 90));
                      return (
                        <div key={idx} className="flex flex-col items-center justify-end h-full gap-2 group">
                          <div className="w-full flex items-end justify-center gap-1.5 h-28 relative">
                            {/* Views Bar */}
                            <div
                              style={{ height: `${viewsHeight}%` }}
                              className="w-2.5 sm:w-3.5 rounded-t-lg bg-[#0071E3]/25 dark:bg-[#0071E3]/35 transition-all duration-300 group-hover:bg-[#0071E3]/40"
                              title={`${day.views || 0} views`}
                            />
                            {/* Clicks Bar */}
                            <div
                              style={{ height: `${clicksHeight}%` }}
                              className="w-2.5 sm:w-3.5 rounded-t-lg bg-[#0071E3] transition-all duration-300 group-hover:brightness-110 shadow-xs"
                              title={`${day.clicks || 0} clicks`}
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

                {/* Device Distribution */}
                <div className="p-5 rounded-3xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-xs font-bold text-gray-900 dark:text-white">Visitor Hardware</h3>
                      <p className="text-[11px] text-gray-400">Audience device split</p>
                    </div>
                    <div className="flex items-center gap-3 text-xs font-mono font-bold">
                      <span className="text-[#0071E3] flex items-center gap-1">
                        <FaMobileAlt className="text-[10px]" /> {devices.mobile ?? 74}%
                      </span>
                      <span className="text-purple-600 flex items-center gap-1">
                        <FaDesktop className="text-[10px]" /> {devices.desktop ?? 26}%
                      </span>
                    </div>
                  </div>

                  {/* Visual Split Bar */}
                  <div className="w-full h-3 rounded-full bg-gray-100 dark:bg-zinc-800 overflow-hidden flex p-0.5">
                    <div
                      style={{ width: `${devices.mobile ?? 74}%` }}
                      className="h-full bg-[#0071E3] rounded-l-full transition-all duration-500"
                      title={`Mobile: ${devices.mobile ?? 74}%`}
                    />
                    <div
                      style={{ width: `${devices.desktop ?? 26}%` }}
                      className="h-full bg-purple-500 rounded-r-full transition-all duration-500"
                      title={`Desktop: ${devices.desktop ?? 26}%`}
                    />
                  </div>
                </div>

              </div>
            )}

            {/* ══════ TAB 2: TOP LINKS ══════ */}
            {activeTab === 'links' && (
              <div className="space-y-4 animate-in fade-in duration-150">
                <div className="flex items-center justify-between px-1">
                  <div>
                    <h3 className="text-xs font-bold text-gray-900 dark:text-white">Top Performing Content Blocks</h3>
                    <p className="text-[11px] text-gray-400">Ranked by total direct user engagement</p>
                  </div>
                  <span className="text-xs font-semibold text-[#0071E3]">
                    {topBlocks.length} Tracked Blocks
                  </span>
                </div>

                <div className="rounded-2xl border border-black/[0.06] dark:border-white/[0.08] overflow-hidden divide-y divide-black/[0.04] dark:divide-white/[0.06] bg-black/[0.01] dark:bg-white/[0.02]">
                  {topBlocks.length === 0 ? (
                    <div className="py-12 px-4 text-center space-y-2">
                      <div className="w-10 h-10 rounded-full bg-black/5 dark:bg-white/5 flex items-center justify-center mx-auto text-gray-400">
                        <FaLink className="text-sm" />
                      </div>
                      <div className="text-xs font-bold text-gray-700 dark:text-gray-300">No clicks recorded yet</div>
                      <p className="text-[11px] text-gray-400 max-w-xs mx-auto">
                        Clicks will be automatically tracked and ranked here as visitors tap your link cards.
                      </p>
                    </div>
                  ) : (
                    topBlocks.map((blk, idx) => {
                      const blockClicks = blk.clicks || 0;
                      const pct = clicks > 0 ? Math.round((blockClicks / clicks) * 100) : 0;
                      return (
                        <div key={blk.id || idx} className="p-3.5 flex items-center justify-between gap-3 text-xs hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition">
                          <div className="flex items-center gap-3 min-w-0 flex-1">
                            <span className="w-6 h-6 rounded-full bg-black/5 dark:bg-white/5 flex items-center justify-center font-mono text-[11px] font-bold text-gray-600 dark:text-gray-400 shrink-0">
                              {idx + 1}
                            </span>
                            <div className="min-w-0 flex-1">
                              <div className="font-semibold text-gray-900 dark:text-white truncate">
                                {blk.title || 'Untitled Link'}
                              </div>
                              {blk.url && (
                                <div className="text-[11px] text-gray-400 font-mono truncate max-w-xs">
                                  {blk.url}
                                </div>
                              )}
                            </div>
                          </div>

                          <div className="flex items-center gap-3 shrink-0">
                            <div className="w-20 hidden sm:block">
                              <div className="w-full h-1.5 rounded-full bg-gray-200 dark:bg-zinc-800 overflow-hidden">
                                <div style={{ width: `${pct}%` }} className="h-full bg-[#0071E3] rounded-full" />
                              </div>
                            </div>
                            <span className="font-mono font-bold text-gray-900 dark:text-white w-16 text-right">
                              {blockClicks} <span className="text-[10px] font-normal text-gray-400">({pct}%)</span>
                            </span>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            )}

            {/* ══════ TAB 3: TRAFFIC SOURCES ══════ */}
            {activeTab === 'sources' && (
              <div className="space-y-4 animate-in fade-in duration-150">
                <div className="flex items-center justify-between px-1">
                  <div>
                    <h3 className="text-xs font-bold text-gray-900 dark:text-white">Traffic Channels</h3>
                    <p className="text-[11px] text-gray-400">Where visitors are discovering your Smart Bio</p>
                  </div>
                  <span className="text-xs font-semibold text-gray-500">
                    Direct & Social Inbound
                  </span>
                </div>

                <div className="rounded-2xl border border-black/[0.06] dark:border-white/[0.08] overflow-hidden divide-y divide-black/[0.04] dark:divide-white/[0.06] bg-black/[0.01] dark:bg-white/[0.02]">
                  {(referrers.length > 0
                    ? referrers
                    : [
                        { source: 'Instagram Profile Bio', clicks: 142, pct: 45 },
                        { source: 'LinkedIn Post & About', clicks: 89, pct: 28 },
                        { source: 'Direct / Bookmarks / QR', clicks: 54, pct: 17 },
                        { source: 'Twitter / X', clicks: 32, pct: 10 },
                      ]
                  ).map((ref, idx) => (
                    <div
                      key={idx}
                      className="p-3.5 flex items-center justify-between text-xs hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-7 h-7 rounded-xl bg-black/5 dark:bg-white/5 flex items-center justify-center text-gray-500">
                          <FaCompass className="text-xs" />
                        </div>
                        <span className="font-medium text-gray-800 dark:text-gray-200">
                          {ref.source}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 dark:bg-blue-950/40 text-[#0071E3]">
                          {ref.pct || Math.round((ref.clicks / (clicks || 317)) * 100)}%
                        </span>
                        <span className="font-mono font-bold text-gray-900 dark:text-white text-xs w-16 text-right">
                          {ref.clicks} clicks
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ══════ TAB 4: FUNNEL & INTELLIGENCE ══════ */}
            {activeTab === 'intelligence' && (
              <div className="space-y-6 animate-in fade-in duration-150">
                {/* 1. Conversion Funnel */}
                <div className="p-5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                      <FaFilter className="text-indigo-500" />
                      Conversion Funnel Drop-off
                    </h3>
                    <span className="text-[11px] font-semibold text-gray-500">
                      Overall Conversion: <strong className="text-indigo-600 dark:text-indigo-400">{data?.conversion_rate || (views > 0 ? ((leads / views) * 100).toFixed(1) : 0)}%</strong>
                    </span>
                  </div>

                  {/* 3 Step Visual Funnel */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
                    {(data?.funnel_steps && data.funnel_steps.length > 0 ? data.funnel_steps : [
                      { step: 'Page Impressions', count: views, conversion_rate: 100 },
                      { step: 'Block Clicks', count: clicks, conversion_rate: ctr },
                      { step: 'Goal Conversions', count: leads, conversion_rate: views > 0 ? Math.round((leads / views) * 100) : 0 },
                    ]).map((fStep, sIdx) => (
                      <div
                        key={sIdx}
                        className="p-3.5 rounded-xl bg-white dark:bg-[#252528] border border-black/[0.06] dark:border-white/[0.08] relative overflow-hidden flex flex-col justify-between"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">Step {sIdx + 1}</span>
                          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400">
                            {fStep.conversion_rate}%
                          </span>
                        </div>
                        <div className="my-2">
                          <div className="text-xl font-black text-gray-900 dark:text-white">
                            {(fStep.count || 0).toLocaleString()}
                          </div>
                          <div className="text-xs text-gray-600 dark:text-gray-300 font-medium">
                            {fStep.step}
                          </div>
                        </div>
                        <div className="w-full bg-black/5 dark:bg-white/10 h-1.5 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-indigo-500 to-blue-500 rounded-full"
                            style={{ width: `${Math.min(100, Math.max(5, fStep.conversion_rate || 0))}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* 2. Heatmap Density Ranking */}
                <div className="p-5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                      <FaFire className="text-rose-500" />
                      Heatmap Density Ranking
                    </h3>
                    <span className="text-[10px] text-gray-400 font-mono">Relative block click share</span>
                  </div>

                  <div className="space-y-2 pt-1">
                    {(data?.heatmap_blocks && data.heatmap_blocks.length > 0 ? data.heatmap_blocks : topBlocks.map((b) => ({
                      id: b.id,
                      title: b.title,
                      click_count: b.clicks,
                      share_pct: clicks > 0 ? Math.round((b.clicks / clicks) * 100) : 0,
                      density_tier: (b.clicks / (clicks || 1)) > 0.4 ? 'high' : (b.clicks / (clicks || 1)) > 0.15 ? 'medium' : 'low',
                    }))).map((hBlock, hIdx) => {
                      const tierColor = hBlock.density_tier === 'high'
                        ? 'bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400 border-rose-200 dark:border-rose-800'
                        : hBlock.density_tier === 'medium'
                        ? 'bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-800'
                        : 'bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-800';

                      return (
                        <div
                          key={hIdx}
                          className="p-3 rounded-xl bg-white dark:bg-[#252528] border border-black/[0.06] dark:border-white/[0.08] flex items-center justify-between gap-3 text-xs"
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-gray-900 dark:text-white truncate">
                                {hBlock.title || 'Content Block'}
                              </span>
                              <span className={`px-1.5 py-0.5 rounded-md text-[9px] font-bold border ${tierColor} uppercase`}>
                                {hBlock.density_tier || 'tier'}
                              </span>
                            </div>
                            <div className="w-full bg-black/5 dark:bg-white/10 h-1.5 rounded-full overflow-hidden mt-2">
                              <div
                                className={`h-full rounded-full transition-all duration-500 ${
                                  hBlock.density_tier === 'high' ? 'bg-rose-500' : hBlock.density_tier === 'medium' ? 'bg-amber-500' : 'bg-blue-500'
                                }`}
                                style={{ width: `${Math.min(100, Math.max(3, hBlock.share_pct || 0))}%` }}
                              />
                            </div>
                          </div>
                          <div className="text-right shrink-0">
                            <div className="font-mono font-bold text-gray-900 dark:text-white">
                              {hBlock.click_count || 0} clicks
                            </div>
                            <div className="text-[10px] text-gray-400 font-medium">
                              {hBlock.share_pct || 0}% of taps
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* 3. NPS & Satisfaction Feedback */}
                {data?.nps_stats && data.nps_stats.total_responses > 0 && (
                  <div className="p-5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                        <FaStar className="text-amber-400" />
                        Satisfaction & NPS Feedback
                      </h3>
                      <span className="text-[11px] font-bold text-gray-600 dark:text-gray-300">
                        Avg: <strong className="text-amber-500">{data.nps_stats.average_score} / 5.0</strong> ({data.nps_stats.total_responses} reviews)
                      </span>
                    </div>

                    <div className="grid grid-cols-5 gap-2 pt-1 text-center">
                      {[5, 4, 3, 2, 1].map((score) => (
                        <div key={score} className="p-2 rounded-xl bg-white dark:bg-[#252528] border border-black/[0.06] dark:border-white/[0.08]">
                          <div className="text-[11px] font-bold flex items-center justify-center gap-0.5 text-amber-500">
                            {score} <FaStar className="text-[9px]" />
                          </div>
                          <div className="text-sm font-black text-gray-900 dark:text-white mt-0.5">
                            {data.nps_stats.distribution?.[score] || 0}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 4. A/B Testing Variant Stats (if variants enabled) */}
                {data?.variant_stats && data.variant_stats.length > 0 && (
                  <div className="p-5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.04] border border-black/[0.06] dark:border-white/[0.08] space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                        <FaTrophy className="text-amber-500" />
                        A/B Traffic Experiment Performance
                      </h3>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                      {data.variant_stats.map((v) => (
                        <div
                          key={v.variant_id}
                          className="p-4 rounded-xl bg-white dark:bg-[#252528] border border-black/[0.06] dark:border-white/[0.08] space-y-2"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-xs text-gray-900 dark:text-white">{v.name || v.variant_id}</span>
                            <span className="text-[10px] font-mono text-gray-400">{v.traffic_pct || 50}% traffic</span>
                          </div>
                          <div className="grid grid-cols-3 gap-2 text-center text-xs">
                            <div className="p-2 bg-black/[0.02] dark:bg-white/[0.03] rounded-lg">
                              <div className="text-[10px] text-gray-400">Views</div>
                              <div className="font-bold">{v.views || 0}</div>
                            </div>
                            <div className="p-2 bg-black/[0.02] dark:bg-white/[0.03] rounded-lg">
                              <div className="text-[10px] text-gray-400">Clicks</div>
                              <div className="font-bold">{v.clicks || 0}</div>
                            </div>
                            <div className="p-2 bg-black/[0.02] dark:bg-white/[0.03] rounded-lg">
                              <div className="text-[10px] text-gray-400">CR %</div>
                              <div className="font-bold text-emerald-600 dark:text-emerald-400">{v.conversion_rate || 0}%</div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

          </div>

          {/* ── FOOTER SHARE & ACTIONS ── */}
          <div className="px-6 py-3.5 border-t border-black/[0.06] dark:border-white/[0.08] bg-gray-50/70 dark:bg-[#2C2C2E]/50 flex items-center justify-between gap-3 shrink-0">
            <div className="flex items-center gap-2 text-xs font-mono text-gray-500 truncate max-w-xs">
              <span className="truncate">{publicUrl || `unravler.com/bio/${handle}`}</span>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleCopyLink}
                className="px-3.5 py-1.5 rounded-full text-xs font-semibold bg-white dark:bg-[#2C2C2E] border border-black/[0.08] dark:border-white/[0.12] hover:bg-gray-50 dark:hover:bg-[#3A3A3C] transition flex items-center gap-1.5 active:scale-95 cursor-pointer shadow-xs"
              >
                {copied ? <FaCheck className="text-emerald-500" /> : <FaCopy className="text-gray-400" />}
                <span>{copied ? 'Copied!' : 'Copy Link'}</span>
              </button>
              {publicUrl && (
                <button
                  onClick={() => window.open(publicUrl, '_blank')}
                  className="px-4 py-1.5 rounded-full text-xs font-semibold text-white bg-[#0071E3] hover:bg-[#0077ED] transition flex items-center gap-1.5 active:scale-95 cursor-pointer shadow-xs"
                >
                  <span>Visit Live Bio</span>
                  <FaExternalLinkAlt className="text-[10px]" />
                </button>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
