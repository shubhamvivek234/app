import React, { useState, useEffect, useCallback } from 'react';
import {
  Webhook,
  Key,
  MessageSquare,
  Plus,
  Trash2,
  Copy,
  Check,
  RefreshCw,
  AlertCircle,
  ExternalLink,
  Shield,
  Activity,
  Send,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
} from 'lucide-react';
import { toast } from 'sonner';

const AVAILABLE_EVENTS = [
  { id: 'lead.replied', label: 'Lead Replied', desc: 'Prospect replies to a LinkedIn message or email' },
  { id: 'lead.connection_accepted', label: 'Connection Accepted', desc: 'Prospect accepts LinkedIn connection request' },
  { id: 'lead.created', label: 'Lead Created', desc: 'New prospect enrolled into a campaign' },
  { id: 'lead.stage_changed', label: 'Lead Stage Changed', desc: 'Prospect pipeline stage or execution status updated' },
  { id: 'campaign.paused', label: 'Campaign Paused', desc: 'Campaign paused due to safety, limits, or user action' },
  { id: 'email.accepted', label: 'Email Accepted', desc: 'Outbound email accepted by mailbox provider' },
];

export default function OutreachIntegrations() {
  const [activeSection, setActiveSection] = useState('webhooks'); // 'webhooks' | 'apikeys' | 'apps'

  // ── Webhooks State ──────────────────────────────────────────────────────────
  const [webhooks, setWebhooks] = useState([]);
  const [loadingWebhooks, setLoadingWebhooks] = useState(false);
  const [webhookModalOpen, setWebhookModalOpen] = useState(false);
  const [targetUrl, setTargetUrl] = useState('');
  const [selectedEvents, setSelectedEvents] = useState(['lead.replied', 'lead.connection_accepted']);
  const [submittingWebhook, setSubmittingWebhook] = useState(false);
  const [newlyCreatedSecret, setNewlyCreatedSecret] = useState(null);

  // Delivery log modal
  const [selectedWebhookForLogs, setSelectedWebhookForLogs] = useState(null);
  const [deliveries, setDeliveries] = useState([]);
  const [loadingDeliveries, setLoadingDeliveries] = useState(false);

  // ── API Keys State ──────────────────────────────────────────────────────────
  const [apiKeys, setApiKeys] = useState([]);
  const [loadingApiKeys, setLoadingApiKeys] = useState(false);
  const [keyModalOpen, setKeyModalOpen] = useState(false);
  const [keyName, setKeyName] = useState('');
  const [keyScopes, setKeyScopes] = useState(['leads:write', 'campaigns:read']);
  const [submittingKey, setSubmittingKey] = useState(false);
  const [newlyCreatedKey, setNewlyCreatedKey] = useState(null);

  // ── Slack Config State ──────────────────────────────────────────────────────
  const [slackConnected, setSlackConnected] = useState(false);
  const [slackWebhookUrl, setSlackWebhookUrl] = useState('');
  const [slackChannel, setSlackChannel] = useState('#sales-leads');
  const [savingSlack, setSavingSlack] = useState(false);
  const [testingSlack, setTestingSlack] = useState(false);

  // ── HubSpot Config State ───────────────────────────────────────────────────
  const [hubspotConnected, setHubspotConnected] = useState(false);
  const [hubspotPortalId, setHubspotPortalId] = useState('');
  const [hubspotToken, setHubspotToken] = useState('');
  const [hubspotAutoSync, setHubspotAutoSync] = useState(true);
  const [savingHubspot, setSavingHubspot] = useState(false);

  // ── Google Sheets / CSV Import State ───────────────────────────────────────
  const [campaignsList, setCampaignsList] = useState([]);
  const [sheetsCampaignId, setSheetsCampaignId] = useState('');
  const [csvText, setCsvText] = useState('');
  const [previewResult, setPreviewResult] = useState(null);
  const [previewingSheets, setPreviewingSheets] = useState(false);
  const [importingSheets, setImportingSheets] = useState(false);

  const copyToClipboard = (text, label = 'Copied to clipboard') => {
    navigator.clipboard.writeText(text);
    toast.success(label);
  };

  // ── Fetch Webhooks ──────────────────────────────────────────────────────────
  const fetchWebhooks = useCallback(async () => {
    setLoadingWebhooks(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/integrations/webhooks', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setWebhooks(data || []);
      }
    } catch (_) {
      toast.error('Failed to load webhooks');
    } finally {
      setLoadingWebhooks(false);
    }
  }, []);

  // ── Fetch API Keys ──────────────────────────────────────────────────────────
  const fetchApiKeys = useCallback(async () => {
    setLoadingApiKeys(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/integrations/api-keys', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setApiKeys(data || []);
      }
    } catch (_) {
      toast.error('Failed to load API keys');
    } finally {
      setLoadingApiKeys(false);
    }
  }, []);

  // ── Fetch Slack Config ──────────────────────────────────────────────────────
  const fetchSlack = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/integrations/slack', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setSlackConnected(Boolean(data.connected));
        if (data.channel_name) setSlackChannel(data.channel_name);
      }
    } catch (_) {}
  }, []);

  // ── Fetch HubSpot Config ────────────────────────────────────────────────────
  const fetchHubSpot = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/integrations/hubspot', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setHubspotConnected(Boolean(data.connected));
        if (data.portal_id) setHubspotPortalId(data.portal_id);
        if (typeof data.auto_sync_on_reply === 'boolean') setHubspotAutoSync(data.auto_sync_on_reply);
      }
    } catch (_) {}
  }, []);

  // ── Fetch Campaigns for Sheets Ingestion ────────────────────────────────────
  const fetchCampaigns = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/campaigns', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        const active = (data || []).filter((c) => !c.is_deleted);
        setCampaignsList(active);
        if (active.length > 0 && !sheetsCampaignId) {
          setSheetsCampaignId(active[0].id);
        }
      }
    } catch (_) {}
  }, [sheetsCampaignId]);

  useEffect(() => {
    fetchWebhooks();
    fetchApiKeys();
    fetchSlack();
    fetchHubSpot();
    fetchCampaigns();
  }, [fetchWebhooks, fetchApiKeys, fetchSlack, fetchHubSpot, fetchCampaigns]);

  // ── Create Webhook ──────────────────────────────────────────────────────────
  const handleCreateWebhook = async (e) => {
    e.preventDefault();
    if (!targetUrl.startsWith('https://')) {
      toast.error('Webhook URL must begin with https:// for safe egress delivery');
      return;
    }
    if (selectedEvents.length === 0) {
      toast.error('Select at least one event');
      return;
    }
    setSubmittingWebhook(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/integrations/webhooks', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          target_url: targetUrl.trim(),
          events: selectedEvents,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setNewlyCreatedSecret(data.secret);
        setTargetUrl('');
        fetchWebhooks();
        toast.success('Webhook created successfully');
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to create webhook');
      }
    } catch (_) {
      toast.error('Network error creating webhook');
    } finally {
      setSubmittingWebhook(false);
    }
  };

  const handleDeleteWebhook = async (webhookId) => {
    if (!window.confirm('Delete this webhook endpoint? All pending deliveries will be cancelled.')) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/integrations/webhooks/${webhookId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        toast.success('Webhook deleted');
        fetchWebhooks();
      }
    } catch (_) {
      toast.error('Failed to delete webhook');
    }
  };

  const handleTestWebhook = async (webhookId) => {
    toast.info('Sending test ping with HMAC signature...');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/integrations/webhooks/${webhookId}/test`, {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      const data = await res.json();
      if (data.success) {
        toast.success(`Ping delivered (HTTP ${data.status_code})`);
      } else {
        toast.error(`Ping failed: ${data.error || `HTTP ${data.status_code}`}`);
      }
    } catch (_) {
      toast.error('Network error sending test ping');
    }
  };

  // ── Delivery History ────────────────────────────────────────────────────────
  const openDeliveryLogs = async (whk) => {
    setSelectedWebhookForLogs(whk);
    setLoadingDeliveries(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/integrations/webhooks/${whk.id}/deliveries`, {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setDeliveries(data.deliveries || []);
      }
    } catch (_) {
      toast.error('Failed to load deliveries');
    } finally {
      setLoadingDeliveries(false);
    }
  };

  const handleReplayDelivery = async (deliveryId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/integrations/deliveries/${deliveryId}/replay`, {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        toast.success('Delivery queued for immediate retry');
        if (selectedWebhookForLogs) openDeliveryLogs(selectedWebhookForLogs);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Could not replay delivery');
      }
    } catch (_) {
      toast.error('Failed to replay delivery');
    }
  };

  // ── Create API Key ──────────────────────────────────────────────────────────
  const handleCreateApiKey = async (e) => {
    e.preventDefault();
    if (!keyName.trim()) {
      toast.error('Please enter a descriptive key name');
      return;
    }
    setSubmittingKey(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/integrations/api-keys', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          name: keyName.trim(),
          scopes: keyScopes,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setNewlyCreatedKey(data.api_key);
        setKeyName('');
        fetchApiKeys();
        toast.success('API key generated');
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to generate API key');
      }
    } catch (_) {
      toast.error('Network error creating API key');
    } finally {
      setSubmittingKey(false);
    }
  };

  const handleRevokeApiKey = async (keyId) => {
    if (!window.confirm('Revoke this API key? External workflows using this key will immediately be denied access.')) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/integrations/api-keys/${keyId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        toast.success('API key revoked');
        fetchApiKeys();
      }
    } catch (_) {
      toast.error('Failed to revoke API key');
    }
  };

  // ── Save Slack ──────────────────────────────────────────────────────────────
  const handleSaveSlack = async (e) => {
    e.preventDefault();
    setSavingSlack(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/integrations/slack', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          enabled: true,
          webhook_url: slackWebhookUrl.trim(),
          channel_name: slackChannel.trim(),
        }),
      });
      if (res.ok) {
        toast.success('Slack settings saved');
        setSlackConnected(true);
        setSlackWebhookUrl('');
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to save Slack webhook');
      }
    } catch (_) {
      toast.error('Network error saving Slack configuration');
    } finally {
      setSavingSlack(false);
    }
  };

  const handleTestSlack = async () => {
    setTestingSlack(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/integrations/slack/test', {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      const data = await res.json();
      if (data.success) {
        toast.success('Slack test notification sent!');
      } else {
        toast.error(`Slack test failed (HTTP ${data.status_code})`);
      }
    } catch (_) {
      toast.error('Network error testing Slack');
    } finally {
      setTestingSlack(false);
    }
  };

  const handleDisconnectSlack = async () => {
    if (!window.confirm('Disconnect Slack notifications?')) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/integrations/slack', {
        method: 'DELETE',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        toast.success('Slack disconnected');
        setSlackConnected(false);
      }
    } catch (_) {
      toast.error('Failed to disconnect Slack');
    }
  };

  // ── HubSpot Handlers ────────────────────────────────────────────────────────
  const handleSaveHubSpot = async (e) => {
    e.preventDefault();
    if (!hubspotToken.trim() || !hubspotPortalId.trim()) {
      toast.error('Please enter both Access Token and Portal ID');
      return;
    }
    setSavingHubspot(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/integrations/hubspot', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          access_token: hubspotToken.trim(),
          portal_id: hubspotPortalId.trim(),
          auto_sync_on_reply: hubspotAutoSync,
        }),
      });
      if (res.ok) {
        toast.success('HubSpot CRM connected');
        setHubspotConnected(true);
        setHubspotToken('');
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to connect HubSpot');
      }
    } catch (_) {
      toast.error('Network error connecting HubSpot');
    } finally {
      setSavingHubspot(false);
    }
  };

  const handleDisconnectHubSpot = async () => {
    if (!window.confirm('Disconnect HubSpot CRM sync?')) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/integrations/hubspot', {
        method: 'DELETE',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        toast.success('HubSpot CRM disconnected');
        setHubspotConnected(false);
        setHubspotPortalId('');
      }
    } catch (_) {
      toast.error('Failed to disconnect HubSpot');
    }
  };

  // ── Google Sheets / CSV Parser & Import Handlers ────────────────────────────
  const parseCsvLines = (text) => {
    const lines = text.trim().split('\n').map((l) => l.trim()).filter(Boolean);
    if (lines.length < 2) return [];
    const headers = lines[0].split(',').map((h) => h.trim().replace(/^["']|["']$/g, ''));
    const rows = [];
    for (let i = 1; i < lines.length; i++) {
      const values = lines[i].split(',').map((v) => v.trim().replace(/^["']|["']$/g, ''));
      const obj = {};
      headers.forEach((h, idx) => {
        obj[h] = values[idx] || '';
      });
      rows.push(obj);
    }
    return rows;
  };

  const handlePreviewSheets = async () => {
    if (!sheetsCampaignId) {
      toast.error('Please select a target campaign');
      return;
    }
    const rows = parseCsvLines(csvText);
    if (rows.length === 0) {
      toast.error('Paste at least a header row and one data row');
      return;
    }
    setPreviewingSheets(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/integrations/sheets/preview', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          campaign_id: sheetsCampaignId,
          rows: rows,
          column_mapping: {
            linkedin_url: 'linkedin_url',
            first_name: 'first_name',
            last_name: 'last_name',
            email: 'email',
            company_name: 'company_name',
            job_title: 'job_title',
          },
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setPreviewResult(data);
        toast.success(`Validated ${data.valid_count} rows (${data.formula_neutralized_count} formulas neutralized)`);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to preview rows');
      }
    } catch (_) {
      toast.error('Network error previewing rows');
    } finally {
      setPreviewingSheets(false);
    }
  };

  const handleImportSheets = async () => {
    if (!sheetsCampaignId || !previewResult) return;
    const rows = parseCsvLines(csvText);
    setImportingSheets(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/integrations/sheets/import', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          campaign_id: sheetsCampaignId,
          rows: rows,
          column_mapping: {
            linkedin_url: 'linkedin_url',
            first_name: 'first_name',
            last_name: 'last_name',
            email: 'email',
            company_name: 'company_name',
            job_title: 'job_title',
          },
        }),
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(`Successfully enrolled ${data.enrolled_count} leads!`);
        setCsvText('');
        setPreviewResult(null);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Import failed');
      }
    } catch (_) {
      toast.error('Network error importing leads');
    } finally {
      setImportingSheets(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Sub-navigation pills */}
      <div className="flex items-center gap-2 border-b border-gray-200 pb-3">
        <button
          type="button"
          onClick={() => setActiveSection('webhooks')}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
            activeSection === 'webhooks'
              ? 'bg-blue-50 text-blue-700 font-semibold'
              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          }`}
        >
          <Webhook className="w-4 h-4" />
          Webhooks ({webhooks.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveSection('apikeys')}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
            activeSection === 'apikeys'
              ? 'bg-blue-50 text-blue-700 font-semibold'
              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          }`}
        >
          <Key className="w-4 h-4" />
          API Keys ({apiKeys.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveSection('apps')}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
            activeSection === 'apps'
              ? 'bg-blue-50 text-blue-700 font-semibold'
              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          }`}
        >
          <MessageSquare className="w-4 h-4" />
          Connected Apps & Slack
        </button>
      </div>

      {/* ── SECTION: WEBHOOKS ────────────────────────────────────────────── */}
      {activeSection === 'webhooks' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold text-gray-900">Custom Webhooks</h3>
              <p className="text-sm text-gray-500">
                Receive real-time event notifications with HMAC-SHA256 signatures when prospects reply or take action.
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                setNewlyCreatedSecret(null);
                setWebhookModalOpen(true);
              }}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm"
            >
              <Plus className="w-4 h-4" />
              Add Webhook
            </button>
          </div>

          {loadingWebhooks ? (
            <div className="p-8 text-center text-gray-500">
              <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-blue-600" />
              Loading webhooks...
            </div>
          ) : webhooks.length === 0 ? (
            <div className="p-8 text-center bg-gray-50 rounded-xl border border-dashed border-gray-200">
              <Webhook className="w-8 h-8 text-gray-400 mx-auto mb-2" />
              <p className="text-sm font-medium text-gray-700">No webhooks registered yet</p>
              <p className="text-xs text-gray-500 mt-1">
                Connect external servers, Zapier webhooks, or CRM endpoints to receive event streams.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100 bg-white border border-gray-200 rounded-xl shadow-xs overflow-hidden">
              {webhooks.map((whk) => (
                <div key={whk.id} className="p-4 flex items-center justify-between hover:bg-gray-50/50">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${whk.status === 'active' ? 'bg-emerald-500' : 'bg-amber-500'}`} />
                      <span className="font-mono text-sm font-medium text-gray-800">{whk.target_url}</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {whk.events.map((ev) => (
                        <span key={ev} className="px-2 py-0.5 text-xs font-mono bg-blue-50 text-blue-700 rounded-md">
                          {ev}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleTestWebhook(whk.id)}
                      className="px-2.5 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md inline-flex items-center gap-1"
                    >
                      <Send className="w-3 h-3" />
                      Test Ping
                    </button>
                    <button
                      type="button"
                      onClick={() => openDeliveryLogs(whk)}
                      className="px-2.5 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md inline-flex items-center gap-1"
                    >
                      <Activity className="w-3 h-3" />
                      Delivery Logs
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDeleteWebhook(whk.id)}
                      className="p-1.5 text-gray-400 hover:text-red-600 rounded-md"
                      title="Delete webhook"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── SECTION: API KEYS ────────────────────────────────────────────── */}
      {activeSection === 'apikeys' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold text-gray-900">Public REST API Keys</h3>
              <p className="text-sm text-gray-500">
                Generate high-entropy <code>unr_live_</code> keys for Zapier, Make, or custom CRM lead ingestion scripts.
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                setNewlyCreatedKey(null);
                setKeyModalOpen(true);
              }}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm"
            >
              <Plus className="w-4 h-4" />
              Generate Key
            </button>
          </div>

          {loadingApiKeys ? (
            <div className="p-8 text-center text-gray-500">
              <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-blue-600" />
              Loading API keys...
            </div>
          ) : apiKeys.length === 0 ? (
            <div className="p-8 text-center bg-gray-50 rounded-xl border border-dashed border-gray-200">
              <Key className="w-8 h-8 text-gray-400 mx-auto mb-2" />
              <p className="text-sm font-medium text-gray-700">No API keys created yet</p>
              <p className="text-xs text-gray-500 mt-1">
                Create a scoped API key to enroll leads or query campaigns programmatically.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100 bg-white border border-gray-200 rounded-xl shadow-xs overflow-hidden">
              {apiKeys.map((key) => (
                <div key={key.id} className="p-4 flex items-center justify-between hover:bg-gray-50/50">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-gray-900">{key.name}</span>
                      <span className="font-mono text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                        {key.key_prefix}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-500 mt-1">
                      <span>Created: {new Date(key.created_at).toLocaleDateString()}</span>
                      {key.last_used_at && (
                        <span>Last used: {new Date(key.last_used_at).toLocaleDateString()}</span>
                      )}
                      <div className="flex gap-1">
                        {key.scopes.map((s) => (
                          <span key={s} className="px-1.5 py-0.5 bg-gray-100 text-gray-700 rounded text-[11px] font-mono">
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRevokeApiKey(key.id)}
                    className="p-1.5 text-gray-400 hover:text-red-600 rounded-md"
                    title="Revoke key"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── SECTION: CONNECTED APPS & SLACK ──────────────────────────────── */}
      {activeSection === 'apps' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Slack Connector */}
          <div className="p-5 bg-white border border-gray-200 rounded-xl shadow-xs space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-lg bg-[#4A154B]/10 flex items-center justify-center font-bold text-[#4A154B]">
                  #
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-gray-900">Slack Alerts</h4>
                  <p className="text-xs text-gray-500">Post lead replies directly into your channel</p>
                </div>
              </div>
              <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                slackConnected ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-600'
              }`}>
                {slackConnected ? '● Connected' : '○ Not Configured'}
              </span>
            </div>

            <form onSubmit={handleSaveSlack} className="space-y-3 pt-2">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Incoming Webhook URL (from hooks.slack.com)
                </label>
                <input
                  type="url"
                  placeholder="https://hooks.slack.com/services/..."
                  value={slackWebhookUrl}
                  onChange={(e) => setSlackWebhookUrl(e.target.value)}
                  className="w-full text-xs font-mono px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Target Channel</label>
                <input
                  type="text"
                  placeholder="#sales-leads"
                  value={slackChannel}
                  onChange={(e) => setSlackChannel(e.target.value)}
                  className="w-full text-xs px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>

              <div className="flex items-center justify-between pt-2">
                <button
                  type="submit"
                  disabled={savingSlack}
                  className="px-3.5 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
                >
                  {savingSlack ? 'Saving...' : 'Save Slack Settings'}
                </button>
                {slackConnected && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleTestSlack}
                      disabled={testingSlack}
                      className="px-3 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
                    >
                      {testingSlack ? 'Sending...' : 'Send Test Alert'}
                    </button>
                    <button
                      type="button"
                      onClick={handleDisconnectSlack}
                      className="px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 hover:bg-red-100 rounded-lg"
                    >
                      Disconnect
                    </button>
                  </div>
                )}
              </div>
            </form>
          </div>

          {/* HubSpot CRM Card */}
          <div className="p-5 bg-white border border-gray-200 rounded-xl shadow-xs space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-lg bg-[#FF7A59]/10 flex items-center justify-center font-bold text-[#FF7A59]">
                  H
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-gray-900">HubSpot CRM</h4>
                  <p className="text-xs text-gray-500">One-way contact sync on verified prospect replies</p>
                </div>
              </div>
              <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                hubspotConnected ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
              }`}>
                {hubspotConnected ? 'Connected' : 'Setup Required'}
              </span>
            </div>

            {hubspotConnected ? (
              <div className="p-3 bg-gray-50 border border-gray-200 rounded-lg space-y-2">
                <div className="text-xs text-gray-700">
                  <span className="font-semibold">Portal ID:</span> {hubspotPortalId}
                </div>
                <div className="text-xs text-gray-600">
                  Confirmed prospect replies and stage updates are automatically synced as HubSpot contacts.
                </div>
                <div className="pt-1">
                  <button
                    type="button"
                    onClick={handleDisconnectHubSpot}
                    className="px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 hover:bg-red-100 rounded-lg"
                  >
                    Disconnect HubSpot
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSaveHubSpot} className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    Private App Token / Access Token
                  </label>
                  <input
                    type="password"
                    required
                    placeholder="pat-na1-..."
                    value={hubspotToken}
                    onChange={(e) => setHubspotToken(e.target.value)}
                    className="w-full text-xs font-mono px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">HubSpot Portal ID</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. 12345678"
                    value={hubspotPortalId}
                    onChange={(e) => setHubspotPortalId(e.target.value)}
                    className="w-full text-xs px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>
                <label className="flex items-center gap-2 text-xs text-gray-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={hubspotAutoSync}
                    onChange={(e) => setHubspotAutoSync(e.target.checked)}
                    className="rounded text-blue-600"
                  />
                  Automatically sync contact when a prospect replies
                </label>
                <button
                  type="submit"
                  disabled={savingHubspot}
                  className="px-3.5 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
                >
                  {savingHubspot ? 'Connecting...' : 'Connect HubSpot'}
                </button>
              </form>
            )}
          </div>

          {/* Google Sheets / CSV Import Card */}
          <div className="p-5 bg-white border border-gray-200 rounded-xl shadow-xs space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-lg bg-emerald-100 flex items-center justify-center font-bold text-emerald-700">
                  <Activity className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-gray-900">Google Sheets & CSV Lead Ingest</h4>
                  <p className="text-xs text-gray-500">Neutralizes formula injection (CWE-1236) and deduplicates</p>
                </div>
              </div>
              <span className="px-2 py-0.5 text-xs font-medium bg-emerald-50 text-emerald-700 rounded-full">
                Active Tool
              </span>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Target Campaign</label>
                <select
                  value={sheetsCampaignId}
                  onChange={(e) => setSheetsCampaignId(e.target.value)}
                  className="w-full text-xs px-3 py-2 border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  {campaignsList.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.status})
                    </option>
                  ))}
                  {campaignsList.length === 0 && <option value="">No campaigns available</option>}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Paste Spreadsheet Rows (CSV format: linkedin_url,first_name,last_name,email,company_name,job_title)
                </label>
                <textarea
                  rows={4}
                  placeholder={`linkedin_url,first_name,last_name,email,company_name,job_title\nhttps://www.linkedin.com/in/alex-smith,Alex,Smith,alex@example.com,Acme Inc,VP Sales`}
                  value={csvText}
                  onChange={(e) => {
                    setCsvText(e.target.value);
                    setPreviewResult(null);
                  }}
                  className="w-full text-xs font-mono px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handlePreviewSheets}
                  disabled={previewingSheets || !csvText.trim()}
                  className="px-3.5 py-1.5 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
                >
                  {previewingSheets ? 'Validating...' : 'Validate & Preview'}
                </button>
                {previewResult && (
                  <button
                    type="button"
                    onClick={handleImportSheets}
                    disabled={importingSheets || previewResult.valid_count === 0}
                    className="px-3.5 py-1.5 text-xs font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg"
                  >
                    {importingSheets ? 'Enrolling...' : `Enroll ${previewResult.valid_count} Leads`}
                  </button>
                )}
              </div>

              {previewResult && (
                <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs space-y-1 text-blue-900">
                  <div><strong>Total Rows:</strong> {previewResult.total_rows}</div>
                  <div><strong>Valid / Ready:</strong> {previewResult.valid_count}</div>
                  <div><strong>Duplicate Skipped:</strong> {previewResult.duplicate_count}</div>
                  <div><strong>Formulas Neutralized:</strong> {previewResult.formula_neutralized_count}</div>
                </div>
              )}
            </div>
          </div>

          {/* Zapier Card */}
          <div className="p-5 bg-white border border-gray-200 rounded-xl shadow-xs space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-lg bg-[#FF4A00]/10 flex items-center justify-center font-bold text-[#FF4A00]">
                  _
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-gray-900">Zapier</h4>
                  <p className="text-xs text-gray-500">Connect Unravler with downstream tools via REST Hooks</p>
                </div>
              </div>
              <span className="px-2 py-0.5 text-xs font-medium bg-blue-50 text-blue-700 rounded-full">
                Private Pilot
              </span>
            </div>
            <p className="text-xs text-gray-600 leading-relaxed">
              Use <code>POST /api/v1/outreach/public/hooks/subscribe</code> with your <code>unr_live_</code> key to register target webhook callbacks. Field mapping sample available at <code>/public/hooks/sample</code>.
            </p>
            <div className="pt-2">
              <button
                type="button"
                onClick={() => setActiveSection('apikeys')}
                className="text-xs text-blue-600 hover:text-blue-700 font-medium inline-flex items-center gap-1"
              >
                View API Keys for Zapier setup <ExternalLink className="w-3 h-3" />
              </button>
            </div>
          </div>

          {/* Make Card */}
          <div className="p-5 bg-white border border-gray-200 rounded-xl shadow-xs space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-lg bg-[#6F00FF]/10 flex items-center justify-center font-bold text-[#6F00FF]">
                  M
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-gray-900">Make.com</h4>
                  <p className="text-xs text-gray-500">Advanced multi-step integration scenarios</p>
                </div>
              </div>
              <span className="px-2 py-0.5 text-xs font-medium bg-blue-50 text-blue-700 rounded-full">
                Private Pilot
              </span>
            </div>
            <p className="text-xs text-gray-600 leading-relaxed">
              Configure Webhook modules in Make with your <code>unr_live_</code> key to subscribe to real-time outreach event streams.
            </p>
          </div>
        </div>
      )}

      {/* ── MODAL: CREATE WEBHOOK ────────────────────────────────────────── */}
      {webhookModalOpen && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl max-w-lg w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="text-base font-semibold text-gray-900">Add Webhook Endpoint</h3>
              <button
                type="button"
                onClick={() => setWebhookModalOpen(false)}
                className="text-gray-400 hover:text-gray-600 text-sm"
              >
                ✕
              </button>
            </div>

            {newlyCreatedSecret ? (
              <div className="space-y-4">
                <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-lg space-y-2">
                  <div className="flex items-center gap-2 text-emerald-800 font-semibold text-sm">
                    <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                    Webhook Created Successfully!
                  </div>
                  <p className="text-xs text-emerald-700">
                    Copy your HMAC-SHA256 signing secret below. For security, it will <strong>never be shown again</strong>.
                  </p>
                  <div className="flex items-center gap-2 bg-white p-2.5 rounded border border-emerald-200">
                    <code className="text-xs font-mono text-gray-900 flex-1 truncate">{newlyCreatedSecret}</code>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(newlyCreatedSecret, 'Secret copied!')}
                      className="px-2.5 py-1 text-xs bg-emerald-600 text-white rounded font-medium hover:bg-emerald-700 inline-flex items-center gap-1"
                    >
                      <Copy className="w-3 h-3" /> Copy
                    </button>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setWebhookModalOpen(false)}
                  className="w-full py-2 text-sm bg-gray-100 hover:bg-gray-200 text-gray-800 rounded-lg font-medium"
                >
                  Done
                </button>
              </div>
            ) : (
              <form onSubmit={handleCreateWebhook} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    Destination URL (Must be HTTPS)
                  </label>
                  <input
                    type="url"
                    required
                    placeholder="https://api.yourdomain.com/webhooks/unravler"
                    value={targetUrl}
                    onChange={(e) => setTargetUrl(e.target.value)}
                    className="w-full text-xs font-mono px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-2">
                    Subscribed Events
                  </label>
                  <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                    {AVAILABLE_EVENTS.map((ev) => (
                      <label key={ev.id} className="flex items-start gap-2.5 text-xs text-gray-700 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={selectedEvents.includes(ev.id)}
                          onChange={(e) => {
                            if (e.target.checked) setSelectedEvents([...selectedEvents, ev.id]);
                            else setSelectedEvents(selectedEvents.filter((x) => x !== ev.id));
                          }}
                          className="mt-0.5 rounded text-blue-600"
                        />
                        <div>
                          <span className="font-semibold text-gray-900">{ev.label}</span> (<code>{ev.id}</code>)
                          <p className="text-gray-500 text-[11px]">{ev.desc}</p>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t">
                  <button
                    type="button"
                    onClick={() => setWebhookModalOpen(false)}
                    className="px-4 py-2 text-xs font-medium text-gray-700 hover:bg-gray-100 rounded-lg"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submittingWebhook}
                    className="px-4 py-2 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
                  >
                    {submittingWebhook ? 'Creating...' : 'Create Endpoint'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* ── MODAL: GENERATE API KEY ──────────────────────────────────────── */}
      {keyModalOpen && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl max-w-lg w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="text-base font-semibold text-gray-900">Generate API Key</h3>
              <button
                type="button"
                onClick={() => setKeyModalOpen(false)}
                className="text-gray-400 hover:text-gray-600 text-sm"
              >
                ✕
              </button>
            </div>

            {newlyCreatedKey ? (
              <div className="space-y-4">
                <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-lg space-y-2">
                  <div className="flex items-center gap-2 text-emerald-800 font-semibold text-sm">
                    <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                    Key Generated Successfully!
                  </div>
                  <p className="text-xs text-emerald-700">
                    Copy your API key below. Store it in your secret manager. It will <strong>never be shown again</strong>.
                  </p>
                  <div className="flex items-center gap-2 bg-white p-2.5 rounded border border-emerald-200">
                    <code className="text-xs font-mono text-gray-900 flex-1 truncate">{newlyCreatedKey}</code>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(newlyCreatedKey, 'API Key copied!')}
                      className="px-2.5 py-1 text-xs bg-emerald-600 text-white rounded font-medium hover:bg-emerald-700 inline-flex items-center gap-1"
                    >
                      <Copy className="w-3 h-3" /> Copy
                    </button>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setKeyModalOpen(false)}
                  className="w-full py-2 text-sm bg-gray-100 hover:bg-gray-200 text-gray-800 rounded-lg font-medium"
                >
                  Done
                </button>
              </div>
            ) : (
              <form onSubmit={handleCreateApiKey} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Key Name / Description</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Zapier Production Key"
                    value={keyName}
                    onChange={(e) => setKeyName(e.target.value)}
                    className="w-full text-xs px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-2">Granted Scopes</label>
                  <div className="space-y-2">
                    {[
                      { id: 'leads:write', label: 'leads:write', desc: 'Enroll or pause leads programmatically' },
                      { id: 'campaigns:read', label: 'campaigns:read', desc: 'Read campaign list and status' },
                      { id: 'leads:read', label: 'leads:read', desc: 'Read lead history and attributes' },
                    ].map((scope) => (
                      <label key={scope.id} className="flex items-start gap-2.5 text-xs text-gray-700 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={keyScopes.includes(scope.id)}
                          onChange={(e) => {
                            if (e.target.checked) setKeyScopes([...keyScopes, scope.id]);
                            else setKeyScopes(keyScopes.filter((x) => x !== scope.id));
                          }}
                          className="mt-0.5 rounded text-blue-600"
                        />
                        <div>
                          <span className="font-mono font-semibold text-gray-900">{scope.label}</span>
                          <p className="text-gray-500 text-[11px]">{scope.desc}</p>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t">
                  <button
                    type="button"
                    onClick={() => setKeyModalOpen(false)}
                    className="px-4 py-2 text-xs font-medium text-gray-700 hover:bg-gray-100 rounded-lg"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submittingKey}
                    className="px-4 py-2 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
                  >
                    {submittingKey ? 'Generating...' : 'Generate Key'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* ── MODAL: DELIVERY LOGS & REPLAY ────────────────────────────────── */}
      {selectedWebhookForLogs && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl max-w-2xl w-full p-6 shadow-xl space-y-4 max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between border-b pb-3">
              <div>
                <h3 className="text-base font-semibold text-gray-900">Webhook Delivery History</h3>
                <p className="text-xs text-gray-500 font-mono truncate max-w-md">{selectedWebhookForLogs.target_url}</p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedWebhookForLogs(null)}
                className="text-gray-400 hover:text-gray-600 text-sm"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto pr-1">
              {loadingDeliveries ? (
                <div className="p-8 text-center text-gray-500">
                  <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-blue-600" />
                  Loading delivery attempts...
                </div>
              ) : deliveries.length === 0 ? (
                <div className="p-8 text-center text-gray-500 text-xs">
                  No delivery attempts recorded for this endpoint yet.
                </div>
              ) : (
                <table className="w-full text-xs text-left">
                  <thead className="bg-gray-50 text-gray-600 border-b">
                    <tr>
                      <th className="py-2 px-3">Event Type</th>
                      <th className="py-2 px-3">Status</th>
                      <th className="py-2 px-3">Response</th>
                      <th className="py-2 px-3">Attempt</th>
                      <th className="py-2 px-3">Timestamp</th>
                      <th className="py-2 px-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {deliveries.map((del) => (
                      <tr key={del.id} className="hover:bg-gray-50/50">
                        <td className="py-2 px-3 font-mono">{del.payload?.type || 'event'}</td>
                        <td className="py-2 px-3">
                          <span className={`px-2 py-0.5 rounded text-[11px] font-medium ${
                            del.status === 'delivered' ? 'bg-emerald-50 text-emerald-700' :
                            del.status === 'retry' ? 'bg-amber-50 text-amber-700' :
                            del.status === 'dead_letter' ? 'bg-red-50 text-red-700' : 'bg-gray-100 text-gray-600'
                          }`}>
                            {del.status}
                          </span>
                        </td>
                        <td className="py-2 px-3 font-mono">
                          {del.response_status ? `HTTP ${del.response_status}` : (del.error_sanitized || '—')}
                        </td>
                        <td className="py-2 px-3">{del.attempt} / {del.max_attempts || 6}</td>
                        <td className="py-2 px-3 text-gray-500">
                          {new Date(del.created_at).toLocaleTimeString()}
                        </td>
                        <td className="py-2 px-3 text-right">
                          {(del.status === 'dead_letter' || del.status === 'failed') && (
                            <button
                              type="button"
                              onClick={() => handleReplayDelivery(del.id)}
                              className="px-2 py-1 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded text-[11px] inline-flex items-center gap-1 font-medium"
                            >
                              <RefreshCw className="w-3 h-3" /> Replay
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
        </div>
      )}
    </div>
  );
}
