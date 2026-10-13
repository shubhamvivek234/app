const { test, expect } = require('@playwright/test');

test('compiled Home restores deduplicated observations only after readmission', async ({ page }) => {
  await page.addInitScript(() => {
    window.EventSource = class {
      constructor() { this.handlers = {}; window.activitySource = this; }
      addEventListener(name, handler) { this.handlers[name] = handler; }
      close() { this.closed = true; }
      emit(name, value) { this.handlers[name]({ data: JSON.stringify(value), lastEventId: value?.event_id }); }
    };
  });
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:4179') return route.abort();
    if (url.pathname.startsWith('/api/')) return route.fulfill({ json: [] });
    return route.continue();
  });
  await page.goto('/?view=home');
  await expect(page.getByRole('heading', { name: 'Completed Task Activity' })).toBeVisible();
  await page.evaluate(() => {
    const event = { id: 'synthetic-task', task_type: 'profile_visit', event_id: 'position-1', timestamp: '2026-10-13T00:00:00Z' };
    window.activitySource.emit('connected');
    window.activitySource.emit('task_completed', event);
    window.activitySource.emit('task_completed', event);
  });
  await expect(page.getByText('profile visit', { exact: true })).toHaveCount(1);
  await page.evaluate(() => window.activitySource.onerror());
  await expect(page.getByText('profile visit', { exact: true })).toHaveCount(0);
  await page.evaluate(() => window.activitySource.emit('connected'));
  await expect(page.getByText('profile visit', { exact: true })).toHaveCount(1);
  await page.evaluate(() => window.activitySource.emit('stream_closed', { reason: 'access_changed' }));
  await expect(page.getByText('profile visit', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Activity unavailable', { exact: true })).toBeVisible();
});

test('compiled Voice sends the displayed revision and shows assignment conflicts', async ({ page }) => {
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:4179') return route.abort();
    if (!url.pathname.startsWith('/api/')) return route.continue();
    if (url.pathname.endsWith('/accounts')) return route.fulfill({ json: [{ id: 'a', account_name: 'Alice' }] });
    if (url.pathname.endsWith('/assign')) {
      expect(route.request().postDataJSON()).toEqual({ account_ids: ['a'], revision: 7 });
      return route.fulfill({ status: 409, json: { detail: 'Voice assignment changed; reload Voice Studio' } });
    }
    return route.fulfill({ json: { studio_enabled: true, jobs: [], voices: [{ id: 'v1', name: 'My selected voice',
      status: 'active', consent_current: true, revision: 7, assigned_account_ids: [] }] } });
  });
  await page.goto('/?view=voice');
  await page.getByRole('button', { name: 'Assign to connected sender...' }).click();
  await page.getByRole('button', { name: 'Alice', exact: true }).click();
  await expect(page.getByText('Voice assignment changed; reload Voice Studio', { exact: true })).toBeVisible();
  await expect(page.getByText('No sender assigned', { exact: true })).toBeVisible();
});
