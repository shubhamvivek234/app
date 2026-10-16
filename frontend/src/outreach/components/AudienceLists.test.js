import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import AudienceListsPanel from './AudienceListsPanel';
import AudienceListImport from './AudienceListImport';
const SCOPE = 'b'.repeat(64), ID = '00000000-0000-4000-8000-000000000001';
const LIST = { id: `list_${'a'.repeat(64)}`, campaign_id: 'campaign', name: 'Prospects', revision: 1, review_digest: 'c'.repeat(64), archived: false, collection_verified: false, source_kind: 'manual' };
const ok = (data) => ({ ok: true, json: async () => data });
const page = (row = LIST) => ({ list: row, members: [], membership_count: 0, next_cursor: null, membership_controls_execution: false, complete_collection: false });
const preview = () => ({ list: LIST, request_scope: SCOPE, rows: [{ row_number: 1, linkedin_url: 'https://www.linkedin.com/in/one', first_name: 'One', status: 'valid' }], more_rows_in_source: true });
const receipt = (status = 'completed') => ({ request_id: ID, request_scope: SCOPE, status, list_name: 'Original prospects', campaign_id: 'campaign', result: status === 'completed' ? { imported_count: 1, skipped_count: 0, duplicates_count: 0, membership_added_count: 1, requested_rows: 1, considered_rows: 1, list_revision: 2, lead_ids: ['l1'], row_results: [{ row_number: 1, status: 'imported', lead_id: 'l1' }], more_rows_in_source: true, collection_verified: false } : null });
const change = async (el, value) => act(async () => {
  const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value); el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
});
const KEY = 'unravler.audience-imports.v1';
const saveRef = () => sessionStorage.setItem(KEY, JSON.stringify({ [SCOPE]: { request_id: ID, request_scope: SCOPE } }));
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };

describe('Audience lists and recoverable import review', () => {
  let container, root;
  beforeEach(() => { global.IS_REACT_ACT_ENVIRONMENT = true; localStorage.clear(); sessionStorage.clear(); container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); Object.defineProperty(window, 'crypto', { configurable: true, value: { randomUUID: () => ID } }); });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.restoreAllMocks(); delete global.fetch; });
  const button = (text) => [...container.querySelectorAll('button')].find((el) => el.textContent === text);
  const renderImport = async (onImported = jest.fn()) => act(async () => root.render(<AudienceListImport audience={LIST} onImported={onImported} />));
  const review = async () => { await change(container.querySelector('[aria-label="Audience import text"]'), 'https://www.linkedin.com/in/one'); await change(container.querySelector('[aria-label="Audience requested rows"]'), '1'); await act(async () => button('Review input rows').click()); };
  const importFetch = (handler) => jest.fn(async (url, opts) => url.endsWith('/import-context') ? ok({ request_scope: SCOPE }) : url.endsWith('/import-preview') ? ok(preview()) : handler(url, opts));
  const renderPanel = async (props = {}) => act(async () => root.render(<AudienceListsPanel campaigns={[{ id: 'campaign', name: 'Campaign' }, { id: 'other', name: 'Other' }]} {...props} />));

  it('shows orphaned membership and explains that membership does not stop sends', async () => {
    global.fetch = jest.fn(async (url) => url.includes('/members') ? ok({ ...page(), membership_count: 1, members: [{ id: 'd'.repeat(64), lead_id: 'gone', status: 'orphaned', contact: null }] }) : ok({ lists: [LIST], membership_controls_execution: false }));
    await renderPanel(); expect(container.textContent).toContain('Contact unavailable'); expect(container.textContent).toContain('does not stop outreach');
  });
  it('binds rename and membership to the reviewed native token', async () => {
    let current = LIST;
    global.fetch = jest.fn(async (url, opts) => { if (opts.method === 'PATCH') { current = { ...LIST, name: 'Renamed', revision: 2, review_digest: 'e'.repeat(64) }; return ok(current); } if (opts.method === 'POST') return ok({ modified_count: 1 }); return url.includes('/members') ? ok(page(current)) : ok({ lists: [current], membership_controls_execution: false }); });
    await renderPanel({ selectedLeadIds: ['l1'] }); await change(container.querySelector('[aria-label="Rename audience list"]'), 'Renamed'); await act(async () => button('Rename list').click());
    const renamed = global.fetch.mock.calls.find(([, opts]) => opts.method === 'PATCH'); expect(JSON.parse(renamed[1].body)).toEqual({ revision: 1, review_digest: LIST.review_digest, name: 'Renamed' });
    await act(async () => button('Add selected contacts (1)').click()); const members = global.fetch.mock.calls.find(([url, opts]) => opts.method === 'POST' && url.endsWith('/members')); expect(JSON.parse(members[1].body)).toEqual({ revision: 2, review_digest: 'e'.repeat(64), lead_ids: ['l1'], operation: 'add' });
  });
  it('retries a lost list-create request with its exact UUID and name', async () => {
    let calls = 0; global.fetch = jest.fn(async (url, opts) => { if (opts.method === 'POST') { if (++calls === 1) throw new Error('lost'); return ok(LIST); } return ok({ lists: [], membership_controls_execution: false }); });
    await renderPanel(); await change(container.querySelector('[aria-label="New audience list name"]'), 'Prospects'); await act(async () => button('Create list').click()); expect(container.querySelector('[aria-label="Audience campaign"]').disabled).toBe(true);
    await act(async () => button('Retry original list request').click()); const bodies = global.fetch.mock.calls.filter(([, opts]) => opts.method === 'POST').map(([, opts]) => opts.body); expect(bodies[0]).toBe(bodies[1]);
  });
  it('disables writes when the member page revision changed', async () => {
    global.fetch = jest.fn(async (url) => url.includes('/members') ? ok(page({ ...LIST, review_digest: 'e'.repeat(64) })) : ok({ lists: [LIST], membership_controls_execution: false })); await renderPanel(); expect(container.querySelector('[role="alert"]').textContent).toContain('Audience changed'); expect(button('Archive list').disabled).toBe(true);
  });
  it('ignores an old catalog response after changing campaigns', async () => {
    const old = deferred(); global.fetch = jest.fn(async (url) => url.includes('campaign_id=campaign') ? old.promise : ok({ lists: [], membership_controls_execution: false })); await renderPanel(); await change(container.querySelector('[aria-label="Audience campaign"]'), 'other'); await act(async () => old.resolve(ok({ lists: [LIST], membership_controls_execution: false }))); expect(container.textContent).not.toContain('Prospects'); expect(container.textContent).toContain('No audience lists yet');
  });
  it('sends original source plus name overrides and stores only a reference before POST', async () => {
    let stored, body; global.fetch = importFetch(async (url, opts) => { stored = sessionStorage.getItem(KEY); body = JSON.parse(opts.body); return ok(receipt()); }); await renderImport(); await review(); await change(container.querySelector('[aria-label="Audience first name row 1"]'), 'Edited'); await act(async () => button('Import reviewed rows').click()); expect(body.raw_text).toBe('https://www.linkedin.com/in/one'); expect(body.name_overrides).toEqual({ '1': 'Edited' }); expect(body.review_digest).toBe(LIST.review_digest); expect(stored).not.toContain('linkedin.com'); expect(stored).not.toContain('Edited'); expect(JSON.parse(sessionStorage.getItem(KEY))).toEqual({}); expect(container.textContent).toContain('More input rows remain');
  });
  it('keeps lost imports held on 404 and cancels the original reference', async () => {
    global.fetch = importFetch(async (url) => { if (url.endsWith('/import')) throw new Error('lost response'); if (url.endsWith('/cancel')) return ok(receipt('cancelled')); return { ok: false, json: async () => ({ detail: 'No saved status is available yet' }) }; }); await renderImport(); await review(); await act(async () => button('Import reviewed rows').click()); await act(async () => button('Check original import').click()); expect(container.textContent).toContain('original import is unresolved'); expect(sessionStorage.getItem(KEY)).toContain(ID); await act(async () => button('Cancel original import').click()); expect(container.textContent).toContain('Original import cancelled'); expect(global.fetch.mock.calls.filter(([url]) => url.endsWith('/import'))).toHaveLength(1);
  });
  it('recovers completed imports after remount without another POST', async () => {
    saveRef(); const imported = jest.fn(); global.fetch = importFetch(async () => ok(receipt())); await renderImport(imported); expect(imported).toHaveBeenCalledTimes(1); expect(container.textContent).toContain('Saved to Original prospects: 1 contacts'); expect(global.fetch.mock.calls.some(([url]) => url.endsWith('/import'))).toBe(false);
  });
  it('shows completion when it wins against cancellation', async () => {
    saveRef(); let calls = 0; global.fetch = importFetch(async () => ok(++calls === 1 ? receipt('pending') : receipt())); await renderImport(); await act(async () => button('Cancel original import').click()); expect(container.textContent).toContain('Saved to Original prospects'); expect(container.textContent).not.toContain('Original import cancelled');
  });
  it('does not let a stale pending response undo confirmed cancellation', async () => {
    const submit = deferred(); global.fetch = importFetch(async (url) => url.endsWith('/cancel') ? ok(receipt('cancelled')) : submit.promise); await renderImport(); await review(); await act(async () => { button('Import reviewed rows').click(); }); await act(async () => button('Cancel original import').click()); await act(async () => submit.resolve(ok(receipt('pending')))); expect(container.textContent).toContain('Original import cancelled'); expect(container.textContent).not.toContain('original import is unresolved');
  });
  it('holds malformed success without fabricating completion', async () => {
    saveRef(); global.fetch = importFetch(async () => ok({ ...receipt(), result: { imported_count: 1 } })); await renderImport(); expect(container.textContent).toContain('Import evidence could not be confirmed'); expect(container.textContent).toContain('original import is unresolved'); expect(sessionStorage.getItem(KEY)).toContain(ID);
  });
  it('blocks fresh import when saved references are malformed', async () => {
    sessionStorage.setItem(KEY, '[]'); global.fetch = importFetch(async () => { throw new Error('unexpected'); }); await renderImport(); expect(container.textContent).toContain('Saved request references need review'); expect(button('Review input rows').disabled).toBe(true);
  });
  it('invalidates review when original quantity changes', async () => {
    global.fetch = importFetch(async () => ok(receipt())); await renderImport(); await review(); expect(button('Import reviewed rows')).toBeDefined(); await change(container.querySelector('[aria-label="Audience requested rows"]'), '2'); expect(button('Import reviewed rows')).toBeUndefined();
  });
  it('holds review while a newly selected CSV is still being read', async () => {
    let reader;
    jest.spyOn(window, 'FileReader').mockImplementation(() => { reader = { readAsText: jest.fn() }; return reader; });
    global.fetch = importFetch(async () => ok(receipt())); await renderImport();
    await change(container.querySelector('[aria-label="Audience import format"]'), 'csv');
    await change(container.querySelector('[aria-label="Audience import text"]'), 'linkedin_url,first_name\nold,Old');
    const input = container.querySelector('[aria-label="Audience CSV file"]');
    Object.defineProperty(input, 'files', { configurable: true, value: [new File(['new'], 'new.csv')] });
    await act(async () => input.dispatchEvent(new Event('change', { bubbles: true })));
    expect(button('Review input rows').disabled).toBe(true);
    expect(container.querySelector('[aria-label="Audience import text"]').value).toBe('');
    await act(async () => { reader.result = 'linkedin_url,first_name\nnew,New'; reader.onload(); });
    expect(button('Review input rows').disabled).toBe(false);
    expect(container.querySelector('[aria-label="Audience import text"]').value).toContain('new,New');
  });
  it('retains a completion arriving after close so reopening can present it', async () => {
    const submit = deferred(); global.fetch = importFetch(async (url) => url.endsWith('/import') ? submit.promise : ok(receipt()));
    await renderImport(); await review(); await act(async () => { button('Import reviewed rows').click(); });
    await act(async () => root.unmount()); await act(async () => submit.resolve(ok(receipt())));
    expect(sessionStorage.getItem(KEY)).toContain(ID);
    root = createRoot(container); await renderImport();
    expect(container.textContent).toContain('Saved to Original prospects');
    expect(JSON.parse(sessionStorage.getItem(KEY))).toEqual({});
  });
  it('unlocks the list form after a confirmed pre-write name rejection', async () => {
    global.fetch = jest.fn(async (url, opts) => opts.method === 'POST'
      ? { ok: false, status: 409, json: async () => ({ detail: 'Name already exists' }) }
      : ok({ lists: [], membership_controls_execution: false }));
    await renderPanel(); await change(container.querySelector('[aria-label="New audience list name"]'), 'Prospects');
    await act(async () => button('Create list').click());
    expect(container.querySelector('[aria-label="New audience list name"]').disabled).toBe(false);
    expect(container.textContent).toContain('Name already exists');
    expect(button('Retry original list request')).toBeUndefined();
  });

});
