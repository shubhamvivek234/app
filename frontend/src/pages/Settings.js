import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { EmailAuthProvider, reauthenticateWithCredential, updatePassword as updateFirebasePassword } from 'firebase/auth';
import {
  FaBell,
  FaClock,
  FaEnvelope,
  FaExclamationTriangle,
  FaExternalLinkAlt,
  FaShieldAlt,
  FaTrashAlt,
  FaUser,
} from 'react-icons/fa';

import DashboardLayout from '@/components/DashboardLayout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { useAuth } from '@/context/AuthContext';
import {
  getNotificationPreferences,
  requestAccountDeletion,
  requestDataExport,
  requestVerificationEmail,
  updateCurrentUser,
  updateNotificationPreferences,
} from '@/lib/api';
import { toast } from 'sonner';

const COMMON_TIMEZONES = [
  'UTC',
  'Asia/Kolkata',
  'Asia/Dubai',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Sao_Paulo',
  'Australia/Sydney',
  'Pacific/Auckland',
];

const NOTIFICATION_EVENTS = [
  {
    key: 'post.published',
    label: 'Published posts',
    description: 'Successful publishing confirmations.',
    defaultChannels: ['in_app'],
  },
  {
    key: 'post.failed',
    label: 'Post failures',
    description: 'Retries exhausted or platform publish failures.',
    defaultChannels: ['email', 'in_app'],
  },
  {
    key: 'post.dlq',
    label: 'Permanent failures',
    description: 'Posts moved to dead-letter recovery.',
    defaultChannels: ['email', 'in_app'],
  },
  {
    key: 'account.expiring',
    label: 'Subscription and access issues',
    description: 'Expiry warnings, paused posts, and grace-period notices.',
    defaultChannels: ['email', 'in_app'],
  },
  {
    key: 'billing.failed',
    label: 'Billing failures',
    description: 'Payment failures that need action.',
    defaultChannels: ['email'],
  },
];

const buildNotificationDefaults = () => (
  NOTIFICATION_EVENTS.reduce((accumulator, event) => ({
    ...accumulator,
    [event.key]: {
      channels: [...event.defaultChannels],
      digest: 'immediate',
    },
  }), {})
);

const normalizeNotificationPreferences = (preferences) => {
  const defaults = buildNotificationDefaults();
  if (!preferences || typeof preferences !== 'object') {
    return defaults;
  }

  const next = { ...defaults };
  NOTIFICATION_EVENTS.forEach((event) => {
    const raw = preferences[event.key];
    if (!raw || typeof raw !== 'object') {
      return;
    }
    const rawChannels = Array.isArray(raw.channels) ? raw.channels : next[event.key].channels;
    const channels = [];
    rawChannels.forEach((channel) => {
      if ((channel === 'email' || channel === 'in_app') && !channels.includes(channel)) {
        channels.push(channel);
      }
    });
    next[event.key] = {
      channels,
      digest: raw.digest === 'hourly' || raw.digest === 'daily' ? raw.digest : 'immediate',
    };
  });
  return next;
};

const buildInitials = (displayName, email) => {
  const source = (displayName || email || 'Unravler')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  return source
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase();
};

const statusBadgeClassName = (status) => {
  switch (status) {
    case 'active':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    case 'expired':
    case 'cancelled':
      return 'bg-rose-50 text-rose-700 border-rose-200';
    case 'grace':
      return 'bg-amber-50 text-amber-700 border-amber-200';
    default:
      return 'bg-slate-100 text-slate-700 border-slate-200';
  }
};

const mapPasswordError = (error) => {
  switch (error?.code) {
    case 'auth/invalid-credential':
    case 'auth/wrong-password':
      return 'Current password is incorrect.';
    case 'auth/weak-password':
      return 'Choose a stronger password.';
    case 'auth/requires-recent-login':
      return 'Please sign in again before changing your password.';
    case 'auth/too-many-requests':
      return 'Too many attempts. Please wait and try again.';
    default:
      return 'Unable to update your password right now.';
  }
};

const Settings = () => {
  const { user, firebaseUser, refreshUser, logout } = useAuth();
  const [displayName, setDisplayName] = useState('');
  const [timezone, setTimezone] = useState('UTC');
  const [savingProfile, setSavingProfile] = useState(false);
  const [loadingNotifications, setLoadingNotifications] = useState(true);
  const [notificationPreferences, setNotificationPreferences] = useState(buildNotificationDefaults());
  const [savingNotifications, setSavingNotifications] = useState(false);
  const [resendingVerification, setResendingVerification] = useState(false);
  const [exportingData, setExportingData] = useState(false);
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [passwordForm, setPasswordForm] = useState({ current: '', next: '', confirm: '' });
  const [updatingPassword, setUpdatingPassword] = useState(false);

  useEffect(() => {
    setDisplayName(user?.display_name || user?.name || '');
    setTimezone(user?.timezone || 'UTC');
  }, [user?.display_name, user?.name, user?.timezone]);

  useEffect(() => {
    let cancelled = false;

    const loadPreferences = async () => {
      setLoadingNotifications(true);
      try {
        const response = await getNotificationPreferences();
        if (!cancelled) {
          setNotificationPreferences(normalizeNotificationPreferences(response.preferences));
        }
      } catch (error) {
        if (!cancelled) {
          toast.error(error?.response?.data?.detail || 'Failed to load notification preferences.');
          setNotificationPreferences(buildNotificationDefaults());
        }
      } finally {
        if (!cancelled) {
          setLoadingNotifications(false);
        }
      }
    };

    loadPreferences();
    return () => {
      cancelled = true;
    };
  }, []);

  const timezoneOptions = useMemo(() => {
    const values = new Set(COMMON_TIMEZONES);
    if (user?.timezone) values.add(user.timezone);
    try {
      const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (browserTimezone) values.add(browserTimezone);
    } catch {
      // Ignore environments without Intl timezone support.
    }
    return Array.from(values);
  }, [user?.timezone]);

  const avatarInitials = useMemo(
    () => buildInitials(user?.display_name || user?.name || '', user?.email || ''),
    [user?.display_name, user?.name, user?.email],
  );

  const resolvedDisplayName = user?.display_name || user?.name || '';
  const profileDirty = displayName.trim() !== resolvedDisplayName || timezone !== (user?.timezone || 'UTC');
  const providerIds = useMemo(
    () => Array.from(new Set((firebaseUser?.providerData || []).map((provider) => provider?.providerId).filter(Boolean))),
    [firebaseUser],
  );
  const hasPasswordProvider = providerIds.includes('password');
  const hasGoogleProvider = providerIds.includes('google.com');
  const securityMode = !firebaseUser ? 'reset-guidance' : hasPasswordProvider ? 'password' : hasGoogleProvider ? 'google' : 'provider';

  const handleProfileSave = async (event) => {
    event.preventDefault();
    const nextDisplayName = displayName.trim();
    if (!nextDisplayName) {
      toast.error('Display name cannot be blank.');
      return;
    }

    setSavingProfile(true);
    try {
      await updateCurrentUser({
        display_name: nextDisplayName,
        timezone,
      });
      await refreshUser();
      toast.success('Account settings saved.');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to save account settings.');
    } finally {
      setSavingProfile(false);
    }
  };

  const toggleNotificationChannel = (eventKey, channel, enabled) => {
    setNotificationPreferences((current) => {
      const existing = current[eventKey] || { channels: [], digest: 'immediate' };
      const nextChannels = enabled
        ? Array.from(new Set([...existing.channels, channel]))
        : existing.channels.filter((value) => value !== channel);
      return {
        ...current,
        [eventKey]: {
          ...existing,
          channels: nextChannels,
        },
      };
    });
  };

  const handleNotificationSave = async () => {
    setSavingNotifications(true);
    try {
      const response = await updateNotificationPreferences(notificationPreferences);
      setNotificationPreferences(normalizeNotificationPreferences(response.preferences));
      toast.success('Notification preferences saved.');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to save notification preferences.');
    } finally {
      setSavingNotifications(false);
    }
  };

  const handleResendVerification = async () => {
    setResendingVerification(true);
    try {
      await requestVerificationEmail('/settings');
      toast.success('Verification email sent. Check your inbox.');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Could not send a verification email right now.');
    } finally {
      setResendingVerification(false);
    }
  };

  const handlePasswordChange = async (event) => {
    event.preventDefault();
    if (!firebaseUser || !firebaseUser.email) {
      toast.error('Sign in again before changing your password.');
      return;
    }
    if (passwordForm.next !== passwordForm.confirm) {
      toast.error('New passwords do not match.');
      return;
    }
    if (passwordForm.next.length < 8) {
      toast.error('New password must be at least 8 characters.');
      return;
    }

    setUpdatingPassword(true);
    try {
      const credential = EmailAuthProvider.credential(firebaseUser.email, passwordForm.current);
      await reauthenticateWithCredential(firebaseUser, credential);
      await updateFirebasePassword(firebaseUser, passwordForm.next);
      setPasswordForm({ current: '', next: '', confirm: '' });
      toast.success('Password updated.');
    } catch (error) {
      toast.error(mapPasswordError(error));
    } finally {
      setUpdatingPassword(false);
    }
  };

  const handleExportData = async () => {
    setExportingData(true);
    try {
      await requestDataExport();
      toast.success('Export queued. We will email you the download link when it is ready.');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to queue your data export.');
    } finally {
      setExportingData(false);
    }
  };

  const handleDeleteAccount = async () => {
    setDeletingAccount(true);
    try {
      await requestAccountDeletion();
      toast.success('Account deletion queued. Your data will be removed within 30 days.');
      await logout();
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to queue account deletion.');
    } finally {
      setDeletingAccount(false);
    }
  };

  if (!user) {
    return (
      <DashboardLayout>
        <div className="mx-auto max-w-4xl">
          <Card className="border-slate-200 shadow-sm">
            <CardContent className="flex h-48 items-center justify-center">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-slate-700" />
            </CardContent>
          </Card>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">Settings</h1>
          <p className="max-w-2xl text-sm text-slate-500 dark:text-slate-400">
            Keep your account details, verification state, and notification preferences aligned with how you publish inside Unravler.
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.85fr)]">
          <Card className="border-slate-200 shadow-sm">
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-2 text-slate-900 dark:text-slate-100">
                <FaUser className="text-sm text-slate-500" />
                Account profile
              </CardTitle>
              <CardDescription>
                Update the display name and timezone the scheduler should use. Email stays read-only here.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-col gap-6 sm:flex-row">
                <div className="flex items-center gap-4 sm:w-48 sm:flex-col sm:items-start">
                  {user.avatar_url ? (
                    <img
                      src={user.avatar_url}
                      alt={resolvedDisplayName || user.email}
                      className="h-20 w-20 rounded-2xl object-cover ring-1 ring-slate-200"
                    />
                  ) : (
                    <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-slate-900 text-lg font-semibold text-white shadow-sm">
                      {avatarInitials}
                    </div>
                  )}
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                      {resolvedDisplayName || 'Unravler user'}
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      Profile photos are read from your sign-in provider. Avatar uploads are not managed here.
                    </p>
                  </div>
                </div>

                <form onSubmit={handleProfileSave} className="flex-1 space-y-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="settings-display-name">Display name</Label>
                    <Input
                      id="settings-display-name"
                      value={displayName}
                      onChange={(event) => setDisplayName(event.target.value)}
                      placeholder="Your name"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="settings-email">Email</Label>
                    <Input
                      id="settings-email"
                      type="email"
                      value={user.email || ''}
                      disabled
                      className="bg-slate-50 text-slate-500 dark:bg-slate-900/40"
                    />
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      Email changes are not supported from Settings.
                    </p>
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="settings-timezone">Timezone</Label>
                    <select
                      id="settings-timezone"
                      value={timezone}
                      onChange={(event) => setTimezone(event.target.value)}
                      className="flex h-10 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    >
                      {timezoneOptions.map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      Scheduler and calendar times are rendered in this timezone.
                    </p>
                  </div>

                  <div className="flex items-center justify-between gap-3 pt-2">
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      Current plan: <span className="font-medium capitalize text-slate-700 dark:text-slate-300">{user.plan || 'starter'}</span>
                    </p>
                    <Button type="submit" disabled={!profileDirty || savingProfile}>
                      {savingProfile ? 'Saving…' : 'Save changes'}
                    </Button>
                  </div>
                </form>
              </div>
            </CardContent>
          </Card>

          <div className="space-y-6">
            <Card className="border-slate-200 shadow-sm">
              <CardHeader className="pb-4">
                <CardTitle className="flex items-center gap-2 text-slate-900 dark:text-slate-100">
                  <FaShieldAlt className="text-sm text-slate-500" />
                  Verification and security
                </CardTitle>
                <CardDescription>
                  Confirm your email and manage password access based on how this account signs in.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-900/40">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <Badge className={user.email_verified ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-amber-200 bg-amber-50 text-amber-700'} variant="outline">
                          {user.email_verified ? 'Verified' : 'Verification required'}
                        </Badge>
                        {!user.email_verified && <FaClock className="text-xs text-amber-600" />}
                      </div>
                      <p className="text-sm text-slate-700 dark:text-slate-300">
                        {user.email_verified
                          ? 'Your email is confirmed. Publishing, scheduling, and team approvals can proceed normally.'
                          : 'Verify this email before publishing, scheduling, and team invite or approval actions.'}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        We can resend a fresh verification link to <span className="font-medium">{user.email}</span>.
                      </p>
                    </div>
                    {!user.email_verified && (
                      <Button variant="outline" onClick={handleResendVerification} disabled={resendingVerification}>
                        {resendingVerification ? 'Sending…' : 'Resend email'}
                      </Button>
                    )}
                  </div>
                </div>

                {securityMode === 'password' && (
                  <form onSubmit={handlePasswordChange} className="space-y-4">
                    <div className="space-y-1.5">
                      <Label htmlFor="settings-current-password">Current password</Label>
                      <Input
                        id="settings-current-password"
                        type="password"
                        value={passwordForm.current}
                        onChange={(event) => setPasswordForm((current) => ({ ...current, current: event.target.value }))}
                        placeholder="Enter your current password"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="settings-new-password">New password</Label>
                      <Input
                        id="settings-new-password"
                        type="password"
                        value={passwordForm.next}
                        onChange={(event) => setPasswordForm((current) => ({ ...current, next: event.target.value }))}
                        placeholder="At least 8 characters"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="settings-confirm-password">Confirm new password</Label>
                      <Input
                        id="settings-confirm-password"
                        type="password"
                        value={passwordForm.confirm}
                        onChange={(event) => setPasswordForm((current) => ({ ...current, confirm: event.target.value }))}
                        placeholder="Repeat the new password"
                      />
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        Password changes use Firebase re-authentication for security.
                      </p>
                      <Button
                        type="submit"
                        disabled={updatingPassword || !passwordForm.current || !passwordForm.next || !passwordForm.confirm}
                      >
                        {updatingPassword ? 'Updating…' : 'Update password'}
                      </Button>
                    </div>
                  </form>
                )}

                {securityMode === 'google' && (
                  <div className="rounded-2xl border border-slate-200 p-4 text-sm text-slate-700 dark:border-slate-800 dark:text-slate-300">
                    This account signs in through Google. Password changes are managed by Google rather than inside Unravler.
                  </div>
                )}

                {securityMode === 'provider' && (
                  <div className="rounded-2xl border border-slate-200 p-4 text-sm text-slate-700 dark:border-slate-800 dark:text-slate-300">
                    This sign-in method is provider-managed. If you need to change credentials, update them through the provider you used to log in.
                  </div>
                )}

                {securityMode === 'reset-guidance' && (
                  <div className="rounded-2xl border border-slate-200 p-4 dark:border-slate-800">
                    <p className="text-sm text-slate-700 dark:text-slate-300">
                      Password changes require an active Firebase session. If you signed in from another browser or only have a server session right now, use reset password instead.
                    </p>
                    <Button asChild variant="outline" className="mt-4">
                      <Link to="/forgot-password">Open reset password</Link>
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="border-slate-200 shadow-sm">
              <CardHeader className="pb-4">
                <CardTitle className="flex items-center gap-2 text-slate-900 dark:text-slate-100">
                  <FaExternalLinkAlt className="text-sm text-slate-500" />
                  Billing
                </CardTitle>
                <CardDescription>
                  Subscription changes stay on the dedicated billing surface.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex items-center justify-between gap-4">
                <div className="space-y-2">
                  <Badge className={statusBadgeClassName(user.subscription_status)} variant="outline">
                    {(user.subscription_status || 'free').replace('_', ' ')}
                  </Badge>
                  <p className="text-sm text-slate-700 dark:text-slate-300">
                    <span className="font-medium capitalize">{user.plan || 'starter'}</span> plan
                  </p>
                </div>
                <Button asChild variant="outline">
                  <Link to="/billing">Manage billing</Link>
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>

        <Card className="border-slate-200 shadow-sm">
          <CardHeader className="pb-4">
            <CardTitle className="flex items-center gap-2 text-slate-900 dark:text-slate-100">
              <FaBell className="text-sm text-slate-500" />
              Notification preferences
            </CardTitle>
            <CardDescription>
              Control the supported events Unravler can send by email or show inside the app.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-[minmax(0,1fr)_72px_72px] items-center gap-3 border-b border-slate-200 pb-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:border-slate-800">
              <span>Event</span>
              <span className="text-center">Email</span>
              <span className="text-center">In-app</span>
            </div>

            {loadingNotifications ? (
              <div className="space-y-3">
                {NOTIFICATION_EVENTS.map((event) => (
                  <div key={event.key} className="grid grid-cols-[minmax(0,1fr)_72px_72px] items-center gap-3 rounded-2xl border border-slate-200 p-4 dark:border-slate-800">
                    <div className="space-y-2">
                      <div className="h-4 w-40 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
                      <div className="h-3 w-64 animate-pulse rounded bg-slate-100 dark:bg-slate-900" />
                    </div>
                    <div className="mx-auto h-5 w-9 animate-pulse rounded-full bg-slate-200 dark:bg-slate-800" />
                    <div className="mx-auto h-5 w-9 animate-pulse rounded-full bg-slate-200 dark:bg-slate-800" />
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                {NOTIFICATION_EVENTS.map((event) => {
                  const channels = notificationPreferences[event.key]?.channels || [];
                  return (
                    <div
                      key={event.key}
                      className="grid grid-cols-[minmax(0,1fr)_72px_72px] items-center gap-3 rounded-2xl border border-slate-200 px-4 py-4 dark:border-slate-800"
                    >
                      <div className="space-y-1">
                        <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{event.label}</p>
                        <p className="text-xs text-slate-500 dark:text-slate-400">{event.description}</p>
                      </div>
                      <div className="flex justify-center">
                        <Switch
                          checked={channels.includes('email')}
                          onCheckedChange={(checked) => toggleNotificationChannel(event.key, 'email', checked)}
                          aria-label={`${event.label} email notifications`}
                        />
                      </div>
                      <div className="flex justify-center">
                        <Switch
                          checked={channels.includes('in_app')}
                          onCheckedChange={(checked) => toggleNotificationChannel(event.key, 'in_app', checked)}
                          aria-label={`${event.label} in-app notifications`}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="flex justify-end pt-2">
              <Button onClick={handleNotificationSave} disabled={savingNotifications || loadingNotifications}>
                {savingNotifications ? 'Saving…' : 'Save preferences'}
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.85fr)]">
          <Card className="border-slate-200 shadow-sm">
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-2 text-slate-900 dark:text-slate-100">
                <FaEnvelope className="text-sm text-slate-500" />
                Privacy and data
              </CardTitle>
              <CardDescription>
                Export your account data or review how Unravler handles privacy and deletion requests.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-2xl border border-slate-200 p-4 dark:border-slate-800">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Export my data</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      Queue a portable export of your account, scheduling, and workspace data.
                    </p>
                  </div>
                  <Button variant="outline" onClick={handleExportData} disabled={exportingData}>
                    {exportingData ? 'Preparing…' : 'Request export'}
                  </Button>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600 dark:text-slate-300">
                <Link to="/privacy" className="inline-flex items-center gap-2 hover:text-slate-900 dark:hover:text-slate-100">
                  Privacy policy <FaExternalLinkAlt className="text-xs" />
                </Link>
                <Link to="/data-deletion" className="inline-flex items-center gap-2 hover:text-slate-900 dark:hover:text-slate-100">
                  Data deletion instructions <FaExternalLinkAlt className="text-xs" />
                </Link>
              </div>
            </CardContent>
          </Card>

          <Card className="border-rose-200 shadow-sm dark:border-rose-900/60">
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-2 text-rose-700 dark:text-rose-300">
                <FaTrashAlt className="text-sm" />
                Danger zone
              </CardTitle>
              <CardDescription>
                Queue permanent account deletion. This removes your workspace data and cannot be undone.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-200">
                <div className="flex items-start gap-3">
                  <FaExclamationTriangle className="mt-0.5 text-sm" />
                  <div className="space-y-1">
                    <p className="font-medium">Delete account</p>
                    <p className="text-xs leading-5 text-rose-700 dark:text-rose-300">
                      Connected accounts, scheduled posts, and workspace data enter the deletion pipeline immediately after confirmation.
                    </p>
                  </div>
                </div>
              </div>

              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="destructive" className="w-full">
                    Delete account
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader className="text-left sm:text-left">
                    <AlertDialogTitle>Delete your Unravler account?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This queues permanent deletion of your account, scheduled posts, media, and workspace data. The request cannot be undone after it is submitted.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel disabled={deletingAccount}>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={handleDeleteAccount}
                      disabled={deletingAccount}
                      className="bg-rose-600 hover:bg-rose-700 focus:ring-rose-500"
                    >
                      {deletingAccount ? 'Deleting…' : 'Yes, queue deletion'}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </CardContent>
          </Card>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Settings;
