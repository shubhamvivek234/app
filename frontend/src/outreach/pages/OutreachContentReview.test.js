import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachContentReview from './OutreachContentReview';

const ok = (value) => ({ ok: true, json: async () => value });
const item = { id: 'review-1', revision: 1, status: 'pending', current: true, action: 'send_message', sender_name: 'Sam', recipient: 'urn:recipient', content: { body: 'Hello Ada\nExact personalized content' } };

describe('exact content review', () => {
  let container; let root;
  const button = (text) => [...container.querySelectorAll('button')].find((value) => value.textContent === text);
  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div'); document.body.appendChild(container);
    root = createRoot(container); localStorage.setItem('token', 'test-token');
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); localStorage.clear(); delete global.fetch; });

  it('shows exact recipient and content, requires review, and sends a revision-bound decision', async () => {
    global.fetch = jest.fn((url, options = {}) => Promise.resolve(ok(url.includes('/campaigns/') ? [] : options.method === 'POST' ? { status: 'recorded' } : { items: [item], total: 1 })));
    await act(async () => root.render(<OutreachContentReview />));
    expect(container.textContent).toContain(item.recipient);
    expect(container.textContent).toContain(item.content.body);
    expect(button('Approve content').disabled).toBe(true);
    await act(async () => container.querySelector('input[type="checkbox"]').click());
    await act(async () => button('Approve content').click());
    const post = global.fetch.mock.calls.find(([, value]) => value.method === 'POST');
    expect(post[0]).toBe('/api/v1/outreach/content-approvals/review-1/decision');
    expect(JSON.parse(post[1].body)).toEqual({ decision: 'approve', revision: 1, reviewed: true });
    expect(post[1].headers.Authorization).toBe('Bearer test-token');
    expect(global.fetch.mock.calls.some(([url]) => url.includes('/launch') || url.includes('/send'))).toBe(false);
  });

  it('cannot approve a stale snapshot', async () => {
    global.fetch = jest.fn((url) => Promise.resolve(ok(url.includes('/campaigns/') ? [] : { items: [{ ...item, current: false }], total: 1 })));
    await act(async () => root.render(<OutreachContentReview />));
    expect(button('Approve content')).toBeUndefined();
    expect(container.textContent).toContain('no longer current');
  });

  it('prepares successive pages without sending or enabling execution', async () => {
    global.fetch = jest.fn((url) => Promise.resolve(ok(url.includes('/campaigns/') ? [{ id: 'c', name: 'Pilot' }] : url.includes('/prepare/') ? { prepared: 50, voice_pending: 0, next_skip: url.includes('skip=0&') ? 50 : null } : { items: [], total: 0 })));
    await act(async () => root.render(<OutreachContentReview />));
    await act(async () => {
      const select = container.querySelector('select');
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, 'c');
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await act(async () => button('Prepare current steps').click());
    expect(global.fetch.mock.calls.filter(([url]) => url.includes('/prepare/')).map(([url]) => url)).toEqual([
      '/api/v1/outreach/content-approvals/prepare/c?skip=0&limit=50', '/api/v1/outreach/content-approvals/prepare/c?skip=50&limit=50',
    ]);
    expect(container.textContent).toContain('100 current steps');
  });

  it('requires playing the complete prepared voice clip before acknowledging review', async () => {
    URL.createObjectURL = jest.fn(() => 'blob:voice-preview'); URL.revokeObjectURL = jest.fn();
    global.fetch = jest.fn((url) => Promise.resolve(url.endsWith('/audio') ? { ok: true, blob: async () => new Blob(['RIFF-clip']) } : ok(url.includes('/campaigns/') ? [] : { items: [{ ...item, action: 'voice_note', has_audio: true }], total: 1 })));
    await act(async () => root.render(<OutreachContentReview />));
    expect(container.querySelector('input').disabled).toBe(true);
    await act(async () => button('Load voice preview').click());
    await act(async () => container.querySelector('audio').dispatchEvent(new Event('ended', { bubbles: true })));
    expect(container.querySelector('input').disabled).toBe(false);
  });

  it('reports queued, held and unavailable recordings truthfully and can refresh', async () => {
    global.fetch = jest.fn((url) => Promise.resolve(ok(url.includes('/campaigns/') ? [{ id: 'c', name: 'Pilot' }] : url.includes('/prepare/') ? { prepared: 0, voice_pending: 4, voice_queued: 2, voice_held: 1, voice_unavailable: 1, next_skip: null } : { items: [], total: 0 })));
    await act(async () => root.render(<OutreachContentReview />));
    await act(async () => {
      const select = container.querySelector('select');
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, 'c');
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await act(async () => button('Prepare current steps').click());
    expect(container.textContent).toContain('2 voice clips queued or preparing');
    expect(container.textContent).toContain('1 generation outcomes need operator review');
    expect(container.textContent).toContain('1 voice clips cannot be prepared');
    expect(container.textContent).toContain('voice provider credits');
    const previous = global.fetch.mock.calls.length;
    await act(async () => button('Refresh reviews').click());
    expect(global.fetch.mock.calls.length).toBe(previous + 1);
    expect(global.fetch.mock.calls.some(([url]) => url.includes('/send') || url.includes('/launch'))).toBe(false);
  });
});
