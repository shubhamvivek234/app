export const TIKTOK_PUBLIC_POSTING_RESTRICTION_CODE = 'unaudited_client_can_only_post_to_private_accounts';

export const isTikTokPublicPostingRestriction = (result) => {
  if (!result || typeof result !== 'object') return false;
  const code = String(result.error_code || result.publish_error_code || '').toLowerCase();
  const restrictionType = String(result.restriction_type || result.publish_restriction_type || '').toLowerCase();
  const errorText = String(result.error || result.publish_error || '').toLowerCase();
  return (
    code === TIKTOK_PUBLIC_POSTING_RESTRICTION_CODE
    || restrictionType === 'tiktok_public_posting_not_approved'
    || errorText.includes(TIKTOK_PUBLIC_POSTING_RESTRICTION_CODE)
  );
};

export const parsePlatformError = (platformKey, result) => {
  if (!result || typeof result !== 'object') {
    return null;
  }
  const status = String(result.status || '').toLowerCase();
  const isFailed = status === 'failed' || status === 'permanently_failed' || Boolean(result.error || result.publish_error);
  if (!isFailed) {
    return null;
  }

  const platform = String(platformKey || result.platform || '').toLowerCase();
  const rawError = String(result.error || result.publish_error || '').trim();
  const lowerError = rawError.toLowerCase();
  const errorCode = String(result.error_code || result.publish_error_code || '').toLowerCase();
  const actionReq = String(result.action_required || result.publish_action_required || '').trim();

  // 1. TikTok specific
  if (platform.includes('tiktok') || isTikTokPublicPostingRestriction(result)) {
    if (isTikTokPublicPostingRestriction(result)) {
      return {
        title: 'TikTok Developer Review Restriction',
        message: 'TikTok blocked public posting for this app until app review is approved. A private TikTok account may still work.',
        action: 'Switch to a private account or wait for TikTok developer audit approval.',
        actionType: 'reconnect',
        reconnectPlatform: 'tiktok',
        canRetryDirectly: false,
        rawError,
      };
    }
    if (lowerError.includes('duration') || lowerError.includes('short') || lowerError.includes('3 second')) {
      return {
        title: 'Video Too Short for TikTok',
        message: 'TikTok requires videos to be at least 3 seconds long.',
        action: 'Edit the post and replace with a longer video before retrying.',
        actionType: 'edit_post',
        canRetryDirectly: false,
        rawError,
      };
    }
  }

  // 2. Meta / Instagram / Facebook
  if (platform.includes('instagram') || platform.includes('facebook') || platform.includes('meta')) {
    const isInstagram = platform.includes('instagram');
    const brand = isInstagram ? 'Instagram' : 'Facebook';

    if (
      lowerError.includes('190') ||
      lowerError.includes('oauthexception') ||
      lowerError.includes('token') ||
      lowerError.includes('session has expired') ||
      lowerError.includes('validating access token') ||
      lowerError.includes('permissions error')
    ) {
      return {
        title: `${brand} Session Expired`,
        message: `Meta invalidated the access token or publishing permission was revoked for this ${brand} account.`,
        action: `Reconnect your ${brand} account in Settings > Connected Accounts.`,
        actionType: 'reconnect',
        reconnectPlatform: isInstagram ? 'instagram' : 'facebook',
        canRetryDirectly: false,
        rawError,
      };
    }

    if (
      lowerError.includes('aspect ratio') ||
      lowerError.includes('4:5') ||
      lowerError.includes('1.91:1') ||
      lowerError.includes('aspect_ratio')
    ) {
      return {
        title: 'Invalid Media Aspect Ratio',
        message: `${brand} requires images and videos to fit between 4:5 (vertical) and 1.91:1 (landscape).`,
        action: 'Edit post and crop media to an approved aspect ratio before retrying.',
        actionType: 'crop_media',
        canRetryDirectly: false,
        rawError,
      };
    }

    if (
      lowerError.includes('pages_manage_posts') ||
      lowerError.includes('instagram_content_publish') ||
      lowerError.includes('permission')
    ) {
      return {
        title: `Missing ${brand} Publishing Permissions`,
        message: `Your connected Meta profile did not grant publishing permission for this page.`,
        action: `Reconnect your ${brand} account and grant all page publishing permissions.`,
        actionType: 'reconnect',
        reconnectPlatform: isInstagram ? 'instagram' : 'facebook',
        canRetryDirectly: false,
        rawError,
      };
    }
  }

  // 3. Twitter / X
  if (platform.includes('twitter') || platform.includes('x')) {
    if (
      lowerError.includes('187') ||
      lowerError.includes('duplicate') ||
      lowerError.includes('status is a duplicate') ||
      lowerError.includes('not allowed to create a post with duplicate')
    ) {
      return {
        title: 'Duplicate Tweet Detected',
        message: 'Twitter/X blocks identical tweets posted within a short period to prevent spam.',
        action: 'Edit the post to make the wording unique before retrying.',
        actionType: 'edit_post',
        canRetryDirectly: false,
        rawError,
      };
    }

    if (lowerError.includes('401') || lowerError.includes('unauthorized') || lowerError.includes('token')) {
      return {
        title: 'Twitter Authorization Expired',
        message: 'Twitter/X token is invalid or app permissions were revoked.',
        action: 'Reconnect your Twitter/X account in Connected Accounts.',
        actionType: 'reconnect',
        reconnectPlatform: 'twitter',
        canRetryDirectly: false,
        rawError,
      };
    }

    if (lowerError.includes('429') || lowerError.includes('rate limit') || lowerError.includes('too many requests')) {
      return {
        title: 'Twitter Rate Limit Exceeded',
        message: 'Twitter API quota has temporarily been exceeded for this window.',
        action: 'Wait 15 minutes, then retry this platform.',
        actionType: 'wait',
        canRetryDirectly: true,
        rawError,
      };
    }

    if (lowerError.includes('file size') || lowerError.includes('media') || lowerError.includes('large')) {
      return {
        title: 'Twitter Media Limit Exceeded',
        message: 'Images must be under 5MB and videos under 512MB for Twitter/X.',
        action: 'Compress media before retrying.',
        actionType: 'edit_post',
        canRetryDirectly: false,
        rawError,
      };
    }
  }

  // 4. LinkedIn
  if (platform.includes('linkedin')) {
    if (
      lowerError.includes('422') ||
      lowerError.includes('unprocessable') ||
      lowerError.includes('media processing') ||
      lowerError.includes('urn invalid')
    ) {
      return {
        title: 'LinkedIn Media Processing Failed',
        message: 'LinkedIn rejected the attached image or video format.',
        action: 'Edit post to replace the media with a standard PNG, JPEG, or MP4 file.',
        actionType: 'edit_post',
        canRetryDirectly: false,
        rawError,
      };
    }

    if (lowerError.includes('token') || lowerError.includes('expired') || lowerError.includes('unauthorized') || lowerError.includes('401')) {
      return {
        title: 'LinkedIn Token Expired',
        message: 'LinkedIn 60-day OAuth token expired.',
        action: 'Reconnect your LinkedIn account in Connected Accounts.',
        actionType: 'reconnect',
        reconnectPlatform: 'linkedin',
        canRetryDirectly: false,
        rawError,
      };
    }
  }

  // 5. YouTube
  if (platform.includes('youtube')) {
    if (lowerError.includes('quotaexceeded') || lowerError.includes('daily upload') || lowerError.includes('quota')) {
      return {
        title: 'YouTube Daily Quota Exceeded',
        message: 'Google YouTube API video upload quota for today has been reached. Quota resets at midnight PST.',
        action: 'Wait until midnight PST, then retry publishing.',
        actionType: 'wait',
        canRetryDirectly: true,
        rawError,
      };
    }

    if (lowerError.includes('title') || lowerError.includes('100 char')) {
      return {
        title: 'YouTube Title Too Long',
        message: 'YouTube titles cannot exceed 100 characters.',
        action: 'Edit the post and shorten the title before retrying.',
        actionType: 'edit_post',
        canRetryDirectly: false,
        rawError,
      };
    }
  }

  // 6. Google Business Profile
  if (platform.includes('google_business') || platform.includes('gbp') || platform.includes('google')) {
    if (lowerError.includes('verify') || lowerError.includes('unverified')) {
      return {
        title: 'Google Business Location Unverified',
        message: 'This location has not completed verification on Google Maps yet.',
        action: 'Verify your location on Google Business Profile before posting.',
        actionType: 'reconnect',
        reconnectPlatform: 'google_business',
        canRetryDirectly: false,
        rawError,
      };
    }
  }

  // Generic fallback with clean humanized message
  let cleanMessage = rawError;
  if (!cleanMessage || cleanMessage === 'Failed') {
    cleanMessage = actionReq || 'The social platform rejected this post during delivery.';
  }

  return {
    title: `${platform ? platform.charAt(0).toUpperCase() + platform.slice(1) : 'Publish'} Delivery Issue`,
    message: cleanMessage,
    action: actionReq || (result.retry_count > 0 ? 'Retry this platform or edit the post.' : 'Click Retry to re-queue delivery.'),
    actionType: 'retry_now',
    reconnectPlatform: null,
    canRetryDirectly: true,
    rawError,
  };
};

export const getPublishFailureMessage = (result, platform = null) => {
  const diagnostic = parsePlatformError(platform, result);
  if (diagnostic) {
    return diagnostic.message;
  }
  return result?.error || result?.publish_error || 'Failed';
};

export const getPublishFailureAction = (result, platform = null) => {
  const diagnostic = parsePlatformError(platform, result);
  if (diagnostic && diagnostic.action) {
    return diagnostic.action;
  }
  return null;
};

export const getTikTokRestrictionFromAccount = (account) => {
  if (!isTikTokPublicPostingRestriction(account)) {
    return null;
  }
  return {
    accountId: account?.account_id || account?.id || null,
    result: {
      error: account?.publish_error || null,
      error_code: account?.publish_error_code || null,
      error_category: account?.publish_error_category || null,
      action_required: account?.publish_action_required || null,
      restriction_type: account?.publish_restriction_type || null,
      blocked_at: account?.publish_blocked_at || null,
    },
  };
};

export const getLatestTikTokRestriction = (posts, accountId = null) => {
  if (!Array.isArray(posts)) return null;

  for (const post of posts) {
    const accountResults = post?.account_results || {};
    if (accountId) {
      const accountResult = accountResults[accountId];
      if (isTikTokPublicPostingRestriction(accountResult)) {
        return {
          post,
          result: accountResult,
          accountId,
        };
      }
    }

    const matchedEntry = Object.entries(accountResults).find(
      ([candidateId, result]) => (!accountId || candidateId === accountId) && isTikTokPublicPostingRestriction(result)
    );
    if (matchedEntry) {
      const [matchedAccountId, result] = matchedEntry;
      return {
        post,
        result,
        accountId: matchedAccountId,
      };
    }

    const platformResult = post?.platform_results?.tiktok;
    if (!accountId && isTikTokPublicPostingRestriction(platformResult)) {
      return {
        post,
        result: platformResult,
        accountId: null,
      };
    }
  }

  return null;
};
