import React, { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import { useAuth } from '@/context/AuthContext';
import {
  getSocialAccounts,
  disconnectSocialAccount,
  connectBluesky,
  connectDiscord,
  connectMastodon,
  getLinkedInPendingOrgs,
  saveLinkedInOrgs,
  addLinkedInPageManually,
} from '@/lib/api';
import {
  getPublishFailureAction,
  getPublishFailureMessage,
  getTikTokRestrictionFromAccount,
} from '@/lib/publishFailures';
import { clearOAuthPopupExpected, listenForOAuthResult, markOAuthPopupExpected } from '@/lib/oauthPopup';
import { requestOAuthUrl } from '@/lib/requestOAuthUrl';
import { toast } from 'sonner';
import {
  FaCheckCircle,
  FaDiscord,
  FaExclamationTriangle,
  FaFacebook,
  FaInstagram,
  FaLink,
  FaLinkedin,
  FaPinterest,
  FaPlus,
  FaTimes,
  FaTiktok,
  FaTwitter,
  FaYoutube,
} from 'react-icons/fa';
import { SiBluesky, SiMastodon, SiReddit, SiSnapchat, SiThreads } from 'react-icons/si';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

const MANUAL_PLATFORMS = new Set(['bluesky', 'discord', 'mastodon']);
const OAUTH_PLATFORMS = new Set([
  'facebook',
  'instagram',
  'youtube',
  'twitter',
  'linkedin',
  'threads',
  'reddit',
  'pinterest',
  'snapchat',
  'tiktok',
]);
const ATTENTION_STATES = new Set(['reconnect_required', 'restricted', 'expiring']);
const STATE_ORDER = {
  reconnect_required: 0,
  restricted: 1,
  expiring: 2,
  healthy: 3,
};

const PLATFORMS = [
  { id: 'instagram', name: 'Instagram', icon: FaInstagram, color: 'text-pink-500', bg: 'bg-pink-50', border: 'border-pink-200', btn: 'bg-pink-500 hover:bg-pink-600' },
  { id: 'facebook', name: 'Facebook', icon: FaFacebook, color: 'text-blue-600', bg: 'bg-blue-50', border: 'border-blue-200', btn: 'bg-blue-600 hover:bg-blue-700' },
  { id: 'twitter', name: 'X (Twitter)', icon: FaTwitter, color: 'text-sky-400', bg: 'bg-sky-50', border: 'border-sky-200', btn: 'bg-gray-900 hover:bg-black' },
  { id: 'linkedin', name: 'LinkedIn', icon: FaLinkedin, color: 'text-blue-700', bg: 'bg-blue-50', border: 'border-blue-300', btn: 'bg-blue-700 hover:bg-blue-800' },
  { id: 'youtube', name: 'YouTube', icon: FaYoutube, color: 'text-red-600', bg: 'bg-red-50', border: 'border-red-200', btn: 'bg-red-600 hover:bg-red-700' },
  { id: 'tiktok', name: 'TikTok', icon: FaTiktok, color: 'text-gray-900', bg: 'bg-gray-50', border: 'border-gray-300', btn: 'bg-gray-900 hover:bg-black' },
  { id: 'threads', name: 'Threads', icon: SiThreads, color: 'text-gray-900', bg: 'bg-gray-50', border: 'border-gray-300', btn: 'bg-gray-900 hover:bg-black' },
  { id: 'pinterest', name: 'Pinterest', icon: FaPinterest, color: 'text-red-600', bg: 'bg-red-50', border: 'border-red-200', btn: 'bg-red-600 hover:bg-red-700' },
  { id: 'reddit', name: 'Reddit', icon: SiReddit, color: 'text-orange-500', bg: 'bg-orange-50', border: 'border-orange-200', btn: 'bg-orange-500 hover:bg-orange-600' },
  { id: 'snapchat', name: 'Snapchat', icon: SiSnapchat, color: 'text-yellow-500', bg: 'bg-yellow-50', border: 'border-yellow-200', btn: 'bg-yellow-400 hover:bg-yellow-500', badge: 'Spotlight only' },
  { id: 'bluesky', name: 'Bluesky', icon: SiBluesky, color: 'text-sky-500', bg: 'bg-sky-50', border: 'border-sky-200', btn: 'bg-sky-500 hover:bg-sky-600', badge: 'App Password' },
  { id: 'discord', name: 'Discord', icon: FaDiscord, color: 'text-indigo-500', bg: 'bg-indigo-50', border: 'border-indigo-200', btn: 'bg-indigo-500 hover:bg-indigo-600', badge: 'Webhook' },
  { id: 'mastodon', name: 'Mastodon', icon: SiMastodon, color: 'text-indigo-600', bg: 'bg-indigo-50', border: 'border-indigo-200', btn: 'bg-indigo-600 hover:bg-indigo-700', badge: 'Access token' },
];

const getAvatarColor = (value = '') => {
  const palette = ['bg-blue-500', 'bg-green-500', 'bg-yellow-500', 'bg-red-500', 'bg-purple-500', 'bg-pink-500', 'bg-indigo-500', 'bg-teal-500'];
  return palette[value.charCodeAt(0) % palette.length];
};

const formatAbsoluteDate = (value, { includeTime = false } = {}) => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString('en-US', includeTime
    ? { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }
    : { month: 'short', day: 'numeric', year: 'numeric' });
};

const getConnectionState = (account) => {
  const state = account?.connection_state;
  if (state && STATE_ORDER[state] !== undefined) return state;

  if (account?.publish_restriction_type || account?.publish_action_required || account?.publish_error_code) {
    return 'restricted';
  }

  const expiresAt = account?.expires_at || account?.token_expiry;
  if (!expiresAt) return account?.token_error ? 'reconnect_required' : 'healthy';

  const expiryDate = new Date(expiresAt);
  if (Number.isNaN(expiryDate.getTime())) return account?.token_error ? 'reconnect_required' : 'healthy';

  const diffHours = (expiryDate.getTime() - Date.now()) / (1000 * 60 * 60);
  if (account?.token_error || diffHours < 0) return 'reconnect_required';
  if (diffHours < 24) return 'expiring';
  return 'healthy';
};

const getConnectionMessage = (account) => {
  if (account?.connection_message) return account.connection_message;
  const state = getConnectionState(account);
  if (state === 'restricted') {
    return account?.publish_action_required || account?.publish_restriction_type || account?.publish_error_code || 'Publishing is currently restricted for this account.';
  }
  if (state === 'reconnect_required') {
    return account?.reconnect_reason || account?.token_error || 'Reconnect this account to restore access.';
  }
  if (state === 'expiring') {
    return 'Access token expires soon. Reconnect proactively to avoid interruptions.';
  }
  return 'Connection is healthy.';
};

const getStatusTone = (state) => {
  switch (state) {
    case 'reconnect_required':
      return {
        label: 'Reconnect required',
        badge: 'bg-red-100 text-red-700 border-red-200',
        panel: 'border-red-200 bg-red-50',
      };
    case 'restricted':
      return {
        label: 'Restricted',
        badge: 'bg-amber-100 text-amber-800 border-amber-200',
        panel: 'border-amber-200 bg-amber-50',
      };
    case 'expiring':
      return {
        label: 'Expiring soon',
        badge: 'bg-yellow-100 text-yellow-800 border-yellow-200',
        panel: 'border-yellow-200 bg-yellow-50',
      };
    default:
      return {
        label: 'Healthy',
        badge: 'bg-emerald-100 text-emerald-700 border-emerald-200',
        panel: 'border-emerald-200 bg-emerald-50',
      };
  }
};

const getDisplayName = (account) => account.display_name || account.platform_username || 'Connected account';

const getHandle = (account) => account.platform_username ? `@${account.platform_username}` : null;

const getLinkedInAccountType = (account) => {
  const raw = String(account?.account_type || '').toLowerCase();
  if (raw === 'organization' || account?.linkedin_org_id) return 'organization';
  return 'profile';
};

const getLinkedInAccountTypeLabel = (account) => (
  getLinkedInAccountType(account) === 'organization' ? 'Company Page' : 'Profile'
);

const sortAccounts = (accounts) => (
  [...accounts].sort((left, right) => {
    const leftState = getConnectionState(left);
    const rightState = getConnectionState(right);
    const stateDiff = (STATE_ORDER[leftState] ?? 99) - (STATE_ORDER[rightState] ?? 99);
    if (stateDiff !== 0) return stateDiff;
    return getDisplayName(left).localeCompare(getDisplayName(right));
  })
);

const getPrimaryActionLabel = (accounts) => {
  if (accounts.length === 0) return 'Connect';
  if (accounts.some((account) => ATTENTION_STATES.has(getConnectionState(account)))) return 'Reconnect';
  return 'Add account';
};

const VerificationBanner = () => (
  <div className="rounded-3xl border border-blue-200 bg-blue-50 px-5 py-4">
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="text-sm font-semibold text-blue-900">Account connection is available, but email verification is still recommended</p>
        <p className="mt-1 text-sm text-blue-800">
          You can connect and reconnect accounts now. Email verification is still required before publishing, scheduling, and inviting teammates.
        </p>
      </div>
      <Link
        to="/verify-email?returnTo=/accounts"
        className="inline-flex items-center justify-center rounded-full bg-blue-900 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-950"
      >
        Verify email
      </Link>
    </div>
  </div>
);

const SummaryCard = ({ label, value, tone = 'neutral', detail }) => {
  const toneClasses = {
    neutral: 'border-gray-200 bg-white text-gray-900',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    warning: 'border-amber-200 bg-amber-50 text-amber-900',
    danger: 'border-red-200 bg-red-50 text-red-900',
  };

  return (
    <div className={`rounded-3xl border px-5 py-4 ${toneClasses[tone] || toneClasses.neutral}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-current/70">{label}</p>
      <p className="mt-3 text-3xl font-semibold">{value}</p>
      {detail ? <p className="mt-2 text-sm text-current/75">{detail}</p> : null}
    </div>
  );
};

const StatusBadge = ({ state }) => {
  const tone = getStatusTone(state);
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${tone.badge}`}>
      {tone.label}
    </span>
  );
};

const AccountAvatar = ({ account }) => {
  const displayName = getDisplayName(account);
  if (account.picture_url) {
    return <img src={account.picture_url} alt={displayName} className="h-12 w-12 rounded-2xl object-cover shadow-sm" />;
  }
  return (
    <div className={`flex h-12 w-12 items-center justify-center rounded-2xl text-sm font-bold text-white shadow-sm ${getAvatarColor(displayName)}`}>
      {displayName.charAt(0).toUpperCase()}
    </div>
  );
};

const ConnectedAccountRow = ({
  account,
  platform,
  onReconnect,
  onDisconnect,
  connecting,
  disconnectingAccountId,
}) => {
  const state = getConnectionState(account);
  const tone = getStatusTone(state);
  const handle = getHandle(account);
  const expiresAt = formatAbsoluteDate(account.expires_at);
  const connectedAt = formatAbsoluteDate(account.connected_at);
  const restriction = platform.id === 'tiktok' ? getTikTokRestrictionFromAccount(account) : null;
  const primaryMessage = restriction ? getPublishFailureMessage(restriction) : getConnectionMessage(account);
  const secondaryMessage = restriction ? getPublishFailureAction(restriction) : null;
  const linkedinTypeLabel = platform.id === 'linkedin' ? getLinkedInAccountTypeLabel(account) : null;

  return (
    <div className={`rounded-2xl border px-4 py-4 ${tone.panel}`}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 gap-3">
          <AccountAvatar account={account} />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold text-gray-900">{getDisplayName(account)}</p>
              {linkedinTypeLabel ? (
                <span className="rounded-full border border-blue-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-blue-700">
                  {linkedinTypeLabel}
                </span>
              ) : null}
              <StatusBadge state={state} />
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-500">
              {handle ? <span>{handle}</span> : null}
              <span>{platform.name}</span>
              {linkedinTypeLabel ? <span>{linkedinTypeLabel}</span> : null}
              {expiresAt ? <span>Expires {expiresAt}</span> : null}
              {!expiresAt && connectedAt ? <span>Connected {connectedAt}</span> : null}
            </div>
            <p className="mt-2 text-sm text-gray-700">{primaryMessage}</p>
            {secondaryMessage ? <p className="mt-1 text-xs font-medium text-amber-800">{secondaryMessage}</p> : null}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {state !== 'healthy' ? (
            <button
              onClick={() => onReconnect(platform.id, { mode: 'reconnect', account })}
              disabled={connecting === platform.id}
              className="inline-flex items-center gap-2 rounded-full bg-gray-900 px-3.5 py-2 text-sm font-semibold text-white transition-colors hover:bg-black disabled:opacity-60"
            >
              {connecting === platform.id ? (
                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
              ) : (
                <FaLink className="text-[11px]" />
              )}
              {connecting === platform.id ? 'Opening…' : 'Reconnect'}
            </button>
          ) : null}
          <button
            onClick={() => onDisconnect(account.id, platform.name)}
            disabled={disconnectingAccountId === account.id}
            className="inline-flex items-center gap-2 rounded-full border border-gray-300 bg-white px-3.5 py-2 text-sm font-medium text-gray-700 transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-700 disabled:opacity-60"
          >
            {disconnectingAccountId === account.id ? (
              <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-gray-500 border-t-transparent" />
            ) : (
              <FaTimes className="text-[10px]" />
            )}
            Disconnect
          </button>
        </div>
      </div>
    </div>
  );
};

const PlatformCard = ({
  platform,
  accounts,
  onPrimaryAction,
  onReconnect,
  onDisconnect,
  connecting,
  disconnectingAccountId,
}) => {
  const Icon = platform.icon;
  const sortedAccounts = useMemo(() => sortAccounts(accounts), [accounts]);
  const attentionAccounts = sortedAccounts.filter((account) => ATTENTION_STATES.has(getConnectionState(account)));
  const healthyAccounts = sortedAccounts.filter((account) => !ATTENTION_STATES.has(getConnectionState(account)));
  const state = sortedAccounts[0] ? getConnectionState(sortedAccounts[0]) : 'healthy';
  const count = accounts.length;

  return (
    <section className="flex h-[44rem] flex-col overflow-hidden rounded-[28px] border border-gray-200 bg-white shadow-sm">
      <div className={`border-b px-5 py-5 ${platform.bg} ${platform.border}`}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <div className={`flex h-12 w-12 items-center justify-center rounded-2xl border bg-white/80 shadow-sm ${platform.border}`}>
              <Icon className={`text-xl ${platform.color}`} />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold text-gray-900">{platform.name}</h2>
                {platform.badge ? (
                  <span className="rounded-full border border-white/70 bg-white/80 px-2 py-0.5 text-[11px] font-medium text-gray-600">
                    {platform.badge}
                  </span>
                ) : null}
              </div>
              <p className="mt-1 text-sm text-gray-600">
                {count > 0
                  ? `${count} connected ${count === 1 ? 'account' : 'accounts'}`
                  : 'No accounts connected yet'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {count > 0 ? <StatusBadge state={state} /> : null}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-hidden px-5 py-5">
        <div className="h-full space-y-5 overflow-y-auto pr-2">
        {count === 0 ? (
          <div className="rounded-2xl border border-dashed border-gray-300 bg-gray-50 px-4 py-5 text-sm text-gray-500">
            Connect this platform to schedule, publish, and track account health from one place.
          </div>
        ) : (
          <>
            {attentionAccounts.length > 0 ? (
              <div>
                <div className="mb-3 flex items-center gap-2">
                  <FaExclamationTriangle className="text-red-500" />
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-500">Needs attention</p>
                </div>
                <div className="space-y-3">
                  {attentionAccounts.map((account) => (
                    <ConnectedAccountRow
                      key={account.id}
                      account={account}
                      platform={platform}
                      onReconnect={onReconnect}
                      onDisconnect={onDisconnect}
                      connecting={connecting}
                      disconnectingAccountId={disconnectingAccountId}
                    />
                  ))}
                </div>
              </div>
            ) : null}

            {healthyAccounts.length > 0 ? (
              <div>
                <div className="mb-3 flex items-center gap-2">
                  <FaCheckCircle className="text-emerald-500" />
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-500">Healthy connections</p>
                </div>
                <div className="space-y-3">
                  {healthyAccounts.map((account) => (
                    <ConnectedAccountRow
                      key={account.id}
                      account={account}
                      platform={platform}
                      onReconnect={onReconnect}
                      onDisconnect={onDisconnect}
                      connecting={connecting}
                      disconnectingAccountId={disconnectingAccountId}
                    />
                  ))}
                </div>
              </div>
            ) : null}
          </>
        )}
        </div>
      </div>

      <div className="border-t border-gray-100 px-5 py-4">
        <button
          onClick={() => onPrimaryAction(platform.id)}
          disabled={connecting === platform.id}
          className={`inline-flex w-full items-center justify-center gap-2 rounded-2xl px-4 py-3 text-sm font-semibold text-white transition-colors disabled:opacity-60 ${platform.btn}`}
        >
          {connecting === platform.id ? (
            <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
          ) : accounts.length > 0 && accounts.some((account) => ATTENTION_STATES.has(getConnectionState(account))) ? (
            <FaLink className="text-[11px]" />
          ) : (
            <FaPlus className="text-[11px]" />
          )}
          {connecting === platform.id ? 'Opening…' : `${getPrimaryActionLabel(accounts)} ${platform.name}`}
        </button>
      </div>
    </section>
  );
};

const AttentionItem = ({ account, platform, onReconnect, connecting }) => {
  const state = getConnectionState(account);
  const handle = getHandle(account);
  const restriction = platform.id === 'tiktok' ? getTikTokRestrictionFromAccount(account) : null;
  const message = restriction ? getPublishFailureMessage(restriction) : getConnectionMessage(account);
  const linkedinTypeLabel = platform.id === 'linkedin' ? getLinkedInAccountTypeLabel(account) : null;

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-gray-200 bg-white px-4 py-4 md:flex-row md:items-center md:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        <div className={`flex h-11 w-11 items-center justify-center rounded-2xl ${platform.bg}`}>
          <platform.icon className={`text-lg ${platform.color}`} />
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-gray-900">{getDisplayName(account)}</p>
            {linkedinTypeLabel ? (
              <span className="rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] font-semibold text-blue-700">
                {linkedinTypeLabel}
              </span>
            ) : null}
            <StatusBadge state={state} />
          </div>
          <p className="mt-1 text-sm text-gray-600">
            {platform.name}{handle ? ` · ${handle}` : ''}
          </p>
          <p className={`mt-2 text-sm ${state === 'restricted' ? 'text-amber-800' : 'text-gray-700'}`}>
            {message}
          </p>
        </div>
      </div>
      <button
        onClick={() => onReconnect(platform.id, { mode: 'reconnect', account })}
        disabled={connecting === platform.id}
        className="inline-flex shrink-0 items-center justify-center gap-2 rounded-full bg-gray-900 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-black disabled:opacity-60"
      >
        {connecting === platform.id ? (
          <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
        ) : (
          <FaLink className="text-[11px]" />
        )}
        {connecting === platform.id ? 'Opening…' : 'Reconnect'}
      </button>
    </div>
  );
};

const LoadingSkeleton = () => (
  <div className="space-y-8">
    <div className="grid gap-4 md:grid-cols-3">
      {[0, 1, 2].map((index) => (
        <div key={index} className="h-28 animate-pulse rounded-3xl border border-gray-200 bg-white" />
      ))}
    </div>
    <div className="grid gap-5 xl:grid-cols-2">
      {[0, 1, 2, 3].map((index) => (
        <div key={index} className="h-80 animate-pulse rounded-[28px] border border-gray-200 bg-white" />
      ))}
    </div>
  </div>
);

const CredentialDialogShell = ({
  open,
  onOpenChange,
  icon,
  iconClassName,
  iconWrapClassName,
  title,
  description,
  children,
  footer,
}) => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="max-w-md rounded-[28px] border-0 p-0 shadow-2xl">
      <div className="space-y-6 p-6">
        <DialogHeader className="text-left">
          <div className="flex items-start gap-3">
            <div className={`flex h-12 w-12 items-center justify-center rounded-2xl border ${iconWrapClassName}`}>
              {React.createElement(icon, { className: iconClassName })}
            </div>
            <div>
              <DialogTitle>{title}</DialogTitle>
              <DialogDescription className="mt-1">{description}</DialogDescription>
            </div>
          </div>
        </DialogHeader>
        {children}
        <DialogFooter className="justify-end gap-2 sm:justify-end">
          {footer}
        </DialogFooter>
      </div>
    </DialogContent>
  </Dialog>
);

const ConnectedAccounts = () => {
  const { user } = useAuth();
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(null);
  const [disconnectingAccountId, setDisconnectingAccountId] = useState(null);
  const [fetchError, setFetchError] = useState(null);
  const [manualModal, setManualModal] = useState({ platformId: null, mode: 'connect' });

  const [blueskyHandle, setBlueskyHandle] = useState('');
  const [blueskyPass, setBlueskyPass] = useState('');
  const [blueskyLoading, setBlueskyLoading] = useState(false);

  const [discordWebhookUrl, setDiscordWebhookUrl] = useState('');
  const [discordChannelName, setDiscordChannelName] = useState('');
  const [discordLoading, setDiscordLoading] = useState(false);

  const [mastodonInstanceUrl, setMastodonInstanceUrl] = useState('');
  const [mastodonAccessToken, setMastodonAccessToken] = useState('');
  const [mastodonLoading, setMastodonLoading] = useState(false);

  const [linkedinOrgsModal, setLinkedinOrgsModal] = useState(false);
  const [linkedinOrgs, setLinkedinOrgs] = useState([]);
  const [selectedOrgs, setSelectedOrgs] = useState([]);
  const [savingOrgs, setSavingOrgs] = useState(false);
  const [linkedinGrantAccountId, setLinkedinGrantAccountId] = useState(null);
  const [linkedinChoiceModal, setLinkedinChoiceModal] = useState({ open: false, mode: 'connect', account: null });
  const [linkedinPageModal, setLinkedinPageModal] = useState(false);
  const [pageIdInput, setPageIdInput] = useState('');
  const [pageNameInput, setPageNameInput] = useState('');
  const [addingPage, setAddingPage] = useState(false);

  const [searchParams] = useSearchParams();

  useEffect(() => {
    fetchAccounts();
  }, []);

  useEffect(() => {
    clearOAuthPopupExpected();
  }, []);

  useEffect(() => (
    listenForOAuthResult((message) => {
      if (!message || message.returnTo !== 'accounts') return;

      clearOAuthPopupExpected();
      setConnecting(null);

      if (message.status === 'success') {
        toast.success(`${message.platform || 'Account'} connected successfully!`);
        fetchAccounts();
      } else if (message.status === 'error') {
        toast.error(message.error || 'Failed to connect account');
      }
    })
  ), []);

  useEffect(() => {
    if (searchParams.get('linkedin_profile') === '1') {
      toast.success('LinkedIn profile connected!');
      fetchAccounts();
    } else if (searchParams.get('linkedin_orgs') === '1') {
      fetchAccounts();
      getLinkedInPendingOrgs().then((data) => {
        setLinkedinGrantAccountId(data.grant_account_id || null);
        if (data.orgs?.length > 0) {
          setLinkedinOrgs(data.orgs);
          setSelectedOrgs(data.orgs.map((org) => org.org_id));
          setLinkedinOrgsModal(true);
        } else {
          toast.info('LinkedIn connected, but no manageable company pages were returned.');
        }
      }).catch((error) => {
        toast.error(error?.response?.data?.detail || 'Unable to load LinkedIn company pages.');
      });
    } else if (searchParams.get('connected') === 'true') {
      toast.success(`Successfully connected: ${searchParams.get('platforms') || 'account'}`);
      fetchAccounts();
    }

    if (searchParams.get('error')) {
      toast.error(`Connection failed: ${searchParams.get('message') || searchParams.get('error')}`);
    }
  }, [searchParams]);

  const fetchAccounts = async () => {
    try {
      setFetchError(null);
      const data = await getSocialAccounts();
      setAccounts(data);
    } catch {
      setFetchError('Failed to load connected accounts.');
      toast.error('Failed to load accounts');
    } finally {
      setLoading(false);
    }
  };

  const closeManualModal = () => {
    setManualModal({ platformId: null, mode: 'connect' });
    setBlueskyHandle('');
    setBlueskyPass('');
    setDiscordWebhookUrl('');
    setDiscordChannelName('');
    setMastodonInstanceUrl('');
    setMastodonAccessToken('');
  };

  const openManualModal = (platformId, mode) => {
    setManualModal({ platformId, mode });
  };

  const startOAuth = async (platformId, { accountType = null } = {}) => {
    setConnecting(platformId);
    markOAuthPopupExpected(false);

    try {
      const requestOptions = platformId === 'linkedin' && accountType
        ? { accountType }
        : {};
      const { authorization_url, code_verifier } = await requestOAuthUrl(platformId, requestOptions);
      if (code_verifier) sessionStorage.setItem('twitter_code_verifier', code_verifier);
      sessionStorage.setItem('oauth_platform', platformId);
      sessionStorage.setItem('oauth_return_to', 'accounts');
      if (platformId === 'linkedin' && accountType) {
        sessionStorage.setItem('linkedin_account_type', accountType);
      } else {
        sessionStorage.removeItem('linkedin_account_type');
      }
      window.location.assign(authorization_url);
      return;
    } catch (error) {
      clearOAuthPopupExpected();
      const detail = error.response?.data?.detail;
      if ((error.response?.status === 500 || error.response?.status === 503) && detail?.includes('not configured')) {
        toast.error(detail);
      } else {
        toast.error(detail || 'Failed to connect account');
      }
    } finally {
      setConnecting(null);
    }
  };

  const handleLinkedInChoice = (accountType) => {
    setLinkedinChoiceModal({ open: false, mode: 'connect', account: null });
    startOAuth('linkedin', { accountType });
  };

  const handleConnect = async (platformId, { mode = 'connect', account = null, accountType = null } = {}) => {
    if (MANUAL_PLATFORMS.has(platformId)) {
      openManualModal(platformId, mode);
      return;
    }

    if (!OAUTH_PLATFORMS.has(platformId)) return;

    if (platformId === 'linkedin') {
      const inferredType = accountType || (account ? getLinkedInAccountType(account) : null);
      if (inferredType) {
        await startOAuth(platformId, { accountType: inferredType });
        return;
      }
      setLinkedinChoiceModal({ open: true, mode, account });
      return;
    }

    await startOAuth(platformId);
  };

  const handleDisconnect = async (accountId, platformName) => {
    if (!window.confirm(`Disconnect your ${platformName} account? This cannot be undone.`)) return;
    try {
      setDisconnectingAccountId(accountId);
      await disconnectSocialAccount(accountId);
      setAccounts((previous) => previous.filter((account) => account.id !== accountId));
      toast.success(`${platformName} account disconnected`);
    } catch {
      toast.error('Failed to disconnect account');
    } finally {
      setDisconnectingAccountId(null);
    }
  };

  const handleBlueskyConnect = async () => {
    if (!blueskyHandle.trim() || !blueskyPass.trim()) return;

    setBlueskyLoading(true);
    try {
      await connectBluesky({ handle: blueskyHandle.trim(), app_password: blueskyPass.trim() });
      toast.success(`Bluesky account ${manualModal.mode === 'reconnect' ? 'reconnected' : 'connected'}!`);
      closeManualModal();
      fetchAccounts();
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to connect Bluesky');
    } finally {
      setBlueskyLoading(false);
    }
  };

  const handleDiscordConnect = async () => {
    if (!discordWebhookUrl.trim()) return;

    setDiscordLoading(true);
    try {
      const response = await connectDiscord(discordWebhookUrl.trim(), discordChannelName.trim() || null);
      toast.success(
        response?.channel
          ? `Discord channel ${manualModal.mode === 'reconnect' ? 'reconnected' : 'connected'}: ${response.channel}`
          : `Discord ${manualModal.mode === 'reconnect' ? 'reconnected' : 'connected'} successfully!`,
      );
      closeManualModal();
      fetchAccounts();
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Invalid webhook URL. Make sure it is a valid Discord webhook.');
    } finally {
      setDiscordLoading(false);
    }
  };

  const handleMastodonConnect = async () => {
    if (!mastodonInstanceUrl.trim() || !mastodonAccessToken.trim()) return;

    setMastodonLoading(true);
    try {
      const response = await connectMastodon(mastodonInstanceUrl.trim(), mastodonAccessToken.trim());
      toast.success(`Mastodon account "${response.username}" ${manualModal.mode === 'reconnect' ? 'reconnected' : 'connected'}!`);
      closeManualModal();
      fetchAccounts();
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to connect Mastodon');
    } finally {
      setMastodonLoading(false);
    }
  };

  const handleAddLinkedinPage = async () => {
    if (!pageIdInput.trim() || !pageNameInput.trim()) return;

    setAddingPage(true);
    try {
      await addLinkedInPageManually({
        page_id: pageIdInput.trim(),
        page_name: pageNameInput.trim(),
      });
      toast.success(`LinkedIn page "${pageNameInput}" connected!`);
      setLinkedinPageModal(false);
      setPageIdInput('');
      setPageNameInput('');
      fetchAccounts();
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Failed to add LinkedIn page');
    } finally {
      setAddingPage(false);
    }
  };

  const handleSaveLinkedinOrgs = async () => {
    setSavingOrgs(true);
    try {
      const result = await saveLinkedInOrgs({
        org_ids: selectedOrgs,
        grant_account_id: linkedinGrantAccountId,
      });
      toast.success(`${result.org_count} LinkedIn page${result.org_count !== 1 ? 's' : ''} connected!`);
      setLinkedinOrgsModal(false);
      setLinkedinGrantAccountId(null);
      fetchAccounts();
    } catch {
      toast.error('Failed to connect LinkedIn pages');
    } finally {
      setSavingOrgs(false);
    }
  };

  const verificationRequired = Boolean(user && !user.email_verified);

  const platformModels = useMemo(
    () => PLATFORMS.map((platform) => ({
      platform,
      accounts: sortAccounts(accounts.filter((account) => account.platform === platform.id)),
    })),
    [accounts],
  );

  const attentionAccounts = useMemo(
    () => platformModels.flatMap(({ platform, accounts: platformAccounts }) => (
      platformAccounts
        .filter((account) => ATTENTION_STATES.has(getConnectionState(account)))
        .map((account) => ({ account, platform }))
    )),
    [platformModels],
  );

  const totalConnected = accounts.length;
  const connectedPlatformsCount = platformModels.filter(({ accounts: platformAccounts }) => platformAccounts.length > 0).length;
  const expiringCount = accounts.filter((account) => getConnectionState(account) === 'expiring').length;
  const reconnectCount = accounts.filter((account) => getConnectionState(account) === 'reconnect_required').length;

  if (loading) {
    return (
      <DashboardLayout>
        <div className="mx-auto max-w-6xl pb-12">
          <LoadingSkeleton />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-6xl space-y-8 pb-12">
        <section className="rounded-[32px] border border-gray-200 bg-white px-6 py-6 shadow-sm">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.22em] text-gray-400">Connections</p>
              <h1 className="mt-3 text-3xl font-semibold text-gray-900">Connected Accounts</h1>
              <p className="mt-2 max-w-2xl text-sm text-gray-600">
                Keep every channel healthy, reconnect accounts before they interrupt scheduling, and manage provider-specific setup from one place.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <a
                href="/support"
                className="inline-flex items-center justify-center rounded-full border border-gray-300 px-4 py-2 font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                Need help?
              </a>
              <button
                onClick={fetchAccounts}
                className="inline-flex items-center justify-center rounded-full bg-gray-900 px-4 py-2 font-semibold text-white transition-colors hover:bg-black"
              >
                Refresh status
              </button>
            </div>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <SummaryCard
              label="Connected"
              value={totalConnected}
              tone={totalConnected > 0 ? 'success' : 'neutral'}
              detail={`${connectedPlatformsCount} ${connectedPlatformsCount === 1 ? 'platform' : 'platforms'} active`}
            />
            <SummaryCard
              label="Needs attention"
              value={attentionAccounts.length}
              tone={attentionAccounts.length > 0 ? 'danger' : 'success'}
              detail={
                attentionAccounts.length > 0
                  ? `${reconnectCount} reconnect required${expiringCount > 0 ? ` · ${expiringCount} expiring soon` : ''}`
                  : 'All connected accounts are currently healthy'
              }
            />
            <SummaryCard
              label="Verification"
              value={verificationRequired ? 'Required' : 'Ready'}
              tone={verificationRequired ? 'warning' : 'success'}
              detail={
                verificationRequired
                  ? 'Email verification is still required before publishing, scheduling, and inviting teammates'
                  : 'Email is verified for connection and publishing actions'
              }
            />
          </div>
        </section>

        {verificationRequired ? <VerificationBanner /> : null}

        {fetchError ? (
          <div className="rounded-3xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
            {fetchError}
          </div>
        ) : null}

        {attentionAccounts.length > 0 ? (
          <section className="rounded-[32px] border border-red-200 bg-red-50/70 px-6 py-6 shadow-sm">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.22em] text-red-500">Needs attention</p>
                <h2 className="mt-2 text-xl font-semibold text-gray-900">Reconnect or review these accounts first</h2>
                <p className="mt-1 text-sm text-gray-600">
                  These accounts are expired, expiring, or restricted and may interrupt publishing until you act.
                </p>
              </div>
            </div>
            <div className="mt-5 space-y-3">
              {attentionAccounts.map(({ account, platform }) => (
                <AttentionItem
                  key={`${platform.id}-${account.id}`}
                  account={account}
                  platform={platform}
                  onReconnect={handleConnect}
                  connecting={connecting}
                />
              ))}
            </div>
          </section>
        ) : totalConnected > 0 ? (
          <section className="rounded-[32px] border border-emerald-200 bg-emerald-50 px-6 py-5 shadow-sm">
            <div className="flex items-start gap-3">
              <FaCheckCircle className="mt-0.5 text-emerald-500" />
              <div>
                <h2 className="text-lg font-semibold text-emerald-900">All connected accounts look healthy</h2>
                <p className="mt-1 text-sm text-emerald-800">
                  No reconnect work is needed right now. You can still add more accounts or refresh a provider proactively.
                </p>
              </div>
            </div>
          </section>
        ) : (
          <section className="rounded-[32px] border border-dashed border-gray-300 bg-white px-6 py-8 text-center shadow-sm">
            <h2 className="text-xl font-semibold text-gray-900">Connect your first platform</h2>
            <p className="mx-auto mt-2 max-w-2xl text-sm text-gray-600">
              Start with the channels you publish to most often. Once connected, this page will surface expiring tokens, reconnect needs, and provider restrictions automatically.
            </p>
          </section>
        )}

        <section className="space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.22em] text-gray-400">All platforms</p>
              <h2 className="mt-2 text-2xl font-semibold text-gray-900">Manage every provider connection</h2>
            </div>
            <p className="text-sm text-gray-500">
              Use reconnect for any account that expires, loses access, or needs updated credentials.
            </p>
          </div>
          <div className="grid gap-5 xl:grid-cols-2">
            {platformModels.map(({ platform, accounts: platformAccounts }) => (
              <PlatformCard
                key={platform.id}
                platform={platform}
                accounts={platformAccounts}
                onPrimaryAction={handleConnect}
                onReconnect={handleConnect}
                onDisconnect={handleDisconnect}
                connecting={connecting}
                disconnectingAccountId={disconnectingAccountId}
              />
            ))}
          </div>
        </section>

        <CredentialDialogShell
          open={manualModal.platformId === 'bluesky'}
          onOpenChange={(open) => { if (!open) closeManualModal(); }}
          icon={SiBluesky}
          iconClassName="text-lg text-sky-500"
          iconWrapClassName="border-sky-200 bg-sky-50"
          title={`${manualModal.mode === 'reconnect' ? 'Reconnect' : 'Connect'} Bluesky`}
          description={manualModal.mode === 'reconnect'
            ? 'Update the app password or handle to restore Bluesky access.'
            : 'Enter your handle and app password to connect Bluesky.'}
          footer={(
            <>
              <button
                onClick={closeManualModal}
                className="rounded-full border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleBlueskyConnect}
                disabled={blueskyLoading || !blueskyHandle.trim() || !blueskyPass.trim()}
                className="rounded-full bg-sky-500 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-sky-600 disabled:opacity-50"
              >
                {blueskyLoading ? 'Saving…' : manualModal.mode === 'reconnect' ? 'Reconnect Bluesky' : 'Connect Bluesky'}
              </button>
            </>
          )}
        >
          <div className="rounded-2xl border border-sky-100 bg-sky-50 px-4 py-3 text-sm text-sky-800">
            Use an{' '}
            <a href="https://bsky.app/settings/app-passwords" target="_blank" rel="noreferrer" className="font-semibold underline">
              App Password
            </a>{' '}
            instead of your main Bluesky password.
          </div>
          <div className="space-y-3">
            <input
              type="text"
              value={blueskyHandle}
              onChange={(event) => setBlueskyHandle(event.target.value)}
              placeholder="handle.bsky.social"
              className="w-full rounded-2xl border border-gray-200 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400"
            />
            <input
              type="password"
              value={blueskyPass}
              onChange={(event) => setBlueskyPass(event.target.value)}
              placeholder="App password (xxxx-xxxx-xxxx-xxxx)"
              className="w-full rounded-2xl border border-gray-200 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400"
              onKeyDown={(event) => { if (event.key === 'Enter') handleBlueskyConnect(); }}
            />
          </div>
        </CredentialDialogShell>

        <CredentialDialogShell
          open={manualModal.platformId === 'discord'}
          onOpenChange={(open) => { if (!open) closeManualModal(); }}
          icon={FaDiscord}
          iconClassName="text-xl text-indigo-500"
          iconWrapClassName="border-indigo-200 bg-indigo-50"
          title={`${manualModal.mode === 'reconnect' ? 'Reconnect' : 'Connect'} Discord`}
          description={manualModal.mode === 'reconnect'
            ? 'Update the webhook details for this Discord destination.'
            : 'Connect a Discord channel using an incoming webhook URL.'}
          footer={(
            <>
              <button
                onClick={closeManualModal}
                className="rounded-full border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleDiscordConnect}
                disabled={discordLoading || !discordWebhookUrl.trim()}
                className="rounded-full bg-indigo-500 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-600 disabled:opacity-50"
              >
                {discordLoading ? 'Saving…' : manualModal.mode === 'reconnect' ? 'Reconnect Discord' : 'Connect Discord'}
              </button>
            </>
          )}
        >
          <div className="rounded-2xl border border-indigo-100 bg-indigo-50 px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-indigo-800">How to get a webhook URL</p>
            <ol className="mt-2 space-y-1 text-sm text-indigo-800">
              <li>1. Open your Discord server and channel settings.</li>
              <li>2. Go to Integrations → Webhooks.</li>
              <li>3. Create or copy an incoming webhook URL for the channel.</li>
            </ol>
          </div>
          <div className="space-y-3">
            <input
              type="url"
              value={discordWebhookUrl}
              onChange={(event) => setDiscordWebhookUrl(event.target.value)}
              placeholder="https://discord.com/api/webhooks/..."
              className="w-full rounded-2xl border border-gray-200 px-4 py-3 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
            <input
              type="text"
              value={discordChannelName}
              onChange={(event) => setDiscordChannelName(event.target.value)}
              placeholder="Channel label (optional)"
              className="w-full rounded-2xl border border-gray-200 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              onKeyDown={(event) => { if (event.key === 'Enter') handleDiscordConnect(); }}
            />
          </div>
        </CredentialDialogShell>

        <CredentialDialogShell
          open={manualModal.platformId === 'mastodon'}
          onOpenChange={(open) => { if (!open) closeManualModal(); }}
          icon={SiMastodon}
          iconClassName="text-lg text-indigo-600"
          iconWrapClassName="border-indigo-200 bg-indigo-50"
          title={`${manualModal.mode === 'reconnect' ? 'Reconnect' : 'Connect'} Mastodon`}
          description={manualModal.mode === 'reconnect'
            ? 'Update the instance URL or access token to restore Mastodon access.'
            : 'Connect Mastodon with your instance URL and a personal access token.'}
          footer={(
            <>
              <button
                onClick={closeManualModal}
                className="rounded-full border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleMastodonConnect}
                disabled={mastodonLoading || !mastodonInstanceUrl.trim() || !mastodonAccessToken.trim()}
                className="rounded-full bg-indigo-600 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
              >
                {mastodonLoading ? 'Saving…' : manualModal.mode === 'reconnect' ? 'Reconnect Mastodon' : 'Connect Mastodon'}
              </button>
            </>
          )}
        >
          <div className="space-y-3">
            <div className="rounded-2xl border border-indigo-100 bg-indigo-50 px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-indigo-800">How to connect Mastodon</p>
              <ol className="mt-2 space-y-1.5 text-sm text-indigo-900">
                <li>1. Sign in to your Mastodon instance in another tab.</li>
                <li>2. Open <span className="font-medium">Preferences → Development</span> and create a new application, or open an existing one.</li>
                <li>3. Copy the app&apos;s <span className="font-medium">Your access token</span> value after saving.</li>
                <li>4. Paste your instance home URL here, such as <span className="font-mono">https://mastodon.social</span>.</li>
                <li>5. Paste the access token below and connect.</li>
              </ol>
            </div>
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <p className="font-medium">Recommended Mastodon app scopes</p>
              <p className="mt-1">
                If you are creating a new Mastodon app for Unravler, enable read access plus posting/media scopes so scheduling and publishing can work later.
              </p>
              <p className="mt-2 font-mono text-xs text-amber-950">read, read:accounts, read:statuses, write, write:media, write:statuses</p>
              <p className="mt-2 text-xs text-amber-800">
                If your instance asks for a redirect URI while creating the app, keep its default value unless your instance requires something else.
              </p>
            </div>
          </div>
          <div className="space-y-3">
            <input
              type="url"
              value={mastodonInstanceUrl}
              onChange={(event) => setMastodonInstanceUrl(event.target.value)}
              placeholder="https://mastodon.social"
              className="w-full rounded-2xl border border-gray-200 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
            <input
              type="password"
              value={mastodonAccessToken}
              onChange={(event) => setMastodonAccessToken(event.target.value)}
              placeholder="Paste your Mastodon access token"
              className="w-full rounded-2xl border border-gray-200 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              onKeyDown={(event) => { if (event.key === 'Enter') handleMastodonConnect(); }}
            />
          </div>
        </CredentialDialogShell>

        <Dialog
          open={linkedinChoiceModal.open}
          onOpenChange={(open) => {
            if (!open) setLinkedinChoiceModal({ open: false, mode: 'connect', account: null });
          }}
        >
          <DialogContent className="max-w-lg rounded-[28px]">
            <DialogHeader className="text-left">
              <DialogTitle>
                {linkedinChoiceModal.mode === 'reconnect' ? 'Reconnect LinkedIn' : 'Connect LinkedIn'}
              </DialogTitle>
              <DialogDescription>
                Choose whether this connection should publish as your member profile or as a company page you manage.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-3 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => handleLinkedInChoice('profile')}
                className="rounded-3xl border border-blue-200 bg-blue-50 p-5 text-left transition-colors hover:border-blue-400 hover:bg-blue-100"
              >
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-blue-700 shadow-sm">
                  <FaLinkedin />
                </div>
                <p className="mt-4 text-sm font-semibold text-gray-900">LinkedIn profile</p>
                <p className="mt-1 text-xs leading-5 text-gray-600">
                  Connect your personal member profile and publish as yourself.
                </p>
              </button>
              <button
                type="button"
                onClick={() => handleLinkedInChoice('organization')}
                className="rounded-3xl border border-blue-200 bg-white p-5 text-left transition-colors hover:border-blue-400 hover:bg-blue-50"
              >
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-700 text-white shadow-sm">
                  <FaPlus />
                </div>
                <p className="mt-4 text-sm font-semibold text-gray-900">LinkedIn company page</p>
                <p className="mt-1 text-xs leading-5 text-gray-600">
                  Connect one or more organization pages and publish as the page.
                </p>
              </button>
            </div>
            <div className="rounded-2xl border border-gray-200 bg-gray-50 px-4 py-3 text-xs leading-5 text-gray-600">
              Company page connection requires approved LinkedIn organization scopes on the Unravler LinkedIn app. If LinkedIn has not approved them yet, the app will show a configuration message.
            </div>
            <DialogFooter className="justify-end gap-2">
              <button
                onClick={() => setLinkedinChoiceModal({ open: false, mode: 'connect', account: null })}
                className="rounded-full border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                Cancel
              </button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={linkedinPageModal} onOpenChange={setLinkedinPageModal}>
          <DialogContent className="max-w-md rounded-[28px]">
            <DialogHeader className="text-left">
              <DialogTitle>Add LinkedIn Company Page</DialogTitle>
              <DialogDescription>Enter the page name and page ID or URL slug for the company profile you manage.</DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-gray-500">Page name</label>
                <input
                  type="text"
                  value={pageNameInput}
                  onChange={(event) => setPageNameInput(event.target.value)}
                  placeholder="Acme Corporation"
                  className="w-full rounded-2xl border border-gray-200 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-gray-500">Page ID or URL slug</label>
                <input
                  type="text"
                  value={pageIdInput}
                  onChange={(event) => setPageIdInput(event.target.value)}
                  placeholder="acme-corp or 12345678"
                  className="w-full rounded-2xl border border-gray-200 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="mt-2 text-xs text-gray-500">Find it in your page URL: linkedin.com/company/your-page-id</p>
              </div>
            </div>
            <DialogFooter className="justify-end gap-2">
              <button
                onClick={() => {
                  setLinkedinPageModal(false);
                  setPageIdInput('');
                  setPageNameInput('');
                }}
                className="rounded-full border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleAddLinkedinPage}
                disabled={addingPage || !pageIdInput.trim() || !pageNameInput.trim()}
                className="rounded-full bg-blue-700 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-800 disabled:opacity-50"
              >
                {addingPage ? 'Saving…' : 'Connect page'}
              </button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={linkedinOrgsModal} onOpenChange={setLinkedinOrgsModal}>
          <DialogContent className="max-w-md rounded-[28px]">
            <DialogHeader className="text-left">
              <DialogTitle>Connect LinkedIn Pages</DialogTitle>
              <DialogDescription>Select the company pages you want to manage from this workspace.</DialogDescription>
            </DialogHeader>
            <div className="max-h-72 space-y-2 overflow-y-auto">
              {linkedinOrgs.map((org) => (
                <label
                  key={org.org_id}
                  className="flex cursor-pointer items-center gap-3 rounded-2xl border border-gray-200 px-4 py-3 transition-colors hover:border-blue-300 hover:bg-blue-50"
                >
                  <input
                    type="checkbox"
                    checked={selectedOrgs.includes(org.org_id)}
                    onChange={() => setSelectedOrgs((previous) => (
                      previous.includes(org.org_id)
                        ? previous.filter((orgId) => orgId !== org.org_id)
                        : [...previous, org.org_id]
                    ))}
                    className="h-4 w-4 accent-blue-600"
                  />
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-100 text-sm font-semibold text-blue-700">
                    {org.name.charAt(0).toUpperCase()}
                  </div>
                  <span className="text-sm font-medium text-gray-800">{org.name}</span>
                </label>
              ))}
            </div>
            <DialogFooter className="justify-end gap-2">
              <button
                onClick={() => setLinkedinOrgsModal(false)}
                className="rounded-full border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                Skip
              </button>
              <button
                onClick={handleSaveLinkedinOrgs}
                disabled={savingOrgs || selectedOrgs.length === 0}
                className="rounded-full bg-blue-700 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-800 disabled:opacity-50"
              >
                {savingOrgs ? 'Saving…' : `Connect ${selectedOrgs.length} page${selectedOrgs.length !== 1 ? 's' : ''}`}
              </button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
};

export default ConnectedAccounts;
