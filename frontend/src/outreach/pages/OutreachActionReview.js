import React, { useCallback, useEffect, useState } from 'react';

const API = '/api/v1/outreach/action-reviews';
const PAGE_SIZE = 25;

async function reviewFetch(path, options = {}) {
  const token = localStorage.getItem('token');
  const response = await fetch(path, {
    ...options,
    credentials: 'include',
    headers: {
      Authorization: token ? `Bearer ${token}` : '',
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Action review could not be completed.');
  }
  return response.json();
}

const formatDate = (value) => {
  if (!value) return 'Unknown date';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unknown date' : date.toLocaleString();
};

export default function OutreachActionReview() {
  const [view, setView] = useState('pending');
  const [page, setPage] = useState(0);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [decision, setDecision] = useState('confirmed_sent');
  const [evidenceNote, setEvidenceNote] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await reviewFetch(`${API}?view=${view}&skip=${page * PAGE_SIZE}&limit=${PAGE_SIZE}`);
      setItems(Array.isArray(result.items) ? result.items : []);
      setTotal(Number(result.total) || 0);
    } catch (failure) {
      setError(failure.message || 'Action reviews could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [page, view]);

  useEffect(() => { load(); }, [load]);

  const chooseView = (nextView) => {
    setView(nextView);
    setPage(0);
    setSelectedId('');
    setNotice('');
  };

  const openReview = (item) => {
    setSelectedId(item.id);
    setDecision(item.can_confirm ? 'confirmed_sent' : 'not_sent_stop');
    setEvidenceNote('');
    setAcknowledged(false);
    setError('');
  };

  const resolve = async (event) => {
    event.preventDefault();
    if (!selectedId || evidenceNote.trim().length < 10 || !acknowledged || busy) return;
    setBusy(true);
    setError('');
    try {
      await reviewFetch(`${API}/${encodeURIComponent(selectedId)}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, evidence_note: evidenceNote.trim(), acknowledged: true }),
      });
      setSelectedId('');
      setEvidenceNote('');
      setAcknowledged(false);
      setNotice('Review recorded. The campaign remains paused; inspect it before resuming.');
      await load();
    } catch (failure) {
      setError(failure.message || 'Action review could not be completed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-5" aria-label="Action reviews">
      <div>
        <h2 className="text-base font-bold text-gray-900">Action reviews</h2>
        <p className="mt-1 text-sm text-gray-600">Review outreach actions whose provider outcome could not be confirmed. Check the sender account or provider Sent folder before recording a decision. Unravler never retries an uncertain action automatically.</p>
        <p className="mt-2 text-xs text-amber-800">A review does not restart a paused campaign. Resume it separately only after checking the sender, sequence, and remaining leads.</p>
      </div>

      <div className="flex gap-2" aria-label="Action review view">
        <button type="button" onClick={() => chooseView('pending')} aria-pressed={view === 'pending'} className={`rounded-lg px-3 py-2 text-sm ${view === 'pending' ? 'bg-gray-900 text-white' : 'border border-gray-300 text-gray-700'}`}>Needs review</button>
        <button type="button" onClick={() => chooseView('resolved')} aria-pressed={view === 'resolved'} className={`rounded-lg px-3 py-2 text-sm ${view === 'resolved' ? 'bg-gray-900 text-white' : 'border border-gray-300 text-gray-700'}`}>Review history</button>
      </div>

      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      {notice && <p role="status" className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-800">{notice}</p>}
      {loading ? <p className="text-sm text-gray-500">Loading action reviews…</p> : (
        <>
          {items.length === 0 && <p className="rounded-xl border border-gray-200 bg-white p-5 text-sm text-gray-600">{view === 'pending' ? 'No actions need review.' : 'No recorded reviews yet.'}</p>}
          <ul className="space-y-3">
            {items.map((item) => (
              <li key={item.id} className="rounded-xl border border-gray-200 bg-white p-4 space-y-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-gray-900">{item.lead_name} · {item.task_type?.replaceAll('_', ' ')}</p>
                    <p className="text-xs text-gray-600">{item.campaign_name} · {item.sender_name} · {formatDate(item.updated_at || item.created_at)}</p>
                    {item.lead_email && <p className="text-xs text-gray-600">{item.lead_email}</p>}
                  </div>
                  <span className="rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-800">{item.status?.replaceAll('_', ' ')}</span>
                </div>
                {view === 'pending' ? (
                  <>
                    <p className="text-xs text-gray-600">{item.reason}</p>
                    {item.campaign_status !== 'paused' && <p className="text-xs text-red-700">Pause this campaign before resolving the action.</p>}
                    <button type="button" disabled={item.campaign_status !== 'paused' || busy} onClick={() => openReview(item)} className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-semibold text-gray-800 disabled:opacity-50">Review action</button>
                    {selectedId === item.id && (
                      <form onSubmit={resolve} className="mt-3 space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
                        <fieldset className="space-y-2 text-sm text-gray-800">
                          <legend className="font-semibold">What did you verify?</legend>
                          {item.can_confirm && <label className="flex items-start gap-2"><input type="radio" name={`decision-${item.id}`} checked={decision === 'confirmed_sent'} onChange={() => setDecision('confirmed_sent')} /> Confirmed sent in provider account</label>}
                          <label className="flex items-start gap-2"><input type="radio" name={`decision-${item.id}`} checked={decision === 'not_sent_stop'} onChange={() => setDecision('not_sent_stop')} /> Not sent — stop this lead (no retry)</label>
                        </fieldset>
                        <label className="block text-xs font-semibold text-gray-700" htmlFor="review-evidence">Evidence and checks performed</label>
                        <textarea id="review-evidence" value={evidenceNote} onChange={(event) => setEvidenceNote(event.target.value)} minLength={10} maxLength={500} required rows={3} className="w-full rounded-lg border border-gray-300 p-2 text-sm" placeholder="For example: checked the provider Sent folder and message timestamp" />
                        <label className="flex items-start gap-2 text-xs text-gray-700"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} /> I checked the provider account. This decision is recorded as my assertion, not provider verification.</label>
                        <div className="flex gap-2">
                          <button type="submit" disabled={busy || evidenceNote.trim().length < 10 || !acknowledged} className="rounded-lg bg-gray-900 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy ? 'Recording…' : 'Record decision'}</button>
                          <button type="button" disabled={busy} onClick={() => setSelectedId('')} className="rounded-lg border border-gray-300 px-3 py-2 text-xs text-gray-700">Cancel</button>
                        </div>
                      </form>
                    )}
                  </>
                ) : item.resolution && (
                  <p className="text-xs text-gray-600">{item.resolution.decision?.replaceAll('_', ' ')} by {item.resolution.actor_id} on {formatDate(item.resolution.recorded_at)}. Evidence: {item.resolution.evidence_note}</p>
                )}
              </li>
            ))}
          </ul>
          <div className="flex items-center justify-between text-xs text-gray-600">
            <span>{total} total</span>
            <div className="flex gap-2">
              <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)} className="rounded-lg border border-gray-300 px-3 py-1.5 disabled:opacity-50">Previous</button>
              <button type="button" disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => setPage(page + 1)} className="rounded-lg border border-gray-300 px-3 py-1.5 disabled:opacity-50">Next</button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
