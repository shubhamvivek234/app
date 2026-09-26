import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachEngage from './OutreachEngage';

jest.mock('sonner', () => ({ toast: { error: jest.fn(), success: jest.fn(), info: jest.fn() } }));

const ok = (body) => ({ ok: true, json: async () => body });

describe('Engage review and reporting', () => {
  let root;
  let container;

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    localStorage.clear();
    global.fetch = jest.fn((url) => {
      if (url === '/api/v1/outreach/engage/lists') return Promise.resolve(ok([{ id: 'list_1', name: 'Prospects', contacts_count: 1 }]));
      if (url === '/api/v1/outreach/engage/lists/list_1') return Promise.resolve(ok({ id: 'list_1', name: 'Prospects', contacts: [] }));
      if (url.startsWith('/api/v1/outreach/engage/lists/list_1/posts')) return Promise.resolve(ok({ posts: [], total: 0 }));
      if (url === '/api/v1/outreach/engage/lists/list_1/stats') return Promise.resolve(ok({ pending: 0, liked: 0, commented: 0, discarded: 0, total: 0, contacts: 1 }));
      if (url === '/api/v1/outreach/engage/lists/list_1/drafts') return Promise.resolve(ok({ drafts: [], pending_count: 0 }));
      if (url === '/api/v1/outreach/engage/lists/list_1/report') return Promise.resolve(ok({ list_name: 'Prospects', contacts: 1, posts_fetched: 2, likes_sent: 1, comments_published: 0, contacts_engaged: 1, posts_discarded: 0 }));
      if (url === '/api/v1/outreach/engage/accounts') return Promise.resolve(ok([]));
      if (url === '/api/v1/outreach/styles') return Promise.resolve(ok([]));
      if (url === '/api/v1/outreach/campaigns') return Promise.resolve(ok([]));
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    delete global.fetch;
  });

  it('shows the manual draft queue and a truthful print report', async () => {
    await act(async () => root.render(<OutreachEngage />));
    await act(async () => [...container.querySelectorAll('h3')].find((node) => node.textContent === 'Prospects')?.closest('.cursor-pointer')?.click());
    expect(container.textContent).toContain('Draft & Review');
    expect(container.textContent).toContain('Print / Save as PDF');
    await act(async () => [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Print / Save as PDF')).click());
    expect(container.textContent).toContain('Confirmed likes sent');
    expect(container.textContent).not.toContain('Response rate');
  });

  it('edits and completes a review draft without publishing to LinkedIn', async () => {
    const originalFetch = global.fetch;
    global.fetch = jest.fn((url, options = {}) => {
      if (url === '/api/v1/outreach/engage/lists/list_1/drafts' && options.method === 'PATCH') {
        return Promise.resolve(ok({ id: 'draft_1', status: 'completed' }));
      }
      if (url === '/api/v1/outreach/engage/lists/list_1/drafts') {
        return Promise.resolve(ok({ pending_count: 1, drafts: [{
          id: 'draft_1', author_name: 'Alex', comment_text: 'Original draft',
          post_url: 'https://www.linkedin.com/feed/update/1', status: 'pending',
        }] }));
      }
      return originalFetch(url, options);
    });
    await act(async () => root.render(<OutreachEngage />));
    await act(async () => [...container.querySelectorAll('h3')].find((node) => node.textContent === 'Prospects')?.closest('.cursor-pointer')?.click());
    await act(async () => [...container.querySelectorAll('button')].find((node) => node.textContent.includes('Draft & Review'))?.click());
    const editor = container.querySelector('#draft-draft_1');
    expect(editor.value).toBe('Original draft');
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
      setter.call(editor, 'Reviewed draft');
      editor.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => [...container.querySelectorAll('button')].find((node) => node.textContent === 'Mark done manually')?.click());
    const updateCall = global.fetch.mock.calls.find(([url, options]) => url.endsWith('/drafts/draft_1') && options?.method === 'PATCH');
    expect(JSON.parse(updateCall[1].body)).toMatchObject({ status: 'completed', comment_text: 'Reviewed draft' });
    expect(global.fetch.mock.calls.some(([url]) => /\/comment$|\/like$/.test(url))).toBe(false);
  });
});
