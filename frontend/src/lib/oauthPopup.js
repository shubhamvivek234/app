const OAUTH_CHANNEL_NAME = 'oauth-status';
const OAUTH_RESULT_STORAGE_KEY = 'oauth_result';
const OAUTH_POPUP_EXPECTED_KEY = 'oauth_popup_expected';

export const markOAuthPopupExpected = (expected) => {
  localStorage.setItem(OAUTH_POPUP_EXPECTED_KEY, expected ? '1' : '0');
};

export const isOAuthPopupExpected = () => localStorage.getItem(OAUTH_POPUP_EXPECTED_KEY) === '1';

export const clearOAuthPopupExpected = () => {
  localStorage.removeItem(OAUTH_POPUP_EXPECTED_KEY);
};

export const broadcastOAuthResult = (payload) => {
  const message = { ...payload, ts: Date.now() };

  if (typeof BroadcastChannel !== 'undefined') {
    const channel = new BroadcastChannel(OAUTH_CHANNEL_NAME);
    channel.postMessage(message);
    channel.close();
  }

  localStorage.setItem(OAUTH_RESULT_STORAGE_KEY, JSON.stringify(message));
};

export const listenForOAuthResult = (handler) => {
  let channel = null;

  const onStorage = (event) => {
    if (event.key !== OAUTH_RESULT_STORAGE_KEY || !event.newValue) return;
    try {
      handler(JSON.parse(event.newValue));
    } catch (_) {
      // Ignore malformed storage payloads.
    }
  };

  if (typeof BroadcastChannel !== 'undefined') {
    channel = new BroadcastChannel(OAUTH_CHANNEL_NAME);
    channel.onmessage = (event) => handler(event.data);
  }

  window.addEventListener('storage', onStorage);

  return () => {
    if (channel) channel.close();
    window.removeEventListener('storage', onStorage);
  };
};
