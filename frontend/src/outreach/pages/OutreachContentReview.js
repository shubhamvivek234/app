import React, { useCallback, useEffect, useState } from 'react';

const API = '/api/v1/outreach/content-approvals';
const SIZE = 25;
const labels = { send_message: 'Message', connection_request: 'Connection invitation', voice_note: 'Voice note', send_email: 'Email', comment: 'Comment', inbox_reply: 'Inbox reply', like: 'Like' };

async function request(path, options = {}) {
  const token = localStorage.getItem('token');
  const response = await fetch(path, { ...options, credentials: 'include', headers: { Authorization: token ? `Bearer ${token}` : '', ...options.headers } });
  if (!response.ok) {
    const value = await response.json().catch(() => ({}));
    throw new Error(typeof value.detail === 'string' ? value.detail : 'Content review could not be completed.');
  }
  return response;
}

function VoicePreview({ id, onHeard }) {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await request(`${API}/${encodeURIComponent(id)}/audio`);
      setUrl(URL.createObjectURL(await response.blob()));
    } catch (failure) { setError(failure.message); }
    finally { setLoading(false); }
  };
  return <div className="mt-3">
    {url ? <audio aria-label="Prepared voice preview" controls src={url} onEnded={onHeard} /> : <button type="button" disabled={loading} onClick={load} className="rounded border px-3 py-2 text-sm">{loading ? 'Loading preview…' : 'Load voice preview'}</button>}
    {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
  </div>;
}

export default function OutreachContentReview() {
  const [view, setView] = useState('pending');
  const [page, setPage] = useState(0);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [campaigns, setCampaigns] = useState([]);
  const [campaign, setCampaign] = useState('');
  const [checked, setChecked] = useState({});
  const [heard, setHeard] = useState({});
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const value = await (await request(`${API}?view=${view}&skip=${page * SIZE}&limit=${SIZE}`)).json();
      setItems(value.items || []);
      setTotal(value.total || 0);
    } catch (failure) { setError(failure.message); }
    finally { setLoading(false); }
  }, [view, page]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    let active = true;
    request('/api/v1/outreach/campaigns/').then((response) => response.json()).then((value) => {
      if (active) setCampaigns(Array.isArray(value) ? value : []);
    }).catch((failure) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, []);
  const decide = async (item, decision) => {
    setBusy(true); setError(''); setNotice('');
    try {
      await request(`${API}/${encodeURIComponent(item.id)}/decision`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, revision: item.revision, reviewed: Boolean(checked[item.id]) }) });
      setChecked({}); setHeard({});
      setNotice(decision === 'approve' ? 'Content approved for 24 hours. Sender and campaign checks still apply.' : 'Decision recorded.');
      await load();
    } catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  };
  const prepare = async () => {
    if (!campaign) return;
    setBusy(true); setError(''); setNotice('');
    try {
      let skip = 0; let prepared = 0; let voice = 0; let queued = 0; let held = 0; let unavailable = 0;
      do {
        const result = await (await request(`${API}/prepare/${encodeURIComponent(campaign)}?skip=${skip}&limit=50`, { method: 'POST' })).json();
        prepared += result.prepared; voice += result.voice_pending;
        queued += result.voice_queued || 0; held += result.voice_held || 0; unavailable += result.voice_unavailable || 0;
        skip = result.next_skip;
      } while (skip !== null && skip !== undefined);
      setNotice(`${prepared} current steps prepared for review.${queued ? ` ${queued} voice clips queued or preparing. Refresh reviews when ready.` : ''}${held ? ` ${held} generation outcomes need operator review; preparation will not repeat them.` : ''}${unavailable ? ` ${unavailable} voice clips cannot be prepared. Check voice setup, paid access, and preparation availability.` : ''}${voice && !queued && !held && !unavailable ? ` ${voice} voice clips still need preparation.` : ''}`);
      setView('pending'); setPage(0); await load();
    } catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  };
  const cancel = async (item) => {
    setBusy(true); setError('');
    try {
      await request(`${API}/${encodeURIComponent(item.id)}/cancel`, { method: 'POST' });
      setNotice('Pending action cancelled. Completed stages remain in its history.'); await load();
    } catch (failure) { setError(failure.message); }
    finally { setBusy(false); }
  };
  return <section aria-label="Content reviews" className="space-y-5">
    <div><h2 className="text-base font-bold text-gray-900">Content reviews</h2>
      <p className="mt-1 text-sm text-gray-600">Review the exact recipient and personalized content before campaign messages can send. Changes to the content, sender, or campaign require a new review.</p>
      <p className="mt-2 text-xs text-gray-600">Approving content does not enable live sending or resume a campaign. Manual Send, Comment, and Like clicks record your exact choice here.</p></div>
    <p className="text-xs text-gray-600">When campaign voice preparation is enabled, preparing voice steps uses your configured voice provider credits. Listen to each finished recording before approving it.</p>
    <div className="flex flex-wrap gap-2">
      <select aria-label="Campaign to prepare" value={campaign} onChange={(event) => setCampaign(event.target.value)} className="rounded border p-2 text-sm"><option value="">Choose campaign</option>{campaigns.map((item) => <option key={item.id} value={item.id}>{item.name || item.id}</option>)}</select>
      <button type="button" disabled={!campaign || busy} onClick={prepare} className="rounded border px-3 py-2 text-sm disabled:opacity-50">Prepare current steps</button>
      <button type="button" disabled={busy || loading} onClick={load} className="rounded border px-3 py-2 text-sm disabled:opacity-50">Refresh reviews</button>
      <button type="button" onClick={() => { setView('pending'); setPage(0); }} aria-pressed={view === 'pending'} className="rounded border px-3 py-2 text-sm">Needs review</button>
      <button type="button" onClick={() => { setView('history'); setPage(0); }} aria-pressed={view === 'history'} className="rounded border px-3 py-2 text-sm">Review history</button>
    </div>
    {error && <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
    {notice && <p role="status" className="text-sm text-green-800">{notice}</p>}
    {loading ? <p className="text-sm">Loading content reviews…</p> : !items.length ? <p className="text-sm text-gray-600">No content reviews in this view. Prepare the assigned current steps of a campaign to review them.</p> : items.map((item) => <article key={`${item.id}:${item.revision}`} className="rounded-xl border border-gray-200 p-4">
      <h3 className="font-semibold">{labels[item.action] || 'Outreach action'} · {item.status}</h3>
      <p className="mt-1 break-all text-sm">From {item.sender_name || item.sender_id} · To {item.recipient}</p>
      {item.content.sender_email && <p className="mt-1 break-all text-sm">Sending mailbox: {item.content.sender_email}</p>}
      {item.content.subject && <p className="mt-3 text-sm font-semibold">{item.content.subject}</p>}
      {item.content.body !== undefined && <p className="mt-3 whitespace-pre-wrap break-words text-sm">{item.content.body || '(No invitation note)'}</p>}
      {item.content.reaction && <p className="mt-3 text-sm">Reaction: {item.content.reaction}</p>}
      {item.content.auto_like && <p className="mt-2 text-sm">Also like this post before commenting.</p>}
      {item.has_audio && <VoicePreview key={`${item.id}:${item.revision}`} id={item.id} onHeard={() => setHeard((value) => ({ ...value, [item.id]: true }))} />}
      {item.reviewed_by && <p className="mt-2 text-xs text-gray-600">Reviewed by {item.reviewed_by}{item.expires_at ? ` · Valid until ${new Date(item.expires_at).toLocaleString()}` : ''}</p>}
      {!item.current && <p className="mt-3 text-sm text-amber-800">This review is no longer current. Prepare the current campaign step, or cancel a pending manual action and review it again.</p>}
      {item.current && <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(checked[item.id])} disabled={item.has_audio && !heard[item.id]} onChange={(event) => setChecked((value) => ({ ...value, [item.id]: event.target.checked }))} />I reviewed the recipient and exact content{item.has_audio ? ', and listened to the full clip' : ''}.</label>}
      <div className="mt-3 flex flex-wrap gap-2">
        {item.current && <button type="button" disabled={busy || !checked[item.id]} onClick={() => decide(item, 'approve')} className="rounded bg-gray-900 px-3 py-2 text-sm text-white disabled:opacity-50">Approve content</button>}
        {item.status === 'pending' && <button type="button" disabled={busy} onClick={() => decide(item, 'reject')} className="rounded border px-3 py-2 text-sm">Reject</button>}
        {item.status === 'approved' && <button type="button" disabled={busy} onClick={() => decide(item, 'revoke')} className="rounded border px-3 py-2 text-sm">Revoke approval</button>}
        {item.can_cancel && <button type="button" disabled={busy} onClick={() => cancel(item)} className="rounded border px-3 py-2 text-sm">Cancel pending action</button>}
      </div>
    </article>)}
    <div className="flex items-center gap-3 text-sm"><button type="button" disabled={!page || busy} onClick={() => setPage(page - 1)}>Previous</button><span>{total} reviews · Page {page + 1}</span><button type="button" disabled={(page + 1) * SIZE >= total || busy} onClick={() => setPage(page + 1)}>Next</button></div>
  </section>;
}
