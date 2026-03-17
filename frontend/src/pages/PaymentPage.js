import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import axios from 'axios';
import { loadStripe } from '@stripe/stripe-js';

import { useAuth } from '@/context/AuthContext';

const PaymentPage = () => {
  const navigate = useNavigate();
  const { user, token } = useAuth(); // Get user and token from context
  const [searchParams] = useSearchParams();
  const plan = searchParams.get('plan') || 'monthly';
  const [paymentMethod, setPaymentMethod] = useState('razorpay');
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState('');
  const [cardNumber, setCardNumber] = useState('');
  const [expiry, setExpiry] = useState('');
  const [cvc, setCvc] = useState('');
  const [cardholderName, setCardholderName] = useState('');
  const [country, setCountry] = useState('US');
  const [saveInfo, setSaveInfo] = useState(false);
  const [businessPurchase, setBusinessPurchase] = useState(false);
  const [promoCode, setPromoCode] = useState('');
  const [showPromo, setShowPromo] = useState(false);

  const plans = {
    monthly: {
      name: 'Monthly',
      price: 500,
      currency: '₹',
      trialDays: 7,
    },
    yearly: {
      name: 'Yearly',
      price: 3000,
      currency: '₹',
      trialDays: 7,
    },
  };

  const selectedPlan = plans[plan];
  const tax = (selectedPlan.price * 0.1).toFixed(2);
  const total = (selectedPlan.price + parseFloat(tax)).toFixed(2);
  const trialEndDate = new Date(Date.now() + selectedPlan.trialDays * 24 * 60 * 60 * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

  useEffect(() => {
    if (!token) {
      navigate('/login');
    }
    if (user && user.email) {
      setEmail(user.email);
    }
  }, [navigate, user, token]);

  const handleStripePayment = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_BACKEND_URL || '';

      const response = await axios.post(
        `${apiUrl}/api/payments/checkout`,
        {
          plan: plan,
          payment_method: 'stripe',
        },
        {
          headers: { Authorization: `Bearer ${token}` },
          withCredentials: true,
        }
      );

      if (response.data.checkout_url) {
        window.location.href = response.data.checkout_url;
      }
    } catch (error) {
      console.error('Payment error:', error);
      toast.error('Failed to initiate payment');
    } finally {
      setLoading(false);
    }
  };

  const handleRazorpayPayment = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_BACKEND_URL || '';

      const response = await axios.post(
        `${apiUrl}/api/payments/checkout`,
        {
          plan: plan,
          payment_method: 'razorpay',
        },
        {
          headers: { Authorization: `Bearer ${token}` },
          withCredentials: true,
        }
      );

      if (response.data.order_id) {
        const options = {
          key: response.data.razorpay_key,
          amount: selectedPlan.price * 100,
          currency: 'INR',
          name: 'SocialEntangler',
          description: `${selectedPlan.name} Plan`,
          order_id: response.data.order_id,
          handler: async function (response) {
            try {
              setLoading(true);
              // Verify payment on backend
              const verifyResponse = await axios.post(
                `${apiUrl}/api/payments/verify-razorpay`,
                {
                  order_id: response.razorpay_order_id,
                  payment_id: response.razorpay_payment_id,
                  signature: response.razorpay_signature,
                },
                {
                  headers: { Authorization: `Bearer ${token}` },
                }
              );

              if (verifyResponse.data.status === 'success') {
                // Update onboarding status
                await axios.patch(
                  `${apiUrl}/api/auth/me`,
                  { onboarding_completed: true },
                  {
                    headers: { Authorization: `Bearer ${token}` },
                    withCredentials: true,
                  }
                );

                toast.success('Payment successful!');
                navigate('/dashboard');
              }
            } catch (error) {
              console.error('Verification error:', error);
              toast.error('Payment verification failed');
            } finally {
              setLoading(false);
            }
          },
          prefill: {
            email: email,
            name: cardholderName,
          },
          theme: {
            color: '#6569f0',
          },
          modal: {
            ondismiss: function () {
              setLoading(false);
              toast('Payment cancelled');
            },
          },
        };

        if (!window.Razorpay) {
          console.error('Razorpay SDK not loaded');
          toast.error('Payment system not loaded. Please refresh.');
          return;
        }

        const rzp = new window.Razorpay(options);

        rzp.on('payment.failed', function (response) {
          console.error('Payment Failed:', response.error);
          toast.error(`Payment Failed: ${response.error.description || 'Reason unknown'}`);
          // You can also log this to your backend
        });

        rzp.open();
      }
    } catch (error) {
      console.error('Payment error full details:', error);
      if (error.response) {
        console.error('Response data:', error.response.data);
        console.error('Response status:', error.response.status);
        toast.error(`Payment failed: ${error.response.data.detail || 'Unknown server error'}`);
      } else {
        console.error('Error:', error.message);
        toast.error('Failed to initiate payment. Check console for details.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handlePayPalPayment = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

      const response = await axios.post(
        `${apiUrl}/api/payments/checkout`,
        {
          plan: plan,
          payment_method: 'paypal',
        },
        {
          headers: { Authorization: `Bearer ${token}` },
          withCredentials: true,
        }
      );

      if (response.data.approval_url) {
        window.location.href = response.data.approval_url;
      }
    } catch (error) {
      console.error('Payment error:', error);
      toast.error('Failed to initiate payment');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    if (paymentMethod === 'stripe') {
      handleStripePayment();
    } else if (paymentMethod === 'razorpay') {
      handleRazorpayPayment();
    } else if (paymentMethod === 'paypal') {
      handlePayPalPayment();
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <Button variant="ghost" onClick={() => navigate('/onboarding/pricing')} className="text-gray-600">
            ← Back to Pricing
          </Button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
          {/* Left Column - Trial Details */}
          <div className="bg-white rounded-lg p-8 border border-gray-200 h-fit">
            <h2 className="text-2xl font-bold text-gray-900 mb-6">
              Try SocialEntangler {selectedPlan.name.toLowerCase()}
            </h2>

            <div className="space-y-4">
              <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                <p className="text-green-800 font-semibold text-lg">{selectedPlan.trialDays} days free</p>
                <p className="text-green-600 text-sm mt-1">
                  Then ₹{selectedPlan.price}.00 per month starting {trialEndDate}
                </p>
              </div>

              <div className="border-t border-gray-200 pt-4 space-y-3">
                <div className="flex justify-between text-gray-700">
                  <span>Subtotal</span>
                  <span>₹{selectedPlan.price}.00</span>
                </div>
                <div className="flex justify-between text-gray-700">
                  <span>Tax</span>
                  <span>₹{tax}</span>
                </div>
                <div className="flex justify-between text-lg font-semibold text-gray-900 border-t border-gray-200 pt-3">
                  <span>Total due today</span>
                  <span>₹0.00</span>
                </div>
                <div className="flex justify-between text-sm text-gray-600">
                  <span>Total after trial</span>
                  <span>₹{total}</span>
                </div>
              </div>

              {!showPromo && (
                <button
                  onClick={() => setShowPromo(true)}
                  className="text-green-600 hover:text-green-700 text-sm font-medium"
                >
                  Add promotion code
                </button>
              )}

              {showPromo && (
                <div className="flex space-x-2">
                  <Input
                    value={promoCode}
                    onChange={(e) => setPromoCode(e.target.value)}
                    placeholder="Enter code"
                    className="flex-1"
                  />
                  <Button variant="outline">Apply</Button>
                </div>
              )}
            </div>
          </div>

          {/* Right Column - Payment Form */}
          <div className="bg-white rounded-lg p-8 border border-gray-200">
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Email */}
              <div>
                <Label htmlFor="email" className="text-sm font-medium">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  readOnly
                  disabled
                  placeholder="you@example.com"
                  required
                  className="mt-1 bg-gray-100 cursor-not-allowed"
                />
              </div>

              {/* Payment Method Selection */}
              <div>
                <Label className="text-sm font-medium mb-3 block">Payment Method</Label>
                <div className="space-y-2">
                  <button
                    type="button"
                    className="w-full text-left px-4 py-3 border-2 rounded-lg transition-all border-green-500 bg-green-50"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">UPI / Cards / Net Banking</span>
                      <span className="text-sm text-gray-500">Razorpay</span>
                    </div>
                  </button>
                </div>
              </div>

              {paymentMethod === 'stripe' && (
                <>
                  {/* Card Details */}
                  <div>
                    <Label htmlFor="cardNumber" className="text-sm font-medium">Card information</Label>
                    <div className="mt-1 space-y-2">
                      <Input
                        id="cardNumber"
                        type="text"
                        value={cardNumber}
                        onChange={(e) => setCardNumber(e.target.value)}
                        placeholder="1234 1234 1234 1234"
                        maxLength="19"
                        required
                      />
                      <div className="grid grid-cols-2 gap-2">
                        <Input
                          type="text"
                          value={expiry}
                          onChange={(e) => setExpiry(e.target.value)}
                          placeholder="MM / YY"
                          maxLength="7"
                          required
                        />
                        <Input
                          type="text"
                          value={cvc}
                          onChange={(e) => setCvc(e.target.value)}
                          placeholder="CVC"
                          maxLength="4"
                          required
                        />
                      </div>
                    </div>
                  </div>

                  {/* Cardholder Name */}
                  <div>
                    <Label htmlFor="cardholderName" className="text-sm font-medium">Full name on card</Label>
                    <Input
                      id="cardholderName"
                      type="text"
                      value={cardholderName}
                      onChange={(e) => setCardholderName(e.target.value)}
                      placeholder="John Doe"
                      required
                      className="mt-1"
                    />
                  </div>

                  {/* Country */}
                  <div>
                    <Label htmlFor="country" className="text-sm font-medium">Country or region</Label>
                    <select
                      id="country"
                      value={country}
                      onChange={(e) => setCountry(e.target.value)}
                      className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-green-500 focus:outline-none focus:ring-1 focus:ring-green-500"
                      required
                    >
                      <option value="US">United States</option>
                      <option value="IN">India</option>
                      <option value="GB">United Kingdom</option>
                      <option value="CA">Canada</option>
                      <option value="AU">Australia</option>
                    </select>
                  </div>
                </>
              )}

              {/* Checkboxes */}
              <div className="space-y-3">
                <label className="flex items-start space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={saveInfo}
                    onChange={(e) => setSaveInfo(e.target.checked)}
                    className="mt-1 rounded border-gray-300 text-green-600 focus:ring-green-500"
                  />
                  <span className="text-sm text-gray-700">Save my information for faster checkout</span>
                </label>

                <label className="flex items-start space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={businessPurchase}
                    onChange={(e) => setBusinessPurchase(e.target.checked)}
                    className="mt-1 rounded border-gray-300 text-green-600 focus:ring-green-500"
                  />
                  <span className="text-sm text-gray-700">I'm purchasing as a business</span>
                </label>
              </div>

              {/* Submit Button */}
              <Button
                type="submit"
                disabled={loading}
                className="w-full bg-green-500 hover:bg-green-600 text-white py-3 text-base font-semibold"
              >
                {loading ? 'Processing...' : 'Initiate Payment'}
              </Button>

              <div className="mt-6 text-center">
                <p className="text-sm text-gray-400 mb-2">Trusted by 10,000+ creators</p>
                <span className="font-bold text-lg text-gray-600">SocialEntangler</span>
              </div>

              {/* Footer Links */}
              <div className="text-center text-xs text-gray-500 space-x-2 mt-4">
                <span>Powered by Razorpay</span>
                <span>•</span>
                <a href="/terms" className="hover:text-gray-700">Terms</a>
                <span>•</span>
                <a href="/privacy" className="hover:text-gray-700">Privacy</a>
                <span>•</span>
                <a href="#" className="hover:text-gray-700">Refunds</a>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PaymentPage;