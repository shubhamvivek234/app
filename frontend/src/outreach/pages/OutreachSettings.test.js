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
          rate_cards: [{ tier: '1-5', label: '1–5 accounts', annual: 61.99, quarterly: 69.99, monthly: 79.99 }],
          features_included: ['Unlimited campaigns', 'Voice cloning'],
          billing_email: 'billing@company.com',
          trial_active: true,
          trial_days_remaining: 3,
        }));
      }
      if (url === '/api/v1/outreach/accounts') {
        return Promise.resolve(ok([]));
      }
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });

    await act(async () => root.render(<OutreachSettings initialTab="billing" />));

    expect(container.textContent).toContain('Billing & Subscriptions');
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
});
