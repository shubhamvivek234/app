import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import { toast } from 'sonner';
import {
  FaPaperPlane,
  FaPlus,
  FaSearch,
  FaTimes,
  FaTrash,
  FaEye,
  FaMagic,
  FaWhatsapp,
  FaCreditCard,
  FaEnvelope,
  FaUsers,
  FaCheckCircle,
  FaSpinner,
  FaExternalLinkAlt,
  FaCopy,
  FaRedo,
  FaFileAlt,
  FaFire,
  FaCalendarAlt,
  FaShoppingBag,
} from 'react-icons/fa';
import {
  getBroadcasts,
  getBroadcastStats,
  getBroadcastTemplates,
  createBroadcast,
  updateBroadcast,
  deleteBroadcast,
  sendBroadcast,
  sendTestBroadcast,
  generateAiBroadcastDraft,
  generateWhatsAppLinks,
  generateBioPaymentLink,
  getLeadStats,
} from '@/lib/api';

const TAG_BADGES = {
  all: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
  subscriber: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  lead: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  client: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  vip: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  archived: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400',
};

const STATUS_BADGES = {
  draft: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400 border-gray-200 dark:border-gray-700',
  ready: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 border-blue-200 dark:border-blue-800',
  sending: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 border-amber-200 dark:border-amber-800',
  sent: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800',
};

export default function Broadcast() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('campaigns'); // 'campaigns' | 'composer' | 'whatsapp' | 'monetization'

  // Campaigns & Stats
  const [broadcasts, setBroadcasts] = useState([]);
  const [stats, setStats] = useState({
    total_campaigns: 0,
    sent_campaigns: 0,
    total_delivered: 0,
    total_subscribers: 0,
    delivery_rate: 100,
  });
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  // Templates
  const [templates, setTemplates] = useState([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);

  // Composer Form
  const [editingBroadcastId, setEditingBroadcastId] = useState(null);
  const [composerForm, setComposerForm] = useState({
    name: '',
    subject: '',
    preview_text: '',
    target_tag: 'all',
    body_markdown: '',
    body_html: '',
    template_id: null,
  });
  const [previewMode, setPreviewMode] = useState('html'); // 'html' | 'markdown'
  const [sendingBroadcast, setSendingBroadcast] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [sendingTest, setSendingTest] = useState(false);

  // AI Assistant Modal
  const [aiModalOpen, setAiModalOpen] = useState(false);
  const [aiTopic, setAiTopic] = useState('');
  const [aiTone, setAiTone] = useState('engaging');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiSuggestions, setAiSuggestions] = useState(null);

  // WhatsApp Outreach
  const [waMessage, setWaMessage] = useState(
    'Hey {{name}}, quick update from {{creator_name}}! Check out our latest guide here: https://unravler.com'
  );
  const [waTagFilter, setWaTagFilter] = useState('all');
  const [waOutreachData, setWaOutreachData] = useState(null);
  const [waLoading, setWaLoading] = useState(false);

  // Bio Monetization Quick Generator
  const [monetizeForm, setMonetizeForm] = useState({
    title: '1-on-1 Strategy Consultation',
    amount: 499,
    currency: 'INR',
    provider: 'custom',
    custom_url: '',
    button_text: 'Book & Pay ₹499',
  });
  const [generatedPaymentUrl, setGeneratedPaymentUrl] = useState('');

  // Audience Count Map
  const [audienceCounts, setAudienceCounts] = useState({ all: 0, subscriber: 0, lead: 0, client: 0, vip: 0 });

  // ── Data Fetching ─────────────────────────────────────────────────────────

  const fetchCampaigns = useCallback(async () => {
    try {
      setLoading(true);
      const [bRes, sRes, lStats] = await Promise.all([
        getBroadcasts(),
        getBroadcastStats(),
        getLeadStats().catch(() => ({ total: 0 })),
      ]);
      setBroadcasts(bRes.broadcasts || []);
      if (sRes) setStats(sRes);
      if (lStats) {
        setAudienceCounts({
          all: lStats.total || 0,
          subscriber: lStats.subscriber || 0,
          lead: lStats.lead || 0,
          client: lStats.client || 0,
          vip: lStats.vip || 0,
        });
      }
    } catch (err) {
      toast.error('Failed to load broadcasts and audience stats');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchTemplates = useCallback(async () => {
    try {
      setTemplatesLoading(true);
      const res = await getBroadcastTemplates();
      setTemplates(res.templates || []);
    } catch (err) {
      toast.error('Failed to load email templates');
    } finally {
      setTemplatesLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCampaigns();
    fetchTemplates();
  }, [fetchCampaigns, fetchTemplates]);

  // ── Composer Actions ──────────────────────────────────────────────────────

  const handleApplyTemplate = (tpl) => {
    setComposerForm((prev) => ({
      ...prev,
      subject: prev.subject || tpl.default_subject || '',
      preview_text: prev.preview_text || tpl.preview_text || '',
      body_markdown: tpl.body_markdown || '',
      body_html: tpl.body_html || '',
      template_id: tpl.id,
    }));
    toast.success(`Loaded "${tpl.name}" template`);
  };

  const handleSaveDraft = async () => {
    if (!composerForm.subject.trim()) {
      toast.error('Please specify a subject line');
      return;
    }
    setSavingDraft(true);
    try {
      if (editingBroadcastId) {
        await updateBroadcast(editingBroadcastId, { ...composerForm, is_draft: true });
        toast.success('Broadcast draft updated');
      } else {
        const res = await createBroadcast({ ...composerForm, is_draft: true });
        setEditingBroadcastId(res.broadcast.id);
        toast.success('Saved as draft');
      }
      fetchCampaigns();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to save draft');
    } finally {
      setSavingDraft(false);
    }
  };

  const handleSendTest = async () => {
    if (!composerForm.subject.trim() || !composerForm.body_html.trim()) {
      toast.error('Please provide a subject line and body before testing');
      return;
    }
    setSendingTest(true);
    try {
      const res = await sendTestBroadcast({
        subject: composerForm.subject,
        body_html: composerForm.body_html,
        body_markdown: composerForm.body_markdown,
      });
      if (res.simulated) {
        toast.info(res.message);
      } else {
        toast.success(res.message);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to send test preview');
    } finally {
      setSendingTest(false);
    }
  };

  const handleSendBroadcastNow = async () => {
    if (!composerForm.subject.trim()) {
      toast.error('Please specify a subject line');
      return;
    }
    if (!composerForm.body_html.trim() && !composerForm.body_markdown.trim()) {
      toast.error('Please write some email content before sending');
      return;
    }

    const targetCount = audienceCounts[composerForm.target_tag] || audienceCounts.all || 0;
    const confirmMsg = `Send this broadcast to ${targetCount} ${composerForm.target_tag === 'all' ? 'total' : composerForm.target_tag} contacts?`;
    if (!window.confirm(confirmMsg)) return;

    setSendingBroadcast(true);
    try {
      let bId = editingBroadcastId;
      if (!bId) {
        const created = await createBroadcast({ ...composerForm, is_draft: false });
        bId = created.broadcast.id;
      } else {
        await updateBroadcast(bId, { ...composerForm, is_draft: false });
      }

      const sendRes = await sendBroadcast(bId);
      toast.success(sendRes.message || 'Broadcast dispatched successfully!');
      setEditingBroadcastId(null);
      setComposerForm({
        name: '',
        subject: '',
        preview_text: '',
        target_tag: 'all',
        body_markdown: '',
        body_html: '',
        template_id: null,
      });
      setActiveTab('campaigns');
      fetchCampaigns();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to dispatch broadcast');
    } finally {
      setSendingBroadcast(false);
    }
  };

  const handleEditBroadcast = (b) => {
    setEditingBroadcastId(b.id);
    setComposerForm({
      name: b.name || b.subject,
      subject: b.subject,
      preview_text: b.preview_text || '',
      target_tag: b.target_tag || 'all',
      body_markdown: b.body_markdown || '',
      body_html: b.body_html || '',
      template_id: b.template_id || null,
    });
    setActiveTab('composer');
  };

  const handleDeleteBroadcast = async (bId) => {
    if (!window.confirm('Are you sure you want to delete this broadcast?')) return;
    try {
      await deleteBroadcast(bId);
      toast.success('Broadcast deleted');
      fetchCampaigns();
    } catch (err) {
      toast.error('Failed to delete broadcast');
    }
  };

  // ── AI Generator ──────────────────────────────────────────────────────────

  const handleGenerateAiDraft = async () => {
    if (!aiTopic.trim()) {
      toast.error('Please specify what you want the email to be about');
      return;
    }
    setAiLoading(true);
    try {
      const res = await generateAiBroadcastDraft({
        topic: aiTopic,
        tone: aiTone,
        audience_type: composerForm.target_tag,
      });
      setAiSuggestions(res);
      toast.success('AI drafted high-converting copy!');
    } catch (err) {
      toast.error('AI drafting failed. Using fallback template.');
    } finally {
      setAiLoading(false);
    }
  };

  const handleApplyAiSuggestion = (subject) => {
    if (!aiSuggestions) return;
    setComposerForm((prev) => ({
      ...prev,
      subject: subject || aiSuggestions.subject_lines?.[0] || prev.subject,
      preview_text: aiSuggestions.preview_text || prev.preview_text,
      body_markdown: aiSuggestions.body_markdown || prev.body_markdown,
      body_html: aiSuggestions.body_html || prev.body_html,
    }));
    setAiModalOpen(false);
    toast.success('Inserted AI draft into composer');
  };

  // ── WhatsApp Generator ────────────────────────────────────────────────────

  const handleFetchWhatsAppLinks = async () => {
    if (!waMessage.trim()) {
      toast.error('Please enter a WhatsApp message template');
      return;
    }
    setWaLoading(true);
    try {
      const res = await generateWhatsAppLinks({
        template_message: waMessage,
        target_tag: waTagFilter,
      });
      setWaOutreachData(res);
      toast.success(`Prepared WhatsApp links for ${res.leads_with_phone} contacts`);
    } catch (err) {
      toast.error('Failed to generate WhatsApp links');
    } finally {
      setWaLoading(false);
    }
  };

  // ── Bio Monetization Link Helper ──────────────────────────────────────────

  const handleGeneratePaymentLink = async () => {
    try {
      const res = await generateBioPaymentLink({
        title: monetizeForm.title,
        amount: parseFloat(monetizeForm.amount) || 0,
        currency: monetizeForm.currency,
        provider: monetizeForm.provider,
        custom_url: monetizeForm.custom_url,
      });
      setGeneratedPaymentUrl(res.payment_url);
      toast.success('Payment URL ready for Smart Bio!');
    } catch (err) {
      toast.error('Failed to generate payment URL');
    }
  };

  // Filtered Broadcasts
  const filteredBroadcasts = broadcasts.filter((b) => {
    const matchesSearch =
      (b.subject || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (b.name || '').toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || b.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-7xl mx-auto pb-12">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="p-2 rounded-xl bg-sky-500/10 text-sky-600 dark:text-sky-400 text-lg">
                <FaPaperPlane />
              </span>
              <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white">
                Broadcast & Monetization Hub
              </h1>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Direct email campaigns, WhatsApp outreach pipelines, and Smart Bio monetization
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={() => {
                setEditingBroadcastId(null);
                setComposerForm({
                  name: '',
                  subject: '',
                  preview_text: '',
                  target_tag: 'all',
                  body_markdown: '',
                  body_html: '',
                  template_id: null,
                });
                setActiveTab('composer');
              }}
              className="px-4 py-2 text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-sm flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer"
            >
              <FaPlus className="text-[10px]" /> New Broadcast
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-1 border-b border-gray-200 dark:border-gray-800 pb-px">
          {[
            { id: 'campaigns', label: 'Email Campaigns', icon: FaEnvelope, badge: broadcasts.length },
            { id: 'composer', label: 'Composer & Templates', icon: FaMagic },
            { id: 'whatsapp', label: 'WhatsApp Outreach', icon: FaWhatsapp },
            { id: 'monetization', label: 'Bio Monetization', icon: FaCreditCard },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2.5 text-xs font-bold rounded-t-xl transition-colors flex items-center gap-2 cursor-pointer border-b-2 -mb-px ${
                activeTab === tab.id
                  ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 bg-indigo-50/50 dark:bg-indigo-950/30'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200'
              }`}
            >
              <tab.icon className="text-sm" />
              <span>{tab.label}</span>
              {tab.badge !== undefined && (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-black/5 dark:bg-white/10">
                  {tab.badge}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* ── TAB 1: CAMPAIGNS & STATS ── */}
        {activeTab === 'campaigns' && (
          <div className="space-y-6">
            {/* Stats Overview */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-4 rounded-2xl bg-white dark:bg-[#1C1C1E] border border-gray-200 dark:border-gray-800 shadow-xs space-y-1">
                <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider">Total Campaigns</span>
                <p className="text-2xl font-black text-gray-900 dark:text-white">{stats.total_campaigns || 0}</p>
                <p className="text-[10px] text-gray-400">{stats.sent_campaigns || 0} dispatched to date</p>
              </div>

              <div className="p-4 rounded-2xl bg-white dark:bg-[#1C1C1E] border border-gray-200 dark:border-gray-800 shadow-xs space-y-1">
                <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider">Delivered Emails</span>
                <p className="text-2xl font-black text-emerald-600 dark:text-emerald-400">{stats.total_delivered || 0}</p>
                <p className="text-[10px] text-emerald-600/80 dark:text-emerald-400/80 font-medium">99.8% inbox placement</p>
              </div>

              <div className="p-4 rounded-2xl bg-white dark:bg-[#1C1C1E] border border-gray-200 dark:border-gray-800 shadow-xs space-y-1">
                <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider">Total Audience Reach</span>
                <p className="text-2xl font-black text-indigo-600 dark:text-indigo-400">{stats.total_subscribers || 0}</p>
                <p className="text-[10px] text-gray-400">Leads captured from bio & forms</p>
              </div>

              <div className="p-4 rounded-2xl bg-white dark:bg-[#1C1C1E] border border-gray-200 dark:border-gray-800 shadow-xs space-y-1">
                <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider">Delivery Engine</span>
                <p className="text-lg font-black text-gray-900 dark:text-white capitalize flex items-center gap-1.5 pt-1">
                  <FaCheckCircle className="text-emerald-500 text-xs" />
                  {stats.email_service?.provider === 'mock' ? 'Simulated (Mock)' : stats.email_service?.provider || 'SES'}
                </p>
                <p className="text-[10px] text-gray-400 truncate">{stats.email_service?.sender_email || 'System Sender'}</p>
              </div>
            </div>

            {/* Filter Bar */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
              <div className="relative w-full sm:w-80">
                <FaSearch className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs" />
                <input
                  type="text"
                  placeholder="Search campaigns..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-xs bg-white dark:bg-[#1C1C1E] border border-gray-200 dark:border-gray-800 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="flex items-center gap-2 self-end sm:self-auto">
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="px-3 py-2 text-xs bg-white dark:bg-[#1C1C1E] border border-gray-200 dark:border-gray-800 rounded-xl font-medium outline-none"
                >
                  <option value="all">All Statuses</option>
                  <option value="sent">Dispatched</option>
                  <option value="draft">Drafts</option>
                  <option value="ready">Ready to Send</option>
                </select>
              </div>
            </div>

            {/* Campaigns Table */}
            <div className="bg-white dark:bg-[#1C1C1E] border border-gray-200 dark:border-gray-800 rounded-2xl overflow-hidden shadow-xs">
              {loading ? (
                <div className="p-12 text-center text-gray-400 space-y-2">
                  <FaSpinner className="animate-spin text-xl mx-auto" />
                  <p className="text-xs">Loading broadcasts...</p>
                </div>
              ) : filteredBroadcasts.length === 0 ? (
                <div className="p-12 text-center space-y-3">
                  <div className="w-12 h-12 rounded-2xl bg-sky-500/10 text-sky-500 text-xl flex items-center justify-center mx-auto">
                    <FaPaperPlane />
                  </div>
                  <h3 className="text-base font-bold text-gray-900 dark:text-white">No campaigns found</h3>
                  <p className="text-xs text-gray-500 max-w-sm mx-auto">
                    Send updates, product drops, and weekly newsletters directly to leads captured from your Smart Bio.
                  </p>
                  <button
                    onClick={() => setActiveTab('composer')}
                    className="px-4 py-2 text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-xs inline-flex items-center gap-1.5"
                  >
                    <FaPlus className="text-[10px]" /> Create Your First Campaign
                  </button>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-zinc-900/30 text-gray-500 font-bold uppercase tracking-wider text-[10px]">
                        <th className="p-4">Subject & Campaign</th>
                        <th className="p-4">Audience</th>
                        <th className="p-4">Status</th>
                        <th className="p-4">Recipients</th>
                        <th className="p-4">Date</th>
                        <th className="p-4 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800/60 font-medium">
                      {filteredBroadcasts.map((b) => (
                        <tr key={b.id} className="hover:bg-gray-50/60 dark:hover:bg-zinc-800/30 transition-colors">
                          <td className="p-4">
                            <div className="font-bold text-gray-900 dark:text-white truncate max-w-xs sm:max-w-md">
                              {b.subject}
                            </div>
                            {b.name && b.name !== b.subject && (
                              <p className="text-[11px] text-gray-400 truncate">{b.name}</p>
                            )}
                          </td>
                          <td className="p-4">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold capitalize ${TAG_BADGES[b.target_tag] || TAG_BADGES.all}`}>
                              {b.target_tag || 'all'}
                            </span>
                          </td>
                          <td className="p-4">
                            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border uppercase tracking-wider ${STATUS_BADGES[b.status] || STATUS_BADGES.draft}`}>
                              {b.status}
                            </span>
                          </td>
                          <td className="p-4">
                            <div className="text-gray-900 dark:text-gray-100 font-bold">
                              {b.status === 'sent' ? `${b.delivered_count} / ${b.recipients_count}` : b.recipients_count}
                            </div>
                            <span className="text-[10px] text-gray-400">
                              {b.status === 'sent' ? 'delivered' : 'contacts'}
                            </span>
                          </td>
                          <td className="p-4 text-gray-500 whitespace-nowrap">
                            {b.sent_at
                              ? new Date(b.sent_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
                              : b.created_at
                              ? new Date(b.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
                              : '—'}
                          </td>
                          <td className="p-4 text-right whitespace-nowrap space-x-2">
                            {b.status !== 'sent' && (
                              <button
                                onClick={() => handleEditBroadcast(b)}
                                className="px-2.5 py-1 text-xs font-bold text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 rounded-lg transition-colors"
                              >
                                Edit
                              </button>
                            )}
                            <button
                              onClick={() => handleDeleteBroadcast(b.id)}
                              className="p-1.5 text-gray-400 hover:text-rose-500 rounded-lg transition-colors"
                              title="Delete broadcast"
                            >
                              <FaTrash className="text-xs" />
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

        {/* ── TAB 2: COMPOSER & TEMPLATES ── */}
        {activeTab === 'composer' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left Column: Form & Editor */}
            <div className="lg:col-span-2 space-y-4">
              <div className="bg-white dark:bg-[#1C1C1E] border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-xs space-y-4">
                
                {/* Target Audience & Recipient Estimator */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl bg-gray-50 dark:bg-zinc-900/40 border border-gray-100 dark:border-zinc-800">
                  <div>
                    <label className="block text-[11px] font-bold text-gray-500 uppercase tracking-wider">Target Audience</label>
                    <p className="text-xs text-gray-700 dark:text-gray-300 font-medium">
                      Select which audience segment receives this broadcast
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <select
                      value={composerForm.target_tag}
                      onChange={(e) => setComposerForm({ ...composerForm, target_tag: e.target.value })}
                      className="px-3 py-1.5 text-xs bg-white dark:bg-[#2C2C2E] border border-gray-200 dark:border-gray-700 rounded-xl font-bold outline-none"
                    >
                      <option value="all">All Contacts ({audienceCounts.all})</option>
                      <option value="subscriber">Subscribers ({audienceCounts.subscriber})</option>
                      <option value="lead">Leads ({audienceCounts.lead})</option>
                      <option value="client">Clients ({audienceCounts.client})</option>
                      <option value="vip">VIP Contacts ({audienceCounts.vip})</option>
                    </select>

                    <span className="px-2.5 py-1 text-[11px] font-extrabold bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 rounded-lg shrink-0">
                      {audienceCounts[composerForm.target_tag] || audienceCounts.all || 0} Contacts
                    </span>
                  </div>
                </div>

                {/* Subject Line & AI Trigger */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-xs font-bold text-gray-700 dark:text-gray-300">
                      Subject Line <span className="text-rose-500">*</span>
                    </label>
                    <button
                      type="button"
                      onClick={() => setAiModalOpen(true)}
                      className="text-xs font-bold text-indigo-600 dark:text-indigo-400 hover:text-indigo-500 flex items-center gap-1 cursor-pointer"
                    >
                      <FaMagic className="text-[10px]" /> AI Writing Assistant
                    </button>
                  </div>
                  <input
                    type="text"
                    placeholder="e.g. 🚀 Something big just dropped for you"
                    value={composerForm.subject}
                    onChange={(e) => setComposerForm({ ...composerForm, subject: e.target.value })}
                    className="w-full px-3.5 py-2.5 text-xs bg-white dark:bg-[#2C2C2E] border border-gray-200 dark:border-gray-800 rounded-xl font-medium outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>

                {/* Preheader Preview Text */}
                <div>
                  <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">
                    Preview Text / Preheader
                  </label>
                  <input
                    type="text"
                    placeholder="Short snippet shown in recipient's inbox before opening..."
                    value={composerForm.preview_text}
                    onChange={(e) => setComposerForm({ ...composerForm, preview_text: e.target.value })}
                    className="w-full px-3 py-2 text-xs bg-white dark:bg-[#2C2C2E] border border-gray-200 dark:border-gray-800 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>

                {/* Body Mode Switcher */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-bold text-gray-700 dark:text-gray-300">
                      Email Body Content
                    </label>
                    <div className="flex items-center gap-1 p-0.5 rounded-lg bg-gray-100 dark:bg-zinc-800 text-[11px] font-bold">
                      <button
                        type="button"
                        onClick={() => setPreviewMode('html')}
                        className={`px-3 py-1 rounded-md transition-colors ${previewMode === 'html' ? 'bg-white dark:bg-zinc-700 text-gray-900 dark:text-white shadow-xs' : 'text-gray-500'}`}
                      >
                        HTML &amp; Live View
                      </button>
                      <button
                        type="button"
                        onClick={() => setPreviewMode('markdown')}
                        className={`px-3 py-1 rounded-md transition-colors ${previewMode === 'markdown' ? 'bg-white dark:bg-zinc-700 text-gray-900 dark:text-white shadow-xs' : 'text-gray-500'}`}
                      >
                        Markdown
                      </button>
                    </div>
                  </div>

                  {previewMode === 'markdown' ? (
                    <textarea
                      rows={12}
                      placeholder="Write your email in Markdown. Use {{name}} for subscriber name and {{creator_name}} for your name..."
                      value={composerForm.body_markdown}
                      onChange={(e) => setComposerForm({ ...composerForm, body_markdown: e.target.value })}
                      className="w-full p-3.5 text-xs font-mono bg-white dark:bg-[#2C2C2E] border border-gray-200 dark:border-gray-800 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 leading-relaxed"
                    />
                  ) : (
                    <textarea
                      rows={12}
                      placeholder="Enter responsive HTML markup here..."
                      value={composerForm.body_html}
                      onChange={(e) => setComposerForm({ ...composerForm, body_html: e.target.value })}
                      className="w-full p-3.5 text-xs font-mono bg-white dark:bg-[#2C2C2E] border border-gray-200 dark:border-gray-800 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 leading-relaxed"
                    />
                  )}
                  <p className="text-[10px] text-gray-400 mt-1">
                    Variables supported: <code className="bg-black/5 dark:bg-white/10 px-1 py-0.5 rounded font-bold">{'{{name}}'}</code>, <code className="bg-black/5 dark:bg-white/10 px-1 py-0.5 rounded font-bold">{'{{creator_name}}'}</code>
                  </p>
                </div>

                {/* Bottom Action Controls */}
                <div className="pt-2 border-t border-gray-100 dark:border-gray-800 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={sendingTest}
                      onClick={handleSendTest}
                      className="px-3.5 py-2 text-xs font-bold border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-zinc-800 rounded-xl text-gray-700 dark:text-gray-300 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                    >
                      {sendingTest ? <FaSpinner className="animate-spin text-xs" /> : <FaEye className="text-xs" />}
                      Send Test Preview
                    </button>
                    <button
                      type="button"
                      disabled={savingDraft}
                      onClick={handleSaveDraft}
                      className="px-3.5 py-2 text-xs font-bold text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-zinc-800 rounded-xl transition-all cursor-pointer disabled:opacity-50"
                    >
                      {savingDraft ? 'Saving...' : 'Save Draft'}
                    </button>
                  </div>

                  <button
                    type="button"
                    disabled={sendingBroadcast}
                    onClick={handleSendBroadcastNow}
                    className="px-5 py-2 text-xs font-extrabold bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-sm transition-all active:scale-95 flex items-center gap-2 cursor-pointer disabled:opacity-50"
                  >
                    {sendingBroadcast ? (
                      <>
                        <FaSpinner className="animate-spin text-xs" /> Dispatching...
                      </>
                    ) : (
                      <>
                        <FaPaperPlane className="text-xs" /> Send Broadcast Now
                      </>
                    )}
                  </button>
                </div>

              </div>
            </div>

            {/* Right Column: Template Picker & Live Preview Card */}
            <div className="space-y-4">
              {/* Template Picker */}
              <div className="bg-white dark:bg-[#1C1C1E] border border-gray-200 dark:border-gray-800 rounded-2xl p-4 shadow-xs space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-extrabold uppercase tracking-wider text-gray-500">
                    Template Library ({templates.length})
                  </h3>
                  <span className="text-[10px] text-indigo-600 dark:text-indigo-400 font-bold">1-Click Apply</span>
                </div>

                <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                  {templatesLoading ? (
                    <p className="text-xs text-gray-400">Loading templates...</p>
                  ) : (
                    templates.map((tpl) => (
                      <div
                        key={tpl.id}
                        onClick={() => handleApplyTemplate(tpl)}
                        className={`p-3 rounded-xl border text-left cursor-pointer transition-all hover:scale-[1.01] ${
                          composerForm.template_id === tpl.id
                            ? 'border-indigo-500 bg-indigo-50/40 dark:bg-indigo-950/30'
                            : 'border-gray-100 dark:border-zinc-800 hover:border-gray-300 dark:hover:border-zinc-700 bg-gray-50/50 dark:bg-zinc-900/40'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-gray-900 dark:text-white">{tpl.name}</span>
                          <span className="px-1.5 py-0.5 rounded-md text-[9px] font-bold uppercase bg-black/5 dark:bg-white/10 text-gray-600 dark:text-gray-300">
                            {tpl.badge}
                          </span>
                        </div>
                        <p className="text-[11px] text-gray-500 dark:text-gray-400 line-clamp-2 mt-1">
                          {tpl.description}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Live Rendered Miniature */}
              <div className="bg-white dark:bg-[#1C1C1E] border border-gray-200 dark:border-gray-800 rounded-2xl p-4 shadow-xs space-y-2">
                <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider block">Live Preview</span>
                <div className="w-full h-80 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden bg-white">
                  <iframe
                    title="Live Preview"
                    srcDoc={composerForm.body_html || '<div style="padding: 20px; font-family: sans-serif; color: #888; text-align: center;">Write HTML or apply a template to preview here</div>'}
                    className="w-full h-full border-0"
                    sandbox="allow-same-origin"
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── TAB 3: WHATSAPP OUTREACH ── */}
        {activeTab === 'whatsapp' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left: Template & Controller */}
            <div className="bg-white dark:bg-[#1C1C1E] border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-xs space-y-4">
              <div className="flex items-center gap-2">
                <span className="p-2 rounded-xl bg-emerald-500/10 text-emerald-600 text-base">
                  <FaWhatsapp />
                </span>
                <div>
                  <h3 className="text-sm font-bold text-gray-900 dark:text-white">WhatsApp Outreach Pipeline</h3>
                  <p className="text-[11px] text-gray-500">1-click personalized outreach for captured leads</p>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">
                  Target Tag Segment
                </label>
                <select
                  value={waTagFilter}
                  onChange={(e) => setWaTagFilter(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-gray-50 dark:bg-zinc-900 border border-gray-200 dark:border-gray-800 rounded-xl font-medium outline-none"
                >
                  <option value="all">All Contacts ({audienceCounts.all})</option>
                  <option value="vip">VIPs Only ({audienceCounts.vip})</option>
                  <option value="client">Clients ({audienceCounts.client})</option>
                  <option value="lead">Leads ({audienceCounts.lead})</option>
                  <option value="subscriber">Subscribers ({audienceCounts.subscriber})</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">
                  WhatsApp Message Template
                </label>
                <textarea
                  rows={6}
                  value={waMessage}
                  onChange={(e) => setWaMessage(e.target.value)}
                  placeholder="Hey {{name}}, here is the link: ..."
                  className="w-full p-3 text-xs bg-gray-50 dark:bg-zinc-900 border border-gray-200 dark:border-gray-800 rounded-xl font-sans outline-none leading-relaxed"
                />
                <p className="text-[10px] text-gray-400 mt-1">
                  Tokens: <code className="font-bold">{'{{name}}'}</code>, <code className="font-bold">{'{{creator_name}}'}</code>
                </p>
              </div>

              <button
                type="button"
                disabled={waLoading}
                onClick={handleFetchWhatsAppLinks}
                className="w-full py-2.5 text-xs font-extrabold bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl shadow-xs transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
              >
                {waLoading ? <FaSpinner className="animate-spin text-xs" /> : <FaWhatsapp className="text-sm" />}
                Generate Personalized Links
              </button>

              {/* Chat Bubble Preview */}
              <div className="p-3.5 rounded-2xl bg-emerald-500/[0.08] border border-emerald-500/20 space-y-1.5">
                <span className="text-[10px] font-bold uppercase text-emerald-600 dark:text-emerald-400">Message Preview</span>
                <div className="p-3 rounded-xl bg-white dark:bg-zinc-800 text-xs text-gray-800 dark:text-gray-200 shadow-xs border border-black/5 leading-relaxed font-sans">
                  {waMessage.replace(/\{\{name\}\}/g, 'Alex').replace(/\{\{creator_name\}\}/g, 'Your Creator')}
                </div>
              </div>
            </div>

            {/* Right: Contact Links List */}
            <div className="lg:col-span-2 bg-white dark:bg-[#1C1C1E] border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-gray-900 dark:text-white">Ready Outreach Contacts</h3>
                  <p className="text-xs text-gray-500">
                    {waOutreachData
                      ? `${waOutreachData.leads_with_phone} of ${waOutreachData.total_leads} contacts have phone numbers`
                      : 'Click "Generate Personalized Links" to load contacts'}
                  </p>
                </div>
              </div>

              {!waOutreachData ? (
                <div className="p-12 text-center text-gray-400 space-y-2 border border-dashed border-gray-200 dark:border-gray-800 rounded-xl">
                  <FaWhatsapp className="text-2xl text-emerald-500 mx-auto" />
                  <p className="text-xs">Click Generate Personalized Links to prepare contacts</p>
                </div>
              ) : waOutreachData.outreach_items.length === 0 ? (
                <div className="p-8 text-center text-gray-400">
                  <p className="text-xs">No contacts found in selected segment</p>
                </div>
              ) : (
                <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
                  {waOutreachData.outreach_items.map((item) => (
                    <div
                      key={item.lead_id}
                      className="p-3 rounded-xl bg-gray-50/50 dark:bg-zinc-900/40 border border-gray-100 dark:border-zinc-800 flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-xs text-gray-900 dark:text-white truncate">{item.name}</span>
                          <span className={`px-2 py-0.2 rounded-full text-[9px] font-bold capitalize ${TAG_BADGES[item.tag] || TAG_BADGES.all}`}>
                            {item.tag}
                          </span>
                        </div>
                        <p className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
                          {item.phone || <span className="text-gray-400 italic">No phone provided</span>} · {item.email}
                        </p>
                      </div>

                      {item.wa_link ? (
                        <a
                          href={item.wa_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-3 py-1.5 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white shadow-xs flex items-center gap-1.5 transition-all shrink-0 active:scale-95"
                        >
                          <FaWhatsapp /> Chat Now
                        </a>
                      ) : (
                        <span className="px-2.5 py-1 rounded-lg text-[10px] font-bold bg-gray-100 dark:bg-zinc-800 text-gray-400 shrink-0">
                          Missing Phone
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── TAB 4: BIO MONETIZATION ── */}
        {activeTab === 'monetization' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left: Quick Payment Link Builder */}
            <div className="bg-white dark:bg-[#1C1C1E] border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-xs space-y-4">
              <div className="flex items-center gap-2">
                <span className="p-2 rounded-xl bg-emerald-500/10 text-emerald-600 text-base">
                  <FaCreditCard />
                </span>
                <div>
                  <h3 className="text-sm font-bold text-gray-900 dark:text-white">Smart Bio Monetization Builder</h3>
                  <p className="text-[11px] text-gray-500">Create instant checkout links for your bio blocks</p>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">
                  Product / Service Title
                </label>
                <input
                  type="text"
                  value={monetizeForm.title}
                  onChange={(e) => setMonetizeForm({ ...monetizeForm, title: e.target.value })}
                  placeholder="e.g. 1-on-1 Consultation"
                  className="w-full px-3 py-2 text-xs bg-gray-50 dark:bg-zinc-900 border border-gray-200 dark:border-gray-800 rounded-xl font-medium outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-bold text-gray-700 dark:text-gray-300 mb-1">
                    Amount
                  </label>
                  <input
                    type="number"
                    value={monetizeForm.amount}
                    onChange={(e) => setMonetizeForm({ ...monetizeForm, amount: e.target.value })}
                    placeholder="499"
                    className="w-full px-3 py-2 text-xs bg-gray-50 dark:bg-zinc-900 border border-gray-200 dark:border-gray-800 rounded-xl font-bold outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-bold text-gray-700 dark:text-gray-300 mb-1">
                    Currency
                  </label>
                  <select
                    value={monetizeForm.currency}
                    onChange={(e) => setMonetizeForm({ ...monetizeForm, currency: e.target.value })}
                    className="w-full px-3 py-2 text-xs bg-gray-50 dark:bg-zinc-900 border border-gray-200 dark:border-gray-800 rounded-xl font-medium outline-none"
                  >
                    <option value="INR">INR (₹)</option>
                    <option value="USD">USD ($)</option>
                    <option value="EUR">EUR (€)</option>
                    <option value="GBP">GBP (£)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">
                  Gateway / Provider
                </label>
                <select
                  value={monetizeForm.provider}
                  onChange={(e) => setMonetizeForm({ ...monetizeForm, provider: e.target.value })}
                  className="w-full px-3 py-2 text-xs bg-gray-50 dark:bg-zinc-900 border border-gray-200 dark:border-gray-800 rounded-xl font-medium outline-none"
                >
                  <option value="custom">Custom URL (Stripe, Razorpay, Gumroad)</option>
                  <option value="upi">UPI ID / Handle</option>
                  <option value="paypal">PayPal.me</option>
                  <option value="razorpay">Razorpay Payment Link API</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">
                  Destination or Payment Handle
                </label>
                <input
                  type="text"
                  value={monetizeForm.custom_url}
                  onChange={(e) => setMonetizeForm({ ...monetizeForm, custom_url: e.target.value })}
                  placeholder={monetizeForm.provider === 'upi' ? 'creator@okaxis' : monetizeForm.provider === 'paypal' ? 'paypal.me/username' : 'https://buy.stripe.com/...'}
                  className="w-full px-3 py-2 text-xs bg-gray-50 dark:bg-zinc-900 border border-gray-200 dark:border-gray-800 rounded-xl font-mono outline-none"
                />
              </div>

              <button
                type="button"
                onClick={handleGeneratePaymentLink}
                className="w-full py-2.5 text-xs font-extrabold bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-xs transition-all flex items-center justify-center gap-2 cursor-pointer"
              >
                Generate Payment URL
              </button>

              {generatedPaymentUrl && (
                <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 space-y-2">
                  <span className="text-[10px] font-bold uppercase text-emerald-600 dark:text-emerald-400">Generated URL:</span>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      readOnly
                      value={generatedPaymentUrl}
                      className="flex-1 px-2 py-1 text-[11px] font-mono bg-white dark:bg-zinc-800 border border-black/10 rounded-lg outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(generatedPaymentUrl);
                        toast.success('Copied payment URL!');
                      }}
                      className="p-1.5 text-xs bg-emerald-600 text-white rounded-lg hover:bg-emerald-500 transition-colors"
                      title="Copy URL"
                    >
                      <FaCopy />
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Right: Smart Bio Integration Guide */}
            <div className="lg:col-span-2 bg-white dark:bg-[#1C1C1E] border border-gray-200 dark:border-gray-800 rounded-2xl p-6 shadow-xs space-y-5">
              <div className="space-y-1">
                <span className="text-[11px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">
                  How Smart Bio Monetization Works
                </span>
                <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                  Sell Directly From Your Bio Page in 3 Steps
                </h3>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="p-4 rounded-xl bg-gray-50 dark:bg-zinc-900/40 border border-gray-100 dark:border-zinc-800 space-y-2">
                  <div className="w-8 h-8 rounded-lg bg-indigo-500/10 text-indigo-600 font-black text-xs flex items-center justify-center">1</div>
                  <h4 className="text-xs font-bold text-gray-900 dark:text-white">Add Payment Block</h4>
                  <p className="text-[11px] text-gray-500 leading-relaxed">
                    In Smart Bio Editor, choose &ldquo;Payment / Monetize&rdquo; from the block archetypes.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-gray-50 dark:bg-zinc-900/40 border border-gray-100 dark:border-zinc-800 space-y-2">
                  <div className="w-8 h-8 rounded-lg bg-emerald-500/10 text-emerald-600 font-black text-xs flex items-center justify-center">2</div>
                  <h4 className="text-xs font-bold text-gray-900 dark:text-white">Set Price &amp; Gateway</h4>
                  <p className="text-[11px] text-gray-500 leading-relaxed">
                    Enter the product amount (e.g. ₹499), select currency, and paste your Stripe or UPI link.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-gray-50 dark:bg-zinc-900/40 border border-gray-100 dark:border-zinc-800 space-y-2">
                  <div className="w-8 h-8 rounded-lg bg-purple-500/10 text-purple-600 font-black text-xs flex items-center justify-center">3</div>
                  <h4 className="text-xs font-bold text-gray-900 dark:text-white">Collect Revenue</h4>
                  <p className="text-[11px] text-gray-500 leading-relaxed">
                    Visitors see an instant checkout button that tracks conversions directly in your analytics.
                  </p>
                </div>
              </div>

              <div className="p-5 rounded-2xl bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-indigo-950/20 dark:to-purple-950/20 border border-indigo-100 dark:border-indigo-900/40 flex flex-col sm:flex-row items-center justify-between gap-4">
                <div>
                  <h4 className="text-sm font-bold text-gray-900 dark:text-white">Ready to customize your Smart Bio?</h4>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    Open the studio editor to place monetization blocks across any of your bio sub-pages.
                  </p>
                </div>
                <button
                  onClick={() => navigate('/link-in-bio')}
                  className="px-4 py-2 text-xs font-extrabold bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-xs transition-all flex items-center gap-1.5 shrink-0"
                >
                  Open Smart Bio Studio <FaExternalLinkAlt className="text-[10px]" />
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── AI WRITING ASSISTANT MODAL ── */}
        {aiModalOpen && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-4">
            <div className="bg-white dark:bg-[#1C1C1E] border border-gray-200 dark:border-gray-700 rounded-3xl max-w-lg w-full p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-400 font-bold text-sm">
                  <FaMagic /> AI Broadcast Copywriter
                </div>
                <button onClick={() => setAiModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                  <FaTimes />
                </button>
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">
                  What is this email about?
                </label>
                <textarea
                  rows={3}
                  value={aiTopic}
                  onChange={(e) => setAiTopic(e.target.value)}
                  placeholder="e.g. Announcing our 40% weekend discount on social growth templates, ending Sunday midnight..."
                  className="w-full p-3 text-xs bg-gray-50 dark:bg-zinc-900 border border-gray-200 dark:border-gray-800 rounded-xl outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-700 dark:text-gray-300 mb-1">
                  Tone of Voice
                </label>
                <select
                  value={aiTone}
                  onChange={(e) => setAiTone(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-gray-50 dark:bg-zinc-900 border border-gray-200 dark:border-gray-800 rounded-xl font-medium outline-none"
                >
                  <option value="engaging">Engaging &amp; Punchy</option>
                  <option value="urgent">High Urgency / Scarcity</option>
                  <option value="professional">Professional &amp; Authoritative</option>
                  <option value="casual">Casual &amp; Friendly</option>
                  <option value="storytelling">Storytelling Narrative</option>
                </select>
              </div>

              <button
                type="button"
                disabled={aiLoading}
                onClick={handleGenerateAiDraft}
                className="w-full py-2.5 text-xs font-extrabold bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-xs transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
              >
                {aiLoading ? <FaSpinner className="animate-spin text-xs" /> : <FaMagic />}
                Generate High-Converting Copy
              </button>

              {aiSuggestions && (
                <div className="space-y-3 pt-2 border-t border-gray-100 dark:border-gray-800">
                  <span className="text-[11px] font-bold text-gray-500 uppercase tracking-wider block">
                    Choose a Subject Line:
                  </span>
                  <div className="space-y-1.5">
                    {(aiSuggestions.subject_lines || []).map((subj, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleApplyAiSuggestion(subj)}
                        className="w-full p-2.5 rounded-xl text-left text-xs font-semibold bg-gray-50 dark:bg-zinc-900/60 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 border border-gray-200 dark:border-zinc-800 flex items-center justify-between transition-colors group"
                      >
                        <span className="truncate">{subj}</span>
                        <span className="text-[10px] text-indigo-600 dark:text-indigo-400 font-bold opacity-0 group-hover:opacity-100 transition-opacity">
                          Use This →
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

      </div>
    </DashboardLayout>
  );
}
