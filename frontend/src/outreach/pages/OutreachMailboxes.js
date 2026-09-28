import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';

const API = '/api/v1/outreach/mailboxes';
const MAX_JOB_POLLS = 45;

async function mailboxFetch(url, options = {}) {
  const token = localStorage.getItem('token');
  const response = await fetch(url, {
    ...options,
    credentials: 'include',
    headers: {
      Authorization: token ? `Bearer ${token}` : '',
      ...options.headers,
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : 'Email settings could not be updated.');
  }
  return response.status === 204 ? {} : response.json();
}

function verifiedAuthorizationUrl(value, provider) {
  try {
    const parsed = new URL(value);
    const allowedHost = provider === 'gmail' ? 'accounts.google.com' : 'login.microsoftonline.com';
    return parsed.protocol === 'https:' && parsed.hostname === allowedHost ? parsed.href : null;
  } catch (_) {
    return null;
  }
}

export default function OutreachMailboxes() {
  const [senders, setSenders] = useState([]);
  const [selectedSenderId, setSelectedSenderId] = useState('');
  const [mailboxes, setMailboxes] = useState([]);
  const [connectionEnabled, setConnectionEnabled] = useState(false);
  const [sendEnabled, setSendEnabled] = useState(false);
  const [syncEnabled, setSyncEnabled] = useState(false);
  const [hunterConfigured, setHunterConfigured] = useState(false);
  const [hunterEnabled, setHunterEnabled] = useState(false);
  const [hunterKey, setHunterKey] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [jobStatus, setJobStatus] = useState('');
  const [pendingJobId, setPendingJobId] = useState(() => (
    new URLSearchParams(window.location.search).get('mailbox_job_id') || ''
  ));

  const refreshMailboxes = useCallback(async () => {
    const data = await mailboxFetch(API);
    setMailboxes(Array.isArray(data.mailboxes) ? data.mailboxes : []);
    setConnectionEnabled(Boolean(data.connection_enabled));
    setSendEnabled(Boolean(data.send_enabled));
    setSyncEnabled(Boolean(data.sync_enabled));
  }, []);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [accounts, mailboxData, hunter] = await Promise.all([
          mailboxFetch('/api/v1/outreach/accounts'),
          mailboxFetch(API),
          mailboxFetch(`${API}/hunter-key`),
        ]);
        if (!active) return;
        const senderList = Array.isArray(accounts) ? accounts.filter((account) => account.status === 'active') : [];
        setSenders(senderList);
        setSelectedSenderId((previous) => previous || senderList[0]?.id || '');
        setMailboxes(Array.isArray(mailboxData.mailboxes) ? mailboxData.mailboxes : []);
        setConnectionEnabled(Boolean(mailboxData.connection_enabled));
        setSendEnabled(Boolean(mailboxData.send_enabled));
        setSyncEnabled(Boolean(mailboxData.sync_enabled));
        setHunterConfigured(Boolean(hunter.configured));
        setHunterEnabled(Boolean(hunter.enabled));
      } catch (failure) {
        if (active) setError(failure.message || 'Email settings could not be loaded.');
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const jobId = pendingJobId;
    if (!jobId) return undefined;
    let active = true;
    let timer;
    let attempts = 0;
    const removeJobParam = () => {
      const url = new URL(window.location.href);
      url.searchParams.delete('mailbox_job_id');
      window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash);
    };
    const poll = async () => {
      try {
        const job = await mailboxFetch(`${API}/connection-jobs/${encodeURIComponent(jobId)}`);
        if (!active) return;
        if (job.status === 'connected') {
          setJobStatus('Mailbox connected.');
          removeJobParam();
          setPendingJobId('');
          await refreshMailboxes();
          return;
        }
        if (job.status === 'failed') {
          setJobStatus(job.error || 'Mailbox connection failed. Try again.');
          removeJobParam();
          setPendingJobId('');
          return;
        }
        attempts += 1;
        if (attempts >= MAX_JOB_POLLS) {
          setJobStatus('Connection is still processing. Refresh this page to check again.');
          return;
        }
        setJobStatus('Checking mailbox connection…');
        timer = window.setTimeout(poll, 2000);
      } catch (failure) {
        if (active) setJobStatus(failure.message || 'Could not check mailbox connection.');
      }
    };
    poll();
    return () => { active = false; window.clearTimeout(timer); };
  }, [pendingJobId, refreshMailboxes]);

  const startConnection = async (provider) => {
    if (!connectionEnabled || !selectedSenderId || busy) return;
    const popup = window.open('about:blank', '_blank');
    if (popup) popup.opener = null;
    setBusy(provider);
    setError('');
    try {
      const result = await mailboxFetch(`${API}/${provider}/authorize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sender_account_id: selectedSenderId }),
      });
      const authorizationUrl = verifiedAuthorizationUrl(result.authorization_url, provider);
      if (!authorizationUrl) throw new Error('The provider returned an invalid authorization link.');
      if (popup) popup.location.href = authorizationUrl;
      else window.location.assign(authorizationUrl);
      if (result.connection_job_id) setPendingJobId(result.connection_job_id);
      setJobStatus('Complete sign-in with the provider. Your password stays with the provider.');
    } catch (failure) {
      if (popup) popup.close();
      setError(failure.message || 'Could not start mailbox connection.');
      toast.error(failure.message || 'Could not start mailbox connection.');
    } finally {
      setBusy('');
    }
  };

  const saveHunterKey = async (event) => {
    event.preventDefault();
    if (!hunterEnabled || !hunterKey.trim() || busy) return;
    setBusy('hunter');
    setError('');
    try {
      const result = await mailboxFetch(`${API}/hunter-key`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: hunterKey.trim() }),
      });
      setHunterConfigured(Boolean(result.configured));
      setHunterKey('');
      toast.success('Hunter key saved securely.');
    } catch (failure) {
      setError(failure.message || 'Could not save Hunter key.');
      toast.error(failure.message || 'Could not save Hunter key.');
    } finally {
      setBusy('');
    }
  };

  const removeHunterKey = async () => {
    if (!window.confirm('Remove the Hunter key? Find email steps will stop until another key is saved.')) return;
    setBusy('hunter');
    try {
      await mailboxFetch(`${API}/hunter-key`, { method: 'DELETE' });
      setHunterConfigured(false);
      setHunterKey('');
      toast.success('Hunter key removed.');
    } catch (failure) {
      setError(failure.message || 'Could not remove Hunter key.');
    } finally {
      setBusy('');
    }
  };

  const disconnect = async (senderId) => {
    if (!window.confirm('Disconnect this email mailbox? Email steps for this sender will pause.')) return;
    setBusy(senderId);
    try {
      await mailboxFetch(`${API}/${encodeURIComponent(senderId)}`, { method: 'DELETE' });
      await refreshMailboxes();
      toast.success('Mailbox disconnected.');
    } catch (failure) {
      setError(failure.message || 'Could not disconnect the mailbox.');
    } finally {
      setBusy('');
    }
  };

  return (
    <section className="space-y-5" aria-label="Email mailboxes">
      <div>
        <h2 className="text-base font-bold text-gray-900">Email mailboxes</h2>
        <p className="mt-1 text-sm text-gray-600">Connect a Gmail or Microsoft mailbox to a specific sender. Sign-in happens directly with the provider; Unravler does not ask for your email password.</p>
        <p className="mt-2 text-xs text-gray-600">With your consent, Unravler stores encrypted access tokens and requests send and mailbox-read permission. It normally reads message headers to detect replies, and reads delivery-report content to identify bounces. Disconnect here to stop access. A provider accepting a send does not confirm delivery.</p>
      </div>
      {loading && <p className="text-sm text-gray-500">Loading email settings…</p>}
      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      {jobStatus && <p role="status" className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">{jobStatus}</p>}
      {!loading && (
        <>
          {!connectionEnabled && <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Email connection is not enabled for this pilot yet. Existing mailbox status remains visible, but new connections cannot be started.</p>}
          {!sendEnabled && <p className="text-xs text-gray-600">Email sending is not enabled. A connected mailbox alone does not activate campaign email steps.</p>}
          {!syncEnabled && <p className="text-xs text-gray-600">Reply monitoring is not enabled. Email follow-ups cannot safely run without it.</p>}
          <div className="rounded-xl border border-gray-200 p-4 space-y-3">
            <label htmlFor="mailbox-sender" className="block text-xs font-semibold text-gray-700">LinkedIn sender for this mailbox</label>
            <select id="mailbox-sender" value={selectedSenderId} onChange={(event) => setSelectedSenderId(event.target.value)} className="w-full rounded-lg border border-gray-200 p-2 text-sm">
              {senders.length === 0 && <option value="">No sender available</option>}
              {senders.map((sender) => <option key={sender.id} value={sender.id}>{sender.account_name || sender.name || sender.id}</option>)}
            </select>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => startConnection('gmail')} disabled={!connectionEnabled || !selectedSenderId || Boolean(busy)} className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Connect Gmail</button>
              <button type="button" onClick={() => startConnection('microsoft')} disabled={!connectionEnabled || !selectedSenderId || Boolean(busy)} className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-900 disabled:opacity-50">Connect Microsoft</button>
            </div>
          </div>
          <div className="rounded-xl border border-gray-200 p-4">
            <h3 className="text-sm font-bold text-gray-900">Connected mailboxes</h3>
            {mailboxes.length === 0 ? <p className="mt-2 text-sm text-gray-500">No mailbox connected.</p> : (
              <ul className="mt-3 space-y-2">
                {mailboxes.map((mailbox) => <li key={mailbox.sender_account_id} className="flex items-center justify-between gap-3 rounded-lg bg-gray-50 p-3 text-sm">
                  <span><strong>{mailbox.email}</strong> · {mailbox.provider} · {mailbox.status}</span>
                  <button type="button" disabled={Boolean(busy)} onClick={() => disconnect(mailbox.sender_account_id)} className="text-xs font-semibold text-red-700 disabled:opacity-50">Disconnect</button>
                </li>)}
              </ul>
            )}
          </div>
          <form onSubmit={saveHunterKey} className="rounded-xl border border-gray-200 p-4 space-y-3">
            <div>
              <h3 className="text-sm font-bold text-gray-900">Find email · Hunter key</h3>
              <p className="mt-1 text-xs text-gray-600">{hunterConfigured ? 'A key is configured. The key value is never shown again.' : 'No Hunter key configured.'}</p>
              {!hunterEnabled && <p className="mt-1 text-xs text-amber-800">Email lookup is not enabled for this pilot.</p>}
            </div>
            <label htmlFor="hunter-api-key" className="block text-xs font-semibold text-gray-700">API key</label>
            <input id="hunter-api-key" aria-label="Hunter API key" type="password" autoComplete="off" value={hunterKey} onChange={(event) => setHunterKey(event.target.value)} className="w-full rounded-lg border border-gray-200 p-2 text-sm" />
            <div className="flex flex-wrap gap-2">
              <button type="submit" disabled={!hunterEnabled || !hunterKey.trim() || Boolean(busy)} className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Save Hunter key</button>
              {hunterConfigured && <button type="button" onClick={removeHunterKey} disabled={Boolean(busy)} className="rounded-lg border border-red-200 px-4 py-2 text-sm font-semibold text-red-700 disabled:opacity-50">Remove key</button>}
            </div>
          </form>
        </>
      )}
    </section>
  );
}
