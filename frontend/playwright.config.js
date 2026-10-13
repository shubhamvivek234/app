const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/browser',
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [['list'], ['junit', { outputFile: 'test-results/outreach-browser.xml' }]],
  use: { baseURL: 'http://127.0.0.1:4179', browserName: 'chromium', trace: 'retain-on-failure' },
  webServer: {
    command: 'node tests/browser/serve.cjs',
    url: 'http://127.0.0.1:4179',
    timeout: 60000,
    reuseExistingServer: false,
    gracefulShutdown: { signal: 'SIGTERM', timeout: 5000 },
  },
});
