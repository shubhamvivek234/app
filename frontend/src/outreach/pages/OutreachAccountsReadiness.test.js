import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import OutreachAccounts from './OutreachAccounts';

jest.mock('../components/SenderVerificationRecovery', () => () => null);
jest.mock('../components/ConnectLinkedInModal', () => () => null);

describe('sender record observations and saved caps', () => {
  let root; let container; let account;
  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div'); document.body.appendChild(container);
    root = createRoot(container); localStorage.clear();
    account = { id: 'sender', account_name: 'Alex', status: 'active' };
    global.fetch = jest.fn(async (url, options) => ({ ok: true, json: async () => options?.method === 'PATCH'
      ? { ...account, limits: { ...account.limits, ...JSON.parse(options.body) } } : [account] }));
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); delete global.fetch; });
  const render = async () => { await act(async () => root.render(<OutreachAccounts />)); };
  const button = text => [...container.querySelectorAll('button')].find(x => x.textContent === text);
  const edit = async () => { await act(async () => button('Adjust').click()); };
  const change = async (index, value) => {
    const input = container.querySelectorAll('input[type="number"]')[index];
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
  };
  const writes = () => global.fetch.mock.calls.filter(([, options]) => options?.method === 'PATCH');

  it('does not infer dedicated proxy, live health or warm-up evidence from a hostname', async () => {
    account.proxy = { host: 'configured.example', status: 'healthy' };
    await render();
    expect(container.textContent).toContain('Configured proxy');
    expect(container.textContent).toContain('Saved status: Active');
    expect(container.textContent).toContain('Live health is not verified here');
    expect(container.textContent).not.toContain('1:1 Dedicated');
    expect(container.textContent).not.toContain('Warmup: Level 1');
    expect(container.textContent).toContain('Warm-up level: Not recorded');
  });

  it('keeps zero caps and does not invent missing or malformed caps', async () => {
    account.limits = { connection_invites: 0, messages: '20' };
    await render();
    expect(container.textContent).toContain('Saved daily caps');
    expect(container.textContent).toContain('0/day');
    expect(container.textContent).toContain('Not recorded');
    expect(container.textContent).not.toContain('20/day');
    expect(container.textContent).toContain('Actual allowance can be lower');
  });

  it('shows a recorded stop and timestamp without treating elapsed cooldown as clearance', async () => {
    account.stop_reason = 'rate_limited_429'; account.cooldown_until = '2020-01-02T03:04:05Z';
    account.warmup_level = 4;
    await render();
    expect(container.textContent).toContain('Recorded stop: Rate limit');
    expect(container.querySelector('time').dateTime).toBe('2020-01-02T03:04:05.000Z');
    expect(container.textContent).toContain('Elapsed cooldown does not clear a recorded stop');
    expect(container.textContent).toContain('Warm-up level: 4');
  });

  it('holds malformed stop/timing metadata without rendering provider error text', async () => {
    account.stop_reason = 'mongodb://private-provider-error'; account.cooldown_until = 'broken';
    await render();
    expect(container.textContent).toContain('Recorded stop requires review');
    expect(container.textContent).toContain('Cooldown timing requires review');
    expect(container.textContent).not.toContain('private-provider-error');
  });

  it('leaves unknown fields blank and submits only the cap explicitly changed', async () => {
    account.limits = { connection_invites: 50, messages: 20 };
    await render(); await edit();
    expect([...container.querySelectorAll('input')].map(x => x.value)).toEqual(['50', '20', '']);
    expect(button('Save Limits').disabled).toBe(true);
    await change(1, '7');
    await act(async () => button('Save Limits').click());
    expect(writes()).toHaveLength(1);
    expect(JSON.parse(writes()[0][1].body)).toEqual({ messages: 7 });
    expect(container.textContent).toContain('50/day');
  });

  it.each(['', '1.5', '-1', '36'])('does not silently coerce an invalid edited cap %s', async value => {
    account.limits = { messages: 20 }; await render(); await edit(); await change(1, value);
    expect(button('Save Limits').disabled).toBe(true);
    expect(writes()).toHaveLength(0);
  });

  it('permits an explicit zero cap', async () => {
    account.limits = { messages: 20 }; await render(); await edit(); await change(1, '0');
    await act(async () => button('Save Limits').click());
    expect(JSON.parse(writes()[0][1].body)).toEqual({ messages: 0 });
  });

  it('does not resend a cap restored to its opening value while saving another cap', async () => {
    account.limits = { messages: 20 }; await render(); await edit();
    await change(1, '7'); await change(1, '20');
    expect(button('Save Limits').disabled).toBe(true);
    account.limits.messages = 22; // Another writer changed the stored cap.
    await change(2, '3');
    await act(async () => button('Save Limits').click());
    expect(JSON.parse(writes()[0][1].body)).toEqual({ email_sends: 3 });
    expect(container.textContent).toContain('22/day');
  });
});
