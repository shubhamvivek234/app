import React, { useEffect, useRef, useState } from 'react';

export const audienceRequest = async (path, body, method = 'POST', signal) => {
  const token = localStorage.getItem('token');
  const response = await fetch(`/api/v1/outreach/lead-lists${path}`, {
    method: body === undefined ? 'GET' : method, credentials: 'include', signal,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json();
  if (!response.ok) { const failure = new Error(typeof data?.detail === 'string' ? data.detail : 'Could not confirm this request. Refresh its status.'); failure.status = response.status; throw failure; }
  return data;
};
export const validAudience = (row) => row && typeof row.id === 'string' && /^list_[0-9a-f]{64}$/.test(row.id) && typeof row.name === 'string'
  && typeof row.review_digest === 'string' && Number.isInteger(row.revision) && row.revision > 0 && /^[0-9a-f]{64}$/.test(row.review_digest)
  && typeof row.campaign_id === 'string' && typeof row.archived === 'boolean' && row.collection_verified === false;
const STORAGE = 'unravler.audience-imports.v1';
const validRef = (value) => value && typeof value.request_id === 'string'
  && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value.request_id)
  && typeof value.request_scope === 'string' && /^[0-9a-f]{64}$/.test(value.request_scope);
const savedRequests = () => {
  const data = JSON.parse(sessionStorage.getItem(STORAGE) || '{}');
  if (!data || Array.isArray(data) || typeof data !== 'object' || Object.keys(data).length > 10
      || Object.entries(data).some(([scope, ref]) => !validRef(ref) || scope !== ref.request_scope)) {
    throw new Error('Saved request references need review. Keep this browser session and check the original imports before starting another.');
  }
  return data;
};
const storeRequest = (ref, remove = false) => {
  const data = savedRequests();
  if (remove) {
    if (data[ref.request_scope]?.request_id === ref.request_id) delete data[ref.request_scope];
  } else {
    if (data[ref.request_scope] && data[ref.request_scope].request_id !== ref.request_id) throw new Error('Check the earlier import first.');
    data[ref.request_scope] = ref;
  }
  if (Object.keys(data).length > 10) throw new Error('Resolve earlier workspace imports before starting another.');
  sessionStorage.setItem(STORAGE, JSON.stringify(data));
};
const validReceipt = (data, ref) => {
  if (data?.request_id !== ref.request_id || data?.request_scope !== ref.request_scope
      || !['pending', 'completed', 'cancelled'].includes(data.status)) return false;
  if (data.status !== 'completed') return data.result == null;
  const r = data.result;
  const keys = ['imported_count', 'skipped_count', 'duplicates_count', 'membership_added_count', 'requested_rows', 'considered_rows', 'list_revision'];
  if (!r || typeof data.list_name !== 'string' || !data.list_name || data.list_name.length > 60
      || typeof data.campaign_id !== 'string' || !keys.every((key) => Number.isInteger(r[key]) && r[key] >= 0)
      || r.list_revision < 2 || r.considered_rows < 1 || r.considered_rows > r.requested_rows || r.requested_rows > 100
      || r.imported_count + r.skipped_count + r.duplicates_count !== r.considered_rows
      || !Array.isArray(r.lead_ids) || r.lead_ids.length !== r.imported_count || new Set(r.lead_ids).size !== r.lead_ids.length
      || r.lead_ids.some((id) => typeof id !== 'string' || !/^[A-Za-z0-9_.:-]{1,200}$/.test(id))
      || r.membership_added_count !== r.imported_count || !Array.isArray(r.row_results) || r.row_results.length !== r.considered_rows
      || r.collection_verified !== false || typeof r.more_rows_in_source !== 'boolean') return false;
  const codes = ['invalid_url', 'missing_name', 'duplicate_batch', 'duplicate_campaign', 'duplicate_contacted', 'do_not_contact', 'email_suppressed', 'withdrawn_cooldown'];
  let imported = 0, skipped = 0, duplicates = 0;
  for (const [index, row] of r.row_results.entries()) {
    if (!row || row.row_number !== index + 1) return false;
    if (row.status === 'imported' && row.lead_id === r.lead_ids[imported]) imported += 1;
    else if (row.status === 'excluded' && codes.includes(row.rejection_code)) {
      if (['duplicate_batch', 'duplicate_campaign'].includes(row.rejection_code)) duplicates += 1;
      else skipped += 1;
    } else return false;
  }
  return imported === r.imported_count && skipped === r.skipped_count && duplicates === r.duplicates_count;
};
const field = 'w-full rounded-lg border border-gray-200 bg-white p-2 text-sm';
const button = 'rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm disabled:opacity-50';

export default function AudienceListImport({ audience, onClose, onImported }) {
  const [source, setSource] = useState('pasted_urls');
  const [raw, setRaw] = useState('');
  const [quantity, setQuantity] = useState(100);
  const [requireName, setRequireName] = useState(true);
  const [skipContacted, setSkipContacted] = useState(true);
  const [preview, setPreview] = useState(null);
  const [overrides, setOverrides] = useState({});
  const [scope, setScope] = useState(null);
  const [pending, setPending] = useState(null);
  const [receipt, setReceipt] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(true);
  const [reading, setReading] = useState(false);
  const generation = useRef(0);
  const previewBody = useRef(null);
  const retry = useRef(null);
  const mounted = useRef(true);
  const terminal = useRef(new Set());
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; generation.current += 1; }; }, []);
  const applyReceipt = (data, ref) => {
    if (!mounted.current) return;
    if (!validReceipt(data, ref)) throw new Error('Import evidence could not be confirmed. Keep the original request and check again.');
    if (data.status === 'pending' && terminal.current.has(ref.request_id)) return;
    if (data.status !== 'pending') { terminal.current.add(ref.request_id); storeRequest(ref, true); }
    if (!mounted.current) return;
    setReceipt(data);
    setPending(data.status === 'pending' ? ref : null);
    if (data.status === 'completed') onImported?.(data);
  };
  useEffect(() => {
    const controller = new AbortController();
    setChecking(true); setScope(null);
    (async () => {
      const context = await audienceRequest('/import-context', undefined, undefined, controller.signal);
      if (typeof context?.request_scope !== 'string' || !/^[0-9a-f]{64}$/.test(context.request_scope)) throw new Error('Could not confirm import account and workspace.');
      const ref = savedRequests()[context.request_scope];
      if (controller.signal.aborted) return;
      setScope(context.request_scope);
      if (ref) {
        setPending(ref);
        const data = await audienceRequest(`/imports/${ref.request_id}?request_scope=${ref.request_scope}`, undefined, undefined, controller.signal);
        if (!controller.signal.aborted) applyReceipt(data, ref);
      }
    })().catch((failure) => { if (!controller.signal.aborted) setError(failure.message); })
      .finally(() => { if (!controller.signal.aborted) setChecking(false); });
    return () => controller.abort();
    // The captured audience is immutable for the lifetime of this dialog.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const invalidate = () => { generation.current += 1; setPreview(null); previewBody.current = null; setOverrides({}); setError(''); };
  const check = async (cancel = false) => {
    if (!pending) return;
    const ref = pending;
    setChecking(true); setError('');
    try {
      const data = await audienceRequest(`/imports/${ref.request_id}${cancel ? '/cancel' : `?request_scope=${ref.request_scope}`}`,
        cancel ? { request_scope: ref.request_scope } : undefined);
      applyReceipt(data, ref);
    } catch (failure) { if (mounted.current) setError(failure.message); }
    finally { if (mounted.current) setChecking(false); }
  };
  const runPreview = async () => {
    if (!scope || pending || checking || busy) return;
    const version = ++generation.current;
    const body = { source_type: source, raw_text: raw, quantity: Number(quantity), require_name: requireName,
      skip_already_contacted: skipContacted, default_first_name: null, default_company_name: null, name_overrides: {} };
    setBusy(true); setError(''); setPreview(null);
    try {
      const data = await audienceRequest(`/${audience.id}/import-preview`, body);
      if (version !== generation.current || !mounted.current) return;
      if (!validAudience(data.list) || data.list.id !== audience.id || data.list.campaign_id !== audience.campaign_id
          || data.request_scope !== scope || !Array.isArray(data.rows) || !data.rows.length || data.rows.length > body.quantity
          || data.rows.some((row, index) => !row || row.row_number !== index + 1 || !['valid', 'rejected'].includes(row.status)
            || ['linkedin_url', 'raw_url', 'first_name', 'cleaned_first_name', 'rejection_code'].some((key) => row[key] != null && typeof row[key] !== 'string'))
          || typeof data.more_rows_in_source !== 'boolean') throw new Error('Could not confirm the reviewed import target and rows.');
      previewBody.current = body; setPreview(data); setOverrides({});
    } catch (failure) { if (version === generation.current && mounted.current) setError(failure.message); }
    finally { if (mounted.current) setBusy(false); }
  };
  const execute = async (sameRequest = false) => {
    if (checking || busy || !scope) return;
    let operation = sameRequest ? retry.current : null;
    if (!sameRequest) {
      if (!preview || !previewBody.current || pending) return;
      if (typeof window.crypto?.randomUUID !== 'function') { setError('This browser cannot create a recoverable request.'); return; }
      const request_id = window.crypto.randomUUID();
      const ref = { request_id, request_scope: scope };
      operation = { ref, path: `/${audience.id}/import`, body: { ...previewBody.current, name_overrides: overrides,
        request_id, request_scope: scope, campaign_id: preview.list.campaign_id, revision: preview.list.revision, review_digest: preview.list.review_digest } };
      try { storeRequest(ref); } catch (failure) { setError(failure.message); return; }
      retry.current = operation; setPending(ref);
    }
    if (!operation) return;
    setBusy(true); setError('');
    try { applyReceipt(await audienceRequest(operation.path, operation.body), operation.ref); }
    catch (failure) { if (mounted.current) setError(`${failure.message} Keep this request and check its status before starting another.`); }
    finally { if (mounted.current) setBusy(false); }
  };
  const fileChanged = (event) => {
    const file = event.target.files[0]; invalidate(); setRaw('');
    if (!file) return;
    if (file.size > 2_000_000) { setRaw(''); setError('CSV must be at most 2 MB.'); return; }
    const version = generation.current; setReading(true);
    const reader = new FileReader();
    reader.onload = () => { if (mounted.current && version === generation.current) { setRaw(String(reader.result)); setReading(false); } };
    reader.onerror = () => { if (mounted.current && version === generation.current) { setError('Could not read this CSV.'); setReading(false); } };
    reader.readAsText(file);
  };
  const held = checking || busy || reading || !!pending || !scope;
  return <div className="space-y-4" role="dialog" aria-label="Import into audience list">
    <div className="flex items-start justify-between gap-4"><div><h3 className="text-lg font-semibold">Import into {audience.name}</h3>
      <p className="text-sm text-gray-500">Review up to 100 input rows. Importing does not launch a campaign.</p></div><button className={button} onClick={onClose}>Back to lists</button></div>
    {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    {checking && <p role="status">Checking original request…</p>}
    {reading && <p role="status">Reading selected CSV…</p>}
    {pending && <div className="space-y-2 rounded-lg bg-amber-50 p-3 text-sm"><p>The original import is unresolved. Check or cancel it before starting another.</p>
      <p className="break-all">Request: {pending.request_id}</p><button className={button} disabled={checking} onClick={() => check()}>Check original import</button>{' '}
      <button className={button} disabled={checking} onClick={() => check(true)}>Cancel original import</button>{' '}
      {retry.current && <button className={button} disabled={checking || busy} onClick={() => execute(true)}>Retry same import</button>}
      <p>Cancellation stops a pending import. If it already completed, its saved result is shown.</p></div>}
    {receipt?.status === 'cancelled' && <p role="status">Original import cancelled. No contacts were imported by that request.</p>}
    {receipt?.status === 'completed' && <div role="status" className="rounded-lg bg-green-50 p-3 text-sm"><p>Saved to {receipt.list_name}: {receipt.result.imported_count} contacts and {receipt.result.membership_added_count} memberships.</p>
      <p>Considered {receipt.result.considered_rows} of {receipt.result.requested_rows} requested rows. Excluded {receipt.result.skipped_count + receipt.result.duplicates_count}.</p>
      {receipt.result.more_rows_in_source && <p>More input rows remain. The full source total is unknown.</p>}
      <p>This is a recorded import result; source collection completeness is unverified.</p>
      <ul className="mt-2 max-h-40 overflow-auto" aria-label="Final import row decisions">{receipt.result.row_results.map((row) => <li key={row.row_number}>
        Row {row.row_number}: {row.status === 'imported' ? 'Imported' : `Excluded — ${row.rejection_code.replaceAll('_', ' ')}`}
      </li>)}</ul></div>}
    {!pending && receipt?.status !== 'completed' && <>
      <label className="block text-sm">Input format<select aria-label="Audience import format" className={field} value={source} disabled={held} onChange={(e) => { invalidate(); setSource(e.target.value); setRaw(''); }}>
        <option value="pasted_urls">Public LinkedIn profile URLs</option><option value="csv">CSV</option></select></label>
      {source === 'csv' && <label className="block text-sm">Upload CSV<input aria-label="Audience CSV file" type="file" accept=".csv,text/csv" disabled={held} onChange={fileChanged} /></label>}
      <label className="block text-sm">{source === 'csv' ? 'CSV with linkedin_url and first_name columns' : 'Profile URLs, one per line (names can be edited in review)'}
        <textarea aria-label="Audience import text" className={field} rows={5} value={raw} disabled={held} onChange={(e) => { invalidate(); setRaw(e.target.value); }} /></label>
      <label className="block text-sm">Input rows to consider (1–100)<input aria-label="Audience requested rows" className={field} type="number" min={1} max={100} value={quantity} disabled={held} onChange={(e) => { invalidate(); setQuantity(e.target.value); }} /></label>
      <label className="mr-4 text-sm"><input type="checkbox" checked={requireName} disabled={held} onChange={(e) => { invalidate(); setRequireName(e.target.checked); }} /> Require first name</label>
      <label className="text-sm"><input type="checkbox" checked={skipContacted} disabled={held} onChange={(e) => { invalidate(); setSkipContacted(e.target.checked); }} /> Skip previously contacted</label>
      <p className="text-xs text-gray-500">Use public profile URLs. Supplied member/transport IDs are unavailable pending verified identity resolution. Do-not-contact and email suppression checks are always applied. Invalid and duplicate rows count toward the selected prefix.</p>
      <button className={button} disabled={held || !raw.trim() || !Number.isInteger(Number(quantity)) || Number(quantity) < 1 || Number(quantity) > 100} onClick={runPreview}>Review input rows</button>
      {preview && <div className="space-y-2"><p className="text-sm">Reviewed target: {preview.list.name}. Eligibility is checked again when saving.</p>
        {preview.more_rows_in_source && <p className="text-sm">More input rows remain outside this review.</p>}
        <div className="max-h-60 overflow-auto">{preview.rows.map((row) => <div key={row.row_number} className="grid grid-cols-[2rem_1fr_1fr] items-center gap-2 border-b py-2 text-xs">
          <span>{row.row_number}</span><span className="break-all">{row.linkedin_url || row.raw_url || 'Invalid profile'}<br />{row.rejection_code || row.status}</span>
          <input aria-label={`Audience first name row ${row.row_number}`} className={field} maxLength={100} value={overrides[row.row_number] ?? row.cleaned_first_name ?? row.first_name ?? ''}
            onChange={(e) => setOverrides((current) => ({ ...current, [row.row_number]: e.target.value }))} /></div>)}</div>
        <button className={button} disabled={held} onClick={() => execute()}>Import reviewed rows</button></div>}
    </>}
  </div>;
}
