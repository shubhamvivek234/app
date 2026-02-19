import React, { useEffect, useState } from 'react';
import axios from 'axios';
import DashboardLayout from '@/components/DashboardLayout';
import { getSocialAccounts, connectSocialAccount, disconnectSocialAccount } from '@/lib/api';
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
  FaFilter
} from 'react-icons/fa';
import { SiBluesky, SiThreads } from 'react-icons/si';

const ConnectedAccounts = () => {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(null);

  // Platform definitions
  const platforms = [
    {
      id: 'bluesky',
      name: 'Bluesky',
      icon: SiBluesky,
      color: 'text-blue-500',
      buttonBg: 'bg-gray-900 hover:bg-gray-800',
      mockAccounts: ['jack friks']
    },
    {
      id: 'facebook',
      name: 'Facebook',
      icon: FaFacebook,
      color: 'text-blue-600',
      buttonBg: 'bg-gray-900 hover:bg-gray-800',
      mockAccounts: ['Jack friks', 'Curiosity Quench', 'Scroll less', 'SocialEntangler', 'SocialEntangler 2', 'Doof - food diary app']
    },
    {
      id: 'instagram',
      name: 'Instagram',
      icon: FaInstagram,
      color: 'text-pink-500',
      buttonBg: 'bg-gray-900 hover:bg-gray-800',
      mockAccounts: ['jackfriks', 'curiosity.quench', 'scroll_less_live_more', 'crosspost', 'doof.app']
    },
    {
      id: 'linkedin',
      name: 'LinkedIn',
      icon: FaLinkedin,
      color: 'text-blue-700',
      buttonBg: 'bg-gray-900 hover:bg-gray-800',
      mockAccounts: ['SocialEntangler', 'jack friks']
    },
    {
      id: 'pinterest',
      name: 'Pinterest',
      icon: FaPinterest,
      color: 'text-red-600',
      buttonBg: 'bg-gray-900 hover:bg-gray-800',
      mockAccounts: ['jackfriks', 'crosspost']
    },
    {
      id: 'threads',
      name: 'Threads',
      icon: SiThreads,
      color: 'text-gray-900',
      buttonBg: 'bg-gray-900 hover:bg-gray-800',
      mockAccounts: ['curiosity.quench', 'jackfriks']
    },
    {
      id: 'tiktok',
      name: 'TikTok',
      icon: FaTiktok,
      color: 'text-gray-900',
      buttonBg: 'bg-gray-900 hover:bg-gray-800',
      mockAccounts: ['jack friks', 'Curiosity Quench', 'jack friks', 'doof - food diary app', 'post.bridge']
    },
    {
      id: 'twitter',
      name: 'Twitter',
      icon: FaTwitter,
      color: 'text-blue-400',
      buttonBg: 'bg-gray-900 hover:bg-gray-800',
      mockAccounts: ['doofapp', 'jackfriks', 'curiousquench', 'crosspost_']
    },
    {
      id: 'youtube',
      name: 'Youtube',
      icon: FaYoutube,
      color: 'text-red-600',
      buttonBg: 'bg-gray-900 hover:bg-gray-800',
      mockAccounts: ['jack friks', 'jack friks shorts']
    },
  ];

  useEffect(() => {
    fetchAccounts();
  }, []);

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

  const handleConnect = async (platformId) => {
    setConnecting(platformId);
    try {
      if (platformId === 'facebook' || platformId === 'instagram') {
        const token = localStorage.getItem('token');
        const apiUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

        // 1. Get Auth URL from backend
        const response = await axios.get(`${apiUrl}/api/oauth/facebook/authorize`, {
          headers: { Authorization: `Bearer ${token}` }
        });

        // 2. Redirect user
        window.location.href = response.data.authorization_url;
        return;
      }

      // Generate a mock username for demo (for other platforms)
      const platform = platforms.find(p => p.id === platformId);
      const mockUsername = `@user_${Date.now().toString(36)}`;

      await connectSocialAccount(platformId, mockUsername);
      toast.success(`${platform.name} connected! (Note: Real OAuth integration required for production)`);
      fetchAccounts();
    } catch (error) {
      console.error('Connect error:', error);
      toast.error(error.response?.data?.detail || 'Failed to connect account');
    } finally {
      if (platformId !== 'facebook' && platformId !== 'instagram') {
        setConnecting(null);
      }
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

        {/* Platform Rows */}
        <div className="space-y-4">
          {platforms.map((platform) => {
            const Icon = platform.icon;
            const connectedAccounts = getAccountsByPlatform(platform.id);
            // Combine real accounts with mock data for display
            const displayAccounts = connectedAccounts.length > 0
              ? connectedAccounts
              : platform.mockAccounts.map((name, idx) => ({
                id: `mock-${platform.id}-${idx}`,
                platform: platform.id,
                platform_username: name,
                isMock: true
              }));

            return (
              <div key={platform.id} className="flex items-center gap-4 py-2">
                {/* Platform Icon */}
                <div className="w-8 h-8 flex items-center justify-center">
                  <Icon className={`text-2xl ${platform.color}`} />
                </div>

                {/* Connect Button */}
                <Button
                  onClick={() => handleConnect(platform.id)}
                  disabled={connecting === platform.id}
                  className={`${platform.buttonBg} text-white min-w-[160px]`}
                  data-testid={`connect-${platform.id}`}
                >
                  {connecting === platform.id ? 'Connecting...' : `Connect ${platform.name}`}
                </Button>

                {/* Connected Account Tags */}
                <div className="flex flex-wrap items-center gap-2">
                  {displayAccounts.map((account, idx) => (
                    <div
                      key={account.id}
                      className="flex items-center gap-1.5 bg-white border border-gray-200 rounded-full px-2 py-1 text-sm"
                      data-testid={`account-tag-${account.id}`}
                    >
                      {/* Avatar */}
                      <div className={`w-5 h-5 rounded-full ${getAvatarColor(account.platform_username)} flex items-center justify-center text-white text-xs`}>
                        {account.platform_username?.charAt(0)?.toUpperCase() || 'U'}
                      </div>
                      {/* Username */}
                      <span className="text-gray-700">{account.platform_username}</span>
                      {/* Close Button */}
                      <button
                        onClick={() => account.isMock
                          ? toast.info('This is a demo account')
                          : handleDisconnect(account.id, platform.name)
                        }
                        className="text-red-400 hover:text-red-600 ml-1"
                        data-testid={`disconnect-${account.id}`}
                      >
                        <FaTimes className="text-xs" />
                      </button>
                    </div>
                  ))}
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
    </DashboardLayout>
  );
};

export default ConnectedAccounts;
