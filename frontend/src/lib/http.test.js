import env from '@/env';
import axios from 'axios';
import { backendFetchUrl, initHttpInterceptors } from './http';

jest.mock('@/firebase', () => ({ auth: { currentUser: null } }));

describe('backend fetch routing', () => {
  it('routes relative API requests to the configured API host', () => {
    expect(backendFetchUrl('/api/v1/outreach/accounts')).toBe(`${env.BACKEND_URL}/api/v1/outreach/accounts`);
    expect(backendFetchUrl('/api/v1/outreach/campaigns?limit=50')).toBe(`${env.BACKEND_URL}/api/v1/outreach/campaigns?limit=50`);
  });

  it('leaves external and browser routes unchanged', () => {
    expect(backendFetchUrl('https://example.com/image.png')).toBe('https://example.com/image.png');
    expect(backendFetchUrl('/outreach?tab=home')).toBe('/outreach?tab=home');
  });

  it('sends outreach API fetches to the API host with credentials', async () => {
    const originalFetch = jest.fn(() => Promise.resolve({ ok: true }));
    window.fetch = originalFetch;
    initHttpInterceptors();
    await window.fetch('/api/v1/outreach/accounts');
    expect(originalFetch).toHaveBeenCalledWith(
      `${env.BACKEND_URL}/api/v1/outreach/accounts`,
      expect.objectContaining({ credentials: 'include' })
    );
    const request = new Request(`${window.location.origin}/api/v1/outreach/campaigns`);
    await window.fetch(request);
    const routedRequest = originalFetch.mock.calls[1][0];
    expect(routedRequest).toBeInstanceOf(Request);
    expect(routedRequest.url).toBe(`${env.BACKEND_URL}/api/v1/outreach/campaigns`);
    expect(routedRequest.credentials).toBe('include');
  });

  it('routes relative axios API calls to the API host', async () => {
    initHttpInterceptors();
    const response = await axios.get('/api/v1/outreach/accounts', {
      adapter: async (config) => ({ data: {}, status: 200, statusText: 'OK', headers: {}, config }),
    });
    expect(response.config.url).toBe(`${env.BACKEND_URL}/api/v1/outreach/accounts`);
    expect(response.config.withCredentials).toBe(true);
  });
});
