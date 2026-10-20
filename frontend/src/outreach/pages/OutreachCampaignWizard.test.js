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
const ready = { campaign_id: 'campaign-saved', can_launch: true, blockers: [], checklist: [{ id: 'proxies', name: 'Sender Resource Assignment', passed: true, message: 'Stored leases match' }], summary: { branch_paths: ['a → b (next)'], variables_detected: ['first_name'] }, execution_checks: [{ id: 'permission', message: 'Fresh execution permission is checked by workers' }] };

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

  it('shows a configurable email daily limit in sender review', async () => {
    global.fetch = jest.fn((url) => Promise.resolve({
      ok: true,
      json: async () => url.includes('/auto-draft')
        ? { id: 'campaign-saved', name: 'First campaign' }
        : url.endsWith('/accounts') ? [{ id: 'sender-a', status: 'active' }] : { leads: [], total: 0 },
    }));
    await act(async () => root.render(<OutreachCampaignWizard campaignId="new" initialStep={3} />));
    expect(container.textContent).toContain('Email sends');
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

  it('preserves numeric-weekday working hours and timezone when reopening and saving a draft', async () => {
    const saved = { id: 'campaign-saved', name: 'Early hours', status: 'paused', sender_account_ids: ['sender-a'],
      schedule: { days: [0, 2, 4], start_time: '07:00', end_time: '11:00', timezone: 'Asia/Kolkata' } };
    global.fetch = jest.fn((url) => Promise.resolve({ ok: true, json: async () => url.endsWith('/accounts')
      ? [{ id: 'sender-a', status: 'active' }] : url.endsWith('/preflight') ? ready
      : url.includes('/leads') ? { leads: [], total: 0 } : saved }));
    await act(async () => root.render(<OutreachCampaignWizard campaignId="campaign-saved" initialStep={3} />));
    await act(async () => container.querySelector('button[title="Back to campaigns"]').click());
    const payload = JSON.parse(global.fetch.mock.calls.find(([url]) => url.endsWith('/auto-draft'))[1].body);
    expect(payload.schedule.timezone).toBe('Asia/Kolkata');
    expect(payload.schedule.days.filter(day => day.enabled).map(day => day.day)).toEqual(['Monday', 'Wednesday', 'Friday']);
    expect(payload.schedule.days.every(day => day.ranges[0].start === '07:00 AM' && day.ranges[0].end === '11:00 AM')).toBe(true);
  });

  it('retains an unavailable saved sender when account loading completes later', async () => {
    let finishAccounts;
    const saved = { id: 'campaign-saved', name: 'Paused', status: 'paused', sender_account_ids: ['old-sender'] };
    global.fetch = jest.fn((url) => url.endsWith('/accounts') ? new Promise(resolve => { finishAccounts = resolve; })
      : Promise.resolve({ ok: true, json: async () => url.endsWith('/preflight') ? ready : url.includes('/leads') ? { leads: [], total: 0 } : saved }));
    await act(async () => root.render(<OutreachCampaignWizard campaignId="campaign-saved" initialStep={3} />));
    await act(async () => finishAccounts({ ok: true, json: async () => [{ id: 'other-sender', account_name: 'Other', status: 'active' }] }));
    expect(container.textContent).toContain('Previously selected senders are unavailable');
    await act(async () => container.querySelector('button[title="Back to campaigns"]').click());
    const payload = JSON.parse(global.fetch.mock.calls.find(([url]) => url.endsWith('/auto-draft'))[1].body);
    expect(payload.sender_account_ids).toEqual(['old-sender']);
    expect(container.querySelector('input[type="checkbox"]').checked).toBe(false);
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
            : url.endsWith('/preflight') ? ready : { status: 'launched' },
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

  it('keeps the launch review open and shows the backend capability blocker', async () => {
    global.fetch = jest.fn((url) => Promise.resolve({
      ok: !url.endsWith('/launch'),
      json: async () => url.includes('/auto-draft')
        ? { id: 'campaign-saved', name: 'First campaign' }
        : url.endsWith('/accounts')
          ? [{ id: 'sender-a', status: 'active', account_name: 'Sam Sender' }]
          : url.includes('/leads')
            ? { leads: [{ id: 'lead-1' }], total: 1 }
            : url.endsWith('/preflight') ? ready : url.endsWith('/launch')
              ? { detail: 'Send email requires a connected mailbox.' }
              : {},
    }));
    await act(async () => root.render(<OutreachCampaignWizard campaignId="new" initialStep={3} />));
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Launch Campaign')).click());
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Confirm and Launch')).click());
    expect(container.textContent).toContain('Send email requires a connected mailbox.');
    expect(container.textContent).toContain('Review campaign launch');
  });
  const installReviewResponses = (preflight) => {
    global.fetch = jest.fn((url, options = {}) => {
      if (url.endsWith('/preflight')) return preflight(url, options);
      return Promise.resolve({ ok: true, json: async () => url.includes('/auto-draft')
        ? { id: 'campaign-saved', name: 'First campaign' }
        : url.endsWith('/accounts') ? [{ id: 'sender-a', status: 'active', account_name: 'Sender' }]
        : url.includes('/leads') ? { leads: [{ id: 'lead' }], total: 1 } : {} });
    });
  };
  const clickReview = async () => act(async () => [...container.querySelectorAll('button')].find((b) => b.textContent.includes('Review and launch')).click());
  const confirm = () => [...container.querySelectorAll('button')].find((b) => b.textContent.includes('Confirm and Launch'));

  it('renders the server checklist names, reasons and summary alongside daily limit labels', async () => {
    installReviewResponses(async () => ({ ok: true, json: async () => ready }));
    await act(async () => root.render(<OutreachCampaignWizard campaignId="new" initialStep={3} />));
    expect(container.textContent).toContain('Sender Resource Assignment');
    expect(container.textContent).toContain('Stored leases match');
    expect(container.textContent).toContain('{{first_name}}');
    expect(container.textContent).toContain('a → b (next)');
    expect(container.textContent).toContain('Connection invites');
    expect(container.textContent).toContain('Email sends');
    expect(container.textContent).toContain('Fresh execution permission is checked by workers');
    expect(container.textContent).toContain('Launch prerequisites met');
    expect(container.textContent).not.toContain('Ready to Launch');
  });

  it('disables normal launch while review refresh is pending or failed', async () => {
    let pending; let fail = false;
    installReviewResponses(() => fail ? new Promise((resolve) => { pending = resolve; }) : Promise.resolve({ ok: true, json: async () => ready }));
    await act(async () => root.render(<OutreachCampaignWizard campaignId="new" initialStep={3} />));
    fail = true; await clickReview();
    expect(confirm().disabled).toBe(true);
    expect(container.textContent).not.toContain('Launch prerequisites met');
    await act(async () => pending({ ok: false, json: async () => ({ detail: 'Readiness unavailable' }) }));
    expect(confirm().disabled).toBe(true); expect(container.textContent).toContain('Readiness unavailable');
    expect(global.fetch.mock.calls.some(([url]) => url.endsWith('/launch'))).toBe(false);
  });

  it('checks the saved prospective inputs again and blocks launch if prerequisites changed', async () => {
    let block = false;
    installReviewResponses(async () => ({ ok: true, json: async () => block ? { ...ready, can_launch: false, blockers: ['Paid term expired'] } : ready }));
    await act(async () => root.render(<OutreachCampaignWizard campaignId="new" initialStep={3} />));
    await clickReview(); expect(confirm().disabled).toBe(false); block = true;
    await act(async () => confirm().click());
    expect(container.textContent).toContain('Paid term expired');
    expect(global.fetch.mock.calls.some(([url]) => url.endsWith('/launch'))).toBe(false);
    const previews = global.fetch.mock.calls.filter(([url]) => url.endsWith('/preflight'));
    expect(JSON.parse(previews.at(-1)[1].body).sender_account_ids).toEqual(['sender-a']);
  });

});
