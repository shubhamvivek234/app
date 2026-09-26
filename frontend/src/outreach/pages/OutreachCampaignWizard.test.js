import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachCampaignWizard from './OutreachCampaignWizard';

jest.mock('../components/sequence/SequenceCanvas', () => {
  const MockReact = require('react');
  return ({ campaignId, onRegisterSave }) => {
    MockReact.useEffect(() => {
      onRegisterSave(() => globalThis.__wizardSequenceSaveResult ?? Promise.resolve(true));
      return () => onRegisterSave(null);
    }, [onRegisterSave]);
    return MockReact.createElement('div', { 'data-testid': 'sequence-canvas' }, `Sequence for ${campaignId}`);
  };
});
jest.mock('../components/ImportLeadsModal', () => () => null);
jest.mock('../components/ConnectLinkedInModal', () => () => null);
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

describe('First campaign wizard', () => {
  let container;
  let root;

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    localStorage.clear();
    window.__wizardSequenceSaveResult = null;
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    delete global.fetch;
    delete window.__wizardSequenceSaveResult;
  });

  it('does not expose an unsavable sequence when draft creation fails', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: false, json: async () => ({ detail: 'Draft unavailable' }) }));
    await act(async () => root.render(<OutreachCampaignWizard campaignId="new" initialStep={2} />));
    expect(container.textContent).toContain('Draft unavailable');
    expect(container.textContent).toContain('Retry');
    expect(container.querySelector('[data-testid="sequence-canvas"]')).toBeNull();
  });

  it('binds the sequence editor to the saved campaign ID', async () => {
    global.fetch = jest.fn((url) => Promise.resolve({
      ok: true,
      json: async () => url.includes('/auto-draft') ? { id: 'campaign-saved', name: 'First campaign' } : url.endsWith('/accounts') ? [] : { leads: [], total: 0 },
    }));
    await act(async () => root.render(<OutreachCampaignWizard campaignId="new" initialStep={2} />));
    expect(container.querySelector('[data-testid="sequence-canvas"]')?.textContent).toContain('campaign-saved');
  });

  it('surfaces sender loading errors and allows retry', async () => {
    global.fetch = jest.fn((url) => Promise.resolve({
      ok: !url.endsWith('/accounts'),
      json: async () => url.includes('/auto-draft') ? { id: 'campaign-saved', name: 'First campaign' } : url.endsWith('/accounts') ? { detail: 'Accounts unavailable' } : { leads: [], total: 0 },
    }));
    await act(async () => root.render(<OutreachCampaignWizard campaignId="new" initialStep={3} />));
    expect(container.textContent).toContain('Accounts unavailable');
    expect([...container.querySelectorAll('button')].some((button) => button.textContent.includes('Retry'))).toBe(true);
  });

  it('does not open an editable sequence for an active campaign', async () => {
    global.fetch = jest.fn((url) => Promise.resolve({
      ok: true,
      json: async () => url.endsWith('/accounts') ? [] : { id: 'campaign-active', name: 'Running', status: 'active' },
    }));
    await act(async () => root.render(<OutreachCampaignWizard campaignId="campaign-active" initialStep={2} />));
    expect(container.textContent).toContain('Pause the campaign');
    expect(container.querySelector('[data-testid="sequence-canvas"]')).toBeNull();
  });

  it('stays on Leads when Proceed cannot save the draft', async () => {
    let draftSaves = 0;
    global.fetch = jest.fn((url) => Promise.resolve({
      ok: !url.includes('/auto-draft') || ++draftSaves === 1,
      json: async () => url.includes('/auto-draft')
        ? { id: 'campaign-saved', name: 'First campaign' }
        : url.endsWith('/accounts') ? [] : { leads: [{ id: 'lead-1', first_name: 'Sam' }], total: 1 },
    }));
    await act(async () => root.render(<OutreachCampaignWizard campaignId="new" initialStep={1} />));
    const proceed = [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Proceed to Sequence'));
    expect(proceed).toBeTruthy();
    await act(async () => proceed.click());
    expect(container.querySelector('[data-testid="sequence-canvas"]')).toBeNull();
    expect(container.textContent).toContain('Recent Prospects Preview');
  });

  it('does not leave Sequence through a step tab when sequence save fails', async () => {
    window.__wizardSequenceSaveResult = Promise.resolve(false);
    global.fetch = jest.fn((url) => Promise.resolve({
      ok: true,
      json: async () => url.includes('/auto-draft')
        ? { id: 'campaign-saved', name: 'First campaign' }
        : url.endsWith('/accounts') ? [] : { leads: [{ id: 'lead-1' }], total: 1 },
    }));
    await act(async () => root.render(<OutreachCampaignWizard campaignId="new" initialStep={2} />));
    const launchTab = [...container.querySelectorAll('button')].find((button) => button.textContent.trim() === '3Launch & Senders');
    expect(launchTab).toBeTruthy();
    await act(async () => launchTab.click());
    expect(container.querySelector('[data-testid="sequence-canvas"]')).not.toBeNull();
  });

  it('takes a first draft through leads, sequence, sender review, and launch request', async () => {
    global.fetch = jest.fn((url) => Promise.resolve({
      ok: true,
      json: async () => url.includes('/auto-draft')
        ? { id: 'campaign-saved', name: 'First campaign' }
        : url.endsWith('/accounts')
          ? [{ id: 'sender-a', status: 'active', account_name: 'Sam Sender' }]
          : url.includes('/leads')
            ? { leads: [{ id: 'lead-1', first_name: 'Alex' }], total: 1 }
            : { status: 'launched' },
    }));
    await act(async () => root.render(<OutreachCampaignWizard campaignId="new" initialStep={1} />));
    const clickButton = async (label) => {
      const button = [...container.querySelectorAll('button')].find((item) => item.textContent.includes(label));
      expect(button).toBeTruthy();
      await act(async () => button.click());
    };
    await clickButton('Proceed to Sequence');
    expect(container.querySelector('[data-testid="sequence-canvas"]')).not.toBeNull();
    await clickButton('Next: Launch');
    expect(container.textContent).toContain('Who is sending?');
    expect(container.textContent).toContain('1 of 1 selected');
    await clickButton('Launch Campaign');
    expect(container.textContent).toContain('Review campaign launch');
    await clickButton('Confirm and Launch');
    const launchCall = global.fetch.mock.calls.find(([url]) => url === '/api/v1/outreach/campaigns/campaign-saved/launch');
    expect(launchCall).toBeTruthy();
    expect(JSON.parse(launchCall[1].body).sender_account_ids).toEqual(['sender-a']);
  });

  it('arms conditional launch only after an explicit warm-up opt-in', async () => {
    const { toast } = require('sonner');
    toast.error.mockClear();
    global.fetch = jest.fn((url) => Promise.resolve({
      ok: true,
      json: async () => url.includes('/auto-draft')
        ? { id: 'campaign-saved', name: 'First campaign' }
        : url.endsWith('/accounts')
          ? [{ id: 'sender-a', status: 'active', account_name: 'Sam Sender' }]
          : url.includes('/leads')
            ? { leads: [{ id: 'lead-1', first_name: 'Alex' }], total: 1 }
            : url.includes('/features/conditional-launch')
              ? { enabled: true }
              : url.endsWith('/engage/lists')
                ? [{ id: 'list-1', name: 'Warm Cohort' }]
                : { status: 'warming_up' },
    }));
    await act(async () => root.render(<OutreachCampaignWizard campaignId="new" initialStep={3} />));
    const toggle = container.querySelector('input[aria-label="Automatically launch after warm-up"]');
    expect(toggle).toBeTruthy();
    await act(async () => toggle.click());
    await act(async () => { await Promise.resolve(); });
    const listPicker = container.querySelector('input[name="engage-cohort"][value="list-1"]');
    expect(global.fetch.mock.calls.map(([url]) => url)).toContain('/api/v1/outreach/engage/lists');
    expect(container.textContent).toContain('Warm Cohort');
    expect(listPicker).toBeTruthy();
    await act(async () => listPicker.click());
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Review and launch')).click());
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Confirm conditional launch')).click());
    expect(toast.error.mock.calls).toEqual([]);
    const armCall = global.fetch.mock.calls.find(([url]) => url === '/api/v1/outreach/campaigns/campaign-saved/arm-warmup');
    expect(armCall).toBeTruthy();
    expect(JSON.parse(armCall[1].body)).toEqual({ engage_list_id: 'list-1', warmup_hours: 24 });
    expect(global.fetch.mock.calls.some(([url]) => url === '/api/v1/outreach/campaigns/campaign-saved/launch')).toBe(false);
  });
});
