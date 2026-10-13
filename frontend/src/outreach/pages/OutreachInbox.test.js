import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { toast } from 'sonner';
import OutreachInbox from './OutreachInbox';

jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
const ok = (data) => ({ ok: true, json: async () => data });
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };
const makeThread = (id, name, scope = {}) => ({ id, lead_name: name, workspace_id: 'workspace',
  account_id: 'sender', lead_urn: `urn:${id}`, conversation_urn: `conversation:${id}`, messages: [], tags: [], ...scope });

describe('Inbox recipient and draft revision binding', () => {
  let container; let root; let threads; let completion; let replyResponse;
  const input = () => container.querySelector('textarea');
  const type = async (text) => act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(input(), text);
    input().dispatchEvent(new Event('input', { bubbles: true }));
  });
  const select = async (name) => act(async () => {
    [...container.querySelectorAll('span')].find((span) => span.textContent === name).click();
  });
  const send = async () => act(async () => container.querySelector('button[title="Send message"]').click());
  const finish = async (job = { status: 'completed', result: { message: { id: 'sent', body: 'Alice text', sender_type: 'me' } } }) => {
    await act(async () => { jest.advanceTimersByTime(2000); });
    await act(async () => completion.resolve(ok(job)));
  };
  beforeEach(async () => {
    jest.useFakeTimers(); jest.clearAllMocks(); global.IS_REACT_ACT_ENVIRONMENT = true;
    sessionStorage.clear();
    Object.defineProperty(window, 'crypto', { configurable: true, value: { randomUUID: () => '00000000-0000-4000-8000-000000000001' } });
    HTMLElement.prototype.scrollIntoView = jest.fn();
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    threads = [makeThread('a', 'Alice'), makeThread('b', 'Bob')]; completion = deferred(); replyResponse = ok({ status: 'queued', job_id: 'job' });
    global.fetch = jest.fn((url, options = {}) => {
      if (url.startsWith('/api/v1/outreach/inbox?')) return Promise.resolve(ok(threads));
      if (url === '/api/v1/outreach/inbox/jobs/job') return completion.promise;
      if (url.endsWith('/reply')) return Promise.resolve(replyResponse);
      if (/\/inbox\/[ab]$/.test(url)) return Promise.resolve(ok(threads.find((thread) => url.endsWith(`/${thread.id}`))));
      return Promise.resolve(ok([]));
    });
    await act(async () => root.render(<OutreachInbox />));
    await act(async () => jest.advanceTimersByTime(0));
  });
  afterEach(async () => {
    await act(async () => root.unmount()); container.remove(); jest.useRealTimers(); jest.restoreAllMocks(); delete global.fetch;
  });

  it('keeps Alice and Bob drafts separate and submits only the selected recipient text', async () => {
    await type('Alice private text'); await select('Bob'); expect(input().value).toBe('');
    expect(container.querySelector('button[title="Send message"]').disabled).toBe(true);
    await type('Bob text'); await select('Alice'); expect(input().value).toBe('Alice private text');
    await select('Bob'); await send();
    expect(global.fetch).toHaveBeenCalledWith('/api/v1/outreach/inbox/b/reply', expect.objectContaining({ body: JSON.stringify({ body: 'Bob text',
      request_id: '00000000-0000-4000-8000-000000000001', context: { account_id: 'sender', conversation_urn: 'conversation:b', thread_revision: 0 } }) }));
    await finish(); await select('Alice'); expect(input().value).toBe('Alice private text');
  });

  it('preserves a newer same-thread edit when an earlier reply completes', async () => {
    await type('Alice text'); await send(); await type('New unsent edit'); await finish();
    expect(input().value).toBe('New unsent edit');
  });

  it('preserves a different recipient draft when an earlier reply completes', async () => {
    await type('Alice text'); await send(); await select('Bob'); await type('Bob unsent text'); await finish();
    expect(input().value).toBe('Bob unsent text');
    await select('Alice'); expect(input().value).toBe('');
  });

  it('retains uncertain reply text and prevents blind resend after unknown outcome', async () => {
    await type('Alice text'); await send(); await finish({ status: 'unknown_outcome' });
    expect(input().value).toBe('Alice text');
    expect(container.querySelector('button[title="Send message"]').disabled).toBe(true);
    expect(container.textContent).toContain('Check reply status');
    expect(toast.success).not.toHaveBeenCalledWith('Reply dispatched');
  });

  it('does not reuse a draft when the same thread ID is rebound to another sender', async () => {
    await type('Alice private text'); await select('Bob');
    threads[0] = makeThread('a', 'Alice', { account_id: 'other-sender' });
    await type('Bob text');
    await select('Alice'); expect(input().value).toBe('');
  });

  it('recovers a lost reply acknowledgement after remount without another submission', async () => {
    replyResponse = Promise.reject(new Error('synthetic lost response'));
    // Attach a handler now; fetch adopts this rejection when Send is clicked.
    replyResponse.catch(() => {});
    await type('Private text stays out of storage'); await send();
    expect(sessionStorage.getItem('unravler.inbox.reply-holds.v1')).not.toContain('Private text');
    await act(async () => root.unmount()); root = createRoot(container);
    await act(async () => root.render(<OutreachInbox />));
    await act(async () => jest.advanceTimersByTime(0));
    await type('A newer draft');
    expect(container.querySelector('button[title="Send message"]').disabled).toBe(true);
    global.fetch.mockImplementationOnce(async () => ok({ status: 'completed', result: { message: { id: 'original', body: 'Original accepted text' } } }));
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent === 'Check reply status').click());
    expect(global.fetch.mock.calls.filter(([url]) => url.endsWith('/reply'))).toHaveLength(1);
    expect(global.fetch.mock.calls.some(([url]) => url.includes('/inbox/requests/'))).toBe(true);
    expect(input().value).toBe('A newer draft');
    expect(container.querySelector('button[title="Send message"]').disabled).toBe(false);
  });
});
