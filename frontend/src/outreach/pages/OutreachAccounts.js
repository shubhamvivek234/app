import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Globe, Trash2, Sliders, RefreshCw, Shield } from 'lucide-react';
import ConnectLinkedInModal from '../components/ConnectLinkedInModal';
import SenderVerificationRecovery from '../components/SenderVerificationRecovery';
import SenderStoredDetails, { savedStatus, savedCap } from '../components/SenderStoredDetails';
import { toast } from 'sonner';

export default function OutreachAccounts() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [reconnectAccount, setReconnectAccount] = useState(null);
  const [modalContext, setModalContext] = useState(null);
  const [recovery, setRecovery] = useState({ blocked: true, context: null, token: null });
  const [recoveryRevision, setRecoveryRevision] = useState(0);
  const [editingLimitsId, setEditingLimitsId] = useState(null);
  const [limitsForm, setLimitsForm] = useState({ connection_invites: '', messages: '', email_sends: '' });
  const [limitChanges, setLimitChanges] = useState({});
  const [savingLimits, setSavingLimits] = useState(false);
  const [togglingActivityControlId, setTogglingActivityControlId] = useState(null);
  const openingLimits = useRef({});
  const validChanges = Object.values(limitChanges).every(value => /^(0|[1-9]\d?)$/.test(value) && Number(value) <= 35);
  const canSaveLimits = Object.keys(limitChanges).length > 0 && validChanges && !savingLimits;
  const changeLimit = (field, value) => {
    setLimitsForm(current => ({ ...current, [field]: value }));
    setLimitChanges(current => {
      const next = { ...current };
      if (value === String(openingLimits.current[field] ?? '')) delete next[field];
      else next[field] = value;
      return next;
    });
  };
  const loadVersion = useRef(0);

  const fetchAccounts = useCallback(async () => {
    const version = ++loadVersion.current;
    const token = localStorage.getItem('token');
    const current = () => loadVersion.current === version && localStorage.getItem('token') === token;
    setLoading(true);
    setLoadError('');
    try {
      const res = await fetch('/api/v1/outreach/accounts', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not load LinkedIn accounts');
      const data = await res.json();
      if (!current()) return;
      if (!Array.isArray(data)) throw new Error('LinkedIn accounts returned an invalid response.');
      setAccounts(data);
    } catch (err) {
      if (current()) setLoadError(err.message || 'Could not load LinkedIn accounts');
    } finally {
      if (loadVersion.current === version) setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAccounts();
    return () => { loadVersion.current += 1; };
  }, [fetchAccounts]);

  const handleDisconnect = async (accountId) => {
    if (!window.confirm('Disconnect this sender and pause its campaigns? Its session is removed, but the paid-term IP stays reserved for this sender until its provider term ends.')) {
      return;
    }
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/accounts/${accountId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not disconnect account');
      loadVersion.current += 1;
      setLoading(false);
      setAccounts((current) => current.map((account) => account.id === accountId
        ? { ...account, status: 'disconnected' } : account));
      toast.success('Sender disconnected. Its paid-term IP remains reserved.');
    } catch (err) {
      toast.error(err.message || 'Could not disconnect account');
    }
  };

  const handleSaveLimits = async (accountId) => {
    if (!canSaveLimits) return;
    setSavingLimits(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/accounts/${accountId}/limits`, {
        method: 'PATCH',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify(Object.fromEntries(Object.entries(limitChanges).map(([key, value]) => [key, Number(value)]))),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not save daily limits');
      const updated = await res.json();
      setAccounts((current) => current.map((account) => (account.id === accountId ? { ...account, ...updated } : account)));
      setEditingLimitsId(null);
      toast.success('Daily limits saved');
    } catch (err) {
      toast.error(err.message || 'Could not save daily limits');
    } finally {
      setSavingLimits(false);
    }
  };

  const handleToggleActivityControl = async (acc) => {
    const currentlyEnabled = Boolean(acc.activity_control_enabled || acc.activity_control?.activity_control_enabled);
    setTogglingActivityControlId(acc.id);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/accounts/${acc.id}/activity-control`, {
        method: 'PATCH',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ activity_control_enabled: !currentlyEnabled }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not update Activity Control');
      const updated = await res.json();
      setAccounts((current) => current.map((account) => (account.id === acc.id ? { ...account, ...updated } : account)));
      toast.success(!currentlyEnabled ? 'Activity Control enabled' : 'Activity Control disabled');
    } catch (err) {
      toast.error(err.message || 'Could not update Activity Control');
    } finally {
      setTogglingActivityControlId(null);
    }
  };

  const openConnection = target => {
    if (recovery.blocked || !recovery.context || recovery.token !== localStorage.getItem('token')) return;
    setModalContext(recovery.context);
    setReconnectAccount(target); setModalOpen(true);
  };

  return (
    <div className="max-w-6xl mx-auto">
      {/* Header matching Prosp media_1790020960165.png */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-base font-bold text-gray-900">LinkedIn accounts</h2>
        <button type="button" onClick={fetchAccounts} disabled={loading} aria-label="Refresh sender accounts"
          className="ml-auto mr-3 inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-2 text-xs font-semibold text-gray-700 disabled:opacity-50">
          <RefreshCw className="h-3.5 w-3.5" />Refresh
        </button>
        <button
          disabled={recovery.blocked}
          onClick={() => openConnection(null)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-[#2e266f] hover:bg-[#251e5c] px-4 py-2 text-xs font-semibold text-white shadow-2xs transition-colors"
        >
          Connect account
        </button>
      </div>

      <SenderVerificationRecovery onState={setRecovery} refreshKey={recoveryRevision} onAccountConnected={fetchAccounts} />

      {/* Account Cards or Empty State */}
      {loading ? (
        <div className="flex items-center justify-center py-16 text-gray-400">
          <RefreshCw className="h-6 w-6 animate-spin" />
        </div>
      ) : loadError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
          {loadError} <button type="button" onClick={fetchAccounts} className="font-semibold underline">Retry</button>
        </div>
      ) : accounts.length === 0 ? (
        <div className="rounded-xl border border-gray-200/80 bg-gray-50/50 p-6 text-xs sm:text-sm text-gray-500">
          No accounts connected yet. Click{' '}
          <button
            disabled={recovery.blocked}
            onClick={() => openConnection(null)}
            className="font-semibold text-gray-800 hover:underline"
          >
            Connect account
          </button>{' '}
          to add one.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {accounts.map((acc) => (
            <div key={acc.id} className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm hover:shadow-md transition-shadow">
              {/* Account Top Row */}
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3.5">
                  {acc.avatar_url ? (
                    <img
                      src={acc.avatar_url}
                      alt={acc.account_name}
                      className="h-12 w-12 rounded-full object-cover border border-gray-100"
                    />
                  ) : (
                    <div className="h-12 w-12 rounded-full bg-indigo-100 text-indigo-700 font-bold flex items-center justify-center text-sm border border-indigo-200 shrink-0">
                      {(acc.account_name || 'LI')
                        .split(/\s+/)
                        .filter(Boolean)
                        .slice(0, 2)
                        .map((part) => part[0]?.toUpperCase())
                        .join('')}
                    </div>
                  )}
                  <div>
                    <div className="flex items-center gap-1.5">
                      <h3 className="font-bold text-gray-900 leading-tight">{acc.account_name}</h3>
                      <span
                        title="Activity Control automatically adjusts daily connection & message limits based on 1st-degree connections, pending sent invitations, account type & warm-up activity."
                        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold ${
                          acc.activity_control_enabled || acc.activity_control?.activity_control_enabled
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-gray-100 text-gray-500'
                        }`}
                      >
                        <Shield className="h-3 w-3" />
                        {acc.activity_control_enabled || acc.activity_control?.activity_control_enabled ? 'Activity Control' : 'Manual Caps'}
                      </span>
                    </div>
                    <p className="text-xs text-gray-400 font-mono mt-0.5">@{acc.vanity_name || 'linkedin'}</p>
                    <div className="flex items-center gap-1.5 mt-1">
                      <span className="inline-flex items-center text-[11px] font-medium px-2 py-0.5 rounded-full text-gray-600 bg-gray-100">
                        Saved status: {savedStatus(acc.status)}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    disabled={recovery.blocked}
                    onClick={() => openConnection(acc)}
                    title="Reconnect this sender"
                    aria-label={`Reconnect ${acc.account_name}`}
                    className="rounded-lg p-2 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                  >
                    <RefreshCw className="h-4 w-4" />
                  </button>
                  {acc.status !== 'disconnected' && <button
                    onClick={() => handleDisconnect(acc.id)}
                    title="Disconnect account"
                    className="rounded-lg p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>}
                </div>
              </div>

              {/* Proxy & Network Badge */}
              <div className="mt-5 pt-4 border-t border-gray-100 flex items-center justify-between text-xs text-gray-500">
                <div className="flex items-center gap-2">
                  <Globe className="h-3.5 w-3.5 text-indigo-500" />
                  <span>Configured proxy: <strong className="text-gray-700">{typeof acc.proxy?.host === 'string' && acc.proxy.host ? acc.proxy.host : 'Not recorded'}</strong></span>
                </div>
              </div>
              <SenderStoredDetails account={acc} />

              {/* Limits & Counters Section */}
              <div className="mt-4 rounded-xl bg-gray-50/80 p-3.5 border border-gray-100">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-gray-700 uppercase tracking-wider">Saved daily caps</span>
                  <button
                    disabled={savingLimits}
                    onClick={() => {
                      setEditingLimitsId(editingLimitsId === acc.id ? null : acc.id);
                      const opening = {
                        connection_invites: savedCap(acc.limits?.connection_invites) ?? '',
                        messages: savedCap(acc.limits?.messages) ?? '',
                        email_sends: savedCap(acc.limits?.email_sends) ?? '',
                      };
                      openingLimits.current = opening;
                      setLimitsForm(opening);
                      setLimitChanges({});
                    }}
                    className="text-xs font-medium text-indigo-600 hover:text-indigo-800 inline-flex items-center gap-1"
                  >
                    <Sliders className="h-3 w-3" />
                    {editingLimitsId === acc.id ? 'Close' : 'Adjust'}
                  </button>
                </div>

                {editingLimitsId === acc.id ? (
                  <div className="space-y-2.5 pt-1">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-600">Invites/day:</span>
                      <input
                        type="number"
                        max={35}
                        min={0}
                        value={limitsForm.connection_invites}
                        disabled={savingLimits}
                        aria-label="Saved invites per day"
                        onChange={(e) => changeLimit('connection_invites', e.target.value)}
                        className="w-20 text-center rounded-lg border border-gray-300 py-1 text-xs"
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-600">Messages/day:</span>
                      <input
                        type="number"
                        max={35}
                        min={0}
                        value={limitsForm.messages}
                        disabled={savingLimits}
                        aria-label="Saved messages per day"
                        onChange={(e) => changeLimit('messages', e.target.value)}
                        className="w-20 text-center rounded-lg border border-gray-300 py-1 text-xs"
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-600">Email sends/day:</span>
                      <input
                        type="number"
                        max={35}
                        min={0}
                        value={limitsForm.email_sends}
                        disabled={savingLimits}
                        aria-label="Saved emails per day"
                        onChange={(e) => changeLimit('email_sends', e.target.value)}
                        className="w-20 text-center rounded-lg border border-gray-300 py-1 text-xs"
                      />
                    </div>
                    <button
                      disabled={!canSaveLimits}
                      onClick={() => handleSaveLimits(acc.id)}
                      className="w-full mt-2 rounded-lg bg-indigo-600 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700"
                    >
                      Save Limits
                    </button>
                    {!validChanges && <p role="alert" className="text-xs text-amber-800">Enter a whole number from 0 to 35 for each changed cap.</p>}
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-gray-400">Invites:</span> <strong className="text-gray-800">{savedCap(acc.limits?.connection_invites) === null ? 'Not recorded' : `${acc.limits.connection_invites}/day`}</strong>
                    </div>
                    <div>
                      <span className="text-gray-400">Messages:</span> <strong className="text-gray-800">{savedCap(acc.limits?.messages) === null ? 'Not recorded' : `${acc.limits.messages}/day`}</strong>
                    </div>
                    <div><span className="text-gray-400">Email sends:</span> <strong className="text-gray-800">{savedCap(acc.limits?.email_sends) === null ? 'Not recorded' : `${acc.limits.email_sends}/day`}</strong></div>
                  </div>
                )}
                <p className="mt-2 text-xs text-gray-500">Actual allowance can be lower. Campaign caps, daily use, warm-up and current execution checks also apply.</p>
                <div className="mt-3 pt-2.5 border-t border-gray-200/70 flex flex-wrap items-center justify-between gap-2 text-[11px]">
                  <div className="text-gray-600">
                    <span className="font-semibold text-gray-800 inline-flex items-center gap-1">
                      <Shield className="h-3 w-3 text-emerald-600" /> Activity Control:
                    </span>{' '}
                    Auto-adjusts daily limits by connections, pending invites, tier ({acc.premium_product || 'classic'}) &amp; warm-up.
                  </div>
                  <button
                    type="button"
                    disabled={togglingActivityControlId === acc.id}
                    onClick={() => handleToggleActivityControl(acc)}
                    className={`px-2.5 py-1 rounded-lg font-semibold transition-colors ${
                      acc.activity_control_enabled || acc.activity_control?.activity_control_enabled
                        ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200'
                        : 'bg-white border border-gray-200 text-gray-700 hover:bg-gray-100'
                    }`}
                  >
                    {acc.activity_control_enabled || acc.activity_control?.activity_control_enabled ? 'Disable Activity Control' : 'Enable Activity Control'}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      <ConnectLinkedInModal
        isOpen={modalOpen}
        reconnectAccount={reconnectAccount}
        connectionContext={modalContext}
        onClose={() => { setModalOpen(false); setReconnectAccount(null); setRecoveryRevision(value => value + 1); }}
        onAccountConnected={() => { setModalOpen(false); setReconnectAccount(null); fetchAccounts(); }}
      />
    </div>
  );
}
