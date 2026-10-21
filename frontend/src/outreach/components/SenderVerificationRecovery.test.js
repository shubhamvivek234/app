import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import SenderVerificationRecovery from './SenderVerificationRecovery';

const context = { contract_version: 1, workspace_id: 'w', scope_digest: 'a'.repeat(64) };
const pending = { job_id: 'saved-job', sender_id: 'sender', status: 'running', reconnect: false };
const list = (jobs = [pending], extra = {}) => ({ context, jobs, operator_review_required: false, ...extra });
const response = (value, ok = true) => ({ ok, json: async () => value });

describe('server-backed sender recovery', () => {
  let root, container, state, connected;
  const render = async (props = {}) => { await act(async () => root.render(
    <SenderVerificationRecovery onState={state} onAccountConnected={connected} {...props} />)); };
  const click = async (label) => { await act(async () => [...container.querySelectorAll('button')]
    .find(button => button.textContent.includes(label)).click()); };
  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    state = jest.fn(); connected = jest.fn(); localStorage.clear(); sessionStorage.clear();
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); delete global.fetch; });

  test('rediscovers the original job after remount without browser persistence or POST', async () => {
    global.fetch = jest.fn(async () => response(list()));
    await render();
    expect(container.textContent).toContain('running');
    expect(state).toHaveBeenLastCalledWith(expect.objectContaining({ blocked: true, context }));
    await act(async () => root.unmount()); root = createRoot(container); await render();
    expect(global.fetch.mock.calls).toHaveLength(2);
    expect(global.fetch.mock.calls.every(([url, options]) => url.endsWith('/connection-jobs') && !options.method)).toBe(true);
    expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0);
  });

  test('checks the exact scoped original job and accepts only its current account', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce(response(list())).mockResolvedValueOnce(response(list()))
      .mockResolvedValueOnce(response({ ...context, ...pending, status: 'completed', account_current: true,
        account: { id: 'sender', workspace_id: 'w', status: 'active' } }));
    await render(); await click('Check verification');
    expect(global.fetch.mock.calls[2][0]).toBe(`/api/v1/outreach/accounts/connection-jobs/saved-job?scope_digest=${context.scope_digest}`);
    expect(connected).toHaveBeenCalledTimes(1);
    expect(global.fetch.mock.calls.every(([, options]) => !options.method)).toBe(true);
  });

  test('lists multiple jobs for explicit selection', async () => {
    global.fetch = jest.fn(async () => response(list([pending, { ...pending, job_id: 'other', sender_id: 'two' }])));
    await render();
    expect(container.querySelectorAll('[data-verification-job]')).toHaveLength(2);
    expect(global.fetch).toHaveBeenCalledTimes(1); expect(connected).not.toHaveBeenCalled();
  });

  test('context changes before checking hold the saved selection without reading a foreign job', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce(response(list()))
      .mockResolvedValueOnce(response(list([], { context: { ...context, workspace_id: 'other', scope_digest: 'b'.repeat(64) } })));
    await render(); await click('Check verification');
    expect(global.fetch).toHaveBeenCalledTimes(2); expect(connected).not.toHaveBeenCalled();
    expect(container.textContent).toContain('context changed');
    expect(state).toHaveBeenLastCalledWith(expect.objectContaining({ blocked: true }));
  });

  test.each([{ workspace_id: 'other' }, { scope_digest: 'b'.repeat(64) }, { job_id: 'different' },
    { sender_id: 'different' }, { account: { id: 'replacement', workspace_id: 'w', status: 'active' } }])(
    'malformed or mismatched completion cannot report success %j', async change => {
      global.fetch = jest.fn().mockResolvedValueOnce(response(list())).mockResolvedValueOnce(response(list()))
        .mockResolvedValueOnce(response({ ...context, ...pending, status: 'completed', account_current: true,
          account: { id: 'sender', workspace_id: 'w', status: 'active' }, ...change }));
      await render(); await click('Check verification');
      expect(connected).not.toHaveBeenCalled(); expect(container.querySelector('[role="alert"]')).not.toBeNull();
    });

  test('historical completion never confirms a disconnected or replaced account', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce(response(list())).mockResolvedValueOnce(response(list()))
      .mockResolvedValueOnce(response({ ...context, ...pending, status: 'completed', account_current: false }));
    await render(); await click('Check verification');
    expect(connected).not.toHaveBeenCalled(); expect(container.textContent).toContain('no longer confirms');
  });

  test.each([null, {}, { ...list(), jobs: [pending, pending] }, { ...list(), operator_review_required: 'false' }])(
    'discovery failure or invalid metadata holds new connection %j', async payload => {
      global.fetch = jest.fn(async () => response(payload)); await render();
      expect(state).toHaveBeenLastCalledWith(expect.objectContaining({ blocked: true }));
      expect(container.querySelector('[role="alert"]')).not.toBeNull();
    });

  test('unknown storage remains a support hold and no secret is replayed', async () => {
    global.fetch = jest.fn(async () => response(list([], { operator_review_required: true })));
    await render(); expect(container.textContent).toContain('support review');
    expect(state).toHaveBeenLastCalledWith(expect.objectContaining({ blocked: true }));
  });

  test('ignores a late completion after token change', async () => {
    let finish;
    global.fetch = jest.fn().mockResolvedValueOnce(response(list())).mockResolvedValueOnce(response(list()))
      .mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    await render(); await click('Check verification'); localStorage.setItem('token', 'changed');
    await act(async () => finish(response({ ...context, ...pending, status: 'completed', account_current: true,
      account: { id: 'sender', workspace_id: 'w', status: 'active' } })));
    expect(connected).not.toHaveBeenCalled();
  });
});
