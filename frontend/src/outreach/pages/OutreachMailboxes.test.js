import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachMailboxes from './OutreachMailboxes';

jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const ok = (value) => ({ ok: true, json: async () => value });

describe('Outreach email connection settings', () => {
  let container;
  let root;

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    localStorage.clear();
    window.history.replaceState({}, '', '/outreach?tab=settings');
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    delete global.fetch;
    window.history.replaceState({}, '', '/');
    jest.restoreAllMocks();
  });

  it('shows existing mailbox status but disables connection while the pilot flag is off', async () => {
    global.fetch = jest.fn((url) => Promise.resolve(url.endsWith('/accounts')
      ? ok([{ id: 'sender-a', account_name: 'Sam Sender', status: 'active' }])
      : url.endsWith('/mailboxes/hunter-key')
        ? ok({ configured: false })
      : ok({ mailboxes: [{ sender_account_id: 'sender-a', provider: 'gmail', email: 'sam@example.com', status: 'connected' }], connection_enabled: false, send_enabled: false, sync_enabled: false })));
    await act(async () => root.render(<OutreachMailboxes />));
    expect(container.textContent).toContain('sam@example.com');
    expect(container.textContent).toContain('Email connection is not enabled');
    expect(container.textContent).toContain('Reply monitoring is not enabled');
    expect([...container.querySelectorAll('button')].find((button) => button.textContent.includes('Connect Gmail')).disabled).toBe(true);
  });

  it('starts Gmail authorization for the chosen sender without handling credentials', async () => {
    global.fetch = jest.fn((url, options = {}) => Promise.resolve(url.endsWith('/accounts')
      ? ok([{ id: 'sender-a', account_name: 'Sam Sender', status: 'active' }])
      : url.endsWith('/mailboxes/hunter-key')
        ? ok({ configured: false, enabled: true })
        : url.endsWith('/mailboxes/gmail/authorize')
          ? ok({ authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?state=x', connection_job_id: 'job-1' })
          : ok({ mailboxes: [], connection_enabled: true, send_enabled: false })));
    const popup = { location: { href: '' }, close: jest.fn() };
    jest.spyOn(window, 'open').mockReturnValue(popup);
    await act(async () => root.render(<OutreachMailboxes />));
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Connect Gmail')).click());
    const request = global.fetch.mock.calls.find(([url]) => url.endsWith('/mailboxes/gmail/authorize'));
    expect(JSON.parse(request[1].body)).toEqual({ sender_account_id: 'sender-a' });
    expect(popup.location.href).toContain('accounts.google.com');
    expect(request[1].credentials).toBe('include');
  });

  it('polls the callback job and removes its query token after completion', async () => {
    window.history.replaceState({}, '', '/outreach?tab=settings&mailbox_job_id=job-1');
    global.fetch = jest.fn((url) => Promise.resolve(url.endsWith('/accounts')
      ? ok([{ id: 'sender-a', account_name: 'Sam Sender', status: 'active' }])
      : url.endsWith('/mailboxes/hunter-key')
        ? ok({ configured: false, enabled: true })
        : url.endsWith('/mailboxes/connection-jobs/job-1')
          ? ok({ status: 'connected', provider: 'gmail', sender_account_id: 'sender-a' })
          : ok({ mailboxes: [{ sender_account_id: 'sender-a', provider: 'gmail', email: 'sam@example.com', status: 'connected' }], connection_enabled: true, send_enabled: false })));
    await act(async () => root.render(<OutreachMailboxes />));
    expect(global.fetch.mock.calls.some(([url]) => url.endsWith('/mailboxes/connection-jobs/job-1'))).toBe(true);
    expect(window.location.search).not.toContain('mailbox_job_id');
    expect(container.textContent).toContain('sam@example.com');
  });

  it('saves a Hunter API key without displaying it afterward', async () => {
    global.fetch = jest.fn((url, options = {}) => Promise.resolve(url.endsWith('/accounts')
      ? ok([{ id: 'sender-a', account_name: 'Sam Sender', status: 'active' }])
      : url.endsWith('/mailboxes/hunter-key')
        ? ok({ configured: options.method === 'PUT', enabled: true })
        : ok({ mailboxes: [], connection_enabled: true, send_enabled: false })));
    await act(async () => root.render(<OutreachMailboxes />));
    const input = container.querySelector('input[aria-label="Hunter API key"]');
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, 'secret-key');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Save Hunter key')).click());
    const request = global.fetch.mock.calls.find(([url, options]) => url.endsWith('/mailboxes/hunter-key') && options.method === 'PUT');
    expect(JSON.parse(request[1].body)).toEqual({ api_key: 'secret-key' });
    expect(container.textContent).not.toContain('secret-key');
    expect(input.type).toBe('password');
  });

  it('rejects an untrusted provider authorization link', async () => {
    global.fetch = jest.fn((url) => Promise.resolve(url.endsWith('/accounts')
      ? ok([{ id: 'sender-a', account_name: 'Sam Sender', status: 'active' }])
      : url.endsWith('/mailboxes/hunter-key')
        ? ok({ configured: false, enabled: true })
        : url.endsWith('/mailboxes/gmail/authorize')
          ? ok({ authorization_url: 'https://example.org/steal', connection_job_id: 'job-1' })
          : ok({ mailboxes: [], connection_enabled: true, send_enabled: false, sync_enabled: false })));
    const popup = { location: { href: '' }, close: jest.fn() };
    jest.spyOn(window, 'open').mockReturnValue(popup);
    await act(async () => root.render(<OutreachMailboxes />));
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Connect Gmail')).click());
    expect(popup.close).toHaveBeenCalled();
    expect(popup.location.href).toBe('');
    expect(container.textContent).toContain('invalid authorization link');
  });

  it('disconnects a sender mailbox only after confirmation', async () => {
    let connected = true;
    global.fetch = jest.fn((url, options = {}) => Promise.resolve(url.endsWith('/accounts')
      ? ok([{ id: 'sender-a', account_name: 'Sam Sender', status: 'active' }])
      : url.endsWith('/mailboxes/hunter-key')
        ? ok({ configured: false, enabled: false })
        : url.endsWith('/mailboxes/sender-a') && options.method === 'DELETE'
          ? (connected = false, ok({ status: 'disconnected' }))
          : ok({ mailboxes: connected ? [{ sender_account_id: 'sender-a', provider: 'gmail', email: 'sam@example.com', status: 'connected' }] : [], connection_enabled: true, send_enabled: false, sync_enabled: false })));
    jest.spyOn(window, 'confirm').mockReturnValue(true);
    await act(async () => root.render(<OutreachMailboxes />));
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent === 'Disconnect').click());
    expect(global.fetch.mock.calls.some(([url, options]) => url.endsWith('/mailboxes/sender-a') && options.method === 'DELETE')).toBe(true);
    expect(container.textContent).toContain('No mailbox connected.');
  });
});
