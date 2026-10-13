import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachAnalytics from './OutreachAnalytics';

jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const ok = (value) => ({ ok: true, json: async () => value, blob: async () => new Blob([value], { type: 'text/csv' }) });

describe('OutreachAnalytics component', () => {
  let container;
  let root;

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    localStorage.clear();
    jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    delete global.fetch;
    jest.restoreAllMocks();
  });

  const mockAnalyticsData = {
    has_connected_account: true,
    linkedin_cohorts: { status: 'recorded', attribution_window_days: 30 },
    kpis: {
      requests: {
        sent: 20,
        accepted: 8,
        acceptance_rate: 40.0,
        denominator: 20,
        period_activity: { sent: 20, accepted: 8 },
        cohort: { denominator: 10, accepted: 4, acceptance_rate: 40.0 },
      },
      messages: {
        sent: 10,
        replied: 3,
        reply_rate: 30.0,
        denominator: 10,
        period_activity: { sent: 10, replied: 3 },
        cohort: { denominator: 5, replied: 2, reply_rate: 40.0 },
      },
      engagement: {
        total_actions: 15,
        profile_visits: 10,
        post_engagements: 5,
      },
      email: {
        sent: 0,
        provider_accepted: 0,
        bounced: 0,
        possible_bounced: 0,
        delivery_unknown: 0,
        delivered: null,
        evidence_status: 'recorded',
        deliverability_rate: null,
        denominator: 0,
      },
      pipeline: {
        total_leads: 50,
        in_campaign: 15,
        replied: 3,
        call_booked: 2,
      },
    },
    daily_chart: [
      { date: '25 Sep', sent: 5, accepted: 2, messages_sent: 3, replied: 1, profile_visits: 2, post_engagements: 1 },
      { date: '26 Sep', sent: 8, accepted: 3, messages_sent: 4, replied: 1, profile_visits: 4, post_engagements: 2 },
    ],
  };

  it('renders analytics cards with rate percentages, denominators, and email status', async () => {
    global.fetch = jest.fn((url) => {
      if (url.includes('/campaigns')) {
        return Promise.resolve(ok([{ id: 'camp-1', name: 'Q4 Outbound' }]));
      }
      if (url.includes('/accounts')) {
        return Promise.resolve(ok([{ id: 'sender-1', account_name: 'Alice Sender' }]));
      }
      if (url.includes('/analytics')) {
        return Promise.resolve(ok(mockAnalyticsData));
      }
      return Promise.resolve(ok({}));
    });

    await act(async () => root.render(<OutreachAnalytics />));

    expect(container.textContent).toContain('Analytics');
    expect(container.textContent).toContain('20');
    expect(container.textContent).toContain('4 associated acceptances (40%)');
    expect(container.textContent).toContain('10 original sends · 30-day observation window');

    expect(container.textContent).toContain('10');
    expect(container.textContent).toContain('2 associated replies (40%)');
    expect(container.textContent).toContain('5 original sends · 30-day observation window');

    expect(container.textContent).toContain('Email Outcomes');
    expect(container.textContent).toContain('Delivery unavailable');
    expect(container.textContent).toContain('Provider acceptances recorded in the selected UTC period');
    expect(container.textContent).toContain('0 accepted emails with unknown delivery');
  });

  it('populates sender account filter and updates analytics query on selection', async () => {
    global.fetch = jest.fn((url) => {
      if (url.includes('/campaigns')) {
        return Promise.resolve(ok([{ id: 'camp-1', name: 'Q4 Outbound' }]));
      }
      if (url.includes('/accounts')) {
        return Promise.resolve(ok([
          { id: 'sender-1', account_name: 'Alice Sender' },
          { id: 'sender-2', account_name: 'Bob Rep' },
        ]));
      }
      if (url.includes('/analytics')) {
        return Promise.resolve(ok(mockAnalyticsData));
      }
      return Promise.resolve(ok({}));
    });

    await act(async () => root.render(<OutreachAnalytics />));
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });

    const selects = container.querySelectorAll('select');
    const senderSelect = Array.from(selects).find((sel) => sel.innerHTML.includes('Alice Sender'));
    expect(senderSelect).toBeTruthy();
    expect(senderSelect.textContent).toContain('All senders');
    expect(senderSelect.textContent).toContain('Alice Sender');
    expect(senderSelect.textContent).toContain('Bob Rep');

    // Select Alice Sender
    await act(async () => {
      senderSelect.value = 'sender-1';
      senderSelect.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });

    const calls = global.fetch.mock.calls.map(([callUrl]) => callUrl);
    const senderQueryCall = calls.find((callUrl) => callUrl.includes('sender_account_id=sender-1'));
    expect(senderQueryCall).toBeTruthy();
  });

  it('triggers CSV export request with active filters', async () => {
    global.fetch = jest.fn((url) => {
      if (url.includes('/analytics/export')) {
        return Promise.resolve(ok('date,requests_sent,requests_accepted\n2026-09-25,5,2\n'));
      }
      if (url.includes('/campaigns')) return Promise.resolve(ok([]));
      if (url.includes('/accounts')) return Promise.resolve(ok([]));
      return Promise.resolve(ok(mockAnalyticsData));
    });

    // Mock window.URL methods
    window.URL.createObjectURL = jest.fn(() => 'blob:mock-url');
    window.URL.revokeObjectURL = jest.fn();

    await act(async () => root.render(<OutreachAnalytics />));

    const exportBtn = Array.from(container.querySelectorAll('button')).find((btn) => btn.textContent.includes('Export CSV'));
    expect(exportBtn).toBeTruthy();

    await act(async () => {
      exportBtn.click();
    });

    const exportCall = global.fetch.mock.calls.find(([callUrl]) => callUrl.includes('/analytics/export'));
    expect(exportCall).toBeTruthy();
    expect(exportCall[0]).toContain('timeframe=30d');
  });

  const emailCard = () => Array.from(container.querySelectorAll('span'))
    .find((node) => node.textContent === 'Email Outcomes').parentElement.parentElement;

  const installEmail = (email) => {
    global.fetch = jest.fn((url) => Promise.resolve(ok(url.includes('/campaigns') || url.includes('/accounts')
      ? [] : { ...mockAnalyticsData, kpis: { ...mockAnalyticsData.kpis, email } })));
  };

  it('keeps provider acceptance, reference bounces, possible bounces and unknown delivery distinct', async () => {
    installEmail({ provider_accepted: 4, bounced: 1, possible_bounced: 1, delivery_unknown: 3,
      delivered: 4, deliverability_rate: 100, evidence_status: 'recorded' });
    await act(async () => root.render(<OutreachAnalytics />));
    const card = emailCard().textContent;
    expect(card).toContain('1 recorded reference bounces · 1 possible bounces');
    expect(card).toContain('3 accepted emails with unknown delivery');
    expect(card).toContain('Delivery unavailable');
    expect(card).not.toContain('100%');
    expect(card).not.toContain('4 delivered');
  });

  it('shows partial coverage and human or pending evidence without treating it as provider acceptance', async () => {
    installEmail({ provider_accepted: 0, bounced: 0, possible_bounced: 0, delivery_unknown: 0,
      human_reported: 2, pending_or_unknown_operations: 3, evidence_status: 'partial' });
    await act(async () => root.render(<OutreachAnalytics />));
    expect(emailCard().textContent).toContain('2 human assertions kept separate');
    expect(emailCard().textContent).toContain('3 pending or unknown operations created in this period');
    expect(emailCard().textContent).toContain('Known counts are not a complete history');
  });

  it('preserves unavailable counts through loading and source failure without zero placeholders', async () => {
    let resolve;
    global.fetch = jest.fn((url) => url.includes('/campaigns') || url.includes('/accounts')
      ? Promise.resolve(ok([])) : new Promise((done) => { resolve = done; }));
    await act(async () => root.render(<OutreachAnalytics />));
    expect(emailCard().textContent).toContain('Loading…');
    expect(emailCard().textContent).not.toContain('0 accepted');
    await act(async () => resolve(ok({ ...mockAnalyticsData, kpis: { ...mockAnalyticsData.kpis,
      email: { provider_accepted: null, bounced: null, possible_bounced: null,
        delivery_unknown: null, evidence_status: 'unavailable' } } })));
    expect(emailCard().textContent).toContain('Not available accepted emails with unknown delivery');
    expect(emailCard().textContent).toContain('Email evidence is unavailable');
    expect(emailCard().textContent).not.toContain('0 accepted');
  });

  it('does not revive the legacy mixed-cohort rate when cohort fields are absent', async () => {
    global.fetch = jest.fn((url) => Promise.resolve(ok(url.includes('/campaigns') || url.includes('/accounts')
      ? [] : { ...mockAnalyticsData, linkedin_cohorts: undefined, kpis: {
        ...mockAnalyticsData.kpis, requests: { sent: 1, accepted: 2, acceptance_rate: 200 },
        messages: { sent: 1, replied: 2, reply_rate: 200 } } })));
    await act(async () => root.render(<OutreachAnalytics />));
    expect(container.textContent).not.toContain('200%');
    expect(container.textContent).toContain('Not available associated acceptances');
    expect(container.textContent).toContain('Cohort observations unavailable');
  });

  it('distinguishes empty recorded cohorts from incomplete reads', async () => {
    global.fetch = jest.fn((url) => Promise.resolve(ok(url.includes('/campaigns') || url.includes('/accounts')
      ? [] : { ...mockAnalyticsData, kpis: { ...mockAnalyticsData.kpis,
        requests: { cohort: { denominator: 0, accepted: 0, acceptance_rate: null } } } })));
    await act(async () => root.render(<OutreachAnalytics />));
    expect(container.textContent).toContain('0 associated acceptances');
    expect(container.textContent).toContain('0 original sends · 30-day observation window');
    expect(container.textContent).not.toContain('(0%)');
  });

  it('keeps null cohort counts unavailable and suppresses partial percentages', async () => {
    global.fetch = jest.fn((url) => Promise.resolve(ok(url.includes('/campaigns') || url.includes('/accounts')
      ? [] : { ...mockAnalyticsData, linkedin_cohorts: { status: 'partial', attribution_window_days: 30 },
        kpis: { ...mockAnalyticsData.kpis,
          requests: { cohort: { denominator: null, accepted: null, acceptance_rate: 200 } },
          messages: { cohort: { denominator: 1, replied: 1, reply_rate: 100 } } } })));
    await act(async () => root.render(<OutreachAnalytics />));
    expect(container.textContent).toContain('Not available associated acceptances');
    expect(container.textContent).toContain('Known records only · rates unavailable');
    expect(container.textContent).not.toContain('200%');
    expect(container.textContent).not.toContain('100%');
    expect(container.textContent).not.toContain('0 associated acceptances');
  });

  it('does not show zero cohort observations while loading', async () => {
    let resolve;
    global.fetch = jest.fn((url) => url.includes('/campaigns') || url.includes('/accounts')
      ? Promise.resolve(ok([])) : new Promise((done) => { resolve = done; }));
    await act(async () => root.render(<OutreachAnalytics />));
    expect(container.textContent).toContain('Loading… associated replies');
    expect(container.textContent).not.toContain('0 associated replies');
    await act(async () => resolve(ok(mockAnalyticsData)));
    expect(container.textContent).toContain('2 associated replies (40%)');
  });
});
