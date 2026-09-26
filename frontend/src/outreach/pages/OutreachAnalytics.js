import React, { useState, useEffect, useRef } from 'react';
import { toast } from 'sonner';
import {
  BarChart3,
  UserCheck,
  MessageSquare,
  Sparkles,
  Calendar,
  Filter,
  RefreshCw,
  PhoneCall,
  TrendingUp,
} from 'lucide-react';

export default function OutreachAnalytics() {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [timeframe, setTimeframe] = useState('30d');
  const [campaignId, setCampaignId] = useState('all');
  const [campaigns, setCampaigns] = useState([]);
  const [selectedMetric, setSelectedMetric] = useState('requests'); // 'requests' | 'messages'
  const [hoveredBar, setHoveredBar] = useState(null);
  const requestId = useRef(0);

  const fetchCampaigns = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/campaigns', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setCampaigns(data || []);
      } else {
        toast.error('Could not load campaigns for analytics');
      }
    } catch (err) {
      console.error('Failed to fetch campaigns for analytics:', err);
    }
  };

  const fetchAnalytics = async () => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    setLoadError('');
    try {
      const token = localStorage.getItem('token');
      const params = new URLSearchParams();
      if (timeframe) params.append('timeframe', timeframe);
      if (campaignId && campaignId !== 'all') params.append('campaign_id', campaignId);

      const res = await fetch(`/api/v1/outreach/analytics?${params.toString()}`, {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not load analytics');
      const data = await res.json();
      if (currentRequest === requestId.current) setAnalytics(data);
    } catch (err) {
      if (currentRequest === requestId.current) {
        setAnalytics(null);
        setLoadError(err.message || 'Could not load analytics');
        toast.error(err.message || 'Could not load analytics');
      }
    } finally {
      if (currentRequest === requestId.current) setLoading(false);
    }
  };

  useEffect(() => {
    fetchCampaigns();
  }, []);

  useEffect(() => {
    fetchAnalytics();
    return () => { requestId.current += 1; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeframe, campaignId]);

  const emptyKpis = {
    requests: { sent: 0, accepted: 0, acceptance_rate: 0 },
    messages: { sent: 0, replied: 0, reply_rate: 0 },
    engagement: { total_actions: 0, profile_visits: 0, post_engagements: 0 },
    pipeline: { total_leads: 0, in_campaign: 0, replied: 0, call_booked: 0 },
  };

  const kpis = analytics?.kpis || emptyKpis;

  const dailyChart = analytics?.daily_chart || [];
  const maxBarValue = Math.max(
    ...dailyChart.map((d) => Math.max(d.sent || 0, d.messages_sent || 0, d.accepted || 0, d.replied || 0)),
    10
  );
  // Round up to nearest multiple of 5 for clean Y-axis ticks
  const yMax = Math.ceil(maxBarValue / 5) * 5;
  const yTicks = [yMax, Math.round(yMax * 0.75), Math.round(yMax * 0.5), Math.round(yMax * 0.25), 0];

  if (loadError && !loading) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-[#fafafa] p-8 text-center">
        <p className="text-sm font-semibold text-gray-900">Analytics could not be loaded</p>
        <p className="text-xs text-gray-600">{loadError}</p>
        <button type="button" onClick={fetchAnalytics} className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white">Retry</button>
      </div>
    );
  }

  return (
    <div className="h-full max-h-full min-h-0 bg-[#fafafa] overflow-y-auto px-8 py-7 font-sans">
      {/* Notice Banner if No Account or No Activity */}
      {analytics && !analytics.has_connected_account && (
        <div className="mb-6 rounded-2xl border border-amber-200/80 bg-amber-50/70 p-4 text-xs text-amber-900 flex items-center justify-between shadow-2xs">
          <div className="flex items-center gap-2.5">
            <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-100 font-bold text-amber-700">
              !
            </span>
            <div>
              <p className="font-bold">No LinkedIn account connected</p>
              <p className="text-amber-700 text-[11px] mt-0.5">
                Connect a sender account in Settings to start launching campaigns and collecting live outreach analytics.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Top Header matching prosp_campaign_analytics.jpg */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-7">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-indigo-600/10 text-indigo-600 flex items-center justify-center">
              <BarChart3 className="w-4 h-4 stroke-[2.2]" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Analytics</h1>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">Monitor the results of your campaign</p>
        </div>

        {/* Global Filters */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 bg-white border border-gray-200/90 rounded-xl px-3 py-1.5 shadow-2xs">
            <Filter className="w-3.5 h-3.5 text-gray-400" />
            <select
              value={campaignId}
              onChange={(e) => setCampaignId(e.target.value)}
              className="text-xs font-medium text-gray-700 bg-transparent border-0 focus:ring-0 cursor-pointer"
            >
              <option value="all">All campaigns</option>
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5 bg-white border border-gray-200/90 rounded-xl px-3 py-1.5 shadow-2xs">
            <Calendar className="w-3.5 h-3.5 text-gray-400" />
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="text-xs font-medium text-gray-700 bg-transparent border-0 focus:ring-0 cursor-pointer"
            >
              <option value="7d">Last 7 days</option>
              <option value="14d">Last 14 days</option>
              <option value="30d">Last 30 days</option>
            </select>
          </div>

          <button
            onClick={fetchAnalytics}
            className="p-2 rounded-xl bg-white border border-gray-200 text-gray-500 hover:text-gray-800 hover:bg-gray-50 shadow-2xs transition-colors"
            title="Refresh analytics"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* KPI Cards Grid matching prosp_campaign_analytics.jpg */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        {/* Card 1: LinkedIn Requests */}
        <div
          onClick={() => setSelectedMetric('requests')}
          className={`cursor-pointer rounded-2xl p-5 border transition-all shadow-2xs ${
            selectedMetric === 'requests'
              ? 'bg-white border-indigo-500 ring-2 ring-indigo-500/20 shadow-md'
              : 'bg-white border-gray-200/90 hover:border-gray-300'
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
              <UserCheck className="w-4 h-4" />
            </div>
            <span className="text-xs font-semibold text-gray-700">Linkedin Requests</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-3xl font-extrabold text-gray-900 tracking-tight">
              {kpis.requests?.sent ?? 0}
            </span>
            <span className="text-[11px] font-semibold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-full">
              {kpis.requests?.accepted ?? 0} accepted
            </span>
          </div>
          <p className="text-[11px] text-gray-600 mt-2">
            Confirmed invitations sent in this period
          </p>
        </div>

        {/* Card 2: LinkedIn Messages */}
        <div
          onClick={() => setSelectedMetric('messages')}
          className={`cursor-pointer rounded-2xl p-5 border transition-all shadow-2xs ${
            selectedMetric === 'messages'
              ? 'bg-white border-indigo-500 ring-2 ring-indigo-500/20 shadow-md'
              : 'bg-white border-gray-200/90 hover:border-gray-300'
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center">
              <MessageSquare className="w-4 h-4" />
            </div>
            <span className="text-xs font-semibold text-gray-700">Linkedin Messages</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-3xl font-extrabold text-gray-900 tracking-tight">
              {kpis.messages?.sent ?? 0}
            </span>
            <span className="text-[11px] font-semibold text-purple-700 bg-purple-50 px-2 py-0.5 rounded-full">
              {kpis.messages?.replied ?? 0} replies
            </span>
          </div>
          <p className="text-[11px] text-gray-600 mt-2">
            Confirmed direct messages sent in this period
          </p>
        </div>

        {/* Card 3: LinkedIn Engagement */}
        <div className="rounded-2xl p-5 border bg-white border-gray-200/90 shadow-2xs">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-xl bg-pink-50 text-pink-600 flex items-center justify-center">
              <Sparkles className="w-4 h-4" />
            </div>
            <span className="text-xs font-semibold text-gray-700">Linkedin Engagement</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-3xl font-extrabold text-gray-900 tracking-tight">
              {kpis.engagement?.total_actions ?? 0}
            </span>
            <span className="text-[11px] font-semibold text-pink-700 bg-pink-50 px-2 py-0.5 rounded-full">
              Pre-warming
            </span>
          </div>
          <p className="text-[11px] text-gray-600 mt-2">
            {kpis.engagement?.profile_visits ?? 0} profile views · {kpis.engagement?.post_engagements ?? 0} post actions
          </p>
        </div>
      </div>

      {/* CRM Pipeline Conversion Ribbon */}
      <div className="bg-white rounded-2xl border border-gray-200/90 p-5 mb-6 shadow-2xs">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-indigo-600" />
            <h2 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
              Pipeline Stage Conversion
            </h2>
          </div>
          <span className="text-xs text-gray-600">
            Total active prospects: <strong className="text-gray-900">{kpis.pipeline?.total_leads ?? 0}</strong>
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-gray-50/80 rounded-xl p-3 border border-gray-200/60">
            <span className="text-[10px] font-bold uppercase tracking-wider text-gray-600">Total Leads</span>
            <p className="text-lg font-bold text-gray-900 mt-1">{kpis.pipeline?.total_leads ?? 0}</p>
          </div>
          <div className="bg-amber-50/50 rounded-xl p-3 border border-amber-200/60">
            <span className="text-[10px] font-bold uppercase tracking-wider text-amber-700">In Campaign</span>
            <p className="text-lg font-bold text-amber-900 mt-1">{kpis.pipeline?.in_campaign ?? 0}</p>
          </div>
          <div className="bg-purple-50/50 rounded-xl p-3 border border-purple-200/60">
            <span className="text-[10px] font-bold uppercase tracking-wider text-purple-700">Replied</span>
            <p className="text-lg font-bold text-purple-900 mt-1">{kpis.pipeline?.replied ?? 0}</p>
          </div>
          <div className="bg-emerald-50/50 rounded-xl p-3 border border-emerald-200/60 flex items-center justify-between">
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700">Calls Booked</span>
              <p className="text-lg font-bold text-emerald-900 mt-1">{kpis.pipeline?.call_booked ?? 0}</p>
            </div>
            <PhoneCall className="w-5 h-5 text-emerald-600" />
          </div>
        </div>
      </div>

      {/* Main Bar Chart Panel matching prosp_campaign_analytics.jpg */}
      <div className="bg-white rounded-2xl border border-gray-200/90 p-6 shadow-2xs">
        {/* Chart Legend Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6 pb-4 border-b border-gray-100">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="w-3.5 h-3.5 rounded bg-indigo-600 inline-block shadow-2xs" />
              <span className="text-xs font-semibold text-gray-700">
                Sent: <strong className="text-gray-900">{selectedMetric === 'requests' ? kpis.requests?.sent ?? 0 : kpis.messages?.sent ?? 0}</strong>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3.5 h-3.5 rounded bg-sky-400 inline-block shadow-2xs" />
              <span className="text-xs font-semibold text-gray-700">
                {selectedMetric === 'requests' ? 'Accepted' : 'Replied'}: <strong className="text-gray-900">{selectedMetric === 'requests' ? kpis.requests?.accepted ?? 0 : kpis.messages?.replied ?? 0}</strong>
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1.5 text-xs text-gray-600 font-medium">
            <span>Recorded activity in the selected period</span>
          </div>
        </div>

        {/* Bar Chart Canvas with SVG */}
        <div className="relative pt-2">
          {/* Y Axis Grid Lines */}
          <div className="relative h-64 w-full">
            <div className="absolute inset-0 flex flex-col justify-between pointer-events-none">
              {yTicks.map((tick, idx) => (
                <div key={idx} className="flex items-center w-full">
                  <span className="w-7 text-[10px] font-mono text-gray-400 text-right pr-2">
                    {tick}
                  </span>
                  <div className="flex-1 border-b border-gray-100" />
                </div>
              ))}
            </div>

            {/* Bars Container */}
            <div className="absolute inset-y-0 left-9 right-2 flex items-end justify-between gap-1 sm:gap-2 pb-1">
              {dailyChart.map((d, index) => {
                const sentCount = selectedMetric === 'requests' ? d.sent || 0 : d.messages_sent || 0;
                const outcomeCount = selectedMetric === 'requests' ? d.accepted || 0 : d.replied || 0;
                const sentH = Math.min(Math.round((sentCount / yMax) * 100), 100);
                const outcomeH = Math.min(Math.round((outcomeCount / yMax) * 100), 100);

                return (
                  <div
                    key={index}
                    className="flex-1 flex flex-col items-center h-full justify-end group relative cursor-pointer"
                    onMouseEnter={() => setHoveredBar(d)}
                    onMouseLeave={() => setHoveredBar(null)}
                  >
                    {/* Tooltip */}
                    {hoveredBar?.date === d.date && (
                      <div className="absolute -top-12 z-20 bg-gray-900 text-white rounded-lg px-2.5 py-1.5 text-[10px] shadow-lg pointer-events-none whitespace-nowrap">
                        <p className="font-bold">{d.date}</p>
                        <p className="text-gray-300">
                          Sent: <strong className="text-white">{sentCount}</strong> · {selectedMetric === 'requests' ? 'Accepted' : 'Replied'}:{' '}
                          <strong className="text-white">{outcomeCount}</strong>
                        </p>
                      </div>
                    )}

                    {/* Paired Bar Columns */}
                    <div className="w-full flex items-end justify-center gap-1 h-full pb-1">
                      {/* Sent bar */}
                      <div
                        style={{ height: `${sentH}%` }}
                        className="w-1/2 max-w-[16px] rounded-t-sm sm:rounded-t-md bg-indigo-600 transition-all duration-300 group-hover:bg-indigo-700"
                      />
                      {/* Accepted bar */}
                      <div
                        style={{ height: `${outcomeH}%` }}
                        className="w-1/2 max-w-[16px] rounded-t-sm sm:rounded-t-md bg-sky-400 transition-all duration-300 group-hover:bg-sky-500"
                      />
                    </div>

                    {/* Date label */}
                    <span className="text-[9px] font-medium text-gray-600 mt-2 truncate max-w-full text-center">
                      {d.date}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
