import { createImportContextSession } from './importContextSession';

const context = { contract_version: 1, workspace_id: 'w', campaign_id: 'campaign', scope_digest: 'a'.repeat(64) };
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });

describe('server-bound importer session', () => {
  let fetchImpl; let onHold; let current; let server; let session;
  beforeEach(() => {
    current = true; server = { ...context }; onHold = jest.fn();
    fetchImpl = jest.fn(async (url) => url.includes('/import-context?')
      ? response(server) : response({ valid_count: 1, import_context: context }));
    session = createImportContextSession({ campaignId: 'campaign', isCurrent: () => current, onHold, fetchImpl });
  });
  it('adds the original digest, privately bootstraps and verifies around a request', async () => {
    const result = await session.request('/api/v1/outreach/leads/preview', { method: 'POST', headers: { Authorization: 'Bearer original' } });
    expect((await result.json()).valid_count).toBe(1);
    const post = fetchImpl.mock.calls.find(([url]) => url.endsWith('/preview'));
    expect(post[1].headers).toEqual(expect.objectContaining({ Authorization: 'Bearer original', 'X-Outreach-Import-Scope': context.scope_digest }));
    expect(fetchImpl.mock.calls.filter(([url]) => url.includes('/import-context?')).length).toBeGreaterThanOrEqual(2);
    expect(onHold).not.toHaveBeenCalled();
  });
  it.each(['workspace_id', 'scope_digest'])('holds a changed current %s before sending reviewed data', async (field) => {
    await session.bootstrap(); server = { ...context, [field]: field === 'scope_digest' ? 'b'.repeat(64) : 'other' };
    await expect(session.request('/api/v1/outreach/leads/import-csv', { method: 'POST' })).rejects.toThrow();
    expect(fetchImpl.mock.calls.some(([url]) => url.endsWith('/import-csv'))).toBe(false);
    expect(onHold).toHaveBeenCalledTimes(1);
    server = { ...context };
    await expect(session.request('/api/v1/outreach/leads/import-csv', { method: 'POST' })).rejects.toThrow();
  });
  it('suppresses a body after the same-token server context changes during the request', async () => {
    fetchImpl.mockImplementation(async (url) => {
      if (url.includes('/import-context?')) return response(server);
      return { ok: true, status: 200, json: async () => {
        server = { ...context, scope_digest: 'b'.repeat(64) };
        return { imported_count: 1, import_context: context };
      } };
    });
    await expect(session.request('/api/v1/outreach/leads/import-csv', { method: 'POST' })).rejects.toThrow();
    expect(onHold).toHaveBeenCalledTimes(1);
  });
  it.each([null, {}, { ...context, extra: true }, { ...context, contract_version: true },
    { ...context, campaign_id: 'replacement' }])('holds malformed/missing bootstrap %p', async (body) => {
    server = body;
    await expect(session.bootstrap()).rejects.toThrow();
    expect(onHold).toHaveBeenCalledTimes(1);
  });
  it('rejects a successful legacy response without the required original context echo', async () => {
    fetchImpl.mockImplementation(async (url) => url.includes('/import-context?') ? response(context) : response({ imported_count: 1 }));
    await expect(session.request('/api/v1/outreach/leads/import-csv', { method: 'POST' })).rejects.toThrow();
    expect(onHold).toHaveBeenCalledTimes(1);
  });
  it('keeps known HTTP errors recoverable when current context is still confirmed', async () => {
    fetchImpl.mockImplementation(async (url) => url.includes('/import-context?') ? response(context) : response({ detail: 'Paused campaign required' }, 409));
    const result = await session.request('/api/v1/outreach/leads/import-csv', { method: 'POST' });
    expect(result.status).toBe(409); expect(onHold).not.toHaveBeenCalled();
  });
  it('holds an unknown mutation response without replaying it', async () => {
    fetchImpl.mockImplementation(async (url) => { if (url.includes('/import-context?')) return response(context); throw new Error('lost acknowledgement'); });
    await expect(session.request('/api/v1/outreach/leads/import-csv', { method: 'POST' })).rejects.toThrow();
    expect(onHold).toHaveBeenCalledTimes(1);
    expect(fetchImpl.mock.calls.filter(([url]) => url.endsWith('/import-csv'))).toHaveLength(1);
  });
  it('does not hold a newer opening when an older request becomes obsolete', async () => {
    current = false;
    await expect(session.request('/api/v1/outreach/leads/preview')).rejects.toThrow();
    expect(fetchImpl).not.toHaveBeenCalled(); expect(onHold).not.toHaveBeenCalled();
  });
});
