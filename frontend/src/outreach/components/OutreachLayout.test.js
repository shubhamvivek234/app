import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachLayout from './OutreachLayout';
jest.mock('@/components/UnravlerLogo', () => () => null);
const ok = (data) => ({ ok: true, json: async () => data });
describe('Outreach header authoritative identity and billing', () => {
  let root; let container;
  beforeEach(() => { global.IS_REACT_ACT_ENVIRONMENT = true; container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); delete global.fetch; });
  const render = async (billing, activeTab = 'home') => {
    global.fetch = jest.fn(async (url) => {
      if (url.endsWith('/billing/plans')) return billing;
      if (url.endsWith('/accounts')) return ok([]);
      if (url.endsWith('/workspace/members')) return ok({ workspace_name: 'Actual Workspace' });
      if (url.endsWith('/auth/me')) return ok({ display_name: 'Actual Person' });
      throw new Error('Unexpected overview request');
    });
    await act(async () => root.render(<OutreachLayout activeTab={activeTab} />));
  };
  it('shows real workspace identity without inventing a trial', async () => {
    await render(ok({ trial_available: false, access_active: true }));
    expect(container.textContent).toContain('Actual Workspace'); expect(container.textContent).toContain('AP');
    expect(container.textContent).toContain('Paid access active'); expect(container.textContent).not.toContain('Trial ends');
    expect(container.textContent).not.toContain('My First Workspace');
    expect(global.fetch.mock.calls.every(([, options]) => options.credentials === 'include')).toBe(true);
  });
  it('renders an explicitly available zero-day trial', async () => {
    await render(ok({ trial_available: true, trial_days_remaining: 0, access_active: false }));
    expect(container.textContent).toContain('Trial ends in 0 days');
  });
  it('shows an unavailable billing state after a failed refresh', async () => {
    await render(ok({ access_active: true }));
    await render({ ok: false, status: 503 }, 'campaigns');
    expect(container.textContent).toContain('Billing unavailable'); expect(container.textContent).not.toContain('Trial ends');
    expect(container.textContent).not.toContain('Paid access active');
  });
});
