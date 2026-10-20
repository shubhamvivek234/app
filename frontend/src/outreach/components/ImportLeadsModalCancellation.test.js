import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ImportLeadsModal from './ImportLeadsModal';
const response = (data, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => data });
describe('Search cancellation confirmation and recovery', () => {
  let root; let container; let job; let cancel;
  const button = (text) => [...container.querySelectorAll('button')].find((value) => value.textContent.includes(text));
  beforeEach(async () => {
    jest.useFakeTimers(); global.IS_REACT_ACT_ENVIRONMENT = true; sessionStorage.clear();
    sessionStorage.setItem('unravler.search-job.campaign', 'job');
    job = { id: 'job', campaign_id: 'campaign', status: 'crawling', target_count: 100 };
    cancel = async () => response({ detail: 'Cancellation rejected' }, 403);
    global.fetch = jest.fn(async (url) => {
      // Synthetic enabled contract isolates historical batching/cancel mechanics.
      // Product-disabled collection is covered separately by the source tests.
      if (url.endsWith('/import-sources')) return response({ contract_version: 1,
        sources: [{ type: 'basic', parser_supported: true, collection_available: true, reason: '' }] });
      if (url.endsWith('/cancel')) return cancel();
      if (url.endsWith('/import-jobs/job')) return response(job);
      return response([]);
    });
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" />));
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); sessionStorage.clear(); jest.useRealTimers(); delete global.fetch; });
  it.each([403, 409, 500])('keeps observing the server after cancellation HTTP %s', async (status) => {
    cancel = async () => response({ detail: 'Cancellation rejected' }, status);
    await act(async () => button('Stop Crawl').click());
    expect(container.textContent).toContain('Cancellation rejected');
    expect(container.textContent).not.toContain('Search Extraction Stopped');
    expect(button('Stop Crawl')).toBeTruthy();
    const reads = global.fetch.mock.calls.length;
    await act(async () => jest.advanceTimersByTime(2000));
    expect(global.fetch.mock.calls.length).toBeGreaterThan(reads);
  });
  it('does not infer stop from a network failure', async () => {
    cancel = async () => { throw new Error('Synthetic lost response'); };
    await act(async () => button('Stop Crawl').click());
    expect(container.textContent).not.toContain('Search Extraction Stopped'); expect(button('Stop Crawl')).toBeTruthy();
  });
  it('waits for the current server record after an accepted cancellation', async () => {
    let resolve; cancel = () => new Promise((done) => { resolve = done; });
    await act(async () => button('Stop Crawl').click());
    expect(button('Requesting stop').disabled).toBe(true);
    await act(async () => resolve(response({ status: 'stopped' })));
    expect(container.textContent).not.toContain('Search Extraction Stopped');
    expect(container.textContent).toContain('Cancellation is not confirmed yet');
    job = { ...job, status: 'stopped', stop_reason: 'cancelled' };
    await act(async () => jest.advanceTimersByTime(2000));
    expect(container.textContent).toContain('Search Extraction Stopped'); expect(button('Stop Crawl')).toBeUndefined();
  });
  it('recovers the current job when the importer is reopened', async () => {
    await act(async () => root.render(<ImportLeadsModal isOpen={false} campaignId="campaign" />));
    job = { ...job, status: 'completed' };
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" />));
    expect(container.textContent).toContain('Search Lead Extraction Completed');
    expect(global.fetch.mock.calls.some(([url]) => url.endsWith('/import-jobs/job'))).toBe(true);
  });
  it('keeps a confirmed stop when an earlier crawling read arrives late', async () => {
    let finishEarlierRead;
    const earlierJob = { ...job };
    global.fetch.mockImplementationOnce(() => new Promise((done) => { finishEarlierRead = done; }));
    await act(async () => jest.advanceTimersByTime(2000));
    cancel = async () => { job = { ...job, status: 'stopped' }; return response({ status: 'stopped' }); };
    await act(async () => button('Stop Crawl').click());
    expect(container.textContent).toContain('Search Extraction Stopped');
    await act(async () => finishEarlierRead(response(earlierJob)));
    expect(container.textContent).toContain('Search Extraction Stopped');
    expect(button('Stop Crawl')).toBeUndefined();
  });
  it('keeps a confirmed stop when a reopening recovery read arrives late', async () => {
    await act(async () => root.render(<ImportLeadsModal isOpen={false} campaignId="campaign" />));
    let finishRecovery;
    const earlierJob = { ...job };
    global.fetch.mockImplementationOnce(() => new Promise((done) => { finishRecovery = done; }));
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" />));
    await act(async () => jest.advanceTimersByTime(2000));
    cancel = async () => { job = { ...job, status: 'stopped' }; return response({ status: 'stopped' }); };
    await act(async () => button('Stop Crawl').click());
    expect(container.textContent).toContain('Search Extraction Stopped');
    await act(async () => finishRecovery(response(earlierJob)));
    expect(container.textContent).toContain('Search Extraction Stopped');
    expect(button('Stop Crawl')).toBeUndefined();
  });
  it.each(['none', 'http', 'network'])('commits reviewed search rows in bounded batches; later failure=%s', async (failure) => {
    const rows = Array.from({ length: 1001 }, (_, index) => ({ id: String(index), first_name: 'Person', linkedin_url: `https://linkedin.com/in/person-${index}` }));
    const commits = [];
    job = { ...job, status: 'completed', leads_imported: 1001 };
    global.fetch.mockImplementation(async (url, options) => {
      if (url.endsWith('/staged')) return response({ leads: rows });
      if (url.endsWith('/commit')) {
        const payload = JSON.parse(options.body); commits.push(payload);
        if (failure === 'network' && commits.length === 2) throw new Error('Synthetic lost response');
        if (failure === 'http' && commits.length === 2) return response({ detail: 'Campaign now warming up' }, 409);
        return response({ enrolled_count: payload.selected_lead_ids.length, rejections: [] });
      }
      return response(job);
    });
    await act(async () => jest.advanceTimersByTime(2000));
    await act(async () => button('Review 1001').click());
    await act(async () => button('Confirm & Ingest').click());
    expect(commits.map((payload) => payload.selected_lead_ids.length)).toEqual([1000, 1]);
    expect(new Set(commits.flatMap((payload) => payload.selected_lead_ids)).size).toBe(1001);
    if (failure !== 'none') {
      expect(container.textContent).toContain('Some rows may already be saved');
      expect(container.textContent).not.toContain('Lead Intake Complete');
    } else expect(container.textContent).toContain('1001 leads saved in this attempt');
  });

  it.each(['Edited name', ''])('keeps staged-search edits on the job commit contract, including explicit name %p', async (name) => {
    let committed;
    job = { ...job, status: 'completed', leads_imported: 1 };
    global.fetch.mockImplementation(async (url, options) => {
      if (url.endsWith('/staged')) return response({ leads: [{ id: 'lead-1', first_name: 'Original', linkedin_url: 'https://linkedin.com/in/synthetic' }] });
      if (url.endsWith('/commit')) { committed = JSON.parse(options.body); return response({ enrolled_count: 1 }); }
      return response(job);
    });
    await act(async () => jest.advanceTimersByTime(2000));
    await act(async () => button('Review 1').click());
    const input = container.querySelector('input[aria-label="First name for lead #1"]');
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, name);
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(button('Validate Changes')).toBeUndefined();
    expect(button('Confirm & Ingest').disabled).toBe(false);
    await act(async () => button('Confirm & Ingest').click());
    expect(committed.name_overrides).toEqual({ 'lead-1': name });
  });

  it('does not continue an earlier batch after the modal closes and reopens', async () => {
    const rows = Array.from({ length: 1001 }, (_, index) => ({ id: String(index), first_name: 'Person' }));
    let resolveFirst;
    let commits = 0;
    job = { ...job, status: 'completed', leads_imported: 1001 };
    global.fetch.mockImplementation(async (url) => {
      if (url.endsWith('/staged')) return response({ leads: rows });
      if (url.endsWith('/commit')) { commits += 1; return new Promise((resolve) => { resolveFirst = resolve; }); }
      return response(job);
    });
    await act(async () => jest.advanceTimersByTime(2000));
    await act(async () => button('Review 1001').click());
    await act(async () => button('Confirm & Ingest').click());
    await act(async () => root.render(<ImportLeadsModal isOpen={false} campaignId="campaign" />));
    await act(async () => root.render(<ImportLeadsModal isOpen campaignId="campaign" />));
    await act(async () => resolveFirst(response({ enrolled_count: 1000, rejections: [] })));
    expect(commits).toBe(1);
    expect(container.textContent).not.toContain('Lead Intake Complete');
  });

});
