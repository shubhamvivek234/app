import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import axios from 'axios';

import OnboardingHeader from '@/components/OnboardingHeader';

const COMMON_TIMEZONES = [
  "UTC",
  "Asia/Kolkata",
  "Asia/Dubai",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Asia/Shanghai",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Sao_Paulo",
  "Australia/Sydney",
  "Pacific/Auckland",
];

const Onboarding = () => {
  const navigate = useNavigate();
  const [selectedType, setSelectedType] = useState('');
  const [timezone, setTimezone] = useState(
    Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  );
  const [loading, setLoading] = useState(false);

  const userTypes = [
    { id: 'founder', label: 'Founder', description: 'Building a business' },
    { id: 'creator', label: 'Creator', description: 'Sharing content online' },
    { id: 'agency', label: 'Agency', description: 'Managing client accounts' },
    { id: 'enterprise', label: 'Enterprise', description: 'Large organization' },
    { id: 'small_business', label: 'Small Business', description: 'Running a local business' },
    { id: 'personal', label: 'Personal', description: 'Managing personal brand' },
  ];

  const handleNext = async () => {
    if (!selectedType) {
      toast.error('Please select an option');
      return;
    }

    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_BACKEND_URL || '';

      await axios.patch(
        `${apiUrl}/api/auth/me`,
        { user_type: selectedType, onboarding_completed: false, timezone },
        {
          headers: { Authorization: `Bearer ${token}` },
          withCredentials: true,
        }
      );

      toast.success('Profile updated!');
      navigate('/onboarding/connect');
    } catch (error) {
      console.error('Error updating profile:', error);
      toast.error('Failed to update profile');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-white pt-20">
      <OnboardingHeader step={1} />

      <div className="flex items-center justify-center px-4 py-12">
        <div className="max-w-2xl w-full">
          <div className="bg-white rounded-xl shadow-sm border border-border p-8">
            <p className="text-green-500 text-sm mb-2 text-center">almost ready</p>
            <h2 className="text-3xl font-bold text-slate-900 mb-8 text-center">what sounds most like you?</h2>

            <div className="space-y-3">
              {userTypes.map((type) => (
                <button
                  key={type.id}
                  onClick={() => setSelectedType(type.id)}
                  className={`w-full text-left p-4 rounded-lg border-2 transition-all ${selectedType === type.id
                    ? 'border-green-500 bg-green-50'
                    : 'border-gray-200 bg-white hover:border-gray-300'
                    }`}
                >
                  <div className="flex items-center">
                    <div
                      className={`w-5 h-5 rounded-full border-2 flex items-center justify-center mr-4 ${selectedType === type.id
                        ? 'border-green-500 bg-green-500'
                        : 'border-gray-300'
                        }`}
                    >
                      {selectedType === type.id && (
                        <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                          <path
                            fillRule="evenodd"
                            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                            clipRule="evenodd"
                          />
                        </svg>
                      )}
                    </div>
                    <div>
                      <p className={`font-semibold ${selectedType === type.id ? 'text-slate-900' : 'text-slate-700'}`}>
                        {type.label}
                      </p>
                      <p className="text-sm text-slate-500">{type.description}</p>
                    </div>
                  </div>
                </button>
              ))}
            </div>

            <div className="mt-6 space-y-1.5">
              <Label htmlFor="timezone" className="text-xs font-medium text-slate-600">Your Timezone</Label>
              <select
                id="timezone"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500"
              >
                {COMMON_TIMEZONES.map((tz) => (
                  <option key={tz} value={tz}>{tz}</option>
                ))}
              </select>
              <p className="text-xs text-slate-400">Used to schedule your posts at the right time.</p>
            </div>

            <div className="mt-8 flex justify-between">
              <Button
                variant="outline"
                onClick={() => navigate('/')}
                className="text-gray-600"
              >
                Back to Home
              </Button>
              <Button
                onClick={handleNext}
                disabled={!selectedType || loading}
                className="px-8"
              >
                {loading ? 'Saving...' : 'Next'}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Onboarding;
