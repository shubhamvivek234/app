import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachVoice from './OutreachVoice';

let container; let root;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  Object.defineProperty(window, 'crypto', { configurable: true, value: { randomUUID: jest.fn(() => 'stable-request-id') } });
  global.fetch = jest.fn(async url => ({ ok: true, json: async () => url.includes('/accounts') ? [] : {
    studio_enabled: true, voices: [{ id: 'local-voice', name: 'My voice', status: 'active', consent_current: true, assigned_account_ids: [] }],
    jobs: [{ _id: 'held', operation: 'clone', status: 'held_outcome' }] } }));
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); delete global.fetch; jest.restoreAllMocks(); });

test('held jobs explain review and preview queues local identity', async () => {
  await act(async () => root.render(<OutreachVoice />));
  expect(container.textContent).toContain('My voice');
  expect(container.textContent).toContain('Operator review required');
  await act(async () => [...container.querySelectorAll('button')].find(button => button.textContent === 'Preview').click());
  const generate = [...container.querySelectorAll('button')].find(button => button.textContent.includes('Queue preview'));
  expect(generate).toBeDefined();
  await act(async () => generate.click());
  const call = global.fetch.mock.calls.find(([url]) => url.endsWith('/preview'));
  expect(JSON.parse(call[1].body)).toMatchObject({ voice_id: 'local-voice', request_id: 'stable-request-id' });
});
