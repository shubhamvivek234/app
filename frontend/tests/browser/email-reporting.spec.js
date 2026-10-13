const { test, expect } = require('@playwright/test');

test('stored email evidence stays distinct from delivery and becomes unavailable on incomplete reads', async ({ page }) => {
  let unavailable = false;
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:4179') return route.abort();
    if (url.pathname === '/' || url.pathname === '/bundle.js') return route.continue();
    if (url.pathname.endsWith('/campaigns') || url.pathname.endsWith('/accounts')) return route.fulfill({ json: [] });
    if (url.pathname.endsWith('/analytics')) return route.fulfill({ json: {
      has_connected_account: true, daily_chart: [], kpis: { email: unavailable
        ? { provider_accepted: null, bounced: null, possible_bounced: null, delivery_unknown: null, evidence_status: 'unavailable' }
        : { provider_accepted: 2, bounced: 0, possible_bounced: 1, delivery_unknown: 2,
          delivered: null, deliverability_rate: null, evidence_status: 'recorded' } },
    } });
    return route.abort();
  });
  await page.goto('/?view=analytics');
  await expect(page.getByText('2 accepted emails with unknown delivery', { exact: true })).toBeVisible();
  await expect(page.getByText('0 recorded reference bounces · 1 possible bounces', { exact: true })).toBeVisible();
  await expect(page.getByText('Delivery unavailable', { exact: true })).toBeVisible();
  unavailable = true;
  await page.getByRole('button', { name: 'Refresh analytics' }).click();
  await expect(page.getByText('Email evidence is unavailable. Retry or narrow the filters.', { exact: true })).toBeVisible();
  await expect(page.getByText('2 accepted emails with unknown delivery', { exact: true })).toHaveCount(0);
  await expect(page.getByText('0 accepted emails with unknown delivery', { exact: true })).toHaveCount(0);
});
