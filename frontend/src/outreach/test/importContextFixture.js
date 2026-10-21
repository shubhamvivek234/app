// Synthetic contracts for historical component tests; not a data-provider fake.
export const importContextFixture = (campaignId = 'campaign') => ({ contract_version: 1,
  campaign_id: campaignId, workspace_id: 'test-workspace',
  scope_digest: [...campaignId].map((value) => value.charCodeAt(0).toString(16)).join('').padEnd(64, '0').slice(0, 64) });

export const withImportContext = (handler = async () => ({ ok: true, status: 200, json: async () => [] })) => {
  const contexts = new Map();
  return async (url, options = {}) => {
    if (url.includes('/leads/import-context?')) {
      const context = importContextFixture(new URL(url, 'http://test').searchParams.get('campaign_id'));
      contexts.set(context.scope_digest, context);
      return { ok: true, status: 200, json: async () => context };
    }
    const response = await handler(url, options);
    const path = url.split('?')[0];
    if (!response?.ok || !path.startsWith('/api/v1/outreach/leads/') || path.endsWith('/import-sources')) return response;
    const context = contexts.get(options.headers?.['X-Outreach-Import-Scope']);
    if (!context) throw new Error('Synthetic importer request lacks its scoped bootstrap');
    return { ...response, json: async () => ({ ...await response.json(), import_context: context }) };
  };
};
