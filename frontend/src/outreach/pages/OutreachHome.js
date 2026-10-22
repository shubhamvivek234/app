import React, { useState, useEffect } from 'react';
import { Check, Plus, UserPlus, Calendar, ArrowRight, Sparkles, Activity, ExternalLink, AlertCircle, Shield, Users } from 'lucide-react';
import ConnectLinkedInModal from '../components/ConnectLinkedInModal';
import { outreachLogger } from '../utils/logger';
import env from '@/env';

export default function OutreachHome({ onNavigate, onOpenWizard, onOpenCampaign }) {
  const [userName, setUserName] = useState('There');
  const [recentCampaigns, setRecentCampaigns] = useState([]);
  const [allCampaigns, setAllCampaigns] = useState([]);
  const [senderAccounts, setSenderAccounts] = useState([]);
  const [teamPerformance, setTeamPerformance] = useState([]);
  const [selectedTeammateId, setSelectedTeammateId] = useState(null);
  const [accountStats, setAccountStats] = useState({
    pending_invitations_count: 0,
    excessive_pending_invites_warning: false,
    unread_inbox_count: 0,
    profile_views_count: 0,
  });
  const [statsTimeframe, setStatsTimeframe] = useState('30d');
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);
  const [connectedAccountsCount, setConnectedAccountsCount] = useState(0);
  const [liveEvents, setLiveEvents] = useState([]);
  const [streamStatus, setStreamStatus] = useState('connecting');
  const [overviewError, setOverviewError] = useState('');
  const [streamNotice, setStreamNotice] = useState('');

  const loadOverview = async (tf = statsTimeframe) => {
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: token ? `Bearer ${token}` : '' };
      const [campRes, accRes] = await Promise.all([
        fetch('/api/v1/outreach/campaigns', { credentials: 'include', headers }),
        fetch('/api/v1/outreach/accounts', { credentials: 'include', headers }),
      ]);
      if (!campRes.ok || !accRes.ok) throw new Error('Could not load outreach setup');
      const [campaigns, accounts] = await Promise.all([campRes.json(), accRes.json()]);
      const campList = Array.isArray(campaigns) ? campaigns : [];
      const accList = Array.isArray(accounts) ? accounts : [];
      setAllCampaigns(campList);
      setRecentCampaigns(campList.slice(0, 5));
      setSenderAccounts(accList);
      setConnectedAccountsCount(accList.filter((account) => account.status === 'active').length);
      setOverviewError('');
      try {
        const analyticsRes = await fetch(`/api/v1/outreach/analytics?timeframe=${tf}`, { credentials: 'include', headers });
        if (analyticsRes && analyticsRes.ok) {
          const analyticsJson = await analyticsRes.json();
          if (analyticsJson && !Array.isArray(analyticsJson)) {
            if (analyticsJson.account_stats) {
              setAccountStats(analyticsJson.account_stats);
            }
            if (Array.isArray(analyticsJson.team_performance)) {
              setTeamPerformance(analyticsJson.team_performance);
              setSelectedTeammateId((prev) => prev || analyticsJson.team_performance[0]?.account_id || null);
            }
          }
        }
      } catch (err) {
        outreachLogger.debug('home.analytics_summary_unavailable', { error: err });
      }
    } catch (err) {
      outreachLogger.warn('home.overview_load_failed', { error: err });
      setOverviewError(err.message || 'Could not load outreach setup');
    }
  };

  useEffect(() => {
    // Try to get user name from local storage or profile
    try {
      const stored = localStorage.getItem('user');
      if (stored) {
        const u = JSON.parse(stored);
        if (u.name) setUserName(u.name.split(' ')[0]);
      }
    } catch (_) {}

    loadOverview();

    // Connect to the bounded activity stream using the existing session cookie.
    let eventSource;
    let streamClosed = false;
    let acceptingActivity = false;
    const seen = new Set();
    let retainedEvents = [];
    try {
      eventSource = new EventSource(`${env.BACKEND_URL}/api/v1/outreach/analytics/live-feed`, { withCredentials: true });

      eventSource.addEventListener('connected', () => {
        if (streamClosed) return;
        acceptingActivity = true;
        setStreamStatus('live');
        setStreamNotice('');
        setLiveEvents(retainedEvents);
      });

      eventSource.addEventListener('heartbeat', () => {
        if (streamClosed || !acceptingActivity) return;
        setStreamStatus('live');
      });

      eventSource.addEventListener('task_completed', (e) => {
        if (streamClosed || !acceptingActivity) return;
        try {
          const data = JSON.parse(e.data);
          const key = e.lastEventId || data.event_id || `${data.id}:${data.timestamp}`;
          if (!data.id || !data.timestamp || seen.has(key)) return;
          seen.add(key);
          if (seen.size > 4096) seen.delete(seen.values().next().value);
          retainedEvents = [data, ...retainedEvents.slice(0, 19)];
          setLiveEvents(retainedEvents);
        } catch (_) {}
      });

      eventSource.addEventListener('stream_closed', (event) => {
        if (streamClosed) return;
        streamClosed = true;
        acceptingActivity = false;
        retainedEvents = [];
        seen.clear();
        eventSource.close();
        setLiveEvents([]);
        setStreamStatus('stopped');
        let reason;
        try { reason = JSON.parse(event.data).reason; } catch (_) {}
        setStreamNotice(reason === 'resume_unavailable'
          ? 'The saved activity position is no longer available. Refresh to load recent observations.'
          : 'Refresh to check access again.');
      });

      eventSource.onerror = () => {
        if (streamClosed) return;
        acceptingActivity = false;
        setLiveEvents([]);
        setStreamStatus('standby');
      };
    } catch (err) {
      setStreamStatus('standby');
    }

    return () => {
      streamClosed = true;
      acceptingActivity = false;
      retainedEvents = [];
      seen.clear();
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [loadOverview]);

  const isAccountConnected = connectedAccountsCount > 0;
  const isCampaignCreated = recentCampaigns.length > 0;
  const completedSteps = 1 + (isAccountConnected ? 1 : 0) + (isCampaignCreated ? 1 : 0);
  const totalLeadsCount = allCampaigns.reduce((sum, c) => sum + (Number(c.leads_count) || 0), 0);
  const activeCampaignsCount = allCampaigns.filter((c) => c.status === 'active' || c.status === 'warming_up').length;
  const totalAcceptancesCount = allCampaigns.reduce((sum, c) => sum + (Number(c.acceptances_count) || 0), 0);
  const totalRepliesCount = allCampaigns.reduce((sum, c) => sum + (Number(c.replies_count) || 0), 0);
  const dailyActions = senderAccounts.reduce(
    (acc, sender) => {
      const c = sender?.counters || {};
      return {
        invites: acc.invites + (Number(c.invites) || 0),
        messages: acc.messages + (Number(c.messages) || 0),
        profile_views: acc.profile_views + (Number(c.profile_views) || 0),
        likes: acc.likes + (Number(c.likes) || 0),
        inmails: acc.inmails + (Number(c.inmails) || 0),
        follows: acc.follows + (Number(c.follows) || 0),
        comments: acc.comments + (Number(c.comments) || 0),
      };
    },
    { invites: 0, messages: 0, profile_views: 0, likes: 0, inmails: 0, follows: 0, comments: 0 }
  );

  return (
    <div className="min-h-screen bg-neutral-50/40 p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Welcome Header */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Welcome, {userName}.
            </h1>
            <p className="text-xs text-gray-500 mt-1">Your workspace is ready.</p>
          </div>
          {onOpenWizard && (
            <button
              type="button"
              onClick={() => onOpenWizard('new', 1)}
              className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 px-4 py-2 text-xs font-bold text-white shadow-xs transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              Create campaign
            </button>
          )}
        </div>

        {/* Workspace Performance Summary Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-white rounded-2xl border border-gray-200/80 p-4 shadow-2xs">
            <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider block">Connected Senders</span>
            <span className="text-xl font-bold text-gray-900 mt-1 block">{connectedAccountsCount}</span>
          </div>
          <div className="bg-white rounded-2xl border border-gray-200/80 p-4 shadow-2xs">
            <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider block">Active Campaigns</span>
            <span className="text-xl font-bold text-gray-900 mt-1 block">{activeCampaignsCount}</span>
          </div>
          <div className="bg-white rounded-2xl border border-gray-200/80 p-4 shadow-2xs">
            <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider block">Enrolled Leads</span>
            <span className="text-xl font-bold text-gray-900 mt-1 block">{totalLeadsCount.toLocaleString()}</span>
          </div>
          <div className="bg-white rounded-2xl border border-gray-200/80 p-4 shadow-2xs">
            <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider block">Accepted / Replies</span>
            <span className="text-xl font-bold text-indigo-600 mt-1 block">
              {totalAcceptancesCount} <span className="text-gray-300 font-normal">/</span> {totalRepliesCount}
            </span>
          </div>
        </div>

        {overviewError && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            {overviewError} <button type="button" onClick={loadOverview} className="font-semibold underline">Retry</button>
          </div>
        )}

        {/* Onboarding Checklist Card */}
        <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs overflow-hidden">
          <div className="p-6 border-b border-gray-100 flex items-center gap-4">
            <div className="w-12 h-12 rounded-full border-4 border-indigo-100 flex items-center justify-center font-bold text-xs text-indigo-600 bg-indigo-50/50 shrink-0">
              {completedSteps}/3
            </div>
            <div>
              <h3 className="font-bold text-gray-900 text-sm">Finish setting up</h3>
              <p className="text-xs text-gray-500">
                You are {Math.round((completedSteps / 3) * 100)}% of the way through setup.
              </p>
            </div>
          </div>

          <div className="divide-y divide-gray-100 text-xs">
            {/* Step 1: Create your account */}
            <div className="p-4 px-6 flex items-center justify-between hover:bg-gray-50/50">
              <div className="flex items-center gap-3.5">
                <div className="w-6 h-6 rounded-full bg-indigo-600 text-white flex items-center justify-center shrink-0">
                  <Check className="w-3.5 h-3.5 stroke-[3]" />
                </div>
                <div>
                  <p className="font-medium text-gray-900">Create your account</p>
                  <p className="text-gray-400 text-[11px]">Done. Step 1 was on us.</p>
                </div>
              </div>
              <span className="text-gray-400 font-medium">Done</span>
            </div>

            {/* Step 2: Connect LinkedIn Account */}
            <div className="p-4 px-6 flex items-center justify-between hover:bg-gray-50/50">
              <div className="flex items-center gap-3.5">
                {isAccountConnected ? (
                  <div className="w-6 h-6 rounded-full bg-indigo-600 text-white flex items-center justify-center shrink-0">
                    <Check className="w-3.5 h-3.5 stroke-[3]" />
                  </div>
                ) : (
                  <div className="w-6 h-6 rounded-full border-2 border-gray-300 shrink-0" />
                )}
                <div>
                  <p className="font-medium text-gray-900">Connect your LinkedIn account</p>
                  <p className="text-gray-400 text-[11px]">Connect via Chrome Extension or session cookie + dedicated proxy.</p>
                </div>
              </div>
              {isAccountConnected ? (
                <span className="text-gray-400 font-medium">Done</span>
              ) : (
                <button
                  onClick={() => setIsConnectModalOpen(true)}
                  className="px-4 py-1.5 bg-indigo-50 text-indigo-600 hover:bg-indigo-100 font-medium rounded-lg transition-colors"
                >
                  Start
                </button>
              )}
            </div>

            {/* Step 3: Create your first campaign */}
            <div className="p-4 px-6 flex items-center justify-between hover:bg-gray-50/50">
              <div className="flex items-center gap-3.5">
                {isCampaignCreated ? (
                  <div className="w-6 h-6 rounded-full bg-indigo-600 text-white flex items-center justify-center shrink-0">
                    <Check className="w-3.5 h-3.5 stroke-[3]" />
                  </div>
                ) : (
                  <div className="w-6 h-6 rounded-full border-2 border-gray-300 shrink-0" />
                )}
                <div>
                  <p className="font-medium text-gray-900">Create your first campaign</p>
                  <p className="text-gray-400 text-[11px]">
                    {isCampaignCreated ? 'Your first campaign is saved.' : 'Build your multi-step sequence.'}
                  </p>
                </div>
              </div>
              {isCampaignCreated ? (
                <span className="text-gray-400 font-medium">Done</span>
              ) : (
                <button
                  onClick={() => onOpenWizard('new', 1)}
                  className="px-4 py-1.5 bg-indigo-50 text-indigo-600 hover:bg-indigo-100 font-medium rounded-lg transition-colors"
                >
                  Start
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Recent Campaigns Card */}
        <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-gray-900 text-sm">Recent campaigns</h3>
            <button
              onClick={() => onNavigate('campaigns')}
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 flex items-center gap-1"
            >
              View all campaigns
              <ArrowRight className="w-3 h-3" />
            </button>
          </div>

          {recentCampaigns.length === 0 ? (
            <div className="py-8 text-center bg-gray-50/50 rounded-xl border border-dashed border-gray-200 text-gray-400 text-xs">
              No campaigns created yet. Click "+ Create campaign" to set up your first outreach campaign.
            </div>
          ) : (
            <div className="divide-y divide-gray-100 text-xs">
              {recentCampaigns.map((camp) => {
                const leadsCount = Number(camp.leads_count) || 0;
                const acceptances = Number(camp.acceptances_count) || 0;
                const replies = Number(camp.replies_count) || 0;
                const acceptRate = leadsCount > 0 ? `${Math.round((acceptances / leadsCount) * 100)}%` : '—';
                const replyRate = leadsCount > 0 ? `${Math.round((replies / leadsCount) * 100)}%` : '—';
                return (
                  <div
                    key={camp.id}
                    onClick={() => onOpenCampaign ? onOpenCampaign(camp.id) : onNavigate('campaigns')}
                    className="py-3 flex flex-wrap items-center justify-between gap-3 hover:bg-gray-50/60 px-2 rounded-lg cursor-pointer transition-colors"
                  >
                    <div>
                      <span className="font-medium text-gray-900">{camp.name}</span>
                      <span className="ml-2 text-[11px] text-gray-400">
                        {leadsCount} leads · {acceptRate} accepted · {replyRate} replied
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-gray-400 text-[11px]">
                        {new Date(camp.created_at || Date.now()).toLocaleDateString([], {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                        })}
                      </span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-gray-100 text-gray-600 capitalize">
                        {camp.status || 'draft'}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Dripify Account Stats Bar: Profile Views, Pending Sent Invitations & Unread Inbox (Video #10: iYeXpqZWvms) */}
        <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs p-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-bold text-gray-900 text-sm">Account Stats &amp; Invitation Hygiene</h3>
              <p className="text-[11px] text-gray-500">
                Track profile views, pending sent invitations, and unread prospect replies across your timeframe.
              </p>
            </div>
            <div className="inline-flex items-center rounded-xl border border-gray-200 bg-gray-50 p-0.5 text-[11px] font-semibold">
              {[
                { id: '7d', label: '7 Days' },
                { id: '14d', label: '14 Days' },
                { id: '30d', label: '30 Days' },
                { id: '90d', label: '90 Days' },
              ].map((tf) => (
                <button
                  key={tf.id}
                  type="button"
                  onClick={() => {
                    setStatsTimeframe(tf.id);
                    loadOverview(tf.id);
                  }}
                  className={`px-2.5 py-1 rounded-lg transition-colors cursor-pointer ${
                    statsTimeframe === tf.id
                      ? 'bg-white text-indigo-600 shadow-2xs font-bold'
                      : 'text-gray-500 hover:text-gray-800'
                  }`}
                >
                  {tf.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="rounded-xl border border-gray-100 bg-gray-50/70 p-3.5">
              <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                Profile Views ({statsTimeframe})
              </span>
              <span className="text-xl font-bold text-gray-900 mt-1 block">
                {accountStats.profile_views_count ?? dailyActions.profile_views}
              </span>
              <span className="text-[11px] text-gray-500 mt-0.5 block">
                Recorded sequence profile visits
              </span>
            </div>

            <div className={`rounded-xl border p-3.5 ${
              accountStats.excessive_pending_invites_warning
                ? 'border-amber-200 bg-amber-50/70'
                : 'border-gray-100 bg-gray-50/70'
            }`}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                  Pending Sent Invitations
                </span>
                {accountStats.excessive_pending_invites_warning && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-800 bg-amber-100 px-2 py-0.5 rounded-full">
                    <AlertCircle className="w-3 h-3" /> Withdraw Old Invites
                  </span>
                )}
              </div>
              <span className="text-xl font-bold text-gray-900 mt-1 block">
                {accountStats.pending_invitations_count || 0}
              </span>
              <span className="text-[11px] text-gray-500 mt-0.5 block">
                {accountStats.excessive_pending_invites_warning
                  ? 'High pending count — add a Withdraw Invite step to keep acceptance rates healthy'
                  : 'Unaccepted invites awaiting prospect response'}
              </span>
            </div>

            <div className="rounded-xl border border-gray-100 bg-gray-50/70 p-3.5 flex flex-col justify-between">
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                  Unread Inbox Messages
                </span>
                <span className="text-xl font-bold text-indigo-600 mt-1 block">
                  {accountStats.unread_inbox_count || 0}
                </span>
              </div>
              {onNavigate && (
                <button
                  type="button"
                  onClick={() => onNavigate('inbox')}
                  className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 cursor-pointer"
                >
                  Open Unified Inbox <ArrowRight className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Daily LinkedIn Action Stats & Sender Team Performance (Dripify Dashboard Parity) */}
        <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-bold text-gray-900 text-sm">Today&apos;s LinkedIn Actions</h3>
              <p className="text-[11px] text-gray-500">Recorded daily action volume across connected sender accounts.</p>
            </div>
            {onNavigate && (
              <button
                type="button"
                onClick={() => onNavigate('accounts')}
                className="text-xs font-semibold text-indigo-600 hover:text-indigo-700"
              >
                Manage senders
              </button>
            )}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2.5 text-center">
            {[
              { label: 'Invites', value: dailyActions.invites },
              { label: 'Messages', value: dailyActions.messages },
              { label: 'Profile Views', value: dailyActions.profile_views },
              { label: 'Post Likes', value: dailyActions.likes },
              { label: 'InMails', value: dailyActions.inmails },
              { label: 'Follows', value: dailyActions.follows },
              { label: 'Comments', value: dailyActions.comments },
            ].map((stat) => (
              <div key={stat.label} className="rounded-xl border border-gray-100 bg-gray-50/70 p-2.5">
                <span className="block text-base font-bold text-gray-900">{stat.value}</span>
                <span className="block text-[10px] font-medium text-gray-500 mt-0.5">{stat.label}</span>
              </div>
            ))}
          </div>
          {senderAccounts.length > 0 && (
            <div className="pt-3 border-t border-gray-100 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Users className="w-4 h-4 text-indigo-600" />
                  <h4 className="text-xs font-bold text-gray-900">Your Team &amp; Sender Activity ({statsTimeframe})</h4>
                </div>
                {onNavigate && (
                  <button
                    type="button"
                    onClick={() => onNavigate('analytics')}
                    className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 cursor-pointer"
                  >
                    Full Team Analytics →
                  </button>
                )}
              </div>

              {teamPerformance.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-12 gap-4 pt-1">
                  {/* Left: Selectable Team / Sender List */}
                  <div className="md:col-span-5 space-y-1.5">
                    {teamPerformance.map((member) => {
                      const isSelected = (selectedTeammateId || teamPerformance[0]?.account_id) === member.account_id;
                      const qStatus = member.queue_health_status || 'healthy';
                      return (
                        <button
                          key={member.account_id}
                          type="button"
                          onClick={() => setSelectedTeammateId(member.account_id)}
                          className={`w-full text-left p-2.5 rounded-xl border transition-all flex items-center justify-between gap-2 cursor-pointer ${
                            isSelected
                              ? 'border-indigo-500 bg-indigo-50/50 shadow-2xs'
                              : 'border-gray-100 bg-gray-50/40 hover:bg-gray-50'
                          }`}
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className={`w-2 h-2 rounded-full shrink-0 ${member.status === 'active' ? 'bg-emerald-500' : 'bg-gray-300'}`} />
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5">
                                <span className="text-xs font-bold text-gray-900 truncate">
                                  {member.account_name || 'LinkedIn Sender'}
                                </span>
                                {member.activity_control_enabled && (
                                  <Shield className="w-3 h-3 text-emerald-600 shrink-0" title="Protected by Activity Control" />
                                )}
                              </div>
                              <span className="text-[10px] text-gray-400 block truncate">
                                {member.active_campaigns_count ?? 0} active campaigns · {member.queued_leads_count ?? 0} queued leads
                              </span>
                            </div>
                          </div>
                          <div className="flex items-center gap-1.5 shrink-0">
                            {qStatus === 'empty_queue' && (
                              <span
                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-700"
                                title="All leads in active campaigns have started the sequence (0 queued left) — add more leads immediately"
                              >
                                <AlertCircle className="w-3 h-3" /> Empty Queue
                              </span>
                            )}
                            {qStatus === 'low_queue' && (
                              <span
                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800"
                                title="Most leads in active campaigns have started the sequence (<20 queued) — time to add more leads"
                              >
                                <AlertCircle className="w-3 h-3" /> Low Queue
                              </span>
                            )}
                            {member.unread_messages_count > 0 && (
                              <span className="px-1.5 py-0.5 rounded-full bg-indigo-100 text-indigo-700 text-[10px] font-bold">
                                {member.unread_messages_count} unread
                              </span>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>

                  {/* Right: Selected Teammate Activity Breakdown (Dripify Video #19) */}
                  <div className="md:col-span-7 rounded-xl border border-gray-100 bg-gray-50/50 p-4 space-y-3">
                    {(() => {
                      const activeMember =
                        teamPerformance.find((m) => m.account_id === selectedTeammateId) || teamPerformance[0];
                      if (!activeMember) return null;
                      const ps = activeMember.period_stats || {};
                      return (
                        <>
                          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200/70 pb-2.5">
                            <div>
                              <div className="flex items-center gap-1.5">
                                <span className="text-xs font-bold text-gray-900">{activeMember.account_name}</span>
                                {activeMember.activity_control_enabled && (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                                    <Shield className="w-2.5 h-2.5" /> Activity Control
                                  </span>
                                )}
                              </div>
                              <p className="text-[10px] text-gray-500">
                                {activeMember.connections_count != null ? `${activeMember.connections_count.toLocaleString()} 1st-degree connections · ` : ''}
                                {activeMember.pending_invitations_count ?? 0} pending invites · {activeMember.unread_messages_count ?? 0} unread messages
                              </p>
                            </div>
                            <div className="flex items-center gap-2">
                              {onNavigate && (
                                <button
                                  type="button"
                                  onClick={() => onNavigate('campaigns')}
                                  className="px-2.5 py-1 rounded-lg bg-white border border-gray-200 text-[10px] font-semibold text-gray-700 hover:bg-gray-50 cursor-pointer"
                                >
                                  View Campaigns
                                </button>
                              )}
                              {onNavigate && (
                                <button
                                  type="button"
                                  onClick={() => onNavigate('inbox')}
                                  className="px-2.5 py-1 rounded-lg bg-indigo-600 text-[10px] font-semibold text-white hover:bg-indigo-700 cursor-pointer"
                                >
                                  Open Inbox
                                </button>
                              )}
                            </div>
                          </div>
                          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs">
                            <div className="bg-white rounded-lg border border-gray-100 p-2.5">
                              <span className="text-[10px] text-gray-400 block">Connection Requests Sent</span>
                              <span className="text-sm font-bold text-gray-900">{ps.requests_sent ?? 0}</span>
                            </div>
                            <div className="bg-white rounded-lg border border-gray-100 p-2.5">
                              <span className="text-[10px] text-gray-400 block">Requests Accepted</span>
                              <span className="text-sm font-bold text-indigo-600">
                                {ps.requests_accepted ?? 0}
                                {ps.acceptance_rate != null ? ` (${ps.acceptance_rate}%)` : ''}
                              </span>
                            </div>
                            <div className="bg-white rounded-lg border border-gray-100 p-2.5">
                              <span className="text-[10px] text-gray-400 block">Messages &amp; InMails Sent</span>
                              <span className="text-sm font-bold text-gray-900">
                                {(ps.messages_sent ?? 0) + (ps.inmails_sent ?? 0)}
                              </span>
                            </div>
                            <div className="bg-white rounded-lg border border-gray-100 p-2.5">
                              <span className="text-[10px] text-gray-400 block">Leads Responded</span>
                              <span className="text-sm font-bold text-purple-600">
                                {ps.messages_replied ?? 0}
                                {ps.reply_rate != null ? ` (${ps.reply_rate}%)` : ''}
                              </span>
                            </div>
                            <div className="bg-white rounded-lg border border-gray-100 p-2.5">
                              <span className="text-[10px] text-gray-400 block">Profiles Visited</span>
                              <span className="text-sm font-bold text-gray-900">{ps.profile_visits ?? 0}</span>
                            </div>
                            <div className="bg-white rounded-lg border border-gray-100 p-2.5">
                              <span className="text-[10px] text-gray-400 block">Profiles Followed</span>
                              <span className="text-sm font-bold text-gray-900">{ps.follows_count ?? 0}</span>
                            </div>
                          </div>
                        </>
                      );
                    })()}
                  </div>
                </div>
              ) : (
                <div className="divide-y divide-gray-100 text-xs">
                  {senderAccounts.map((sender) => {
                    const c = sender.counters || {};
                    const lim = sender.daily_limits || {};
                    return (
                      <div key={sender.id} className="py-2 flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${sender.status === 'active' ? 'bg-emerald-500' : 'bg-gray-300'}`} />
                          <span className="font-semibold text-gray-900">{sender.account_name || sender.vanity_name || 'LinkedIn Sender'}</span>
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 capitalize">{sender.status || 'disconnected'}</span>
                        </div>
                        <div className="flex items-center gap-3 text-[11px] text-gray-500 font-mono">
                          <span>Invites: {Number(c.invites) || 0}/{Number(lim.invites) || 25}</span>
                          <span>Msgs: {Number(c.messages) || 0}/{Number(lim.messages) || 50}</span>
                          <span>Views: {Number(c.profile_views) || 0}/{Number(lim.profile_views) || 80}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Activity observations from the bounded stream */}
        <div className="bg-white rounded-2xl border border-gray-200/80 shadow-xs p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-indigo-600" />
              <h3 className="font-bold text-gray-900 text-sm">Completed Task Activity</h3>
            </div>
            {streamStatus === 'live' ? (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Live Feed
              </span>
            ) : streamStatus === 'connecting' ? (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-200">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                Connecting
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-gray-50 text-gray-500 border border-gray-200">
                <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />
                {streamStatus === 'stopped' ? 'Activity unavailable' : 'Standby'}
              </span>
            )}
          </div>
          <p className="text-[11px] text-gray-500">Recent stored task completions, followed by new observations. Reconnect resumes for up to 24 hours while the saved task is retained. This feed does not verify sends, replies, or campaign health.</p>

          {liveEvents.length === 0 ? (
            <div className="py-6 px-4 bg-gray-50/60 rounded-xl border border-gray-100 text-center">
              <p className="text-xs font-medium text-gray-700">
                {streamStatus === 'stopped' ? 'Activity connection ended' : 'Waiting for completed-task observations'}
              </p>
              <p className="text-[11px] text-gray-400 mt-0.5">
                {streamStatus === 'stopped' ? streamNotice : 'Starts with the last 10 minutes. Older or backdated changes may be absent; this is not a complete event history.'}
              </p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100 text-xs">
              {liveEvents.map((evt, idx) => (
                <div key={evt.id || idx} className="py-2.5 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="w-2 h-2 rounded-full bg-indigo-500 shrink-0" />
                    <span className="font-medium text-gray-900 capitalize shrink-0">
                      {(evt.task_type || 'activity').replace(/_/g, ' ')}
                    </span>
                    {(evt.lead_name || evt.lead_id) && (
                      <span className="text-gray-500 text-[11px] truncate">
                        {evt.lead_name || `Lead: ${evt.lead_id.slice(0, 10)}...`}
                      </span>
                    )}
                    {evt.lead_linkedin_url && (
                      <a
                        href={evt.lead_linkedin_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-gray-400 hover:text-[#0A66C2] shrink-0"
                        title="Open LinkedIn Profile"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}
                    {evt.campaign_id && onOpenCampaign && (
                      <button
                        type="button"
                        onClick={() => onOpenCampaign(evt.campaign_id)}
                        className="text-[11px] font-semibold text-indigo-600 hover:underline truncate cursor-pointer"
                      >
                        {evt.campaign_name || 'View Campaign'}
                      </button>
                    )}
                  </div>
                  <span className="text-[11px] text-gray-400 font-mono shrink-0">
                    {evt.timestamp ? new Date(evt.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'just now'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Connect Account Modal */}
      <ConnectLinkedInModal
        isOpen={isConnectModalOpen}
        onClose={() => {
          setIsConnectModalOpen(false);
        }}
        onAccountConnected={() => {
          setIsConnectModalOpen(false);
          loadOverview();
        }}
      />
    </div>
  );
}
