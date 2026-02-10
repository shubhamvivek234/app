import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import axios from 'axios';
import { FaCheck } from 'react-icons/fa';

const OnboardingPricing = () => {
  const navigate = useNavigate();
  const [billingCycle, setBillingCycle] = useState('monthly');
  const [showFreeTrial, setShowFreeTrial] = useState(true);
  const [loading, setLoading] = useState(false);

  const plans = [
    {
      id: 'creator',
      name: 'Creator',
      badge: 'Most popular',
      badgeColor: 'bg-green-500',
      description: 'Best for growing creators',
      monthlyPrice: 29,
      yearlyPrice: 290,
      features: [
        '15 connected social accounts',
        'Multiple accounts per platform',
        'Unlimited posts',
        'Schedule posts',
        'Carousel posts',
        'Bulk video scheduling',
        'Content studio access',
        'API add-on available',
        'Human support',
      ],
    },
    {
      id: 'pro',
      name: 'Pro',
      badge: 'Best deal',
      badgeColor: 'bg-green-500',
      description: 'Best for scaling brands',
      monthlyPrice: 49,
      yearlyPrice: 490,
      features: [
        'Unlimited connected accounts',
        'Multiple accounts per platform',
        'Unlimited posts',
        'Schedule posts',
        'Carousel posts',
        'Bulk video scheduling',
        'Content studio access',
        'API add-on available',
        'Viral growth consulting',
        'Priority human support',
        'Invite team members',
      ],
    },
  ];

  const handleSelectPlan = async (planId) => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

      // Update user's onboarding as completed
      await axios.patch(
        `${apiUrl}/api/auth/me`,
        { onboarding_completed: true },
        {
          headers: { Authorization: `Bearer ${token}` },
          withCredentials: true,
        }
      );

      // Navigate to payment page with selected plan
      navigate(`/payment?plan=${planId}`);
    } catch (error) {
      console.error('Error:', error);
      toast.error('Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    navigate('/onboarding/connect');
  };

  const getPrice = (plan) => {
    if (billingCycle === 'monthly') {
      return `$${plan.monthlyPrice}`;
    } else {
      return `$${Math.floor(plan.yearlyPrice / 12)}`;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-12">
      <div className="max-w-6xl w-full">
        {/* Progress Indicator */}
        <div className="flex items-center justify-center mb-12">
          <div className="flex items-center space-x-4">
            <div className="flex items-center">
              <div className="w-8 h-8 rounded-full bg-green-500 text-white flex items-center justify-center font-semibold">
                ✓
              </div>
            </div>
            <div className="w-16 h-1 bg-green-500"></div>
            <div className="flex items-center">
              <div className="w-8 h-8 rounded-full bg-green-500 text-white flex items-center justify-center font-semibold">
                ✓
              </div>
            </div>
            <div className="w-16 h-1 bg-green-500"></div>
            <div className="flex items-center">
              <div className="w-8 h-8 rounded-full bg-green-500 text-white flex items-center justify-center font-semibold">
                3
              </div>
            </div>
          </div>
        </div>

        {/* Logo */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-slate-900">post bridge</h1>
        </div>

        {/* Header */}
        <div className="text-center mb-8">
          <h2 className="text-4xl font-bold text-gray-900 mb-3">Choose your plan</h2>
          <p className="text-gray-600 text-lg">Try for free for 7 days - cancel anytime</p>
        </div>

        {/* Billing Toggle */}
        <div className="flex items-center justify-center mb-10">
          <div className="inline-flex items-center bg-white rounded-full p-1 border border-gray-200 shadow-sm">
            <button
              onClick={() => setBillingCycle('monthly')}
              className={`px-8 py-2 rounded-full text-sm font-medium transition-all ${
                billingCycle === 'monthly'
                  ? 'bg-green-500 text-white'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Monthly
            </button>
            <button
              onClick={() => setBillingCycle('yearly')}
              className={`px-8 py-2 rounded-full text-sm font-medium transition-all relative ${
                billingCycle === 'yearly'
                  ? 'bg-green-500 text-white'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Yearly
              <span className="absolute -top-6 left-1/2 transform -translate-x-1/2 bg-red-500 text-white text-xs px-2 py-1 rounded-full whitespace-nowrap">
                1 month free
              </span>
            </button>
            <label className="flex items-center ml-6 cursor-pointer">
              <input
                type="checkbox"
                checked={showFreeTrial}
                onChange={(e) => setShowFreeTrial(e.target.checked)}
                className="sr-only peer"
              />
              <div className="relative w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-green-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-500"></div>
              <span className="ml-3 text-sm font-medium text-gray-700">Free trial</span>
            </label>
          </div>
        </div>

        {/* Pricing Cards */}
        <div className="grid md:grid-cols-2 gap-6 mb-8">
          {plans.map((plan) => (
            <div
              key={plan.id}
              className="bg-white rounded-2xl p-8 border-2 border-green-500 shadow-lg relative"
            >
              {/* Badge */}
              <div className="absolute -top-3 left-8">
                <span className={`${plan.badgeColor} text-white text-xs font-semibold px-3 py-1 rounded-full`}>
                  {plan.badge}
                </span>
              </div>

              {/* Plan Name */}
              <h3 className="text-2xl font-bold text-gray-900 mb-2">{plan.name}</h3>
              <p className="text-gray-600 text-sm mb-6">{plan.description}</p>

              {/* Price */}
              <div className="mb-6">
                <span className="text-5xl font-bold text-gray-900">{getPrice(plan)}</span>
                <span className="text-gray-600 text-lg">/month</span>
              </div>

              {/* Features */}
              <ul className="space-y-3 mb-8">
                {plan.features.map((feature, index) => (
                  <li key={index} className="flex items-start">
                    <FaCheck className="text-green-500 mt-1 mr-3 flex-shrink-0" />
                    <span className="text-gray-700 text-sm">{feature}</span>
                  </li>
                ))}
              </ul>

              {/* CTA Button */}
              <Button
                onClick={() => handleSelectPlan(plan.id)}
                disabled={loading}
                className="w-full bg-green-500 hover:bg-green-600 text-white py-4 rounded-full text-base font-semibold"
              >
                Start 7 day free trial →
              </Button>

              {/* Footer Text */}
              <div className="flex items-center justify-center mt-4 text-sm text-gray-500">
                <FaCheck className="text-green-500 mr-2" />
                $0.00 due today, cancel anytime
              </div>
            </div>
          ))}
        </div>

        {/* Navigation */}
        <div className="flex justify-center">
          <Button variant="ghost" onClick={handleBack} className="text-gray-600">
            ← Back
          </Button>
        </div>
      </div>
    </div>
  );
};

export default OnboardingPricing;