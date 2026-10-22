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

  it('fetches and renders real-time lead count badges on sequence cards for campaign', async () => {
    global.fetch = jest.fn((url) => {
      if (url.includes('node-counts')) {
        return Promise.resolve(ok({
          campaign_id: 'camp-active',
          node_counts: { node_invite: 34 },
          waiting_node_counts: { node_invite: 34 },
          execution_state_counts: { in_progress: 34 },
          total_leads: 34,
        }));
      }
      if (url.includes('sequence-capabilities')) {
        return Promise.resolve(ok({ capabilities: [] }));
      }
      if (url.includes('/api/v1/outreach/sequences')) {
        return Promise.resolve(ok({
          tree: [
            {
              id: 'node_invite',
              type: 'connection_request',
              title: 'Send Invite',
              subtitle: 'Wait 1 day',
              delay_days: 1,
            },
          ],
        }));
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });

    await act(async () => root.render(<SequenceCanvas campaignId="camp-active" />));
    expect(container.textContent).toContain('34 leads waiting');
  });

  it('allows zooming out below 50% down to 20% and has Fit button', async () => {
    global.fetch = jest.fn((url) => {
      if (url.includes('node-counts')) return Promise.resolve(ok({ node_counts: {}, waiting_node_counts: {}, total_leads: 0 }));
      if (url.includes('sequence-capabilities')) return Promise.resolve(ok({ capabilities: [] }));
      if (url.includes('/api/v1/outreach/sequences')) {
        return Promise.resolve(ok({
          tree: [{ id: 'step_1', type: 'visit_profile', title: 'Visit Profile', delay_days: 1 }],
        }));
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });

    await act(async () => root.render(<SequenceCanvas campaignId="camp-active" />));
    expect(container.textContent).toContain('100%');

    const fitBtn = container.querySelector('button[title="Fit sequence to screen"]');
    expect(fitBtn).toBeTruthy();

    const zoomOutBtn = container.querySelector('button[title="Zoom out"]');
    expect(zoomOutBtn).toBeTruthy();

    // Zoom out multiple times below 50%
    for (let i = 0; i < 7; i++) {
      await act(async () => zoomOutBtn.click());
    }
    // Should be at 30% (100 - 70)
    expect(container.textContent).toContain('30%');

    // Zoom out to minimum 20%
    for (let i = 0; i < 3; i++) {
      await act(async () => zoomOutBtn.click());
    }
    expect(container.textContent).toContain('20%');

    // Click fit to screen
    await act(async () => fitBtn.click());
    // Should execute without crashing
  });

  it('splices trailing steps into the appropriate branch when inserting a condition before existing steps and guards message steps', async () => {
    let savedPayloads = [];
    global.fetch = jest.fn((url, opts) => {
      if (url.includes('sequence-capabilities')) {
        return Promise.resolve(ok({
          capabilities: [
            { type: 'if_connected', supported: true, builder_available: true, live_enabled: true },
            { type: 'send_message', supported: true, builder_available: true, live_enabled: true },
            { type: 'visit_profile', supported: true, builder_available: true, live_enabled: true },
          ],
        }));
      }
      if (url === '/api/v1/outreach/sequences' && opts?.method === 'POST') {
        savedPayloads.push(JSON.parse(opts.body));
        return Promise.resolve(ok({ id: 'seq-1' }));
      }
      return Promise.resolve(ok({
        tree: [
          { id: 'step_visit', type: 'visit_profile', title: 'Visit profile', delay_days: 1, config: {} },
        ],
      }));
    });

    const onRegisterSave = jest.fn();
    await act(async () => root.render(<SequenceCanvas campaignId="camp-splice" onRegisterSave={onRegisterSave} />));

    // Open the first "+" button (index 0, before step_visit)
    const addButtons = container.querySelectorAll('button[title="Add a step"]');
    expect(addButtons.length).toBeGreaterThanOrEqual(2);
    await act(async () => addButtons[0].click());

    // Insert "If connected" before Visit profile
    await act(async () => paletteButton(container, 'If connected').click());

    // Save and inspect the compiled DAG
    const save = onRegisterSave.mock.calls.filter(([cb]) => cb).at(-1)?.[0];
    expect(save).toBeTruthy();
    let saved;
    await act(async () => { saved = await save(); });
    expect(saved).toBe(true);

    const lastPayload = savedPayloads.at(-1);
    expect(lastPayload).toBeTruthy();
    const ifConnNode = lastPayload.nodes.find((n) => n.type === 'if_connected');
    expect(ifConnNode).toBeTruthy();
    // Trailing step_visit should now be attached to if_connected via a labeled branch edge ('connected')
    expect(lastPayload.edges).toEqual(expect.arrayContaining([
      expect.objectContaining({
        source: ifConnNode.id,
        target: 'step_visit',
        label: 'connected',
      }),
    ]));
  });

  it('inserts AI prompt into step, previews with real campaign leads, applies AI copy, and enables Voice Note controls', async () => {
    global.fetch = jest.fn((url, opts) => {
      if (url.includes('sequence-capabilities')) {
        return Promise.resolve(ok({
          capabilities: [
            { type: 'connection_request', supported: true, builder_available: true, live_enabled: true },
            { type: 'voice_note', supported: true, builder_available: true, live_enabled: true },
          ],
        }));
      }
      if (url.includes('/api/v1/outreach/voice')) {
        return Promise.resolve(ok({
          voices: [{ id: 'v-1', name: 'Mohit Cloned Voice', status: 'ready' }],
        }));
      }
      if (url.includes('node-counts')) {
        return Promise.resolve(ok({ node_counts: {}, waiting_node_counts: {}, total_leads: 1 }));
      }
      if (url === '/api/v1/outreach/prompts') {
        return Promise.resolve(ok([
          { id: 'curated_activity-snippet', name: "Saw you're doing X (3-5 words)", prompt_text: 'Extract 3-5 words', is_system: true },
        ]));
      }
      if (url === '/api/v1/outreach/prompts/preview' && opts?.method === 'POST') {
        return Promise.resolve(ok({
          evaluated_text: 'Hey Son, saw you enhancing customer connection with AI. Would love to connect.',
          ai_generated_text: 'Hey Son, saw you enhancing customer connection with AI. Would love to connect.',
          has_ai_tokens: true,
          is_illustrative_preview: false,
          selected_lead_id: 'lead-son',
          available_leads: [
            { id: 'lead-son', first_name: 'Son', last_name: 'Nguyen', company_name: 'Prosp' },
          ],
          lead_preview: {
            first_name: 'Son',
            last_name: 'Nguyen',
            company_name: 'Prosp',
            job_title: 'Founder',
            location: 'San Francisco',
          },
          notice: 'AI prompt personalized against lead profile.',
        }));
      }
      if (url.includes('/api/v1/outreach/sequences')) {
        return Promise.resolve(ok({
          tree: [
            {
              id: 'node_invite',
              type: 'connection_request',
              title: 'Send Invite',
              subtitle: 'Blank invite',
              delay_hours: 0,
              config: { note: 'Hey {{first_name}}, saw you' },
            },
            {
              id: 'node_voice',
              type: 'voice_note',
              title: 'Voice note',
              subtitle: 'Action required',
              delay_hours: 24,
              config: { script: 'Hey {{first_name}}' },
            },
          ],
        }));
      }
      return Promise.resolve(ok({}));
    });

    await act(async () => root.render(<SequenceCanvas campaignId="camp-video-parity" />));

    // Select Connection Request step
    const inviteCard = [...container.querySelectorAll('h4')].find((el) => el.textContent.includes('Send Invite'));
    expect(inviteCard).toBeTruthy();
    await act(async () => inviteCard.click());

    // Open Prompt guidance library and click Insert prompt
    const promptGuidanceBtn = [...container.querySelectorAll('button')].find((b) => b.textContent.includes('Prompt guidance'));
    expect(promptGuidanceBtn).toBeTruthy();
    await act(async () => promptGuidanceBtn.click());

    const insertPromptBtn = [...container.querySelectorAll('button')].find((b) => b.textContent.includes('Insert prompt'));
    expect(insertPromptBtn).toBeTruthy();
    await act(async () => insertPromptBtn.click());

    // Click Preview and verify real lead switcher + AI Apply button
    const previewBtn = [...container.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Preview');
    expect(previewBtn).toBeTruthy();
    await act(async () => previewBtn.click());

    expect(container.textContent).toContain('Real Lead');
    expect(container.textContent).toContain('Hey Son, saw you enhancing customer connection with AI.');

    const applyAiBtn = [...container.querySelectorAll('button')].find((b) => b.textContent.includes('Apply AI Copy to Step'));
    expect(applyAiBtn).toBeTruthy();
    await act(async () => applyAiBtn.click());

    // Select Voice note step and verify Record audio & Upload MP3 are enabled
    const voiceCard = [...container.querySelectorAll('h4')].find((el) => el.textContent.includes('Voice note'));
    expect(voiceCard).toBeTruthy();
    await act(async () => voiceCard.click());

    const recordBtn = [...container.querySelectorAll('button')].find((b) => b.textContent.includes('Record audio'));
    const uploadBtn = [...container.querySelectorAll('button')].find((b) => b.textContent.includes('Upload MP3'));
    expect(recordBtn).toBeTruthy();
    expect(recordBtn.disabled).toBe(false);
    expect(uploadBtn).toBeTruthy();
    expect(uploadBtn.disabled).toBe(false);
    expect(container.textContent).toContain('Mohit Cloned Voice');
  });

  it('renders Dripify message editor with Primary/Fallback tabs and warns when [BRACKETS] are unreplaced', async () => {
    global.fetch = jest.fn((url) => {
      if (url.endsWith('/api/v1/outreach/sequence-capabilities')) return Promise.resolve(ok(CAPABILITIES));
      if (url.includes('/api/v1/outreach/sequences')) {
        return Promise.resolve(ok({
          tree: [
            {
              id: 'step_msg',
              type: 'send_message',
              title: 'Message',
              subtitle: 'Send message',
              delay_hours: 0,
              config: { body: 'Hi {{first_name}}, saw your post about [insert topic]!' },
            },
          ],
        }));
      }
      return Promise.resolve(ok([]));
    });

    await act(async () => root.render(<SequenceCanvas campaignId="camp-1" />));

    const msgCard = [...container.querySelectorAll('h4')].find((el) => el.textContent.includes('Message'));
    expect(msgCard).toBeTruthy();
    await act(async () => msgCard.click());

    // Dripify message editor header, tabs, and unreplaced brackets warning
    expect(container.querySelector('[data-testid="dripify-message-editor"]')).toBeTruthy();
    expect(container.textContent).toContain('Input your LinkedIn message');
    expect(container.textContent).toContain('Primary message');
    expect(container.textContent).toContain('Fallback message (optional)');
    expect(container.querySelector('[data-testid="unreplaced-brackets-warning"]')).toBeTruthy();
    expect(container.textContent).toContain('Make sure to replace the example text in [BRACKETS] with your own wording before saving');

    // Clicking Save inside the Dripify message editor keeps the editor open and blocks saving when [BRACKETS] remain
    const saveStepBtn = container.querySelector('[data-testid="dripify-save-message-btn"]');
    expect(saveStepBtn).toBeTruthy();
    await act(async () => saveStepBtn.click());
    expect(container.querySelector('[data-testid="dripify-message-editor"]')).toBeTruthy();
  });
});
