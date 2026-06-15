import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { broadcastOAuthResult, clearOAuthPopupExpected, isOAuthPopupExpected } from '@/lib/oauthPopup';
import { getGoogleOAuthHashParams, isGooglePhotosImportState } from '@/lib/googlePhotosAuth';
import { submitOAuthCallback } from '@/lib/requestOAuthCallback';

const resolvePostConnectPath = (platform, returnTo, { linkedinAccountType = null } = {}) => {
  if (platform === 'linkedin') {
    const params = new URLSearchParams(
      linkedinAccountType === 'organization'
        ? { linkedin_orgs: '1' }
        : { linkedin_profile: '1' },
    );
    return `/accounts?${params.toString()}`;
  }
  return returnTo === 'onboarding' ? '/onboarding/connect' : '/accounts';
};

const OAuthCallback = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState('processing');
  const [message, setMessage] = useState('Please wait while we complete the connection.');

  useEffect(() => {
    const handleOAuthCallback = async () => {
      const code = searchParams.get('code');
      const state = searchParams.get('state');
      const error = searchParams.get('error');
      const success = searchParams.get('success');
      const hashParams = getGoogleOAuthHashParams();
      const hashState = hashParams.get('state');
      const hashError = hashParams.get('error');
      const hashAccessToken = hashParams.get('access_token');
      const platform = searchParams.get('platform') || sessionStorage.getItem('oauth_platform') || '';
      const linkedinAccountType = searchParams.get('linkedin_orgs') === '1'
        ? 'organization'
        : searchParams.get('linkedin_profile') === '1'
          ? 'profile'
          : sessionStorage.getItem('linkedin_account_type');

      const fallbackUrl = sessionStorage.getItem('oauth_return_to') === 'accounts' ? '/accounts' : '/onboarding/connect';
      const returnTo = sessionStorage.getItem('oauth_return_to') || 'accounts';
      const popupExpected = isOAuthPopupExpected();

      const cleanup = () => {
        sessionStorage.removeItem('oauth_platform');
        sessionStorage.removeItem('oauth_return_to');
        sessionStorage.removeItem('linkedin_account_type');
      };

      const finishPopupFlow = (result) => {
        broadcastOAuthResult(result);
        cleanup();
        clearOAuthPopupExpected();
        setTimeout(() => window.close(), 500);
      };

      if (isGooglePhotosImportState(hashState || state)) {
        const resultState = hashState || state;
        if (hashError) {
          setStatus('error');
          setMessage('Google Photos authorization failed.');
          broadcastOAuthResult({
            type: 'google_photos_import',
            status: 'error',
            state: resultState,
            error: hashError,
          });
          setTimeout(() => window.close(), 500);
          return;
        }

        if (!hashAccessToken) {
          setStatus('error');
          setMessage('Google Photos authorization did not return an access token.');
          broadcastOAuthResult({
            type: 'google_photos_import',
            status: 'error',
            state: resultState,
            error: 'Google Photos authorization did not return an access token.',
          });
          setTimeout(() => window.close(), 500);
          return;
        }

        setStatus('processing');
        setMessage('Preparing Google Photos picker…');
        broadcastOAuthResult({
          type: 'google_photos_import',
          status: 'success',
          state: resultState,
          access_token: hashAccessToken,
        });
        return;
      }

      // Backend-redirect flow: backend already processed the OAuth and redirected here
      if (success === 'true') {
        setStatus('success');
        setMessage('Redirecting you back...');
        if (popupExpected) {
          finishPopupFlow({ status: 'success', platform, returnTo });
          return;
        }
        toast.success(`${platform} connected successfully!`);
        cleanup();
        clearOAuthPopupExpected();
        const destination = resolvePostConnectPath(platform, returnTo, { linkedinAccountType });
        setTimeout(() => navigate(destination), 1500);
        return;
      }

      if (error) {
        setStatus('error');
        setMessage('Redirecting you back...');
        if (popupExpected) {
          finishPopupFlow({ status: 'error', platform, returnTo, error: `OAuth error: ${error}` });
          return;
        }
        toast.error(`OAuth error: ${error}`);
        clearOAuthPopupExpected();
        setTimeout(() => navigate(fallbackUrl), 2000);
        return;
      }

      if (!code || !state) {
        setStatus('error');
        setMessage('Redirecting you back...');
        toast.error('Invalid OAuth callback');
        setTimeout(() => navigate(fallbackUrl), 2000);
        return;
      }

      try {
        const token = localStorage.getItem('token');
        const platform = sessionStorage.getItem('oauth_platform');
        const returnTo = sessionStorage.getItem('oauth_return_to');

        if (!platform) {
          throw new Error('Platform information not found');
        }

        // Prepare callback data
        const callbackData = { code };

        // Send state back to backend for CSRF validation + state-context lookup.
        // (Twitter also needs it if Redis/state fallback is used.)
        if (state) {
          callbackData.state = state;
        }

        // For Twitter, include code_verifier (PKCE)
        if (platform === 'twitter') {
          const codeVerifier = sessionStorage.getItem('twitter_code_verifier');
          if (codeVerifier) {
            callbackData.code_verifier = codeVerifier;
            sessionStorage.removeItem('twitter_code_verifier');
          }
        }

        const responseData = await submitOAuthCallback(platform, callbackData, token);
        const connected = Boolean(responseData.success || responseData.connected || responseData.account_id);
        if (connected) {
          setStatus('success');
          setMessage('Redirecting you back...');
          const resolvedPlatform = responseData.platform || platform;
          if (popupExpected) {
            finishPopupFlow({ status: 'success', platform: resolvedPlatform, returnTo });
            return;
          }
          toast.success(`${resolvedPlatform} connected successfully!`);
          cleanup();
          clearOAuthPopupExpected();

          // Redirect based on return destination securely provided by backend or fallback to session
          const finalReturnTo = responseData.return_to || returnTo;
          const destination = resolvePostConnectPath(resolvedPlatform, finalReturnTo, {
            linkedinAccountType: resolvedPlatform === 'linkedin' ? linkedinAccountType : null,
          });

          setTimeout(() => {
            navigate(destination);
          }, 1500);
        }
      } catch (error) {
        console.error('OAuth callback error:', error);
        setStatus('error');
        setMessage('Redirecting you back...');
        const message = error.response?.data?.detail || 'Failed to connect account';

        if (popupExpected) {
          finishPopupFlow({ status: 'error', platform, returnTo, error: message });
          return;
        }

        if ((error.response?.status === 500 || error.response?.status === 503) && error.response?.data?.detail?.includes('not configured')) {
          toast.error(error.response.data.detail);
        } else {
          toast.error(message);
        }

        clearOAuthPopupExpected();
        const fallbackUrl = sessionStorage.getItem('oauth_return_to') === 'accounts' ? '/accounts' : '/onboarding/connect';
        setTimeout(() => navigate(fallbackUrl), 2000);
      }
    };

    handleOAuthCallback();
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen bg-offwhite flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-offwhite rounded-xl shadow-sm border border-border p-8 text-center">
        {status === 'processing' && (
          <>
            <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-green-500 mx-auto mb-4"></div>
            <h2 className="text-2xl font-bold text-slate-900 mb-2">Connecting your account...</h2>
            <p className="text-slate-600">{message}</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-slate-900 mb-2">Successfully Connected!</h2>
            <p className="text-slate-600">{message}</p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-slate-900 mb-2">Connection Failed</h2>
            <p className="text-slate-600">{message}</p>
          </>
        )}
      </div>
    </div>
  );
};

export default OAuthCallback;
