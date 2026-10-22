import React, { useState, useEffect, useRef } from 'react';
import {
  Search,
  Download,
  Plus,
  Users,
  Building,
  MapPin,
  Mail,
  Phone,
  RefreshCw,
  Trash2,
  Columns,
  List,
  ArrowRight,
  ExternalLink,
  X,
  Check,
  ChevronDown,
  Tag,
  Ban,
  Play,
  Pause,
} from 'lucide-react';
import ImportLeadsModal from '../components/ImportLeadsModal';
import AudienceListsPanel from '../components/AudienceListsPanel';
import LeadActivityDrawer from '../components/LeadActivityDrawer';
import LeadTagManager from '../components/LeadTagManager';
import LeadSelectionReview from '../components/LeadSelectionReview';

const PIPELINE_STAGES = [
  { id: 'unassigned', label: 'Unassigned', dotColor: 'bg-gray-400', textColor: 'text-gray-600', countBadge: 'bg-gray-100 text-gray-700' },
  { id: 'in_campaign', label: 'In Campaign', dotColor: 'bg-amber-400', textColor: 'text-amber-700', countBadge: 'bg-amber-50 text-amber-800' },
  { id: 'contacted', label: 'Contacted', dotColor: 'bg-purple-500', textColor: 'text-purple-700', countBadge: 'bg-purple-50 text-purple-800' },
  { id: 'replied', label: 'Replied', dotColor: 'bg-emerald-500', textColor: 'text-emerald-700', countBadge: 'bg-emerald-50 text-emerald-800' },
  { id: 'call_booked', label: 'Call booked', dotColor: 'bg-rose-500', textColor: 'text-rose-700', countBadge: 'bg-rose-50 text-rose-800' },
];

const PAGE_SIZE = 50;
const authHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const errorMessage = async (response, fallback) => {
  const body = await response.json().catch(() => ({}));
  return typeof body.detail === 'string' ? body.detail : fallback;
};

const displayLocation = (lead) => lead.location || (
  lead.country_code?.toLowerCase() === 'us' ? '' : lead.country_code
);

export default function OutreachLeads({ onOpenWizard }) {
  const [leads, setLeads] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedState, setSelectedState] = useState('');
  const [selectedStage, setSelectedStage] = useState('');
  const [selectedSource, setSelectedSource] = useState('');
  const [selectedLocation, setSelectedLocation] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [debouncedLocation, setDebouncedLocation] = useState('');
  const [page, setPage] = useState(0);
  const [error, setError] = useState('');
  const [campaigns, setCampaigns] = useState([]);
  const [importCampaignId, setImportCampaignId] = useState('');
  const [exporting, setExporting] = useState(false);
  const [updatingLeadId, setUpdatingLeadId] = useState(null);
  const [deletingLeadId, setDeletingLeadId] = useState(null);
  const [selectedLead, setSelectedLead] = useState(null);
  const [columnPickerOpen, setColumnPickerOpen] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState({
    pipelineStage: true,
    executionState: true,
    lastAction: true,
    company: true,
    jobTitle: true,
    location: true,
    email: true,
  });
  const [modalOpen, setModalOpen] = useState(false);
  const [audiencesOpen, setAudiencesOpen] = useState(false);
  const [selectedList, setSelectedList] = useState('all');
  const [viewMode, setViewMode] = useState(() => {
    return localStorage.getItem('outreach_leads_view_mode') || 'kanban';
  });
  const [draggedLeadId, setDraggedLeadId] = useState(null);
  const [tagDefinitions, setTagDefinitions] = useState([]);
  const [tagLoadError, setTagLoadError] = useState('');
  const [selectedTagFilter, setSelectedTagFilter] = useState('');
  const [tagMatchMode, setTagMatchMode] = useState('all');
  const [selectedActionPerformed, setSelectedActionPerformed] = useState('');
  const [selectedFailureReason, setSelectedFailureReason] = useState('');
  const [includeActionsFilter, setIncludeActionsFilter] = useState('');
  const [excludeActionsFilter, setExcludeActionsFilter] = useState('');
  const [customFilters, setCustomFilters] = useState([]);
  const [customFilterModalOpen, setCustomFilterModalOpen] = useState(false);
  const [newFilterName, setNewFilterName] = useState('');
  const [newFilterInclude, setNewFilterInclude] = useState([]);
  const [newFilterExclude, setNewFilterExclude] = useState([]);
  const [savingCustomFilter, setSavingCustomFilter] = useState(false);
  const [selectedLeadIds, setSelectedLeadIds] = useState([]);
  const [bulkTagId, setBulkTagId] = useState('');
  const [bulkBusy, setBulkBusy] = useState(false);
  const [tagManagerOpen, setTagManagerOpen] = useState(false);
  const [followUpSelection, setFollowUpSelection] = useState(null);
  const leadRequest = useRef(0);
  const refreshLeads = useRef(null);
  const currentQuery = useRef('');
  const queryKey = JSON.stringify([page, debouncedSearch, selectedState, selectedStage, selectedSource, selectedTagFilter, tagMatchMode, debouncedLocation, selectedList, selectedActionPerformed, selectedFailureReason, includeActionsFilter, excludeActionsFilter]);
  currentQuery.current = queryKey;

  const handleSetViewMode = (mode) => {
    setViewMode(mode);
    localStorage.setItem('outreach_leads_view_mode', mode);
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery.trim());
      setDebouncedLocation(selectedLocation.trim());
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery, selectedLocation]);

  useEffect(() => { setPage(0); setSelectedLeadIds([]); }, [selectedList, selectedState, selectedStage, selectedSource, selectedTagFilter, debouncedSearch, debouncedLocation, selectedActionPerformed, selectedFailureReason, includeActionsFilter, excludeActionsFilter]);

  const fetchCustomFilters = async () => {
    try {
      const res = await fetch('/api/v1/outreach/leads/custom-filters', {
        credentials: 'include', headers: authHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) setCustomFilters(data);
      }
    } catch {
      // non-fatal
    }
  };

  useEffect(() => { fetchCustomFilters(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSaveCustomFilter = async (e) => {
    if (e) e.preventDefault();
    if (!newFilterName.trim() || (!newFilterInclude.length && !newFilterExclude.length)) return;
    setSavingCustomFilter(true);
    try {
      const res = await fetch('/api/v1/outreach/leads/custom-filters', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          name: newFilterName.trim(),
          include_actions: newFilterInclude,
          exclude_actions: newFilterExclude,
        }),
      });
      if (!res.ok) throw new Error(await errorMessage(res, 'Could not save custom filter'));
      const saved = await res.json();
      setCustomFilters((prev) => [saved, ...prev]);
      setIncludeActionsFilter((saved.include_actions || []).join(','));
      setExcludeActionsFilter((saved.exclude_actions || []).join(','));
      setNewFilterName('');
      setNewFilterInclude([]);
      setNewFilterExclude([]);
      setCustomFilterModalOpen(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingCustomFilter(false);
    }
  };

  const handleDeleteCustomFilter = async (filterId) => {
    try {
      const res = await fetch(`/api/v1/outreach/leads/custom-filters/${filterId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: authHeaders(),
      });
      if (res.ok) {
        setCustomFilters((prev) => prev.filter((f) => f.id !== filterId));
      }
    } catch {
      // non-fatal
    }
  };

  const fetchCampaigns = async () => {
    try {
      const res = await fetch('/api/v1/outreach/campaigns', {
        credentials: 'include', headers: authHeaders(),
      });
      if (!res.ok) throw new Error(await errorMessage(res, 'Could not load campaigns'));
      const data = await res.json();
      const nextCampaigns = Array.isArray(data) ? data : [];
      setCampaigns(nextCampaigns);
      setImportCampaignId((previous) => nextCampaigns.some((campaign) => campaign.id === previous)
        ? previous : nextCampaigns[0]?.id || '');
      setSelectedList((previous) => previous === 'all' || nextCampaigns.some((campaign) => campaign.id === previous)
        ? previous : 'all');
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => { fetchCampaigns(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchTags = async () => {
    setTagLoadError('');
    try {
      const res = await fetch('/api/v1/outreach/leads/tags', { credentials: 'include', headers: authHeaders() });
      if (!res.ok) throw new Error(await errorMessage(res, 'Could not load lead tags'));
      const data = await res.json();
      if (!Array.isArray(data)) throw new Error('Could not load lead tags');
      setTagDefinitions(data);
      setBulkTagId((current) => (data || []).some((tag) => tag.id === current) ? current : data?.[0]?.id || '');
      setSelectedTagFilter((current) => current === '__untagged__' || (data || []).some((tag) => tag.id === current) ? current : '');
    } catch (err) {
      setTagLoadError(err.message || 'Could not load lead tags');
    }
  };

  useEffect(() => { fetchTags(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const buildParams = () => {
    const params = new URLSearchParams();
    if (selectedList !== 'all') params.set('campaign_id', selectedList);
    if (debouncedSearch) params.set('search', debouncedSearch);
    if (selectedState) params.set('execution_state', selectedState);
    if (selectedStage) params.set('pipeline_stage', selectedStage);
    if (selectedSource) params.set('source', selectedSource);
    if (debouncedLocation) params.set('location', debouncedLocation);
    if (selectedTagFilter === '__untagged__') params.set('untagged', 'true');
    else if (selectedTagFilter) {
      params.set('tag_ids', selectedTagFilter);
      if (selectedTagFilter.includes(',') && tagMatchMode === 'any') {
        params.set('tag_match', 'any');
      }
    }
    if (selectedActionPerformed) params.set('action_performed', selectedActionPerformed);
    if (selectedFailureReason) params.set('failure_reason', selectedFailureReason);
    if (includeActionsFilter) params.set('include_actions', includeActionsFilter);
    if (excludeActionsFilter) params.set('exclude_actions', excludeActionsFilter);
    return params;
  };

  const fetchLeads = async (signal) => {
    if (queryKey !== currentQuery.current || signal?.aborted) return;
    const requestId = ++leadRequest.current;
    const isCurrent = () => !signal?.aborted && requestId === leadRequest.current && queryKey === currentQuery.current;
    setLoading(true);
    try {
      const params = buildParams();
      params.set('skip', String(page * PAGE_SIZE));
      params.set('limit', String(PAGE_SIZE));
      const res = await fetch(`/api/v1/outreach/leads?${params.toString()}`, {
        credentials: 'include', headers: authHeaders(), signal,
      });
      if (!res.ok) throw new Error(await errorMessage(res, 'Could not load leads'));
      const data = await res.json();
      if (!isCurrent()) return;
      if (page > 0 && !data.leads?.length && data.total <= page * PAGE_SIZE) {
        setPage(page - 1);
        return;
      }
      setLeads(data.leads || []);
      setTotal(data.total || 0);
      setError('');
    } catch (err) {
      if (isCurrent() && err.name !== 'AbortError') {
        setLeads([]);
        setTotal(0);
        setError(err.message);
      }
    } finally {
      if (isCurrent()) setLoading(false);
    }
  };
  refreshLeads.current = fetchLeads;

  useEffect(() => {
    const controller = new AbortController();
    fetchLeads(controller.signal);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, debouncedSearch, selectedState, selectedStage, selectedSource, selectedTagFilter, tagMatchMode, debouncedLocation, selectedList, selectedActionPerformed, selectedFailureReason, includeActionsFilter, excludeActionsFilter]);

  const toggleSelected = (leadId) => {
    setSelectedLeadIds((current) => current.includes(leadId)
      ? current.filter((id) => id !== leadId) : [...current, leadId]);
  };

  const handleBulkTag = async (operation) => {
    if (!bulkTagId || !selectedLeadIds.length) return;
    setBulkBusy(true);
    try {
      const res = await fetch('/api/v1/outreach/leads/tags/bulk', {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ lead_ids: selectedLeadIds, tag_id: bulkTagId, operation }),
      });
      if (!res.ok) throw new Error(await errorMessage(res, 'Could not update selected leads'));
      setSelectedLeadIds([]);
      await refreshLeads.current();
    } catch (err) {
      setError(err.message);
    } finally {
      setBulkBusy(false);
    }
  };

  const openImport = () => {
    if (!importCampaignId) {
      setError('Create a campaign in Campaigns before importing contacts.');
      return;
    }
    setModalOpen(true);
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await fetch(`/api/v1/outreach/leads/export?${buildParams().toString()}`, {
        credentials: 'include', headers: authHeaders(),
      });
      if (!res.ok) throw new Error(await errorMessage(res, 'Could not export leads'));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'outreach-leads.csv';
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setError('');
    } catch (err) {
      setError(err.message);
    } finally {
      setExporting(false);
    }
  };

  const handleDeleteLead = async (leadId) => {
    if (!window.confirm('Delete this contact?')) return;
    setDeletingLeadId(leadId);
    try {
      const res = await fetch(`/api/v1/outreach/leads/${leadId}`, {
        method: 'DELETE', credentials: 'include', headers: authHeaders(),
      });
      if (!res.ok) throw new Error(await errorMessage(res, 'Could not delete contact'));
      setSelectedLead((previous) => previous?.id === leadId ? null : previous);
      if (leads.length === 1 && page > 0) setPage((previous) => previous - 1);
      else await fetchLeads();
      await fetchCampaigns();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeletingLeadId(null);
    }
  };

  const handleUpdateStage = async (leadId, newStage) => {
    if (updatingLeadId) return;
    const oldStage = leads.find((lead) => lead.id === leadId)?.pipeline_stage || 'unassigned';
    if (oldStage === newStage) return;
    setUpdatingLeadId(leadId);
    setLeads((prev) =>
      prev.map((l) => (l.id === leadId ? { ...l, pipeline_stage: newStage } : l))
    );
    setSelectedLead((previous) => previous?.id === leadId ? { ...previous, pipeline_stage: newStage } : previous);

    try {
      const res = await fetch(`/api/v1/outreach/leads/${leadId}/stage`, {
        method: 'PATCH', credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
        },
        body: JSON.stringify({ pipeline_stage: newStage }),
      });
      if (!res.ok) throw new Error(await errorMessage(res, 'Could not update pipeline stage'));
      setError('');
      if (selectedStage && newStage !== selectedStage) await fetchLeads();
    } catch (err) {
      setLeads((prev) => prev.map((lead) => lead.id === leadId ? { ...lead, pipeline_stage: oldStage } : lead));
      setSelectedLead((previous) => previous?.id === leadId ? { ...previous, pipeline_stage: oldStage } : previous);
      setError(err.message);
    } finally {
      setUpdatingLeadId(null);
    }
  };

  // Move to next stage helper
  const handleAdvanceStage = (lead) => {
    const currentIdx = PIPELINE_STAGES.findIndex(
      (s) => s.id === (lead.pipeline_stage || 'unassigned')
    );
    if (currentIdx < PIPELINE_STAGES.length - 1) {
      const nextStage = PIPELINE_STAGES[currentIdx + 1].id;
      handleUpdateStage(lead.id, nextStage);
    }
  };

  const handleToggleSequencePause = async (lead) => {
    if (!lead?.id || updatingLeadId) return;
    setUpdatingLeadId(lead.id);
    const isPaused = lead.execution_state === 'paused' || lead.execution_state === 'replied';
    const endpoint = isPaused
      ? `/api/v1/outreach/leads/${lead.id}/resume`
      : `/api/v1/outreach/leads/${lead.id}/pause`;
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
        },
        body: isPaused ? undefined : JSON.stringify({ reason: 'Manually paused from CRM leads view' }),
      });
      if (!res.ok) throw new Error(await errorMessage(res, `Could not ${isPaused ? 'resume' : 'pause'} lead sequence`));
      const nextState = isPaused ? 'queued' : 'paused';
      setLeads((prev) => prev.map((l) => (l.id === lead.id ? { ...l, execution_state: nextState } : l)));
      setSelectedLead((prev) => (prev?.id === lead.id ? { ...prev, execution_state: nextState } : prev));
      setError('');
    } catch (err) {
      setError(err.message);
    } finally {
      setUpdatingLeadId(null);
    }
  };

  // Drag and Drop handlers
  const handleDragStart = (e, leadId) => {
    setDraggedLeadId(leadId);
    e.dataTransfer.setData('text/plain', leadId);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleDrop = (e, targetStage) => {
    e.preventDefault();
    const leadId = e.dataTransfer.getData('text/plain') || draggedLeadId;
    if (leadId) {
      handleUpdateStage(leadId, targetStage);
    }
    setDraggedLeadId(null);
  };

  const getInitials = (firstName, lastName) => {
    const f = (firstName || '').charAt(0).toUpperCase();
    const l = (lastName || '').charAt(0).toUpperCase();
    return f || l ? `${f}${l}` : 'LI';
  };

  const displayedLeads = leads;
  const campaignName = (id) => id
    ? campaigns.find((campaign) => campaign.id === id)?.name || 'Unknown campaign'
    : 'Unassigned';

  return (
    <div className="flex h-full max-h-full min-h-0 bg-[#fafafa] overflow-hidden">
      {/* Campaign-scoped lead lists */}
      <div className="w-60 border-r border-gray-200/80 bg-white p-5 flex flex-col justify-between shrink-0 h-full gap-4">
        <div className="min-h-0 flex-1 flex flex-col">
          <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">CAMPAIGNS</span>
          <div className="mt-3 space-y-1 overflow-y-auto min-h-0">
            <button
              onClick={() => setSelectedList('all')}
              className={`w-full flex items-center justify-between px-3 py-2 text-xs font-medium rounded-xl transition-colors ${
                selectedList === 'all'
                  ? 'bg-indigo-50 text-indigo-700 font-bold'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <div className="flex items-center gap-2">
                <Users className="h-3.5 w-3.5" />
                <span>All contacts</span>
              </div>
              {selectedList === 'all' && <span className="text-[11px] font-semibold text-gray-600">{total}</span>}
            </button>
            {campaigns.map((campaign) => (
              <button
                key={campaign.id}
                onClick={() => { setSelectedList(campaign.id); setImportCampaignId(campaign.id); }}
                className={`w-full flex items-center justify-between gap-2 px-3 py-2 text-xs font-medium rounded-xl transition-colors ${
                  selectedList === campaign.id ? 'bg-indigo-50 text-indigo-700 font-bold' : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                <span className="truncate">{campaign.name}</span>
                <span className="text-[11px] font-semibold text-gray-600">{campaign.leads_count || 0}</span>
              </button>
            ))}
            {!campaigns.length && (
              <p className="px-3 py-2 text-xs text-gray-500">Create a campaign to start importing contacts.</p>
            )}
          </div>
        </div>

        <button
          onClick={campaigns.length ? openImport : onOpenWizard}
          className="w-full flex items-center justify-center gap-2 py-2 text-xs font-semibold text-indigo-600 border border-indigo-200 rounded-xl hover:bg-indigo-50 transition-colors shadow-2xs"
        >
          <Plus className="h-3.5 w-3.5" />
          {campaigns.length ? 'Import contacts' : 'Create campaign'}
        </button>
      </div>

      {/* Main CRM Area */}
      <div className="flex-1 px-8 py-7 overflow-y-auto h-full min-h-0">
        {/* Top Actions Row with Prosp Switcher matching prosp_crm_kanban.jpg */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Leads</h1>
            <p className="text-xs text-gray-400 mt-0.5">
              {total} leads {selectedList === 'all' ? 'in this workspace' : `in ${campaignName(selectedList)}`}
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <button onClick={() => setAudiencesOpen(true)} className="rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700">Audience lists</button>
            {/* View Mode Switcher [ = | 00 ] */}
            <div className="flex items-center bg-gray-100/90 p-0.5 rounded-xl border border-gray-200/80 shadow-2xs">
              <button
                onClick={() => handleSetViewMode('table')}
                className={`p-1.5 rounded-lg text-xs transition-all ${
                  viewMode === 'table'
                    ? 'bg-white text-gray-900 shadow-xs font-bold'
                    : 'text-gray-500 hover:text-gray-800'
                }`}
                title="Table view (=)"
              >
                <List className="h-4 w-4" />
              </button>
              <button
                onClick={() => handleSetViewMode('kanban')}
                className={`p-1.5 rounded-lg text-xs transition-all ${
                  viewMode === 'kanban'
                    ? 'bg-white text-gray-900 shadow-xs font-bold'
                    : 'text-gray-500 hover:text-gray-800'
                }`}
                title="Kanban columns (00)"
              >
                <Columns className="h-4 w-4" />
              </button>
            </div>

            <button
              onClick={handleExport}
              disabled={exporting || !total}
              className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-gray-700 hover:bg-gray-50 shadow-2xs transition-colors disabled:opacity-50"
            >
              <Download className="h-3.5 w-3.5 text-gray-500" />
              {exporting ? 'Exporting...' : 'Export CSV'}
            </button>

            <select
              aria-label="Import contacts into campaign"
              value={importCampaignId}
              onChange={(e) => setImportCampaignId(e.target.value)}
              className="rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-700 max-w-44"
            >
              {!campaigns.length && <option value="">No campaigns</option>}
              {campaigns.map((campaign) => (
                <option key={campaign.id} value={campaign.id}>{campaign.name}</option>
              ))}
            </select>
            <button
              onClick={campaigns.length ? openImport : onOpenWizard}
              disabled={!importCampaignId}
              className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 shadow-xs transition-colors disabled:opacity-50"
            >
              <Plus className="h-3.5 w-3.5" />
              Import contacts
            </button>
          </div>
        </div>

        {/* Filter Bar matching prosp_crm_kanban.jpg */}
        <div className="flex flex-wrap items-center gap-3 mb-6">
          <div className="relative flex-1 min-w-[240px] max-w-md">
            <Search className="absolute left-3.5 top-2.5 h-3.5 w-3.5 text-gray-400" />
            <input
              type="text"
              placeholder="Search leads by name, title, or company..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-xl border border-gray-200 bg-white pl-9 pr-4 py-2 text-xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 shadow-2xs"
            />
          </div>

          <div className="relative">
            <select
              value={selectedState}
              onChange={(e) => setSelectedState(e.target.value)}
              className="rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-xs font-medium text-gray-700 shadow-2xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 cursor-pointer"
            >
              <option value="">All statuses</option>
              <option value="queued">Queued</option>
              <option value="waiting_delay">Waiting delay</option>
              <option value="waiting_trigger">Waiting trigger</option>
              <option value="accepted">Accepted</option>
              <option value="replied">Replied</option>
              <option value="finished">Finished</option>
              <option value="bounced">Bounced</option>
              <option value="failed">Failed</option>
            </select>
          </div>

          <div className="relative">
            <select
              value={selectedStage}
              onChange={(e) => setSelectedStage(e.target.value)}
              className="rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-xs font-medium text-gray-700 shadow-2xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 cursor-pointer"
            >
              <option value="">All stages</option>
              {PIPELINE_STAGES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>

          <div className="relative">
            <select
              aria-label="Filter leads by source"
              value={selectedSource}
              onChange={(e) => setSelectedSource(e.target.value)}
              className="rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-xs font-medium text-gray-700 shadow-2xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 cursor-pointer"
            >
              <option value="">All sources</option>
              <option value="csv">CSV upload</option>
              <option value="pasted_urls">Pasted URLs</option>
              <option value="staged_preview">Reviewed import</option>
              <option value="linkedin_search">LinkedIn search</option>
              <option value="post_engagers">Post engagers</option>
              <option value="my_network">My network</option>
            </select>
          </div>

          <div className="relative">
            <select
              aria-label="Filter leads by action performed"
              value={selectedActionPerformed}
              onChange={(e) => setSelectedActionPerformed(e.target.value)}
              className="rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-xs font-medium text-gray-700 shadow-2xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 cursor-pointer"
            >
              <option value="">Actions performed</option>
              <option value="ready_to_enter">Ready to enter campaign</option>
              <option value="invite_sent">Invite sent</option>
              <option value="invite_accepted">Invite accepted</option>
              <option value="invite_pending">Invite pending</option>
              <option value="messaged">Messaged</option>
              <option value="replied">Replied</option>
              <option value="profile_viewed">Profile viewed</option>
              <option value="liked_post">Liked a post</option>
              <option value="endorsed">Endorsed skill</option>
            </select>
          </div>

          <div className="relative">
            <select
              aria-label="Filter leads by failure reason"
              value={selectedFailureReason}
              onChange={(e) => setSelectedFailureReason(e.target.value)}
              className="rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-xs font-medium text-gray-700 shadow-2xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 cursor-pointer"
            >
              <option value="">All failure reasons</option>
              <option value="missing_profile_variable">Missing profile variable</option>
              <option value="note_exceeds_300_chars">Invite note &gt; 300 chars</option>
              <option value="duplicate_message">Duplicate message blocked</option>
              <option value="not_first_degree">Not 1st-degree connection</option>
            </select>
          </div>

          <button
            type="button"
            onClick={() => setCustomFilterModalOpen(true)}
            className={`inline-flex items-center gap-1 rounded-xl border px-3 py-2 text-xs font-semibold shadow-2xs transition-colors ${
              includeActionsFilter || excludeActionsFilter
                ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
                : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'
            }`}
            title="Create or apply Include / Exclude action filter"
          >
            <Plus className="h-3.5 w-3.5" /> Add Filter
          </button>

          {(includeActionsFilter || excludeActionsFilter) && (
            <button
              type="button"
              onClick={() => { setIncludeActionsFilter(''); setExcludeActionsFilter(''); }}
              className="inline-flex items-center gap-1 rounded-xl border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[11px] font-semibold text-amber-800"
            >
              <span>Custom Filter Active</span>
              <X className="h-3 w-3" />
            </button>
          )}

          {customFilters.map((cf) => {
            const isActive =
              includeActionsFilter === (cf.include_actions || []).join(',') &&
              excludeActionsFilter === (cf.exclude_actions || []).join(',');
            return (
              <div key={cf.id} className="inline-flex items-center rounded-full border border-gray-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-gray-700 gap-1.5 shadow-2xs">
                <button
                  type="button"
                  onClick={() => {
                    if (isActive) {
                      setIncludeActionsFilter('');
                      setExcludeActionsFilter('');
                    } else {
                      setIncludeActionsFilter((cf.include_actions || []).join(','));
                      setExcludeActionsFilter((cf.exclude_actions || []).join(','));
                    }
                  }}
                  className={isActive ? 'text-indigo-700 font-bold' : 'text-gray-700 hover:text-indigo-600'}
                >
                  {cf.name}
                </button>
                <button
                  type="button"
                  onClick={() => handleDeleteCustomFilter(cf.id)}
                  className="text-gray-400 hover:text-red-600"
                  title={`Delete ${cf.name}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            );
          })}

          <div className="relative">
            <input
              type="search"
              aria-label="Filter leads by location"
              placeholder="Filter location"
              value={selectedLocation}
              onChange={(e) => setSelectedLocation(e.target.value)}
              className="rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-xs font-medium text-gray-700 shadow-2xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 cursor-pointer"
            />
          </div>

          <select
            aria-label="Filter leads by tag"
            value={selectedTagFilter.includes(',') ? '' : selectedTagFilter}
            onChange={(event) => setSelectedTagFilter(event.target.value)}
            className="rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-xs font-medium text-gray-700 shadow-2xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">All tags</option>
            <option value="__untagged__">Untagged</option>
            {tagDefinitions.map((tag) => <option key={tag.id} value={tag.id}>{tag.name}</option>)}
          </select>

          <button
            onClick={() => setTagManagerOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 shadow-2xs"
          >
            <Tag className="h-3.5 w-3.5 text-gray-400" /> Manage tags
          </button>

          {tagDefinitions.length > 0 && selectedTagFilter !== '__untagged__' && (
            <div className="flex flex-wrap items-center gap-1.5">
              {tagDefinitions.map((tag) => {
                const selectedIds = selectedTagFilter ? selectedTagFilter.split(',').filter(Boolean) : [];
                const active = selectedIds.includes(tag.id);
                return (
                  <button
                    key={`lead-tag-chip:${tag.id}`}
                    type="button"
                    onClick={() => {
                      const next = active ? selectedIds.filter((id) => id !== tag.id) : [...selectedIds, tag.id];
                      setSelectedTagFilter(next.join(','));
                    }}
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-all ${
                      active ? 'ring-1 ring-indigo-600 bg-indigo-50 text-indigo-700 border-indigo-300' : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: tag.color || '#6366f1' }} />
                    {tag.name}
                  </button>
                );
              })}
              {selectedTagFilter.includes(',') && (
                <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-0.5 text-[10px]">
                  <button
                    type="button"
                    onClick={() => setTagMatchMode('all')}
                    className={`px-2 py-0.5 rounded-md font-semibold ${tagMatchMode === 'all' ? 'bg-white text-gray-900 shadow-2xs' : 'text-gray-500'}`}
                  >
                    Match All
                  </button>
                  <button
                    type="button"
                    onClick={() => setTagMatchMode('any')}
                    className={`px-2 py-0.5 rounded-md font-semibold ${tagMatchMode === 'any' ? 'bg-white text-gray-900 shadow-2xs' : 'text-gray-500'}`}
                  >
                    Match Any
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Columns Visibility Picker matching Prosp Columns */}
          <div className="relative">
            <button
              onClick={() => setColumnPickerOpen((prev) => !prev)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 shadow-2xs transition-colors"
            >
              <Columns className="w-3.5 h-3.5 text-gray-400" />
              <span>Columns</span>
              <ChevronDown className="w-3 h-3 text-gray-400" />
            </button>

            {columnPickerOpen && (
              <div className="absolute right-0 mt-1.5 w-44 rounded-xl border border-gray-200 bg-white p-2 shadow-lg z-20 space-y-1 text-xs">
                <label className="flex items-center gap-2 px-2 py-1 hover:bg-gray-50 rounded-lg cursor-pointer">
                  <input type="checkbox" checked={visibleColumns.pipelineStage} onChange={(e) => setVisibleColumns((prev) => ({ ...prev, pipelineStage: e.target.checked }))} />
                  <span>Pipeline stage</span>
                </label>
                <label className="flex items-center gap-2 px-2 py-1 hover:bg-gray-50 rounded-lg cursor-pointer">
                  <input type="checkbox" checked={visibleColumns.executionState} onChange={(e) => setVisibleColumns((prev) => ({ ...prev, executionState: e.target.checked }))} />
                  <span>Execution status</span>
                </label>
                <label className="flex items-center gap-2 px-2 py-1 hover:bg-gray-50 rounded-lg cursor-pointer">
                  <input type="checkbox" checked={visibleColumns.lastAction} onChange={(e) => setVisibleColumns((prev) => ({ ...prev, lastAction: e.target.checked }))} />
                  <span>Last action</span>
                </label>
                <label className="flex items-center gap-2 px-2 py-1 hover:bg-gray-50 rounded-lg cursor-pointer">
                  <input
                    type="checkbox"
                    checked={visibleColumns.company}
                    onChange={(e) => setVisibleColumns((prev) => ({ ...prev, company: e.target.checked }))}
                    className="rounded text-indigo-600 focus:ring-0"
                  />
                  <span>Company</span>
                </label>
                <label className="flex items-center gap-2 px-2 py-1 hover:bg-gray-50 rounded-lg cursor-pointer">
                  <input
                    type="checkbox"
                    checked={visibleColumns.jobTitle}
                    onChange={(e) => setVisibleColumns((prev) => ({ ...prev, jobTitle: e.target.checked }))}
                    className="rounded text-indigo-600 focus:ring-0"
                  />
                  <span>Job title</span>
                </label>
                <label className="flex items-center gap-2 px-2 py-1 hover:bg-gray-50 rounded-lg cursor-pointer">
                  <input
                    type="checkbox"
                    checked={visibleColumns.location}
                    onChange={(e) => setVisibleColumns((prev) => ({ ...prev, location: e.target.checked }))}
                    className="rounded text-indigo-600 focus:ring-0"
                  />
                  <span>Location</span>
                </label>
                <label className="flex items-center gap-2 px-2 py-1 hover:bg-gray-50 rounded-lg cursor-pointer">
                  <input
                    type="checkbox"
                    checked={visibleColumns.email}
                    onChange={(e) => setVisibleColumns((prev) => ({ ...prev, email: e.target.checked }))}
                    className="rounded text-indigo-600 focus:ring-0"
                  />
                  <span>Email</span>
                </label>
              </div>
            )}
          </div>

          <button
            onClick={() => { fetchLeads(); fetchCampaigns(); }}
            className="p-2 rounded-xl bg-white border border-gray-200 text-gray-500 hover:text-gray-800 hover:bg-gray-50 shadow-2xs transition-colors"
            title="Refresh leads"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {tagLoadError && (
          <div role="alert" className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700">
            <p>{tagLoadError}</p><button onClick={fetchTags} className="mt-2 font-semibold">Retry loading lead tags</button>
          </div>
        )}
        {error && (
          <div role="alert" className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700 flex justify-between gap-3">
            <span>{error}</span>
            <button onClick={() => setError('')} aria-label="Dismiss error"><X className="h-4 w-4" /></button>
          </div>
        )}

        {selectedLeadIds.length > 0 && (
          <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-xs">
            <strong className="text-indigo-900">{selectedLeadIds.length} selected</strong>
            <select aria-label="Bulk tag" value={bulkTagId} onChange={(event) => setBulkTagId(event.target.value)} className="rounded-lg border border-indigo-200 bg-white px-2 py-1.5">
              {!tagDefinitions.length && <option value="">Create a tag first</option>}
              {tagDefinitions.map((tag) => <option key={tag.id} value={tag.id}>{tag.name}</option>)}
            </select>
            <button disabled={bulkBusy || !bulkTagId} onClick={() => handleBulkTag('add')} className="rounded-lg bg-indigo-600 px-3 py-1.5 font-semibold text-white disabled:opacity-50">Add tag</button>
            <button disabled={bulkBusy || !bulkTagId} onClick={() => handleBulkTag('remove')} className="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 font-semibold text-indigo-700 disabled:opacity-50">Remove tag</button>
            <button disabled={bulkBusy} onClick={() => setFollowUpSelection([...selectedLeadIds])} className="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 font-semibold text-indigo-700">Review follow-up draft</button>
            <button onClick={() => setSelectedLeadIds([])} className="ml-auto text-indigo-700 underline">Clear</button>
          </div>
        )}

        {/* Loading Indicator */}
        {loading ? (
          <div className="flex items-center justify-center py-24 text-gray-400">
            <RefreshCw className="h-6 w-6 animate-spin" />
          </div>
        ) : displayedLeads.length === 0 ? (
          <div className="rounded-2xl border border-gray-200/90 bg-white p-16 text-center text-gray-500 shadow-2xs">
            <p className="text-xs text-gray-500 font-medium">No leads match the current filters.</p>
            <button
              onClick={campaigns.length ? openImport : onOpenWizard}
              className="mt-2 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors cursor-pointer"
            >
              + Import contacts
            </button>
          </div>
        ) : viewMode === 'kanban' ? (
          /* Kanban Vertical Stack Board matching prosp_crm_kanban.jpg */
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 items-start pb-8">
            {PIPELINE_STAGES.map((stage) => {
              const columnLeads = displayedLeads.filter(
                (l) => (l.pipeline_stage || 'unassigned') === stage.id
              );

              return (
                <div
                  key={stage.id}
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDrop(e, stage.id)}
                  className="bg-gray-100/60 rounded-2xl p-3 border border-gray-200/70 min-h-[500px] flex flex-col transition-colors"
                >
                  {/* Column Header matching prosp_crm_kanban.jpg */}
                  <div className="flex items-center justify-between mb-3 px-1">
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${stage.dotColor}`} />
                      <span className="text-xs font-bold text-gray-800 tracking-tight">
                        {stage.label}
                      </span>
                    </div>
                    <span className="text-[11px] font-semibold text-gray-500">
                      {columnLeads.length} on this page
                    </span>
                  </div>

                  {/* Column Lead Cards */}
                  <div className="space-y-2.5 flex-1 overflow-y-auto">
                    {columnLeads.map((lead) => {
                      const fullName =
                        lead.first_name || lead.last_name
                          ? `${lead.first_name || ''} ${lead.last_name || ''}`.trim()
                          : 'LinkedIn Member';

                      return (
                        <div
                          key={lead.id}
                          draggable
                          onDragStart={(e) => handleDragStart(e, lead.id)}
                          onClick={() => setSelectedLead(lead)}
                          className="bg-white rounded-xl border border-gray-200/90 p-3.5 shadow-2xs hover:shadow-md hover:border-indigo-300 transition-all cursor-pointer group relative"
                        >
                          <label className="mb-2 flex items-center gap-1.5 text-[10px] font-medium text-gray-500" onClick={(event) => event.stopPropagation()}>
                            <input aria-label={`Select ${fullName}`} type="checkbox" checked={selectedLeadIds.includes(lead.id)} onChange={() => toggleSelected(lead.id)} className="rounded border-gray-300 text-indigo-600" />
                            Select
                          </label>
                          {/* Card Top: Avatar, Name, LinkedIn badge */}
                          <div className="flex items-start gap-2.5">
                            {lead.avatar_url ? (
                              <img
                                src={lead.avatar_url}
                                alt={fullName}
                                className="w-8 h-8 rounded-full object-cover shrink-0"
                              />
                            ) : (
                              <div className="w-8 h-8 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-[10px] shrink-0">
                                {getInitials(lead.first_name, lead.last_name)}
                              </div>
                            )}

                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="text-xs font-bold text-gray-900 truncate">
                                  {fullName}
                                </span>
                                {lead.do_not_contact && <Ban className="h-3.5 w-3.5 text-red-600" aria-label="Do-Not-Contact" />}
                                {lead.linkedin_url && (
                                  <a
                                    href={lead.linkedin_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="inline-flex items-center justify-center w-4 h-4 rounded bg-[#0077b5] text-white text-[9px] font-bold hover:opacity-90"
                                    title="Open LinkedIn profile"
                                  >
                                    in
                                  </a>
                                )}
                              </div>
                              {lead.job_title && (
                                <p className="text-[11px] text-gray-600 truncate mt-0.5">
                                  {lead.job_title}
                                </p>
                              )}
                            </div>

                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteLead(lead.id);
                              }}
                              disabled={deletingLeadId === lead.id}
                              className="text-gray-300 hover:text-red-600 p-0.5 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity disabled:opacity-50"
                              title="Delete contact"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>

                          {!!lead.tags?.length && (
                            <div className="mt-2 flex flex-wrap gap-1">
                              {lead.tags.map((tag) => (
                                <span key={tag.id} className="rounded-full border px-1.5 py-0.5 text-[9px] font-semibold" style={{ color: tag.color, borderColor: `${tag.color}55`, backgroundColor: `${tag.color}12` }}>{tag.name}</span>
                              ))}
                            </div>
                          )}

                          {/* Card Attributes: Company, Location/Country, Phone */}
                          <div className="mt-3 pt-2.5 border-t border-gray-100 space-y-1.5 text-[11px] text-gray-600">
                            {lead.company_name && (
                              <div className="flex items-center gap-1.5 truncate">
                                <Building className="w-3 h-3 text-gray-400 shrink-0" />
                                <span className="truncate">{lead.company_name}</span>
                              </div>
                            )}

                            {displayLocation(lead) && (
                              <div className="flex items-center gap-1.5 truncate">
                                <MapPin className="w-3 h-3 text-gray-400 shrink-0" />
                                <span className="truncate font-mono uppercase text-[10px]">
                                  {displayLocation(lead)}
                                </span>
                              </div>
                            )}

                            {lead.phone && (
                              <div className="flex items-center gap-1.5 truncate">
                                <Phone className="w-3 h-3 text-gray-400 shrink-0" />
                                <span className="truncate font-mono text-[10px]">{lead.phone}</span>
                              </div>
                            )}

                            {lead.last_action_taken && (
                              <div className="flex items-center justify-between text-[10px] text-indigo-700 bg-indigo-50/70 rounded-lg px-2 py-0.5 font-semibold">
                                <span>Last: {String(lead.last_action_taken).replace(/_/g, ' ')}</span>
                              </div>
                            )}

                            {(lead.failure_code || lead.failure_reason) && (
                              <div className="text-[10px] text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-2 py-0.5 font-medium truncate" title={lead.failure_reason || lead.failure_code}>
                                ⚠ {lead.failure_reason || String(lead.failure_code).replace(/_/g, ' ')}
                              </div>
                            )}
                          </div>

                          {/* Card Footer: Stage Quick-Changer */}
                          <div
                            className="mt-3 pt-2 border-t border-gray-50 flex items-center justify-between"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <select
                              value={lead.pipeline_stage || 'unassigned'}
                              onChange={(e) => handleUpdateStage(lead.id, e.target.value)}
                              disabled={updatingLeadId === lead.id}
                              className="text-[10px] font-medium text-gray-600 bg-gray-50 border border-gray-200 rounded-lg px-2 py-0.5 cursor-pointer focus:ring-0"
                            >
                              {PIPELINE_STAGES.map((s) => (
                                <option key={s.id} value={s.id}>
                                  {s.label}
                                </option>
                              ))}
                            </select>

                            {stage.id !== 'call_booked' && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleAdvanceStage(lead);
                                }}
                                disabled={updatingLeadId === lead.id}
                                className="inline-flex items-center gap-1 text-[10px] font-semibold text-indigo-600 hover:text-indigo-800 transition-colors p-1"
                                title="Advance to next pipeline stage"
                              >
                                <span>Advance</span>
                                <ArrowRight className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          /* Table View matching media_1790103640399.png */
          <div className="rounded-2xl border border-gray-200/90 bg-white shadow-2xs overflow-hidden">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-gray-200 bg-gray-50/70 text-gray-500 uppercase font-semibold tracking-wider text-[10px]">
                <tr>
                  <th className="py-3 px-4">
                    <input aria-label="Select all leads on this page" type="checkbox" checked={displayedLeads.length > 0 && displayedLeads.every((lead) => selectedLeadIds.includes(lead.id))} onChange={(event) => {
                      const pageIds = displayedLeads.map((lead) => lead.id);
                      setSelectedLeadIds((current) => event.target.checked
                        ? Array.from(new Set([...current, ...pageIds]))
                        : current.filter((id) => !pageIds.includes(id)));
                    }} className="rounded border-gray-300 text-indigo-600" />
                  </th>
                  <th className="py-3 px-4">Contact</th>
                  <th className="py-3 px-4">Tags</th>
                  {visibleColumns.pipelineStage && <th className="py-3 px-4">Pipeline Stage</th>}
                  {visibleColumns.executionState && <th className="py-3 px-4">Execution Status</th>}
                  {visibleColumns.lastAction && <th className="py-3 px-4">Last Action</th>}
                  {visibleColumns.company && <th className="py-3 px-4">Company</th>}
                  {visibleColumns.jobTitle && <th className="py-3 px-4">Job Title</th>}
                  {visibleColumns.location && <th className="py-3 px-4">Location</th>}
                  {visibleColumns.email && <th className="py-3 px-4">Email</th>}
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {displayedLeads.map((lead) => {
                  const fullName =
                    lead.first_name || lead.last_name
                      ? `${lead.first_name || ''} ${lead.last_name || ''}`.trim()
                      : 'LinkedIn Member';

                  return (
                    <tr
                      key={lead.id}
                      onClick={() => setSelectedLead(lead)}
                      className="hover:bg-gray-50/60 transition-colors cursor-pointer"
                    >
                      <td className="py-3 px-4" onClick={(event) => event.stopPropagation()}>
                        <input aria-label={`Select ${fullName}`} type="checkbox" checked={selectedLeadIds.includes(lead.id)} onChange={() => toggleSelected(lead.id)} className="rounded border-gray-300 text-indigo-600" />
                      </td>
                      <td className="py-3 px-4 font-semibold text-gray-900">
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-6 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-[9px] shrink-0">
                            {getInitials(lead.first_name, lead.last_name)}
                          </div>
                          <a
                            href={lead.linkedin_url}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="hover:text-indigo-600 hover:underline flex items-center gap-1"
                          >
                            <span>{fullName}</span>
                            {lead.do_not_contact && <Ban className="h-3.5 w-3.5 text-red-600" aria-label="Do-Not-Contact" />}
                            <ExternalLink className="w-3 h-3 text-gray-400" />
                          </a>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex max-w-48 flex-wrap gap-1">
                          {(lead.tags || []).map((tag) => <span key={tag.id} className="rounded-full border px-1.5 py-0.5 text-[9px] font-semibold" style={{ color: tag.color, borderColor: `${tag.color}55`, backgroundColor: `${tag.color}12` }}>{tag.name}</span>)}
                          {!lead.tags?.length && <span className="text-gray-400">—</span>}
                        </div>
                      </td>
                      {visibleColumns.pipelineStage && (
                        <td className="py-3 px-4" onClick={(e) => e.stopPropagation()}>
                          <select
                            value={lead.pipeline_stage || 'unassigned'}
                            onChange={(e) => handleUpdateStage(lead.id, e.target.value)}
                            disabled={updatingLeadId === lead.id}
                            className="rounded-lg border border-gray-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-gray-700 shadow-2xs focus:ring-indigo-500 cursor-pointer"
                          >
                            {PIPELINE_STAGES.map((s) => (
                              <option key={s.id} value={s.id}>
                                {s.label}
                              </option>
                            ))}
                          </select>
                        </td>
                      )}
                      {visibleColumns.executionState && (
                        <td className="py-3 px-4">
                          <div className="flex flex-col items-start gap-1">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${
                                lead.execution_state === 'replied'
                                  ? 'bg-emerald-50 text-emerald-700'
                                  : lead.execution_state === 'accepted'
                                  ? 'bg-indigo-50 text-indigo-700'
                                  : 'bg-gray-100 text-gray-600'
                              }`}
                            >
                              {lead.execution_state}
                            </span>
                            {(lead.failure_code || lead.failure_reason) && (
                              <span className="text-[10px] text-rose-700 bg-rose-50 border border-rose-200 rounded px-1.5 py-0.5 font-medium truncate max-w-[160px]" title={lead.failure_reason || lead.failure_code}>
                                ⚠ {String(lead.failure_code || lead.failure_reason).replace(/_/g, ' ')}
                              </span>
                            )}
                          </div>
                        </td>
                      )}
                      {visibleColumns.lastAction && (
                        <td className="py-3 px-4 text-gray-600 capitalize">
                          {lead.last_action_taken ? String(lead.last_action_taken).replace(/_/g, ' ') : '—'}
                        </td>
                      )}
                      {visibleColumns.company && <td className="py-3 px-4 text-gray-600">{lead.company_name || '—'}</td>}
                      {visibleColumns.jobTitle && <td className="py-3 px-4 text-gray-600 truncate max-w-xs">{lead.job_title || '—'}</td>}
                      {visibleColumns.location && (
                        <td className="py-3 px-4 text-gray-500">
                          {displayLocation(lead) || '—'}
                        </td>
                      )}
                      {visibleColumns.email && <td className="py-3 px-4 text-gray-500">{lead.email || '—'}</td>}
                      <td className="py-3 px-4 text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="inline-flex items-center justify-end gap-1.5">
                          {lead.execution_state !== 'staged' && (
                            <button
                              type="button"
                              onClick={() => handleToggleSequencePause(lead)}
                              disabled={updatingLeadId === lead.id}
                              className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-semibold border transition-colors cursor-pointer ${
                                lead.execution_state === 'paused' || lead.execution_state === 'replied'
                                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100'
                                  : 'bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100'
                              }`}
                              title={lead.execution_state === 'paused' || lead.execution_state === 'replied' ? 'Resume sequence' : 'Pause sequence'}
                            >
                              {lead.execution_state === 'paused' || lead.execution_state === 'replied' ? (
                                <Play className="h-3 w-3" />
                              ) : (
                                <Pause className="h-3 w-3" />
                              )}
                              <span>{lead.execution_state === 'paused' || lead.execution_state === 'replied' ? 'Resume' : 'Pause'}</span>
                            </button>
                          )}
                          <button
                            onClick={() => handleDeleteLead(lead.id)}
                            disabled={deletingLeadId === lead.id}
                            className="text-gray-400 hover:text-red-600 p-1 transition-colors"
                            title="Delete contact"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
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
        {total > 0 && (
          <div className="mt-4 flex items-center justify-between text-xs text-gray-600">
            <span>Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total}</span>
            <div className="flex gap-2">
              <button onClick={() => setPage((current) => current - 1)} disabled={page === 0 || loading} className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 disabled:opacity-50">Previous</button>
              <button onClick={() => setPage((current) => current + 1)} disabled={(page + 1) * PAGE_SIZE >= total || loading} className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 disabled:opacity-50">Next</button>
            </div>
          </div>
        )}
      </div>

      {audiencesOpen && <AudienceListsPanel campaigns={campaigns} initialCampaignId={selectedList === 'all' ? importCampaignId : selectedList}
        selectedLeadIds={selectedLeadIds} onClose={() => setAudiencesOpen(false)} onChanged={() => { fetchLeads(); fetchCampaigns(); }} />}

      {/* Import Modal */}
      <ImportLeadsModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        campaignId={importCampaignId}
        onLeadsImported={() => {
          if (selectedList === importCampaignId && page === 0) fetchLeads();
          setSelectedList(importCampaignId);
          setPage(0);
          fetchCampaigns();
        }}
      />

      {/* Slide-over Lead Details & Activity Drawer */}
      <LeadActivityDrawer
        leadId={selectedLead?.id}
        isOpen={!!selectedLead}
        onClose={() => setSelectedLead(null)}
        onLeadUpdated={() => fetchLeads()}
        onDeleteLead={(id) => handleDeleteLead(id)}
      />

      {tagManagerOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setTagManagerOpen(false)}>
          <div className="max-h-[85vh] w-full max-w-xl overflow-y-auto" onClick={(event) => event.stopPropagation()}>
            <div className="mb-2 flex justify-end"><button aria-label="Close tag manager" onClick={() => setTagManagerOpen(false)} className="rounded-full bg-white p-2 text-gray-600 shadow"><X className="h-4 w-4" /></button></div>
            <LeadTagManager onChanged={() => { fetchTags(); fetchLeads(); }} />
          </div>
        </div>
      )}
      {followUpSelection && <LeadSelectionReview leadIds={followUpSelection} onClose={() => setFollowUpSelection(null)} onCreated={(result) => {
        setFollowUpSelection(null); setSelectedLeadIds([]); fetchCampaigns();
        onOpenWizard?.(result.campaign_id, 1, result.name);
      }} />}

      {/* Custom Include / Exclude Action Filter Builder Modal (Dripify Video #15 Parity) */}
      {customFilterModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setCustomFilterModalOpen(false)}>
          <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl border border-gray-100 space-y-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between pb-3 border-b border-gray-100">
              <div>
                <h3 className="text-sm font-bold text-gray-900">Create Custom Action Filter</h3>
                <p className="text-[11px] text-gray-500">Combine Include & Exclude actions (e.g., Ignored Messages)</p>
              </div>
              <button type="button" onClick={() => setCustomFilterModalOpen(false)} className="p-1 text-gray-400 hover:bg-gray-100 rounded-lg">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-[10px] font-bold uppercase text-gray-500 mb-1">Filter Name</label>
                <input
                  type="text"
                  placeholder="e.g., Ignored Messages"
                  value={newFilterName}
                  onChange={(e) => setNewFilterName(e.target.value)}
                  className="w-full rounded-xl border border-gray-200 px-3 py-2 text-xs focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase text-emerald-700 mb-1">Include Actions Performed</label>
                <div className="flex flex-wrap gap-1.5">
                  {[
                    { id: 'invite_sent', label: 'Invite sent' },
                    { id: 'invite_accepted', label: 'Invite accepted' },
                    { id: 'messaged', label: 'Messaged' },
                    { id: 'replied', label: 'Replied' },
                    { id: 'profile_viewed', label: 'Profile viewed' },
                    { id: 'liked_post', label: 'Liked post' },
                    { id: 'endorsed', label: 'Endorsed' },
                  ].map((act) => {
                    const active = newFilterInclude.includes(act.id);
                    return (
                      <button
                        key={`inc:${act.id}`}
                        type="button"
                        onClick={() => setNewFilterInclude((prev) => active ? prev.filter((x) => x !== act.id) : [...prev, act.id])}
                        className={`px-2.5 py-1 rounded-lg border text-[11px] font-semibold transition-colors ${
                          active ? 'bg-emerald-50 border-emerald-300 text-emerald-800' : 'bg-gray-50 border-gray-200 text-gray-600'
                        }`}
                      >
                        {active ? '✓ ' : '+ '}{act.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="block text-[10px] font-bold uppercase text-rose-700 mb-1">Exclude Actions Performed</label>
                <div className="flex flex-wrap gap-1.5">
                  {[
                    { id: 'invite_accepted', label: 'Invite accepted' },
                    { id: 'messaged', label: 'Messaged' },
                    { id: 'replied', label: 'Replied' },
                  ].map((act) => {
                    const active = newFilterExclude.includes(act.id);
                    return (
                      <button
                        key={`exc:${act.id}`}
                        type="button"
                        onClick={() => setNewFilterExclude((prev) => active ? prev.filter((x) => x !== act.id) : [...prev, act.id])}
                        className={`px-2.5 py-1 rounded-lg border text-[11px] font-semibold transition-colors ${
                          active ? 'bg-rose-50 border-rose-300 text-rose-800' : 'bg-gray-50 border-gray-200 text-gray-600'
                        }`}
                      >
                        {active ? '✕ ' : '– '}{act.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-gray-100">
              <button
                type="button"
                onClick={() => {
                  setIncludeActionsFilter(newFilterInclude.join(','));
                  setExcludeActionsFilter(newFilterExclude.join(','));
                  setCustomFilterModalOpen(false);
                }}
                disabled={!newFilterInclude.length && !newFilterExclude.length}
                className="px-3.5 py-2 rounded-xl border border-gray-200 text-xs font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                Apply Without Saving
              </button>
              <button
                type="button"
                onClick={handleSaveCustomFilter}
                disabled={savingCustomFilter || !newFilterName.trim() || (!newFilterInclude.length && !newFilterExclude.length)}
                className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold disabled:opacity-50"
              >
                {savingCustomFilter ? 'Saving…' : 'Save & Apply Filter'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
