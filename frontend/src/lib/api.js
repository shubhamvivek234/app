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

// Agent API (Front-end only for testing/demo if needed)
export const getAgentChannels = async (apiKey) => {
  const response = await axios.get(`${API}/agent/channels`, {
    headers: { 'X-API-KEY': apiKey },
  });
  return response.data;
};