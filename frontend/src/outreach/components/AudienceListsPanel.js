import React, { useEffect, useRef, useState } from 'react';
import AudienceListImport, { audienceRequest, validAudience } from './AudienceListImport';

const button = 'rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm disabled:opacity-50';
const field = 'rounded-lg border border-gray-200 bg-white p-2 text-sm';
const validPage = (page, row) => validAudience(page?.list) && page.list.id === row.id && page.list.campaign_id === row.campaign_id
  && page.list.review_digest === row.review_digest && Array.isArray(page.members) && page.members.length <= 50
  && Number.isInteger(page.membership_count) && page.membership_count >= page.members.length
  && page.membership_controls_execution === false && page.complete_collection === false
  && (page.next_cursor === null || (typeof page.next_cursor === 'string' && /^[0-9a-f]{64}$/.test(page.next_cursor)))
  && page.members.every((member) => member && typeof member.lead_id === 'string' && typeof member.id === 'string'
    && ['available', 'orphaned', 'source_review'].includes(member.status)
    && (member.status === 'orphaned' ? member.contact === null : member.contact && typeof member.contact === 'object'));

export default function AudienceListsPanel({ campaigns, initialCampaignId, selectedLeadIds = [], onClose, onChanged }) {
  const [campaign, setCampaign] = useState(initialCampaignId || campaigns[0]?.id || '');
  const [inventory, setInventory] = useState(null);
  const [selected, setSelected] = useState('');
  const [page, setPage] = useState(null);
  const [after, setAfter] = useState(null);
  const [name, setName] = useState('');
  const [rename, setRename] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [importing, setImporting] = useState(null);
  const generation = useRef(0);
  const creation = useRef(null);
  const row = inventory?.find((item) => item.id === selected);
  useEffect(() => {
    const controller = new AbortController(); ++generation.current;
    setLoading(true); setInventory(null); setPage(null); setError(''); setAfter(null); setBusy(false);
    if (!campaign) { setLoading(false); return undefined; }
    audienceRequest(`?campaign_id=${encodeURIComponent(campaign)}&include_archived=true`, undefined, undefined, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        if (!Array.isArray(data.lists) || data.lists.some((item) => !validAudience(item) || item.campaign_id !== campaign)
            || data.membership_controls_execution !== false) throw new Error('Could not confirm this audience catalog.');
        setInventory(data.lists); setSelected((value) => data.lists.some((item) => item.id === value) ? value : data.lists[0]?.id || '');
      }).catch((failure) => { if (!controller.signal.aborted) setError(failure.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { controller.abort(); ++generation.current; };
  }, [campaign, reload]);
  useEffect(() => {
    const controller = new AbortController(); setPage(null); setRename(row?.name || '');
    if (!row) return undefined;
    audienceRequest(`/${row.id}/members?limit=50${after ? `&after=${after}` : ''}`, undefined, undefined, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        if (!validPage(data, row)) throw new Error('Audience changed or its members could not be confirmed. Refresh lists.');
        setPage(data);
      }).catch((failure) => { if (!controller.signal.aborted) setError(failure.message); });
    return () => controller.abort();
  }, [row, after]);
  const mutate = async (path, body, method = 'POST') => {
    const version = generation.current; setBusy(true); setError(''); setPage(null);
    try {
      await audienceRequest(path, body, method);
      if (generation.current === version) { setAfter(null); setReload((n) => n + 1); onChanged?.(); }
    } catch (failure) {
      if (generation.current === version) { setError(`${failure.message} Refresh lists before making another change.`); setInventory(null); }
    } finally { if (generation.current === version) setBusy(false); }
  };
  const create = async () => {
    if (!creation.current) {
      if (typeof window.crypto?.randomUUID !== 'function') { setError('This browser cannot create a recoverable list request.'); return; }
      creation.current = { campaign_id: campaign, name: name.trim(), request_id: window.crypto.randomUUID() };
    }
    const body = creation.current;
    const version = generation.current; setBusy(true); setError('');
    try {
      const created = await audienceRequest('', body);
      if (!validAudience(created) || created.campaign_id !== body.campaign_id) throw new Error('Could not confirm the created audience list.');
      creation.current = null;
      if (version === generation.current) { setName(''); setSelected(created.id); setReload((n) => n + 1); }
    } catch (failure) { if (version === generation.current) {
      if ([409, 422].includes(failure.status)) { creation.current = null; setError(`${failure.message} Review the list name and current catalog before creating another.`); }
      else setError(`${failure.message} Retry the original list request or refresh lists.`);
    } }
    finally { if (version === generation.current) setBusy(false); }
  };
  const revision = row && { revision: row.revision, review_digest: row.review_digest };
  const disabled = busy || loading || !row || !page || row.archived;
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-label="Audience lists">
    <div className="max-h-[90vh] w-full max-w-3xl space-y-4 overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
      <div className="flex items-start justify-between gap-4"><div><h2 className="text-xl font-semibold">Audience lists</h2>
        <p className="mt-1 text-sm text-gray-500">Organize campaign contacts. Removing or archiving membership does not stop outreach or delete contacts.</p></div>
        <button className={button} onClick={onClose}>Close lists</button></div>
      {importing ? <AudienceListImport key={importing.id} audience={importing} onClose={() => { setImporting(null); setReload((n) => n + 1); }} onImported={(result) => onChanged?.(result)} /> : <>
        <label className="block text-sm">Campaign <select aria-label="Audience campaign" className={field} value={campaign} disabled={busy || !!creation.current} onChange={(e) => { setSelected(''); setAfter(null); setCampaign(e.target.value); }}>
          {!campaigns.length && <option value="">Create a campaign first</option>}{campaigns.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        <div className="flex flex-wrap gap-2"><input aria-label="New audience list name" className={field} maxLength={60} placeholder="New list name" value={name} disabled={busy || !!creation.current} onChange={(e) => setName(e.target.value)} />
          <button className={button} disabled={busy || loading || !campaign || (!creation.current && (!name.trim() || !inventory))} onClick={create}>{creation.current ? 'Retry original list request' : 'Create list'}</button>
          <button className={button} disabled={busy} onClick={() => setReload((n) => n + 1)}>Refresh lists</button></div>
        {loading && <p role="status">Loading audience lists…</p>}
        {inventory?.length === 0 && <p>No audience lists yet. Existing campaign contacts are unchanged.</p>}
        {!!inventory?.length && <label className="block text-sm">List <select aria-label="Audience list" className={field} value={selected} disabled={busy} onChange={(e) => { setSelected(e.target.value); setAfter(null); }}>
          {inventory.map((item) => <option key={item.id} value={item.id}>{item.name}{item.archived ? ' (archived)' : ''}</option>)}</select></label>}
        {row && <>
          <p className="text-sm text-gray-500">{row.source_kind === 'legacy_unknown' ? 'Historical source unknown' : 'Manually organized'} · Collection completeness unverified</p>
          {row.archived && <p>This list is archived. Its contacts and outreach are unchanged.</p>}
          <div className="flex flex-wrap gap-2"><input aria-label="Rename audience list" maxLength={60} className={field} value={rename} disabled={disabled} onChange={(e) => setRename(e.target.value)} />
            <button className={button} disabled={disabled || !rename.trim()} onClick={() => mutate(`/${row.id}`, { ...revision, name: rename.trim() }, 'PATCH')}>Rename list</button>
            <button className={button} disabled={disabled} onClick={() => mutate(`/${row.id}/archive`, revision)}>Archive list</button>
            <button className={button} disabled={disabled} onClick={() => setImporting(row)}>Import into list</button>
            <button className={button} disabled={disabled || !selectedLeadIds.length || selectedLeadIds.length > 100} onClick={() => mutate(`/${row.id}/members`, { ...revision, lead_ids: selectedLeadIds, operation: 'add' })}>Add selected contacts ({selectedLeadIds.length})</button></div>
          <p className="text-xs text-gray-500">Selected contacts must all belong to this campaign. A membership can be available while execution remains blocked.</p>
          {!page && <p role="status">Members are unavailable until this page is confirmed.</p>}
          {page && <><p className="text-sm">{page.membership_count} stored memberships</p>
            {!page.members.length && <p>No memberships on this page.</p>}
            <ul className="divide-y">{page.members.map((member) => <li key={member.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span>{member.contact ? `${member.contact.first_name || 'Unnamed'} ${member.contact.last_name || ''}` : 'Contact unavailable'}<span className="ml-2 text-xs text-gray-500">{member.status === 'available' ? 'Recorded contact' : member.status === 'source_review' ? 'Source review required' : 'Orphaned membership'}</span></span>
              <button className={button} disabled={disabled} onClick={() => mutate(`/${row.id}/members`, { ...revision, lead_ids: [member.lead_id], operation: 'remove' })}>Remove membership</button></li>)}</ul>
            <div className="flex gap-2"><button className={button} disabled={busy || !after} onClick={() => setAfter(null)}>First members page</button>
              <button className={button} disabled={busy || !page.next_cursor} onClick={() => setAfter(page.next_cursor)}>Next members page</button></div></>}
        </>}
      </>}
    </div>
  </div>;
}
