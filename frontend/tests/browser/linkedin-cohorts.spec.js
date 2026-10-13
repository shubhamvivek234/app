const { test, expect } = require('@playwright/test');

test('LinkedIn cohort UI never revives mixed rates or invents zeros on unavailable reads', async ({ page }) => {
  let unavailable = false;
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:4179') return route.abort();
    if (url.pathname === '/' || url.pathname === '/bundle.js') return route.continue();
    if (url.pathname.endsWith('/campaigns') || url.pathname.endsWith('/accounts')) return route.fulfill({ json: [] });
    if (url.pathname.endsWith('/analytics')) return route.fulfill({ json: {
      has_connected_account: true, daily_chart: [],
      linkedin_cohorts: { status: unavailable ? 'unavailable' : 'recorded', attribution_window_days: 30 },
      kpis: { requests: { sent: 1, accepted: 2, acceptance_rate: 200,
        cohort: unavailable ? { denominator: null, accepted: null, acceptance_rate: null }
          : { denominator: 1, accepted: 1, acceptance_rate: 100 } } },
    } });
    return route.abort();
  });
  await page.goto('/?view=analytics');
  await expect(page.getByText('1 associated acceptances (100%)', { exact: true })).toBeVisible();
  await expect(page.getByText('1 original sends · 30-day observation window', { exact: true })).toBeVisible();
  await expect(page.getByText('200%', { exact: false })).toHaveCount(0);
  unavailable = true;
  await page.getByRole('button', { name: 'Refresh analytics' }).click();
  await expect(page.getByText('Not available associated acceptances', { exact: true })).toBeVisible();
  await expect(page.getByText('0 associated acceptances', { exact: false })).toHaveCount(0);
  await expect(page.getByText('1 associated acceptances (100%)', { exact: true })).toHaveCount(0);
});
