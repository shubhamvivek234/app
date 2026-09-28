import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import SequenceCanvas, { flattenTreeToDAG } from './SequenceCanvas';

const ok = (value) => ({ ok: true, json: async () => value });

async function openPalette(container) {
  const add = container.querySelector('button[title="Add a step"]');
  expect(add).toBeTruthy();
  await act(async () => add.click());
}

function paletteButton(container, label) {
  return [...container.querySelectorAll('button')].find((button) => button.textContent.trim().startsWith(label));
}

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

describe('Server-driven sequence capabilities', () => {
  let container;
  let root;

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    delete global.fetch;
  });

  it('shows the backend reason for unavailable steps and keeps them disabled', async () => {
    global.fetch = jest.fn((url) => Promise.resolve(url.includes('sequence-capabilities')
      ? ok({ capabilities: [
        { type: 'follow', supported: false, builder_available: false, live_enabled: false, reason: 'Follow is not supported by the runner.' },
        { type: 'like_last_post', supported: true, builder_available: true, live_enabled: false, reason: 'Live LinkedIn actions are disabled.' },
      ] })
      : ok({ tree: [] })));
    await act(async () => root.render(<SequenceCanvas campaignId="new" />));
    await openPalette(container);
    expect(paletteButton(container, 'Follow').disabled).toBe(true);
    expect(container.textContent).toContain('Follow is not supported by the runner.');
    expect(paletteButton(container, 'Like last post').disabled).toBe(false);
    expect(container.textContent).toContain('Live LinkedIn actions are disabled.');
  });

  it('fails closed when capability lookup fails, with a retry control', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: false, json: async () => ({ detail: 'Unavailable' }) }));
    await act(async () => root.render(<SequenceCanvas campaignId="new" />));
    await openPalette(container);
    expect(paletteButton(container, 'Like last post').disabled).toBe(true);
    expect(container.textContent).toContain('Step availability could not be checked');
    expect([...container.querySelectorAll('button')].some((button) => button.textContent.includes('Retry availability'))).toBe(true);
  });

  it('exposes email steps only when the backend permits draft building', async () => {
    global.fetch = jest.fn((url) => Promise.resolve(url.includes('sequence-capabilities')
      ? ok({ capabilities: [
        { type: 'find_email', supported: true, builder_available: true, live_enabled: false, reason: 'Email execution is not enabled.' },
        { type: 'send_email', supported: true, builder_available: true, live_enabled: false, reason: 'Email execution is not enabled.' },
        { type: 'if_email_available', supported: true, builder_available: true, live_enabled: false, reason: 'Email execution is not enabled.' },
      ] })
      : ok({ tree: [] })));
    await act(async () => root.render(<SequenceCanvas campaignId="new" />));
    await openPalette(container);
    expect(paletteButton(container, 'Find email').disabled).toBe(false);
    expect(paletteButton(container, 'Send email').disabled).toBe(false);
    expect(paletteButton(container, 'If email available').disabled).toBe(false);
    await act(async () => paletteButton(container, 'Send email').click());
    expect(container.textContent).toContain('Email subject');
    expect(container.textContent).toContain('Email body');
  });

  it('serializes if-email-available branches as Yes and No', () => {
    const graph = flattenTreeToDAG([{
      id: 'condition', type: 'if_email_available', title: 'If email available', config: {},
      branches: {
        left: { condition: 'No', steps: [{ id: 'without-email', type: 'visit_profile', config: {} }] },
        right: { condition: 'Yes', steps: [{ id: 'with-email', type: 'send_email', config: { subject: 'Hi', body: 'Hello' } }] },
      },
    }]);
    expect(graph.edges).toEqual(expect.arrayContaining([
      expect.objectContaining({ source: 'condition', target: 'without-email', label: 'No' }),
      expect.objectContaining({ source: 'condition', target: 'with-email', label: 'Yes' }),
    ]));
  });
});
