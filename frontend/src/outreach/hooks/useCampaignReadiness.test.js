import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import useCampaignReadiness from './useCampaignReadiness';
const ok = (data) => ({ ok: true, json: async () => data });
const ready = (id) => ({ campaign_id: id, can_launch: true, checklist: [], blockers: [] });
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };
function Harness({ id = 'a', sender = 'one' }) {
  const result = useCampaignReadiness(id, { sender_account_ids: [sender] }, true);
  return <div><button onClick={() => result.refresh()}>Refresh</button>
    <p>{result.loading ? 'Checking' : result.error || (result.data?.can_launch ? `Eligible ${result.data.campaign_id}` : 'Unknown')}</p></div>;
}
describe('Campaign readiness request lifetime', () => {
  let container; let root;
  beforeEach(() => { global.IS_REACT_ACT_ENVIRONMENT = true; localStorage.clear(); container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); delete global.fetch; });
  it('clears the previous green result during a refresh and on failure', async () => {
    const pending = deferred(); global.fetch = jest.fn().mockResolvedValueOnce(ok(ready('a'))).mockReturnValueOnce(pending.promise);
    await act(async () => root.render(<Harness />)); expect(container.textContent).toContain('Eligible a');
    await act(async () => container.querySelector('button').click()); expect(container.textContent).toContain('Checking'); expect(container.textContent).not.toContain('Eligible');
    await act(async () => pending.resolve({ ok: false, json: async () => ({ detail: 'Unavailable' }) }));
    expect(container.textContent).toContain('Unavailable'); expect(container.textContent).not.toContain('Eligible');
  });
  it('discards an earlier campaign response after the selection changes', async () => {
    const old = deferred(); global.fetch = jest.fn().mockReturnValueOnce(old.promise).mockResolvedValue(ok(ready('b')));
    await act(async () => root.render(<Harness />)); await act(async () => root.render(<Harness id="b" />));
    await act(async () => old.resolve(ok(ready('a')))); expect(container.textContent).toContain('Eligible b'); expect(container.textContent).not.toContain('Eligible a');
    expect(global.fetch.mock.calls[0][1].signal.aborted).toBe(true);
  });
  it('discards a stale result after sender inputs change', async () => {
    const old = deferred(); const fresh = deferred(); global.fetch = jest.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
    await act(async () => root.render(<Harness />)); await act(async () => root.render(<Harness sender="two" />));
    await act(async () => old.resolve(ok(ready('a')))); expect(container.textContent).not.toContain('Eligible');
    expect(JSON.parse(global.fetch.mock.calls[1][1].body).sender_account_ids).toEqual(['two']);
    await act(async () => fresh.resolve(ok(ready('a')))); expect(container.textContent).toContain('Eligible a');
  });
  it('does not use a result received after logout', async () => {
    localStorage.setItem('token', 'synthetic'); const pending = deferred(); global.fetch = jest.fn(() => pending.promise);
    await act(async () => root.render(<Harness />)); localStorage.removeItem('token');
    await act(async () => pending.resolve(ok(ready('a')))); expect(container.textContent).not.toContain('Eligible');
  });
  it('rejects malformed or different-campaign successful responses', async () => {
    global.fetch = jest.fn().mockResolvedValueOnce(ok({ can_launch: true })).mockResolvedValueOnce(ok(ready('foreign')));
    await act(async () => root.render(<Harness />)); expect(container.textContent).toContain('could not be verified');
    await act(async () => container.querySelector('button').click()); expect(container.textContent).toContain('could not be verified'); expect(container.textContent).not.toContain('Eligible');
  });
  it('keeps the newest refresh when an older request completes later', async () => {
    const old = deferred(); global.fetch = jest.fn().mockReturnValueOnce(old.promise).mockResolvedValueOnce(ok(ready('a')));
    await act(async () => root.render(<Harness />)); await act(async () => container.querySelector('button').click());
    await act(async () => old.resolve({ ok: false, json: async () => ({ detail: 'Old failure' }) })); expect(container.textContent).toContain('Eligible a');
  });
});
