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

test('sender cards show recorded blockers and save only an explicitly edited cap', async ({ page }) => {
  const writes = [];
  let account = { id: 'stored-sender', account_name: 'Stored Sender', status: 'active',
    proxy: { host: 'configured.example', status: 'healthy' }, stop_reason: 'rate_limited_429',
    cooldown_until: '2020-01-02T03:04:05Z', limits: { connection_invites: 50, messages: 0 } };
  await isolate(page, async (route, path) => {
    if (path.endsWith('/connection-jobs')) return route.fulfill({ json: {
      context: { contract_version: 1, workspace_id: 'w', scope_digest: 'a'.repeat(64) }, jobs: [], operator_review_required: false } });
    if (path.endsWith('/limits')) {
      const body = route.request().postDataJSON(); writes.push(body);
      account = { ...account, limits: { ...account.limits, ...body } };
      return route.fulfill({ json: account });
    }
    return route.fulfill({ json: [account] });
  });
  await page.goto('/?view=accounts');
  await expect(page.getByText('Saved status: Active', { exact: true })).toBeVisible();
  await expect(page.getByText('Recorded stop: Rate limit', { exact: true })).toBeVisible();
  await expect(page.getByText('Live health is not verified here.', { exact: false })).toBeVisible();
  await expect(page.getByText('1:1 Dedicated', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Warm-up level: Not recorded', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Adjust', exact: true }).click();
  await expect(page.getByLabel('Saved emails per day')).toHaveValue('');
  await expect(page.getByRole('button', { name: 'Save Limits', exact: true })).toBeDisabled();
  await page.getByLabel('Saved messages per day').fill('3');
  await page.getByRole('button', { name: 'Save Limits', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes).toEqual([{ messages: 3 }]);
  await expect(page.getByText('50/day', { exact: true })).toBeVisible();
});

for (const change of ['browser sign-in', 'same-token server workspace']) test(`a changed ${change} holds a late lead preview and prevents importing its contacts`, async ({ page }) => {
  let pendingPreview; let imports = 0;
  const original = { contract_version: 1, workspace_id: 'w', campaign_id: 'campaign', scope_digest: 'a'.repeat(64) };
  let context = { ...original };
  await page.addInitScript(() => localStorage.setItem('token', 'original-test-token'));
  await isolate(page, async (route, path) => {
    if (path.endsWith('/import-context')) return route.fulfill({ json: context });
    if (path.endsWith('/campaigns')) return route.fulfill({ json: [{ id: 'campaign', name: 'Test campaign', status: 'draft' }] });
    if (path.endsWith('/import-sources')) return route.fulfill({ json: { contract_version: 1, sources: [{ type: 'basic', parser_supported: true, collection_available: false, reason: 'Unavailable' }] } });
    if (path.endsWith('/preview')) { pendingPreview = route; return; }
    if (path.endsWith('/import-urls')) imports += 1;
    return route.fulfill({ json: path.endsWith('/leads') ? { leads: [], total: 0 } : [] });
  });
  await page.goto('/?view=leads');
  await page.getByRole('button', { name: 'Import contacts', exact: true }).first().click();
  await page.getByRole('button', { name: 'Paste LinkedIn profile URLs', exact: false }).click();
  await page.locator('textarea').first().fill('https://linkedin.com/in/old-private');
  await page.getByRole('button', { name: 'Validate & Preview', exact: false }).click();
  await expect.poll(() => Boolean(pendingPreview)).toBe(true);
  if (change === 'browser sign-in') await page.evaluate(() => localStorage.setItem('token', 'replacement-test-token'));
  else context = { ...original, workspace_id: 'other', scope_digest: 'b'.repeat(64) };
  await pendingPreview.fulfill({ json: { total_submitted: 1, valid_count: 1, import_context: original, rows: [{ row_number: 1, first_name: 'Old Private Contact', status: 'valid' }] } });
  await expect(page.getByText('could not be confirmed', { exact: false })).toBeVisible();
  await expect(page.getByText('Old Private Contact', { exact: true })).toHaveCount(0);
  expect(imports).toBe(0);
});

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
  const account = { id: 'synthetic-sender', workspace_id: 'w', account_name: 'Synthetic Sender', status: 'active' };
  const context = { contract_version: 1, workspace_id: 'w', scope_digest: 'a'.repeat(64) };
  await isolate(page, async (route, path) => {
    if (path.endsWith('/connection-jobs')) return route.fulfill({ json: { context, jobs: [], operator_review_required: false } });
    if (path.endsWith('/connect-cookie')) { posts += 1; return route.fulfill({ json: { job_id: 'saved-job', status: 'running' } }); }
    if (path.endsWith('/connection-jobs/saved-job')) {
      reads += 1;
      if (reads === 1) return route.fulfill({ status: 503, json: { detail: 'Status temporarily unavailable' } });
      completed = true; return route.fulfill({ json: { ...context, job_id: 'saved-job', sender_id: account.id, status: 'completed', account_current: true, account } });
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

test('a lost POST acknowledgement is recovered after a full reload by reading the original server job', async ({ page }) => {
  let posts = 0; let saved = false; let completed = false;
  const context = { contract_version: 1, workspace_id: 'w', scope_digest: 'a'.repeat(64) };
  const job = { job_id: 'lost-ack-job', sender_id: 'original', status: 'running', reconnect: false };
  const account = { id: 'original', workspace_id: 'w', account_name: 'Recovered Original', status: 'active' };
  await isolate(page, async (route, path) => {
    if (path.endsWith('/connection-jobs')) return route.fulfill({ json: { context, jobs: saved ? [{ ...job, status: completed ? 'completed' : 'running' }] : [], operator_review_required: false } });
    if (path.endsWith('/connect-cookie')) { posts += 1; saved = true; return route.abort('failed'); }
    if (path.endsWith('/connection-jobs/lost-ack-job')) {
      completed = true;
      return route.fulfill({ json: { ...context, ...job, status: 'completed', account_current: true, account } });
    }
    return route.fulfill({ json: completed ? [account] : [] });
  });
  await page.goto('/?view=accounts');
  await page.getByRole('button', { name: 'Connect account', exact: true }).first().click();
  await page.getByLabel('li_at session cookie', { exact: false }).fill('li_at=synthetic; JSESSIONID="ajax:synthetic"');
  await page.getByLabel('Proxy country', { exact: false }).fill('IN');
  await page.getByRole('button', { name: 'Verify & Connect', exact: true }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Check verification', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Connect account', exact: true }).first()).toBeDisabled();
  await page.getByRole('button', { name: 'Check verification', exact: true }).click();
  await expect(page.getByText('Recovered Original', { exact: true })).toBeVisible();
  expect(posts).toBe(1);
  expect(await page.evaluate(() => Object.keys(sessionStorage).length)).toBe(0);
});
