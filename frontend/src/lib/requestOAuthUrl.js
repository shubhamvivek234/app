import axios from 'axios';
import env from '@/env';

const buildHeaders = (token) => ({
  Authorization: `Bearer ${token}`,
});

export async function requestOAuthUrl(platform, token) {
  const requestConfig = {
    headers: buildHeaders(token),
    withCredentials: true,
  };

  try {
    const response = await axios.get(
      `${env.BACKEND_URL}/api/v1/oauth/${platform}/url`,
      requestConfig,
    );
    return response.data;
  } catch (error) {
    const status = error?.response?.status;
    if (status !== 404 && status !== 405) {
      throw error;
    }
  }

  const fallbackResponse = await axios.get(
    `${env.BACKEND_URL}/api/oauth/${platform}/authorize`,
    requestConfig,
  );
  return fallbackResponse.data;
}
