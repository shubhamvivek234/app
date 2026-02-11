import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import axios from 'axios';

const Onboarding = () => {
  const navigate = useNavigate();
  const [selectedType, setSelectedType] = useState('');
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
      const apiUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

      await axios.patch(
        `${apiUrl}/api/auth/me`,
        { user_type: selectedType, onboarding_completed: false },
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
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="max-w-2xl w-full">
        {/* Progress Indicator */}
        <div className="flex items-center justify-center mb-12">
          <div className="flex items-center space-x-4">
            <div className="flex items-center">
              <div className="w-8 h-8 rounded-full bg-green-500 text-white flex items-center justify-center font-semibold">
                1
              </div>
            </div>
            <div className="w-16 h-1 bg-gray-300"></div>
            <div className="flex items-center">
              <div className="w-8 h-8 rounded-full bg-gray-300 text-gray-600 flex items-center justify-center font-semibold">
                2
              </div>
            </div>
            <div className="w-16 h-1 bg-gray-300"></div>
            <div className="flex items-center">
              <div className="w-8 h-8 rounded-full bg-gray-300 text-gray-600 flex items-center justify-center font-semibold">
                3
              </div>
            </div>
          </div>
        </div>

        {/* Logo */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-slate-900">CrossPost</h1>
        </div>

        {/* Content */}
        <div className="bg-white rounded-xl shadow-sm border border-border p-8">
          <p className="text-green-500 text-sm mb-2">almost ready</p>
          <h2 className="text-3xl font-bold text-slate-900 mb-8">what sounds most like you?</h2>

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

          <div className="mt-8 flex justify-end">
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
  );
};

export default Onboarding;
