import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachLeads from './OutreachLeads';

jest.mock('../components/ImportLeadsModal', () => ({ isOpen, campaignId }) => (
  isOpen ? <div data-testid="import-modal">Importing into {campaignId}</div> : null
));

const response = (body) => ({ ok: true, json: async () => body });

describe('Outreach Leads CRM', () => {
  let container;
  let root;

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    localStorage.clear();
    URL.createObjectURL = jest.fn(() => 'blob:outreach-test');
    URL.revokeObjectURL = jest.fn();
    jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    global.fetch = jest.fn((url) => {
      if (url === '/api/v1/outreach/campaigns') {
        return Promise.resolve(response([{ id: 'camp-1', name: 'Growth', leads_count: 75 }]));
      }
      if (url.startsWith('/api/v1/outreach/leads?')) {
        const params = new URL(url, 'http://localhost').searchParams;
        const skip = Number(params.get('skip') || 0);
        return Promise.resolve(response({
          leads: Array.from({ length: skip ? 25 : 50 }, (_, index) => ({
            id: `lead-${skip + index}`, campaign_id: 'camp-1',
            linkedin_url: `https://linkedin.com/in/lead-${skip + index}`,
            first_name: 'Alex', pipeline_stage: 'unassigned', execution_state: 'queued',
          })),
          total: 75,
        }));
      }
      if (url.startsWith('/api/v1/outreach/leads/export?')) {
        return Promise.resolve({ ok: true, blob: async () => new Blob(['first_name\nAlex']) });
      }
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    jest.restoreAllMocks();
    delete global.fetch;
  });

  it('uses a real campaign for imports and pages through all leads', async () => {
    await act(async () => { root.render(<OutreachLeads onOpenWizard={() => {}} />); });
    expect(container.textContent).toContain('Showing 1–50 of 75');

    const campaignButton = [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Growth'));
    await act(async () => campaignButton.click());
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('campaign_id=camp-1'),
      expect.objectContaining({ credentials: 'include' })
    );

    const importButton = [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Import contacts'));
    await act(async () => importButton.click());
    expect(container.querySelector('[data-testid="import-modal"]').textContent).toContain('camp-1');

    const nextButton = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Next');
    await act(async () => nextButton.click());
    expect(container.textContent).toContain('Showing 51–75 of 75');
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('skip=50'),
      expect.objectContaining({ credentials: 'include' })
    );

    const exportButton = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Export CSV');
    await act(async () => exportButton.click());
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/outreach/leads/export?campaign_id=camp-1'),
      expect.objectContaining({ credentials: 'include' })
    );
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

});
