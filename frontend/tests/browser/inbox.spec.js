const { test, expect } = require('@playwright/test');

const threads = ['Alice', 'Bob'].map((name, index) => ({
  id: index ? 'b' : 'a', workspace_id: 'synthetic-workspace', account_id: 'synthetic-sender',
  lead_name: name, lead_urn: `synthetic:${name}`, conversation_urn: `synthetic:conversation:${name}`, messages: [], tags: [],
}));

test.beforeEach(async ({ page }) => {
  // No request leaves the loopback harness, including unexpected provider calls.
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:4179') return route.abort();
    if (url.pathname === '/' || url.pathname === '/bundle.js') return route.continue();
    let body = [];
    if (url.pathname === '/api/v1/outreach/inbox') body = threads;
    else if (/\/inbox\/[ab]$/.test(url.pathname)) body = threads.find((row) => url.pathname.endsWith(`/${row.id}`));
    else if (url.pathname.endsWith('/reply')) body = { status: 'queued', job_id: 'synthetic-job' };
    else if (url.pathname.includes('/inbox/jobs/')) body = { status: 'unknown_outcome' };
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('/');
  await expect(page.getByPlaceholder('Reply to Alice...')).toBeVisible();
});

test('recipient switches preserve separate drafts in a real browser', async ({ page }) => {
  await page.getByPlaceholder('Reply to Alice...').fill('Alice private draft');
  await page.getByText('Bob', { exact: true }).click();
  await expect(page.getByPlaceholder('Reply to Bob...')).toHaveValue('');
  await expect(page.getByTitle('Send message')).toBeDisabled();
  await page.getByPlaceholder('Reply to Bob...').fill('Bob private draft');
  await page.getByText('Alice', { exact: true }).click();
  await expect(page.getByPlaceholder('Reply to Alice...')).toHaveValue('Alice private draft');
});

test('unknown acceptance retains the draft and blocks repeat submission', async ({ page }) => {
  let calls = 0;
  page.on('request', (request) => { if (request.url().endsWith('/reply')) calls += 1; });
  await page.getByPlaceholder('Reply to Alice...').fill('Do not replay');
  await page.getByTitle('Send message').click();
  await expect(page.getByText('Check reply status', { exact: true })).toBeVisible();
  await expect(page.getByTitle('Send message')).toBeDisabled();
  await expect(page.getByPlaceholder('Reply to Alice...')).toHaveValue('Do not replay');
  await page.getByText('Check reply status', { exact: true }).click();
  await page.reload();
  await expect(page.getByPlaceholder('Reply to Alice...')).toBeVisible();
  await page.getByPlaceholder('Reply to Alice...').fill('New draft after reload');
  await expect(page.getByTitle('Send message')).toBeDisabled();
  await page.getByText('Check reply status', { exact: true }).click();
  expect(calls).toBe(1);
});
