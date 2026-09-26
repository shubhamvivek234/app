import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachCampaignDetail from './OutreachCampaignDetail';

jest.mock('../components/ImportLeadsModal', () => () => null);
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

describe('Campaign detail launch flow', () => {
  let container;
  let root;

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    delete global.fetch;
  });

  it('opens sender review instead of launching an unreviewed draft', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: async () => ({
      id: 'campaign-a', name: 'First campaign', status: 'draft', sender_account_ids: [],
      leads_count: 0, schedule: {},
    }) }));
    const onEdit = jest.fn();
    await act(async () => root.render(<OutreachCampaignDetail campaignId="campaign-a" onBack={() => {}} onEdit={onEdit} />));
    const launch = [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Launch Campaign'));
    await act(async () => launch.click());
    expect(onEdit).toHaveBeenCalledWith('campaign-a', 3, 'First campaign');
    expect(global.fetch).not.toHaveBeenCalledWith('/api/v1/outreach/campaigns/campaign-a/launch', expect.anything());
  });

  it('distinguishes a temporary API failure from a missing campaign and offers retry', async () => {
    global.fetch = jest.fn()
      .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'Service unavailable' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'campaign-a', name: 'Recovered', status: 'draft', schedule: {} }) });
    await act(async () => root.render(<OutreachCampaignDetail campaignId="campaign-a" onBack={() => {}} />));
    expect(container.textContent).toContain('Service unavailable');
    expect(container.textContent).not.toContain('Campaign not found');
    const retry = [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Retry'));
    await act(async () => retry.click());
    expect(container.textContent).toContain('Recovered');
  });

  it('lets a user cancel a waiting conditional launch', async () => {
    global.fetch = jest.fn((url) => Promise.resolve({ ok: true, json: async () => (
      url.endsWith('/pause') ? { status: 'paused' } : {
        id: 'campaign-a', name: 'Waiting campaign', status: 'warming_up',
        auto_launch_missing_count: 1, sender_account_ids: ['sender-a'], schedule: {},
      }
    ) }));
    await act(async () => root.render(<OutreachCampaignDetail campaignId="campaign-a" onBack={() => {}} />));
    const cancel = [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Cancel auto-launch'));
    expect(cancel).toBeTruthy();
    await act(async () => cancel.click());
    expect(global.fetch.mock.calls.some(([url]) => url === '/api/v1/outreach/campaigns/campaign-a/pause')).toBe(true);
    expect(container.textContent).toContain('paused');
  });
});
