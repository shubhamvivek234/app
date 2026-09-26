import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import ConnectLinkedInModal from './ConnectLinkedInModal';

describe('LinkedIn sender session connection', () => {
  let container;
  let root;

  const renderModal = async (props = {}) => {
    await act(async () => root.render(
      <ConnectLinkedInModal isOpen onClose={() => {}} {...props} />
    ));
  };

  const enterValue = async (id, value) => {
    const input = container.querySelector(`#${id}`);
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
  };

  const submit = async () => {
    await act(async () => container.querySelector('form').dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true })
    ));
  };

  beforeEach(() => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    localStorage.clear();
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    delete global.fetch;
  });

  it('opens directly to one session form with honest platform and secret disclosures', async () => {
    global.fetch = jest.fn();
    await renderModal();

    const dialog = container.querySelector('[role="dialog"]');
    expect(dialog).not.toBeNull();
    expect(document.activeElement).toBe(dialog);
    expect(dialog.getAttribute('aria-describedby')).toContain('linkedin-platform-notice');
    expect(container.querySelector('form')).not.toBeNull();
    expect(container.textContent).toContain('Connect LinkedIn sender');
    expect(container.textContent).toContain('not an official LinkedIn OAuth connection');
    expect(container.textContent).toContain('account restriction');
    expect(container.textContent).toContain('dedicated residential proxy');
    expect(container.textContent).toContain('Treat session cookies like a password');
    expect(container.textContent).toContain('encrypted before storage');
    expect(container.querySelector('#linkedin-proxy-country').value).toBe('US');
    expect(container.textContent).toContain('purchased proxy');
    expect(container.querySelectorAll('form')).toHaveLength(1);
    expect(container.querySelector('input[type="email"]')).toBeNull();
    expect(container.querySelector('input[name="password"]')).toBeNull();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('keeps LinkedIn sign-in as a manual helper, not a second connection path', async () => {
    global.fetch = jest.fn();
    await renderModal();
    const link = [...container.querySelectorAll('a')].find((item) => item.textContent.includes('Open LinkedIn'));

    expect(link.href).toBe('https://www.linkedin.com/login');
    expect(link.target).toBe('_blank');
    expect(link.rel).toContain('noopener');
    expect(container.textContent).toContain('return here and enter your session values');
    await act(async () => link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })));
    expect(container.querySelector('form')).not.toBeNull();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('requires both li_at and JSESSIONID before requesting a connection', async () => {
    global.fetch = jest.fn();
    await renderModal();
    await submit();
    expect(container.querySelector('[role="alert"]').textContent).toContain('li_at');
    await enterValue('linkedin-li-at', 'AQvalid');
    await submit();
    expect(container.querySelector('[role="alert"]').textContent).toContain('JSESSIONID');
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('does not mix session values from two pasted cookie headers', async () => {
    await renderModal();
    await enterValue('linkedin-li-at', 'li_at=AQfirst; JSESSIONID="ajax:first"; li_a=nav-first');
    await enterValue('linkedin-li-at', 'li_at=AQsecond; other=value');
    expect(container.querySelector('#linkedin-li-at').value).toBe('AQsecond');
    expect(container.querySelector('#linkedin-jsession').value).toBe('');
    expect(container.querySelector('#linkedin-li-a').value).toBe('');
  });

  it('verifies pasted session values and reports only a confirmed account', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: async () => ({ id: 'sender-1' }) }));
    const onAccountConnected = jest.fn();
    const onClose = jest.fn();
    await renderModal({ onClose, onAccountConnected });
    await enterValue('linkedin-li-at', 'li_at=AQvalid; JSESSIONID="ajax:123"; li_a=nav-token');
    await submit();

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/v1/outreach/accounts/connect-cookie');
    expect(options.credentials).toBe('include');
    expect(JSON.parse(options.body)).toMatchObject({
      li_at: 'AQvalid', jsession_id: 'ajax:123', li_a: 'nav-token',
      country_code: 'US', premium_product: 'classic',
    });
    expect(onAccountConnected).toHaveBeenCalledWith({ id: 'sender-1' });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(container.querySelector('#linkedin-li-at').value).toBe('');
  });

  it('submits the purchased proxy country instead of forcing US', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: async () => ({ id: 'sender-in' }) }));
    await renderModal();
    await enterValue('linkedin-li-at', 'li_at=AQvalid; JSESSIONID="ajax:123"');
    await enterValue('linkedin-proxy-country', 'in');
    await submit();
    expect(JSON.parse(global.fetch.mock.calls[0][1].body).country_code).toBe('IN');
  });

  it('reconnects the same sender using its existing country and account ID', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: async () => ({ id: 'sender-1' }) }));
    await renderModal({ reconnectAccount: { id: 'sender-1', country_code: 'IN' } });
    expect(container.querySelector('#linkedin-proxy-country').value).toBe('IN');
    expect(container.textContent).toContain('Reconnect LinkedIn sender');
    await enterValue('linkedin-li-at', 'li_at=AQvalid; JSESSIONID="ajax:123"');
    await submit();
    expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toMatchObject({
      country_code: 'IN', reconnect_account_id: 'sender-1',
    });
  });

  it('shows failed verification without marking the sender connected', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: false, json: async () => ({ detail: 'LinkedIn session expired' }) }));
    const onAccountConnected = jest.fn();
    await renderModal({ onAccountConnected });
    await enterValue('linkedin-li-at', 'li_at=AQexpired; JSESSIONID="ajax:123"');
    await submit();

    expect(container.querySelector('[role="alert"]').textContent).toContain('LinkedIn session expired');
    expect(onAccountConnected).not.toHaveBeenCalled();
    expect(container.querySelector('button[type="submit"]').disabled).toBe(false);
  });

  it('accepts individually copied cookies and preserves the selected account details', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: async () => ({ id: 'sender-nav' }) }));
    localStorage.setItem('token', 'app-token');
    await renderModal();
    await enterValue('linkedin-li-at', 'AQdirect');
    await enterValue('linkedin-jsession', 'JSESSIONID="ajax:direct"');
    await enterValue('linkedin-li-a', 'li_a=nav-direct');
    await enterValue('linkedin-user-agent', 'Test browser agent');
    await act(async () => {
      const product = container.querySelector('#linkedin-premium-product');
      product.value = 'sales_navigator';
      product.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await submit();

    const options = global.fetch.mock.calls[0][1];
    expect(options.headers.Authorization).toBe('Bearer app-token');
    expect(JSON.parse(options.body)).toMatchObject({
      li_at: 'AQdirect', jsession_id: 'ajax:direct', li_a: 'nav-direct',
      premium_product: 'sales_navigator', user_agent: 'Test browser agent',
    });
  });

  it('does not treat an unconfirmed success response as a connected sender', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: async () => ({ status: 'pending' }) }));
    const onAccountConnected = jest.fn();
    await renderModal({ onAccountConnected });
    await enterValue('linkedin-li-at', 'li_at=AQvalid; JSESSIONID="ajax:123"');
    await submit();
    expect(container.querySelector('[role="alert"]').textContent).toContain('not confirmed');
    expect(onAccountConnected).not.toHaveBeenCalled();
  });

  it('shows a retryable error when the network request fails', async () => {
    global.fetch = jest.fn(() => Promise.reject(new Error('Connection unavailable')));
    await renderModal();
    await enterValue('linkedin-li-at', 'li_at=AQvalid; JSESSIONID="ajax:123"');
    await submit();
    expect(container.querySelector('[role="alert"]').textContent).toContain('Connection unavailable');
    expect(container.querySelector('button[type="submit"]').disabled).toBe(false);
  });

  it('uses a safe fallback message when the API returns an empty error body', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: false, json: async () => null }));
    await renderModal();
    await enterValue('linkedin-li-at', 'li_at=AQexpired; JSESSIONID="ajax:123"');
    await submit();
    expect(container.querySelector('[role="alert"]').textContent).toContain('LinkedIn session verification failed');
  });

  it('prevents a second submission while verification is in flight', async () => {
    let finishRequest;
    global.fetch = jest.fn(() => new Promise((resolve) => { finishRequest = resolve; }));
    await renderModal();
    await enterValue('linkedin-li-at', 'li_at=AQvalid; JSESSIONID="ajax:123"');
    await act(async () => {
      const form = container.querySelector('form');
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(container.querySelector('button[type="submit"]').disabled).toBe(true);
    expect(container.querySelector('button[aria-label="Close connection dialog"]').disabled).toBe(true);
    await act(async () => finishRequest({ ok: false, json: async () => ({ detail: 'Try again' }) }));
    expect(container.querySelector('button[type="submit"]').disabled).toBe(false);
  });

  it('clears secret inputs when cancelled and when reopened', async () => {
    const onClose = jest.fn();
    await renderModal({ onClose });
    await enterValue('linkedin-li-at', 'AQprivate');
    await enterValue('linkedin-jsession', 'ajax:private');
    await act(async () => container.querySelector('button[aria-label="Cancel connection"]').click());
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(container.querySelector('#linkedin-li-at').value).toBe('');
    expect(container.querySelector('#linkedin-jsession').value).toBe('');

    await renderModal({ isOpen: false, onClose });
    await renderModal({ isOpen: true, onClose });
    expect(container.querySelector('#linkedin-li-at').value).toBe('');
  });

  it('clears pasted tokens when the dialog close button is used', async () => {
    const onClose = jest.fn();
    await renderModal({ onClose });
    await enterValue('linkedin-li-at', 'AQprivate');
    await act(async () => container.querySelector('button[aria-label="Close connection dialog"]').click());
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(container.querySelector('#linkedin-li-at').value).toBe('');
  });

  it('supports Escape and restores focus to the opener after closing', async () => {
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();
    const onClose = jest.fn();
    await renderModal({ onClose });
    const dialog = container.querySelector('[role="dialog"]');
    await act(async () => dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    expect(onClose).toHaveBeenCalledTimes(1);
    await renderModal({ isOpen: false, onClose });
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });
});
