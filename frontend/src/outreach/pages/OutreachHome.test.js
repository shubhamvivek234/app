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

describe('Activity stream access lifetime', () => {
  let container;
  let root;
  let source;
  let handlers;

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    handlers = {};
    source = { close: jest.fn(), addEventListener: jest.fn((kind, callback) => { handlers[kind] = callback; }) };
    global.EventSource = jest.fn(() => source);
    global.fetch = jest.fn(() => Promise.resolve(ok([])));
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    delete global.fetch;
    delete global.EventSource;
  });

  const emitTask = (id) => handlers.task_completed({ data: JSON.stringify({
    id, task_type: id, timestamp: '2026-10-12T00:00:00Z',
  }) });

  it('clears activity and closes after explicit access termination, ignoring queued events', async () => {
    await act(async () => root.render(<OutreachHome />));
    await act(async () => { handlers.connected(); emitTask('private-before-stop'); });
    expect(container.textContent).toContain('private-before-stop');
    await act(async () => handlers.stream_closed({ data: '{"reason":"access_changed"}' }));
    expect(source.close).toHaveBeenCalledTimes(1);
    expect(container.textContent).not.toContain('private-before-stop');
    expect(container.textContent).toContain('Activity unavailable');
    await act(async () => { handlers.connected(); handlers.heartbeat(); emitTask('late-private'); source.onerror(); });
    expect(container.textContent).not.toContain('late-private');
    expect(container.textContent).not.toContain('Live Feed');
    expect(container.textContent).toContain('Activity unavailable');
  });

  it('clears cached activity on transport error and accepts activity only after a new greeting', async () => {
    await act(async () => root.render(<OutreachHome />));
    await act(async () => { handlers.connected(); emitTask('old-private'); });
    await act(async () => source.onerror());
    expect(container.textContent).not.toContain('old-private');
    await act(async () => { handlers.heartbeat(); emitTask('late-private'); });
    expect(container.textContent).not.toContain('late-private');
    expect(container.textContent).not.toContain('Live Feed');
    await act(async () => { handlers.connected(); emitTask('fresh-task'); });
    expect(container.textContent).toContain('old-private');
    expect(container.textContent).toContain('fresh-task');
    expect(container.textContent).toContain('Live Feed');
  });

  it('closes when access checks are unavailable, without displaying server details', async () => {
    await act(async () => root.render(<OutreachHome />));
    await act(async () => handlers.stream_closed({ data: '{"reason":"unavailable"}' }));
    expect(source.close).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain('Activity unavailable');
    expect(container.textContent).toContain('Refresh to check access again');
    expect(container.textContent).not.toContain('Listening to live outreach pipeline');
  });

  it('deduplicates repeated observations and keeps their history after readmission', async () => {
    await act(async () => root.render(<OutreachHome />));
    await act(async () => { handlers.connected(); emitTask('same-task'); emitTask('same-task'); });
    expect(container.textContent.match(/same-task/g)).toHaveLength(1);
    await act(async () => source.onerror());
    expect(container.textContent).not.toContain('same-task');
    await act(async () => { handlers.connected(); emitTask('same-task'); });
    expect(container.textContent.match(/same-task/g)).toHaveLength(1);
  });

  it('explains unavailable resume without showing a complete history claim', async () => {
    await act(async () => root.render(<OutreachHome />));
    await act(async () => handlers.stream_closed({ data: '{"reason":"resume_unavailable"}' }));
    expect(container.textContent).toContain('saved activity position is no longer available');
    expect(container.textContent).toContain('does not verify sends, replies, or campaign health');
  });
});
