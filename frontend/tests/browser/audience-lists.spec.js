const { test, expect } = require('@playwright/test');
const LIST = { id: `list_${'a'.repeat(64)}`, campaign_id: 'campaign', name: 'Prospects', revision: 1, review_digest: 'c'.repeat(64), archived: false, collection_verified: false, source_kind: 'manual' };
const SCOPE = 'b'.repeat(64);
const pageBody = (row) => ({ list: row, members: [], membership_count: 0, next_cursor: null, membership_controls_execution: false, complete_collection: false });
async function routes(page, extra) {
  await page.route('**/api/v1/outreach/**', async (route) => {
    const url = new URL(route.request().url()), path = url.pathname;
    const handled = await extra(route, path); if (handled) return;
    let body;
    if (path.endsWith('/campaigns')) body = [{ id: 'campaign', name: 'Campaign', status: 'draft' }];
    else if (path.endsWith('/leads/tags')) body = [];
    else if (path.endsWith('/leads')) body = { total: 0, leads: [] };
    else if (path.endsWith('/lead-lists/import-context')) body = { request_scope: SCOPE };
    else throw new Error(`Unexpected ${path}`);
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
}
const fulfill = (route, body) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });

test('real Leads list UI imports a reviewed prefix and recovers a lost response by original reference', async ({ page }) => {
  let original, completed, submissions = 0;
  await routes(page, async (route, path) => {
    if (path.endsWith('/lead-lists')) { await fulfill(route, { lists: [LIST], membership_controls_execution: false }); return true; }
    if (path.endsWith('/members')) { await fulfill(route, pageBody(LIST)); return true; }
    if (path.endsWith('/import-preview')) {
      expect(route.request().postDataJSON()).toMatchObject({ quantity: 1, source_type: 'pasted_urls' });
      await fulfill(route, { list: LIST, request_scope: SCOPE, rows: [{ row_number: 1, linkedin_url: 'https://www.linkedin.com/in/one', first_name: 'One', status: 'valid' }], more_rows_in_source: true }); return true;
    }
    if (path.endsWith('/import')) {
      submissions++; original = route.request().postDataJSON();
      expect(original).toMatchObject({ campaign_id: 'campaign', revision: 1, review_digest: LIST.review_digest, name_overrides: { '1': 'Edited' } });
      completed = { request_id: original.request_id, request_scope: SCOPE, status: 'completed', list_name: 'Prospects', campaign_id: 'campaign', result: {
        imported_count: 1, skipped_count: 0, duplicates_count: 0, membership_added_count: 1, requested_rows: 1, considered_rows: 1, list_revision: 2,
        lead_ids: ['l1'], row_results: [{ row_number: 1, status: 'imported', lead_id: 'l1' }], more_rows_in_source: true, collection_verified: false } };
      const stored = await page.evaluate(() => sessionStorage.getItem('unravler.audience-imports.v1'));
      expect(stored).toContain(original.request_id); expect(stored).not.toContain('linkedin.com');
      await route.abort('failed'); return true;
    }
    if (path.includes('/lead-lists/imports/')) { expect(path).toContain(original.request_id); await fulfill(route, completed); return true; }
    return false;
  });
  await page.goto('/?view=leads');
  await page.getByRole('button', { name: 'Audience lists', exact: true }).click();
  await page.getByRole('button', { name: 'Import into list', exact: true }).click();
  await page.getByLabel('Audience import text').fill('https://www.linkedin.com/in/one, One\nhttps://www.linkedin.com/in/two, Two');
  await page.getByLabel('Audience requested rows').fill('1');
  await page.getByRole('button', { name: 'Review input rows', exact: true }).click();
  await page.getByLabel('Audience first name row 1').fill('Edited');
  await page.getByRole('button', { name: 'Import reviewed rows', exact: true }).click();
  await expect(page.getByText('The original import is unresolved.', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Check original import', exact: true }).click();
  await expect(page.getByText('Saved to Prospects: 1 contacts and 1 memberships.')).toBeVisible();
  await expect(page.getByText('The full source total is unknown.', { exact: false })).toBeVisible();
  expect(submissions).toBe(1);
});

test('real list UI preserves native review binding when renaming and archiving', async ({ page }) => {
  let row = LIST;
  await routes(page, async (route, path) => {
    if (route.request().method() === 'PATCH') {
      expect(route.request().postDataJSON()).toEqual({ revision: 1, review_digest: LIST.review_digest, name: 'Reviewed prospects' });
      row = { ...LIST, name: 'Reviewed prospects', revision: 2, review_digest: 'd'.repeat(64) }; await fulfill(route, row); return true;
    }
    if (path.endsWith('/archive')) {
      expect(route.request().postDataJSON()).toEqual({ revision: 2, review_digest: 'd'.repeat(64) });
      row = { ...row, archived: true, revision: 3, review_digest: 'e'.repeat(64) }; await fulfill(route, row); return true;
    }
    if (path.endsWith('/lead-lists')) { await fulfill(route, { lists: [row], membership_controls_execution: false }); return true; }
    if (path.endsWith('/members')) { await fulfill(route, pageBody(row)); return true; }
    return false;
  });
  await page.goto('/?view=leads'); await page.getByRole('button', { name: 'Audience lists', exact: true }).click();
  await page.getByLabel('Rename audience list').fill('Reviewed prospects'); await page.getByRole('button', { name: 'Rename list', exact: true }).click();
  await expect(page.getByLabel('Audience list', { exact: true })).toContainText('Reviewed prospects');
  await page.getByRole('button', { name: 'Archive list', exact: true }).click();
  await expect(page.getByText('This list is archived.', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Import into list', exact: true })).toBeDisabled();
});
