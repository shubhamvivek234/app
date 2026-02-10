import React, { useState } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';

const Settings = () => {
  const { user } = useAuth();
  const [formData, setFormData] = useState({
    name: user?.name || '',
    email: user?.email || '',
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    // In production, implement update user API
    toast.info('User settings update coming soon');
  };

  return (
    <DashboardLayout>
      <div className="max-w-2xl space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Settings</h1>
          <p className="text-base text-slate-600 mt-1">Manage your account settings and preferences</p>
        </div>

        {/* Profile Settings */}
        <div className="bg-white rounded-lg border border-border p-6">
          <h2 className="text-xl font-semibold text-slate-900 mb-6">Profile Information</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label htmlFor="name">Full Name</Label>
              <Input
                id="name"
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                data-testid="name-input"
              />
            </div>
            <div>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                data-testid="email-input"
              />
            </div>
            <Button type="submit" data-testid="save-settings-button">
              Save Changes
            </Button>
          </form>
        </div>

        {/* Subscription Info */}
        <div className="bg-white rounded-lg border border-border p-6">
          <h2 className="text-xl font-semibold text-slate-900 mb-4">Subscription</h2>
          <div className="space-y-2">
            <p className="text-sm text-slate-600">
              <strong>Status:</strong>{' '}
              <span className={user?.subscription_status === 'active' ? 'text-green-600' : 'text-slate-600'}>
                {user?.subscription_status === 'active' ? 'Active' : 'Free'}
              </span>
            </p>
            {user?.subscription_plan && (
              <p className="text-sm text-slate-600">
                <strong>Plan:</strong> <span className="capitalize">{user.subscription_plan}</span>
              </p>
            )}
          </div>
        </div>

        {/* API Keys Info */}
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-slate-900 mb-3">Social Media API Setup</h2>
          <div className="space-y-2 text-sm text-slate-700">
            <p><strong>To enable real social media posting, add these to backend/.env:</strong></p>
            <div className="bg-white rounded p-3 font-mono text-xs mt-3 space-y-1">
              <p># Twitter/X API</p>
              <p>TWITTER_API_KEY=your_key</p>
              <p>TWITTER_API_SECRET=your_secret</p>
              <p className="mt-2"># Instagram (via Facebook Graph API)</p>
              <p>INSTAGRAM_ACCESS_TOKEN=your_token</p>
              <p className="mt-2"># LinkedIn API</p>
              <p>LINKEDIN_CLIENT_ID=your_client_id</p>
              <p>LINKEDIN_CLIENT_SECRET=your_client_secret</p>
            </div>
            <p className="mt-3 text-amber-700">
              <strong>Note:</strong> Currently using mock connections. Real OAuth integration required for production.
            </p>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Settings;