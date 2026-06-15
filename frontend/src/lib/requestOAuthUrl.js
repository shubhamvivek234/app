import axios from 'axios';
import env from '@/env';

const buildHeaders = (token) => (token ? { Authorization: `Bearer ${token}` } : {});

export async function requestOAuthUrl(platform, options = {}, token = null) {
  const requestOptions = typeof options === 'string' ? {} : (options || {});
  const authToken = typeof options === 'string' ? options : token;
  const params = {};
  const linkedinAccountType = requestOptions.accountType || requestOptions.account_type;
  if (platform === 'linkedin' && linkedinAccountType) {
    params.account_type = linkedinAccountType;
  }

  const requestConfig = {
    headers: buildHeaders(authToken),
    withCredentials: true,
    params,
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
