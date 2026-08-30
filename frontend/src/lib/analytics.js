import posthog from 'posthog-js';

const isPostHogConfigured = () => {
  const key = process.env.REACT_APP_POSTHOG_KEY;
  return Boolean(key && key !== 'YOUR_POSTHOG_KEY');
};

/**
 * Identify a user in PostHog upon authentication.
 */
export const identifyUser = (user) => {
  if (!isPostHogConfigured() || !user?.user_id && !user?.id) return;
  try {
    const userId = user.user_id || user.id;
    posthog.identify(userId, {
      email: user.email,
      name: user.name || user.display_name,
      plan: user.plan || 'starter',
      role: user.role || 'owner',
      subscription_status: user.subscription_status || 'free',
      created_at: user.created_at,
    });
  } catch (err) {
    console.debug('[Analytics] identify error:', err);
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
