import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachInbox from './OutreachInbox';

jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
const org = (revision, changes = {}) => ({ editable: true, revision, identity_digest: 'a'.repeat(64),
  review_digest: String(revision + 1).repeat(64), is_starred: false, is_archived: false, note: '', ...changes });
const ok = (data) => ({ ok: true, json: async () => data });
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };

describe('Inbox organization view integration', () => {
  let root; let container; let row; let list; let saved;
  const button = (text) => [...container.querySelectorAll('button')].find((item) => item.textContent === text);
  const changeView = async (view) => act(async () => {
    const select = container.querySelector('select[aria-label="Conversation view"]');
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, view);
    select.dispatchEvent(new Event('change', { bubbles: true })); jest.advanceTimersByTime(0);
  });
  beforeEach(async () => {
    jest.useFakeTimers(); global.IS_REACT_ACT_ENVIRONMENT = true; sessionStorage.clear();
    HTMLElement.prototype.scrollIntoView = jest.fn();
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    row = { id: 'a', workspace_id: 'w', account_id: 'sender', lead_name: 'Alice',
      lead_urn: 'person', conversation_urn: 'conversation', tags: [], messages: [], organization: org(0) };
    list = () => [row]; saved = deferred();
    global.fetch = jest.fn(async (url, options = {}) => {
      if (url.includes('/inbox?')) return ok(list(url));
      if (options.method === 'PATCH') return saved.promise;
      if (url === '/api/v1/outreach/inbox/a') return ok(row);
      return ok([]);
    });
    await act(async () => root.render(<OutreachInbox />));
    await act(async () => jest.advanceTimersByTime(0));
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); jest.useRealTimers(); delete global.fetch; });

  it('retains unsaved notes through an empty filter and uses server view parameters', async () => {
    await act(async () => {
      const input = container.querySelector('#conversation-note');
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(input, 'unsaved note');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    list = (url) => url.includes('view=archived') ? [] : [row];
    await changeView('archived'); await act(async () => jest.advanceTimersByTime(0));
    expect(container.querySelector('#conversation-note')).toBeNull();
    await changeView('all'); await act(async () => jest.advanceTimersByTime(0));
    expect(container.querySelector('#conversation-note').value).toBe('unsaved note');
    expect(global.fetch.mock.calls.some(([url]) => url.includes('view=archived'))).toBe(true);
  });

  it('a delayed save acknowledgement cannot replace a newer reloaded projection', async () => {
    await act(async () => button('Star conversation').click());
    row = { ...row, organization: org(2, { is_starred: true, note: 'newer editor note' }) };
    await changeView('all'); await act(async () => jest.advanceTimersByTime(0));
    expect(container.querySelector('#conversation-note').value).toBe('newer editor note');
    // Subsequent list reads may still return a lagging snapshot.
    list = () => [{ ...row, organization: org(1, { is_starred: true }) }];
    await act(async () => saved.resolve(ok({ thread_id: 'a', organization: org(1, { is_starred: true }) })));
    expect(container.querySelector('#conversation-note').value).toBe('newer editor note');
  });
});
