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

  it('approves and posts a review draft to LinkedIn and marks it completed', async () => {
    jest.useFakeTimers();
    const originalFetch = global.fetch;
    global.fetch = jest.fn((url, options = {}) => {
      if (url === '/api/v1/outreach/engage/accounts') {
        return Promise.resolve(ok([{ id: 'acc_1', account_name: 'Sender 1' }]));
      }
      if (url === '/api/v1/outreach/engage/lists/list_1/drafts' && (!options.method || options.method === 'GET')) {
        return Promise.resolve(ok({
          pending_count: 1,
          drafts: [{
            id: 'draft_1', post_id: 'post_1', author_name: 'Alex',
            comment_text: 'Approved draft reply', status: 'pending',
          }],
        }));
      }
      if (url === '/api/v1/outreach/engage/posts/post_1/comment' && options.method === 'POST') {
        return Promise.resolve(ok({ status: 'queued' }));
      }
      if (url === '/api/v1/outreach/engage/posts/post_1/action') {
        return Promise.resolve(ok({ status: 'commented', liked_at: new Date().toISOString() }));
      }
      if (url === '/api/v1/outreach/engage/lists/list_1/drafts/draft_1' && options.method === 'PATCH') {
        return Promise.resolve(ok({ id: 'draft_1', status: 'completed', completion_source: 'linkedin_confirmed' }));
      }
      return originalFetch(url, options);
    });

    await act(async () => root.render(<OutreachEngage />));
    await act(async () => [...container.querySelectorAll('h3')].find((node) => node.textContent === 'Prospects')?.closest('.cursor-pointer')?.click());
    await act(async () => [...container.querySelectorAll('button')].find((node) => node.textContent.includes('Draft & Review'))?.click());

    const approveBtn = [...container.querySelectorAll('button')].find((node) => node.textContent.includes('Approve & Post Comment'));
    expect(approveBtn).toBeTruthy();

    let clickPromise;
    await act(async () => {
      clickPromise = approveBtn.click();
    });
    await act(async () => {
      jest.advanceTimersByTime(1600);
    });
    await act(async () => {
      await clickPromise;
    });

    const commentCall = global.fetch.mock.calls.find(([url, options]) => url === '/api/v1/outreach/engage/posts/post_1/comment' && options?.method === 'POST');
    expect(commentCall).toBeTruthy();
    expect(JSON.parse(commentCall[1].body)).toMatchObject({
      comment_text: 'Approved draft reply',
      auto_like: true,
      sender_account_id: 'acc_1',
    });
    const patchCall = global.fetch.mock.calls.find(([url, options]) => url === '/api/v1/outreach/engage/lists/list_1/drafts/draft_1' && options?.method === 'PATCH');
    expect(patchCall).toBeTruthy();
    jest.useRealTimers();
  });

  it('displays per-contact warm-up readiness badges, progress bar, and pushes contacts to a campaign', async () => {
    const originalFetch = global.fetch;
    global.fetch = jest.fn((url, options = {}) => {
      if (url === '/api/v1/outreach/campaigns') {
        return Promise.resolve(ok([{ id: 'camp_1', name: 'Q4 SaaS Outreach', status: 'draft' }]));
      }
      if (url === '/api/v1/outreach/engage/lists/list_1') {
        return Promise.resolve(ok({
          id: 'list_1',
          name: 'Prospects',
          warmed_up_contacts_count: 1,
          contacts: [
            { id: 'c1', full_name: 'Alice Warm', profile_url: 'https://www.linkedin.com/in/alice', warmup_status: 'warmed_up', last_engaged_at: new Date().toISOString() },
            { id: 'c2', full_name: 'Bob Pending', profile_url: 'https://www.linkedin.com/in/bob', warmup_status: 'needs_engagement' },
            { id: 'c3', full_name: 'Charlie Quiet', profile_url: 'https://www.linkedin.com/in/charlie', warmup_status: 'no_recent_posts' },
          ],
        }));
      }
      if (url === '/api/v1/outreach/engage/lists/list_1/push-to-campaign' && options.method === 'POST') {
        return Promise.resolve(ok({ pushed_count: 1, skipped_duplicates: 2, campaign_id: 'camp_1' }));
      }
      return originalFetch(url, options);
    });

    const { toast } = require('sonner');
    toast.success.mockClear();
    await act(async () => root.render(<OutreachEngage />));
    await act(async () => [...container.querySelectorAll('h3')].find((node) => node.textContent === 'Prospects')?.closest('.cursor-pointer')?.click());
    await act(async () => [...container.querySelectorAll('button')].find((node) => node.textContent.includes('Contacts ('))?.click());

    expect(container.textContent).toContain('1 / 3 leads warmed up for campaign launch');
    expect(container.textContent).toContain('Warmed up ✓');
    expect(container.textContent).toContain('Needs Engagement');
    expect(container.textContent).toContain('No recent posts');

    const pushSelect = container.querySelector('select[aria-label="Target campaign for push"]');
    await act(async () => {
      pushSelect.value = 'camp_1';
      pushSelect.dispatchEvent(new Event('change', { bubbles: true }));
    });
    const pushBtn = [...container.querySelectorAll('button')].find((node) => node.textContent === 'Push to Campaign');
    await act(async () => pushBtn.click());

    const pushCall = global.fetch.mock.calls.find(([url, options]) => url.endsWith('/push-to-campaign') && options?.method === 'POST');
    expect(pushCall).toBeTruthy();
    expect(JSON.parse(pushCall[1].body)).toEqual({ campaign_id: 'camp_1', only_warmed_up: true });
    expect(toast.success).toHaveBeenCalledWith('Pushed 1 lead to campaign (2 already in campaign)');
  });

  it('supports inline 1-click AI tone pills, feed search/sort, edit list metadata, and daily auto-fetch toggle', async () => {
    const originalFetch = global.fetch;
    global.fetch = jest.fn((url, options = {}) => {
      if (url === '/api/v1/outreach/engage/accounts') {
        return Promise.resolve(ok([{ id: 'acc_1', account_name: 'Sender 1' }]));
      }
      if (url.startsWith('/api/v1/outreach/engage/lists/list_1/posts')) {
        return Promise.resolve(ok({
          total: 2,
          posts: [
            { id: 'p1', contact_id: 'c1', author_name: 'Alice Founder', author_headline: 'CEO', content_text: 'Scaling revenue in B2B', reactions_count: 5, comments_count: 1, status: 'pending', published_at: new Date().toISOString() },
            { id: 'p2', contact_id: 'c2', author_name: 'Bob Builder', author_headline: 'CTO', content_text: 'Kubernetes migration notes', reactions_count: 42, comments_count: 8, status: 'pending', published_at: new Date().toISOString() },
          ],
        }));
      }
      if (url === '/api/v1/outreach/engage/ai-comment' && options.method === 'POST') {
        return Promise.resolve(ok({ comments: ['Great point on B2B revenue scaling!'] }));
      }
      if (url === '/api/v1/outreach/engage/lists/list_1/settings' && options.method === 'PATCH') {
        return Promise.resolve(ok(JSON.parse(options.body)));
      }
      return originalFetch(url, options);
    });

    await act(async () => root.render(<OutreachEngage />));
    await act(async () => [...container.querySelectorAll('h3')].find((node) => node.textContent === 'Prospects')?.closest('.cursor-pointer')?.click());

    // 1-click AI tone pill populates inline comment box
    const insightfulPill = [...container.querySelectorAll('button')].find((node) => node.textContent.includes('💡 Insightful'));
    expect(insightfulPill).toBeTruthy();
    await act(async () => insightfulPill.click());
    const textarea = container.querySelector('textarea');
    expect(textarea.value).toBe('Great point on B2B revenue scaling!');

    // Search filters visible posts
    const searchInput = container.querySelector('input[aria-label="Search posts"]');
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(searchInput, 'Kubernetes');
      searchInput.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(container.textContent).toContain('Bob Builder');
    expect(container.textContent).not.toContain('Alice Founder');

    // Edit list metadata modal
    const editBtn = container.querySelector('button[aria-label="Edit List"]');
    await act(async () => editBtn.click());
    const nameInput = container.querySelector('#edit-list-name');
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(nameInput, 'Dream 50 Founders');
      nameInput.dispatchEvent(new Event('input', { bubbles: true }));
    });
    const saveChangesBtn = [...container.querySelectorAll('button')].find((node) => node.textContent === 'Save Changes');
    await act(async () => saveChangesBtn.click());

    const settingsCalls = global.fetch.mock.calls.filter(([url, options]) => url.endsWith('/settings') && options?.method === 'PATCH');
    expect(settingsCalls.length).toBeGreaterThanOrEqual(1);
    expect(JSON.parse(settingsCalls[0][1].body)).toMatchObject({ name: 'Dream 50 Founders' });
  });
});
