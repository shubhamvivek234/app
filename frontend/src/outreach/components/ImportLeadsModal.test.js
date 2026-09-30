import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ImportLeadsModal from './ImportLeadsModal';

const response = (body, ok = true, status = 200) => ({
  ok,
  status,
  json: async () => body,
});

describe('ImportLeadsModal', () => {
  let container;
  let root;

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    localStorage.clear();
    global.fetch = jest.fn();
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    jest.restoreAllMocks();
    delete global.fetch;
  });

  it('renders nothing when isOpen is false', async () => {
    await act(async () => {
      root.render(<ImportLeadsModal isOpen={false} onClose={() => {}} campaignId="camp-1" />);
    });
    expect(container.innerHTML).toBe('');
  });

  it('renders source options and allows selecting pasted LinkedIn URLs', async () => {
    await act(async () => {
      root.render(<ImportLeadsModal isOpen={true} onClose={() => {}} campaignId="camp-1" />);
    });

    expect(container.textContent).toContain('Choose Lead Sourcing Method');
    expect(container.textContent).toContain('Paste LinkedIn profile URLs');
    expect(container.textContent).toContain('Import from CSV file');
    expect(container.textContent).toContain('Scraping disabled');

    // Click "Paste LinkedIn profile URLs"
    const pasteButton = [...container.querySelectorAll('button')].find((b) =>
      b.textContent.includes('Paste LinkedIn profile URLs')
    );
    await act(async () => pasteButton.click());

    expect(container.textContent).toContain('Paste LinkedIn Profile URLs (One per line)');
  });

  it('previews pasted URLs and proceeds through import', async () => {
    const onLeadsImported = jest.fn();

    global.fetch.mockImplementation((url, opts) => {
      if (url === '/api/v1/outreach/leads/preview') {
        const body = JSON.parse(opts.body);
        expect(body.source_type).toBe('pasted_urls');
        expect(body.campaign_id).toBe('camp-1');
        return Promise.resolve(response({
          total_submitted: 2,
          valid_count: 1,
          duplicate_count: 1,
          contacted_count: 0,
          dnc_count: 0,
          invalid_count: 0,
          rows: [
            {
              row_number: 1,
              linkedin_url: 'https://linkedin.com/in/alexsmith',
              first_name: 'Alex',
              last_name: 'Smith',
              company_name: 'Acme',
              status: 'valid',
              rejection_code: null,
              error_reason: null,
            },
            {
              row_number: 2,
              linkedin_url: 'https://linkedin.com/in/alexsmith',
              first_name: 'Alex',
              last_name: 'Smith',
              company_name: 'Acme',
              status: 'rejected',
              rejection_code: 'duplicate_batch',
              error_reason: 'Duplicate profile URL in this import batch',
            },
          ],
        }));
      }

      if (url === '/api/v1/outreach/leads/import-urls') {
        const body = JSON.parse(opts.body);
        expect(body.campaign_id).toBe('camp-1');
        return Promise.resolve(response({
          imported_count: 1,
          duplicates_count: 1,
          skipped_count: 0,
          total_submitted: 2,
          rejections: [
            {
              linkedin_url: 'https://linkedin.com/in/alexsmith',
              reason: 'Duplicate profile URL in this import batch',
            },
          ],
        }));
      }

      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });

    await act(async () => {
      root.render(
        <ImportLeadsModal
          isOpen={true}
          onClose={() => {}}
          campaignId="camp-1"
          onLeadsImported={onLeadsImported}
        />
      );
    });

    // Step 1: Select Paste URLs
    const pasteButton = [...container.querySelectorAll('button')].find((b) =>
      b.textContent.includes('Paste LinkedIn profile URLs')
    );
    await act(async () => pasteButton.click());

    // Step 2: Fill in URLs textarea
    const textarea = container.querySelector('textarea');
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set.call(
        textarea,
        'https://linkedin.com/in/alexsmith, Alex Smith, Acme\nhttps://linkedin.com/in/alexsmith, Alex Smith, Acme'
      );
      textarea.dispatchEvent(new Event('change', { bubbles: true }));
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
    });

    const previewBtn = [...container.querySelectorAll('button')].find((b) =>
      b.textContent.includes('Validate & Preview')
    );
    await act(async () => previewBtn.click());

    // Step 3: Verify preview stats & table
    expect(container.textContent).toContain('Validation Preview & Deduplication');
    expect(container.textContent).toContain('Valid to Enroll');
    expect(container.textContent).toContain('Row Verification Preview');
    expect(container.textContent).toContain('Alex Smith');
    expect(container.textContent).toContain('Valid');
    expect(container.textContent).toContain('Duplicate profile URL in this import batch');

    // Confirm & Ingest
    const ingestBtn = [...container.querySelectorAll('button')].find((b) =>
      b.textContent.includes('Confirm & Ingest')
    );
    await act(async () => ingestBtn.click());

    // Step 4: Verify complete state
    expect(container.textContent).toContain('Lead Intake Complete');
    expect(container.textContent).toContain('Successfully attached 1 leads');
    expect(container.textContent).toContain('Excluded Leads Summary (1)');
    expect(onLeadsImported).toHaveBeenCalledWith(
      expect.objectContaining({ imported_count: 1 })
    );
  });

  it('supports staged lead name editing, reverting to original, and submitting to import-staged', async () => {
    const onLeadsImported = jest.fn();
    let stagedPayload = null;

    global.fetch.mockImplementation((url, opts) => {
      if (url === '/api/v1/outreach/leads/preview') {
        return Promise.resolve(response({
          total_submitted: 1,
          valid_count: 1,
          duplicate_count: 0,
          contacted_count: 0,
          dnc_count: 0,
          invalid_count: 0,
          rows: [
            {
              row_number: 1,
              linkedin_url: 'https://linkedin.com/in/alexhamilton',
              raw_first_name: 'ALEXANDER',
              cleaned_first_name: 'Alexander',
              first_name: 'Alexander',
              last_name: 'Hamilton',
              company_name: 'Treasury',
              status: 'valid',
              rejection_code: null,
              error_reason: null,
            },
          ],
        }));
      }

      if (url === '/api/v1/outreach/leads/import-staged') {
        stagedPayload = JSON.parse(opts.body);
        return Promise.resolve(response({
          imported_count: 1,
          duplicates_count: 0,
          skipped_count: 0,
          total_submitted: 1,
          rejections: [],
        }));
      }

      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });

    await act(async () => {
      root.render(
        <ImportLeadsModal
          isOpen={true}
          onClose={() => {}}
          campaignId="camp-1"
          onLeadsImported={onLeadsImported}
        />
      );
    });

    // Step 1: Select Paste URLs
    const pasteButton = [...container.querySelectorAll('button')].find((b) =>
      b.textContent.includes('Paste LinkedIn profile URLs')
    );
    await act(async () => pasteButton.click());

    // Step 2: Fill in URLs textarea
    const textarea = container.querySelector('textarea');
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set.call(
        textarea,
        'https://linkedin.com/in/alexhamilton, ALEXANDER Hamilton, Treasury'
      );
      textarea.dispatchEvent(new Event('change', { bubbles: true }));
    });

    const previewBtn = [...container.querySelectorAll('button')].find((b) =>
      b.textContent.includes('Validate & Preview')
    );
    await act(async () => previewBtn.click());

    // Step 3: Verify preview row and test revert
    expect(container.textContent).toContain('Validation Preview');
    const revertBtn = [...container.querySelectorAll('button')].find((b) =>
      b.textContent.includes('Revert')
    );
    expect(revertBtn).toBeTruthy();

    // Click revert to restore raw name
    await act(async () => revertBtn.click());
    const nameInput = container.querySelector('input[aria-label="First name for lead #1"]');
    expect(nameInput.value).toBe('ALEXANDER');

    // Now edit the name to "Alex"
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(
        nameInput,
        'Alex'
      );
      nameInput.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(nameInput.value).toBe('Alex');

    // Confirm & Ingest with custom edits
    const ingestBtn = [...container.querySelectorAll('button')].find((b) =>
      b.textContent.includes('Confirm & Ingest')
    );
    await act(async () => ingestBtn.click());

    // Verify /import-staged was called with custom edited name
    expect(stagedPayload).toBeTruthy();
    expect(stagedPayload.campaign_id).toBe('camp-1');
    expect(stagedPayload.leads[0].cleaned_first_name).toBe('Alex');
    expect(stagedPayload.leads[0].raw_first_name).toBe('ALEXANDER');
    expect(container.textContent).toContain('Lead Intake Complete');
  });
});
