/**
 * useGoogleAuth Hook
 *
 * Encapsulates all Google authentication logic.
 * This hook is completely isolated from UI changes.
 *
 * Usage:
 *   const { loginWithGoogle, isLoading } = useGoogleAuth();
 *   await loginWithGoogle();
 */

import { useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';

export const useGoogleAuth = () => {
  const { loginWithGoogle: authContextLogin } = useAuth();

  const loginWithGoogle = useCallback(async () => {
    try {
      console.log('[useGoogleAuth] Initiating Google login...');
      await authContextLogin();
      console.log('[useGoogleAuth] Google login successful');
      return true;
    } catch (error) {
      console.error('[useGoogleAuth] Google login failed:', error.code);

      // User cancelled popup - don't show error toast
      if (error.code === 'auth/popup-closed-by-user') {
        return false;
      }

      // Other errors already handled in AuthContext, but log here too
      if (error.code !== 'auth/popup-closed-by-user') {
        console.error('[useGoogleAuth] Unexpected error:', error.message);
      }

      return false;
    }
  }, [authContextLogin]);

  return {
    loginWithGoogle,
  };
};

export default useGoogleAuth;
