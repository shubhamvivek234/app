import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import SenderStoredDetails, { savedCap, savedStatus } from './SenderStoredDetails';

it.each([undefined, null, true, '20', -1, 101, 1.5, [], {}])('does not invent a saved cap from %p', value => {
  expect(savedCap(value)).toBeNull();
});
it.each([0, 20, 100])('retains the recorded cap %p', value => expect(savedCap(value)).toBe(value));
it.each(['toString', 'constructor', [], {}, undefined])('holds unknown saved status %p', value => {
  expect(savedStatus(value)).toBe('Needs review');
});

describe('stored timestamp and stop metadata', () => {
  let container; let root;
  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
  const render = async account => { await act(async () => root.render(<SenderStoredDetails account={account} />)); };
  it.each(['2026-02-30T10:00:00Z', '2026-13-01T10:00:00Z', '2026-10-21T24:00:00Z', true, [], {}, 1])('holds malformed cooldown %p', async value => {
    await render({ cooldown_until: value });
    expect(container.querySelector('time')).toBeNull();
    expect(container.textContent).toContain('Cooldown timing requires review');
  });
  it.each([
    ['2026-10-21T10:00:00', '2026-10-21T10:00:00.000Z'],
    ['2026-10-21T10:00:00+05:30', '2026-10-21T04:30:00.000Z'],
    ['2028-02-29T10:00:00.123456Z', '2028-02-29T10:00:00.123Z'],
  ])('renders recorded UTC timestamp %s', async (value, expected) => {
    await render({ cooldown_until: value });
    expect(container.querySelector('time').dateTime).toBe(expected);
  });
  it('handles malformed stop and warm-up values without rendering raw values', async () => {
    await render({ stop_reason: { error: 'private-value' }, warmup_level: 0 });
    expect(container.textContent).toContain('Recorded stop requires review');
    expect(container.textContent).toContain('Warm-up level: Not recorded');
    expect(container.textContent).not.toContain('private-value');
  });
});
