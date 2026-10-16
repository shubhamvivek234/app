import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { toast } from 'sonner';
import LeadTagManager from './LeadTagManager';
import LeadSelectionReview from './LeadSelectionReview';
import OutreachLeads from '../pages/OutreachLeads';

jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
const TAG = { id: `tag_${'a'.repeat(24)}`, name: 'Qualified', color: '#123456', revision: 3 };
const ok = (body) => ({ ok: true, status: 200, json: async () => body });
const fail = (detail, status = 409) => ({ ok: false, status, json: async () => ({ detail }) });
const withContext = (handler) => (url, options) => url.endsWith('/selection/context')
  ? Promise.resolve(ok({ request_scope: 'b'.repeat(64) })) : handler(url, options);
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };
const change = async (element, value) => act(async () => {
  const prototype = element.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(prototype, 'value').set.call(element, value);
  element.dispatchEvent(new Event(element.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
});

describe('Canonical lead tags and reviewed draft controls', () => {
  let container; let root;
  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true; jest.clearAllMocks(); localStorage.clear(); sessionStorage.clear();
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    Object.defineProperty(window, 'crypto', { configurable: true, value: { randomUUID: () => '00000000-0000-4000-8000-000000000001' } });
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.restoreAllMocks(); delete global.fetch; });
  const button = (text) => [...container.querySelectorAll('button')].find((item) => item.textContent === text);

  it('shares the tag filter with CSV export and sends only selected IDs in bulk', async () => {
    localStorage.setItem('outreach_leads_view_mode', 'table');
    URL.createObjectURL = jest.fn(() => 'blob:test'); URL.revokeObjectURL = jest.fn();
    jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    global.fetch = jest.fn(async (url) => {
      if (url === '/api/v1/outreach/leads/tags') return ok([TAG]);
      if (url === '/api/v1/outreach/campaigns') return ok([]);
      if (url.includes('/leads/export?')) return { ok: true, blob: async () => new Blob(['tags\nQualified']) };
      if (url === '/api/v1/outreach/leads/tags/bulk') return ok({ matched_count: 1, modified_count: 1 });
      if (url.includes('/leads?')) return ok({ total: 2, leads: [{ id: 'l1', first_name: 'Alex', tags: [TAG] }, { id: 'l2', first_name: 'Sam', tags: [] }] });
      throw new Error(`Unexpected ${url}`);
    });
    await act(async () => root.render(<OutreachLeads />));
    await change(container.querySelector('[aria-label="Filter leads by tag"]'), TAG.id);
    await act(async () => button('Export CSV').click());
    expect(global.fetch.mock.calls.some(([url]) => url.includes(`/leads/export?tag_ids=${TAG.id}`))).toBe(true);
    await act(async () => container.querySelector('[aria-label="Select Alex"]').click());
    await act(async () => button('Add tag').click());
    expect(global.fetch).toHaveBeenCalledWith('/api/v1/outreach/leads/tags/bulk', expect.objectContaining({ body: JSON.stringify({ lead_ids: ['l1'], tag_id: TAG.id, operation: 'add' }) }));
    expect(container.textContent).not.toContain('1 selected');
  });

  it('preserves bulk selection when the server rejects the mutation', async () => {
    global.fetch = jest.fn(async (url) => {
      if (url === '/api/v1/outreach/leads/tags') return ok([TAG]);
      if (url === '/api/v1/outreach/campaigns') return ok([]);
      if (url === '/api/v1/outreach/leads/tags/bulk') return fail('One or more leads were not found');
      return ok({ total: 1, leads: [{ id: 'l1', first_name: 'Alex', tags: [] }] });
    });
    await act(async () => root.render(<OutreachLeads />));
    await act(async () => container.querySelector('[aria-label="Select Alex"]').click());
    await act(async () => button('Add tag').click());
    expect(container.textContent).toContain('1 selected');
    expect(container.querySelector('[role="alert"]').textContent).toContain('One or more leads were not found');
  });

  it('uses the definition revision and surfaces stale edits without claiming success', async () => {
    global.fetch = jest.fn(async (url, options = {}) => options.method === 'PATCH' ? fail('Tag changed; reload before editing again') : ok([TAG]));
    await act(async () => root.render(<LeadTagManager />));
    await change(container.querySelector('[aria-label="Name for Qualified"]'), 'Ready');
    await act(async () => container.querySelector('[title="Save tag"]').click());
    expect(JSON.parse(global.fetch.mock.calls.find(([, options]) => options.method === 'PATCH')[1].body)).toEqual({ name: 'Ready', color: TAG.color, revision: 3 });
    expect(toast.error).toHaveBeenCalledWith('Tag changed; reload before editing again');
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('ignores an older follow-up preview after the inclusion rule changes', async () => {
    const first = deferred();
    global.fetch = jest.fn(withContext((url, options) => JSON.parse(options.body).allow_contacted ? Promise.resolve(ok({ valid_count: 1, excluded_count: 0, request_scope: 'b'.repeat(64), review_digest: 'new', rows: [] })) : first.promise));
    await act(async () => root.render(<LeadSelectionReview leadIds={['l1']} />));
    await act(async () => container.querySelector('input[type="checkbox"]').click());
    expect(container.textContent).toContain('1 eligible');
    await act(async () => first.resolve(ok({ valid_count: 0, excluded_count: 1, request_scope: 'b'.repeat(64), review_digest: 'old', rows: [] })));
    expect(container.textContent).toContain('1 eligible');
    expect(button('Create draft & configure').disabled).toBe(false);
  });

  it('retries the same draft request after acknowledgement loss and never calls launch', async () => {
    const created = jest.fn(); let attempts = 0;
    global.fetch = jest.fn(withContext(async (url) => {
      if (url.endsWith('/preview')) return ok({ valid_count: 1, excluded_count: 0, request_scope: 'b'.repeat(64), review_digest: 'a'.repeat(64), rows: [] });
      attempts += 1;
      if (attempts === 1) throw new Error('Response lost; retry the same request');
      return ok({ campaign_id: 'draft', name: 'Follow-up', imported_count: 1 });
    }));
    await act(async () => root.render(<LeadSelectionReview leadIds={['l1']} onCreated={created} />));
    await act(async () => button('Create draft & configure').click());
    expect(container.querySelector('[aria-label="Follow-up campaign name"]').disabled).toBe(true);
    await act(async () => button('Retry same draft request').click());
    const calls = global.fetch.mock.calls.filter(([url]) => url.endsWith('/draft'));
    expect(calls).toHaveLength(2); expect(calls[0][1].body).toBe(calls[1][1].body);
    expect(created).toHaveBeenCalledWith(expect.objectContaining({ campaign_id: 'draft' }));
    expect(global.fetch.mock.calls.some(([url]) => /launch|resume/.test(url))).toBe(false);
  });

  it('clears a rejected follow-up preview and requires another review', async () => {
    global.fetch = jest.fn(withContext(async (url) => url.endsWith('/draft') ? fail('Selected leads or exclusions changed') : ok({ valid_count: 1, excluded_count: 0, request_scope: 'b'.repeat(64), review_digest: 'a'.repeat(64), rows: [] })));
    await act(async () => root.render(<LeadSelectionReview leadIds={['l1']} />));
    await act(async () => button('Create draft & configure').click());
    expect(container.textContent).toContain('Selected leads or exclusions changed');
    expect(button('Create draft & configure').disabled).toBe(true);
    await act(async () => button('Review again').click());
    expect(button('Create draft & configure').disabled).toBe(false);
  });

  it('recovers the same unresolved request after closing and remounting', async () => {
    let submitted;
    global.fetch = jest.fn(withContext(async (url, options) => {
      if (url.endsWith('/preview')) return ok({ request_scope: 'b'.repeat(64), valid_count: 1, excluded_count: 0, review_digest: 'a'.repeat(64), rows: [] });
      submitted = options.body;
      throw new Error('Acknowledgement lost');
    }));
    await act(async () => root.render(<LeadSelectionReview leadIds={['l1']} />));
    await act(async () => button('Create draft & configure').click());
    const originalRequest = submitted;
    await act(async () => root.unmount()); root = createRoot(container);
    const created = jest.fn();
    global.fetch.mockImplementation(withContext(async (url, options) => {
      if (url.endsWith('/preview')) return fail('Source lead deleted', 404);
      expect(options.body).toBe(originalRequest);
      return ok({ campaign_id: 'original-draft' });
    }));
    await act(async () => root.render(<LeadSelectionReview leadIds={['l2']} onCreated={created} />));
    expect(container.textContent).toContain('An earlier draft request for 1 leads needs confirmation');
    await act(async () => button('Retry same draft request').click());
    expect(created).toHaveBeenCalledWith({ campaign_id: 'original-draft' });
    expect(sessionStorage.getItem('unravler.leads.draft-requests.v1')).toBe('{}');
  });

  it('clears a terminal deleted-draft hold so a new review is possible', async () => {
    sessionStorage.setItem('unravler.leads.draft-requests.v1', JSON.stringify({ ['b'.repeat(64)]: {
      lead_ids: ['l1'], allow_contacted: false, name: 'Deleted draft',
      request_id: '00000000-0000-4000-8000-000000000001', review_digest: 'a'.repeat(64),
    } }));
    global.fetch = jest.fn(withContext(async (url) => url.endsWith('/draft') ? fail('This follow-up draft was deleted; start a new review', 410) : ok({ request_scope: 'b'.repeat(64), valid_count: 1, excluded_count: 0, review_digest: 'c'.repeat(64), rows: [] })));
    await act(async () => root.render(<LeadSelectionReview leadIds={['l2']} />));
    await act(async () => button('Retry same draft request').click());
    expect(sessionStorage.getItem('unravler.leads.draft-requests.v1')).toBe('{}');
    expect(container.querySelector('[aria-label="Follow-up campaign name"]').disabled).toBe(false);
    await act(async () => button('Review again').click());
    expect(button('Create draft & configure').disabled).toBe(false);
  });

  it('retains the original unresolved request when workspace changes before submission', async () => {
    global.fetch = jest.fn(withContext(async (url) => url.endsWith('/draft') ? fail('Workspace changed. Return to the original workspace', 403)
      : ok({ request_scope: 'b'.repeat(64), valid_count: 1, excluded_count: 0, review_digest: 'a'.repeat(64), rows: [] })));
    await act(async () => root.render(<LeadSelectionReview leadIds={['l1']} />));
    await act(async () => button('Create draft & configure').click());
    expect(JSON.parse(global.fetch.mock.calls.find(([url]) => url.endsWith('/draft'))[1].body).request_scope).toBe('b'.repeat(64));
    expect(JSON.parse(sessionStorage.getItem('unravler.leads.draft-requests.v1'))['b'.repeat(64)]).toBeDefined();
    expect(button('Retry same draft request').disabled).toBe(false);
  });

  it.each(['oversized', 'corrupt'])('preserves %s recovery data and prevents a new draft', async (kind) => {
    const original = kind === 'oversized' ? JSON.stringify({ data: 'x'.repeat(100001) }) : '{broken';
    sessionStorage.setItem('unravler.leads.draft-requests.v1', original);
    global.fetch = jest.fn(withContext(async () => ok({ request_scope: 'b'.repeat(64), valid_count: 1, excluded_count: 0, review_digest: 'a'.repeat(64), rows: [] })));
    await act(async () => root.render(<LeadSelectionReview leadIds={['l1']} />));
    expect(container.querySelector('[role="alert"]').textContent).toMatch(/recovery|earlier draft/i);
    expect(button('Create draft & configure').disabled).toBe(true);
    expect(sessionStorage.getItem('unravler.leads.draft-requests.v1')).toBe(original);
  });

  it('does not overwrite existing holds when another valid request exceeds the storage bound', async () => {
    const large = (scope) => ({ lead_ids: Array.from({ length: 200 }, (_, index) => `${index}`.padEnd(200, 'x')), allow_contacted: false,
      name: 'Follow-up', request_id: '00000000-0000-4000-8000-000000000001', review_digest: 'a'.repeat(64), request_scope: scope });
    const original = JSON.stringify({ ['c'.repeat(64)]: large('c'.repeat(64)), ['d'.repeat(64)]: large('d'.repeat(64)) });
    sessionStorage.setItem('unravler.leads.draft-requests.v1', original);
    global.fetch = jest.fn(withContext(async () => ok({ request_scope: 'b'.repeat(64), valid_count: 200, excluded_count: 0, review_digest: 'a'.repeat(64), rows: [] })));
    await act(async () => root.render(<LeadSelectionReview leadIds={large('b'.repeat(64)).lead_ids} />));
    await act(async () => button('Create draft & configure').click());
    expect(global.fetch.mock.calls.some(([url]) => url.endsWith('/draft'))).toBe(false);
    expect(sessionStorage.getItem('unravler.leads.draft-requests.v1')).toBe(original);
    expect(container.querySelector('[role="alert"]').textContent).toMatch(/earlier draft/);
  });

  it('refreshes the current filter after a pending bulk mutation completes', async () => {
    const bulk = deferred();
    global.fetch = jest.fn(async (url) => {
      if (url.endsWith('/leads/tags')) return ok([TAG]);
      if (url.endsWith('/campaigns')) return ok([]);
      if (url.endsWith('/tags/bulk')) return bulk.promise;
      return ok({ total: 1, leads: [{ id: 'l1', first_name: url.includes('untagged=true') ? 'Current filter' : 'Old filter', tags: [] }] });
    });
    await act(async () => root.render(<OutreachLeads />));
    await act(async () => container.querySelector('[aria-label="Select Old filter"]').click());
    await act(async () => button('Add tag').click());
    await change(container.querySelector('[aria-label="Filter leads by tag"]'), '__untagged__');
    await act(async () => bulk.resolve(ok({ modified_count: 1 })));
    expect(global.fetch.mock.calls.filter(([url]) => url.includes('/leads?')).at(-1)[0]).toContain('untagged=true');
    expect(container.textContent).toContain('Current filter');
    expect(container.textContent).not.toContain('Old filter');
  });

  it('ignores a delayed old-filter response even if the transport ignores abort', async () => {
    const first = deferred();
    global.fetch = jest.fn(async (url) => {
      if (url.endsWith('/leads/tags')) return ok([TAG]);
      if (url.endsWith('/campaigns')) return ok([]);
      if (!url.includes('untagged=true')) return first.promise;
      return ok({ total: 1, leads: [{ id: 'current', first_name: 'Current result', tags: [] }] });
    });
    await act(async () => root.render(<OutreachLeads />));
    await change(container.querySelector('[aria-label="Filter leads by tag"]'), '__untagged__');
    await act(async () => first.resolve(ok({ total: 1, leads: [{ id: 'old', first_name: 'Old result', tags: [] }] })));
    expect(container.textContent).toContain('Current result');
    expect(container.textContent).not.toContain('Old result');
  });

  it('keeps a tag-inventory failure visible after leads finish loading', async () => {
    const pendingLeads = deferred();
    global.fetch = jest.fn(async (url) => {
      if (url.endsWith('/leads/tags')) return fail('Tag inventory unavailable', 503);
      if (url.endsWith('/campaigns')) return ok([]);
      return pendingLeads.promise;
    });
    await act(async () => root.render(<OutreachLeads />));
    await act(async () => pendingLeads.resolve(ok({ total: 1, leads: [{ id: 'l1', first_name: 'Alex', tags: [] }] })));
    expect(container.querySelector('[role="alert"]').textContent).toContain('Tag inventory unavailable');
    expect(button('Retry loading lead tags')).toBeDefined();
  });

  it('never restores another account or workspace request into the current review', async () => {
    const original = JSON.stringify({ ['c'.repeat(64)]: { lead_ids: ['foreign'], name: 'Other workspace', allow_contacted: false,
      request_id: '00000000-0000-4000-8000-000000000001', review_digest: 'a'.repeat(64) } });
    sessionStorage.setItem('unravler.leads.draft-requests.v1', original);
    global.fetch = jest.fn(withContext(async () => ok({ request_scope: 'b'.repeat(64), valid_count: 1, excluded_count: 0, review_digest: 'a'.repeat(64), rows: [] })));
    await act(async () => root.render(<LeadSelectionReview leadIds={['l1']} />));
    expect(container.textContent).not.toContain('An earlier draft request');
    expect(container.querySelector('[aria-label="Follow-up campaign name"]').value).toBe('Follow-up campaign');
    expect(sessionStorage.getItem('unravler.leads.draft-requests.v1')).toBe(original);
  });

  it.each([fail('Tags unavailable', 503), ok({ unexpected: true })])('shows tag inventory failures without a false empty state', async (response) => {
    global.fetch = jest.fn(async () => response);
    await act(async () => root.render(<LeadTagManager />));
    expect(container.querySelector('[role="alert"]')).not.toBeNull();
    expect(container.textContent).not.toContain('No tags yet');
    expect(button('Retry loading tags')).toBeDefined();
  });
});
