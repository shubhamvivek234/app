import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachAnalytics from './OutreachAnalytics';
import OutreachSwipeFiles from './OutreachSwipeFiles';
import OutreachInbox from './OutreachInbox';

jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

const ok = (body) => ({ ok: true, json: async () => body });

describe('Outreach analytics, swipe files, and inbox screens', () => {
  let container;
  let root;

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    localStorage.clear();
    HTMLElement.prototype.scrollIntoView = jest.fn();
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    jest.restoreAllMocks();
    delete global.fetch;
  });

  it('shows recorded analytics without invented email health', async () => {
    global.fetch = jest.fn((url) => {
      if (url === '/api/v1/outreach/campaigns') return Promise.resolve(ok([]));
      if (url.startsWith('/api/v1/outreach/analytics?')) return Promise.resolve(ok({
        has_connected_account: true,
        kpis: {
          requests: { sent: 2, accepted: 1 },
          messages: { sent: 1, replied: 1 },
          engagement: { total_actions: 0, profile_visits: 0, post_engagements: 0 },
          pipeline: { total_leads: 2, in_campaign: 1, replied: 1, call_booked: 0 },
        },
        daily_chart: [{ date: '25 Sep', sent: 2, messages_sent: 1, accepted: 1, replied: 1 }],
      }));
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });

    await act(async () => root.render(<OutreachAnalytics />));
    expect(container.textContent).toContain('Confirmed invitations sent in this period');
    expect(container.textContent).not.toContain('99.4% health');
    expect(container.textContent).not.toContain('Email Delivered');
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/outreach/analytics?'),
      expect.objectContaining({ credentials: 'include' })
    );
  });

  it('loads swipe files with cookie credentials and pagination', async () => {
    global.fetch = jest.fn(() => Promise.resolve(ok([])));
    await act(async () => root.render(<OutreachSwipeFiles />));
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 300)); });
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/outreach/swipe?skip=0&limit=30'),
      expect.objectContaining({ credentials: 'include' })
    );
    expect(container.textContent).toContain('Your Swipe File is Empty');
  });

  it('keeps sample conversations out of the real inbox', async () => {
    global.fetch = jest.fn(() => Promise.resolve(ok([])));
    await act(async () => root.render(<OutreachInbox />));
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
    expect(container.textContent).toContain('No conversations yet.');
    expect(container.textContent).not.toContain('Load Sample Conversations');
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/outreach/inbox?'),
      expect.objectContaining({ credentials: 'include' })
    );
  });
});
