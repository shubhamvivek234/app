import { PREBUILT_TEMPLATES, isLaunchableTemplate } from './OutreachCampaigns';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachCampaigns from './OutreachCampaigns';

jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

describe('Campaign template readiness', () => {
  it('allows runner-supported templates and blocks unsupported InMail steps', () => {
    expect(isLaunchableTemplate(PREBUILT_TEMPLATES.find((template) => template.id === 'tpl_connect_and_follow_up'))).toBe(true);
    expect(isLaunchableTemplate(PREBUILT_TEMPLATES.find((template) => template.id === 'tpl_multitouch_inmail'))).toBe(false);
  });

  it('does not claim invented conversion metrics for starter templates', () => {
    expect(PREBUILT_TEMPLATES.every((template) => !template.acceptance && !template.reply && !template.uses)).toBe(true);
  });
});

describe('Campaign list availability', () => {
  it('shows an API failure with retry instead of an empty campaign list', async () => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    global.fetch = jest.fn()
      .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'Campaign service unavailable' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'campaign-a', name: 'Recovered', status: 'draft' }] });
    try {
      await act(async () => root.render(<OutreachCampaigns onOpenWizard={() => {}} />));
      expect(container.textContent).toContain('Campaign service unavailable');
      const retry = [...container.querySelectorAll('button')].find((button) => button.textContent.includes('Retry'));
      await act(async () => retry.click());
      expect(container.textContent).toContain('Recovered');
    } finally {
      await act(async () => root.unmount());
      container.remove();
      delete global.fetch;
    }
  });
});
