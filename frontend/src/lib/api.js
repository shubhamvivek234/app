import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const SOCIAL_ACCOUNTS_CACHE_KEY = 'social_accounts_cache_v2';
const SOCIAL_ACCOUNTS_CACHE_TTL_MS = 60 * 1000;

const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
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

const postLegacyUpload = async (file, onProgress) => {
  const formData = new FormData();
  formData.append('file', file);

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
  const response = await axios.post(`${API}/posts`, postData, {
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

// Media Upload with progress tracking
export const uploadMedia = async (file, onProgress) => {
  let mediaJobId = null;

  try {
    const sessionResponse = await axios.post(
      `${API}/upload/session`,
      {
        filename: file.name,
        file_size_bytes: file.size,
        content_type: file.type || 'application/octet-stream',
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
      return postLegacyUpload(file, onProgress);
    }
    await abortDirectUpload(mediaJobId, error?.message || 'Upload failed');
    throw error;
  }
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

// ── Inbox Messages (Stub - to be implemented) ──
export const getInbox = async () => {
  const response = await axios.get(`${API}/inbox`, {
    headers: getAuthHeaders(),
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

export const uploadMediaAsset = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await axios.post(`${API}/media-assets`, formData, {
    headers: {
      ...getAuthHeaders(),
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
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

export const getConversations = async () => {
  const response = await axios.get(`${API}/conversations`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// ── Comments (Stub - to be implemented) ──
export const getPostComments = async (postId) => {
  const response = await axios.get(`${API}/posts/${postId}/comments`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const replyToComment = async (postId, commentId, data) => {
  const response = await axios.post(
    `${API}/posts/${postId}/comments/${commentId}/reply`,
    data,
    { headers: getAuthHeaders() }
  );
  return response.data;
};

export const sendDmReply = async (conversationId, data) => {
  const response = await axios.post(
    `${API}/conversations/${conversationId}/reply`,
    data,
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

// ── User Profile (Stub - to be implemented) ──
export const uploadProfilePhoto = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await axios.post(`${API}/profile/photo`, formData, {
    headers: {
      ...getAuthHeaders(),
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const updateProfile = async (data) => {
  const response = await axios.patch(`${API}/profile`, data, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const changePassword = async (data) => {
  const response = await axios.post(`${API}/profile/change-password`, data, {
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

export const inviteWorkspaceMember = async (data) => {
  const response = await axios.post(`${API}/workspace/members/invite`, data, {
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

// Notifications
export const getNotifications = async (unreadOnly = false) => {
  const url = unreadOnly
    ? `${API}/notifications?unread_only=true`
    : `${API}/notifications`;
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
  const response = await axios.post(`${API}/posts/${postId}/submit-review`, data, {
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
export const approvePost = async (postId) => {
  const response = await axios.post(`${API}/posts/${postId}/approve`, {}, { headers: getAuthHeaders() });
  return response.data;
};

export const rejectPost = async (postId, data) => {
  const response = await axios.post(`${API}/posts/${postId}/reject`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const resubmitPost = async (postId, data) => {
  const response = await axios.post(`${API}/posts/${postId}/resubmit`, data, { headers: getAuthHeaders() });
  return response.data;
};

// ── Bulk Upload ──
export const bulkCreatePosts = async (payload) => {
  const response = await axios.post(`${API}/posts/bulk`, payload, {
    headers: getAuthHeaders(),
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

// ── Calendar Notes ──
export const getCalendarNotes = async (params) => {
  const response = await axios.get(`${API}/calendar/notes`, { headers: getAuthHeaders(), params });
  return response.data;
};

export const createCalendarNote = async (data) => {
  const response = await axios.post(`${API}/calendar/notes`, data, { headers: getAuthHeaders() });
  return response.data;
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
  const response = await axios.post(`${API}/workspace/invite/${token}/accept`, data, { headers: getAuthHeaders() });
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
