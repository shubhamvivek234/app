import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { toast } from 'sonner';
import axios from 'axios';
import {
  FaInstagram,
  FaYoutube,
  FaFacebook,
  FaTwitter,
  FaPlus,
  FaLinkedin,
  FaTiktok,
  FaPinterest,
  FaDiscord,
} from 'react-icons/fa';
import { SiBluesky, SiMastodon, SiSnapchat, SiThreads } from 'react-icons/si';
import { clearOAuthPopupExpected, listenForOAuthResult, markOAuthPopupExpected } from '@/lib/oauthPopup';
import { requestOAuthUrl } from '@/lib/requestOAuthUrl';
import { connectBluesky, connectDiscord, connectMastodon } from '@/lib/api';

import OnboardingHeader from '@/components/OnboardingHeader';

const OnboardingConnect = () => {
  const navigate = useNavigate();
  const [showAddModal, setShowAddModal] = useState(false);
  const [showPlatformModal, setShowPlatformModal] = useState(false);
  const [selectedPlatform, setSelectedPlatform] = useState(null);
  const [connectedAccounts, setConnectedAccounts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [blueskyModal, setBlueskyModal] = useState(false);
  const [blueskyHandle, setBlueskyHandle] = useState('');
  const [blueskyPass, setBlueskyPass] = useState('');
  const [blueskyLoading, setBlueskyLoading] = useState(false);
  const [discordModal, setDiscordModal] = useState(false);
  const [discordWebhookUrl, setDiscordWebhookUrl] = useState('');
  const [discordChannelName, setDiscordChannelName] = useState('');
  const [discordLoading, setDiscordLoading] = useState(false);
  const [mastodonModal, setMastodonModal] = useState(false);
  const [mastodonInstanceUrl, setMastodonInstanceUrl] = useState('');
  const [mastodonAccessToken, setMastodonAccessToken] = useState('');
  const [mastodonLoading, setMastodonLoading] = useState(false);

  const platforms = [
    { id: 'instagram', name: 'Instagram', icon: FaInstagram, color: '#E4405F' },
    { id: 'youtube', name: 'YouTube', icon: FaYoutube, color: '#FF0000' },
    { id: 'facebook', name: 'Facebook', icon: FaFacebook, color: '#1877F2' },
    { id: 'twitter', name: 'Twitter/X', icon: FaTwitter, color: '#1DA1F2' },
    { id: 'linkedin', name: 'LinkedIn', icon: FaLinkedin, color: '#0A66C2' },
    { id: 'tiktok', name: 'TikTok', icon: FaTiktok, color: '#111827' },
    { id: 'pinterest', name: 'Pinterest', icon: FaPinterest, color: '#E60023' },
    { id: 'threads', name: 'Threads', icon: SiThreads, color: '#111827' },
    { id: 'snapchat', name: 'Snapchat', icon: SiSnapchat, color: '#EAB308' },
    { id: 'bluesky', name: 'Bluesky', icon: SiBluesky, color: '#0284C7', credential: true },
    { id: 'discord', name: 'Discord', icon: FaDiscord, color: '#5865F2', credential: true },
    { id: 'mastodon', name: 'Mastodon', icon: SiMastodon, color: '#4F46E5', credential: true, badge: 'Access token' },
  ];

  useEffect(() => {
    fetchConnectedAccounts();
  }, []);

  useEffect(() => {
    return listenForOAuthResult((message) => {
      if (!message || message.returnTo !== 'onboarding') return;

      clearOAuthPopupExpected();
      setLoading(false);
      setShowPlatformModal(false);

      if (message.status === 'success') {
        toast.success(`${message.platform || 'Account'} connected successfully!`);
        fetchConnectedAccounts();
      } else if (message.status === 'error') {
        toast.error(message.error || 'Failed to connect platform');
      }
    });
  }, []);

  const fetchConnectedAccounts = async () => {
    try {
      const token = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_BACKEND_URL || '';

      const response = await axios.get(`${apiUrl}/api/social-accounts`, {
        headers: { Authorization: `Bearer ${token}` },
        withCredentials: true,
      });

      setConnectedAccounts(response.data);
    } catch (error) {
      console.error('Error fetching accounts:', error);
    }
  };

  const handleAddClick = (platform) => {
    if (platform.id === 'bluesky') {
      setShowAddModal(false);
      setBlueskyModal(true);
      return;
    }
    if (platform.id === 'discord') {
      setShowAddModal(false);
      setDiscordModal(true);
      return;
    }
    if (platform.id === 'mastodon') {
      setShowAddModal(false);
      setMastodonModal(true);
      return;
    }
    setSelectedPlatform(platform);
    setShowAddModal(false);
    setShowPlatformModal(true);
  };

  const handleConnectPlatform = async () => {
    if (!selectedPlatform) return;

    setLoading(true);
    // Open a popup synchronously so browsers don't block it (window.open after an await
    // is treated as a non-user gesture and is frequently blocked).
    const popup = window.open('', '_blank', 'noopener,noreferrer');
    if (popup) popup.opener = null;
    markOAuthPopupExpected(Boolean(popup));
    try {
      const token = localStorage.getItem('token');
      const { authorization_url, code_verifier } = await requestOAuthUrl(selectedPlatform.id, token);

      // Store code_verifier for Twitter if present
      if (code_verifier) {
        sessionStorage.setItem('twitter_code_verifier', code_verifier);
      }

      // Store platform info for callback
      sessionStorage.setItem('oauth_platform', selectedPlatform.id);
      sessionStorage.setItem('oauth_return_to', 'onboarding');

      // Navigate the pre-opened popup (or fall back to same-tab redirect).
      if (popup) {
        popup.location.href = authorization_url;
      } else {
        window.location.assign(authorization_url);
      }

    } catch (error) {
      console.error('Error initiating OAuth:', error);
      clearOAuthPopupExpected();
      if (popup) popup.close();
      if (error.response?.status === 500 && error.response?.data?.detail?.includes('not configured')) {
        toast.error(`${selectedPlatform.name} API credentials not configured. Please contact administrator.`);
      } else {
        toast.error('Failed to connect platform');
      }
    } finally {
      setLoading(false);
      setShowPlatformModal(false);
    }
  };

  const handleNext = async () => {
    // Allow proceeding to pricing without connections
    navigate('/onboarding/pricing');
  };

  const resetBlueskyModal = () => {
    setBlueskyModal(false);
    setBlueskyHandle('');
    setBlueskyPass('');
  };

  const handleBlueskyConnect = async () => {
    if (!blueskyHandle.trim() || !blueskyPass.trim()) return;

    setBlueskyLoading(true);
    try {
      await connectBluesky({
        handle: blueskyHandle.trim(),
        app_password: blueskyPass.trim(),
      });
      toast.success('Bluesky connected successfully!');
      resetBlueskyModal();
      fetchConnectedAccounts();
    } catch (error) {
      console.error('Error connecting Bluesky:', error);
      toast.error(error?.response?.data?.detail || 'Failed to connect Bluesky');
    } finally {
      setBlueskyLoading(false);
    }
  };

  const resetDiscordModal = () => {
    setDiscordModal(false);
    setDiscordWebhookUrl('');
    setDiscordChannelName('');
  };

  const handleDiscordConnect = async () => {
    if (!discordWebhookUrl.trim()) return;

    setDiscordLoading(true);
    try {
      const result = await connectDiscord(
        discordWebhookUrl.trim(),
        discordChannelName.trim() || null,
      );
      toast.success(
        result?.channel
          ? `Discord channel connected: ${result.channel}`
          : 'Discord connected successfully!',
      );
      resetDiscordModal();
      fetchConnectedAccounts();
    } catch (error) {
      console.error('Error connecting Discord:', error);
      toast.error(error?.response?.data?.detail || 'Failed to connect Discord');
    } finally {
      setDiscordLoading(false);
    }
  };

  const resetMastodonModal = () => {
    setMastodonModal(false);
    setMastodonInstanceUrl('');
    setMastodonAccessToken('');
  };

  const handleMastodonConnect = async () => {
    if (!mastodonInstanceUrl.trim() || !mastodonAccessToken.trim()) return;

    setMastodonLoading(true);
    try {
      await connectMastodon(mastodonInstanceUrl.trim(), mastodonAccessToken.trim());
      toast.success('Mastodon connected successfully!');
      resetMastodonModal();
      fetchConnectedAccounts();
    } catch (error) {
      console.error('Error connecting Mastodon:', error);
      toast.error(error?.response?.data?.detail || 'Failed to connect Mastodon');
    } finally {
      setMastodonLoading(false);
    }
  };

  const handleBack = () => {
    navigate('/onboarding');
  };

  const PlatformIcon = selectedPlatform?.icon;

  return (
    <div className="min-h-screen bg-offwhite pt-20 flex items-center justify-center px-4">
      <OnboardingHeader step={2} />

      <div className="max-w-3xl w-full">
        {/* Content */}
        <div className="bg-offwhite rounded-xl shadow-sm border border-border p-8">
          <h2 className="text-3xl font-bold text-slate-900 mb-2">Connect your accounts</h2>
          <p className="text-slate-600 mb-8">
            Connect and then manage all your social media accounts from one place
          </p>

          {/* Connection Area */}
          <div className="border-2 border-dashed border-gray-300 rounded-lg p-12 mb-6 min-h-[200px] flex flex-col items-center justify-center">
            {connectedAccounts.length === 0 ? (
              <>
                <Button
                  onClick={() => setShowAddModal(true)}
                  variant="outline"
                  className="mb-4"
                >
                  <FaPlus className="mr-2" />
                  Add connection
                </Button>
                <p className="text-sm text-slate-500 text-center">
                  No connected accounts yet. Use the 'Add connection' button to get started.
                </p>
              </>
            ) : (
              <div className="w-full">
                <div className="grid grid-cols-2 gap-4 mb-4">
                  {connectedAccounts.map((account) => {
                    const platform = platforms.find((p) => p.id === account.platform);
                    const PlatformIcon = platform?.icon;
                    return (
                      <div
                        key={account.id}
                        className="flex items-center p-4 bg-offwhite rounded-lg border border-slate-200"
                      >
                        {PlatformIcon && <PlatformIcon className="text-2xl mr-3" style={{ color: platform.color }} />}
                        <div>
                          <p className="font-semibold text-slate-900">{platform?.name}</p>
                          <p className="text-sm text-slate-500">@{account.username}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <Button
                  onClick={() => setShowAddModal(true)}
                  variant="outline"
                  size="sm"
                >
                  <FaPlus className="mr-2" />
                  Add another connection
                </Button>
              </div>
            )}
          </div>

          {/* Navigation */}
          <div className="flex justify-between">
            <Button variant="outline" onClick={handleBack}>
              Back
            </Button>
            <Button onClick={handleNext}>
              Next
            </Button>
          </div>
        </div>
      </div>

      {/* Add Connection Modal */}
      <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-2xl">Add all your accounts</DialogTitle>
            <p className="text-sm text-slate-600 mt-2">
              Connect your social media accounts to Unravler and post to all of them at once
            </p>
          </DialogHeader>

          <div className="grid grid-cols-2 gap-4 mt-4">
            {platforms.map((platform) => {
              const Icon = platform.icon;
              return (
                <div
                  key={platform.id}
                  className="flex items-center justify-between p-4 bg-offwhite rounded-lg border border-slate-200 hover:border-slate-300 transition-colors"
                >
                  <div className="flex items-center">
                    <Icon className="text-2xl mr-3" style={{ color: platform.color }} />
                    <div>
                      <span className="font-medium">{platform.name}</span>
                      {platform.badge && (
                        <div className="text-[10px] text-gray-500">{platform.badge}</div>
                      )}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    onClick={() => handleAddClick(platform)}
                    className="bg-green-500 hover:bg-green-600"
                  >
                    Add
                  </Button>
                </div>
              );
            })}
          </div>

          <div className="flex justify-between mt-6">
            <Button variant="outline" onClick={() => setShowAddModal(false)}>
              Back
            </Button>
            <Button onClick={() => setShowAddModal(false)}>
              Next
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Platform Connection Modal */}
      <Dialog open={showPlatformModal} onOpenChange={setShowPlatformModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-xl flex items-center">
              {PlatformIcon && <PlatformIcon className="mr-2 text-2xl" style={{ color: selectedPlatform?.color }} />}
              Connect {selectedPlatform?.name}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 mt-4">
            {selectedPlatform?.id === 'instagram' && (
              <div className="space-y-2">
                <div className="flex items-start">
                  <span className="mr-2">•</span>
                  <p className="text-sm text-slate-600">
                    Requires Instagram Business or Creator profile.{' '}
                    <a href="#" className="text-indigo-600 hover:underline">
                      (How to set up?)
                    </a>
                  </p>
                </div>
                <div className="flex items-start">
                  <span className="mr-2">•</span>
                  <p className="text-sm text-slate-600">
                    To add another account, log out/switch on instagram.com first
                  </p>
                </div>
              </div>
            )}

            {selectedPlatform?.id === 'youtube' && (
              <div className="space-y-2">
                <div className="flex items-start">
                  <span className="mr-2">•</span>
                  <p className="text-sm text-slate-600">
                    You'll be redirected to YouTube to authorize access to your channel
                  </p>
                </div>
              </div>
            )}

            {selectedPlatform?.id === 'facebook' && (
              <div className="space-y-2">
                <div className="flex items-start">
                  <span className="mr-2">•</span>
                  <p className="text-sm text-slate-600">
                    Connect your Facebook Page to schedule posts
                  </p>
                </div>
              </div>
            )}

            {selectedPlatform?.id === 'twitter' && (
              <div className="space-y-2">
                <div className="flex items-start">
                  <span className="mr-2">•</span>
                  <p className="text-sm text-slate-600">
                    You'll be redirected to Twitter/X to authorize access to your account
                  </p>
                </div>
              </div>
            )}

            {selectedPlatform?.id === 'pinterest' && (
              <div className="space-y-2">
                <div className="flex items-start">
                  <span className="mr-2">•</span>
                  <p className="text-sm text-slate-600">
                    You'll be redirected to Pinterest to approve access to your boards and pins.
                  </p>
                </div>
                <div className="flex items-start">
                  <span className="mr-2">•</span>
                  <p className="text-sm text-slate-600">
                    Make sure the Pinterest app has your production redirect URI configured before connecting.
                  </p>
                </div>
              </div>
            )}

            {selectedPlatform?.id === 'threads' && (
              <div className="space-y-2">
                <div className="flex items-start">
                  <span className="mr-2">•</span>
                  <p className="text-sm text-slate-600">
                    You&apos;ll be redirected to Threads to approve publishing access for your account.
                  </p>
                </div>
              </div>
            )}

            {selectedPlatform?.id === 'snapchat' && (
              <div className="space-y-2">
                <div className="flex items-start">
                  <span className="mr-2">•</span>
                  <p className="text-sm text-slate-600">
                    Snapchat currently supports account login and profile connection. Organic post publishing is limited on their public API.
                  </p>
                </div>
              </div>
            )}
          </div>

          <div className="flex justify-end space-x-2 mt-6">
            <Button variant="outline" onClick={() => setShowPlatformModal(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleConnectPlatform}
              disabled={loading}
              className="bg-green-500 hover:bg-green-600"
            >
              {loading ? 'Connecting...' : `Connect ${selectedPlatform?.name}`}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Bluesky modal */}
      {blueskyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-sky-50 border border-sky-200 flex items-center justify-center">
                <SiBluesky className="text-sky-500 text-lg" />
              </div>
              <div>
                <h2 className="text-base font-bold text-gray-900">Connect Bluesky</h2>
                <p className="text-xs text-gray-500">Use your handle and an app password</p>
              </div>
            </div>
            <p className="text-xs text-gray-500 mb-4 bg-sky-50 border border-sky-100 rounded-lg px-3 py-2">
              Create an{' '}
              <a
                href="https://bsky.app/settings/app-passwords"
                target="_blank"
                rel="noreferrer"
                className="text-sky-600 hover:underline font-medium"
              >
                app password
              </a>
              {' '}in Bluesky settings. Don&apos;t use your main account password here.
            </p>
            <div className="space-y-3 mb-5">
              <input
                type="text"
                value={blueskyHandle}
                onChange={(e) => setBlueskyHandle(e.target.value)}
                placeholder="handle.bsky.social"
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400"
              />
              <input
                type="password"
                value={blueskyPass}
                onChange={(e) => setBlueskyPass(e.target.value)}
                placeholder="App password (xxxx-xxxx-xxxx-xxxx)"
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleBlueskyConnect();
                }}
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={resetBlueskyModal}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-xl transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleBlueskyConnect}
                disabled={blueskyLoading || !blueskyHandle.trim() || !blueskyPass.trim()}
                className="px-5 py-2 text-sm font-semibold bg-sky-500 hover:bg-sky-600 text-white rounded-xl disabled:opacity-50 transition-colors"
              >
                {blueskyLoading ? 'Connecting…' : 'Connect'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Discord modal */}
      {discordModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-200 flex items-center justify-center">
                <FaDiscord className="text-indigo-500 text-xl" />
              </div>
              <div>
                <h2 className="text-base font-bold text-gray-900">Connect Discord Channel</h2>
                <p className="text-xs text-gray-500">Paste an incoming webhook URL</p>
              </div>
            </div>
            <div className="bg-indigo-50 border border-indigo-100 rounded-xl px-4 py-3 mb-4">
              <p className="text-xs font-semibold text-indigo-700 mb-2">How to get a webhook URL:</p>
              <ol className="space-y-1 text-xs text-indigo-700">
                {[
                  'Open your Discord server and edit the channel you want to post into.',
                  'Go to Integrations → Webhooks.',
                  'Create a webhook and copy its URL into Unravler.',
                ].map((step, index) => (
                  <li key={step} className="flex items-start gap-2">
                    <span className="w-4 h-4 rounded-full bg-indigo-200 text-indigo-800 text-[9px] font-bold flex items-center justify-center shrink-0 mt-0.5">
                      {index + 1}
                    </span>
                    {step}
                  </li>
                ))}
              </ol>
            </div>
            <div className="space-y-3 mb-5">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">
                  Webhook URL <span className="text-red-500">*</span>
                </label>
                <input
                  type="url"
                  value={discordWebhookUrl}
                  onChange={(e) => setDiscordWebhookUrl(e.target.value)}
                  placeholder="https://discord.com/api/webhooks/..."
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 font-mono"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1.5 uppercase tracking-wide">
                  Channel Label <span className="text-gray-400">(optional)</span>
                </label>
                <input
                  type="text"
                  value={discordChannelName}
                  onChange={(e) => setDiscordChannelName(e.target.value)}
                  placeholder="e.g. #announcements"
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleDiscordConnect();
                  }}
                />
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={resetDiscordModal}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-xl transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDiscordConnect}
                disabled={discordLoading || !discordWebhookUrl.trim()}
                className="px-5 py-2 text-sm font-semibold bg-indigo-500 hover:bg-indigo-600 text-white rounded-xl disabled:opacity-50 transition-colors flex items-center gap-2"
              >
                {discordLoading && (
                  <span className="animate-spin w-3 h-3 border-2 border-white border-t-transparent rounded-full" />
                )}
                {discordLoading ? 'Validating…' : 'Connect Channel'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Mastodon modal */}
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
                Mastodon uses per-instance tokens. Paste the full instance URL and a personal
                access token created from that instance&apos;s settings page.
              </p>
            </div>
            <div className="space-y-3 mb-5">
              <input
                type="url"
                value={mastodonInstanceUrl}
                onChange={(e) => setMastodonInstanceUrl(e.target.value)}
                placeholder="https://mastodon.social"
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
              <input
                type="password"
                value={mastodonAccessToken}
                onChange={(e) => setMastodonAccessToken(e.target.value)}
                placeholder="Paste your Mastodon access token"
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleMastodonConnect();
                }}
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={resetMastodonModal}
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
    </div>
  );
};

export default OnboardingConnect;
