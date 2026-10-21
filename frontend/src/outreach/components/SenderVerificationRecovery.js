import React, { useCallback, useEffect, useRef, useState } from 'react';

const STATUSES = new Set(['queued', 'running', 'finalizing', 'repairing', 'completed', 'failed',
  'storage_stopped', 'repaired_stopped', 'cancelled']);
const HOLDS = new Set(['queued', 'running', 'finalizing', 'repairing', 'storage_stopped', 'repaired_stopped']);
const plainId = value => typeof value === 'string' && value.trim().length > 0 && value.length <= 200;
const exact = (value, keys) => value && !Array.isArray(value)
  && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
const validContext = value => exact(value, ['contract_version', 'workspace_id', 'scope_digest'])
  && value.contract_version === 1 && plainId(value.workspace_id) && /^[a-f0-9]{64}$/.test(value.scope_digest);
const validJob = value => exact(value, ['job_id', 'sender_id', 'status', 'reconnect'])
  && plainId(value.job_id) && plainId(value.sender_id) && STATUSES.has(value.status) && typeof value.reconnect === 'boolean';
const validList = value => exact(value, ['context', 'jobs', 'operator_review_required'])
  && validContext(value.context) && typeof value.operator_review_required === 'boolean'
  && Array.isArray(value.jobs) && value.jobs.length <= 20 && value.jobs.every(validJob)
  && new Set(value.jobs.map(job => job.job_id)).size === value.jobs.length;
const sameContext = (left, right) => validContext(left) && validContext(right)
  && left.workspace_id === right.workspace_id && left.scope_digest === right.scope_digest;

export default function SenderVerificationRecovery({ onState, onAccountConnected, refreshKey = 0 }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(null);
  const version = useRef(0);
  const callbacks = useRef({ onState, onAccountConnected });
  callbacks.current = { onState, onAccountConnected };
  const headers = token => ({ Authorization: token ? `Bearer ${token}` : '' });
  const publish = (value, token) => callbacks.current.onState?.({ context: value?.context || null, token,
    blocked: !value || value.operator_review_required || value.jobs.some(job => HOLDS.has(job.status)) });
  const readList = async token => {
    const result = await fetch('/api/v1/outreach/accounts/connection-jobs', {
      credentials: 'include', cache: 'no-store', headers: headers(token),
    });
    const value = await result.json().catch(() => null);
    if (!result.ok || !validList(value)) throw new Error('Could not discover sender verifications. Refresh before connecting.');
    return value;
  };

  const refresh = useCallback(async () => {
    const currentVersion = ++version.current;
    const token = localStorage.getItem('token');
    const current = () => version.current === currentVersion && localStorage.getItem('token') === token;
    setLoading(true); setChecking(null); setError(''); setData(null); publish(null, token);
    try {
      const value = await readList(token);
      if (!current()) return;
      setData(value); publish(value, token);
    } catch (failure) {
      if (current()) setError(failure.message);
    } finally {
      if (version.current === currentVersion) setLoading(false);
    }
    // onState/onAccountConnected are read from refs so parent renders do not restart discovery.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    refresh();
    const refocus = () => refresh();
    window.addEventListener('focus', refocus);
    window.addEventListener('storage', refocus);
    return () => { version.current += 1; window.removeEventListener('focus', refocus); window.removeEventListener('storage', refocus); };
  }, [refresh, refreshKey]);

  const checkJob = async original => {
    if (loading || checking || !data) return;
    const captured = data;
    const currentVersion = ++version.current;
    const token = localStorage.getItem('token');
    const current = () => version.current === currentVersion && localStorage.getItem('token') === token;
    setChecking(original.job_id); setError(''); publish(null, token);
    try {
      const fresh = await readList(token);
      if (!current()) return;
      if (!sameContext(fresh.context, captured.context)) throw new Error('Sender verification context changed; refresh the page.');
      const selected = fresh.jobs.find(job => job.job_id === original.job_id && job.sender_id === original.sender_id);
      if (!selected) throw new Error('The original verification is no longer discoverable; contact support if its result is unknown.');
      const params = new URLSearchParams({ scope_digest: captured.context.scope_digest });
      const response = await fetch(`/api/v1/outreach/accounts/connection-jobs/${encodeURIComponent(original.job_id)}?${params}`, {
        credentials: 'include', cache: 'no-store', headers: headers(token),
      });
      const job = await response.json().catch(() => null);
      if (!current()) return;
      if (!response.ok || !job || job.job_id !== original.job_id || job.sender_id !== original.sender_id
          || job.workspace_id !== captured.context.workspace_id || job.scope_digest !== captured.context.scope_digest
          || job.contract_version !== 1 || !STATUSES.has(job.status) || typeof job.account_current !== 'boolean') {
        throw new Error('The original verification status could not be confirmed. Refresh or contact support.');
      }
      if (job.status === 'completed' && job.account_current && (!job.account || job.account.id !== original.sender_id
          || job.account.workspace_id !== captured.context.workspace_id || job.account.status !== 'active')) {
        throw new Error('The current sender does not match this verification. Refresh or contact support.');
      }
      const updated = { ...fresh, jobs: fresh.jobs.map(row => row.job_id === original.job_id ? { ...row, status: job.status } : row) };
      setData(updated); publish(updated, token);
      if (job.status === 'completed' && job.account_current) callbacks.current.onAccountConnected?.(job.account);
      else if (job.status === 'completed') setError('This historical verification no longer confirms a current connected sender. Review the sender account before reconnecting.');
      else if (job.status === 'failed') setError('Verification failed. Review your session and sender account before trying again.');
      else if (HOLDS.has(job.status)) setError('Verification is still pending or needs support review. Check its status again before reconnecting.');
    } catch (failure) {
      if (current()) { publish(null, token); setError(failure.message); }
    } finally {
      if (version.current === currentVersion) setChecking(null);
    }
  };

  return (
    <section aria-label="Sender verification recovery" className="mb-5 rounded-xl border border-gray-200 bg-gray-50 p-4 text-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="font-semibold text-gray-900">Sender verifications</p>
        <button type="button" onClick={refresh} disabled={loading || Boolean(checking)} className="text-xs font-semibold underline disabled:opacity-50">Refresh verifications</button>
      </div>
      {loading ? <p className="mt-2 text-xs text-gray-600">Checking for unfinished verifications…</p>
        : data?.jobs.length === 0 && !data.operator_review_required ? <p className="mt-2 text-xs text-gray-600">No recent verifications to recover.</p> : null}
      {data?.operator_review_required && <p className="mt-2 text-amber-800">A verification storage result needs support review before another connection.</p>}
      {data?.jobs.map(job => (
        <div key={job.job_id} data-verification-job={job.job_id} className="mt-3 flex items-center justify-between gap-3 border-t border-gray-200 pt-2">
          <span className="text-xs text-gray-700">{job.reconnect ? 'Reconnect' : 'Connection'} {job.job_id.slice(0, 8)} · {job.status.replaceAll('_', ' ')}</span>
          <button type="button" disabled={loading || Boolean(checking)} onClick={() => checkJob(job)} className="text-xs font-semibold underline disabled:opacity-50">
            {checking === job.job_id ? 'Checking…' : 'Check verification'}
          </button>
        </div>
      ))}
      {error && <p role="alert" className="mt-3 text-xs text-red-700">{error}</p>}
    </section>
  );
}
