import React, { useEffect, useState, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import {
  getSocialAccounts, connectSocialAccount, disconnectSocialAccount,
  connectBluesky, connectDiscord, connectMastodon, getLinkedInPendingOrgs, saveLinkedInOrgs, addLinkedInPageManually,
} from '@/lib/api';
import { clearOAuthPopupExpected, listenForOAuthResult, markOAuthPopupExpected } from '@/lib/oauthPopup';
import { requestOAuthUrl } from '@/lib/requestOAuthUrl';
import { toast } from 'sonner';
import {
  FaTwitter, FaLinkedin, FaInstagram, FaFacebook, FaYoutube,
  FaTiktok, FaPinterest, FaTimes, FaExclamationTriangle, FaClock,
  FaCheckCircle, FaPlus, FaLink, FaDiscord,
} from 'react-icons/fa';
import { SiThreads, SiReddit, SiSnapchat, SiBluesky, SiMastodon } from 'react-icons/si';
import BrandLoader from '@/components/BrandLoader';

// ── Token status helper ───────────────────────────────────────────────────────
const getTokenStatus = (account) => {
  const expiry = account.token_expiry;
  if (!expiry) return 'unknown';
  const expiryDate = new Date(expiry);
  if (isNaN(expiryDate)) return 'unknown';
  const now = new Date();
  const diffHours = (expiryDate - now) / (1000 * 60 * 60);
  if (diffHours < 0) return account.refresh_token ? 'ok' : 'expired';
  if (diffHours < 24 && !account.refresh_token) return 'expiring';
  return 'ok';
};

// ── Platform definitions ──────────────────────────────────────────────────────
const PLATFORMS = [
  { id: 'instagram',  name: 'Instagram',  icon: FaInstagram, color: 'text-pink-500',    bg: 'bg-pink-50',    border: 'border-pink-200',   ring: 'focus:ring-pink-400',   btn: 'bg-pink-500 hover:bg-pink-600' },
  { id: 'facebook',   name: 'Facebook',   icon: FaFacebook,  color: 'text-blue-600',    bg: 'bg-blue-50',    border: 'border-blue-200',   ring: 'focus:ring-blue-400',   btn: 'bg-blue-600 hover:bg-blue-700' },
  { id: 'twitter',    name: 'X (Twitter)',icon: FaTwitter,   color: 'text-sky-400',     bg: 'bg-sky-50',     border: 'border-sky-200',    ring: 'focus:ring-sky-400',    btn: 'bg-gray-900 hover:bg-black' },
  { id: 'linkedin',   name: 'LinkedIn',   icon: FaLinkedin,  color: 'text-blue-700',    bg: 'bg-blue-50',    border: 'border-blue-300',   ring: 'focus:ring-blue-500',   btn: 'bg-blue-700 hover:bg-blue-800' },
  { id: 'youtube',    name: 'YouTube',    icon: FaYoutube,   color: 'text-red-600',     bg: 'bg-red-50',     border: 'border-red-200',    ring: 'focus:ring-red-400',    btn: 'bg-red-600 hover:bg-red-700' },
  { id: 'tiktok',     name: 'TikTok',     icon: FaTiktok,    color: 'text-gray-900',    bg: 'bg-gray-50',    border: 'border-gray-300',   ring: 'focus:ring-gray-400',   btn: 'bg-gray-900 hover:bg-black' },
  { id: 'threads',    name: 'Threads',    icon: SiThreads,   color: 'text-gray-900',    bg: 'bg-gray-50',    border: 'border-gray-300',   ring: 'focus:ring-gray-400',   btn: 'bg-gray-900 hover:bg-black' },
  { id: 'pinterest',  name: 'Pinterest',  icon: FaPinterest, color: 'text-red-600',     bg: 'bg-red-50',     border: 'border-red-200',    ring: 'focus:ring-red-400',    btn: 'bg-red-600 hover:bg-red-700' },
  { id: 'reddit',     name: 'Reddit',     icon: SiReddit,    color: 'text-orange-500',  bg: 'bg-orange-50',  border: 'border-orange-200', ring: 'focus:ring-orange-400', btn: 'bg-orange-500 hover:bg-orange-600' },
  { id: 'snapchat',   name: 'Snapchat',   icon: SiSnapchat,  color: 'text-yellow-500',  bg: 'bg-yellow-50',  border: 'border-yellow-200', ring: 'focus:ring-yellow-400', btn: 'bg-yellow-400 hover:bg-yellow-500',  badge: 'Spotlight only' },
  { id: 'bluesky',    name: 'Bluesky',    icon: SiBluesky,   color: 'text-sky-500',     bg: 'bg-sky-50',     border: 'border-sky-200',    ring: 'focus:ring-sky-400',    btn: 'bg-sky-500 hover:bg-sky-600',       badge: 'App Password', credential: true },
  { id: 'discord',    name: 'Discord',    icon: FaDiscord,   color: 'text-indigo-500',  bg: 'bg-indigo-50',  border: 'border-indigo-200', ring: 'focus:ring-indigo-400', btn: 'bg-indigo-500 hover:bg-indigo-600', badge: 'Webhook',      credential: true },
  { id: 'mastodon',   name: 'Mastodon',   icon: SiMastodon,  color: 'text-indigo-600',  bg: 'bg-indigo-50',  border: 'border-indigo-200', ring: 'focus:ring-indigo-400', btn: 'bg-indigo-600 hover:bg-indigo-700', badge: 'Access token', credential: true },
];

const getAvatarColor = (username = '') => {
  const palette = ['bg-blue-500','bg-green-500','bg-yellow-500','bg-red-500','bg-purple-500','bg-pink-500','bg-indigo-500','bg-teal-500'];
  return palette[username.charCodeAt(0) % palette.length];
};

// ── Account chip — round avatar with tooltip (fixed-position, never clipped) ──
const AccountChip = ({ account, onDisconnect }) => {
  const status     = getTokenStatus(account);
  const displayName = account.platform_username || account.platform;
  const statusRing =
    status === 'expired'  ? 'ring-2 ring-red-400'    :
    status === 'expiring' ? 'ring-2 ring-yellow-400'  : '';

  const ref = useRef(null);
  const [tooltipStyle, setTooltipStyle] = useState({});
  const [showTip, setShowTip] = useState(false);

  const handleMouseEnter = () => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    // Position tooltip centered above the avatar; clamp to left edge of viewport
    const tipWidth = 180; // estimated max width
    let left = rect.left + rect.width / 2 - tipWidth / 2;
    if (left < 8) left = 8;
    if (left + tipWidth > window.innerWidth - 8) left = window.innerWidth - tipWidth - 8;
    setTooltipStyle({ top: rect.top - 8, left, transform: 'translateY(-100%)' });
    setShowTip(true);
  };

  return (
    <div
      ref={ref}
      className="relative flex-shrink-0 cursor-default"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={() => setShowTip(false)}
    >
      {/* Avatar */}
      <div className="relative">
        {account.picture_url ? (
          <img src={account.picture_url} alt={displayName}
            className={`w-10 h-10 rounded-full object-cover ${statusRing}`} />
        ) : (
          <div className={`w-10 h-10 rounded-full ${getAvatarColor(displayName)} flex items-center justify-center text-white text-sm font-bold ${statusRing}`}>
            {displayName.charAt(0).toUpperCase()}
          </div>
        )}
        {status === 'expired' && (
          <div className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-red-500 rounded-full flex items-center justify-center">
            <FaExclamationTriangle className="text-white text-[8px]" />
          </div>
        )}
        {status === 'expiring' && (
          <div className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-yellow-400 rounded-full flex items-center justify-center">
            <FaClock className="text-white text-[8px]" />
          </div>
        )}
      </div>

      {/* Fixed-position tooltip — never clipped by card overflow */}
      {showTip && (
        <div
          className="fixed z-[9999] pointer-events-auto"
          style={tooltipStyle}
        >
          <div className="bg-gray-900 text-white rounded-xl shadow-2xl px-3 py-2 flex items-center gap-2 whitespace-nowrap">
            <span className="text-xs font-medium">@{displayName}</span>
            {status === 'expired'  && <span className="text-[9px] font-bold text-red-400 uppercase">Expired</span>}
            {status === 'expiring' && <span className="text-[9px] font-bold text-yellow-400 uppercase">Expiring</span>}
            <button
              onClick={onDisconnect}
              className="ml-1 text-gray-400 hover:text-red-400 transition-colors"
              title="Disconnect"
            >
              <FaTimes className="text-[10px]" />
            </button>
          </div>
          <div className="flex justify-center">
            <div className="border-4 border-transparent border-t-gray-900" />
          </div>
        </div>
      )}
    </div>
  );
};

// ── Platform card ─────────────────────────────────────────────────────────────
const MAX_VISIBLE = 3; // avatars shown before "+N more"

const PlatformCard = ({ platform, connectedAccounts, onConnect, onDisconnect, connecting, extra }) => {
  const Icon = platform.icon;
  const count = connectedAccounts.length;
  const hasExpired  = connectedAccounts.some(a => getTokenStatus(a) === 'expired');
  const hasExpiring = connectedAccounts.some(a => getTokenStatus(a) === 'expiring');

  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  const visible  = connectedAccounts.slice(0, MAX_VISIBLE);
  const overflow = connectedAccounts.slice(MAX_VISIBLE);

  // Close dropdown on outside click
  useEffect(() => {
    if (!dropdownOpen) return;
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) setDropdownOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [dropdownOpen]);

  return (
    // No overflow-hidden — needed so fixed tooltips aren't clipped
    <div className={`relative bg-white rounded-2xl border ${hasExpired ? 'border-red-200' : hasExpiring ? 'border-yellow-200' : 'border-gray-200'} shadow-sm hover:shadow-md transition-shadow flex flex-col`}>
      {/* Card header */}
      <div className={`${platform.bg} px-4 pt-4 pb-3 border-b ${platform.border} rounded-t-2xl`}>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl ${platform.bg} border ${platform.border} flex items-center justify-center shadow-sm`}>
              <Icon className={`text-xl ${platform.color}`} />
            </div>
            <div>
              <p className="text-sm font-bold text-gray-900">{platform.name}</p>
              {platform.badge && (
                <span className="text-[10px] text-gray-500 bg-white border border-gray-200 px-1.5 py-0.5 rounded-full">{platform.badge}</span>
              )}
            </div>
          </div>
          {count > 0 && (
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${hasExpired ? 'bg-red-100 text-red-600' : hasExpiring ? 'bg-yellow-100 text-yellow-600' : 'bg-green-100 text-green-600'}`}>
              {count} connected
            </span>
          )}
        </div>
      </div>

      {/* Connected accounts */}
      <div className="px-4 py-3 flex-1 min-h-[64px]">
        {count > 0 ? (
          <div className="flex items-center gap-3 flex-wrap">
            {visible.map(account => (
              <AccountChip
                key={account.id}
                account={account}
                onDisconnect={() => onDisconnect(account.id, platform.name)}
              />
            ))}

            {/* +N more dropdown button */}
            {overflow.length > 0 && (
              <div className="relative" ref={dropdownRef}>
                <button
                  onClick={() => setDropdownOpen(v => !v)}
                  className="w-10 h-10 rounded-full bg-gray-100 hover:bg-gray-200 border-2 border-dashed border-gray-300 flex items-center justify-center text-xs font-bold text-gray-500 transition-colors"
                >
                  +{overflow.length}
                </button>

                {dropdownOpen && (
                  <div className="absolute top-full left-0 mt-2 bg-white border border-gray-200 rounded-2xl shadow-xl z-50 min-w-[200px] py-2">
                    <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest px-3 pb-1.5 border-b border-gray-100 mb-1">
                      More accounts
                    </p>
                    {overflow.map(account => {
                      const name = account.platform_username || account.platform;
                      const status = getTokenStatus(account);
                      return (
                        <div key={account.id} className="flex items-center gap-2.5 px-3 py-2 hover:bg-gray-50 transition-colors">
                          {account.picture_url ? (
                            <img src={account.picture_url} alt={name} className="w-7 h-7 rounded-full object-cover flex-shrink-0" />
                          ) : (
                            <div className={`w-7 h-7 rounded-full ${getAvatarColor(name)} flex items-center justify-center text-white text-xs font-bold flex-shrink-0`}>
                              {name.charAt(0).toUpperCase()}
                            </div>
                          )}
                          <span className="text-xs text-gray-800 font-medium flex-1 truncate">@{name}</span>
                          {status === 'expired'  && <span className="text-[9px] font-bold text-red-500 uppercase">Expired</span>}
                          {status === 'expiring' && <span className="text-[9px] font-bold text-yellow-500 uppercase">Soon</span>}
                          <button
                            onClick={() => { onDisconnect(account.id, platform.name); setDropdownOpen(false); }}
                            className="text-gray-300 hover:text-red-400 transition-colors flex-shrink-0"
                            title="Disconnect"
                          >
                            <FaTimes className="text-[10px]" />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {extra}
          </div>
        ) : (
          <p className="text-xs text-gray-400 italic">No accounts connected</p>
        )}
      </div>

      {/* Connect button */}
      <div className="px-4 pb-4">
        <button
          onClick={() => onConnect(platform.id)}
          disabled={connecting === platform.id}
          className={`w-full flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-white transition-colors disabled:opacity-60 ${platform.btn}`}
        >
          {connecting === platform.id ? (
            <span className="animate-spin inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full" />
          ) : (
            <FaPlus className="text-[10px]" />
          )}
          {connecting === platform.id ? 'Connecting…' : count > 0 ? `Add ${platform.name}` : `Connect ${platform.name}`}
        </button>
      </div>
    </div>
  );
};

// ── Main page ─────────────────────────────────────────────────────────────────
const ConnectedAccounts = () => {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(null);

  // Bluesky modal
  const [blueskyModal, setBlueskyModal] = useState(false);
  const [blueskyHandle, setBlueskyHandle] = useState('');
  const [blueskyPass, setBlueskyPass] = useState('');
  const [blueskyLoading, setBlueskyLoading] = useState(false);

  // Discord modal
  const [discordModal, setDiscordModal] = useState(false);
  const [discordWebhookUrl, setDiscordWebhookUrl] = useState('');
  const [discordChannelName, setDiscordChannelName] = useState('');
  const [discordLoading, setDiscordLoading] = useState(false);
  const [mastodonModal, setMastodonModal] = useState(false);
  const [mastodonInstanceUrl, setMastodonInstanceUrl] = useState('');
  const [mastodonAccessToken, setMastodonAccessToken] = useState('');
  const [mastodonLoading, setMastodonLoading] = useState(false);

  // LinkedIn modals
  const [linkedinOrgsModal, setLinkedinOrgsModal] = useState(false);
  const [linkedinOrgs, setLinkedinOrgs] = useState([]);
  const [selectedOrgs, setSelectedOrgs] = useState([]);
  const [savingOrgs, setSavingOrgs] = useState(false);
  const [linkedinPageModal, setLinkedinPageModal] = useState(false);
  const [pageIdInput, setPageIdInput] = useState('');
  const [pageNameInput, setPageNameInput] = useState('');
  const [addingPage, setAddingPage] = useState(false);

  const [searchParams] = useSearchParams();

  useEffect(() => { fetchAccounts(); }, []);

  useEffect(() => {
    return listenForOAuthResult((message) => {
      if (!message || message.returnTo !== 'accounts') return;

      clearOAuthPopupExpected();
      setConnecting(null);

      if (message.status === 'success') {
        toast.success(`${message.platform || 'Account'} connected successfully!`);
        fetchAccounts();
      } else if (message.status === 'error') {
        toast.error(message.error || 'Failed to connect account');
      }
    });
  }, []);

  useEffect(() => {
    if (searchParams.get('linkedin_orgs') === '1') {
      if (searchParams.get('personal_connected') === 'true') toast.success('LinkedIn personal account connected!');
      fetchAccounts();
      getLinkedInPendingOrgs().then((data) => {
        if (data.orgs?.length > 0) {
          setLinkedinOrgs(data.orgs);
          setSelectedOrgs(data.orgs.map(o => o.org_id));
          setLinkedinOrgsModal(true);
        }
      }).catch(() => {});
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
      const data = await getSocialAccounts();
      setAccounts(data);
    } catch {
      toast.error('Failed to load accounts');
    } finally {
      setLoading(false);
    }
  };

  const handleConnect = async (platformId) => {
    if (platformId === 'bluesky') { setBlueskyModal(true); return; }
    if (platformId === 'discord') { setDiscordModal(true); return; }
    if (platformId === 'mastodon') { setMastodonModal(true); return; }

    setConnecting(platformId);
    // Open a popup synchronously so browsers don't block it.
    const popup = window.open('', '_blank', 'noopener,noreferrer');
    if (popup) popup.opener = null;
    markOAuthPopupExpected(Boolean(popup));
    try {
      const token = localStorage.getItem('token');
      const oauthPlatforms = ['facebook','instagram','youtube','twitter','linkedin','threads','reddit','pinterest','snapchat','tiktok'];

      if (oauthPlatforms.includes(platformId)) {
        const { authorization_url, code_verifier } = await requestOAuthUrl(platformId, token);
        if (code_verifier) sessionStorage.setItem('twitter_code_verifier', code_verifier);
        sessionStorage.setItem('oauth_platform', platformId);
        sessionStorage.setItem('oauth_return_to', 'accounts');
        if (popup) {
          popup.location.href = authorization_url;
        } else {
          window.location.assign(authorization_url);
        }
        return;
      }
    } catch (error) {
      clearOAuthPopupExpected();
      if (popup) popup.close();
      if (error.response?.status === 500 && error.response?.data?.detail?.includes('not configured')) {
        toast.error('API credentials not configured for this platform.');
      } else {
        toast.error(error.response?.data?.detail || 'Failed to connect account');
      }
    } finally {
      setConnecting(null);
    }
  };

  const handleDisconnect = async (accountId, platformName) => {
    if (!window.confirm(`Disconnect your ${platformName} account? This cannot be undone.`)) return;
    try {
      await disconnectSocialAccount(accountId);
      setAccounts(prev => prev.filter(a => a.id !== accountId));
      toast.success(`${platformName} account disconnected`);
    } catch {
      toast.error('Failed to disconnect account');
    }
  };

  const handleBlueskyConnect = async () => {
    if (!blueskyHandle.trim() || !blueskyPass.trim()) return;
    setBlueskyLoading(true);
    try {
      await connectBluesky({ handle: blueskyHandle.trim(), app_password: blueskyPass.trim() });
      toast.success('Bluesky account connected!');
      setBlueskyModal(false);
      setBlueskyHandle(''); setBlueskyPass('');
      fetchAccounts();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to connect Bluesky');
    } finally {
      setBlueskyLoading(false);
    }
  };

  const handleDiscordConnect = async () => {
    if (!discordWebhookUrl.trim()) return;
    setDiscordLoading(true);
    try {
      const res = await connectDiscord(discordWebhookUrl.trim(), discordChannelName.trim() || null);
      toast.success(`Discord channel "${res.channel}" connected!`);
      setDiscordModal(false);
      setDiscordWebhookUrl(''); setDiscordChannelName('');
      fetchAccounts();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Invalid webhook URL. Make sure it is a valid Discord webhook.');
    } finally {
      setDiscordLoading(false);
    }
  };

  const handleMastodonConnect = async () => {
    if (!mastodonInstanceUrl.trim() || !mastodonAccessToken.trim()) return;
    setMastodonLoading(true);
    try {
      const res = await connectMastodon(mastodonInstanceUrl.trim(), mastodonAccessToken.trim());
      toast.success(`Mastodon account "${res.username}" connected!`);
      setMastodonModal(false);
      setMastodonInstanceUrl('');
      setMastodonAccessToken('');
      fetchAccounts();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to connect Mastodon');
    } finally {
      setMastodonLoading(false);
    }
  };

  const handleAddLinkedinPage = async () => {
    if (!pageIdInput.trim() || !pageNameInput.trim()) return;
    setAddingPage(true);
    try {
      await addLinkedInPageManually(pageIdInput.trim(), pageNameInput.trim());
      toast.success(`LinkedIn page "${pageNameInput}" connected!`);
      setLinkedinPageModal(false); setPageIdInput(''); setPageNameInput('');
      fetchAccounts();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to add LinkedIn page');
    } finally {
      setAddingPage(false);
    }
  };

  const handleSaveLinkedinOrgs = async () => {
    setSavingOrgs(true);
    try {
      const result = await saveLinkedInOrgs(selectedOrgs);
      toast.success(`${result.saved} LinkedIn page${result.saved !== 1 ? 's' : ''} connected!`);
      setLinkedinOrgsModal(false);
      fetchAccounts();
    } catch {
      toast.error('Failed to connect LinkedIn pages');
    } finally {
      setSavingOrgs(false);
    }
  };

  const getAccountsByPlatform = (id) => accounts.filter(a => a.platform === id);

  const totalConnected = accounts.length;
  const expiredCount = accounts.filter(a => getTokenStatus(a) === 'expired').length;

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center min-h-[60vh]">
          <BrandLoader />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="max-w-5xl mx-auto pb-12">

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Connected Accounts</h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage your social accounts and channels. Connect as many as you need.
          </p>
          {totalConnected > 0 && (
            <div className="flex items-center gap-4 mt-3">
              <span className="flex items-center gap-1.5 text-sm text-green-700 font-medium">
                <FaCheckCircle className="text-green-500" /> {totalConnected} account{totalConnected !== 1 ? 's' : ''} connected
              </span>
              {expiredCount > 0 && (
                <span className="flex items-center gap-1.5 text-sm text-red-600 font-medium">
                  <FaExclamationTriangle className="text-red-500" /> {expiredCount} expired — reconnect required
                </span>
              )}
            </div>
          )}
        </div>

        {/* Expired token banner */}
        {expiredCount > 0 && (
          <div className="mb-6 flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
            <FaExclamationTriangle className="text-red-500 mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-semibold text-red-700">One or more platform tokens have expired</p>
              <p className="text-xs text-red-500 mt-0.5">
                Click <strong>Connect</strong> on the expired platform to re-authenticate.
              </p>
            </div>
          </div>
        )}

        {/* Platform grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {PLATFORMS.map((platform) => {
            const connected = getAccountsByPlatform(platform.id);
            const extra = platform.id === 'linkedin' && connected.length > 0 ? (
              <button
                onClick={() => setLinkedinPageModal(true)}
                className="flex items-center gap-1 text-[10px] text-blue-700 hover:text-blue-800 bg-blue-50 hover:bg-blue-100 border border-blue-200 px-2 py-1 rounded-full transition-colors"
              >
                <FaLinkedin className="text-[9px]" /> + Company Page
              </button>
            ) : null;

            return (
              <PlatformCard
                key={platform.id}
                platform={platform}
                connectedAccounts={connected}
                onConnect={handleConnect}
                onDisconnect={handleDisconnect}
                connecting={connecting}
                extra={extra}
              />
            );
          })}
        </div>

        {/* Help */}
        <div className="mt-8 pt-6 border-t border-gray-200">
          <a href="/support" className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 w-fit">
            <span className="w-4 h-4 rounded-full border border-gray-400 flex items-center justify-center text-xs font-bold">i</span>
            Need help connecting an account?
          </a>
        </div>
      </div>

      {/* ── Bluesky Modal ──────────────────────────────────────────────────── */}
      {blueskyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-sky-50 border border-sky-200 flex items-center justify-center">
                <SiBluesky className="text-sky-500 text-lg" />
              </div>
              <div>
                <h2 className="text-base font-bold text-gray-900">Connect Bluesky</h2>
                <p className="text-xs text-gray-500">Enter your handle and app password</p>
              </div>
            </div>
            <p className="text-xs text-gray-500 mb-4 bg-sky-50 border border-sky-100 rounded-lg px-3 py-2">
              Use an{' '}
              <a href="https://bsky.app/settings/app-passwords" target="_blank" rel="noreferrer" className="text-sky-600 hover:underline font-medium">
                App Password
              </a>
              {' '}— not your main Bluesky password.
            </p>
            <div className="space-y-3 mb-5">
              <input type="text" value={blueskyHandle} onChange={e => setBlueskyHandle(e.target.value)}
                placeholder="handle.bsky.social"
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400" />
              <input type="password" value={blueskyPass} onChange={e => setBlueskyPass(e.target.value)}
                placeholder="App password (xxxx-xxxx-xxxx-xxxx)"
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400"
                onKeyDown={e => { if (e.key === 'Enter') handleBlueskyConnect(); }} />
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => { setBlueskyModal(false); setBlueskyHandle(''); setBlueskyPass(''); }}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-xl transition-colors">Cancel</button>
              <button onClick={handleBlueskyConnect}
                disabled={blueskyLoading || !blueskyHandle.trim() || !blueskyPass.trim()}
                className="px-5 py-2 text-sm font-semibold bg-sky-500 hover:bg-sky-600 text-white rounded-xl disabled:opacity-50 transition-colors">
                {blueskyLoading ? 'Connecting…' : 'Connect'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Discord Modal ──────────────────────────────────────────────────── */}
      {discordModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-200 flex items-center justify-center">
                <FaDiscord className="text-indigo-500 text-xl" />
              </div>
              <div>
                <h2 className="text-base font-bold text-gray-900">Connect Discord Channel</h2>
                <p className="text-xs text-gray-500">Via an incoming webhook URL</p>
              </div>
            </div>

            {/* How to steps */}
            <div className="bg-indigo-50 border border-indigo-100 rounded-xl px-4 py-3 mb-4">
              <p className="text-xs font-semibold text-indigo-700 mb-2">How to get a webhook URL:</p>
              <ol className="space-y-1 text-xs text-indigo-700">
                {[
                  'Open your Discord server → right-click the channel',
                  'Go to Edit Channel → Integrations → Webhooks',
                  'Click "New Webhook", name it, then Copy Webhook URL',
                ].map((step, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="w-4 h-4 rounded-full bg-indigo-200 text-indigo-800 text-[9px] font-bold flex items-center justify-center shrink-0 mt-0.5">{i + 1}</span>
                    {step}
                  </li>
                ))}
              </ol>
            </div>

            <div className="space-y-3 mb-5">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Webhook URL <span className="text-red-500">*</span></label>
                <input type="url" value={discordWebhookUrl} onChange={e => setDiscordWebhookUrl(e.target.value)}
                  placeholder="https://discord.com/api/webhooks/..."
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 font-mono" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Channel Label <span className="text-gray-400">(optional)</span></label>
                <input type="text" value={discordChannelName} onChange={e => setDiscordChannelName(e.target.value)}
                  placeholder="e.g. #announcements"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  onKeyDown={e => { if (e.key === 'Enter') handleDiscordConnect(); }} />
              </div>
            </div>

            <div className="flex gap-2 justify-end">
              <button onClick={() => { setDiscordModal(false); setDiscordWebhookUrl(''); setDiscordChannelName(''); }}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-xl transition-colors">Cancel</button>
              <button onClick={handleDiscordConnect}
                disabled={discordLoading || !discordWebhookUrl.trim()}
                className="px-5 py-2 text-sm font-semibold bg-indigo-500 hover:bg-indigo-600 text-white rounded-xl disabled:opacity-50 transition-colors flex items-center gap-2">
                {discordLoading && <span className="animate-spin w-3 h-3 border-2 border-white border-t-transparent rounded-full" />}
                {discordLoading ? 'Validating…' : 'Connect Channel'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Mastodon Modal ────────────────────────────────────────────────── */}
      {mastodonModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-200 flex items-center justify-center">
                <SiMastodon className="text-indigo-600 text-lg" />
              </div>
              <div>
                <h2 className="text-base font-bold text-gray-900">Connect Mastodon</h2>
                <p className="text-xs text-gray-500">Use your instance URL and a personal access token</p>
              </div>
            </div>
            <div className="bg-indigo-50 border border-indigo-100 rounded-xl px-4 py-3 mb-4">
              <p className="text-xs text-gray-700">
                Create a personal access token from your Mastodon instance settings, then paste the
                instance URL and token here. We&apos;ll validate the account before saving it.
              </p>
            </div>
            <div className="space-y-3 mb-5">
              <input
                type="url"
                value={mastodonInstanceUrl}
                onChange={e => setMastodonInstanceUrl(e.target.value)}
                placeholder="https://mastodon.social"
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
              <input
                type="password"
                value={mastodonAccessToken}
                onChange={e => setMastodonAccessToken(e.target.value)}
                placeholder="Paste your Mastodon access token"
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                onKeyDown={e => { if (e.key === 'Enter') handleMastodonConnect(); }}
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => {
                  setMastodonModal(false);
                  setMastodonInstanceUrl('');
                  setMastodonAccessToken('');
                }}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-xl transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleMastodonConnect}
                disabled={mastodonLoading || !mastodonInstanceUrl.trim() || !mastodonAccessToken.trim()}
                className="px-5 py-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl disabled:opacity-50 transition-colors"
              >
                {mastodonLoading ? 'Connecting…' : 'Connect'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── LinkedIn Manual Page Modal ─────────────────────────────────────── */}
      {linkedinPageModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl bg-blue-50 border border-blue-200 flex items-center justify-center">
                <FaLinkedin className="text-blue-700 text-xl" />
              </div>
              <div>
                <h2 className="text-base font-bold text-gray-900">Add LinkedIn Company Page</h2>
                <p className="text-xs text-gray-500">Enter your company page details</p>
              </div>
            </div>
            <div className="space-y-4 mb-5">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Page Name</label>
                <input type="text" value={pageNameInput} onChange={e => setPageNameInput(e.target.value)}
                  placeholder="e.g. Acme Corporation"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">Page ID or URL slug</label>
                <input type="text" value={pageIdInput} onChange={e => setPageIdInput(e.target.value)}
                  placeholder="e.g. acme-corp or 12345678"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                <p className="text-[11px] text-gray-400 mt-1.5">Find it in your page URL: linkedin.com/company/<strong>your-page-id</strong></p>
              </div>
            </div>
            <div className="flex gap-3 justify-end">
              <button onClick={() => { setLinkedinPageModal(false); setPageIdInput(''); setPageNameInput(''); }}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 border border-gray-200 rounded-xl transition-colors">Cancel</button>
              <button onClick={handleAddLinkedinPage}
                disabled={addingPage || !pageIdInput.trim() || !pageNameInput.trim()}
                className="px-5 py-2 text-sm font-semibold bg-blue-700 text-white rounded-xl hover:bg-blue-800 disabled:opacity-50 transition-colors">
                {addingPage ? 'Connecting…' : 'Connect Page'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── LinkedIn Orgs Selection Modal ──────────────────────────────────── */}
      {linkedinOrgsModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-blue-50 border border-blue-200 flex items-center justify-center">
                <FaLinkedin className="text-blue-700 text-xl" />
              </div>
              <div>
                <h2 className="text-base font-bold text-gray-900">Connect LinkedIn Pages</h2>
                <p className="text-xs text-gray-500">Select company pages to manage</p>
              </div>
            </div>
            <div className="space-y-2 max-h-64 overflow-y-auto mb-5">
              {linkedinOrgs.map(org => (
                <label key={org.org_id} className="flex items-center gap-3 p-3 rounded-xl border border-gray-200 hover:border-blue-300 hover:bg-blue-50 cursor-pointer transition-colors">
                  <input type="checkbox" checked={selectedOrgs.includes(org.org_id)}
                    onChange={() => setSelectedOrgs(prev => prev.includes(org.org_id) ? prev.filter(id => id !== org.org_id) : [...prev, org.org_id])}
                    className="w-4 h-4 accent-blue-600" />
                  <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center text-blue-700 font-bold text-sm shrink-0">
                    {org.name.charAt(0).toUpperCase()}
                  </div>
                  <span className="font-medium text-gray-800 text-sm">{org.name}</span>
                </label>
              ))}
            </div>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setLinkedinOrgsModal(false)} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 border border-gray-200 rounded-xl transition-colors">Skip</button>
              <button onClick={handleSaveLinkedinOrgs}
                disabled={savingOrgs || selectedOrgs.length === 0}
                className="px-5 py-2 text-sm font-semibold bg-blue-700 text-white rounded-xl hover:bg-blue-800 disabled:opacity-50 transition-colors">
                {savingOrgs ? 'Connecting…' : `Connect ${selectedOrgs.length} Page${selectedOrgs.length !== 1 ? 's' : ''}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
};

export default ConnectedAccounts;
