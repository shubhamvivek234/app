import axios from 'axios';
import env from '@/env';

export async function submitOAuthCallback(platform, callbackData, token) {
  const requestConfig = {
    headers: { Authorization: `Bearer ${token}` },
    withCredentials: true,
  };

  try {
    const response = await axios.post(
      `${env.BACKEND_URL}/api/v1/oauth/${platform}/callback`,
      callbackData,
      requestConfig,
    );
    return response.data;
  } catch (error) {
    const status = error?.response?.status;
    if (status !== 404 && status !== 405) {
      throw error;
    }
  }

  const fallbackResponse = await axios.post(
    `${env.BACKEND_URL}/api/oauth/${platform}/callback`,
    callbackData,
    requestConfig,
  );
  return fallbackResponse.data;
}
