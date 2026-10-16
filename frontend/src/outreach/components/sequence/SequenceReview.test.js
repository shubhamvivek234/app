import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import SequenceReview from './SequenceReview';
import { flattenTreeToDAG } from './sequenceGraph';
const SCOPE = 'd'.repeat(64);
const ID = '00000000-0000-4000-8000-000000000001';
const TREE = [{ id: 'check', type: 'if_connected', title: 'Connection check', config: {}, branches: { right: { condition: 'connected', steps: [{ id: 'next', type: 'visit_profile', delay_days: 1, config: {} }] } } }];
const ok = (data) => ({ ok: true, json: async () => data });
const result = (request, overrides = {}) => ({ request_id: request.request_id, request_scope: SCOPE, contract_version: 1, valid: true, execution_authorized: false, provider_outcomes_verified: false, input_digest: 'a'.repeat(64), graph_digest: 'b'.repeat(64), issues: [], steps: [{ node_id: 'check', type: 'if_connected', status: 'waiting_for_observation', configured_delay_hours: 0 }], ending: 'waiting_for_observation', configured_delay_hours: 0, assumed_wait_hours: 0, ...overrides });
const change = async (el, value) => act(async () => {
  const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value); el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
});
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };
describe('Supplied-data sequence review', () => {
  let container, root;
  beforeEach(() => { global.IS_REACT_ACT_ENVIRONMENT = true; container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); Object.defineProperty(window, 'crypto', { configurable: true, value: { randomUUID: () => ID } }); });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.restoreAllMocks(); delete global.fetch; });
  const render = async (tree = TREE) => {
    const handler = global.fetch;
    if (!handler.withContext) {
      global.fetch = jest.fn((url, opts) => url.endsWith('/preview-context') ? Promise.resolve(ok({ contract_version: 1, request_scope: SCOPE })) : handler(url, opts));
      global.fetch.withContext = true;
    }
    await act(async () => root.render(<SequenceReview tree={tree} campaignId="campaign" />));
  };
  const run = async () => act(async () => [...container.querySelectorAll('button')].find((el) => el.textContent === 'Validate & preview path').click());
  it('keeps assumptions unknown and actions unconfirmed by default', async () => {
    let sent; global.fetch = jest.fn(async (url, opts) => { sent = JSON.parse(opts.body); return ok(result(sent)); });
    await render(); await run();
    expect(sent).toMatchObject({ tree: TREE, initial_connected: 'unknown', initial_email_available: 'unknown', assume_action_completion: false, observations: {} });
    expect(container.textContent).toContain('Waiting for an observation'); expect(container.textContent).toContain('It sends nothing');
    expect(global.fetch.mock.calls.every(([url]) => url.startsWith('/api/v1/outreach/sequences/preview'))).toBe(true);
  });
  it('binds the graph, sample and explicit observation to one preview request', async () => {
    let sent; global.fetch = jest.fn(async (url, opts) => { sent = JSON.parse(opts.body); return ok(result(sent)); });
    await render(); await change(container.querySelector('[aria-label="Sequence sample first_name"]'), 'Example');
    await change(container.querySelector('[aria-label="Assumed observation check"]'), 'deadline_no');
    await act(async () => container.querySelector('[aria-label="Assume successful action completion"]').click()); await run();
    expect(sent).toMatchObject({ sample: { first_name: 'Example' }, observations: { check: 'deadline_no' }, assume_action_completion: true });
    expect(sent.nodes.find((node) => node.id === 'next').delay_hours).toBe(24);
  });
  it('hides previous validity immediately when a sample changes', async () => {
    global.fetch = jest.fn(async (url, opts) => ok(result(JSON.parse(opts.body)))); await render(); await run();
    expect(container.textContent).toContain('Graph checks passed');
    await change(container.querySelector('[aria-label="Sequence sample company_name"]'), 'Changed');
    expect(container.textContent).not.toContain('Graph checks passed');
  });
  it('ignores a stale response after changing the graph or closing', async () => {
    const pending = deferred(); global.fetch = jest.fn(() => pending.promise); await render(); await run();
    const request = JSON.parse(global.fetch.mock.calls.find(([url]) => url.endsWith('/preview'))[1].body);
    await render([{ id: 'different', type: 'visit_profile', config: {} }]);
    await act(async () => pending.resolve(ok(result(request))));
    expect(container.textContent).not.toContain('Graph checks passed');
  });
  it('rejects an old nonce or a response claiming execution authority', async () => {
    global.fetch = jest.fn(async (url, opts) => ok(result(JSON.parse(opts.body), { execution_authorized: true })));
    await render(); await run(); expect(container.querySelector('[role="alert"]').textContent).toContain('Could not confirm');
    expect(container.textContent).not.toContain('Graph checks passed');
  });
  it('renders invalid and unavailable results without a misleading successful path', async () => {
    global.fetch = jest.fn(async (url, opts) => ok(result(JSON.parse(opts.body), { valid: false, ending: 'invalid_graph', steps: [], issues: [{ node_id: 'check', severity: 'error', message: 'Fix this branch' }] })));
    await render(); await run(); expect(container.textContent).toContain('Sequence needs correction'); expect(container.textContent).toContain('Fix this branch');
    global.fetch = jest.fn(async () => { throw new Error('Network unavailable'); }); await run();
    expect(container.textContent).toContain('Network unavailable'); expect(container.textContent).not.toContain('Fix this branch');
  });
  it('does not round fractional hours or invent missing IDs', () => {
    expect(flattenTreeToDAG([{ id: 'hour', type: 'visit_profile', delay_days: 1 / 24 }]).nodes[0].delay_hours).toBe(1);
    expect(() => flattenTreeToDAG([{ id: 'fraction', type: 'visit_profile', delay_days: .1 }])).toThrow('whole hours');
    expect(() => flattenTreeToDAG([{ type: 'visit_profile' }])).toThrow('valid ID');
  });
  it('rejects malformed custom samples before requesting a preview', async () => {
    global.fetch = jest.fn(); await render(); await change(container.querySelector('[aria-label="Sequence custom sample variables"]'), '[]'); await run();
    expect(container.textContent).toContain('Custom variables must be an object'); expect(global.fetch.mock.calls.some(([url]) => url.endsWith('/preview'))).toBe(false);
  });
  it('binds actual typed field samples, without an assumed field observation or sending permission', async () => {
    let sent; global.fetch = jest.fn(async (url, opts) => { sent = JSON.parse(opts.body); return ok(result(sent, { steps: [{ node_id: 'check', type: 'has_data_in_column', status: 'evaluated_branch', branch: 'positive', configured_delay_hours: 0 }], ending: 'finished' })); });
    const tree = [{ id: 'check', type: 'has_data_in_column', config: { condition_contract_version: 1, field: 'custom_variables.score', operator: 'has_value' } }];
    await render(tree);
    expect(container.querySelector('[aria-label="Assumed observation check"]')).toBeNull();
    await change(container.querySelector('[aria-label="Condition sample type custom_variables.score"]'), 'boolean');
    await run();
    expect(sent.condition_values).toEqual({ custom_variables: { score: false } });
    expect(sent.observations).toEqual({});
    expect(container.textContent).toContain('Branch from supplied field value');
    await change(container.querySelector('[aria-label="Condition sample type custom_variables.score"]'), 'missing');
    expect(container.textContent).not.toContain('Graph checks passed');
  });
  it('does not interpret incomplete numeric samples as present text', async () => {
    global.fetch = jest.fn(async () => ok({}));
    await render([{ id: 'check', type: 'has_data_in_column', config: { condition_contract_version: 1, field: 'custom_variables.score', operator: 'has_value' } }]);
    await change(container.querySelector('[aria-label="Condition sample type custom_variables.score"]'), 'number');
    await change(container.querySelector('[aria-label="Condition sample value custom_variables.score"]'), '1e');
    await run();
    expect(container.textContent).toContain('Enter complete, finite');
    expect(global.fetch.mock.calls.some(([url]) => url.endsWith('/preview'))).toBe(false);
  });
});

it('rejects hidden nested linear actions and malformed visible labels', () => {
  expect(() => flattenTreeToDAG([{id:'one',type:'visit_profile',steps:[{id:'hidden',type:'visit_profile'}]}])).toThrow('not displayed');
  expect(() => flattenTreeToDAG([{id:'one',type:'visit_profile',title:{x:1}}])).toThrow('labels');
  expect(() => flattenTreeToDAG([{id:'one',type:'if_connected',branches:{left:[]}}])).toThrow('branch');
});
