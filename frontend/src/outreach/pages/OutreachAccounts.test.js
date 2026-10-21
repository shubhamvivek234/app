import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachAccounts from './OutreachAccounts';

const discovery = { context: { contract_version: 1, workspace_id: 'w', scope_digest: 'a'.repeat(64) }, jobs: [], operator_review_required: false };

jest.mock('../components/ConnectLinkedInModal', () => ({ isOpen, onClose, onAccountConnected }) => (
  isOpen ? <div><button onClick={onClose}>Cancel connect</button><button onClick={() => onAccountConnected({ id: 'sender-1' })}>Reconnect</button></div> : null
));

describe('LinkedIn sender accounts', () => {
  let container;
  let root;

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    localStorage.clear();
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    delete global.fetch;
  });

  it('shows true sender status and zero daily limits', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: async () => [{
      id: 'sender-1', account_name: 'Alex', status: 'paused', limits: { connection_invites: 0, messages: 0 },
    }] }));
    await act(async () => root.render(<OutreachAccounts />));
    expect(container.textContent).toContain('Paused');
    expect(container.textContent).toContain('0/day');
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Adjust')).click());
    expect([...container.querySelectorAll('input[type="number"]')].every((input) => input.min === '0')).toBe(true);
    expect(global.fetch).toHaveBeenCalledWith('/api/v1/outreach/accounts', expect.objectContaining({ credentials: 'include' }));
  });

  it('shows an API error rather than an empty connected-account state', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: false, json: async () => ({ detail: 'Unauthorized' }) }));
    await act(async () => root.render(<OutreachAccounts />));
    expect(container.textContent).toContain('Unauthorized');
    expect(container.textContent).toContain('Retry');
  });

  it('refreshes an existing sender after background verification finishes', async () => {
    let complete = false;
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: async () => [{
      id: 'sender-1', account_name: 'Alex', status: complete ? 'active' : 'session_expired',
    }] }));
    await act(async () => root.render(<OutreachAccounts />));
    complete = true;
    const refresh = container.querySelector('button[aria-label="Refresh sender accounts"]');
    expect(refresh).not.toBeNull();
    await act(async () => refresh.click());
    expect(container.textContent).toContain('Active');
    expect(global.fetch.mock.calls.filter(([url]) => url === '/api/v1/outreach/accounts')).toHaveLength(2);
  });

  it('does not describe a malformed successful response as having no senders', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: async () => ({ accounts: [] }) }));
    await act(async () => root.render(<OutreachAccounts />));
    expect(container.textContent).toContain('invalid response');
    expect(container.textContent).not.toContain('No accounts connected yet');
  });

  it('holds new connections until current durable verification discovery succeeds', async () => {
    let finish;
    global.fetch = jest.fn(url => url.endsWith('/connection-jobs')
      ? new Promise(resolve => { finish = resolve; })
      : Promise.resolve({ ok: true, json: async () => [] }));
    await act(async () => root.render(<OutreachAccounts />));
    const connect = [...container.querySelectorAll('button')].find(button => button.textContent === 'Connect account');
    expect(connect.disabled).toBe(true);
    await act(async () => finish({ ok: true, json: async () => discovery }));
    expect(connect.disabled).toBe(false);
  });
});
