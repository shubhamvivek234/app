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
      if (url === '/api/v1/outreach/billing/plans') return Promise.resolve(ok({ access_active: false, subscription: { status: 'none', seats: 0 } }));
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

  it('does not present a failed billing load as confirmed unpaid access', async () => {
    global.fetch = jest.fn(async () => ({ ok: false, status: 503, json: async () => ({}) }));
    await act(async () => root.render(<OutreachSettings initialTab="billing" />));
    expect(container.textContent).toContain('Billing status unavailable');
    expect(container.textContent).not.toContain('No paid sender access yet');
    expect([...container.querySelectorAll('button')].find((button) => button.textContent === 'Cancel').disabled).toBe(true);
    global.fetch.mockResolvedValue(ok({ access_active: true, subscription: { seats: 1, status: 'active' } }));
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent === 'Retry billing').click());
    expect(container.textContent).toContain('Paid access active');
  });

  it('loads and displays live subscription monitor, expiry, voice quota, and operator overview on subscription-monitor tab', async () => {
    global.fetch = jest.fn((url) => {
      if (url === '/api/v1/outreach/billing/plans') {
        return Promise.resolve(ok({ access_active: true, subscription: { seats: 2, status: 'active' } }));
      }
      if (url === '/api/v1/outreach/billing/subscription-monitor') {
        return Promise.resolve(ok({
          generated_at: '2026-10-22T14:30:00+00:00',
          is_platform_operator: true,
          posthog: {
            backend_configured: true,
            frontend_configured: true,
            host: 'https://us.i.posthog.com',
          },
          elevenlabs: {
            api_key_configured: true,
            voice_studio_enabled: false,
            model_id: 'eleven_turbo_v2_5',
            max_daily_clips_per_sender: 20,
            max_daily_chars_per_workspace: 20000,
          },
          workspace: {
            workspace_id: 'ws_alpha',
            workspace_name: 'Alpha Growth',
            billing_email: 'founder@alpha.io',
            lifecycle_state: 'active',
            plan_label: 'Managed Pilot ($59/sender/mo)',
            access_active: true,
            seats_granted: 2,
            seats_used: 1,
            seats_remaining: 1,
            country_code: 'US',
            paid_through: '2026-10-27T14:30:00+00:00',
            days_remaining: 5,
            hours_remaining: 120,
            expiring_soon: true,
            cancel_at_period_end: false,
            monthly_recurring_usd: 118,
            active_campaigns_count: 2,
            total_campaigns_count: 3,
            active_members_24h: 1,
            active_members_7d: 2,
            total_members: 2,
            members: [
              {
                user_id: 'u1',
                email: 'founder@alpha.io',
                display_name: 'Alice Founder',
                role: 'owner',
                last_active_at: '2026-10-22T14:00:00+00:00',
                active_24h: true,
                active_7d: true,
              },
            ],
            senders: [
              {
                id: 'acc_1',
                account_name: 'Alice LinkedIn',
                status: 'connected',
                seat_active: true,
                proxy_country: 'US',
                daily_invites_used: 9,
                daily_invites_limit: 25,
                daily_messages_used: 14,
                daily_messages_limit: 50,
                daily_voice_notes_used: 4,
                daily_voice_notes_limit: 20,
              },
            ],
            voice_usage: {
              today_clips_used: 4,
              daily_clips_limit: 20,
              today_chars_used: 1250,
              daily_chars_limit: 20000,
              cloned_voices_count: 1,
              max_cloned_voices: 5,
              model_id: 'eleven_turbo_v2_5',
            },
          },
          platform_overview: {
            kpis: {
              total_workspaces: 2,
              active_paid_workspaces: 1,
              expiring_within_7d_workspaces: 1,
              expired_workspaces: 0,
              pending_quote_workspaces: 1,
              total_paid_seats: 2,
              connected_senders: 1,
              estimated_mrr_usd: 118,
              total_users: 3,
              active_users_24h: 2,
              active_users_7d: 3,
            },
            subscribers: [
              {
                workspace_id: 'ws_alpha',
                workspace_name: 'Alpha Growth',
                owner_email: 'founder@alpha.io',
                lifecycle_state: 'active',
                plan_label: 'Managed Pilot ($59/sender/mo)',
                access_active: true,
                seats_granted: 2,
                seats_used: 1,
                country_code: 'US',
                paid_through: '2026-10-27T14:30:00+00:00',
                days_remaining: 5,
                expiring_soon: true,
                cancel_at_period_end: false,
                monthly_recurring_usd: 118,
                active_campaigns_count: 2,
                active_members_24h: 1,
                active_members_7d: 2,
                total_members: 2,
                voice_clips_today: 4,
                voice_chars_today: 1250,
              },
            ],
          },
        }));
      }
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });

    await act(async () => root.render(<OutreachSettings initialTab="subscription-monitor" />));

    expect(container.querySelector('[data-testid="subscription-monitor-view"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="platform-operator-overview"]')).not.toBeNull();
    expect(container.textContent).toContain('Subscriptions, Active Users & Quota Monitor');
    expect(container.textContent).toContain('Managed Pilot ($59/sender/mo)');
    expect(container.textContent).toContain('5d left');
    expect(container.textContent).toContain('1,250 / 20,000 chars');
    expect(container.textContent).toContain('Alice LinkedIn');
  });

  it('renders Sign out as the last button inside Settings navigation and invokes onSignOut', async () => {
    const onSignOut = jest.fn();
    global.fetch = jest.fn((url) => {
      if (url === '/api/v1/outreach/billing/plans') return Promise.resolve(ok({}));
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });

    await act(async () => root.render(<OutreachSettings initialTab="help" onSignOut={onSignOut} />));

    const signOutBtn = container.querySelector('[data-testid="settings-signout-button"]');
    expect(signOutBtn).not.toBeNull();
    expect(signOutBtn.textContent).toContain('Sign out');
    expect(container.querySelector('[data-testid="outreach-settings-contact-card"]')).not.toBeNull();
    expect(container.textContent).toContain('contact@unravler.com');
    await act(async () => signOutBtn.click());
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });
});
