import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import axios from 'axios';
import { loadStripe } from '@stripe/stripe-js';

const PaymentPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const plan = searchParams.get('plan') || 'creator';
  const [paymentMethod, setPaymentMethod] = useState('stripe');
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
    creator: {
      name: 'Creator',
      price: 29,
      trialDays: 7,
    },
    pro: {
      name: 'Pro',
      price: 49,
      trialDays: 7,
    },
  };

  const selectedPlan = plans[plan];
  const tax = (selectedPlan.price * 0.1).toFixed(2);
  const total = (selectedPlan.price + parseFloat(tax)).toFixed(2);
  const trialEndDate = new Date(Date.now() + selectedPlan.trialDays * 24 * 60 * 60 * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      navigate('/login');
    }
  }, [navigate]);

  const handleStripePayment = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

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
      const apiUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

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
          name: 'post bridge',
          description: `${selectedPlan.name} Plan`,
          order_id: response.data.order_id,
          handler: function (response) {
            toast.success('Payment successful!');
            navigate('/dashboard');
          },
          prefill: {
            email: email,
            name: cardholderName,
          },
          theme: {
            color: '#10b981',
          },
        };

        const rzp = new window.Razorpay(options);
        rzp.open();
      }
    } catch (error) {
      console.error('Payment error:', error);
      toast.error('Failed to initiate payment');
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
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
          {/* Left Column - Trial Details */}
          <div className="bg-white rounded-lg p-8 border border-gray-200 h-fit">
            <h2 className="text-2xl font-bold text-gray-900 mb-6">
              Try post bridge {selectedPlan.name.toLowerCase()}
            </h2>

            <div className="space-y-4">
              <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                <p className="text-green-800 font-semibold text-lg">{selectedPlan.trialDays} days free</p>
                <p className="text-green-600 text-sm mt-1">
                  Then US${selectedPlan.price}.00 per month starting {trialEndDate}
                </p>
              </div>

              <div className="border-t border-gray-200 pt-4 space-y-3">
                <div className="flex justify-between text-gray-700">
                  <span>Subtotal</span>
                  <span>${selectedPlan.price}.00</span>
                </div>
                <div className="flex justify-between text-gray-700">
                  <span>Tax</span>
                  <span>${tax}</span>
                </div>
                <div className="flex justify-between text-lg font-semibold text-gray-900 border-t border-gray-200 pt-3">
                  <span>Total due today</span>
                  <span>$0.00</span>
                </div>
                <div className="flex justify-between text-sm text-gray-600">
                  <span>Total after trial</span>
                  <span>${total}</span>
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
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  className="mt-1"
                />
              </div>

              {/* Payment Method Selection */}
              <div>
                <Label className="text-sm font-medium mb-3 block">Payment Method</Label>
                <div className="space-y-2">
                  <button
                    type="button"
                    onClick={() => setPaymentMethod('stripe')}
                    className={`w-full text-left px-4 py-3 border-2 rounded-lg transition-all ${
                      paymentMethod === 'stripe'
                        ? 'border-green-500 bg-green-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">Credit / Debit Card</span>
                      <span className="text-sm text-gray-500">Stripe</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => setPaymentMethod('razorpay')}
                    className={`w-full text-left px-4 py-3 border-2 rounded-lg transition-all ${
                      paymentMethod === 'razorpay'
                        ? 'border-green-500 bg-green-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">UPI / Cards / Net Banking</span>
                      <span className="text-sm text-gray-500">Razorpay</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => setPaymentMethod('paypal')}
                    className={`w-full text-left px-4 py-3 border-2 rounded-lg transition-all ${
                      paymentMethod === 'paypal'
                        ? 'border-green-500 bg-green-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">PayPal</span>
                      <span className="text-sm text-gray-500">PayPal</span>
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
                {loading ? 'Processing...' : 'Start trial'}
              </Button>

              {/* Footer Links */}
              <div className="text-center text-xs text-gray-500 space-x-2">
                <span>Powered by {paymentMethod === 'stripe' ? 'Stripe' : paymentMethod === 'razorpay' ? 'Razorpay' : 'PayPal'}</span>
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