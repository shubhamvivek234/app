import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { toast } from 'sonner';
import axios from 'axios';
import { FaInstagram, FaYoutube, FaFacebook, FaTwitter, FaPlus } from 'react-icons/fa';

import OnboardingHeader from '@/components/OnboardingHeader';

const OnboardingConnect = () => {
  const navigate = useNavigate();
  const [showAddModal, setShowAddModal] = useState(false);
  const [showPlatformModal, setShowPlatformModal] = useState(false);
  const [selectedPlatform, setSelectedPlatform] = useState(null);
  const [connectedAccounts, setConnectedAccounts] = useState([]);
  const [loading, setLoading] = useState(false);

  // ... (rest of logic same)

  const platforms = [
    { id: 'instagram', name: 'Instagram', icon: FaInstagram, color: '#E4405F' },
    { id: 'youtube', name: 'YouTube', icon: FaYoutube, color: '#FF0000' },
    { id: 'facebook', name: 'Facebook', icon: FaFacebook, color: '#1877F2' },
    { id: 'twitter', name: 'Twitter/X', icon: FaTwitter, color: '#1DA1F2' },
  ];

  useEffect(() => {
    fetchConnectedAccounts();
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
    setSelectedPlatform(platform);
    setShowAddModal(false);
    setShowPlatformModal(true);
  };

  const handleConnectPlatform = async () => {
    if (!selectedPlatform) return;

    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

      // Get OAuth authorization URL
      const authResponse = await axios.get(
        `${apiUrl}/api/oauth/${selectedPlatform.id}/authorize`,
        {
          headers: { Authorization: `Bearer ${token}` },
          withCredentials: true,
        }
      );

      const { authorization_url, code_verifier } = authResponse.data;

      // Store code_verifier for Twitter if present
      if (code_verifier) {
        sessionStorage.setItem('twitter_code_verifier', code_verifier);
      }

      // Store platform info for callback
      sessionStorage.setItem('oauth_platform', selectedPlatform.id);
      sessionStorage.setItem('oauth_return_to', 'onboarding');

      // Redirect to OAuth page
      window.location.href = authorization_url;

    } catch (error) {
      console.error('Error initiating OAuth:', error);
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

  const handleBack = () => {
    navigate('/onboarding');
  };

  const PlatformIcon = selectedPlatform?.icon;

  return (
    <div className="min-h-screen bg-slate-50 pt-20 flex items-center justify-center px-4">
      <OnboardingHeader step={2} />

      <div className="max-w-3xl w-full">
        {/* Content */}
        <div className="bg-white rounded-xl shadow-sm border border-border p-8">
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
                        className="flex items-center p-4 bg-slate-50 rounded-lg border border-slate-200"
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
              Connect your social media accounts to SocialEntangler and post to all of them at once
            </p>
          </DialogHeader>

          <div className="grid grid-cols-2 gap-4 mt-4">
            {platforms.map((platform) => {
              const Icon = platform.icon;
              return (
                <div
                  key={platform.id}
                  className="flex items-center justify-between p-4 bg-white rounded-lg border border-slate-200 hover:border-slate-300 transition-colors"
                >
                  <div className="flex items-center">
                    <Icon className="text-2xl mr-3" style={{ color: platform.color }} />
                    <span className="font-medium">{platform.name}</span>
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
    </div>
  );
};

export default OnboardingConnect;
