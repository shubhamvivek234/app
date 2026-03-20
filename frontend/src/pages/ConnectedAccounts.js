import React, { useEffect, useState } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { getSocialAccounts, connectSocialAccount, disconnectSocialAccount } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { FaTwitter, FaLinkedin, FaInstagram, FaPlus, FaTrash, FaCheckCircle } from 'react-icons/fa';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';

const ConnectedAccounts = () => {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connectDialogOpen, setConnectDialogOpen] = useState(false);
  const [selectedPlatform, setSelectedPlatform] = useState('');
  const [username, setUsername] = useState('');
  const [connecting, setConnecting] = useState(false);

  const platforms = [
    { id: 'twitter', name: 'Twitter/X', icon: FaTwitter, color: 'text-blue-400', bg: 'bg-blue-50' },
    { id: 'instagram', name: 'Instagram', icon: FaInstagram, color: 'text-pink-500', bg: 'bg-pink-50' },
    { id: 'linkedin', name: 'LinkedIn', icon: FaLinkedin, color: 'text-blue-600', bg: 'bg-blue-50' },
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

  const handleConnect = async (e) => {
    e.preventDefault();

    if (!selectedPlatform || !username.trim()) {
      toast.error('Please select a platform and enter username');
      return;
    }

    setConnecting(true);
    try {
      await connectSocialAccount(selectedPlatform, username);
      toast.success('Account connected! (Note: Add real OAuth integration for production)');
      setConnectDialogOpen(false);
      setSelectedPlatform('');
      setUsername('');
      fetchAccounts();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to connect account');
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async (accountId) => {
    if (!window.confirm('Are you sure you want to disconnect this account?')) return;

    try {
      await disconnectSocialAccount(accountId);
      setAccounts(accounts.filter((a) => a.id !== accountId));
      toast.success('Account disconnected');
    } catch (error) {
      toast.error('Failed to disconnect account');
    }
  };

  const getPlatformInfo = (platformId) => {
    return platforms.find((p) => p.id === platformId) || {};
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-slate-600">Loading accounts...</div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-8">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900">
              Connected Accounts
            </h1>
            <p className="text-base text-slate-600 mt-1">
              Manage your social media connections
            </p>
          </div>
          <Dialog open={connectDialogOpen} onOpenChange={setConnectDialogOpen}>
            <DialogTrigger asChild>
              <Button data-testid="connect-account-button">
                <FaPlus className="mr-2" />
                Connect Account
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Connect Social Account</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleConnect} className="space-y-4 mt-4">
                <div>
                  <Label>Platform</Label>
                  <div className="grid grid-cols-3 gap-3 mt-2">
                    {platforms.map((platform) => {
                      const Icon = platform.icon;
                      return (
                        <button
                          key={platform.id}
                          type="button"
                          onClick={() => setSelectedPlatform(platform.id)}
                          data-testid={`select-${platform.id}`}
                          className={`p-4 rounded-lg border-2 transition-all ${
                            selectedPlatform === platform.id
                              ? 'border-indigo-600 bg-indigo-50'
                              : 'border-border hover:border-slate-300'
                          }`}
                        >
                          <Icon className={`text-2xl ${platform.color} mx-auto`} />
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div>
                  <Label htmlFor="username">Username</Label>
                  <Input
                    id="username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="@username"
                    data-testid="username-input"
                  />
                  <p className="text-xs text-slate-500 mt-1">
                    Note: In production, this would use OAuth authentication
                  </p>
                </div>
                <Button type="submit" disabled={connecting} data-testid="connect-submit-button">
                  {connecting ? 'Connecting...' : 'Connect'}
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {/* Info Banner */}
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
          <p className="text-sm text-amber-800">
            <strong>Note:</strong> For production use, you'll need to add OAuth integration for each platform:
            <br />• Twitter/X: Create app at developer.twitter.com
            <br />• Instagram: Use Facebook Graph API
            <br />• LinkedIn: Create app at developer.linkedin.com
          </p>
        </div>

        {/* Connected Accounts List */}
        <div className="grid gap-4">
          {accounts.length === 0 ? (
            <div className="bg-white rounded-lg border border-border p-12 text-center">
              <p className="text-slate-600 mb-4">No accounts connected yet</p>
              <Button
                onClick={() => setConnectDialogOpen(true)}
                data-testid="empty-connect-button"
              >
                <FaPlus className="mr-2" />
                Connect Your First Account
              </Button>
            </div>
          ) : (
            accounts.map((account) => {
              const platformInfo = getPlatformInfo(account.platform);
              const Icon = platformInfo.icon || FaCheckCircle;
              return (
                <div
                  key={account.id}
                  className="bg-white rounded-lg border border-border p-6 flex items-center justify-between"
                  data-testid={`account-${account.id}`}
                >
                  <div className="flex items-center gap-4">
                    <div className={`w-12 h-12 rounded-lg ${platformInfo.bg} flex items-center justify-center`}>
                      <Icon className={`text-2xl ${platformInfo.color}`} />
                    </div>
                    <div>
                      <h3 className="text-lg font-medium text-slate-900">{platformInfo.name}</h3>
                      <p className="text-sm text-slate-600">{account.platform_username}</p>
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    onClick={() => handleDisconnect(account.id)}
                    data-testid={`disconnect-${account.id}`}
                  >
                    <FaTrash className="mr-2 text-red-600" />
                    Disconnect
                  </Button>
                </div>
              );
            })
          )}
        </div>
      </div>
    </DashboardLayout>
  );
};

export default ConnectedAccounts;