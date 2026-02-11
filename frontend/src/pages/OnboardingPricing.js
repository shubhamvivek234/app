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
      id: 'monthly',
      name: 'Monthly',
      badge: 'Flexible',
      badgeColor: 'bg-gray-500',
      description: 'Perfect for getting started',
      price: 500,
      currency: '₹',
      period: '/month',
      features: [
        'Connect 3 social accounts',
        'Unlimited posts',
        'Schedule posts',
        'AI content generation',
        'Basic analytics',
        'Email support',
      ],
    },
    {
      id: 'yearly',
      name: 'Yearly',
      badge: 'Best Value',
      badgeColor: 'bg-rose-500',
      description: 'Save big with annual billing',
      price: 3000,
      currency: '₹',
      period: '/year',
      features: [
        'Everything in Monthly',
        '50% discount',
        'Priority support',
        'Early access to features',
        'Advanced analytics',
        'Connect 10 social accounts',
      ],
    },
  ];

  const handleSelectPlan = async (planId) => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

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
    return `${plan.currency}${plan.price}`;
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-12">
      <div className="max-w-6xl w-full">
        {/* Progress Indicator */}
        <div className="flex items-center justify-center mb-12">
          <div className="flex items-center space-x-4">
            <div className="flex items-center">
              <div className="w-8 h-8 rounded-full bg-indigo-500 text-white flex items-center justify-center font-semibold">
                ✓
              </div>
            </div>
            <div className="w-16 h-1 bg-indigo-500"></div>
            <div className="flex items-center">
              <div className="w-8 h-8 rounded-full bg-indigo-500 text-white flex items-center justify-center font-semibold">
                ✓
              </div>
            </div>
            <div className="w-16 h-1 bg-indigo-500"></div>
            <div className="flex items-center">
              <div className="w-8 h-8 rounded-full bg-indigo-500 text-white flex items-center justify-center font-semibold">
                3
              </div>
            </div>
          </div>
        </div>

        {/* Logo */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-slate-900">CrossPost</h1>
        </div>

        {/* Header */}
        <div className="text-center mb-8">
          <h2 className="text-4xl font-bold text-gray-900 mb-3">Choose your plan</h2>
          <p className="text-gray-600 text-lg">Try for free for 7 days - cancel anytime</p>
        </div>

        {/* Billing Toggle Removed - Plans have fixed periods */}
        <div className="mb-8"></div>

        {/* Pricing Cards */}
        <div className="grid md:grid-cols-2 gap-6 mb-8">
          {plans.map((plan) => (
            <div
              key={plan.id}
              className="bg-white rounded-2xl p-8 border-2 border-indigo-500 shadow-lg relative"
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
                <span className="text-gray-600 text-lg">{plan.period}</span>
              </div>

              {/* Features */}
              <ul className="space-y-3 mb-8">
                {plan.features.map((feature, index) => (
                  <li key={index} className="flex items-start">
                    <FaCheck className="text-indigo-500 mt-1 mr-3 flex-shrink-0" />
                    <span className="text-gray-700 text-sm">{feature}</span>
                  </li>
                ))}
              </ul>

              {/* CTA Button */}
              <Button
                onClick={() => handleSelectPlan(plan.id)}
                disabled={loading}
                className="w-full bg-indigo-500 hover:bg-indigo-600 text-white py-4 rounded-full text-base font-semibold"
              >
                Start 7 day free trial →
              </Button>

              {/* Footer Text */}
              <div className="flex items-center justify-center mt-4 text-sm text-gray-500">
                <FaCheck className="text-indigo-500 mr-2" />
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