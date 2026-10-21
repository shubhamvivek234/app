import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachCampaigns from './OutreachCampaigns';

jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
const KEY = 'unravler.campaign-deletions.v1';
const REQUEST = '12345678-1234-4234-8234-123456789012';
const OP = { id: 'campaign', workspaceId: 'workspace', requestId: REQUEST, phase: 'deletion_pending' };
const response = (data, ok = true) => ({ ok, json: async () => data });

describe('Campaign deletion recovery', () => {
  let container, root;
  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    sessionStorage.clear();
    container = document.createElement('div'); document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); delete global.fetch; sessionStorage.clear(); });
  const mount = async (op = OP) => {
    sessionStorage.setItem(KEY, JSON.stringify({ [JSON.stringify(['workspace', 'campaign'])]: op }));
    await act(async () => root.render(<OutreachCampaigns />));
  };
  const click = async (label) => {
    const button = [...container.querySelectorAll('button')].find((item) => item.textContent === label);
    expect(button).toBeTruthy(); await act(async () => button.click());
  };

  it('recovers a lost deletion response after remount using the same workspace and request', async () => {
    global.fetch = jest.fn((url) => Promise.resolve(url.includes('?')
      ? response({ id: 'campaign', request_id: REQUEST, status: 'deleted' }) : response([])));
    await mount();
    expect(global.fetch.mock.calls.some(([, options]) => options?.method === 'DELETE')).toBe(false);
    await click('Finish deletion');
    const call = global.fetch.mock.calls.find(([, options]) => options?.method === 'DELETE');
    expect(call[0]).toContain(`request_id=${REQUEST}`);
    expect(call[0]).toContain('expected_workspace_id=workspace');
    expect(container.textContent).toContain('Undo restores it paused');
    expect(JSON.parse(sessionStorage.getItem(KEY))[JSON.stringify(['workspace', 'campaign'])].phase).toBe('deleted');
  });

  it('keeps unfinished cleanup recoverable without claiming completion', async () => {
    global.fetch = jest.fn((url) => Promise.resolve(url.includes('?')
      ? response({ id: 'campaign', request_id: REQUEST, status: 'deletion_pending' }) : response([])));
    await mount(); await click('Finish deletion');
    expect(container.textContent).toContain('deletion needs confirmation');
    expect(container.textContent).not.toContain('Undo restores');
  });

  it('preserves a restoration reference after a network failure and retries only restore', async () => {
    let attempts = 0;
    global.fetch = jest.fn((url, options) => {
      if (options?.method === 'POST') {
        attempts += 1;
        return attempts === 1 ? Promise.reject(new Error('lost response'))
          : Promise.resolve(response({ id: 'campaign', request_id: REQUEST, status: 'restored' }));
      }
      return Promise.resolve(response([]));
    });
    await mount({ ...OP, phase: 'deleted' }); await click('Undo');
    expect(container.textContent).toContain('restoration needs confirmation');
    await click('Finish restoration');
    expect(sessionStorage.getItem(KEY)).toBe('{}');
    expect(global.fetch.mock.calls.filter(([, options]) => options?.method === 'DELETE')).toHaveLength(0);
  });

  it('does not send a request when its operation reference cannot be saved', async () => {
    global.fetch = jest.fn(() => Promise.resolve(response([])));
    await mount();
    const spy = jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage unavailable'); });
    try { await click('Finish deletion'); }
    finally { spy.mockRestore(); }
    expect(global.fetch.mock.calls.some(([, options]) => options?.method === 'DELETE')).toBe(false);
  });

  it('clears a stale deletion reference when the server returns 404 on Finish deletion', async () => {
    global.fetch = jest.fn((url) => Promise.resolve(url.includes('?')
      ? { ok: false, status: 404, json: async () => ({ detail: 'Campaign not found' }) } : response([])));
    await mount();
    await click('Finish deletion');
    expect(sessionStorage.getItem(KEY)).toBe('{}');
    expect(container.textContent).not.toContain('deletion needs confirmation');
  });
});
