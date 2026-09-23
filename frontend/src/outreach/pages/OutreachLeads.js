import React, { useState, useEffect } from 'react';
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
  Filter,
} from 'lucide-react';
import ImportLeadsModal from '../components/ImportLeadsModal';

const PIPELINE_STAGES = [
  { id: 'unassigned', label: 'Unassigned', dotColor: 'bg-gray-400', textColor: 'text-gray-600', countBadge: 'bg-gray-100 text-gray-700' },
  { id: 'in_campaign', label: 'In Campaign', dotColor: 'bg-amber-400', textColor: 'text-amber-700', countBadge: 'bg-amber-50 text-amber-800' },
  { id: 'contacted', label: 'Contacted', dotColor: 'bg-purple-500', textColor: 'text-purple-700', countBadge: 'bg-purple-50 text-purple-800' },
  { id: 'replied', label: 'Replied', dotColor: 'bg-emerald-500', textColor: 'text-emerald-700', countBadge: 'bg-emerald-50 text-emerald-800' },
  { id: 'call_booked', label: 'call booked', dotColor: 'bg-rose-500', textColor: 'text-rose-700', countBadge: 'bg-rose-50 text-rose-800' },
];

export default function OutreachLeads() {
  const [leads, setLeads] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedState, setSelectedState] = useState('');
  const [selectedStage, setSelectedStage] = useState('');
  const [selectedLocation, setSelectedLocation] = useState('');
  const [selectedLead, setSelectedLead] = useState(null);
  const [columnPickerOpen, setColumnPickerOpen] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState({
    pipelineStage: true,
    executionState: true,
    company: true,
    jobTitle: true,
    location: true,
    email: true,
  });
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedList, setSelectedList] = useState('all');
  const [viewMode, setViewMode] = useState(() => {
    return localStorage.getItem('outreach_leads_view_mode') || 'kanban';
  });
  const [draggedLeadId, setDraggedLeadId] = useState(null);

  const handleSetViewMode = (mode) => {
    setViewMode(mode);
    localStorage.setItem('outreach_leads_view_mode', mode);
  };

  const fetchLeads = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const params = new URLSearchParams();
      if (searchQuery) params.append('search', searchQuery);
      if (selectedState) params.append('execution_state', selectedState);
      if (selectedStage) params.append('pipeline_stage', selectedStage);

      const res = await fetch(`/api/v1/outreach/leads?${params.toString()}`, {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setLeads(data.leads || []);
        setTotal(data.total || 0);
      }
    } catch (err) {
      console.error('Failed to fetch leads:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLeads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, selectedState, selectedStage]);

  const handleDeleteLead = async (leadId) => {
    if (!window.confirm('Delete this contact?')) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/leads/${leadId}`, {
        method: 'DELETE',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        setLeads((prev) => prev.filter((l) => l.id !== leadId));
        setTotal((prev) => Math.max(0, prev - 1));
      }
    } catch (err) {
      console.error('Delete lead failed:', err);
    }
  };

  const handleUpdateStage = async (leadId, newStage) => {
    // Optimistic local update
    setLeads((prev) =>
      prev.map((l) => (l.id === leadId ? { ...l, pipeline_stage: newStage } : l))
    );

    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/leads/${leadId}/stage`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ pipeline_stage: newStage }),
      });
      if (!res.ok) {
        console.error('Failed to update stage on server');
        fetchLeads();
      }
    } catch (err) {
      console.error('Error updating stage:', err);
      fetchLeads();
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

  const availableLocations = Array.from(
    new Set(
      leads
        .map((l) => l.country_code || l.location)
        .filter((loc) => Boolean(loc && typeof loc === 'string' && loc.trim()))
    )
  ).sort();

  const displayedLeads = leads.filter((lead) => {
    if (selectedLocation) {
      const loc = (lead.country_code || lead.location || '').toLowerCase();
      if (!loc.includes(selectedLocation.toLowerCase())) return false;
    }
    return true;
  });

  return (
    <div className="flex h-full max-h-full min-h-0 bg-[#fafafa] overflow-hidden">
      {/* Left Sidebar: Lists matching media_1790103640399.png */}
      <div className="w-60 border-r border-gray-200/80 bg-white p-5 flex flex-col justify-between shrink-0 h-full">
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">MY LISTS</span>
          <div className="mt-3 space-y-1">
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
              <span className="text-[11px] font-semibold text-gray-600">{total}</span>
            </button>
          </div>
        </div>

        <button
          onClick={() => setModalOpen(true)}
          className="w-full flex items-center justify-center gap-2 py-2 text-xs font-semibold text-indigo-600 border border-indigo-200 rounded-xl hover:bg-indigo-50 transition-colors shadow-2xs"
        >
          <Plus className="h-3.5 w-3.5" />
          Create new list
        </button>
      </div>

      {/* Main CRM Area */}
      <div className="flex-1 px-8 py-7 overflow-y-auto h-full min-h-0">
        {/* Top Actions Row with Prosp Switcher matching prosp_crm_kanban.jpg */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Leads</h1>
            <p className="text-xs text-gray-400 mt-0.5">{total} leads in All contacts</p>
          </div>

          <div className="flex items-center gap-2.5">
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

            <button className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-gray-700 hover:bg-gray-50 shadow-2xs transition-colors">
              <Download className="h-3.5 w-3.5 text-gray-500" />
              Export
            </button>

            <button
              onClick={() => setModalOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 shadow-xs transition-colors"
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
              <option value="accepted">Accepted</option>
              <option value="replied">Replied</option>
              <option value="finished">Finished</option>
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

          {/* Location Filter matching Prosp All locations */}
          <div className="relative">
            <select
              value={selectedLocation}
              onChange={(e) => setSelectedLocation(e.target.value)}
              className="rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-xs font-medium text-gray-700 shadow-2xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 cursor-pointer"
            >
              <option value="">All locations</option>
              {availableLocations.map((loc) => (
                <option key={loc} value={loc}>
                  {loc}
                </option>
              ))}
            </select>
          </div>

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
            onClick={fetchLeads}
            className="p-2 rounded-xl bg-white border border-gray-200 text-gray-500 hover:text-gray-800 hover:bg-gray-50 shadow-2xs transition-colors"
            title="Refresh leads"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Loading Indicator */}
        {loading ? (
          <div className="flex items-center justify-center py-24 text-gray-400">
            <RefreshCw className="h-6 w-6 animate-spin" />
          </div>
        ) : displayedLeads.length === 0 ? (
          <div className="rounded-2xl border border-gray-200/90 bg-white p-16 text-center text-gray-500 shadow-2xs">
            <p className="text-xs text-gray-500 font-medium">No leads match your filter.</p>
            <button
              onClick={() => setModalOpen(true)}
              className="mt-2 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors cursor-pointer"
            >
              + Import your first leads list
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
                      {columnLeads.length}
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
                              className="text-gray-300 hover:text-red-600 p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                              title="Delete contact"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>

                          {/* Card Attributes: Company, Location/Country, Phone */}
                          <div className="mt-3 pt-2.5 border-t border-gray-100 space-y-1.5 text-[11px] text-gray-600">
                            {lead.company_name && (
                              <div className="flex items-center gap-1.5 truncate">
                                <Building className="w-3 h-3 text-gray-400 shrink-0" />
                                <span className="truncate">{lead.company_name}</span>
                              </div>
                            )}

                            {(lead.country_code || lead.location) && (
                              <div className="flex items-center gap-1.5 truncate">
                                <MapPin className="w-3 h-3 text-gray-400 shrink-0" />
                                <span className="truncate font-mono uppercase text-[10px]">
                                  {lead.country_code || lead.location}
                                </span>
                              </div>
                            )}

                            {lead.phone && (
                              <div className="flex items-center gap-1.5 truncate">
                                <Phone className="w-3 h-3 text-gray-400 shrink-0" />
                                <span className="truncate font-mono text-[10px]">{lead.phone}</span>
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
                  <th className="py-3 px-4">Contact</th>
                  {visibleColumns.pipelineStage && <th className="py-3 px-4">Pipeline Stage</th>}
                  {visibleColumns.executionState && <th className="py-3 px-4">Execution Status</th>}
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
                            <ExternalLink className="w-3 h-3 text-gray-400" />
                          </a>
                        </div>
                      </td>
                      {visibleColumns.pipelineStage && (
                        <td className="py-3 px-4" onClick={(e) => e.stopPropagation()}>
                          <select
                            value={lead.pipeline_stage || 'unassigned'}
                            onChange={(e) => handleUpdateStage(lead.id, e.target.value)}
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
                        </td>
                      )}
                      {visibleColumns.company && <td className="py-3 px-4 text-gray-600">{lead.company_name || '—'}</td>}
                      {visibleColumns.jobTitle && <td className="py-3 px-4 text-gray-600 truncate max-w-xs">{lead.job_title || '—'}</td>}
                      {visibleColumns.location && (
                        <td className="py-3 px-4 text-gray-500">
                          {lead.country_code ? (
                            <span className="font-mono uppercase">{lead.country_code}</span>
                          ) : (
                            lead.location || '—'
                          )}
                        </td>
                      )}
                      {visibleColumns.email && <td className="py-3 px-4 text-gray-500">{lead.email || '—'}</td>}
                      <td className="py-3 px-4 text-right" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => handleDeleteLead(lead.id)}
                          className="text-gray-400 hover:text-red-600 p-1 transition-colors"
                          title="Delete contact"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Import Modal */}
      <ImportLeadsModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        campaignId="default_campaign"
        onLeadsImported={() => fetchLeads()}
      />

      {/* Slide-over Lead Details Drawer matching Prosp Part 2 */}
      {selectedLead && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-black/40 backdrop-blur-2xs flex justify-end">
          <div className="w-full max-w-md bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right duration-200 border-l border-gray-200">
            {/* Drawer Header */}
            <div className="p-6 border-b border-gray-100 flex items-start justify-between bg-gradient-to-b from-gray-50/70 to-white shrink-0">
              <div className="flex items-start gap-3">
                {selectedLead.avatar_url ? (
                  <img
                    src={selectedLead.avatar_url}
                    alt={selectedLead.first_name}
                    className="w-12 h-12 rounded-full object-cover border border-gray-200 shrink-0"
                  />
                ) : (
                  <div className="w-12 h-12 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-sm shrink-0">
                    {getInitials(selectedLead.first_name, selectedLead.last_name)}
                  </div>
                )}
                <div>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <h3 className="text-base font-bold text-gray-900 leading-tight">
                      {selectedLead.first_name || selectedLead.last_name
                        ? `${selectedLead.first_name || ''} ${selectedLead.last_name || ''}`.trim()
                        : 'LinkedIn Member'}
                    </h3>
                    {selectedLead.linkedin_url && (
                      <a
                        href={selectedLead.linkedin_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center justify-center w-4 h-4 rounded bg-[#0077b5] text-white text-[9px] font-bold hover:opacity-90"
                        title="Open LinkedIn profile"
                      >
                        in
                      </a>
                    )}
                  </div>
                  {selectedLead.job_title && (
                    <p className="text-xs text-gray-600 font-medium mt-0.5">
                      {selectedLead.job_title}
                    </p>
                  )}
                  {selectedLead.company_name && (
                    <p className="text-xs text-indigo-600 font-semibold">
                      {selectedLead.company_name}
                    </p>
                  )}
                </div>
              </div>

              <button
                onClick={() => setSelectedLead(null)}
                className="p-1 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
                title="Close drawer"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Drawer Body Scroll */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Pipeline Stage Quick-Changer */}
              <div className="p-3.5 rounded-xl bg-gray-50 border border-gray-200/80 space-y-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-gray-500 block">
                  Pipeline Stage
                </span>
                <div className="flex items-center justify-between">
                  <select
                    value={selectedLead.pipeline_stage || 'unassigned'}
                    onChange={(e) => {
                      const newStage = e.target.value;
                      handleUpdateStage(selectedLead.id, newStage);
                      setSelectedLead((prev) => ({ ...prev, pipeline_stage: newStage }));
                    }}
                    className="text-xs font-semibold text-gray-800 bg-white border border-gray-200 rounded-lg px-3 py-1.5 cursor-pointer shadow-2xs focus:ring-1 focus:ring-indigo-500"
                  >
                    {PIPELINE_STAGES.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.label}
                      </option>
                    ))}
                  </select>

                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                      selectedLead.execution_state === 'replied'
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : selectedLead.execution_state === 'accepted'
                        ? 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                        : 'bg-gray-100 text-gray-600 border border-gray-200'
                    }`}
                  >
                    {selectedLead.execution_state || 'queued'}
                  </span>
                </div>
              </div>

              {/* Contact Information */}
              <div className="space-y-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                  Contact Information
                </span>

                <div className="space-y-2.5 text-xs text-gray-700">
                  <div className="flex items-center gap-3 p-2.5 rounded-xl border border-gray-100 bg-white shadow-2xs">
                    <Mail className="w-4 h-4 text-gray-400 shrink-0" />
                    <span className="truncate flex-1 font-mono text-xs">
                      {selectedLead.email || 'No email available'}
                    </span>
                  </div>

                  <div className="flex items-center gap-3 p-2.5 rounded-xl border border-gray-100 bg-white shadow-2xs">
                    <Phone className="w-4 h-4 text-gray-400 shrink-0" />
                    <span className="truncate flex-1 font-mono text-xs">
                      {selectedLead.phone || 'No phone recorded'}
                    </span>
                  </div>

                  <div className="flex items-center gap-3 p-2.5 rounded-xl border border-gray-100 bg-white shadow-2xs">
                    <MapPin className="w-4 h-4 text-gray-400 shrink-0" />
                    <span className="truncate flex-1">
                      {selectedLead.location || selectedLead.country_code || 'Location unverified'}
                    </span>
                  </div>

                  <div className="flex items-center gap-3 p-2.5 rounded-xl border border-gray-100 bg-white shadow-2xs">
                    <Building className="w-4 h-4 text-gray-400 shrink-0" />
                    <span className="truncate flex-1">
                      {selectedLead.company_name || 'Company unverified'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Outreach Campaign Membership */}
              <div className="space-y-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                  Campaign Membership
                </span>

                <div className="p-3.5 rounded-xl border border-gray-100 bg-white shadow-2xs space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-gray-900">
                      {selectedLead.campaign_name || 'Active Campaign'}
                    </span>
                    <span className="text-[10px] text-gray-400">
                      ID: {selectedLead.campaign_id ? selectedLead.campaign_id.slice(-6) : 'default'}
                    </span>
                  </div>
                  <p className="text-[11px] text-gray-500">
                    Lead is enrolled in the campaign automation sequence.
                  </p>
                </div>
              </div>

              {/* Activity Touchpoints History */}
              <div className="space-y-3">
                <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                  Touchpoints & Timeline
                </span>

                <div className="relative pl-5 space-y-4 border-l-2 border-indigo-100 ml-2">
                  <div className="relative">
                    <span className="absolute -left-[27px] top-0.5 w-3 h-3 rounded-full bg-emerald-500 ring-4 ring-white" />
                    <p className="text-xs font-bold text-gray-800">Lead added to workspace</p>
                    <p className="text-[10px] text-gray-400 mt-0.5">Ingested via lead importer</p>
                  </div>

                  {selectedLead.execution_state !== 'queued' && (
                    <div className="relative">
                      <span className="absolute -left-[27px] top-0.5 w-3 h-3 rounded-full bg-indigo-500 ring-4 ring-white" />
                      <p className="text-xs font-bold text-gray-800">Connection invite queued</p>
                      <p className="text-[10px] text-gray-400 mt-0.5">Automated sequence step #1</p>
                    </div>
                  )}

                  {selectedLead.execution_state === 'accepted' && (
                    <div className="relative">
                      <span className="absolute -left-[27px] top-0.5 w-3 h-3 rounded-full bg-indigo-600 ring-4 ring-white" />
                      <p className="text-xs font-bold text-gray-800">Invitation accepted</p>
                      <p className="text-[10px] text-gray-400 mt-0.5">Moved to Step #2 branch</p>
                    </div>
                  )}

                  {selectedLead.execution_state === 'replied' && (
                    <div className="relative">
                      <span className="absolute -left-[27px] top-0.5 w-3 h-3 rounded-full bg-emerald-600 ring-4 ring-white" />
                      <p className="text-xs font-bold text-gray-800">Prospect replied</p>
                      <p className="text-[10px] text-gray-400 mt-0.5">Sequence paused for human follow-up</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Drawer Footer Actions */}
            <div className="p-4 border-t border-gray-100 bg-gray-50 flex items-center justify-between shrink-0">
              <button
                onClick={() => {
                  handleDeleteLead(selectedLead.id);
                  setSelectedLead(null);
                }}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-rose-600 hover:text-rose-800 p-2 rounded-lg hover:bg-rose-50 transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Delete Contact
              </button>

              {selectedLead.linkedin_url && (
                <a
                  href={selectedLead.linkedin_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-[#0077b5] hover:bg-[#006097] text-white text-xs font-semibold rounded-xl shadow-xs transition-colors"
                >
                  <span>Open LinkedIn</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
