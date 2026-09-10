import React, { useState, useEffect, useCallback } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { toast } from 'sonner';
import { 
  FaPlus, FaFileExport, FaFileImport, FaSearch, FaTimes, 
  FaUserEdit, FaTrash, FaCalendarAlt, FaUserFriends, FaInbox, FaChevronDown
} from 'react-icons/fa';
import { 
  getLeads, getLeadStats, addLead, updateLead, deleteLead, 
  exportLeadsCsv, importLeadsCsv, getDeals, getDealStats, 
  createDeal, updateDeal, deleteDeal, generateLeadSummary
} from '@/lib/api';

const TAG_COLORS = {
  subscriber: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  lead: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  client: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  vip: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  archived: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400'
};

const PRIORITY_COLORS = {
  low: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400',
  medium: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  high: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
};

const STAGES = [
  { id: 'lead', name: 'Lead', color: 'bg-gray-100 dark:bg-gray-800' },
  { id: 'contacted', name: 'Contacted', color: 'bg-blue-50 dark:bg-blue-900/20' },
  { id: 'proposal', name: 'Proposal', color: 'bg-amber-50 dark:bg-amber-900/20' },
  { id: 'negotiation', name: 'Negotiation', color: 'bg-purple-50 dark:bg-purple-900/20' },
  { id: 'won', name: 'Won', color: 'bg-emerald-50 dark:bg-emerald-900/20' },
  { id: 'lost', name: 'Lost', color: 'bg-red-50 dark:bg-red-900/20' }
];

const formatCurrency = (value, currency = 'INR') => {
  if (value == null) return '';
  return new Intl.NumberFormat(currency === 'INR' ? 'en-IN' : 'en-US', { 
    style: 'currency', 
    currency: currency,
    maximumFractionDigits: 0
  }).format(value);
};

const formatDate = (dateStr) => {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleDateString('en-IN', { 
    day: 'numeric', month: 'short', year: 'numeric' 
  });
};

export default function Audience() {
  const [activeTab, setActiveTab] = useState('contacts');
  
  // Contacts State
  const [leads, setLeads] = useState([]);
  const [leadStats, setLeadStats] = useState({ subscriber: 0, lead: 0, client: 0, vip: 0, archived: 0, total: 0 });
  const [leadsLoading, setLeadsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [tagFilter, setTagFilter] = useState('all');
  
  // Deals State
  const [deals, setDeals] = useState([]);
  const [dealStats, setDealStats] = useState({ totalValue: 0, wonThisMonth: 0, activeCount: 0 });
  const [dealsLoading, setDealsLoading] = useState(true);

  // Modals & Panels State
  const [isAddContactModalOpen, setIsAddContactModalOpen] = useState(false);
  const [selectedContact, setSelectedContact] = useState(null);
  const [contactForm, setContactForm] = useState({ name: '', email: '', phone: '', tag: 'subscriber', notes: '' });
  
  const [isAddDealModalOpen, setIsAddDealModalOpen] = useState(false);
  const [selectedDeal, setSelectedDeal] = useState(null);
  const [dealForm, setDealForm] = useState({ title: '', contact_name: '', contact_email: '', value: '', currency: 'INR', stage: 'lead', priority: 'medium', notes: '', tags: '' });

  // AI Summary State
  const [aiSummary, setAiSummary] = useState('');
  const [aiSummaryLoading, setAiSummaryLoading] = useState(false);

  const fetchLeadsData = useCallback(async () => {
    try {
      setLeadsLoading(true);
      const [leadsRes, statsRes] = await Promise.all([getLeads(), getLeadStats()]);
      setLeads(leadsRes.leads || []);
      setLeadStats(statsRes || { subscriber: 0, lead: 0, client: 0, vip: 0, archived: 0, total: 0 });
    } catch (err) {
      toast.error('Failed to load contacts');
    } finally {
      setLeadsLoading(false);
    }
  }, []);

  const fetchDealsData = useCallback(async () => {
    try {
      setDealsLoading(true);
      const [dealsRes, statsRes] = await Promise.all([getDeals(), getDealStats()]);
      setDeals(dealsRes.deals || []);
      const s = statsRes || {};
      setDealStats({
        totalValue: s.total_pipeline_value || 0,
        wonValue: s.won_value || 0,
        activeCount: s.total_deals || 0,
      });
    } catch (err) {
      toast.error('Failed to load deals');
    } finally {
      setDealsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'contacts') fetchLeadsData();
    else fetchDealsData();
  }, [activeTab, fetchLeadsData, fetchDealsData]);

  // Contact Handlers
  const handleSaveContact = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        name: contactForm.name || '',
        email: contactForm.email || '',
        phone: contactForm.phone || '',
        tag: contactForm.tag || 'subscriber',
        notes: contactForm.notes || '',
      };
      if (selectedContact) {
        await updateLead(selectedContact.id, payload);
        toast.success('Contact updated successfully');
        setSelectedContact(null);
      } else {
        await addLead(payload);
        toast.success('Contact added successfully');
        setIsAddContactModalOpen(false);
      }
      fetchLeadsData();
    } catch (err) {
      toast.error(selectedContact ? 'Failed to update contact' : 'Failed to add contact');
    }
  };

  const handleDeleteContact = async (id) => {
    if (!window.confirm('Are you sure you want to delete this contact?')) return;
    try {
      await deleteLead(id);
      toast.success('Contact deleted');
      setSelectedContact(null);
      fetchLeadsData();
    } catch (err) {
      toast.error('Failed to delete contact');
    }
  };

  const handleExportCsv = async () => {
    try {
      const blob = await exportLeadsCsv();
      const url = window.URL.createObjectURL(new Blob([blob]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `unravler_contacts_${new Date().toISOString().slice(0, 10)}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success('Contacts exported successfully');
    } catch (err) {
      toast.error('Export failed');
    }
  };

  const handleImportCsv = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const formData = new FormData();
      formData.append('file', file);
      await importLeadsCsv(formData);
      toast.success('Contacts imported successfully');
      fetchLeadsData();
    } catch (err) {
      toast.error('Import failed');
    } finally {
      e.target.value = '';
    }
  };

  // Deal Handlers
  const handleSaveDeal = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        title: dealForm.title.trim(),
        contact_name: (dealForm.contact_name || '').trim(),
        contact_email: (dealForm.contact_email || '').trim(),
        value: parseFloat(dealForm.value) || 0,
        currency: dealForm.currency || 'INR',
        stage: dealForm.stage || 'lead',
        priority: dealForm.priority || 'medium',
        notes: (dealForm.notes || '').trim(),
        tags: typeof dealForm.tags === 'string'
          ? dealForm.tags.split(',').map(t => t.trim()).filter(Boolean)
          : Array.isArray(dealForm.tags) ? dealForm.tags : [],
      };

      if (selectedDeal) {
        await updateDeal(selectedDeal.id, payload);
        toast.success('Deal updated');
        setSelectedDeal(null);
      } else {
        await createDeal(payload);
        toast.success('Deal created');
        setIsAddDealModalOpen(false);
      }
      fetchDealsData();
    } catch (err) {
      toast.error(selectedDeal ? 'Failed to update deal' : 'Failed to create deal');
    }
  };

  const handleDeleteDeal = async (id) => {
    if (!window.confirm('Are you sure you want to delete this deal?')) return;
    try {
      await deleteDeal(id);
      toast.success('Deal deleted');
      setSelectedDeal(null);
      fetchDealsData();
    } catch (err) {
      toast.error('Failed to delete deal');
    }
  };

  const handleDealStageChange = async (deal, newStage) => {
    try {
      await updateDeal(deal.id, { stage: newStage });
      toast.success('Deal stage updated');
      fetchDealsData();
    } catch (err) {
      toast.error('Failed to update deal stage');
    }
  };

  const handleGenerateAiSummary = useCallback(async (leadId) => {
    try {
      setAiSummaryLoading(true);
      setAiSummary('');
      const res = await generateLeadSummary(leadId);
      setAiSummary(res.summary || 'No summary available.');
    } catch (err) {
      toast.error('Failed to generate AI summary');
      setAiSummary('');
    } finally {
      setAiSummaryLoading(false);
    }
  }, []);

  // Renderers
  const filteredLeads = leads.filter(l => 
    (tagFilter === 'all' || l.tag === tagFilter) &&
    ((l.name || '').toLowerCase().includes(searchQuery.toLowerCase()) || (l.email || '').toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <DashboardLayout>
      <div className="w-full max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 animate-in fade-in duration-500 text-slate-900 dark:text-slate-100">
        {/* Header & Tabs */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-8 gap-4">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-3">
              Audience Hub
              {activeTab === 'contacts' && (
                <span className="bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300 py-0.5 px-2.5 rounded-full text-sm font-semibold">
                  {leadStats.total || 0}
                </span>
              )}
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Manage your contacts and sales pipeline</p>
          </div>
          
          <div className="flex bg-slate-100 dark:bg-slate-800 p-1 rounded-xl w-fit">
            <button 
              onClick={() => setActiveTab('contacts')}
              className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'contacts' ? 'bg-white dark:bg-slate-700 shadow-sm text-indigo-600 dark:text-indigo-400' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'}`}
            >
              Contacts
            </button>
            <button 
              onClick={() => setActiveTab('deals')}
              className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'deals' ? 'bg-white dark:bg-slate-700 shadow-sm text-indigo-600 dark:text-indigo-400' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'}`}
            >
              Deals
            </button>
          </div>
        </div>

        {/* TAB 1: CONTACTS */}
        {activeTab === 'contacts' && (
          <div className="space-y-6">
            {/* Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {['subscriber', 'lead', 'client', 'vip'].map(tag => (
                <div key={tag} className="bg-white dark:bg-slate-800 p-5 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-700">
                  <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">{tag}</h3>
                  <p className="text-2xl font-bold text-slate-900 dark:text-white">{leadStats[tag] || 0}</p>
                </div>
              ))}
            </div>

            {/* Actions */}
            <div className="flex flex-col md:flex-row gap-4 justify-between items-center bg-white dark:bg-slate-800 p-4 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-700">
              <div className="flex items-center gap-3 w-full md:w-auto">
                <button 
                  onClick={() => { setContactForm({ name: '', email: '', phone: '', tag: 'subscriber', notes: '' }); setIsAddContactModalOpen(true); }}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 transition-colors"
                >
                  <FaPlus className="text-xs" /> Add Contact
                </button>
                
                <button onClick={handleExportCsv} className="bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 px-3 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 transition-colors">
                  <FaFileExport className="text-xs" /> Export
                </button>
                
                <label className="bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 px-3 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 transition-colors cursor-pointer">
                  <FaFileImport className="text-xs" /> Import
                  <input type="file" accept=".csv" className="hidden" onChange={handleImportCsv} />
                </label>
              </div>

              <div className="flex items-center gap-3 w-full md:w-auto">
                <div className="relative w-full md:w-64">
                  <FaSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400" />
                  <input 
                    type="text" 
                    placeholder="Search contacts..." 
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-9 pr-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:text-white"
                  />
                </div>
                <select 
                  value={tagFilter}
                  onChange={(e) => setTagFilter(e.target.value)}
                  className="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="all">All Tags</option>
                  <option value="subscriber">Subscriber</option>
                  <option value="lead">Lead</option>
                  <option value="client">Client</option>
                  <option value="vip">VIP</option>
                  <option value="archived">Archived</option>
                </select>
              </div>
            </div>

            {/* Table Area */}
            <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-700 overflow-hidden">
              {leadsLoading ? (
                <div className="flex justify-center items-center p-12">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
                </div>
              ) : filteredLeads.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-16 text-center">
                  <div className="bg-slate-100 dark:bg-slate-700 p-4 rounded-full mb-4">
                    <FaUserFriends className="text-3xl text-slate-400 dark:text-slate-500" />
                  </div>
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">No contacts found</h3>
                  <p className="text-sm text-slate-500 dark:text-slate-400 mb-6 max-w-sm">
                    {searchQuery ? "No contacts match your search or filters." : "Add your first contact or set up your Smart Bio to capture leads automatically."}
                  </p>
                  {!searchQuery && (
                    <button 
                      onClick={() => { setContactForm({ name: '', email: '', phone: '', tag: 'subscriber', notes: '' }); setIsAddContactModalOpen(true); }}
                      className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition-colors"
                    >
                      Add Contact
                    </button>
                  )}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-slate-50 dark:bg-slate-900/50 border-b border-slate-200 dark:border-slate-700">
                        <th className="px-6 py-4 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Name</th>
                        <th className="px-6 py-4 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Email</th>
                        <th className="px-6 py-4 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Tag</th>
                        <th className="px-6 py-4 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Source</th>
                        <th className="px-6 py-4 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Date Added</th>
                        <th className="px-6 py-4 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                      {filteredLeads.map(lead => (
                        <tr 
                          key={lead.id} 
                          className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors cursor-pointer"
                          onClick={() => { setContactForm(lead); setSelectedContact(lead); setAiSummary(''); }}
                        >
                          <td className="px-6 py-4 whitespace-nowrap">
                            <div className="font-medium text-slate-900 dark:text-slate-100">{lead.name || 'Unnamed'}</div>
                            {lead.phone && <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{lead.phone}</div>}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-600 dark:text-slate-300">{lead.email}</td>
                          <td className="px-6 py-4 whitespace-nowrap">
                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${TAG_COLORS[lead.tag || 'subscriber'] || TAG_COLORS.subscriber}`}>
                              {lead.tag || 'subscriber'}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-600 dark:text-slate-300">{lead.source || 'Manual'}</td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-600 dark:text-slate-300">{formatDate(lead.created_at)}</td>
                          <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                            <button 
                              onClick={(e) => { e.stopPropagation(); setContactForm(lead); setSelectedContact(lead); setAiSummary(''); }}
                              className="text-indigo-600 hover:text-indigo-900 dark:text-indigo-400 dark:hover:text-indigo-300 mr-4"
                            >
                              Edit
                            </button>
                            <button 
                              onClick={(e) => { e.stopPropagation(); handleDeleteContact(lead.id); }}
                              className="text-red-600 hover:text-red-900 dark:text-red-400 dark:hover:text-red-300"
                            >
                              Delete
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: DEALS */}
        {activeTab === 'deals' && (
          <div className="space-y-6 h-[calc(100vh-140px)] flex flex-col">
            {/* Stats */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 shrink-0">
              <div className="bg-white dark:bg-slate-800 p-5 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-700 flex justify-between items-center">
                <div>
                  <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Total Pipeline</h3>
                  <p className="text-2xl font-bold text-slate-900 dark:text-white">{formatCurrency(dealStats.totalValue)}</p>
                </div>
                <button 
                  onClick={() => { setDealForm({ title: '', contact_name: '', contact_email: '', value: '', currency: 'INR', stage: 'lead', priority: 'medium', notes: '', tags: '' }); setIsAddDealModalOpen(true); }}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 transition-colors"
                >
                  <FaPlus className="text-xs" /> New Deal
                </button>
              </div>
              <div className="bg-white dark:bg-slate-800 p-5 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-700">
                <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Won Pipeline</h3>
                <p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">{formatCurrency(dealStats.wonValue ?? dealStats.wonThisMonth)}</p>
              </div>
              <div className="bg-white dark:bg-slate-800 p-5 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-700">
                <h3 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Active Deals</h3>
                <p className="text-2xl font-bold text-slate-900 dark:text-white">{dealStats.activeCount}</p>
              </div>
            </div>

            {/* Kanban Board */}
            <div className="flex-1 overflow-x-auto pb-4 custom-scrollbar">
              {dealsLoading ? (
                <div className="flex justify-center items-center h-64">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
                </div>
              ) : (
                <div className="flex gap-4 h-full min-w-max pb-2">
                  {STAGES.map(stage => {
                    const stageDeals = deals.filter(d => d.stage === stage.id);
                    return (
                      <div key={stage.id} className={`w-80 flex flex-col rounded-2xl border border-slate-200 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-800/30 overflow-hidden`}>
                        <div className={`p-4 border-b border-slate-200 dark:border-slate-700/50 flex items-center justify-between ${stage.color}`}>
                          <h3 className="font-bold text-slate-900 dark:text-slate-100">{stage.name}</h3>
                          <span className="bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 text-xs font-bold px-2 py-1 rounded-lg shadow-sm">
                            {stageDeals.length}
                          </span>
                        </div>
                        
                        <div className="flex-1 p-3 space-y-3 overflow-y-auto">
                          {stageDeals.length === 0 ? (
                            <div className="text-center py-8 text-sm text-slate-400 dark:text-slate-500">No deals</div>
                          ) : (
                            stageDeals.map(deal => (
                              <div 
                                key={deal.id} 
                                onClick={() => {
                                  setDealForm({
                                    title: deal.title || '',
                                    contact_name: deal.contact_name || deal.contactName || '',
                                    contact_email: deal.contact_email || deal.contactEmail || '',
                                    value: deal.value ?? '',
                                    currency: deal.currency || 'INR',
                                    stage: deal.stage || 'lead',
                                    priority: deal.priority || 'medium',
                                    notes: deal.notes || '',
                                    tags: Array.isArray(deal.tags) ? deal.tags.join(', ') : (deal.tags || ''),
                                  });
                                  setSelectedDeal(deal);
                                }}
                                className="bg-white dark:bg-slate-800 p-4 rounded-xl shadow-sm border border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-500/50 transition-colors cursor-pointer group"
                              >
                                <div className="flex justify-between items-start mb-2">
                                  <h4 className="font-bold text-sm text-slate-900 dark:text-slate-100 leading-tight">{deal.title}</h4>
                                  <div onClick={(e) => e.stopPropagation()} className="relative inline-block text-left">
                                    <select 
                                      value={deal.stage} 
                                      onChange={(e) => handleDealStageChange(deal, e.target.value)}
                                      className="appearance-none bg-transparent border-none text-xs text-indigo-600 dark:text-indigo-400 font-semibold focus:outline-none cursor-pointer pr-4"
                                    >
                                      {STAGES.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                                    </select>
                                    <FaChevronDown className="absolute right-0 top-1/2 transform -translate-y-1/2 text-[8px] text-indigo-600 dark:text-indigo-400 pointer-events-none" />
                                  </div>
                                </div>
                                <div className="text-xs text-slate-500 dark:text-slate-400 mb-3">{deal.contact_name || deal.contactName || 'No contact specified'}</div>
                                
                                <div className="flex items-center justify-between mt-auto">
                                  <div className="font-semibold text-sm text-slate-700 dark:text-slate-300">
                                    {formatCurrency(deal.value, deal.currency)}
                                  </div>
                                  <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded ${PRIORITY_COLORS[deal.priority || 'medium']}`}>
                                    {deal.priority || 'medium'}
                                  </span>
                                </div>
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* OVERLAYS & MODALS */}
      
      {/* Contact Side Panel */}
      {selectedContact && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/20 dark:bg-black/40 backdrop-blur-sm animate-in fade-in">
          <div className="bg-white dark:bg-slate-900 w-full max-w-md h-full shadow-2xl border-l border-slate-200 dark:border-slate-800 animate-in slide-in-from-right-full duration-300 flex flex-col">
            <div className="p-6 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <h2 className="text-xl font-bold">Edit Contact</h2>
              <button onClick={() => setSelectedContact(null)} className="p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors"><FaTimes /></button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-6">
              {/* ✨ AI Summary Section */}
              <div className="mb-5 rounded-2xl border border-indigo-100 dark:border-indigo-900/40 bg-indigo-50/50 dark:bg-indigo-950/20 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-indigo-700 dark:text-indigo-300 flex items-center gap-1.5">✨ AI Insight</span>
                  <button
                    type="button"
                    onClick={() => handleGenerateAiSummary(selectedContact.id)}
                    disabled={aiSummaryLoading}
                    className="text-[11px] font-semibold text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-200 transition-colors disabled:opacity-50"
                  >
                    {aiSummaryLoading ? 'Generating…' : aiSummary ? 'Regenerate' : 'Generate Summary'}
                  </button>
                </div>
                {aiSummaryLoading ? (
                  <div className="space-y-2 animate-pulse">
                    <div className="h-3 bg-indigo-200/50 dark:bg-indigo-800/30 rounded-full w-full" />
                    <div className="h-3 bg-indigo-200/50 dark:bg-indigo-800/30 rounded-full w-4/5" />
                  </div>
                ) : aiSummary ? (
                  <p className="text-xs text-indigo-900 dark:text-indigo-200 leading-relaxed">{aiSummary}</p>
                ) : (
                  <p className="text-[11px] text-indigo-400 dark:text-indigo-500">Click "Generate Summary" for an AI-powered overview of this contact's activity and engagement.</p>
                )}
              </div>

              <form id="editContactForm" onSubmit={handleSaveContact} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Name</label>
                  <input required type="text" value={contactForm.name} onChange={(e) => setContactForm({...contactForm, name: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Email</label>
                  <input type="email" value={contactForm.email || ''} onChange={(e) => setContactForm({...contactForm, email: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Phone</label>
                  <input type="text" value={contactForm.phone || ''} onChange={(e) => setContactForm({...contactForm, phone: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Tag</label>
                  <select value={contactForm.tag || 'subscriber'} onChange={(e) => setContactForm({...contactForm, tag: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                    <option value="subscriber">Subscriber</option>
                    <option value="lead">Lead</option>
                    <option value="client">Client</option>
                    <option value="vip">VIP</option>
                    <option value="archived">Archived</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Notes</label>
                  <textarea rows={4} value={contactForm.notes || ''} onChange={(e) => setContactForm({...contactForm, notes: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"></textarea>
                </div>
              </form>
            </div>
            
            <div className="p-6 border-t border-slate-100 dark:border-slate-800 flex justify-between gap-3 bg-slate-50 dark:bg-slate-900/50">
              <button type="button" onClick={() => handleDeleteContact(selectedContact.id)} className="px-4 py-2 text-sm font-semibold text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-xl transition-colors">Delete</button>
              <div className="flex gap-3">
                <button type="button" onClick={() => setSelectedContact(null)} className="px-4 py-2 text-sm font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors">Cancel</button>
                <button type="submit" form="editContactForm" className="px-5 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-colors shadow-sm">Save Changes</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Contact Modal */}
      {isAddContactModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/20 dark:bg-black/40 backdrop-blur-sm animate-in fade-in">
          <div className="bg-white dark:bg-slate-900 w-full max-w-md rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-800 overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="p-6 border-b border-slate-100 dark:border-slate-800">
              <h2 className="text-xl font-bold">Add New Contact</h2>
            </div>
            <div className="p-6">
              <form id="addContactForm" onSubmit={handleSaveContact} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Name</label>
                  <input required type="text" value={contactForm.name} onChange={(e) => setContactForm({...contactForm, name: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Email</label>
                  <input type="email" value={contactForm.email} onChange={(e) => setContactForm({...contactForm, email: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Phone</label>
                  <input type="text" value={contactForm.phone} onChange={(e) => setContactForm({...contactForm, phone: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Tag</label>
                  <select value={contactForm.tag} onChange={(e) => setContactForm({...contactForm, tag: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                    <option value="subscriber">Subscriber</option>
                    <option value="lead">Lead</option>
                    <option value="client">Client</option>
                    <option value="vip">VIP</option>
                  </select>
                </div>
              </form>
            </div>
            <div className="p-6 border-t border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 flex justify-end gap-3">
              <button type="button" onClick={() => setIsAddContactModalOpen(false)} className="px-4 py-2 text-sm font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors">Cancel</button>
              <button type="submit" form="addContactForm" className="px-5 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-colors shadow-sm">Add Contact</button>
            </div>
          </div>
        </div>
      )}

      {/* Deal Side Panel */}
      {selectedDeal && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/20 dark:bg-black/40 backdrop-blur-sm animate-in fade-in">
          <div className="bg-white dark:bg-slate-900 w-full max-w-md h-full shadow-2xl border-l border-slate-200 dark:border-slate-800 animate-in slide-in-from-right-full duration-300 flex flex-col">
            <div className="p-6 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <h2 className="text-xl font-bold">Edit Deal</h2>
              <button onClick={() => setSelectedDeal(null)} className="p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors"><FaTimes /></button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-6">
              <form id="editDealForm" onSubmit={handleSaveDeal} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Deal Title</label>
                  <input required type="text" value={dealForm.title} onChange={(e) => setDealForm({...dealForm, title: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Contact Name</label>
                    <input type="text" value={dealForm.contact_name || ''} onChange={(e) => setDealForm({...dealForm, contact_name: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Contact Email</label>
                    <input type="email" value={dealForm.contact_email || ''} onChange={(e) => setDealForm({...dealForm, contact_email: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Value</label>
                    <input type="number" value={dealForm.value || ''} onChange={(e) => setDealForm({...dealForm, value: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Currency</label>
                    <select value={dealForm.currency || 'INR'} onChange={(e) => setDealForm({...dealForm, currency: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                      <option value="INR">INR (₹)</option>
                      <option value="USD">USD ($)</option>
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Stage</label>
                    <select value={dealForm.stage || 'lead'} onChange={(e) => setDealForm({...dealForm, stage: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                      {STAGES.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Priority</label>
                    <select value={dealForm.priority || 'medium'} onChange={(e) => setDealForm({...dealForm, priority: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                      <option value="low">Low</option>
                      <option value="medium">Medium</option>
                      <option value="high">High</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Tags (comma separated)</label>
                  <input type="text" value={dealForm.tags || ''} onChange={(e) => setDealForm({...dealForm, tags: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. enterprise, software" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Notes</label>
                  <textarea rows={4} value={dealForm.notes || ''} onChange={(e) => setDealForm({...dealForm, notes: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"></textarea>
                </div>
              </form>
            </div>
            
            <div className="p-6 border-t border-slate-100 dark:border-slate-800 flex justify-between gap-3 bg-slate-50 dark:bg-slate-900/50">
              <button type="button" onClick={() => handleDeleteDeal(selectedDeal.id)} className="px-4 py-2 text-sm font-semibold text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-xl transition-colors">Delete</button>
              <div className="flex gap-3">
                <button type="button" onClick={() => setSelectedDeal(null)} className="px-4 py-2 text-sm font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors">Cancel</button>
                <button type="submit" form="editDealForm" className="px-5 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-colors shadow-sm">Save Changes</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Deal Modal */}
      {isAddDealModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/20 dark:bg-black/40 backdrop-blur-sm animate-in fade-in">
          <div className="bg-white dark:bg-slate-900 w-full max-w-lg rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-800 overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="p-6 border-b border-slate-100 dark:border-slate-800">
              <h2 className="text-xl font-bold">Create New Deal</h2>
            </div>
            <div className="p-6 max-h-[70vh] overflow-y-auto">
              <form id="addDealForm" onSubmit={handleSaveDeal} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Deal Title</label>
                  <input required type="text" value={dealForm.title} onChange={(e) => setDealForm({...dealForm, title: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Contact Name</label>
                    <input type="text" value={dealForm.contact_name || ''} onChange={(e) => setDealForm({...dealForm, contact_name: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Contact Email</label>
                    <input type="email" value={dealForm.contact_email || ''} onChange={(e) => setDealForm({...dealForm, contact_email: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Value</label>
                    <input type="number" value={dealForm.value} onChange={(e) => setDealForm({...dealForm, value: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Currency</label>
                    <select value={dealForm.currency} onChange={(e) => setDealForm({...dealForm, currency: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                      <option value="INR">INR (₹)</option>
                      <option value="USD">USD ($)</option>
                    </select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Stage</label>
                    <select value={dealForm.stage} onChange={(e) => setDealForm({...dealForm, stage: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                      {STAGES.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">Priority</label>
                    <select value={dealForm.priority} onChange={(e) => setDealForm({...dealForm, priority: e.target.value})} className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                      <option value="low">Low</option>
                      <option value="medium">Medium</option>
                      <option value="high">High</option>
                    </select>
                  </div>
                </div>
              </form>
            </div>
            <div className="p-6 border-t border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 flex justify-end gap-3">
              <button type="button" onClick={() => setIsAddDealModalOpen(false)} className="px-4 py-2 text-sm font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors">Cancel</button>
              <button type="submit" form="addDealForm" className="px-5 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-colors shadow-sm">Create Deal</button>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
