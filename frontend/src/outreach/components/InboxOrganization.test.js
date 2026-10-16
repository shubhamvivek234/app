import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import InboxOrganization from './InboxOrganization';

const organization = (revision = 0, overrides = {}) => ({ editable: true, revision,
  review_digest: String(revision + 1).repeat(64), identity_digest: 'a'.repeat(64),
  is_starred: false, is_archived: false, note: '', ...overrides });
const ok = (data) => ({ ok: true, json: async () => data });
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };

describe('Conversation organization revision and draft safety', () => {
  let container; let root; let row; let request; let onSaved;
  const button = (text) => [...container.querySelectorAll('button')].find((element) => element.textContent === text);
  const render = async (next = row) => { row = next; await act(async () => root.render(
    <InboxOrganization thread={row} request={request} onSaved={onSaved} />)); };
  const click = async (text) => act(async () => button(text).click());
  const type = async (text) => act(async () => {
    const input = container.querySelector('textarea');
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(input, text);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  beforeEach(async () => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
    row = { id: 'thread', organization: organization() };
    request = jest.fn(); onSaved = jest.fn();
    await render();
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); });

  it('sends explicit star/archive values with the reviewed revision', async () => {
    request.mockResolvedValue(ok({ thread_id: 'thread', organization: organization(1, { is_starred: true }) }));
    await click('Star conversation');
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ revision: 0, review_digest: '1'.repeat(64), is_starred: true });
    expect(onSaved).toHaveBeenCalledWith(row, expect.objectContaining({ is_starred: true, revision: 1 }));
  });

  it('keeps note drafts separate across conversations and empty views', async () => {
    await type('Alice note');
    await render({ id: 'other', organization: organization(0, { identity_digest: 'b'.repeat(64) }) });
    expect(container.querySelector('textarea').value).toBe(''); await type('Bob note');
    await render(null); expect(container.textContent).toBe('');
    await render({ id: 'thread', organization: organization() });
    expect(container.querySelector('textarea').value).toBe('Alice note');
  });

  it('preserves newer edits even if they return to the submitted text', async () => {
    const response = deferred(); request.mockReturnValue(response.promise);
    await type('original'); await click('Save note');
    await type('new edit'); await type('original');
    await act(async () => response.resolve(ok({ thread_id: 'thread', organization: organization(1, { note: 'original' }) })));
    expect(container.querySelector('textarea').value).toBe('original');
    expect(button('Use saved note')).toBeDefined();
  });

  it('does not make a stale note current by starring a newer conversation version', async () => {
    await type('older unsaved note');
    await render({ ...row, organization: organization(1, { note: 'another editor' }) });
    expect(button('Save note').disabled).toBe(true);
    request.mockResolvedValue(ok({ thread_id: 'thread', organization: organization(2, { note: 'another editor', is_starred: true }) }));
    await click('Star conversation');
    await render({ ...row, organization: organization(2, { note: 'another editor', is_starred: true }) });
    expect(container.querySelector('textarea').value).toBe('older unsaved note');
    expect(button('Save note').disabled).toBe(true);
    await click('Keep my draft for this version');
    expect(button('Save note').disabled).toBe(false);
  });

  it('holds unconfirmed saves until read-only reload and keeps the draft', async () => {
    request.mockRejectedValueOnce(new Error('Lost response'));
    await type('keep private draft'); await click('Save note');
    expect(button('Save note').disabled).toBe(true); expect(button('Star conversation').disabled).toBe(true);
    request.mockResolvedValueOnce(ok({ ...row, organization: organization(1, { note: 'saved original' }) }));
    await click('Reload conversation');
    expect(request.mock.calls[1]).toEqual(['/api/v1/outreach/inbox/thread']);
    expect(container.querySelector('textarea').value).toBe('keep private draft');
    expect(onSaved).toHaveBeenCalledWith(row, expect.objectContaining({ revision: 1 }));
  });

  it.each(['contradiction', 'wrong identity', 'wrong revision'])('holds a %s success response instead of discarding note text', async (kind) => {
    const result = organization(1, { note: 'draft' });
    if (kind === 'contradiction') result.note = 'different';
    if (kind === 'wrong identity') result.identity_digest = 'b'.repeat(64);
    if (kind === 'wrong revision') result.revision = 2;
    request.mockResolvedValue(ok({ thread_id: 'thread', organization: result }));
    await type('draft'); await click('Save note');
    expect(container.querySelector('textarea').value).toBe('draft');
    expect(button('Save note').disabled).toBe(true); expect(onSaved).not.toHaveBeenCalled();
  });

  it.each([['a'.repeat(64)], { toString: false }])('rejects compound digest projections without crashing', async (identity) => {
    await render({ ...row, organization: organization(0, { identity_digest: identity }) });
    expect(container.textContent).toContain('needs review'); expect(button('Star conversation')).toBeUndefined();
  });

  it('renders saved note text literally and supports an explicit empty clear', async () => {
    await render({ ...row, organization: organization(1, { note: '<script>never execute</script>' }) });
    expect(container.querySelector('script')).toBeNull();
    request.mockResolvedValue(ok({ thread_id: 'thread', organization: organization(2) }));
    await type(''); await click('Save note');
    expect(JSON.parse(request.mock.calls[0][1].body).note).toBe('');
  });

  it('accepts a server note within the Unicode codepoint limit', async () => {
    await render({ ...row, organization: organization(1, { note: '😀'.repeat(2001) }) });
    expect(button('Star conversation').disabled).toBe(false);
    expect(container.querySelector('textarea').value).toBe('😀'.repeat(2001));
  });
});
