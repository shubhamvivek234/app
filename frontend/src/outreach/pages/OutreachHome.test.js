import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachHome from './OutreachHome';
import env from '@/env';

jest.mock('../components/ConnectLinkedInModal', () => ({ isOpen, onClose, onAccountConnected }) => (
  isOpen ? <div><button onClick={onClose}>Cancel connection</button><button onClick={() => onAccountConnected({ id: 'sender-1', status: 'active' })}>Connected</button></div> : null
));

const ok = (body) => ({ ok: true, json: async () => body });

describe('Outreach first-run home', () => {
  let container;
  let root;

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    localStorage.clear();
    global.fetch = jest.fn((url) => Promise.resolve(ok(url.includes('/campaigns') ? [] : [])));
    global.EventSource = jest.fn(() => ({ addEventListener: jest.fn(), close: jest.fn() }));
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    delete global.fetch;
    delete global.EventSource;
  });

  it('does not complete account setup when connection is cancelled', async () => {
    await act(async () => root.render(<OutreachHome onNavigate={() => {}} onOpenWizard={() => {}} />));
    expect(container.textContent).toContain('1/3');
    const start = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Start');
    await act(async () => start.click());
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent === 'Cancel connection').click());
    expect(container.textContent).toContain('1/3');
    expect(container.textContent).toContain('Connect your LinkedIn account');
  });

  it('loads the overview with cookie credentials but never embeds a token in the live URL', async () => {
    localStorage.setItem('token', 'private-token');
    await act(async () => root.render(<OutreachHome onNavigate={() => {}} onOpenWizard={() => {}} />));
    expect(global.fetch).toHaveBeenCalledWith('/api/v1/outreach/accounts', expect.objectContaining({ credentials: 'include' }));
    expect(global.EventSource.mock.calls[0][0]).toBe(`${env.BACKEND_URL}/api/v1/outreach/analytics/live-feed`);
    expect(global.EventSource.mock.calls[0][0]).not.toContain('private-token');
  });

  it('starts a first campaign at the lead setup step', async () => {
    const onOpenWizard = jest.fn();
    await act(async () => root.render(<OutreachHome onNavigate={() => {}} onOpenWizard={onOpenWizard} />));
    const starts = [...container.querySelectorAll('button')].filter((button) => button.textContent === 'Start');
    await act(async () => starts[starts.length - 1].click());
    expect(onOpenWizard).toHaveBeenCalledWith('new', 1);
  });
});
