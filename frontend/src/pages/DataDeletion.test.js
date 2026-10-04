import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import DataDeletion from './DataDeletion';

jest.mock('@/components/Footer', () => () => null);
jest.mock('@/components/UnravlerLogo', () => () => null);
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock('react-router-dom', () => ({ Link: ({ children }) => <a>{children}</a> }), { virtual: true });

describe('recorded deletion status', () => {
  let container; let root;
  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    window.scrollTo = jest.fn();
    window.history.replaceState({}, '', '/data-deletion?code=test-code');
    container = document.createElement('div'); document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); delete global.fetch; });

  it.each(['network', 'http'])('keeps completion unverified when the lookup fails: %s', async (failure) => {
    global.fetch = jest.fn(() => failure === 'network' ? Promise.reject(new Error('Test network failure')) : Promise.resolve({ ok: false }));
    await act(async () => root.render(<DataDeletion />));
    expect(container.textContent).toContain('Status: unavailable');
    expect(container.textContent).not.toContain('permanently purged');
    expect(container.textContent).not.toContain('Verified:');
  });

  it.each(['not_found', 'unknown', 'pending'])('renders the recorded non-completion status: %s', async (status) => {
    global.fetch = jest.fn(async () => ({ ok: true, json: async () => ({ confirmation_code: 'test-code', status,
      created_at: status === 'unknown' ? 'None' : null }) }));
    await act(async () => root.render(<DataDeletion />));
    expect(container.textContent).toContain(`Status: ${status}`);
    expect(container.textContent).not.toContain('permanently purged');
    expect(container.textContent).not.toContain('Verified:');
    expect(container.textContent).not.toContain('Invalid Date');
  });

  it('shows completed only when the server records completion and preserves its details', async () => {
    global.fetch = jest.fn(async () => ({ ok: true, json: async () => ({ confirmation_code: 'test-code', status: 'completed',
      details: 'This request has completed its recorded cleanup.', created_at: '2026-10-03T01:00:00Z' }) }));
    await act(async () => root.render(<DataDeletion />));
    expect(container.textContent).toContain('Status: completed');
    expect(container.textContent).toContain('This request has completed its recorded cleanup.');
    expect(container.textContent).not.toContain('Verified:');
  });
});
