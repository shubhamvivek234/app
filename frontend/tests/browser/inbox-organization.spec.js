const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  let revision = 0;
  let metadata = { editable: true, revision, identity_digest: 'a'.repeat(64), review_digest: '1'.repeat(64),
    note: '', is_starred: false, is_archived: false };
  const row = () => ({ id: 'a', workspace_id: 'synthetic-workspace', account_id: 'synthetic-sender',
    lead_name: 'Alice', lead_urn: 'person', conversation_urn: 'conversation', messages: [], tags: [], organization: metadata });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:4179') return route.abort();
    if (url.pathname === '/' || url.pathname === '/bundle.js') return route.continue();
    let body = [];
    if (url.pathname.endsWith('/organization')) {
      const changes = route.request().postDataJSON();
      for (const field of ['note', 'is_starred', 'is_archived']) if (field in changes) metadata[field] = changes[field];
      revision += 1; metadata = { ...metadata, revision, review_digest: String(revision + 1).repeat(64) };
      body = { thread_id: 'a', organization: metadata };
    } else if (url.pathname === '/api/v1/outreach/inbox') {
      const view = url.searchParams.get('view');
      body = view === 'archived' ? (metadata.is_archived ? [row()] : [])
        : view === 'inbox' ? (!metadata.is_archived ? [row()] : [])
          : view === 'starred' ? (metadata.is_starred && !metadata.is_archived ? [row()] : []) : [row()];
    } else if (url.pathname === '/api/v1/outreach/inbox/a') body = row();
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Star conversation', exact: true })).toBeVisible();
});

test('star/archive/restore and shared note survive synthetic server reload', async ({ page }) => {
  await page.getByRole('button', { name: 'Star conversation', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Unstar conversation', exact: true })).toBeVisible();
  await page.getByText('Conversation note', { exact: true }).click();
  await page.getByLabel('Conversation note', { exact: true }).fill('<b>Literal workspace note</b>');
  await page.getByRole('button', { name: 'Save note', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Save note', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Archive conversation', exact: true }).click();
  await expect(page.getByPlaceholder('Reply to Alice...')).toHaveCount(0);
  await page.getByLabel('Conversation view').selectOption('archived');
  await expect(page.getByRole('button', { name: 'Move to inbox', exact: true })).toBeVisible();
  await expect(page.getByLabel('Conversation note', { exact: true })).toHaveValue('<b>Literal workspace note</b>');
  await page.getByRole('button', { name: 'Move to inbox', exact: true }).click();
  await page.getByLabel('Conversation view').selectOption('inbox');
  await expect(page.getByRole('button', { name: 'Archive conversation', exact: true })).toBeVisible();
});

test('unsaved note survives an empty archived view', async ({ page }) => {
  await page.getByText('Conversation note', { exact: true }).click();
  await page.getByLabel('Conversation note', { exact: true }).fill('Keep this unsaved note');
  await page.getByLabel('Conversation view').selectOption('archived');
  await expect(page.getByText('No conversations match this view.')).toBeVisible();
  await page.getByLabel('Conversation view').selectOption('inbox');
  await expect(page.getByLabel('Conversation note', { exact: true })).toHaveValue('Keep this unsaved note');
});

test('lost save response holds edits and reload reads the result without replay', async ({ page }) => {
  let patches = 0;
  page.on('request', (request) => { if (request.method() === 'PATCH') patches += 1; });
  await page.route('**/api/v1/outreach/inbox/a/organization', (route) => route.abort());
  await page.getByText('Conversation note', { exact: true }).click();
  await page.getByLabel('Conversation note', { exact: true }).fill('Unconfirmed draft');
  await page.getByRole('button', { name: 'Save note', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Star conversation', exact: true })).toBeDisabled();
  await expect(page.getByLabel('Conversation note', { exact: true })).toHaveValue('Unconfirmed draft');
  await page.getByRole('button', { name: 'Reload conversation', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Star conversation', exact: true })).toBeEnabled();
  expect(patches).toBe(1);
});
