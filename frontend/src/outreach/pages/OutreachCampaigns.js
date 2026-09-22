import React, { useState, useEffect } from 'react';
import { Plus, Search, Sparkles, Play, Pause, MoreVertical, RefreshCw, Users, MessageSquare } from 'lucide-react';
import OutreachCampaignWizard from './OutreachCampaignWizard';

export default function OutreachCampaigns({ onOpenWizard }) {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [activeCampaignId, setActiveCampaignId] = useState(null);

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

  useEffect(() => {
    fetchCampaigns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleLaunch = async (campaignId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/campaigns/${campaignId}/launch`, {
        method: 'POST',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) fetchCampaigns();
    } catch (err) {
      console.error('Launch failed:', err);
    }
  };

  const handlePause = async (campaignId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/campaigns/${campaignId}/pause`, {
        method: 'POST',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) fetchCampaigns();
    } catch (err) {
      console.error('Pause failed:', err);
    }
  };

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

  const filteredCampaigns = campaigns.filter((c) => {
    if (statusFilter === 'sending') return c.status === 'active';
    if (statusFilter === 'paused') return c.status === 'paused';
    if (statusFilter === 'draft') return c.status === 'draft';
    return true;
  });

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      {/* Header (Part 1, Image 2) */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Campaigns</h1>
          <p className="text-xs text-gray-500 mt-0.5">Your outreach campaigns, newest first.</p>
        </div>
        <div className="flex items-center gap-3">
          <button className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-4 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-50 shadow-sm">
            <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
            Browse winning templates
          </button>
          <button
            onClick={() => {
              if (onOpenWizard) {
                onOpenWizard('new');
              } else {
                setActiveCampaignId(null);
                setIsWizardOpen(true);
              }
            }}
            className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 shadow-sm transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            New campaign
          </button>
        </div>
      </div>

      {/* Filter Tabs & Search Bar */}
      <div className="flex items-center justify-between mb-4 border-b border-gray-200 pb-3">
        <div className="flex items-center gap-2">
          {['all', 'sending', 'paused', 'draft'].map((tab) => (
            <button
              key={tab}
              onClick={() => setStatusFilter(tab)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold capitalize transition-colors ${
                statusFilter === tab
                  ? 'bg-indigo-50 text-indigo-700'
                  : 'text-gray-500 hover:text-gray-800'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        <div className="relative w-64">
          <Search className="absolute left-3 top-2 h-3.5 w-3.5 text-gray-400" />
          <input
            type="text"
            placeholder="Search campaigns..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-xl border border-gray-200 bg-white pl-8 pr-3 py-1.5 text-xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
          />
        </div>
      </div>

      {/* Campaigns Table */}
      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-gray-400">
            <RefreshCw className="h-6 w-6 animate-spin" />
          </div>
        ) : filteredCampaigns.length === 0 ? (
          <div className="p-12 text-center text-gray-500">
            <p className="text-sm font-medium">No campaigns found in this view.</p>
            <button
              onClick={() => {
                if (onOpenWizard) onOpenWizard('new');
                else setIsWizardOpen(true);
              }}
              className="mt-3 text-xs font-semibold text-indigo-600 hover:text-indigo-800"
            >
              + Create your first outreach campaign
            </button>
          </div>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="border-b border-gray-200 bg-gray-50/70 text-gray-500 uppercase font-semibold tracking-wider text-[10px]">
              <tr>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Name</th>
                <th className="py-3 px-4">Leads Done</th>
                <th className="py-3 px-4">Acceptance</th>
                <th className="py-3 px-4">Reply</th>
                <th className="py-3 px-4">Senders</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filteredCampaigns.map((camp) => (
                <tr key={camp.id} className="hover:bg-gray-50/60 transition-colors">
                  <td className="py-3.5 px-4">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                      camp.status === 'active' ? 'bg-emerald-50 text-emerald-700' :
                      camp.status === 'paused' ? 'bg-amber-50 text-amber-700' :
                      'bg-gray-100 text-gray-600'
                    }`}>
                      {camp.status}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 font-bold text-gray-900">
                    <button
                      onClick={() => {
                        if (onOpenWizard) {
                          onOpenWizard(camp.id);
                        } else {
                          setActiveCampaignId(camp.id);
                          setIsWizardOpen(true);
                        }
                      }}
                      className="hover:text-indigo-600 hover:underline text-left"
                    >
                      {camp.name}
                    </button>
                    <p className="text-[10px] text-gray-400 font-normal">
                      Audience: {camp.leads_count || 0} leads
                    </p>
                  </td>
                  <td className="py-3.5 px-4 font-semibold text-gray-700">
                    {camp.leads_contacted || 0} / {camp.leads_count || 0}
                  </td>
                  <td className="py-3.5 px-4 font-semibold text-gray-700">
                    {camp.leads_contacted > 0 ? `${Math.round((camp.acceptances_count / camp.leads_contacted) * 100)}%` : '—'}
                  </td>
                  <td className="py-3.5 px-4 font-semibold text-gray-700">
                    {camp.leads_contacted > 0 ? `${Math.round((camp.replies_count / camp.leads_contacted) * 100)}%` : '—'}
                  </td>
                  <td className="py-3.5 px-4 text-gray-600">
                    {camp.sender_account_ids?.length || 0} pooled
                  </td>
                  <td className="py-3.5 px-4 text-right">
                    {camp.status === 'draft' || camp.status === 'paused' ? (
                      <button
                        onClick={() => handleLaunch(camp.id)}
                        className="inline-flex items-center gap-1 text-emerald-600 hover:text-emerald-800 font-semibold p-1"
                      >
                        <Play className="h-3.5 w-3.5" />
                        Launch
                      </button>
                    ) : (
                      <button
                        onClick={() => handlePause(camp.id)}
                        className="inline-flex items-center gap-1 text-amber-600 hover:text-amber-800 font-semibold p-1"
                      >
                        <Pause className="h-3.5 w-3.5" />
                        Pause
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
