const { test, expect } = require('@playwright/test');

// Compile actual components; every API and external resource is intercepted.
async function isolate(page, handle) {
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:4179') return route.abort();
    if (url.pathname === '/' || url.pathname === '/bundle.js') return route.continue();
    return handle(route, url.pathname);
  });
}

test('reopening preserves working hours and never substitutes an unavailable saved sender', async ({ page }) => {
  const writes = [];
  const saved = { id: 'existing', name: 'Early hours', status: 'paused', sender_account_ids: ['original-sender'],
    schedule: { days: [0, 2, 4], start_time: '07:00', end_time: '11:00', timezone: 'Asia/Kolkata' } };
  await isolate(page, async (route, path) => {
    let body = {};
    if (path.endsWith('/accounts')) body = [{ id: 'other-sender', account_name: 'Other Sender', status: 'active' }];
    else if (path.endsWith('/auto-draft')) { writes.push(route.request().postDataJSON()); body = saved; }
    else if (path.endsWith('/campaigns/existing')) body = saved;
    else if (path.endsWith('/preflight')) body = { can_launch: false, blockers: ['Original sender requires review'], checklist: [], summary: {} };
    else if (path.endsWith('/leads')) body = { leads: [], total: 0 };
    return route.fulfill({ json: body });
  });
  await page.goto('/?view=wizard&campaign=existing');
  await expect(page.getByText('Previously selected senders are unavailable.', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Save and close', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].sender_account_ids).toEqual(['original-sender']);
  expect(writes[0].schedule.timezone).toBe('Asia/Kolkata');
  expect(writes[0].schedule.days.filter(day => day.enabled).map(day => day.day)).toEqual(['Monday', 'Wednesday', 'Friday']);
  expect(writes[0].schedule.days.every(day => day.ranges[0].start === '07:00 AM' && day.ranges[0].end === '11:00 AM')).toBe(true);
});

test('sender verification recovers the same job after a failed read without submitting credentials twice', async ({ page }) => {
  let posts = 0; let reads = 0; let completed = false;
  const account = { id: 'synthetic-sender', account_name: 'Synthetic Sender', status: 'active' };
  await isolate(page, async (route, path) => {
    if (path.endsWith('/connect-cookie')) { posts += 1; return route.fulfill({ json: { job_id: 'saved-job', status: 'running' } }); }
    if (path.endsWith('/connection-jobs/saved-job')) {
      reads += 1;
      if (reads === 1) return route.fulfill({ status: 503, json: { detail: 'Status temporarily unavailable' } });
      completed = true; return route.fulfill({ json: { status: 'completed', account } });
    }
    return route.fulfill({ json: completed ? [account] : [] });
  });
  await page.goto('/?view=accounts');
  await page.getByRole('button', { name: 'Connect account', exact: true }).first().click();
  await page.getByLabel('li_at session cookie', { exact: false }).fill('li_at=synthetic-session; JSESSIONID="ajax:synthetic"');
  await page.getByLabel('Proxy country', { exact: false }).fill('IN');
  await page.getByRole('button', { name: 'Verify & Connect', exact: true }).click();
  await expect(page.getByText('Status temporarily unavailable', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Check verification status', exact: true }).click();
  await expect(page.getByText('Synthetic Sender', { exact: true })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(posts).toBe(1); expect(reads).toBe(2);
  await page.getByRole('button', { name: 'Refresh sender accounts', exact: true }).click();
  await expect(page.getByText('Synthetic Sender', { exact: true })).toBeVisible();
});
