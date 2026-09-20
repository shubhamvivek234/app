import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '@/context/AuthContext';
import OnboardingHeader from '@/components/OnboardingHeader';

// ─── Keyframe styles injected once ───────────────────────────────────────────
const ANIMATION_STYLES = `
  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(28px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes fadeIn {
    from { opacity: 0; }
    to   { opacity: 1; }
  }
  @keyframes badgePulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(251,191,36,0.5); }
    50%       { box-shadow: 0 0 0 6px rgba(251,191,36,0); }
  }
  @keyframes shimmer {
    0%   { background-position: -400px 0; }
    100% { background-position: 400px 0; }
  }
  @keyframes glow {
    0%, 100% { box-shadow: 0 0 18px 2px rgba(99,102,241,0.28); }
    50%       { box-shadow: 0 0 32px 6px rgba(139,92,246,0.38); }
  }
  @keyframes floatBadge {
    0%, 100% { transform: translateY(0px); }
    50%       { transform: translateY(-3px); }
  }
  @keyframes priceFlip {
    0%   { opacity: 0; transform: translateY(-8px) scale(0.95); }
    100% { opacity: 1; transform: translateY(0) scale(1); }
  }
  @keyframes trustSlide {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .card-animate {
    opacity: 0;
    animation: fadeUp 0.55s cubic-bezier(0.22,1,0.36,1) forwards;
  }
  .header-animate {
    opacity: 0;
    animation: fadeIn 0.6s ease forwards;
  }
  .price-flip {
    animation: priceFlip 0.25s ease forwards;
  }
  .trust-animate {
    opacity: 0;
    animation: trustSlide 0.5s ease 1.1s forwards;
  }
`;

// ─── Plan Definitions ────────────────────────────────────────────────────────
const PLANS = [
  {
    id: 'starter',
    name: 'Starter',
    badge: 'Solo Creators',
    tagline: 'Perfect for independent creators & podcasters',
    monthlyPrice: 19,
    annualPrice: 16,
    annualTotal: 192,
    highlight: false,
    btnClass: 'bg-indigo-600 hover:bg-indigo-700 text-white',
    features: [
      '6 social accounts',
      '150 posts per month',
      'Twitter: 60 tweets/mo (15 links)',
      '30 min AI video clipping',
      '100 AI content generations/mo',
      '30 AI FLUX images / month',
      'Smart Bio (2 pages) + 500 contacts',
      '10 GB storage (250 MB file)',
      'Developer API & MCP integration',
      'Standard support (24-48h)',
    ],
    notIncluded: ['Custom domains', 'Team members', 'Client portals', 'Auto-plugs'],
  },
  {
    id: 'pro',
    name: 'Pro',
    badge: 'Most Popular',
    tagline: 'For high-output creators, startups & brands',
    monthlyPrice: 45,
    annualPrice: 39,
    annualTotal: 468,
    highlight: true,
    btnClass: 'bg-white hover:bg-indigo-50 text-indigo-700 font-semibold',
    features: [
      '18 social accounts (3 full brands)',
      'Unlimited general social posts',
      'Twitter: 180 tweets/mo (40 links) + BYOK',
      '120 min AI video clipping (~45 shorts)',
      '500 AI content generations/mo',
      '150 AI FLUX images / month',
      'Smart Bio (5 pages + Custom Domain)',
      '5,000 CRM contacts + Deals pipeline',
      'Auto-plugs & staggered cross-posting',
      '50 GB storage + 3 team seats',
      '10 Scoped webhooks + Developer API',
    ],
    notIncluded: ['Client review portals', '50+ social accounts'],
  },
  {
    id: 'agency',
    name: 'Agency / Scale',
    badge: 'Best Value',
    tagline: 'For marketing agencies & autonomous fleets',
    monthlyPrice: 110,
    annualPrice: 99,
    annualTotal: 1188,
    highlight: false,
    dark: true,
    btnClass: 'bg-indigo-500 hover:bg-indigo-600 text-white',
    features: [
      '50 social accounts (8–10 brands)',
      'Unlimited posts & carousels across all networks',
      'Twitter: 500 tweets/mo (120 links)',
      'Twitter BYOK included (unlimited tweets)',
      '400 min AI video clipping (~150 shorts)',
      '2,000 AI content generations/mo',
      '500 AI FLUX images / month',
      'Unlimited Smart Bio pages & domains',
      '50,000 CRM contacts + client pipelines',
      'Client review approval portals',
      '250 GB storage + 10 team seats',
      'Dedicated MCP agent pool + Priority 1h SLA',
    ],
    notIncluded: [],
  },
];

const CheckIcon = ({ inverted }) => (
  <svg className={`w-4 h-4 flex-shrink-0 ${inverted ? 'text-indigo-200' : 'text-indigo-500'}`}
    fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
  </svg>
);

const XIcon = () => (
  <svg className="w-4 h-4 flex-shrink-0 text-slate-300" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
  </svg>
);

const OnboardingPricing = () => {
  const navigate = useNavigate();
  const { token } = useAuth();
  const [billing, setBilling] = useState('annual');
  const [loadingPlan, setLoadingPlan] = useState(null);
  const [priceKey, setPriceKey] = useState(0); // triggers price flip animation
  const [hoveredPlan, setHoveredPlan] = useState(null);
  const styleInjected = useRef(false);

  // Inject keyframes once into document head
  useEffect(() => {
    if (styleInjected.current) return;
    const tag = document.createElement('style');
    tag.textContent = ANIMATION_STYLES;
    document.head.appendChild(tag);
    styleInjected.current = true;
  }, []);

  const handleBillingChange = (cycle) => {
    setBilling(cycle);
    setPriceKey(k => k + 1); // re-trigger price flip
  };

  const getPrice = (plan) => billing === 'annual' ? plan.annualPrice : plan.monthlyPrice;

  const handleSelectPlan = async (planId) => {
    setLoadingPlan(planId);
    try {
      navigate(`/payment?plan=${planId}&billing=${billing}`);
    } catch {
      toast.error('Something went wrong. Please try again.');
    } finally {
      setLoadingPlan(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#f7f8fc] pt-20 pb-16 px-4 overflow-hidden">
      <OnboardingHeader step={3} />

      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="max-w-5xl mx-auto text-center mb-10 header-animate" style={{ animationDelay: '0.05s' }}>
        <span
          className="inline-block bg-indigo-100 text-indigo-700 text-xs font-semibold px-3 py-1 rounded-full mb-4 tracking-wide uppercase"
          style={{
            background: 'linear-gradient(90deg, #e0e7ff 25%, #c7d2fe 50%, #e0e7ff 75%)',
            backgroundSize: '400px 100%',
            animation: 'shimmer 2.2s infinite linear',
          }}
        >
          7-day free trial · No credit card required
        </span>

        <h1
          className="text-4xl sm:text-5xl font-bold text-slate-900 mb-3 header-animate"
          style={{ animationDelay: '0.12s' }}
        >
          Simple, transparent pricing
        </h1>
        <p
          className="text-slate-500 text-lg max-w-xl mx-auto header-animate"
          style={{ animationDelay: '0.22s' }}
        >
          Up to <span className="font-semibold text-indigo-600">3× cheaper</span> than the competition.
        </p>

        {/* ── Billing Toggle ──────────────────────────────────── */}
        <div
          className="mt-8 inline-flex items-center bg-white border border-slate-200 rounded-full p-1 shadow-sm header-animate"
          style={{ animationDelay: '0.32s' }}
        >
          <button
            onClick={() => handleBillingChange('monthly')}
            className={`px-5 py-2 rounded-full text-sm font-medium transition-all duration-250
              ${billing === 'monthly' ? 'bg-indigo-600 text-white shadow' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Monthly
          </button>
          <button
            onClick={() => handleBillingChange('annual')}
            className={`px-5 py-2 rounded-full text-sm font-medium transition-all duration-250 flex items-center gap-2
              ${billing === 'annual' ? 'bg-indigo-600 text-white shadow' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Annual
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full transition-colors duration-200
              ${billing === 'annual' ? 'bg-white text-indigo-600' : 'bg-green-100 text-green-700'}`}>
              Save 25%
            </span>
          </button>
        </div>
      </div>

      {/* ── Pricing Cards ──────────────────────────────────────── */}
      <div className="max-w-5xl mx-auto grid md:grid-cols-3 gap-6 mb-12">
        {PLANS.map((plan, idx) => {
          const isInverted = plan.highlight;
          const isDark = plan.dark;
          const isHovered = hoveredPlan === plan.id;

          return (
            <div
              key={plan.id}
              className="card-animate"
              style={{ animationDelay: `${0.18 + idx * 0.12}s` }}
              onMouseEnter={() => setHoveredPlan(plan.id)}
              onMouseLeave={() => setHoveredPlan(null)}
            >
              <div
                className={`relative rounded-2xl overflow-hidden border-2 flex flex-col h-full
                  transition-transform duration-300 ease-out cursor-default
                  ${isHovered ? '-translate-y-2' : 'translate-y-0'}
                  ${isInverted
                    ? 'border-indigo-500 bg-gradient-to-br from-indigo-600 to-violet-700 text-white'
                    : isDark
                    ? 'border-slate-700 bg-gradient-to-br from-slate-800 to-slate-900 text-white'
                    : 'border-slate-200 bg-white text-slate-900'}
                `}
                style={isInverted ? {
                  animation: 'glow 3s ease-in-out infinite',
                } : {
                  boxShadow: isHovered
                    ? '0 20px 48px rgba(0,0,0,0.13)'
                    : '0 4px 14px rgba(0,0,0,0.07)',
                  transition: 'box-shadow 0.3s ease, transform 0.3s ease',
                }}
              >
                {/* Badge */}
                {plan.badge && (
                  <div
                    className={`absolute top-0 right-0 text-xs font-bold px-4 py-1 rounded-bl-xl
                      ${isInverted ? 'bg-amber-400 text-amber-900' : 'bg-green-500 text-white'}`}
                    style={{ animation: 'floatBadge 2.8s ease-in-out infinite' }}
                  >
                    {plan.badge}
                  </div>
                )}

                {/* Shimmer overlay on Creator card */}
                {isInverted && (
                  <div
                    className="absolute inset-0 pointer-events-none opacity-10 rounded-2xl"
                    style={{
                      background: 'linear-gradient(105deg, transparent 40%, rgba(255,255,255,0.7) 50%, transparent 60%)',
                      backgroundSize: '400px 100%',
                      animation: 'shimmer 2.8s infinite linear',
                    }}
                  />
                )}

                <div className="p-7 flex flex-col flex-1 relative z-10">
                  {/* Plan name & tagline */}
                  <div className="mb-5">
                    <h3 className={`text-xl font-bold mb-1 ${isInverted || isDark ? 'text-white' : 'text-slate-900'}`}>
                      {plan.name}
                    </h3>
                    <p className={`text-sm ${isInverted ? 'text-indigo-200' : isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                      {plan.tagline}
                    </p>
                  </div>

                  {/* Price — re-keyed on billing toggle to trigger flip animation */}
                  <div className="mb-6">
                    <div key={`${priceKey}-${plan.id}`} className="flex items-end gap-1 price-flip">
                      <span className={`text-5xl font-extrabold ${isInverted || isDark ? 'text-white' : 'text-slate-900'}`}>
                        ${getPrice(plan)}
                      </span>
                      <span className={`text-sm pb-2 ${isInverted ? 'text-indigo-200' : isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                        /mo
                      </span>
                    </div>
                    <p className={`text-xs mt-1 ${isInverted ? 'text-indigo-200' : isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                      {billing === 'annual'
                        ? `$${plan.annualTotal} billed annually · save $${(plan.monthlyPrice - plan.annualPrice) * 12}/yr`
                        : 'billed monthly · no commitment'}
                    </p>
                  </div>

                  {/* CTA */}
                  <button
                    onClick={() => handleSelectPlan(plan.id)}
                    disabled={loadingPlan !== null}
                    className={`w-full py-3 rounded-xl text-sm font-semibold mb-7
                      transition-all duration-200 active:scale-95 disabled:opacity-60
                      ${plan.btnClass}`}
                    style={loadingPlan === plan.id ? { opacity: 0.7 } : {}}
                  >
                    {loadingPlan === plan.id
                      ? <span className="flex items-center justify-center gap-2">
                          <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                          </svg>
                          Redirecting…
                        </span>
                      : 'Start 7-day free trial →'
                    }
                  </button>

                  {/* Features */}
                  <ul className="space-y-2.5 flex-1">
                    {plan.features.map((f, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-2.5 text-sm"
                        style={{
                          opacity: 0,
                          animation: `fadeIn 0.3s ease ${0.4 + idx * 0.1 + i * 0.03}s forwards`,
                        }}
                      >
                        <CheckIcon inverted={isInverted || isDark} />
                        <span className={isInverted || isDark ? 'text-indigo-100' : 'text-slate-600'}>{f}</span>
                      </li>
                    ))}
                    {plan.notIncluded.map((f, i) => (
                      <li key={`x-${i}`} className="flex items-start gap-2.5 text-sm opacity-40">
                        <XIcon />
                        <span className={isInverted ? 'text-indigo-200' : isDark ? 'text-slate-500' : 'text-slate-400'}>{f}</span>
                      </li>
                    ))}
                  </ul>

                  <p className={`text-center text-xs mt-6 ${isInverted ? 'text-indigo-300' : isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                    $0.00 due today · Cancel anytime
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Trust Strip ─────────────────────────────────────────── */}
      <div className="max-w-2xl mx-auto text-center trust-animate">
        <p className="text-xs text-slate-400 mb-4">Trusted and secure</p>
        <div className="flex justify-center flex-wrap gap-4 text-xs text-slate-500 font-medium">
          {['🔐 256-bit SSL', '💳 Powered by Stripe', '🔄 Cancel anytime', '📧 7-day money-back'].map((t, i) => (
            <span
              key={t}
              className="bg-white border border-slate-200 rounded-full px-4 py-1.5 shadow-sm
                hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 cursor-default"
            >
              {t}
            </span>
          ))}
        </div>
        <div className="mt-8">
          <button
            onClick={() => navigate('/onboarding/connect')}
            className="text-sm text-slate-400 hover:text-slate-600 transition-colors"
          >
            ← Back to connecting accounts
          </button>
        </div>
      </div>
    </div>
  );
};

export default OnboardingPricing;