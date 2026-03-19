import axios from 'axios';
import { auth } from '@/firebase';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

// ── Auto Token Refresh Interceptor ───────────────────────────────────────────
// Firebase ID tokens expire every 1 hour. When the backend returns 401
// ("Token expired"), we force-refresh the Firebase token, update localStorage,
// and retry the original request once. If refresh fails, clear session and
// redirect to login.
let _isRefreshing = false;
let _refreshQueue = []; // pending requests waiting for fresh token

const processRefreshQueue = (error, token = null) => {
  _refreshQueue.forEach(({ resolve, reject }) =>
    error ? reject(error) : resolve(token)
  );
  _refreshQueue = [];
};

axios.interceptors.response.use(
  res => res,
  async error => {
    const originalRequest = error.config;

    const is401 = error.response?.status === 401;
    const isTokenError =
      error.response?.data?.detail === 'Token expired' ||
      error.response?.data?.detail === 'Session expired' ||
      error.response?.data?.detail === 'Not authenticated';

    if (is401 && isTokenError && !originalRequest._retry) {
      originalRequest._retry = true;

      if (_isRefreshing) {
        // Another refresh is in progress — queue this request
        return new Promise((resolve, reject) => {
          _refreshQueue.push({ resolve, reject });
        }).then(freshToken => {
          originalRequest.headers['Authorization'] = `Bearer ${freshToken}`;
          return axios(originalRequest);
        });
      }

      _isRefreshing = true;

      try {
        const firebaseUser = auth.currentUser;
        if (!firebaseUser) throw new Error('No firebase user');

        // Force-refresh the Firebase ID token
        const freshToken = await firebaseUser.getIdToken(true);
        localStorage.setItem('token', freshToken);
        axios.defaults.headers.common['Authorization'] = `Bearer ${freshToken}`;

        processRefreshQueue(null, freshToken);
        _isRefreshing = false;

        originalRequest.headers['Authorization'] = `Bearer ${freshToken}`;
        return axios(originalRequest);
      } catch (refreshError) {
        processRefreshQueue(refreshError);
        _isRefreshing = false;

        // Refresh failed — clear session and force re-login
        localStorage.removeItem('token');
        delete axios.defaults.headers.common['Authorization'];
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

// Posts
export const createPost = async (postData) => {
  const response = await axios.post(`${API}/posts`, postData, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const getPosts = async (statusOrOptions = null) => {
  // Accept either a plain status string or an options object { status }
  const status = statusOrOptions && typeof statusOrOptions === 'object'
    ? statusOrOptions.status
    : statusOrOptions;
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

export const duplicatePost = async (postId) => {
  const response = await axios.post(`${API}/posts/${postId}/duplicate`, {}, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const addInternalNote = async (postId, text) => {
  const response = await axios.post(`${API}/posts/${postId}/notes`, { text }, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const deleteInternalNote = async (postId, noteId) => {
  const response = await axios.delete(`${API}/posts/${postId}/notes/${noteId}`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// AI Content Generation
export const generateImage = async (prompt, size = '1024x1024', style = 'vivid') => {
  const response = await axios.post(
    `${API}/ai/generate-image`,
    { prompt, size, style },
    { headers: getAuthHeaders() }
  );
  return response.data;
};

export const generateContent = async (prompt, platform = null) => {
  const response = await axios.post(
    `${API}/ai/generate-content`,
    { prompt, platform },
    {
      headers: getAuthHeaders(),
    }
  );
  return response.data;
};

// Media Upload
export const uploadMedia = async (file, onUploadProgress) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await axios.post(`${API}/upload`, formData, {
    headers: {
      ...getAuthHeaders(),
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress,
  });
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

// Bluesky connect (handle + app password flow)
export const connectBluesky = async (handle, appPassword) => {
  const response = await axios.post(
    `${API}/oauth/bluesky/connect`,
    { handle, app_password: appPassword },
    { headers: getAuthHeaders() }
  );
  return response.data;
};

// Hashtag Groups
export const getHashtagGroups = async () => {
  const response = await axios.get(`${API}/hashtag-groups`, { headers: getAuthHeaders() });
  return response.data;
};
export const createHashtagGroup = async (name, hashtags) => {
  const response = await axios.post(`${API}/hashtag-groups`, { name, hashtags }, { headers: getAuthHeaders() });
  return response.data;
};
export const updateHashtagGroup = async (id, data) => {
  const response = await axios.patch(`${API}/hashtag-groups/${id}`, data, { headers: getAuthHeaders() });
  return response.data;
};
export const deleteHashtagGroup = async (id) => {
  const response = await axios.delete(`${API}/hashtag-groups/${id}`, { headers: getAuthHeaders() });
  return response.data;
};

// Team Members
export const getTeamMembers = async () => {
  const response = await axios.get(`${API}/team/members`, { headers: getAuthHeaders() });
  return response.data;
};
export const inviteTeamMember = async (email, role) => {
  const response = await axios.post(`${API}/team/invite`, { email, role }, { headers: getAuthHeaders() });
  return response.data;
};
export const updateTeamMember = async (id, data) => {
  const response = await axios.patch(`${API}/team/members/${id}`, data, { headers: getAuthHeaders() });
  return response.data;
};
export const removeTeamMember = async (id) => {
  const response = await axios.delete(`${API}/team/members/${id}`, { headers: getAuthHeaders() });
  return response.data;
};
export const resendTeamInvite = async (id) => {
  const response = await axios.post(`${API}/team/resend-invite/${id}`, {}, { headers: getAuthHeaders() });
  return response.data;
};
export const assignTeamMemberAccounts = async (memberId, accountIds) => {
  const response = await axios.patch(`${API}/team/members/${memberId}/accounts`, { account_ids: accountIds }, { headers: getAuthHeaders() });
  return response.data;
};
// Public — no auth header needed
export const checkInviteToken = async (token) => {
  const response = await axios.get(`${API}/team/check-invite?token=${encodeURIComponent(token)}`);
  return response.data;
};
export const acceptInviteToken = async (token) => {
  const response = await axios.post(`${API}/auth/accept-invite`, { token }, { headers: getAuthHeaders() });
  return response.data;
};

// Workspace API (Stage 5.9)
export const getWorkspace = async () => {
  const response = await axios.get(`${API}/workspace`, { headers: getAuthHeaders() });
  return response.data;
};
export const getWorkspaceMembers = async () => {
  const response = await axios.get(`${API}/workspace/members`, { headers: getAuthHeaders() });
  return response.data;
};
export const inviteWorkspaceMember = async (email, role) => {
  const response = await axios.post(`${API}/workspace/invite`, { email, role }, { headers: getAuthHeaders() });
  return response.data;
};
export const removeWorkspaceMember = async (memberUserId) => {
  const response = await axios.delete(`${API}/workspace/members/${memberUserId}`, { headers: getAuthHeaders() });
  return response.data;
};
export const getWorkspaceActivity = async (limit = 10) => {
  const response = await axios.get(`${API}/workspace/activity?limit=${limit}`, { headers: getAuthHeaders() });
  return response.data;
};
// Public — no auth needed
export const getWorkspaceInviteDetails = async (token) => {
  const response = await axios.get(`${API}/workspace/invite/${encodeURIComponent(token)}`);
  return response.data;
};
export const acceptWorkspaceInvite = async (token) => {
  const response = await axios.post(`${API}/workspace/invite/${encodeURIComponent(token)}/accept`, {}, { headers: getAuthHeaders() });
  return response.data;
};

// Inbox
export const getInbox = async ({ platform, type, status } = {}) => {
  const params = new URLSearchParams();
  if (platform) params.append('platform', platform);
  if (type) params.append('msg_type', type);
  if (status) params.append('status', status);
  const response = await axios.get(`${API}/inbox?${params.toString()}`, { headers: getAuthHeaders() });
  return response.data;
};
export const createInboxMessage = async (data) => {
  const response = await axios.post(`${API}/inbox`, data, { headers: getAuthHeaders() });
  return response.data;
};
export const updateInboxMessage = async (id, data) => {
  const response = await axios.patch(`${API}/inbox/${id}`, data, { headers: getAuthHeaders() });
  return response.data;
};
export const deleteInboxMessage = async (id) => {
  const response = await axios.delete(`${API}/inbox/${id}`, { headers: getAuthHeaders() });
  return response.data;
};
export const getInboxStats = async () => {
  const response = await axios.get(`${API}/inbox/stats`, { headers: getAuthHeaders() });
  return response.data;
};

// Calendar Notes
export const getCalendarNotes = async (month) => {
  const response = await axios.get(`${API}/calendar-notes?month=${month}`, { headers: getAuthHeaders() });
  return response.data;
};
export const createCalendarNote = async (data) => {
  const response = await axios.post(`${API}/calendar-notes`, data, { headers: getAuthHeaders() });
  return response.data;
};
export const updateCalendarNote = async (id, data) => {
  const response = await axios.patch(`${API}/calendar-notes/${id}`, data, { headers: getAuthHeaders() });
  return response.data;
};
export const deleteCalendarNote = async (id) => {
  const response = await axios.delete(`${API}/calendar-notes/${id}`, { headers: getAuthHeaders() });
  return response.data;
};

// Calendar Share
export const createCalendarShare = async () => {
  const response = await axios.post(`${API}/calendar/share`, {}, { headers: getAuthHeaders() });
  return response.data;
};
export const deleteCalendarShare = async () => {
  const response = await axios.delete(`${API}/calendar/share`, { headers: getAuthHeaders() });
  return response.data;
};
export const getPublicCalendar = async (token) => {
  const response = await axios.get(`${API}/calendar/public/${token}`);
  return response.data;
};

// Analytics
export const getAnalyticsOverview = async ({ days = 30, platform = null, accountId = null } = {}) => {
  const params = new URLSearchParams({ days });
  if (platform) params.append('platform', platform);
  if (accountId) params.append('account_id', accountId);
  const response = await axios.get(`${API}/analytics/overview?${params}`, { headers: getAuthHeaders() });
  return response.data;
};
export const getAnalyticsTimeline = async ({ days = 30, platform = null, accountId = null } = {}) => {
  const params = new URLSearchParams({ days });
  if (platform) params.append('platform', platform);
  if (accountId) params.append('account_id', accountId);
  const response = await axios.get(`${API}/analytics/timeline?${params}`, { headers: getAuthHeaders() });
  return response.data;
};
export const getAnalyticsEngagement = async ({ days = 30, platform = null, accountId = null } = {}) => {
  const params = new URLSearchParams({ days });
  if (platform) params.append('platform', platform);
  if (accountId) params.append('account_id', accountId);
  const response = await axios.get(`${API}/analytics/engagement?${params}`, { headers: getAuthHeaders() });
  return response.data;
};

// Media Library
export const getMediaAssets = async ({ mediaType, search } = {}) => {
  const params = {};
  if (mediaType) params.media_type = mediaType;
  if (search) params.search = search;
  const response = await axios.get(`${API}/media`, { headers: getAuthHeaders(), params });
  return response.data;
};
export const uploadMediaAsset = async (file, onUploadProgress) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await axios.post(`${API}/media`, formData, {
    headers: { ...getAuthHeaders(), 'Content-Type': 'multipart/form-data' },
    onUploadProgress,
  });
  return response.data;
};
export const deleteMediaAsset = async (assetId) => {
  const response = await axios.delete(`${API}/media/${assetId}`, { headers: getAuthHeaders() });
  return response.data;
};

// Recurring Rules
export const getRecurringRules = async () => {
  const response = await axios.get(`${API}/recurring-rules`, { headers: getAuthHeaders() });
  return response.data;
};
export const createRecurringRule = async (data) => {
  const response = await axios.post(`${API}/recurring-rules`, data, { headers: getAuthHeaders() });
  return response.data;
};
export const updateRecurringRule = async (id, data) => {
  const response = await axios.patch(`${API}/recurring-rules/${id}`, data, { headers: getAuthHeaders() });
  return response.data;
};
export const deleteRecurringRule = async (id) => {
  const response = await axios.delete(`${API}/recurring-rules/${id}`, { headers: getAuthHeaders() });
  return response.data;
};

// Post Approval Workflow
export const submitPostForReview = async (postId) => {
  const response = await axios.post(`${API}/posts/${postId}/submit-for-review`, {}, { headers: getAuthHeaders() });
  return response.data;
};
export const approvePost = async (postId) => {
  const response = await axios.post(`${API}/posts/${postId}/approve`, {}, { headers: getAuthHeaders() });
  return response.data;
};
export const rejectPost = async (postId, note = '') => {
  const response = await axios.post(`${API}/posts/${postId}/reject`, { note }, { headers: getAuthHeaders() });
  return response.data;
};
export const resubmitPost = async (postId) => {
  const response = await axios.post(`${API}/posts/${postId}/resubmit`, {}, { headers: getAuthHeaders() });
  return response.data;
};

// Bulk Upload
export const bulkCreatePosts = async (posts) => {
  const response = await axios.post(`${API}/posts/bulk`, { posts }, { headers: getAuthHeaders() });
  return response.data;
};

export const downloadBulkTemplate = () => {
  const lines = [
    'content,platforms,scheduled_time,post_type,media_urls,instagram_first_comment',
    '"Hello world! Check out our latest update. #launch #socialmedia","instagram|twitter",2026-04-01 09:00,text,,',
    '"New product drop! Limited time offer.","facebook|linkedin",2026-04-02 14:00,text,https://cdn.example.com/product.jpg,First comment here',
    '"Draft idea — will schedule later","instagram",,text,,',
  ];
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'bulk_posts_template.csv';
  a.click();
  URL.revokeObjectURL(url);
};

// Analytics Demographics
export const getAnalyticsDemographics = async ({ platform = null, accountId = null } = {}) => {
  const params = new URLSearchParams();
  if (platform) params.append('platform', platform);
  if (accountId) params.append('account_id', accountId);
  const response = await axios.get(`${API}/analytics/demographics?${params}`, { headers: getAuthHeaders() });
  return response.data;
};

// Comments
export const getPostComments = async (platform, postId, accountId = null) => {
  const params = new URLSearchParams();
  if (accountId) params.append('account_id', accountId);
  const response = await axios.get(`${API}/comments/${platform}/${encodeURIComponent(postId)}?${params}`, { headers: getAuthHeaders() });
  return response.data;
};
export const replyToComment = async (platform, commentId, data) => {
  const response = await axios.post(`${API}/comments/${platform}/${encodeURIComponent(commentId)}/reply`, data, { headers: getAuthHeaders() });
  return response.data;
};

// DMs / Messages
export const getConversations = async (platform, accountId = null) => {
  const params = new URLSearchParams();
  if (accountId) params.append('account_id', accountId);
  const response = await axios.get(`${API}/messages/${platform}?${params}`, { headers: getAuthHeaders() });
  return response.data;
};
export const sendDmReply = async (platform, conversationId, data) => {
  const response = await axios.post(`${API}/messages/${platform}/${conversationId}/reply`, data, { headers: getAuthHeaders() });
  return response.data;
};

export const getPublishFeed = async ({ accountId, platform, limit = 20 } = {}) => {
  const params = { limit };
  if (accountId) params.account_id = accountId;
  if (platform) params.platform = platform;
  const response = await axios.get(`${API}/publish/feed`, {
    headers: getAuthHeaders(),
    params,
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

export const verifyRazorpay = async (data) => {
  const response = await axios.post(`${API}/payments/verify-razorpay`, data, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const capturePaypal = async (orderId) => {
  const response = await axios.post(
    `${API}/payments/capture-paypal`,
    { order_id: orderId },
    {
      headers: getAuthHeaders(),
    }
  );
  return response.data;
};

// Stats
export const getStats = async () => {
  const response = await axios.get(`${API}/stats`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const completeOnboarding = async () => {
  const response = await axios.patch(`${API}/auth/me`,
    { onboarding_completed: true },
    {
      headers: getAuthHeaders(),
    }
  );
  return response.data;
};

// Support
export const sendSupportRequest = async (formData) => {
  const response = await axios.post(`${API}/support`, formData, {
    headers: {
      ...getAuthHeaders(),
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

// API Keys
export const getApiKeys = async () => {
  const response = await axios.get(`${API}/keys`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const createApiKey = async (name) => {
  const response = await axios.post(`${API}/keys`, { name }, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const deleteApiKey = async (keyId) => {
  const response = await axios.delete(`${API}/keys/${keyId}`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// Profile
export const updateProfile = async (data) => {
  const response = await axios.patch(`${API}/auth/me`, data, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const updateUserTimezone = async (timezone) => {
  const response = await axios.patch(`${API}/auth/me`, { timezone }, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const uploadProfilePhoto = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  // Do NOT set Content-Type manually — axios must set it automatically
  // with the correct multipart boundary, otherwise the server can't parse the body.
  const response = await axios.post(`${API}/auth/profile-photo`, formData, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

export const changePassword = async ({ old_password, new_password }) => {
  const response = await axios.post(`${API}/auth/change-password`, { old_password, new_password }, {
    headers: getAuthHeaders(),
  });
  return response.data;
};

// LinkedIn Pages / Organizations
export const getLinkedInPendingOrgs = async () => {
  const response = await axios.get(`${API}/oauth/linkedin/pending-orgs`, { headers: getAuthHeaders() });
  return response.data;
};

export const saveLinkedInOrgs = async (orgIds) => {
  const response = await axios.post(`${API}/oauth/linkedin/save-orgs`, { org_ids: orgIds }, { headers: getAuthHeaders() });
  return response.data;
};

export const addLinkedInPageManually = async (pageId, pageName) => {
  const response = await axios.post(`${API}/oauth/linkedin/add-page`, { page_id: pageId, page_name: pageName }, { headers: getAuthHeaders() });
  return response.data;
};

// Agent API (Front-end only for testing/demo if needed)
export const getAgentChannels = async (apiKey) => {
  const response = await axios.get(`${API}/agent/channels`, {
    headers: { 'X-API-KEY': apiKey },
  });
  return response.data;
};

// GDPR / Privacy
export const exportMyData = async () => {
  const response = await axios.get(`${API}/gdpr/export`, {
    headers: getAuthHeaders(),
    responseType: 'blob',
  });
  return response.data;
};

export const getGdprStatus = async () => {
  const response = await axios.get(`${API}/gdpr/status`, {
    headers: getAuthHeaders(),
  });
  return response.data;
};