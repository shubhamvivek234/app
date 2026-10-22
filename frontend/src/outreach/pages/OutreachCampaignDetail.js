import React, { useState, useEffect } from 'react';
import {
  ArrowLeft,
  Pencil,
  Users,
  Send,
  Calendar,
  Clock,
  CheckCircle2,
  AlertCircle,
  Search,
  Plus,
  RefreshCw,
  ExternalLink,
  Shield,
  Layers,
  Play,
  Pause,
} from 'lucide-react';
import { toast } from 'sonner';
import ImportLeadsModal from '../components/ImportLeadsModal';
import LeadActivityDrawer from '../components/LeadActivityDrawer';

const WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

const getScheduleSummary = (schedule = {}) => {
  const days = schedule.days;
  if (Array.isArray(days) && days.some((day) => day && typeof day === 'object')) {
    const enabledDays = days.filter((day) => day.enabled);
    if (!enabledDays.length) return { days: 'No days enabled', hours: 'No active hours' };
    const names = enabledDays.map((day) => day.day).filter(Boolean);
    const rangesByDay = enabledDays.map((day) => (day.ranges || []).map((range) => `${range.start}–${range.end}`).join(', '));
    const hours = rangesByDay.every((ranges) => ranges === rangesByDay[0])
      ? rangesByDay[0] || 'No active hours'
      : 'Hours vary by day';
    return { days: names.join(', ') || 'Selected days', hours };
  }
  if (Array.isArray(days)) {
    const names = days.map((day) => WEEKDAY_NAMES[day]).filter(Boolean);
    return {
      days: names.join(', ') || 'No days enabled',
      hours: `${schedule.start_time || '09:00'}–${schedule.end_time || '17:00'}`,
    };
  }
  return { days: 'Mon–Fri', hours: `${schedule.start_time || '09:00'}–${schedule.end_time || '17:00'}` };
};

export default function OutreachCampaignDetail({ campaignId, onBack, onEdit }) {
  const [campaign, setCampaign] = useState(null);
  const [activeTab, setActiveTab] = useState('analytics'); // 'analytics' | 'leads' | 'sequence' | 'settings'
  const [loading, setLoading] = useState(true);
  const [campaignError, setCampaignError] = useState('');
  const [leads, setLeads] = useState([]);
  const [leadsLoading, setLeadsLoading] = useState(false);
  const [leadsError, setLeadsError] = useState('');
  const [leadsSearch, setLeadsSearch] = useState('');
  const [selectedCohortFilter, setSelectedCohortFilter] = useState('all');
  const [leadsModalOpen, setLeadsModalOpen] = useState(false);
  const [selectedLeadId, setSelectedLeadId] = useState(null);
  const [sequence, setSequence] = useState(null);
  const [sequenceLoading, setSequenceLoading] = useState(false);
  const [sequenceError, setSequenceError] = useState('');
  const [statusUpdating, setStatusUpdating] = useState(false);
  const [togglingLeadId, setTogglingLeadId] = useState(null);
  const scheduleSummary = getScheduleSummary(campaign?.schedule);
  const totalLeads = campaign?.leads_count || 0;
  const contactedLeads = campaign?.leads_contacted || 0;
  const acceptedLeads = campaign?.acceptances_count || 0;
  const repliedLeads = campaign?.replies_count || 0;
  const interestedLeads = campaign?.interested_count || 0;
  const acceptanceRatePct = contactedLeads > 0 ? Math.round((acceptedLeads / contactedLeads) * 100) : null;
  const replyRatePct = contactedLeads > 0 ? Math.round((repliedLeads / contactedLeads) * 100) : null;
  const funnelStages = campaign?.funnel_stages || {
    completed: 0,
    paused: 0,
    moving: 0,
    queued: Math.max(0, totalLeads - contactedLeads),
    staged: 0,
    low_queue_warning: false,
  };

  const handleToggleLeadPause = async (lead, e) => {
    if (e) e.stopPropagation();
    if (!lead?.id) return;
    setTogglingLeadId(lead.id);
    const isPaused = lead.execution_state === 'paused' || lead.execution_state === 'replied';
    const endpoint = isPaused
      ? `/api/v1/outreach/leads/${lead.id}/resume`
      : `/api/v1/outreach/leads/${lead.id}/pause`;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(endpoint, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: isPaused ? undefined : JSON.stringify({ reason: 'Manually paused from campaign leads table' }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast.error(data.detail || `Failed to ${isPaused ? 'resume' : 'pause'} lead`);
        return;
      }
      toast.success(isPaused ? 'Lead sequence resumed' : 'Lead sequence paused');
      fetchLeads(leadsSearch);
      fetchCampaign();
    } catch (err) {
      toast.error('Could not update lead sequence state');
    } finally {
      setTogglingLeadId(null);
    }
  };
  const openEditor = (step) => {
    if (['active', 'warming_up'].includes(campaign?.status)) {
      toast.error('Pause the campaign before editing its sequence or settings.');
      return;
    }
    if (onEdit && campaign) onEdit(campaign.id, step, campaign.name);
  };

  const fetchCampaign = async () => {
    setLoading(true);
    setCampaignError('');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/campaigns/${campaignId}`, {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (res.status === 404) setCampaign(null);
        else throw new Error(data.detail || 'Campaign could not be loaded.');
        return;
      }
      setCampaign(data);
    } catch (err) {
      console.error('Failed to load campaign:', err);
      setCampaignError(err.message || 'Campaign could not be loaded.');
    } finally {
      setLoading(false);
    }
  };

  const fetchLeads = async (searchQuery = '') => {
    setLeadsLoading(true);
    setLeadsError('');
    try {
      const token = localStorage.getItem('token');
      const query = new URLSearchParams({ campaign_id: campaignId });
      if (searchQuery) query.set('search', searchQuery);
      const res = await fetch(`/api/v1/outreach/leads?${query.toString()}`, {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Campaign leads could not be loaded.');
      setLeads(data.leads || []);
    } catch (err) {
      console.error('Failed to fetch leads:', err);
      setLeadsError(err.message || 'Campaign leads could not be loaded.');
    } finally {
      setLeadsLoading(false);
    }
  };

  const fetchSequence = async () => {
    setSequenceLoading(true);
    setSequenceError('');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/sequences/${campaignId}`, {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Sequence could not be loaded.');
      setSequence(data);
    } catch (err) {
      console.error('Failed to load sequence:', err);
      setSequenceError(err.message || 'Sequence could not be loaded.');
    } finally {
      setSequenceLoading(false);
    }
  };

  const handleToggleStatus = async () => {
    if (!campaign) return;
    setStatusUpdating(true);
    const token = localStorage.getItem('token');
    try {
      if (['active', 'warming_up'].includes(campaign.status)) {
        const res = await fetch(`/api/v1/outreach/campaigns/${campaign.id}/pause`, {
          method: 'POST',
          credentials: 'include',
          headers: { Authorization: token ? `Bearer ${token}` : '' },
        });
        if (res.ok) {
          toast.success(campaign.status === 'warming_up' ? 'Conditional launch canceled' : 'Campaign paused');
          setCampaign((prev) => ({ ...prev, status: 'paused', auto_launch_enabled: false }));
        } else {
          toast.error('Failed to pause campaign');
        }
      } else {
        // Paused or Draft -> Launch/Resume
        const res = await fetch(`/api/v1/outreach/campaigns/${campaign.id}/launch`, {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            Authorization: token ? `Bearer ${token}` : '',
          },
          body: JSON.stringify({ status: 'active' }),
        });
        if (res.ok) {
          toast.success(campaign.status === 'paused' ? 'Campaign resumed' : 'Campaign launched!');
          setCampaign((prev) => ({ ...prev, status: 'active' }));
        } else {
          const data = await res.json().catch(() => ({}));
          toast.error(data.detail || 'Failed to activate campaign');
        }
      }
    } catch (err) {
      console.error('Status toggle failed:', err);
      toast.error('Error changing campaign status');
    } finally {
      setStatusUpdating(false);
    }
  };

  useEffect(() => {
    if (campaignId) {
      fetchCampaign();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId]);

  useEffect(() => {
    if (activeTab === 'leads' && campaignId) {
      fetchLeads(leadsSearch);
    }
    if (activeTab === 'sequence' && campaignId) {
      fetchSequence();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, campaignId]);

  const handleLeadsSearchSubmit = (e) => {
    e.preventDefault();
    fetchLeads(leadsSearch);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px] text-gray-400">
        <RefreshCw className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-8 text-center text-gray-500">
        <p className="text-sm">{campaignError || 'Campaign not found or has been removed.'}</p>
        {campaignError && <button type="button" onClick={fetchCampaign} className="mt-4 mr-4 text-xs font-semibold text-indigo-600 hover:text-indigo-800">Retry</button>}
        <button
          onClick={onBack}
          className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Campaigns
        </button>
      </div>
    );
  }

  const createdDate = campaign.created_at
    ? new Date(campaign.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    : 'recently';

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      {/* Back to campaigns navigation */}
      <button
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-xs font-semibold text-gray-500 hover:text-gray-900 transition-colors mb-4 group"
      >
        <ArrowLeft className="h-3.5 w-3.5 transition-transform group-hover:-translate-x-0.5" />
        Campaigns
      </button>

      {/* Top Campaign Header matching media_1790104472298.png */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
              {campaign.name}
            </h1>
            <span
              className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium border ${
                campaign.status === 'active'
                  ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                  : campaign.status === 'warming_up'
                  ? 'text-indigo-700 bg-indigo-50 border-indigo-200'
                  : campaign.status === 'paused'
                  ? 'text-amber-700 bg-amber-50 border-amber-200'
                  : campaign.status === 'completed'
                  ? 'text-blue-700 bg-blue-50 border-blue-200'
                  : 'text-gray-600 bg-gray-100 border-gray-200/80'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  campaign.status === 'active'
                    ? 'bg-emerald-500'
                    : campaign.status === 'warming_up'
                    ? 'bg-indigo-500'
                    : campaign.status === 'paused'
                    ? 'bg-amber-500'
                    : campaign.status === 'completed'
                    ? 'bg-blue-500'
                    : 'bg-gray-400'
                }`}
              />
              {campaign.status || 'draft'}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            {campaign.leads_count ? `${campaign.leads_count} lead${campaign.leads_count === 1 ? '' : 's'}` : 'No leads enrolled'} · {(campaign.senders?.length || campaign.sender_account_ids?.length || 0)} sender{(campaign.senders?.length || campaign.sender_account_ids?.length || 0) === 1 ? '' : 's'} · created {createdDate}
          </p>
          {campaign.status === 'warming_up' && <p className="mt-2 text-xs text-amber-800">
            Waiting for confirmed engagement from every lead and the full cooldown.
            {campaign.auto_launch_missing_count > 0 && ` ${campaign.auto_launch_missing_count} lead(s) still need engagement.`}
            {campaign.auto_launch_error && ` ${campaign.auto_launch_error}`}
          </p>}
        </div>

        <div className="flex items-center gap-3">
          {campaign.status === 'active' && (
            <button
              onClick={handleToggleStatus}
              disabled={statusUpdating}
              className="inline-flex items-center gap-1.5 rounded-xl border border-amber-200 bg-amber-50 hover:bg-amber-100 text-amber-700 px-4 py-2 text-xs font-semibold shadow-2xs transition-colors"
            >
              <Pause className="h-3.5 w-3.5" />
              {statusUpdating ? 'Pausing...' : 'Pause Campaign'}
            </button>
          )}
          {campaign.status === 'warming_up' && (
            <button onClick={handleToggleStatus} disabled={statusUpdating}
              className="inline-flex items-center gap-1.5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-xs font-semibold text-amber-800 disabled:opacity-50">
              <Pause className="h-3.5 w-3.5" /> {statusUpdating ? 'Canceling...' : 'Cancel auto-launch'}
            </button>
          )}
          {campaign.status === 'paused' && (
            <button
              onClick={handleToggleStatus}
              disabled={statusUpdating}
              className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 px-4 py-2 text-xs font-semibold shadow-2xs transition-colors"
            >
              <Play className="h-3.5 w-3.5" />
              {statusUpdating ? 'Resuming...' : 'Resume Campaign'}
            </button>
          )}
          {campaign.status === 'draft' && (
            <button
              onClick={() => openEditor(3)}
              disabled={statusUpdating}
              className="inline-flex items-center gap-1.5 rounded-xl bg-[#5145cd] hover:bg-[#4338ca] text-white px-4 py-2 text-xs font-semibold shadow-2xs transition-colors"
            >
              <Play className="h-3.5 w-3.5" />
              {statusUpdating ? 'Launching...' : 'Launch Campaign'}
            </button>
          )}
          <button
            onClick={() => openEditor(campaign.draft_step || 2)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-4 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-50 shadow-2xs transition-colors"
          >
            <Pencil className="h-3.5 w-3.5 text-indigo-600" />
            Edit
          </button>
        </div>
      </div>

      {/* Navigation Tabs matching media_1790104472298.png */}
      <div className="flex items-center gap-8 border-b border-gray-200 mb-6">
        {[
          { id: 'analytics', label: 'Analytics' },
          { id: 'leads', label: 'Leads' },
          { id: 'sequence', label: 'Sequence' },
          { id: 'settings', label: 'Settings' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`pb-3 text-xs font-semibold transition-all relative ${
              activeTab === tab.id
                ? 'text-indigo-600 font-bold'
                : 'text-gray-500 hover:text-gray-800'
            }`}
          >
            {tab.label}
            {activeTab === tab.id && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 rounded-full" />
            )}
          </button>
        ))}
      </div>

      {/* TAB 1: ANALYTICS (media_1790104472298.png) */}
      {activeTab === 'analytics' && (
        <div className="space-y-6">
          {/* Top 4 Metric Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-2xs">
              <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                LEADS CONTACTED
              </p>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                {campaign.leads_contacted || 0}
              </p>
              <p className="text-[11px] text-gray-400 mt-0.5">
                of {campaign.leads_count || 0} leads
              </p>
            </div>

            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-2xs">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                  ACCEPTED
                </p>
                {acceptanceRatePct !== null && (
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      acceptanceRatePct >= 30
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : acceptanceRatePct < 20
                        ? 'bg-rose-50 text-rose-700 border border-rose-200'
                        : 'bg-amber-50 text-amber-800 border border-amber-200'
                    }`}
                  >
                    {acceptanceRatePct >= 30
                      ? 'Healthy (30–35% target)'
                      : acceptanceRatePct < 20
                      ? 'Low (<20%) · Review ICP'
                      : 'Building (Target 30–35%)'}
                  </span>
                )}
              </div>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                {campaign.acceptances_count || 0}
              </p>
              <p className="text-[11px] text-gray-400 mt-0.5">
                {campaign.leads_contacted > 0
                  ? `${acceptanceRatePct}% acceptance`
                  : 'Not available'}
              </p>
            </div>

            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-2xs">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                  REPLIED
                </p>
                {replyRatePct !== null && (
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      replyRatePct >= 10
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : 'bg-amber-50 text-amber-800 border border-amber-200'
                    }`}
                  >
                    {replyRatePct >= 10 ? 'Healthy (10–15%+ target)' : 'Target 10–15%'}
                  </span>
                )}
              </div>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                {campaign.replies_count || 0}
              </p>
              <p className="text-[11px] text-gray-400 mt-0.5">
                {campaign.leads_contacted > 0
                  ? `${replyRatePct}% reply rate`
                  : 'Not available'}
              </p>
            </div>

            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-2xs">
              <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                INTERESTED
              </p>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                {campaign.interested_count || 0}
              </p>
              <p className="text-[11px] text-gray-400 mt-0.5">
                marked interested
              </p>
            </div>
          </div>

          {/* Middle Row: Funnel (left) + Context Cards (right) */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-start">
            {/* Funnel Card */}
            <div className="md:col-span-8 rounded-xl border border-gray-200 bg-white p-6 shadow-2xs">
              <h3 className="text-sm font-bold text-gray-900 mb-5">Funnel</h3>
              <div className="space-y-4">
                {[
                  { label: 'Leads contacted', count: contactedLeads, denominator: totalLeads },
                  { label: 'Accepted', count: acceptedLeads, denominator: contactedLeads },
                  { label: 'Replied', count: repliedLeads, denominator: acceptedLeads },
                  { label: 'Interested', count: interestedLeads, denominator: repliedLeads },
                ].map((item) => (
                  <div key={item.label} className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-gray-700">{item.label}</span>
                      <span className="text-gray-400 font-mono text-[11px]">
                        {item.count} · {item.denominator ? `${Math.round((item.count / item.denominator) * 100)}%` : 'Not available'}
                      </span>
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-gray-100 overflow-hidden">
                      <div
                        className="h-full bg-indigo-600 rounded-full transition-all"
                        style={{ width: `${item.denominator ? Math.min(100, (item.count / item.denominator) * 100) : 0}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-400 mt-6 pt-4 border-t border-gray-100">
                {contactedLeads ? 'Funnel rates are based on the previous stage.' : 'No runner activity yet.'}
              </p>

              {/* Dripify 5-Stage Lead Status Breakdown (Video #9: 2ZosGksIVRQ) */}
              <div className="mt-5 pt-4 border-t border-gray-100">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                    Lead Sequence Status Breakdown
                  </h4>
                  {funnelStages.low_queue_warning && (
                    <button
                      type="button"
                      onClick={() => setLeadsModalOpen(true)}
                      className="inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 px-2.5 py-0.5 text-[11px] font-bold text-amber-800 hover:bg-amber-100 cursor-pointer"
                    >
                      <AlertCircle className="w-3 h-3" />
                      Low Queue ({funnelStages.queued} left) · + Add Lead List
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 text-xs">
                  {[
                    { label: 'Completed', desc: 'Finished all steps', count: funnelStages.completed || 0, tone: 'bg-emerald-50/70 border-emerald-200 text-emerald-900' },
                    { label: 'Paused / Replied', desc: 'Stopped for reply/manual', count: funnelStages.paused || 0, tone: 'bg-amber-50/70 border-amber-200 text-amber-900' },
                    { label: 'Moving in Sequence', desc: 'Active between steps', count: funnelStages.moving || 0, tone: 'bg-indigo-50/70 border-indigo-200 text-indigo-900' },
                    { label: 'Waiting in Queue', desc: 'Getting ready to start', count: funnelStages.queued || 0, tone: 'bg-sky-50/70 border-sky-200 text-sky-900' },
                    { label: 'Uploading / Staged', desc: 'Pending source review', count: funnelStages.staged || 0, tone: 'bg-gray-50 border-gray-200 text-gray-700' },
                  ].map((stage) => (
                    <div key={stage.label} className={`rounded-xl border p-2.5 ${stage.tone}`}>
                      <p className="text-lg font-bold leading-tight">{stage.count}</p>
                      <p className="text-[11px] font-semibold mt-0.5">{stage.label}</p>
                      <p className="text-[10px] opacity-75">{stage.desc}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Right Stack: Audience, Sending from, Schedule */}
            <div className="md:col-span-4 space-y-4">
              {/* Audience */}
              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-2xs">
                <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-2">
                  Audience
                </p>
                <div className="flex items-center gap-2.5">
                  <div className="h-8 w-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                    <Users className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-xs font-bold text-gray-900 leading-tight">
                      {campaign.leads_count || 0} leads
                    </p>
                    <p className="text-[11px] text-gray-400 mt-0.5">
                      {campaign.leads_count ? 'Enrolled leads ready' : 'No enrolled leads'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Sending from */}
              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-2xs">
                <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1.5">
                  Sending from
                </p>
                <p className="text-xs font-semibold text-gray-800">
                  {campaign.senders && campaign.senders.length > 0
                    ? campaign.senders.map((s) => s.account_name).join(', ')
                    : 'No sender configured'}
                </p>
              </div>

              {/* Schedule */}
              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-2xs">
                <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1.5">
                  Schedule
                </p>
                <p className="text-xs font-semibold text-gray-800">
                  {scheduleSummary.days} · {scheduleSummary.hours}
                </p>
                <p className="text-[11px] text-gray-400 mt-0.5">{campaign.schedule?.timezone || 'UTC'}</p>
              </div>
            </div>
          </div>

          {/* Bottom Section 1: Step performance matching media_1790104472298.png */}
          <div className="rounded-2xl border border-gray-200 bg-white shadow-2xs overflow-hidden">
            <div className="p-5 border-b border-gray-100">
              <h3 className="text-sm font-bold text-gray-900">Step performance</h3>
            </div>
            {campaign.sequence?.nodes?.length ? (
              <div className="divide-y divide-gray-100">
                {campaign.sequence.nodes.map((node, index) => {
                  const stepStats = campaign.step_performance?.[node.id];
                  const hasStepEvents = stepStats && (stepStats.completed > 0 || stepStats.queued > 0 || stepStats.failed > 0);
                  return (
                    <div key={node.id || `${node.type}-${index}`} className="flex items-center gap-3 px-5 py-3">
                      <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-50 text-xs font-bold text-indigo-700">{index + 1}</span>
                      <div className="min-w-0">
                        <p className="truncate text-xs font-semibold text-gray-800">{node.title || node.type}</p>
                        <p className="text-[11px] text-gray-400">{node.type?.replaceAll('_', ' ')}</p>
                      </div>
                      {hasStepEvents ? (
                        <span className="ml-auto text-[11px] font-mono text-gray-600">
                          {stepStats.completed || 0} completed · {stepStats.queued || 0} active
                          {stepStats.failed > 0 ? ` · ${stepStats.failed} failed` : ''}
                        </span>
                      ) : (
                        <span className="ml-auto text-[11px] text-gray-400">No step events yet</span>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="py-14 px-4 text-center">
                <p className="text-xs text-gray-400">This campaign has no saved sequence flow yet.</p>
              </div>
            )}
          </div>

          {/* Bottom Section 2: Sender performance matching media_1790104472298.png */}
          <div className="rounded-2xl border border-gray-200 bg-white shadow-2xs overflow-hidden">
            <div className="p-5 border-b border-gray-100">
              <h3 className="text-sm font-bold text-gray-900">Sender performance</h3>
              <p className="text-[11px] text-gray-400 mt-0.5">
                Reply rate by sender in this campaign, best first.
              </p>
            </div>
            {campaign.senders?.some((s) => (s.contacted || 0) > 0 || (s.requests_sent || 0) > 0 || (s.messages_sent || 0) > 0) ? (
              <div className="divide-y divide-gray-100">
                {campaign.senders.map((sender) => (
                  <div key={sender.id} className="flex items-center justify-between gap-4 px-5 py-3.5 text-xs">
                    <div>
                      <p className="font-semibold text-gray-900">{sender.account_name}</p>
                      <p className="text-[11px] text-gray-400">
                        {sender.contacted || 0} contacted · {sender.acceptances || 0} accepted · {sender.replies || 0} replied
                      </p>
                    </div>
                    <span className="font-mono text-xs font-semibold text-indigo-700 bg-indigo-50 px-2.5 py-1 rounded-full">
                      {sender.reply_rate !== null && sender.reply_rate !== undefined ? `${sender.reply_rate}% reply rate` : 'Not available'}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-14 px-4 text-center">
                <p className="text-xs text-gray-400">
                  {campaign.senders && campaign.senders.length > 0
                    ? 'No sender activity recorded yet.'
                    : 'No sender is configured.'}
                </p>
              </div>
            )}
          </div>

          {/* Bottom Section 3: Per-Lead-List Performance Comparison (Video #9: 2ZosGksIVRQ) */}
          {Array.isArray(campaign.list_performance) && campaign.list_performance.length > 0 && (
            <div className="rounded-2xl border border-gray-200 bg-white shadow-2xs overflow-hidden">
              <div className="p-5 border-b border-gray-100 flex items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-bold text-gray-900">Lead list performance comparison</h3>
                  <p className="text-[11px] text-gray-400 mt-0.5">
                    Acceptance and response rates by imported lead list cohort (target 30–35% acceptance, 10–15% reply).
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setLeadsModalOpen(true)}
                  className="rounded-lg bg-indigo-50 text-indigo-700 hover:bg-indigo-100 px-3 py-1.5 text-xs font-semibold transition-colors cursor-pointer"
                >
                  + Add Lead List
                </button>
              </div>
              <div className="divide-y divide-gray-100">
                {campaign.list_performance.map((lp) => (
                  <div key={lp.list_name} className="flex flex-wrap items-center justify-between gap-4 px-5 py-3.5 text-xs">
                    <div>
                      <p className="font-bold text-gray-900">{lp.list_name}</p>
                      <p className="text-[11px] text-gray-400">
                        {lp.leads_count} leads · {lp.contacted} contacted · {lp.accepted} accepted · {lp.replied} replied
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
                        {lp.acceptance_rate !== null && lp.acceptance_rate !== undefined ? `${lp.acceptance_rate}% acceptance` : '0% acceptance'}
                      </span>
                      <span className="font-mono text-[11px] font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2.5 py-0.5 rounded-full">
                        {lp.reply_rate !== null && lp.reply_rate !== undefined ? `${lp.reply_rate}% reply` : '0% reply'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Bottom Section 4: Campaign Recent Activity Feed (Video #9 & Video #11) */}
          {Array.isArray(campaign.recent_activity) && campaign.recent_activity.length > 0 && (
            <div className="rounded-2xl border border-gray-200 bg-white shadow-2xs overflow-hidden">
              <div className="p-5 border-b border-gray-100">
                <h3 className="text-sm font-bold text-gray-900">Campaign recent activity</h3>
                <p className="text-[11px] text-gray-400 mt-0.5">
                  Chronological log of actions executed on prospects in this campaign.
                </p>
              </div>
              <div className="divide-y divide-gray-100">
                {campaign.recent_activity.slice(0, 10).map((act) => (
                  <div key={act.id || `${act.lead_id}-${act.timestamp}`} className="flex items-center justify-between gap-3 px-5 py-3 text-xs">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <span className="px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 font-semibold text-[11px] capitalize shrink-0">
                        {String(act.action_type || 'action').replace(/_/g, ' ')}
                      </span>
                      <button
                        type="button"
                        onClick={() => act.lead_id && setSelectedLeadId(act.lead_id)}
                        className="font-bold text-gray-900 hover:text-indigo-600 truncate cursor-pointer"
                      >
                        {act.lead_name}
                      </button>
                      {act.lead_company && (
                        <span className="text-gray-400 truncate hidden sm:inline">· {act.lead_company}</span>
                      )}
                      {act.lead_linkedin_url && (
                        <a
                          href={act.lead_linkedin_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-gray-400 hover:text-[#0A66C2] shrink-0"
                          title="Open LinkedIn Profile"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                    </div>
                    <span className="text-[11px] text-gray-400 font-mono shrink-0">
                      {act.timestamp ? new Date(act.timestamp).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: LEADS (media_1790104550721.png) */}
      {activeTab === 'leads' && (
        <div className="rounded-xl border border-gray-200 bg-white shadow-2xs overflow-hidden">
          {/* Leads Header Row */}
          <div className="p-5 border-b border-gray-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <h3 className="text-sm font-bold text-gray-900">
              Leads in this campaign {leads.length || campaign.leads_count || 0}
            </h3>

            <div className="flex items-center gap-3">
              <button
                onClick={() => setLeadsModalOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[#3730a3] hover:bg-[#312e81] px-3.5 py-1.5 text-xs font-semibold text-white shadow-2xs transition-colors"
              >
                Add leads
              </button>

              <form onSubmit={handleLeadsSearchSubmit} className="flex items-center gap-2">
                <div className="relative">
                  <Search className="absolute left-3 top-2 h-3.5 w-3.5 text-gray-400" />
                  <input
                    type="text"
                    value={leadsSearch}
                    onChange={(e) => setLeadsSearch(e.target.value)}
                    placeholder="Search leads"
                    className="w-48 sm:w-56 rounded-lg border border-gray-200 pl-8 pr-3 py-1.5 text-xs text-gray-800 placeholder:text-gray-400 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <button
                  type="submit"
                  className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  Search
                </button>
              </form>
            </div>
          </div>

          {/* Cohort / Lead List Filter Bar */}
          {Array.isArray(campaign.list_performance) && campaign.list_performance.length > 1 && (
            <div className="px-5 py-2.5 bg-gray-50/70 border-b border-gray-100 flex items-center gap-1.5 flex-wrap">
              <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mr-1">Lead List:</span>
              <button
                type="button"
                onClick={() => setSelectedCohortFilter('all')}
                className={`px-2.5 py-1 rounded-full text-[11px] font-semibold transition-colors cursor-pointer ${
                  selectedCohortFilter === 'all'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-100'
                }`}
              >
                All Lists ({leads.length})
              </button>
              {campaign.list_performance.map((lp) => (
                <button
                  key={lp.list_name}
                  type="button"
                  onClick={() => setSelectedCohortFilter(lp.list_name)}
                  className={`px-2.5 py-1 rounded-full text-[11px] font-semibold transition-colors cursor-pointer ${
                    selectedCohortFilter === lp.list_name
                      ? 'bg-indigo-600 text-white'
                      : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-100'
                  }`}
                >
                  {lp.list_name} ({lp.leads_count})
                </button>
              ))}
            </div>
          )}

          {/* Leads Table */}
          {leadsLoading ? (
            <div className="flex items-center justify-center py-16 text-gray-400">
              <RefreshCw className="h-6 w-6 animate-spin" />
            </div>
          ) : leadsError ? (
            <div role="alert" className="py-16 text-center text-xs text-red-600">
              {leadsError} <button type="button" onClick={() => fetchLeads(leadsSearch)} className="ml-2 font-semibold underline">Retry</button>
            </div>
          ) : leads.length === 0 ? (
            <div className="py-20 text-center text-xs text-gray-400">
              No leads assigned yet.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-gray-100 bg-gray-50/50 text-gray-400 uppercase font-semibold text-[10px] tracking-wider">
                  <tr>
                    <th className="py-3 px-5">NAME</th>
                    <th className="py-3 px-5">STATUS</th>
                    <th className="py-3 px-5">SEQUENCE STEP</th>
                    <th className="py-3 px-5">COMPANY</th>
                    <th className="py-3 px-5">LAST ACTIVITY</th>
                    <th className="py-3 px-5 text-right">ACTION</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {leads
                    .filter((l) => {
                      if (selectedCohortFilter === 'all') return true;
                      const cohort = l.list_name || l.source_metadata?.list_name || 'Default Cohort';
                      return cohort === selectedCohortFilter || (Array.isArray(l.tags) && l.tags.includes(selectedCohortFilter));
                    })
                    .map((l) => {
                      const isLeadPaused = l.execution_state === 'paused' || l.execution_state === 'replied';
                      return (
                    <tr
                      key={l.id}
                      onClick={() => setSelectedLeadId(l.id)}
                      className="hover:bg-gray-50/80 transition-colors cursor-pointer"
                    >
                      <td className="py-3.5 px-5 font-bold text-gray-900">
                        {l.first_name} {l.last_name}
                      </td>
                      <td className="py-3.5 px-5">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${
                            l.execution_state === 'replied'
                              ? 'bg-emerald-50 text-emerald-700'
                              : l.execution_state === 'paused'
                              ? 'bg-amber-50 text-amber-800'
                              : l.execution_state === 'accepted'
                              ? 'bg-indigo-50 text-indigo-700'
                              : 'bg-gray-100 text-gray-600'
                          }`}
                        >
                          {l.execution_state || 'queued'}
                        </span>
                        {l.pause_reason && (
                          <span
                            className="block text-[10px] text-amber-700 font-medium truncate max-w-[150px] mt-0.5"
                            title={l.pause_reason}
                          >
                            {l.pause_reason}
                          </span>
                        )}
                      </td>
                      <td className="py-3.5 px-5 text-gray-600 font-mono text-[11px]">
                        {l.current_node_id || 'Not started'}
                      </td>
                      <td className="py-3.5 px-5 text-gray-600">{l.company_name || '—'}</td>
                      <td className="py-3.5 px-5 text-gray-400 font-mono text-[11px]">
                        {l.updated_at ? new Date(l.updated_at).toLocaleDateString() : '—'}
                      </td>
                      <td className="py-3.5 px-5 text-right">
                        <div className="inline-flex items-center justify-end gap-2">
                          {l.execution_state !== 'staged' && (
                            <button
                              type="button"
                              disabled={togglingLeadId === l.id}
                              onClick={(e) => handleToggleLeadPause(l, e)}
                              className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold border transition-colors cursor-pointer ${
                                isLeadPaused
                                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100'
                                  : 'bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100'
                              }`}
                            >
                              {isLeadPaused ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
                              {isLeadPaused ? 'Resume' : 'Pause'}
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedLeadId(l.id);
                            }}
                            className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 hover:underline"
                          >
                            Timeline →
                          </button>
                        </div>
                      </td>
                    </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: SEQUENCE */}
      {activeTab === 'sequence' && (
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-2xs space-y-6">
          <div className="flex items-center justify-between pb-4 border-b border-gray-100">
            <div>
              <h3 className="text-sm font-bold text-gray-900">Sequence flow</h3>
              <p className="text-xs text-gray-400 mt-0.5">Automated outreach steps and conditional branches</p>
            </div>
            <button
              onClick={() => openEditor(2)}
              className="rounded-lg bg-indigo-50 text-indigo-600 hover:bg-indigo-100 px-3.5 py-1.5 text-xs font-semibold transition-colors inline-flex items-center gap-1.5"
            >
              <Pencil className="w-3.5 h-3.5" />
              Open in builder
            </button>
          </div>

          {sequenceLoading ? (
            <div className="flex items-center justify-center py-20 text-gray-400">
              <RefreshCw className="h-6 w-6 animate-spin" />
            </div>
          ) : sequenceError ? (
            <div role="alert" className="py-16 text-center text-xs text-red-600">
              {sequenceError} <button type="button" onClick={fetchSequence} className="ml-2 font-semibold underline">Retry</button>
            </div>
          ) : (sequence?.nodes?.length || campaign?.sequence?.nodes?.length) ? (
            <div className="space-y-3 max-w-2xl">
              {(sequence?.nodes || campaign?.sequence?.nodes || []).map((node, idx) => (
                <div
                  key={node.id || idx}
                  className="rounded-xl border border-gray-200 bg-white p-4 shadow-2xs flex items-start gap-3.5 hover:border-indigo-200 transition-colors"
                >
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 font-bold text-xs">
                    {idx + 1}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-bold text-xs text-gray-900 capitalize">
                        {node.title || node.type?.replace(/_/g, ' ') || 'Outreach step'}
                      </span>
                      {node.delay_hours !== undefined && (
                        <span className="text-[10px] font-semibold text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full inline-flex items-center gap-1">
                          <Clock className="w-3 h-3 text-gray-400" />
                          {node.delay_hours === 0 ? 'Immediately' : `Wait ${node.delay_hours}h`}
                        </span>
                      )}
                    </div>
                    {node.subtitle && (
                      <p className="text-[11px] text-gray-400 mt-0.5">{node.subtitle}</p>
                    )}
                    {(node.config?.body || node.config?.script || node.config?.note || node.config?.message) && (
                      <div className="mt-2 rounded-lg bg-gray-50 border border-gray-100 p-2.5 text-[11px] text-gray-600 font-mono line-clamp-2">
                        {node.config.body || node.config.script || node.config.note || node.config.message}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50/50 py-20 px-4 text-center">
              <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-50 text-indigo-500 mb-3">
                <Send className="h-5 w-5" />
              </div>
              <h4 className="text-sm font-bold text-gray-900">Nothing published yet</h4>
              <p className="text-xs text-gray-400 mt-1 max-w-sm mx-auto">
                This campaign has no published sequence flow. Click below to configure your sequence.
              </p>
              <button
                onClick={() => openEditor(2)}
                className="mt-4 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 text-xs font-semibold shadow-xs transition-colors inline-flex items-center gap-1.5"
              >
                <Plus className="w-3.5 h-3.5" />
                Configure sequence
              </button>
            </div>
          )}
        </div>
      )}

      {/* TAB 4: SETTINGS */}
      {activeTab === 'settings' && (
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-2xs space-y-6">
          <div className="flex items-center justify-between pb-4 border-b border-gray-100">
            <h3 className="text-sm font-bold text-gray-900">Campaign settings</h3>
            <div className="flex items-center gap-2.5">
              <button
                onClick={() => openEditor(2)}
                className="rounded-lg bg-indigo-50 text-indigo-600 hover:bg-indigo-100 px-3.5 py-1.5 text-xs font-semibold transition-colors"
              >
                Edit in builder
              </button>
              <button
                onClick={() => openEditor(3)}
                className="rounded-lg border border-gray-200 bg-white hover:bg-gray-50 px-3.5 py-1.5 text-xs font-semibold text-gray-700 transition-colors shadow-2xs"
              >
                Edit settings
              </button>
            </div>
          </div>

          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-1 md:grid-cols-12 gap-2 py-2">
              <span className="md:col-span-3 text-gray-500 font-medium">Name</span>
              <span className="md:col-span-9 font-bold text-gray-900">{campaign.name}</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-12 gap-2 py-2 border-t border-gray-100">
              <span className="md:col-span-3 text-gray-500 font-medium">Audience</span>
              <span className="md:col-span-9 text-gray-700">
                {campaign.leads_count || 0} leads · {campaign.leads_count ? 'Enrolled leads ready' : 'No enrolled leads'}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-12 gap-2 py-2 border-t border-gray-100">
              <span className="md:col-span-3 text-gray-500 font-medium">Team Deduplication</span>
              <span className="md:col-span-9 text-gray-700">
                {campaign.skip_team_campaign_leads
                  ? 'Skip leads found in campaigns of your team members'
                  : 'Contacted leads & Do-Not-Contact list only'}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-12 gap-2 py-2 border-t border-gray-100">
              <span className="md:col-span-3 text-gray-500 font-medium">Senders</span>
              <span className="md:col-span-9 text-gray-700">
                {campaign.senders && campaign.senders.length > 0
                  ? campaign.senders.map((s) => s.account_name).join(', ')
                  : 'No sender assigned'}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-12 gap-2 py-2 border-t border-gray-100">
              <span className="md:col-span-3 text-gray-500 font-medium">Schedule</span>
              <div className="md:col-span-9">
                <p className="font-semibold text-gray-900">
                  {scheduleSummary.days} · {scheduleSummary.hours}
                </p>
                <p className="text-[11px] text-gray-400 mt-0.5">
                  Sends in {campaign.schedule?.timezone || 'UTC'}.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-12 gap-2 py-2 border-t border-gray-100 items-start">
              <span className="md:col-span-3 text-gray-500 font-medium pt-1">Daily limits</span>
              <div className="md:col-span-9 flex flex-wrap gap-2">
                {[
                  { label: 'Connection invites', val: campaign.limits?.connection_invites ?? 20 },
                  { label: 'Messages', val: campaign.limits?.messages ?? 20 },
                  { label: 'Voice notes', val: campaign.limits?.voice_notes ?? 20 },
                  { label: 'InMails', val: campaign.limits?.inmails ?? 20 },
                  { label: 'Profile visits', val: campaign.limits?.profile_visits ?? 20 },
                  { label: 'Follows', val: campaign.limits?.follows ?? 20 },
                  { label: 'Post likes', val: campaign.limits?.post_likes ?? 20 },
                  { label: 'Comments', val: campaign.limits?.comments ?? 20 },
                ].map((lim) => (
                  <span
                    key={lim.label}
                    className="inline-flex items-center gap-1.5 bg-gray-100 text-gray-700 px-2.5 py-1 rounded-full text-[11px] font-medium"
                  >
                    <span>{lim.label}{lim.supported === false ? ' (coming soon)' : ''}</span>
                    <strong className="font-bold text-gray-900">{lim.val}</strong>
                  </span>
                ))}
              </div>
            </div>
          </div>

          <p className="text-[11px] text-gray-400 pt-4 border-t border-gray-100 leading-normal">
            Campaign limits apply per sender and cannot exceed that account's own safety cap. Changes take effect on the next send.
          </p>
        </div>
      )}

      {/* Import Leads Modal Trigger */}
      <ImportLeadsModal
        isOpen={leadsModalOpen}
        onClose={() => setLeadsModalOpen(false)}
        campaignId={campaign.id}
        onLeadsImported={() => {
          fetchLeads();
          fetchCampaign();
        }}
      />

      {/* Lead Activity & Journey Drawer */}
      <LeadActivityDrawer
        leadId={selectedLeadId}
        isOpen={!!selectedLeadId}
        onClose={() => setSelectedLeadId(null)}
        onLeadUpdated={() => fetchLeads(leadsSearch)}
      />
    </div>
  );
}
