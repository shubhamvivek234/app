import React, { useEffect, useState } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { createCheckout, getPaymentStatus } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { FaCheckCircle, FaCreditCard } from 'react-icons/fa';
import { format } from 'date-fns';

const Billing = () => {
  const { user, refreshUser } = useAuth();
  const [loading, setLoading] = useState(false);
  const [checkingStatus, setCheckingStatus] = useState(false);

  useEffect(() => {
    // Check for payment status in URL
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get('session_id');
    if (sessionId) {
      checkPaymentStatus(sessionId);
    }
  }, []);

  const checkPaymentStatus = async (sessionId) => {
    setCheckingStatus(true);
    try {
      let attempts = 0;
      const maxAttempts = 5;
      
      const pollStatus = async () => {
        if (attempts >= maxAttempts) {
          toast.error('Payment verification timed out. Please refresh the page.');
          setCheckingStatus(false);
          return;
        }

        const status = await getPaymentStatus(sessionId);
        
        if (status.payment_status === 'paid') {
          toast.success('Payment successful! Your subscription is now active.');
          await refreshUser();
          setCheckingStatus(false);
          // Clear URL params
          window.history.replaceState({}, document.title, window.location.pathname);
          return;
        }

        attempts++;
        setTimeout(pollStatus, 2000);
      };

      await pollStatus();
    } catch (error) {
      toast.error('Failed to verify payment');
      setCheckingStatus(false);
    }
  };

  const handleSubscribe = async (plan, paymentMethod) => {
    setLoading(true);
    try {
      const response = await createCheckout(plan, paymentMethod);
      window.location.href = response.url;
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create checkout');
      setLoading(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Billing & Subscription</h1>
          <p className="text-base text-slate-600 mt-1">Manage your subscription and payments</p>
        </div>

        {checkingStatus && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <p className="text-sm text-blue-800">Verifying your payment...</p>
          </div>
        )}

        {/* Current Subscription */}
        <div className="bg-white rounded-lg border border-border p-6">
          <h2 className="text-xl font-semibold text-slate-900 mb-4">Current Plan</h2>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                user?.subscription_status === 'active'
                  ? 'bg-green-100 text-green-700'
                  : 'bg-slate-100 text-slate-700'
              }`}>
                {user?.subscription_status === 'active' ? 'Active' : 'Free'}
              </span>
              {user?.subscription_plan && (
                <span className="text-slate-600 capitalize">{user.subscription_plan} Plan</span>
              )}
            </div>
            {user?.subscription_end_date && (
              <p className="text-sm text-slate-600">
                Your subscription {user.subscription_status === 'active' ? 'renews' : 'expired'} on{' '}
                {format(new Date(user.subscription_end_date), 'MMMM d, yyyy')}
              </p>
            )}
          </div>
        </div>

        {/* Pricing Plans */}
        <div>
          <h2 className="text-xl font-semibold text-slate-900 mb-6">Available Plans</h2>
          <div className="grid md:grid-cols-2 gap-6">
            {/* Monthly Plan */}
            <div className="bg-white rounded-lg border border-border p-8 space-y-6">
              <div>
                <h3 className="text-2xl font-semibold text-slate-900">Monthly</h3>
                <div className="mt-4 flex items-baseline">
                  <span className="text-4xl font-semibold text-slate-900">₹500</span>
                  <span className="ml-2 text-slate-600">/month</span>
                </div>
              </div>
              <ul className="space-y-3">
                <li className="flex items-center gap-2 text-slate-600">
                  <FaCheckCircle className="text-indigo-600" />
                  Connect 3 social accounts
                </li>
                <li className="flex items-center gap-2 text-slate-600">
                  <FaCheckCircle className="text-indigo-600" />
                  Unlimited posts
                </li>
                <li className="flex items-center gap-2 text-slate-600">
                  <FaCheckCircle className="text-indigo-600" />
                  Schedule posts
                </li>
                <li className="flex items-center gap-2 text-slate-600">
                  <FaCheckCircle className="text-indigo-600" />
                  AI content generation
                </li>
              </ul>
              <div className="space-y-2">
                <Button
                  className="w-full"
                  onClick={() => handleSubscribe('monthly', 'stripe')}
                  disabled={loading || user?.subscription_status === 'active'}
                  data-testid="subscribe-monthly-stripe"
                >
                  <FaCreditCard className="mr-2" />
                  Pay with Stripe
                </Button>
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => handleSubscribe('monthly', 'razorpay')}
                  disabled={loading || user?.subscription_status === 'active'}
                  data-testid="subscribe-monthly-razorpay"
                >
                  Pay with Razorpay
                </Button>
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => handleSubscribe('monthly', 'paypal')}
                  disabled={loading || user?.subscription_status === 'active'}
                  data-testid="subscribe-monthly-paypal"
                >
                  Pay with PayPal
                </Button>
              </div>
            </div>

            {/* Yearly Plan */}
            <div className="bg-indigo-600 text-white rounded-lg border border-indigo-700 p-8 space-y-6 relative">
              <div className="absolute -top-3 right-8 bg-rose-500 text-white text-xs font-medium px-3 py-1 rounded-full">
                Best Value
              </div>
              <div>
                <h3 className="text-2xl font-semibold">Yearly</h3>
                <div className="mt-4 flex items-baseline">
                  <span className="text-4xl font-semibold">₹3,000</span>
                  <span className="ml-2 text-indigo-200">/year</span>
                </div>
                <p className="text-sm text-indigo-200 mt-2">Save ₹3,000 per year</p>
              </div>
              <ul className="space-y-3">
                <li className="flex items-center gap-2">
                  <FaCheckCircle />
                  Everything in Monthly
                </li>
                <li className="flex items-center gap-2">
                  <FaCheckCircle />
                  50% discount
                </li>
                <li className="flex items-center gap-2">
                  <FaCheckCircle />
                  Priority support
                </li>
                <li className="flex items-center gap-2">
                  <FaCheckCircle />
                  Early access to features
                </li>
              </ul>
              <div className="space-y-2">
                <Button
                  className="w-full bg-white text-indigo-600 hover:bg-gray-100"
                  onClick={() => handleSubscribe('yearly', 'stripe')}
                  disabled={loading || user?.subscription_status === 'active'}
                  data-testid="subscribe-yearly-stripe"
                >
                  <FaCreditCard className="mr-2" />
                  Pay with Stripe
                </Button>
                <Button
                  variant="outline"
                  className="w-full border-white text-white hover:bg-indigo-700"
                  onClick={() => handleSubscribe('yearly', 'razorpay')}
                  disabled={loading || user?.subscription_status === 'active'}
                  data-testid="subscribe-yearly-razorpay"
                >
                  Pay with Razorpay
                </Button>
                <Button
                  variant="outline"
                  className="w-full border-white text-white hover:bg-indigo-700"
                  onClick={() => handleSubscribe('yearly', 'paypal')}
                  disabled={loading || user?.subscription_status === 'active'}
                  data-testid="subscribe-yearly-paypal"
                >
                  Pay with PayPal
                </Button>
              </div>
            </div>
          </div>
        </div>

        {/* Payment Info */}
        <div className="bg-slate-50 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-slate-900 mb-3">Payment Information</h3>
          <div className="space-y-2 text-sm text-slate-600">
            <p>• All payments are secure and encrypted</p>
            <p>• You can cancel your subscription anytime</p>
            <p>• Refunds available within 7 days of purchase</p>
            <p className="mt-4 text-amber-700">
              <strong>Note:</strong> Razorpay requires you to add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to backend/.env
            </p>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Billing;