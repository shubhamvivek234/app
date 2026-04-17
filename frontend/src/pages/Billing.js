import React, { useEffect, useState } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { createCheckout, getPaymentStatus, completeOnboarding } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';
import { format } from 'date-fns';

// ─── Plan Definitions ────────────────────────────────────────────────────────
const PLANS = [
  {
    id: 'starter',
    name: 'Starter',
    badge: null,
    tagline: 'Perfect for getting started',
    monthlyPrice: 12,
    annualPrice: 9,
    annualTotal: 108,
    features: [
      '5 social accounts',
      '60 posts per month',
      'Full scheduling & queue',
      '30 AI generations/month',
      'AI hashtag generator',
      '5 saved hashtag groups',
      'Image uploads (10 MB)',
      'Auto-retry on failed posts',
      'Email support (72h)',
    ],
  },
  {
    id: 'creator',
    name: 'Creator',
    badge: 'Most Popular',
    tagline: 'For serious content creators',
    monthlyPrice: 25,
    annualPrice: 19,
    annualTotal: 228,
    highlight: true,
    features: [
      '15 social accounts',
      'Unlimited posts',
      '150 AI generations/month',
      'Video & image uploads (500 MB)',
      'Bulk CSV upload (100 posts/batch)',
      'Basic analytics dashboard',
      'AI hashtag generator (unlimited)',
      '20 saved hashtag groups',
      'Read-only API + MCP integration',
      'Email support (48h)',
    ],
  },
  {
    id: 'business',
    name: 'Business',
    badge: 'Best Value',
    tagline: 'For teams & agencies',
    monthlyPrice: 49,
    annualPrice: 38,
    annualTotal: 456,
    features: [
      'Unlimited social accounts',
      'Unlimited posts',
      'Unlimited AI generation',
      'Video & image uploads (2 GB)',
      'Bulk CSV upload (500 posts/batch)',
      'Advanced analytics (per-platform)',
      'Full API access (read + write)',
      '5 team members',
      'Admin dashboard',
      'Priority support (24h)',
    ],
  },
];

const CheckIcon = () => (
  <svg className="w-4 h-4 flex-shrink-0 text-indigo-500" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
  </svg>
);

const Billing = () => {
  const { user, refreshUser } = useAuth();
  const [billing, setBilling] = useState('annual');
  const [loading, setLoading] = useState(null);
  const [checkingStatus, setCheckingStatus] = useState(false);

  const currentPlanId = user?.subscription_plan || null;
  const isActive = user?.subscription_status === 'active';

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get('session_id');
    if (sessionId) checkPaymentStatus(sessionId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const checkPaymentStatus = async (sessionId) => {
    setCheckingStatus(true);
    try {
      let attempts = 0;
      const poll = async () => {
        if (attempts >= 6) { toast.error('Verification timed out — please refresh.'); setCheckingStatus(false); return; }
        const status = await getPaymentStatus(sessionId);
        if (status.payment_status === 'paid') {
          await completeOnboarding();
          toast.success('Payment successful! Your subscription is now active.');
          await refreshUser();
          setCheckingStatus(false);
          window.history.replaceState({}, document.title, window.location.pathname);
          return;
        }
        attempts++;
        setTimeout(poll, 2000);
      };
      await poll();
    } catch (err) {
      toast.error('Failed to verify payment');
      setCheckingStatus(false);
    }
  };

  const handleSubscribe = (planId) => {
    window.location.href = `/payment?plan=${planId}&billing=${billing}`;
  };

  const getPrice = (plan) => billing === 'annual' ? plan.annualPrice : plan.monthlyPrice;

  return (
    <DashboardLayout>
      <div className="max-w-5xl mx-auto space-y-8">

        {/* ── Page Header ─────────────────────────────────────── */}
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Billing & Subscription</h1>
          <p className="text-slate-500 mt-1">Manage your plan and payments</p>
        </div>

        {/* ── Payment Verifying Banner ─────────────────────────── */}
        {checkingStatus && (
          <div className="flex items-center gap-3 bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
            <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
            Verifying your payment, please wait…
          </div>
        )}

        {/* ── Current Plan Card ────────────────────────────────── */}
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-4">Current Plan</h2>
          <div className="flex items-center flex-wrap gap-3">
            <span className={`px-3 py-1 rounded-full text-sm font-semibold ${isActive ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-600'}`}>
              {isActive ? '● Active' : '○ Free Trial / Inactive'}
            </span>
            {currentPlanId && (
              <span className="text-slate-600 capitalize font-medium">{currentPlanId} Plan</span>
            )}
            {user?.subscription_end_date && (
              <span className="text-sm text-slate-500 ml-auto">
                {isActive ? 'Renews' : 'Expired'} on {format(new Date(user.subscription_end_date), 'MMMM d, yyyy')}
              </span>
            )}
          </div>
        </div>

        {/* ── Billing Toggle ───────────────────────────────────── */}
        <div>
          <h2 className="text-xl font-semibold text-slate-900 mb-5">
            {isActive ? 'Upgrade Your Plan' : 'Choose a Plan'}
          </h2>
          <div className="inline-flex items-center bg-slate-100 rounded-full p-1 mb-6">
            <button
              onClick={() => setBilling('monthly')}
              className={`px-5 py-2 rounded-full text-sm font-medium transition-all ${billing === 'monthly' ? 'bg-white text-indigo-700 shadow font-semibold' : 'text-slate-500 hover:text-slate-700'}`}
            >
              Monthly
            </button>
            <button
              onClick={() => setBilling('annual')}
              className={`px-5 py-2 rounded-full text-sm font-medium transition-all flex items-center gap-2 ${billing === 'annual' ? 'bg-white text-indigo-700 shadow font-semibold' : 'text-slate-500 hover:text-slate-700'}`}
            >
              Annual
              <span className="bg-green-100 text-green-700 text-xs font-bold px-2 py-0.5 rounded-full">Save 25%</span>
            </button>
          </div>

          {/* ── Plan Cards ──────────────────────────────────────── */}
          <div className="grid md:grid-cols-3 gap-5">
            {PLANS.map((plan) => {
              const isCurrent = currentPlanId === plan.id && isActive;
              return (
                <div
                  key={plan.id}
                  className={`relative rounded-2xl border-2 flex flex-col transition-transform hover:-translate-y-1 duration-200 overflow-hidden
                    ${plan.highlight
                      ? 'border-indigo-500 bg-gradient-to-br from-indigo-600 to-violet-700 text-white shadow-lg'
                      : 'border-slate-200 bg-white text-slate-900 shadow-sm'}
                  `}
                >
                  {plan.badge && (
                    <div className={`absolute top-0 right-0 text-xs font-bold px-4 py-1 rounded-bl-xl ${plan.highlight ? 'bg-amber-400 text-amber-900' : 'bg-green-500 text-white'}`}>
                      {plan.badge}
                    </div>
                  )}

                  <div className="p-6 flex flex-col flex-1">
                    <h3 className={`text-lg font-bold mb-0.5 ${plan.highlight ? 'text-white' : 'text-slate-900'}`}>{plan.name}</h3>
                    <p className={`text-xs mb-5 ${plan.highlight ? 'text-indigo-200' : 'text-slate-500'}`}>{plan.tagline}</p>

                    <div className="mb-5">
                      <div className="flex items-end gap-1">
                        <span className={`text-4xl font-extrabold ${plan.highlight ? 'text-white' : 'text-slate-900'}`}>${getPrice(plan)}</span>
                        <span className={`text-sm pb-1 ${plan.highlight ? 'text-indigo-200' : 'text-slate-400'}`}>/mo</span>
                      </div>
                      <p className={`text-xs mt-1 ${plan.highlight ? 'text-indigo-300' : 'text-slate-400'}`}>
                        {billing === 'annual'
                          ? `$${plan.annualTotal}/yr · save $${(plan.monthlyPrice - plan.annualPrice) * 12}`
                          : 'billed monthly'}
                      </p>
                    </div>

                    <button
                      onClick={() => handleSubscribe(plan.id)}
                      disabled={isCurrent || loading !== null}
                      className={`w-full py-2.5 rounded-xl text-sm font-semibold mb-6 transition-all duration-150 disabled:opacity-50
                        ${isCurrent
                          ? 'bg-green-100 text-green-700 cursor-default'
                          : plan.highlight
                          ? 'bg-white hover:bg-indigo-50 text-indigo-700'
                          : 'bg-indigo-600 hover:bg-indigo-700 text-white'}
                      `}
                    >
                      {isCurrent ? '✓ Current Plan' : 'Subscribe →'}
                    </button>

                    <ul className="space-y-2 flex-1">
                      {plan.features.map((f, i) => (
                        <li key={i} className={`flex items-start gap-2 text-xs ${plan.highlight ? 'text-indigo-100' : 'text-slate-600'}`}>
                          <svg className={`w-3.5 h-3.5 mt-0.5 flex-shrink-0 ${plan.highlight ? 'text-indigo-200' : 'text-indigo-500'}`} fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                          {f}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Payment Info Footer ──────────────────────────────── */}
        <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Payment Information</h3>
          <div className="flex flex-wrap gap-x-8 gap-y-2 text-xs text-slate-500">
            <span>🔐 256-bit SSL encryption</span>
            <span>💳 Powered by Stripe</span>
            <span>🔄 Cancel anytime, no lock-in</span>
            <span>📧 7-day money-back guarantee</span>
          </div>
        </div>

      </div>
    </DashboardLayout>
  );
};

export default Billing;