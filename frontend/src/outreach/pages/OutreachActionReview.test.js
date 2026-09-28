import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachActionReview from './OutreachActionReview';

const ok = (value) => ({ ok: true, json: async () => value });

describe('uncertain action review', () => {
  let container;
  let root;

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    localStorage.setItem('token', 'test-token');
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    localStorage.clear();
    delete global.fetch;
  });

  it('requires an explicit evidenced assertion and never resumes or resends automatically', async () => {
    const item = {
      id: 'lead-1:step-1', task_type: 'send_email', status: 'uncertain',
      lead_name: 'Ada Lovelace', lead_email: 'ada@example.com', campaign_name: 'Pilot',
      campaign_status: 'paused', sender_name: 'Sam', can_confirm: true,
      reason: 'The provider outcome is unknown.',
    };
    global.fetch = jest.fn((url, options = {}) => Promise.resolve(options.method === 'POST'
      ? ok({ id: item.id, status: 'accepted', campaign_status: 'paused' })
      : ok({ items: [item], total: 1 })));
    await act(async () => root.render(<OutreachActionReview />));
    expect(container.textContent).toContain('Ada Lovelace');
    expect(container.textContent).toContain('never retries an uncertain action automatically');

    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent === 'Review action').click());
    const submit = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Record decision');
    expect(submit.disabled).toBe(true);
    const evidence = container.querySelector('#review-evidence');
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(evidence, 'Confirmed the message in Gmail Sent folder');
      evidence.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => container.querySelector('input[type="checkbox"]').click());
    expect(submit.disabled).toBe(false);
    await act(async () => submit.click());

    const post = global.fetch.mock.calls.find(([, options]) => options.method === 'POST');
    expect(post[0]).toContain('/action-reviews/lead-1%3Astep-1/resolve');
    expect(JSON.parse(post[1].body)).toEqual({
      decision: 'confirmed_sent', evidence_note: 'Confirmed the message in Gmail Sent folder', acknowledged: true,
    });
    expect(post[1].credentials).toBe('include');
    expect(container.textContent).toContain('campaign remains paused');
    expect(global.fetch.mock.calls.some(([url]) => url.includes('/campaigns/') || url.includes('/send'))).toBe(false);
  });

  it('does not offer a sent assertion when the email operation record is missing', async () => {
    global.fetch = jest.fn(() => Promise.resolve(ok({
      items: [{
        id: 'lead-2:step-2', task_type: 'send_email', status: 'uncertain', lead_name: 'Review lead',
        campaign_name: 'Pilot', campaign_status: 'paused', sender_name: 'Sam', can_confirm: false,
      }], total: 1,
    })));
    await act(async () => root.render(<OutreachActionReview />));
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent === 'Review action').click());
    expect(container.textContent).not.toContain('Confirmed sent in provider account');
    expect(container.textContent).toContain('Not sent — stop this lead');
  });
});
