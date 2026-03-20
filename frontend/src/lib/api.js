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