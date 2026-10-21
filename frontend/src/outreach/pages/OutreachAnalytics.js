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
  Mail,
  Download,
  User,
} from 'lucide-react';

export default function OutreachAnalytics() {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [timeframe, setTimeframe] = useState('30d');
  const [campaignId, setCampaignId] = useState('all');
  const [campaigns, setCampaigns] = useState([]);
  const [senderAccountId, setSenderAccountId] = useState('all');
  const [senders, setSenders] = useState([]);
  const [exporting, setExporting] = useState(false);
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

  const fetchSenders = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/accounts', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setSenders(data || []);
      }
    } catch (err) {
      console.error('Failed to fetch senders for analytics:', err);
    }
  };

  const handleExportCsv = async () => {
    try {
      setExporting(true);
      const token = localStorage.getItem('token');
      const params = new URLSearchParams();
      if (timeframe) params.append('timeframe', timeframe);
      if (campaignId && campaignId !== 'all') params.append('campaign_id', campaignId);
      if (senderAccountId && senderAccountId !== 'all') params.append('sender_account_id', senderAccountId);

      const res = await fetch(`/api/v1/outreach/analytics/export?${params.toString()}`, {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (!res.ok) throw new Error('Could not export analytics CSV');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `outreach-analytics-${timeframe}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success('Analytics CSV exported');
    } catch (err) {
      toast.error(err.message || 'Could not export analytics');
    } finally {
      setExporting(false);
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
      if (senderAccountId && senderAccountId !== 'all') params.append('sender_account_id', senderAccountId);

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
    fetchSenders();
  }, []);

  useEffect(() => {
    fetchAnalytics();
    return () => { requestId.current += 1; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeframe, campaignId, senderAccountId]);

  const emptyKpis = {
    requests: { sent: 0, accepted: 0, acceptance_rate: 0 },
    messages: { sent: 0, replied: 0, reply_rate: 0 },
    engagement: { total_actions: 0, profile_visits: 0, post_engagements: 0 },
    pipeline: { total_leads: 0, in_campaign: 0, replied: 0, call_booked: 0 },
  };

  const kpis = analytics?.kpis || emptyKpis;
  const requestCohort = kpis.requests?.cohort || {};
  const messageCohort = kpis.messages?.cohort || {};
  const linkedin = analytics?.linkedin_cohorts;
  const cohortCount = (cohort, key) => loading ? 'Loading…' : (cohort[key] ?? 'Not available');
  const cohortRate = (cohort, key) => !loading && linkedin?.status === 'recorded' && Number.isFinite(cohort[key])
    ? ` (${cohort[key]}%)` : '';
  const cohortDescription = (cohort) => {
    if (loading) return 'Loading cohort observations…';
    if (!linkedin || linkedin.status === 'unavailable') return 'Cohort observations unavailable';
    if (linkedin.status === 'partial') return 'Known records only · rates unavailable';
    return `${cohort.denominator ?? 'Not available'} original sends · ${linkedin.attribution_window_days}-day observation window`;
  };
  const email = kpis.email;
  const emailCount = (key) => loading ? 'Loading…' : (email?.[key] ?? 'Not available');

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
        <div className="flex flex-wrap items-center gap-3">
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
            <User className="w-3.5 h-3.5 text-gray-400" />
            <select
              aria-label="Filter by sender"
              value={senderAccountId}
              onChange={(e) => setSenderAccountId(e.target.value)}
              className="text-xs font-medium text-gray-700 bg-transparent border-0 focus:ring-0 cursor-pointer"
            >
              <option value="all">All senders</option>
              {senders.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.account_name || s.name || s.id}
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
            type="button"
            onClick={handleExportCsv}
            disabled={exporting}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-gray-200 text-gray-700 hover:text-gray-900 hover:bg-gray-50 shadow-2xs text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer"
            title="Export analytics CSV"
          >
            <Download className={`w-3.5 h-3.5 ${exporting ? 'animate-bounce' : ''}`} />
            <span>Export CSV</span>
          </button>

          <button
            type="button"
            onClick={fetchAnalytics}
            className="p-2 rounded-xl bg-white border border-gray-200 text-gray-500 hover:text-gray-800 hover:bg-gray-50 shadow-2xs transition-colors cursor-pointer"
            title="Refresh analytics"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* KPI Cards Grid matching prosp_campaign_analytics.jpg */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
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
              {loading ? 'Loading…' : (kpis.requests?.period_activity?.sent ?? 'Not available')}
            </span>
            <span className="text-[11px] font-semibold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-full">
              {cohortCount(requestCohort, 'accepted')} associated acceptances
              {cohortRate(requestCohort, 'acceptance_rate')}
            </span>
          </div>
          <p className="text-[11px] text-gray-500 mt-1">Recorded activity in period</p>
          <p className="text-[11px] text-gray-600 mt-2">
            {cohortDescription(requestCohort)}
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
              {loading ? 'Loading…' : (kpis.messages?.period_activity?.sent ?? 'Not available')}
            </span>
            <span className="text-[11px] font-semibold text-purple-700 bg-purple-50 px-2 py-0.5 rounded-full">
              {cohortCount(messageCohort, 'replied')} associated replies
              {cohortRate(messageCohort, 'reply_rate')}
            </span>
          </div>
          <p className="text-[11px] text-gray-500 mt-1">Recorded activity in period</p>
          <p className="text-[11px] text-gray-600 mt-2">
            {cohortDescription(messageCohort)}
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
            {kpis.engagement?.profile_visits ?? 0} views · {kpis.engagement?.post_engagements ?? 0} actions
          </p>
        </div>

        {/* Card 4: Stored email outcomes; acceptance never implies delivery. */}
        <div className="rounded-2xl p-5 border bg-white border-gray-200/90 shadow-2xs">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-xl bg-sky-50 text-sky-600 flex items-center justify-center">
              <Mail className="w-4 h-4" />
            </div>
            <span className="text-xs font-semibold text-gray-700">Email Outcomes</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-3xl font-extrabold text-gray-900 tracking-tight">
              {emailCount('provider_accepted')}
            </span>
            <span className="text-[11px] font-semibold text-sky-700 bg-sky-50 px-2 py-0.5 rounded-full">
              Delivery unavailable
            </span>
          </div>
          <p className="text-[11px] text-gray-600 mt-2">
            Provider acceptances recorded in the selected UTC period
          </p>
          <p className="text-[11px] text-gray-600 mt-2">
            {emailCount('bounced')} recorded reference bounces · {emailCount('possible_bounced')} possible bounces
          </p>
          <p className="text-[11px] text-gray-600 mt-2">
            {emailCount('delivery_unknown')} accepted emails with unknown delivery
          </p>
          {!loading && email?.human_reported > 0 && <p className="text-[11px] text-gray-600 mt-2">
            {email.human_reported} human assertions kept separate
          </p>}
          {!loading && email?.pending_or_unknown_operations > 0 && <p className="text-[11px] text-gray-600 mt-2">
            {email.pending_or_unknown_operations} pending or unknown operations created in this period
          </p>}
          {!loading && email?.evidence_status === 'partial' && <p role="status" className="text-[11px] text-amber-800 mt-2">
            Some records lack usable evidence. Known counts are not a complete history.
          </p>}
          {!loading && (!email || email.evidence_status === 'unavailable') && <p role="status" className="text-[11px] text-amber-800 mt-2">
            Email evidence is unavailable. Retry or narrow the filters.
          </p>}
          <p className="text-[10px] text-gray-500 mt-2">
            Bounce classifications come from stored records. Delivery and submission coverage are unavailable.
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
      <p className="mb-4 text-xs text-gray-600">
        Activity counts cover updates in the selected UTC period. Cohort rates associate original recorded sends with
        LinkedIn observations during the next {linkedin?.attribution_window_days ?? 30} days, up to the report time.
        Recent observation windows are still open. Recorded association does not establish causation.
      </p>
      <div className="bg-white rounded-2xl border border-gray-200/90 p-6 shadow-2xs">
        {/* Chart Legend Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6 pb-4 border-b border-gray-100">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="w-3.5 h-3.5 rounded bg-indigo-600 inline-block shadow-2xs" />
              <span className="text-xs font-semibold text-gray-700">
                Sent activity: <strong className="text-gray-900">{selectedMetric === 'requests' ? kpis.requests?.period_activity?.sent ?? 'Not available' : kpis.messages?.period_activity?.sent ?? 'Not available'}</strong>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3.5 h-3.5 rounded bg-sky-400 inline-block shadow-2xs" />
              <span className="text-xs font-semibold text-gray-700">
                {selectedMetric === 'requests' ? 'Acceptance observations' : 'Reply flags'}: <strong className="text-gray-900">{selectedMetric === 'requests' ? kpis.requests?.period_activity?.accepted ?? 'Not available' : kpis.messages?.period_activity?.replied ?? 'Not available'}</strong>
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

      {/* Sequence Step Conversion Funnel */}
      {analytics?.sequence_funnel && (
        <div className="bg-white rounded-2xl border border-gray-200/90 p-6 mt-6 shadow-2xs">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-indigo-600" />
              <h2 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                Sequence Step Conversion Funnel
              </h2>
            </div>
            <span className="text-[11px] text-gray-500">Step-by-step progression in period</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {[
              { label: 'Total Prospects', val: analytics.sequence_funnel.total_leads ?? 0, sub: 'Enrolled' },
              { label: 'Profile Views', val: analytics.sequence_funnel.profile_visits ?? 0, sub: 'Auto-viewed' },
              { label: 'Invites Sent', val: analytics.sequence_funnel.requests_sent ?? 0, sub: 'Connection reqs' },
              {
                label: 'Connected',
                val: analytics.sequence_funnel.requests_accepted ?? 0,
                sub: Number.isFinite(analytics.sequence_funnel.acceptance_rate)
                  ? `${analytics.sequence_funnel.acceptance_rate}% cohort rate`
                  : 'Accepted',
              },
              { label: 'Messages Sent', val: analytics.sequence_funnel.messages_sent ?? 0, sub: 'Direct messages' },
              {
                label: 'Replied',
                val: analytics.sequence_funnel.messages_replied ?? 0,
                sub: Number.isFinite(analytics.sequence_funnel.reply_rate)
                  ? `${analytics.sequence_funnel.reply_rate}% cohort rate`
                  : 'Prospect replies',
              },
            ].map((stage, idx) => (
              <div key={idx} className="rounded-xl border border-gray-100 bg-gray-50/70 p-3.5">
                <p className="text-[10px] font-bold uppercase tracking-wider text-gray-500">{stage.label}</p>
                <p className="text-xl font-extrabold text-gray-900 mt-1">{stage.val}</p>
                <p className="text-[10px] text-indigo-600 font-medium mt-0.5">{stage.sub}</p>
              </div>
            ))}
          </div>
          {analytics.sequence_funnel.variants_breakdown && Object.keys(analytics.sequence_funnel.variants_breakdown).length > 0 && (
            <div className="mt-4 pt-3 border-t border-gray-100 flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-gray-500">A/B Variants Sent:</span>
              {Object.values(analytics.sequence_funnel.variants_breakdown).map((vb) => (
                <span
                  key={vb.variant_id}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-violet-50 border border-violet-200 px-2.5 py-1 text-xs font-semibold text-violet-800"
                >
                  <span>Variant {vb.variant_id}:</span>
                  <strong>{vb.total_sent} sent</strong>
                  <span className="text-[10px] text-violet-600">({vb.requests_sent} invites · {vb.messages_sent} msgs)</span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Team & Sender Performance + Daily Activity Control Quota Table */}
      {Array.isArray(analytics?.team_performance) && analytics.team_performance.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-200/90 p-6 mt-6 shadow-2xs">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
            <div className="flex items-center gap-2">
              <User className="w-4 h-4 text-indigo-600" />
              <h2 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                Team & Sender Account Performance
              </h2>
            </div>
            <span className="text-[11px] text-gray-500">
              Daily usage vs. Activity Control cap & period conversion stats
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-gray-100 text-[10px] font-bold uppercase tracking-wider text-gray-500">
                  <th className="py-2.5 pr-4">Sender Account</th>
                  <th className="py-2.5 px-3">Safety / Activity Control</th>
                  <th className="py-2.5 px-3">Today&apos;s Invites</th>
                  <th className="py-2.5 px-3">Today&apos;s Messages</th>
                  <th className="py-2.5 px-3">Period Invites (Acc %)</th>
                  <th className="py-2.5 pl-3 text-right">Period Messages (Reply %)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {analytics.team_performance.map((member) => {
                  const invUsed = member.daily_usage_today?.connection_invites ?? 0;
                  const invMax = member.effective_limits?.connection_invites ?? 20;
                  const msgUsed = member.daily_usage_today?.messages ?? 0;
                  const msgMax = member.effective_limits?.messages ?? 20;
                  const pStats = member.period_stats || {};
                  return (
                    <tr
                      key={member.account_id}
                      onClick={() => setSenderAccountId(member.account_id === senderAccountId ? 'all' : member.account_id)}
                      className="hover:bg-gray-50/80 cursor-pointer transition-colors"
                    >
                      <td className="py-3 pr-4">
                        <div className="font-bold text-gray-900">{member.account_name}</div>
                        <div className="text-[11px] text-gray-400">
                          {member.vanity_name ? `@${member.vanity_name} · ` : ''}
                          {member.premium_product === 'sales_navigator' ? 'Sales Navigator' : member.premium_product === 'recruiter' ? 'Recruiter' : 'Standard LinkedIn'}
                        </div>
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex flex-wrap items-center gap-1">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                            member.activity_control_enabled
                              ? 'bg-emerald-50 text-emerald-700'
                              : 'bg-gray-100 text-gray-600'
                          }`}>
                            {member.activity_control_enabled ? `Activity Control · Lvl ${member.warmup_level || 1}` : `Static Cap · Lvl ${member.warmup_level || 1}`}
                          </span>
                          {member.weekly_invite_limit_reached && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-800 border border-amber-200">
                              Weekly Invite Cap (Messages Active)
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-3">
                        <span className="font-semibold text-gray-900">{invUsed}</span>
                        <span className="text-gray-400"> / {invMax}</span>
                      </td>
                      <td className="py-3 px-3">
                        <span className="font-semibold text-gray-900">{msgUsed}</span>
                        <span className="text-gray-400"> / {msgMax}</span>
                      </td>
                      <td className="py-3 px-3">
                        <span className="font-semibold text-gray-900">{pStats.requests_sent ?? 0}</span>
                        <span className="text-gray-500"> sent · {pStats.requests_accepted ?? 0} acc</span>
                        {Number.isFinite(pStats.acceptance_rate) && (
                          <span className="ml-1 text-[10px] font-semibold text-indigo-600">
                            ({pStats.acceptance_rate}%)
                          </span>
                        )}
                      </td>
                      <td className="py-3 pl-3 text-right">
                        <span className="font-semibold text-gray-900">{pStats.messages_sent ?? 0}</span>
                        <span className="text-gray-500"> sent · {pStats.messages_replied ?? 0} rep</span>
                        {Number.isFinite(pStats.reply_rate) && (
                          <span className="ml-1 text-[10px] font-semibold text-purple-600">
                            ({pStats.reply_rate}%)
                          </span>
                        )}
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
  );
}
