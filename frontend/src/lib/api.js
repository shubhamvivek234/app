import axios from 'axios';
import env from '@/env';

const BACKEND_URL = env.BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const SOCIAL_ACCOUNTS_CACHE_KEY = 'social_accounts_cache_v2';
const SOCIAL_ACCOUNTS_CACHE_TTL_MS = 60 * 1000;

const getAuthHeaders = () => {
  return {};
};

const getDefaultScheduleTimezone = () => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
};

const normalizeSocialAccount = (account) => {
  if (!account || typeof account !== 'object') return null;

  const platform = typeof account.platform === 'string'
    ? account.platform.toLowerCase()
    : null;

  const rawId = account.id
    || account.account_id
    || (platform && account.platform_user_id ? `${platform}:${account.platform_user_id}` : null)
    || (platform && (account.platform_username || account.display_name)
      ? `${platform}:${account.platform_username || account.display_name}`
      : null);

  if (!platform || !rawId) return null;

  return {
    ...account,
    id: String(rawId),
    account_id: String(account.account_id || rawId),
    platform,
    platform_user_id: account.platform_user_id ? String(account.platform_user_id) : null,
    platform_username: typeof account.platform_username === 'string' ? account.platform_username : null,
    display_name: typeof account.display_name === 'string' ? account.display_name : null,
    picture_url: typeof account.picture_url === 'string' ? account.picture_url : null,
  };
};

const normalizeSocialAccounts = (accounts) => (
  Array.isArray(accounts)
    ? accounts.map(normalizeSocialAccount).filter(Boolean)
    : []
);

const DIRECT_UPLOAD_FALLBACK_STATUSES = new Set([404, 405, 501]);

const readSocialAccountsCache = (maxAgeMs = SOCIAL_ACCOUNTS_CACHE_TTL_MS) => {
  try {
    const raw = localStorage.getItem(SOCIAL_ACCOUNTS_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.data) || typeof parsed.timestamp !== 'number') {
      return null;
    }
    if (Date.now() - parsed.timestamp > maxAgeMs) {
      return null;
    }
    return normalizeSocialAccounts(parsed.data);
  } catch {
    return null;
  }
};

const writeSocialAccountsCache = (accounts) => {
  try {
    const normalizedAccounts = normalizeSocialAccounts(accounts);
    localStorage.setItem(
      SOCIAL_ACCOUNTS_CACHE_KEY,
      JSON.stringify({
        data: normalizedAccounts,
        timestamp: Date.now(),
      })
    );
  } catch {
    // Ignore cache write failures.
  }
};

const postLegacyUpload = async (file, onProgress, options = {}) => {
  const formData = new FormData();
  formData.append('file', file);
  if (options.purpose) formData.append('purpose', options.purpose);
  if (options.composerSessionId) formData.append('composer_session_id', options.composerSessionId);

  const response = await axios.post(`${API}/upload`, formData, {
    headers: {
      ...getAuthHeaders(),
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: onProgress,
  });
  return response.data;
};

const abortDirectUpload = async (mediaJobId, reason = 'Upload aborted') => {
  if (!mediaJobId) return;
  try {
    await axios.post(
      `${API}/upload/${mediaJobId}/abort`,
      { reason },
      { headers: getAuthHeaders() }
    );
  } catch (error) {
    console.warn('Direct upload abort failed', error);
  }
};

const emitUploadProgress = (onProgress, loaded, total) => {
  if (!onProgress) return;
  onProgress({
    loaded,
    total,
    progress: total > 0 ? loaded / total : undefined,
  });
};

const encodePathSegment = (value) => {
  const stringValue = String(value ?? '');
  const bytes = new TextEncoder().encode(stringValue);
  let binary = '';
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  const base64Value = btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  return `b64.${base64Value}`;
};

const uploadSinglePartToCloud = async (file, upload, onProgress) => {
  await axios.put(upload.url, file, {
    headers: upload.headers || { 'Content-Type': file.type || 'application/octet-stream' },
    onUploadProgress: (event) => {
      emitUploadProgress(onProgress, event.loaded || 0, file.size);
    },
  });
};

const uploadMultipartToCloud = async (file, upload, onProgress) => {
  const partSize = upload.part_size_bytes || 64 * 1024 * 1024;
  let uploadedBytes = 0;
  const completedParts = [];

  for (const part of upload.parts || []) {
    const start = (part.part_number - 1) * partSize;
    const end = Math.min(start + partSize, file.size);
    const chunk = file.slice(start, end);

    const response = await axios.put(part.url, chunk, {
      headers: {
        'Content-Type': 'application/octet-stream',
      },
      onUploadProgress: (event) => {
        emitUploadProgress(
          onProgress,
          uploadedBytes + (event.loaded || 0),
          file.size
        );
      },
    });

    const etag = response.headers?.etag || response.headers?.ETag;
    if (!etag) {
      throw new Error('Missing ETag from multipart upload response. Check R2 CORS exposed headers.');
    }

    uploadedBytes += chunk.size;
    emitUploadProgress(onProgress, uploadedBytes, file.size);
    completedParts.push({
      PartNumber: part.part_number,
      ETag: etag,
    });
  }

  return completedParts;
};

// Posts
export const createPost = async (postData) => {
  const normalizedPostData = {
    ...postData,
    ...(postData?.scheduled_time && !postData?.timezone ? { timezone: getDefaultScheduleTimezone() } : {}),
  };
  const response = await axios.post(`${API}/posts`, normalizedPostData, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const getPosts = async (status = null, params = {}) => {
  const query = new URLSearchParams();
  if (status) query.set('status', status);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, value);
    }
  });
  const url = query.toString() ? `${API}/posts?${query.toString()}` : `${API}/posts`;
  const response = await axios.get(url, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const getRecentPublishedPosts = async (limit = 25) => {
  const response = await axios.get(`${API}/posts/recent-published?limit=${limit}`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const getPost = async (postId) => {
  const response = await axios.get(`${API}/posts/${postId}`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const updatePost = async (postId, updateData) => {
  const response = await axios.patch(`${API}/posts/${postId}`, updateData, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const deletePost = async (postId) => {
  const response = await axios.delete(`${API}/posts/${postId}`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// AI Content Generation
export const generateContent = async (prompt, platform = null, tone = null, language = null) => {
  const response = await axios.post(
    `${API}/ai/generate-content`,
    { prompt, platform, tone, language },
    {
      headers: getAuthHeaders(),
    }
  );
  return response.data;
};

// AI Hashtag Generation
export const generateHashtags = async (topic, platform = null, count = 20) => {
  const response = await axios.post(
    `${API}/ai/generate-hashtags`,
    { topic, platform, count },
    { headers: getAuthHeaders() }
  );
  return response.data; // { hashtags: ["#tag1", "#tag2", ...] }
};

// Universal Content Repurposer
export const repurposeContent = async (urlOrText, { tone = 'engaging', useBrandVoice = true } = {}) => {
  const response = await axios.post(
    `${API}/ai/repurpose`,
    { url_or_text: urlOrText, tone, use_brand_voice: useBrandVoice },
    { headers: getAuthHeaders() }
  );
  return response.data;
};

// Voice-to-Post (PostCast)
export const voiceToPost = async (audioBase64, mimeType = 'audio/webm', { tone = null, useBrandVoice = true } = {}) => {
  const response = await axios.post(
    `${API}/ai/voice-to-post`,
    { audio_base64: audioBase64, mime_type: mimeType, tone, use_brand_voice: useBrandVoice },
    { headers: getAuthHeaders() }
  );
  return response.data;
};

// Content DNA Voice Profiler
export const scanContentDNA = async () => {
  const response = await axios.post(
    `${API}/ai/content-dna/scan`,
    {},
    { headers: getAuthHeaders() }
  );
  return response.data;
};

// Focus Mode AI Comment Suggestions
export const suggestAIComment = async (postContent, authorName = '', platform = 'linkedin') => {
  const response = await axios.post(
    `${API}/ai/suggest-comment`,
    { post_content: postContent, author_name: authorName, platform },
    { headers: getAuthHeaders() }
  );
  return response.data;
};

// Social Accounts
export const connectSocialAccount = async (platform, platformUsername) => {
  const response = await axios.post(
    `${API}/social-accounts`,
    { platform, platform_username: platformUsername },
    {
      headers: getAuthHeaders(),
    }
  );
  return response.data;
};

export const getCachedSocialAccounts = (maxAgeMs = SOCIAL_ACCOUNTS_CACHE_TTL_MS) =>
  readSocialAccountsCache(maxAgeMs);

export const getSocialAccounts = async () => {
  const response = await axios.get(`${API}/social-accounts`, {
    headers: getAuthHeaders(),
  });
  const normalizedAccounts = normalizeSocialAccounts(response.data);
  writeSocialAccountsCache(normalizedAccounts);
  return normalizedAccounts;
};

export const disconnectSocialAccount = async (accountId) => {
  const response = await axios.delete(`${API}/social-accounts/${accountId}`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// Payments
export const createCheckout = async (plan, paymentMethod) => {
  const response = await axios.post(
    `${API}/payments/checkout`,
    { plan, payment_method: paymentMethod },
    {
      headers: {
        ...getAuthHeaders(),
        origin: window.location.origin,
      },
    }
  );
  return response.data;
};

export const getPaymentStatus = async (sessionId) => {
  const response = await axios.get(`${API}/payments/status/${sessionId}`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// Stats
export const getStats = async () => {
  const response = await axios.get(`${API}/stats`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const getDashboardOverview = async ({ days = 7, refresh = false, sections = null } = {}) => {
  const params = new URLSearchParams();
  if (days) params.set('days', String(days));
  if (refresh) params.set('refresh', 'true');
  if (Array.isArray(sections) && sections.length > 0) {
    params.set('sections', sections.join(','));
  } else if (typeof sections === 'string' && sections.trim()) {
    params.set('sections', sections.trim());
  }
  const query = params.toString();
  const response = await axios.get(`${API}/dashboard/overview${query ? `?${query}` : ''}`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// Media Upload with progress tracking
export const uploadMedia = async (file, onProgress, options = {}) => {
  let mediaJobId = null;

  try {
    const sessionResponse = await axios.post(
      `${API}/upload/session`,
      {
        filename: file.name,
        file_size_bytes: file.size,
        content_type: file.type || 'application/octet-stream',
        ...(options.purpose ? { purpose: options.purpose } : {}),
        ...(options.composerSessionId ? { composer_session_id: options.composerSessionId } : {}),
      },
      {
        headers: getAuthHeaders(),
      }
    );

    const session = sessionResponse.data;
    mediaJobId = session.media_job_id;
    const upload = session.upload;

    let completedParts = [];
    if (upload.mode === 'multipart') {
      completedParts = await uploadMultipartToCloud(file, upload, onProgress);
    } else {
      await uploadSinglePartToCloud(file, upload, onProgress);
      emitUploadProgress(onProgress, file.size, file.size);
    }

    const completeResponse = await axios.post(
      `${API}/upload/complete`,
      {
        media_job_id: mediaJobId,
        upload_id: upload.upload_id || null,
        parts: completedParts,
      },
      {
        headers: getAuthHeaders(),
      }
    );
    return completeResponse.data;
  } catch (error) {
    const status = error?.response?.status;
    if (DIRECT_UPLOAD_FALLBACK_STATUSES.has(status)) {
      return postLegacyUpload(file, onProgress, options);
    }
    await abortDirectUpload(mediaJobId, error?.message || 'Upload failed');
    throw error;
  }
};

export const cleanupTemporaryAudio = async (
  { mediaIds = [], composerSessionId = null, reason = 'composer_abandoned' } = {},
  { keepalive = false } = {}
) => {
  const payload = {
    media_ids: mediaIds,
    composer_session_id: composerSessionId,
    reason,
  };
  if (keepalive && typeof fetch === 'function') {
    const response = await fetch(`${API}/media/audio/temp/cleanup`, {
      method: 'POST',
      headers: {
        ...getAuthHeaders(),
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      keepalive: true,
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error('Temporary audio cleanup failed');
    }
    return response.json();
  }
  const response = await axios.post(`${API}/media/audio/temp/cleanup`, payload, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const getUploadStatus = async (mediaJobId) => {
  const response = await axios.get(`${API}/upload/${mediaJobId}`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const waitForUploadReady = async (
  mediaJobId,
  { intervalMs = 2000, timeoutMs = 300000, onPoll = null } = {}
) => {
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    const asset = await getUploadStatus(mediaJobId);
    onPoll?.(asset);

    if (asset.status === 'ready' || asset.status === 'archived') {
      return asset;
    }
    if (asset.status === 'failed') {
      throw new Error(asset.error_message || 'Upload processing failed');
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  throw new Error('Upload processing timed out');
};

export const getAudioAssets = async () => {
  const response = await axios.get(`${API}/media-assets`, {
    headers: getAuthHeaders(),
    params: { asset_kind: 'audio' },
  });
  return response.data;
};

export const renderVideoAudio = async (videoMediaId, mix) => {
  const response = await axios.post(
    `${API}/media/${videoMediaId}/audio/render`,
    { mix },
    { headers: getAuthHeaders() }
  );
  return response.data;
};

export const getAudioRenderStatus = async (renderJobId) => {
  const response = await axios.get(`${API}/media/audio-renders/${renderJobId}`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const waitForAudioRenderReady = async (
  renderJobId,
  { intervalMs = 2500, timeoutMs = 600000, onPoll = null } = {}
) => {
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    const asset = await getAudioRenderStatus(renderJobId);
    onPoll?.(asset);

    if (asset.status === 'ready') {
      return asset;
    }
    if (asset.status === 'failed') {
      throw new Error(asset.error_message || 'Audio render failed');
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  throw new Error('Audio render timed out');
};

export const searchUnsplashMedia = async ({ query, page = 1 }) => {
  const response = await axios.get(`${API}/media-sources/unsplash/search`, {
    headers: getAuthHeaders(),
    params: {
      q: query,
      page,
    },
  });
  return response.data;
};

export const importRemoteMedia = async (items) => {
  const response = await axios.post(
    `${API}/media-sources/import`,
    { items },
    {
      headers: getAuthHeaders(),
    }
  );
  return response.data;
};

export const getCanvaImportUrl = async () => {
  const response = await axios.get(`${API}/media-sources/canva/url`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const submitCanvaImportCallback = async (callbackData) => {
  const response = await axios.post(`${API}/media-sources/canva/callback`, callbackData, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const listCanvaDesigns = async ({ sessionId, query = '', continuation = null } = {}) => {
  const response = await axios.get(`${API}/media-sources/canva/designs`, {
    headers: getAuthHeaders(),
    params: {
      session_id: sessionId,
      query: query || undefined,
      continuation: continuation || undefined,
    },
  });
  return response.data;
};

export const createCanvaExport = async ({ sessionId, designId, fileType }) => {
  const response = await axios.post(
    `${API}/media-sources/canva/exports`,
    {
      session_id: sessionId,
      design_id: designId,
      file_type: fileType,
    },
    {
      headers: getAuthHeaders(),
    }
  );
  return response.data;
};

export const getCanvaExport = async ({ sessionId, exportId }) => {
  const response = await axios.get(`${API}/media-sources/canva/exports/${exportId}`, {
    headers: getAuthHeaders(),
    params: {
      session_id: sessionId,
    },
  });
  return response.data;
};

// Failed Posts (Dead Letter Queue)
export const getFailedPosts = async () => {
  const response = await axios.get(`${API}/posts/failed`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const retryFailedPost = async (postId, platform = null) => {
  const url = platform
    ? `${API}/posts/${postId}/retry?platform=${platform}`
    : `${API}/posts/${postId}/retry`;
  const response = await axios.post(url, {}, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// ── Hashtag Groups (Stub - to be implemented) ──
export const createHashtagGroup = async (data) => {
  const response = await axios.post(`${API}/hashtag-groups`, data, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const updateHashtagGroup = async (groupId, data) => {
  const response = await axios.patch(`${API}/hashtag-groups/${groupId}`, data, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const deleteHashtagGroup = async (groupId) => {
  const response = await axios.delete(`${API}/hashtag-groups/${groupId}`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// ── Inbox Messages ──
export const getInbox = async (params = {}) => {
  const response = await axios.get(`${API}/inbox`, {
    headers: getAuthHeaders(),
    params,
  });
  return response.data;
};

export const getInboxStats = async () => {
  const response = await axios.get(`${API}/inbox/stats`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const updateInboxMessage = async (messageId, data) => {
  const response = await axios.patch(`${API}/inbox/${messageId}`, data, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const deleteInboxMessage = async (messageId) => {
  const response = await axios.delete(`${API}/inbox/${messageId}`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const createInboxMessage = async (data) => {
  const response = await axios.post(`${API}/inbox`, data, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// ── Media Assets (Stub - to be implemented) ──
export const getMediaAssets = async () => {
  const response = await axios.get(`${API}/media-assets`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const uploadMediaAsset = async (file, onProgress) => {
  try {
    // Prefer Direct-to-R2 cloud upload with progress support
    const res = await uploadMedia(file, onProgress);
    return res;
  } catch (directErr) {
    // Fallback to legacy endpoint if direct upload fails
    const formData = new FormData();
    formData.append('file', file);
    const response = await axios.post(`${API}/media-assets`, formData, {
      headers: {
        ...getAuthHeaders(),
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          onProgress(progressEvent);
        }
      },
    });
    return response.data;
  }
};

export const deleteMediaAsset = async (assetId) => {
  const response = await axios.delete(`${API}/media-assets/${assetId}`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// ── Public Calendar (Stub - to be implemented) ──
export const getPublicCalendar = async (workspaceId) => {
  const response = await axios.get(`${API}/calendar/public/${workspaceId}`);
  return response.data;
};

// ── Publish Feed (Stub - to be implemented) ──
export const getPublishFeed = async (params = {}) => {
  const response = await axios.get(`${API}/publish/feed`, {
    headers: getAuthHeaders(),
    params,
  });
  return response.data;
};

export const getConversations = async (platform, accountId = null, params = {}) => {
  const response = await axios.get(`${API}/conversations`, {
    headers: getAuthHeaders(),
    params: {
      platform,
      ...(accountId ? { accountId } : {}),
      ...params,
    },
  });
  return response.data;
};

export const syncInboxConversations = async (data = {}) => {
  const response = await axios.post(`${API}/conversations/sync`, data, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// ── Comments ──
export const getPostComments = async (platform, postId, accountId = null, params = {}) => {
  const response = await axios.get(`${API}/posts/${encodePathSegment(postId)}/comments`, {
    headers: getAuthHeaders(),
    params: {
      platform,
      ...(accountId ? { accountId } : {}),
      ...params,
    },
  });
  return response.data;
};

export const replyToComment = async (platform, postId, commentId, data) => {
  const response = await axios.post(
    `${API}/posts/${encodePathSegment(postId)}/comments/${encodePathSegment(commentId)}/reply`,
    { platform, ...data },
    { headers: getAuthHeaders() }
  );
  return response.data;
};

export const sendDmReply = async (platform, conversationId, data) => {
  const response = await axios.post(
    `${API}/conversations/${encodeURIComponent(conversationId)}/reply`,
    { platform, ...data },
    { headers: getAuthHeaders() }
  );
  return response.data;
};

// ── Recurring Posts (Stub - to be implemented) ──
export const getRecurringRules = async () => {
  const response = await axios.get(`${API}/recurring-rules`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const createRecurringRule = async (data) => {
  const response = await axios.post(`${API}/recurring-rules`, data, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const updateRecurringRule = async (ruleId, data) => {
  const response = await axios.patch(`${API}/recurring-rules/${ruleId}`, data, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const deleteRecurringRule = async (ruleId) => {
  const response = await axios.delete(`${API}/recurring-rules/${ruleId}`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// ── Account Settings ─────────────────────────────────────────────────────────
export const updateCurrentUser = async (data) => {
  const response = await axios.patch(`${API}/auth/me`, data, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const requestVerificationEmail = async (returnTo = null) => {
  const response = await axios.post(
    `${API}/auth/verify-email/request`,
    { return_to: returnTo },
    {
      headers: getAuthHeaders(),
    }
  );
  return response.data;
};

export const getNotificationPreferences = async () => {
  const response = await axios.get(`${API}/user/notification-preferences`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const updateNotificationPreferences = async (preferences) => {
  const response = await axios.patch(
    `${API}/user/notification-preferences`,
    { preferences },
    {
      headers: getAuthHeaders(),
    }
  );
  return response.data;
};

export const requestDataExport = async () => {
  const response = await axios.post(
    `${API}/user/data-export`,
    {},
    {
      headers: getAuthHeaders(),
    }
  );
  return response.data;
};

export const requestAccountDeletion = async () => {
  const response = await axios.delete(`${API}/user/account`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// ── Workspace Members (Stub - to be implemented) ──
export const getWorkspaceMembers = async () => {
  const response = await axios.get(`${API}/workspace/members`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const inviteWorkspaceMember = async (dataOrEmail, role = 'viewer') => {
  const payload = typeof dataOrEmail === 'string'
    ? { email: dataOrEmail, role }
    : dataOrEmail;
  const response = await axios.post(`${API}/workspace/members/invite`, payload, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const removeWorkspaceMember = async (memberId) => {
  const response = await axios.delete(
    `${API}/workspace/members/${memberId}`,
    { headers: getAuthHeaders() }
  );
  return response.data;
};

export const updateWorkspaceMemberRole = async (memberId, role) => {
  const response = await axios.patch(
    `${API}/workspace/members/${memberId}/role`,
    { role },
    { headers: getAuthHeaders() }
  );
  return response.data;
};

export const revokeWorkspaceInvite = async (inviteId) => {
  const response = await axios.delete(
    `${API}/workspace/invites/${inviteId}`,
    { headers: getAuthHeaders() }
  );
  return response.data;
};

// Notifications
export const getNotifications = async ({ unreadOnly = false, limit = 20 } = {}) => {
  const params = new URLSearchParams();
  if (unreadOnly) params.set('unread_only', 'true');
  if (limit) params.set('limit', String(limit));
  const query = params.toString();
  const url = `${API}/notifications${query ? `?${query}` : ''}`;
  const response = await axios.get(url, { headers: getAuthHeaders() });
  return response.data;
};

export const markNotificationRead = async (notificationId) => {
  const response = await axios.patch(
    `${API}/notifications/${notificationId}/read`,
    {},
    { headers: getAuthHeaders() }
  );
  return response.data;
};

export const markAllNotificationsRead = async () => {
  const response = await axios.patch(
    `${API}/notifications/read-all`,
    {},
    { headers: getAuthHeaders() }
  );
  return response.data;
};

export const deleteNotification = async (notificationId) => {
  await axios.delete(`${API}/notifications/${notificationId}`, {
    headers: getAuthHeaders(),
  });
  return true;
};

export const clearAllNotifications = async () => {
  const response = await axios.delete(`${API}/notifications/clear-all`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// ── Internal Notes (Stub - to be implemented) ──
export const addInternalNote = async (postId, data) => {
  const response = await axios.post(`${API}/posts/${postId}/internal-notes`, data, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const deleteInternalNote = async (noteId) => {
  const response = await axios.delete(`${API}/internal-notes/${noteId}`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// ── Post Review (Stub - to be implemented) ──
export const submitPostForReview = async (postId, data) => {
  const response = await axios.post(`${API}/posts/${postId}/submit-review`, data || {}, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// ── Hashtag Groups (Alternative getter) ──
export const getHashtagGroups = async () => {
  const response = await axios.get(`${API}/hashtag-groups`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// ── AI Image Generation (Stub - to be implemented) ──
export const generateImage = async (prompt, style) => {
  const response = await axios.post(
    `${API}/ai/generate-image`,
    { prompt, style },
    {
      headers: getAuthHeaders(),
    }
  );
  return response.data;
};

// ── Support ──
export const sendSupportRequest = async (formData) => {
  const response = await axios.post(`${API}/support/contact`, formData, {
    headers: { ...getAuthHeaders(), 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

// ── Approval Queue ──
export const getApprovalQueue = async () => {
  const response = await axios.get(`${API}/approvals`, { headers: getAuthHeaders() });
  return response.data;
};

export const getApprovalActivity = async (postId) => {
  const response = await axios.get(`${API}/approvals/${postId}/activity`, { headers: getAuthHeaders() });
  return response.data;
};

export const bulkApprovePosts = async (postIds) => {
  const response = await axios.post(`${API}/approvals/bulk/approve`, { post_ids: postIds }, { headers: getAuthHeaders() });
  return response.data;
};

export const bulkRejectPosts = async (postIds, reason = '') => {
  const response = await axios.post(`${API}/approvals/bulk/reject`, { post_ids: postIds, reason }, { headers: getAuthHeaders() });
  return response.data;
};

export const approvePost = async (postId) => {
  const response = await axios.post(`${API}/posts/${postId}/approve`, {}, { headers: getAuthHeaders() });
  return response.data;
};

export const rejectPost = async (postId, reason = '') => {
  const response = await axios.post(`${API}/posts/${postId}/reject`, { reason }, { headers: getAuthHeaders() });
  return response.data;
};

export const resubmitPost = async (postId, data = {}) => {
  const response = await axios.post(`${API}/posts/${postId}/resubmit`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const returnPostToDraft = async (postId) => {
  const response = await axios.post(`${API}/posts/${postId}/return-to-draft`, {}, { headers: getAuthHeaders() });
  return response.data;
};

// ── Bulk Upload ──
export const bulkCreatePosts = async (payload) => {
  const response = await axios.post(`${API}/posts/bulk`, payload, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const bulkCsvSchedule = async (payload) => {
  const response = await axios.post(`${API}/bulk/csv-schedule`, payload, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const validateBulkUrls = async (urls) => {
  const response = await axios.post(`${API}/bulk/validate-urls`, { urls }, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const downloadBulkCsvTemplate = async () => {
  const response = await axios.get(`${API}/bulk/csv-template`, {
    headers: getAuthHeaders(),
    responseType: 'blob',
  });
  return response.data;
};

export const downloadBulkTemplate = async () => {
  const response = await axios.get(`${API}/posts/bulk/template`, {
    headers: getAuthHeaders(),
    responseType: 'blob',
  });
  return response.data;
};

// ── RSS Feeds & Automations ──
export const validateRssFeed = async (feedUrl) => {
  const response = await axios.post(`${API}/rss/validate`, { feed_url: feedUrl }, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const getRssFeeds = async () => {
  const response = await axios.get(`${API}/rss/feeds`, { headers: getAuthHeaders() });
  return response.data;
};

export const createRssFeed = async (data) => {
  const response = await axios.post(`${API}/rss/feeds`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const getRssFeed = async (feedId) => {
  const response = await axios.get(`${API}/rss/feeds/${feedId}`, { headers: getAuthHeaders() });
  return response.data;
};

export const updateRssFeed = async (feedId, data) => {
  const response = await axios.patch(`${API}/rss/feeds/${feedId}`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const deleteRssFeed = async (feedId) => {
  const response = await axios.delete(`${API}/rss/feeds/${feedId}`, { headers: getAuthHeaders() });
  return response.data;
};

export const syncRssFeed = async (feedId) => {
  const response = await axios.post(`${API}/rss/feeds/${feedId}/sync`, {}, { headers: getAuthHeaders() });
  return response.data;
};

export const getRssItems = async (params = {}) => {
  const response = await axios.get(`${API}/rss/items`, {
    headers: getAuthHeaders(),
    params,
  });
  return response.data;
};

export const shareRssItem = async (itemId, data = {}) => {
  const response = await axios.post(`${API}/rss/items/${itemId}/share`, data, { headers: getAuthHeaders() });
  return response.data;
};

// ── API Keys ──
export const getApiKeys = async () => {
  const response = await axios.get(`${API}/api-keys`, { headers: getAuthHeaders() });
  return response.data;
};

export const createApiKey = async (data) => {
  const response = await axios.post(`${API}/api-keys`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const deleteApiKey = async (keyId) => {
  const response = await axios.delete(`${API}/api-keys/${keyId}`, { headers: getAuthHeaders() });
  return response.data;
};

export const getDeveloperScopes = async () => {
  const response = await axios.get(`${API}/developer/scopes`, { headers: getAuthHeaders() });
  return response.data;
};

export const getPersonalTokens = async () => {
  const response = await axios.get(`${API}/developer/personal-tokens`, { headers: getAuthHeaders() });
  return response.data;
};

export const createPersonalToken = async (data) => {
  const response = await axios.post(`${API}/developer/personal-tokens`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const deletePersonalToken = async (tokenId) => {
  const response = await axios.delete(`${API}/developer/personal-tokens/${tokenId}`, { headers: getAuthHeaders() });
  return response.data;
};

// ── Calendar Notes ──
const CALENDAR_NOTE_COLOR_ALIASES = {
  '#4caf50': 'green',
  '#2196f3': 'blue',
  '#ffc107': 'yellow',
  '#f44336': 'red',
  green: 'green',
  emerald: 'green',
  blue: 'blue',
  sky: 'blue',
  yellow: 'yellow',
  amber: 'yellow',
  red: 'red',
  rose: 'red',
};

const normalizeCalendarNoteColor = (color) => {
  const normalized = String(color || '').trim().toLowerCase();
  return CALENDAR_NOTE_COLOR_ALIASES[normalized] || 'green';
};

const normalizeCalendarNote = (note) => ({
  ...note,
  id: note?.id || note?.note_id || '',
  note_id: note?.note_id || note?.id || '',
  text: String(note?.text || note?.note || '').trim(),
  note: String(note?.note || note?.text || '').trim(),
  color: normalizeCalendarNoteColor(note?.color),
});

export const getCalendarNotes = async (paramsOrMonth) => {
  const params = typeof paramsOrMonth === 'string'
    ? { month: paramsOrMonth }
    : (paramsOrMonth || {});
  const response = await axios.get(`${API}/calendar/notes`, { headers: getAuthHeaders(), params });
  return Array.isArray(response.data) ? response.data.map(normalizeCalendarNote) : [];
};

export const createCalendarNote = async (data) => {
  const payload = {
    date: data?.date,
    note: String(data?.note || data?.text || '').trim(),
    color: normalizeCalendarNoteColor(data?.color),
  };
  const response = await axios.post(`${API}/calendar/notes`, payload, { headers: getAuthHeaders() });
  return normalizeCalendarNote(response.data);
};

export const deleteCalendarNote = async (noteId) => {
  const response = await axios.delete(`${API}/calendar/notes/${noteId}`, { headers: getAuthHeaders() });
  return response.data;
};

export const createCalendarShare = async (data) => {
  const response = await axios.post(`${API}/calendar/share`, data, { headers: getAuthHeaders() });
  return response.data;
};

// ── Billing ──
export const capturePaypal = async (data) => {
  const response = await axios.post(`${API}/billing/paypal/capture`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const completeOnboarding = async (data) => {
  const response = await axios.post(`${API}/onboarding/complete`, data, { headers: getAuthHeaders() });
  return response.data;
};

// ── Connected Accounts ──
export const connectBluesky = async (data) => {
  const response = await axios.post(`${API}/social-accounts/bluesky/connect`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const connectDiscord = async (webhookUrl, channelName) => {
  const response = await axios.post(`${API}/social-accounts/discord/connect`, { webhook_url: webhookUrl, channel_name: channelName || null }, { headers: getAuthHeaders() });
  return response.data;
};

export const connectTelegram = async (botToken, chatId, channelName) => {
  const response = await axios.post(
    `${API}/social-accounts/telegram/connect`,
    { bot_token: botToken, chat_id: chatId, channel_name: channelName || null },
    { headers: getAuthHeaders() },
  );
  return response.data;
};

export const testAccountConnection = async (accountId) => {
  const response = await axios.post(
    `${API}/social-accounts/${accountId}/test-connection`,
    {},
    { headers: getAuthHeaders() },
  );
  return response.data;
};

export const connectMastodon = async (instanceUrl, accessToken) => {
  const response = await axios.post(
    `${API}/social-accounts/mastodon/connect`,
    { instance_url: instanceUrl, access_token: accessToken },
    { headers: getAuthHeaders() },
  );
  return response.data;
};

export const getLinkedInPendingOrgs = async () => {
  const response = await axios.get(`${API}/social-accounts/linkedin/pending-orgs`, { headers: getAuthHeaders() });
  return response.data;
};

export const saveLinkedInOrgs = async (data) => {
  const response = await axios.post(`${API}/social-accounts/linkedin/save-orgs`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const addLinkedInPageManually = async (data) => {
  const response = await axios.post(`${API}/social-accounts/linkedin/manual`, data, { headers: getAuthHeaders() });
  return response.data;
};

// ── Posts (extra actions) ──
export const duplicatePost = async (postId) => {
  const response = await axios.post(`${API}/posts/${postId}/duplicate`, {}, { headers: getAuthHeaders() });
  return response.data;
};

// ── Workspace Invites ──
export const getWorkspaceInviteDetails = async (token) => {
  const response = await axios.get(`${API}/workspace/invite/${token}`);
  return response.data;
};

export const acceptWorkspaceInvite = async (token, data) => {
  const response = await axios.post(`${API}/workspace/invite/${token}/accept`, data || {}, { headers: getAuthHeaders() });
  return response.data;
};

// ── Analytics ──
export const getAnalyticsOverview = async (params) => {
  const response = await axios.get(`${API}/analytics/overview`, { headers: getAuthHeaders(), params });
  return response.data;
};

export const getAnalyticsTimeline = async (params) => {
  const response = await axios.get(`${API}/analytics/timeline`, { headers: getAuthHeaders(), params });
  return response.data?.timeline || [];
};

export const getAnalyticsEngagement = async (params) => {
  const response = await axios.get(`${API}/analytics/engagement`, { headers: getAuthHeaders(), params });
  return response.data;
};

export const getAnalyticsDemographics = async (params) => {
  const response = await axios.get(`${API}/analytics/demographics`, { headers: getAuthHeaders(), params });
  return response.data;
};

export const getInstagramAnalyticsReport = async (params) => {
  const response = await axios.get(`${API}/analytics/instagram-report`, { headers: getAuthHeaders(), params });
  return response.data;
};

export const getBlueskyAnalyticsReport = async (params) => {
  const response = await axios.get(`${API}/analytics/bluesky-report`, { headers: getAuthHeaders(), params });
  return response.data;
};

export const getYoutubeAnalyticsReport = async (params) => {
  const response = await axios.get(`${API}/analytics/youtube-report`, { headers: getAuthHeaders(), params });
  return response.data;
};

export const getTikTokAnalyticsReport = async (params) => {
  const response = await axios.get(`${API}/analytics/tiktok-report`, { headers: getAuthHeaders(), params });
  return response.data;
};

// ── Magic Links ──
export const exchangeMagicLink = async (token) => {
  const response = await axios.post(`${API}/auth/magic-link/exchange`, { token }, {
    withCredentials: true,
  });
  return response.data;
};

export const requestMagicLink = async (email, cfTurnstileToken = null) => {
  const response = await axios.post(`${API}/auth/magic-link/request`, {
    email,
    cf_turnstile_token: cfTurnstileToken,
  }, {
    withCredentials: true,
  });
  return response.data;
};

// ── Short Links & UTM Builder (Feature 1) ──
export const createShortLink = async (data) => {
  const response = await axios.post(`${API}/short-links`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const getShortLinks = async (params = {}) => {
  const response = await axios.get(`${API}/short-links`, { headers: getAuthHeaders(), params });
  return response.data;
};

export const getShortLinkStats = async (code) => {
  const response = await axios.get(`${API}/short-links/${code}/stats`, { headers: getAuthHeaders() });
  return response.data;
};

export const deleteShortLink = async (code) => {
  const response = await axios.delete(`${API}/short-links/${code}`, { headers: getAuthHeaders() });
  return response.data;
};

export const getUTMPresets = async () => {
  const response = await axios.get(`${API}/utm-presets`, { headers: getAuthHeaders() });
  return response.data;
};

export const saveUTMPreset = async (data) => {
  const response = await axios.post(`${API}/utm-presets`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const deleteUTMPreset = async (id) => {
  const response = await axios.delete(`${API}/utm-presets/${id}`, { headers: getAuthHeaders() });
  return response.data;
};

// ── Client Review Magic Links (Feature 2) ──
export const createShareReviewLink = async (data = {}) => {
  const response = await axios.post(`${API}/approvals/share-link`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const getPublicReviewFeed = async (token) => {
  const response = await axios.get(`${API}/approvals/public/${token}`);
  return response.data;
};

export const submitPublicReviewDecision = async (token, data) => {
  const response = await axios.post(`${API}/approvals/public/${token}/decision`, data);
  return response.data;
};

// ── Link-in-Bio / Start Page (Feature 3) ──
export const getMyBioPage = async () => {
  const response = await axios.get(`${API}/bio-pages/mine`, { headers: getAuthHeaders() });
  return response.data;
};

export const saveMyBioPage = async (data) => {
  const response = await axios.put(`${API}/bio-pages/mine`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const getPublicBioPage = async (handle) => {
  const response = await axios.get(`${API}/bio-pages/public/${handle}`);
  return response.data;
};

export const trackBioLinkClick = async (handle, linkId) => {
  const response = await axios.post(`${API}/bio-pages/public/${handle}/click/${linkId}`);
  return response.data;
};

// ── Branded PDF Reports & Schedules (Feature 4) ──
export const exportBrandedReport = async (data) => {
  const response = await axios.post(`${API}/analytics/report/export`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const scheduleReport = async (data) => {
  const response = await axios.post(`${API}/analytics/report/schedules`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const getReportSchedules = async () => {
  const response = await axios.get(`${API}/analytics/report/schedules`, { headers: getAuthHeaders() });
  return response.data;
};

export const deleteReportSchedule = async (scheduleId) => {
  const response = await axios.delete(`${API}/analytics/report/schedules/${scheduleId}`, { headers: getAuthHeaders() });
  return response.data;
};

// ── Post Draft Inline Comments (Feature 5) ──
export const addPostComment = async (postId, text) => {
  const response = await axios.post(`${API}/posts/${postId}/comments`, { text }, { headers: getAuthHeaders() });
  return response.data;
};

export const toggleCommentResolve = async (postId, commentId) => {
  const response = await axios.patch(`${API}/posts/${postId}/comments/${commentId}/resolve`, {}, { headers: getAuthHeaders() });
  return response.data;
};

export const deletePostComment = async (postId, commentId) => {
  const response = await axios.delete(`${API}/posts/${postId}/comments/${commentId}`, { headers: getAuthHeaders() });
  return response.data;
};

// ── Brand Voice & AI Vault (Feature 6) ──
export const getBrandVoice = async () => {
  const response = await axios.get(`${API}/ai/brand-voice`, { headers: getAuthHeaders() });
  return response.data;
};

export const saveBrandVoice = async (data) => {
  const response = await axios.put(`${API}/ai/brand-voice`, data, { headers: getAuthHeaders() });
  return response.data;
};


