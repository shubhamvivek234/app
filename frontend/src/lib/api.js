import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

// Posts
export const createPost = async (postData) => {
  const response = await axios.post(`${API}/posts`, postData, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const getPosts = async (status = null) => {
  const url = status ? `${API}/posts?status=${status}` : `${API}/posts`;
  const response = await axios.get(url, {
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
export const generateContent = async (prompt, platform = null, tone = null) => {
  const response = await axios.post(
    `${API}/ai/generate-content`,
    { prompt, platform, tone },
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

export const getSocialAccounts = async () => {
  const response = await axios.get(`${API}/social-accounts`, {
    headers: getAuthHeaders(),
  });
  return response.data;
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
export const getPublishFeed = async () => {
  const response = await axios.get(`${API}/publish/feed`, {
    headers: getAuthHeaders(),
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

export const connectMedium = async (integrationToken) => {
  const response = await axios.post(
    `${API}/social-accounts/medium/connect`,
    { integration_token: integrationToken },
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
  return response.data;
};

export const getAnalyticsEngagement = async (params) => {
  const response = await axios.get(`${API}/analytics/engagement`, { headers: getAuthHeaders(), params });
  return response.data;
};

export const getAnalyticsDemographics = async (params) => {
  const response = await axios.get(`${API}/analytics/demographics`, { headers: getAuthHeaders(), params });
  return response.data;
};
