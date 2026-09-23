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

export default function OutreachCampaignDetail({ campaignId, onBack, onEdit }) {
  const [campaign, setCampaign] = useState(null);
  const [activeTab, setActiveTab] = useState('analytics'); // 'analytics' | 'leads' | 'sequence' | 'settings'
  const [loading, setLoading] = useState(true);
  const [leads, setLeads] = useState([]);
  const [leadsLoading, setLeadsLoading] = useState(false);
  const [leadsSearch, setLeadsSearch] = useState('');
  const [leadsModalOpen, setLeadsModalOpen] = useState(false);
  const [sequence, setSequence] = useState(null);
  const [sequenceLoading, setSequenceLoading] = useState(false);
  const [statusUpdating, setStatusUpdating] = useState(false);

  const fetchCampaign = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/campaigns/${campaignId}`, {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setCampaign(data);
      }
    } catch (err) {
      console.error('Failed to load campaign:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchLeads = async (searchQuery = '') => {
    setLeadsLoading(true);
    try {
      const token = localStorage.getItem('token');
      const query = new URLSearchParams({ campaign_id: campaignId });
      if (searchQuery) query.set('search', searchQuery);
      const res = await fetch(`/api/v1/outreach/leads?${query.toString()}`, {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setLeads(data.leads || []);
      }
    } catch (err) {
      console.error('Failed to fetch leads:', err);
    } finally {
      setLeadsLoading(false);
    }
  };

  const fetchSequence = async () => {
    setSequenceLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/sequences/${campaignId}`, {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setSequence(data);
      }
    } catch (err) {
      console.error('Failed to load sequence:', err);
    } finally {
      setSequenceLoading(false);
    }
  };

  const handleToggleStatus = async () => {
    if (!campaign) return;
    setStatusUpdating(true);
    const token = localStorage.getItem('token');
    try {
      if (campaign.status === 'active') {
        const res = await fetch(`/api/v1/outreach/campaigns/${campaign.id}/pause`, {
          method: 'POST',
          credentials: 'include',
          headers: { Authorization: token ? `Bearer ${token}` : '' },
        });
        if (res.ok) {
          toast.success('Campaign paused');
          setCampaign((prev) => ({ ...prev, status: 'paused' }));
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
        <p className="text-sm">Campaign not found or has been removed.</p>
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
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium text-gray-600 bg-gray-100 border border-gray-200/80">
              <span className="h-1.5 w-1.5 rounded-full bg-gray-400" />
              {campaign.status || 'draft'}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Persona not set · created {createdDate}
          </p>
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
              onClick={handleToggleStatus}
              disabled={statusUpdating}
              className="inline-flex items-center gap-1.5 rounded-xl bg-[#5145cd] hover:bg-[#4338ca] text-white px-4 py-2 text-xs font-semibold shadow-2xs transition-colors"
            >
              <Play className="h-3.5 w-3.5" />
              {statusUpdating ? 'Launching...' : 'Launch Campaign'}
            </button>
          )}
          <button
            onClick={() => onEdit && onEdit(campaign.id, campaign.draft_step || 2, campaign.name)}
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
                INVITES SENT
              </p>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                {campaign.leads_contacted || 0}
              </p>
              <p className="text-[11px] text-gray-400 mt-0.5">
                of {campaign.leads_count || 0} leads
              </p>
            </div>

            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-2xs">
              <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                ACCEPTED
              </p>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                {campaign.acceptances_count || 0}
              </p>
              <p className="text-[11px] text-gray-400 mt-0.5">
                {campaign.leads_contacted > 0
                  ? `${Math.round((campaign.acceptances_count / campaign.leads_contacted) * 100)}%`
                  : '0%'} acceptance
              </p>
            </div>

            <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-2xs">
              <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                REPLIED
              </p>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                {campaign.replies_count || 0}
              </p>
              <p className="text-[11px] text-gray-400 mt-0.5">
                {campaign.leads_contacted > 0
                  ? `${Math.round((campaign.replies_count / campaign.leads_contacted) * 100)}%`
                  : '0%'} reply rate
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
                  { label: 'Invites sent', value: `${campaign.leads_contacted || 0} · 0%`, pct: 0 },
                  { label: 'Accepted', value: `${campaign.acceptances_count || 0} · 0%`, pct: 0 },
                  { label: 'Replied', value: `${campaign.replies_count || 0} · 0%`, pct: 0 },
                  { label: 'Interested', value: `${campaign.interested_count || 0} · 0%`, pct: 0 },
                ].map((item) => (
                  <div key={item.label} className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-gray-700">{item.label}</span>
                      <span className="text-gray-400 font-mono text-[11px]">{item.value}</span>
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-gray-100 overflow-hidden">
                      <div
                        className="h-full bg-indigo-600 rounded-full transition-all"
                        style={{ width: `${item.pct}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-400 mt-6 pt-4 border-t border-gray-100">
                No runner activity yet.
              </p>
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
                  Mon–Fri · 09:00–17:00
                </p>
                <p className="text-[11px] text-gray-400 mt-0.5">UTC</p>
              </div>
            </div>
          </div>

          {/* Bottom Section 1: Step performance matching media_1790104472298.png */}
          <div className="rounded-2xl border border-gray-200 bg-white shadow-2xs overflow-hidden">
            <div className="p-5 border-b border-gray-100">
              <h3 className="text-sm font-bold text-gray-900">Step performance</h3>
            </div>
            <div className="py-14 px-4 text-center">
              <p className="text-xs text-gray-400">
                This campaign has no published flow, so it has no steps to report on.
              </p>
            </div>
          </div>

          {/* Bottom Section 2: Sender performance matching media_1790104472298.png */}
          <div className="rounded-2xl border border-gray-200 bg-white shadow-2xs overflow-hidden">
            <div className="p-5 border-b border-gray-100">
              <h3 className="text-sm font-bold text-gray-900">Sender performance</h3>
              <p className="text-[11px] text-gray-400 mt-0.5">
                Reply rate by sender in this campaign, best first.
              </p>
            </div>
            <div className="py-14 px-4 text-center">
              <p className="text-xs text-gray-400">
                {campaign.senders && campaign.senders.length > 0
                  ? 'No sender activity recorded yet.'
                  : 'No sender is configured.'}
              </p>
            </div>
          </div>
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

          {/* Leads Table */}
          {leadsLoading ? (
            <div className="flex items-center justify-center py-16 text-gray-400">
              <RefreshCw className="h-6 w-6 animate-spin" />
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
                    <th className="py-3 px-5">COMPANY</th>
                    <th className="py-3 px-5">JOB TITLE</th>
                    <th className="py-3 px-5">LAST ACTIVITY</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {leads.map((l) => (
                    <tr key={l.id} className="hover:bg-gray-50/60 transition-colors">
                      <td className="py-3.5 px-5 font-bold text-gray-900">
                        {l.first_name} {l.last_name}
                      </td>
                      <td className="py-3.5 px-5">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gray-100 text-gray-600 uppercase tracking-wider">
                          {l.execution_state || 'queued'}
                        </span>
                      </td>
                      <td className="py-3.5 px-5 text-gray-600">{l.company_name || '—'}</td>
                      <td className="py-3.5 px-5 text-gray-600">{l.job_title || '—'}</td>
                      <td className="py-3.5 px-5 text-gray-400 font-mono text-[11px]">
                        {l.updated_at ? new Date(l.updated_at).toLocaleDateString() : '—'}
                      </td>
                    </tr>
                  ))}
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
              onClick={() => onEdit && onEdit(campaign.id, 2)}
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
                onClick={() => onEdit && onEdit(campaign.id, 2)}
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
                onClick={() => onEdit && onEdit(campaign.id, 2)}
                className="rounded-lg bg-indigo-50 text-indigo-600 hover:bg-indigo-100 px-3.5 py-1.5 text-xs font-semibold transition-colors"
              >
                Edit in builder
              </button>
              <button
                onClick={() => onEdit && onEdit(campaign.id, 3)}
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
                  {Array.isArray(campaign.schedule?.days)
                    ? campaign.schedule.days.filter((d) => d.enabled).map((d) => d.day).join(', ') || 'None'
                    : 'Mon–Fri'} · {
                    Array.isArray(campaign.schedule?.days) && campaign.schedule.days.find((d) => d.enabled)?.ranges?.[0]
                      ? `${campaign.schedule.days.find((d) => d.enabled).ranges[0].start} – ${campaign.schedule.days.find((d) => d.enabled).ranges[0].end}`
                      : '09:00 AM – 05:00 PM'
                  }
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
                    <span>{lim.label}</span>
                    <strong className="font-bold text-gray-900">{lim.val}</strong>
                  </span>
                ))}
              </div>
            </div>
          </div>

          <p className="text-[11px] text-gray-400 pt-4 border-t border-gray-100 leading-normal">
            Limits apply to every sender separately. Changes in the builder take effect on the next send.
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
    </div>
  );
}
