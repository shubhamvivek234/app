const { test, expect } = require('@playwright/test');
const ready = { campaign_id: 'synthetic-campaign', can_launch: true, blockers: [],
  checklist: [{ id: 'proxies', name: 'Sender Resource Assignment', passed: true, message: 'Stored proxy leases match; health is not verified' }],
  summary: { variables_detected: ['first_name'], branch_paths: ['root → next'] },
  execution_checks: [{ id: 'permission', message: 'Workers check fresh permission and health before sending' }] };
async function install(page, preflight) {
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:4179') return route.abort();
    if (url.pathname === '/' || url.pathname === '/bundle.js') return route.continue();
    if (url.pathname.endsWith('/preflight')) return preflight(route);
    const body = url.pathname.includes('/auto-draft') ? { id: 'synthetic-campaign', name: 'Synthetic campaign' }
      : url.pathname.endsWith('/accounts') ? [{ id: 'synthetic-sender', status: 'active', account_name: 'Synthetic Sender' }]
      : url.pathname.includes('/leads') ? { leads: [{ id: 'synthetic-lead' }], total: 1 } : {};
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto('/?view=wizard');
  await expect(page.getByText('Launch prerequisites met', { exact: true })).toBeVisible();
}

test('checklist displays actual fields and removes green status on refresh failure', async ({ page }) => {
  let pending = null;
  await install(page, async (route) => pending ? pending(route) : route.fulfill({ json: ready }));
  await expect(page.getByText('Sender Resource Assignment', { exact: true })).toBeVisible();
  await expect(page.getByText('Connection invites', { exact: true })).toBeVisible();
  await expect(page.getByText('Email sends', { exact: true })).toBeVisible();
  await expect(page.getByText('{{first_name}}', { exact: true })).toBeVisible();
  let captured; let release;
  pending = (route) => new Promise((resolve) => { captured = route; release = resolve; });
  await page.getByRole('button', { name: 'Review and launch' }).click();
  await expect(page.getByRole('button', { name: 'Confirm and Launch' })).toBeDisabled();
  await expect(page.getByText('Launch prerequisites met', { exact: true })).toHaveCount(0);
  await expect.poll(() => !!captured).toBe(true);
  await captured.fulfill({ status: 503, json: { detail: 'Synthetic unavailable check' } }); release();
  await expect(page.getByText('Synthetic unavailable check')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Confirm and Launch' })).toBeDisabled();
});

test('normal launch rechecks saved inputs and stops when eligibility changes', async ({ page }) => {
  let block = false; let launches = 0;
  page.on('request', (request) => { if (request.url().endsWith('/launch')) launches += 1; });
  await install(page, (route) => route.fulfill({ json: block ? { ...ready, can_launch: false, blockers: ['Synthetic paid term expired'] } : ready }));
  await page.getByRole('button', { name: 'Review and launch' }).click();
  await expect(page.getByRole('button', { name: 'Confirm and Launch' })).toBeEnabled(); block = true;
  await page.getByRole('button', { name: 'Confirm and Launch' }).click();
  await expect(page.getByText('Synthetic paid term expired', { exact: false }).first()).toBeVisible();
  expect(launches).toBe(0);
});
