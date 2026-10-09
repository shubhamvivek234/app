import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachIntegrations from './OutreachIntegrations';

jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn(), info: jest.fn(), warning: jest.fn() } }));
const ok = body => ({ ok: true, json: async () => body });

let container;
let root;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  localStorage.clear();
  global.fetch = jest.fn((url, options) => {
    if (url.endsWith('/hubspot')) return Promise.resolve(ok(options?.method === 'POST' ? {} : { connected: false }));
    if (url.endsWith('/slack')) return Promise.resolve(ok({ connected: false }));
    return Promise.resolve(ok([]));
  });
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  jest.restoreAllMocks();
  delete global.fetch;
});

const openApps = async () => {
  await act(async () => root.render(<OutreachIntegrations />));
  const tab = [...container.querySelectorAll('button')].find(button => button.textContent.includes('Connected Apps & Slack'));
  await act(async () => tab.click());
};
const enter = async (id, value) => {
  const input = container.querySelector(`#${id}`);
  expect(input).not.toBeNull();
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
};

test('new workspace can enter both credentials and submit HubSpot setup', async () => {
  await openApps();
  await enter('hubspot-access-token', 'fixture-pat');
  await enter('hubspot-portal-id', '123456');
  expect(container.querySelector('#hubspot-portal-id').required).toBe(true);
  const form = container.querySelector('#hubspot-portal-id').closest('form');
  await act(async () => form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(global.fetch).toHaveBeenCalledWith('/api/v1/outreach/integrations/hubspot', expect.objectContaining({
    method: 'POST', body: JSON.stringify({ access_token: 'fixture-pat', portal_id: '123456', auto_sync_on_reply: false }),
  }));
  expect(container.textContent).toContain('Contacts can be synchronized manually.');
  expect(container.textContent).not.toContain('automatically synced');
});
