export const GOOGLE_PHOTOS_SCOPE = 'https://www.googleapis.com/auth/photospicker.mediaitems.readonly';
export const GOOGLE_PHOTOS_IMPORT_STATE_PREFIX = 'google_photos_import';

const randomStateSuffix = () => {
  if (typeof window !== 'undefined' && window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
};

export const buildGooglePhotosImportState = (mode = 'image') => (
  `${GOOGLE_PHOTOS_IMPORT_STATE_PREFIX}:${mode}:${randomStateSuffix()}`
);

export const isGooglePhotosImportState = (state = '') => (
  typeof state === 'string' && state.startsWith(`${GOOGLE_PHOTOS_IMPORT_STATE_PREFIX}:`)
);

export const buildGooglePhotosAuthUrl = ({ clientId, redirectUri, state }) => {
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: 'token',
    scope: GOOGLE_PHOTOS_SCOPE,
    include_granted_scopes: 'true',
    prompt: 'consent',
    state,
  });
  return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
};

export const getGoogleOAuthHashParams = (hashValue) => {
  const rawHash = typeof hashValue === 'string'
    ? hashValue
    : (typeof window !== 'undefined' ? window.location.hash : '');
  return new URLSearchParams(rawHash.startsWith('#') ? rawHash.slice(1) : rawHash);
};
