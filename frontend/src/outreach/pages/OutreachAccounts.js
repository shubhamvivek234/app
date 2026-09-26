import React, { useState, useEffect } from 'react';
import { Plus, Shield, Globe, Trash2, CheckCircle2, AlertTriangle, Sliders, RefreshCw } from 'lucide-react';
import ConnectLinkedInModal from '../components/ConnectLinkedInModal';
import { toast } from 'sonner';

export default function OutreachAccounts() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingLimitsId, setEditingLimitsId] = useState(null);
  const [limitsForm, setLimitsForm] = useState({ connection_invites: 20, messages: 20 });

  const fetchAccounts = async () => {
    setLoading(true);
    setLoadError('');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/accounts', {
        credentials: 'include',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not load LinkedIn accounts');
      const data = await res.json();
      setAccounts(Array.isArray(data) ? data : []);
    } catch (err) {
      setLoadError(err.message || 'Could not load LinkedIn accounts');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDisconnect = async (accountId) => {
    if (!window.confirm('Are you sure you want to disconnect this account? Its proxy assignment will be cleared; your Webshare plan stays active.')) {
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
      setAccounts((current) => current.filter((account) => account.id !== accountId));
      toast.success('LinkedIn sender disconnected');
    } catch (err) {
      toast.error(err.message || 'Could not disconnect account');
    }
  };

  const handleSaveLimits = async (accountId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/accounts/${accountId}/limits`, {
        method: 'PATCH',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify(limitsForm),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Could not save daily limits');
      const updated = await res.json();
      setAccounts((current) => current.map((account) => (account.id === accountId ? updated : account)));
      setEditingLimitsId(null);
      toast.success('Daily limits saved');
    } catch (err) {
      toast.error(err.message || 'Could not save daily limits');
    }
  };

  return (
    <div className="max-w-6xl mx-auto">
      {/* Header matching Prosp media_1790020960165.png */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-base font-bold text-gray-900">LinkedIn accounts</h2>
        <button
          onClick={() => setModalOpen(true)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-[#2e266f] hover:bg-[#251e5c] px-4 py-2 text-xs font-semibold text-white shadow-2xs transition-colors"
        >
          Connect account
        </button>
      </div>

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
            onClick={() => setModalOpen(true)}
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
                  <img
                    src={acc.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100'}
                    alt={acc.account_name}
                    className="h-12 w-12 rounded-full object-cover border border-gray-100"
                  />
                  <div>
                    <h3 className="font-bold text-gray-900 leading-tight">{acc.account_name}</h3>
                    <p className="text-xs text-gray-400 font-mono mt-0.5">@{acc.vanity_name || 'linkedin'}</p>
                    <div className="flex items-center gap-1.5 mt-1">
                      <span className={`inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full ${acc.status === 'active' ? 'text-emerald-600 bg-emerald-50' : 'text-amber-700 bg-amber-50'}`}>
                        <CheckCircle2 className="h-3 w-3" />
                        {acc.status === 'active' ? 'Active' : (acc.status || 'Unknown').replace(/_/g, ' ').replace(/^./, (letter) => letter.toUpperCase())}
                      </span>
                      <span className="text-[11px] text-gray-400">Warmup: Level {acc.warmup_level || 1}</span>
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => handleDisconnect(acc.id)}
                  title="Disconnect account"
                  className="rounded-lg p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>

              {/* Proxy & Network Badge */}
              <div className="mt-5 pt-4 border-t border-gray-100 flex items-center justify-between text-xs text-gray-500">
                <div className="flex items-center gap-2">
                  <Globe className="h-3.5 w-3.5 text-indigo-500" />
                  <span>Residential Proxy: <strong className="text-gray-700">{acc.proxy?.host ? `${acc.country_code || ''} (${acc.proxy.host})` : 'Not configured'}</strong></span>
                </div>
                {acc.proxy?.host && acc.proxy.host !== '127.0.0.1' && <span className="text-[11px] bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-md font-medium">1:1 Dedicated</span>}
              </div>

              {/* Limits & Counters Section */}
              <div className="mt-4 rounded-xl bg-gray-50/80 p-3.5 border border-gray-100">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-gray-700 uppercase tracking-wider">Daily Limits</span>
                  <button
                    onClick={() => {
                      setEditingLimitsId(editingLimitsId === acc.id ? null : acc.id);
                      setLimitsForm({
                        connection_invites: acc.limits?.connection_invites ?? 20,
                        messages: acc.limits?.messages ?? 20,
                      });
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
                        onChange={(e) => setLimitsForm({ ...limitsForm, connection_invites: parseInt(e.target.value) || 0 })}
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
                        onChange={(e) => setLimitsForm({ ...limitsForm, messages: parseInt(e.target.value) || 0 })}
                        className="w-20 text-center rounded-lg border border-gray-300 py-1 text-xs"
                      />
                    </div>
                    <button
                      onClick={() => handleSaveLimits(acc.id)}
                      className="w-full mt-2 rounded-lg bg-indigo-600 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700"
                    >
                      Save Limits
                    </button>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-gray-400">Invites:</span> <strong className="text-gray-800">{acc.limits?.connection_invites ?? 20}/day</strong>
                    </div>
                    <div>
                      <span className="text-gray-400">Messages:</span> <strong className="text-gray-800">{acc.limits?.messages ?? 20}/day</strong>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      <ConnectLinkedInModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onAccountConnected={() => { setModalOpen(false); fetchAccounts(); }}
      />
    </div>
  );
}
