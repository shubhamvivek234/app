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
  ArrowRight,
  Copy,
} from 'lucide-react';
import { toast } from 'sonner';
import OutreachCampaignWizard from './OutreachCampaignWizard';
import OutreachCampaignDetail from './OutreachCampaignDetail';

export const PREBUILT_TEMPLATES = [
  {
    id: 'tpl_connect_and_follow_up',
    name: 'Connect and follow up',
    description: 'Standard high-conversion outreach: Clean connection invite with no note, and follow-up message 1 day after acceptance.',
    uses: '1,240',
    acceptance: '32%',
    reply: '24%',
    nodes: [
      {
        id: 'step_connect_root',
        type: 'connection_request',
        title: 'Connection request',
        subtitle: 'Send a connection request',
        delay_hours: 0,
        config: { note: '' },
        position: { x: 250, y: 50 },
      },
      {
        id: 'step_msg_followup',
        type: 'send_message',
        title: 'Send message',
        subtitle: 'Hi {{first_name}}, thanks for...',
        delay_hours: 24,
        config: {
          body: 'Hi {{first_name}}, thanks for connecting! Looking forward to following your work at {{company_name}}.',
        },
        position: { x: 400, y: 200 },
      },
    ],
    edges: [
      { id: 'e_conn_to_msg', source: 'step_connect_root', target: 'step_msg_followup', label: 'accepted' },
    ],
    tree: [
      {
        id: 'step_connect_root',
        type: 'connection_request',
        title: 'Connection request',
        subtitle: 'Send a connection request',
        delay_days: 0,
        config: { note: '' },
        branches: {
          left: {
            condition: 'not accepted yet',
            type: 'danger',
            steps: [],
            endsHere: true,
          },
          right: {
            condition: 'accepted',
            type: 'success',
            steps: [
              {
                id: 'step_msg_followup',
                type: 'send_message',
                title: 'Send message',
                subtitle: 'Hi {{first_name}}, thanks for ...',
                delay_days: 1,
                config: {
                  body: 'Hi {{first_name}}, thanks for connecting! Looking forward to following your work at {{company_name}}.',
                },
                branches: {
                  left: { condition: 'no reply', type: 'danger', steps: [], endsHere: true },
                  right: { condition: 'replied', type: 'success', steps: [], endsHere: true },
                },
              },
            ],
          },
        },
      },
    ],
  },
  {
    id: 'tpl_profile_warmup',
    name: 'Profile warm-up',
    description: 'Multi-touch warm-up sequence: View profile and like recent post before sending a connection invite and welcome message.',
    uses: '890',
    acceptance: '38%',
    reply: '29%',
    nodes: [
      {
        id: 'step_warmup_visit',
        type: 'visit_profile',
        title: 'Visit profile',
        subtitle: "Visit lead's profile",
        delay_hours: 0,
        config: { dwell_mode: 'realistic', skip_if_visited: true },
        position: { x: 250, y: 50 },
      },
      {
        id: 'step_warmup_like',
        type: 'like_last_post',
        title: 'Like last post',
        subtitle: 'Like most recent activity',
        delay_hours: 24,
        config: { max_post_age_days: 30, skip_if_no_posts: true },
        position: { x: 250, y: 180 },
      },
      {
        id: 'step_warmup_connect',
        type: 'connection_request',
        title: 'Connection request',
        subtitle: 'Send a connection request',
        delay_hours: 24,
        config: { note: '' },
        position: { x: 250, y: 310 },
      },
      {
        id: 'step_warmup_msg',
        type: 'send_message',
        title: 'Send message',
        subtitle: 'Hi {{first_name}}, thanks for...',
        delay_hours: 24,
        config: {
          body: 'Hi {{first_name}}, thanks for connecting! Looking forward to following your work at {{company_name}}.',
        },
        position: { x: 400, y: 440 },
      },
    ],
    edges: [
      { id: 'e_warmup_1', source: 'step_warmup_visit', target: 'step_warmup_like' },
      { id: 'e_warmup_2', source: 'step_warmup_like', target: 'step_warmup_connect' },
      { id: 'e_warmup_3', source: 'step_warmup_connect', target: 'step_warmup_msg', label: 'accepted' },
    ],
    tree: [
      {
        id: 'step_warmup_visit',
        type: 'visit_profile',
        title: 'Visit profile',
        subtitle: "Visit lead's profile",
        delay_days: 0,
        config: { dwell_mode: 'realistic', skip_if_visited: true },
      },
      {
        id: 'step_warmup_like',
        type: 'like_last_post',
        title: 'Like last post',
        subtitle: 'Like most recent activity',
        delay_days: 1,
        config: { max_post_age_days: 30, skip_if_no_posts: true },
      },
      {
        id: 'step_warmup_connect',
        type: 'connection_request',
        title: 'Connection request',
        subtitle: 'Send a connection request',
        delay_days: 1,
        config: { note: '' },
        branches: {
          left: {
            condition: 'not accepted yet',
            type: 'danger',
            steps: [],
            endsHere: true,
          },
          right: {
            condition: 'accepted',
            type: 'success',
            steps: [
              {
                id: 'step_warmup_msg',
                type: 'send_message',
                title: 'Send message',
                subtitle: 'Hi {{first_name}}, thanks for...',
                delay_days: 1,
                config: {
                  body: 'Hi {{first_name}}, thanks for connecting! Looking forward to following your work at {{company_name}}.',
                },
                branches: {
                  left: { condition: 'no reply', type: 'danger', steps: [], endsHere: true },
                  right: { condition: 'replied', type: 'success', steps: [], endsHere: true },
                },
              },
            ],
          },
        },
      },
    ],
  },
  {
    id: 'tpl_voice_note_outreach',
    name: 'Voice note outreach',
    description: 'High-reply multi-touch strategy: Profile visit, clean invite, and hyper-personalized AI voice note upon acceptance.',
    uses: '2,150',
    acceptance: '38%',
    reply: '41%',
    nodes: [
      {
        id: 'step_vn_visit',
        type: 'visit_profile',
        title: 'Visit profile',
        subtitle: "Visit lead's profile",
        delay_hours: 0,
        config: {},
        position: { x: 250, y: 50 },
      },
      {
        id: 'step_vn_connect',
        type: 'connection_request',
        title: 'Connection request',
        subtitle: 'Send a connection request',
        delay_hours: 24,
        config: { note: '' },
        position: { x: 250, y: 180 },
      },
      {
        id: 'step_vn_voice',
        type: 'voice_note',
        title: 'Voice note',
        subtitle: 'Personalized AI cloned voice bubble',
        delay_hours: 24,
        config: {
          script: 'Hey {{first_name}}, saw your work at {{company_name}} and wanted to send a quick voice note to introduce myself!',
          fallback: 'Hi {{first_name}}, wanted to reach out and say hello! Excited to connect.',
        },
        position: { x: 400, y: 320 },
      },
      {
        id: 'step_vn_msg',
        type: 'send_message',
        title: 'Send message',
        subtitle: 'Following up on voice note',
        delay_hours: 48,
        config: {
          body: 'Hey {{first_name}}, following up on my quick voice note—would love to hear your thoughts when you have a moment!',
        },
        position: { x: 300, y: 460 },
      },
    ],
    edges: [
      { id: 'e_vn_1', source: 'step_vn_visit', target: 'step_vn_connect' },
      { id: 'e_vn_2', source: 'step_vn_connect', target: 'step_vn_voice', label: 'accepted' },
      { id: 'e_vn_3', source: 'step_vn_voice', target: 'step_vn_msg', label: 'no reply' },
    ],
    tree: [
      {
        id: 'step_vn_visit',
        type: 'visit_profile',
        title: 'Visit profile',
        subtitle: "Visit lead's profile",
        delay_days: 0,
        config: {},
      },
      {
        id: 'step_vn_connect',
        type: 'connection_request',
        title: 'Connection request',
        subtitle: 'Send a connection request',
        delay_days: 1,
        config: { note: '' },
        branches: {
          left: {
            condition: 'not accepted yet',
            type: 'danger',
            steps: [],
            endsHere: true,
          },
          right: {
            condition: 'accepted',
            type: 'success',
            steps: [
              {
                id: 'step_vn_voice',
                type: 'voice_note',
                title: 'Voice note',
                subtitle: 'Personalized AI cloned voice bubble',
                delay_days: 1,
                config: {
                  script: 'Hey {{first_name}}, saw your work at {{company_name}} and wanted to send a quick voice note to introduce myself!',
                  fallback: 'Hi {{first_name}}, wanted to reach out and say hello! Excited to connect.',
                },
                branches: {
                  left: {
                    condition: 'no reply',
                    type: 'danger',
                    steps: [
                      {
                        id: 'step_vn_msg',
                        type: 'send_message',
                        title: 'Send message',
                        subtitle: 'Following up on voice note',
                        delay_days: 2,
                        config: {
                          body: 'Hey {{first_name}}, following up on my quick voice note—would love to hear your thoughts when you have a moment!',
                        },
                        branches: {
                          left: { condition: 'no reply', type: 'danger', steps: [], endsHere: true },
                          right: { condition: 'replied', type: 'success', steps: [], endsHere: true },
                        },
                      },
                    ],
                  },
                  right: { condition: 'replied', type: 'success', steps: [], endsHere: true },
                },
              },
            ],
          },
        },
      },
    ],
  },
  {
    id: 'tpl_multitouch_inmail',
    name: 'Multi-touch InMail & engage',
    description: 'Engage via follow and post like before dispatching targeted InMail directly to decision makers.',
    uses: '1,420',
    acceptance: '45%',
    reply: '34%',
    nodes: [
      {
        id: 'step_inmail_follow',
        type: 'follow',
        title: 'Follow',
        subtitle: "Follow lead's profile",
        delay_hours: 0,
        config: {},
        position: { x: 250, y: 50 },
      },
      {
        id: 'step_inmail_like',
        type: 'like_last_post',
        title: 'Like last post',
        subtitle: 'Like most recent activity',
        delay_hours: 24,
        config: {},
        position: { x: 250, y: 180 },
      },
      {
        id: 'step_inmail_send',
        type: 'inmail',
        title: 'InMail',
        subtitle: 'Send message to 2nd/3rd degree lead',
        delay_hours: 24,
        config: {
          subject: 'Quick question regarding {{company_name}}',
          message: 'Hi {{first_name}}, came across your profile and noticed your focus at {{company_name}}. Would love to share a quick perspective if you are open to it!',
        },
        position: { x: 250, y: 320 },
      },
    ],
    edges: [
      { id: 'e_inmail_1', source: 'step_inmail_follow', target: 'step_inmail_like' },
      { id: 'e_inmail_2', source: 'step_inmail_like', target: 'step_inmail_send' },
    ],
    tree: [
      {
        id: 'step_inmail_follow',
        type: 'follow',
        title: 'Follow',
        subtitle: "Follow lead's profile",
        delay_days: 0,
        config: {},
      },
      {
        id: 'step_inmail_like',
        type: 'like_last_post',
        title: 'Like last post',
        subtitle: 'Like most recent activity',
        delay_days: 1,
        config: {},
      },
      {
        id: 'step_inmail_send',
        type: 'inmail',
        title: 'InMail',
        subtitle: 'Send message to 2nd/3rd degree lead',
        delay_days: 1,
        config: {
          subject: 'Quick question regarding {{company_name}}',
          message: 'Hi {{first_name}}, came across your profile and noticed your focus at {{company_name}}. Would love to share a quick perspective if you are open to it!',
        },
        branches: {
          left: { condition: 'no reply', type: 'danger', steps: [], endsHere: true },
          right: { condition: 'replied', type: 'success', steps: [], endsHere: true },
        },
      },
    ],
  },
];

export default function OutreachCampaigns({
  onOpenWizard,
  selectedCampaignId: propSelectedCampaignId,
  onSelectCampaign: propOnSelectCampaign,
}) {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [activeCampaignId, setActiveCampaignId] = useState(null);
  const [internalSelectedId, setInternalSelectedId] = useState(null);
  const selectedCampaignId = propSelectedCampaignId !== undefined ? propSelectedCampaignId : internalSelectedId;
  const setSelectedCampaignId = (id) => {
    if (propOnSelectCampaign) {
      propOnSelectCampaign(id);
    } else {
      setInternalSelectedId(id);
    }
  };
  const [isTemplatesOpen, setIsTemplatesOpen] = useState(false);
  const [templatesList, setTemplatesList] = useState([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [undoAlert, setUndoAlert] = useState(null); // { id, name }
  const [menuOpenId, setMenuOpenId] = useState(null);
  const [newCampaignModalOpen, setNewCampaignModalOpen] = useState(false);
  const [scratchCampaignName, setScratchCampaignName] = useState('');

  const fetchCampaigns = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/campaigns', {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setCampaigns(data || []);
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
        if (Array.isArray(data) && data.length > 0) {
          setTemplatesList(data);
        }
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
        toast.success('Template deleted');
      } else {
        toast.error('Failed to delete template');
      }
    } catch (err) {
      console.error('Failed to delete template:', err);
      toast.error('Error deleting template');
    }
  };

  const handleUseTemplate = async (tpl) => {
    // 1. Immediately close templates view so user transitions to campaign builder
    setIsTemplatesOpen(false);

    const fullTpl =
      PREBUILT_TEMPLATES.find(
        (p) => p.id === tpl.id || (tpl.id === 'tpl_inmail_engage' && p.id === 'tpl_multitouch_inmail') || p.name === tpl.name
      ) || tpl;

    // 3. Cache template tree locally so SequenceCanvas renders the pre-made campaign immediately
    if (fullTpl.tree) {
      try {
        localStorage.setItem('pending_template_tree', JSON.stringify(fullTpl.tree));
      } catch (_) {}
    }

    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/campaigns/auto-draft', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          name: fullTpl.name || 'Connect and follow up',
          draft_step: 2,
          draft_progress: 60,
          next_step_label: 'Next: Launch',
        }),
      });

      if (res.ok) {
        const draft = await res.json();
        if (fullTpl.nodes && fullTpl.edges) {
          await fetch('/api/v1/outreach/sequences', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: token ? `Bearer ${token}` : '',
            },
            body: JSON.stringify({
              campaign_id: draft.id,
              nodes: fullTpl.nodes,
              edges: fullTpl.edges,
              tree: fullTpl.tree || null,
            }),
          }).catch((err) => console.warn('Could not save sequence to backend:', err));
        }

        toast.success(`Template loaded: “${fullTpl.name}”`);
        if (onOpenWizard) {
          onOpenWizard(draft.id, 2);
        } else {
          setActiveCampaignId(draft.id);
          setIsWizardOpen(true);
        }
        return;
      }
    } catch (err) {
      console.error('Failed to use template via auto-draft:', err);
    }

    // Reliable Fallback: Always open wizard on step 2 even if network failed
    const fallbackId = `camp_${Date.now()}`;
    toast.success(`Template loaded: “${fullTpl.name}”`);
    if (onOpenWizard) {
      onOpenWizard(fallbackId, 2);
    } else {
      setActiveCampaignId(fallbackId);
      setIsWizardOpen(true);
    }
  };

  // Auto-drafting when user clicks "New campaign"
  const handleCreateNewCampaign = async (nameOverride) => {
    const safeName = typeof nameOverride === 'string' && nameOverride.trim()
      ? nameOverride.trim()
      : `test${campaigns.length + 1}`;

    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/campaigns/auto-draft', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          name: safeName,
          draft_step: 2,
          draft_progress: 40,
          next_step_label: 'Next: add your leads',
        }),
      });
      if (res.ok) {
        const draft = await res.json();
        toast.success(`Campaign created: “${safeName}”`);
        if (onOpenWizard) {
          onOpenWizard(draft.id, 2);
        } else {
          setActiveCampaignId(draft.id);
          setIsWizardOpen(true);
        }
        return;
      }
    } catch (err) {
      console.error('Failed to auto-draft campaign:', err);
    }

    // Reliable Fallback: Always open campaign wizard immediately
    const fallbackId = `camp_${Date.now()}`;
    toast.success(`Campaign started: “${safeName}”`);
    if (onOpenWizard) {
      onOpenWizard(fallbackId, 2);
    } else {
      setActiveCampaignId(fallbackId);
      setIsWizardOpen(true);
    }
  };

  const handlePauseCampaign = async (campaignId, campaignName) => {
    setMenuOpenId(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/campaigns/${campaignId}/pause`, {
        method: 'POST',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        toast.success(`Paused “${campaignName}”`);
        fetchCampaigns();
      } else {
        toast.error('Failed to pause campaign');
      }
    } catch (err) {
      console.error('Failed to pause campaign:', err);
      toast.error('Error pausing campaign');
    }
  };

  const handleResumeCampaign = async (campaignId, campaignName) => {
    setMenuOpenId(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/campaigns/${campaignId}/launch`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ status: 'active' }),
      });
      if (res.ok) {
        toast.success(`Resumed “${campaignName}”`);
        fetchCampaigns();
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || 'Failed to resume campaign');
      }
    } catch (err) {
      console.error('Failed to resume campaign:', err);
      toast.error('Error resuming campaign');
    }
  };

  const handleDuplicateCampaign = async (campaignId) => {
    setMenuOpenId(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/campaigns/${campaignId}/duplicate`, {
        method: 'POST',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const cloned = await res.json();
        toast.success(`Duplicated as “${cloned.name}”`);
        fetchCampaigns();
      } else {
        toast.error('Failed to duplicate campaign');
      }
    } catch (err) {
      console.error('Failed to duplicate campaign:', err);
      toast.error('Error duplicating campaign');
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
        toast.success(`Deleted “${campaignName}”`);
        fetchCampaigns();
      } else {
        toast.error('Failed to delete campaign');
      }
    } catch (err) {
      console.error('Failed to delete campaign:', err);
      toast.error('Error deleting campaign');
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
        toast.success('Campaign restored');
        fetchCampaigns();
      } else {
        toast.error('Failed to restore campaign');
      }
    } catch (err) {
      console.error('Failed to restore campaign:', err);
      toast.error('Error restoring campaign');
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
    const displayTemplates = templatesList.length > 0 ? templatesList : PREBUILT_TEMPLATES;

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
            onClick={() => {
              setScratchCampaignName(`Campaign #${campaigns.length + 1}`);
              setNewCampaignModalOpen(true);
            }}
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

      {/* Filter Row: Segmented Pills & Search Input matching media_1790104399010.png */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
        <div className="inline-flex items-center bg-gray-100/80 p-1 rounded-xl gap-1">
          {[
            { id: 'all', label: 'All', count: campaigns.length },
            { id: 'sending', label: 'Sending', count: campaigns.filter((c) => c.status === 'active').length },
            { id: 'paused', label: 'Paused', count: campaigns.filter((c) => c.status === 'paused').length },
            { id: 'draft', label: 'Draft', count: campaigns.filter((c) => c.status === 'draft').length },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setStatusFilter(tab.id)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all inline-flex items-center gap-1.5 ${
                statusFilter === tab.id
                  ? 'bg-white text-gray-900 shadow-2xs'
                  : 'text-gray-500 hover:text-gray-800'
              }`}
            >
              <span>{tab.label}</span>
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                  statusFilter === tab.id ? 'bg-gray-100 text-gray-700' : 'text-gray-400'
                }`}
              >
                {tab.count}
              </span>
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
              onClick={() => {
                setScratchCampaignName(`Campaign #${campaigns.length + 1}`);
                setNewCampaignModalOpen(true);
              }}
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
                        <div className="absolute right-5 mt-1 w-44 rounded-xl border border-gray-100 bg-white p-1 shadow-lg z-30 text-xs">
                          {camp.status === 'active' && (
                            <button
                              onClick={() => handlePauseCampaign(camp.id, camp.name)}
                              className="w-full text-left px-3 py-1.5 rounded-lg text-amber-700 hover:bg-amber-50 font-medium flex items-center gap-2"
                            >
                              <Pause className="h-3.5 w-3.5 text-amber-600" />
                              Pause campaign
                            </button>
                          )}
                          {camp.status === 'paused' && (
                            <button
                              onClick={() => handleResumeCampaign(camp.id, camp.name)}
                              className="w-full text-left px-3 py-1.5 rounded-lg text-emerald-700 hover:bg-emerald-50 font-medium flex items-center gap-2"
                            >
                              <Play className="h-3.5 w-3.5 text-emerald-600" />
                              Resume campaign
                            </button>
                          )}
                          {camp.status === 'draft' && (
                            <button
                              onClick={() => {
                                setMenuOpenId(null);
                                if (onOpenWizard) onOpenWizard(camp.id, camp.draft_step || 2);
                              }}
                              className="w-full text-left px-3 py-1.5 rounded-lg text-indigo-700 hover:bg-indigo-50 font-medium flex items-center gap-2"
                            >
                              <Play className="h-3.5 w-3.5 text-indigo-600" />
                              Resume draft
                            </button>
                          )}
                          <button
                            onClick={() => handleDuplicateCampaign(camp.id)}
                            className="w-full text-left px-3 py-1.5 rounded-lg text-gray-700 hover:bg-gray-50 font-medium flex items-center gap-2"
                          >
                            <Copy className="h-3.5 w-3.5 text-gray-500" />
                            Duplicate
                          </button>
                          <button
                            onClick={() => {
                              setMenuOpenId(null);
                              setSelectedCampaignId(camp.id);
                            }}
                            className="w-full text-left px-3 py-1.5 rounded-lg text-gray-700 hover:bg-gray-50 font-medium flex items-center gap-2"
                          >
                            <ExternalLink className="h-3.5 w-3.5 text-gray-500" />
                            View details
                          </button>
                          <button
                            onClick={() => {
                              setMenuOpenId(null);
                              if (onOpenWizard) onOpenWizard(camp.id, 2);
                            }}
                            className="w-full text-left px-3 py-1.5 rounded-lg text-gray-700 hover:bg-gray-50 font-medium flex items-center gap-2"
                          >
                            <Pencil className="h-3.5 w-3.5 text-gray-500" />
                            Edit sequence
                          </button>
                          <div className="h-px bg-gray-100 my-1" />
                          <button
                            onClick={() => handleSoftDelete(camp.id, camp.name)}
                            className="w-full text-left px-3 py-1.5 rounded-lg text-rose-600 hover:bg-rose-50 font-medium flex items-center gap-2"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
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

      {/* Start a new campaign Modal */}
      {newCampaignModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 overflow-y-auto">
          <div className="relative w-full max-w-2xl rounded-2xl bg-white shadow-2xl border border-gray-100 p-6 space-y-6 animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-xl font-extrabold text-gray-900 tracking-tight">
                  Start a new campaign
                </h2>
                <p className="text-xs text-gray-500 mt-1">
                  Build the outreach first. You add leads in the next step.
                </p>
              </div>
              <button
                onClick={() => setNewCampaignModalOpen(false)}
                className="p-1 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
                title="Close"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* 2-Card Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-stretch">
              {/* Card 1: Build it your way */}
              <div className="flex flex-col rounded-2xl border border-gray-200 bg-white p-4 hover:border-indigo-300 hover:shadow-md transition-all group">
                {/* Visual Art Box */}
                <div className="relative h-32 rounded-xl border border-indigo-100 bg-gradient-to-br from-[#EEF0FF] to-[#E3E7FF] p-3 flex flex-col justify-between overflow-hidden">
                  <div className="flex items-center justify-between">
                    <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-indigo-600 text-white font-bold text-[10px]">
                      in
                    </span>
                    <span className="px-2 py-0.5 rounded-full bg-white/80 text-[10px] font-semibold text-indigo-700 shadow-2xs">
                      Scratch
                    </span>
                  </div>
                  <div className="space-y-1.5">
                    <div className="h-2 w-28 bg-white/70 rounded-full" />
                    <div className="h-2 w-16 bg-white/50 rounded-full" />
                  </div>
                </div>

                {/* Content */}
                <div className="mt-4 flex-1 flex flex-col justify-between space-y-3">
                  <div>
                    <h3 className="text-base font-extrabold text-gray-900">
                      Build it your way
                    </h3>
                    <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                      Create a draft and add leads from an existing lead list. Set the campaign name and supported lead filters.
                    </p>
                  </div>

                  <div className="space-y-2 pt-2">
                    <input
                      type="text"
                      value={scratchCampaignName}
                      onChange={(e) => setScratchCampaignName(e.target.value)}
                      placeholder="e.g. Q4 Growth Leaders"
                      className="w-full text-xs rounded-xl border border-gray-200 px-3 py-2 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                    />
                    <button
                      onClick={() => {
                        const name = scratchCampaignName.trim() || `Campaign #${campaigns.length + 1}`;
                        setNewCampaignModalOpen(false);
                        handleCreateNewCampaign(name);
                      }}
                      className="w-full inline-flex items-center justify-center gap-1.5 rounded-xl bg-[#5145cd] hover:bg-[#4338ca] px-4 py-2.5 text-xs font-bold text-white shadow-xs transition-colors"
                    >
                      Build from scratch
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Card 2: Use a proven template [Recommended] */}
              <div className="flex flex-col rounded-2xl border-2 border-indigo-200/90 bg-indigo-50/10 p-4 hover:border-indigo-400 hover:shadow-md transition-all group relative">
                {/* Recommended Badge */}
                <div className="absolute -top-2.5 right-4 px-2 py-0.5 rounded-full bg-[#5145cd] text-white text-[10px] font-bold shadow-xs">
                  Recommended
                </div>

                {/* Visual Art Box */}
                <div className="relative h-32 rounded-xl border border-rose-100 bg-gradient-to-br from-[#FDECEC] to-[#FBE3E8] p-3 flex flex-col justify-between overflow-hidden">
                  <div className="flex items-center justify-between">
                    <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-rose-500 text-white font-bold text-[10px]">
                      %
                    </span>
                    <div className="flex items-center gap-1">
                      <span className="px-2 py-0.5 rounded-md bg-white/90 text-[10px] font-bold text-indigo-700 shadow-2xs">
                        32% Acc
                      </span>
                      <span className="px-2 py-0.5 rounded-md bg-white/90 text-[10px] font-bold text-emerald-700 shadow-2xs">
                        24% Rep
                      </span>
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <div className="h-2 w-32 bg-white/70 rounded-full" />
                    <div className="h-2 w-20 bg-white/50 rounded-full" />
                  </div>
                </div>

                {/* Content */}
                <div className="mt-4 flex-1 flex flex-col justify-between space-y-3">
                  <div>
                    <h3 className="text-base font-extrabold text-gray-900">
                      Use a proven template
                    </h3>
                    <p className="text-xs text-indigo-600 font-semibold mt-0.5">
                      Most teams start here.
                    </p>
                    <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                      Browse and review available prebuilt sequences with proven conversion data and instant setup.
                    </p>
                  </div>

                  <div className="pt-2">
                    <button
                      onClick={() => {
                        setNewCampaignModalOpen(false);
                        setIsTemplatesOpen(true);
                      }}
                      className="w-full inline-flex items-center justify-center gap-1.5 rounded-xl border border-indigo-200 bg-white hover:bg-indigo-50 px-4 py-2.5 text-xs font-bold text-indigo-700 shadow-2xs transition-colors"
                    >
                      <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
                      Browse templates
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
