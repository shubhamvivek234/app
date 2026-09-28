import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachSettings from './OutreachSettings';

jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const ok = (body) => ({ ok: true, json: async () => body });

describe('OutreachSettings page', () => {
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
    jest.restoreAllMocks();
    delete global.fetch;
  });

  it('renders tabs without Import from V1 and displays billing and accounts', async () => {
    global.fetch = jest.fn((url) => {
      if (url === '/api/v1/outreach/billing/plans') {
        return Promise.resolve(ok({
          price_usd_per_sender_month: 59,
          billing_email: 'billing@company.com',
          subscription: { status: 'none', seats: 0 },
          access_active: false,
        }));
      }
      if (url === '/api/v1/outreach/accounts') {
        return Promise.resolve(ok([]));
      }
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });

    await act(async () => root.render(<OutreachSettings initialTab="billing" />));

    expect(container.textContent).toContain('Outreach billing');
    expect(container.textContent).toContain('$59');
    expect(container.textContent).not.toContain('4-day trial');
    expect(container.textContent).toContain('billing@company.com');
    // Ensure Import from V1 is completely removed
    expect(container.textContent).not.toContain('Import from V1');
    expect(container.textContent).toContain('Help & Resources');
  });

  it('loads and displays workspace members when members tab is active', async () => {
    global.fetch = jest.fn((url) => {
      if (url === '/api/v1/outreach/billing/plans') return Promise.resolve(ok({}));
      if (url === '/api/v1/workspace/members') {
        return Promise.resolve(ok({
          workspace_id: 'ws_123',
          current_user_role: 'admin',
          permissions: { can_invite: true, can_remove_member: true },
          members: [
            { user_id: 'u1', display_name: 'Alice Founder', email: 'alice@example.com', role: 'owner' },
            { user_id: 'u2', display_name: 'Bob SDR', email: 'bob@example.com', role: 'editor' },
          ],
          pending_invites: [
            { invite_id: 'inv_1', email: 'charlie@example.com', role: 'viewer', status: 'pending', invite_url: 'http://localhost/accept/token1' },
          ],
        }));
      }
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });

    await act(async () => root.render(<OutreachSettings initialTab="members" />));

    expect(container.textContent).toContain('Workspace Members');
    expect(container.textContent).toContain('Alice Founder');
    expect(container.textContent).toContain('bob@example.com');
    expect(container.textContent).toContain('Pending Invites (1)');
    expect(container.textContent).toContain('charlie@example.com');
  });

  it('opens the sender mailbox settings from its own navigation tab', async () => {
    global.fetch = jest.fn((url) => {
      if (url === '/api/v1/outreach/billing/plans') return Promise.resolve(ok({}));
      if (url === '/api/v1/outreach/accounts') return Promise.resolve(ok([{ id: 'sender-a', account_name: 'Sam' }]));
      if (url === '/api/v1/outreach/mailboxes/hunter-key') return Promise.resolve(ok({ configured: false, enabled: false }));
      if (url === '/api/v1/outreach/mailboxes') return Promise.resolve(ok({ mailboxes: [], connection_enabled: false, send_enabled: false, sync_enabled: false }));
      throw new Error(`Unexpected request: ${url}`);
    });
    await act(async () => root.render(<OutreachSettings initialTab="accounts" />));
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent === 'Email mailboxes').click());
    expect(container.textContent).toContain('Connect a Gmail or Microsoft mailbox');
    expect(global.fetch.mock.calls.some(([url]) => url === '/api/v1/outreach/mailboxes')).toBe(true);
  });

  it('renders FAQ and safety guidance on help tab', async () => {
    global.fetch = jest.fn((url) => {
      if (url === '/api/v1/outreach/billing/plans') return Promise.resolve(ok({}));
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });

    await act(async () => root.render(<OutreachSettings initialTab="help" />));

    expect(container.textContent).toContain('Help & Outreach Safety Guidelines');
    expect(container.textContent).toContain('Platform policy notice');
    expect(container.textContent).not.toContain('simulate genuine human browsing');
    expect(container.textContent).not.toContain('requests appear natural');
    expect(container.textContent).not.toContain('safe daily volume limits');
  });

  it('requests managed access without activating a trial or charging a card', async () => {
    global.fetch = jest.fn((url) => {
      if (url === '/api/v1/outreach/billing/plans') return Promise.resolve(ok({ subscription: { status: 'none', seats: 0 } }));
      if (url === '/api/v1/outreach/billing/request-access') return Promise.resolve(ok({ status: 'pending_quote' }));
      throw new Error(`Unexpected request: ${url}`);
    });
    await act(async () => root.render(<OutreachSettings initialTab="billing" />));
    const country = container.querySelector('#pilot-country');
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(country, 'IN');
      country.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => [...container.querySelectorAll('button')]
      .find((button) => button.textContent === 'Request managed access').click());
    const request = global.fetch.mock.calls.find(([url]) => url === '/api/v1/outreach/billing/request-access');
    expect(request[1].credentials).toBe('include');
    expect(JSON.parse(request[1].body)).toEqual({ seats: 1, country_code: 'IN' });
    expect(global.fetch.mock.calls.some(([url]) => url.includes('start-trial'))).toBe(false);
    expect(container.textContent).toContain('awaiting availability and quote');
  });
});
