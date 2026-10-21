import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ImportLeadsModal from './ImportLeadsModal';

const reply = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
const initial = { contract_version: 1, workspace_id: 'w', campaign_id: 'campaign', scope_digest: 'a'.repeat(64) };
const row = { row_number: 1, first_name: 'Old Private', cleaned_first_name: 'Old Private', status: 'valid' };
const preview = { total_submitted: 1, valid_count: 1, duplicate_count: 0, contacted_count: 0, dnc_count: 0, invalid_count: 0, rows: [row] };

describe('importer current server context', () => {
  let root; let container; let current; let contextStatus; let pending; let imported;
  const button = (text) => [...container.querySelectorAll('button')].find((b) => b.textContent.includes(text));
  const change = async (element, text) => act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(element, text);
    element.dispatchEvent(new Event('change', { bubbles: true }));
  });
  const open = async () => {
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" onLeadsImported={imported} />));
    await act(async () => button('Paste LinkedIn profile URLs').click());
    await change(container.querySelector('textarea'), 'https://linkedin.com/in/private, Private');
  };
  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true; localStorage.clear(); sessionStorage.clear();
    localStorage.setItem('token', 'unchanged-browser-token');
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    current = { ...initial }; contextStatus = 200; imported = jest.fn();
    global.fetch = jest.fn(async (url) => {
      if (url.includes('/import-context?')) return reply(current, contextStatus);
      if (url.endsWith('/accounts')) return reply([]);
      if (url.endsWith('/import-sources')) return reply({ contract_version: 1, sources: [{ type: 'basic', collection_available: false, parser_supported: true, reason: 'Unavailable' }] });
      if (url.endsWith('/preview')) return reply({ ...preview, import_context: initial });
      if (url.endsWith('/import-urls')) return pending ? pending() : reply({ imported_count: 1, import_context: initial });
      throw new Error(url);
    });
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.restoreAllMocks(); delete global.fetch; });

  it.each(['workspace', 'uid-or-native'])('blocks earlier review before a mutation when same-token %s changes', async (changeKind) => {
    await open(); await act(async () => button('Validate & Preview').click());
    current = { ...initial, scope_digest: 'b'.repeat(64), ...(changeKind === 'workspace' ? { workspace_id: 'other' } : {}) };
    await act(async () => button('Confirm & Ingest').click());
    expect(global.fetch.mock.calls.some(([url]) => url.endsWith('/import-urls'))).toBe(false);
    expect(container.textContent).toContain('could not be confirmed');
    expect(imported).not.toHaveBeenCalled();
  });
  it('holds an earlier successful response when the current server scope changes during import', async () => {
    await open(); await act(async () => button('Validate & Preview').click());
    let finish; pending = () => new Promise((resolve) => { finish = resolve; });
    await act(async () => button('Confirm & Ingest').click());
    current = { ...initial, scope_digest: 'b'.repeat(64) };
    await act(async () => finish(reply({ imported_count: 1, import_context: initial })));
    expect(imported).not.toHaveBeenCalled(); expect(container.textContent).not.toContain('Lead Intake Complete');
    expect(container.textContent).toContain('Some rows may already be saved');
  });
  it.each([403, 503])('keeps inputs unavailable when bootstrap HTTP %s cannot confirm current scope', async (status) => {
    contextStatus = status;
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" />));
    expect(container.querySelector('textarea')).toBeNull();
    expect(container.textContent).toContain('could not be confirmed');
    expect(global.fetch.mock.calls.every(([url]) => url.includes('/import-context?'))).toBe(true);
  });
  it('discards an earlier file completion when the server UID changes with the same token', async () => {
    let reader;
    jest.spyOn(global, 'FileReader').mockImplementation(() => (reader = { readAsText() {} }));
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" />));
    await act(async () => button('Import from CSV').click());
    const file = container.querySelector('input[type="file"]');
    Object.defineProperty(file, 'files', { value: [new File(['private'], 'private.csv')] });
    await act(async () => file.dispatchEvent(new Event('change', { bubbles: true })));
    current = { ...initial, scope_digest: 'b'.repeat(64) };
    await act(async () => reader.onload({ target: { result: 'old-private-file' } }));
    expect(container.querySelector('textarea')).toBeNull();
    expect(container.textContent).toContain('could not be confirmed');
  });
  it('keeps a mismatch held after current scope returns to its earlier value', async () => {
    await open(); current = { ...initial, scope_digest: 'b'.repeat(64) };
    await act(async () => window.dispatchEvent(new Event('focus')));
    current = { ...initial };
    await act(async () => window.dispatchEvent(new Event('focus')));
    expect(container.querySelector('textarea')).toBeNull();
    expect(container.textContent).toContain('could not be confirmed');
    expect(imported).not.toHaveBeenCalled();
  });
});
