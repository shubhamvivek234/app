import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachAccounts from './OutreachAccounts';

it('connects a verified session from the Accounts page and refreshes the sender list', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  let connected = false;
  const account = {
    id: 'sender-1', account_name: 'Alex Sender', vanity_name: 'alex',
    status: 'active', country_code: 'US', proxy: { host: '198.51.100.12' },
    limits: { connection_invites: 20, messages: 20 },
  };
  global.fetch = jest.fn((url) => {
    if (url === '/api/v1/outreach/accounts/connect-cookie') {
      connected = true;
      return Promise.resolve({ ok: true, json: async () => account });
    }
    if (url === '/api/v1/outreach/accounts') {
      return Promise.resolve({ ok: true, json: async () => connected ? [account] : [] });
    }
    throw new Error(`Unexpected request: ${url}`);
  });

  try {
    await act(async () => root.render(<OutreachAccounts />));
    expect(container.textContent).toContain('No accounts connected yet');
    await act(async () => [...container.querySelectorAll('button')]
      .find((button) => button.textContent.trim() === 'Connect account').click());
    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
    const input = container.querySelector('#linkedin-li-at');
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, 'li_at=AQvalid; JSESSIONID="ajax:123"');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => container.querySelector('form').dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true })
    ));

    expect(global.fetch.mock.calls.filter(([url]) => url === '/api/v1/outreach/accounts')).toHaveLength(2);
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(container.textContent).toContain('Alex Sender');
    expect(container.textContent).toContain('Active');
  } finally {
    await act(async () => root.unmount());
    container.remove();
    delete global.fetch;
  }
});
