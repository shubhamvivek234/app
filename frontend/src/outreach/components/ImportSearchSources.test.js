import { withImportContext } from '../test/importContextFixture';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ImportLeadsModal from './ImportLeadsModal';

const reply = (body, status = 200) => ({ ok: status === 200, status, json: async () => body });
const unavailable = { contract_version: 1, sources: [{ type: 'basic', parser_supported: true,
  collection_available: false, reason: 'Search filters are not verified. Use CSV or public profile links.' }] };

describe('Truthful search source availability', () => {
  let root; let container;
  const searchButton = () => [...container.querySelectorAll('button')].find((button) => button.textContent.includes('LinkedIn & Sales Nav Search'));
  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true; sessionStorage.clear();
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); sessionStorage.clear(); delete global.fetch; });

  it.each([reply(unavailable), reply({}, 503), reply({ contract_version: 1, sources: [null, unavailable.sources[0]] })])('keeps unavailable or unreadable sources disabled while manual imports work', async (response) => {
    global.fetch = jest.fn(withImportContext(async (url) => url.endsWith('/import-sources') ? response : reply([])));
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" />));
    expect(searchButton().disabled).toBe(true);
    expect(container.textContent).not.toContain('1-Click Infusion');
    const manual = [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Paste LinkedIn profile URLs'));
    expect(manual.disabled).toBe(false);
    await act(async () => manual.click());
    expect(container.textContent).toContain('Paste LinkedIn Profile URLs');
    expect(global.fetch.mock.calls.some(([url]) => url.endsWith('/import-search'))).toBe(false);
  });

  it('preserves saved search inspection and blocks its enrollment', async () => {
    sessionStorage.setItem('unravler.search-job.campaign', 'job');
    global.fetch = jest.fn(withImportContext(async (url) => {
      if (url.endsWith('/import-sources')) return reply(unavailable);
      if (url.endsWith('/import-jobs/job')) return reply({ id: 'job', campaign_id: 'campaign', status: 'completed', leads_imported: 1 });
      if (url.endsWith('/staged')) return reply({ leads: [{ id: 'saved', first_name: 'Saved', linkedin_url: 'https://linkedin.com/in/saved' }] });
      return reply([]);
    }));
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" />));
    expect(container.textContent).toContain('enrollment remains unavailable');
    const inspect = [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Review 1'));
    await act(async () => inspect.click());
    const confirm = [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Confirm & Ingest'));
    expect(confirm.disabled).toBe(true);
    expect(container.textContent).toContain('Saved for review');
    expect(container.textContent).not.toContain('Valid to Enroll');
    expect(global.fetch.mock.calls.some(([url]) => url.endsWith('/commit'))).toBe(false);
  });

  it('ignores an older availability response after campaign changes', async () => {
    let resolveOld;
    global.fetch = jest.fn(withImportContext((url) => {
      if (!url.endsWith('/import-sources')) return Promise.resolve(reply([]));
      if (!resolveOld) return new Promise((done) => { resolveOld = done; });
      return Promise.resolve(reply(unavailable));
    }));
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="first" />));
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="second" />));
    await act(async () => resolveOld(reply({ contract_version: 1, sources: [{ type: 'basic', parser_supported: true, collection_available: true, reason: '' }] })));
    expect(searchButton().disabled).toBe(true);
  });
});
