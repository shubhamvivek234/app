import { withImportContext } from '../test/importContextFixture';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ImportLeadsModal from './ImportLeadsModal';

const response = (body) => ({ ok: true, status: 200, json: async () => body });
const preview = (rows) => ({ total_submitted: rows.length, valid_count: rows.filter((r) => r.status === 'valid').length,
  duplicate_count: 0, contacted_count: 0, dnc_count: 0, invalid_count: rows.filter((r) => r.status !== 'valid').length, rows });
const row = (name = '') => ({ row_number: 1, linkedin_url: 'https://linkedin.com/in/alice', first_name: name,
  cleaned_first_name: name, raw_first_name: name, location: 'Sydney', status: name ? 'valid' : 'rejected',
  rejection_code: name ? null : 'missing_name', error_reason: name ? null : 'First name is required' });

describe('direct lead intake review parity', () => {
  let container; let root;
  const button = (text) => [...container.querySelectorAll('button')].find((b) => b.textContent.includes(text));
  const change = async (element, value) => act(async () => {
    Object.getOwnPropertyDescriptor(element.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype,
      'value').set.call(element, value);
    element.dispatchEvent(new Event('change', { bubbles: true }));
  });
  const openCsv = async () => {
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" onClose={() => {}} />));
    await act(async () => button('Import from CSV').click());
    jest.spyOn(global, 'FileReader').mockImplementation(() => ({ readAsText() {
      this.onload({ target: { result: 'linkedin_url,first_name,location\nhttps://linkedin.com/in/alice,,Sydney' } });
    } }));
    const file = container.querySelector('input[type="file"]');
    Object.defineProperty(file, 'files', { value: [new File(['csv'], 'contacts.csv', { type: 'text/csv' })] });
    await act(async () => file.dispatchEvent(new Event('change', { bubbles: true })));
    await act(async () => button('Validate & Preview').click());
  };
  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    localStorage.clear(); sessionStorage.clear(); global.fetch = jest.fn(withImportContext());
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.restoreAllMocks(); delete global.fetch; });

  it('propagates the reviewed strict name policy to an unedited CSV confirmation', async () => {
    let saved;
    global.fetch.mockImplementation(withImportContext(async (url, opts) => {
      if (url.endsWith('/accounts')) return response([]);
      if (url.endsWith('/import-sources')) return response({ contract_version: 1, sources: [{ type: 'basic', collection_available: false, parser_supported: true, reason: 'Unavailable' }] });
      if (url.endsWith('/preview')) return response(preview([row('Alice')]));
      if (url.endsWith('/import-csv')) { saved = JSON.parse(opts.body); return response({ imported_count: 1 }); }
      throw new Error(url);
    }));
    await openCsv();
    await act(async () => button('Confirm & Ingest').click());
    expect(saved.require_name).toBe(true);
  });

  it('allows repairing a missing name, rechecks server exclusions and preserves location through staging', async () => {
    let saved; let checked;
    global.fetch.mockImplementation(withImportContext(async (url, opts) => {
      if (url.endsWith('/accounts')) return response([]);
      if (url.endsWith('/import-sources')) return response({ contract_version: 1, sources: [{ type: 'basic', collection_available: false, parser_supported: true, reason: 'Unavailable' }] });
      if (url.endsWith('/preview')) return response(preview([row()]));
      if (url.endsWith('/preview-staged')) {
        checked = JSON.parse(opts.body);
        return response(preview(checked.leads.map((r) => ({ ...r, status: 'valid', rejection_code: null, error_reason: null }))));
      }
      if (url.endsWith('/import-staged')) { saved = JSON.parse(opts.body); return response({ imported_count: 1 }); }
      throw new Error(url);
    }));
    await openCsv();
    const input = container.querySelector('input[aria-label="First name for lead #1"]');
    expect(input).not.toBeNull();
    await change(input, 'Ally');
    expect(button('Confirm & Ingest').disabled).toBe(true);
    await act(async () => button('Validate Changes').click());
    expect(checked.leads[0]).toEqual(expect.objectContaining({ first_name: 'Ally', cleaned_first_name: 'Ally', location: 'Sydney' }));
    expect(button('Confirm & Ingest').textContent).toContain('1 Valid Leads');
    await act(async () => button('Confirm & Ingest').click());
    expect(saved.leads[0]).toEqual(expect.objectContaining({ first_name: 'Ally', location: 'Sydney' }));
    expect(saved.require_name).toBe(true);
  });

  it('does not apply a late source preview after switching the campaign', async () => {
    let finish;
    global.fetch.mockImplementation(withImportContext(async (url) => {
      if (url.endsWith('/accounts')) return response([]);
      if (url.endsWith('/import-sources')) return response({ contract_version: 1, sources: [{ type: 'basic', collection_available: false, parser_supported: true, reason: 'Unavailable' }] });
      if (url.endsWith('/preview')) return new Promise((resolve) => { finish = resolve; });
      throw new Error(url);
    }));
    await openCsv();
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="other-campaign" onClose={() => {}} />));
    await act(async () => finish(response(preview([row('Old Contact')]))));
    expect(container.textContent).toContain('Choose Lead Sourcing Method');
    expect(container.textContent).not.toContain('Old Contact');
  });

  it('does not announce an old import result after the importer closes', async () => {
    let finish; const imported = jest.fn();
    global.fetch.mockImplementation(withImportContext(async (url) => {
      if (url.endsWith('/accounts')) return response([]);
      if (url.endsWith('/import-sources')) return response({ contract_version: 1, sources: [{ type: 'basic', collection_available: false, parser_supported: true, reason: 'Unavailable' }] });
      if (url.endsWith('/preview')) return response(preview([row('Alice')]));
      if (url.endsWith('/import-csv')) return new Promise((resolve) => { finish = resolve; });
      throw new Error(url);
    }));
    await openCsv();
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" onClose={() => {}} onLeadsImported={imported} />));
    await act(async () => button('Confirm & Ingest').click());
    await act(async () => root.render(<ImportLeadsModal isOpen={false} campaignId="campaign" onClose={() => {}} onLeadsImported={imported} />));
    await act(async () => finish(response({ imported_count: 1 })));
    expect(imported).not.toHaveBeenCalled();
  });

  it.each(['preview', 'import-csv'])('holds a late %s response after the sign-in token changes', async (pendingPath) => {
    let finish; const imported = jest.fn();
    localStorage.setItem('token', 'original');
    global.fetch.mockImplementation(withImportContext(async (url) => {
      if (url.endsWith('/accounts')) return response([]);
      if (url.endsWith('/import-sources')) return response({ contract_version: 1, sources: [{ type: 'basic', collection_available: false, parser_supported: true, reason: 'Unavailable' }] });
      if (url.endsWith(`/${pendingPath}`)) return new Promise((resolve) => { finish = resolve; });
      if (url.endsWith('/preview')) return response(preview([row('Alice')]));
      throw new Error(url);
    }));
    await openCsv();
    if (pendingPath === 'import-csv') {
      await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" onLeadsImported={imported} />));
      await act(async () => button('Confirm & Ingest').click());
    }
    localStorage.setItem('token', 'replacement');
    await act(async () => finish(response(pendingPath === 'preview' ? preview([row('Old Contact')]) : { imported_count: 1 })));
    expect(imported).not.toHaveBeenCalled();
    expect(container.textContent).not.toContain('Old Contact');
    expect(container.textContent).not.toContain('Lead Intake Complete');
    expect(container.textContent).toContain('Sign-in changed');
  });

  it('blocks a new import from an earlier review after a same-tab token change', async () => {
    localStorage.setItem('token', 'original');
    global.fetch.mockImplementation(withImportContext(async (url) => {
      if (url.endsWith('/accounts')) return response([]);
      if (url.endsWith('/import-sources')) return response({ contract_version: 1, sources: [{ type: 'basic', collection_available: false, parser_supported: true, reason: 'Unavailable' }] });
      if (url.endsWith('/preview')) return response(preview([row('Alice')]));
      if (url.endsWith('/import-csv')) return response({ imported_count: 1 });
      throw new Error(url);
    }));
    await openCsv();
    localStorage.setItem('token', 'replacement');
    await act(async () => button('Confirm & Ingest').click());
    expect(global.fetch.mock.calls.some(([url]) => url.endsWith('/import-csv'))).toBe(false);
    expect(container.textContent).toContain('Sign-in changed');
  });

  it('holds a file read completed after sign-in changes without exposing its contacts', async () => {
    let reader;
    localStorage.setItem('token', 'original');
    global.fetch.mockImplementation(withImportContext(async () => response([])));
    jest.spyOn(global, 'FileReader').mockImplementation(() => (reader = { readAsText() {} }));
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" />));
    await act(async () => button('Import from CSV').click());
    const file = container.querySelector('input[type="file"]');
    Object.defineProperty(file, 'files', { value: [new File(['secret contacts'], 'contacts.csv')] });
    await act(async () => file.dispatchEvent(new Event('change', { bubbles: true })));
    localStorage.setItem('token', 'replacement');
    await act(async () => reader.onload({ target: { result: 'old private contacts' } }));
    expect(container.textContent).toContain('Sign-in changed');
    expect(container.textContent).not.toContain('old private contacts');
  });

  it('holds on a focus sign-in change and clears earlier inputs on explicit reopen', async () => {
    localStorage.setItem('token', 'original');
    global.fetch.mockImplementation(withImportContext(async () => response([])));
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" />));
    await act(async () => button('Paste LinkedIn profile URLs').click());
    const text = container.querySelector('textarea');
    await change(text, 'https://linkedin.com/in/private-previous');
    localStorage.setItem('token', 'replacement');
    await act(async () => window.dispatchEvent(new Event('focus')));
    expect(container.textContent).toContain('Sign-in changed');
    await act(async () => root.render(<ImportLeadsModal isOpen={false} campaignId="campaign" />));
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" />));
    await act(async () => button('Paste LinkedIn profile URLs').click());
    expect(container.querySelector('textarea').value).toBe('');
  });

  it('keeps an observed sign-in hold when the original token returns before an import finishes', async () => {
    let finish;
    const imported = jest.fn();
    localStorage.setItem('token', 'original');
    global.fetch.mockImplementation(withImportContext(async (url) => {
      if (url.endsWith('/accounts')) return response([]);
      if (url.endsWith('/import-sources')) return response({ contract_version: 1,
        sources: [{ type: 'basic', collection_available: false, parser_supported: true, reason: 'Unavailable' }] });
      if (url.endsWith('/preview')) return response(preview([row('Alice')]));
      if (url.endsWith('/import-csv')) return new Promise((resolve) => { finish = resolve; });
      throw new Error(url);
    }));
    await openCsv();
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" onLeadsImported={imported} />));
    await act(async () => button('Confirm & Ingest').click());
    await act(async () => {
      localStorage.setItem('token', 'replacement');
      window.dispatchEvent(new Event('focus'));
    });
    expect(container.textContent).toContain('Sign-in changed');
    localStorage.setItem('token', 'original');
    await act(async () => finish(response({ imported_count: 1 })));
    expect(imported).not.toHaveBeenCalled();
    expect(container.textContent).toContain('Sign-in changed');
    expect(container.textContent).not.toContain('Lead Intake Complete');
  });
});
