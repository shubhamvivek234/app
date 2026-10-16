import React, { useCallback, useEffect, useState } from 'react';
import { Plus, RefreshCw, Save, Trash2 } from 'lucide-react';
import { toast } from 'sonner';

const headers = () => {
  const token = localStorage.getItem('token');
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
};

const detail = async (response, fallback) => {
  const body = await response.json().catch(() => ({}));
  return typeof body.detail === 'string' ? body.detail : fallback;
};

export default function LeadTagManager({ onChanged }) {
  const [tags, setTags] = useState([]);
  const [name, setName] = useState('');
  const [color, setColor] = useState('#6366f1');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [importCursor, setImportCursor] = useState('');
  const [importResult, setImportResult] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setLoadError('');
    try {
      const response = await fetch('/api/v1/outreach/leads/tags', { credentials: 'include', headers: headers() });
      if (!response.ok) throw new Error(await detail(response, 'Could not load tags'));
      const data = await response.json();
      if (!Array.isArray(data)) throw new Error('Could not load tags');
      setTags(data);
    } catch (error) {
      setTags([]); setLoadError(error.message || 'Could not load tags');
      toast.error(error.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = async (event) => {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      const response = await fetch('/api/v1/outreach/leads/tags', {
        method: 'POST', credentials: 'include', headers: headers(),
        body: JSON.stringify({ name: name.trim(), color }),
      });
      if (!response.ok) throw new Error(await detail(response, 'Could not create tag'));
      setName('');
      await load();
      onChanged?.();
      toast.success('Tag created');
    } catch (error) {
      toast.error(error.message);
    } finally {
      setBusy(false);
    }
  };

  const save = async (tag) => {
    setBusy(true);
    try {
      const response = await fetch(`/api/v1/outreach/leads/tags/${tag.id}`, {
        method: 'PATCH', credentials: 'include', headers: headers(),
        body: JSON.stringify({ name: tag.name, color: tag.color, revision: tag.revision }),
      });
      if (!response.ok) throw new Error(await detail(response, 'Could not update tag'));
      await load();
      onChanged?.();
      toast.success('Tag updated everywhere');
    } catch (error) {
      toast.error(error.message);
    } finally {
      setBusy(false);
    }
  };

  const archive = async (tag) => {
    if (!window.confirm(`Archive “${tag.name}”? It will be hidden from leads and filters.`)) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/v1/outreach/leads/tags/${tag.id}?revision=${tag.revision}`, {
        method: 'DELETE', credentials: 'include', headers: headers(),
      });
      if (!response.ok) throw new Error(await detail(response, 'Could not archive tag'));
      await load();
      onChanged?.();
      toast.success('Tag archived');
    } catch (error) {
      toast.error(error.message);
    } finally {
      setBusy(false);
    }
  };

  const importLegacy = async () => {
    setBusy(true);
    try {
      const response = await fetch(`/api/v1/outreach/leads/tags/import-legacy?after_id=${encodeURIComponent(importCursor)}`, { method: 'POST', credentials: 'include', headers: headers() });
      if (!response.ok) throw new Error(await detail(response, 'Could not import older Inbox labels'));
      const result = await response.json();
      setImportResult(result);
      setImportCursor(result.has_more ? result.next_after_id : '');
      await load();
      onChanged?.();
    } catch (error) {
      toast.error(error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-xs space-y-5">
      <div>
        <h2 className="text-base font-bold text-gray-900">Lead tags</h2>
        <p className="mt-1 text-xs text-gray-500">Names and colors update across Leads, campaigns, Inbox, and CSV exports.</p>
      </div>
      <form onSubmit={create} className="flex flex-wrap items-center gap-2">
        <input aria-label="New tag color" type="color" value={color} onChange={(event) => setColor(event.target.value)} className="h-9 w-10 rounded-lg border border-gray-200 p-1" />
        <input aria-label="New tag name" value={name} onChange={(event) => setName(event.target.value)} maxLength={60} placeholder="New tag name" className="min-w-48 flex-1 rounded-xl border border-gray-200 px-3 py-2 text-xs" />
        <button disabled={busy || !name.trim()} className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"><Plus className="h-3.5 w-3.5" />Create</button>
      </form>
      <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 space-y-2 text-xs text-gray-600">
        <p>Import older Inbox labels onto their linked CRM leads. Unlinked conversations and labels that need review stay intact.</p>
        <button type="button" disabled={busy} onClick={importLegacy} className="font-semibold text-indigo-700 disabled:opacity-50">{importResult?.has_more ? 'Import next batch of conversations' : 'Import older Inbox labels'}</button>
        {importResult && <p role="status">{importResult.migrated_threads} conversations imported; {importResult.skipped.length} need review.{importResult.has_more ? ' More conversations remain.' : ' Scan complete.'}</p>}
      </div>
      {loading ? <RefreshCw className="h-5 w-5 animate-spin text-gray-400" /> : loadError ? (
        <div role="alert" className="rounded-xl bg-red-50 p-4 text-xs text-red-700"><p>{loadError}</p><button type="button" onClick={load} className="mt-2 font-semibold">Retry loading tags</button></div>
      ) : tags.length === 0 ? (
        <p className="rounded-xl bg-gray-50 p-4 text-xs text-gray-500">No tags yet. Create one to classify leads by interest, priority, or follow-up stage.</p>
      ) : (
        <div className="divide-y divide-gray-100 rounded-xl border border-gray-200">
          {tags.map((tag) => (
            <div key={tag.id} className="flex flex-wrap items-center gap-2 p-3">
              <input aria-label={`Color for ${tag.name}`} type="color" value={tag.color} onChange={(event) => setTags((current) => current.map((item) => item.id === tag.id ? { ...item, color: event.target.value } : item))} className="h-8 w-9 rounded border-0 p-0" />
              <input aria-label={`Name for ${tag.name}`} value={tag.name} maxLength={60} onChange={(event) => setTags((current) => current.map((item) => item.id === tag.id ? { ...item, name: event.target.value } : item))} className="min-w-40 flex-1 rounded-lg border border-gray-200 px-3 py-1.5 text-xs" />
              <button type="button" disabled={busy || !tag.name.trim()} onClick={() => save(tag)} title="Save tag" className="rounded-lg p-2 text-indigo-600 hover:bg-indigo-50 disabled:opacity-50"><Save className="h-4 w-4" /></button>
              <button type="button" disabled={busy} onClick={() => archive(tag)} title="Archive tag" className="rounded-lg p-2 text-gray-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
