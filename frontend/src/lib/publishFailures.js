export const TIKTOK_PUBLIC_POSTING_RESTRICTION_CODE = 'unaudited_client_can_only_post_to_private_accounts';

export const isTikTokPublicPostingRestriction = (result) => {
  if (!result || typeof result !== 'object') return false;
  const code = String(result.error_code || '').toLowerCase();
  const restrictionType = String(result.restriction_type || '').toLowerCase();
  const errorText = String(result.error || '').toLowerCase();
  return (
    code === TIKTOK_PUBLIC_POSTING_RESTRICTION_CODE
    || restrictionType === 'tiktok_public_posting_not_approved'
    || errorText.includes(TIKTOK_PUBLIC_POSTING_RESTRICTION_CODE)
  );
};

export const getPublishFailureMessage = (result) => {
  if (isTikTokPublicPostingRestriction(result)) {
    return 'TikTok blocked public posting for this app until TikTok app review is approved. A private TikTok account may still work.';
  }
  return result?.error || 'Failed';
};

export const getPublishFailureAction = (result) => {
  if (isTikTokPublicPostingRestriction(result)) {
    return 'Action required: complete TikTok app audit/review for public posting, or use a private TikTok account.';
  }
  return null;
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
