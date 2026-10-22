import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Activity,
  AlertTriangle,
  Calendar,
  CheckCircle2,
  Clock,
  CreditCard,
  ExternalLink,
  Mic,
  RefreshCw,
  Search,
  Shield,
  Users,
} from 'lucide-react';

const STATUS_BADGE = {
  active: {
    label: 'Active Paid',
    className: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  },
  expiring_soon: {
    label: 'Expiring ≤ 7d',
    className: 'bg-amber-50 text-amber-700 border-amber-200',
  },
  cancel_scheduled: {
    label: 'Cancels at Period End',
    className: 'bg-orange-50 text-orange-700 border-orange-200',
  },
  pending_quote: {
    label: 'Quote Requested',
    className: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  },
  expired: {
    label: 'Expired',
    className: 'bg-red-50 text-red-700 border-red-200',
  },
  unpaid: {
    label: 'Unpaid / Draft',
    className: 'bg-gray-100 text-gray-700 border-gray-200',
  },
};

function formatDate(iso) {
  if (!iso) return '—';
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return '—';
  return dt.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function formatDateTime(iso) {
  if (!iso) return '—';
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return '—';
  return dt.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function OutreachSubscriptionMonitor() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  const fetchMonitor = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/billing/subscription-monitor', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.detail || 'Could not load subscription & activity monitor.');
      }
      const payload = await res.json();
      setData(payload);
    } catch (err) {
      setError(err.message || 'Could not load subscription & activity monitor.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMonitor();
  }, [fetchMonitor]);

  const ws = data?.workspace || null;
  const platform = data?.platform_overview || null;
  const posthogInfo = data?.posthog || {};
  const elevenlabsInfo = data?.elevenlabs || {};

  const filteredSubscribers = useMemo(() => {
    if (!platform?.subscribers) return [];
    const q = searchQuery.trim().toLowerCase();
    return platform.subscribers.filter((sub) => {
      if (statusFilter !== 'all' && sub.lifecycle_state !== statusFilter) {
        return false;
      }
      if (!q) return true;
      return (
        (sub.workspace_name || '').toLowerCase().includes(q) ||
        (sub.owner_email || '').toLowerCase().includes(q) ||
        (sub.owner_name || '').toLowerCase().includes(q) ||
        (sub.workspace_id || '').toLowerCase().includes(q) ||
        (sub.country_code || '').toLowerCase().includes(q)
      );
    });
  }, [platform, statusFilter, searchQuery]);

  if (loading && !data) {
    return (
      <div
        className="bg-white rounded-2xl border border-gray-200/80 p-8 text-center text-sm text-gray-500"
        data-testid="subscription-monitor-loading"
      >
        Loading live subscriptions, active users, and voice quota telemetry…
      </div>
    );
  }

  if (error && !data) {
    return (
      <div
        className="bg-white rounded-2xl border border-red-200 p-6 space-y-3"
        data-testid="subscription-monitor-error"
      >
        <div className="flex items-center gap-2 text-red-700 font-semibold text-sm">
          <AlertTriangle className="w-4 h-4" />
          <span>Subscription monitor unavailable</span>
        </div>
        <p className="text-xs text-gray-600">{error}</p>
        <button
          onClick={fetchMonitor}
          className="px-3.5 py-2 bg-gray-900 text-white rounded-xl text-xs font-semibold hover:bg-gray-800"
        >
          Retry monitor
        </button>
      </div>
    );
  }

  const wsBadge = STATUS_BADGE[ws?.lifecycle_state] || STATUS_BADGE.unpaid;

  return (
    <div className="space-y-6" data-testid="subscription-monitor-view">
      {/* Header & Integration Telemetry Bar */}
      <div className="bg-white rounded-2xl border border-gray-200/80 p-6 shadow-2xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
              <Activity className="w-4 h-4 text-indigo-600" />
              Subscriptions, Active Users & Quota Monitor
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Live MongoDB entitlement state, subscription expiry countdowns, active users, and ElevenLabs daily voice quotas.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {data?.generated_at && (
              <span className="text-[11px] text-gray-400">
                Updated {formatDateTime(data.generated_at)}
              </span>
            )}
            <button
              onClick={fetchMonitor}
              disabled={loading}
              data-testid="refresh-subscription-monitor-btn"
              className="px-3 py-1.5 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 text-xs font-semibold text-gray-700 flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>

        {/* PostHog & ElevenLabs Status Strip */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t border-gray-100">
          <div className="flex items-center justify-between p-3 rounded-xl bg-gray-50/80 border border-gray-200/60">
            <div className="flex items-center gap-2.5">
              <div
                className={`w-2 h-2 rounded-full ${
                  posthogInfo.configured ? 'bg-emerald-500' : 'bg-amber-500'
                }`}
              />
              <div>
                <p className="text-xs font-semibold text-gray-900">PostHog Product Analytics</p>
                <p className="text-[11px] text-gray-500">
                  {posthogInfo.configured
                    ? `Connected (${posthogInfo.host}) — syncing user plan, seats & expiry`
                    : 'Free tier ready — set REACT_APP_POSTHOG_KEY in .env to enable live session replay'}
                </p>
              </div>
            </div>
            <a
              href={posthogInfo.host || 'https://us.posthog.com'}
              target="_blank"
              rel="noreferrer"
              className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-700 flex items-center gap-1 shrink-0"
            >
              PostHog <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          <div className="flex items-center justify-between p-3 rounded-xl bg-gray-50/80 border border-gray-200/60">
            <div className="flex items-center gap-2.5">
              <div
                className={`w-2 h-2 rounded-full ${
                  elevenlabsInfo.configured ? 'bg-emerald-500' : 'bg-amber-500'
                }`}
              />
              <div>
                <p className="text-xs font-semibold text-gray-900">
                  ElevenLabs Voice Engine ({elevenlabsInfo.model_id || 'eleven_turbo_v2_5'})
                </p>
                <p className="text-[11px] text-gray-500">
                  {elevenlabsInfo.configured ? 'API Key Active' : 'API Key Not Set'} · Studio:{' '}
                  {elevenlabsInfo.voice_studio_enabled ? 'ON' : 'OFF'} · Cap:{' '}
                  {elevenlabsInfo.daily_clips_per_workspace || 20} clips /{' '}
                  {(elevenlabsInfo.daily_chars_per_workspace || 20000).toLocaleString()} chars per day
                </p>
              </div>
            </div>
            <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-100">
              0.5x credits/char
            </span>
          </div>
        </div>
      </div>

      {/* Platform-Wide Operator Overview (Only visible for platform admin/owner/operator) */}
      {platform && (
        <div
          className="bg-white rounded-2xl border border-indigo-200/80 p-6 shadow-2xs space-y-5"
          data-testid="platform-operator-overview"
        >
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-indigo-50 text-indigo-700 border border-indigo-200 mb-1">
                Platform Operator View
              </span>
              <h3 className="text-base font-bold text-gray-900">
                All Workspaces, Active Users & Subscriptions
              </h3>
            </div>
            <div className="text-right">
              <p className="text-xs text-gray-500">Active Pilot MRR</p>
              <p className="text-lg font-extrabold text-emerald-700" data-testid="platform-mrr-usd">
                ${platform.kpis?.mrr_usd || 0}/mo
              </p>
            </div>
          </div>

          {/* Platform KPIs Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="p-3.5 rounded-xl bg-gray-50 border border-gray-200/70">
              <p className="text-[11px] text-gray-500 font-medium">Active Users (24h / 7d)</p>
              <p className="text-base font-bold text-gray-900 mt-1" data-testid="platform-active-users">
                {platform.kpis?.active_users_24h ?? 0} / {platform.kpis?.active_users_7d ?? 0}
              </p>
              <p className="text-[10px] text-gray-400 mt-0.5">
                of {platform.kpis?.total_users ?? 0} total users
              </p>
            </div>

            <div className="p-3.5 rounded-xl bg-emerald-50/50 border border-emerald-200/70">
              <p className="text-[11px] text-emerald-700 font-medium">Active Paid Plans</p>
              <p className="text-base font-bold text-emerald-900 mt-1" data-testid="platform-active-paid">
                {platform.kpis?.active_paid_workspaces ?? 0}
              </p>
              <p className="text-[10px] text-emerald-600 mt-0.5">
                {platform.kpis?.total_granted_seats ?? 0} paid sender seats
              </p>
            </div>

            <div className="p-3.5 rounded-xl bg-amber-50/50 border border-amber-200/70">
              <p className="text-[11px] text-amber-700 font-medium">Expiring ≤ 7 Days</p>
              <p className="text-base font-bold text-amber-900 mt-1" data-testid="platform-expiring-soon">
                {platform.kpis?.expiring_soon_workspaces ?? 0}
              </p>
              <p className="text-[10px] text-amber-600 mt-0.5">
                {platform.kpis?.expired_workspaces ?? 0} already expired
              </p>
            </div>

            <div className="p-3.5 rounded-xl bg-indigo-50/50 border border-indigo-200/70">
              <p className="text-[11px] text-indigo-700 font-medium">Pending Quotes</p>
              <p className="text-base font-bold text-indigo-900 mt-1">
                {platform.kpis?.pending_quote_workspaces ?? 0}
              </p>
              <p className="text-[10px] text-indigo-600 mt-0.5">
                awaiting invoice & IP
              </p>
            </div>

            <div className="p-3.5 rounded-xl bg-gray-50 border border-gray-200/70">
              <p className="text-[11px] text-gray-500 font-medium">Connected Senders</p>
              <p className="text-base font-bold text-gray-900 mt-1">
                {platform.kpis?.total_connected_senders ?? 0}
              </p>
              <p className="text-[10px] text-gray-400 mt-0.5">
                across {platform.kpis?.total_workspaces ?? 0} workspaces
              </p>
            </div>

            <div className="p-3.5 rounded-xl bg-purple-50/50 border border-purple-200/70">
              <p className="text-[11px] text-purple-700 font-medium">Voice Used Today</p>
              <p className="text-base font-bold text-purple-900 mt-1">
                {platform.kpis?.voice_clips_today ?? 0} clips
              </p>
              <p className="text-[10px] text-purple-600 mt-0.5">
                {(platform.kpis?.voice_chars_today ?? 0).toLocaleString()} chars today
              </p>
            </div>
          </div>

          {/* Filter & Search Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
            <div className="flex flex-wrap items-center gap-1.5">
              {[
                { id: 'all', label: 'All Workspaces' },
                { id: 'active', label: 'Active Paid' },
                { id: 'expiring_soon', label: 'Expiring ≤ 7d' },
                { id: 'pending_quote', label: 'Pending Quote' },
                { id: 'expired', label: 'Expired' },
                { id: 'unpaid', label: 'Unpaid' },
              ].map((pill) => (
                <button
                  key={pill.id}
                  onClick={() => setStatusFilter(pill.id)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                    statusFilter === pill.id
                      ? 'bg-gray-900 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200/70'
                  }`}
                >
                  {pill.label}
                </button>
              ))}
            </div>

            <div className="relative w-full sm:w-64">
              <Search className="w-3.5 h-3.5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search email, workspace, country…"
                className="w-full pl-8 pr-3 py-1.5 rounded-xl border border-gray-200 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>

          {/* Subscribers Table */}
          <div className="overflow-x-auto border border-gray-200/80 rounded-xl">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-gray-50/80 border-b border-gray-200/80 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                  <th className="py-2.5 px-3.5">Workspace / Customer</th>
                  <th className="py-2.5 px-3.5">Subscription Status</th>
                  <th className="py-2.5 px-3.5">Seats & Senders</th>
                  <th className="py-2.5 px-3.5">Subscription Ends</th>
                  <th className="py-2.5 px-3.5">Voice Today</th>
                  <th className="py-2.5 px-3.5">Last Active</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 text-xs">
                {filteredSubscribers.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-6 text-center text-gray-400">
                      No workspaces match the current filter.
                    </td>
                  </tr>
                ) : (
                  filteredSubscribers.map((sub) => {
                    const badge = STATUS_BADGE[sub.lifecycle_state] || STATUS_BADGE.unpaid;
                    return (
                      <tr key={sub.workspace_id} className="hover:bg-gray-50/60">
                        <td className="py-3 px-3.5">
                          <p className="font-semibold text-gray-900">{sub.workspace_name}</p>
                          <p className="text-[11px] text-gray-500">
                            {sub.owner_email || sub.billing_email || sub.workspace_id}
                            {sub.country_code ? ` · ${sub.country_code}` : ''}
                          </p>
                        </td>
                        <td className="py-3 px-3.5">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border ${badge.className}`}
                          >
                            {badge.label}
                          </span>
                          <p className="text-[11px] text-gray-500 mt-0.5">{sub.plan_label}</p>
                        </td>
                        <td className="py-3 px-3.5">
                          <p className="font-semibold text-gray-900">
                            {sub.connected_senders_count} / {sub.seats_granted} seats
                          </p>
                          <p className="text-[11px] text-gray-500">
                            {sub.active_campaigns_count} active{' '}
                            {sub.active_campaigns_count === 1 ? 'campaign' : 'campaigns'}
                          </p>
                        </td>
                        <td className="py-3 px-3.5">
                          {sub.paid_through ? (
                            <>
                              <p className="font-semibold text-gray-900">
                                {formatDate(sub.paid_through)}
                              </p>
                              <p
                                className={`text-[11px] font-medium ${
                                  sub.days_remaining === 0
                                    ? 'text-red-600'
                                    : sub.days_remaining <= 7
                                    ? 'text-amber-600'
                                    : 'text-emerald-600'
                                }`}
                              >
                                {sub.days_remaining === 0
                                  ? 'Expired'
                                  : `${sub.days_remaining}d left (${sub.hours_remaining}h)`}
                              </p>
                            </>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </td>
                        <td className="py-3 px-3.5">
                          <p className="font-medium text-gray-900">
                            {sub.voice_usage?.today_clips_used ?? 0} /{' '}
                            {sub.voice_usage?.daily_clips_limit ?? 20} clips
                          </p>
                          <p className="text-[11px] text-gray-500">
                            {(sub.voice_usage?.today_chars_used ?? 0).toLocaleString()} chars
                          </p>
                        </td>
                        <td className="py-3 px-3.5 text-gray-500">
                          {formatDateTime(sub.last_active_at)}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Current Workspace Subscription, Expiry & Quota Cards */}
      {ws && (
        <div className="bg-white rounded-2xl border border-gray-200/80 p-6 shadow-2xs space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-bold text-gray-900">
                Current Workspace: {ws.workspace_name}
              </h3>
              <p className="text-xs text-gray-500">
                Billing contact: {ws.billing_email || ws.owner_email || 'Not set'}
              </p>
            </div>
            <span
              className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold border ${wsBadge.className}`}
              data-testid="workspace-lifecycle-badge"
            >
              {wsBadge.label}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Card 1: Plan & Seats */}
            <div className="p-4 rounded-xl border border-gray-200/80 bg-gray-50/50 space-y-1">
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>Subscription Plan</span>
                <CreditCard className="w-4 h-4 text-indigo-600" />
              </div>
              <p className="text-sm font-bold text-gray-900" data-testid="workspace-plan-label">
                {ws.plan_label}
              </p>
              <p className="text-xs text-gray-500">
                {ws.connected_senders_count} connected / {ws.seats_granted} granted seats
              </p>
            </div>

            {/* Card 2: Subscription Expiry Date & Countdown */}
            <div className="p-4 rounded-xl border border-gray-200/80 bg-gray-50/50 space-y-1">
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>Subscription Ending</span>
                <Calendar className="w-4 h-4 text-indigo-600" />
              </div>
              <p className="text-sm font-bold text-gray-900" data-testid="workspace-paid-through">
                {ws.paid_through ? formatDate(ws.paid_through) : 'No active paid term'}
              </p>
              <p
                className={`text-xs font-medium ${
                  ws.days_remaining === null
                    ? 'text-gray-400'
                    : ws.days_remaining === 0
                    ? 'text-red-600'
                    : ws.days_remaining <= 7
                    ? 'text-amber-600'
                    : 'text-emerald-600'
                }`}
                data-testid="workspace-days-remaining"
              >
                {ws.days_remaining === null
                  ? 'Awaiting verified invoice activation'
                  : ws.days_remaining === 0
                  ? 'Paid period ended'
                  : `${ws.days_remaining} days remaining (${ws.hours_remaining}h)`}
              </p>
            </div>

            {/* Card 3: Active Workspace Users */}
            <div className="p-4 rounded-xl border border-gray-200/80 bg-gray-50/50 space-y-1">
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>Active Users</span>
                <Users className="w-4 h-4 text-indigo-600" />
              </div>
              <p className="text-sm font-bold text-gray-900" data-testid="workspace-active-members">
                {ws.active_members_24h ?? 0} active today · {ws.active_members_7d ?? 0} this week
              </p>
              <p className="text-xs text-gray-500">
                {ws.members_count ?? 0} total workspace{' '}
                {ws.members_count === 1 ? 'member' : 'members'}
              </p>
            </div>

            {/* Card 4: ElevenLabs Voice Quota */}
            <div className="p-4 rounded-xl border border-gray-200/80 bg-gray-50/50 space-y-1">
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>Daily Voice Note Quota</span>
                <Mic className="w-4 h-4 text-indigo-600" />
              </div>
              <p className="text-sm font-bold text-gray-900" data-testid="workspace-voice-clips">
                {ws.voice_usage?.today_clips_used ?? 0} / {ws.voice_usage?.daily_clips_limit ?? 20} clips today
              </p>
              <p className="text-xs text-gray-500">
                {(ws.voice_usage?.today_chars_used ?? 0).toLocaleString()} /{' '}
                {(ws.voice_usage?.daily_chars_limit ?? 20000).toLocaleString()} chars ·{' '}
                {ws.voice_usage?.voices_cloned_count ?? 0}/{ws.voice_usage?.max_voices ?? 5} voices cloned
              </p>
            </div>
          </div>

          {/* Per-Sender LinkedIn Account Quotas */}
          <div className="space-y-2.5 pt-2">
            <h4 className="text-xs font-bold text-gray-700 uppercase tracking-wider">
              Connected LinkedIn Senders & Daily Limits ({ws.senders?.length || 0})
            </h4>
            {!ws.senders || ws.senders.length === 0 ? (
              <p className="text-xs text-gray-400 py-2">
                No LinkedIn sender accounts connected in this workspace yet.
              </p>
            ) : (
              <div className="overflow-x-auto border border-gray-200/80 rounded-xl">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-gray-50/80 border-b border-gray-200/80 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                      <th className="py-2 px-3">LinkedIn Account</th>
                      <th className="py-2 px-3">Status & Proxy</th>
                      <th className="py-2 px-3">Invites Today</th>
                      <th className="py-2 px-3">Messages Today</th>
                      <th className="py-2 px-3">Voice Notes Today</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 text-xs">
                    {ws.senders.map((sender) => (
                      <tr key={sender.id} className="hover:bg-gray-50/60">
                        <td className="py-2.5 px-3">
                          <p className="font-semibold text-gray-900">{sender.account_name}</p>
                          <p className="text-[11px] text-gray-500 capitalize">
                            {String(sender.premium_product || 'free').replace('_', ' ')}
                            {sender.activity_control_enabled ? ' · Warm-up shield ON' : ''}
                          </p>
                        </td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                              sender.status === 'active' || sender.status === 'connected'
                                ? 'bg-emerald-50 text-emerald-700'
                                : 'bg-gray-100 text-gray-700'
                            }`}
                          >
                            {sender.status || 'unknown'}
                          </span>
                          <span className="text-[11px] text-gray-500 ml-1.5">
                            {sender.proxy_country ? `${sender.proxy_country} IP` : 'No IP'} (
                            {sender.proxy_status || 'assigned'})
                          </span>
                        </td>
                        <td className="py-2.5 px-3 font-medium text-gray-900">
                          {sender.daily_invites_used} / {sender.daily_invites_limit}
                        </td>
                        <td className="py-2.5 px-3 font-medium text-gray-900">
                          {sender.daily_messages_used} / {sender.daily_messages_limit}
                        </td>
                        <td className="py-2.5 px-3 font-medium text-gray-900">
                          {sender.daily_voice_notes_used} / {sender.daily_voice_notes_limit}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Workspace Members Activity Table */}
          {ws.members && ws.members.length > 0 && (
            <div className="space-y-2.5 pt-2">
              <h4 className="text-xs font-bold text-gray-700 uppercase tracking-wider">
                Workspace Users & Recent Activity ({ws.members.length})
              </h4>
              <div className="overflow-x-auto border border-gray-200/80 rounded-xl">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-gray-50/80 border-b border-gray-200/80 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                      <th className="py-2 px-3">User</th>
                      <th className="py-2 px-3">Role</th>
                      <th className="py-2 px-3">Activity Status</th>
                      <th className="py-2 px-3">Last Seen</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 text-xs">
                    {ws.members.map((m) => (
                      <tr key={m.user_id || m.email} className="hover:bg-gray-50/60">
                        <td className="py-2.5 px-3">
                          <p className="font-semibold text-gray-900">
                            {m.display_name || m.email || m.user_id}
                          </p>
                          {m.email && <p className="text-[11px] text-gray-500">{m.email}</p>}
                        </td>
                        <td className="py-2.5 px-3 capitalize font-medium text-gray-700">
                          {m.role}
                        </td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium ${
                              m.active_24h
                                ? 'bg-emerald-50 text-emerald-700'
                                : m.active_7d
                                ? 'bg-blue-50 text-blue-700'
                                : 'bg-gray-100 text-gray-600'
                            }`}
                          >
                            <span
                              className={`w-1.5 h-1.5 rounded-full ${
                                m.active_24h
                                  ? 'bg-emerald-500'
                                  : m.active_7d
                                  ? 'bg-blue-500'
                                  : 'bg-gray-400'
                              }`}
                            />
                            {m.active_24h ? 'Active (24h)' : m.active_7d ? 'Active (7d)' : 'Idle'}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-gray-500">
                          {formatDateTime(m.last_active_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
