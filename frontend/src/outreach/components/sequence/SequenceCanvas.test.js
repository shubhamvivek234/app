import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import SequenceCanvas from './SequenceCanvas';

describe('Sequence loading safety', () => {
  it('cannot overwrite a stored sequence if its initial load fails', async () => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    const onRegisterSave = jest.fn();
    global.fetch = jest.fn(() => Promise.resolve({ ok: false, json: async () => ({ detail: 'Sequence unavailable' }) }));
    try {
      await act(async () => root.render(<SequenceCanvas campaignId="campaign-a" onRegisterSave={onRegisterSave} />));
      const save = onRegisterSave.mock.calls.filter(([callback]) => callback).at(-1)?.[0];
      expect(save).toBeTruthy();
      let saved;
      await act(async () => { saved = await save(); });
      expect(saved).toBe(false);
      expect(global.fetch).not.toHaveBeenCalledWith('/api/v1/outreach/sequences', expect.objectContaining({ method: 'POST' }));
      expect(container.textContent).toContain('Sequence unavailable');
    } finally {
      await act(async () => root.unmount());
      container.remove();
      delete global.fetch;
    }
  });
});
