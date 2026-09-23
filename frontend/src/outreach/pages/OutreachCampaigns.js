import React, { useState, useEffect } from 'react';
import {
  Plus,
  Search,
  Sparkles,
  MoreVertical,
  RefreshCw,
  Pencil,
  Calendar,
  X,
  Play,
  Pause,
  Trash2,
  ExternalLink,
} from 'lucide-react';
import OutreachCampaignWizard from './OutreachCampaignWizard';
import OutreachCampaignDetail from './OutreachCampaignDetail';

export default function OutreachCampaigns({ onOpenWizard }) {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [activeCampaignId, setActiveCampaignId] = useState(null);
  const [selectedCampaignId, setSelectedCampaignId] = useState(null);
  const [isTemplatesOpen, setIsTemplatesOpen] = useState(false);
  const [templatesList, setTemplatesList] = useState([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [undoAlert, setUndoAlert] = useState(null); // { id, name }
  const [menuOpenId, setMenuOpenId] = useState(null);
  const [isBookingModalOpen, setIsBookingModalOpen] = useState(false);

  const fetchCampaigns = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/campaigns', {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setCampaigns(data);
      }
    } catch (err) {
      console.error('Failed to fetch campaigns:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchTemplates = async () => {
    setLoadingTemplates(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/sequences/templates', {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setTemplatesList(data);
      }
    } catch (err) {
      console.error('Failed to fetch templates:', err);
    } finally {
      setLoadingTemplates(false);
    }
  };

  useEffect(() => {
    fetchCampaigns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (isTemplatesOpen) {
      fetchTemplates();
    }
  }, [isTemplatesOpen]);

  const handleDeleteTemplate = async (templateId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/sequences/templates/${templateId}`, {
        method: 'DELETE',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        setTemplatesList((prev) => prev.filter((t) => t.id !== templateId));
      }
    } catch (err) {
      console.error('Failed to delete template:', err);
    }
  };

  const handleUseTemplate = async (tpl) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/campaigns/auto-draft', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          name: tpl.name || 'Connect and follow up',
          draft_step: 2,
          draft_progress: 60,
          next_step_label: 'Next: Launch',
        }),
      });
      if (res.ok) {
        const draft = await res.json();
        if (tpl.nodes && tpl.edges) {
          await fetch('/api/v1/outreach/sequences', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: token ? `Bearer ${token}` : '',
            },
            body: JSON.stringify({
              campaign_id: draft.id,
              nodes: tpl.nodes,
              edges: tpl.edges,
              tree: tpl.tree || null,
            }),
          });
        }
        setIsTemplatesOpen(false);
        if (onOpenWizard) {
          onOpenWizard(draft.id, 2);
        } else {
          setActiveCampaignId(draft.id);
          setIsWizardOpen(true);
        }
      }
    } catch (err) {
      console.error('Failed to use template:', err);
    }
  };

  // Auto-drafting when user clicks "New campaign"
  const handleCreateNewCampaign = async (nameOverride) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/campaigns/auto-draft', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          name: nameOverride || `test${campaigns.length + 1}`,
          draft_step: 2,
          draft_progress: 40,
          next_step_label: 'Next: add your leads',
        }),
      });
      if (res.ok) {
        const draft = await res.json();
        if (onOpenWizard) {
          onOpenWizard(draft.id, 2);
        } else {
          setActiveCampaignId(draft.id);
          setIsWizardOpen(true);
        }
      }
    } catch (err) {
      console.error('Failed to auto-draft campaign:', err);
      if (onOpenWizard) onOpenWizard('new', 2);
      else setIsWizardOpen(true);
    }
  };

  const handleSoftDelete = async (campaignId, campaignName) => {
    setMenuOpenId(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/campaigns/${campaignId}`, {
        method: 'DELETE',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        setUndoAlert({ id: campaignId, name: campaignName });
        fetchCampaigns();
      }
    } catch (err) {
      console.error('Failed to delete campaign:', err);
    }
  };

  const handleRestore = async (campaignId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/campaigns/${campaignId}/restore`, {
        method: 'POST',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        setUndoAlert(null);
        fetchCampaigns();
      }
    } catch (err) {
      console.error('Failed to restore campaign:', err);
    }
  };

  // If a campaign is selected, render Campaign Details (media_1790104472298.png)
  if (selectedCampaignId) {
    return (
      <OutreachCampaignDetail
        campaignId={selectedCampaignId}
        onBack={() => {
          setSelectedCampaignId(null);
          fetchCampaigns();
        }}
        onEdit={(id, step) => {
          if (onOpenWizard) {
            onOpenWizard(id, step || 2);
          } else {
            setActiveCampaignId(id);
            setIsWizardOpen(true);
          }
        }}
      />
    );
  }

  // If standalone wizard fallback is open
  if (isWizardOpen) {
    return (
      <OutreachCampaignWizard
        campaignId={activeCampaignId || 'new'}
        onBack={() => {
          setIsWizardOpen(false);
          setActiveCampaignId(null);
          fetchCampaigns();
        }}
        onComplete={() => {
          setIsWizardOpen(false);
          setActiveCampaignId(null);
          fetchCampaigns();
        }}
      />
    );
  }

  // Templates View matching media_1790104784825.png
  if (isTemplatesOpen) {
    const displayTemplates = templatesList.length > 0 ? templatesList : [
      { id: 'tpl_connect_and_follow_up', name: 'Connect and follow up', uses: '—', acceptance: '—', reply: '—' },
      { id: 'tpl_profile_warmup', name: 'Profile warm-up', uses: '—', acceptance: '—', reply: '—' },
      { id: 'tpl_voice_note_outreach', name: 'Voice note outreach', uses: '—', acceptance: '—', reply: '—' },
      { id: 'tpl_inmail_engage', name: 'Multi-touch InMail & engage', uses: '—', acceptance: '—', reply: '—' },
    ];

    return (
      <div className="max-w-6xl mx-auto px-6 py-8">
        <button
          onClick={() => setIsTemplatesOpen(false)}
          className="text-xs font-semibold text-gray-500 hover:text-gray-900 transition-colors mb-4 inline-flex items-center gap-1.5"
        >
          ← Campaigns
        </button>
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Templates</h1>
            <p className="text-xs text-gray-500 mt-0.5">
              Prebuilt sequences and your saved templates. Save any campaign as a template to reuse it.
            </p>
          </div>
          {loadingTemplates && (
            <span className="text-xs text-gray-400 animate-pulse">Loading templates...</span>
          )}
        </div>

        <div className="rounded-2xl border border-gray-200 bg-white shadow-2xs overflow-hidden">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-gray-100 bg-gray-50/50 text-gray-400 uppercase font-semibold text-[10px] tracking-wider">
              <tr>
                <th className="py-3 px-5">TEMPLATE</th>
                <th className="py-3 px-5">USES</th>
                <th className="py-3 px-5">ACCEPTANCE</th>
                <th className="py-3 px-5">REPLY</th>
                <th className="py-3 px-5 text-right">ACTION</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {displayTemplates.map((tpl) => (
                <tr key={tpl.id} className="hover:bg-gray-50/60 transition-colors">
                  <td className="py-4 px-5">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-gray-900">{tpl.name}</span>
                      {tpl.is_custom && (
                        <span className="px-2 py-0.5 text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200 rounded-md">
                          Custom
                        </span>
                      )}
                    </div>
                    {tpl.description && (
                      <p className="text-[11px] text-gray-400 mt-0.5 truncate max-w-md">{tpl.description}</p>
                    )}
                  </td>
                  <td className="py-4 px-5 text-gray-400">{tpl.uses || '—'}</td>
                  <td className="py-4 px-5 text-gray-400">{tpl.acceptance || '—'}</td>
                  <td className="py-4 px-5 text-gray-400">{tpl.reply || '—'}</td>
                  <td className="py-4 px-5 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {tpl.is_custom && (
                        <button
                          onClick={() => handleDeleteTemplate(tpl.id)}
                          className="p-1.5 text-gray-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                          title="Delete custom template"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                      <button
                        onClick={() => handleUseTemplate(tpl)}
                        className="rounded-lg bg-indigo-50 text-[#5145cd] hover:bg-indigo-100 px-3.5 py-1.5 text-xs font-semibold transition-colors"
                      >
                        Use
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // Find most recent draft campaign to display in Draft Banner
  const draftCampaign = campaigns.find((c) => c.status === 'draft');

  const filteredCampaigns = campaigns.filter((c) => {
    if (statusFilter === 'sending') return c.status === 'active';
    if (statusFilter === 'paused') return c.status === 'paused';
    if (statusFilter === 'draft') return c.status === 'draft';
    if (searchQuery) {
      return (c.name || '').toLowerCase().includes(searchQuery.toLowerCase());
    }
    return true;
  });

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-4">
      {/* Top Header matching media_1790104399010.png */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Campaigns</h1>
          <p className="text-xs text-gray-500 mt-0.5">Your outreach campaigns, newest first.</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsTemplatesOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-4 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-50 shadow-2xs transition-colors"
          >
            <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
            Browse winning templates
          </button>
          <button
            onClick={() => handleCreateNewCampaign()}
            className="inline-flex items-center gap-1.5 rounded-xl bg-[#5145cd] hover:bg-[#4338ca] px-4 py-2 text-xs font-semibold text-white shadow-2xs transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            New campaign
          </button>
        </div>
      </div>

      {/* Banner 1: Draft Banner matching media_1790104399010.png */}
      {draftCampaign && (
        <div className="rounded-2xl border border-indigo-100 bg-white/90 p-4 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-all">
          <div className="flex items-center gap-3.5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-[#5145cd]">
              <Pencil className="h-4 w-4" />
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-gray-900">
                  Your draft: {draftCampaign.name}
                </span>
                <span className="inline-flex items-center rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-[#5145cd]">
                  {draftCampaign.draft_progress || 40}% ready
                </span>
              </div>
              <div className="flex items-center gap-3">
                <div className="h-1.5 w-36 sm:w-48 rounded-full bg-gray-100 overflow-hidden">
                  <div
                    className="h-full bg-[#5145cd] rounded-full transition-all duration-300"
                    style={{ width: `${draftCampaign.draft_progress || 40}%` }}
                  />
                </div>
                <span className="text-[11px] text-gray-400">
                  {draftCampaign.next_step_label || 'Next: add your leads'}
                </span>
              </div>
            </div>
          </div>

          <button
            onClick={() => {
              if (onOpenWizard) {
                onOpenWizard(draftCampaign.id, draftCampaign.draft_step || 2);
              } else {
                setActiveCampaignId(draftCampaign.id);
                setIsWizardOpen(true);
              }
            }}
            className="rounded-xl bg-[#5145cd] hover:bg-[#4338ca] px-4 py-2 text-xs font-semibold text-white shadow-2xs transition-colors shrink-0"
          >
            Resume draft
          </button>
        </div>
      )}

      {/* Banner 2: LinkedIn Expert Help Banner matching media_1790104399010.png */}
      <div className="rounded-2xl border border-indigo-100/70 bg-[#f5f6ff] p-4 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-[#5145cd] shadow-2xs">
            <Calendar className="h-4 w-4" />
          </div>
          <p className="text-xs text-gray-800">
            <strong className="font-bold text-gray-900 mr-1.5">
              Facing trouble with setting up campaigns?
            </strong>
            <span className="text-gray-500">
              Book a free session with our LinkedIn expert, Jack (worth $175).
            </span>
          </p>
        </div>

        <button
          onClick={() => setIsBookingModalOpen(true)}
          className="rounded-xl bg-[#5145cd] hover:bg-[#4338ca] px-4 py-2 text-xs font-semibold text-white shadow-2xs transition-colors shrink-0"
        >
          Book a call
        </button>
      </div>

      {/* Filter Row: Segmented Pills & Search Input matching media_1790104399010.png */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
        <div className="inline-flex items-center bg-gray-100/80 p-1 rounded-xl gap-1">
          {['all', 'sending', 'paused', 'draft'].map((tab) => (
            <button
              key={tab}
              onClick={() => setStatusFilter(tab)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold capitalize transition-all ${
                statusFilter === tab
                  ? 'bg-white text-gray-900 shadow-2xs'
                  : 'text-gray-500 hover:text-gray-800'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-2 h-3.5 w-3.5 text-gray-400" />
          <input
            type="text"
            placeholder="Search campaigns"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-xl border border-gray-200 bg-white pl-8 pr-3 py-1.5 text-xs text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 shadow-2xs"
          />
        </div>
      </div>

      {/* Reversible Undo Alert Banner matching media_1790104399010.png */}
      {undoAlert && (
        <div className="rounded-xl border border-gray-200 bg-gray-50/90 p-3.5 flex items-center justify-between text-xs transition-all shadow-2xs">
          <span className="text-gray-700">
            “{undoAlert.name}” deleted. The row survives, so this is reversible.
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleRestore(undoAlert.id)}
              className="rounded-lg bg-[#5145cd] hover:bg-[#4338ca] text-white px-3 py-1 font-semibold text-xs transition-colors"
            >
              Undo
            </button>
            <button
              onClick={() => setUndoAlert(null)}
              className="text-gray-500 hover:text-gray-800 text-xs px-2 py-1 font-medium transition-colors"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Campaigns Table matching media_1790104399010.png */}
      <div className="rounded-2xl border border-gray-200 bg-white shadow-2xs overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-gray-400">
            <RefreshCw className="h-6 w-6 animate-spin" />
          </div>
        ) : filteredCampaigns.length === 0 ? (
          <div className="p-16 text-center text-gray-500">
            <p className="text-xs font-medium text-gray-500">No campaigns found in this view.</p>
            <button
              onClick={() => handleCreateNewCampaign()}
              className="mt-3 text-xs font-semibold text-indigo-600 hover:text-indigo-800"
            >
              + Create your first outreach campaign
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-gray-100 bg-gray-50/50 text-gray-400 uppercase font-semibold text-[10px] tracking-wider">
                <tr>
                  <th className="py-3 px-5">STATUS</th>
                  <th className="py-3 px-5">NAME</th>
                  <th className="py-3 px-5">LEADS DONE</th>
                  <th className="py-3 px-5">ACCEPTANCE</th>
                  <th className="py-3 px-5">REPLY</th>
                  <th className="py-3 px-5">SENDERS</th>
                  <th className="py-3 px-5">LAST ACTION</th>
                  <th className="py-3 px-5 text-right"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredCampaigns.map((camp) => (
                  <tr
                    key={camp.id}
                    onClick={() => setSelectedCampaignId(camp.id)}
                    className="hover:bg-gray-50/60 transition-colors cursor-pointer group"
                  >
                    {/* Status Pill */}
                    <td className="py-4 px-5">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${
                          camp.status === 'active'
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : camp.status === 'paused'
                            ? 'bg-amber-50 text-amber-700 border-amber-200'
                            : 'bg-white text-gray-600 border-gray-200'
                        }`}
                      >
                        {camp.status || 'draft'}
                      </span>
                    </td>

                    {/* Name + Subtitle */}
                    <td className="py-4 px-5">
                      <p className="font-bold text-gray-900 group-hover:text-indigo-600 transition-colors">
                        {camp.name}
                      </p>
                      <p className="text-[11px] text-gray-400 mt-0.5 font-normal">
                        {camp.leads_count ? `${camp.leads_count} leads` : 'Audience not set'} · {camp.status || 'draft'}
                      </p>
                    </td>

                    {/* Leads Done */}
                    <td className="py-4 px-5 text-gray-500 font-mono">
                      {camp.status === 'draft' || !camp.leads_contacted
                        ? '—'
                        : `${camp.leads_contacted} / ${camp.leads_count || 0}`}
                    </td>

                    {/* Acceptance */}
                    <td className="py-4 px-5 text-gray-500 font-mono">
                      {camp.leads_contacted && camp.leads_contacted > 0
                        ? `${Math.round((camp.acceptances_count / camp.leads_contacted) * 100)}%`
                        : '—'}
                    </td>

                    {/* Reply */}
                    <td className="py-4 px-5 text-gray-500 font-mono">
                      {camp.leads_contacted && camp.leads_contacted > 0
                        ? `${Math.round((camp.replies_count / camp.leads_contacted) * 100)}%`
                        : '—'}
                    </td>

                    {/* Senders */}
                    <td className="py-4 px-5 text-gray-500">
                      {camp.sender_account_ids?.length
                        ? `${camp.sender_account_ids.length} pooled`
                        : '—'}
                    </td>

                    {/* Last Action */}
                    <td className="py-4 px-5 text-gray-400 font-mono text-[11px]">
                      {camp.status === 'draft' ? '—' : camp.updated_at ? new Date(camp.updated_at).toLocaleDateString() : '—'}
                    </td>

                    {/* Options Menu ⋮ */}
                    <td
                      className="py-4 px-5 text-right relative"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        onClick={() => setMenuOpenId(menuOpenId === camp.id ? null : camp.id)}
                        className="p-1 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
                      >
                        <MoreVertical className="h-4 w-4" />
                      </button>

                      {menuOpenId === camp.id && (
                        <div className="absolute right-5 mt-1 w-40 rounded-xl border border-gray-100 bg-white p-1 shadow-lg z-30 text-xs">
                          <button
                            onClick={() => {
                              setMenuOpenId(null);
                              setSelectedCampaignId(camp.id);
                            }}
                            className="w-full text-left px-3 py-1.5 rounded-lg text-gray-700 hover:bg-gray-50 font-medium"
                          >
                            View details
                          </button>
                          <button
                            onClick={() => {
                              setMenuOpenId(null);
                              if (onOpenWizard) onOpenWizard(camp.id, 2);
                            }}
                            className="w-full text-left px-3 py-1.5 rounded-lg text-gray-700 hover:bg-gray-50 font-medium"
                          >
                            Edit sequence
                          </button>
                          <button
                            onClick={() => handleSoftDelete(camp.id, camp.name)}
                            className="w-full text-left px-3 py-1.5 rounded-lg text-rose-600 hover:bg-rose-50 font-medium flex items-center gap-1.5"
                          >
                            <Trash2 className="h-3 w-3" />
                            Delete
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Booking Modal for LinkedIn Expert */}
      {isBookingModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl border border-gray-100 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-lg bg-indigo-50 text-[#5145cd] flex items-center justify-center">
                  <Calendar className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-gray-900">Book 1:1 Expert Session</h3>
                  <p className="text-[11px] text-gray-400">With Jack (LinkedIn Growth Strategist)</p>
                </div>
              </div>
              <button
                onClick={() => setIsBookingModalOpen(false)}
                className="p-1.5 text-gray-400 hover:text-gray-600 rounded-lg"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <p className="text-xs text-gray-600 leading-relaxed">
              Get personalized feedback on your campaign targeting, message sequences, and sender warmup strategy.
            </p>

            <div className="p-3 rounded-xl bg-gray-50 border border-gray-100 space-y-2 text-xs">
              <div className="flex justify-between text-gray-600">
                <span>Duration</span>
                <span className="font-semibold text-gray-900">30 minutes</span>
              </div>
              <div className="flex justify-between text-gray-600">
                <span>Value</span>
                <span className="font-semibold text-emerald-600">Free ($175 off)</span>
              </div>
            </div>

            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={() => {
                  window.open('https://calendly.com', '_blank');
                  setIsBookingModalOpen(false);
                }}
                className="flex-1 rounded-xl bg-[#5145cd] hover:bg-[#4338ca] text-white py-2.5 text-xs font-semibold shadow-2xs transition-colors flex items-center justify-center gap-1.5"
              >
                Select time on Calendly
                <ExternalLink className="h-3 w-3" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
