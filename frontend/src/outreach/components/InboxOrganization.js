import React, { useEffect, useRef, useState } from 'react';
import { Archive, ArchiveRestore, Star } from 'lucide-react';

const valid = (value) => value?.editable === true && Number.isSafeInteger(value.revision)
  && value.revision >= 0 && typeof value.review_digest === 'string' && /^[a-f0-9]{64}$/.test(value.review_digest)
  && typeof value.identity_digest === 'string' && /^[a-f0-9]{64}$/.test(value.identity_digest)
  && typeof value.note === 'string' && value.note.length <= 8000 && Array.from(value.note).length <= 4000
  && typeof value.is_starred === 'boolean' && typeof value.is_archived === 'boolean';

export default function InboxOrganization({ thread, request, onSaved }) {
  const organization = thread?.organization;
  const identity = valid(organization) ? organization.identity_digest : null;
  const [drafts, setDrafts] = useState({});
  const [pending, setPending] = useState({});
  const [errors, setErrors] = useState({});
  const mounted = useRef(true);
  const draft = drafts[identity];
  const note = draft?.text ?? organization?.note ?? '';
  const busy = Boolean(pending[identity]);
  const held = Boolean(errors[identity]);
  const stale = draft && draft.base !== organization?.review_digest;
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const save = async (changes) => {
    if (!identity || busy || held) return;
    const captured = { ...organization };
    const capturedEdit = draft?.editRevision;
    setPending((previous) => ({ ...previous, [identity]: true }));
    setErrors((previous) => ({ ...previous, [identity]: '' }));
    try {
      const response = await request(`/api/v1/outreach/inbox/${encodeURIComponent(thread.id)}/organization`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revision: captured.revision, review_digest: captured.review_digest, ...changes }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not save conversation organization.');
      if (data.thread_id !== thread.id || !valid(data.organization)
          || data.organization.identity_digest !== identity || data.organization.revision !== captured.revision + 1
          || !Object.entries(changes).every(([field, value]) => data.organization[field] === value)) {
        throw new Error('Could not confirm the organization change. Reload the conversation.');
      }
      if (!mounted.current) return;
      setDrafts((previous) => {
        const saved = previous[identity];
        if (!saved) return previous;
        // Preserve an edit made while a previous save was in flight.
        if ('note' in changes && saved.text === changes.note && saved.base === captured.review_digest
            && saved.editRevision === capturedEdit) {
          const next = { ...previous }; delete next[identity]; return next;
        }
        return saved.base === captured.review_digest
          ? { ...previous, [identity]: { ...saved, base: data.organization.review_digest } } : previous;
      });
      onSaved(thread, data.organization);
    } catch (error) {
      if (mounted.current) setErrors((previous) => ({ ...previous, [identity]: error.message || 'Save unconfirmed. Reload before retrying.' }));
    } finally {
      if (mounted.current) setPending((previous) => ({ ...previous, [identity]: false }));
    }
  };

  const reload = async () => {
    if (busy) return;
    setPending((previous) => ({ ...previous, [identity]: true }));
    try {
      const response = await request(`/api/v1/outreach/inbox/${encodeURIComponent(thread.id)}`);
      const data = await response.json();
      if (!response.ok || data.id !== thread.id || !valid(data.organization)
          || data.organization.identity_digest !== identity) throw new Error('Conversation changed or access is unavailable. Select it again.');
      if (!mounted.current) return;
      onSaved(thread, data.organization);
      setErrors((previous) => ({ ...previous, [identity]: '' }));
    } catch (error) {
      if (mounted.current) setErrors((previous) => ({ ...previous, [identity]: error.message || 'Could not reload the conversation.' }));
    } finally {
      if (mounted.current) setPending((previous) => ({ ...previous, [identity]: false }));
    }
  };

  if (!thread) return null;
  if (!identity) return <p className="border-b px-6 py-2 text-xs text-amber-800">Conversation organization needs review. Reload the conversation or contact support.</p>;
  return (
    <div className="shrink-0 border-b border-gray-200 px-6 py-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" aria-pressed={organization.is_starred} disabled={busy || held}
          onClick={() => save({ is_starred: !organization.is_starred })}
          className="inline-flex items-center gap-1 rounded-lg border px-2 py-1.5 disabled:opacity-50">
          <Star className={`h-3.5 w-3.5 ${organization.is_starred ? 'fill-amber-400 text-amber-600' : ''}`} />
          {organization.is_starred ? 'Unstar conversation' : 'Star conversation'}
        </button>
        <button type="button" disabled={busy || held} onClick={() => save({ is_archived: !organization.is_archived })}
          className="inline-flex items-center gap-1 rounded-lg border px-2 py-1.5 disabled:opacity-50">
          {organization.is_archived ? <ArchiveRestore className="h-3.5 w-3.5" /> : <Archive className="h-3.5 w-3.5" />}
          {organization.is_archived ? 'Move to inbox' : 'Archive conversation'}
        </button>
        <span className="text-gray-500">Shared with your workspace. Archive only changes this inbox view.</span>
      </div>
      <details className="mt-2">
        <summary className="cursor-pointer font-medium text-gray-700">Conversation note{draft && note !== organization.note ? ' · unsaved changes' : organization.note ? ' · saved' : ''}</summary>
        <label className="mt-2 block text-gray-600" htmlFor="conversation-note">Workspace note · never sent to the prospect</label>
        <textarea id="conversation-note" aria-label="Conversation note" maxLength={4000} value={note}
          onChange={(event) => {
            const text = event.target.value;
            setDrafts((previous) => {
              if (!previous[identity] && Object.keys(previous).length >= 50) return previous;
              return { ...previous, [identity]: { text, base: previous[identity]?.base ?? organization.review_digest,
                editRevision: (previous[identity]?.editRevision ?? 0) + 1 } };
            });
          }} className="mt-1 w-full rounded-lg border border-gray-200 p-2" rows={2} />
        {Object.keys(drafts).length >= 50 && !draft && <p role="alert">Save or reload an earlier note draft before adding another.</p>}
        {stale && <p role="alert" className="text-amber-800">This conversation changed. Reload it, then review your unsaved note before saving.</p>}
        <div className="mt-2 flex items-center gap-2">
          <button type="button" disabled={busy || held || stale || !draft || note === organization.note}
            onClick={() => save({ note })} className="rounded-lg border px-3 py-1.5 disabled:opacity-50">Save note</button>
          {draft && <button type="button" disabled={busy} onClick={() => setDrafts((previous) => {
            const next = { ...previous }; delete next[identity]; return next;
          })} className="text-gray-600 underline">Use saved note</button>}
          {stale && <button type="button" disabled={busy || held} onClick={() => setDrafts((previous) => ({
            ...previous, [identity]: { ...previous[identity], base: organization.review_digest },
          }))} className="text-gray-600 underline">Keep my draft for this version</button>}
          <span className="text-gray-500">{note.length}/4,000</span>
        </div>
      </details>
      {errors[identity] && <p role="alert" className="mt-2 text-red-700">{errors[identity]} Reload the conversation before another save.</p>}
      <button type="button" disabled={busy} onClick={reload} className="mt-2 text-gray-600 underline">Reload conversation</button>
    </div>
  );
}
