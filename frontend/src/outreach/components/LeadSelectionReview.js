import React, { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';

const REQUEST_KEY = 'unravler.leads.draft-requests.v1';
const MAX_RECOVERY_LENGTH = 100000;
const RECOVERY_ERROR = 'Earlier draft recovery data needs review. Keep this browser session and confirm saved campaigns before starting another request.';
const validRequest = (value) => value && typeof value.name === 'string' && value.name.length <= 100
  && typeof value.request_id === 'string' && /^[a-f0-9-]{36}$/i.test(value.request_id)
  && typeof value.review_digest === 'string' && /^[a-f0-9]{64}$/.test(value.review_digest)
  && typeof value.allow_contacted === 'boolean' && Array.isArray(value.lead_ids)
  && value.lead_ids.length > 0 && value.lead_ids.length <= 200
  && value.lead_ids.every((id) => typeof id === 'string' && id.length <= 200);
const readRequests = () => {
  try {
    const saved = sessionStorage.getItem(REQUEST_KEY);
    if (saved && saved.length > MAX_RECOVERY_LENGTH) throw new Error(RECOVERY_ERROR);
    const entries = JSON.parse(saved || '{}');
    if (!entries || typeof entries !== 'object' || Array.isArray(entries)
      || Object.entries(entries).some(([scope, request]) => !/^[a-f0-9]{64}$/.test(scope) || !validRequest(request)
        || (request.request_scope && request.request_scope !== scope))) throw new Error(RECOVERY_ERROR);
    return Object.fromEntries(Object.entries(entries).map(([scope, request]) => [scope, { ...request, request_scope: scope }]));
  } catch { throw new Error(RECOVERY_ERROR); }
};
const persistRequest = (scope, request) => {
  const requests = readRequests();
  if (request) requests[scope] = request;
  else delete requests[scope];
  if (Object.keys(requests).length > 10) throw new Error('Resolve earlier draft requests before creating another draft.');
  const serialized = JSON.stringify(requests);
  if (serialized.length > MAX_RECOVERY_LENGTH) throw new Error('Resolve earlier draft requests before creating another draft. Recovery storage is full.');
  sessionStorage.setItem(REQUEST_KEY, serialized);
};

const headers = () => {
  const token = localStorage.getItem('token');
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
};

export default function LeadSelectionReview({ leadIds, onClose, onCreated }) {
  const [name, setName] = useState('Follow-up campaign');
  const [allowContacted, setAllowContacted] = useState(false);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [reviewKey, setReviewKey] = useState(0);
  const [restoredRequest, setRestoredRequest] = useState(false);
  const [requestScope, setRequestScope] = useState(null);
  const request = useRef(null);
  const selectionKey = JSON.stringify([...leadIds].sort());

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setPreview(null); setError('');
    setRequestScope(null); setRestoredRequest(false); request.current = null;
    const load = async () => {
      const context = await fetch('/api/v1/outreach/leads/selection/context', {
        credentials: 'include', headers: headers(), signal: controller.signal,
      });
      const scopeBody = await context.json().catch(() => ({}));
      if (!context.ok || typeof scopeBody.request_scope !== 'string' || !/^[a-f0-9]{64}$/.test(scopeBody.request_scope)) {
        throw new Error('Could not confirm the workspace for this review');
      }
      if (controller.signal.aborted) return;
      const scope = scopeBody.request_scope;
      const saved = readRequests()[scope];
      setRequestScope(scope);
      if (saved) {
        request.current = saved; setName(saved.name); setRestoredRequest(true);
        return;
      }
      const response = await fetch('/api/v1/outreach/leads/selection/preview', {
        method: 'POST', credentials: 'include', headers: headers(), signal: controller.signal,
        body: JSON.stringify({ lead_ids: JSON.parse(selectionKey), allow_contacted: allowContacted }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || 'Could not review selected leads');
      if (body.request_scope !== scope) throw new Error('Workspace changed. Review the selection again.');
      if (!controller.signal.aborted) setPreview(body);
    };
    load().catch((failure) => { if (!controller.signal.aborted) setError(failure.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [selectionKey, allowContacted, reviewKey]);

  const create = async () => {
    if ((!preview && !request.current) || saving || !name.trim() || !requestScope) return;
    setSaving(true); setError('');
    try {
      if (!request.current) request.current = { lead_ids: JSON.parse(selectionKey), allow_contacted: allowContacted,
        name: name.trim(), request_id: crypto.randomUUID(), review_digest: preview.review_digest, request_scope: requestScope };
      // Store references before submitting. A closed modal or refreshed page can
      // retry the original request without creating a second campaign.
      persistRequest(requestScope, request.current);
      const response = await fetch('/api/v1/outreach/leads/selection/draft', {
        method: 'POST', credentials: 'include', headers: headers(), body: JSON.stringify(request.current),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 409 || response.status === 410) {
          persistRequest(requestScope, null); request.current = null; setRestoredRequest(false); setPreview(null);
          throw new Error(body.detail || 'Selection changed. Review again before creating a draft.');
        }
        throw new Error(body.detail || 'Could not confirm the draft. Retry the same request.');
      }
      if (typeof body.campaign_id !== 'string' || !body.campaign_id.trim()) throw new Error('Could not confirm the saved draft. Retry the same request.');
      persistRequest(requestScope, null);
      onCreated?.(body);
    } catch (failure) {
      setError(failure.message || 'Could not confirm the draft. Retry the same request.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div role="dialog" aria-modal="true" aria-label="Review follow-up campaign" className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-gray-200 bg-white p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between"><h2 className="text-base font-bold text-gray-900">Review follow-up campaign</h2><button disabled={saving} aria-label="Close follow-up review" onClick={onClose} className="p-1 text-gray-500"><X className="h-4 w-4" /></button></div>
        <p className="text-xs text-gray-500">This creates a draft from the eligible selected leads. Choose senders and a sequence, then review launch separately.</p>
        <input aria-label="Follow-up campaign name" value={name} maxLength={100} disabled={saving || !!request.current} onChange={(event) => setName(event.target.value)} className="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm" />
        <label className="flex items-start gap-2 text-xs text-gray-700"><input type="checkbox" checked={request.current?.allow_contacted ?? allowContacted} disabled={saving || !!request.current} onChange={(event) => setAllowContacted(event.target.checked)} />Include previously contacted leads. Recorded replies and Do-Not-Contact exclusions still block admission.</label>
        {restoredRequest && <p role="status" className="rounded-xl bg-amber-50 p-3 text-xs text-amber-800">An earlier draft request for {request.current?.lead_ids.length} leads needs confirmation. Retry it before creating another draft.</p>}
        {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-xs text-red-700">{error}</p>}
        {loading ? <p className="text-xs text-gray-500">Checking selected leads…</p> : preview && !restoredRequest && (
          <>
            <p role="status" className="text-sm font-semibold text-gray-900">{preview.valid_count} eligible · {preview.excluded_count} excluded</p>
            <div className="max-h-72 overflow-y-auto rounded-xl border border-gray-200 divide-y divide-gray-100">
              {(preview.rows || []).map((row) => <div key={row.source_lead_id} className="flex justify-between gap-4 p-3 text-xs"><span className="font-semibold text-gray-800">{[row.first_name, row.last_name].filter(Boolean).join(' ') || row.linkedin_url}</span><span className={row.status === 'valid' ? 'text-emerald-700' : 'text-red-700'}>{row.status === 'valid' ? 'Eligible' : row.error_reason}</span></div>)}
            </div>
          </>
        )}
        <div className="flex justify-end gap-2">
          {!preview && !restoredRequest && !loading && <button onClick={() => setReviewKey((value) => value + 1)} className="rounded-xl border border-gray-200 px-4 py-2 text-xs">Review again</button>}
          <button disabled={saving || loading || (!restoredRequest && !preview?.valid_count) || !name.trim() || !requestScope} onClick={create} className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{saving ? 'Creating draft…' : request.current ? 'Retry same draft request' : 'Create draft & configure'}</button>
        </div>
      </div>
    </div>
  );
}
