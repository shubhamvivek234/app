const { test, expect } = require('@playwright/test');

const TAG = { id: `tag_${'a'.repeat(24)}`, name: 'Qualified', color: '#123456', revision: 1 };

test('actual import modal disables unverified search while public profile intake stays available', async ({ page }) => {
  let searchPosts = 0;
  await page.route('**/api/v1/outreach/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body;
    if (path.endsWith('/campaigns')) body = [{ id: 'campaign', name: 'Reviewed campaign', status: 'draft' }];
    else if (path.endsWith('/leads/import-sources')) body = { contract_version: 1, sources: [{
      type: 'basic', parser_supported: true, collection_available: false,
      reason: 'Search filters are not verified. Use CSV or public profile links.' }] };
    else if (path.endsWith('/leads/import-search')) { searchPosts += 1; body = {}; }
    else if (path.endsWith('/leads')) body = { total: 0, leads: [] };
    else if (path.endsWith('/leads/tags') || path.endsWith('/accounts')) body = [];
    else throw new Error(`Unexpected API ${path}`);
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('/?view=leads');
  await page.getByRole('button', { name: 'Import contacts', exact: true }).first().click();
  await expect(page.getByRole('button', { name: /LinkedIn & Sales Nav Search/ })).toBeDisabled();
  await expect(page.getByText('Search filters are not verified.', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: /Paste LinkedIn profile URLs/ }).click();
  await expect(page.getByText('Paste LinkedIn Profile URLs', { exact: true })).toBeVisible();
  expect(searchPosts).toBe(0);
});

test('real Leads component filters, tags a selection, exports and reviews an inactive follow-up draft', async ({ page }) => {
  let tagged = false; let exported = false; let created = false;
  await page.addInitScript(() => localStorage.setItem('outreach_leads_view_mode', 'table'));
  await page.route('**/api/v1/outreach/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let body;
    if (path.endsWith('/campaigns')) body = [];
    else if (path.endsWith('/leads/tags')) body = [TAG];
    else if (path.endsWith('/leads/tags/bulk')) {
      expect(route.request().postDataJSON()).toEqual({ lead_ids: ['lead'], tag_id: TAG.id, operation: 'add' });
      tagged = true; body = { matched_count: 1, modified_count: 1 };
    } else if (path.endsWith('/leads/export')) {
      expect(url.searchParams.get('tag_ids')).toBe(TAG.id); exported = true;
      return route.fulfill({ contentType: 'text/csv', body: 'first_name,tags\nAlex,Qualified\n' });
    } else if (path.endsWith('/leads/selection/context')) {
      body = { request_scope: 'b'.repeat(64) };
    } else if (path.endsWith('/leads/selection/preview')) {
      body = { valid_count: 1, excluded_count: 0, request_scope: 'b'.repeat(64), review_digest: 'a'.repeat(64), rows: [{ source_lead_id: 'lead', first_name: 'Alex', status: 'valid' }] };
    } else if (path.endsWith('/leads/selection/draft')) {
      expect(route.request().postDataJSON()).toMatchObject({ lead_ids: ['lead'], allow_contacted: false, review_digest: 'a'.repeat(64) });
      created = true; body = { campaign_id: 'reviewed-draft', name: 'Follow-up campaign', imported_count: 1 };
    } else if (path.endsWith('/leads')) body = { total: 1, leads: [{ id: 'lead', first_name: 'Alex', tags: tagged ? [TAG] : [], tag_ids: tagged ? [TAG.id] : [] }] };
    else throw new Error(`Unexpected API ${path}`);
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('/?view=leads');
  await page.getByLabel('Select Alex', { exact: true }).check();
  await page.getByRole('button', { name: 'Add tag', exact: true }).click();
  await expect(page.getByText('1 selected', { exact: true })).toHaveCount(0);
  await page.getByLabel('Filter leads by tag').selectOption(TAG.id);
  await expect(page.getByRole('cell', { name: 'Qualified', exact: true })).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export CSV', exact: true }).click(); await download;
  await page.getByLabel('Select Alex', { exact: true }).check();
  await page.getByRole('button', { name: 'Review follow-up draft', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('1 eligible');
  await page.getByRole('button', { name: 'Create draft & configure', exact: true }).click();
  await expect(page.locator('body')).toHaveAttribute('data-opened-draft', 'reviewed-draft');
  expect(tagged && exported && created).toBe(true);
});

test('tag settings keeps immutable identity while editing name and color', async ({ page }) => {
  let current = { ...TAG }; let saved = false;
  await page.route('**/api/v1/outreach/leads/tags**', async (route) => {
    if (route.request().method() === 'PATCH') {
      const payload = route.request().postDataJSON();
      expect(payload).toEqual({ name: 'Ready for review', color: '#abcdef', revision: 1 });
      expect(route.request().url()).toContain(TAG.id); saved = true;
      current = { ...current, ...payload, revision: 2 };
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(current) });
    }
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify([current]) });
  });
  await page.goto('/?view=tags');
  await page.getByLabel('Name for Qualified', { exact: true }).fill('Ready for review');
  await page.getByLabel('Color for Ready for review', { exact: true }).fill('#abcdef');
  await page.getByRole('button', { name: 'Save tag', exact: true }).click();
  await expect(page.getByLabel('Name for Ready for review', { exact: true })).toHaveValue('Ready for review');
  expect(saved).toBe(true);
});
