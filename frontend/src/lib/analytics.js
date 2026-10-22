import posthog from 'posthog-js';

export const isPostHogConfigured = () => {
  const key = process.env.REACT_APP_POSTHOG_KEY;
  return Boolean(key && key !== 'YOUR_POSTHOG_KEY');
};

export const computeDaysRemaining = (paidThrough) => {
  if (!paidThrough) return null;
  const target = new Date(paidThrough).getTime();
  if (Number.isNaN(target)) return null;
  const diffMs = target - Date.now();
  if (diffMs <= 0) return 0;
  return Math.ceil(diffMs / (1000 * 60 * 60 * 24));
};

/**
 * Identify a user in PostHog upon authentication.
 */
export const identifyUser = (user) => {
  if (!isPostHogConfigured() || (!user?.user_id && !user?.id)) return;
  try {
    const userId = user.user_id || user.id;
    const daysRemaining = computeDaysRemaining(user.subscription_end_date);
    posthog.identify(userId, {
      email: user.email,
      name: user.name || user.display_name,
      plan: user.plan || 'starter',
      role: user.role || user.workspace_role || 'owner',
      workspace_id: user.default_workspace_id || null,
      subscription_status: user.subscription_status || 'free',
      subscription_end_date: user.subscription_end_date || null,
      subscription_days_remaining: daysRemaining,
      created_at: user.created_at,
    });
  } catch (err) {
    console.debug('[Analytics] identify error:', err);
  }
};

/**
 * Enrich PostHog person & workspace group properties with live Outreach
 * subscription, seat allowance, expiry countdown, and connected sender counts.
 */
export const identifyOutreachContext = ({ actor, billing, accounts, workspace }) => {
  if (!isPostHogConfigured() || (!actor?.user_id && !actor?.id)) return;
  try {
    const userId = actor.user_id || actor.id;
    const sub = billing?.subscription || {};
    const accessReq = billing?.access_request || null;
    const accessActive = Boolean(billing?.access_active);
    const paidThrough = sub.paid_through || null;
    const daysRemaining = computeDaysRemaining(paidThrough);
    const seats = accessActive ? Number(sub.seats || 0) : 0;
    const cancelScheduled = Boolean(sub.cancel_at_period_end);

    let outreachStatus = 'unpaid';
    if (accessActive && cancelScheduled) outreachStatus = 'cancel_scheduled';
    else if (accessActive && daysRemaining !== null && daysRemaining <= 7) outreachStatus = 'expiring_soon';
    else if (accessActive) outreachStatus = 'active';
    else if (paidThrough && daysRemaining === 0) outreachStatus = 'expired';
    else if (accessReq?.status === 'pending_quote') outreachStatus = 'pending_quote';

    const accList = Array.isArray(accounts) ? accounts : [];
    const connectedCount = accList.length;
    const activeSendersCount = accList.filter((a) => a?.status === 'active').length;
    const workspaceId = actor.default_workspace_id || workspace?.workspace_id || null;
    const workspaceName = workspace?.workspace_name || 'Workspace';

    posthog.identify(userId, {
      email: actor.email,
      name: actor.display_name || actor.name,
      role: actor.role || actor.workspace_role || 'owner',
      workspace_id: workspaceId,
      workspace_name: workspaceName,
      outreach_access_active: accessActive,
      outreach_subscription_status: outreachStatus,
      outreach_seats: seats,
      outreach_paid_through: paidThrough,
      outreach_days_remaining: daysRemaining,
      outreach_cancel_at_period_end: cancelScheduled,
      connected_linkedin_accounts_count: connectedCount,
      active_linkedin_accounts_count: activeSendersCount,
    });

    if (workspaceId && typeof posthog.group === 'function') {
      posthog.group('workspace', workspaceId, {
        name: workspaceName,
        outreach_access_active: accessActive,
        outreach_subscription_status: outreachStatus,
        outreach_seats: seats,
        outreach_paid_through: paidThrough,
        outreach_days_remaining: daysRemaining,
        connected_linkedin_accounts_count: connectedCount,
      });
    }
  } catch (err) {
    console.debug('[Analytics] outreach identify error:', err);
  }
};

/**
 * Reset user identity on logout.
 */
export const resetUser = () => {
  if (!isPostHogConfigured()) return;
  try {
    posthog.reset();
  } catch (err) {
    console.debug('[Analytics] reset error:', err);
  }
};

/**
 * Track custom product and conversion events safely.
 */
export const trackEvent = (eventName, properties = {}) => {
  if (!isPostHogConfigured()) return;
  try {
    posthog.capture(eventName, {
      ...properties,
      timestamp: new Date().toISOString(),
    });
  } catch (err) {
    console.debug(`[Analytics] track ${eventName} error:`, err);
  }
};
