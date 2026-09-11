import React, { useState, useEffect, useCallback } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { toast } from 'sonner';
import {
  FaBolt,
  FaPlus,
  FaPlay,
  FaTrash,
  FaEdit,
  FaCheckCircle,
  FaTimesCircle,
  FaRedo,
  FaExternalLinkAlt,
  FaEnvelope,
  FaTag,
  FaLayerGroup,
  FaShareAlt,
  FaStar,
  FaUsers,
  FaSearch,
  FaTimes,
  FaToggleOn,
  FaToggleOff,
  FaFilter,
} from 'react-icons/fa';
import {
  getAutomations,
  getAutomationRecipes,
  createAutomation,
  updateAutomation,
  deleteAutomation,
  testAutomation,
  getAutomationLogs,
} from '@/lib/api';

const TRIGGER_META = {
  'lead.created': {
    label: 'New Lead Captured',
    desc: 'Fires when a visitor enters their details on Smart Bio',
    badge: 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800',
    icon: FaUsers,
  },
  'deal.stage_changed': {
    label: 'Deal Stage Changed',
    desc: 'Fires when a CRM deal transitions between pipeline stages',
    badge: 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-800',
    icon: FaLayerGroup,
  },
  'feedback.received': {
    label: 'NPS / Rating Received',
    desc: 'Fires when a visitor submits a poll or star rating',
    badge: 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800',
    icon: FaStar,
  },
  'broadcast.sent': {
    label: 'Broadcast Sent',
    desc: 'Fires after an email broadcast dispatch completes',
    badge: 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800',
    icon: FaShareAlt,
  },
};

const ACTION_META = {
  send_email: {
    label: 'Send Email',
    badge: 'bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300 border-sky-200 dark:border-sky-800',
    icon: FaEnvelope,
  },
  create_deal: {
    label: 'Create CRM Deal',
    badge: 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800',
    icon: FaLayerGroup,
  },
  dispatch_webhook: {
    label: 'Dispatch Webhook',
    badge: 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800',
    icon: FaExternalLinkAlt,
  },
  tag_lead: {
    label: 'Tag Lead',
    badge: 'bg-rose-100 dark:bg-rose-900/40 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800',
    icon: FaTag,
  },
};

export default function Automations() {
  const [activeTab, setActiveTab] = useState('rules'); // 'rules' | 'recipes' | 'logs'
  const [rules, setRules] = useState([]);
  const [recipes, setRecipes] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Modal State
  const [modalOpen, setModalOpen] = useState(false);
  const [editingRule, setEditingRule] = useState(null);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState(null);

  // Form Fields
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [triggerType, setTriggerType] = useState('lead.created');
  const [triggerConfig, setTriggerConfig] = useState({});
  const [actionType, setActionType] = useState('send_email');
  const [actionConfig, setActionConfig] = useState({
    subject: 'Welcome to our community!',
    body: 'Hi {{name}},\n\nThank you for reaching out! Excited to connect with you.',
  });

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [rulesRes, recipesRes, logsRes] = await Promise.all([
        getAutomations(),
        getAutomationRecipes(),
        getAutomationLogs({ limit: 40 }),
      ]);
      setRules(rulesRes.automations || []);
      setRecipes(recipesRes.recipes || []);
      setLogs(logsRes.logs || []);
    } catch (err) {
      console.error('Failed to load automations data:', err);
      toast.error('Unable to load automations');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleOpenCreateModal = (preset = null) => {
    if (preset) {
      setEditingRule(null);
      setName(preset.name || '');
      setDescription(preset.description || '');
      setTriggerType(preset.trigger_type || 'lead.created');
      setTriggerConfig(preset.trigger_config || {});
      setActionType(preset.action_type || 'send_email');
      setActionConfig(preset.action_config || {});
    } else {
      setEditingRule(null);
      setName('');
      setDescription('');
      setTriggerType('lead.created');
      setTriggerConfig({});
      setActionType('send_email');
      setActionConfig({
        subject: 'Welcome to our community!',
        body: 'Hi {{name}},\n\nThank you for reaching out! Excited to connect with you.',
      });
    }
    setModalOpen(true);
  };

  const handleOpenEditModal = (rule) => {
    setEditingRule(rule);
    setName(rule.name || '');
    setDescription(rule.description || '');
    setTriggerType(rule.trigger_type || 'lead.created');
    setTriggerConfig(rule.trigger_config || {});
    setActionType(rule.action_type || 'send_email');
    setActionConfig(rule.action_config || {});
    setModalOpen(true);
  };

  const handleSaveRule = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      toast.error('Please provide a name for this automation.');
      return;
    }

    setSaving(true);
    try {
      const payload = {
        name: name.trim(),
        description: description.trim(),
        trigger_type: triggerType,
        trigger_config: triggerConfig,
        action_type: actionType,
        action_config: actionConfig,
        is_active: true,
      };

      if (editingRule) {
        await updateAutomation(editingRule.id, payload);
        toast.success('Automation rule updated!');
      } else {
        await createAutomation(payload);
        toast.success('Automation rule created and activated!');
      }
      setModalOpen(false);
      loadData();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to save automation rule');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (rule) => {
    try {
      const newStatus = !rule.is_active;
      await updateAutomation(rule.id, { is_active: newStatus });
      setRules((prev) =>
        prev.map((r) => (r.id === rule.id ? { ...r, is_active: newStatus } : r))
      );
      toast.success(newStatus ? 'Automation enabled' : 'Automation paused');
    } catch (err) {
      toast.error('Failed to update status');
    }
  };

  const handleDeleteRule = async (ruleId) => {
    if (!window.confirm('Are you sure you want to delete this automation rule?')) return;
    try {
      await deleteAutomation(ruleId);
      setRules((prev) => prev.filter((r) => r.id !== ruleId));
      toast.success('Automation rule deleted');
    } catch (err) {
      toast.error('Failed to delete automation');
    }
  };

  const handleTestRule = async (ruleId) => {
    setTestingId(ruleId);
    try {
      const res = await testAutomation(ruleId);
      if (res.success) {
        toast.success(res.message || 'Test execution succeeded!');
        // Refresh logs in background
        getAutomationLogs({ limit: 40 }).then((lRes) => setLogs(lRes.logs || []));
      } else {
        toast.error(res.message || 'Test execution failed');
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Dry run failed');
    } finally {
      setTestingId(null);
    }
  };

  const filteredRules = rules.filter((r) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      r.name?.toLowerCase().includes(q) ||
      r.trigger_type?.toLowerCase().includes(q) ||
      r.action_type?.toLowerCase().includes(q)
    );
  });

  const totalRuns = rules.reduce((acc, r) => acc + (r.execution_count || 0), 0);
  const activeCount = rules.filter((r) => r.is_active).length;

  return (
    <DashboardLayout>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8 font-sans text-gray-900 dark:text-white">
        
        {/* ── HEADER & STATS ── */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="w-10 h-10 rounded-2xl bg-amber-500/10 text-amber-500 flex items-center justify-center text-lg">
                <FaBolt />
              </div>
              <h1 className="text-2xl sm:text-3xl font-black tracking-tight">Automations Engine</h1>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-black bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                Cluster D
              </span>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Connect Smart Bio leads, CRM pipeline stages, and outbound webhooks with automated actions.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => handleOpenCreateModal()}
              className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs shadow-md shadow-indigo-600/20 flex items-center gap-2 transition-all active:scale-95 cursor-pointer"
            >
              <FaPlus className="text-xs" />
              <span>Create Automation</span>
            </button>
          </div>
        </div>

        {/* ── STATS ROW ── */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="p-5 rounded-2xl bg-white dark:bg-[#1C1C1E] border border-black/[0.06] dark:border-white/[0.08] shadow-xs">
            <div className="text-xs font-bold text-gray-400 uppercase tracking-wider">Total Rules</div>
            <div className="text-2xl sm:text-3xl font-black mt-1 text-gray-900 dark:text-white">
              {rules.length}
            </div>
            <div className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">Configured pipelines</div>
          </div>

          <div className="p-5 rounded-2xl bg-white dark:bg-[#1C1C1E] border border-black/[0.06] dark:border-white/[0.08] shadow-xs">
            <div className="text-xs font-bold text-gray-400 uppercase tracking-wider">Active Status</div>
            <div className="text-2xl sm:text-3xl font-black mt-1 text-emerald-600 dark:text-emerald-400">
              {activeCount} <span className="text-sm font-semibold text-gray-400">/ {rules.length} live</span>
            </div>
            <div className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">Reacting to real-time events</div>
          </div>

          <div className="p-5 rounded-2xl bg-white dark:bg-[#1C1C1E] border border-black/[0.06] dark:border-white/[0.08] shadow-xs">
            <div className="text-xs font-bold text-gray-400 uppercase tracking-wider">Total Executions</div>
            <div className="text-2xl sm:text-3xl font-black mt-1 text-indigo-600 dark:text-indigo-400">
              {totalRuns.toLocaleString()}
            </div>
            <div className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">Automated runs completed</div>
          </div>
        </div>

        {/* ── TABS SELECTOR ── */}
        <div className="flex items-center justify-between border-b border-black/[0.06] dark:border-white/[0.08] pb-3">
          <div className="flex items-center gap-2">
            {[
              { id: 'rules', label: 'My Automations', count: rules.length },
              { id: 'recipes', label: 'Recipe Gallery', count: recipes.length },
              { id: 'logs', label: 'Execution Logs', count: logs.length },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer flex items-center gap-2 ${
                  activeTab === tab.id
                    ? 'bg-black dark:bg-white text-white dark:text-black shadow-xs'
                    : 'text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5'
                }`}
              >
                <span>{tab.label}</span>
                <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-black/10 dark:bg-white/20 font-mono">
                  {tab.count}
                </span>
              </button>
            ))}
          </div>

          {activeTab === 'rules' && (
            <div className="relative w-48 sm:w-64">
              <FaSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search automations..."
                className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.1] outline-hidden focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          )}
        </div>

        {/* ══════ TAB 1: MY AUTOMATIONS ══════ */}
        {activeTab === 'rules' && (
          <div className="space-y-4">
            {loading ? (
              <div className="py-16 text-center text-gray-400">Loading automation workflows...</div>
            ) : filteredRules.length === 0 ? (
              <div className="p-12 text-center rounded-3xl bg-white dark:bg-[#1C1C1E] border border-dashed border-black/[0.1] dark:border-white/[0.1] space-y-4">
                <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-950/40 text-indigo-500 flex items-center justify-center text-xl mx-auto">
                  <FaBolt />
                </div>
                <div>
                  <h3 className="text-base font-bold">No automations configured yet</h3>
                  <p className="text-xs text-gray-500 max-w-sm mx-auto mt-1">
                    Set up your first event-driven automation or install a pre-built recipe to streamline audience operations.
                  </p>
                </div>
                <div className="flex items-center justify-center gap-3">
                  <button
                    onClick={() => setActiveTab('recipes')}
                    className="px-4 py-2 rounded-xl text-xs font-bold bg-black/[0.04] dark:bg-white/[0.06] hover:bg-black/[0.08] transition-all"
                  >
                    Explore 5 Presets
                  </button>
                  <button
                    onClick={() => handleOpenCreateModal()}
                    className="px-4 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white transition-all shadow-xs"
                  >
                    + Build from Scratch
                  </button>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {filteredRules.map((rule) => {
                  const trigger = TRIGGER_META[rule.trigger_type] || {
                    label: rule.trigger_type,
                    badge: 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300',
                    icon: FaBolt,
                  };
                  const action = ACTION_META[rule.action_type] || {
                    label: rule.action_type,
                    badge: 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300',
                    icon: FaBolt,
                  };

                  return (
                    <div
                      key={rule.id}
                      className={`p-5 rounded-3xl bg-white dark:bg-[#1C1C1E] border transition-all flex flex-col justify-between space-y-4 shadow-xs ${
                        rule.is_active
                          ? 'border-black/[0.08] dark:border-white/[0.1]'
                          : 'border-black/[0.04] dark:border-white/[0.04] opacity-75'
                      }`}
                    >
                      <div className="space-y-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <h3 className="text-sm font-bold text-gray-900 dark:text-white flex items-center gap-2">
                              <span>{rule.name}</span>
                              {!rule.is_active && (
                                <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-gray-100 dark:bg-gray-800 text-gray-500 uppercase">
                                  Paused
                                </span>
                              )}
                            </h3>
                            {rule.description && (
                              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">
                                {rule.description}
                              </p>
                            )}
                          </div>
                          
                          <button
                            type="button"
                            onClick={() => handleToggleActive(rule)}
                            className={`text-xl transition-colors cursor-pointer ${
                              rule.is_active ? 'text-emerald-500' : 'text-gray-400'
                            }`}
                            title={rule.is_active ? 'Pause Automation' : 'Enable Automation'}
                          >
                            {rule.is_active ? <FaToggleOn /> : <FaToggleOff />}
                          </button>
                        </div>

                        {/* Visual Flow Diagram */}
                        <div className="p-3 rounded-2xl bg-black/[0.02] dark:bg-white/[0.03] border border-black/[0.04] dark:border-white/[0.04] flex items-center justify-between gap-2 text-xs">
                          {/* Trigger */}
                          <div className="flex items-center gap-2 min-w-0">
                            <span className={`p-1.5 rounded-lg border text-[11px] ${trigger.badge}`}>
                              <trigger.icon />
                            </span>
                            <div className="min-w-0">
                              <div className="text-[10px] uppercase font-bold text-gray-400">Trigger</div>
                              <div className="font-bold truncate">{trigger.label}</div>
                            </div>
                          </div>

                          <span className="text-gray-400 font-bold shrink-0">➔</span>

                          {/* Action */}
                          <div className="flex items-center gap-2 min-w-0">
                            <span className={`p-1.5 rounded-lg border text-[11px] ${action.badge}`}>
                              <action.icon />
                            </span>
                            <div className="min-w-0">
                              <div className="text-[10px] uppercase font-bold text-gray-400">Action</div>
                              <div className="font-bold truncate">{action.label}</div>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Footer Actions */}
                      <div className="flex items-center justify-between pt-3 border-t border-black/[0.04] dark:border-white/[0.06] text-xs">
                        <span className="text-[11px] font-mono text-gray-400">
                          {rule.execution_count || 0} runs
                        </span>

                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            disabled={testingId === rule.id}
                            onClick={() => handleTestRule(rule.id)}
                            className="px-2.5 py-1 rounded-lg bg-black/[0.04] dark:bg-white/[0.06] hover:bg-black/[0.08] text-gray-700 dark:text-gray-300 font-semibold text-xs flex items-center gap-1 transition-all disabled:opacity-50"
                            title="Trigger dry-run test"
                          >
                            <FaPlay className="text-[9px] text-amber-500" />
                            <span>{testingId === rule.id ? 'Testing...' : 'Test'}</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => handleOpenEditModal(rule)}
                            className="p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 text-gray-500 hover:text-gray-900 dark:hover:text-white transition-all"
                            title="Edit rule"
                          >
                            <FaEdit />
                          </button>

                          <button
                            type="button"
                            onClick={() => handleDeleteRule(rule.id)}
                            className="p-1.5 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950/40 text-gray-400 hover:text-rose-500 transition-all"
                            title="Delete rule"
                          >
                            <FaTrash />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ══════ TAB 2: RECIPE GALLERY ══════ */}
        {activeTab === 'recipes' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-bold">One-Click Recipe Catalog</h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Pre-configured automation recipes designed for creator and sales operations.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {recipes.map((rcp) => {
                const trigger = TRIGGER_META[rcp.trigger_type] || { label: rcp.trigger_type, icon: FaBolt };
                const action = ACTION_META[rcp.action_type] || { label: rcp.action_type, icon: FaBolt };

                return (
                  <div
                    key={rcp.id}
                    className="p-5 rounded-3xl bg-white dark:bg-[#1C1C1E] border border-black/[0.06] dark:border-white/[0.08] flex flex-col justify-between space-y-4 hover:border-indigo-500/50 transition-all group shadow-xs"
                  >
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800">
                          {rcp.category}
                        </span>
                        <span className="text-xs font-mono text-gray-400">Preset</span>
                      </div>

                      <h3 className="text-sm font-bold text-gray-900 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                        {rcp.name}
                      </h3>

                      <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                        {rcp.description}
                      </p>

                      {/* Visual Flow Mini-tag */}
                      <div className="p-2.5 rounded-xl bg-black/[0.02] dark:bg-white/[0.04] text-[11px] font-semibold flex items-center justify-between">
                        <span className="truncate">{trigger.label}</span>
                        <span className="text-gray-400 px-1 font-bold">➔</span>
                        <span className="truncate text-indigo-600 dark:text-indigo-400">{action.label}</span>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => handleOpenCreateModal(rcp)}
                      className="w-full py-2.5 rounded-xl bg-black/[0.04] dark:bg-white/[0.06] hover:bg-indigo-600 hover:text-white text-xs font-bold transition-all active:scale-95 cursor-pointer"
                    >
                      Use This Recipe
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ══════ TAB 3: EXECUTION LOGS ══════ */}
        {activeTab === 'logs' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold">Real-time Execution Audit Log</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  Audit trail of all automated dispatches, status codes, and execution durations.
                </p>
              </div>

              <button
                type="button"
                onClick={() => loadData()}
                className="px-3 py-1.5 rounded-xl border border-black/[0.08] dark:border-white/[0.1] text-xs font-semibold hover:bg-black/5 dark:hover:bg-white/5 transition flex items-center gap-1.5"
              >
                <FaRedo className="text-[10px]" />
                <span>Refresh Logs</span>
              </button>
            </div>

            <div className="bg-white dark:bg-[#1C1C1E] border border-black/[0.06] dark:border-white/[0.08] rounded-3xl overflow-hidden shadow-xs">
              {logs.length === 0 ? (
                <div className="p-12 text-center text-xs text-gray-400">
                  No automated execution logs recorded yet. Run a test from the My Automations tab.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-black/[0.06] dark:border-white/[0.08] bg-black/[0.02] dark:bg-white/[0.02] text-gray-400 font-bold uppercase tracking-wider text-[10px]">
                        <th className="py-3 px-4">Time</th>
                        <th className="py-3 px-4">Automation</th>
                        <th className="py-3 px-4">Trigger Event</th>
                        <th className="py-3 px-4">Action</th>
                        <th className="py-3 px-4">Status</th>
                        <th className="py-3 px-4">Details</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-black/[0.04] dark:divide-white/[0.04]">
                      {logs.map((log) => {
                        const isSuccess = log.status === 'success';
                        const timeStr = log.executed_at
                          ? new Date(log.executed_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                          : 'Just now';

                        return (
                          <tr key={log.id} className="hover:bg-black/[0.01] dark:hover:bg-white/[0.01]">
                            <td className="py-3 px-4 font-mono text-gray-400 text-[11px] whitespace-nowrap">
                              {timeStr}
                            </td>
                            <td className="py-3 px-4 font-bold text-gray-900 dark:text-white">
                              {log.automation_name || log.automation_id}
                            </td>
                            <td className="py-3 px-4">
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400">
                                {log.trigger_type}
                              </span>
                            </td>
                            <td className="py-3 px-4 font-semibold text-gray-700 dark:text-gray-300">
                              {log.action_type}
                            </td>
                            <td className="py-3 px-4">
                              {isSuccess ? (
                                <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-bold">
                                  <FaCheckCircle className="text-[10px]" />
                                  <span>Success</span>
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 text-rose-600 dark:text-rose-400 font-bold">
                                  <FaTimesCircle className="text-[10px]" />
                                  <span>Failed</span>
                                </span>
                              )}
                            </td>
                            <td className="py-3 px-4 text-gray-500 max-w-xs truncate font-mono text-[11px]">
                              {JSON.stringify(log.action_result || {})}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ══════ MODAL: CREATE / EDIT AUTOMATION ══════ */}
        {modalOpen && (
          <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-4">
            <div className="bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.12] rounded-3xl max-w-xl w-full p-6 shadow-2xl space-y-5 text-gray-900 dark:text-white animate-in fade-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto">
              
              <div className="flex items-center justify-between border-b border-black/[0.06] dark:border-white/[0.08] pb-3">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center text-sm">
                    <FaBolt />
                  </div>
                  <div>
                    <h3 className="text-base font-bold">
                      {editingRule ? 'Edit Automation Rule' : 'New Event Automation'}
                    </h3>
                    <p className="text-[11px] text-gray-500">Configure trigger conditions and automatic executions</p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 p-2 rounded-full hover:bg-black/5 dark:hover:bg-white/5"
                >
                  <FaTimes />
                </button>
              </div>

              <form onSubmit={handleSaveRule} className="space-y-4 text-xs">
                {/* Rule Name */}
                <div className="space-y-1">
                  <label className="font-bold text-gray-700 dark:text-gray-300">Workflow Name</label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Welcome Email on New Bio Lead"
                    className="w-full px-3 py-2 rounded-xl bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.08] dark:border-white/[0.1] outline-hidden focus:ring-2 focus:ring-indigo-500 font-semibold"
                  />
                </div>

                {/* Description */}
                <div className="space-y-1">
                  <label className="font-bold text-gray-700 dark:text-gray-300">Description (Optional)</label>
                  <input
                    type="text"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="What does this rule do?"
                    className="w-full px-3 py-2 rounded-xl bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.08] dark:border-white/[0.1] outline-hidden focus:ring-2 focus:ring-indigo-500"
                  />
                </div>

                {/* Trigger Select */}
                <div className="space-y-1 pt-1">
                  <label className="font-bold text-gray-700 dark:text-gray-300 flex items-center justify-between">
                    <span>When this event happens (Trigger)</span>
                    <span className="text-[10px] text-indigo-500 uppercase font-mono">Event Source</span>
                  </label>
                  <select
                    value={triggerType}
                    onChange={(e) => setTriggerType(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.08] dark:border-white/[0.1] outline-hidden focus:ring-2 focus:ring-indigo-500 font-bold"
                  >
                    <option value="lead.created">👤 New Contact / Lead Captured (Smart Bio or Audience)</option>
                    <option value="deal.stage_changed">📊 Deal Pipeline Stage Changed (CRM)</option>
                    <option value="feedback.received">⭐ Visitor Feedback / Star Rating Submitted</option>
                    <option value="broadcast.sent">✉️ Email Broadcast Dispatch Completed</option>
                  </select>
                </div>

                {/* Optional trigger condition */}
                {triggerType === 'deal.stage_changed' && (
                  <div className="p-3 rounded-xl bg-purple-500/5 border border-purple-500/20 space-y-1">
                    <label className="font-bold text-purple-600 dark:text-purple-400">Target Pipeline Stage</label>
                    <select
                      value={triggerConfig.target_stage || ''}
                      onChange={(e) => setTriggerConfig({ ...triggerConfig, target_stage: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl bg-white dark:bg-[#252528] border border-purple-500/20 outline-hidden font-bold"
                    >
                      <option value="">Any Stage Transition</option>
                      <option value="lead">Lead</option>
                      <option value="contacted">Contacted</option>
                      <option value="proposal">Proposal</option>
                      <option value="negotiation">Negotiation</option>
                      <option value="won">Won</option>
                      <option value="lost">Lost</option>
                    </select>
                  </div>
                )}

                {/* Action Select */}
                <div className="space-y-1 pt-1">
                  <label className="font-bold text-gray-700 dark:text-gray-300 flex items-center justify-between">
                    <span>Then perform this Action</span>
                    <span className="text-[10px] text-indigo-500 uppercase font-mono">Execution</span>
                  </label>
                  <select
                    value={actionType}
                    onChange={(e) => {
                      const val = e.target.value;
                      setActionType(val);
                      if (val === 'create_deal') {
                        setActionConfig({ title: 'New Bio Lead: {{name}}', stage: 'lead', value: 0.0, currency: 'INR', priority: 'medium' });
                      } else if (val === 'tag_lead') {
                        setActionConfig({ target_tag: 'vip' });
                      } else if (val === 'dispatch_webhook') {
                        setActionConfig({ webhook_url: '' });
                      } else {
                        setActionConfig({ subject: 'Welcome!', body: 'Hi {{name}},\n\nThank you!' });
                      }
                    }}
                    className="w-full px-3 py-2 rounded-xl bg-black/[0.03] dark:bg-white/[0.05] border border-black/[0.08] dark:border-white/[0.1] outline-hidden focus:ring-2 focus:ring-indigo-500 font-bold"
                  >
                    <option value="send_email">✉️ Send Automated Email (SES / Resend)</option>
                    <option value="create_deal">📊 Create Card in CRM Deals Pipeline</option>
                    <option value="dispatch_webhook">🌐 Dispatch Outbound Webhook (Slack / Discord / Zapier)</option>
                    <option value="tag_lead">🏷️ Tag Contact in Audience Hub</option>
                  </select>
                </div>

                {/* Action Config Form: Send Email */}
                {actionType === 'send_email' && (
                  <div className="space-y-3 p-3.5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.03] border border-black/[0.06] dark:border-white/[0.08]">
                    <div className="space-y-1">
                      <label className="font-bold text-gray-600 dark:text-gray-300">Email Subject</label>
                      <input
                        type="text"
                        required
                        value={actionConfig.subject || ''}
                        onChange={(e) => setActionConfig({ ...actionConfig, subject: e.target.value })}
                        placeholder="Welcome! So glad you connected."
                        className="w-full px-3 py-2 rounded-xl bg-white dark:bg-[#252528] border border-black/[0.08] dark:border-white/[0.1] outline-hidden font-semibold"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="font-bold text-gray-600 dark:text-gray-300 flex items-center justify-between">
                        <span>Email Body</span>
                        <span className="text-[10px] text-gray-400">Available: &#123;&#123;name&#125;&#125;, &#123;&#123;creator_name&#125;&#125;</span>
                      </label>
                      <textarea
                        rows={4}
                        required
                        value={actionConfig.body || ''}
                        onChange={(e) => setActionConfig({ ...actionConfig, body: e.target.value })}
                        className="w-full px-3 py-2 rounded-xl bg-white dark:bg-[#252528] border border-black/[0.08] dark:border-white/[0.1] outline-hidden font-mono text-[11px]"
                      />
                    </div>
                  </div>
                )}

                {/* Action Config Form: Create Deal */}
                {actionType === 'create_deal' && (
                  <div className="grid grid-cols-2 gap-3 p-3.5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.03] border border-black/[0.06] dark:border-white/[0.08]">
                    <div className="col-span-2 space-y-1">
                      <label className="font-bold text-gray-600 dark:text-gray-300">Deal Title Template</label>
                      <input
                        type="text"
                        value={actionConfig.title || ''}
                        onChange={(e) => setActionConfig({ ...actionConfig, title: e.target.value })}
                        placeholder="Deal: {{name}}"
                        className="w-full px-3 py-2 rounded-xl bg-white dark:bg-[#252528] border border-black/[0.08] dark:border-white/[0.1] outline-hidden font-semibold"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="font-bold text-gray-600 dark:text-gray-300">Pipeline Stage</label>
                      <select
                        value={actionConfig.stage || 'lead'}
                        onChange={(e) => setActionConfig({ ...actionConfig, stage: e.target.value })}
                        className="w-full px-3 py-2 rounded-xl bg-white dark:bg-[#252528] border border-black/[0.08] dark:border-white/[0.1] outline-hidden font-semibold"
                      >
                        <option value="lead">Lead</option>
                        <option value="contacted">Contacted</option>
                        <option value="proposal">Proposal</option>
                        <option value="negotiation">Negotiation</option>
                        <option value="won">Won</option>
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="font-bold text-gray-600 dark:text-gray-300">Estimated Value</label>
                      <input
                        type="number"
                        value={actionConfig.value || 0}
                        onChange={(e) => setActionConfig({ ...actionConfig, value: Number(e.target.value) })}
                        className="w-full px-3 py-2 rounded-xl bg-white dark:bg-[#252528] border border-black/[0.08] dark:border-white/[0.1] outline-hidden font-mono"
                      />
                    </div>
                  </div>
                )}

                {/* Action Config Form: Webhook */}
                {actionType === 'dispatch_webhook' && (
                  <div className="space-y-1 p-3.5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.03] border border-black/[0.06] dark:border-white/[0.08]">
                    <label className="font-bold text-gray-600 dark:text-gray-300">Target Webhook URL</label>
                    <input
                      type="url"
                      required
                      value={actionConfig.webhook_url || ''}
                      onChange={(e) => setActionConfig({ ...actionConfig, webhook_url: e.target.value })}
                      placeholder="https://hooks.slack.com/services/..."
                      className="w-full px-3 py-2 rounded-xl bg-white dark:bg-[#252528] border border-black/[0.08] dark:border-white/[0.1] outline-hidden font-mono text-[11px]"
                    />
                    <p className="text-[10px] text-gray-400 mt-1">Payload contains event type, timestamp, and contact metadata.</p>
                  </div>
                )}

                {/* Action Config Form: Tag Lead */}
                {actionType === 'tag_lead' && (
                  <div className="space-y-1 p-3.5 rounded-2xl bg-black/[0.02] dark:bg-white/[0.03] border border-black/[0.06] dark:border-white/[0.08]">
                    <label className="font-bold text-gray-600 dark:text-gray-300">Target Lead Tag</label>
                    <select
                      value={actionConfig.target_tag || 'vip'}
                      onChange={(e) => setActionConfig({ ...actionConfig, target_tag: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl bg-white dark:bg-[#252528] border border-black/[0.08] dark:border-white/[0.1] outline-hidden font-bold"
                    >
                      <option value="vip">VIP (High value contact)</option>
                      <option value="client">Client (Paying customer)</option>
                      <option value="lead">Lead (Active prospect)</option>
                      <option value="subscriber">Subscriber (Standard audience)</option>
                    </select>
                  </div>
                )}

                <div className="flex items-center justify-end gap-3 pt-3 border-t border-black/[0.06] dark:border-white/[0.08]">
                  <button
                    type="button"
                    onClick={() => setModalOpen(false)}
                    className="px-4 py-2 rounded-xl text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 font-bold text-xs"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={saving}
                    className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs shadow-md shadow-indigo-600/20 transition-all active:scale-95 disabled:opacity-50"
                  >
                    {saving ? 'Saving...' : editingRule ? 'Save Changes' : 'Activate Automation'}
                  </button>
                </div>
              </form>

            </div>
          </div>
        )}

      </div>
    </DashboardLayout>
  );
}
