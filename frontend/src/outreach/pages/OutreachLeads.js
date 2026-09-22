import React, { useState, useEffect } from 'react';
import { Search, Download, Plus, Filter, Users, Building, MapPin, Mail, Phone, RefreshCw, Trash2 } from 'lucide-react';
import ImportLeadsModal from '../components/ImportLeadsModal';

export default function OutreachLeads() {
  const [leads, setLeads] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedState, setSelectedState] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedList, setSelectedList] = useState('all');

  const fetchLeads = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const params = new URLSearchParams();
      if (searchQuery) params.append('search', searchQuery);
      if (selectedState) params.append('execution_state', selectedState);

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
  }, [searchQuery, selectedState]);

  const handleDeleteLead = async (leadId) => {
    if (!window.confirm('Delete this contact?')) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/leads/${leadId}`, {
        method: 'DELETE',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        setLeads(leads.filter((l) => l.id !== leadId));
        setTotal((prev) => Math.max(0, prev - 1));
      }
    } catch (err) {
      console.error('Delete lead failed:', err);
    }
  };

  return (
    <div className="flex h-full min-h-screen bg-gray-50/50">
      {/* Left Sidebar: Lists */}
      <div className="w-64 border-r border-gray-200 bg-white p-5 flex flex-col justify-between shrink-0">
        <div>
          <span className="text-[11px] font-bold uppercase tracking-wider text-gray-400">My Lists</span>
          <div className="mt-3 space-y-1">
            <button
              onClick={() => setSelectedList('all')}
              className={`w-full flex items-center justify-between px-3 py-2 text-sm font-medium rounded-xl transition-colors ${
                selectedList === 'all'
                  ? 'bg-indigo-50 text-indigo-700 font-semibold'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <div className="flex items-center gap-2">
                <Users className="h-4 w-4" />
                <span>All contacts</span>
              </div>
              <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{total}</span>
            </button>
          </div>
        </div>

        <button
          onClick={() => setModalOpen(true)}
          className="w-full flex items-center justify-center gap-2 py-2 text-xs font-semibold text-indigo-600 border border-indigo-200 rounded-xl hover:bg-indigo-50 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          Create new list
        </button>
      </div>

      {/* Main CRM Area */}
      <div className="flex-1 px-8 py-7 overflow-y-auto">
        {/* Top Actions Row */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Leads</h1>
            <p className="text-xs text-gray-500 mt-0.5">{total} leads in All contacts</p>
          </div>
          <div className="flex items-center gap-2.5">
            <button className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-50 shadow-sm">
              <Download className="h-3.5 w-3.5" />
              Export
            </button>
            <button
              onClick={() => setModalOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 shadow-sm transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
              Import leads
            </button>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="flex items-center gap-3 mb-5">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3.5 top-2.5 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search leads by name, title, or company..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-xl border border-gray-200 bg-white pl-9 pr-4 py-2 text-xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 shadow-sm"
            />
          </div>

          <select
            value={selectedState}
            onChange={(e) => setSelectedState(e.target.value)}
            className="rounded-xl border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-gray-600 shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">All statuses</option>
            <option value="queued">Queued</option>
            <option value="waiting_delay">Waiting delay</option>
            <option value="accepted">Accepted</option>
            <option value="replied">Replied</option>
            <option value="finished">Finished</option>
          </select>
        </div>

        {/* Leads Table */}
        <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center py-20 text-gray-400">
              <RefreshCw className="h-6 w-6 animate-spin" />
            </div>
          ) : leads.length === 0 ? (
            <div className="p-12 text-center text-gray-500">
              <p className="text-sm">No leads match your filter.</p>
              <button
                onClick={() => setModalOpen(true)}
                className="mt-3 text-xs font-semibold text-indigo-600 hover:text-indigo-800"
              >
                + Import your first leads list
              </button>
            </div>
          ) : (
            <table className="w-full text-left text-xs">
              <thead className="border-b border-gray-200 bg-gray-50/70 text-gray-500 uppercase font-semibold tracking-wider text-[10px]">
                <tr>
                  <th className="py-3 px-4">Name</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Company</th>
                  <th className="py-3 px-4">Job Title</th>
                  <th className="py-3 px-4">Location</th>
                  <th className="py-3 px-4">Email</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {leads.map((lead) => (
                  <tr key={lead.id} className="hover:bg-gray-50/60 transition-colors">
                    <td className="py-3.5 px-4 font-semibold text-gray-900">
                      <a
                        href={lead.linkedin_url}
                        target="_blank"
                        rel="noreferrer"
                        className="hover:text-indigo-600 hover:underline"
                      >
                        {lead.first_name || lead.last_name ? `${lead.first_name} ${lead.last_name}`.trim() : 'LinkedIn Member'}
                      </a>
                    </td>
                    <td className="py-3.5 px-4">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${
                        lead.execution_state === 'replied' ? 'bg-emerald-50 text-emerald-700' :
                        lead.execution_state === 'accepted' ? 'bg-indigo-50 text-indigo-700' :
                        'bg-gray-100 text-gray-600'
                      }`}>
                        {lead.execution_state}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-gray-600">{lead.company_name || '—'}</td>
                    <td className="py-3.5 px-4 text-gray-600 truncate max-w-xs">{lead.job_title || '—'}</td>
                    <td className="py-3.5 px-4 text-gray-500">{lead.location || '—'}</td>
                    <td className="py-3.5 px-4 text-gray-500">{lead.email || '—'}</td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={() => handleDeleteLead(lead.id)}
                        className="text-gray-400 hover:text-red-600 p-1 transition-colors"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Import Modal */}
      <ImportLeadsModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        campaignId="default_campaign"
        onLeadsImported={() => fetchLeads()}
      />
    </div>
  );
}
