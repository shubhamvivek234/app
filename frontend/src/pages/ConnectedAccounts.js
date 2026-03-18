import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';
import DashboardLayout from '@/components/DashboardLayout';
import { getSocialAccounts, connectSocialAccount, disconnectSocialAccount, connectBluesky, getLinkedInPendingOrgs, saveLinkedInOrgs, addLinkedInPageManually } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import {
  FaTwitter,
  FaLinkedin,
  FaInstagram,
  FaFacebook,
  FaYoutube,
  FaTiktok,
  FaPinterest,
  FaTimes,
  FaFilter,
  FaExclamationTriangle,
  FaClock,
  FaCheckCircle,
} from 'react-icons/fa';

// Returns 'expired' | 'expiring' | 'ok' | 'unknown'
const getTokenStatus = (account) => {
  const expiry = account.token_expiry;
  if (!expiry) return 'unknown';
  const expiryDate = new Date(expiry);
  if (isNaN(expiryDate)) return 'unknown';
  const now = new Date();
  const diffHours = (expiryDate - now) / (1000 * 60 * 60);
  if (diffHours < 0) {
    // Even if expired, if there's a refresh_token the backend can auto-refresh
    return account.refresh_token ? 'ok' : 'expired';
  }
  // Show 'expiring' only if under 24h AND no refresh_token to auto-heal it
  // (Twitter tokens are always 2h but auto-refresh on load — don't alarm user)
  if (diffHours < 24 && !account.refresh_token) return 'expiring';
  return 'ok';
};
import { SiThreads, SiReddit, SiSnapchat, SiBluesky } from 'react-icons/si';

const ConnectedAccounts = () => {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(null);
  const [blueskyModal, setBlueskyModal] = useState(false);
  const [blueskyHandle, setBlueskyHandle] = useState('');
  const [blueskyPass, setBlueskyPass] = useState('');
  const [blueskyLoading, setBlueskyLoading] = useState(false);

  // LinkedIn Pages modal state (auto, from OAuth)
  const [linkedinOrgsModal, setLinkedinOrgsModal] = useState(false);
  const [linkedinOrgs, setLinkedinOrgs] = useState([]);
  const [selectedOrgs, setSelectedOrgs] = useState([]);
  const [savingOrgs, setSavingOrgs] = useState(false);

  // LinkedIn manual page-add modal
  const [linkedinPageModal, setLinkedinPageModal] = useState(false);
  const [pageIdInput, setPageIdInput] = useState('');
  const [pageNameInput, setPageNameInput] = useState('');
  const [addingPage, setAddingPage] = useState(false);

  // Platform definitions
  const platforms = [
    {
      id: 'facebook',
      name: 'Facebook',
      icon: FaFacebook,
      color: 'text-blue-600',
      buttonBg: 'bg-gray-900 hover:bg-gray-800'
    },
    {
      id: 'instagram',
      name: 'Instagram',
      icon: FaInstagram,
      color: 'text-pink-500',
      buttonBg: 'bg-gray-900 hover:bg-gray-800'
    },
    {
      id: 'linkedin',
      name: 'LinkedIn',
      icon: FaLinkedin,
      color: 'text-blue-700',
      buttonBg: 'bg-gray-900 hover:bg-gray-800'
    },
    {
      id: 'tiktok',
      name: 'TikTok',
      icon: FaTiktok,
      color: 'text-gray-900',
      buttonBg: 'bg-gray-900 hover:bg-gray-800'
    },
    {
      id: 'twitter',
      name: 'Twitter',
      icon: FaTwitter,
      color: 'text-blue-400',
      buttonBg: 'bg-gray-900 hover:bg-gray-800'
    },
    {
      id: 'youtube',
      name: 'Youtube',
      icon: FaYoutube,
      color: 'text-red-600',
      buttonBg: 'bg-gray-900 hover:bg-gray-800'
    },
    {
      id: 'threads',
      name: 'Threads',
      icon: SiThreads,
      color: 'text-gray-900',
      buttonBg: 'bg-gray-900 hover:bg-gray-800'
    },
    {
      id: 'pinterest',
      name: 'Pinterest',
      icon: FaPinterest,
      color: 'text-red-600',
      buttonBg: 'bg-red-600 hover:bg-red-700'
    },
    {
      id: 'reddit',
      name: 'Reddit',
      icon: SiReddit,
      color: 'text-orange-500',
      buttonBg: 'bg-orange-500 hover:bg-orange-600'
    },
    {
      id: 'snapchat',
      name: 'Snapchat',
      icon: SiSnapchat,
      color: 'text-yellow-400',
      buttonBg: 'bg-yellow-400 hover:bg-yellow-500',
      badge: 'Spotlight only',
    },
    {
      id: 'bluesky',
      name: 'Bluesky',
      icon: SiBluesky,
      color: 'text-sky-500',
      buttonBg: 'bg-sky-500 hover:bg-sky-600',
      badge: 'App password',
    },
  ];

  const [searchParams] = useSearchParams();

  useEffect(() => {
    fetchAccounts();
  }, []);

  // After OAuth redirect, refresh accounts and show success message
  useEffect(() => {
    if (searchParams.get('linkedin_orgs') === '1') {
      // Personal LinkedIn account saved — now offer pages selection
      if (searchParams.get('personal_connected') === 'true') {
        toast.success('LinkedIn personal account connected!');
      }
      fetchAccounts();
      getLinkedInPendingOrgs()
        .then((data) => {
          if (data.orgs && data.orgs.length > 0) {
            setLinkedinOrgs(data.orgs);
            setSelectedOrgs(data.orgs.map((o) => o.org_id)); // pre-select all
            setLinkedinOrgsModal(true);
          }
        })
        .catch(() => {});
    } else if (searchParams.get('connected') === 'true') {
      const platforms = searchParams.get('platforms') || 'account';
      toast.success(`Successfully connected: ${platforms}`);
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
    } catch (error) {
      toast.error('Failed to load accounts');
    } finally {
      setLoading(false);
    }
  };

  const handleAddLinkedinPage = async () => {
    if (!pageIdInput.trim() || !pageNameInput.trim()) return;
    setAddingPage(true);
    try {
      await addLinkedInPageManually(pageIdInput.trim(), pageNameInput.trim());
      toast.success(`LinkedIn page "${pageNameInput}" connected!`);
      setLinkedinPageModal(false);
      setPageIdInput('');
      setPageNameInput('');
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

  const handleBlueskyConnect = async () => {
    if (!blueskyHandle.trim() || !blueskyPass.trim()) return;
    setBlueskyLoading(true);
    try {
      await connectBluesky(blueskyHandle.trim(), blueskyPass.trim());
      toast.success('Bluesky account connected!');
      setBlueskyModal(false);
      setBlueskyHandle('');
      setBlueskyPass('');
      fetchAccounts();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to connect Bluesky');
    } finally {
      setBlueskyLoading(false);
    }
  };

  const handleConnect = async (platformId) => {
    setConnecting(platformId);
    try {
      const token = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_BACKEND_URL || '';

      // Bluesky uses custom modal (not redirect OAuth)
      if (platformId === 'bluesky') {
        setBlueskyModal(true);
        setConnecting(null);
        return;
      }

      // Use real OAuth for integrated platforms
      if (['facebook', 'instagram', 'youtube', 'twitter', 'linkedin', 'threads', 'reddit', 'pinterest', 'snapchat', 'tiktok'].includes(platformId)) {
        // 1. Get Auth URL from backend
        const authResponse = await axios.get(
          `${apiUrl}/api/oauth/${platformId}/authorize`,
          {
            headers: { Authorization: `Bearer ${token}` },
            withCredentials: true,
          }
        );

        const { authorization_url, code_verifier } = authResponse.data;

        if (code_verifier) {
          sessionStorage.setItem('twitter_code_verifier', code_verifier);
        }

        // Store platform info for callback so it redirects back here
        sessionStorage.setItem('oauth_platform', platformId);
        sessionStorage.setItem('oauth_return_to', 'accounts');

        // 2. Redirect user to authorization page
        window.location.href = authorization_url;
        return;
      }

      // Generate a mock username for demo (for other non-integrated platforms like tiktok/linkedin)
      const platform = platforms.find(p => p.id === platformId);
      const mockUsername = `@user_${Date.now().toString(36)}`;

      await connectSocialAccount(platformId, mockUsername);
      toast.success(`${platform.name} mock account connected!`);
      fetchAccounts();
    } catch (error) {
      console.error('Connect error:', error);
      if (error.response?.status === 500 && error.response?.data?.detail?.includes('not configured')) {
        toast.error(`API credentials not configured for this platform.`);
      } else {
        toast.error(error.response?.data?.detail || 'Failed to connect account');
      }
    } finally {
      setConnecting(null);
    }
  };

  const handleDisconnect = async (accountId, platform) => {
    try {
      await disconnectSocialAccount(accountId);
      setAccounts(accounts.filter((a) => a.id !== accountId));
      toast.success(`${platform} account disconnected`);
    } catch (error) {
      toast.error('Failed to disconnect account');
    }
  };

  const handleRefresh = (platform) => {
    toast.success(`${platform} connections refreshed`);
  };

  // Get accounts by platform
  const getAccountsByPlatform = (platformId) => {
    return accounts.filter(a => a.platform === platformId);
  };

  // Generate avatar colors based on username
  const getAvatarColor = (username) => {
    const colors = [
      'bg-blue-500', 'bg-green-500', 'bg-yellow-500', 'bg-red-500',
      'bg-purple-500', 'bg-pink-500', 'bg-indigo-500', 'bg-teal-500'
    ];
    const index = username.charCodeAt(0) % colors.length;
    return colors[index];
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-gray-600">Loading accounts...</div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Connected Accounts</h1>
          <button className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900">
            <span>all accounts</span>
            <FaFilter className="text-xs" />
          </button>
        </div>

        {/* Expired token banner */}
        {accounts.some(a => getTokenStatus(a) === 'expired') && (
          <div className="mb-4 flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
            <FaExclamationTriangle className="text-red-500 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-sm font-semibold text-red-700">One or more platform tokens have expired</p>
              <p className="text-xs text-red-500 mt-0.5">
                Expired accounts are shown in red below. Click <strong>Connect</strong> next to the platform to re-authenticate.
              </p>
            </div>
          </div>
        )}
        {accounts.some(a => getTokenStatus(a) === 'expiring') && !accounts.some(a => getTokenStatus(a) === 'expired') && (
          <div className="mb-4 flex items-start gap-3 bg-yellow-50 border border-yellow-200 rounded-xl px-4 py-3">
            <FaClock className="text-yellow-500 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-yellow-700">
              Some platform tokens are expiring within 24 hours. Consider reconnecting them soon.
            </p>
          </div>
        )}

        {/* Platform Rows */}
        <div className="space-y-4">
          {platforms.map((platform) => {
            const Icon = platform.icon;
            const connectedAccounts = getAccountsByPlatform(platform.id);

            return (
              <div key={platform.id} className="flex items-center gap-4 py-2">
                {/* Platform Icon */}
                <div className="w-8 h-8 flex items-center justify-center">
                  <Icon className={`text-2xl ${platform.color}`} />
                </div>

                {/* Connect Button + optional badge */}
                <div className="flex flex-col gap-0.5">
                  <Button
                    onClick={() => handleConnect(platform.id)}
                    disabled={connecting === platform.id}
                    className={`${platform.buttonBg} text-white min-w-[160px]`}
                    data-testid={`connect-${platform.id}`}
                  >
                    {connecting === platform.id ? 'Connecting...' : `Connect ${platform.name}`}
                  </Button>
                  {platform.badge && (
                    <span className="text-[10px] text-gray-400 pl-1">{platform.badge}</span>
                  )}
                </div>

                {/* Connected Account Tags */}
                <div className="flex flex-wrap items-center gap-2">
                  {connectedAccounts.map((account) => {
                    const tokenStatus = getTokenStatus(account);
                    return (
                    <div
                      key={account.id}
                      className={`flex items-center gap-1.5 bg-white border rounded-full px-2 py-1 text-sm shadow-sm ${
                        tokenStatus === 'expired'  ? 'border-red-300 bg-red-50' :
                        tokenStatus === 'expiring' ? 'border-yellow-300 bg-yellow-50' :
                        'border-gray-200'
                      }`}
                      data-testid={`account-tag-${account.id}`}
                      title={
                        tokenStatus === 'expired'  ? 'Token expired — please reconnect' :
                        tokenStatus === 'expiring' ? 'Token expiring soon — reconnect recommended' :
                        tokenStatus === 'ok'       ? 'Connected and active' : ''
                      }
                    >
                      {/* Token Status Icon */}
                      {tokenStatus === 'expired' && (
                        <FaExclamationTriangle className="text-red-500 text-[10px] flex-shrink-0" />
                      )}
                      {tokenStatus === 'expiring' && (
                        <FaClock className="text-yellow-500 text-[10px] flex-shrink-0" />
                      )}
                      {/* Avatar */}
                      {account.picture_url ? (
                        <img
                          src={account.picture_url}
                          alt={account.platform_username}
                          className="w-5 h-5 rounded-full object-cover"
                        />
                      ) : (
                        <div className={`w-5 h-5 rounded-full ${getAvatarColor(account.platform_username)} flex items-center justify-center text-white text-xs`}>
                          {account.platform_username?.charAt(0)?.toUpperCase() || 'U'}
                        </div>
                      )}
                      {/* Username */}
                      <span className={`font-medium ${
                        tokenStatus === 'expired'  ? 'text-red-700' :
                        tokenStatus === 'expiring' ? 'text-yellow-700' :
                        'text-gray-800'
                      }`}>{account.platform_username}</span>
                      {/* Expired label */}
                      {tokenStatus === 'expired' && (
                        <span className="text-[9px] font-bold text-red-500 uppercase tracking-wide">Expired</span>
                      )}
                      {tokenStatus === 'expiring' && (
                        <span className="text-[9px] font-bold text-yellow-600 uppercase tracking-wide">Expiring</span>
                      )}
                      {/* Close Button */}
                      <button
                        onClick={() => handleDisconnect(account.id, platform.name)}
                        className="text-red-400 hover:text-red-600 ml-1"
                        data-testid={`disconnect-${account.id}`}
                      >
                        <FaTimes className="text-xs" />
                      </button>
                    </div>
                    );
                  })}

                  {/* Add Company Page button — only for LinkedIn */}
                  {platform.id === 'linkedin' && connectedAccounts.length > 0 && (
                    <button
                      onClick={() => setLinkedinPageModal(true)}
                      className="flex items-center gap-1.5 text-xs text-blue-700 hover:text-blue-800 bg-blue-50 hover:bg-blue-100 border border-blue-200 px-2.5 py-1.5 rounded-lg transition-colors mt-1"
                    >
                      <FaLinkedin className="text-[11px]" />
                      + Add Company Page
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Refresh Buttons */}
        <div className="mt-8 pt-6 border-t border-gray-200">
          <div className="flex flex-wrap gap-3">
            {['Instagram', 'Twitter', 'TikTok', 'Facebook'].map((platform) => (
              <Button
                key={platform}
                variant="outline"
                onClick={() => handleRefresh(platform)}
                className="text-gray-700 border-gray-300 hover:bg-gray-50"
                data-testid={`refresh-${platform.toLowerCase()}`}
              >
                Refresh {platform}
              </Button>
            ))}
          </div>
        </div>

        {/* Help Link */}
        <div className="mt-6">
          <a
            href="/support"
            className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
          >
            <span className="w-4 h-4 rounded-full border border-gray-400 flex items-center justify-center text-xs">i</span>
            Get help connecting your accounts
          </a>
        </div>
      </div>

      {/* Bluesky modal */}
      {blueskyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm mx-4 p-6">
            <div className="flex items-center gap-2 mb-4">
              <SiBluesky className="text-sky-500 text-xl" />
              <h2 className="text-lg font-semibold text-gray-900">Connect Bluesky</h2>
            </div>
            <p className="text-sm text-gray-500 mb-4">
              Enter your Bluesky handle and an{' '}
              <a
                href="https://bsky.app/settings/app-passwords"
                target="_blank"
                rel="noreferrer"
                className="text-sky-500 hover:underline"
              >
                App Password
              </a>
              {' '}(not your main password).
            </p>
            <div className="space-y-3 mb-5">
              <input
                type="text"
                value={blueskyHandle}
                onChange={(e) => setBlueskyHandle(e.target.value)}
                placeholder="handle.bsky.social"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400"
              />
              <input
                type="password"
                value={blueskyPass}
                onChange={(e) => setBlueskyPass(e.target.value)}
                placeholder="App password"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400"
                onKeyDown={(e) => { if (e.key === 'Enter') handleBlueskyConnect(); }}
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => { setBlueskyModal(false); setBlueskyHandle(''); setBlueskyPass(''); }}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleBlueskyConnect}
                disabled={blueskyLoading || !blueskyHandle.trim() || !blueskyPass.trim()}
                className="px-4 py-2 text-sm font-semibold bg-sky-500 hover:bg-sky-600 text-white rounded-lg disabled:opacity-50 transition-colors"
              >
                {blueskyLoading ? 'Connecting…' : 'Connect'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── LinkedIn Manual Page Add Modal ── */}
      {linkedinPageModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center gap-3 mb-5">
              <FaLinkedin className="text-blue-700 text-2xl" />
              <div>
                <h2 className="text-lg font-bold text-gray-900">Add LinkedIn Company Page</h2>
                <p className="text-sm text-gray-500">Enter your page details to connect it</p>
              </div>
            </div>

            <div className="space-y-4 mb-5">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">
                  Page Name
                </label>
                <input
                  type="text"
                  value={pageNameInput}
                  onChange={(e) => setPageNameInput(e.target.value)}
                  placeholder="e.g. Acme Corporation"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">
                  Page ID or URL
                </label>
                <input
                  type="text"
                  value={pageIdInput}
                  onChange={(e) => setPageIdInput(e.target.value)}
                  placeholder="e.g. acme-corp or 12345678"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
                <p className="text-[11px] text-gray-400 mt-1.5">
                  Find it in your LinkedIn Page URL: linkedin.com/company/<strong>your-page-id</strong>
                </p>
              </div>
            </div>

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => { setLinkedinPageModal(false); setPageIdInput(''); setPageNameInput(''); }}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 border border-gray-200 rounded-xl transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleAddLinkedinPage}
                disabled={addingPage || !pageIdInput.trim() || !pageNameInput.trim()}
                className="px-5 py-2 text-sm font-semibold bg-blue-700 text-white rounded-xl hover:bg-blue-800 disabled:opacity-50 transition-colors"
              >
                {addingPage ? 'Connecting…' : 'Connect Page'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── LinkedIn Pages Selection Modal (auto, from OAuth) ── */}
      {linkedinOrgsModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center gap-3 mb-4">
              <FaLinkedin className="text-blue-700 text-2xl" />
              <div>
                <h2 className="text-lg font-bold text-gray-900">Connect LinkedIn Pages</h2>
                <p className="text-sm text-gray-500">Select the company pages you'd like to manage</p>
              </div>
            </div>

            <div className="space-y-2 max-h-64 overflow-y-auto mb-5">
              {linkedinOrgs.map((org) => (
                <label
                  key={org.org_id}
                  className="flex items-center gap-3 p-3 rounded-xl border border-gray-200 hover:border-blue-300 hover:bg-blue-50 cursor-pointer transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={selectedOrgs.includes(org.org_id)}
                    onChange={() =>
                      setSelectedOrgs((prev) =>
                        prev.includes(org.org_id)
                          ? prev.filter((id) => id !== org.org_id)
                          : [...prev, org.org_id]
                      )
                    }
                    className="w-4 h-4 accent-blue-600"
                  />
                  <div className="w-9 h-9 rounded-lg bg-blue-100 flex items-center justify-center text-blue-700 font-bold text-sm flex-shrink-0">
                    {org.name.charAt(0).toUpperCase()}
                  </div>
                  <span className="font-medium text-gray-800 text-sm">{org.name}</span>
                </label>
              ))}
            </div>

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setLinkedinOrgsModal(false)}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 border border-gray-200 rounded-xl transition-colors"
              >
                Skip
              </button>
              <button
                onClick={handleSaveLinkedinOrgs}
                disabled={savingOrgs || selectedOrgs.length === 0}
                className="px-5 py-2 text-sm font-semibold bg-blue-700 text-white rounded-xl hover:bg-blue-800 disabled:opacity-50 transition-colors"
              >
                {savingOrgs
                  ? 'Connecting…'
                  : `Connect ${selectedOrgs.length} Page${selectedOrgs.length !== 1 ? 's' : ''}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
};

export default ConnectedAccounts;
