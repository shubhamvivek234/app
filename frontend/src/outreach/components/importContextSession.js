const CONTEXT_KEYS = ['campaign_id', 'contract_version', 'scope_digest', 'workspace_id'];
const plainId = (value) => typeof value === 'string' && value.trim() && value.length <= 200;
const validContext = (value, campaignId) => value && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).sort().join(',') === CONTEXT_KEYS.join(',')
  && value.contract_version === 1 && value.campaign_id === campaignId
  && plainId(value.workspace_id) && typeof value.scope_digest === 'string' && /^[a-f0-9]{64}$/.test(value.scope_digest);
const sameContext = (left, right) => CONTEXT_KEYS.every((key) => left[key] === right[key]);

// Current observations only: this neither undoes writes nor recovers unknown results.
export function createImportContextSession({ campaignId, isCurrent, onHold, fetchImpl = (...args) => fetch(...args), headers = {} }) {
  let held = false;
  let original;
  let bootstrapPromise;
  const assertCurrent = () => {
    if (held || !isCurrent()) throw new Error('Import opening changed. Close and review it again.');
  };
  const hold = () => {
    if (!held && isCurrent()) { held = true; onHold(); }
    throw new Error('Import context or result could not be confirmed. Check the original campaign before retrying.');
  };
  const loadContext = async () => {
    assertCurrent();
    const response = await fetchImpl(`/api/v1/outreach/leads/import-context?campaign_id=${encodeURIComponent(campaignId)}`,
      { credentials: 'include', cache: 'no-store', headers });
    const body = await response.json();
    assertCurrent();
    if (!response.ok || !validContext(body, campaignId)) return hold();
    return Object.freeze({ ...body });
  };
  const bootstrap = () => {
    if (!bootstrapPromise) bootstrapPromise = loadContext().then((value) => {
      assertCurrent(); original = value; return value;
    }).catch(() => hold());
    return bootstrapPromise;
  };
  const verify = async () => {
    try {
      const expected = await bootstrap();
      const current = await loadContext();
      assertCurrent();
      if (!sameContext(expected, current)) return hold();
      return expected;
    } catch (failure) {
      if (isCurrent() && !held) return hold();
      throw failure;
    }
  };
  const request = async (url, options = {}) => {
    try {
      const context = await verify();
      assertCurrent();
      const path = url.split('?')[0];
      const bound = path.startsWith('/api/v1/outreach/leads/') && !path.endsWith('/import-sources');
      const response = await fetchImpl(url, { ...options, cache: 'no-store',
        headers: { ...options.headers, ...(bound ? { 'X-Outreach-Import-Scope': context.scope_digest } : {}) } });
      const body = await response.json();
      assertCurrent();
      await verify();
      assertCurrent();
      if (response.ok && bound && (!validContext(body?.import_context, campaignId)
          || !sameContext(original, body.import_context))) return hold();
      return { ok: response.ok, status: response.status, json: async () => { assertCurrent(); return body; } };
    } catch (failure) {
      if (isCurrent() && !held) return hold();
      throw failure;
    }
  };
  return { bootstrap, verify, request };
}
